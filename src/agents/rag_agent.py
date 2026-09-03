"""
RAG Agent for knowledge base retrieval.

Uses pgvector embeddings to answer questions about Diving Planet
services, policies, and FAQs that fall outside the predefined
decision tree.
"""

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
from src.agents.query_rewriter import condense_query
from src.config import settings
from src.knowledge.loader import (
    load_brand_tone,
    load_conversations,
    load_faqs,
    load_policies,
)
from src.knowledge.vector_store import detect_query_topics, get_pool, search_knowledge_base
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

_BRAND_TONE_CACHE: dict | None = None
_CONVERSATIONS_CACHE: list[dict] | None = None
_FAQS_CACHE: list | None = None
_POLICIES_CACHE: dict | None = None
FEWSHOT_MAX_CHARS = 220


def _load_brand_tone_cached() -> dict:
    """Load and cache brand_tone.json at first access."""
    global _BRAND_TONE_CACHE
    if _BRAND_TONE_CACHE is None:
        _BRAND_TONE_CACHE = (load_brand_tone() or {}).get("brand_tone", {})
    return _BRAND_TONE_CACHE


def _load_faqs_cached() -> list:
    """Load and cache the faqs list at first access."""
    global _FAQS_CACHE
    if _FAQS_CACHE is None:
        _FAQS_CACHE = (load_faqs() or {}).get("faqs") or []
    return _FAQS_CACHE


def _load_policies_cached() -> dict:
    """Load and cache the policies dict at first access."""
    global _POLICIES_CACHE
    if _POLICIES_CACHE is None:
        _POLICIES_CACHE = (load_policies() or {}).get("policies") or {}
    return _POLICIES_CACHE


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


def _load_conversations_cached() -> list[dict]:
    """Load and cache conversation_examples from conversations.json at first access."""
    global _CONVERSATIONS_CACHE
    if _CONVERSATIONS_CACHE is None:
        _CONVERSATIONS_CACHE = (load_conversations() or {}).get("conversation_examples", []) or []
    return _CONVERSATIONS_CACHE


# Translate the legacy/Spanish `extracted_topics` labels stored in
# conversations.json into the canonical TOPIC_PATTERNS labels used by
# detect_query_topics(). Canonical labels (certification, location_islands,
# availability, schedule, meeting_point, pricing, equipment, discount_colombian,
# refresher, accommodation, weather_cancellation, booking...) pass through
# unchanged via aliases.get(t, t).
_FEWSHOT_TOPIC_ALIASES: dict[str, str] = {
    # Pricing / currency
    "precios": "pricing",
    "precios_usd": "pricing",
    "price_usd": "pricing",
    "precio_desde_isla": "pricing",
    # Colombian / resident pricing
    "precio_colombianos": "discount_colombian",
    "precio_local_residente": "discount_colombian",
    "precio_local": "discount_colombian",
    # Availability / booking cutoff
    "disponibilidad_ultima_hora": "availability",
    "ultima_hora": "availability",
    "corte_reserva_online": "availability",
    # Schedule
    "horarios": "schedule",
    "snorkel": "schedule",
    # Meeting point
    "punto_encuentro": "meeting_point",
    "punto_de_encuentro": "meeting_point",
    # Islands / pickup / base location
    "recogida_en_hotel": "location_islands",
    "planes_desde_islas": "location_islands",
    "base_en_islas": "location_islands",
    "base_cocoliso": "location_islands",
    "diferencia_isla_vs_cartagena": "location_islands",
    # Equipment / included
    "ubicacion_equipo": "equipment",
    "equipo_incluido": "equipment",
    "transfer_included": "equipment",
    "incluye": "equipment",
    # Booking process
    "grupo_mixto": "booking",
    "proceso_reserva": "booking",
    # Refresher
    "refresh": "refresher",
    # Weather / cancellation
    "clima": "weather_cancellation",
    "cancelacion_reembolso": "weather_cancellation",
    # Accommodation
    "alojamiento": "accommodation",
    # Courses
    "open_water_course": "certification",
}


# Stale few-shot guard: the "Colombian discount" was removed (v0.18.0) — Colombian
# clients now simply pay in COP (same price, currency only). Imported WhatsApp
# examples where the ADVISOR offered a special Colombian discount/bonus would
# teach the model the old behavior, so we skip them from few-shot selection.
# We only exclude examples whose ADVISOR messages pair a discount word with a
# Colombian/resident word — examples that merely quote a COP price for Colombians
# ("el valor para colombianos es 630.000") stay, since that is still correct.
_STALE_DISCOUNT_WORDS = ("descuento", "bono", "tarifa especial", "precio especial", "rebaja")
_STALE_COLOMBIAN_WORDS = ("colombian", "residente", "descuento local", "precio local")


def _strip_accents_lower(text: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


def _example_teaches_stale_colombian_discount(example: dict) -> bool:
    """True if the ADVISOR messages offer a (now-removed) Colombian discount."""
    bot_msgs = (example.get("diving_planet") or {}).get("messages") or []
    for msg in bot_msgs:
        norm = _strip_accents_lower(str(msg))
        if any(d in norm for d in _STALE_DISCOUNT_WORDS) and any(
            c in norm for c in _STALE_COLOMBIAN_WORDS
        ):
            return True
    return False


def _select_fewshot_examples(query: str, lang: str, k: int = 2) -> list[dict]:
    """Pick up to k conversation examples whose extracted_topics overlap with the query topics.

    Returns the raw example dicts (filtered by lang). Empty list if no useful match.
    Uses detect_query_topics() to score overlap; ties broken by example order in JSON.
    Examples that teach the removed Colombian discount are skipped entirely.
    """
    if not query:
        return []
    query_topics = set(detect_query_topics(query))
    if not query_topics:
        return []

    candidates = []
    for example in _load_conversations_cached():
        if (example.get("lang") or "").lower() != lang:
            continue
        if _example_teaches_stale_colombian_discount(example):
            continue
        ex_topics = set(str(t) for t in (example.get("extracted_topics") or []))
        normalized = {_FEWSHOT_TOPIC_ALIASES.get(t, t) for t in ex_topics}
        overlap = len(query_topics & normalized)
        if overlap > 0:
            candidates.append((overlap, example))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [example for _, example in candidates[:k]]


def _format_fewshot_block(examples: list[dict], lang: str) -> str:
    """Render a compact reference block from picked conversation examples.

    Each example is summarised in <= FEWSHOT_MAX_CHARS chars to keep the prompt cheap.
    Framed as 'real situations the center has handled' so the model treats them as
    domain context, not as a template to imitate verbatim.

    Deliberately does NOT quote the real customer's literal message: it's personal,
    specific detail (a spouse, a named hotel, a family composition) that belongs to a
    DIFFERENT, unrelated customer. Quoting it invited the model to blend those details
    into its answer for the current customer (e.g. inventing "tu esposo" out of thin
    air because a past customer's message happened to mention one). Only the topic
    label and the advisor's response pattern are shown — that's what teaches tone and
    coverage without leaking someone else's facts.
    """
    if not examples:
        return ""

    header = (
        "Situaciones reales del centro (referencia de tono/cobertura, NO son datos del cliente actual):"
        if lang == "es"
        else "Real situations the center has handled (tone/coverage reference, NOT facts about the current customer):"
    )
    lines = [header]
    for ex in examples:
        scenario = (ex.get("scenario") or "").strip()
        first_bot_action = ""
        bot_msgs = ((ex.get("diving_planet") or {}).get("messages") or [])
        if bot_msgs:
            first_bot_action = str(bot_msgs[0]).strip()

        action = first_bot_action[:120] + ("..." if len(first_bot_action) > 120 else "")
        bullet = f"- {scenario[:60]} | Asesor cubrio: {action}"
        if lang == "en":
            bullet = f"- {scenario[:60]} | Advisor covered: {action}"
        # Hard cap per bullet
        if len(bullet) > FEWSHOT_MAX_CHARS:
            bullet = bullet[:FEWSHOT_MAX_CHARS - 3] + "..."
        lines.append(bullet)

    return "\n".join(lines)


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


def build_system_prompt(lang: str, query: str | None = None) -> str:
    """Compose the full system prompt: intro + dynamic tone + body + optional few-shot block.

    When ``query`` is provided, picks up to 2 topic-matching examples from conversations.json
    and appends them as compact reference context (not as imitation templates).
    """
    fewshot_block = ""
    if query:
        examples = _select_fewshot_examples(query, lang, k=2)
        fewshot_block = _format_fewshot_block(examples, lang)

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

    if fewshot_block:
        prompt = f"{prompt}\n\n{fewshot_block}"
    return prompt


FOOD_QUERY_PATTERN = re.compile(
    r"\b(comida|almuerzo|lunch|meal|meals|food|vegetariano|vegetariana|vegetarian|vegano|vegana|vegan|celiaco|celiaca|celiac|alergia|alergias|allergy|allergies)\b",
    re.IGNORECASE,
)

DIETARY_QUERY_PATTERN = re.compile(
    r"\b(vegetariano|vegetariana|vegetarian|vegano|vegana|vegan|celiaco|celiaca|celiac|alergia|alergias|allergy|allergies)\b",
    re.IGNORECASE,
)

FOOD_FAQ_QUESTIONS = {
    "meal": {
        "es": "¿Que comida incluye el tour?",
        "en": "What food is included in the tour?",
    },
    "dietary": {
        "es": "Soy vegetariano o tengo una alergia alimentaria, ¿pueden atenderme?",
        "en": "I'm vegetarian or have a food allergy. Can you accommodate me?",
    },
}


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


def _find_food_faq_answer(question: str, lang: str) -> str | None:
    faqs = _load_faqs_cached()
    question_key = "question_es" if lang == "es" else "question_en"
    answer_key = "answer_es" if lang == "es" else "answer_en"
    normalized_question = _normalize_text(question)

    for faq in faqs:
        faq_question = faq.get(question_key)
        faq_answer = faq.get(answer_key)
        if not isinstance(faq_question, str) or not isinstance(faq_answer, str):
            continue
        if _normalize_text(faq_question) == normalized_question and faq_answer.strip():
            return faq_answer.strip()
    return None


def _food_policy_answer(lang: str) -> str | None:
    policies = _load_policies_cached()
    food_policy = policies.get("food_policy") or {}
    answer = food_policy.get(lang)
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return None


# The food canonical answer must NOT hijack a broader booking/recommendation
# query that merely mentions a dietary word (e.g. "somos 8, 3 open water... uno
# vegetariano, ¿qué recomiendan y cuánto sale?"). When the message also carries
# group-composition / cert-level / budget / recommendation / package signals,
# food is incidental — let RAG answer the whole thing (it still covers the food).
_FOOD_HIJACK_GUARD = re.compile(
    r"\b(?:recomien\w+|recommend\w*|presupuesto|budget|"
    r"\d+\s+personas?|somos\s+\d+|we\s+are\s+\d+|group\s+of\s+\d+|"
    r"open\s+water|advanced|rescue|divemaster|"
    r"paquete|package|reserv\w+|book)\b",
    re.IGNORECASE,
)


# Canonical shortcuts answer with a fixed/generic text instead of real retrieval.
# When the regex that decides "this is generic, not a specific question" misses a
# phrasing we didn't anticipate (regional slang, synonyms, typos), the shortcut
# still fires and the client silently gets an answer that looks complete but may
# not cover what they actually asked. This closing line is a safety net: it makes
# the shortcut itself invite the client to re-ask with detail, so an uncovered
# phrasing doesn't end the conversation with a wrong impression.
_CANONICAL_SAFETY_NET = {
    "es": "\n\nSi tu pregunta era sobre algo más concreto que esto, cuéntamelo con más detalle y te confirmo con exactitud. 🙂",
    "en": "\n\nIf your question was about something more specific than this, tell me more and I'll confirm the exact details. 🙂",
}


def _canonical_food_answer(query: str, lang: str) -> str | None:
    if not FOOD_QUERY_PATTERN.search(query):
        return None

    # Food is incidental inside a bigger booking/recommendation query -> defer to RAG.
    if _FOOD_HIJACK_GUARD.search(query):
        return None

    answer = None
    if DIETARY_QUERY_PATTERN.search(query):
        answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["dietary"][lang], lang)

    if not answer:
        answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["meal"][lang], lang)

    if not answer:
        answer = _food_policy_answer(lang)

    if not answer:
        return None

    return answer + _CANONICAL_SAFETY_NET[lang]


# "What do you offer / what options / what plans for diving?" — an open overview
# question. RAG used to answer it by picking a couple of arbitrary services (e.g.
# minicourse + Nitrox specialty), which read as random. Instead we give one short,
# structured overview grouped by the customer's situation. Requires BOTH an
# "offer/options/what-can-I-do" phrase AND a diving word, so specific questions
# ("what does the minicourse include?", "how much is diving?") don't match.
_OVERVIEW_PHRASE = re.compile(
    r"\b(?:qu[eé]\s+(?:ofrec\w*|tien\w+|hay|opciones|planes|actividades|tipos|servicios)|"
    r"qu[eé]\s+puedo\s+hacer|qu[eé]\s+se\s+puede\s+hacer|"
    r"what\s+(?:do\s+you\s+(?:offer|have|got)|options|can\s+i\s+do|kind\s+of|"
    r"\w+\s+options\s+do\s+you\s+have)|"
    r"which\s+(?:options|plans)|tell\s+me\s+about\s+(?:your\s+)?(?:diving|options))\b",
    re.IGNORECASE,
)
# Bare "planes"/"opciones"/"alternativas" (no "qué" in front) used to match
# ANYWHERE in the message, so "mejor evitar planes muy físicos" (a booking
# statement about the father's mobility, nothing to do with tour packages)
# false-positived into the overview (found live 2026-07-17). These words only
# unambiguously mean "what do you offer" when they're basically the WHOLE
# message (a short standalone query like "¿planes?"), so this only fires then.
_OVERVIEW_BARE_WORD_RE = re.compile(
    r"^[\s¿?¡!.,]*(?:opciones|planes|alternativas|options|plans|alternatives)[\s¿?¡!.,]*$",
    re.IGNORECASE,
)
_OVERVIEW_DIVING_WORD = re.compile(
    r"\b(?:buce\w*|buse\w*|buz\w*|dive|dives|diver|divers|diving|scuba|snorkel\w*|inmersi\w+)\b",
    re.IGNORECASE,
)
# Guard: don't hijack price/inclusion/logistics questions that happen to match.
_OVERVIEW_EXCLUDE = re.compile(
    r"\b(?:precio|precios|cuesta|cu[aá]nto|vale|incluye|incluyen|"
    r"price|cost|how\s+much|include|includes)\b",
    re.IGNORECASE,
)

# The overview covers 4 audiences (never dived / certified / wants course /
# snorkel-only) so it's safe by default, but a client who already tells us
# "soy buzo"/"tengo el open water" doesn't need to be asked "¿nunca has
# buceado?" first — it reads as if we ignored what they just said. When this
# fires, the certified block moves to the front and the intro acknowledges it,
# without dropping the other blocks (their companion could still be a
# beginner, so full coverage stays).
_ALREADY_CERTIFIED_RE = re.compile(
    r"\b(?:soy|somos|estoy|estamos)\s+(?:ya\s+)?(?:un[oa]?\s+)?buz[oa]s?\b"
    r"|\bya\s+(?:soy|somos)\s+(?:buz[oa]s?|certificad\w*)\b"
    r"|\b(?:soy|somos|estoy|estamos)\s+certificad\w*\b"
    r"|\btengo\s+(?:el\s+|la\s+|mi\s+)?(?:open\s*water|advanced|rescue|divemaster|licencia)\b"
    r"|\bi(?:'?m|\s+am)\s+a\s+certified\s+diver\b|\bwe\s+are\s+certified\s+divers?\b"
    r"|\bi\s+have\s+(?:my\s+)?open\s*water\b",
    re.IGNORECASE,
)
# Excludes "wants to get certified" phrasings so they're never read as already
# holding a cert (mirrors intent_detector._WANTS_CERT_RE at a lighter weight,
# since this only needs to gate the overview's framing, not full state).
_WANTS_CERT_EXCLUDE_RE = re.compile(
    r"\bquiero\s+(?:ser|sacar(?:me)?|hacer(?:me)?|certificar(?:me)?)\b"
    r"|\bme\s+gustar[ií]a\s+certificarme\b|\bwant\s+to\s+(?:get|become)\s+certified\b",
    re.IGNORECASE,
)

# A client traveling with someone else who doesn't dive is asking, in part,
# what THAT person can do — the overview used to ignore this entirely. Not
# everyone says "acompañante": "soy buzo y uno acompaña", "somos 5, tres
# bucean y dos no", "mi pareja no bucea" all describe the same situation
# without ever using the noun, so several independent phrasings are checked.
_MENTIONS_COMPANION_RE = re.compile(r"\bacompa\w+|\bcompanion\w*\b", re.IGNORECASE)
# Explicit "doesn't/don't dive" — conjugation already encodes singular/plural
# in Spanish ("no bucea" vs "no bucean"), so it doubles as the plural signal.
_NON_DIVER_SINGULAR_RE = re.compile(
    r"\bno\s+bucea\b|\bdoesn'?t\s+dive\b|\bnot\s+diving\b", re.IGNORECASE
)
_NON_DIVER_PLURAL_RE = re.compile(
    r"\bno\s+bucean\b|\bdon'?t\s+dive\b|\bnon-?divers\b", re.IGNORECASE
)
# Elliptical split — the verb is omitted the second time ("tres bucean y dos
# no", "y el resto no"; EN "three dive and two don't"), so anchor on
# "y/and <quantifier> no/don't". Spanish drops the verb after "no"; English
# keeps the negated auxiliary ("don't"/"doesn't"), so each needs its own regex.
_NON_DIVER_ELLIPTICAL_ES_RE = re.compile(
    r"\by\s+(?:\d+|uno|una|dos|tres|cuatro|cinco|seis|otro|otra|otros|otras|"
    r"el\s+resto|los\s+dem[aá]s)\s+no\b",
    re.IGNORECASE,
)
_NON_DIVER_ELLIPTICAL_EN_RE = re.compile(
    r"\band\s+(?:\d+|one|two|three|four|five|another|others?|the\s+rest)\s+"
    r"(?:don'?t|doesn'?t)\b",
    re.IGNORECASE,
)
_NON_DIVER_ELLIPTICAL_PLURAL_WORDS = (
    "dos", "tres", "cuatro", "cinco", "seis", "otros", "otras",
    "el resto", "los dem", "two", "three", "four", "five", "rest", "others",
)
# Distinguishes "un acompañante" (one) from several, so the reply says "your
# companion" vs "your companions" instead of always assuming just one.
# Plural fires on the plain plural noun ("acompañantes"/"companions") or a
# quantifier > 1 right before it ("2 acompañantes", "varios amigos que...").
_COMPANION_PLURAL_QUANTIFIER_RE = re.compile(
    r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|varios|varias|"
    r"algunos|algunas|unos|unas|several|multiple|two|three|four|five)\s+(?:acompa\w+|companions?)",
    re.IGNORECASE,
)


def _mentions_already_certified(query: str) -> bool:
    return bool(_ALREADY_CERTIFIED_RE.search(query)) and not _WANTS_CERT_EXCLUDE_RE.search(query)


def _mentions_plural_companions(query: str) -> bool:
    match = re.search(r"\bacompa\w+\b|\bcompanions?\b", query, re.IGNORECASE)
    if match and match.group(0).lower().rstrip("?.,;:!").endswith("s"):
        return True
    return bool(_COMPANION_PLURAL_QUANTIFIER_RE.search(query))


def _detect_companion_mention(query: str) -> tuple[bool, bool]:
    """Returns (has_companion, is_plural) from any of the phrasings a client
    might use to describe someone in the group who doesn't dive."""
    if _MENTIONS_COMPANION_RE.search(query):
        return True, _mentions_plural_companions(query)
    if _NON_DIVER_PLURAL_RE.search(query):
        return True, True
    if _NON_DIVER_SINGULAR_RE.search(query):
        # "el resto"/"los demás"/"the rest"/"the others" are collective nouns
        # that take a grammatically singular verb ("el resto no bucea") even
        # when they refer to several people — bias plural for these.
        if re.search(r"\b(?:el\s+resto|los\s+dem[aá]s|the\s+rest|the\s+others?)\b", query, re.IGNORECASE):
            return True, True
        return True, False
    elliptical = _NON_DIVER_ELLIPTICAL_ES_RE.search(query) or _NON_DIVER_ELLIPTICAL_EN_RE.search(query)
    if elliptical:
        matched = elliptical.group(0).lower()
        is_plural = any(w in matched for w in _NON_DIVER_ELLIPTICAL_PLURAL_WORDS)
        return True, is_plural
    return False, False


def _canonical_diving_overview_answer(query: str, lang: str) -> str | None:
    if _OVERVIEW_EXCLUDE.search(query):
        return None
    phrase_match = _OVERVIEW_PHRASE.search(query) or _OVERVIEW_BARE_WORD_RE.match(query.strip())
    if not (phrase_match and _OVERVIEW_DIVING_WORD.search(query)):
        return None

    already_certified = _mentions_already_certified(query)
    has_companion, plural_companions = _detect_companion_mention(query)

    # Once we already know the client is certified, re-asking "¿ya eres buzo
    # certificado?" as a bullet heading is redundant with the intro that just
    # acknowledged it — swap that block for a statement instead of a question.
    # And when there's ALSO a companion, the generic "¿nunca has buceado?"
    # block says the same thing as the companion line below (minicurso/
    # snorkel/accompany), just aimed at a generic "you" instead of "your
    # companion" — drop it to avoid saying it twice. Without a companion, it
    # stays (it may still be useful for someone else not mentioned).
    drop_beginner_block = already_certified and has_companion

    if lang == "es":
        intro = (
            "🌊 *Buceamos en las Islas del Rosario* (Parque Nacional Corales del Rosario), "
            "a 45–60 min en lancha desde Cartagena: aguas cálidas, arrecifes y mucha vida marina. "
        )
        if already_certified:
            intro = "¡Qué bien que ya seas buzo certificado! 🤿 " + intro
        intro += "Te resumo las opciones:\n\n"

        blocks = {
            "beginner": (
                "🆕 *¿Nunca has buceado?* → el *Minicurso de buceo* (bautismo): teoría, práctica en "
                "piscina y una inmersión en el mar con instructor. Desde los 10 años."
            ),
            "certified": (
                "🤿 *Para ti*: *paquetes de inmersiones* — 2 buceos en 1 día, o planes multi-día "
                "(4, 5, 7 o 9 buceos)."
                if already_certified else (
                    "🤿 *¿Ya eres buzo certificado?* → *paquetes de inmersiones*: 2 buceos en 1 día, o "
                    "planes multi-día (4, 5, 7 o 9 buceos)."
                )
            ),
            "course": (
                "🎓 *¿Quieres sacarte el título?* → *cursos PADI*: Open Water (el básico), Advanced, "
                "Rescue, Divemaster y especialidades."
            ),
            "snorkel": (
                "🐠 Y si prefieres sin bucear, el *snorkel* es una chulada para ver el arrecife desde "
                "la superficie."
            ),
        }
        if already_certified:
            order = ("certified", "course", "snorkel") if drop_beginner_block else (
                "certified", "course", "snorkel", "beginner"
            )
        else:
            order = ("beginner", "certified", "course", "snorkel")
        body = "\n\n".join(blocks[k] for k in order)

        if plural_companions:
            companion_line = (
                "\n\n👥 *¿Tus acompañantes no bucean?* También tienen opciones: pueden hacer el "
                "*minicurso* si quieren probar, ir de *snorkel*, o simplemente acompañarte en "
                "la lancha sin bucear."
            )
        elif has_companion:
            companion_line = (
                "\n\n👥 *¿Tu acompañante no bucea?* También tiene opciones: puede hacer el "
                "*minicurso* si quiere probar, ir de *snorkel*, o simplemente acompañarte en "
                "la lancha sin bucear."
            )
        else:
            companion_line = ""
        outro = "\n\n¿Cuál te llama? Si quieres te armo la reserva. 😄"
        return intro + body + companion_line + outro + _CANONICAL_SAFETY_NET["es"]

    intro = (
        "🌊 *We dive in the Rosario Islands* (Corales del Rosario National Park), 45–60 min by boat "
        "from Cartagena: warm water, reefs and lots of marine life. "
    )
    if already_certified:
        intro = "Great to hear you're already a certified diver! 🤿 " + intro
    intro += "Here's a quick overview:\n\n"

    blocks_en = {
        "beginner": (
            "🆕 *Never dived before?* → the *Dive Mini-Course* (Discover Scuba): theory, pool practice "
            "and one open-water dive with an instructor. From age 10."
        ),
        "certified": (
            "🤿 *For you*: *dive packages* — 2 dives in 1 day, or multi-day plans (4, 5, 7 or 9 dives)."
            if already_certified else (
                "🤿 *Already a certified diver?* → *dive packages*: 2 dives in 1 day, or multi-day plans "
                "(4, 5, 7 or 9 dives)."
            )
        ),
        "course": (
            "🎓 *Want to get certified?* → *PADI courses*: Open Water (the basic one), Advanced, "
            "Rescue, Divemaster and specialties."
        ),
        "snorkel": (
            "🐠 And if you'd rather not dive, *snorkeling* is a lovely way to see the reef from the "
            "surface."
        ),
    }
    if already_certified:
        order = ("certified", "course", "snorkel") if drop_beginner_block else (
            "certified", "course", "snorkel", "beginner"
        )
    else:
        order = ("beginner", "certified", "course", "snorkel")
    body = "\n\n".join(blocks_en[k] for k in order)

    if plural_companions:
        companion_line = (
            "\n\n👥 *If your companions don't dive*, they've got options too: they can try the "
            "*mini-course*, go snorkeling, or simply come along on the boat without diving."
        )
    elif has_companion:
        companion_line = (
            "\n\n👥 *If your companion doesn't dive*, they've got options too: they can try the "
            "*mini-course*, go snorkeling, or simply come along on the boat without diving."
        )
    else:
        companion_line = ""
    outro = "\n\nWhich one sounds good? I can put the booking together for you. 😄"
    return intro + body + companion_line + outro + _CANONICAL_SAFETY_NET["en"]


# A GENERIC price question ("¿cuánto cuesta?", "precios?", "how much?") with no
# specific service named. RAG used to deflect with "no info" or a question back;
# instead give a short price overview of the main services (pulled from SERVICES
# so it stays current). A price question that DOES name a service ("cuánto cuesta
# el minicurso") is left to RAG, which answers it well.
_PRICE_QUESTION = re.compile(
    r"\b(?:cu[aá]nto\s+(?:cuesta|cuestan|vale|valen|sale|salen|es|ser[ií]a)|"
    r"cu[aá]nto|precios?|qu[eé]\s+precios?|tarifas?|how\s+much|prices?|cost|"
    # Auditoría 2026-08-26 (Grupo 5, portado de pre_gadea v0.21.5): "¿qué es
    # más barato, X o Y?" es una pregunta de precio tan real como "¿cuánto
    # cuesta?" pero no usa ninguna de esas palabras — sin esto,
    # `_canonical_price_named_services_answer` nunca llegaba a evaluarse
    # para una comparación de precio.
    r"m[aá]s\s+barato|m[aá]s\s+econ[oó]mico|menos\s+caro|cheaper|less\s+expensive|"
    r"which\s+is\s+cheaper)\b",
    re.IGNORECASE,
)
_PRICE_SPECIFIC = re.compile(
    r"\b(?:minicurso|mini\s?curso|snorkel\w*|open\s*water|advanced|rescue|"
    r"divemaster|nitrox|especialidad|comida|almuerzo|acompa\w+|companion|"
    r"noche|nocturn\w+|paquetes?|referido|referral|fish|peces|flotabilidad|buoyancy|"
    r"naturalista|naturalist|vuelo|hotel|"
    # "el buceo"/"bucear"/"diving" bare is itself a specific service (certified
    # diving), not a generic price question — found live 2026-07-17: "¿qué
    # precio tiene el buceo?" fell into the 4-service generic overview (with
    # both currencies) instead of a targeted answer, even mid-flow where the
    # client had already told the bot they're a certified group choosing
    # between the 2-dives-1-day and multi-day plans.
    r"buce\w*|buse\w*|buz\w*|div(?:e|es|er|ers|ing)|"
    # Multi-day pricing ("paquetes multidía", "varios días", "multi-day") is
    # its own specific question — the canonical overview below only mentions
    # it in passing without real prices, so it must fall through to RAG
    # (which retrieves the actual per-package multi-day pricing FAQ). Found
    # missing 2026-07-16: bare "paquete" (singular, no wildcard) never matched
    # the plural "paquetes" either, so "los paquetes multidía" slipped past
    # this exclusion entirely and got the generic single-day-only summary.
    r"multi[\s\-]?d[ií]as?|varios\s+d[ií]as|\d\s*(?:d[ií]as|dives?|inmersi\w+)|"
    r"multi[\s\-]?day)\b",
    re.IGNORECASE,
)


def _fmt_price_usd(v) -> str:
    try:
        return f"${int(round(float(v)))}"
    except (TypeError, ValueError):
        return "consultar"


def _fmt_price_cop(v) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "consultar"


def _canonical_price_overview_answer(query: str, lang: str) -> str | None:
    if not _PRICE_QUESTION.search(query):
        return None
    if _PRICE_SPECIFIC.search(query):
        return None  # names a specific service -> let RAG answer it precisely
    # A price question that also carries a group/cert booking is not a plain
    # "what are the prices?" — let the flow/RAG handle it.
    if _FOOD_HIJACK_GUARD.search(query):
        return None
    try:
        from src.flows.catalog import SERVICES
    except Exception:
        return None
    svc = {k: SERVICES.get(k, {}) for k in ("2_dives_1_day", "minicourse", "snorkeling", "open_water")}

    def line(usd, cop):
        return f"{_fmt_price_usd(usd)} USD / {_fmt_price_cop(cop)} COP"

    cert = svc["2_dives_1_day"]
    mini = svc["minicourse"]
    snk = svc["snorkeling"]
    ow = svc["open_water"]
    if lang == "es":
        return (
            "🌊 Te dejo los *precios de referencia saliendo desde Cartagena* "
            "(incluyen lancha, almuerzo, equipo y entrada al parque), con el descuento por reservar online:\n\n"
            f"🤿 *Buceo certificado* (2 inmersiones, 1 día): *{line(cert.get('price_usd'), cert.get('price_cop'))}* por persona.\n"
            f"🆕 *Minicurso de buceo* (sin experiencia): *{line(mini.get('price_usd'), mini.get('price_cop'))}* por persona.\n"
            f"🐠 *Snorkel*: *{line(snk.get('price_usd'), snk.get('price_cop'))}* por persona.\n"
            f"🎓 *Curso Open Water* (certificación PADI): *{line(ow.get('price_usd'), ow.get('price_cop'))}*.\n\n"
            "Los colombianos/residentes pagan en pesos (COP) y los internacionales en dólares (USD) — "
            "mismo precio, sin cobro extra por la divisa. También hay paquetes multi-día (4/5/7/9 inmersiones) "
            "y otros cursos. ¿Cuál te interesa? 😄"
        ) + _CANONICAL_SAFETY_NET["es"]
    return (
        "🌊 Here are the *reference prices departing from Cartagena* "
        "(they include the boat, lunch, gear and park entrance), with the online-booking discount:\n\n"
        f"🤿 *Certified diving* (2 dives, 1 day): *{line(cert.get('price_usd'), cert.get('price_cop'))}* per person.\n"
        f"🆕 *Dive mini-course* (no experience): *{line(mini.get('price_usd'), mini.get('price_cop'))}* per person.\n"
        f"🐠 *Snorkeling*: *{line(snk.get('price_usd'), snk.get('price_cop'))}* per person.\n"
        f"🎓 *Open Water course* (PADI certification): *{line(ow.get('price_usd'), ow.get('price_cop'))}*.\n\n"
        "Colombians/residents pay in pesos (COP) and international guests in dollars (USD) — same price, "
        "no extra charge for the currency. There are also multi-day packages (4/5/7/9 dives) and other "
        "courses. Which one are you interested in? 😄"
    ) + _CANONICAL_SAFETY_NET["en"]


# Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 5, portado de
# pre_gadea v0.21.5): el comentario de `_PRICE_QUESTION` decía "una pregunta
# que SÍ nombra un servicio se deja a RAG, que la responde bien" — medido en
# vivo que es FALSO para una pregunta de precio "en frío" (sin contexto de
# reserva ya establecido): "cuánto cuesta el buceo certificado en dólares?"
# y "cuánto es el snorkel en pesos colombianos?" fallaban el grounding del
# RAG (`ungrounded_amount`/`HALLUCINATED`) y caían al fallback genérico "no
# lo tengo a la mano" — pese a que el precio SÍ está disponible en el mismo
# catálogo `SERVICES` que ya alimenta `_canonical_price_overview_answer`. En
# vez de depender de una retrieval que se ha medido poco fiable para este
# caso muy concreto y bien definido, se responde con el mismo dato
# determinista — pero solo cuando la pregunta nombra EXACTAMENTE uno de los
# 4 servicios del catálogo (buceo certificado/minicurso/snorkel/open water)
# sin ambigüedad; cualquier otra cosa (comida, hotel, buceo nocturno,
# paquetes multi-día, curso specialty...) NO está en este catálogo y sigue
# yendo a RAG como antes.
_PRICE_SINGLE_SERVICE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("certified_diving", re.compile(r"\bbuce\w*|\bbuse\w*|\bbuz\w*|\bdiv(?:e|es|er|ers|ing)\b", re.IGNORECASE)),
    ("minicourse", re.compile(r"\bminicurso\b|\bmini[\s-]?curso\b|\bmini[\s-]?course\b", re.IGNORECASE)),
    ("snorkeling", re.compile(r"\bsnorkel\w*\b", re.IGNORECASE)),
    ("open_water", re.compile(r"\bopen\s*water\b", re.IGNORECASE)),
]
# Cualquiera de estas señales significa que la pregunta NO es un simple
# lookup de precio de catálogo (multi-día, comida, acompañante, curso
# specialty sin precio fijo en `SERVICES`...) — se excluye explícitamente
# para no responder con el precio de UN día cuando preguntan por otra cosa.
_PRICE_NON_CATALOG_RE = re.compile(
    r"\b(?:advanced|rescue|divemaster|nitrox|especialidad|specialty|comida|almuerzo|"
    r"acompa\w+|companion|noche|nocturn\w+|paquetes?|referido|referral|fish|peces|"
    r"flotabilidad|buoyancy|naturalista|naturalist|vuelo|hotel|"
    r"multi[\s\-]?d[ií]as?|varios\s+d[ií]as|\d\s*(?:d[ií]as|dives?|inmersi\w+)|multi[\s\-]?day)\b",
    re.IGNORECASE,
)


_PRICE_CATALOG_LABELS_ES = {
    "certified_diving": "Buceo certificado (2 inmersiones, 1 día)",
    "minicourse": "Minicurso de buceo",
    "snorkeling": "Snorkel",
    "open_water": "Curso Open Water (certificación PADI)",
}
_PRICE_CATALOG_LABELS_EN = {
    "certified_diving": "Certified diving (2 dives, 1 day)",
    "minicourse": "Dive mini-course",
    "snorkeling": "Snorkeling",
    "open_water": "Open Water course (PADI certification)",
}


def _canonical_price_named_services_answer(query: str, lang: str) -> str | None:
    """Precio (o comparación de 1-2 precios) para servicios NOMBRADOS
    explícitamente del catálogo. 2 servicios cubre "¿qué es más barato,
    snorkel o minicurso?" (conv 197, mismo hallazgo): RAG acertaba el
    primero pero fallaba el segundo con "no tengo el precio exacto" pese a
    que SÍ está disponible — 3+ servicios o ninguno se deja a RAG/overview
    (ambiguo o genérico, respectivamente)."""
    if not _PRICE_QUESTION.search(query) or _PRICE_NON_CATALOG_RE.search(query):
        return None
    matched = [key for key, pat in _PRICE_SINGLE_SERVICE_PATTERNS if pat.search(query)]
    if not matched or len(matched) > 2:
        return None
    try:
        from src.flows.catalog import SERVICES
    except Exception:
        return None
    labels = _PRICE_CATALOG_LABELS_ES if lang == "es" else _PRICE_CATALOG_LABELS_EN
    lines = []
    for key in matched:
        lookup_key = "2_dives_1_day" if key == "certified_diving" else key
        svc = SERVICES.get(lookup_key, {})
        usd, cop = svc.get("price_usd"), svc.get("price_cop")
        if usd is None and cop is None:
            return None  # un servicio nombrado sin precio en catálogo -> no arriesgar, dejar a RAG
        price_line = f"{_fmt_price_usd(usd)} USD / {_fmt_price_cop(cop)} COP"
        lines.append((labels[key], price_line))

    disclaimer = (
        "Los colombianos/residentes pagan en pesos (COP) y los internacionales en dólares (USD) "
        "— mismo precio, sin cobro extra por la divisa."
        if lang == "es" else
        "Colombians/residents pay in pesos (COP) and international guests in dollars (USD) — "
        "same price, no extra charge for the currency."
    )
    if len(lines) == 1:
        label, price_line = lines[0]
        if lang == "es":
            body = f"🌊 *{label}*: *{price_line}* por persona (con el descuento por reservar online)."
            outro = "¿Te ayudo a armar la reserva? 😊"
        else:
            body = f"🌊 *{label}*: *{price_line}* per person (with the online-booking discount)."
            outro = "Want me to help you put the booking together? 😊"
    else:
        bullets = "\n".join(f"• *{label}*: {price_line} " + ("por persona." if lang == "es" else "per person.") for label, price_line in lines)
        if lang == "es":
            body = f"🌊 Aquí tienes los precios para comparar:\n\n{bullets}"
            outro = "¿Cuál te gustaría reservar? 😊"
        else:
            body = f"🌊 Here are the prices to compare:\n\n{bullets}"
            outro = "Which one would you like to book? 😊"
    safety = _CANONICAL_SAFETY_NET["es" if lang == "es" else "en"]
    return f"{body}\n\n{disclaimer} {outro}" + safety


# Hallazgo (batería sintética contra PRE, 2026-08-26, lote 4, portado de
# pre_gadea v0.21.9): preguntas de precio de paquete multi-día tenían
# resultado inconsistente — "how much is the 9 dive package?" (EN) RAG
# respondió con NÚMEROS INVENTADOS ($544.5/$605 USD, ninguno de los dos
# coincide con el precio real del catálogo, $602/$668), mientras que
# "cuánto cuesta el paquete de 5 inmersiones?" (ES) cayó al fallback "no lo
# tengo a la mano" — dos fallos distintos (uno peor que el otro: una
# alucinación confiada es más grave que abstenerse) para el mismo tipo de
# pregunta, sobre datos que SÍ están en `SERVICES` con precio exacto (igual
# que `_canonical_price_named_services_answer` para los 4 servicios base).
# Se responde determinista para los 4 paquetes multi-día reales (4/5/7/9
# inmersiones) en vez de arriesgar otra alucinación.
_PRICE_PACKAGE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("4_dives_2_days", re.compile(r"\b4\s*(?:d[ií]as?|dives?|inmersi\w+|buceos?)\b|\bpaquete\s+de\s+4\b|\b4[\s-]dive\s+package\b", re.IGNORECASE)),
    ("5_dives_2_days", re.compile(r"\b5\s*(?:d[ií]as?|dives?|inmersi\w+|buceos?)\b|\bpaquete\s+de\s+5\b|\b5[\s-]dive\s+package\b", re.IGNORECASE)),
    ("7_dives_3_days", re.compile(r"\b7\s*(?:d[ií]as?|dives?|inmersi\w+|buceos?)\b|\bpaquete\s+de\s+7\b|\b7[\s-]dive\s+package\b", re.IGNORECASE)),
    ("9_dives_4_days", re.compile(r"\b9\s*(?:d[ií]as?|dives?|inmersi\w+|buceos?)\b|\bpaquete\s+de\s+9\b|\b9[\s-]dive\s+package\b", re.IGNORECASE)),
]


def _canonical_price_package_answer(query: str, lang: str) -> str | None:
    """Precio del paquete multi-día nombrado explícitamente por su número de
    inmersiones (4/5/7/9) — solo cuando la pregunta nombra EXACTAMENTE uno
    de ellos sin ambigüedad; 2+ o ninguno se deja a RAG."""
    if not _PRICE_QUESTION.search(query):
        return None
    matched = [key for key, pat in _PRICE_PACKAGE_PATTERNS if pat.search(query)]
    if len(matched) != 1:
        return None
    try:
        from src.flows.catalog import SERVICES
    except Exception:
        return None
    svc = SERVICES.get(matched[0], {})
    usd, cop = svc.get("price_usd"), svc.get("price_cop")
    if usd is None and cop is None:
        return None
    name = svc.get("name_es") if lang == "es" else svc.get("name_en")
    if not name:
        return None
    price_line = f"{_fmt_price_usd(usd)} USD / {_fmt_price_cop(cop)} COP"
    disclaimer = (
        "Los colombianos/residentes pagan en pesos (COP) y los internacionales en dólares (USD) "
        "— mismo precio, sin cobro extra por la divisa."
        if lang == "es" else
        "Colombians/residents pay in pesos (COP) and international guests in dollars (USD) — "
        "same price, no extra charge for the currency."
    )
    safety = _CANONICAL_SAFETY_NET["es" if lang == "es" else "en"]
    if lang == "es":
        body = f"🌊 *{name}*: *{price_line}* por persona (con el descuento por reservar online)."
        outro = "¿Te ayudo a armar la reserva? 😊"
    else:
        body = f"🌊 *{name}*: *{price_line}* per person (with the online-booking discount)."
        outro = "Want me to help you put the booking together? 😊"
    return f"{body}\n\n{disclaimer} {outro}" + safety


# Hallazgo (batería sintética contra PRE, 2026-08-26, lote 5 — conversaciones
# largas, portado de pre_gadea v0.21.14): "¿el refresher tiene costo
# adicional?" respondía "sí, puede tener costo, escríbenos por WhatsApp para
# confirmar" — CONTRADICE la respuesta determinista que el propio núcleo
# conversacional da cuando ofrece el refresher dentro del flujo de reserva
# ("sin coste adicional"). La política de `policies.json`
# (`refresh_requirement`) es ambigua sobre el costo y no lo aclara — el RAG
# rellenaba el hueco adivinando que sí tiene costo, dos respuestas
# incompatibles a la misma pregunta según el camino. Se responde con la
# verdad ya conocida (gratis) en vez de dejar que el RAG adivine.
_REFRESHER_COST_QUESTION_RE = re.compile(
    r"\brefresher\b.{0,30}\b(?:costo|coste|cuesta|precio|adicional|gratis|cost|"
    r"price|free|extra)\b"
    r"|\b(?:costo|coste|cuesta|precio|cost|price)\b.{0,30}\brefresher\b",
    re.IGNORECASE,
)


def _canonical_refresher_cost_answer(query: str, lang: str) -> str | None:
    if not _REFRESHER_COST_QUESTION_RE.search(query):
        return None
    if lang == "es":
        return (
            "🌊 El *refresher* (repaso corto en el agua antes de la inmersión) "
            "**no tiene costo adicional** — está incluido si te hace falta, sin "
            "cobro extra. ¿Te ayudo a armar la reserva? 😊"
        ) + _CANONICAL_SAFETY_NET["es"]
    return (
        "🌊 The *refresher* (a short in-water review before the dive) is "
        "**at no extra cost** — it's included if you need it, no additional "
        "charge. Want me to help you put the booking together? 😊"
    ) + _CANONICAL_SAFETY_NET["en"]


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


async def _verify_grounding_with_retry(answer: str, context: str, lang: str) -> tuple[bool, str]:
    grounded, reason = await is_grounded(answer, context, lang=lang)
    if grounded:
        return True, reason
    grounded_retry, reason_retry = await is_grounded(answer, context, lang=lang)
    if grounded_retry:
        return True, f"{reason}|retry:{reason_retry}"
    return False, f"{reason}|retry:{reason_retry}"


async def rag_answer(
    query: str,
    lang: str = "es",
    history: list[dict] | None = None,
    extra_context: str | None = None,
    verify_grounding: bool = True,
) -> str:
    """`verify_grounding=False` keeps the deterministic price/URL guards but skips
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
    pii_hits = detect_pii(query)
    if pii_hits:
        logger.warning(f"[RAG][PRIVACY] PII detected in query hits={pii_hits}")
        return privacy_block_message(lang)

    canonical_food_answer = _canonical_food_answer(query, lang)
    if canonical_food_answer:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=food query={query!r} lang={lang}")
        return canonical_food_answer

    diving_overview = _canonical_diving_overview_answer(query, lang)
    if diving_overview:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=diving_overview query={query!r} lang={lang}")
        return diving_overview

    # `_canonical_refresher_cost_answer` va ANTES que `_canonical_price_
    # overview_answer` (hallazgo en vivo, batería sintética contra PRE,
    # 2026-08-26): "does the refresher cost extra?" matchea `_PRICE_QUESTION`
    # (contiene "cost") y "refresher" no está en `_PRICE_SPECIFIC`, así que
    # el overview genérico se adelantaba y ganaba SIEMPRE para la variante en
    # inglés — la versión en español ("¿tiene costo adicional?") solo
    # funcionaba porque "costo" no matchea `\bcost\b` por casualidad de
    # frontera de palabra. La pregunta específica del refresher debe ganar
    # siempre que aplique, sin depender de ese accidente de regex.
    refresher_cost = _canonical_refresher_cost_answer(query, lang)
    if refresher_cost:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=refresher_cost query={query!r} lang={lang}")
        return refresher_cost

    price_overview = _canonical_price_overview_answer(query, lang)
    if price_overview:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=price_overview query={query!r} lang={lang}")
        return price_overview

    price_named_services = _canonical_price_named_services_answer(query, lang)
    if price_named_services:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=price_named_services query={query!r} lang={lang}")
        return price_named_services

    price_package = _canonical_price_package_answer(query, lang)
    if price_package:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=price_package query={query!r} lang={lang}")
        return price_package

    condensed_query = await condense_query(query, history=history, lang=lang)
    ambiguous_location_clarification = _ambiguous_location_clarification(condensed_query, lang)
    if ambiguous_location_clarification:
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
    bare_docs = None
    bare_safe_query = None
    if retrieval_query != condensed_query:
        bare_safe_query = redact_pii(condensed_query)
        bare_docs = await search_knowledge_base(bare_safe_query, lang=lang)
        if any(_is_confident(d) for d in bare_docs):
            retrieval_query = condensed_query

    # Lightly bias retrieval using known origin from extra_context (Cartagena vs already on the islands)
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
    if bare_docs is not None and safe_query == bare_safe_query:
        docs = bare_docs
    else:
        docs = await search_knowledge_base(safe_query, lang=lang)

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
        user_content += f"\n\nPregunta del cliente: {redact_pii(query)}"

        messages.append({"role": "user", "content": user_content})

        grounding_context = _build_grounding_context(context, extra_context=extra_context, history=history)
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        fallback = FALLBACK_ES if lang == "es" else FALLBACK_EN

        # The answer is sampled at temperature 0.3, so it varies run to run. A
        # one-off answer that embellishes a detail trips the grounding judge and,
        # before, went straight to the "no info" fallback — the source of the
        # intermittent (~1/3) false fallbacks. We now REGENERATE the answer once
        # when any guard rejects: a fresh sample is usually grounded, turning a
        # false fallback into a real answer. Only fall back if both tries fail.
        last_reject = ""
        for attempt in range(2):
            try:
                response = await client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=500,
                )
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
            elif not currency_amounts_grounded(answer, grounding_context):
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
                return answer
            else:
                grounded, reason = await _verify_grounding_with_retry(answer, grounding_context, lang=lang)
                if grounded:
                    logger.info(
                        f"[RAG] Query: {query[:60]}... | Docs: {len(docs) if docs else 0} | "
                        f"Tokens: {response.usage.total_tokens} | Sources: {context_sources or []}"
                    )
                    return answer
                last_reject = reason
            logger.info(f"[RAG][GROUNDING] attempt {attempt + 1} rejected ({last_reject}) query={query[:50]}...")

        logger.warning(
            f"[RAG][GROUNDING] Rejecting after 2 attempts query={query[:60]}... reason={last_reject}"
        )
        return fallback

    # 1) Sin documentos del KB
    if not docs:
        logger.info(f"[RAG] No docs found query={query[:60]}...")
        if extra_context:
            # No hay nada util en el KB, pero si tenemos resumen de estado: dejamos que el LLM
            # razone SOLO con ese contexto en lugar de ir directo al fallback.
            # El juez de grounding es OBLIGATORIO aqui (require_grounding): sin
            # soporte del KB, el modelo responderia de su conocimiento propio.
            return await _answer_with_llm(
                extra_context, context_sources=["extra_context_only"], require_grounding=True
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
        if extra_context:
            # Igual que en el caso sin docs: ignoramos estos resultados de baja confianza
            # y dejamos que el LLM trabaje solo con el contexto de estado, pero con
            # el juez de grounding SIEMPRE activo (ver require_grounding arriba).
            return await _answer_with_llm(
                extra_context, context_sources=["extra_context_only"], require_grounding=True
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
        # "conversations" docs describe a DIFFERENT customer's past situation (see
        # scripts/load_embeddings.py). Label them explicitly so the LLM never
        # mistakes their facts (family, companions, budget) for the current
        # customer's — defense in depth alongside stripping their literal quotes
        # at indexing time (T113 in docs/archive/test-battery-edge-cases.md).
        source_label = (
            f"{source} (situacion de otro cliente distinto, no es el cliente actual)"
            if source == "conversations"
            else source
        )
        context_parts.append(f"[{i}] Fuente: {source_label}\n{redact_pii(doc['content'])}")
    context = "\n\n".join(context_parts)

    return await _answer_with_llm(context, context_sources=sources)
