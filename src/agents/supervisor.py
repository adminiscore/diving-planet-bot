"""
LangGraph Supervisor Agent.

Routes incoming messages to the appropriate handler:
- Decision tree: for structured menu flows (user is navigating options)
- RAG agent: for free-text questions outside the menu flow
- Escalation: when user explicitly asks for a human

The routing logic is deterministic (no LLM call for routing),
keeping costs minimal.
"""

import logging
import re
import unicodedata

from src.agents.escalation import detect_sensitive_escalation
from src.agents.lead_summary import build_lead_summary
from src.agents.intent_classifier import classify_menu_intent
from src.flows.decision_tree import DecisionTree, ConversationState, Step
from src.agents.rag_agent import rag_answer
from src.privacy import detect_pii, privacy_block_message

logger = logging.getLogger("uvicorn.error")

decision_tree = DecisionTree()

_GROUP_COUNT_WORDS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
}

# Steps where the user is actively navigating the decision tree menu
MENU_STEPS = {
    Step.WELCOME,
    Step.LANGUAGE,
    Step.MAIN_MENU,
    Step.RESERVA_MENU,
    Step.INFO_MENU,
    Step.INFO_ACTIVITY_LOCATION,
    Step.INFO_ACTIVITIES_MENU,
    Step.INFO_TOURS_MENU,
    Step.INFO_PACKAGES_MENU,
    Step.INFO_COURSES_MENU,
    Step.INFO_SPECIALTIES_MENU,
    Step.INFO_TOUR_DETAIL,
    Step.INFO_PACKAGE_DETAIL,
    Step.INFO_COURSE_DETAIL,
    Step.INFO_SPECIALTY_DETAIL,
    Step.INFO_TOURS_CERTIFIED_MENU,
    Step.INFO_COURSES_ADVANCED_MENU,
    Step.INFO_MIXED_ACTIVITY_MENU,
    Step.INFO_MIXED_CERT_BEG_MENU,
    Step.INFO_CERTIFIED_4_DIVES_VARIANT,
    Step.TOURS_LOCATION,
    Step.GROUP_TYPE,
    Step.TOURS_EXPERIENCE,
    Step.TOURS_CERTIFIED,
    Step.CERTIFIED_LAST_DIVE,
    Step.CERTIFIED_EXPERIENCE,
    Step.REFRESHER_INTEREST,
    Step.TOURS_BEGINNER,
    Step.BEGINNER_AGE,
    Step.COURSES_MENU,
    Step.COURSES_OPEN_WATER_ORIGIN,
    Step.COURSES_OPEN_WATER_TIME,
    Step.COURSES_ADVANCED_MENU,
    Step.COURSES_SPECIALTIES_MENU,
    Step.PRICING_COLOMBIAN,
    Step.MIXED_ENTRY,
    Step.MIXED_LOCATION,
    Step.MIXED_ADD_ACTIVITY,
    Step.MIXED_ADD_CERT_PLAN,
    Step.MIXED_ADD_QTY,
    Step.MIXED_CERT_LAST_DIVE,
    Step.MIXED_CERT_REFRESH_INTEREST,
    Step.MIXED_CERT_REFRESH_QTY,
    Step.MIXED_CERT_SPLIT_REVIEW,
    Step.MIXED_ADD_PREVIEW,
    Step.MIXED_CART_REVIEW,
    Step.MIXED_CART_MODIFY_PICK,
    Step.MIXED_CART_REMOVE_PICK,
    Step.MIXED_FINAL_COLOMBIAN,
    Step.MIXED_FINAL_KIDS,
    Step.MIXED_FINAL_PRIVATE,
    Step.MIXED_FINAL_SUMMARY,
    Step.PRICING_MENU,
    Step.PRICING_CARTAGENA,
    Step.PRICING_ISLANDS,
    Step.PRICING_PACKAGES,
    Step.PRICING_DISCOUNTS,
    Step.BOOKING_MENU,
    Step.LOGISTICS_MENU,
    Step.LOGISTICS_MEETING,
    Step.LOGISTICS_INCLUDES,
    Step.LOGISTICS_WHAT_TO_BRING,
    Step.ISLAND_MENU,
    Step.ISLAND_HOTEL_MENU,
    Step.SERVICE_DETAIL,
    Step.LOCATION,
    Step.COLOMBIAN,
}

# Steps that route through the LLM intent classifier when free text doesn't match a button.
_MIXED_FLOW_STEPS = {
    Step.MIXED_ENTRY,
    Step.MIXED_LOCATION,
    Step.MIXED_ADD_ACTIVITY,
    Step.MIXED_ADD_CERT_PLAN,
    Step.MIXED_ADD_QTY,
    Step.MIXED_CERT_LAST_DIVE,
    Step.MIXED_CERT_REFRESH_INTEREST,
    Step.MIXED_CERT_REFRESH_QTY,
    Step.MIXED_CERT_SPLIT_REVIEW,
    Step.MIXED_ADD_PREVIEW,
    Step.MIXED_CART_REVIEW,
    Step.MIXED_CART_MODIFY_PICK,
    Step.MIXED_CART_REMOVE_PICK,
    Step.MIXED_FINAL_COLOMBIAN,
    Step.MIXED_FINAL_KIDS,
    Step.MIXED_FINAL_PRIVATE,
    Step.MIXED_FINAL_SUMMARY,
}

# Keywords that send the user all the way back to the main menu.
MENU_KEYWORDS = {
    "menu", "menú", "inicio", "start", "opciones", "options",
}

# Keywords that take the user one step UP in the decision tree (see BACK_STEP).
BACK_KEYWORDS = {
    "volver", "back", "atras", "atrás", "regresar",
}

# For each step inside the Reservar branch, the (previous_step, quick_reply_key)
# to use when the user clicks "🔙 Volver" or types a back keyword. Steps that
# are not listed fall back to MAIN_MENU.
BACK_STEP: dict[Step, tuple[Step, str]] = {
    Step.RESERVA_MENU: (Step.MAIN_MENU, "main_menu"),
    Step.INFO_MENU: (Step.MAIN_MENU, "main_menu"),
    Step.PRICING_COLOMBIAN: (Step.INFO_MENU, "info_menu"),
    Step.PRICING_MENU: (Step.INFO_MENU, "info_menu"),
    Step.PRICING_CARTAGENA: (Step.PRICING_MENU, "pricing_menu"),
    Step.PRICING_ISLANDS: (Step.PRICING_MENU, "pricing_menu"),
    Step.PRICING_PACKAGES: (Step.PRICING_MENU, "pricing_menu"),
    Step.PRICING_DISCOUNTS: (Step.PRICING_MENU, "pricing_menu"),
    Step.BOOKING_MENU: (Step.INFO_MENU, "info_menu"),
    Step.LOGISTICS_MENU: (Step.INFO_MENU, "info_menu"),
    Step.LOGISTICS_MEETING: (Step.LOGISTICS_MENU, "logistics_menu"),
    Step.LOGISTICS_INCLUDES: (Step.LOGISTICS_MENU, "logistics_menu"),
    Step.LOGISTICS_WHAT_TO_BRING: (Step.LOGISTICS_MENU, "logistics_menu"),
    Step.ISLAND_MENU: (Step.LOGISTICS_MENU, "logistics_menu"),
    Step.ISLAND_HOTEL_MENU: (Step.ISLAND_MENU, "island_menu"),
    Step.INFO_ACTIVITY_LOCATION: (Step.INFO_MENU, "info_menu"),
    Step.INFO_ACTIVITIES_MENU: (Step.INFO_ACTIVITY_LOCATION, "info_activity_location"),
    Step.INFO_TOURS_MENU: (Step.INFO_ACTIVITIES_MENU, "info_activities_menu"),
    Step.INFO_PACKAGES_MENU: (Step.INFO_TOURS_MENU, "info_tours_menu"),
    Step.INFO_COURSES_MENU: (Step.INFO_ACTIVITIES_MENU, "info_activities_menu"),
    Step.INFO_SPECIALTIES_MENU: (Step.INFO_COURSES_MENU, "info_courses_menu"),
    Step.INFO_TOUR_DETAIL: (Step.INFO_TOURS_MENU, "info_tours_menu"),
    Step.INFO_PACKAGE_DETAIL: (Step.INFO_PACKAGES_MENU, "info_packages_menu"),
    Step.INFO_COURSE_DETAIL: (Step.INFO_COURSES_MENU, "info_courses_menu"),
    Step.INFO_SPECIALTY_DETAIL: (Step.INFO_SPECIALTIES_MENU, "info_specialties_menu"),
    Step.INFO_TOURS_CERTIFIED_MENU: (Step.INFO_PACKAGES_MENU, "info_packages_menu"),
    Step.INFO_COURSES_ADVANCED_MENU: (Step.INFO_COURSES_MENU, "info_courses_menu"),
    Step.INFO_MIXED_ACTIVITY_MENU: (Step.INFO_TOURS_MENU, "info_tours_menu"),
    Step.INFO_MIXED_CERT_BEG_MENU: (Step.INFO_PACKAGES_MENU, "info_packages_menu"),
    Step.INFO_CERTIFIED_4_DIVES_VARIANT: (Step.INFO_TOURS_CERTIFIED_MENU, "info_tours_certified_menu"),
    Step.TOURS_LOCATION: (Step.RESERVA_MENU, "reserva_menu"),
    Step.GROUP_TYPE: (Step.RESERVA_MENU, "reserva_menu"),
    Step.TOURS_EXPERIENCE: (Step.GROUP_TYPE, "group_type"),
    Step.TOURS_CERTIFIED: (Step.TOURS_EXPERIENCE, "tours_experience"),
    Step.CERTIFIED_4_DIVES_VARIANT: (Step.TOURS_CERTIFIED, "tours_certified"),
    Step.TOURS_BEGINNER: (Step.TOURS_EXPERIENCE, "tours_experience"),
    Step.BEGINNER_AGE: (Step.TOURS_EXPERIENCE, "tours_experience"),
    Step.COURSES_MENU: (Step.RESERVA_MENU, "reserva_menu"),
    Step.COURSES_OPEN_WATER_ORIGIN: (Step.COURSES_MENU, "courses_menu"),
    Step.COURSES_OPEN_WATER_TIME: (Step.COURSES_OPEN_WATER_ORIGIN, "courses_open_water_origin"),
    Step.COURSES_ADVANCED_MENU: (Step.COURSES_MENU, "courses_menu"),
    Step.COURSES_SPECIALTIES_MENU: (Step.COURSES_MENU, "courses_menu"),
    # Cart-style mixed flow: most steps loop back to the cart review for "back".
    # MIXED_ENTRY goes back to GROUP_TYPE. Final-question steps are intentionally
    # not back-navigable individually — restart via "empezar de nuevo" if needed.
    Step.MIXED_ENTRY: (Step.GROUP_TYPE, "group_type"),
    Step.MIXED_LOCATION: (Step.MIXED_ENTRY, "mixed_entry"),
    Step.MIXED_ADD_ACTIVITY: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_ADD_CERT_PLAN: (Step.MIXED_ADD_ACTIVITY, "mixed_add_activity"),
    Step.MIXED_ADD_QTY: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_CERT_LAST_DIVE: (Step.MIXED_ADD_QTY, "mixed_quantity"),
    Step.MIXED_CERT_REFRESH_INTEREST: (Step.MIXED_CERT_LAST_DIVE, "certified_last_dive"),
    Step.MIXED_CERT_REFRESH_QTY: (Step.MIXED_CERT_REFRESH_INTEREST, "refresher_interest"),
    Step.MIXED_CERT_SPLIT_REVIEW: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_ADD_PREVIEW: (Step.MIXED_ADD_ACTIVITY, "mixed_add_activity"),
    Step.MIXED_CART_REVIEW: (Step.GROUP_TYPE, "group_type"),
    Step.MIXED_CART_MODIFY_PICK: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_CART_REMOVE_PICK: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_FINAL_COLOMBIAN: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_FINAL_KIDS: (Step.MIXED_FINAL_COLOMBIAN, "mixed_yes_no"),
    Step.MIXED_FINAL_PRIVATE: (Step.MIXED_FINAL_COLOMBIAN, "mixed_yes_no"),
}

# Keywords that indicate escalation to a human
ESCALATION_KEYWORDS = {
    "humano", "human", "agente", "agent", "asesor", "advisor",
    "persona", "person", "hablar con", "speak with", "talk to",
}

# Phrases that indicate a customer complaining about a broken link/URL/form.
BROKEN_LINK_COMPLAINT_PHRASES = {
    # ES
    "no funciona", "no me funciona", "no abre", "no me abre", "no carga",
    "no me carga", "está roto", "esta roto", "está caído", "esta caido",
    "no me lleva", "da error", "me da error", "no entra", "no se abre",
    "no se carga", "está mal", "esta mal", "el link mal", "url mal",
    "no sirve",
    # EN
    "doesn't work", "does not work", "doesnt work", "not working",
    "is broken", "broken link", "won't load", "wont load", "won't open",
    "wont open", "doesn't load", "doesn't open", "is down", "shows an error",
    "gives an error", "not loading",
}

BROKEN_LINK_TARGET_TOKENS = {
    "link", "links", "enlace", "enlaces", "url", "urls",
    "form", "formulario", "formularios", "form jotform", "jotform",
    "página", "pagina", "page", "site", "sitio",
}

LANGUAGE_SELECTION_KEYWORDS = {
    "1", "2", "es", "en", "español", "espanol", "spanish", "english",
}

GREETING_ONLY_KEYWORDS = {
    "hola", "hello", "hi", "buenas", "buenos dias", "buenos días",
    "buenas tardes", "buenas noches", "hey",
}

ENGLISH_HINTS = {
    "we", "are", "family", "certified", "divers", "snorkel", "snorkeling",
    "can", "together", "price", "book", "booking", "discount", "payment",
    "meeting", "point", "open water",
}

SPANISH_HINTS = {
    "somos", "familia", "buzos", "certificados", "bucear", "snorkel",
    "precio", "reservar", "reserva", "descuento", "pago", "juntos",
    "punto de encuentro",
}

# Words that should NOT count as button-title evidence on their own.
MENU_MATCH_STOP_WORDS = {
    "de", "la", "el", "y", "o", "para", "con", "en", "un", "una",
    "los", "las", "del", "al", "que", "es", "se", "lo", "mi", "mis",
    "and", "or", "the", "to", "in", "for", "with", "an", "is",
    "i", "me", "my", "you", "your", "we", "our", "do", "have",
    "quiero", "elijo", "selecciono", "want", "would", "like",
}

# If any of these appear, treat the message as a question (route to RAG, not the menu).
MENU_MATCH_QUESTION_WORDS = {
    "cuánto", "cuanto", "cómo", "como", "qué", "que",
    "dónde", "donde", "cuándo", "cuando", "cuál", "cual",
    "how", "what", "when", "where", "why", "which",
}


def _strip_accents(text: str) -> str:
    """Remove diacritics (á→a, ñ→n, ü→u, …) so text comparison is accent-insensitive."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_for_menu_match(text: str) -> str:
    """Lowercase, drop diacritics, strip punctuation/emoji, collapse whitespace.

    Accent stripping is critical: users frequently type "informacion" instead of
    "información", "espanol" instead of "español", etc., and the matcher must
    treat these as equivalent to the button titles.
    """
    cleaned = _strip_accents(text.strip().lower())
    cleaned = re.sub(r"[¿¡?!.,;:()\[\]\"'/\\]", " ", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def _detect_language_intent(message: str) -> str | None:
    """Detect an explicit language switch request.

    Matches words like "english/ingles", "spanish/espanol/castellano". Accent-insensitive.
    Returns "es", "en", or None when the message contains no language keyword.
    """
    normalized = _strip_accents(message.strip().lower())
    # Word-boundary match so "english" inside another word would not trigger;
    # at the same time tolerate adjacent punctuation.
    if re.search(r"\b(english|ingles)\b", normalized):
        return "en"
    if re.search(r"\b(spanish|espanol|castellano)\b", normalized):
        return "es"
    return None


def _detect_companion_intent(message: str, state: ConversationState | None = None) -> bool:
    """Detect if the user is talking about friends/companions joining the activity.

    Used to offer upgrading a single-activity flow (e.g. solo snorkel) into the
    cart-style mixed-group flow. Accent-insensitive and language-agnostic.
    """
    # Reuse the same normalization pipeline used for menu/intent matching so
    # that tokens like "buceo," or "diving?" are recognised correctly.
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return False
    tokens = set(normalized.split())

    companion_keywords = {
        "amigo",
        "amigos",
        "amiga",
        "amigas",
        "pareja",
        "novio",
        "novia",
        "novios",
        "novias",
        "esposo",
        "esposa",
        "esposos",
        "esposas",
        "marido",
        "companero",
        "companera",
        "companeros",
        "companeras",
        "compa",
        "parce",
        "parcero",
        "parcera",
        "pana",
        "acompanante",
        "acompanantes",
        "friend",
        "friends",
        "partner",
        "partners",
        "companion",
        "companions",
        "family",
        "kids",
        "kid",
        "children",
        "son",
        "daughter",
        "sons",
        "daughters",
    }

    companion_patterns = (
        r"\bmi\s+(pareja|novi[oa]|espos[oa]|marido|mujer|madre|padre|mama|papa|chic[oa])\b",
        r"\bmi\s+(herman[oa]|hij[oa])\b",
        r"\bmis\s+(hij[oa]s|herman[oa]s)\b",
        r"\bmi\s+familia\b",
        r"\b(vengo|voy|vamos|venimos)\s+con\s+mi\b",
        r"\b(vengo|voy|vamos|venimos)\s+con\s+(mis\s+hij[oa]s|mi\s+familia)\b",
        r"\b(otro|otra|otros|otras)\s+(persona|adult[oa]s?|participante?s?)\b",
        r"\b(alguien|alguno|alguna)\s+mas\b",
        r"\b(uno|una)\s+mas\b",
        r"\b(vamos|venimos)\s+en\s+pareja\b",
        r"\breservar\s+para\s+(dos|2)\s+(personas|adultos|adultas|participantes)\b",
    )
    group_patterns = (
        r"\b(venimos|somos|vamos)\s+(dos|2)\b",
        r"\b(venimos|somos|vamos)\s+(tres|3)\b",
        r"\bpara\s+(dos|2)\s+(personas|adultos|adultas|participantes)\b",
    )
    pronoun_patterns = (
        r"\bel\s+quiere\b",
        r"\bella\s+quiere\b",
        r"\bel\s+haria\b",
        r"\bella\s+haria\b",
        r"\bel\s+hace\b",
        r"\bella\s+hace\b",
        r"\bel\s+prefiere\b",
        r"\bella\s+prefiere\b",
        r"\bel\s+bucea\b",
        r"\bella\s+bucea\b",
        r"\bel\s+caretea\b",
        r"\bella\s+caretea\b",
        r"\bel\s+tambien\b",
        r"\bella\s+tambien\b",
        r"\bla\s+otra\s+persona\b",
        # Elipsis: "él el minicurso" / "ella la actividad" (pronombre + artículo +
        # actividad, sin verbo explícito). Conservador: solo cuando va seguido del
        # nombre concreto de la actividad para minimizar falsos positivos.
        r"\b(el|ella)\s+(el|la|los|las)\s+(snorkel|minicurso|buceo|curso)\b",
        # "ella solo snorkel" / "él solamente buceo" (adverbio entre pronombre y
        # actividad).
        r"\b(el|ella)\s+(solo|solamente)\s+(snorkel|minicurso|buceo|esnorquel)\b",
    )
    distribution_patterns = (
        r"\buno\s+quiere\b",
        r"\buna\s+quiere\b",
        r"\buno\s+prefiere\b",
        r"\buna\s+prefiere\b",
        r"\bel\s+otro\b",
        r"\bla\s+otra\b",
        r"\b(dos|2|tres|3)\s+quieren\b",
        r"\b(dos|2|tres|3)\s+prefieren\b",
    )
    activity_patterns = (
        r"\b(snorkel|snorkeling|esnorquel|caretear|caretea|caretean)\b",
        r"\b(minicurso|curso\s+de\s+iniciacion|bautizo\s+de\s+buceo)\b",
        r"\b(buceo|bucear|buceos|buceando|bucea|bucean|dive|dives|diving|scuba)\b",
    )

    if any(word in tokens for word in companion_keywords):
        return True
    if any(re.search(pattern, normalized) for pattern in companion_patterns):
        return True
    if any(re.search(pattern, normalized) for pattern in group_patterns):
        return True

    has_activity_reference = any(re.search(pattern, normalized) for pattern in activity_patterns)
    has_companion_context = bool(getattr(state, "mixed_from_single_companion_context_active", False)) if state else False
    if any(re.search(pattern, normalized) for pattern in distribution_patterns):
        return has_activity_reference or has_companion_context
    if any(re.search(pattern, normalized) for pattern in pronoun_patterns):
        return has_activity_reference or has_companion_context

    return False


def _mentions_diving_intent(message: str) -> bool:
    """Detect diving-related terms in the message (buceo, diving, scuba, etc.).

    Used to specialise friend/companion answers when the main user picked snorkel
    and the friend wants to dive.
    """
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return False
    sanitized = re.sub(
        r"\b(minicurso(\s+de\s+buceo)?|curso\s+de\s+iniciacion|curso\s+de\s+iniciacion\s+al\s+buceo|bautizo\s+de\s+buceo)\b",
        " ",
        normalized,
    )
    tokens = set(sanitized.split())

    diving_keywords = {
        "buceo",
        "bucear",
        "buceos",
        "buceando",
        "bucea",
        "bucean",
        "dive",
        "dives",
        "diving",
        "scuba",
    }

    return any(word in tokens for word in diving_keywords)


def _mentions_snorkeling_intent(message: str) -> bool:
    """Detect snorkeling-related terms in the message (snorkel, snorkeling, etc.)."""
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return False
    tokens = set(normalized.split())

    snorkeling_keywords = {
        "snorkel",
        "snorkeling",
        "esnorquel",
        "caretear",
        "caretea",
        "caretean",
    }

    return any(word in tokens for word in snorkeling_keywords)


def _mentions_minicourse_intent(message: str) -> bool:
    """Detect explicit mini-course wording for a companion diving plan."""
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return False

    minicourse_patterns = (
        r"\bminicurso\b",
        r"\bcurso\s+de\s+iniciacion\b",
        r"\bcurso\s+de\s+iniciación\b",
        r"\bbautizo\s+de\s+buceo\b",
    )
    return any(re.search(pattern, normalized) for pattern in minicourse_patterns)


def _base_service_to_activity_intent(base_id: str | None) -> str | None:
    if base_id == "snorkeling":
        return "snorkeling"
    if base_id == "minicourse":
        return "minicourse"
    if base_id == "2_dives_1_day":
        return "diving"
    return None


def _extract_activity_mentions(message: str) -> set[str]:
    activity_mentions: set[str] = set()
    if _mentions_minicourse_intent(message):
        activity_mentions.add("minicourse")
    if _mentions_snorkeling_intent(message):
        activity_mentions.add("snorkeling")
    if _mentions_diving_intent(message):
        activity_mentions.add("diving")
    return activity_mentions


def _detect_companion_activity_intent(message: str, base_id: str | None = None) -> str | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None
    activity_mentions = _extract_activity_mentions(message)

    if len(activity_mentions) == 1:
        return next(iter(activity_mentions))

    base_activity = _base_service_to_activity_intent(base_id)
    if len(activity_mentions) > 1 and base_activity in activity_mentions:
        non_base_mentions = activity_mentions - {base_activity}
        if len(non_base_mentions) == 1:
            return next(iter(non_base_mentions))

    same_activity_patterns = (
        r"\bhacer\s+lo\s+mismo\b",
        r"\blo\s+mismo\b",
        r"\bla\s+misma\s+actividad\b",
        r"\bel\s+mismo\s+plan\b",
        r"\bigual\s+que\s+yo\b",
        r"\bigual\s+a\s+mi\b",
        r"\btambien\s+quiere\s+venir\b",
        r"\btambien\s+viene\b",
        r"\bse\s+apunta\b",
        r"\bse\s+suma\b",
    )
    if any(re.search(pattern, normalized) for pattern in same_activity_patterns):
        return "same"

    if len(activity_mentions) > 1:
        return None
    return None


def _parse_group_count_token(token: str | None) -> int | None:
    if not token:
        return None
    normalized = _normalize_for_menu_match(token)
    if not normalized:
        return None
    if normalized.isdigit():
        value = int(normalized)
        return value if 1 <= value <= 99 else None
    return _GROUP_COUNT_WORDS.get(normalized)


def _extract_total_people_count(message: str) -> int | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None

    patterns = (
        r"\b(?:somos|venimos|vamos)\s+(?P<count>\d+|un|uno|una|dos|tres|cuatro|cinco|seis)\b",
        r"\bpara\s+(?P<count>\d+|un|uno|una|dos|tres|cuatro|cinco|seis)\s+(?:personas|adultos|adultas|participantes)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return _parse_group_count_token(match.group("count"))
    return None


def _extract_segment_person_count(segment: str) -> int | None:
    if not segment:
        return None

    numeric_match = re.search(
        r"\b(?P<count>\d+|un|uno|una|dos|tres|cuatro|cinco|seis)\s+(?:amig[oa]s?|personas?|adult[oa]s?|participantes?|acompanantes?)?\b",
        segment,
    )
    if numeric_match:
        value = _parse_group_count_token(numeric_match.group("count"))
        if value is not None:
            return value

    single_person_patterns = (
        r"\b(el|la)\s+otro\b",
        r"\botr[oa]\b",
        r"\bla\s+otra\s+persona\b",
        r"\bella\b",
        r"\bel\s+(?:quiere|prefiere|hace|haria|bucea|caretea)\b",
        r"\bmi\s+(pareja|amig[oa]|espos[oa]|novi[oa]|parcer[oa]|companero|companera|acompanante|herman[oa]|hij[oa])\b",
    )
    if any(re.search(pattern, segment) for pattern in single_person_patterns):
        return 1
    return None


def _merge_group_allocations(allocations: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for allocation in allocations:
        activity = allocation.get("activity")
        qty = allocation.get("qty")
        if not activity or not isinstance(qty, int) or qty <= 0:
            continue
        existing = next((item for item in merged if item["activity"] == activity), None)
        if existing is not None:
            existing["qty"] += qty
        else:
            merged.append({"activity": activity, "qty": qty})
    return merged


def _extract_group_activity_allocations(message: str) -> tuple[str | None, list[dict]]:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None, []

    speaker_activity: str | None = None
    allocations: list[dict] = []
    segments = [
        segment.strip()
        for segment in re.split(r"\s*(?:,|;|\by\b|\bpero\b|\bmientras\b)\s*", normalized)
        if segment.strip()
    ]

    for segment in segments:
        activity_mentions = _extract_activity_mentions(segment)
        if len(activity_mentions) != 1:
            continue
        activity = next(iter(activity_mentions))
        if re.search(r"\byo\b", segment):
            speaker_activity = activity
            continue
        count = _extract_segment_person_count(segment)
        if count is None:
            continue
        allocations.append({"activity": activity, "qty": count})

    return speaker_activity, _merge_group_allocations(allocations)


def _build_companion_group_context(message: str, base_id: str | None = None) -> dict | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None

    total_people = _extract_total_people_count(message)
    speaker_activity, allocations = _extract_group_activity_allocations(message)
    base_activity = _base_service_to_activity_intent(base_id)
    companion_count = sum(item["qty"] for item in allocations)

    if not allocations and total_people and total_people > 1:
        companion_count = max(total_people - 1, 1)

    if not allocations and companion_count == 0:
        return None

    if speaker_activity and base_activity and speaker_activity != base_activity:
        return {
            "total_people": total_people,
            "speaker_activity": speaker_activity,
            "companion_count": companion_count or None,
            "allocations": allocations,
            "needs_activity_clarification": True,
        }

    if total_people and allocations and speaker_activity is None and companion_count > max(total_people - 1, 0):
        return {
            "total_people": total_people,
            "speaker_activity": speaker_activity,
            "companion_count": companion_count,
            "allocations": allocations,
            "needs_activity_clarification": True,
        }

    if allocations and base_activity and speaker_activity is None and not total_people:
        allocation_activities = {item["activity"] for item in allocations if item.get("activity")}
        if len(allocation_activities) > 1 and base_activity not in allocation_activities:
            return {
                "total_people": total_people,
                "speaker_activity": speaker_activity,
                "companion_count": companion_count or None,
                "allocations": allocations,
                "needs_activity_clarification": True,
            }

    return {
        "total_people": total_people,
        "speaker_activity": speaker_activity,
        "companion_count": companion_count or None,
        "allocations": allocations,
        "needs_activity_clarification": not allocations,
    }


def _extract_menu_mixed_group_context(message: str) -> dict | None:
    group_context = _build_companion_group_context(message)
    if not group_context:
        return None
    if group_context.get("needs_activity_clarification"):
        return None

    speaker_activity = group_context.get("speaker_activity")
    allocations = group_context.get("allocations", [])
    if not speaker_activity or not allocations:
        return None

    activities = {speaker_activity}
    activities.update(
        allocation.get("activity")
        for allocation in allocations
        if allocation.get("activity")
    )
    if len(activities) != 2:
        return None
    if "snorkeling" not in activities:
        return None
    if not activities.issubset({"snorkeling", "minicourse", "diving"}):
        return None
    return group_context


def _build_group_context_from_activity(activity: str, companion_count: int = 1, total_people: int | None = None) -> dict:
    qty = companion_count if companion_count > 0 else 1
    return {
        "total_people": total_people,
        "speaker_activity": None,
        "companion_count": qty,
        "allocations": [{"activity": activity, "qty": qty}],
        "needs_activity_clarification": False,
    }


def _detect_companion_group_question_answer(
    message: str,
    base_id: str | None,
    default_companion_count: int | None,
    default_total_people: int | None,
) -> dict | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None

    if normalized == "1":
        return _build_group_context_from_activity("snorkeling", default_companion_count or 1, default_total_people)
    if normalized == "2":
        return _build_group_context_from_activity("minicourse", default_companion_count or 1, default_total_people)
    if normalized == "3":
        return _build_group_context_from_activity("diving", default_companion_count or 1, default_total_people)

    parsed = _build_companion_group_context(message, base_id)
    if parsed and parsed.get("allocations"):
        if default_total_people and not parsed.get("total_people"):
            parsed["total_people"] = default_total_people
        if not parsed.get("companion_count"):
            parsed["companion_count"] = default_companion_count or sum(
                item["qty"] for item in parsed.get("allocations", [])
            )
        parsed["needs_activity_clarification"] = False
        return parsed

    activity_answer = _detect_companion_activity_answer(message, base_id)
    if activity_answer is None:
        return None
    return _build_group_context_from_activity(
        activity_answer,
        default_companion_count or 1,
        default_total_people,
    )


def _normalize_base_service_id(service_id: str | None) -> str | None:
    if not service_id:
        return None
    suffix = "_already_on_island"
    if service_id.endswith(suffix):
        return service_id[: -len(suffix)]
    return service_id


def _build_mixed_from_single_follow_up(base_id: str | None, lang: str) -> tuple[str, list[dict]]:
    companion_count = base_id.get("companion_count") if isinstance(base_id, dict) else None
    actual_base_id = base_id.get("base_id") if isinstance(base_id, dict) else base_id
    if lang == "es":
        if actual_base_id == "snorkeling":
            my_activity = "tu reserva de snorkel"
        elif actual_base_id == "2_dives_1_day":
            my_activity = "tu reserva de buceo"
        elif actual_base_id == "minicourse":
            my_activity = "tu minicurso de buceo"
        else:
            my_activity = "la actividad que ya tenías seleccionada"

        if companion_count == 1 or companion_count is None:
            follow_up = (
                f"Si quieres, puedo añadir al carrito {my_activity}, "
                "dejando esta actividad para ti y tú puedes añadir la de tu amigo o acompañante.\n\n"
                "¿Te gustaría que preparemos la reserva también para esa persona?\n"
                "1️⃣ Sí, añadirlo al carrito\n"
                "2️⃣ No, dejar solo mi actividad"
            )
        else:
            group_phrase = f"tus {companion_count} acompañantes"
            follow_up = (
                f"Si quieres, puedo añadir al carrito {my_activity}, "
                f"dejando esta actividad para ti y preparando también la de {group_phrase}.\n\n"
                f"¿Te gustaría que preparemos la reserva también para {group_phrase}?\n"
                "1️⃣ Sí, añadirlo al carrito\n"
                "2️⃣ No, dejar solo mi actividad"
            )
        quick_replies = [
            {"title": "1️⃣ Sí, añadirlo al carrito", "value": "1"},
            {"title": "2️⃣ No, dejar solo mi actividad", "value": "2"},
        ]
        return follow_up, quick_replies

    follow_up = (
        "If you want, I can add your current activity to a *mixed group* booking (cart), "
        "keeping it for you so you can then add your friend or companion.\n\n"
        "Would you like me to prepare the booking for them as well?\n"
        "1️⃣ Yes, add them to the cart\n"
        "2️⃣ No, keep only my activity"
    )
    quick_replies = [
        {"title": "1️⃣ Yes, add to cart", "value": "1"},
        {"title": "2️⃣ No, only my activity", "value": "2"},
    ]
    return follow_up, quick_replies


def _build_mixed_from_single_cert_question(diving_qty: int = 1) -> tuple[str, list[dict]]:
    if diving_qty > 1:
        prompt = (
            "¡Claro! Pueden ir juntos sin problema.\n\n"
            "Para recomendarle bien el plan al grupo que quiere buceo, necesito saber una cosa:\n\n"
            f"¿Estas {diving_qty} personas son *buzos certificados*?\n"
            "1️⃣ Sí, todos están certificados\n"
            "2️⃣ No, alguno sería su primera vez"
        )
        quick_replies = [
            {"title": "1️⃣ Sí, todos están certificados", "value": "1"},
            {"title": "2️⃣ No, alguno sería su primera vez", "value": "2"},
        ]
        return prompt, quick_replies

    prompt = (
        "¡Claro! Pueden ir juntos sin problema.\n\n"
        "Para recomendarle bien el plan a tu amigo, necesito saber una cosa:\n\n"
        "¿Tu amigo es *buzo certificado*?\n"
        "1️⃣ Sí, está certificado\n"
        "2️⃣ No, sería su primera vez"
    )
    quick_replies = [
        {"title": "1️⃣ Sí, está certificado", "value": "1"},
        {"title": "2️⃣ No, sería su primera vez", "value": "2"},
    ]
    return prompt, quick_replies


def _build_mixed_from_single_activity_question(companion_count: int | None = None) -> tuple[str, list[dict]]:
    if companion_count and companion_count > 1:
        prompt = (
            "¡Claro! Pueden ir juntos sin problema.\n\n"
            "Para recomendar bien el plan de tu grupo, necesito saber qué actividad quiere hacer cada persona. "
            "Si quieres, puedes responder con una sola opción o con algo como 'dos snorkel y uno buceo':\n\n"
            "1️⃣ Snorkel\n"
            "2️⃣ Minicurso de buceo\n"
            "3️⃣ Buceo"
        )
    else:
        prompt = (
            "¡Claro! Pueden ir juntos sin problema.\n\n"
            "Para recomendarle bien el plan a tu acompañante, necesito saber qué actividad quiere hacer:\n\n"
            "1️⃣ Snorkel\n"
            "2️⃣ Minicurso de buceo\n"
            "3️⃣ Buceo"
        )
    quick_replies = [
        {"title": "1️⃣ Snorkel", "value": "1"},
        {"title": "2️⃣ Minicurso de buceo", "value": "2"},
        {"title": "3️⃣ Buceo", "value": "3"},
    ]
    return prompt, quick_replies


def _detect_companion_activity_answer(message: str, base_id: str | None) -> str | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None
    if normalized == "1":
        return "snorkeling"
    if normalized == "2":
        return "minicourse"
    if normalized == "3":
        return "diving"

    activity_intent = _detect_companion_activity_intent(message, base_id)
    if activity_intent != "same":
        return activity_intent
    if base_id == "snorkeling":
        return "snorkeling"
    if base_id == "minicourse":
        return "minicourse"
    if base_id == "2_dives_1_day":
        return "diving"
    return None


def _detect_companion_certification_answer(message: str) -> bool | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None

    if normalized in {"1", "si", "sí"}:
        return True
    if normalized in {"2", "no"}:
        return False

    negative_patterns = (
        r"\bno\s+esta\s+certificad[oa]\b",
        r"\bno\s+es\s+certificad[oa]\b",
        r"\bsin\s+certificacion\b",
        r"\bprimera\s+vez\b",
        r"\bnunca\s+ha\s+buceado\b",
        r"\bnunca\s+bucea\b",
        r"\bprincipiante\b",
    )
    for pattern in negative_patterns:
        if re.search(pattern, normalized):
            return False

    positive_patterns = (
        r"\bcertificad[oa]\b",
        r"\bopen\s+water\b",
        r"\badvanced\b",
        r"\brescue\b",
        r"\bdive\s*master\b",
        r"\bdivemaster\b",
    )
    for pattern in positive_patterns:
        if re.search(pattern, normalized):
            return True

    return None


def _detect_binary_yes_no_answer(message: str) -> bool | None:
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return None
    if normalized in {"1", "si", "sí", "yes"}:
        return True
    if normalized in {"2", "no"}:
        return False
    return None


def _render_service_info_card_for_current_location(state: ConversationState, service_id: str) -> str:
    info_state = ConversationState(conversation_id=state.conversation_id)
    info_state.language = state.language
    info_state.location = state.location
    info_state.selected_service = decision_tree._service_for_location(service_id, state)
    return decision_tree._format_info_card(info_state)


def _set_mixed_from_single_group_context(state: ConversationState, group_context: dict | None) -> None:
    setattr(state, "mixed_from_single_group_context", group_context)


def _get_mixed_from_single_group_context(state: ConversationState) -> dict | None:
    group_context = getattr(state, "mixed_from_single_group_context", None)
    return group_context if isinstance(group_context, dict) else None


def _clear_mixed_from_single_group_context(state: ConversationState) -> None:
    setattr(state, "mixed_from_single_group_context", None)


def _activity_to_service_id(activity: str) -> str | None:
    if activity == "snorkeling":
        return "snorkeling"
    if activity == "minicourse":
        return "minicourse"
    if activity == "diving":
        return "2_dives_1_day"
    return None


def _activity_to_cart_item(activity: str) -> tuple[str, str | None] | None:
    if activity == "snorkeling":
        return "snorkel", None
    if activity == "minicourse":
        return "beginner", None
    if activity == "diving":
        return "cert", "2_dives_1_day"
    return None


def _cart_item_to_service_id(item: dict) -> str | None:
    item_type = item.get("type")
    plan = item.get("plan")
    if item_type == "snorkel":
        return "snorkeling"
    if item_type == "beginner":
        return "minicourse"
    if item_type == "cert" and plan == "2_dives_1_day":
        return "2_dives_1_day"
    return None


def _infer_companion_base_service_id(state: ConversationState) -> str | None:
    selected_service = _normalize_base_service_id(getattr(state, "selected_service", None))
    if _map_service_to_cart_item(selected_service or "") is not None:
        return selected_service

    if decision_tree._is_in_mixed_flow(state) and len(getattr(state, "mixed_cart", [])) == 1:
        inferred = _cart_item_to_service_id(state.mixed_cart[0])
        return _normalize_base_service_id(inferred)
    return None


def _append_mixed_cart_item(state: ConversationState, item_type: str, plan: str | None, qty: int) -> None:
    if qty <= 0:
        return
    lang = getattr(state, "language", "es") or "es"
    existing = next(
        (item for item in state.mixed_cart if item.get("type") == item_type and item.get("plan") == plan),
        None,
    )
    if existing is not None:
        existing["qty"] += qty
        return
    state.mixed_cart.append({
        "type": item_type,
        "qty": qty,
        "plan": plan,
        "label": decision_tree._cart_label_for(item_type, plan, lang),
    })


def _append_group_context_to_existing_mixed_cart(state: ConversationState, group_context: dict | None) -> str:
    if group_context:
        for allocation in group_context.get("allocations", []):
            activity = allocation.get("activity")
            qty = allocation.get("qty")
            if not activity or not isinstance(qty, int):
                continue
            cart_item = _activity_to_cart_item(activity)
            if cart_item is None:
                continue
            item_type, plan = cart_item
            _append_mixed_cart_item(state, item_type, plan, qty)
    _clear_mixed_from_single_group_context(state)
    return decision_tree._goto_mixed_cart_review(state)


def _build_group_allocations_summary_line(activity: str, qty: int, lang: str) -> str:
    if lang == "es":
        label = {
            "snorkeling": "Snorkel",
            "minicourse": "Minicurso de buceo",
            "diving": "Buceo certificado",
        }.get(activity, activity)
        person_label = "1 persona" if qty == 1 else f"{qty} personas"
        return f"*{person_label} — {label}*"
    label = {
        "snorkeling": "Snorkeling",
        "minicourse": "Mini-course",
        "diving": "Certified diving",
    }.get(activity, activity)
    person_label = "1 person" if qty == 1 else f"{qty} people"
    return f"*{person_label} — {label}*"


def _activity_display_label(activity: str, lang: str) -> str:
    if lang == "es":
        return {
            "snorkeling": "snorkel",
            "minicourse": "minicurso de buceo",
            "diving": "buceo certificado",
        }.get(activity, activity)
    return {
        "snorkeling": "snorkeling",
        "minicourse": "mini-course",
        "diving": "certified diving",
    }.get(activity, activity)


def _build_menu_mixed_group_offer_text(state: ConversationState, group_context: dict) -> str:
    lang = getattr(state, "language", "es") or "es"
    speaker_activity = group_context.get("speaker_activity")
    allocations = group_context.get("allocations", [])
    if lang != "es":
        return (
            "You can book a mixed group without a problem.\n\n"
            "If you want, continue with *👥 Mixed group (diving + snorkeling)* and I'll guide you through the cart step by step."
        )

    speaker_label = _activity_display_label(speaker_activity, lang) if speaker_activity else "tu actividad"
    if len(allocations) == 1:
        allocation = allocations[0]
        qty = allocation.get("qty", 1)
        companion_label = _activity_display_label(allocation.get("activity", ""), lang)
        companion_phrase = (
            f"tu acompañante puede hacer *{companion_label}*"
            if qty == 1 else
            f"tus {qty} acompañantes pueden hacer *{companion_label}*"
        )
        plan_line = f"Tú puedes hacer *{speaker_label}* y {companion_phrase} en la misma salida."
    else:
        plan_line = "Podemos organizar un plan mixto para el grupo con actividades distintas en la misma salida."

    cta = (
        "Si quieres, pulsa *👥 Grupo mixto (buceo + snorkel)* "
        "y te organizo la reserva paso a paso."
    )
    return f"¡Claro! {plan_line}\n\n{cta}"


def _render_group_info_cards(state: ConversationState, allocations: list[dict]) -> str:
    if not allocations:
        return ""
    if len(allocations) == 1:
        service_id = _activity_to_service_id(allocations[0]["activity"])
        return _render_service_info_card_for_current_location(state, service_id) if service_id else ""

    sections: list[str] = []
    for allocation in allocations:
        service_id = _activity_to_service_id(allocation["activity"])
        if not service_id:
            continue
        sections.append(
            _build_group_allocations_summary_line(allocation["activity"], allocation["qty"], state.language)
            + "\n"
            + _render_service_info_card_for_current_location(state, service_id)
        )
    return "\n\n".join(section for section in sections if section)


def _resolve_group_certification(group_context: dict, cert_answer: bool) -> dict:
    resolved_allocations: list[dict] = []
    for allocation in group_context.get("allocations", []):
        activity = allocation.get("activity")
        qty = allocation.get("qty")
        if not isinstance(qty, int) or qty <= 0 or not activity:
            continue
        if activity == "diving" and not cert_answer:
            resolved_allocations.append({"activity": "minicourse", "qty": qty})
        else:
            resolved_allocations.append({"activity": activity, "qty": qty})

    resolved_context = dict(group_context)
    resolved_context["allocations"] = _merge_group_allocations(resolved_allocations)
    resolved_context["companion_count"] = sum(item["qty"] for item in resolved_context["allocations"])
    resolved_context["needs_activity_clarification"] = False
    return resolved_context


def _replace_group_activity(group_context: dict, source_activity: str, target_activity: str) -> dict:
    replaced_allocations: list[dict] = []
    for allocation in group_context.get("allocations", []):
        activity = allocation.get("activity")
        qty = allocation.get("qty")
        if not isinstance(qty, int) or qty <= 0 or not activity:
            continue
        replaced_allocations.append({
            "activity": target_activity if activity == source_activity else activity,
            "qty": qty,
        })

    resolved_context = dict(group_context)
    resolved_context["allocations"] = _merge_group_allocations(replaced_allocations)
    resolved_context["companion_count"] = sum(item["qty"] for item in resolved_context["allocations"])
    resolved_context["needs_activity_clarification"] = False
    return resolved_context


def _build_companion_last_dive_question(state: ConversationState, diving_qty: int) -> str:
    lang = getattr(state, "language", "es") or "es"
    decision_tree.set_quick_replies(state, "certified_last_dive")
    from src.flows.decision_tree import MESSAGES as _M

    prompt = _M["certified_last_dive"][lang]
    if lang != "es":
        return prompt
    target = "esas personas" if diving_qty > 1 else "tu acompañante"
    return f"Perfecto. Antes de confirmar ese plan, necesito saber una cosa sobre {target}:\n\n{prompt}"


def _build_companion_refresher_prompt(state: ConversationState) -> str:
    lang = getattr(state, "language", "es") or "es"
    decision_tree.set_quick_replies(state, "refresher_interest")
    from src.flows.decision_tree import MESSAGES as _M

    return _M["refresher_info"][lang]


def _build_group_activity_intro(lang: str, allocations: list[dict]) -> str:
    if lang != "es":
        return "Your group can go together without a problem. Here is the information for each activity:"
    if not allocations:
        return "¡Claro! Pueden ir juntos sin problema."
    if len(allocations) == 1:
        allocation = allocations[0]
        qty = allocation["qty"]
        people_phrase = "tu acompañante" if qty == 1 else f"tus {qty} acompañantes"
        if allocation["activity"] == "snorkeling":
            return f"¡Claro! Pueden ir juntos sin problema. Para {people_phrase}, esta es la información completa del plan de snorkel:"
        if allocation["activity"] == "minicourse":
            return f"¡Claro! Pueden ir juntos sin problema. Para {people_phrase}, esta es la información completa del minicurso de buceo:"
        return f"¡Claro! Pueden ir juntos sin problema. Para {people_phrase}, esta es la información completa del plan de buceo para buzos certificados:"
    return "¡Claro! Pueden ir juntos sin problema. Para tu grupo, te comparto la información de cada actividad:"


def _show_group_activity_cards(state: ConversationState, base_id: str | None, group_context: dict) -> str:
    allocations = group_context.get("allocations", [])
    companion_count = group_context.get("companion_count")
    _set_mixed_from_single_group_context(state, group_context)
    info_cards = _render_group_info_cards(state, allocations)
    follow_up, quick_replies = _build_mixed_from_single_follow_up(
        {"base_id": base_id, "companion_count": companion_count},
        state.language,
    )
    setattr(state, "mixed_from_single_offer_pending", True)
    state.quick_replies = quick_replies
    intro = _build_group_activity_intro(state.language, allocations)
    return f"{intro}\n\n{info_cards}\n\n{follow_up}" if info_cards else f"{intro}\n\n{follow_up}"


def _coerce_group_context_with_activity_intent(
    message: str,
    base_id: str | None,
    parsed_group_context: dict | None,
) -> dict | None:
    activity_intent = _detect_companion_activity_intent(message, base_id)
    if activity_intent == "same":
        activity_intent = _base_service_to_activity_intent(base_id)

    if activity_intent is None:
        return parsed_group_context

    if parsed_group_context is None:
        return _build_group_context_from_activity(activity_intent)

    if parsed_group_context.get("allocations"):
        return parsed_group_context

    companion_count = parsed_group_context.get("companion_count") or 1
    total_people = parsed_group_context.get("total_people")
    return _build_group_context_from_activity(activity_intent, companion_count, total_people)


def _handle_companion_group_context(state: ConversationState, base_id: str | None, lang: str, group_context: dict | None) -> str:
    setattr(state, "mixed_from_single_companion_context_active", True)
    if not group_context:
        prompt, quick_replies = _build_mixed_from_single_activity_question()
        setattr(state, "mixed_from_single_activity_question_pending", True)
        state.quick_replies = quick_replies
        return prompt

    _set_mixed_from_single_group_context(state, group_context)
    companion_count = group_context.get("companion_count")
    allocations = group_context.get("allocations", [])
    if group_context.get("needs_activity_clarification") or not allocations:
        prompt, quick_replies = _build_mixed_from_single_activity_question(companion_count)
        setattr(state, "mixed_from_single_activity_question_pending", True)
        state.quick_replies = quick_replies
        return prompt

    diving_qty = sum(item["qty"] for item in allocations if item.get("activity") == "diving")
    if diving_qty > 0:
        prompt, quick_replies = _build_mixed_from_single_cert_question(diving_qty)
        setattr(state, "mixed_from_single_cert_question_pending", True)
        state.quick_replies = quick_replies
        return prompt

    return _show_group_activity_cards(state, base_id, group_context)


def _build_mixed_from_single_activity_response(
    state: ConversationState,
    base_id: str | None,
    lang: str,
    target_service_id: str,
    intro: str,
) -> str:
    info_card = _render_service_info_card_for_current_location(state, target_service_id)
    follow_up, quick_replies = _build_mixed_from_single_follow_up({"base_id": base_id, "companion_count": 1}, lang)
    setattr(state, "mixed_from_single_offer_pending", True)
    _set_mixed_from_single_group_context(state, _build_group_context_from_activity(_base_service_to_activity_intent(target_service_id) or "snorkeling"))
    state.quick_replies = quick_replies
    return f"{intro}\n\n{info_card}\n\n{follow_up}"


def _handle_companion_activity_intent(
    state: ConversationState,
    base_id: str | None,
    lang: str,
    activity_intent: str | None,
) -> str:
    if activity_intent is None:
        return _handle_companion_group_context(state, base_id, lang, None)
    if activity_intent == "same":
        activity_intent = _base_service_to_activity_intent(base_id)
    if activity_intent is None:
        return _handle_companion_group_context(state, base_id, lang, None)
    return _handle_companion_group_context(
        state,
        base_id,
        lang,
        _build_group_context_from_activity(activity_intent),
    )


def _map_service_to_cart_item(service_id: str) -> tuple[str, str | None] | None:
    """Map a concrete service_id to a cart item type/plan for the mixed flow.

    We only support the main day-tour services that already participate in the
    mixed cart: snorkeling, 2_dives_1_day (certified), and minicourse.
    """
    if not service_id:
        return None

    base_id = service_id
    suffix = "_already_on_island"
    if base_id.endswith(suffix):
        base_id = base_id[: -len(suffix)]

    if base_id == "snorkeling":
        return "snorkel", None
    if base_id == "2_dives_1_day":
        # Certified 2-dives / 1-day plan
        return "cert", "2_dives_1_day"
    if base_id == "minicourse":
        return "beginner", None
    return None


def _enter_mixed_flow_from_single(state: ConversationState) -> str:
    """Switch from a single-activity flow into the mixed cart, preloading 1× current service.

    This keeps the existing selected_service/location/colombian state but
    resets the mixed_* fields and appends a single cart item representing the
    current activity for the main user. The user can then add their friend's
    activity from the standard mixed cart UI.
    """
    svc_id = getattr(state, "selected_service", None)
    item = _map_service_to_cart_item(svc_id or "")
    if not item:
        # Fallback: show the standard mixed group menu so an advisor can help
        # structure the group; this should be rare.
        state.step = Step.GROUP_TYPE
        decision_tree.set_quick_replies(state, "group_type")
        from src.flows.decision_tree import MESSAGES as _M

        lang = getattr(state, "language", "es") or "es"
        return _M["group_type"][lang]

    item_type, plan = item

    # Reset cart-style state and enter via the diving+snorkel entry path.
    decision_tree._reset_mixed_state(state)
    state.mixed_entry_path = "diving_snorkel"

    # Preload 1× of the current activity for the main user.
    _append_mixed_cart_item(state, item_type, plan, 1)

    group_context = _get_mixed_from_single_group_context(state)
    if group_context:
        for allocation in group_context.get("allocations", []):
            activity = allocation.get("activity")
            qty = allocation.get("qty")
            if not activity or not isinstance(qty, int):
                continue
            cart_item = _activity_to_cart_item(activity)
            if cart_item is None:
                continue
            companion_item_type, companion_plan = cart_item
            _append_mixed_cart_item(state, companion_item_type, companion_plan, qty)

    _clear_mixed_from_single_group_context(state)

    # Jump straight to the cart review so they immediately see their cart and
    # can add the friend's activity.
    return decision_tree._goto_mixed_cart_review(state)


def _maybe_offer_mixed_from_single(state: ConversationState, message: str, answer: str) -> str:
    """Optionally append an invitation to switch into the mixed cart flow.

    We keep the natural RAG answer, and only when the user mentions friends or
    companions AND we're in a simple tour (snorkel / 2 dives / minicourse) that
    is not already inside the mixed cart flow.
    """
    try:
        svc_id = getattr(state, "selected_service", None)
        if not svc_id:
            return answer

        # Never offer while already inside the mixed flow.
        if decision_tree._is_in_mixed_flow(state):
            return answer

        # Only consider services we know how to represent in the cart.
        if _map_service_to_cart_item(svc_id or "") is None:
            return answer

        if not _detect_companion_intent(message, state):
            return answer

        # Normalise the concrete service_id to its base variant.
        base_id = _normalize_base_service_id(svc_id)

        lang = getattr(state, "language", "es") or "es"
        setattr(state, "mixed_from_single_companion_context_active", True)

        if lang == "es" and base_id in {"snorkeling", "2_dives_1_day", "minicourse"}:
            parsed_group_context = _build_companion_group_context(message, base_id)
            group_context = _coerce_group_context_with_activity_intent(message, base_id, parsed_group_context)
            return _handle_companion_group_context(state, base_id, lang, group_context)

        follow_up, quick_replies = _build_mixed_from_single_follow_up(base_id, lang)

        # Mark that we're waiting for a yes/no answer about entering the mixed cart.
        setattr(state, "mixed_from_single_offer_pending", True)
        state.quick_replies = quick_replies

        if answer:
            return f"{answer}\n\n{follow_up}"
        return follow_up
    except Exception:
        # Fail-safe: never break the main flow because of this helper.
        return answer


def _maybe_handle_mixed_group_from_menu(state: ConversationState, message: str) -> str | None:
    if state.step not in {Step.MAIN_MENU, Step.RESERVA_MENU, Step.GROUP_TYPE}:
        return None
    if not _detect_companion_intent(message, state):
        return None

    group_context = _extract_menu_mixed_group_context(message)
    if not group_context:
        return None

    state.step = Step.GROUP_TYPE
    state.quick_replies = [
        {"title": "👥 Grupo mixto (buceo + snorkel)", "value": "3"},
        {"title": "🔙 Volver", "value": "back"},
    ]
    return _build_menu_mixed_group_offer_text(state, group_context)


def _maybe_handle_companion_request_inside_mixed_flow(state: ConversationState, message: str) -> str | None:
    if not decision_tree._is_in_mixed_flow(state):
        return None
    if getattr(state, "language", "es") != "es":
        return None
    if not _detect_companion_intent(message, state):
        return None

    base_id = _infer_companion_base_service_id(state)
    if base_id is None:
        return None

    parsed_group_context = _build_companion_group_context(message, base_id)
    group_context = _coerce_group_context_with_activity_intent(message, base_id, parsed_group_context)
    return _handle_companion_group_context(state, base_id, state.language, group_context)


def _handle_pending_companion_flow(state: ConversationState, message: str, msg_lower: str) -> str | None:
    if not any(
        getattr(state, attr, False)
        for attr in (
            "mixed_from_single_activity_question_pending",
            "mixed_from_single_cert_question_pending",
            "mixed_from_single_last_dive_question_pending",
            "mixed_from_single_refresher_interest_pending",
            "mixed_from_single_offer_pending",
        )
    ):
        return None

    base_id = _infer_companion_base_service_id(state)

    if getattr(state, "mixed_from_single_activity_question_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or {}
        group_answer = _detect_companion_group_question_answer(
            message,
            base_id,
            current_group_context.get("companion_count"),
            current_group_context.get("total_people"),
        )
        if group_answer is None:
            prompt, quick_replies = _build_mixed_from_single_activity_question(
                current_group_context.get("companion_count")
            )
            state.quick_replies = quick_replies
            return "No te entendí del todo.\n\n" + prompt

        setattr(state, "mixed_from_single_activity_question_pending", False)
        return _handle_companion_group_context(state, base_id, state.language, group_answer)

    if getattr(state, "mixed_from_single_cert_question_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or _build_group_context_from_activity("diving")
        diving_qty = sum(
            item["qty"]
            for item in current_group_context.get("allocations", [])
            if item.get("activity") == "diving"
        ) or 1
        cert_answer = _detect_companion_certification_answer(message)
        if cert_answer is None:
            prompt, quick_replies = _build_mixed_from_single_cert_question(diving_qty)
            state.quick_replies = quick_replies
            return "No te entendí del todo.\n\n" + prompt

        setattr(state, "mixed_from_single_cert_question_pending", False)
        resolved_group_context = _resolve_group_certification(current_group_context, cert_answer)
        _set_mixed_from_single_group_context(state, resolved_group_context)
        if cert_answer:
            setattr(state, "mixed_from_single_last_dive_question_pending", True)
            return _build_companion_last_dive_question(state, diving_qty)
        response = _show_group_activity_cards(state, base_id, resolved_group_context)
        intro = (
            "Perfecto. Si no todos están certificados, lo ideal es pasar ese subgrupo a minicurso de iniciación:"
            if diving_qty > 1 else
            "Perfecto. Si no está certificado, lo ideal es empezar con este minicurso de iniciación:"
        )
        return f"{intro}\n\n{response}"

    if getattr(state, "mixed_from_single_last_dive_question_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or _build_group_context_from_activity("diving")
        diving_qty = sum(
            item["qty"]
            for item in current_group_context.get("allocations", [])
            if item.get("activity") == "diving"
        ) or 1
        last_dive_over_2_years = _detect_binary_yes_no_answer(message)
        if last_dive_over_2_years is None:
            return "No te entendí del todo.\n\n" + _build_companion_last_dive_question(state, diving_qty)

        setattr(state, "mixed_from_single_last_dive_question_pending", False)
        updated_group_context = dict(current_group_context)
        updated_group_context["last_dive_over_2_years"] = last_dive_over_2_years
        _set_mixed_from_single_group_context(state, updated_group_context)
        if last_dive_over_2_years:
            setattr(state, "mixed_from_single_refresher_interest_pending", True)
            return _build_companion_refresher_prompt(state)
        return _show_group_activity_cards(state, base_id, updated_group_context)

    if getattr(state, "mixed_from_single_refresher_interest_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or _build_group_context_from_activity("diving")
        refresher_interested = _detect_binary_yes_no_answer(message)
        if refresher_interested is None:
            return "No te entendí del todo.\n\n" + _build_companion_refresher_prompt(state)

        setattr(state, "mixed_from_single_refresher_interest_pending", False)
        updated_group_context = dict(current_group_context)
        updated_group_context["refresher_interested"] = refresher_interested
        if refresher_interested:
            updated_group_context = _replace_group_activity(updated_group_context, "diving", "minicourse")
        _set_mixed_from_single_group_context(state, updated_group_context)
        return _show_group_activity_cards(state, base_id, updated_group_context)

    if getattr(state, "mixed_from_single_offer_pending", False):
        if msg_lower in {"1", "si", "sí", "yes"}:
            setattr(state, "mixed_from_single_offer_pending", False)
            setattr(state, "mixed_from_single_companion_context_active", False)
            setattr(state, "mixed_from_single_activity_question_pending", False)
            setattr(state, "mixed_from_single_cert_question_pending", False)
            setattr(state, "mixed_from_single_last_dive_question_pending", False)
            setattr(state, "mixed_from_single_refresher_interest_pending", False)
            state.quick_replies = []
            if decision_tree._is_in_mixed_flow(state):
                logger.info("[SUPERVISOR] Mixed companion: user accepted add-to-existing-cart offer")
                return _append_group_context_to_existing_mixed_cart(state, _get_mixed_from_single_group_context(state))
            logger.info("[SUPERVISOR] Mixed-from-single: user accepted cart offer")
            return _enter_mixed_flow_from_single(state)
        if msg_lower in {"2", "no"}:
            setattr(state, "mixed_from_single_offer_pending", False)
            setattr(state, "mixed_from_single_companion_context_active", False)
            setattr(state, "mixed_from_single_activity_question_pending", False)
            setattr(state, "mixed_from_single_cert_question_pending", False)
            setattr(state, "mixed_from_single_last_dive_question_pending", False)
            setattr(state, "mixed_from_single_refresher_interest_pending", False)
            if decision_tree._is_in_mixed_flow(state):
                _clear_mixed_from_single_group_context(state)
                state.quick_replies = []
                return decision_tree._goto_mixed_cart_review(state)
            _clear_mixed_from_single_group_context(state)
            state.quick_replies = []
            if state.language == "es":
                return (
                    "Perfecto, entonces mantenemos solo la actividad que ya tenías. "
                    "Si más adelante quieres que te ayude a armar un plan mixto para tu amigo o acompañante, solo dime."
                )
            return (
                "Perfect, we'll keep only your current activity. "
                "If later you want help building a mixed plan for your friend or companion, just let me know."
            )
        setattr(state, "mixed_from_single_offer_pending", False)
        _clear_mixed_from_single_group_context(state)

    return None


def _match_quick_reply_text(state: ConversationState, message: str) -> str | None:
    """If user free text clearly maps to a current quick-reply button, return its value.

    Only matches against `state.quick_replies` (the buttons actually displayed now), so a
    text match cannot push the user off the current branch of the decision tree.
    """
    if not state.quick_replies:
        return None

    msg_clean = _normalize_for_menu_match(message)
    if not msg_clean:
        return None

    msg_words = msg_clean.split()
    msg_words_set = set(msg_words)

    # Question-word guard: questions belong to RAG even if they contain a button keyword.
    if msg_words_set & MENU_MATCH_QUESTION_WORDS:
        return None

    sig_msg = {w for w in msg_words_set if len(w) >= 3 and w not in MENU_MATCH_STOP_WORDS}
    if not sig_msg:
        return None

    best_value: str | None = None
    best_score = 0.0

    for reply in state.quick_replies:
        title = reply.get("title", "")
        title_clean = _normalize_for_menu_match(title)
        if not title_clean:
            continue

        if msg_clean == title_clean:
            return reply.get("value")

        title_words = set(title_clean.split())
        sig_title = {w for w in title_words if len(w) >= 3 and w not in MENU_MATCH_STOP_WORDS}
        if not sig_title:
            continue

        common = sig_msg & sig_title
        if not common:
            continue
        score = len(common) / max(len(sig_msg), 1)
        if score > best_score and score >= 0.5:
            best_score = score
            best_value = reply.get("value")

    return best_value


def _go_back_one_step(state: ConversationState) -> str:
    """Move state one step up in the decision tree and return the previous prompt.

    Falls back to MAIN_MENU when the current step has no mapping in BACK_STEP.
    """
    from src.flows.decision_tree import MESSAGES

    dynamic_target = decision_tree.resolve_back_target(state)
    if dynamic_target is not None:
        target_step, qr_key = dynamic_target
        state.summary_mode = None
    else:
        target_step, qr_key = BACK_STEP.get(state.step, (Step.MAIN_MENU, "main_menu"))
    state.step = target_step
    decision_tree.set_quick_replies(state, qr_key)
    return MESSAGES[qr_key][state.language]


def _matches_escalation_keyword(msg_lower: str) -> bool:
    """Word-boundary matching for escalation keywords to avoid false positives.

    Multi-word phrases ("hablar con") use substring matching; single words use
    word boundaries so "persona" does not match inside "personas".
    """
    for kw in ESCALATION_KEYWORDS:
        if " " in kw:
            if kw in msg_lower:
                return True
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", msg_lower):
                return True
    return False


def _detect_broken_link_complaint(message: str, state_history: list[dict] | None = None) -> bool:
    """Return True if the user is complaining about a broken link/form/URL.

    Requires either:
    - The message itself mentions a link-like token AND a complaint phrase, OR
    - The complaint phrase is present AND the bot's last reply contained a URL
      (so "no me funciona" right after the bot sends a link is captured).
    """
    msg_lower = " ".join(message.strip().lower().split())
    if not msg_lower:
        return False

    has_complaint = any(phrase in msg_lower for phrase in BROKEN_LINK_COMPLAINT_PHRASES)
    if not has_complaint:
        return False

    has_link_token_in_msg = any(
        re.search(r"\b" + re.escape(tok) + r"\b", msg_lower)
        for tok in BROKEN_LINK_TARGET_TOKENS
    )
    if has_link_token_in_msg:
        return True

    # Otherwise, check if the bot's most recent message contained a URL.
    if state_history:
        for entry in reversed(state_history):
            if entry.get("role") == "assistant":
                content = (entry.get("content") or "").lower()
                if "http://" in content or "https://" in content:
                    return True
                break
    return False


def _is_substantive_free_text(message: str) -> bool:
    normalized = " ".join(message.strip().lower().split())
    normalized_clean = normalized.strip("?!.,;:")
    words = normalized_clean.split()
    if not normalized_clean:
        return False
    if normalized_clean in LANGUAGE_SELECTION_KEYWORDS:
        return False
    if normalized_clean in GREETING_ONLY_KEYWORDS:
        return False
    return len(normalized_clean.split()) >= 4 or "?" in normalized


def _infer_language(message: str, fallback: str = "es") -> str:
    normalized = f" {message.strip().lower()} "
    english_matches = sum(1 for hint in ENGLISH_HINTS if f" {hint} " in normalized)
    spanish_matches = sum(1 for hint in SPANISH_HINTS if f" {hint} " in normalized)
    if english_matches > spanish_matches:
        return "en"
    if spanish_matches > english_matches:
        return "es"
    return fallback


def _build_extra_context(state: ConversationState) -> str | None:
    """Build a compact natural-language summary of the current state to help RAG.

    Se usa como extra_context para que el agente de conocimiento tenga claro:
    - Actividad seleccionada
    - Si el cliente es buzo certificado
    - Si es colombiano
    - Desde donde sale (Cartagena / islas)
    - Isla / hotel reportado
    - Inactividad (>2 años) y si mostro interes en refresher
    """

    parts: list[str] = []

    # Idioma actual de la conversación
    if state.language == "es":
        parts.append("La conversación se esta llevando a cabo en español.")
    elif state.language == "en":
        parts.append("The conversation is currently happening in English.")

    # Ubicacion base
    if state.location == "cartagena":
        parts.append("El cliente indica que saldra desde Cartagena para su experiencia.")
    elif state.location == "island":
        parts.append("El cliente indica que ya esta en las Islas del Rosario.")

    # Isla / hotel
    if getattr(state, "island", None):
        parts.append(f"Se hospeda (o se hospedara) en la isla: {state.island}.")
    if getattr(state, "hotel", None):
        parts.append(f"Hotel/alojamiento reportado: {state.hotel}.")

    # Actividad seleccionada
    if getattr(state, "selected_service", None):
        try:
            from src.flows.decision_tree import SERVICES, MULTI_DAY_SERVICES

            service_id = state.selected_service
            service = SERVICES.get(service_id)
            if service:
                name_es = service.get("name_es", service_id)
                parts.append(
                    f"Actividad seleccionada en el arbol de opciones: {name_es} (id={service_id})."
                )

                # Contexto de tipo de plan: 1 día vs paquete/multi-día
                is_multi_day = service_id in MULTI_DAY_SERVICES or service.get("includes_night_dive", False)
                if state.language == "es":
                    if is_multi_day:
                        parts.append(
                            "El plan seleccionado es un paquete de varios dias o requiere al menos una noche de alojamiento en las islas."
                        )
                    else:
                        parts.append(
                            "El plan seleccionado es de un solo dia (ida y vuelta el mismo dia)."
                        )
                    parts.append(
                        "Si el cliente pregunta por amigos o acompanantes que quieran bucear o hacer snorkel, "
                        "prioriza opciones que respeten este contexto: mismo origen (Cartagena vs ya en las islas) "
                        "y, cuando sea posible, misma logica de duracion (plan de 1 dia vs paquete multi-dia), salvo que el cliente pida explicitamente otra cosa."
                    )
                else:
                    if is_multi_day:
                        parts.append(
                            "The selected plan is a multi-day package or requires at least one overnight stay on the islands."
                        )
                    else:
                        parts.append(
                            "The selected plan is a one-day experience (go and return on the same day)."
                        )
                    parts.append(
                        "If the customer asks about friends or companions who want to dive or snorkel, "
                        "prioritize options that keep this context: same origin (Cartagena vs already on the islands) "
                        "and, when possible, a similar duration pattern (1-day plan vs multi-day package), unless the customer explicitly asks otherwise."
                    )
        except Exception:
            parts.append(
                f"Actividad seleccionada en el arbol de opciones con id={state.selected_service}."
            )

    # Buzo certificado / principiante
    if getattr(state, "is_certified", None) is True:
        parts.append("El cliente marco que es buzo certificado (solo buzos certificados en el grupo).")
    elif getattr(state, "is_certified", None) is False:
        parts.append("El cliente marco que no es buzo certificado o que viene como principiante/snorkel.")

    # Colombiano o no
    if getattr(state, "is_colombian", None) is True:
        parts.append("El cliente indico que es colombiano/a (aplican tarifas locales y descuentos especiales).")
    elif getattr(state, "is_colombian", None) is False:
        parts.append("El cliente indico que no es colombiano/a.")

    # Inactividad y refresher
    if getattr(state, "last_dive_over_2_years", None) is True:
        parts.append("Segun el arbol, lleva mas de 2 años sin bucear.")
    elif getattr(state, "last_dive_over_2_years", None) is False:
        parts.append("Segun el arbol, su ultima inmersión fue hace menos de 2 años.")

    if getattr(state, "refresher_interested", None) is True:
        parts.append("En el flujo marco que SI le interesa incluir un refresher.")
    elif getattr(state, "refresher_interested", None) is False:
        parts.append("En el flujo marco que NO le interesa incluir un refresher.")

    if not parts:
        return None
    return " ".join(parts)


def _answer_state_introspection(state: ConversationState, message: str) -> str | None:
    """Answer simple meta-questions using the current conversation state.

    Esto evita respuestas genéricas de RAG cuando el usuario pregunta por
    cosas que ya sabemos del flujo guiado (actividad elegida, si es buzo
    certificado, si es colombiano, etc.).
    """

    normalized = " ".join(message.strip().lower().split())
    normalized_clean = normalized.strip("?!.,;:")
    words = normalized_clean.split()
    lang = state.language or "es"

    # Por ahora cubrimos solo las preguntas en español e inglés que ya se han visto
    if lang == "es":
        # Preguntas sobre la actividad elegida ("Que actividad hago?", "Que actividad he seleccionado?",
        # "Actividad seleccionada?", etc.). Usamos heuristicas amplias pero intentando no
        # interceptar preguntas generales sobre "actividades" en plural.
        ask_activity_es = False
        # Trabajamos con palabra exacta "actividad" para no confundir con "actividades"
        if "actividad" in words:
            text = normalized_clean

            # Casos directos tipo "actividad seleccionada?" (con o sin una "c")
            if "actividad seleccionad" in text or "actividad selecionad" in text:
                ask_activity_es = True

            # Casos tipo "que actividad ..." / "qué actividad ..." en singular. En este punto ya
            # sabemos que hay la palabra exacta "actividad", asi que asumimos que se refiere a
            # la actividad concreta de esta conversacion y no a una lista generica de actividades.
            if not ask_activity_es and ("que actividad" in text or "qué actividad" in text):
                ask_activity_es = True

            # Casos tipo "cual es la actividad?" / "cual es mi actividad?"
            if not ask_activity_es and ("cual es la actividad" in text or "cuál es la actividad" in text):
                ask_activity_es = True

        if ask_activity_es:
            if state.selected_service:
                try:
                    from src.flows.decision_tree import SERVICES

                    service = SERVICES.get(state.selected_service)
                    if service:
                        name = service.get(f"name_{lang}", state.selected_service)
                        return f"En esta conversación seleccionaste la actividad: {name}."
                except Exception:
                    # Si algo falla al leer SERVICES, caemos en el fallback genérico
                    pass
            return "Todavia no has elegido ninguna actividad concreta en esta conversación."

        # "Soy buzo certificado?"
        if "soy buzo" in normalized_clean and "certificado" in normalized_clean:
            if state.is_certified is True:
                return "En esta conversación marcaste que eres buzo certificado (solo buzos certificados en el grupo)."
            if state.is_certified is False:
                return "En esta conversación marcaste que no eres buzo certificado o que vienes como principiante/snorkel."
            return "Aun no me has dicho si eres buzo certificado o no en esta conversación."

        # "Soy colombiano?" / "Soy colombiana?"
        if "soy " in normalized_clean and "colombian" in normalized_clean:
            if state.is_colombian is True:
                return "En esta conversación me dijiste que eres colombiano/a."
            if state.is_colombian is False:
                return "En esta conversación me dijiste que no eres colombiano/a."
            return "Aun no me has dicho si eres colombiano/a en esta conversación."

        # "De donde soy?" / "De dónde soy?" -> origen aproximado del cliente
        if ("de donde" in normalized_clean or "de dónde" in normalized_clean) and "soy" in normalized_clean:
            idioma_actual = "español" if state.language == "es" else "inglés"
            if state.is_colombian is True:
                return (
                    "En esta conversación me dijiste que eres colombiano/a. "
                    "No tengo mas detalles sobre tu ciudad especifica."
                )
            if state.is_colombian is False:
                return (
                    "En esta conversación no me has dicho exactamente de que pais o ciudad eres. "
                    f"Solo se que marcaste que no eres colombiano/a y que estamos hablando en {idioma_actual}."
                )
            return (
                "Todavia no me has dicho de donde eres en esta conversación. "
                f"Solo se que estamos hablando en {idioma_actual}."
            )

        # "Cual es mi nacionalidad?" / "De que nacionalidad soy?"
        if "nacionalidad" in normalized_clean:
            idioma_actual = "español" if state.language == "es" else "inglés"
            if state.is_colombian is True:
                return (
                    "En esta conversación me dijiste que eres colombiano/a. "
                    "No tengo mas información sobre si tienes otra nacionalidad."
                )
            if state.is_colombian is False:
                return (
                    "En esta conversación marcaste que no eres colombiano/a, "
                    "pero no me has dicho exactamente cuál es tu nacionalidad."
                )
            return (
                "Todavia no me has dicho cuál es tu nacionalidad en esta conversación. "
                f"Solo se que estamos hablando en {idioma_actual}."
            )

        # "Llevo mas de X anos/años sin bucear?" o "Han pasado mas de X anos desde que bucee/hice buceo?"
        ask_last_dive = False
        if "llevo" in normalized_clean and "sin bucear" in normalized_clean:
            ask_last_dive = True
        elif "han pasado" in normalized_clean and (
            "buceo" in normalized_clean
            or "bucee" in normalized_clean
            or "bucear" in normalized_clean
            or "inmersion" in normalized_clean
            or "inmersión" in normalized_clean
        ):
            ask_last_dive = True

        if ask_last_dive:
            if state.last_dive_over_2_years is True:
                return "En esta conversación marcaste que si, que llevas mas de 2 años sin bucear."
            if state.last_dive_over_2_years is False:
                return "En esta conversación marcaste que no, que tu ultima inmersión fue hace menos de 2 años."
            return "Aun no hemos hablado de hace cuanto fue tu ultima inmersión en esta conversación."

        # "Necesito el curso de refresco?" / "Necesito refresher?"
        if ("refres" in normalized_clean or "refresher" in normalized_clean) and (
            "necesito" in normalized_clean
            or "necesitamos" in normalized_clean
            or "tengo que" in normalized_clean
            or "tenemos que" in normalized_clean
        ):
            if state.last_dive_over_2_years is True:
                # Ya marco que lleva mas de 2 anos sin bucear
                if getattr(state, "refresher_interested", None) is True:
                    return (
                        "En esta conversación marcaste que llevas mas de 2 años sin bucear y que SI te interesa "
                        "incluir el refresher. Por seguridad, es muy recomendable hacerlo antes de tus inmersiones."
                    )
                if getattr(state, "refresher_interested", None) is False:
                    return (
                        "En esta conversación marcaste que llevas mas de 2 años sin bucear. Por seguridad, te "
                        "recomendamos hacer un refresher aunque anteriormente dijiste que no te interesaba incluirlo."
                    )
                return (
                    "En esta conversación marcaste que llevas mas de 2 años sin bucear. En esos casos, por seguridad, "
                    "si recomendamos hacer un refresher antes de tus inmersiones."
                )

            if state.last_dive_over_2_years is False:
                if getattr(state, "refresher_interested", None) is True:
                    return (
                        "En esta conversación marcaste que tu ultima inmersión fue hace menos de 2 años, pero que SI "
                        "te interesa hacer un refresher. No es obligatorio en todos los casos, pero puede ser una buena "
                        "idea si sientes que necesitas repasar habilidades."
                    )
                return (
                    "En esta conversación marcaste que tu ultima inmersión fue hace menos de 2 años. En principio "
                    "no es obligatorio hacer un refresher, aunque en algunos casos puede ser recomendable si te sientes "
                    "inseguro o llevas tiempo sin bucear."
                )

            # Si aun no sabemos nada sobre la inactividad, respondemos que falta ese dato
            return (
                "Todavia no me has dicho hace cuanto fue tu ultima inmersión en esta conversación. "
                "Si ha pasado mas de 2 años sin bucear, normalmente recomendamos hacer un refresher por seguridad."
            )

        # "Desde donde salgo?" / "Desde donde salimos?"
        if (
            ("desde donde" in normalized_clean or "desde dónde" in normalized_clean or "de donde" in normalized_clean)
            and ("salgo" in normalized_clean or "salimos" in normalized_clean)
        ):
            if state.location == "cartagena":
                return "En esta conversación marcaste que sales desde Cartagena."
            if state.location == "island":
                return "En esta conversación marcaste que ya estas en las Islas del Rosario."
            return "Aun no me has dicho desde donde sales (si desde Cartagena o si ya estas en las islas) en esta conversación."

    if lang == "en":
        # "What activity did I choose?" / "Which activity have I chosen?"
        if "activity" in normalized_clean and (
            "have i chosen" in normalized_clean
            or "did i choose" in normalized_clean
            or "did i pick" in normalized_clean
            or "am i going to do" in normalized_clean
            or "am i going to be doing" in normalized_clean
            or "am i doing" in normalized_clean
            or "will i do" in normalized_clean
            or "will i be doing" in normalized_clean
        ):
            if state.selected_service:
                try:
                    from src.flows.decision_tree import SERVICES

                    service = SERVICES.get(state.selected_service)
                    if service:
                        name = service.get(f"name_{lang}", state.selected_service)
                        return f"In this conversation you selected the activity: {name}."
                except Exception:
                    pass
            return "You have not selected a specific activity yet in this conversation."

        # "Am I a certified diver?"
        if "certified" in normalized_clean and (
            "am i" in normalized_clean
            or "i am" in normalized_clean
            or "i'm" in normalized_clean
        ) and ("diver" in normalized_clean or "dive" in normalized_clean):
            if state.is_certified is True:
                return "In this conversation you indicated that you are a certified diver (only certified divers in the group)."
            if state.is_certified is False:
                return "In this conversation you indicated that you are not a certified diver or that you are joining as a beginner/snorkeler."
            return "You haven't told me yet in this conversation whether you are a certified diver or not."

        # "Am I Colombian?"
        if "colombian" in normalized_clean and (
            "am i" in normalized_clean
            or "i am" in normalized_clean
            or "i'm" in normalized_clean
        ):
            if state.is_colombian is True:
                return "In this conversation you told me that you are Colombian."
            if state.is_colombian is False:
                return "In this conversation you told me that you are not Colombian."
            return "You haven't told me yet in this conversation whether you are Colombian or not."

        # "Has it been more than X years since my last dive?" / similar
        ask_last_dive_en = False
        if "last dive" in normalized_clean and "since" in normalized_clean:
            ask_last_dive_en = True
        elif "since my last" in normalized_clean and ("dive" in normalized_clean or "time i dived" in normalized_clean):
            ask_last_dive_en = True
        elif "since i last" in normalized_clean and ("dive" in normalized_clean or "dived" in normalized_clean or "went diving" in normalized_clean):
            ask_last_dive_en = True
        elif "since i dived" in normalized_clean or "since i went diving" in normalized_clean:
            ask_last_dive_en = True

        if ask_last_dive_en:
            if state.last_dive_over_2_years is True:
                return "In this conversation you indicated that yes, it has been more than 2 years since your last dive."
            if state.last_dive_over_2_years is False:
                return "In this conversation you indicated that no, your last dive was less than 2 years ago."
            return "We haven't talked yet in this conversation about when your last dive was."

    return None


async def route_message(state: ConversationState, message: str) -> str:
    """
    Supervisor: decides how to handle each incoming message.

    Routing rules (no LLM call):
    1. If user is in a menu step AND sends a number -> decision tree
    2. If user sends a menu/back keyword -> reset to main menu
    3. If user sends an escalation keyword -> escalate
    4. If user is in SUMMARY/ESCALATE/FREE_TEXT step -> RAG agent
    5. If user sends free text while in a menu step -> RAG agent
    """
    msg_lower = message.strip().lower()

    pii_hits = detect_pii(message)
    if pii_hits:
        state.step = Step.ESCALATE
        state.pending_escalation_reason = "datos sensibles detectados"
        logger.warning(f"[SUPERVISOR][PRIVACY] PII detected hits={pii_hits} step={state.step.value}")
        return privacy_block_message(state.language)

    # Check for escalation keywords
    if _matches_escalation_keyword(msg_lower):
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "solicitó asesor"
        state.pending_note = build_lead_summary(state, escalation_reason="solicitó asesor")
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Escalation triggered by keyword")
        return MESSAGES["escalate"][state.language]

    # Customer reports a broken link/form/URL → escalate with high priority.
    # Must run BEFORE sensitive_escalation because phrases like "reserva no funciona"
    # otherwise match the generic real_time_issues rule.
    if _detect_broken_link_complaint(message, state.history):
        reason = "🚨 LINK ROTO reportado por el cliente — revisar URLs"
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.warning(f"[SUPERVISOR] Broken-link complaint detected msg={message[:80]!r}")
        if state.language == "es":
            return (
                "Lamento que el enlace no te haya funcionado. Aviso al equipo para revisarlo y te paso "
                "con un asesor para confirmar el siguiente paso o enviarte el link correcto.\n\n"
                "Enseguida se pone en contacto contigo. ¡Gracias!"
            )
        return (
            "Sorry the link didn't work. I'll let the team know to check it and connect you with a "
            "advisor who can confirm the next step or share the correct link.\n\n"
            "They will get in touch with you shortly. Thanks!"
        )

    sensitive_escalation = detect_sensitive_escalation(message, state.language)
    if sensitive_escalation:
        reason, response = sensitive_escalation
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.info(f"[SUPERVISOR] Sensitive escalation triggered reason={reason}")
        return response

    # Check for menu reset keywords
    if msg_lower in MENU_KEYWORDS:
        state.step = Step.MAIN_MENU
        decision_tree.set_quick_replies(state, "main_menu")
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Menu reset triggered by keyword")
        return MESSAGES["main_menu"][state.language]

    # Step-back: "🔙 Volver" button (value="back") or back keyword
    if msg_lower == "back" or msg_lower in BACK_KEYWORDS:
        logger.info(f"[SUPERVISOR] Back navigation from step={state.step.value}")
        # Cart-flow steps that manage their own back/cancel inline
        if state.step in (
            Step.MIXED_LOCATION,
            Step.MIXED_ADD_ACTIVITY,
            Step.MIXED_ADD_CERT_PLAN,
            Step.MIXED_ADD_QTY,
            Step.MIXED_CERT_LAST_DIVE,
            Step.MIXED_CERT_REFRESH_INTEREST,
            Step.MIXED_CERT_REFRESH_QTY,
            Step.MIXED_CERT_SPLIT_REVIEW,
            Step.MIXED_ADD_PREVIEW,
        ):
            return decision_tree.process_message(state, "back")
        return _go_back_one_step(state)

    # Greeting at any step (except the very first WELCOME) → restart welcome / language selection.
    # We include LANGUAGE here so that a bare "hola" / "hi" at the language step re-shows the
    # welcome screen instead of auto-selecting Spanish (which felt unexpected to users).
    if msg_lower.strip("?!.,;:") in GREETING_ONLY_KEYWORDS and state.step != Step.WELCOME:
        state.step = Step.WELCOME
        state.quick_replies = []
        response = decision_tree.process_message(state, message)
        logger.info(f"[SUPERVISOR] Greeting restart -> step=WELCOME")
        return response

    # Explicit language-switch request ("in english", "spanish please",
    # "me lo puedes decir en español?", etc.) at any step.
    language_intent = _detect_language_intent(message)
    if language_intent is not None:
        from src.flows.decision_tree import MESSAGES
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            # Treat as language selection; advance to MAIN_MENU.
            state.language = language_intent
            state.step = Step.MAIN_MENU
            decision_tree.set_quick_replies(state, "main_menu")
            logger.info(f"[SUPERVISOR] Language intent at start -> lang={language_intent}")
            return MESSAGES["main_menu"][language_intent]
        if state.language != language_intent:
            # Mid-conversation switch: acknowledge in new language and re-show main menu.
            state.language = language_intent
            state.step = Step.MAIN_MENU
            decision_tree.set_quick_replies(state, "main_menu")
            ack = (
                "¡Listo! Sigamos en español. "
                if language_intent == "es"
                else "Got it! Continuing in English. "
            )
            logger.info(f"[SUPERVISOR] Language switch mid-conversation -> lang={language_intent}")
            return ack + MESSAGES["main_menu"][language_intent]

    # If user is in a menu step
    if state.step in MENU_STEPS:
        pending_companion_response = _handle_pending_companion_flow(state, message, msg_lower)
        if pending_companion_response is not None:
            return pending_companion_response

        # Exact button-value match: user sent the raw value of one of the displayed buttons.
        # Handles non-digit values like "6+" that isdigit() would miss.
        raw_msg = message.strip()
        exact_value = next(
            (r.get("value") for r in state.quick_replies if r.get("value") == raw_msg),
            None,
        )
        if exact_value is not None:
            if exact_value == "back":
                logger.info(f"[SUPERVISOR] Back via exact button value from step={state.step.value}")
                return _go_back_one_step(state)
            response = decision_tree.process_message(state, exact_value)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_escalation_reason = reason
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Decision tree (exact button value={exact_value}) -> step={state.step.value}")
            return response

        # If it looks like a menu choice (number), use decision tree
        if msg_lower.isdigit():
            response = decision_tree.process_message(state, message)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_escalation_reason = reason
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Decision tree -> step={state.step.value}")
            return response

        # Free text that clearly matches one of the current quick-reply buttons
        # is treated as if the user clicked that button.
        matched_value = _match_quick_reply_text(state, message)
        if matched_value == "back":
            logger.info(f"[SUPERVISOR] Back via quick-reply text from step={state.step.value}")
            return _go_back_one_step(state)
        if matched_value is not None:
            response = decision_tree.process_message(state, matched_value)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_escalation_reason = reason
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Quick-reply text match value={matched_value} -> step={state.step.value}")
            return response

        if state.step in {
            Step.INFO_TOUR_DETAIL,
            Step.INFO_PACKAGE_DETAIL,
            Step.INFO_COURSE_DETAIL,
            Step.INFO_SPECIALTY_DETAIL,
        } and state.selected_service:
            normalized = _strip_accents(msg_lower)
            if re.search(r"\b(itinerario|itinerary)\b", normalized):
                response = decision_tree.process_message(state, "itinerary")
                logger.info(
                    f"[SUPERVISOR] Decision tree (itinerary keyword) -> step={state.step.value}"
                )
                return response

        if state.step in (Step.WELCOME, Step.LANGUAGE) and _is_substantive_free_text(message):
            state.language = _infer_language(message, state.language)
            state.step = Step.FREE_TEXT
            state.quick_replies = []
            logger.info(f"[SUPERVISOR] RAG (early free text) lang={state.language}")
            state.history.append({"role": "user", "content": message})
            extra_context = _build_extra_context(state)
            answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
            state.history.append({"role": "assistant", "content": answer})
            return answer

        # If it's the welcome/language step and not a real question, use decision tree
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            response = decision_tree.process_message(state, message)
            logger.info(f"[SUPERVISOR] Decision tree (early step) -> step={state.step.value}")
            return response

        mixed_companion_response = _maybe_handle_companion_request_inside_mixed_flow(state, message)
        if mixed_companion_response is not None:
            return mixed_companion_response

        # LLM intent classifier — only inside the cart-style mixed flow.
        # Maps natural-language inputs ("añade otro", "quítalo", "en pesos") to button values.
        if state.step in _MIXED_FLOW_STEPS and state.quick_replies:
            intent = await classify_menu_intent(
                message,
                step_name=state.step.value,
                button_options=list(state.quick_replies),
                lang=state.language,
            )
            if intent == "back":
                logger.info(f"[SUPERVISOR] Intent=back from step={state.step.value}")
                if state.step in (
                    Step.MIXED_LOCATION,
                    Step.MIXED_ADD_ACTIVITY,
                    Step.MIXED_ADD_CERT_PLAN,
                    Step.MIXED_ADD_QTY,
                    Step.MIXED_CERT_LAST_DIVE,
                    Step.MIXED_CERT_REFRESH_INTEREST,
                    Step.MIXED_CERT_REFRESH_QTY,
                    Step.MIXED_CERT_SPLIT_REVIEW,
                    Step.MIXED_ADD_PREVIEW,
                ):
                    return decision_tree.process_message(state, "back")
                return _go_back_one_step(state)
            if intent == "restart":
                logger.info(f"[SUPERVISOR] Intent=restart from step={state.step.value}")
                decision_tree._reset_mixed_state(state)
                state.step = Step.MIXED_ENTRY
                decision_tree.set_quick_replies(state, "mixed_entry")
                from src.flows.decision_tree import MESSAGES as _M
                return _M["mixed_entry"][state.language]
            if intent in ("currency_switch_cop", "currency_switch_usd"):
                target = "COP" if intent == "currency_switch_cop" else "USD"
                state.mixed_display_currency = target
                logger.info(f"[SUPERVISOR] Intent=currency_switch -> {target}")
                # Re-render the final summary if we're already there; otherwise just acknowledge
                if state.step == Step.MIXED_FINAL_SUMMARY:
                    return decision_tree._format_mixed_final_summary(state)
                ack_es = "Listo, te muestro los precios en pesos cuando lleguemos al resumen." if target == "COP" \
                    else "Listo, te muestro los precios en dólares cuando lleguemos al resumen."
                ack_en = "Got it, prices will display in COP at the summary." if target == "COP" \
                    else "Got it, prices will display in USD at the summary."
                return ack_es if state.language == "es" else ack_en
            if intent != "RAG":
                # Resolved to a button value
                response = decision_tree.process_message(state, intent)
                if state.step == Step.ESCALATE and not state.pending_note:
                    reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                    state.pending_escalation_reason = reason
                    state.pending_note = build_lead_summary(state, escalation_reason=reason)
                logger.info(f"[SUPERVISOR] Intent={intent} -> step={state.step.value}")
                return response
            # intent == "RAG" → fall through to RAG below

        deterministic_mixed_response = _maybe_handle_mixed_group_from_menu(state, message)
        if deterministic_mixed_response is not None:
            state.history.append({"role": "user", "content": message})
            state.history.append({"role": "assistant", "content": deterministic_mixed_response})
            return deterministic_mixed_response

        # Free text while in menu -> use RAG but keep menu state
        logger.info(f"[SUPERVISOR] RAG (free text in menu step={state.step.value})")
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        answer = _maybe_offer_mixed_from_single(state, message, answer)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    if state.step == Step.SUMMARY and any(
        getattr(state, attr, False)
        for attr in (
            "mixed_from_single_offer_pending",
            "mixed_from_single_activity_question_pending",
            "mixed_from_single_cert_question_pending",
            "mixed_from_single_last_dive_question_pending",
            "mixed_from_single_refresher_interest_pending",
        )
    ):
        state.step = Step.FREE_TEXT

    # Post-menu steps (SUMMARY, FREE_TEXT) -> summary may still have quick replies (itinerary offer)
    if state.step == Step.SUMMARY:
        matched_value = _match_quick_reply_text(state, message)
        if matched_value == "back":
            logger.info(f"[SUPERVISOR] Back via summary quick-reply from step={state.step.value}")
            return _go_back_one_step(state)
        if matched_value is not None:
            response = decision_tree.process_message(state, matched_value)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Decision tree (summary quick-reply={matched_value}) -> step={state.step.value}")
            return response

        summary_choices = {
            "1",
            "2",
            "si",
            "sí",
            "yes",
            "no",
            "gracias",
            "no gracias",
            "no, gracias",
            "thanks",
            "no thanks",
            "no, thanks",
            "itinerary",
            "skip",
            "ask",
            "done",
            "contact",
            "reservar",
            "book",
        }
        if msg_lower in summary_choices:
            response = decision_tree.process_message(state, message)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Decision tree (summary) -> step={state.step.value}")
            return response

        # Preguntas de estado simples ("que actividad he elegido?", "soy buzo certificado?", etc.)
        introspective = _answer_state_introspection(state, message)
        if introspective is not None:
            logger.info("[SUPERVISOR] State introspection answer (summary)")
            return introspective

        # Free text question after the summary -> use RAG
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        answer = _maybe_offer_mixed_from_single(state, message, answer)
        state.history.append({"role": "assistant", "content": answer})
        logger.info(f"[SUPERVISOR] RAG (post-summary)")
        return answer

    if state.step == Step.FREE_TEXT:
        pending_companion_response = _handle_pending_companion_flow(state, message, msg_lower)
        if pending_companion_response is not None:
            return pending_companion_response

        # Check if user wants to restart the free-text Q&A closing flow.
        if msg_lower in ("1", "si", "sí", "yes"):
            state.quick_replies = []
            if state.language == "es":
                return "Perfecto. ¿Qué te gustaría preguntarme?"
            return "Perfect. What would you like to ask me?"

        if msg_lower in ("2", "no", "gracias", "thanks", "no, gracias", "no, thanks"):
            state.quick_replies = []
            if state.language == "es":
                return (
                    "¡Gracias por contactar a Diving Planet! 🤿\n"
                    "Si necesitas algo más, escribe *menu* para volver al inicio.\n"
                    "¡Te esperamos en las Islas del Rosario!"
                )
            return (
                "Thank you for contacting Diving Planet! 🤿\n"
                "If you need anything else, type *menu* to go back.\n"
                "We look forward to seeing you at the Rosario Islands!"
            )

        if state.selected_service:
            normalized = _strip_accents(msg_lower)
            if re.search(r"\b(itinerario|itinerary)\b", normalized):
                state.step = Step.SUMMARY
                state.summary_mode = "follow_up"
                decision_tree.set_quick_replies(state, decision_tree._summary_quick_replies_key(state))
                itinerary = decision_tree._format_full_itinerary(state)
                if state.language == "es":
                    return itinerary + "\n\n¿Quieres preguntarme algo más?"
                return itinerary + "\n\nWould you like to ask anything else?"

        # Preguntas de estado simples ("que actividad he elegido?", "soy buzo certificado?", etc.)
        introspective = _answer_state_introspection(state, message)
        if introspective is not None:
            logger.info("[SUPERVISOR] State introspection answer (free_text)")
            return introspective

        # Free text question
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        answer = _maybe_offer_mixed_from_single(state, message, answer)
        state.history.append({"role": "assistant", "content": answer})
        logger.info(f"[SUPERVISOR] RAG (post-menu)")
        return answer

    # Escalate step -> let them ask freely via RAG
    if state.step == Step.ESCALATE:
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        answer = _maybe_offer_mixed_from_single(state, message, answer)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Fallback: welcome
    response = decision_tree.process_message(state, message)
    if state.step == Step.ESCALATE and not state.pending_note:
        reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
    return response
