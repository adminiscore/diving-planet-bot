# RAG / LLM — Mejoras pendientes (handoff post v0.16.2)

Este documento describe las mejoras pendientes al pipeline RAG y al uso del LLM del chatbot de Diving Planet. Está pensado para que cualquier desarrollador con acceso al repo pueda implementar cada fase de forma independiente, sin contexto previo de la sesión donde se planificó.

**Branch base sugerida**: partir de `feature/dev_alvaro` (tip `5fbb63d` o superior). Cada fase debería ir en una rama propia (`feature/rag-1.1-hybrid-search`, etc.) para poder revisarla y mergearla por separado.

---

## 0. Contexto: qué ya está hecho y qué falta

### Ya implementado (v0.16.2, commit `5fbb63d`)

1. **Prompt dedup**: el system prompt del RAG tenía dos secciones copy-pasteadas duplicadas en ES y EN. Quitadas.
2. **Brand tone dinámico desde JSON**: las reglas de tono ya no están hardcoded en `rag_agent.py`. Se leen al vuelo desde `data/knowledge_base/brand_tone.json` vía `build_system_prompt(lang)`.
3. **Few-shot examples**: cuando hay query de texto libre, se inyectan 1-2 ejemplos reales desde `data/knowledge_base/conversations.json` cuyos `extracted_topics` solapan con los topics detectados en la query.
4. **Hybrid retrieval compatible hacia atrás**: `vector_store.py` ya ejecuta búsqueda vectorial + BM25/FTS en paralelo, fusiona con RRF y mantiene el rerank por topics/source. Si la migración FTS aún no existe en la DB, degrada sin romper y sigue con vector search.
5. **Query rewriting multi-turno**: `rag_agent.py` ya condensa follow-ups cortos usando `src/agents/query_rewriter.py` antes de recuperar contexto.
6. **Grounding check post-respuesta**: `rag_agent.py` ya valida la respuesta generada con `src/agents/grounding_check.py` y cae a fallback si detecta una respuesta no sustentada por el contexto.
7. **Sub-chunking de servicios preparado**: `scripts/load_embeddings.py` ya genera chunks por resumen/itinerario/incluye/requisitos/precios con `parent_id`, y `rag_agent.py` ya expande summary parent cuando recupera un subchunk hijo.

### Falta por implementar (este documento)

| Fase | Descripción | Riesgo | Esfuerzo aprox. |
|---|---|---|---|
| **1.1** | Hybrid search BM25 + pgvector con Reciprocal Rank Fusion (RRF) | Implementado en código; pendiente aplicar migración SQL en entornos existentes | 15 min |
| **1.2** | Sub-chunking de `services.json` + parent-doc retrieval | Implementado en código; pendiente reindexar embeddings para poblar los nuevos subchunks | 15-30 min |
| **1.3** | Query rewriting / condensación de follow-ups multi-turno | Implementado | 0 |
| **2.1** | Grounding check post-respuesta (detectar hallucinations) | Implementado | 0 |

### Pendings operativos / revisión post-activación

- **Curación KB / review de pesos de rerank**: en algunas queries validadas end-to-end, el top doc sigue viniendo de `conversations.json` o `faqs.json` antes que de `services.json`. No es un bug por sí mismo, pero sí indica que el comportamiento final depende mucho de cómo esté curada la KB y de los pesos actuales de retrieval/rerank. Revisar si conviene:
  - reforzar `services.json` en temas donde debería ser fuente principal,
  - bajar peso relativo de `conversations` en ciertos topics,
  - o añadir reglas de priorización por `source` para intents concretos (pricing / service details / requirements).

- **Queries ultra-cortas ambiguas de hotel/lugar**: ya existe una heurística ligera previa al LLM para nombres sueltos de islas/hoteles del catálogo (`Pao Pao`, `Cocoliso`, `San Pedro de Majagua`, `Islabela`, `Bora Bora`, etc.). En esos casos el RAG pide aclaración breve en vez de inferir un plan concreto. Pendiente revisar más adelante si además conviene:
  - endurecer todavía más el prompt para no asumir actividad/plan en queries ambiguas fuera del catálogo,
  - o ampliar la misma lógica a otros nombres/location aliases que aparezcan en producción.

### Constraints heredados del plan original

- **Solo open-source / infra existente**: cero servicios pagos nuevos (sin Cohere Rerank, sin LangSmith Cloud, sin gpt-4o más caro). Usar Postgres FTS, pgvector y el `gpt-4o-mini` que ya está en uso.
- **Deadline original**: demo en <2 semanas desde el 2026-06-12. Si ya pasó, mantener el espíritu de "bajo riesgo, alto impacto".
- **No tocar**: el routing del supervisor entre tree/RAG/escalación. Ese funciona y está testeado.

---

## 1. Estado actual del pipeline RAG (recap rápido)

Para entender dónde entran las mejoras es útil tener el flujo claro:

```
Usuario escribe texto libre
   ↓
src/agents/supervisor.py decide: "es texto libre, va a RAG"
   ↓
rag_agent.rag_answer(query, lang, history, extra_context)
   ↓
   1. detect_pii() — corta si hay datos sensibles
   2. _canonical_food_answer() — short-circuit para preguntas de comida
   3. condense_query() — reescribe follow-ups cortos en pregunta standalone
   4. build_retrieval_query() — agrega contexto de history a la query
   5. search_knowledge_base() — busca con vector + BM25/FTS, fusiona con RRF
   6. _expand_with_parent_context() — suma el summary parent si llegó un subchunk hijo
   7. _answer_with_llm() — llama a gpt-4o-mini con system prompt + docs
   8. is_grounded() — verifica que la respuesta esté respaldada por el contexto
   ↓
Respuesta al usuario
```

### Archivos clave a conocer

- `src/agents/rag_agent.py` — pipeline RAG principal y construcción del prompt.
- `src/knowledge/vector_store.py` — búsqueda híbrida vector + BM25/FTS + RRF + topic/source boost.
- `src/knowledge/loader.py` — carga de archivos JSON de la KB.
- `scripts/load_embeddings.py` — script que indexa la KB en pgvector y ahora genera subchunks parent/child para `services.json`.
- `src/config.py` — configuración (modelo, dimensiones de embedding, top-K, threshold).
- `data/knowledge_base/` — los JSON: `services.json`, `faqs.json`, `policies.json`, `pricing.json`, `conversations.json`, `brand_tone.json`, `availability.json`, `escalation_rules.json`, `discounts.json`.
- `tests/test_rag_safety.py` — tests de seguridad y comportamiento del RAG.
- `tests/test_retrieval_rerank.py` — tests del rerank y topic detection.
- `migrations/001_add_fts_to_kb_documents.sql` — migración para habilitar `content_tsv` e índice GIN.

### Modelo y parámetros (en `src/config.py`)

- **LLM**: `gpt-4o-mini` (OpenAI).
- **Embeddings**: `text-embedding-3-small`, dimensionalidad 1536.
- **Top-K**: 8 docs por defecto.
- **Threshold mínimo**: 0.40 score normalizado.
- **Similitud**: cosine (vía pgvector `<=>` operator: `1 - distance`).

### Tabla en Postgres

La tabla `kb_documents` (nombre exacto según `vector_store.py`) tiene típicamente:
- `id` — primary key
- `source` — string (`services`, `faqs`, `policies`, `pricing`, `conversations`, etc.)
- `lang` — `es` o `en`
- `content` — el texto del documento
- `metadata` — JSONB con info adicional (key/index, topics, origin, etc.)
- `embedding` — vector de dimensión 1536

Verifica el schema exacto con `\d kb_documents` antes de tocar.

---

## 2. Fase 1.1 — Hybrid search (BM25 + vector) con Reciprocal Rank Fusion

### Por qué

El retrieval actual usa **solo embeddings vectoriales**. Esto funciona bien para preguntas semánticas ("qué pasa si llueve?") pero **falla para términos exactos**:

- Nombres propios de hoteles: `Pao Pao`, `San Pedro de Majagua`, `Coralina`.
- Precios concretos: `$178`, `630000 COP`.
- Códigos / referencias: `Open Water`, `Advanced`, `Bubble Makers`.

Los embeddings difunden la semántica del texto y a veces no privilegian la coincidencia léxica exacta. La solución estándar en producción es combinar **vectorial (denso) + BM25 (sparse)** y fusionar los rankings.

### Qué vamos a hacer

1. Añadir full-text search nativo de Postgres (`tsvector` + `tsquery`) sobre la columna `content`.
2. Ejecutar **dos búsquedas en paralelo** (vectorial y BM25), pedir top-K=12 de cada una.
3. Fusionar los rankings con **Reciprocal Rank Fusion (RRF)**: `score(doc) = Σ_i 1 / (k + rank_i)` donde `k=60` (default literatura) y `rank_i` es el ranking del doc en la búsqueda `i` (vectorial o BM25).
4. Mantener el `topic_boost + source_weight` existente como **segundo nivel de rerank** sobre los candidatos fusionados.

**No añadimos dependencias**: Postgres FTS está incluido en cualquier instalación estándar. RRF se implementa en 20 líneas de Python.

### Implementación paso a paso

#### 1.1.1 Migración de base de datos

Crear archivo `migrations/001_add_fts_to_kb_documents.sql` (o el directorio que use el proyecto — verificar si ya hay carpeta `migrations/`).

```sql
-- Add a stored, auto-updated tsvector column.
-- Uses 'simple' config so it preserves casing of brand/hotel names and prices
-- (Spanish stemming would strip plural endings and decimal points).
ALTER TABLE kb_documents
ADD COLUMN content_tsv tsvector
GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED;

-- GIN index for fast full-text search.
CREATE INDEX IF NOT EXISTS kb_documents_content_tsv_idx
ON kb_documents USING GIN (content_tsv);
```

Ejecutar manualmente o desde el script que el proyecto use para migraciones. Si no existe sistema de migraciones, documentar el SQL en el README y aplicarlo una vez.

**Importante**: la columna es `GENERATED ALWAYS ... STORED`, así que se actualiza sola cuando se inserta o modifica un doc. No hay que tocar `load_embeddings.py` para esto.

#### 1.1.2 Función `_bm25_search` en `vector_store.py`

Localizar la función `search_knowledge_base` (alrededor de la línea 100+). Añadir antes:

```python
async def _bm25_search(query: str, lang: str, k: int = 12) -> list[dict]:
    """BM25-like full-text search using Postgres ts_rank_cd over content_tsv.

    Returns rows in the same shape as the vector search: {id, source, lang, content, metadata, score}
    where score is the ts_rank_cd value (NOT normalized).
    """
    conn = await asyncpg.connect(settings.database_url)
    try:
        # Build a tsquery from the user input. Use plainto_tsquery for safety
        # (it escapes punctuation and joins terms with AND).
        rows = await conn.fetch(
            """
            SELECT id, source, lang, content, metadata,
                   ts_rank_cd(content_tsv, plainto_tsquery('simple', $1)) AS score
            FROM kb_documents
            WHERE lang = $2
              AND content_tsv @@ plainto_tsquery('simple', $1)
            ORDER BY score DESC
            LIMIT $3
            """,
            query, lang, k,
        )
    finally:
        await conn.close()
    return [dict(r) for r in rows]
```

#### 1.1.3 Fusión RRF en `search_knowledge_base`

La función actual ejecuta solo el path vectorial. Reescribirla así (pseudocódigo, ajustar a la implementación real del repo):

```python
RRF_K = 60  # standard parameter from RRF paper

def _reciprocal_rank_fusion(
    rankings: list[list[dict]],
    k: int = RRF_K,
) -> list[dict]:
    """Fuse multiple ranked lists into one using Reciprocal Rank Fusion.

    Each input list should be ordered by relevance (best first). Documents are
    identified by their 'id' field. Returns a new list ordered by RRF score.
    """
    scores: dict[int, float] = {}
    doc_by_id: dict[int, dict] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            # Keep the doc payload from whichever list we saw it in first.
            doc_by_id.setdefault(doc_id, doc)

    fused = []
    for doc_id, rrf_score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        doc = dict(doc_by_id[doc_id])
        doc["rrf_score"] = rrf_score
        fused.append(doc)
    return fused


async def search_knowledge_base(query: str, lang: str = "es", top_k: int = None) -> list[dict]:
    top_k = top_k or settings.rag_top_k
    fetch_k = top_k * 2  # over-fetch from each branch so RRF has material to work with

    # Run both searches in parallel.
    vec_task = asyncio.create_task(_vector_search(query, lang, k=fetch_k))
    bm25_task = asyncio.create_task(_bm25_search(query, lang, k=fetch_k))
    vec_results, bm25_results = await asyncio.gather(vec_task, bm25_task)

    # Fuse rankings with RRF.
    fused = _reciprocal_rank_fusion([vec_results, bm25_results])

    # Apply the existing topic-boost + source-weight as a second-stage rerank.
    # Reuse the helpers already in vector_store.py (detect_query_topics,
    # source_weight_for_topics) on the fused candidates.
    reranked = _apply_topic_and_source_boost(fused, query, lang)

    # Trim to top_k and apply the existing threshold.
    return [d for d in reranked[:top_k] if d.get("final_score", 0) >= settings.rag_min_score]
```

**Detalles importantes**:
- La función `_vector_search` debe extraerse del cuerpo actual de `search_knowledge_base` para que la fusión sea clara.
- El `topic_boost + source_weight` actual (líneas 130-145 del `vector_store.py`) sigue siendo valioso porque codifica conocimiento de dominio (p.ej. `weather_cancellation → policies = 0.35`). Mantenerlo como segundo paso de rerank.
- El threshold final debe aplicarse sobre el score combinado, no sobre el cosine raw. Probablemente haya que recalibrar el `0.40` actual — empezar con `0.05` para el rrf_score y ajustar tras smoke test.

#### 1.1.4 Tests

Añadir a `tests/test_retrieval_rerank.py`:

```python
def test_rrf_fuses_two_rankings_preserves_top_overlap():
    """Documents that appear in BOTH rankings should rank above singles."""
    vec = [{"id": 1, "content": "A"}, {"id": 2, "content": "B"}, {"id": 3, "content": "C"}]
    bm25 = [{"id": 3, "content": "C"}, {"id": 1, "content": "A"}, {"id": 4, "content": "D"}]
    fused = _reciprocal_rank_fusion([vec, bm25])
    ids = [d["id"] for d in fused]
    # 1 and 3 appear in both lists, so they should be first.
    assert set(ids[:2]) == {1, 3}


@pytest.mark.asyncio
async def test_hybrid_retrieval_finds_lexical_exact_match(monkeypatch):
    """A query with a proper noun should retrieve the relevant doc via BM25 even
    when the vector branch ranks it low.
    """
    # Mock _vector_search to return irrelevant docs and _bm25_search to return the right one.
    # Verify the hotel doc surfaces in the top results.
    ...
```

#### 1.1.5 Verificación end-to-end

Crear un set de 5-10 queries léxicas exactas (`"Pao Pao recogida"`, `"$178 dos buceos"`, `"Bubble Makers edad"`) y comparar respuestas antes y después de aplicar 1.1. Esperado: queries que antes devolvían el fallback ahora encuentran el doc relevante.

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `plainto_tsquery` con tildes o ñ puede comportarse raro | Usar `'simple'` config (sin stemming) y probar con queries reales en ES |
| Threshold mal calibrado tras la fusión | Empezar muy permisivo (0.01) y subir iterativamente, loguear scores |
| Latencia: dos búsquedas en paralelo | Asyncio.gather las hace concurrentes, sin coste si el DB tiene buen pool |
| Index GIN ocupa espacio | Aceptable para una KB de <1MB de texto |

---

## 3. Fase 1.2 — Sub-chunking de `services.json` + parent-doc retrieval

### Por qué

Hoy cada servicio (`2_dives_1_day`, `open_water`, etc.) se indexa como **un solo chunk gigante** que contiene:
- Descripción
- Itinerario completo (array de pasos)
- Lista de "incluye"
- Lista de "no incluye"
- Lista de requisitos
- Precios en USD y COP, normal y online

Cuando un cliente pregunta "¿qué incluye el 2 buceos?", el embedding del chunk completo es ambiguo: mezcla incluye + itinerario + precios. La precisión cae respecto a una búsqueda donde el chunk sea **solo** la sección "incluye".

### Qué vamos a hacer

Patrón **small-to-big retrieval** (también llamado **parent-doc retrieval**, de LangChain/LlamaIndex):

1. **Indexar fino**: por cada servicio, generar 4-6 sub-chunks pequeños y específicos, cada uno con su propio embedding optimizado para ese subtópico.
2. **Recuperar fino**: el retrieval encuentra el sub-chunk relevante (mejor match semántico).
3. **Expandir grueso**: al pasar al LLM, además del sub-chunk se le da contexto del padre (la sección `:summary` del mismo service) para que tenga el panorama.

Esto **no requiere parent-doc database separada**: usamos `metadata.parent_id` para encadenar.

### Implementación paso a paso

#### 1.2.1 Cambios en `scripts/load_embeddings.py`

Localizar la función que indexa `services.json` (busca "services" en el script). Reemplazar el chunk único por sub-chunks:

```python
def _service_subchunks(service_id: str, service: dict, lang: str) -> list[dict]:
    """Generate fine-grained chunks for a single service entry.

    Each chunk has a 'parent_id' pointing back to the service summary chunk
    so the RAG agent can expand context at query time.
    """
    name = service.get(f"name_{lang}", "")
    desc = service.get(f"description_{lang}", "")
    base_meta = {"service_id": service_id, "lang": lang, "parent_id": f"{service_id}:summary"}

    chunks = []

    # 1. Summary (description + name + role): used as parent context.
    chunks.append({
        "key": f"{service_id}:summary",
        "content": f"{name}\n\n{desc}",
        "metadata": {**base_meta, "subtype": "summary"},
    })

    # 2. Itinerary
    itinerary = service.get(f"itinerary_{lang}", [])
    if itinerary:
        chunks.append({
            "key": f"{service_id}:itinerary",
            "content": f"Itinerario de {name}:\n" + "\n".join(f"- {step}" for step in itinerary),
            "metadata": {**base_meta, "subtype": "itinerary"},
        })

    # 3. Included
    included = service.get(f"included_{lang}", [])
    not_included = service.get(f"not_included_{lang}", [])
    if included or not_included:
        body = f"Que incluye {name}:\n" + "\n".join(f"- {it}" for it in included)
        if not_included:
            body += f"\n\nQue NO incluye:\n" + "\n".join(f"- {it}" for it in not_included)
        chunks.append({
            "key": f"{service_id}:included",
            "content": body,
            "metadata": {**base_meta, "subtype": "included"},
        })

    # 4. Requirements
    requirements = service.get(f"requirements_{lang}", [])
    if requirements:
        chunks.append({
            "key": f"{service_id}:requirements",
            "content": f"Requisitos para {name}:\n" + "\n".join(f"- {r}" for r in requirements),
            "metadata": {**base_meta, "subtype": "requirements"},
        })

    # 5. Pricing
    price_parts = []
    if service.get("price_usd"):
        price_parts.append(f"Precio USD (online): ${service['price_usd']}")
    if service.get("price_usd_normal"):
        price_parts.append(f"Precio USD (normal): ${service['price_usd_normal']}")
    if service.get("price_cop"):
        price_parts.append(f"Precio COP (online): ${service['price_cop']:,}")
    if service.get("price_cop_normal"):
        price_parts.append(f"Precio COP (normal): ${service['price_cop_normal']:,}")
    if price_parts:
        chunks.append({
            "key": f"{service_id}:pricing",
            "content": f"Precios de {name}:\n" + "\n".join(price_parts),
            "metadata": {**base_meta, "subtype": "pricing"},
        })

    return chunks
```

Cambiar el lugar donde se itera sobre services para llamar a esta función y obtener sub-chunks.

**Verificación**: tras re-index, `SELECT COUNT(*) FROM kb_documents WHERE source = 'services'` debe pasar de ~70 (35 servicios × 2 idiomas) a ~300-400 (35 × ~5 sub-chunks × 2 idiomas).

#### 1.2.2 Función `_expand_with_parent_context` en `rag_agent.py`

Añadir helper que, dado un hit de sub-chunk, busca el `:summary` correspondiente y lo añade al contexto:

```python
async def _expand_with_parent_context(docs: list[dict], lang: str) -> list[dict]:
    """If any retrieved doc is a sub-chunk with parent_id, fetch the parent
    summary chunk and prepend it so the LLM has wider context.

    Returns a new list; doesn't mutate input.
    """
    parent_ids_needed = set()
    for doc in docs:
        parent_id = (doc.get("metadata") or {}).get("parent_id")
        if parent_id and parent_id != (doc.get("metadata") or {}).get("key"):
            parent_ids_needed.add(parent_id)

    if not parent_ids_needed:
        return docs

    # Single DB call to fetch all needed parents at once.
    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT id, source, lang, content, metadata
            FROM kb_documents
            WHERE lang = $1
              AND metadata->>'key' = ANY($2::text[])
            """,
            lang, list(parent_ids_needed),
        )
    finally:
        await conn.close()

    parents = [dict(r) for r in rows]
    # Put parents first so they set context, then the more specific sub-chunks.
    return parents + docs
```

Integrar en `rag_answer`:

```python
docs = await search_knowledge_base(safe_query, lang=lang)
docs = await _expand_with_parent_context(docs, lang)  # NEW
# ... continúa con el flujo normal
```

#### 1.2.3 Tests

Añadir a `tests/test_rag_safety.py`:

```python
def test_parent_doc_expansion_loads_summary_for_subchunk(monkeypatch):
    """A retrieved :itinerary chunk should trigger fetching its :summary parent."""
    # Mock search_knowledge_base to return a fake :itinerary sub-chunk with parent_id.
    # Mock the DB call inside _expand_with_parent_context to return the summary.
    # Assert that the final context passed to the LLM contains BOTH chunks.
    ...


def test_parent_doc_expansion_skips_when_no_parent_id():
    """Docs without parent_id (e.g. policies) should not trigger extra DB calls."""
    ...
```

#### 1.2.4 Verificación end-to-end

Set de queries que antes funcionaban mal con el chunk gigante:
- "¿Qué incluye el 5 buceos?" — antes traía requisitos + itinerario + precio mezclados; ahora debería traer solo `:included` + el `:summary` como contexto.
- "¿Cuánto tarda el Open Water?" — el sub-chunk `:itinerary` debería ganar.
- "¿Precio del minicurso para colombianos?" — `:pricing` debería ganar.

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Re-indexación rompe respuestas que hoy funcionan bien | **Backup**: `pg_dump kb_documents > backup.sql` antes de re-indexar. Rollback es restore + revertir el commit. |
| El número de chunks crece 5x → coste de embeddings al re-indexar | Una sola vez. Los servicios son ~35 entradas; total ~$0.05 con `text-embedding-3-small`. |
| Sub-chunks de pricing pueden devolver precios obsoletos | Los precios están en `pricing.json` y `services.json` — verificar que la fuente sigue siendo correcta. |
| `_expand_with_parent_context` añade latencia (1 query DB) | Una sola query para todos los parents. Esperado: +50-100ms. |

---

## 4. Fase 1.3 — Query rewriting (condensación de follow-ups)

### Por qué

Conversaciones reales tienen este patrón:

```
Cliente: ¿Cuánto cuesta el minicurso?
Bot: $183 USD por persona reservando online.
Cliente: ¿Y los niños?
```

El último mensaje del cliente, **"¿Y los niños?"**, se le pasa al retrieval tal cual. Sin contexto, los embeddings de "y los niños?" no van a encontrar nada útil. El bot acaba en fallback o respondiendo algo genérico.

La solución estándar: antes de retrieval, hacer una **llamada corta al LLM** que reescribe el último mensaje como una **pregunta independiente y completa**:

> "¿Y los niños?" + historial sobre precio del minicurso → "¿Cuánto cuesta el minicurso para niños?"

Esto multiplica el recall en follow-ups por 3-4x según benchmarks de LangChain/LlamaIndex.

### Qué vamos a hacer

Crear módulo `src/agents/query_rewriter.py` con función `condense_query` que:

1. **Solo activa si el query es corto y hay historial** (<8 palabras, ≥2 mensajes previos). Si el query ya es autosuficiente, no llama al LLM (ahorra coste).
2. Llama a `gpt-4o-mini` con un prompt mínimo: system de ~150 tokens, últimos 4 turnos.
3. `temperature=0`, `max_tokens=80`. Es determinista y barato.
4. Devuelve la pregunta reescrita.

El original query se mantiene para mostrar al usuario en logs / debugging.

### Implementación paso a paso

#### 1.3.1 Módulo nuevo `src/agents/query_rewriter.py`

```python
"""
Query rewriter / condensador de follow-ups multi-turno.

Cuando el cliente hace un follow-up corto ("y los ninos?", "y el precio?"),
el retrieval pierde el contexto. Este modulo usa el LLM para reescribir el
ultimo mensaje como una pregunta independiente antes de pasarla al retrieval.
"""

import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("uvicorn.error")

_REWRITE_PROMPT_ES = (
    "Eres un reescritor de preguntas. Dada una conversacion entre un cliente "
    "y un asesor, reescribe la ULTIMA pregunta del cliente como una pregunta "
    "independiente y completa que pueda entenderse sin el contexto previo. "
    "Si la pregunta ya es autosuficiente, devuelvela sin cambios. "
    "Responde SOLO con la pregunta reescrita, sin prefijos ni explicaciones."
)

_REWRITE_PROMPT_EN = (
    "You are a question rewriter. Given a conversation between a customer "
    "and an advisor, rewrite the customer's LAST question as a standalone, "
    "self-contained question that can be understood without prior context. "
    "If the question is already self-contained, return it unchanged. "
    "Respond ONLY with the rewritten question, no prefixes or explanations."
)


def _should_condense(query: str, history: list[dict] | None) -> bool:
    """Decide whether to call the LLM at all.

    Skip if:
    - query is long enough to likely be self-contained
    - there's not enough history to provide context
    """
    if not query or not history:
        return False
    if len(query.split()) >= 8:
        return False
    user_msgs = [m for m in history if m.get("role") == "user"]
    if len(user_msgs) < 2:
        return False
    return True


def _format_history_for_prompt(history: list[dict], max_turns: int = 4) -> str:
    """Render the last N turns as 'Cliente: ...' / 'Asesor: ...' lines."""
    lines = []
    for msg in history[-max_turns:]:
        role = "Cliente" if msg.get("role") == "user" else "Asesor"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def condense_query(
    query: str,
    history: list[dict] | None = None,
    lang: str = "es",
) -> str:
    """Rewrite a follow-up query as a standalone question if needed.

    Returns the original query unchanged when:
    - the heuristic decides condensation is not worth the LLM call
    - the LLM call fails for any reason

    Never raises.
    """
    if not _should_condense(query, history):
        return query

    system = _REWRITE_PROMPT_ES if lang == "es" else _REWRITE_PROMPT_EN
    history_block = _format_history_for_prompt(history or [])

    user_content = (
        f"Conversacion previa:\n{history_block}\n\n"
        f"Pregunta a reescribir: {query}"
        if lang == "es"
        else
        f"Prior conversation:\n{history_block}\n\n"
        f"Question to rewrite: {query}"
    )

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=80,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        if not rewritten:
            return query
        logger.info(
            f"[RAG][REWRITE] original={query[:40]}... rewritten={rewritten[:60]}..."
        )
        return rewritten
    except Exception as e:
        logger.warning(f"[RAG][REWRITE] failed, using original query: {e}")
        return query
```

#### 1.3.2 Integración en `rag_agent.py`

Localizar `rag_answer` y la línea donde se llama `build_retrieval_query` (sobre la línea 240). Añadir antes:

```python
from src.agents.query_rewriter import condense_query
# ...

async def rag_answer(query, lang, history, extra_context):
    # ... PII check, food short-circuit ...

    # NEW: condense follow-up queries.
    condensed = await condense_query(query, history=history, lang=lang)

    retrieval_query = build_retrieval_query(condensed, history)
    # ... resto del flujo igual ...
```

**Importante**: usar `condensed` solo para retrieval. La query original se sigue pasando al `_answer_with_llm` para que el modelo vea exactamente lo que el cliente escribió.

#### 1.3.3 Tests

Añadir a `tests/test_rag_safety.py`:

```python
@pytest.mark.asyncio
async def test_query_rewriter_condenses_short_follow_up(monkeypatch):
    from src.agents import query_rewriter

    # Mock the LLM call.
    captured = {}
    async def fake_create(**kwargs):
        captured["messages"] = kwargs.get("messages")
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "Cuanto cuesta el minicurso para ninos?"})})]})()

    class FakeOpenAI:
        def __init__(self, **k): pass
        chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(fake_create)})})

    monkeypatch.setattr(query_rewriter, "AsyncOpenAI", FakeOpenAI)

    history = [
        {"role": "user", "content": "Cuanto cuesta el minicurso?"},
        {"role": "assistant", "content": "$183 USD por persona."},
    ]
    result = await query_rewriter.condense_query("y los ninos?", history=history, lang="es")
    assert "ninos" in result.lower() and "minicurso" in result.lower()


@pytest.mark.asyncio
async def test_query_rewriter_skips_long_query():
    from src.agents import query_rewriter
    long_q = "Hola buenos dias me gustaria saber cuanto cuesta el plan de dos buceos para manana por la manana"
    result = await query_rewriter.condense_query(long_q, history=[{"role": "user", "content": "hola"}], lang="es")
    assert result == long_q  # no rewriting


@pytest.mark.asyncio
async def test_query_rewriter_returns_original_on_llm_error(monkeypatch):
    """If the LLM call fails, we should return the original query, not raise."""
    from src.agents import query_rewriter

    class BrokenOpenAI:
        def __init__(self, **k): pass
        chat = type("Chat", (), {"completions": type("Comp", (), {
            "create": staticmethod(lambda **k: (_ for _ in ()).throw(RuntimeError("API down")))
        })})

    monkeypatch.setattr(query_rewriter, "AsyncOpenAI", BrokenOpenAI)
    result = await query_rewriter.condense_query("y los ninos?", history=[
        {"role": "user", "content": "minicurso?"},
        {"role": "assistant", "content": "OK"},
    ], lang="es")
    assert result == "y los ninos?"
```

#### 1.3.4 Verificación end-to-end

Conversación manual en Chatwoot:
1. "¿Cuánto cuesta el minicurso?" → bot responde precio.
2. "¿Y los niños?" → con rewriting debe entender que pregunta por precio del minicurso para niños.

Logs deberían mostrar:
```
[RAG][REWRITE] original=y los ninos?... rewritten=cuanto cuesta el minicurso para ninos...
```

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El LLM reescribe mal y pierde la intención original | Heurística conservadora: solo activa si query <8 palabras + history ≥2 turnos. Loguear ambas versiones para debugging. |
| Latencia extra (~300-500ms) | Solo en follow-ups cortos, no en cada query. Si el demo aprieta, se puede desactivar con un flag. |
| Coste extra (~$0.0001 por follow-up) | Despreciable comparado con el RAG call principal. |

---

## 5. Fase 2.1 — Grounding check post-respuesta

### Por qué

Aunque el system prompt dice "responde SOLO con la información del contexto", `gpt-4o-mini` a veces:
- Inventa precios cercanos pero no exactos (p.ej. "$180" cuando el real es "$178").
- Combina información de diferentes contextos.
- Añade detalles plausibles pero no presentes en el contexto.

Para una demo en producción esto es **el peor riesgo**. Un cliente que recibe "$180 USD" cuando es "$178" y reserva en otro centro pierde confianza.

La técnica estándar (Self-RAG / verification step) es: **después de generar la respuesta, hacer una segunda llamada al LLM** que verifica si la respuesta usa solo información del contexto. Si detecta hallucination, devolvemos el fallback en lugar de la respuesta inventada.

### Qué vamos a hacer

Crear módulo `src/agents/grounding_check.py` con función `is_grounded` que:

1. Recibe la respuesta generada y el contexto que se le dio al LLM.
2. Llama a `gpt-4o-mini` con un prompt explícito de verificación.
3. `temperature=0`, `max_tokens=30`. Determinista y barato.
4. Devuelve `(grounded: bool, reason: str)`.

Si `grounded=False`, `rag_answer` devuelve el fallback canónico en lugar de la respuesta no verificada.

**Bypass**: si la respuesta es exactamente el `FALLBACK_*`, no se chequea (no añade nada nuevo, no puede tener hallucinations).

### Implementación paso a paso

#### 2.1.1 Módulo nuevo `src/agents/grounding_check.py`

```python
"""
Grounding check post-respuesta.

Verifica que la respuesta generada por el RAG use exclusivamente informacion
presente en el contexto. Si detecta hallucinations, el caller debe usar el
fallback canonico en lugar de la respuesta inventada.
"""

import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("uvicorn.error")

_VERIFY_PROMPT_ES = """Verifica si la RESPUESTA esta totalmente basada en el CONTEXTO proporcionado.

Reglas:
- "GROUNDED" si cada afirmacion factual de la respuesta (precios, horarios, requisitos, nombres, fechas) aparece literalmente o se infiere directamente del contexto.
- "HALLUCINATED" si la respuesta incluye CUALQUIER dato factual (precios, horarios, requisitos, nombres) que NO este en el contexto.
- Frases de cortesia, ofrecimientos genericos ("te paso con un asesor", "estamos aqui para ayudarte") y reformulaciones del contexto SON aceptables.
- Frases promocionales SIN datos concretos tambien son aceptables.

Responde con UNA palabra: GROUNDED o HALLUCINATED."""

_VERIFY_PROMPT_EN = """Verify whether the RESPONSE is fully based on the provided CONTEXT.

Rules:
- "GROUNDED" if every factual claim in the response (prices, schedules, requirements, names, dates) appears literally or directly inferable from the context.
- "HALLUCINATED" if the response includes ANY factual data (prices, schedules, requirements, names) NOT in the context.
- Politeness, generic offers ("I'll connect you with an advisor", "we're here to help") and rewordings of context are acceptable.
- Promotional phrases WITHOUT concrete data are also acceptable.

Reply with ONE word: GROUNDED or HALLUCINATED."""


async def is_grounded(
    response: str,
    context: str,
    lang: str = "es",
) -> tuple[bool, str]:
    """Check if a response is grounded in the given context.

    Returns (grounded, reason). On any error, returns (True, "verifier_failed")
    to fail-open — better to send a potentially-iffy response than to block
    legitimate answers due to a verifier outage.
    """
    if not response or not context:
        return True, "empty_input"

    system = _VERIFY_PROMPT_ES if lang == "es" else _VERIFY_PROMPT_EN
    user_content = f"CONTEXTO:\n{context}\n\nRESPUESTA:\n{response}"

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        result = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=30,
        )
        verdict = (result.choices[0].message.content or "").strip().upper()
        grounded = "GROUNDED" in verdict and "HALLUCINATED" not in verdict
        logger.info(
            f"[RAG][GROUNDING] verdict={verdict[:30]} grounded={grounded} "
            f"response_preview={response[:60]}..."
        )
        return grounded, verdict
    except Exception as e:
        logger.warning(f"[RAG][GROUNDING] verifier failed, failing open: {e}")
        return True, "verifier_failed"
```

#### 2.1.2 Integración en `rag_agent.py`

En `rag_answer`, después de generar la respuesta:

```python
from src.agents.grounding_check import is_grounded
# ...

# After _answer_with_llm returns the response:
answer = await _answer_with_llm(context, context_sources)

# Skip the check for fallback responses (nothing to verify).
if answer.strip() not in (FALLBACK_ES.strip(), FALLBACK_EN.strip()):
    grounded, verdict = await is_grounded(answer, context, lang=lang)
    if not grounded:
        logger.warning(
            f"[RAG] Response flagged as hallucinated, using fallback. "
            f"query={query[:40]} verdict={verdict}"
        )
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

return answer
```

#### 2.1.3 Tests

```python
@pytest.mark.asyncio
async def test_grounding_check_passes_when_response_is_grounded(monkeypatch):
    from src.agents import grounding_check

    async def fake_create(**kwargs):
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "GROUNDED"})})]})()

    class FakeOpenAI:
        def __init__(self, **k): pass
        chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(fake_create)})})

    monkeypatch.setattr(grounding_check, "AsyncOpenAI", FakeOpenAI)
    grounded, _ = await grounding_check.is_grounded(
        response="El minicurso cuesta $183 USD.",
        context="Precio del minicurso: $183 USD reservando online.",
        lang="es",
    )
    assert grounded is True


@pytest.mark.asyncio
async def test_grounding_check_rejects_hallucinated_price(monkeypatch):
    from src.agents import grounding_check

    async def fake_create(**kwargs):
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "HALLUCINATED — el precio no aparece en el contexto"})})]})()

    class FakeOpenAI:
        def __init__(self, **k): pass
        chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(fake_create)})})

    monkeypatch.setattr(grounding_check, "AsyncOpenAI", FakeOpenAI)
    grounded, _ = await grounding_check.is_grounded(
        response="El minicurso cuesta $999 USD.",
        context="Plan para principiantes en Cartagena.",
        lang="es",
    )
    assert grounded is False


@pytest.mark.asyncio
async def test_grounding_check_fails_open_on_error(monkeypatch):
    """If the verifier LLM fails, don't block — return grounded=True."""
    from src.agents import grounding_check

    class BrokenOpenAI:
        def __init__(self, **k): pass
        chat = type("Chat", (), {"completions": type("Comp", (), {
            "create": staticmethod(lambda **k: (_ for _ in ()).throw(RuntimeError("verifier down")))
        })})

    monkeypatch.setattr(grounding_check, "AsyncOpenAI", BrokenOpenAI)
    grounded, reason = await grounding_check.is_grounded("anything", "anything", "es")
    assert grounded is True
    assert reason == "verifier_failed"


@pytest.mark.asyncio
async def test_rag_returns_fallback_when_hallucinated(monkeypatch):
    """End-to-end: if the grounding check flags hallucination, rag_answer returns fallback."""
    # Mock the search to return a doc and the LLM to return a confident answer.
    # Mock is_grounded to return False.
    # Assert rag_answer returns FALLBACK_ES (or EN).
    ...
```

#### 2.1.4 Verificación end-to-end

Hacer un experimento manual:
1. Buscar una pregunta donde la KB no tenga el dato exacto pero pueda generar respuesta plausible (p.ej. preguntar por un hotel que no esté en la KB).
2. Confirmar que antes del check el bot inventa algo razonable; con el check activo, devuelve el fallback.

Loguear cada rechazo durante la primera semana para revisar falsos positivos.

### Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El verificador rechaza respuestas correctas (false positives) | Prompt del verifier explícito sobre qué es aceptable (cortesía, reformulaciones). Loguear cada rechazo para revisar manualmente. |
| Doble latencia (LLM principal + verifier) | El verifier es muy corto (max_tokens=30). Esperado: +300-600ms. Si latencia es crítica, considerar bypass cuando top retrieval score > 0.7 (alta confianza). |
| Coste por llamada | gpt-4o-mini cobra ~$0.15/1M tokens. Una respuesta del bot ~500 tokens + verifier ~100 tokens = costo despreciable. |
| Verifier rompe en producción | Función `is_grounded` falla **fail-open** (devuelve True ante cualquier excepción). Logging para detectar y monitorear. |

---

## 6. Orden recomendado de implementación

Cada fase es independiente. Sugerencia de orden por relación impacto/riesgo:

1. **Fase 1.3 (query rewriting)** — más barato, más impacto, sin tocar DB. Hacer primero.
2. **Fase 2.1 (grounding check)** — mismo perfil. Buena segunda.
3. **Fase 1.2 (sub-chunking)** — requiere re-index. Hacer cuando puedas dedicar 30 min a backup + re-index + smoke test.
4. **Fase 1.1 (hybrid search)** — requiere migración SQL. Hacerlo cuando puedas coordinar con el equipo (downtime corto al aplicar el ALTER TABLE).

**Branch suggestion**: cada fase en una PR separada. Mergear secuencialmente tras validar en widget.

---

## 7. Validación general (después de cada fase)

```powershell
python -m pytest tests/test_rag_safety.py tests/test_retrieval_rerank.py tests/test_decision_tree.py -v --tb=short
python -m compileall src tests
```

Tras fase 1.2:
```powershell
# Re-index con backup primero
pg_dump -t kb_documents > backup_pre_subchunk.sql
python scripts/load_embeddings.py
psql -c "SELECT source, COUNT(*) FROM kb_documents GROUP BY source"
```

Tras fase 1.1:
```powershell
# Aplicar migración SQL
psql -f migrations/001_add_fts_to_kb_documents.sql
```

### Smoke test manual (set de queries)

Después de cada fase, probar en Chatwoot estas queries y comparar antes/después:

| Query | Fase que mejora |
|---|---|
| "¿Cuál es el punto de encuentro?" | retrieval base + grounding |
| "Si llevo más de 2 años sin bucear, ¿necesito refresh?" | 1.2 + grounding |
| "¿Cómo es el Curso Básico PADI Open Water si ya estoy en las Islas del Rosario?" | 1.1 + 1.2 |
| "¿Tienen opciones de alojamiento en las Islas del Rosario?" | 1.1 (hybrid search exact match) |
| "¿Cómo es el Curso Básico PADI Open Water?" → "¿y si ya estoy en las islas?" | 1.3 (rewriting) |
| "¿Qué comida incluye el tour?" | canonical short-circuit |
| "San Pedro de Majagua" | 1.1 (hybrid search exact match) |
| "Hotel Pao Pao recogida?" | KB curada + query ambigua corta: debe recuperar FAQs de alojamiento/recogida sin inventar un plan |

### Hallazgos de la validación E2E (2026-06-12)

- **Activación OK**: migración FTS aplicada, reindexado ejecutado y smoke test end-to-end satisfactorio.
- **FTS ya aporta valor**: queries como `San Pedro de Majagua` y alojamiento en Islas del Rosario recuperan docs con ramas `bm25 + vector`.
- **Query rewriting útil**: el follow-up `¿y si ya estoy en las islas?` con historial sobre Open Water se resolvió en el contexto correcto.
- **Canónicos intactos**: la pregunta `¿Qué comida incluye el tour?` sigue saliendo por la ruta canónica esperada.
- **KB curada limpiada y reindexada**: se normalizó el WhatsApp oficial en `services.json`, `faqs.json` y `policies.json`, se reforzó cobertura factual de hoteles/islas, y se reindexó la base con 735 documentos.
- **Gap de contenido resuelto**: `Pao Pao` ya aparece en la KB curada actual y ahora recupera FAQs relevantes de alojamiento/recogida.
- **Hallazgo útil adicional**: en queries ultra-cortas de hotel/lugar, el retrieval ya iba bien y ahora el RAG también pide aclaración breve para nombres sueltos del catálogo antes de inferir un plan concreto. El siguiente ajuste, si hace falta, sería extender esta protección a aliases o nombres nuevos que aparezcan en producción.
- **Hallazgo útil para revisar**: en algunas queries, el top doc sigue viniendo de `conversations` o `faqs` antes que de `services`. No es un bug por sí mismo, pero sí señala que la calidad final depende de la curación de la KB y del balance actual de weights / boosts / source priorities.

### Tanda de fiabilidad + rendimiento (2026-06-14)

Aplicada sobre `feature/pruebaGon` tras el merge de `dev_gadea`. Tres cambios de bajo riesgo, todos con tests (`tests/test_rag_safety.py`):

- **Gate de confianza arreglado (antes anulado)**: el `score_final` híbrido (cosine + RRF + boost) hacía que el umbral `rag_min_score` casi nunca disparara fallback, porque el top de BM25 normaliza siempre a `1.0`. Ahora `rag_agent._is_confident()` evalúa cada señal en su escala: cosine `>= rag_min_score` para hits vectoriales y `ts_rank_cd` crudo `>= rag_min_bm25_rank` (nuevo setting, default `0.05`) para hits léxicos. La expansión de padres se hace **después** del gate para que un `:summary` no infle la confianza. Docs sin branch scores (tests/legacy) siguen gateando por `score`.
- **BM25 con `websearch_to_tsquery('simple', …)`** en lugar de `plainto_tsquery`: parsing más seguro (comillas, OR, negación, sin errores con puntuación). Mantiene AND por defecto, así que un hit BM25 sigue implicando match fuerte.
- **Pool de conexiones compartido**: `vector_store._get_pool()` / `get_pool()` reemplaza el `asyncpg.connect()` por query en `_vector_search`, `_bm25_search` y `rag_agent._expand_with_parent_context`. Menos latencia y sin riesgo de agotar conexiones.

Pendiente de tanda futura (no incluido aquí): bypass del grounding check cuando la confianza de retrieval es muy alta (latencia), recalibración fina de `rag_min_bm25_rank` con datos reales, y revisión de pesos de source/topic boost.

### Tanda de correctness (2026-06-14, 2ª)

Enfocada en "mínima equivocación posible", también con tests:

- **Guard determinista de importes** (`grounding_check.currency_amounts_grounded`): antes del grounding por LLM, se verifica sin coste que todo precio/porcentaje de la respuesta (`$178`, `178 USD`, `630.000 COP`, `10%`) aparezca en el contexto. Si hay un importe que no está, se devuelve el fallback. Normaliza decimales USD (`178.00`) y miles COP (`630.000`) para no generar falsos positivos. Los números no monetarios (días, metros, teléfono) se ignoran. Corre **antes** del verificador LLM (que también puede alucinar su veredicto), así que cubre el peor caso: dar un precio inventado.
- **Limpieza de contexto**: se quitó el `Score: X` que se inyectaba en el contexto visible para el LLM (ruido innecesario que no aporta a la respuesta).

### Tanda de correctness + retrieval (2026-06-14, 3ª)

- **Guard determinista de URLs** (`grounding_check.urls_grounded`): cualquier link `http(s)://` o `www.` en la respuesta debe aparecer en el contexto; si no, fallback. Los links de reserva/pago deben venir del flujo estructurado, no del LLM. Respuestas sin links no se ven afectadas.
- **Boost por subtipo de servicio** (`vector_store.subtype_boost_for_topics` + `SUBTYPE_BY_TOPIC`): aprovecha los sub-chunks de `services.json` (`summary`/`itinerary`/`included`/`requirements`/`pricing`) para subir el subchunk correcto según la intención de la query (pricing→`pricing`, schedule→`itinerary`, equipment→`included`, certification/refresher→`requirements`). Se aplica como segundo nivel de rerank (`+0.08`), sin sobrescribir las señales de `source`. Esto también ayuda a que `services` compita mejor en intents de detalle, en lugar de tocar magic-numbers a ciegas.

### Tanda de mantenibilidad + operativa (2026-06-14, 4ª)

- **Reindex seguro** (`scripts/load_embeddings.py`): el `main()` ahora confirma antes del `DELETE FROM kb_documents` mostrando filas actuales vs. nuevas y la DB destino. Flags: `--yes`/`--force` para saltar la confirmación (CI/automatización) y `--dry-run` para construir documentos e imprimir un resumen por `source` sin tocar DB ni OpenAI. Cubre el TODO de "confirmación antes del DELETE".
- **Few-shot alias map a nivel de módulo** (`rag_agent._FEWSHOT_TOPIC_ALIASES`): se extrajo el mapa (antes reconstruido en cada llamada) y se amplió con las etiquetas legacy/español reales de `conversations.json` (`precio_colombianos`, `clima`, `cancelacion_reembolso`, `alojamiento`, `proceso_reserva`, `open_water_course`, etc.), mejorando el overlap de topics para seleccionar ejemplos.
- **Caché de KB en `rag_agent`** (`_load_faqs_cached`/`_load_policies_cached`): las respuestas canónicas de comida ya no leen disco en cada query.

---

## 8. Lo que NO está en este alcance

Para mantener el scope acotado, dejamos fuera (anotar para post-demo):

- **Observabilidad**: integración LangSmith/Phoenix/Langfuse. La config de LangSmith existe en `src/config.py` pero no está activa.
- **Evals automáticos**: golden dataset de 50-100 Q&A para regresión. Sin esto cada cambio se valida manualmente.
- **Cache semántico**: respuestas a queries similares no se cachean — cada query es un nuevo embedding + LLM call.
- **BGE-reranker local**: cross-encoder open-source para reranking final. Requiere modelo HuggingFace + posiblemente GPU.
- **Model cascading**: gpt-4o-mini por defecto, escalar a gpt-4o si baja confianza.
- **Feedback loop**: thumbs up/down del usuario para acumular dataset de fallos.
- **Migración del state**: `conversations` dict en memoria → Redis/PostgreSQL (pendiente desde hace meses).

---

## 9. Referencias rápidas

- Plan original (más conciso, sin instrucciones paso a paso): `C:\Users\plaza\.claude\plans\gleaming-sniffing-snail.md` (local al autor).
- Estado de las preguntas para el owner que deberían enriquecer la KB: `docs/archive/questions_for_owner_business_kb.md` (42 preguntas pendientes).
- Documentación de `brand_tone.json` (formato esperado): leer el JSON directamente, está autoexplicativo.
- Documentación de `conversations.json` (formato esperado): cada ejemplo necesita `id`, `lang`, `scenario`, `customer.messages`, `diving_planet.messages`, `extracted_topics`.

### Bibliografía sobre las técnicas

- **Reciprocal Rank Fusion**: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods" (2009). El parámetro `k=60` es el default establecido.
- **Parent-doc retrieval / small-to-big**: documentado en LangChain (`ParentDocumentRetriever`) y LlamaIndex (`HierarchicalNodeParser`).
- **Query rewriting**: ver "Query Rewriting for Retrieval-Augmented Large Language Models" (Microsoft, 2023).
- **Self-RAG / grounding check**: Asai et al., "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection" (2023).
