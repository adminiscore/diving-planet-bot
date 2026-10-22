"""
RAG Agent for knowledge base retrieval.

Uses pgvector embeddings to answer questions about Diving Planet
services, policies, and FAQs that fall outside the predefined
decision tree.
"""

import asyncio
import contextvars
import json
import logging
import re

from openai import AsyncOpenAI

from src.agents.grounding_check import (
    capacity_claims_grounded,
    contains_phone_number,
    currency_amounts_grounded,
    inactive_certified_companion_not_contradicted,
    is_coherent_text,
    is_grounded,
    requests_personal_data,
    urls_grounded,
)
from src.agents.query_rewriter import condense_query, pregunta_sola
from src.config import settings
from src.knowledge.loader import load_brand_tone
from src.knowledge.vector_store import get_pool, search_knowledge_base
from src.llm_client import trace_openai
from src.privacy import detect_pii, privacy_block_message, redact_pii
from src.prompts.info import (
    RAG_BODY_EN,
    RAG_BODY_ES,
    RAG_INTRO_EN,
    RAG_INTRO_ES,
    RAG_SECURITY_EN,
    RAG_SECURITY_ES,
)

logger = logging.getLogger("uvicorn.error")

# rag-5 (30-sep): True dentro de la tarea que adelanta el RAG en paralelo con el enrutador (Jev). Vive en el
# contexto de ESA tarea (asyncio copia el contexto al crearla), así que no afecta al resto del turno.
RAG_ADELANTADO: contextvars.ContextVar[bool] = contextvars.ContextVar("rag_adelantado", default=False)

_BRAND_TONE_CACHE: dict | None = None


def _load_brand_tone_cached() -> dict:
    """Load and cache brand_tone.json at first access."""
    global _BRAND_TONE_CACHE
    if _BRAND_TONE_CACHE is None:
        _BRAND_TONE_CACHE = (load_brand_tone() or {}).get("brand_tone", {})
    return _BRAND_TONE_CACHE


def _build_tone_section(lang: str) -> str:
    """Compose the Style/Tone bullets dynamically from brand_tone.json.

    Falls back to a minimal hard-coded set if the file is missing or malformed.
    """
    tone = _load_brand_tone_cached()
    bullets: list[str] = []

    personality = (tone.get("personality") or {}).get(lang, "")
    if personality:
        # Capitalize first char only; preserve the rest of the casing (e.g. brand names).
        cap_personality = personality[:1].upper() + personality[1:]
        if lang == "es":
            bullets.append(
                f"- {cap_personality}. Suenas como un asesor real "
                "hablando por WhatsApp: amable, rapido, informal-profesional y orientado a resolver."
            )
        else:
            bullets.append(
                f"- {cap_personality}. Sound like a real Diving Planet advisor on WhatsApp: "
                "warm, fast, informal-professional, and focused on solving the customer's need."
            )

    ws_lang = (tone.get("whatsapp_style") or {}).get(lang) or {}
    for shape in ws_lang.get("message_shape", []):
        bullets.append(f"- {shape}")

    human = ws_lang.get("human_touches", [])
    if human:
        bullets.append(f"- {human[0]}")

    age = (tone.get("age_demographic_consideration") or {}).get(lang, "")
    if age:
        bullets.append(f"- {age}")

    if not bullets:
        # Defensive fallback if brand_tone.json is empty or unreadable.
        if lang == "es":
            return (
                "- Cercano, confiable, profesional pero amigable.\n"
                "- Usa frases cortas y naturales.\n"
                "- Cierra con una pregunta util o un siguiente paso claro."
            )
        return (
            "- Approachable, trustworthy, professional but friendly.\n"
            "- Use short, natural sentences.\n"
            "- End with a useful question or clear next step."
        )

    return "\n".join(bullets)


FALLBACK_ES = (
    "¡Con gusto te ayudo! 🌊 Ese detalle en concreto no lo tengo a la mano, pero puedo "
    "ayudarte con las actividades, precios, logística o a armar tu reserva. ¿Quieres que te "
    "pase con un asesor para resolver eso puntual?"
)

FALLBACK_EN = (
    "Happy to help! 🌊 I don't have that specific detail handy, but I can help you with "
    "activities, prices, logistics or putting your booking together. Would you like me to "
    "connect you with an advisor for that specific point?"
)


def is_fallback_answer(text: str | None) -> bool:
    """¿Esta respuesta es el "no lo tengo a la mano" del RAG?

    Una fuente para los sitios que lo preguntan: la comparación desde el catálogo
    cuando el KB no cubre el par (`conversational_core._routing_phase`), la métrica
    de negocio de m0-5 (`supervisor`, % de turnos con fallback) y u3-4, que no debe
    pegar la pregunta de la reserva detrás de un "no lo sé".

    Se busca como subcadena, no por igualdad, porque el fallback puede llegar
    concatenado (saludo delante, acuse detrás).
    """
    return bool(text) and (FALLBACK_ES in text or FALLBACK_EN in text)


def build_system_prompt(lang: str, query: str | None = None) -> str:
    """Compose the full system prompt: intro + dynamic tone + body.

    ``query`` ya no se usa: alimentaba el few-shot de los chats antiguos de WhatsApp
    (conversations.json), retirado en g-7 paso 4 (2026-09-24). Se deja en la firma para
    no tocar a quien llama.
    """
    if lang == "es":
        prompt = (
            f"{RAG_INTRO_ES}\n\n"
            f"{RAG_SECURITY_ES}\n"
            f"Estilo y tono:\n{_build_tone_section('es')}\n\n"
            f"{RAG_BODY_ES}"
        )
    else:
        prompt = (
            f"{RAG_INTRO_EN}\n\n"
            f"{RAG_SECURITY_EN}\n"
            f"Style and tone:\n{_build_tone_section('en')}\n\n"
            f"{RAG_BODY_EN}"
        )
    if settings.est2_datos:
        # EX-EST-2: siempre hay disponibilidad (decisión del negocio) y, si encajan varios planes, se nombran todos.
        from src.prompts.info import (  # lazy
            RAG_DISPONIBILIDAD_NUEVA_EN,
            RAG_DISPONIBILIDAD_NUEVA_ES,
            RAG_DISPONIBILIDAD_VIEJA_EN,
            RAG_DISPONIBILIDAD_VIEJA_ES,
            RAG_VARIOS_PLANES_EN,
            RAG_VARIOS_PLANES_ES,
        )

        prompt = prompt.replace(RAG_DISPONIBILIDAD_VIEJA_ES, RAG_DISPONIBILIDAD_NUEVA_ES).replace(
            RAG_DISPONIBILIDAD_VIEJA_EN, RAG_DISPONIBILIDAD_NUEVA_EN)
        prompt = f"{prompt}\n\n{RAG_VARIOS_PLANES_ES if lang == 'es' else RAG_VARIOS_PLANES_EN}"
    if settings.rag_no_adivina:
        # 18-oct: no adivinar ningún dato del cliente (origen, nacionalidad, certificación, cuántos, fechas); sustituye
        # a la regla de EX-RAG-2, que solo cubría el servicio (ver RAG_NO_ADIVINA_*).
        from src.prompts.info import RAG_NO_ADIVINA_EN, RAG_NO_ADIVINA_ES  # lazy

        prompt = f"{prompt}\n\n{RAG_NO_ADIVINA_ES if lang == 'es' else RAG_NO_ADIVINA_EN}"
        if settings.abre_con_la_respuesta:
            # gen-2 (20-oct): sin "¡Claro que sí!" delante de un "no" o un "depende" (ver RAG_ABRE_CON_LA_RESPUESTA_*).
            from src.prompts.info import (  # lazy
                RAG_ABRE_CON_LA_RESPUESTA_EN,
                RAG_ABRE_CON_LA_RESPUESTA_ES,
            )

            prompt = f"{prompt}\n\n{RAG_ABRE_CON_LA_RESPUESTA_ES if lang == 'es' else RAG_ABRE_CON_LA_RESPUESTA_EN}"
        if settings.sin_genero_supuesto:
            # gen-12 (21-oct): sin dar por hecho si el cliente es hombre o mujer (ver RAG_SIN_GENERO_*).
            from src.prompts.info import RAG_SIN_GENERO_EN, RAG_SIN_GENERO_ES  # lazy

            prompt = f"{prompt}\n\n{RAG_SIN_GENERO_ES if lang == 'es' else RAG_SIN_GENERO_EN}"
    elif settings.rag_no_supone_reserva:
        # EX-RAG-2: no atribuir al cliente un servicio o una reserva que no dijo.
        from src.prompts.info import RAG_NO_SUPONE_EN, RAG_NO_SUPONE_ES  # lazy

        prompt = f"{prompt}\n\n{RAG_NO_SUPONE_ES if lang == 'es' else RAG_NO_SUPONE_EN}"
    if settings.rag_ofrece_el_pase:
        # G3-03: el RAG no puede pasar el caso a una persona; lo OFRECE como pregunta (ver RAG_PASE_OFRECIDO_*).
        from src.prompts.info import RAG_PASE_OFRECIDO_EN, RAG_PASE_OFRECIDO_ES  # lazy

        prompt = f"{prompt}\n\n{RAG_PASE_OFRECIDO_ES if lang == 'es' else RAG_PASE_OFRECIDO_EN}"
    if settings.rag_sin_hora:
        # EX-EST-2: el RAG no sabe la hora ni la fecha de hoy (ver RAG_SIN_HORA_*).
        from src.prompts.info import RAG_SIN_HORA_EN, RAG_SIN_HORA_ES  # lazy

        prompt = f"{prompt}\n\n{RAG_SIN_HORA_ES if lang == 'es' else RAG_SIN_HORA_EN}"
    # s4-26 (7-oct): una condición del cliente no pasa a hecho sin que nadie lo diga (ver RAG_CONDICIONES_*).
    from src.prompts.info import RAG_CONDICIONES_EN, RAG_CONDICIONES_ES  # lazy

    prompt = f"{prompt}\n\n{RAG_CONDICIONES_ES if lang == 'es' else RAG_CONDICIONES_EN}"
    return prompt


# Anaphoric / follow-up indicators: demonstratives and pronouns that refer back
# to something said earlier ("these packages", "ese plan", "lo mismo"...).
_FOLLOW_UP_INDICATORS = re.compile(
    r"\b("
    r"this|that|these|those|it|them|they|same|also|previous|one|ones|"
    r"ese|esa|eso|esos|esas|este|esta|esto|estos|estas|"
    r"mismo|misma|mismos|mismas|anterior|tambi[eé]n|aquel|aquella|aquello"
    r")\b",
    re.IGNORECASE,
)
# Queries that begin with a connector are almost always continuations ("y ...", "and ...").
_FOLLOW_UP_PREFIX = re.compile(r"^[¿¡\s]*(y|e|and|pero|but|o|or|entonces|then)\b", re.IGNORECASE)

# Declarative location/situation statements answering a prior question
# ("en el hotel Pao Pao", "estoy en Isla Grande", "at the X hotel"). These are
# follow-ups that need the conversation context to be understood for retrieval.
# Note: interrogatives like "¿en qué consiste...?" are NOT matched (require "en el/la").
_LOCATION_STATEMENT_PREFIX = re.compile(
    r"^[¿¡\s]*("
    r"estoy en|estamos en|me hospedo|nos hospedamos|me alojo|nos alojamos|"
    r"en el|en la|en isla|en hotel|"
    r"i'?m (at|in|staying)|we'?re (at|in|staying)|i am (at|in|staying)|"
    r"we are (at|in|staying)|staying at|staying in|at the|in the"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_follow_up(query: str) -> bool:
    """Heuristic: does this query rely on previous turns to be understood?

    A self-contained question (names its own subject) returns False so we do NOT
    pollute its retrieval with unrelated earlier questions. Short queries and
    anaphoric ones return True so they get conversational context.
    """
    text = (query or "").strip()
    if not text:
        return False
    # Very short fragments ("the prices", "y los niños?") are almost always
    # follow-ups; condense_query also handles these, this is a safety net.
    if len(text.split()) < 4:
        return True
    if _FOLLOW_UP_PREFIX.match(text):
        return True
    # Declarative location/situation answers ("en el hotel Pao Pao") need context.
    if _LOCATION_STATEMENT_PREFIX.match(text):
        return True
    return bool(_FOLLOW_UP_INDICATORS.search(text))


def build_retrieval_query(query: str, history: list[dict] | None = None) -> str:
    if not history:
        return query

    # Only enrich genuine follow-ups with conversation history. A self-contained
    # question must be retrieved on its own — otherwise an unrelated previous
    # question dilutes the embedding and the right doc falls below the threshold.
    if not _looks_like_follow_up(query):
        return query

    recent_user_messages = [
        msg["content"]
        for msg in history[-settings.history_retrieval_enrichment_window:]
        if msg.get("role") == "user" and msg.get("content") != query
    ]
    if not recent_user_messages:
        return query

    return "\n".join([*recent_user_messages[-2:], query])


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


AMBIGUOUS_LOCATION_NAMES = (
    "Isla Grande",
    "Isla Marina",
    "Isla del Pirata",
    "Isla del Sol",
    "Isleta",
    "Isla Arena",
    "Isla Pavitos",
    "Isla Lizamar",
    "Isla Gigi",
    "Isla Rosa",
    "Isla Pelicano",
    "Isla Rosario",
    "San Pedro de Majagua",
    "Bora Bora Beach Club",
    "Cocoliso Island Resort",
    "Pao Pao Hotel",
    "Fragata Island House",
    "Secreto Hostel",
    "Gente de Mar Resort",
    "Luxury Beach Club",
    "Ecohotel Las Flores",
    "Ecohostal Playa Libre",
    "Islabela",
    "Hotel El Hamaquero",
    "Centro Ubuntu",
    "Hotel Isla del Pirata",
    "Hotel Isla del Sol",
    "Coralina Island",
    "Isleta Beach",
    "Isla Arena Eco Resort",
    "Isla Pavitos (Privada)",
    "Hotel Lizamar",
    "Casa de Isla Gigi",
    "Isla Rosa (Privada)",
    "Isla Pelicano",
    "Rosario EcoHotel",
    "Hotel San Tropel",
)

AMBIGUOUS_LOCATION_PREFIXES = (
    "hotel ",
    "casa de ",
    "centro ",
)

AMBIGUOUS_LOCATION_SUFFIXES = (
    " hotel",
    " island resort",
    " island house",
    " beach club",
    " eco resort",
    " resort",
    " hostel",
    " island",
    " ecohotel",
)

LOCATION_QUERY_INTENT_PATTERN = re.compile(
    r"\b(recog(?:er|ida|en|eme|emos|ernos)?|pickup|pick\s*up|alojamiento|hosped(?:aje|arme|arnos)?|stay|staying|buce(?:o|ar|a|an)|div(?:e|ing)|snorkel|curso|minicurso|tour|plan|paquete|package|precio|cost|cu[aá]nto|reserv(?:a|ar)|book(?:ing)?|availability|disponibilidad|itinerario|schedule|ubicaci[oó]n|location|d[oó]nde|where|c[oó]mo|how)\b",
    re.IGNORECASE,
)


def _is_safe_location_alias(value: str) -> bool:
    words = value.split()
    return len(words) >= 2 or len(value) >= 7


def _build_ambiguous_location_catalog() -> frozenset[str]:
    aliases: set[str] = set()
    for raw_name in AMBIGUOUS_LOCATION_NAMES:
        cleaned = re.sub(r"\s*\([^)]*\)", "", raw_name).strip()
        normalized = _normalize_text(cleaned)
        if not normalized:
            continue

        candidates = {normalized}
        for prefix in AMBIGUOUS_LOCATION_PREFIXES:
            if normalized.startswith(prefix):
                candidate = normalized[len(prefix):].strip()
                if candidate:
                    candidates.add(candidate)
        for suffix in AMBIGUOUS_LOCATION_SUFFIXES:
            if normalized.endswith(suffix):
                candidate = normalized[: -len(suffix)].strip()
                if candidate:
                    candidates.add(candidate)

        for candidate in candidates:
            if candidate == normalized or _is_safe_location_alias(candidate):
                aliases.add(candidate)

    aliases.add("majagua")
    return frozenset(aliases)


AMBIGUOUS_LOCATION_CATALOG = _build_ambiguous_location_catalog()


def _is_ultra_short_ambiguous_location_query(query: str) -> bool:
    normalized = _normalize_text(query)
    if not normalized:
        return False
    if len(re.findall(r"\w+", normalized, re.UNICODE)) > 5:
        return False
    if normalized not in AMBIGUOUS_LOCATION_CATALOG:
        return False
    if LOCATION_QUERY_INTENT_PATTERN.search(normalized):
        return False
    return True


def _ambiguous_location_clarification(query: str, lang: str) -> str | None:
    if not _is_ultra_short_ambiguous_location_query(query):
        return None

    place = query.strip().strip("¿?¡!.,;:")
    if not place:
        place = query.strip()

    if lang == "es":
        return (
            f"¿Te refieres a {place} para recogida, alojamiento o para saber qué plan aplica si ya estás allí? "
            "Si me dices eso, te respondo más preciso."
        )
    return (
        f"Do you mean {place} for pickup, accommodation, or to know which plan applies if you're already there? "
        "If you tell me that, I can answer more precisely."
    )


def _coerce_metadata(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _score_for_threshold(doc: dict) -> float:
    raw_score = doc.get("score_final", doc.get("score", 0.0))
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return 0.0


BUSQUEDA_DOBLE_EXTRA = 4


def fusionar_busquedas(reescrita: list[dict], original: list[dict], extra: int = BUSQUEDA_DOBLE_EXTRA) -> list[dict]:
    """Las piezas de la consulta reescrita, INTACTAS, más hasta `extra` que solo trae la pregunta original (en su
    orden). Primera versión (intercalar por posición y quedarse en 8): sacaba del top-8 piezas buenas de la
    reescrita ("¿me recuerda los hoteles?" perdía la FAQ de los hoteles base). Así nunca se pierde lo de hoy; no se
    ordena por puntuación porque la de dos consultas distintas no se compara."""
    def clave(doc: dict):
        return doc.get("id") or (doc.get("metadata") or {}).get("key") or doc.get("content")

    vistas = {clave(d) for d in reescrita}
    nuevas = [d for d in original if clave(d) not in vistas]
    return [*reescrita, *nuevas[:extra]]


def _is_confident(doc: dict) -> bool:
    """Decide whether a retrieved doc is a confident match.

    Hybrid retrieval mixes a dense cosine score (0-1) with a normalized BM25
    score whose top value is always 1.0, so the combined ``score_final`` cannot
    be compared against a fixed threshold. Gate each signal on its own scale:

    - vector hits: cosine >= ``rag_min_score``
    - lexical hits: raw ts_rank_cd >= ``rag_min_bm25_rank``

    Docs without branch scores (test fixtures / legacy shape) fall back to the
    generic ``score`` against ``rag_min_score``.
    """
    has_branch_scores = ("score_vector" in doc) or ("score_bm25_raw" in doc)
    if has_branch_scores:
        try:
            vector_score = float(doc.get("score_vector", 0.0) or 0.0)
        except (TypeError, ValueError):
            vector_score = 0.0
        try:
            bm25_raw = float(doc.get("score_bm25_raw", 0.0) or 0.0)
        except (TypeError, ValueError):
            bm25_raw = 0.0
        return vector_score >= settings.rag_min_score or bm25_raw >= settings.rag_min_bm25_rank

    try:
        return float(doc.get("score", 0.0) or 0.0) >= settings.rag_min_score
    except (TypeError, ValueError):
        return False


async def _expand_with_parent_context(docs: list[dict], lang: str) -> list[dict]:
    parent_ids_needed: set[str] = set()
    existing_keys = {
        str((doc.get("metadata") or {}).get("key"))
        for doc in docs
        if (doc.get("metadata") or {}).get("key")
    }
    parent_scores: dict[str, float] = {}

    for doc in docs:
        metadata = doc.get("metadata") or {}
        parent_id = metadata.get("parent_id")
        key = metadata.get("key")
        if not parent_id or parent_id == key or parent_id in existing_keys:
            continue
        parent_key = str(parent_id)
        parent_ids_needed.add(parent_key)
        parent_scores[parent_key] = max(parent_scores.get(parent_key, 0.0), _score_for_threshold(doc))

    if not parent_ids_needed:
        return docs

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata
                FROM kb_documents
                WHERE metadata->>'lang' = $1
                  AND metadata->>'key' = ANY($2::text[])
                """,
                lang,
                list(parent_ids_needed),
            )
    except Exception as exc:
        logger.warning(f"[RAG][PARENT] failed to expand parent context: {exc}")
        return docs

    parents: list[dict] = []
    seen_parent_keys: set[str] = set()
    for row in rows:
        metadata = _coerce_metadata(row["metadata"])
        parent_key = str(metadata.get("key") or "")
        if not parent_key or parent_key in seen_parent_keys:
            continue
        seen_parent_keys.add(parent_key)
        score = parent_scores.get(parent_key, 0.0)
        parents.append({
            "id": row["id"],
            "content": row["content"],
            "metadata": metadata,
            "score": score,
            "score_final": score,
        })

    if not parents:
        return docs
    return parents + docs


def _build_grounding_context(
    context: str,
    extra_context: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Assemble everything the grounding check is allowed to treat as truth.

    Without the conversation history, a perfectly accurate answer that just
    confirms something the BOT ITSELF already said earlier (e.g. "menores de
    8 solo pueden hacer snorkel, min. 6 anos" stated a few turns ago in the
    kids-age question) gets rejected as "ungrounded" because that fact isn't
    in the freshly retrieved docs/extra_context — even though it's exactly
    what the client is asking to confirm. Only the bot's OWN prior messages
    are included (not the client's), since those came from deterministic tree
    templates / KB data, not free-form guesses.
    """
    parts = [context] if context else []
    if extra_context and context != extra_context:
        parts.append(f"Contexto adicional de la situacion: {extra_context}")
    if history:
        prior_bot_messages = [
            turn.get("content", "")
            for turn in history[-settings.history_window_size:]
            if turn.get("role") == "assistant" and turn.get("content")
        ]
        if prior_bot_messages:
            parts.append(
                "Mensajes que el propio bot ya envio antes en esta conversacion "
                "(puedes usarlos para confirmar datos que ya mencionaste):\n"
                + "\n---\n".join(prior_bot_messages)
            )
    return "\n\n".join(parts)


def regen_feedback(reject_reason: str, lang: str) -> str | None:
    """Mensaje para la segunda muestra con lo que el juez o el guard rechazó (28-sep, regeneración con motivo).

    El juez v3 devuelve "HALLUCINATED - dato NO | - dato NO"; los guards, su etiqueta. None = sin motivo que
    contar (se regenera como antes)."""
    from src.prompts.info import (  # lazy
        RAG_REGEN_FEEDBACK_EN,
        RAG_REGEN_FEEDBACK_ES,
        RAG_REGEN_GUARD_EN,
        RAG_REGEN_GUARD_ES,
    )

    guards = RAG_REGEN_GUARD_ES if lang == "es" else RAG_REGEN_GUARD_EN
    if reject_reason in guards:
        facts = guards[reject_reason]
    elif reject_reason.startswith("HALLUCINATED"):
        items = []
        for raw in reject_reason[len("HALLUCINATED"):].split(" | "):
            item = re.sub(r"[\s:.]*\bNO\b\.?\s*$", "", raw.strip().lstrip("- ").strip())
            if item:
                items.append(f"- {item}")
        if not items:
            return None
        facts = "\n".join(items)
    else:
        return None
    template = RAG_REGEN_FEEDBACK_ES if lang == "es" else RAG_REGEN_FEEDBACK_EN
    return template.format(facts=facts)


async def _verify_grounding(answer: str, context: str, lang: str) -> tuple[bool, str]:
    """Juzga UNA vez si la respuesta está sostenida por el contexto (l1-1, Fase L1).

    Antes se re-preguntaba al mismo juez por el mismo texto cuando rechazaba. En el
    A/B del 23-sep esa segunda consulta solo salvó 1 de 24 rechazos (4 %) y se quitó:
    la segunda oportunidad real la da el bucle de `_answer_with_llm`, que REGENERA la
    respuesta y la vuelve a juzgar. -35 % de llamadas al juez, calidad igual.
    """
    return await is_grounded(answer, context, lang=lang)


async def generar_con_respaldo(client, messages: list[dict], pieza: str = "rag_escritor"):
    """La llamada que escribe la respuesta del RAG, con RESPALDO (8-oct, cambio de modelos).

    GPT-6 Luna escribe mejores respuestas, pero tiene una cola de latencia (~8 % de llamadas a 6-13 s en la ronda
    modelos-B). Si el modelo principal no ha terminado en `rag_respaldo_segundos`, se lanza la MISMA petición al
    modelo de respaldo (`rag_respaldo_modelo`, gpt-4.1-mini) en paralelo y se usa la primera que termine; la otra
    se cancela. Si el principal falla, contesta el respaldo. Sin respaldo configurado, la llamada de siempre.
    `pieza`: cómo sale la llamada del principal en [TURN_METRICS] (ARQ-1d: el redactor de hechos usa esta misma)."""
    from src.observability import note_turn, pieza_llm  # lazy

    principal = settings.rag_answer_model or settings.openai_model
    respaldo, espera = settings.rag_respaldo_modelo, settings.rag_respaldo_segundos
    if settings.respaldo_mismo_modelo:
        # r6-1(d) (17-oct, salir de gpt-4.1; acordado con Gadea por Coral): el respaldo es OTRA petición al mismo modelo
        # ("hedging"). La cola de Luna (~8 % de llamadas a 6-13 s) es azar de cada petición: una segunda lanzada a los
        # `rag_respaldo_segundos` suele volver antes. gpt-5-mini/nano se descartaron el 8-oct por latencia.
        respaldo = principal

    async def llamar(model: str, es_respaldo: bool = False):
        # CAL-A1 (`rag_temperatura_cero`): 18 de los 56 fallos del RAG en ex-10 eran azar (mismo contexto, unas veces
        # sí y otras no; diagnóstico de Gadea): con temperatura 0 la redacción es estable.
        temperatura = 0.0 if settings.rag_temperatura_cero else 0.3
        # r6-1: el escritor y el respaldo salen por separado en [TURN_METRICS] (CAL-G).
        with pieza_llm("rag_respaldo" if es_respaldo or model != principal else pieza):
            return await client.chat.completions.create(model=model, messages=messages, temperature=temperatura,
                                                        max_tokens=500)

    if not respaldo or espera <= 0 or (respaldo == principal and not settings.respaldo_mismo_modelo):
        return await llamar(principal)
    t0 = asyncio.get_running_loop().time()
    t_principal = asyncio.ensure_future(llamar(principal))
    await asyncio.wait({t_principal}, timeout=espera)
    if t_principal.done() and t_principal.exception() is None:
        note_turn(rag_respaldo="principal", rag_respaldo_s=round(asyncio.get_running_loop().time() - t0, 2))
        return t_principal.result()
    if t_principal.done():  # el principal falló antes de la espera: contesta el respaldo
        logger.warning(f"[RAG][RESPALDO] {principal} falló ({t_principal.exception()}): contesta {respaldo}")
        note_turn(rag_respaldo="error_principal", rag_respaldo_s=round(asyncio.get_running_loop().time() - t0, 2))
        return await llamar(respaldo, es_respaldo=True)
    t_respaldo = asyncio.ensure_future(llamar(respaldo, es_respaldo=True))
    pendientes = {t_principal, t_respaldo}
    while pendientes:
        hechas, pendientes = await asyncio.wait(pendientes, return_when=asyncio.FIRST_COMPLETED)
        buena = next((t for t in hechas if t.exception() is None), None)
        if buena is not None:
            for t in pendientes:
                t.cancel()
            gana = "gana_principal" if buena is t_principal else "gana_respaldo"
            segundos = round(asyncio.get_running_loop().time() - t0, 2)
            logger.info(f"[RAG][RESPALDO] {principal} tardaba más de {espera:g} s: {gana} ({segundos} s)")
            note_turn(rag_respaldo=gana, rag_respaldo_s=segundos)
            return buena.result()
    return t_respaldo.result()  # fallaron los dos: la excepción del respaldo sube y el llamador da el fallback


async def rag_answer(
    query: str,
    lang: str = "es",
    history: list[dict] | None = None,
    extra_context: str | None = None,
    verify_grounding: bool = True,
    origin: str | None = None,
    avisos_hechos: dict | None = None,
    sin_precio: bool = False,
    sin_lista: bool = False,
    hechos: str | None = None,
) -> str:
    """`hechos` (arq-1g, flag `hechos_al_rag`): en un mensaje mezclado, los hechos del código (JSON de
    `src/flows/hechos.py`) para la parte que pregunta de la tabla (precio, qué incluye, requisitos…): se usan tal cual.

    `sin_precio` (G3-07a, 18-oct; lo pide el flujo con el flag `rag_sin_precio_con_tarjeta`): el turno lleva la
    tarjeta del plan con el precio y el enlace, así que el texto no los da (ver RAG_SIN_PRECIO_*).

    `avisos_hechos` (CAL-A, flag `avisos_condicionados`): lo que ya sabemos del cliente en campos estructurados
    (`src/flows/avisos.hechos_del_estado`), para que el CÓDIGO elija los avisos que la respuesta tiene que dar. Su
    clave "dados" es la lista del propio estado: los avisos dados se apuntan ahí y no se repiten.

    `origin` (rag-3): `state.location` del cliente ("cartagena" / "island"); la
    busqueda baja las fichas del otro origen.

    `verify_grounding=False` keeps the deterministic price/URL guards but skips
    the LLM grounding-judge, which false-negatives on correct answers that combine
    several KB chunks (e.g. a full course program). Used by the conversation agent
    so it can answer multi-part questions naturally; RAG defaults stay strict."""
    """Retrieve context from the knowledge base and answer using the LLM.

    Comportamiento en orden de prioridad:
    - Si hay documentos relevantes por encima del umbral -> usar esos docs como contexto principal.
    - Si NO hay docs o la confianza es baja PERO hay ``extra_context`` (por ejemplo, un
      resumen del estado de la conversacion) -> responder usando SOLO ese contexto
      adicional y el historial.
    - Si no hay ni docs ni ``extra_context`` util -> devolver el fallback seguro.
    """
    from src.observability import note_turn

    if not RAG_ADELANTADO.get():
        # rag-5: una respuesta adelantada (en paralelo con el enrutador) solo cuenta como turno con RAG si se
        # aprovecha; eso lo apunta quien la adopta (`conversational_core._adoptar_o_rehacer`).
        note_turn(rag_used=True)  # el turno lo responde el RAG (resumen del turno, m0-1)
    pii_hits = detect_pii(query)
    if pii_hits:
        logger.warning(f"[RAG][PRIVACY] PII detected in query hits={pii_hits}")
        return privacy_block_message(lang)

    # Paso 5: el catalogo va entero al contexto (fuente de verdad de precios, duracion y
    # pernocta) y los atajos de precio por regex dejan de contestar: se disparaban con
    # "cuánto" aunque se preguntara otra cosa y no sabian de que servicio se hablaba. ex-1 (fase EX,
    # 12-oct): esos atajos (precio, paquete, refresher y comida), apagados desde entonces, se borraron.
    from src.flows.catalog import catalog_facts, para_el_juez  # lazy

    facts = catalog_facts(lang)
    # s4-22 (paso 6): cotizaba el precio de Cartagena (o solo el de las islas) sin saber de
    # donde sale el cliente y sin decirlo. La moneda ya tenia su regla en el catalogo.
    facts += (
        "\nOrigen: si el contexto no dice desde dónde sale el cliente, da el precio desde Cartagena "
        "y el de 'ya en las islas', cada uno rotulado, o pregúntale desde dónde saldría."
        if lang == "es" else
        "\nOrigin: if the context doesn't say where the customer departs from, give the price from "
        "Cartagena and the 'already on the islands' one, each labelled, or ask where they'd leave from."
    )
    from src.flows.catalog import catalog_booking_links  # lazy

    facts += "\n" + catalog_booking_links(lang)
    if settings.rag_politicas_en_contexto:
        # EX-RAG-1: las políticas, siempre (como el catálogo); en el prefijo fijo, cacheable, y el juez también
        # las ve (una política citada en la respuesta queda respaldada).
        from src.flows.catalog import policies_facts  # lazy

        facts += "\n\n" + policies_facts(lang)
    # Paso 9 (l2-2): al prompt del sistema y a la cabeza del contexto del juez (prefijos fijos
    # que OpenAI cachea); en el mensaje del usuario, detras del historial, nunca se cacheaba.
    catalog_prefix = facts
    catalog_prefix_juez = para_el_juez(facts, lang)  # 1-oct: la regla de moneda como hecho

    # CAL-D (`consulta_con_lo_sabido`): el reescritor recibe lo que ya sabemos del cliente para que la consulta nombre
    # el asunto (sin esto deja la elipsis: "per day", "en concepto").
    # G3-05 (`busqueda_con_la_pregunta_sola`): a la vez, la pregunta sola (sin los datos que da el cliente y en el
    # idioma de la respuesta), que hace de "pregunta tal cual" en la búsqueda doble. Sin llamada si el mensaje es corto
    # y está en el idioma de la respuesta. Se espera justo antes de la segunda búsqueda.
    tarea_pregunta = asyncio.create_task(pregunta_sola(query, lang))
    condensed_query = await condense_query(query, history=history, lang=lang, hechos=avisos_hechos)
    ambiguous_location_clarification = _ambiguous_location_clarification(condensed_query, lang)
    if ambiguous_location_clarification:
        tarea_pregunta.cancel()
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=ambiguous_location query={query!r} lang={lang}")
        return ambiguous_location_clarification

    retrieval_query = build_retrieval_query(condensed_query, history)

    # If the query got enriched with prior turns (because it looked like a
    # follow-up), try the BARE query alone first: a short, self-contained
    # question that already retrieves confidently on its own must not be
    # diluted by unrelated earlier turns. Found live 2026-07-21: "y si llueve
    # que pasa" retrieved the correct weather FAQ alone at cosine 0.42 (above
    # threshold), but enriched with the 2 previous unrelated turns (price,
    # food) that same doc dropped to 0.377 (below threshold) and lost to the
    # food FAQs instead — the customer got "no lo tengo a la mano" for a
    # question the KB actually answers well.
    # rag-3: el origen del estado, no leido del resumen (la deteccion por frases de abajo solo casa en espanol).
    origen_kb = {"cartagena": "cartagena", "island": "islas"}.get(origin or "")
    buscar_kw = {"origin": origen_kb} if origen_kb else {}

    bare_docs = None
    bare_safe_query = None
    if retrieval_query != condensed_query:
        bare_safe_query = redact_pii(condensed_query)
        bare_docs = await search_knowledge_base(bare_safe_query, lang=lang, **buscar_kw)
        if any(_is_confident(d) for d in bare_docs):
            retrieval_query = condensed_query

    # Lightly bias retrieval using known origin from extra_context (Cartagena vs already on the islands)
    antes_del_origen = retrieval_query
    if extra_context:
        lowered_ctx = extra_context.lower()

        # Cliente saliendo desde Cartagena
        if "saldra desde cartagena" in lowered_ctx:
            rq_lower = retrieval_query.lower()
            if lang == "es" and "desde cartagena" not in rq_lower:
                retrieval_query += "\n\n[origen_cliente]=desde Cartagena"
            elif lang == "en" and "from cartagena" not in rq_lower:
                retrieval_query += "\n\n[origin]=from Cartagena"

        # Cliente que ya esta en las islas del Rosario
        if "ya esta en las islas del rosario" in lowered_ctx:
            rq_lower = retrieval_query.lower()
            if lang == "es" and "ya estoy en las islas del rosario" not in rq_lower:
                retrieval_query += "\n\n[origen_cliente]=ya en las islas"
            elif lang == "en" and "already on the rosario islands" not in rq_lower:
                retrieval_query += "\n\n[origin]=already on the Rosario Islands"

    safe_query = redact_pii(retrieval_query)

    # Retrieve relevant documents (parent expansion happens later, only if confident).
    # Reuse the bare-query search above instead of repeating it when nothing
    # (origin bias included) ended up changing the query further.
    # 1-oct (búsqueda doble): se busca TAMBIÉN con la pregunta tal cual y se unen los dos rankings. La
    # reescritura mete el servicio de la conversación y a veces se come el tema ("great, how do i pay" -> "How do I
    # pay for the Fun Dives?": las 6 piezas de pago salen con la original y ninguna con la reescrita;
    # `docs/robustness/juez/README.md`). Las dos búsquedas van a la vez. Solo si la reescritura CAMBIÓ la pregunta, y
    # la original lleva la misma marca de origen: en rag_piezas, con la reescrita idéntica, la única diferencia era
    # la marca y la búsqueda sin ella sacaba del top-8 una pieza buena.
    # G3-05: la búsqueda principal arranca ya; la segunda, en cuanto llega la pregunta sola (si la hay).
    sufijo_origen = retrieval_query[len(antes_del_origen):]
    principal = None
    if bare_docs is not None and safe_query == bare_safe_query:
        docs = bare_docs
    else:
        principal = asyncio.create_task(search_knowledge_base(safe_query, lang=lang, **buscar_kw))
    tal_cual = await tarea_pregunta or query
    reescrita_distinta = tal_cual.strip() != condensed_query.strip()
    original_q = redact_pii(tal_cual + sufijo_origen) if reescrita_distinta else ""
    buscar_original = bool(original_q.strip()) and original_q not in (safe_query, bare_safe_query)
    originales = await search_knowledge_base(original_q, lang=lang, **buscar_kw) if buscar_original else None
    if principal is not None:
        docs = await principal
    if originales:
        docs = fusionar_busquedas(docs, originales)

    # Helper to call the LLM with unstructured context (either KB docs o solo extra_context)
    async def _answer_with_llm(
        context: str,
        context_sources: list[str] | None = None,
        require_grounding: bool = False,
    ) -> str:
        """`require_grounding=True` forces the LLM grounding judge even when the
        caller passed `verify_grounding=False`. Used by the "no confident KB
        docs, answer from extra_context only" escape hatches below: there the
        model has NO knowledge-base support, so without the judge it happily
        answers a factual question from its own world knowledge (e.g. inventing
        a list of fish species). The judge is the only thing standing between
        that and the customer."""
        system_prompt = build_system_prompt(lang, query=condensed_query)
        if catalog_prefix:
            system_prompt = f"{system_prompt}\n\n{catalog_prefix}"
        if sin_precio:
            # G3-07a: detrás del catálogo, para no romper el prefijo que OpenAI cachea.
            from src.prompts.info import RAG_SIN_PRECIO_EN, RAG_SIN_PRECIO_ES  # lazy

            system_prompt = f"{system_prompt}\n\n{RAG_SIN_PRECIO_ES if lang == 'es' else RAG_SIN_PRECIO_EN}"
        if sin_lista:
            # ord-9: el código añade la lista exacta de lo que incluye; detrás del catálogo, como G3-07a.
            from src.prompts.info import RAG_SIN_LISTA_EN, RAG_SIN_LISTA_ES  # lazy

            system_prompt = f"{system_prompt}\n\n{RAG_SIN_LISTA_ES if lang == 'es' else RAG_SIN_LISTA_EN}"
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (settings.history_window_size messages max,
        # to keep a longer thread — see Fase A, docs/archive/memory-context-improvement-plan.md)
        if history:
            for msg in history[-settings.history_window_size:]:
                messages.append({"role": msg["role"], "content": redact_pii(msg["content"])})

        user_content = f"Contexto:\n{context}"
        if extra_context and context != extra_context:
            # Si ya tenemos contexto KB y ademas extra_context, lo anexamos explicito
            user_content += f"\n\nContexto adicional de la situacion: {extra_context}"
        if hechos:
            # arq-1g: la parte de la tabla sale del dato, no de memoria; detrás del contexto, antes de la pregunta.
            from src.prompts.info import RAG_CON_HECHOS_EN, RAG_CON_HECHOS_ES  # lazy

            user_content += f"\n\n{RAG_CON_HECHOS_ES if lang == 'es' else RAG_CON_HECHOS_EN}\n{hechos}"
        user_content += f"\n\nPregunta del cliente: {redact_pii(query)}"
        # CAL-A2 (`rag_plan_primero`): la lista de lo que el cliente pregunta, para contestarla punto por punto.
        puntos: list[str] = []
        if settings.rag_plan_primero or settings.rag_revisor_completitud:
            from src.agents.rag_plan import bloque_de_puntos, planificar  # lazy

            puntos = await planificar(redact_pii(query), history, lang) or []
            if puntos and settings.rag_plan_primero:
                user_content += "\n\n" + bloque_de_puntos(puntos, lang)
        # CAL-A5 (`avisos_condicionados`): los avisos que el cliente necesita y no pregunta, elegidos por el
        # CÓDIGO con el estado y con los TEMAS de los documentos que trajo la búsqueda (nunca con patrones sobre su
        # mensaje). A4 usaba el mismo mecanismo pero los elegía un modelo pequeño, y metía avisos que no tocaban.
        avisos_elegidos: list[dict] = []
        if settings.avisos_condicionados and avisos_hechos:
            from src.flows import avisos as avisos_mod  # lazy

            avisos_elegidos = avisos_mod.seleccionar(avisos_hechos, avisos_mod.temas_de_los_docs(docs),
                                                     avisos_mod.fuentes_recuperadas(docs))
            if avisos_elegidos:
                user_content += "\n\n" + avisos_mod.bloque_de_avisos(avisos_elegidos, lang)

        messages.append({"role": "user", "content": user_content})

        grounding_context = _build_grounding_context(context, extra_context=extra_context, history=history)
        if hechos:
            grounding_context = f"{grounding_context}\n\n{hechos}"  # arq-1g: el revisor y las guardas también los ven
        cabeza = [catalog_prefix_juez or catalog_prefix] if catalog_prefix else []
        # Lo que el bot tiene ordenado decir de la empresa, el juez tiene que poder comprobarlo (1-oct). Va tras el
        # catálogo: los dos son fijos por idioma, así que el prefijo sigue siendo cacheable.
        from src.prompts.info import JUEZ_PRESENTACION_EN, JUEZ_PRESENTACION_ES  # lazy

        cabeza.append(JUEZ_PRESENTACION_ES if lang == "es" else JUEZ_PRESENTACION_EN)
        grounding_context = "\n\n".join([*cabeza, grounding_context])
        # Paso 6 (27-sep): corregir un precio que cita el cliente ("¿son los mismos 2.215.000?" -> "el
        # precio es 2.450.000, no 2.215.000") nombra su cifra; el guard la tomaba por inventada y la
        # respuesta acababa en "no lo tengo". Sus propias cifras cuentan; el juez sigue rechazando que
        # se CONFIRME un precio que el contexto no respalda.
        amounts_context = f"{grounding_context}\n{redact_pii(query)}"
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        fallback = FALLBACK_ES if lang == "es" else FALLBACK_EN

        # The answer is sampled at temperature 0.3, so it varies run to run. A
        # one-off answer that embellishes a detail trips the grounding judge and,
        # before, went straight to the "no info" fallback — the source of the
        # intermittent (~1/3) false fallbacks. We now REGENERATE the answer once
        # when any guard rejects: a fresh sample is usually grounded, turning a
        # false fallback into a real answer. Only fall back if both tries fail.
        def _apuntar_avisos() -> None:
            """CAL-A5: los avisos de `una_vez` ya dados quedan en la lista del estado (`avisos_hechos["dados"]`)
            para no repetirlos en los turnos siguientes."""
            dados = (avisos_hechos or {}).get("dados")
            if dados is None:
                return
            for aviso in avisos_elegidos:
                if aviso.get("una_vez") and aviso["id"] not in dados:
                    dados.append(aviso["id"])

        last_reject = ""
        def _con_aviso_al_final(answer: str, aviso: tuple[str, str]) -> str:
            """CAL-A6: la respuesta con la frase del aviso, si la frase pasa las mismas guardas deterministas que la
            respuesta (ni importes, ni enlaces, ni teléfonos, ni datos personales que no estén en el contexto). El
            aviso queda apuntado como dado en la lista del estado, como los de A5."""
            from src.agents import rag_plan  # lazy

            aviso_id, frase = aviso
            if not (is_coherent_text(frase) and currency_amounts_grounded(frase, amounts_context)
                    and urls_grounded(frase, grounding_context) and not contains_phone_number(frase)
                    and not requests_personal_data(frase)):
                logger.info(f"[RAG][AVISO_FINAL] {aviso_id}: la frase no pasa las guardas, no se añade")
                return answer
            dados = (avisos_hechos or {}).get("dados")
            if isinstance(dados, list) and aviso_id not in dados:
                dados.append(aviso_id)
            return rag_plan.insertar_frase(answer, frase)

        respuesta_buena = None  # CAL-A3: la respuesta aprobada a la que solo le faltaba algún punto
        for attempt in range(2):
            try:
                response = await generar_con_respaldo(client, messages)
            except Exception as exc:
                logger.warning(f"[RAG][LLM] failed to answer query={query[:60]}... error={exc}")
                return fallback

            answer = response.choices[0].message.content or ""

            # Deterministic guards first: never let a price/%/URL not in the
            # context reach the customer (e.g. "$180" when the real price is "$178").
            # Coherent-prose check comes first -- garbled output (e.g. the literal
            # `{" "}`, found live 2026-09-01 lote 7) has no price/URL/personal-data
            # to trip the other guards on, so it needs its own catch.
            if not is_coherent_text(answer):
                last_reject = "garbled_output"
            elif not currency_amounts_grounded(answer, amounts_context):
                last_reject = "ungrounded_amount"
            elif not urls_grounded(answer, grounding_context):
                last_reject = "ungrounded_url"
            elif not capacity_claims_grounded(answer, grounding_context):
                last_reject = "ungrounded_capacity"
            elif not inactive_certified_companion_not_contradicted(answer, grounding_context):
                # Hallazgo en vivo (lote 12, 2026-09-02/03): con la regla de
                # negocio correctamente inyectada en el contexto, el LLM la
                # contradice de todos modos ~1/3 de las veces. Regenerar;
                # una segunda muestra normalmente respeta la regla.
                last_reject = "contradicts_inactive_certified_rule"
            elif requests_personal_data(answer):
                # Never run a manual booking ritual in chat (names/ID/passport):
                # bookings close with the online link or an advisor handoff.
                last_reject = "requests_personal_data"
            elif contains_phone_number(answer):
                # Never hand the customer a phone/WhatsApp number (owner decision):
                # advisor contact is handled via the internal Chatwoot handoff.
                # Regenerate; a fresh sample usually drops the number.
                last_reject = "phone_number"
            elif not verify_grounding and not require_grounding:
                _apuntar_avisos()
                return answer
            else:
                aviso_final = None
                if settings.avisos_al_final:
                    # CAL-A6: el revisor de avisos va A LA VEZ que el juez de siempre (no suma latencia si tarda menos
                    # que él); lo que diga solo cuenta si la respuesta pasa.
                    from src.agents import rag_plan  # lazy

                    (grounded, reason), aviso_final = await asyncio.gather(
                        _verify_grounding(answer, grounding_context, lang=lang),
                        rag_plan.aviso_al_final(history, redact_pii(query), answer, lang,
                                                dados=(avisos_hechos or {}).get("dados")))
                else:
                    grounded, reason = await _verify_grounding(answer, grounding_context, lang=lang)
                if grounded and attempt == 0 and (
                        (settings.rag_revisor_completitud and puntos) or settings.rag_revisor_avisos
                        or avisos_elegidos):
                    # CAL-A3/A4: el revisor de siempre solo castiga inventar; aquí también dejarse algo (A3: un punto
                    # del plan; A4: un aviso que el cliente necesita). Si falta, se reintenta UNA vez con lo que
                    # falta; si el reintento sale peor, vale esta.
                    from src.agents import rag_plan  # lazy

                    faltan = await rag_plan.puntos_sin_cubrir(puntos, answer, lang) if (
                        settings.rag_revisor_completitud and puntos) else []
                    avisos = await rag_plan.avisos_que_faltan(redact_pii(query), grounding_context, answer, lang) if (
                        settings.rag_revisor_avisos) else []
                    if avisos_elegidos:
                        # CAL-A5: los eligió el código, así que aquí solo se comprueba que ESTÉN (la misma llamada
                        # barata de A3; ningún modelo vuelve a decidir cuáles hacían falta).
                        from src.flows import avisos as avisos_mod  # lazy

                        avisos += await rag_plan.puntos_sin_cubrir(
                            avisos_mod.textos(avisos_elegidos), answer, lang)
                    if faltan or avisos:
                        partes = ([rag_plan.feedback_de_faltan(faltan, lang)] if faltan else []) + (
                            [rag_plan.feedback_de_avisos(avisos, lang)] if avisos else [])
                        respuesta_buena = answer
                        messages = [*messages, {"role": "assistant", "content": answer},
                                    {"role": "user", "content": "\n\n".join(partes)}]
                        logger.info(f"[RAG][COMPLETITUD] reintento: faltan {len(faltan)} puntos, {len(avisos)} avisos")
                        continue
                if grounded:
                    _apuntar_avisos()
                    if aviso_final:
                        answer = _con_aviso_al_final(answer, aviso_final)
                    logger.info(
                        f"[RAG] Query: {query[:60]}... | Docs: {len(docs) if docs else 0} | "
                        f"Tokens: {response.usage.total_tokens} | "
                        # Paso 9 (l2-2): cuanto del prompt reutilizo el caché de OpenAI.
                        f"Cached: {getattr(getattr(response.usage, 'prompt_tokens_details', None), 'cached_tokens', 0)} | "
                        f"Sources: {context_sources or []}"
                    )
                    return answer
                last_reject = reason
            logger.info(f"[RAG][GROUNDING] attempt {attempt + 1} rejected ({last_reject}) query={query[:50]}...")
            if attempt == 0:
                # 28-sep: la segunda muestra sabe QUÉ se rechazó (antes se repetía la misma petición y el invento).
                feedback = regen_feedback(last_reject, lang)
                if feedback:
                    messages = [*messages, {"role": "assistant", "content": answer},
                                {"role": "user", "content": feedback}]

        if respuesta_buena is not None:
            _apuntar_avisos()
            logger.info("[RAG][COMPLETITUD] el reintento no pasó: se queda la primera respuesta aprobada")
            return respuesta_buena
        logger.warning(
            f"[RAG][GROUNDING] Rejecting after 2 attempts query={query[:60]}... reason={last_reject}"
        )
        return fallback

    # 1) Sin documentos del KB
    if not docs:
        logger.info(f"[RAG] No docs found query={query[:60]}...")
        if extra_context or catalog_prefix:
            # No hay nada util en el KB, pero si tenemos resumen de estado: dejamos que el LLM
            # razone SOLO con ese contexto en lugar de ir directo al fallback.
            # El juez de grounding es OBLIGATORIO aqui (require_grounding): sin
            # soporte del KB, el modelo responderia de su conocimiento propio.
            return await _answer_with_llm(
                extra_context or "", context_sources=["extra_context_only"], require_grounding=True
            )
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # 2) Hay documentos pero ninguno con confianza suficiente
    if not any(_is_confident(doc) for doc in docs):
        sources = [doc.get("metadata", {}).get("source", "unknown") for doc in docs]
        top_score = max((_score_for_threshold(doc) for doc in docs), default=0.0)
        logger.info(
            f"[RAG] Low confidence query={query[:60]}... retrieval_query={safe_query[:120]}... "
            f"top_score={top_score:.3f} min_cosine={settings.rag_min_score:.3f} "
            f"min_bm25={settings.rag_min_bm25_rank:.3f} sources={sources}"
        )
        if extra_context or catalog_prefix:
            # Igual que en el caso sin docs: ignoramos estos resultados de baja confianza
            # y dejamos que el LLM trabaje solo con el contexto de estado, pero con
            # el juez de grounding SIEMPRE activo (ver require_grounding arriba).
            return await _answer_with_llm(
                extra_context or "", context_sources=["extra_context_only"], require_grounding=True
            )
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # 3) Hay documentos suficientemente relevantes -> expandimos contexto padre y respondemos
    docs = await _expand_with_parent_context(docs, lang=lang)
    context_parts = []
    sources = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.get("metadata", {})
        source = metadata.get("source", "unknown")
        sources.append(source)
        context_parts.append(f"[{i}] Fuente: {source}\n{redact_pii(doc['content'])}")
    context = "\n\n".join(context_parts)

    return await _answer_with_llm(context, context_sources=sources)
