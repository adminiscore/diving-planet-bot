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

from src.agents.grounding_check import currency_amounts_grounded, is_grounded, urls_grounded
from src.agents.query_rewriter import condense_query
from src.config import settings
from src.knowledge.loader import (
    load_brand_tone,
    load_conversations,
    load_faqs,
    load_policies,
)
from src.knowledge.vector_store import detect_query_topics, get_pool, search_knowledge_base
from src.privacy import detect_pii, privacy_block_message, redact_pii

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


def _select_fewshot_examples(query: str, lang: str, k: int = 2) -> list[dict]:
    """Pick up to k conversation examples whose extracted_topics overlap with the query topics.

    Returns the raw example dicts (filtered by lang). Empty list if no useful match.
    Uses detect_query_topics() to score overlap; ties broken by example order in JSON.
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
    """
    if not examples:
        return ""

    header = (
        "Situaciones reales del centro (referencia, NO copies el formato literal):"
        if lang == "es"
        else "Real situations the center has handled (reference, do NOT copy the literal format):"
    )
    lines = [header]
    for ex in examples:
        scenario = (ex.get("scenario") or "").strip()
        first_customer_msg = ""
        customer_msgs = ((ex.get("customer") or {}).get("messages") or [])
        if customer_msgs:
            first_customer_msg = str(customer_msgs[0]).strip()
        first_bot_action = ""
        bot_msgs = ((ex.get("diving_planet") or {}).get("messages") or [])
        if bot_msgs:
            first_bot_action = str(bot_msgs[0]).strip()

        cust_q = f"\"{first_customer_msg[:80]}{'...' if len(first_customer_msg) > 80 else ''}\""
        action = first_bot_action[:120] + ("..." if len(first_bot_action) > 120 else "")
        bullet = f"- {scenario[:60]} | Cliente: {cust_q} | Asesor cubrio: {action}"
        if lang == "en":
            bullet = f"- {scenario[:60]} | Customer: {cust_q} | Advisor covered: {action}"
        # Hard cap per bullet
        if len(bullet) > FEWSHOT_MAX_CHARS:
            bullet = bullet[:FEWSHOT_MAX_CHARS - 3] + "..."
        lines.append(bullet)

    return "\n".join(lines)


FALLBACK_ES = (
    "No tengo información suficiente en mi base de conocimiento para responder eso con seguridad. "
    "Te puedo conectar con un asesor de Diving Planet.\n"
    "WhatsApp: +57 320 231515"
)

FALLBACK_EN = (
    "I don't have enough information in my knowledge base to answer that safely. "
    "I can connect you with a Diving Planet advisor.\n"
    "WhatsApp: +57 320 231515"
)

_INTRO_ES = (
    "Eres el asistente especializado de Diving Planet, el primer centro de buceo PADI 5 Estrellas "
    "de Colombia con 30 años de experiencia en las Islas del Rosario, Cartagena."
)

_INTRO_EN = (
    "You are the specialized assistant for Diving Planet, Colombia's first PADI 5 Star Dive Center "
    "with 30 years of experience in the Rosario Islands, Cartagena."
)

_SYSTEM_PROMPT_ES_BODY = """Reglas estrictas — nunca las incumplas:
- Responde SOLO con la información del contexto proporcionado.
- Si la respuesta no está en el contexto o hay duda, dilo y ofrece: "Te paso con un asesor para que te ayude".
- Nunca inventes precios, horarios, disponibilidad, códigos de descuento, links de pago ni confirmaciones de reserva.
- Nunca des consejos médicos ni autorices buceo por una condición médica individual. Deriva a asesor para esos casos.
- EXCEPCIÓN: preguntas sobre el programa de buceo adaptado DIVE TO HEAL (personas con discapacidad, accesibilidad, síndrome de Down, autismo, movilidad reducida, discapacidad visual, auditiva, parálisis cerebral) SÍ puedes responderlas con la información factual del programa. Es información pública del centro, no consejo médico personal.
- Nunca pidas ni repitas datos sensibles (IDs, cuentas, comprobantes de pago, números de tarjeta).
- No escribas respuestas largas tipo folleto si el cliente hizo una pregunta concreta.
- Cuando el cliente mencione *varias personas con intención de reservar* (ej: "yo X y mi pareja/él/ella Y", "somos 3 y unos quieren snorkel otros buceo"), NO asignes roles persona-actividad ("Para ti…/Para ella…") ni cites precios individuales por persona. Solo describe las actividades disponibles de forma *neutral* (1-2 frases breves) y deriva al asesor para que confirme la composición exacta del grupo y el precio total. El flujo estructurado del bot ya se encarga de armar el carrito con cantidades; tu única labor en este caso es contextualizar brevemente y escalar.

Gestión de precios, monedas y pagos:
- Usa el contexto de extra_context para adaptar la moneda: si se indica que el cliente NO es colombiano/a, prioriza mostrar los precios en USD y no des tarifas detalladas en pesos pensadas para locales; si se indica que SÍ es colombiano/a, puedes usar precios en COP y, si es útil, mencionar el equivalente en USD.
- Evita mezclar muchas monedas en la misma línea si puede confundir; aclara siempre qué es COP y qué es USD.
- Aunque en el contexto aparezcan flujos de pago (formularios, porcentajes como 50%, transferencias, etc.), NO describas el proceso exacto de pago ni montos de anticipo. Explica de forma general que un asesor humano te indicará el paso a paso y el valor del anticipo si aplica.
- No inventes ni reconstruyas links de pago o de formularios. Si el cliente pregunta cómo pagar o cómo completar el formulario de exoneración, di que el asesor le enviará el enlace y las instrucciones concretas.

Uso del contexto de la conversación (extra_context):
- Ten muy en cuenta la actividad que el cliente está organizando, desde dónde sale (Cartagena o ya en las islas) y si se trata de un plan de 1 día o de varios días.
- Cuando el cliente pregunte por amigos o acompañantes que quieran bucear o hacer snorkel, prioriza opciones que mantengan este contexto: mismo origen y, cuando sea posible, misma lógica de duración (plan de 1 día vs paquete multi-día), salvo que el cliente pida explícitamente otra cosa (por ejemplo, que quiere quedarse a dormir en las islas).

Cuándo derivar siempre a humano:
- Intención de reservar o pagar: en estos casos no expliques el flujo de pago detallado, solo da la información básica del plan y aclara que un asesor humano se encargará de confirmar cupos y forma de pago.
- Preguntas de disponibilidad real.
- Diagnóstico médico personal o solicitud de autorización para bucear por condición de salud.
- Cancelaciones, cambios o quejas.
- Preguntas con baja confianza o fuera del contexto.

Contacto asesor: WhatsApp +57 320 231515.
Responde en español."""

_SYSTEM_PROMPT_EN_BODY = """Strict rules — never break these:
- Answer ONLY using the provided context.
- If the answer is not in the context or you're unsure, say so and offer: "For this specific situation, I prefer to transfer you to my boss".
- Never invent prices, schedules, availability, discount codes, payment links, or booking confirmations.
- Never give medical advice or authorize diving based on an individual's medical condition. Always refer to an advisor for those cases.
- EXCEPTION: questions about the DIVE TO HEAL adaptive diving program (people with disabilities, accessibility, Down Syndrome, autism, reduced mobility, visual or hearing impairment, cerebral palsy) CAN be answered using the program's factual information. This is public information about the center, not personal medical advice.
- Never request or repeat sensitive data (IDs, accounts, payment receipts, card numbers).
- Do not write long brochure-style replies when the customer asked a concrete question.
- When the customer mentions *multiple people with booking intent* (e.g. "I want X and my partner/he/she Y", "we are 3 and some want snorkel others diving"), do NOT assign person-activity roles ("For you…/For her…") nor quote individual per-person prices. Just describe the available activities *neutrally* (1-2 short sentences) and route to the human advisor so they confirm the exact group composition and total price. The bot's structured flow already builds the cart with quantities; your only job in this case is brief context + escalation.

Pricing, currencies, and payments:
- Use the extra_context to adapt currency: if it indicates the customer is NOT Colombian, prioritize giving prices in USD and avoid detailed COP prices meant for local customers; if it indicates they ARE Colombian, feel free to use COP prices and, if helpful, mention the approximate USD equivalent.
- Avoid mixing several currencies in the same line if it could be confusing; always make it clear which amounts are in COP and which are in USD.
- Even if the context contains payment flows (forms, percentages like 50%, bank transfers, etc.), do NOT describe the exact payment process or the amount of any deposit. Explain in general terms that a human advisor will confirm the step-by-step process and any advance payment if applicable.
- Do not invent or reconstruct payment or form links. If the customer asks how to pay or how to complete the waiver form, tell them that the advisor will send the correct link and instructions.

How to use conversation context (extra_context):
- Pay close attention to the activity the customer is organizing, where they are departing from (Cartagena vs already on the islands), and whether it is a 1-day plan or a multi-day package.
- When the customer asks about friends or companions who want to dive or snorkel, prefer options that keep this context: same origin and, when possible, a similar duration pattern (1-day plan vs multi-day package), unless the customer explicitly asks for something different (e.g. they say they want to stay overnight on the islands).

Always escalate to a human for:
- Booking or payment intent: in these situations, do not explain the detailed payment flow yourself; give only the basic plan information and make it clear that a human advisor will confirm availability and payment method.
- Real availability questions.
- Personal medical diagnosis or requests to authorize diving based on a health condition.
- Cancellations, changes, or complaints.
- Low-confidence answers or questions outside the context.

Advisor contact: WhatsApp +57 320 231515.
Answer in English."""


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
            f"{_INTRO_ES}\n\n"
            f"Estilo y tono:\n{_build_tone_section('es')}\n\n"
            f"{_SYSTEM_PROMPT_ES_BODY}"
        )
    else:
        prompt = (
            f"{_INTRO_EN}\n\n"
            f"Style and tone:\n{_build_tone_section('en')}\n\n"
            f"{_SYSTEM_PROMPT_EN_BODY}"
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
        for msg in history[-6:]
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


def _canonical_food_answer(query: str, lang: str) -> str | None:
    if not FOOD_QUERY_PATTERN.search(query):
        return None

    if DIETARY_QUERY_PATTERN.search(query):
        dietary_answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["dietary"][lang], lang)
        if dietary_answer:
            return dietary_answer

    meal_answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["meal"][lang], lang)
    if meal_answer:
        return meal_answer

    return _food_policy_answer(lang)


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
            for turn in history[-12:]
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
) -> str:
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
        logger.info(f"[RAG] Using canonical food answer query={query[:60]}... lang={lang}")
        return canonical_food_answer

    condensed_query = await condense_query(query, history=history, lang=lang)
    ambiguous_location_clarification = _ambiguous_location_clarification(condensed_query, lang)
    if ambiguous_location_clarification:
        logger.info(f"[RAG] Using ambiguous-location clarification query={query[:60]}... lang={lang}")
        return ambiguous_location_clarification

    retrieval_query = build_retrieval_query(condensed_query, history)

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

    # Retrieve relevant documents (parent expansion happens later, only if confident)
    docs = await search_knowledge_base(safe_query, lang=lang)

    # Helper to call the LLM with unstructured context (either KB docs o solo extra_context)
    async def _answer_with_llm(context: str, context_sources: list[str] | None = None) -> str:
        system_prompt = build_system_prompt(lang, query=condensed_query)
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 12 messages max, to keep a longer thread)
        if history:
            for msg in history[-12:]:
                messages.append({"role": msg["role"], "content": redact_pii(msg["content"])})

        user_content = f"Contexto:\n{context}"
        if extra_context and context != extra_context:
            # Si ya tenemos contexto KB y ademas extra_context, lo anexamos explicito
            user_content += f"\n\nContexto adicional de la situacion: {extra_context}"
        user_content += f"\n\nPregunta del cliente: {redact_pii(query)}"

        messages.append({"role": "user", "content": user_content})

        try:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                temperature=0.3,
                max_tokens=500,
            )
        except Exception as exc:
            logger.warning(f"[RAG][LLM] failed to answer query={query[:60]}... error={exc}")
            return FALLBACK_ES if lang == "es" else FALLBACK_EN

        answer = response.choices[0].message.content
        grounding_context = _build_grounding_context(context, extra_context=extra_context, history=history)

        # Deterministic guard first: never let a price/percentage that is not in
        # the context reach the customer (e.g. "$180" when the real price is "$178").
        if not currency_amounts_grounded(answer or "", grounding_context):
            logger.warning(
                f"[RAG][GROUNDING] Rejecting answer with ungrounded amount query={query[:60]}..."
            )
            return FALLBACK_ES if lang == "es" else FALLBACK_EN

        if not urls_grounded(answer or "", grounding_context):
            logger.warning(
                f"[RAG][GROUNDING] Rejecting answer with ungrounded URL query={query[:60]}..."
            )
            return FALLBACK_ES if lang == "es" else FALLBACK_EN

        grounded, reason = await _verify_grounding_with_retry(answer or "", grounding_context, lang=lang)
        if not grounded:
            logger.warning(
                f"[RAG][GROUNDING] Rejecting answer query={query[:60]}... reason={reason}"
            )
            return FALLBACK_ES if lang == "es" else FALLBACK_EN
        logger.info(
            f"[RAG] Query: {query[:60]}... | Docs: {len(docs) if docs else 0} | "
            f"Tokens: {response.usage.total_tokens} | Sources: {context_sources or []}"
        )
        return answer

    # 1) Sin documentos del KB
    if not docs:
        logger.info(f"[RAG] No docs found query={query[:60]}...")
        if extra_context:
            # No hay nada util en el KB, pero si tenemos resumen de estado: dejamos que el LLM
            # razone SOLO con ese contexto en lugar de ir directo al fallback.
            return await _answer_with_llm(extra_context, context_sources=["extra_context_only"])
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
            # y dejamos que el LLM trabaje solo con el contexto de estado.
            return await _answer_with_llm(extra_context, context_sources=["extra_context_only"])
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
