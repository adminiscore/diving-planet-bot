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

logger = logging.getLogger("uvicorn.error")

RRF_K = 60


TOPIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("pricing", re.compile(r"\b(precio|precios|valor|cu[aá]nto cuesta|usd|d[oó]lares|pesos|cop)\b", re.IGNORECASE)),
    ("discount", re.compile(r"(?:10%|\bdescuento\b|\bdiscount\b|descuento\s*10|discount\s*10)", re.IGNORECASE)),
    ("availability", re.compile(r"\b(disponibilidad|cupos|hay cupo|available|availability|tomorrow|ma[nñ]ana)\b", re.IGNORECASE)),
    ("booking", re.compile(r"\b(reservar|reserva|reservas|reservo|reservamos|apartar|booking|book|p[aá]gina|web|online)\b", re.IGNORECASE)),
    ("meeting_point", re.compile(r"\b(punto de encuentro|muelle|bodeguita|gate|puerta|marina|todo mar)\b", re.IGNORECASE)),
    ("schedule", re.compile(r"\b(horario|hora|itinerario|schedule|duraci[oó]n|duration|regreso|return)\b", re.IGNORECASE)),
    ("reschedule", re.compile(r"\b(mover la fecha|cambiar la fecha|cambio de fecha|reprogramar|reagendar|move the date|change the date|reschedule)\b", re.IGNORECASE)),
    ("certification", re.compile(r"\b(certificaci[oó]n|certificado|open water|advanced|rescue|padi|ssi|logbook)\b", re.IGNORECASE)),
    ("refresher", re.compile(r"\b(refresh|refresher|refresh requirement|hace a[nñ]os no buceo|hace mucho no buceo|sin bucear|tiempo sin bucear)\b", re.IGNORECASE)),
    ("location_islands", re.compile(r"\b(isla|islas|rosario|isla grande|cocoliso|majagua|mulata|hotel)\b", re.IGNORECASE)),
    ("accommodation", re.compile(r"\b(alojamiento|accommodation|hotel|hospedaje|incluye alojamiento|is accommodation included)\b", re.IGNORECASE)),
    ("discount_colombian", re.compile(r"\b(colombian|colombiano|colombiana|colombianos|colombianas|residente)\b", re.IGNORECASE)),
    ("payment", re.compile(r"\b(pago|pagar|transferencia|qr|bancolombia|tarjeta|credit|pasarela|link de pago)\b", re.IGNORECASE)),
    ("forms_waiver", re.compile(r"\b(formulario|exoneraci[oó]n|jotform|carn[eé]|carne|certification photo|foto)\b", re.IGNORECASE)),
    ("equipment", re.compile(r"\b(equipo|equipment|incluye|include|insurance|seguro|qu[eé]\s+debo\s+llevar|qu[eé]\s+llevar|llevar|traer|bring|towel|toalla|bloqueador|sunscreen)\b", re.IGNORECASE)),
    ("depth", re.compile(r"\b(profundidad|metros|m\b|maxima|max\s+depth|depth)\b", re.IGNORECASE)),
    ("weather_cancellation", re.compile(r"\b(clima|weather|cancelaci[oó]n|reembolso|refund|pol[ií]tica)\b", re.IGNORECASE)),
    ("photos_media", re.compile(r"\b(foto|fotos|photos|video|videos)\b", re.IGNORECASE)),
    ("seasickness", re.compile(r"\b(mareo|sea sick|seasick|tabletas|pills)\b", re.IGNORECASE)),
]


def detect_query_topics(query: str) -> list[str]:
    detected: list[str] = []
    for name, pattern in TOPIC_PATTERNS:
        if pattern.search(query):
            detected.append(name)
    return detected


def source_weight_for_topics(source: str | None, topics: list[str]) -> float:
    if not source or not topics:
        return 0.0

    weights_by_topic: dict[str, dict[str, float]] = {
        "weather_cancellation": {"policies": 0.35, "faqs": 0.12, "conversations": 0.05, "services": 0.0},
        "meeting_point": {"conversations": 0.25, "faqs": 0.10, "policies": 0.0, "services": 0.0},
        "payment": {"conversations": 0.20, "faqs": 0.12, "policies": 0.05, "services": 0.0},
        "availability": {"conversations": 0.20, "faqs": 0.08, "services": 0.0, "policies": 0.0},
        "booking": {"faqs": 0.14, "policies": 0.12, "conversations": 0.08, "services": 0.0},
        "pricing": {"services": 0.18, "conversations": 0.10, "faqs": 0.08, "policies": 0.0},
        "discount": {"services": 0.12, "faqs": 0.10, "conversations": 0.06, "policies": 0.0},
        "equipment": {"faqs": 0.16, "conversations": 0.10, "services": 0.06, "policies": 0.0},
        "certification": {"faqs": 0.14, "conversations": 0.10, "services": 0.05, "policies": 0.0},
        "refresher": {"policies": 0.14, "faqs": 0.12, "conversations": 0.06, "services": 0.0},
        "schedule": {"faqs": 0.12, "conversations": 0.10, "services": 0.08, "policies": 0.0},
        "location_islands": {"faqs": 0.12, "conversations": 0.10, "services": 0.06, "policies": 0.0},
        "accommodation": {"faqs": 0.14, "conversations": 0.10, "services": 0.04, "policies": 0.0},
        "discount_colombian": {"conversations": 0.18, "faqs": 0.06, "services": 0.06, "policies": 0.0},
        "forms_waiver": {"conversations": 0.16, "faqs": 0.10, "policies": 0.02, "services": 0.0},
        "seasickness": {"faqs": 0.12, "conversations": 0.06, "services": 0.0, "policies": 0.0},
        "photos_media": {"conversations": 0.08, "faqs": 0.06, "services": 0.0, "policies": 0.0},
        "reschedule": {"policies": 0.18, "faqs": 0.12, "conversations": 0.06, "services": 0.0},
        "depth": {"faqs": 0.14, "conversations": 0.08, "services": 0.0, "policies": 0.0},
    }

    total = 0.0
    for t in topics:
        total += weights_by_topic.get(t, {}).get(source, 0.0)
    return total


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


def _reciprocal_rank_fusion(rankings: list[list[dict]], k: int = RRF_K) -> list[dict]:
    scores: dict[int, float] = {}
    doc_by_id: dict[int, dict] = {}

    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            doc_id = int(doc["id"])
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc_id in doc_by_id:
                doc_by_id[doc_id] = _merge_result(doc_by_id[doc_id], doc)
            else:
                doc_by_id[doc_id] = dict(doc)

    fused: list[dict] = []
    for doc_id, rrf_score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        doc = dict(doc_by_id[doc_id])
        confidence = max(
            float(doc.get("score_vector", 0.0) or 0.0),
            float(doc.get("score_bm25", 0.0) or 0.0),
        )
        doc["rrf_score"] = rrf_score
        doc["score_final"] = confidence + rrf_score
        fused.append(doc)
    return fused


def _apply_topic_and_source_boost(results: list[dict], query_topics: list[str]) -> list[dict]:
    reranked: list[dict] = []
    for doc in results:
        metadata = doc.get("metadata") or {}
        boost = 0.0
        doc_topics = metadata.get("topics") or []
        if query_topics and isinstance(doc_topics, list):
            overlap = set(query_topics) & {str(topic) for topic in doc_topics}
            if overlap:
                boost += 0.05 * len(overlap)

        if query_topics:
            source = metadata.get("source")
            boost += source_weight_for_topics(str(source) if source is not None else None, query_topics)

        reranked_doc = dict(doc)
        reranked_doc["score_boosted"] = float(doc.get("score_final", doc.get("score", 0.0)) or 0.0) + boost
        reranked_doc["score_final"] = reranked_doc["score_boosted"]
        reranked.append(reranked_doc)
    return reranked


async def _vector_search(query: str, lang: str = "es", k: int = 8) -> list[dict]:
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=query,
        )
        query_embedding = resp.data[0].embedding

        conn = await asyncpg.connect(settings.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata, 1 - (embedding <=> $1::vector) AS score
                FROM kb_documents
                WHERE metadata->>'lang' = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                str(query_embedding),
                lang,
                k,
            )
        finally:
            await conn.close()
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
    try:
        conn = await asyncpg.connect(settings.database_url)
        try:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata,
                       ts_rank_cd(content_tsv, plainto_tsquery('simple', $1)) AS score
                FROM kb_documents
                WHERE metadata->>'lang' = $2
                  AND content_tsv @@ plainto_tsquery('simple', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                lang,
                k,
            )
        finally:
            await conn.close()
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


async def search_knowledge_base(
    query: str,
    lang: str = "es",
    top_k: int | None = None,
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
    last_line = query.splitlines()[-1] if "\n" in query else query
    query_topics = detect_query_topics(last_line)
    candidate_limit = max(top_k * 6, top_k)

    vector_task = asyncio.create_task(_vector_search(query, lang=lang, k=candidate_limit))
    bm25_task = asyncio.create_task(_bm25_search(last_line, lang=lang, k=candidate_limit))
    vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)

    rankings = [ranking for ranking in (vector_results, bm25_results) if ranking]
    if not rankings:
        return []

    fused_results = _reciprocal_rank_fusion(rankings)
    reranked_results = _apply_topic_and_source_boost(fused_results, query_topics)
    reranked_results.sort(key=lambda result: result.get("score_final", result.get("score", 0.0)), reverse=True)

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
        f"[RAG][RETRIEVAL] query_topics={query_topics} candidates={len(reranked_results)} preview={top_meta}"
    )
    return reranked_results[:top_k]
