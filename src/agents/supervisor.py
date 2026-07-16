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
from datetime import datetime
from zoneinfo import ZoneInfo

from src.agents import orchestrator
from src.agents.escalation import detect_sensitive_escalation
from src.agents.intent_classifier import classify_menu_intent
from src.agents.intent_detector import IntentDetector
from src.agents.language_detector import detect_language_llm
from src.agents.lead_summary import build_lead_summary
from src.agents.rag_agent import rag_answer
from src.flows import eligibility
from src.flows.decision_tree import (
    MESSAGES as _TREE_MESSAGES,
)
from src.flows.decision_tree import (
    SERVICES,
    ConversationState,
    DecisionTree,
    Step,
    _detect_language_from_text,
)
from src.knowledge.loader import load_policies
from src.privacy import detect_pii, privacy_block_message
from src.utils.fuzzy import is_affirmative, is_negative, word_ratio

logger = logging.getLogger("uvicorn.error")

decision_tree = DecisionTree()
intent_detector = IntentDetector()

# Adaptive diving / DIVE TO HEAL: disability & accessibility questions that must
# be answered with the program's factual info (via RAG) instead of being routed
# into the booking flow. NOT a medical escalation — it's the documented exception.
_ADAPTIVE_DIVING_PATTERN = re.compile(
    r"\b("
    r"dive\s*to\s*heal|buceo\s+adaptado|adaptive\s+diving|"
    r"discapacidad|discapacitad[ao]s?|disabilit(?:y|ies)|disabled|accesibilidad|accessibilit(?:y)|"
    r"s[ií]ndrome\s+de\s+down|down\s+syndrome|autismo|autis(?:m|tic)|"
    r"par[aá]lisis\s+cerebral|cerebral\s+palsy|"
    r"movilidad\s+reducida|reduced\s+mobility|silla\s+de\s+ruedas|wheelchair|"
    r"sord[ao]s?|deaf|cieg[ao]s?|invidente|blind|"
    r"discapacidad\s+(?:visual|auditiva|motora|f[ií]sica|intelectual)"
    r")\b",
    re.IGNORECASE,
)

# Generic "what days / when is there availability" questions. The real
# calendar (exact date + headcount) only exists on the booking link, so we
# never invent a date here — just reassure the client (tours run daily, there
# is availability) and point them to the link's calendar. NOT the same as the
# urgent real_time_issues keywords ("disponible mañana", "hay cupo"...) in
# escalation.py, which still take priority — this check runs after those.
_AVAILABILITY_PATTERN = re.compile(
    r"\b("
    r"qu[ée]\s+d[ií]as?\s+(hay|tienen|disponibles?)|"
    r"d[ií]as?\s+disponibles?|"
    r"fechas?\s+disponibles?|"
    r"qu[ée]\s+fechas?\s+(hay|tienen)|"
    r"disponibilidad\s+de\s+fechas?|"
    r"cu[áa]ndo\s+(hay|puedo|podemos|tienen)\s+\w|"
    r"hay\s+disponibilidad|"
    r"what\s+days|"
    r"which\s+days|"
    r"available\s+dates?|"
    r"what\s+dates?\s+(are|is)|"
    r"any\s+availability|"
    r"is\s+there\s+availability|"
    r"when\s+can\s+(we|i)\s+(go|book)"
    r")\b",
    re.IGNORECASE,
)

# Afirmacion "a secas" ("si", "dale", "ok") — usada para cumplir una oferta que
# el propio bot hizo en el turno anterior (p.ej. "¿te paso con un asesor?").
_BARE_AFFIRMATION_RE = re.compile(
    r"^\s*(s[ií]+|yes|yep|yeah|ok(?:ay)?|dale|claro(?:\s+que\s+s[ií])?|vale|"
    r"por\s+favor|s[ií]\s+por\s+favor|de\s+una|perfecto|me\s+gustar[ií]a|sure|please)"
    r"[\s!.,)]*$",
    re.IGNORECASE,
)
# La oferta del bot que ese "si" acepta: mencion de asesor + verbo de oferta.
_ADVISOR_OFFER_RE = re.compile(r"\b(asesor|advisor|mi jefe|my boss)\b", re.IGNORECASE)
_OFFER_VERB_RE = re.compile(
    r"(te paso|puedo pasarte|te conecto|puedo conectarte|te pongo en contacto|"
    r"pasarte el contacto|te gustar[ií]a|quieres que|connect you|put you in touch|"
    r"pass you the contact|would you like)",
    re.IGNORECASE,
)

# General recommendation / interest queries that have no specific activity keyword.
# "que me recomiendas?", "qué actividades tienen?", "qué ofrecéis?" → route to the
# booking tree (MIXED_ENTRY) so the bot gathers experience/group info instead of
# generating a generic RAG text answer. Only fires outside the cart flow and when
# the cart is empty (mid-flow orchestrator handles these already).
_GENERAL_INTEREST_PATTERN = re.compile(
    r"\b("
    # Recommendation requests (tú/usted/vosotros)
    r"qu[eé]\s+(?:me|nos)\s+recomend\w*|"
    r"qu[eé]\s+(?:me|nos)\s+recomiend\w*|"
    r"qu[eé]\s+recomend\w*|"
    r"qu[eé]\s+recomiend\w*|"
    r"(?:me|nos)\s+recomend\w*\s+algo|"
    # "qué servicios/actividades/opciones/planes tienen/tenéis/hay/ofrecen/hacen/hacéis"
    r"qu[eé]\s+(?:actividades|opciones|planes|servicios|experiencias?)"
    r"\s+(?:tienen|ten[eé]is|hay|ofrecen|hac[eé]is|hacen|ofrecéis|ofreceis)|"
    # "qué hacen/hacéis/ofrecen/ofrecéis [allí/ahí/ustedes]"
    r"qu[eé]\s+(?:hac[eé]is|hacen|ofrecen|ofrecéis|ofreceis)(?:\s+(?:all[ií]|ah[ií]|ustedes))?|"
    # "qué actividades/cosas puedo hacer"
    r"qu[eé]\s+(?:actividades|cosas|experiencias?)\s+puedo\s+(?:hacer|realizar)|"
    r"qu[eé]\s+puedo?\s+(?:hacer|reservar)(?:\s+(?:all[ií]|ah[ií]))?|"
    r"qu[eé]\s+podemos\s+(?:hacer|reservar)|"
    # Generic "qué ofrecen/ofrecéis" family
    r"qu[eé]\s+ofrec[eé]\w*|"
    # English equivalents
    r"what\s+do\s+you\s+(?:recommend|offer|have)|"
    r"what\s+(?:activities|options|services|experiences?)\s+do\s+you\s+(?:have|offer)|"
    r"what\s+(?:can|could)\s+(?:i|we)\s+do|"
    r"any\s+recommendations?|"
    r"what\s+(?:would\s+you\s+)?recommend"
    r")\b",
    re.IGNORECASE,
)

# Question starters used to recognize plain informational questions ("incluye
# comida?", "what's included?") inside the cart-style mixed flow. Real bug this
# guards against: the tool-calling orchestrator (an LLM) occasionally
# misclassified an info question as a cart action — e.g. "Incluye algún
# servicio de comida y bebida" got turned into add_to_cart(companion, 4),
# silently adding 4 bogus companions to the cart. Routing obvious questions
# straight to RAG, before the orchestrator ever sees them, removes that
# failure mode entirely instead of trying to prompt-engineer it away.
_INFO_QUESTION_STARTER_PATTERN = re.compile(
    r"^("
    r"qu[ée]|cu[áa]nto|cu[áa]ndo|c[óo]mo|d[óo]nde|cu[áa]l|"
    r"inclu[yi]e|tiene|tienen|hay|puedo\s+saber|"
    r"what|how|when|where|which|does|is\s+there|are\s+there|do\s+you|can\s+i\s+know"
    r")\b"
)


def _looks_like_info_question(message: str) -> bool:
    """True for plain informational questions ("incluye comida?", "what's
    included?"). Deliberately conservative: only starter words that signal
    "I'm asking for information" (qué/incluye/hay/what/does...), NOT polite
    request phrasing like "puedo añadir..." / "can you remove..." — those are
    real cart actions and must still reach the orchestrator.
    """
    normalized = _strip_accents(message.strip().lower())
    if not normalized:
        return False
    return bool(_INFO_QUESTION_STARTER_PATTERN.match(normalized))


# "¿Cómo reservo?" / "how do I book?" — a question about the booking PROCESS
# rather than about the service itself. Unlike _looks_like_info_question this
# is NOT start-anchored: it must also catch "vale y como reservo" (a filler
# word before the real question), which is exactly the phrasing that exposed
# the gap this guards (owner report 2026-07-16).
_BOOKING_PROCESS_QUESTION_RE = re.compile(
    r"\bc[oó]mo\s+(?:hago\s+(?:para\s+)?|puedo\s+|es\s+(?:el\s+proceso\s+(?:de|para)\s+)?)?reserv[ao]r?\b"
    r"|\bc[oó]mo\s+(?:se\s+)?hace\s+la\s+reserva\b"
    r"|\bhow\s+do\s+i\s+(?:book|reserve)\b"
    r"|\bhow\s+can\s+i\s+(?:book|reserve)\b"
    r"|\bhow\s+to\s+book\b",
    re.IGNORECASE,
)


def _is_booking_process_question(message: str) -> bool:
    normalized = _strip_accents(message.strip().lower())
    if not normalized:
        return False
    return bool(_BOOKING_PROCESS_QUESTION_RE.search(normalized))


def _maybe_answer_how_to_book_with_known_activity(state: ConversationState, message: str) -> str | None:
    """When the customer asks a booking-PROCESS question ("cómo reservo?") at
    a point where we already know exactly which activity/activities they're
    interested in, answer with that activity's own info page directly instead
    of falling through to RAG (whose canned "cómo reservar" answer describes
    the exoneration form + manual 50% payment + advisor confirmation — much
    more friction than needed when we already have a specific service link to
    give).

    Deliberately uses each service's INFO link (web_url), not the BOOKING link
    (booking_url, 10% online): that one still depends on nationality
    (Colombians pay 50/50 via an advisor) which isn't known yet at these
    points. Returns None (fall through to the normal chain) if the message
    isn't this kind of question, or no specific activity is resolved yet.
    """
    if not _is_booking_process_question(message):
        return None

    lang = state.language
    links: list[tuple[str, str]] = []

    if state.step == Step.MIXED_ADD_PREVIEW and state.mixed_pending_preview_service_id:
        service = SERVICES.get(state.mixed_pending_preview_service_id) or {}
        url = service.get("web_url")
        if url:
            label = service.get(f"name_{lang}") or state.mixed_pending_preview_service_id
            links.append((label, url))
    elif state.step == Step.MIXED_CART_REVIEW and state.mixed_cart:
        seen: set[str] = set()
        for item in state.mixed_cart:
            plan = item.get("plan")
            if not plan or plan in seen:
                continue
            service = SERVICES.get(plan) or {}
            url = service.get("web_url")
            if not url:
                continue
            seen.add(plan)
            label = item.get("label") or service.get(f"name_{lang}") or plan
            links.append((label, url))

    if not links:
        return None

    if lang == "es":
        if len(links) == 1:
            label, url = links[0]
            body = f"Ahí tienes toda la información y puedes reservar tu *{label}* directamente:\n{url}"
        else:
            block = "\n".join(f"🔗 {label}: {url}" for label, url in links)
            body = f"Ahí tienes toda la información y puedes reservar cada actividad directamente:\n{block}"
        return (
            f"{body}\n\n¿Tienes alguna otra duda? Aquí estoy para ayudarte. 🐠"
            "\n\nSi tu pregunta era sobre algo más concreto que esto (cancelación, pago, "
            "menores de edad...), cuéntamelo con más detalle y te confirmo con exactitud."
        )

    if len(links) == 1:
        label, url = links[0]
        body = f"There you'll find all the details, and you can book your *{label}* directly:\n{url}"
    else:
        block = "\n".join(f"🔗 {label}: {url}" for label, url in links)
        body = f"There you'll find all the details, and you can book each activity directly:\n{block}"
    return (
        f"{body}\n\nAny other questions? I'm here to help. 🐠"
        "\n\nIf your question was about something more specific than this (cancellation, "
        "payment, minors...), tell me more and I'll confirm the exact details."
    )


# Free-text that RECOMPOSES the group mid-flow: adding a person, or restating a
# new total ("y mi hijo de 12", "se suma mi hermano", "ya seríamos 3", "también
# viene mi esposa"). Deliberately requires an explicit change/addition cue + a
# person noun (or "ya/ahora somos N") so a normal count answer ("somos 3") or a
# location answer starting with "y" ("y desde Cartagena") does NOT trigger it.
_PERSON_NOUN = (
    r"(?:hij[oa]s?|niñ[oa]s?|nin[oa]s?|herman[oa]s?|espos[oa]s?|pareja|marido|mujer|"
    r"amig[oa]s?|suegr[oa]|primo|prima|sobrin[oa]s?|acompañantes?|acompanantes?|"
    r"persona|personas|cuñad[oa]|nietos?|nieta?s?|abuel[oa]s?|pap[aá]|mam[aá]|"
    r"son|daughter|kids?|children|brother|sister|wife|husband|partner|friend)"
)
_GROUP_RECOMPOSE_RE = re.compile(
    r"\bse\s+(?:suma|sumar[oa]n?|a[ñn]ade|agrega|une|unen|apunta|apuntan)\b"
    r"|\b(?:ahora|ya|en realidad|realmente)\s+(?:somos|ser[íi]amos|seremos|vamos)\s+(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b"
    rf"|\btambi[ée]n\s+vien[ea]n?\b"
    rf"|\b(?:y|más|mas|adem[aá]s|tambi[ée]n)\s+(?:(?:mi|mis|otr[oa]s?|un|una|el|la|los|las|nuestr[oa]s?|pequeñ[oa]|mayor|menor)\s+){{1,2}}{_PERSON_NOUN}"
    rf"|\b(?:se\s+nos\s+)?(?:suma|apunta|une)\s+(?:(?:mi|mis|otr[oa]|un|una)\s+){{1,2}}{_PERSON_NOUN}"
    # "se me olvidó (mencionar) mi cuñado" — customer remembers a companion they
    # forgot to count, a natural way of restating the group mid-flow (T008).
    rf"|\bse\s+me\s+(?:olvid[oó]|olvidaba)\b(?:\s+\w+){{0,3}}\s+(?:mi|mis|otr[oa]s?)\s+{_PERSON_NOUN}",
    re.IGNORECASE,
)


def _apply_group_recomposition(message: str, state: ConversationState) -> str | None:
    """If the message adds people / restates the group size mid-flow, capture the
    change (new total and/or new ages) into state and return an acknowledgment
    that keeps the current step's buttons — instead of the step handler answering
    'no te entendí'. Returns None when the message is not a recomposition."""
    if not _GROUP_RECOMPOSE_RE.search(_strip_accents(message)):
        return None

    intent = intent_detector.detect(message, state)
    changed = False

    # New explicit total ("ya seríamos 3", "ahora somos 4").
    m_total = re.search(
        r"\b(?:ahora|ya|en realidad|realmente)\s+(?:somos|ser[íi]amos|seremos|vamos)\s+"
        r"(\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b",
        _strip_accents(message), re.IGNORECASE,
    )
    if m_total:
        n = _GROUP_COUNT_WORDS.get(m_total.group(1), None)
        if n is None and m_total.group(1).isdigit():
            n = int(m_total.group(1))
        if n and n != state.detected_group_size:
            state.detected_group_size = n
            changed = True
    else:
        # A person was added without a new total -> increment by 1 (assume the
        # speaker was at least 1 if the group size wasn't known yet).
        state.detected_group_size = (state.detected_group_size or 1) + 1
        changed = True

    # Merge any newly-mentioned ages.
    if intent.ages:
        merged = sorted(set((state.detected_ages or []) + list(intent.ages)))
        if merged != (state.detected_ages or []):
            state.detected_ages = merged
            changed = True

    if not changed:
        return None

    lang = state.language or "es"
    bits = []
    if state.detected_group_size:
        bits.append(f"ahora sois {state.detected_group_size}" if lang == "es"
                    else f"you're now {state.detected_group_size}")
    if intent.ages:
        edades = ", ".join(str(a) for a in sorted(intent.ages))
        bits.append(f"anoto la(s) edad(es): {edades}" if lang == "es"
                    else f"noting age(s): {edades}")
    detail = "; ".join(bits)
    logger.info(f"[SUPERVISOR] Group recomposition mid-flow -> {detail}")
    if lang == "es":
        return f"¡Anotado! {detail.capitalize()}. Sigamos: elige una de las opciones de abajo 👇"
    return f"Got it! {detail.capitalize()}. Let's continue: pick one of the options below 👇"


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
    # Flujo antiguo eliminado
    Step.COURSES_MENU,
    Step.COURSES_OPEN_WATER_ORIGIN,
    Step.COURSES_OPEN_WATER_TIME,
    Step.COURSES_ADVANCED_MENU,
    Step.COURSES_SPECIALTIES_MENU,
    Step.PRICING_COLOMBIAN,
    Step.MIXED_ENTRY,
    Step.MIXED_LOCATION,
    Step.MIXED_ADD_ACTIVITY,
    Step.MIXED_COMPANION_UPSELL,
    Step.MIXED_ADD_CERT_PLAN,
    Step.MIXED_ADD_CERT_MULTI_DAY,
    Step.MIXED_ADD_QTY,
    Step.MIXED_CERT_LAST_DIVE,
    Step.MIXED_CERT_REFRESH_INTEREST,
    Step.MIXED_CERT_REFRESH_QTY,
    Step.MIXED_CERT_SPLIT_REVIEW,
    Step.MIXED_ADD_PREVIEW,
    Step.MIXED_CART_REVIEW,
    Step.MIXED_CART_MODIFY_PICK,
    Step.MIXED_CART_REMOVE_PICK,
    Step.MIXED_CART_LOCATION,
    Step.MIXED_FINAL_COLOMBIAN,
    Step.MIXED_FINAL_KIDS,
    Step.MIXED_FINAL_PRIVATE,
    Step.MIXED_FINAL_SUMMARY,
    Step.MIXED_ASK_CERTIFICATION,
    Step.MIXED_ASK_CERT_COUNT,
    Step.MIXED_ASK_BEGINNER_ACTIVITY,
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
    Step.MIXED_COMPANION_UPSELL,
    Step.MIXED_ADD_CERT_PLAN,
    Step.MIXED_ADD_CERT_MULTI_DAY,
    Step.MIXED_ADD_QTY,
    Step.MIXED_CERT_LAST_DIVE,
    Step.MIXED_CERT_REFRESH_INTEREST,
    Step.MIXED_CERT_REFRESH_QTY,
    Step.MIXED_CERT_SPLIT_REVIEW,
    Step.MIXED_ADD_PREVIEW,
    Step.MIXED_CART_REVIEW,
    Step.MIXED_CART_MODIFY_PICK,
    Step.MIXED_CART_REMOVE_PICK,
    Step.MIXED_CART_LOCATION,
    Step.MIXED_FINAL_COLOMBIAN,
    Step.MIXED_FINAL_KIDS,
    Step.MIXED_FINAL_KIDS_QTY,
    Step.MIXED_FINAL_KIDS_U8,
    Step.MIXED_FINAL_KIDS_810,
    Step.MIXED_FINAL_PRIVATE,
    Step.MIXED_FINAL_SUMMARY,
    Step.MIXED_ASK_CERTIFICATION,
    Step.MIXED_ASK_CERT_COUNT,
    Step.MIXED_ASK_BEGINNER_ACTIVITY,
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
    # Flujo antiguo eliminado - ahora todo va por el carrito (MIXED_*)
    Step.COURSES_MENU: (Step.MIXED_ADD_ACTIVITY, "mixed_add_activity"),
    Step.COURSES_OPEN_WATER_ORIGIN: (Step.COURSES_MENU, "courses_menu"),
    Step.COURSES_OPEN_WATER_TIME: (Step.MIXED_ADD_QTY, "mixed_quantity"),
    Step.COURSES_ADVANCED_MENU: (Step.COURSES_MENU, "courses_menu"),
    Step.COURSES_SPECIALTIES_MENU: (Step.COURSES_MENU, "courses_menu"),
    # Cart-style mixed flow: most steps loop back to the cart review for "back".
    # MIXED_ENTRY goes back to main menu. Final-question steps are intentionally
    # not back-navigable individually — restart via "empezar de nuevo" if needed.
    Step.MIXED_ENTRY: (Step.MAIN_MENU, "main_menu"),
    Step.MIXED_LOCATION: (Step.MIXED_ENTRY, "mixed_entry"),
    Step.MIXED_ADD_ACTIVITY: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_COMPANION_UPSELL: (Step.MIXED_ADD_ACTIVITY, "mixed_add_activity"),
    Step.MIXED_ADD_CERT_PLAN: (Step.MIXED_ADD_ACTIVITY, "mixed_add_activity"),
    Step.MIXED_ADD_CERT_MULTI_DAY: (Step.MIXED_ADD_CERT_PLAN, "mixed_add_cert_plan"),
    Step.MIXED_ADD_QTY: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_CERT_LAST_DIVE: (Step.MIXED_ADD_QTY, "mixed_quantity"),
    Step.MIXED_CERT_REFRESH_INTEREST: (Step.MIXED_CERT_LAST_DIVE, "certified_last_dive"),
    Step.MIXED_CERT_REFRESH_QTY: (Step.MIXED_CERT_REFRESH_INTEREST, "refresher_interest"),
    Step.MIXED_CERT_SPLIT_REVIEW: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_ADD_PREVIEW: (Step.MIXED_ADD_ACTIVITY, "mixed_add_activity"),
    Step.MIXED_CART_REVIEW: (Step.MAIN_MENU, "main_menu"),
    Step.MIXED_CART_MODIFY_PICK: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_CART_REMOVE_PICK: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_CART_LOCATION: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_FINAL_COLOMBIAN: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
    Step.MIXED_FINAL_KIDS: (Step.MIXED_FINAL_COLOMBIAN, "mixed_yes_no"),
    Step.MIXED_FINAL_KIDS_QTY: (Step.MIXED_FINAL_KIDS, "mixed_kids_age"),
    Step.MIXED_FINAL_KIDS_U8: (Step.MIXED_FINAL_KIDS, "mixed_kids_age"),
    Step.MIXED_FINAL_KIDS_810: (Step.MIXED_FINAL_KIDS, "mixed_kids_age"),
    Step.MIXED_FINAL_PRIVATE: (Step.MIXED_FINAL_COLOMBIAN, "mixed_yes_no"),
    # "Ask" steps reachable directly from free text (IntentDetector jumps),
    # not from a button click in an earlier MIXED_* screen. The handlers'
    # own is_back() logic (routed via the special-case list below) takes
    # precedence; these are just the defensive fallback.
    Step.MIXED_ASK_CERTIFICATION: (Step.MIXED_ENTRY, "mixed_entry"),
    Step.MIXED_ASK_CERT_COUNT: (Step.MIXED_ASK_CERTIFICATION, "mixed_ask_certification"),
    Step.MIXED_ASK_BEGINNER_ACTIVITY: (Step.MIXED_CART_REVIEW, "mixed_cart_actions"),
}

# Keywords that indicate escalation to a human
ESCALATION_KEYWORDS = {
    "humano", "human", "agente", "agent", "asesor", "advisor",
    "hablar con", "speak with", "talk to",
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

# Phrases that indicate the customer wants to cancel an existing booking
# (different from the in-tree "cancelar"/"back" navigation keyword).
CANCEL_BOOKING_PHRASES = {
    # ES — con objeto implícito o explícito
    "cancelar mi reserva", "cancelar la reserva", "cancelar mi tour",
    "cancelar mi cita", "cancelar mi booking", "anular mi reserva",
    "anular la reserva", "anular mi tour", "quiero cancelar mi",
    "necesito cancelar mi", "puedo cancelar mi",
    "quisiera cancelar mi", "quisiera cancelar la",
    "quiero cancelar la", "necesito cancelar la",
    "cancelar el tour", "cancelar el buceo", "cancelar la actividad",
    "cancelar mi pedido", "anular mi pedido",
    # EN — additional common phrasings
    "cancel my booking", "cancel my reservation", "cancel my trip",
    "cancel my tour", "cancel my dive", "i want to cancel my",
    "i need to cancel my", "can i cancel my",
    "i'd like to cancel", "how do i cancel", "how can i cancel",
    "cancel the booking", "cancel the reservation", "cancel the tour",
}

# Phrases that indicate the customer wants to change the date of an
# existing booking (reschedule), as opposed to just asking general
# availability questions.
RESCHEDULE_BOOKING_PHRASES = {
    # ES
    "cambiar la fecha", "cambiar mi fecha", "cambiar de fecha",
    "cambiar fecha de mi reserva", "cambiar la fecha de mi reserva",
    "reprogramar mi reserva", "reprogramar mi tour", "reprogramar mi cita",
    "mover mi reserva", "mover la fecha",
    "quisiera cambiar la fecha", "quisiera cambiar mi fecha",
    "quiero cambiar la fecha", "necesito cambiar la fecha",
    "puedo cambiar la fecha", "como cambio la fecha",
    "cambiar el dia", "cambiar mi dia", "cambiar la cita",
    "posponer mi reserva", "postergar mi reserva",
    # EN — additional common phrasings
    "change my date", "change the date", "reschedule my booking",
    "reschedule my reservation", "reschedule my trip", "move my booking",
    "move my reservation",
    "i'd like to reschedule", "how do i reschedule", "how can i change",
    "change my booking date", "change my reservation date",
    "postpone my booking", "postpone my reservation",
}


def _detect_cancellation_request(msg_lower: str) -> bool:
    # Accent-insensitive so "cancelar mi reservación" also matches the
    # accent-free phrases; CANCEL_BOOKING_PHRASES are stored without accents.
    normalized = _strip_accents(msg_lower)
    return any(phrase in normalized for phrase in CANCEL_BOOKING_PHRASES)


def _detect_reschedule_request(msg_lower: str) -> bool:
    normalized = _strip_accents(msg_lower)
    return any(phrase in normalized for phrase in RESCHEDULE_BOOKING_PHRASES)


# A group where NOT everyone shares the same nationality (some Colombian/
# resident, some foreign) — pricing/currency is set per-conversation
# (state.is_colombian), so this is a real gap: not implemented as a feature
# (T013 in docs/test-battery-edge-cases.md). Detect the contradiction
# explicitly instead of letting it fall through to a generic RAG fallback.
_MIXED_NATIONALITY_RE = re.compile(
    r"\bmi\s+(?:amig[oa]|parej[ao]|espos[oa]|hij[oa]|herman[oa]|novi[oa])\s+es\s+extranjer[oa]\b"
    r"|\bmi\s+(?:amig[oa]|parej[ao]|espos[oa]|hij[oa]|herman[oa]|novi[oa])\s+es\s+colombian[oa]\b"
    r"|\b(?:unos?|algunos?)\s+(?:somos\s+|son\s+)?colombian[oa]s?\s+y\s+(?:otros?|l[oa]s?\s+demas)\s+extranjer[oa]s?\b"
    r"|\bnacionalidad\s+mixta\b"
    r"|\bparte\s+del\s+grupo\s+es\s+extranjer[oa]\b"
    r"|\bsolo\s+yo\s+soy\s+(?:colombian[oa]|extranjer[oa])\b"
    r"|\bmy\s+(?:friend|partner|husband|wife|brother|sister|boyfriend|girlfriend)\s+is\s+(?:a\s+)?foreign(?:er)?\b"
    r"|\bmy\s+(?:friend|partner|husband|wife|brother|sister|boyfriend|girlfriend)\s+is\s+colombian\b"
    r"|\bonly\s+i\s*(?:'m| am)\s+colombian\b"
    r"|\bmixed\s+nationalit(?:y|ies)\b",
    re.IGNORECASE,
)


def _detect_mixed_nationality_request(msg_lower: str) -> bool:
    return bool(_MIXED_NATIONALITY_RE.search(_strip_accents(msg_lower)))


def _booking_change_buttons(lang: str) -> list[dict]:
    if lang == "es":
        return [
            {"title": "🧑‍💬 Hablar con un asesor", "value": "asesor"},
            {"title": "🏠 Menú principal", "value": "inicio"},
        ]
    return [
        {"title": "🧑‍💬 Talk to an advisor", "value": "asesor"},
        {"title": "🏠 Main menu", "value": "inicio"},
    ]


# Verbs the LLM uses when offering to hand the user off ("te paso con un asesor",
# "contactes a un asesor", "connect you with an advisor"...). The exact phrasing
# varies run to run, so we anchor on advisor-noun + offer-verb + a question
# rather than fixed phrases.
_ADVISOR_OFFER_VERBS = (
    "pasar", "pase ", "paso ", "pasart", "contact", "conect", "hablar",
    "connect", "speak", "reach out", "put you in touch", "get you in touch",
)


def _answer_offers_advisor(answer: str) -> bool:
    """True if a free-text answer offers to hand the user to an advisor, so the
    reply can carry matching 'advisor / home' buttons instead of the generic
    main-menu ones (e.g. contact-only courses like Divemaster).

    Robust to the LLM's varying wording: requires the advisor noun, a question,
    and an offer verb — not one fixed phrase.
    """
    a = (answer or "").lower()
    if "asesor" not in a and "advisor" not in a:
        return False
    if "?" not in a:
        return False
    return any(v in a for v in _ADVISOR_OFFER_VERBS)


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

    Also splits number+companion-noun concatenations like "3amigos" or
    "sieteamigos" so the downstream count/intent regexes (which expect a space)
    can find both parts.
    """
    cleaned = _strip_accents(text.strip().lower())
    cleaned = re.sub(r"[¿¡?!.,;:()\[\]\"'/\\]", " ", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Split "3amigos" / "tresamigos" → "3 amigos" / "tres amigos" so person-count
    # parsing (which requires whitespace between the count and the noun) works.
    cleaned = re.sub(
        r"\b(?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)(amig[oa]s?|person[ao]s?|companer[oa]s?|hij[oa]s?|herman[oa]s?|acompanantes?)\b",
        lambda m: m.group(0)[: -len(m.group(1))] + " " + m.group(1),
        cleaned,
    )
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
        # "mis 2 hijos" / "mis dos hermanos" / "mis tres amigos" — número en medio.
        r"\bmis\s+(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+(hij[oa]s|herman[oa]s|amig[oa]s|companer[oa]s|acompanantes)\b",
        # "sieteamigos" / "6amigos" — número pegado a la palabra compañero sin espacio.
        r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)amig[oa]s?\b",
        r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)person[ao]s?\b",
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
        # Incluye typos comunes (snorke, buseo, etc.).
        r"\b(el|ella)\s+(el|la|los|las)\s+(snorkel|snorke|snorkl|esnorquel|esnorkel|minicurso|buceo|buseo|curso)\b",
        # "ella solo snorkel" / "él solamente buceo" (adverbio entre pronombre y
        # actividad), incluyendo typos comunes.
        r"\b(el|ella)\s+(solo|solamente)\s+(snorkel|snorke|snorkl|esnorquel|esnorkel|minicurso|buceo|buseo)\b",
        # Elipsis pura: "yo X y ella snorkel" / "yo X pero él buceo" (pronombre +
        # actividad sin nada en medio). Anclado al conector y/pero anterior para
        # evitar el falso positivo "el snorkel es divertido" (artículo + sustantivo).
        r"\b(?:y|pero)\s+(el|ella)\s+(snorkel|snorke|snorkl|esnorquel|esnorkel|esnorke|esnokel|minicurso|buceo|buseo)\b",
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


def _detect_kids_mention(message: str) -> bool:
    """Detect mentions of kids/children/family in free text.

    Stricter than companion intent: only matches words that clearly imply minors
    (hijo, niño, menor, kid, child, sobrino, familia con hijos/niños). Excludes
    generic companion words (amigo, pareja, esposo) — those don't justify asking
    age ranges. Used to disparar la pregunta de edad en el cart-mixto cuando no
    haya minicurso ni snorkel pero el cliente sí trae niños.
    """
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return False
    tokens = set(normalized.split())

    kids_keywords = {
        "hijo", "hija", "hijos", "hijas",
        "nino", "nina", "ninos", "ninas",
        "menor", "menores",
        "sobrino", "sobrina", "sobrinos", "sobrinas",
        "kid", "kids", "child", "children",
    }
    if tokens & kids_keywords:
        return True

    kids_patterns = (
        r"\bmi\s+(hij[oa]|sobrin[oa]|nin[oa])\b",
        r"\bmis\s+(hij[oa]s|sobrin[oa]s|nin[oa]s)\b",
        r"\bmi\s+familia\s+con\s+(hij[oa]s|nin[oa]s|menores)\b",
        r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+(hij[oa]s|nin[oa]s|sobrin[oa]s|menores)\b",
    )
    return any(re.search(pattern, normalized) for pattern in kids_patterns)


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
        # Typos comunes
        "buseo",
        "buseando",
        "bucearr",
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
        # Typos comunes (truncamientos / variantes ortográficas)
        "snorke",
        "snorkl",
        "esnorkel",
        "esnorke",
        "esnokel",
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
    normalized_base_id = _normalize_base_service_id(base_id)
    if normalized_base_id == "snorkeling":
        return "snorkeling"
    if normalized_base_id == "minicourse":
        return "minicourse"
    service = SERVICES.get(base_id or "") or SERVICES.get(normalized_base_id or "") or {}
    if bool(service.get("requires_cert")) and service.get("category") in {"tour", "package"}:
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
        r"\bel\s+(el|la|los|las)\s+(snorkel|snorke|snorkl|esnorquel|esnorkel|minicurso|buceo|buseo|curso)\b",
        r"\bel\s+(solo|solamente)\s+(snorkel|snorke|snorkl|esnorquel|esnorkel|minicurso|buceo|buseo)\b",
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
        service_id = allocation.get("service_id")
        if not activity or not isinstance(qty, int) or qty <= 0:
            continue
        existing = next(
            (
                item for item in merged
                if item["activity"] == activity and item.get("service_id") == service_id
            ),
            None,
        )
        if existing is not None:
            existing["qty"] += qty
        else:
            merged_item = {"activity": activity, "qty": qty}
            if service_id:
                merged_item["service_id"] = service_id
            merged.append(merged_item)
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


def _build_group_context_from_activity(
    activity: str,
    companion_count: int = 1,
    total_people: int | None = None,
    service_id: str | None = None,
) -> dict:
    qty = companion_count if companion_count > 0 else 1
    allocation = {"activity": activity, "qty": qty}
    if service_id:
        allocation["service_id"] = service_id
    return {
        "total_people": total_people,
        "speaker_activity": None,
        "companion_count": qty,
        "allocations": [allocation],
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
        return _build_group_context_from_activity(
            "snorkeling",
            default_companion_count or 1,
            default_total_people,
            _preferred_service_id_for_activity(base_id, "snorkeling"),
        )
    if normalized == "2":
        return _build_group_context_from_activity(
            "minicourse",
            default_companion_count or 1,
            default_total_people,
            _preferred_service_id_for_activity(base_id, "minicourse"),
        )
    if normalized == "3":
        return _build_group_context_from_activity(
            "diving",
            default_companion_count or 1,
            default_total_people,
            _preferred_service_id_for_activity(base_id, "diving"),
        )

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
        _preferred_service_id_for_activity(base_id, activity_answer),
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
    service = SERVICES.get(actual_base_id) or {}
    category = service.get("category")
    requires_cert = bool(service.get("requires_cert"))
    if lang == "es":
        if actual_base_id == "snorkeling":
            my_activity = "tu reserva de snorkel"
        elif actual_base_id == "2_dives_1_day":
            my_activity = "tu reserva de buceo"
        elif actual_base_id == "minicourse":
            my_activity = "tu minicurso de buceo"
        elif category == "course":
            my_activity = "tu curso PADI"
        elif requires_cert:
            my_activity = "tu plan de buceo certificado"
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

    if actual_base_id == "snorkeling":
        my_activity = "your snorkeling booking"
    elif actual_base_id == "2_dives_1_day":
        my_activity = "your diving booking"
    elif actual_base_id == "minicourse":
        my_activity = "your beginner diving mini-course"
    elif category == "course":
        my_activity = "your PADI course"
    elif requires_cert:
        my_activity = "your certified diving plan"
    else:
        my_activity = "your current activity"
    follow_up = (
        f"If you want, I can add {my_activity} to a *mixed group* booking (cart), "
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
        prompt = f"Para recomendar bien el plan a las {diving_qty} personas que quieren bucear, ¿son *buzos certificados*?"
        quick_replies = [
            {"title": "1️⃣ Sí, todos están certificados", "value": "1"},
            {"title": "2️⃣ No, todos primera vez (minicurso)", "value": "2"},
            {"title": "3️⃣ Algunos sí, algunos no", "value": "3"},
        ]
        return prompt, quick_replies

    prompt = "¿Tu amigo es *buzo certificado*?"
    quick_replies = [
        {"title": "1️⃣ Sí, está certificado", "value": "1"},
        {"title": "2️⃣ No, sería su primera vez", "value": "2"},
    ]
    return prompt, quick_replies


def _build_mixed_from_single_cert_split_question(diving_qty: int) -> tuple[str, list[dict]]:
    """Para el caso 'algunos sí, algunos no': preguntar cuántos están certificados.

    Para diving_qty=2 hay un único reparto posible (1+1) — el caller no debería
    llegar aquí. Para diving_qty>=3 genera N-1 botones (1 cert, 2 cert, ...,
    diving_qty-1 cert).
    """
    if diving_qty < 3:
        # Caso degenerado: solo hay un split posible, el caller lo procesa directo.
        return "", []
    lines = [
        "Perfecto. ¿Cuántos de los que quieren bucear están certificados?",
        "Los demás los apuntamos al minicurso de iniciación:",
        "",
    ]
    quick_replies: list[dict] = []
    for cert_count in range(1, diving_qty):
        mini_count = diving_qty - cert_count
        cert_word = "certificado" if cert_count == 1 else "certificados"
        mini_word = "minicurso" if mini_count == 1 else "minicursos"
        title = f"{cert_count} {cert_word} + {mini_count} {mini_word}"
        lines.append(f"{cert_count}️⃣ {title}")
        quick_replies.append({"title": f"{cert_count}️⃣ {title}", "value": str(cert_count)})
    return "\n".join(lines), quick_replies


def _split_diving_for_mixed_cert(group_context: dict, cert_count: int) -> dict:
    """Divide la qty 'diving' en cert_count (queda diving) + resto (pasa a minicourse)."""
    new_allocs: list[dict] = []
    for alloc in group_context.get("allocations", []):
        if alloc.get("activity") == "diving":
            total_qty = alloc.get("qty", 0)
            mini_count = max(total_qty - cert_count, 0)
            service_id = alloc.get("service_id")
            if cert_count > 0:
                cert_alloc = {"activity": "diving", "qty": cert_count}
                if service_id:
                    cert_alloc["service_id"] = service_id
                new_allocs.append(cert_alloc)
            if mini_count > 0:
                new_allocs.append({"activity": "minicourse", "qty": mini_count})
        else:
            new_allocs.append(alloc)
    result = dict(group_context)
    result["allocations"] = _merge_group_allocations(new_allocs)
    result["companion_count"] = sum(item["qty"] for item in result["allocations"])
    result["needs_activity_clarification"] = False
    return result


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

    if normalized == "1" or is_affirmative(normalized):
        return True
    if normalized == "2" or is_negative(normalized):
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
    if normalized == "1" or is_affirmative(normalized):
        return True
    if normalized == "2" or is_negative(normalized):
        return False
    return None


def _render_service_info_card_for_current_location(state: ConversationState, service_id: str, compact: bool = False) -> str:
    info_state = ConversationState(conversation_id=state.conversation_id)
    info_state.language = state.language
    info_state.location = state.location
    info_state.selected_service = decision_tree._service_for_location(service_id, state)
    return decision_tree._format_info_card(info_state, compact=compact)


def _set_mixed_from_single_group_context(state: ConversationState, group_context: dict | None) -> None:
    setattr(state, "mixed_from_single_group_context", group_context)


def _get_mixed_from_single_group_context(state: ConversationState) -> dict | None:
    group_context = getattr(state, "mixed_from_single_group_context", None)
    return group_context if isinstance(group_context, dict) else None


def _clear_mixed_from_single_group_context(state: ConversationState) -> None:
    setattr(state, "mixed_from_single_group_context", None)


def _preferred_service_id_for_activity(base_id: str | None, activity: str | None) -> str | None:
    if not base_id or not activity:
        return None
    if _base_service_to_activity_intent(base_id) != activity:
        return None
    return base_id


def _activity_to_service_id(activity: str, preferred_service_id: str | None = None) -> str | None:
    if preferred_service_id:
        mapped = _map_service_to_cart_item(preferred_service_id)
        if mapped is not None:
            mapped_type, mapped_plan = mapped
            if activity == "snorkeling" and mapped_type == "snorkel":
                return preferred_service_id
            if activity == "minicourse" and mapped_type == "beginner":
                return preferred_service_id
            if activity == "diving" and mapped_type == "cert":
                return mapped_plan
    if activity == "snorkeling":
        return "snorkeling"
    if activity == "minicourse":
        return "minicourse"
    if activity == "diving":
        return "2_dives_1_day"
    return None


def _activity_to_cart_item(activity: str, preferred_service_id: str | None = None) -> tuple[str, str | None] | None:
    if preferred_service_id:
        mapped = _map_service_to_cart_item(preferred_service_id)
        if mapped is not None:
            mapped_type, mapped_plan = mapped
            if activity == "snorkeling" and mapped_type == "snorkel":
                return mapped
            if activity == "minicourse" and mapped_type == "beginner":
                return mapped
            if activity == "diving" and mapped_type == "cert":
                return mapped_type, mapped_plan
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
    if item_type == "cert" and plan:
        return plan
    if item_type == "course" and plan:
        return plan
    return None


def _infer_companion_base_service_id(state: ConversationState) -> str | None:
    selected_service = getattr(state, "selected_service", None)
    if _map_service_to_cart_item(selected_service or "") is not None:
        return selected_service

    if decision_tree._is_in_mixed_flow(state) and len(getattr(state, "mixed_cart", [])) == 1:
        inferred = _cart_item_to_service_id(state.mixed_cart[0])
        return inferred
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
    diving_qty_total = 0
    if group_context:
        for allocation in group_context.get("allocations", []):
            activity = allocation.get("activity")
            qty = allocation.get("qty")
            service_id = allocation.get("service_id")
            if not activity or not isinstance(qty, int):
                continue
            cart_item = _activity_to_cart_item(activity, service_id)
            if cart_item is None:
                continue
            item_type, plan = cart_item
            _append_mixed_cart_item(state, item_type, plan, qty)
            if activity == "diving":
                diving_qty_total += qty
        if group_context.get("refresher_interested") and diving_qty_total > 0:
            refresher_qty = group_context.get("refresher_qty") or diving_qty_total
            refresher_qty = min(refresher_qty, diving_qty_total)
            if refresher_qty > 0:
                _append_mixed_cart_item(state, "refresh", None, refresher_qty)
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
        return "You can book a mixed group without a problem."

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

    return f"¡Claro! {plan_line}"


def _render_group_info_cards(state: ConversationState, allocations: list[dict]) -> str:
    if not allocations:
        return ""
    if len(allocations) == 1:
        service_id = _activity_to_service_id(allocations[0]["activity"], allocations[0].get("service_id"))
        return _render_service_info_card_for_current_location(state, service_id) if service_id else ""

    sections: list[str] = []
    for allocation in allocations:
        service_id = _activity_to_service_id(allocation["activity"], allocation.get("service_id"))
        if not service_id:
            continue
        sections.append(
            _build_group_allocations_summary_line(allocation["activity"], allocation["qty"], state.language)
            + "\n"
            + _render_service_info_card_for_current_location(state, service_id, compact=True)
        )
    separator = "\n\n─────────────────────────\n\n"
    return separator.join(section for section in sections if section)


def _resolve_group_certification(group_context: dict, cert_answer: bool) -> dict:
    resolved_allocations: list[dict] = []
    for allocation in group_context.get("allocations", []):
        activity = allocation.get("activity")
        qty = allocation.get("qty")
        service_id = allocation.get("service_id")
        if not isinstance(qty, int) or qty <= 0 or not activity:
            continue
        if activity == "diving" and not cert_answer:
            resolved_allocations.append({"activity": "minicourse", "qty": qty})
        else:
            resolved_allocation = {"activity": activity, "qty": qty}
            if service_id:
                resolved_allocation["service_id"] = service_id
            resolved_allocations.append(resolved_allocation)

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

    # Texto adaptado al companion (tercera persona) para que quede claro de quién
    # se está preguntando. No empezamos con "Perfecto." porque el caller
    # frecuentemente ya añade contexto previo.
    if lang == "es":
        if diving_qty > 1:
            return (
                "Antes de confirmar el plan, necesito saber una cosa sobre esas personas:\n\n"
                "¿Han pasado *más de 2 años* desde su última inmersión?\n\n"
                "Si es así, les recomendamos hacer un *refresher* antes de la salida."
            )
        return (
            "Antes de confirmar el plan, necesito saber una cosa sobre tu acompañante:\n\n"
            "¿Han pasado *más de 2 años* desde su última inmersión?\n\n"
            "Si es así, le recomendamos hacer un *refresher* antes de la salida."
        )
    if diving_qty > 1:
        return (
            "Before I confirm the plan, I need to know one thing about those people:\n\n"
            "Has it been *more than 2 years* since their last dive?\n\n"
            "If so, we recommend a *refresher* before the trip."
        )
    return (
        "Before I confirm the plan, I need to know one thing about your companion:\n\n"
        "Has it been *more than 2 years* since their last dive?\n\n"
        "If so, we recommend a *refresher* before the trip."
    )


def _build_companion_refresher_qty_prompt(state: ConversationState, diving_qty: int) -> tuple[str, list[dict]]:
    lang = getattr(state, "language", "es") or "es"
    if lang == "es":
        prompt = (
            f"¿Cuántas de las {diving_qty} personas quieren hacer el *refresher*?\n"
            "_(Sin coste adicional — el guía adapta la inmersión a su nivel)_"
        )
    else:
        prompt = (
            f"How many of the {diving_qty} people want to do the *refresher*?\n"
            "_(No extra cost — the guide adapts the dive to their level)_"
        )
    quick_replies = [
        {"title": f"{n}", "value": str(n)} for n in range(1, diving_qty + 1)
    ]
    return prompt, quick_replies


def _build_companion_refresher_prompt(state: ConversationState, diving_qty: int = 1) -> str:
    lang = getattr(state, "language", "es") or "es"
    decision_tree.set_quick_replies(state, "refresher_interest")
    if lang == "es":
        if diving_qty > 1:
            return (
                "Les recomendamos un *refresher* antes de salir al mar — un repaso rápido para volver al agua con confianza:\n\n"
                "✅ Repaso de teoría (señales, equipo y procedimientos)\n"
                "🏊 Práctica en piscina\n"
                "🤿 1 buceo en el mar con instructor\n\n"
                "⚠️ No es el minicurso de principiantes — está pensado para *buzos ya certificados* que quieren actualizarse.\n\n"
                "¿Quieres incluirlo en su plan?"
            )
        return (
            "Le recomendamos un *refresher* antes de salir al mar — un repaso rápido para volver al agua con confianza:\n\n"
            "✅ Repaso de teoría (señales, equipo y procedimientos)\n"
            "🏊 Práctica en piscina\n"
            "🤿 1 buceo en el mar con instructor\n\n"
            "⚠️ No es el minicurso de principiantes — está pensado para *buzos ya certificados* que quieren actualizarse.\n\n"
            "¿Quieres incluirlo en su plan?"
        )
    target = "they" if diving_qty > 1 else "they"
    return (
        f"We recommend a *refresher* before going out to sea — a quick review to help {target} get back in the water with confidence:\n\n"
        "✅ Theory review (signals, gear, procedures)\n"
        "🏊 Pool practice\n"
        "🤿 1 open-water dive with an instructor\n\n"
        "⚠️ This is not the beginner course — it's designed for *already-certified divers* who want to brush up.\n\n"
        "Would you like to include it in their plan?"
    )


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


def _show_group_activity_cards(state: ConversationState, base_id: str | None, group_context: dict, skip_intro: bool = False) -> str:
    """Build the response with the info card(s) + follow-up offer.

    `skip_intro=True` lets the caller suppress the standard "¡Claro! Pueden ir
    juntos…" line when it has already provided its own context message
    (e.g. the cert-no path that says "Si no todos están certificados…").
    """
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
    if skip_intro:
        return f"{info_cards}\n\n{follow_up}" if info_cards else follow_up
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
        return _build_group_context_from_activity(
            activity_intent,
            service_id=_preferred_service_id_for_activity(base_id, activity_intent),
        )

    if parsed_group_context.get("allocations"):
        return parsed_group_context

    companion_count = parsed_group_context.get("companion_count") or 1
    total_people = parsed_group_context.get("total_people")
    return _build_group_context_from_activity(
        activity_intent,
        companion_count,
        total_people,
        _preferred_service_id_for_activity(base_id, activity_intent),
    )


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
    target_activity = _base_service_to_activity_intent(target_service_id) or "snorkeling"
    _set_mixed_from_single_group_context(
        state,
        _build_group_context_from_activity(target_activity, service_id=_preferred_service_id_for_activity(target_service_id, target_activity)),
    )
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
        _build_group_context_from_activity(
            activity_intent,
            service_id=_preferred_service_id_for_activity(base_id, activity_intent),
        ),
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

    service = SERVICES.get(service_id) or SERVICES.get(base_id) or {}
    category = service.get("category")
    requires_cert = bool(service.get("requires_cert"))

    if base_id == "snorkeling":
        return "snorkel", None
    if base_id == "minicourse":
        return "beginner", None
    if category == "course":
        return "course", service_id
    if requires_cert and category in {"tour", "package"}:
        return "cert", service_id
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
        state.step = Step.MIXED_ENTRY
        decision_tree._reset_mixed_state(state)
        state.mixed_entry_path = "booking"
        decision_tree._set_back_target(state, Step.MAIN_MENU, "main_menu")
        decision_tree.set_quick_replies(state, "mixed_entry")
        from src.flows.decision_tree import MESSAGES as _M

        lang = getattr(state, "language", "es") or "es"
        return _M["mixed_entry"][lang]

    item_type, plan = item

    # Reset cart-style state and enter via the diving+snorkel entry path.
    decision_tree._reset_mixed_state(state)
    state.mixed_entry_path = "diving_snorkel"

    # Preload 1× of the current activity for the main user.
    _append_mixed_cart_item(state, item_type, plan, 1)
    # If the speaker already confirmed a refresher in the single-activity flow,
    # carry it into the mixed cart so it shows in the final summary.
    speaker_refresher = bool(getattr(state, "refresher_interested", False)) and item_type == "cert"

    group_context = _get_mixed_from_single_group_context(state)
    diving_qty_total = 1 if item_type == "cert" else 0
    companion_diving_qty = 0
    if group_context:
        for allocation in group_context.get("allocations", []):
            activity = allocation.get("activity")
            qty = allocation.get("qty")
            service_id = allocation.get("service_id")
            if not activity or not isinstance(qty, int):
                continue
            cart_item = _activity_to_cart_item(activity, service_id)
            if cart_item is None:
                continue
            companion_item_type, companion_plan = cart_item
            _append_mixed_cart_item(state, companion_item_type, companion_plan, qty)
            if activity == "diving":
                companion_diving_qty += qty
                diving_qty_total += qty
        # If companions confirmed refresher for the certified subgroup, use the
        # explicit refresher_qty when set (collected via qty question for 2+);
        # otherwise default to the companion diving qty.
        companion_refresher_qty = 0
        if group_context.get("refresher_interested") and companion_diving_qty > 0:
            companion_refresher_qty = group_context.get("refresher_qty") or companion_diving_qty
            companion_refresher_qty = min(companion_refresher_qty, companion_diving_qty)
    else:
        companion_refresher_qty = 0

    total_refresher_qty = (1 if speaker_refresher else 0) + companion_refresher_qty
    if total_refresher_qty > 0:
        _append_mixed_cart_item(state, "refresh", None, total_refresher_qty)

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
            # No service selected yet. If companion+activity intent detected, offer mixed group routing.
            lang = getattr(state, "language", "es") or "es"
            if _detect_companion_intent(message, state) and (
                _mentions_diving_intent(message)
                or _mentions_snorkeling_intent(message)
                or _mentions_minicourse_intent(message)
            ):
                decision_tree._reset_mixed_state(state)
                state.mixed_entry_path = "booking"
                decision_tree._set_back_target(state, Step.MAIN_MENU, "main_menu")
                state.step = Step.MIXED_ENTRY
                decision_tree.set_quick_replies(state, "mixed_entry")
                if lang == "es":
                    return (
                        "¡Claro! Para organizar el plan de todo el grupo, "
                        "vamos a armar el carrito paso a paso.\n\n"
                        + decision_tree.MESSAGES["mixed_entry"]["es"]
                    )
                return (
                    "Sure! To plan for the whole group, tell me: "
                    "let's build the booking cart step by step.\n\n"
                    + decision_tree.MESSAGES["mixed_entry"]["en"]
                )
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

        if lang == "es":
            parsed_group_context = _build_companion_group_context(message, svc_id)
            group_context = _coerce_group_context_with_activity_intent(message, svc_id, parsed_group_context)
            if group_context is not None:
                return _handle_companion_group_context(state, svc_id, lang, group_context)

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
    if state.step not in {Step.MAIN_MENU, Step.RESERVA_MENU}:
        return None
    if not _detect_companion_intent(message, state):
        return None

    group_context = _extract_menu_mixed_group_context(message)
    if not group_context:
        return None

    decision_tree._reset_mixed_state(state)
    state.mixed_entry_path = "booking"
    decision_tree._set_back_target(state, Step.MAIN_MENU, "main_menu")
    state.step = Step.MIXED_ENTRY
    decision_tree.set_quick_replies(state, "mixed_entry")
    from src.flows.decision_tree import MESSAGES
    intro = _build_menu_mixed_group_offer_text(state, group_context)
    return f"{intro}\n\n{MESSAGES['mixed_entry'][state.language]}"


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
            "mixed_from_single_cert_split_question_pending",
            "mixed_from_single_last_dive_question_pending",
            "mixed_from_single_refresher_interest_pending",
            "mixed_from_single_refresher_qty_pending",
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

        # NUEVO: respuesta "mixto" (botón 3 o palabras 'mezcla'/'algunos').
        normalized_msg = _normalize_for_menu_match(message)
        is_mixed_answer = (
            msg_lower == "3"
            or "algunos si algunos no" in normalized_msg
            or "algunos certificados" in normalized_msg
            or "mezcla" in normalized_msg
            or "mixto" in normalized_msg
        )
        if is_mixed_answer and diving_qty >= 2:
            setattr(state, "mixed_from_single_cert_question_pending", False)
            if diving_qty == 2:
                # Único split posible: 1 cert + 1 minicurso. Procesa directo.
                cert_count = 1
                updated_context = _split_diving_for_mixed_cert(current_group_context, cert_count)
                _set_mixed_from_single_group_context(state, updated_context)
                setattr(state, "mixed_from_single_last_dive_question_pending", True)
                return (
                    "Perfecto. Entonces el certificado hace buceo y el otro hace minicurso de iniciación.\n\n"
                    + _build_companion_last_dive_question(state, cert_count)
                )
            # Para 3+ personas, preguntamos cuántos certificados (botones N-1).
            prompt, quick_replies = _build_mixed_from_single_cert_split_question(diving_qty)
            setattr(state, "mixed_from_single_cert_split_question_pending", True)
            state.quick_replies = quick_replies
            return prompt

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
        # Cert-no path: el caller añade su propia intro explicativa, así que
        # suprimimos la intro estándar para no duplicar el "¡Claro!".
        response = _show_group_activity_cards(state, base_id, resolved_group_context, skip_intro=True)
        intro = (
            "Perfecto. Como no todos están certificados, le ofrecemos a ese grupo el minicurso de iniciación:"
            if diving_qty > 1 else
            "Perfecto. Como no está certificado, le ofrecemos empezar con el minicurso de iniciación:"
        )
        return f"{intro}\n\n{response}"

    # NUEVO: pregunta de reparto cuando el usuario eligió "algunos sí, algunos no" para grupos 3+.
    if getattr(state, "mixed_from_single_cert_split_question_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or _build_group_context_from_activity("diving")
        diving_qty = sum(
            item["qty"]
            for item in current_group_context.get("allocations", [])
            if item.get("activity") == "diving"
        ) or 1
        try:
            cert_count = int(message.strip())
        except (ValueError, TypeError):
            cert_count = None
        if cert_count is None or cert_count < 1 or cert_count >= diving_qty:
            prompt, quick_replies = _build_mixed_from_single_cert_split_question(diving_qty)
            state.quick_replies = quick_replies
            return f"No te entendí del todo.\n\n{prompt}"

        setattr(state, "mixed_from_single_cert_split_question_pending", False)
        updated_context = _split_diving_for_mixed_cert(current_group_context, cert_count)
        _set_mixed_from_single_group_context(state, updated_context)
        mini_count = diving_qty - cert_count
        setattr(state, "mixed_from_single_last_dive_question_pending", True)
        return (
            f"Perfecto. {cert_count} hace{'n' if cert_count > 1 else ''} buceo certificado "
            f"y {mini_count} hace{'n' if mini_count > 1 else ''} minicurso de iniciación.\n\n"
            + _build_companion_last_dive_question(state, cert_count)
        )

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
            return _build_companion_refresher_prompt(state, diving_qty)
        return _show_group_activity_cards(state, base_id, updated_group_context)

    if getattr(state, "mixed_from_single_refresher_interest_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or _build_group_context_from_activity("diving")
        diving_qty = sum(
            item["qty"]
            for item in current_group_context.get("allocations", [])
            if item.get("activity") == "diving"
        ) or 1
        refresher_interested = _detect_binary_yes_no_answer(message)
        if refresher_interested is None:
            return "No te entendí del todo.\n\n" + _build_companion_refresher_prompt(state, diving_qty)

        setattr(state, "mixed_from_single_refresher_interest_pending", False)
        updated_group_context = dict(current_group_context)
        updated_group_context["refresher_interested"] = refresher_interested
        _set_mixed_from_single_group_context(state, updated_group_context)
        if refresher_interested:
            # For 2+ certified divers, ask how many of them want the refresher.
            if diving_qty > 1:
                setattr(state, "mixed_from_single_refresher_qty_pending", True)
                prompt, quick_replies = _build_companion_refresher_qty_prompt(state, diving_qty)
                state.quick_replies = quick_replies
                return prompt
            # diving_qty == 1: auto-assign 1.
            updated_group_context["refresher_qty"] = 1
            _set_mixed_from_single_group_context(state, updated_group_context)
            note = (
                "✅ *Refresher añadido* — el asesor lo coordina al confirmar la reserva (sin coste adicional)."
                if state.language == "es"
                else "✅ *Refresher added* — the advisor coordinates it when confirming the booking (no extra cost)."
            )
            cards = _show_group_activity_cards(state, base_id, updated_group_context, skip_intro=True)
            return f"{note}\n\n{cards}"
        cards = _show_group_activity_cards(state, base_id, updated_group_context)
        return cards

    if getattr(state, "mixed_from_single_refresher_qty_pending", False):
        current_group_context = _get_mixed_from_single_group_context(state) or _build_group_context_from_activity("diving")
        diving_qty = sum(
            item["qty"]
            for item in current_group_context.get("allocations", [])
            if item.get("activity") == "diving"
        ) or 1
        try:
            refresher_qty = int(message.strip())
        except (ValueError, TypeError):
            refresher_qty = None
        if refresher_qty is None or refresher_qty < 1 or refresher_qty > diving_qty:
            prompt, quick_replies = _build_companion_refresher_qty_prompt(state, diving_qty)
            state.quick_replies = quick_replies
            return "No te entendí del todo.\n\n" + prompt

        setattr(state, "mixed_from_single_refresher_qty_pending", False)
        updated_group_context = dict(current_group_context)
        updated_group_context["refresher_qty"] = refresher_qty
        _set_mixed_from_single_group_context(state, updated_group_context)
        person_word_es = "persona" if refresher_qty == 1 else "personas"
        person_word_en = "person" if refresher_qty == 1 else "people"
        note = (
            f"✅ *Refresher añadido para {refresher_qty} {person_word_es}* — el asesor lo coordina al confirmar la reserva (sin coste adicional)."
            if state.language == "es"
            else f"✅ *Refresher added for {refresher_qty} {person_word_en}* — the advisor coordinates it when confirming the booking (no extra cost)."
        )
        cards = _show_group_activity_cards(state, base_id, updated_group_context, skip_intro=True)
        return f"{note}\n\n{cards}"

    if getattr(state, "mixed_from_single_offer_pending", False):
        if msg_lower in {"1", "si", "sí", "yes"}:
            setattr(state, "mixed_from_single_offer_pending", False)
            setattr(state, "mixed_from_single_companion_context_active", False)
            setattr(state, "mixed_from_single_activity_question_pending", False)
            setattr(state, "mixed_from_single_cert_question_pending", False)
            setattr(state, "mixed_from_single_cert_split_question_pending", False)
            setattr(state, "mixed_from_single_last_dive_question_pending", False)
            setattr(state, "mixed_from_single_refresher_interest_pending", False)
            setattr(state, "mixed_from_single_refresher_qty_pending", False)
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
            setattr(state, "mixed_from_single_cert_split_question_pending", False)
            setattr(state, "mixed_from_single_last_dive_question_pending", False)
            setattr(state, "mixed_from_single_refresher_interest_pending", False)
            setattr(state, "mixed_from_single_refresher_qty_pending", False)
            if decision_tree._is_in_mixed_flow(state):
                _clear_mixed_from_single_group_context(state)
                state.quick_replies = []
                return decision_tree._goto_mixed_cart_review(state)
            _clear_mixed_from_single_group_context(state)
            # Devolvemos al cliente al SUMMARY en modo follow_up con sus botones
            # (Reservar, Preguntar, Volver al menú) para que no se quede sin opciones.
            state.step = Step.SUMMARY
            state.summary_mode = "follow_up"
            decision_tree.set_quick_replies(state, decision_tree._summary_quick_replies_key(state))
            if state.language == "es":
                return (
                    "Perfecto, mantenemos solo tu actividad. "
                    "¿Quieres reservarla ya, preguntar algo más o volver al menú?"
                )
            return (
                "Perfect, we'll keep only your activity. "
                "Would you like to book it now, ask anything else, or go back to the menu?"
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
        matched = len(common)
        # Fuzzy fallback per word: catches single-word typos that have zero
        # exact overlap (e.g. "snorlkel" vs button "🤿 Snorkel").
        remaining_title_words = sig_title - common
        for uw in sig_msg - common:
            for tw in remaining_title_words:
                if word_ratio(uw, tw) >= 0.80:
                    matched += 1
                    remaining_title_words.discard(tw)
                    break
        if matched == 0:
            continue
        score = matched / max(len(sig_msg), 1)
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

    Called before EVERY rag_answer(...) in this file — no matter where in the
    tree the free-text question was asked, the LLM gets everything we already
    know about the client so it never re-asks or contradicts it:
    - Idioma de la conversacion
    - Ubicacion (Cartagena / isla / hotel)
    - Actividad activa: seleccionada en el arbol O en previsualizacion del
      carrito sin confirmar, con su "incluye"/"no incluye" real (ground truth,
      no depende de que la busqueda vectorial acierte el chunk)
    - Si es buzo certificado, colombiano, inactivo >2 anios, interes en refresher
    - Tamano de grupo (detectado o pendiente de confirmar), duracion (1 dia vs
      varios), menores de edad ya contabilizados, lancha privada
    - Carrito actual completo, con ground truth de incluye/no incluye por item
    - Paso actual del flujo guiado
    """

    parts: list[str] = []

    # Fecha/hora real (Colombia) — sin esto el LLM no tiene forma de saber si
    # un corte de horario ("cierra a las 4:30 PM del día anterior") ya pasó o
    # no, y termina inventando urgencia/cierre que no puede verificar.
    now = datetime.now(ZoneInfo("America/Bogota"))
    if state.language == "es":
        parts.append(
            f"Fecha y hora actual: {now.strftime('%Y-%m-%d %H:%M')} (hora de Cartagena/Colombia)."
        )
    else:
        parts.append(
            f"Current date and time: {now.strftime('%Y-%m-%d %H:%M')} (Cartagena/Colombia time)."
        )

    # Idioma actual de la conversación
    if state.language == "es":
        parts.append("La conversación se esta llevando a cabo en español.")
    elif state.language == "en":
        parts.append("The conversation is currently happening in English.")

    # Datos que el cliente ya dio en lenguaje natural (presupuesto, días, edades,
    # experiencia, preferencias). Inyectados para que el bot NUNCA los ignore ni
    # los repregunte.
    facts = state.remembered_facts or {}
    if facts:
        _fact_labels = {
            "budget": ("Presupuesto mencionado", "Budget mentioned"),
            "days": ("Días disponibles", "Days available"),
            "child_ages": ("Edades de menores", "Ages of minors"),
            "experience_level": ("Experiencia", "Experience"),
            "preference": ("Preferencia/preocupación", "Preference/concern"),
        }
        idx = 0 if state.language == "es" else 1
        lines = [
            f"{_fact_labels.get(k, (k, k))[idx]}: {v}"
            for k, v in facts.items() if v
        ]
        if lines:
            header = (
                "El cliente ya ha dicho lo siguiente (tenlo en cuenta, no lo repreguntes): "
                if state.language == "es"
                else "The customer already told us the following (use it, don't re-ask): "
            )
            parts.append(header + "; ".join(lines) + ".")

    # Ubicacion base
    if state.location == "cartagena":
        if state.language == "es":
            parts.append(
                "El cliente indica que saldra desde Cartagena para su experiencia. "
                "Si pregunta por punto de encuentro, recogida u horarios, responde SOLO "
                "con la informacion de salida desde Cartagena (Muelle de la Bodeguita); "
                "no menciones la opcion de recogida en hotel/islas salvo que el cliente "
                "pregunte explicitamente por ese caso."
            )
        else:
            parts.append(
                "The customer is departing from Cartagena for their experience. "
                "If they ask about the meeting point, pickup, or schedule, answer ONLY "
                "with the Cartagena departure info (Muelle de la Bodeguita); do not "
                "mention the hotel/island pickup option unless they explicitly ask about it."
            )
    elif state.location == "island":
        if state.language == "es":
            parts.append(
                "El cliente indica que ya esta en las Islas del Rosario. "
                "Si pregunta por punto de encuentro, recogida u horarios, responde SOLO "
                "con la informacion de recogida en hotel/isla; no menciones la salida "
                "desde el Muelle de la Bodeguita en Cartagena salvo que el cliente "
                "pregunte explicitamente por ese caso."
            )
        else:
            parts.append(
                "The customer is already on the Rosario Islands. If they ask about the "
                "meeting point, pickup, or schedule, answer ONLY with the hotel/island "
                "pickup info; do not mention the Cartagena Muelle de la Bodeguita "
                "departure unless they explicitly ask about it."
            )

    # Isla / hotel
    if getattr(state, "island", None):
        parts.append(f"Se hospeda (o se hospedara) en la isla: {state.island}.")
    if getattr(state, "hotel", None):
        parts.append(f"Hotel/alojamiento reportado: {state.hotel}.")

    # Actividad seleccionada
    if getattr(state, "selected_service", None):
        try:
            from src.flows.decision_tree import MULTI_DAY_SERVICES, SERVICES

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

    # Ground truth de la actividad activa (seleccionada en el arbol O en
    # previsualizacion del carrito sin confirmar aun) — inyecta directamente
    # que incluye/no incluye para que preguntas como "tengo que llevar equipo?"
    # o "esta el seguro incluido?" no dependan de que la busqueda vectorial
    # encuentre el chunk correcto del servicio.
    active_service_id = (
        getattr(state, "mixed_pending_preview_service_id", None)
        # Set as soon as the client picks a specific cert/course plan (e.g.
        # "Paquete multi-dia" -> "5 buceos"), well before the final preview
        # card — without this, questions asked mid cert-plan sub-flow (last
        # dive question, refresher interest/qty) had no service context.
        or getattr(state, "mixed_pending_qty_plan", None)
        or getattr(state, "selected_service", None)
    )
    if active_service_id:
        try:
            from src.flows.decision_tree import SERVICES

            active_service = SERVICES.get(active_service_id)
            if active_service:
                name = active_service.get(f"name_{state.language}", active_service_id)
                includes = active_service.get(f"includes_{state.language}")
                not_included = active_service.get(f"not_included_{state.language}") or []
                if state.language == "es":
                    parts.append(f"Actividad que el cliente esta viendo/considerando ahora: {name}.")
                    if includes:
                        parts.append(f"Esta actividad SI incluye: {includes}.")
                    if not_included:
                        parts.append(f"Esta actividad NO incluye: {', '.join(not_included)}.")
                    parts.append(
                        "Usa esta lista como fuente de verdad para preguntas de equipo, seguro o "
                        "que incluye/no incluye; no necesitas buscar en otra parte."
                    )
                else:
                    parts.append(f"Activity the customer is currently viewing/considering: {name}.")
                    if includes:
                        parts.append(f"This activity DOES include: {includes}.")
                    if not_included:
                        parts.append(f"This activity does NOT include: {', '.join(not_included)}.")
                    parts.append(
                        "Use this list as the source of truth for equipment, insurance, or "
                        "what's included/not included questions; no need to search elsewhere."
                    )
        except Exception:
            pass

    # Buzo certificado / principiante
    if getattr(state, "is_certified", None) is True:
        parts.append("El cliente marco que es buzo certificado (solo buzos certificados en el grupo).")
    elif getattr(state, "is_certified", None) is False:
        parts.append("El cliente marco que no es buzo certificado o que viene como principiante/snorkel.")

    # Colombiano o no
    if getattr(state, "is_colombian", None) is True:
        parts.append("El cliente indico que es colombiano/a (mostrar precios en COP, no hay descuento especial por ser colombiano).")
    elif getattr(state, "is_colombian", None) is False:
        parts.append("El cliente indico que no es colombiano/a (mostrar precios en USD).")

    # Inactividad y refresher
    if getattr(state, "last_dive_over_2_years", None) is True:
        parts.append("Segun el arbol, lleva mas de 2 años sin bucear.")
    elif getattr(state, "last_dive_over_2_years", None) is False:
        parts.append("Segun el arbol, su ultima inmersión fue hace menos de 2 años.")

    if getattr(state, "refresher_interested", None) is True:
        parts.append("En el flujo marco que SI le interesa incluir un refresher.")
    elif getattr(state, "refresher_interested", None) is False:
        parts.append("En el flujo marco que NO le interesa incluir un refresher.")

    # Tamano de grupo ya conocido (detectado en texto libre o pendiente de
    # confirmar cantidad) — para que el LLM no pida "cuantos son" si el
    # cliente ya lo dijo en otro punto de la conversacion.
    group_size = getattr(state, "detected_group_size", None) or getattr(state, "mixed_pending_qty_value", None)
    if group_size:
        if state.language == "es":
            parts.append(f"El cliente ya indico que son {group_size} persona(s) en total.")
        else:
            parts.append(f"The customer already said there are {group_size} people in total.")

    # Duracion detectada (un dia vs varios dias)
    duration = getattr(state, "detected_duration", None)
    if duration == "single_day":
        parts.append(
            "El cliente indico que estara solo un dia." if state.language == "es"
            else "The customer indicated they will be there for a single day."
        )
    elif duration == "multi_day":
        parts.append(
            "El cliente indico que estara varios dias." if state.language == "es"
            else "The customer indicated they will be there for multiple days."
        )

    # Edades concretas mencionadas -> ground truth de elegibilidad por edad.
    # Sin esto, un mensaje que solo trae edades ("familia con hijos de 5, 8,
    # 11 y 15") no recupera nada util del KB y cae al fallback generico,
    # aunque el motor determinista de eligibility.py sepa exactamente que
    # puede hacer cada uno.
    mentioned_ages = sorted({a for a in (state.detected_ages or []) if 1 <= a <= 17})
    if mentioned_ages:
        notes = " ".join(
            eligibility.age_eligibility_note(a, state.language or "es")
            for a in mentioned_ages
        )
        header = (
            "Edades de menores mencionadas y qué puede hacer cada uno (datos exactos, úsalos): "
            if state.language == "es"
            else "Ages of minors mentioned and what each can do (exact facts, use them): "
        )
        parts.append(header + notes)

    # Menores de edad ya contabilizados en el grupo
    kids_u8 = getattr(state, "kids_under_8_count", 0) or 0
    kids_8_10 = getattr(state, "kids_eight_to_ten_count", 0) or 0
    if kids_u8 or kids_8_10:
        if state.language == "es":
            parts.append(
                f"En el grupo ya se contabilizaron {kids_u8} menor(es) de 8 años "
                f"y {kids_8_10} de 8 a 10 años. No vuelvas a preguntar por edades de niños. "
                "Regla de edades (fuente de verdad): los menores de 8 años SOLO pueden hacer "
                "snorkel (edad minima 6 años), no pueden bucear. De 8 a 10 años: programa "
                "Bubble Makers — sesion especializada de buceo en piscina y aguas poco "
                "profundas (maximo 2 metros de profundidad) con un instructor PADI dedicado, "
                "es la forma en que los niños de esa edad si pueden iniciarse en el buceo de "
                "forma segura. Desde los 10 años: minicurso de buceo normal y cursos PADI."
            )
        else:
            parts.append(
                f"The group already accounts for {kids_u8} child(ren) under 8 and "
                f"{kids_8_10} aged 8-10. Do not ask about kids' ages again. "
                "Age rule (source of truth): children under 8 can ONLY do snorkeling "
                "(minimum age 6), they cannot dive. Ages 8 to 10: Bubble Makers program — "
                "a specialized dive session in a pool or very shallow water (max 2 meters "
                "deep) with a dedicated PADI instructor; that's how kids that age can safely "
                "start diving. From age 10: the regular dive mini-course and PADI courses."
            )

    # Lancha privada
    if getattr(state, "mixed_final_wants_private", None) is True:
        parts.append(
            "El cliente ya solicito lancha privada para el grupo." if state.language == "es"
            else "The customer already requested a private boat for the group."
        )
    elif getattr(state, "mixed_final_wants_private", None) is False:
        parts.append(
            "El cliente indico que NO quiere lancha privada." if state.language == "es"
            else "The customer indicated they do NOT want a private boat."
        )

    # Carrito actual (clave para no preguntar cosas que el cliente ya eligio)
    cart = getattr(state, "mixed_cart", None) or []
    if cart:
        items = ", ".join(
            f"{it.get('qty', 0)} x {it.get('label') or it.get('type', '')}" for it in cart
        )
        if state.language == "es":
            parts.append(
                f"El cliente YA tiene estas actividades en su carrito: {items}. "
                "No vuelvas a preguntar por estas actividades; tenlas en cuenta como contexto. "
                "Cuando hables de equipo, seguro u otros detalles de la actividad, usa el "
                "mismo termino que tiene en el carrito (buceo, snorkel o minicurso) sin "
                "mezclarlo con otra actividad — por ejemplo, si el carrito tiene snorkel, "
                "habla de 'equipo de snorkel', no de 'equipo de buceo'."
            )
        else:
            parts.append(
                f"The customer ALREADY has these activities in their cart: {items}. "
                "Do not ask again about these activities; treat them as known context. "
                "When talking about equipment, insurance, or other activity details, use "
                "the SAME term as the cart item (diving, snorkeling, or mini-course) — do "
                "not mix it with another activity (e.g. if the cart has snorkeling, say "
                "'snorkeling gear', not 'diving gear')."
            )

        # Ground truth de incluye/no incluye por cada tipo de actividad distinto
        # en el carrito — mismo motivo que para la previsualizacion: evita que
        # la respuesta dependa de que la busqueda vectorial acierte el chunk.
        try:
            from src.flows.decision_tree import SERVICES

            seen_service_ids: set[str] = set()
            for item in cart:
                cart_service_id = decision_tree._cart_service_id(
                    item.get("type"), item.get("plan"), state
                )
                if not cart_service_id or cart_service_id in seen_service_ids:
                    continue
                seen_service_ids.add(cart_service_id)
                cart_service = SERVICES.get(cart_service_id)
                if not cart_service:
                    continue
                name = cart_service.get(f"name_{state.language}", cart_service_id)
                includes = cart_service.get(f"includes_{state.language}")
                not_included = cart_service.get(f"not_included_{state.language}") or []
                if state.language == "es":
                    if includes:
                        parts.append(f"'{name}' SI incluye: {includes}.")
                    if not_included:
                        parts.append(f"'{name}' NO incluye: {', '.join(not_included)}.")
                else:
                    if includes:
                        parts.append(f"'{name}' DOES include: {includes}.")
                    if not_included:
                        parts.append(f"'{name}' does NOT include: {', '.join(not_included)}.")
        except Exception:
            pass

    # Paso actual del flujo guiado (para que el LLM sepa que esta esperando el bot)
    step_value = getattr(getattr(state, "step", None), "value", None)
    if step_value:
        if state.language == "es":
            parts.append(f"Paso actual del flujo guiado: {step_value}.")
        else:
            parts.append(f"Current guided-flow step: {step_value}.")

    if not parts:
        return None
    return " ".join(parts)


# Cues that turn an age mention into an eligibility QUESTION we should answer
# from the rules ("puede bucear?", "hay edad mínima?", "can my son dive?").
_AGE_ELIGIBILITY_CUE = re.compile(
    r"(edad\s+m[ií]nima|edad\s+minima|minimum\s+age|hay\s+(?:una\s+)?edad|"
    r"a\s+partir\s+de\s+qu[eé]\s+edad|desde\s+qu[eé]\s+edad|"
    r"\bpued[eo](?:n|s)?\b|\bpodemos\b|\bpodr[íi]a[n]?\b|se\s+puede|es\s+posible|"
    r"\bcan\s+(?:my|he|she|they|the|a|i|we|kids?|children)\b|"
    r"\bis\s+it\s+possible|old\s+enough|too\s+young|"
    r"dejan?\s+(?:bucear|entrar)|permit|allowed|"
    # options / what-can-they-do questions (valuable when a minor is involved)
    r"qu[eé]\s+opciones|qu[eé]\s+(?:actividad(?:es)?|plan(?:es)?)|"
    r"qu[eé]\s+(?:puede[n]?|podemos|pueden)\s+hacer|"
    r"what\s+(?:can|activities|options)|which\s+activities)",
    re.IGNORECASE,
)


def _maybe_answer_age_eligibility(message: str, state: ConversationState) -> str | None:
    """Deterministic answer to an age-eligibility question.

    Fires only when the message both mentions a concrete age and reads like an
    eligibility question, so it never hijacks a plain booking phrase like
    "reservar para mi hijo de 14". Returns None otherwise.
    """
    if not _AGE_ELIGIBILITY_CUE.search(message):
        return None
    intent = intent_detector.detect(message, state)
    ages = sorted({a for a in (intent.ages or []) if 1 <= a <= 99})
    # Persist any age mentioned here so a later follow-up can reuse it (this
    # responder returns before the conversation agent's _apply_detected_intent).
    if ages:
        state.detected_ages = sorted(set((state.detected_ages or []) + ages))
    # Multi-turn: if this message has no age but refers to a specific person
    # ("pero mi hijo puede bucear?" after "mi hijo tiene 9 años"), reuse the
    # remembered age. Guarded by a person reference so a bare "¿puede bucear?"
    # is not answered with a stale age.
    if not ages and re.search(
        r"\b(mi\s+\w+|hij[oa]s?|niñ[oa]s?|nin[oa]s?|él|ella|ellos|ellas|"
        r"my\s+\w+|son|daughter|kids?|child(?:ren)?|he|she|they)\b",
        message, re.IGNORECASE,
    ):
        ages = sorted({a for a in (state.detected_ages or []) if 1 <= a <= 99})
    if not ages:
        return None
    lang = state.language or "es"

    if len(ages) >= 2:
        # Several people -> a clear per-person plan (who can do what), using any
        # detected certified count so the divers appear in the breakdown too.
        alloc = intent.group_allocation or state.detected_group_allocation or {}
        certified = int(alloc.get("certified_diving", 0) or 0)
        plans = eligibility.plan_group(certified=certified, noncert_ages=ages)
        header = ("¡Con gusto! Esto es lo que puede hacer cada quien: 🐠\n"
                  if lang == "es" else
                  "Happy to help! Here's what each person can do: 🐠\n")
        body = header + eligibility.format_group_plan(plans, lang)
    else:
        # Single person -> the fuller, warmer eligibility note.
        body = eligibility.age_eligibility_note(ages[0], lang)

    if lang == "es":
        outro = (
            "\n\n¿Quieres que te ayude a armar el plan para tu grupo? "
            "Escribe *reservar* o cuéntame qué actividad les interesa. 🐠"
            "\n\nSi además preguntabas por algo más concreto, cuéntamelo con más detalle "
            "y te confirmo con exactitud."
        )
    else:
        outro = (
            "\n\nWant me to help put together the plan for your group? "
            "Type *book* or tell me which activity you're interested in. 🐠"
            "\n\nIf you were also asking about something more specific, tell me more "
            "and I'll confirm the exact details."
        )
    # Stay conversational: leave the welcome/language step so a later reply isn't
    # misread, but don't force menu buttons.
    if state.step in (Step.WELCOME, Step.LANGUAGE):
        state.step = Step.MAIN_MENU
    state.quick_replies = []
    return body + outro


def _maybe_build_pending_note(state: ConversationState) -> None:
    """Build the lead note after a tree call, either via a real escalation or
    a silent note (e.g. a booking link was sent directly, no handoff needed)."""
    if state.step == Step.ESCALATE and not state.pending_note:
        reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
    elif state.pending_lead_note_reason and not state.pending_note:
        state.pending_note = build_lead_summary(state, escalation_reason=state.pending_lead_note_reason)
        state.pending_lead_note_reason = None


def _finalize_tree_response(state: ConversationState, message: str, response: str) -> str:
    """Persist a tool-driven turn in history and fill the lead note if we escalated."""
    state.history.append({"role": "user", "content": message})
    state.history.append({"role": "assistant", "content": response})
    _maybe_build_pending_note(state)
    return response


# Map the `remember` tool's activity enum to the internal detected_activity naming.
_REMEMBER_ACTIVITY_MAP = {
    "certified": "certified_diving",
    "beginner": "minicourse",
    "snorkel": "snorkel",
    "course": "padi_course",
    "padi_course": "padi_course",
}


def _persist_remembered(state: ConversationState, remembered: dict | None) -> None:
    """Write facts the customer volunteered onto state so the bot never re-asks
    them. Hard slots go to the fields the tree consumes; soft facts (budget,
    ages, days, experience, preferences) go to `remembered_facts` for context."""
    if not remembered:
        return
    facts = state.remembered_facts if state.remembered_facts is not None else {}

    gs = remembered.get("group_size")
    if isinstance(gs, int) and gs > 0 and not state.detected_group_size:
        state.detected_group_size = gs

    isc = remembered.get("is_certified")
    if isinstance(isc, bool):
        if state.is_certified is None:
            state.is_certified = isc
        state.detected_is_certified = isc

    cc = remembered.get("certified_count")
    bc = remembered.get("beginner_count")
    sc = remembered.get("snorkel_count")
    if any(isinstance(v, int) and v > 0 for v in (cc, bc, sc)):
        alloc: dict = {}
        if isinstance(cc, int) and cc > 0:
            alloc["certified_diving"] = cc
        if isinstance(bc, int) and bc > 0:
            alloc["minicourse"] = bc
        if isinstance(sc, int) and sc > 0:
            alloc["snorkel"] = sc
        if alloc and not state.detected_group_allocation:
            state.detected_group_allocation = alloc

    activity = remembered.get("activity")
    if activity and activity != "unspecified" and not state.detected_activity:
        state.detected_activity = _REMEMBER_ACTIVITY_MAP.get(activity, state.detected_activity)

    loc = remembered.get("location")
    if loc in ("cartagena", "island"):
        state.detected_location = loc
        if not state.location:
            state.location = loc

    # "island" is NOT a declared property of the `remember` tool schema (only
    # "hotel" is) — but the model occasionally invents that key anyway for a
    # hotel/place name mentioned alongside a location change (T011 in
    # docs/test-battery-edge-cases.md). Accept it as a fallback so the value
    # isn't silently dropped.
    hotel = remembered.get("hotel") or remembered.get("island")
    if hotel:
        state.hotel = str(hotel).strip()

    for key in ("experience_level", "child_ages", "budget", "days", "preference"):
        val = remembered.get(key)
        if val not in (None, "", []):
            facts[key] = str(val)
    state.remembered_facts = facts


async def _dispatch_orchestrator(state: ConversationState, message: str) -> str | None:
    """Fase 2 — tool-calling orchestrator for free text inside the cart flow.

    Returns the rendered response when the orchestrator chose a concrete tree
    action, or None to let the caller fall back (legacy intent classifier / RAG).
    """
    snapshot = _build_extra_context(state)
    decision = await orchestrator.orchestrate(
        message,
        state_snapshot=snapshot,
        history=state.history,
        lang=state.language,
    )
    _persist_remembered(state, decision.remembered)
    return await _apply_orchestrator_decision(state, message, decision)


async def _apply_orchestrator_decision(
    state: ConversationState, message: str, decision
) -> str | None:
    """Execute an orchestrator decision against the tree. Returns the rendered
    response, or None for answer_question / profile-only updates (the caller then
    produces the reply via RAG)."""
    tool = decision.tool
    args = decision.args or {}

    # Informational question -> let the caller route to RAG.
    if tool == orchestrator.TOOL_ANSWER_QUESTION:
        return None

    if tool == orchestrator.TOOL_SET_LOCATION:
        origin = args.get("origin")
        response = decision_tree.orchestrator_set_location(state, origin)
        if response is None:
            return None
        logger.info(f"[SUPERVISOR] Orchestrator set_location({origin}) -> step={state.step.value}")
        return _finalize_tree_response(state, message, response)

    if tool == orchestrator.TOOL_REMOVE_ITEM:
        cart_type = orchestrator.ACTIVITY_TO_CART_TYPE.get(args.get("activity", ""))
        if not cart_type:
            return None
        response = decision_tree.orchestrator_remove_activity(state, cart_type)
        if response is None:
            # Nothing of that type in the cart — acknowledge + re-show the cart.
            not_there = (
                "No tenías esa actividad en el carrito."
                if state.language == "es"
                else "You didn't have that activity in the cart."
            )
            response = not_there + "\n\n" + decision_tree._goto_mixed_cart_review(state)
        logger.info(f"[SUPERVISOR] Orchestrator remove_item({cart_type}) -> step={state.step.value}")
        return _finalize_tree_response(state, message, response)

    if tool == orchestrator.TOOL_START_BOOKING:
        cart_type = orchestrator.ACTIVITY_TO_CART_TYPE.get(args.get("activity", ""))
        if not cart_type:
            return None
        response = decision_tree.orchestrator_start_activity(state, cart_type)
        if response is None:
            return None
        logger.info(f"[SUPERVISOR] Orchestrator start_booking({cart_type}) -> step={state.step.value}")
        return _finalize_tree_response(state, message, response)

    if tool == orchestrator.TOOL_ADD_TO_CART:
        cart_type = orchestrator.ACTIVITY_TO_CART_TYPE.get(args.get("activity", ""))
        qty = args.get("qty")
        if not cart_type or not isinstance(qty, int):
            return None
        response = decision_tree.orchestrator_add_to_cart(state, cart_type, qty)
        if response is None:
            return None
        logger.info(f"[SUPERVISOR] Orchestrator add_to_cart({cart_type}, {qty}) -> step={state.step.value}")
        return _finalize_tree_response(state, message, response)

    if tool == orchestrator.TOOL_CART_ACTION:
        action = args.get("action")
        value_map = {
            "change_origin": "1",
            "add": "2",
            "modify": "3",
            "remove": "4",
            "restart": "5",
            "confirm": "6",
        }
        value = value_map.get(action)
        if value is None:
            return None
        # Cart-level actions are resolved by the review handler.
        state.step = Step.MIXED_CART_REVIEW
        state.quick_replies = []
        response = decision_tree._route(state, value)
        logger.info(f"[SUPERVISOR] Orchestrator cart_action({action}) -> step={state.step.value}")
        return _finalize_tree_response(state, message, response)

    if tool == orchestrator.TOOL_SET_PROFILE:
        field = args.get("field")
        value = args.get("value")
        if isinstance(value, bool):
            if field == "certified":
                state.is_certified = value
            elif field == "colombian":
                state.is_colombian = value
                state.mixed_final_is_colombian = value
            elif field == "refresher":
                state.refresher_interested = value
            logger.info(f"[SUPERVISOR] Orchestrator set_profile({field}={value})")
        # Let the conversational reply come from RAG with the updated context.
        return None

    if tool == orchestrator.TOOL_NOTE_LOGISTICS:
        if args.get("hotel"):
            state.hotel = str(args["hotel"]).strip()
        if args.get("island"):
            state.island = str(args["island"]).strip()
        logger.info(f"[SUPERVISOR] Orchestrator note_logistics hotel={state.hotel!r} island={state.island!r}")
        return None

    if tool == orchestrator.TOOL_ESCALATE:
        reason = args.get("reason") or "derivado por el orquestador"
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Orchestrator escalate reason={reason}")
        return _finalize_tree_response(state, message, MESSAGES["escalate"][state.language])

    return None


# Tools the conversation agent may use at ENTRY steps (no cart yet, so no
# cart_action / remove_item). `remember` + answer_question are always included.
_ENTRY_ACTIONS = {
    orchestrator.TOOL_SET_LOCATION,
    orchestrator.TOOL_START_BOOKING,
    orchestrator.TOOL_ADD_TO_CART,
    orchestrator.TOOL_SET_PROFILE,
    orchestrator.TOOL_NOTE_LOGISTICS,
    orchestrator.TOOL_ESCALATE,
    orchestrator.TOOL_ANSWER_QUESTION,
    orchestrator.TOOL_REMEMBER,
}
# Any of these means "the customer wants to proceed with a booking" -> reuse the
# deterministic booking entry (which pre-fills group splits and skips re-asks).
_ENTRY_BOOKING_TOOLS = {
    orchestrator.TOOL_SET_LOCATION,
    orchestrator.TOOL_START_BOOKING,
    orchestrator.TOOL_ADD_TO_CART,
}


async def _dispatch_conversation_agent(state: ConversationState, message: str) -> str:
    """Understanding-first entry handler for substantive free text at non-cart
    steps. The LLM decides answer/book/escalate and remembers what the customer
    said; questions are answered (RAG), bookings reuse the deterministic entry
    pre-filled from the detected + remembered slots. Always returns a reply."""
    # Fresh conversation: infer language from the first substantive message so the
    # agent (and RAG) reply in the customer's language instead of the default.
    if state.step in (Step.WELCOME, Step.LANGUAGE):
        from src.flows.decision_tree import _detect_language_from_text
        state.language = (
            _detect_language_from_text(message)
            or _infer_language(message, state.language)
        )

    # Cheap regex prior: seed hard slots (group splits, certification, activity,
    # location) unconditionally so nothing is lost even if the LLM misses them.
    intent = intent_detector.detect(message, state)
    _apply_detected_intent(intent, state)

    snapshot = _build_extra_context(state)
    decision = await orchestrator.orchestrate(
        message,
        state_snapshot=snapshot,
        history=state.history,
        lang=state.language,
        allowed_actions=_ENTRY_ACTIONS,
    )
    _persist_remembered(state, decision.remembered)

    if decision.tool == orchestrator.TOOL_ESCALATE:
        result = await _apply_orchestrator_decision(state, message, decision)
        if result is not None:
            return result

    if decision.tool in _ENTRY_BOOKING_TOOLS:
        # Sync any LLM-remembered facts into the intent so the deterministic
        # router sees the merged truth (e.g. certification the regex missed).
        if state.is_certified is not None:
            intent.is_certified = state.is_certified
        intent.group_size = state.detected_group_size or intent.group_size
        intent.group_allocation = state.detected_group_allocation or intent.group_allocation
        intent.activity = state.detected_activity or intent.activity
        intent.location = state.detected_location or intent.location
        logger.info(f"[SUPERVISOR] Conversation agent -> booking entry (tool={decision.tool})")
        result = _route_detected_intent(intent, state, message)
        if result is not None:
            return result
        # Couldn't route (e.g. no concrete activity) -> fall through to an answer.

    # "Soy certificado" / "somos buzos certificados" and similar bare statements:
    # the LLM often tags these as answer_question and RAG gives a vague "do you have
    # a date in mind?" reply. When the deterministic router clearly WOULD offer the
    # certified-diving options and the message isn't literally a question, prefer
    # showing those options over a vague answer.
    if (
        decision.tool not in _ENTRY_BOOKING_TOOLS
        and not _message_looks_like_question(message)
        and _should_skip_to_certified_flow(intent, state)
    ):
        if state.is_certified is not None:
            intent.is_certified = state.is_certified
        intent.group_size = state.detected_group_size or intent.group_size
        intent.location = state.detected_location or intent.location
        result = _route_detected_intent(intent, state, message)
        if result is not None:
            logger.info("[SUPERVISOR] Bare certified-diver statement -> offering diving options")
            return result

    # A companion mentioned in free text ("va mi novia que solo acompaña") — when
    # nothing else would route (no diving intent for the speaker), proactively
    # offer that companion the mini-course/snorkel upsell instead of a plain RAG
    # reply. Reaching here means routing did NOT act (a booking tool whose intent
    # had no concrete activity, or a plain answer_question); if the speaker DID
    # have a diving intent, _route_detected_intent already returned above.
    if not _intent_would_route(intent, state, message) and _mentions_pure_companion(message):
        logger.info("[SUPERVISOR] Pure companion mention -> companion upsell")
        return _enter_companion_upsell(state)

    # answer_question / profile-only / unrouted booking -> reply via RAG with the
    # now-enriched context (remembered facts included).
    if decision.tool in (orchestrator.TOOL_SET_PROFILE, orchestrator.TOOL_NOTE_LOGISTICS):
        await _apply_orchestrator_decision(state, message, decision)  # mutate only
    logger.info(f"[SUPERVISOR] Conversation agent -> RAG answer step={state.step.value}")
    state.history.append({"role": "user", "content": message})
    extra_context = _build_extra_context(state)
    answer = await rag_answer(
        message,
        lang=state.language,
        history=state.history,
        extra_context=extra_context,
        verify_grounding=False,
    )
    state.history.append({"role": "assistant", "content": answer})
    # Conversation has started: leave the welcome/language step so a later bare
    # digit isn't misread as a language pick. Buttons stay off (conversation-first).
    if state.step in (Step.WELCOME, Step.LANGUAGE):
        state.step = Step.MAIN_MENU
    return answer


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


def _apply_detected_intent(intent, state: ConversationState) -> None:
    if intent.language and not state.detected_language:
        state.detected_language = intent.language
        state.language = intent.language
        logger.info(f"[INTENT] Detected language: {intent.language}")

    # Latest concrete activity wins: the customer may change their mind mid-chat
    # ("quiero bucear" ... "mejor un minicurso para mi hijo"). Before, the FIRST
    # activity stuck forever (write-once), so after talking about Bubble Makers /
    # a minicurso, clicking "🤿 Reservar" still routed them into the CERTIFIED
    # diving flow. Now a newly-detected activity replaces the stale one.
    if intent.activity and intent.activity != state.detected_activity:
        state.detected_activity = intent.activity
        state.detected_service_id = intent.service_id
        # A beginner activity (minicurso/snorkel) also carries a certification
        # signal — refresh it so the (possibly stale) certified flag doesn't
        # send a beginner request down the certified path.
        if intent.is_certified is not None:
            state.detected_is_certified = intent.is_certified
            state.is_certified = intent.is_certified
        logger.info(f"[INTENT] Activity updated to: {intent.activity} (service: {intent.service_id})")
    elif intent.is_certified is not None and state.detected_is_certified is None:
        state.detected_is_certified = intent.is_certified
        state.is_certified = intent.is_certified
        logger.info(f"[INTENT] Detected certification: {intent.is_certified}")

    if intent.group_size and not state.detected_group_size:
        state.detected_group_size = intent.group_size
        logger.info(f"[INTENT] Detected group size: {intent.group_size}")

    if intent.group_allocation and not state.detected_group_allocation:
        state.detected_group_allocation = intent.group_allocation
        logger.info(f"[INTENT] Detected group allocation: {intent.group_allocation}")

    if intent.ages:
        merged = sorted(set((state.detected_ages or []) + list(intent.ages)))
        if merged != (state.detected_ages or []):
            state.detected_ages = merged
            logger.info(f"[INTENT] Detected ages: {merged}")

    if intent.last_dive_over_2_years is not None and state.detected_last_dive_over_2_years is None:
        state.detected_last_dive_over_2_years = intent.last_dive_over_2_years
        state.last_dive_over_2_years = intent.last_dive_over_2_years
        logger.info(f"[INTENT] Detected last dive: {intent.last_dive_over_2_years}")

    if getattr(intent, "is_colombian", None) is not None and state.is_colombian is None:
        # Set only is_colombian; the checkout's _goto_mixed_final_colombian inherits
        # it (and sets mixed_final_is_colombian + currency) so its skip stays intact.
        state.is_colombian = intent.is_colombian
        logger.info(f"[INTENT] Detected nationality is_colombian={intent.is_colombian}")

    if intent.duration and not state.detected_duration:
        state.detected_duration = intent.duration
        logger.info(f"[INTENT] Detected duration: {intent.duration}")

    if getattr(intent, "cert_dives", None) and not state.detected_cert_dives:
        state.detected_cert_dives = intent.cert_dives
        logger.info(f"[INTENT] Detected cert dive count: {intent.cert_dives}")

    if getattr(intent, "cert_days", None) and not state.detected_cert_days:
        state.detected_cert_days = intent.cert_days
        logger.info(f"[INTENT] Detected cert day count: {intent.cert_days}")

    if intent.location and not state.detected_location:
        state.detected_location = intent.location
        state.location = intent.location
        logger.info(f"[INTENT] Detected location: {intent.location}")

    if intent.island and not state.detected_island:
        state.detected_island = intent.island
        state.island = intent.island
        logger.info(f"[INTENT] Detected island: {intent.island}")

    if intent.hotel and not state.detected_hotel:
        state.detected_hotel = intent.hotel
        state.hotel = intent.hotel
        logger.info(f"[INTENT] Detected hotel: {intent.hotel}")


def _continue_booking_quick_replies(state: ConversationState) -> list[dict]:
    """Buttons appended after answering an info question mid-flow (availability,
    food/included questions, etc.) without losing the pending cart action.

    Reuses the CURRENT step's primary quick reply value (by convention the
    first option in every mixed_* menu is the main forward action — "Añadir
    al carrito", "Confirmar carrito", etc.) so clicking "Continuar con la
    reserva" resumes exactly where the client was, instead of asking them to
    retype it as free text or letting the orchestrator misfire a tree action.
    """
    lang = state.language
    continue_title = "✅ Continuar con la reserva" if lang == "es" else "✅ Continue with booking"
    home_title = "🏠 Inicio" if lang == "es" else "🏠 Home"
    buttons: list[dict] = []
    if state.quick_replies:
        primary_value = state.quick_replies[0].get("value")
        if primary_value and primary_value != "back":
            buttons.append({"title": continue_title, "value": primary_value})
    buttons.append({"title": home_title, "value": "menu"})
    return buttons


def _build_confirmation_message(intent, state: ConversationState) -> str | None:
    lang = state.language

    # PRIMERO: Verificar si es grupo mixto (tiene prioridad)
    if intent.group_allocation and len(intent.group_allocation) > 1:
        # Construir descripción de actividades
        activities_es = []
        activities_en = []
        total_people = 0
        for activity, qty in intent.group_allocation.items():
            total_people += qty
            if activity == "certified_diving":
                activities_es.append(f"{qty} para buceo certificado")
                activities_en.append(f"{qty} for certified diving")
            elif activity == "snorkel":
                activities_es.append(f"{qty} para snorkel")
                activities_en.append(f"{qty} for snorkeling")
            elif activity == "minicourse":
                activities_es.append(f"{qty} para minicurso")
                activities_en.append(f"{qty} for minicourse")

        # Si el total real del grupo es mayor que lo asignado (tipico: "familia
        # de 6, papa certificado, mama no, y 4 hijos de..."), NO digas "son 2
        # personas" borrando a los demas — nombra a los que faltan (menores con
        # edades detectadas, o "por definir").
        group_total = intent.group_size or getattr(state, "detected_group_size", None) or 0
        if group_total > total_people:
            remaining = group_total - total_people
            minor_ages = sorted(a for a in (state.detected_ages or []) if a < 18)
            if minor_ages and len(minor_ages) == remaining:
                ages_str = ", ".join(str(a) for a in minor_ages)
                activities_es.append(f"{remaining} menores ({ages_str} años) que ubicamos según su edad")
                activities_en.append(f"{remaining} minors (ages {ages_str}) we'll place by age")
            else:
                activities_es.append(f"{remaining} más por definir")
                activities_en.append(f"{remaining} more to define")
            total_people = group_total

        together_note = ""
        preference = (state.remembered_facts or {}).get("preference") or ""
        if re.search(r"junt[oa]s|no separar|together|stay together|don'?t (want to )?split|don'?t separate", preference, re.IGNORECASE):
            together_note = (
                " Cada quien hace su actividad, pero van en la misma salida y el mismo día — no los separamos."
                if lang == "es"
                else " Each of you does your own activity, but you're on the same trip the same day — you won't be split up."
            )

        def _join_natural(items: list[str], conj: str) -> str:
            if len(items) <= 1:
                return "".join(items)
            return f"{', '.join(items[:-1])} {conj} {items[-1]}"

        if lang == "es":
            return f"¡Bienvenidos! Veo que son {total_people} personas: {_join_natural(activities_es, 'y')}.{together_note}"
        return f"Welcome! I see you are {total_people} people: {_join_natural(activities_en, 'and')}.{together_note}"

    # Buceo certificado (solo si NO es grupo mixto)
    if intent.activity == "certified_diving" and intent.is_certified:
        if intent.group_size and intent.group_size > 1:
            if lang == "es":
                return f"¡Genial! Veo que son {intent.group_size} buzos certificados. Para ofrecerles la mejor experiencia, necesito saber:"
            return f"Great! I see you are {intent.group_size} certified divers. To offer you the best experience, I need to know:"
        else:
            if lang == "es":
                return "¡Genial! Veo que eres buzo certificado. Para ofrecerte la mejor experiencia, necesito saber:"
            return "Great! I see you are a certified diver. To offer you the best experience, I need to know:"

    # Minicurso
    if intent.activity == "minicourse":
        if lang == "es":
            return "¡Perfecto! El minicurso de buceo es ideal para principiantes. Déjame preparar la información..."
        return "Perfect! The diving minicourse is ideal for beginners. Let me prepare the information..."

    # No mostrar mensaje de confirmación cuando va al carrito sin certificación clara
    return None


_INTENT_TRIGGER_STEPS = {
    Step.WELCOME,
    Step.LANGUAGE,
    Step.MAIN_MENU,
    Step.RESERVA_MENU,
    Step.INFO_MENU,
    Step.BOOKING_MENU,
    Step.MIXED_ENTRY,
}


def _should_skip_to_certified_flow(intent, state: ConversationState) -> bool:
    return (
        intent.activity == "certified_diving"
        and intent.is_certified is True
        and state.step in _INTENT_TRIGGER_STEPS
    )


def _should_ask_certification(intent, state: ConversationState) -> bool:
    return (
        intent.activity == "certified_diving"
        and intent.is_certified is None
        and state.step in _INTENT_TRIGGER_STEPS
    )


def _should_enter_mixed_flow(intent, state: ConversationState) -> bool:
    return (
        intent.group_allocation is not None
        and len(intent.group_allocation) > 1
        and state.step in _INTENT_TRIGGER_STEPS
    )


def _message_looks_like_question(message: str) -> bool:
    """True if the message contains a literal "?".

    A message that asks ABOUT a course ("¿cómo se paga el curso de
    divemaster?") should never be treated the same as a message that
    REQUESTS one ("quiero el curso de divemaster"). Deliberately narrower
    than a question-word set: common Spanish words like "que"/"como"/"cual"
    double as ordinary conjunctions ("somos 4 que vamos a hacer snorkel"),
    so word-matching false-positives on plain statements. "?" presence is
    the same signal _is_substantive_free_text already uses for this.
    """
    return "?" in message


# A companion who ONLY accompanies, mentioned in free text ("va mi novia que solo
# acompaña", "voy con alguien que solo va a mirar"). We proactively offer that
# companion the mini-course/snorkel upsell. Questions ("¿el acompañante paga?")
# are excluded (they go to RAG).
_PURE_COMPANION_RE = re.compile(
    r"\bsolo\s+(?:me\s+|te\s+|nos\s+|lo\s+|la\s+)?acompan"
    r"|\bsolo\s+(?:va|van|viene|vienen|ira|iran|quiere|quieren)\s+(?:a\s+)?acompan"
    r"|\b(?:de|como)\s+acompan(?:ante|antes)?\b"
    r"|\b(?:va|van|viene|vienen)\s+a\s+acompan"
    r"|\bsolo\s+(?:a\s+)?(?:mirar|ver|acompan)"
    r"|\bno\s+(?:va\s+a\s+|van\s+a\s+|quiere[n]?\s+)?buce\w*\s+ni\b"
    r"|\bjust\s+(?:to\s+)?accompany|\bonly\s+(?:to\s+)?accompany|\bjust\s+accompanying\b"
    r"|\bcome\s+along\b|\bjust\s+(?:to\s+)?watch\b|\bwon'?t\s+dive\b",
    re.IGNORECASE,
)


def _mentions_pure_companion(message: str) -> bool:
    if _message_looks_like_question(message):
        return False
    norm = "".join(
        c for c in unicodedata.normalize("NFD", (message or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    return bool(_PURE_COMPANION_RE.search(norm))


def _enter_companion_upsell(state: ConversationState) -> str:
    """Set up the mixed cart flow and route to the companion mini-course/snorkel
    upsell. Asks the origin first if unknown (needed for pricing); a pending flag
    then routes back to the upsell once the location is set."""
    from src.flows.decision_tree import MESSAGES
    decision_tree._reset_mixed_state(state)
    state.mixed_cart = []
    state.mixed_entry_path = "booking"
    if state.detected_location and not state.location:
        state.location = state.detected_location
    if state.step in (Step.WELCOME, Step.LANGUAGE):
        state.step = Step.MAIN_MENU
    if not state.location:
        state.mixed_pending_companion_upsell = True
        state.step = Step.MIXED_LOCATION
        decision_tree.set_quick_replies(state, "tours_location")
        intro = (
            "¡Qué bueno que venga acompañante! Para armarlo bien, "
            if state.language == "es"
            else "Love that a companion is coming! To set it up right, "
        )
        return intro + MESSAGES["mixed_location"][state.language]
    return decision_tree._goto_mixed_companion_upsell(state)


def _intent_would_route(intent, state: ConversationState, message: str = "") -> bool:
    """Pure check: would _route_detected_intent actually act on this intent?

    Mirrors the branch conditions in _route_detected_intent without mutating
    state, so a low-confidence intent that wouldn't have triggered any flow
    change anyway (e.g. a generic "padi_course" question) falls through
    silently instead of asking a pointless confirmation.
    """
    if _should_enter_mixed_flow(intent, state):
        return True
    if _should_skip_to_certified_flow(intent, state):
        return True
    if intent.activity in ("minicourse", "snorkel", "padi_open_water", "padi_advanced",
                            "padi_rescue", "padi_divemaster", "padi_specialty"):
        return not _message_looks_like_question(message)
    if _should_ask_certification(intent, state):
        return True
    return False


def _route_detected_intent(intent, state: ConversationState, message: str = "") -> str | None:
    """Apply a detected intent to state and route to the matching flow step.

    Returns the response string if a flow branch matched, or None if nothing
    matched (caller should fall through to the rest of route_message).
    """
    _apply_detected_intent(intent, state)

    # PRIMERO: Verificar si es grupo mixto (tiene prioridad sobre flujos individuales)
    if _should_enter_mixed_flow(intent, state):
        confirmation = _build_confirmation_message(intent, state)
        from src.flows.decision_tree import MESSAGES

        state.mixed_cart = []

        # Pre-setar cantidades conocidas para saltarnos preguntas
        cert_qty = (intent.group_allocation or {}).get("certified_diving", 0)
        beginner_qty = (intent.group_allocation or {}).get("minicourse", 0)
        snorkel_qty = (intent.group_allocation or {}).get("snorkel", 0)
        # Snorkel doesn't need a qualifying question chain (unlike cert's
        # last-dive/refresher or minicurso's kids-age questions) — add it to
        # the cart directly so a 3-way split (cert + minicourse + snorkel,
        # T007 in docs/test-battery-edge-cases.md) doesn't silently drop the
        # snorkel person while the other two subgroups go through their flows.
        if snorkel_qty > 0:
            decision_tree._append_mixed_cart_item(
                state, "snorkel", decision_tree._service_for_location("snorkeling", state), snorkel_qty
            )
        if cert_qty > 0:
            state.mixed_pending_qty_type = "cert"
            state.mixed_pending_cert_total_qty = cert_qty
            state.mixed_pending_cert_remaining_qty = cert_qty
            state.mixed_pending_qty_value = cert_qty
            # "some certified, some not": queue the minicurso for the rest
            # so it's added automatically after the certified subgroup.
            if beginner_qty > 0:
                state.mixed_pending_beginner_after_cert = beginner_qty

        # Aplicar ubicación si ya la detectamos
        if intent.location and not state.location:
            state.location = intent.location
        if intent.island and not state.island:
            state.island = intent.island

        # Elegir step de entrada: saltamos MIXED_ENTRY
        if not state.location:
            state.step = Step.MIXED_LOCATION
            decision_tree.set_quick_replies(state, "tours_location")
            next_msg = MESSAGES["mixed_location"][state.language]
        elif cert_qty > 0:
            # On the islands but we don't know the hotel yet (needed for
            # pickup coordination): ask island/hotel BEFORE resolving the cert
            # plan, same as _after_location_set does when location is
            # answered via the MIXED_LOCATION step. Without this, a message
            # like "vamos desde las islas" (location known straight from free
            # text, never asked) skipped island/hotel entirely and the summary
            # silently assumed "Islas del Rosario" with a made-up pickup time.
            if state.location == "island" and not state.hotel:
                next_msg = decision_tree._goto_island_hotel_menu_or_unknown(state)
            else:
                next_msg = decision_tree._resolve_or_ask_cert_plan(
                    state, getattr(intent, "cert_dives", None), getattr(intent, "cert_days", None)
                )
        else:
            # Sólo snorkel/minicurso → entrar al carrito normalmente
            state.step = Step.MIXED_ENTRY
            decision_tree.set_quick_replies(state, "mixed_entry")
            next_msg = MESSAGES["mixed_entry"][state.language]

        logger.info(
            f"[INTENT] Mixed group allocation={intent.group_allocation} "
            f"cert_qty={cert_qty} snorkel_qty={snorkel_qty} -> step={state.step.value}"
        )
        if confirmation:
            return confirmation + "\n\n" + next_msg
        return next_msg

    # Skip to certified diving flow if we detected certified diver
    elif _should_skip_to_certified_flow(intent, state):
        confirmation = _build_confirmation_message(intent, state)

        # Ir al flujo de carrito
        state.step = Step.MIXED_ENTRY
        state.mixed_cart = []

        # Marcar que queremos buceo certificado
        state.mixed_pending_qty_type = "cert"

        # Pre-fill qty if group size is known
        if intent.group_size and intent.group_size > 0:
            state.mixed_pending_qty_value = intent.group_size
            state.mixed_pending_cert_total_qty = intent.group_size
            state.mixed_pending_cert_remaining_qty = intent.group_size

        # Si no tenemos ubicación, preguntar primero
        if not state.detected_location and not state.location:
            state.step = Step.MIXED_LOCATION
            decision_tree.set_quick_replies(state, "tours_location")
            from src.flows.decision_tree import MESSAGES
            logger.info("[INTENT] Detected certified diving, asking location first")
            if confirmation:
                return confirmation + "\n\n" + MESSAGES["mixed_location"][state.language]
            return MESSAGES["mixed_location"][state.language]

        # Si tenemos ubicación, resolver directo el plan de buceo certificado
        state.location = state.detected_location or state.location
        state.mixed_pending_qty_type = "cert"
        # On the islands but no hotel yet: ask island/hotel first (needed for
        # pickup coordination) instead of resolving the plan blind — see the
        # matching comment on the mixed-group branch above for the bug this
        # prevents (a summary silently assuming "Islas del Rosario").
        if state.location == "island" and not state.hotel:
            next_msg = decision_tree._goto_island_hotel_menu_or_unknown(state)
        else:
            next_msg = decision_tree._resolve_or_ask_cert_plan(
                state, getattr(intent, "cert_dives", None), getattr(intent, "cert_days", None)
            )
        logger.info(f"[INTENT] Going to cart with location -> step={state.step.value}")
        return (confirmation + "\n\n" + next_msg) if confirmation else next_msg

    # Detectar actividades específicas (minicurso, PADI, snorkel, etc.) → ir directo al carrito.
    # Skip when the message is a QUESTION about the course ("¿cómo se paga el
    # curso de divemaster?") rather than a request to book it — those belong to RAG.
    elif intent.activity in ("minicourse", "snorkel", "padi_open_water", "padi_advanced",
                              "padi_rescue", "padi_divemaster", "padi_specialty") \
            and not _message_looks_like_question(message):
        confirmation = _build_confirmation_message(intent, state)
        state.step = Step.MIXED_ENTRY
        state.mixed_cart = []

        # Mapear actividad a tipo de carrito
        if intent.activity == "minicourse":
            state.mixed_pending_qty_type = "beginner"
        elif intent.activity == "snorkel":
            state.mixed_pending_qty_type = "snorkel"
        elif intent.activity in ("padi_open_water", "padi_advanced", "padi_rescue",
                                  "padi_divemaster", "padi_specialty"):
            state.mixed_pending_qty_type = "course"
            state.mixed_pending_qty_plan = intent.service_id
            state.selected_service = intent.service_id

        # Pre-fill qty if group size is known
        if intent.group_size and intent.group_size > 0:
            state.mixed_pending_qty_value = intent.group_size

        # Si no tenemos ubicación, preguntar primero
        if not state.detected_location and not state.location:
            state.step = Step.MIXED_LOCATION
            decision_tree.set_quick_replies(state, "tours_location")
            from src.flows.decision_tree import MESSAGES
            logger.info(f"[INTENT] Detected {intent.activity}, asking location first")
            if confirmation:
                return confirmation + "\n\n" + MESSAGES["mixed_location"][state.language]
            return MESSAGES["mixed_location"][state.language]

        # Si tenemos ubicación, usar _goto_mixed_add_qty que ya skipea si hay qty conocida
        state.location = state.detected_location or state.location
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[INTENT] Detected {intent.activity} with location, resolving qty")
        response = decision_tree._goto_mixed_add_qty(state)
        if confirmation:
            return confirmation + "\n\n" + response
        return response

    # Ask certification if activity is diving but certification unknown
    elif _should_ask_certification(intent, state):
        from src.flows.decision_tree import MESSAGES
        state.step = Step.MIXED_ASK_CERTIFICATION
        state.mixed_cart = []
        is_group = (intent.group_size or 0) > 1 or (state.detected_group_size or 0) > 1
        if is_group:
            state.detected_group_size = intent.group_size or state.detected_group_size
            decision_tree.set_quick_replies(state, "mixed_ask_certification_group")
            logger.info("[INTENT] Detected diving group, no cert, asking group certification")
            return MESSAGES["mixed_ask_certification_group"][state.language]
        decision_tree.set_quick_replies(state, "mixed_ask_certification")
        logger.info("[INTENT] Detected diving, no certification, asking certification")
        return MESSAGES["mixed_ask_certification"][state.language]

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

    # Resolve a pending low-confidence intent confirmation ("¿Te refieres a
    # X? Sí/No") before anything else runs. See _route_detected_intent /
    # Capa 3 of the typo-resilience plan.
    pending_intent = getattr(state, "pending_intent_confirmation", None)
    if pending_intent is not None:
        state.pending_intent_confirmation = None
        if is_affirmative(message):
            state.history.append({"role": "user", "content": message})
            result = _route_detected_intent(pending_intent, state)  # yes/no reply, not the original question
            if result is not None:
                state.history.append({"role": "assistant", "content": result})
                return result
        elif is_negative(message):
            from src.flows.decision_tree import MESSAGES
            state.history.append({"role": "user", "content": message})
            state.step = Step.MAIN_MENU
            decision_tree.set_quick_replies(state, "main_menu")
            response = MESSAGES["main_menu"][state.language]
            state.history.append({"role": "assistant", "content": response})
            return response
        # Anything else: drop the pending confirmation and let this message
        # fall through to normal routing below.

    # Sticky detection: once the speaker mentions kids/children/family-with-kids,
    # we remember it for the rest of the conversation so the cart-mixto question
    # about age ranges fires even if the cart ends up cert-only.
    if not getattr(state, "kids_mention_detected", False) and _detect_kids_mention(message):
        state.kids_mention_detected = True

    pii_hits = detect_pii(message)
    if pii_hits:
        state.step = Step.ESCALATE
        state.pending_escalation_reason = "datos sensibles detectados"
        logger.warning(f"[SUPERVISOR][PRIVACY] PII detected hits={pii_hits} step={state.step.value}")
        return privacy_block_message(state.language)

    # SAFETY FIRST: broken-link complaints and sensitive topics (medical,
    # weather, complaints) must escalate BEFORE the intent detector runs.
    # Otherwise a message like "Estoy embarazada, puedo bucear?" gets hijacked
    # by the booking intent ("bucear") and routed into the cart flow instead of
    # being handed to human staff. Broken-link runs before sensitive on purpose
    # (see the note at the original sensitive block below).
    if _detect_broken_link_complaint(message, state.history):
        reason = "🚨 LINK ROTO reportado por el cliente — revisar URLs"
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.warning(f"[SUPERVISOR] Broken-link complaint detected (early) msg={message[:80]!r}")
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

    sensitive_escalation_early = detect_sensitive_escalation(message, state.language)
    if sensitive_escalation_early:
        reason, response = sensitive_escalation_early
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.info(f"[SUPERVISOR] Sensitive escalation triggered (early) reason={reason}")
        return response

    # Booking cancellation/reschedule requests: inform the policy text from
    # the KB and let the customer choose between talking to an advisor or
    # going back to the main menu, instead of the bot deciding on its own.
    if _detect_cancellation_request(msg_lower):
        policy_text = (load_policies().get("policies", {}).get("cancellation") or {}).get(
            state.language, ""
        )
        if state.language == "es":
            response = (
                f"{policy_text}\n\n¿Quieres que te conecte con un asesor para gestionar la "
                "cancelación, o prefieres volver al menú principal?"
            )
        else:
            response = (
                f"{policy_text}\n\nWould you like me to connect you with an advisor to handle the "
                "cancellation, or would you rather go back to the main menu?"
            )
        state.quick_replies = _booking_change_buttons(state.language)
        logger.info("[SUPERVISOR] Cancellation request detected -> policy info + escalate/home buttons")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    if _detect_reschedule_request(msg_lower):
        policy_text = (load_policies().get("policies", {}).get("reschedule") or {}).get(
            state.language, ""
        )
        if state.language == "es":
            response = (
                f"{policy_text}\n\n¿Quieres que te conecte con un asesor para gestionar el cambio "
                "de fecha, o prefieres volver al menú principal?"
            )
        else:
            response = (
                f"{policy_text}\n\nWould you like me to connect you with an advisor to handle the "
                "date change, or would you rather go back to the main menu?"
            )
        state.quick_replies = _booking_change_buttons(state.language)
        logger.info("[SUPERVISOR] Reschedule request detected -> policy info + escalate/home buttons")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    # Mixed-nationality group (some Colombian/resident, some foreign) — not
    # implemented as a feature: pricing/currency is set once per conversation.
    # Answer honestly instead of falling through to a generic RAG fallback
    # (T013 in docs/test-battery-edge-cases.md).
    if _detect_mixed_nationality_request(msg_lower):
        if state.language == "es":
            response = (
                "¡Entendido! Cuando el grupo tiene nacionalidades mixtas, cada quien paga según su "
                "nacionalidad: los colombianos/residentes en pesos (COP) y los extranjeros en dólares "
                "(USD), al mismo precio equivalente — no hay descuento especial por ser colombiano. "
                "Para coordinar el pago individual de cada persona del grupo, lo mejor es que un "
                "asesor te ayude directamente.\n\n¿Quieres que te conecte con un asesor, o prefieres "
                "volver al menú principal?"
            )
        else:
            response = (
                "Got it! When the group has mixed nationalities, each person pays according to their "
                "own nationality: Colombians/residents in pesos (COP) and foreign visitors in dollars "
                "(USD), at the same equivalent price — there's no special discount for being "
                "Colombian. To coordinate each person's individual payment, it's best for an advisor "
                "to help you directly.\n\nWould you like me to connect you with an advisor, or would "
                "you rather go back to the main menu?"
            )
        state.quick_replies = _booking_change_buttons(state.language)
        logger.info("[SUPERVISOR] Mixed-nationality group detected -> honest explanation + escalate/home buttons")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    # Age-eligibility question ("mi hijo de 9 años puede bucear?", "hay edad
    # mínima?", "una persona de 14 puede?"). Answer deterministically from the
    # single source of truth (eligibility.py) so age limitations are always
    # correct and framed positively — no hallucination, no need for RAG.
    if state.step not in _MIXED_FLOW_STEPS:
        age_answer = _maybe_answer_age_eligibility(message, state)
        if age_answer is not None:
            logger.info("[SUPERVISOR] Age-eligibility question answered deterministically")
            state.history.append({"role": "user", "content": message})
            state.history.append({"role": "assistant", "content": age_answer})
            return age_answer

    # Adaptive diving / DIVE TO HEAL questions (disability, accessibility) must
    # be ANSWERED with the program's factual info (RAG handles the exception),
    # not hijacked by the booking IntentDetector into "¿eres certificado?".
    if _ADAPTIVE_DIVING_PATTERN.search(message) and state.step not in _MIXED_FLOW_STEPS:
        logger.info("[SUPERVISOR] Adaptive-diving/DIVE TO HEAL question -> RAG")
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Understanding-first entry (Fase 1). For substantive free text at an entry
    # step, the conversation agent ANSWERS the customer's actual message,
    # remembers what they said, and enters a booking only when they clearly want
    # to — instead of the old generic-catalog blurb and the eager keyword-based
    # booking routing (which ignored questions and volunteered info). Navigation /
    # keyword / language / escalation / availability commands are left to their
    # dedicated handlers below.
    if (
        not msg_lower.isdigit()
        and len(message.strip()) > 3
        and state.step in _INTENT_TRIGGER_STEPS
        and state.step not in _MIXED_FLOW_STEPS
        and msg_lower not in MENU_KEYWORDS
        and msg_lower not in BACK_KEYWORDS
        and msg_lower != "back"
        and msg_lower.strip("?!.,;:") not in GREETING_ONLY_KEYWORDS
        and not _matches_escalation_keyword(msg_lower)
        and not _AVAILABILITY_PATTERN.search(msg_lower)
        and _detect_language_intent(message) is None
    ):
        # Typing the exact current menu option ("reservar", "información") acts as
        # that button, so menu navigation keeps working. Rich free text won't
        # match a button (word-overlap + question-word guards) and goes to the
        # conversation agent.
        if state.quick_replies:
            matched_value = _match_quick_reply_text(state, message)
            if matched_value == "back":
                return _go_back_one_step(state)
            if matched_value is not None:
                response = decision_tree.process_message(state, matched_value)
                _maybe_build_pending_note(state)
                logger.info(f"[SUPERVISOR] Quick-reply text match value={matched_value} -> step={state.step.value}")
                return response
        return await _dispatch_conversation_agent(state, message)

    # Cliente acepta con un "si"/"dale"/"ok" una oferta que el propio bot hizo
    # en el turno anterior de pasarle con un asesor ("¿te paso el contacto de
    # un asesor?"). Sin esta rama, el "si" (demasiado corto para el agente
    # conversacional) caia a RAG y respondia el fallback generico — bug real
    # visto en PRE (2026-07-07). Restringido a pasos conversacionales para no
    # pisar los "si/no" de preguntas del arbol.
    if (
        state.step in (Step.MAIN_MENU, Step.FREE_TEXT)
        and _BARE_AFFIRMATION_RE.match(message.strip())
    ):
        last_bot = next(
            (h.get("content", "") for h in reversed(state.history or []) if h.get("role") == "assistant"),
            "",
        )
        if _ADVISOR_OFFER_RE.search(last_bot) and _OFFER_VERB_RE.search(last_bot):
            reason = "aceptó la oferta del bot de hablar con un asesor"
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = reason
            state.pending_note = build_lead_summary(state, escalation_reason=reason)
            from src.flows.decision_tree import MESSAGES
            logger.info("[SUPERVISOR] Bare affirmation accepted pending advisor offer -> escalate")
            return MESSAGES["escalate"][state.language]

    # Check for escalation keywords
    if _matches_escalation_keyword(msg_lower):
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "solicitó asesor"
        state.pending_note = build_lead_summary(state, escalation_reason="solicitó asesor")
        from src.flows.decision_tree import MESSAGES
        logger.info("[SUPERVISOR] Escalation triggered by keyword")
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

    # Generic "what days / is there availability" question — never invent a
    # date; reassure the client and point them to the booking link's calendar
    # (the real calendar with exact dates + headcount lives there). Runs after
    # the urgent real_time_issues escalation above, so specific phrases like
    # "disponible mañana" / "hay cupo" still escalate instead of getting this
    # canned answer. Keeps state.step untouched so "Continuar con la reserva"
    # resumes exactly where the client was.
    if _AVAILABILITY_PATTERN.search(msg_lower) and state.step not in (Step.WELCOME, Step.LANGUAGE):
        answer = (
            "¡Buena noticia! 📅 Las salidas son diarias y siempre hay disponibilidad. "
            "Vas a poder elegir el día exacto y el número de personas directamente en el "
            "calendario del link de reserva. 😊"
            if state.language == "es"
            else
            "Good news! 📅 Departures run daily and there's always availability. "
            "You'll be able to pick the exact date and number of people right in the "
            "booking link's calendar. 😊"
        )
        state.quick_replies = _continue_booking_quick_replies(state)
        logger.info(f"[SUPERVISOR] Availability/dates question -> canned answer, step kept={state.step.value}")
        return answer

    # Check for menu reset keywords
    if msg_lower in MENU_KEYWORDS:
        state.step = Step.MAIN_MENU
        decision_tree.set_quick_replies(state, "main_menu")
        from src.flows.decision_tree import MESSAGES
        logger.info("[SUPERVISOR] Menu reset triggered by keyword")
        return MESSAGES["main_menu"][state.language]

    # Step-back: "🔙 Volver" button (value="back") or back keyword
    if msg_lower == "back" or msg_lower in BACK_KEYWORDS:
        logger.info(f"[SUPERVISOR] Back navigation from step={state.step.value}")
        # Cart-flow steps that manage their own back/cancel inline (handlers
        # return _goto_mixed_cart_review which renders cart_lines + prompt;
        # _go_back_one_step would only return the prompt without the cart).
        if state.step in (
            Step.MIXED_LOCATION,
            Step.MIXED_ADD_ACTIVITY,
            Step.MIXED_COMPANION_UPSELL,
            Step.MIXED_ADD_CERT_PLAN,
            Step.MIXED_ADD_CERT_MULTI_DAY,
            Step.MIXED_ADD_QTY,
            Step.MIXED_CERT_LAST_DIVE,
            Step.MIXED_CERT_REFRESH_INTEREST,
            Step.MIXED_CERT_REFRESH_QTY,
            Step.MIXED_CERT_SPLIT_REVIEW,
            Step.MIXED_ADD_PREVIEW,
            Step.MIXED_CART_MODIFY_PICK,
            Step.MIXED_CART_REMOVE_PICK,
            Step.MIXED_CART_LOCATION,
            Step.MIXED_FINAL_KIDS_U8,
            Step.MIXED_FINAL_KIDS_810,
            Step.MIXED_ASK_CERTIFICATION,
            Step.MIXED_ASK_CERT_COUNT,
            Step.MIXED_ASK_BEGINNER_ACTIVITY,
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
        logger.info("[SUPERVISOR] Greeting restart -> step=WELCOME")
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
            _maybe_build_pending_note(state)
            logger.info(f"[SUPERVISOR] Decision tree (exact button value={exact_value}) -> step={state.step.value}")
            return response

        # If it looks like a menu choice (number), use decision tree
        if msg_lower.isdigit():
            response = decision_tree.process_message(state, message)
            _maybe_build_pending_note(state)
            logger.info(f"[SUPERVISOR] Decision tree -> step={state.step.value}")
            return response

        # At the cert-plan step, an explicit dive count ("el paquete de 2 buceos",
        # "5 inmersiones") is unambiguous — resolve it deterministically before the
        # quick-reply text matcher below, which otherwise scores "paquete de 2 buceos"
        # against the "Paquete multi-día" button (shared word "paquete" alone clears
        # its 0.5 threshold) and returns that button's value first.
        if state.step == Step.MIXED_ADD_CERT_PLAN:
            from src.agents.intent_detector import detect_cert_dive_count
            if detect_cert_dive_count(message) is not None:
                response = decision_tree.process_message(state, message)
                _maybe_build_pending_note(state)
                logger.info(f"[SUPERVISOR] Explicit dive count at cert-plan -> step={state.step.value}")
                return response

        # Free text that clearly matches one of the current quick-reply buttons
        # is treated as if the user clicked that button.
        matched_value = _match_quick_reply_text(state, message)
        if matched_value == "back":
            logger.info(f"[SUPERVISOR] Back via quick-reply text from step={state.step.value}")
            return _go_back_one_step(state)
        if matched_value is not None:
            response = decision_tree.process_message(state, matched_value)
            _maybe_build_pending_note(state)
            logger.info(f"[SUPERVISOR] Quick-reply text match value={matched_value} -> step={state.step.value}")
            return response

        # Quantity-input steps expect a typed number, not an orchestrator action.
        # Route free text directly to the tree handler so "somos cuatro personas"
        # reaches _handle_mixed_add_qty / _handle_mixed_cert_refresh_qty instead
        # of leaking to the LLM orchestrator which re-shows the plan selection.
        if state.step in {Step.MIXED_ADD_QTY, Step.MIXED_CERT_REFRESH_QTY}:
            response = decision_tree.process_message(state, message)
            logger.info(f"[SUPERVISOR] Decision tree (qty-input free text) -> step={state.step.value}")
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
            # The stopword heuristic (_detect_language_from_text) catches most
            # first messages for free. When it finds nothing at all — a real
            # word/phrase outside the curated lists, not just digits or noise —
            # fall back to a cheap LLM call so we still skip the language
            # question instead of always asking.
            if (
                state.step == Step.WELCOME
                and not msg_lower.isdigit()
                and len(message.strip()) >= 2
                and not _detect_language_from_text(message)
            ):
                llm_language = await detect_language_llm(message)
                if llm_language:
                    state.language = llm_language
                    state.step = Step.MAIN_MENU
                    decision_tree.set_quick_replies(state, "main_menu")
                    logger.info(f"[SUPERVISOR] LLM language fallback -> lang={llm_language}")
                    return _TREE_MESSAGES["welcome_detected"][llm_language]

            response = decision_tree.process_message(state, message)
            logger.info(f"[SUPERVISOR] Decision tree (early step) -> step={state.step.value}")
            return response

        mixed_companion_response = _maybe_handle_companion_request_inside_mixed_flow(state, message)
        if mixed_companion_response is not None:
            return mixed_companion_response

        # "¿Cómo reservo?" at a point where we already know exactly which
        # activity the client wants (the final preview, or the cart review)
        # — give them the activity's own info page directly instead of the
        # generic RAG answer (which describes the exoneration form + manual
        # 50% payment + advisor confirmation). Checked BEFORE the plain
        # info-question shortcut below, since "cómo reservo" would otherwise
        # match that shortcut's starter-word pattern and go to RAG too.
        # Deliberately reduces friction (owner request 2026-07-16): the
        # customer gets the website link as soon as we know what they want,
        # without needing to go through "confirmar carrito" first.
        how_to_book_response = _maybe_answer_how_to_book_with_known_activity(state, message)
        if how_to_book_response is not None:
            logger.info(f"[SUPERVISOR] How-to-book question with known activity -> direct info link, step={state.step.value}")
            state.history.append({"role": "user", "content": message})
            state.history.append({"role": "assistant", "content": how_to_book_response})
            return how_to_book_response

        # Plain info questions ("incluye comida?", "qué incluye?") go straight to
        # RAG, BEFORE the tool-calling orchestrator gets a chance to misfire a
        # cart action on them (see _looks_like_info_question docstring for the
        # real regression this prevents). Keeps state.step/cart untouched and
        # attaches "Continuar con la reserva" + "Inicio" so the client can
        # resume instead of having to retype it.
        if (
            state.step in _MIXED_FLOW_STEPS
            and state.quick_replies
            and _looks_like_info_question(message)
        ):
            logger.info(f"[SUPERVISOR] Info question mid-flow -> RAG (skip orchestrator) step={state.step.value}")
            state.history.append({"role": "user", "content": message})
            extra_context = _build_extra_context(state)
            answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
            state.quick_replies = _continue_booking_quick_replies(state)
            state.history.append({"role": "assistant", "content": answer})
            return answer

        # Group recomposition mid-flow ("y mi hijo de 12", "ya seríamos 3") —
        # capture the change and keep the current step's buttons instead of the
        # step handler answering "no te entendí". Runs before the orchestrator so
        # the added person/age isn't lost. Not applied at qty/count steps, where a
        # bare number IS the expected answer (the explicit-cue regex already avoids
        # plain "somos 3", but we double-guard the numeric-answer steps).
        if (
            state.step in _MIXED_FLOW_STEPS
            and state.quick_replies
            and state.step not in (Step.MIXED_ADD_QTY, Step.MIXED_FINAL_KIDS_QTY,
                                   Step.MIXED_ASK_CERT_COUNT, Step.MIXED_CERT_REFRESH_QTY)
        ):
            recompose_ack = _apply_group_recomposition(message, state)
            if recompose_ack is not None:
                state.history.append({"role": "user", "content": message})
                state.history.append({"role": "assistant", "content": recompose_ack})
                return recompose_ack

        # Tool-calling orchestrator (Fase 2) — only inside the cart-style mixed flow.
        # Turns free text into structured tree actions ("estoy en las islas" ->
        # set_location, "quita el snorkel" -> remove_item, "quiero reservar" -> confirm).
        # Falls back to the legacy intent classifier when it picks answer_question.
        if state.step in _MIXED_FLOW_STEPS and state.quick_replies:
            orchestrator_response = await _dispatch_orchestrator(state, message)
            if orchestrator_response is not None:
                return orchestrator_response

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
                    Step.MIXED_COMPANION_UPSELL,
                    Step.MIXED_ADD_CERT_PLAN,
                    Step.MIXED_ADD_CERT_MULTI_DAY,
                    Step.MIXED_ADD_QTY,
                    Step.MIXED_CERT_LAST_DIVE,
                    Step.MIXED_CERT_REFRESH_INTEREST,
                    Step.MIXED_CERT_REFRESH_QTY,
                    Step.MIXED_CERT_SPLIT_REVIEW,
                    Step.MIXED_ADD_PREVIEW,
                    Step.MIXED_CART_MODIFY_PICK,
                    Step.MIXED_CART_REMOVE_PICK,
                    Step.MIXED_CART_LOCATION,
                    Step.MIXED_FINAL_KIDS_U8,
                    Step.MIXED_FINAL_KIDS_810,
                    Step.MIXED_ASK_CERTIFICATION,
                    Step.MIXED_ASK_CERT_COUNT,
                    Step.MIXED_ASK_BEGINNER_ACTIVITY,
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
                _maybe_build_pending_note(state)
                logger.info(f"[SUPERVISOR] Intent={intent} -> step={state.step.value}")
                return response

            # intent == "RAG" → Para steps críticos que esperan respuestas específicas,
            # enviar al decision_tree en lugar de RAG (el handler detectará texto libre)
            if state.step in (
                Step.MIXED_LOCATION,
                Step.MIXED_ADD_QTY,
                Step.MIXED_CERT_LAST_DIVE,
                Step.MIXED_CERT_REFRESH_INTEREST,
                Step.MIXED_CERT_REFRESH_QTY,
            ):
                logger.info(f"[SUPERVISOR] Classifier returned RAG but step={state.step.value} expects specific input, sending to decision_tree")
                response = decision_tree.process_message(state, message)
                _maybe_build_pending_note(state)
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
        # When the answer offers to hand off to an advisor (e.g. contact-only
        # courses), show matching advisor/home buttons instead of the stale
        # main-menu ones the conversation was carrying.
        if _answer_offers_advisor(answer):
            state.quick_replies = _booking_change_buttons(state.language)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    if state.step == Step.SUMMARY and any(
        getattr(state, attr, False)
        for attr in (
            "mixed_from_single_offer_pending",
            "mixed_from_single_activity_question_pending",
            "mixed_from_single_cert_question_pending",
            "mixed_from_single_cert_split_question_pending",
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
            _maybe_build_pending_note(state)
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
            "cash",
            "efectivo",
            "pago presencial",
        }
        if msg_lower in summary_choices:
            response = decision_tree.process_message(state, message)
            _maybe_build_pending_note(state)
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
        logger.info("[SUPERVISOR] RAG (post-summary)")
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
        logger.info("[SUPERVISOR] RAG (post-menu)")
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
    _maybe_build_pending_note(state)
    return response
