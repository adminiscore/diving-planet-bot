"""
Vector store interface for pgvector-based similarity search.

Retrieves relevant knowledge base documents by embedding the query
and performing cosine similarity search against stored embeddings.
"""

import asyncio
import json
import logging
import re

import asyncpg
from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")

RRF_K = 60
# RAG R1 (3-nov): cuánto pesa la rama de palabras en la fusión por posiciones frente al vector (1). Con «alguna palabra»
# trae más ruido que el vector; a la mitad, su primer puesto empata con el 3.º-4.º del vector.
PESO_PALABRAS = 0.5
# RAG R1: la rama de palabras con raíces del idioma del documento (`kb_v2._ddl`): «inmersiones» encuentra «inmersión».
CONFIG_DEL_IDIOMA = {"es": "spanish", "en": "english"}
# RAG R1: las marcas que pone el código al final de la consulta (`rag_agent`, el origen del cliente); no son palabras
# del cliente. La rama de palabras buscaba la marca en vez de la pregunta (R0, 3-nov).
_MARCA_DE_CONSULTA_RE = re.compile(r"^\[(?:origen_cliente|origin)\]=")

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> asyncpg.Pool:
    """Return a lazily-created shared asyncpg pool.

    A failed creation leaves ``_pool`` as None so the next call retries; the
    exception propagates to the caller's try/except (which degrades to []).
    """
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            # rag-2: las consultas sin esquema (`kb_documents`) resuelven a la base curada (`kb_v2.kb_documents`).
            server_settings = {"search_path": f"{settings.rag_kb_esquema},public"}
            _pool = await asyncpg.create_pool(
                settings.database_url, min_size=1, max_size=10, server_settings=server_settings
            )
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Public accessor for the shared pool (reused by rag_agent)."""
    return await _get_pool()


def excluded_sources() -> list[str]:
    """Fuentes del indice que la busqueda ignora (g-7: `settings.rag_exclude_sources`).

    Lista vacia por defecto: `x = ANY('{}')` es falso, asi que el filtro no quita nada y la
    busqueda es identica a la de siempre.
    """
    raw = settings.rag_exclude_sources or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _coerce_metadata(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _merge_result(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for field in ("score", "score_vector", "score_bm25", "score_bm25_raw"):
        existing_value = float(merged.get(field, 0.0) or 0.0)
        incoming_value = float(incoming.get(field, 0.0) or 0.0)
        if incoming_value > existing_value:
            merged[field] = incoming_value
    branches = set(merged.get("retrieval_branches", []))
    branches.update(incoming.get("retrieval_branches", []))
    merged["retrieval_branches"] = sorted(branches)
    return merged


def _reciprocal_rank_fusion(rankings: list[tuple[list[dict], float]], k: int = RRF_K) -> list[dict]:
    """La fusión por posiciones (RRF) de las ramas, cada una con su peso. RAG R1 (3-nov): la nota final es solo la de
    las posiciones. Antes era `max(coseno, palabras normalizadas) + RRF`, y como la palabra mejor puntuada vale siempre
    1,0, cualquier acierto de palabras tapaba a todo el vector (por eso «cualquier palabra» bajó de 86 a 65 %, 18-oct)."""
    scores: dict[int, float] = {}
    doc_by_id: dict[int, dict] = {}

    for ranking, peso in rankings:
        for rank, doc in enumerate(ranking):
            doc_id = int(doc["id"])
            scores[doc_id] = scores.get(doc_id, 0.0) + peso / (k + rank + 1)
            if doc_id in doc_by_id:
                doc_by_id[doc_id] = _merge_result(doc_by_id[doc_id], doc)
            else:
                doc_by_id[doc_id] = dict(doc)

    fused: list[dict] = []
    for doc_id, rrf_score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        doc = dict(doc_by_id[doc_id])
        doc["rrf_score"] = doc["score_final"] = rrf_score
        fused.append(doc)
    return fused


def texto_para_palabras(query: str) -> str:
    """Lo que busca la rama de palabras: la última línea de la consulta que no es una marca del código, sin tildes
    (la base guarda su texto sin tildes, `kb_v2`). La consulta puede traer delante los mensajes anteriores del cliente
    (`build_retrieval_query`): las palabras, solo de la pregunta de ahora."""
    lineas = [ln.strip() for ln in query.splitlines() if ln.strip() and not _MARCA_DE_CONSULTA_RE.match(ln.strip())]
    return strip_accents(lineas[-1] if lineas else query)


async def _vector_search(query: str, lang: str = "es", k: int = 8) -> list[dict]:
    try:
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        resp = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=query,
        )
        query_embedding = resp.data[0].embedding

        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata, 1 - (embedding <=> $1::vector) AS score
                FROM kb_documents
                WHERE metadata->>'lang' = $2
                  AND NOT (COALESCE(metadata->>'source', '') = ANY($4::text[]))
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                str(query_embedding),
                lang,
                k,
                excluded_sources(),
            )
    except Exception as exc:
        logger.info(f"[RAG][VECTOR] unavailable or failed: {exc}")
        return []

    results: list[dict] = []
    for row in rows:
        metadata = _coerce_metadata(row["metadata"])
        score = float(row["score"])
        results.append({
            "id": row["id"],
            "content": row["content"],
            "metadata": metadata,
            "score": score,
            "score_vector": score,
            "retrieval_branches": ["vector"],
        })
    return results


async def _bm25_search(query: str, lang: str = "es", k: int = 8) -> list[dict]:
    """RAG R1 (3-nov): con las raíces del idioma (`CONFIG_DEL_IDIOMA`, como guarda `kb_v2` el texto) y basta con
    ALGUNA palabra (las de `plainto_tsquery` unidas con `|`); antes, `'simple'` y todas las palabras: 48 de 51 preguntas
    sin resultado (g3/hallazgos, 18-oct). Las que coinciden en más palabras puntúan más (`ts_rank_cd`)."""
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata, ts_rank_cd(content_tsv, consulta.q) AS score
                FROM kb_documents,
                     (SELECT replace(plainto_tsquery($5::regconfig, $1)::text, '&', '|')::tsquery AS q) AS consulta
                WHERE metadata->>'lang' = $2
                  AND content_tsv @@ consulta.q
                  AND NOT (COALESCE(metadata->>'source', '') = ANY($4::text[]))
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                lang,
                k,
                excluded_sources(),
                CONFIG_DEL_IDIOMA.get(lang, "simple"),
            )
    except Exception as exc:
        logger.info(f"[RAG][BM25] unavailable or failed: {exc}")
        return []

    raw_scores = [float(row["score"]) for row in rows]
    max_score = max(raw_scores, default=0.0)
    results: list[dict] = []
    for row in rows:
        metadata = _coerce_metadata(row["metadata"])
        raw_score = float(row["score"])
        normalized_score = (raw_score / max_score) if max_score > 0 else 0.0
        results.append({
            "id": row["id"],
            "content": row["content"],
            "metadata": metadata,
            "score": normalized_score,
            "score_bm25": normalized_score,
            "score_bm25_raw": raw_score,
            "retrieval_branches": ["bm25"],
        })
    return results


# rag-3: cuanto baja una ficha del otro origen (score_final ~ similitud 0,3-0,8 + RRF): la saca del top-8 salvo que
# sea con mucho lo mas parecido a la pregunta (medido offline: las 10 fichas cruzadas salen y no se pierde ningun dato).
PENALIZACION_OTRO_ORIGEN = 0.15


def penalizar_otro_origen(results: list[dict], origin: str | None) -> list[dict]:
    """rag-3: baja los documentos cuyo `metadata.origin` (fichas de `kb_v2`: "cartagena" / "islas") no es el del
    cliente. Sin origen conocido, o en documentos sin origen (FAQs, politicas), no cambia nada."""
    if not origin:
        return results
    out = []
    for doc in results:
        doc_origin = (doc.get("metadata") or {}).get("origin")
        if doc_origin and doc_origin != origin:
            doc = dict(doc)
            doc["score_final"] = float(doc.get("score_final", doc.get("score", 0.0)) or 0.0) - PENALIZACION_OTRO_ORIGEN
        out.append(doc)
    return out


def _con_el_origen(ranking: list[dict], origin: str | None) -> list[dict]:
    """Una rama ordenada otra vez con la ficha del otro origen bajada (`penalizar_otro_origen` sobre su nota)."""
    if not origin:
        return ranking
    return sorted(penalizar_otro_origen([{**d, "score_final": d.get("score", 0.0)} for d in ranking], origin),
                  key=lambda d: d["score_final"], reverse=True)


async def search_knowledge_base(
    query: str,
    lang: str = "es",
    top_k: int | None = None,
    origin: str | None = None,
) -> list[dict]:
    """
    Embed the query and return the top_k most similar documents.

    Args:
        query: User's question.
        lang: Filter results by language (es/en).
        top_k: Number of results to return.

    Returns:
        List of dicts with 'content', 'metadata', and 'score'.
    """
    top_k = top_k or settings.rag_top_k
    candidate_limit = max(top_k * 6, top_k)

    vector_task = asyncio.create_task(_vector_search(query, lang=lang, k=candidate_limit))
    bm25_task = asyncio.create_task(_bm25_search(texto_para_palabras(query), lang=lang, k=candidate_limit))
    vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)

    # rag-2: con la base curada los empujones por tema/fuente (regex, ajustados para la base v1) enterraban las
    # politicas bajo FAQs genericas: sin ellos, el dato llega al top-8 un 85 % frente al 76 % (29-sep, 47
    # preguntas visibles de rag_piezas). Se ordena solo por vector + palabras (RRF). RAG R1: la ficha del otro origen
    # baja dentro de cada rama, antes de fusionar (la nota de la fusión es de posiciones, no de parecido).
    rankings = [(_con_el_origen(ranking, origin), peso)
                for ranking, peso in ((vector_results, 1.0), (bm25_results, PESO_PALABRAS)) if ranking]
    if not rankings:
        return []
    reranked_results = _reciprocal_rank_fusion(rankings)

    top_meta = [
        {
            "source": r.get("metadata", {}).get("source"),
            "id": r.get("id"),
            "score": round(r.get("score", 0.0), 4),
            "score_final": round(r.get("score_final", 0.0), 4),
            "branches": r.get("retrieval_branches", []),
        }
        for r in reranked_results[: min(len(reranked_results), 8)]
    ]
    logger.info(
        f"[RAG][RETRIEVAL] candidates={len(reranked_results)} preview={top_meta}"
    )
    from src.observability import apunta_busqueda  # lazy

    apunta_busqueda(reranked_results[:top_k])  # RAG R0: lo que trajo, con su clave, en [TURN_METRICS]
    return reranked_results[:top_k]
