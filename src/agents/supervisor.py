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

from src.agents import conversation_summarizer
from src.agents.escalation import (
    detect_routing_signals,
    detect_sensitive_escalation,
    sensitive_response_for,
)
from src.agents.intent_detector import DetectedIntent, IntentDetector
from src.agents.lead_summary import build_lead_summary
from src.agents.llm_extractor import fill_gaps, missing_fields
from src.agents.rag_agent import rag_answer
from src.config import settings
from src.flows import cart_render, eligibility
from src.flows.messages import set_quick_replies
from src.flows.state import ConversationState, Step
from src.knowledge.loader import load_policies
from src.privacy import detect_pii, privacy_block_message

logger = logging.getLogger("uvicorn.error")

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
    r"coj[oa]s?|cojera|limp(?:s|ing)?|"
    r"sord[ao]s?|deaf|cieg[ao]s?|invidente|blind|"
    r"discapacidad\s+(?:visual|auditiva|motora|f[ií]sica|intelectual)"
    r")\b",
    re.IGNORECASE,
)

# Price or booking follow-ups. Inside the DIVE TO HEAL context these must NOT
# be answered with the generic Cartagena price list or the normal booking flow
# — adaptive diving is coordinated (logistics + price) per case with an
# advisor, so we route there coherently instead.
_PRICE_OR_BOOKING_Q = re.compile(
    r"\b(?:cu[aá]nto|precio|precios|cuesta|cuestan|vale|valen|sale|salen|tarifa|"
    r"how\s+much|price|cost|"
    r"reserv\w*|c[oó]mo\s+(?:reservo|reservamos|reservar|pago)|book|booking)\b",
    re.IGNORECASE,
)


def _adaptive_diving_advisor_answer(lang: str) -> str:
    """Coherent DIVE TO HEAL reply for price/booking questions: no generic
    prices in chat — adaptive diving is coordinated per case with an advisor
    (owner decision, 2026-07-17). Ends with an advisor offer that the bare-
    affirmation handler recognizes, so a later "sí" escalates."""
    if lang == "es":
        return (
            "En nuestro programa *DIVE TO HEAL* (buceo adaptado) el precio y la logística se "
            "coordinan de forma personalizada según la actividad y las necesidades de cada "
            "persona — por eso no es una tarifa fija de la web, la define un asesor evaluando "
            "tu caso para que la experiencia sea segura y a tu medida. 🤿\n\n"
            "¿Quieres que te pase con un asesor para darte todos los detalles? 😊"
        )
    return (
        "In our *DIVE TO HEAL* program (adaptive diving), the price and logistics are "
        "arranged individually based on the activity and each person's needs — so it isn't a "
        "fixed website rate; an advisor sets it after evaluating your case, so the experience "
        "is safe and tailored to you. 🤿\n\n"
        "Would you like me to connect you with an advisor for all the details? 😊"
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

# Los ÚNICOS 2 días cerrados del año (`policies.json["closed_days"]`): 25 de
# diciembre y 1 de enero, en cualquier forma de nombrarlos (fecha exacta,
# festividad, o "hoy/mañana" no aplica aquí — solo la fecha/festividad
# explícita, que es lo único que se puede resolver sin saber la fecha real
# de "hoy"). Usado para NO darle al cliente el canned de disponibilidad
# genérico ("siempre hay disponibilidad") en esos dos días concretos, que
# sería una respuesta falsa. (Portado de pre_gadea v0.21.10.)
_CLOSED_DATE_RE = re.compile(
    r"\b(25\s+de\s+diciembre|diciembre\s+25|december\s+25th?|dec\s+25th?|"
    r"navidad|christmas\s+day|"
    r"1\s+de\s+enero|enero\s+1|january\s+1st?|jan\s+1st?|"
    r"a[ñn]o\s+nuevo|new\s+year'?s?(?:\s+day)?)\b",
    re.IGNORECASE,
)

# Hallazgo (batería sintética contra PRE, 2026-08-26, lote 4, portado de
# pre_gadea v0.21.11): pregunta directa de si se puede tomar alcohol antes
# de bucear — respuesta plana ya conocida
# (`policies.json["no_alcohol_policy"]`), no un tema médico a evaluar caso
# por caso.
_ALCOHOL_BEFORE_DIVING_RE = re.compile(
    r"\b(?:alcohol|cerveza|tragos?|copas?|vino|licor|beer|alcoholic)\b.{0,25}"
    r"\b(?:bucear|buceo|buzos?|dive|diving)\b"
    r"|\b(?:bucear|buceo|buzos?|dive|diving)\b.{0,25}"
    r"\b(?:alcohol|cerveza|tragos?|copas?|vino|licor|beer|alcoholic)\b",
    re.IGNORECASE,
)

# Palabra de alergia + alérgeno alimentario conocido del catálogo (marisco/
# gluten/nueces/maní/lactosa) -> pregunta de política de comida del tour, ya
# respondida en `policies.json["food_policy"]`. Deliberadamente acotado: una
# alergia sin alérgeno alimentario explícito ("tengo alergias severas, es
# peligroso bucear?") sigue yendo al escalado médico normal.
_ALLERGY_WORD_RE = re.compile(r"\b(?:al[eé]rgic[oa]s?|alergias?|allergic|allergy|allergies)\b", re.IGNORECASE)
_FOOD_ALLERGEN_RE = re.compile(
    r"\b(?:mariscos?|gluten|nueces|man[ií]|cacahuates?|lactosa|"
    r"shellfish|nuts?|peanuts?|dairy|gluten[- ]free)\b",
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
# El acento se quita antes de matchear (más abajo), así que "qué" y "que" son
# indistinguibles aquí. El lookahead evita el falso positivo del "que"
# CONJUNCIÓN/exhortativo ("que se anime", "que él venga", "que uno haga") —
# seguido de pronombre átono/sujeto NUNCA es interrogativo, mientras que "que
# incluye"/"que precio" sí. (Los marcadores están ya sin acento: "él"->"el".)
_QUE_CONJUNCION = r"(?!\s+(?:se|el|ella|ellos|ellas|uno|una|unos|unas)\b)"
_INFO_QUESTION_STARTER_PATTERN = re.compile(
    r"^("
    r"qu[ée]" + _QUE_CONJUNCION + r"|cu[áa]nto|cu[áa]ndo|c[óo]mo|d[óo]nde|cu[áa]l|"
    r"inclu[yi]e|tiene|tienen|hay|puedo\s+saber|"
    # Aperturas de BÚSQUEDA de info sin palabra-pregunta ni "?" (2026-07-24):
    # "cuéntame del precio", "me gustaría saber qué incluye", "dime cómo es".
    # Inequívocamente informativas (no acciones de carrito tipo "puedo añadir").
    r"cu[ée]ntame|d[ií]me|expl[ií]came|me\s+gustar[ií]a\s+saber|"
    r"quiero\s+saber|quisiera\s+saber|necesito\s+saber|"
    r"what|how|when|where|which|does|is\s+there|are\s+there|do\s+you|can\s+i\s+know|"
    r"tell\s+me|i'?d\s+like\s+to\s+know|i\s+want\s+to\s+know"
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

    # NOTE (robustness review H4, deferred): the LLM cutover is NOT wired here.
    # This is a narrow, regex-cued pre-dispatch short-circuit for group
    # recomposition; the cutover belongs in a single early hook shared by all
    # paths, tracked as future work rather than bolted onto this path.
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


# Keywords that send the user all the way back to the main menu.
MENU_KEYWORDS = {
    "menu", "menú", "inicio", "start", "opciones", "options",
}

# Keywords that take the user one step UP in the decision tree.
BACK_KEYWORDS = {
    "volver", "back", "atras", "atrás", "regresar",
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
    # ampliado (Bloque 2.3): la queja de link roto casi siempre nombra el
    # medio que falla — botón/pago/web/checkout — no solo "link"/"página".
    "botón", "boton", "button", "pago", "pagar", "payment", "checkout",
    "web", "reserva online", "booking page", "booking link",
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


def _in_active_cart_building(state: ConversationState) -> bool:
    """True cuando la conversación está CONSTRUYENDO una reserva NUEVA ahora
    mismo. Ahí un mensaje de "cambio" ("mejor 3 días", "cámbialo a snorkel",
    "en realidad somos 4") es una EDICIÓN del plan en curso, que maneja el
    núcleo conversacional (multi-día por texto, corrección de grupo,
    split de acompañante...), NO una cancelación/reprogramación/modificación
    de una reserva YA existente. Se usa para NO dejar que la señal LLM
    `booking_change_topic` (que se equivoca aquí: clasifica "do it for 3
    days instead" como 'reschedule', o "en realidad somos 4" como
    'modify_headcount') pise esos interceptores. La lista de keyword de
    cancelación/reprogramación/modificación (explícita, "cancelar mi
    reserva") sí sigue activa siempre, sin este guard.

    `state.step.value.startswith("mixed")` (el chequeo original) es de la
    arquitectura del árbol guiado PRE-Fase 4 — el núcleo conversacional
    actual (`conversational_core.py`) nunca pone `state.step` en un valor
    "mixed_*" (solo `FREE_TEXT`/`ESCALATE`), así que esa condición llevaba
    tiempo siendo código muerto. Hallazgo en vivo (batería sintética contra
    PRE, 2026-08-26, conv 429, portado de pre_gadea v0.21.10): sin un
    chequeo real, "somos 5 para buceo" → "en realidad revisamos y somos 4"
    (corrección de grupo DENTRO de una reserva que se está armando, ninguna
    reserva existe todavía) disparaba el flujo `modify_headcount` como si
    "somos 4" hablara de una reserva YA hecha. Fix: además del chequeo
    legacy (por si algún step MIXED_* vuelve a usarse), se considera
    "construyendo activamente" en cuanto el núcleo YA tiene una actividad
    detectada, un slot pendiente, o algo en el carrito — cualquiera de esas
    tres señales significa que la reserva en curso es nueva, no una ya
    existente."""
    return bool(
        state.step.value.startswith("mixed")
        or state.detected_activity
        or state.core_pending_slot
        or state.mixed_cart
    )


# Deflexión (Bloque 2.2): el cliente pide un número de teléfono/WhatsApp o una
# vía de contacto directa. El bot NUNCA da un número (decisión owner; el guard
# de grounding `contains_phone_number` ya lo impide en las respuestas de RAG) —
# pero hoy esa petición cae inconsistente: a veces escala a asesor, a veces al
# fallback genérico ("ese detalle no lo tengo a la mano", evasivo). En su lugar,
# una DEFLEXIÓN honesta y consistente: fijar el límite 🔒 + dar lo que SÍ se
# puede (reservar en el chat / el equipo contacta) + redirigir a la reserva.
# Sin escalar. Frases sin acento (se normalizan). Respaldo LLM
# `asks_for_contact_number` en detect_routing_signals para lo que la lista no cace.
CONTACT_NUMBER_REQUEST_PHRASES = {
    # ES
    "numero de telefono", "numero telefonico", "tu telefono", "su telefono",
    "un telefono", "el telefono", "telefono de contacto", "numero de contacto",
    "numero de whatsapp", "tu whatsapp", "su whatsapp", "el whatsapp", "un whatsapp",
    "por whatsapp", "linea de atencion", "linea de contacto", "numero para llamar",
    "un numero para", "me das un numero", "me das tu numero", "dame tu numero",
    "dame un numero", "como los contacto", "como los llamo", "como te llamo",
    "como los puedo llamar", "para llamarlos", "para llamarte", "los puedo llamar",
    "puedo llamarlos", "un correo", "su correo", "tu correo", "email de contacto",
    # EN
    "phone number", "whatsapp number", "your whatsapp", "a number to call",
    "number to call you", "to call you", "call you", "contact number",
    "how do i contact you", "how can i reach you", "how do i reach you",
    "your email", "contact email", "an email to",
}


def _asks_for_contact_number(msg_lower: str) -> bool:
    normalized = _strip_accents(msg_lower)
    return any(phrase in normalized for phrase in CONTACT_NUMBER_REQUEST_PHRASES)


# Dominio blindado (Bloque 2.4): preguntas meta sobre qué IA/modelo/tecnología
# hay detrás, o si es un bot. No se revela nada (el system prompt de RAG ya lo
# prohíbe); pero hoy caen al fallback genérico evasivo. En su lugar, una
# respuesta canónica, cálida y EN PERSONA (Coral), que reconduce al buceo. El
# respaldo semántico es el propio prompt de RAG endurecido; esto solo hace la
# respuesta consistente para las formas más directas.
_AI_IDENTITY_RE = re.compile(
    r"\b(?:qu[eé]\s+(?:modelo|ia|inteligencia\s+artificial)|"
    r"eres\s+(?:un[ao]?\s+)?(?:bot|ia|robot|inteligencia\s+artificial|chatgpt|gpt|programa|m[aá]quina)|"
    r"eres\s+(?:human[ao]|real|una\s+persona)|"
    r"chatgpt|gpt-?\d|openai|llm|modelo\s+de\s+lenguaje|"
    r"qu[eé]\s+(?:ia|tecnolog[ií]a)\s+(?:usas|eres|hay)|"
    r"which\s+(?:ai|model|llm)|what\s+(?:ai|model|llm)|"
    r"are\s+you\s+(?:a\s+)?(?:bot|ai|robot|human|real|chatgpt|gpt)|"
    r"what\s+are\s+you\s+running\s+on)\b",
    re.IGNORECASE,
)


def _asks_about_ai_identity(msg_lower: str) -> bool:
    return bool(_AI_IDENTITY_RE.search(_strip_accents(msg_lower)))


def _ai_identity_deflection(lang: str) -> str:
    if lang == "es":
        return (
            "¡Soy Coral, de Diving Planet! 🐠 Me encanta ayudarte a vivir el buceo en las Islas "
            "del Rosario. De temas técnicos mejor no te cuento — pero de buceo, precios y "
            "reservas sé un montón. ¿Te ayudo a armar tu salida? 🌊"
        )
    return (
        "I'm Coral, from Diving Planet! 🐠 I love helping you experience diving in the Rosario "
        "Islands. I'll skip the techy stuff — but when it comes to diving, prices and bookings I "
        "know plenty. Shall I help you set up your trip? 🌊"
    )


# Disponibilidad (Bloque 2.5): el cliente pregunta si hay cupo/espacio para un
# día concreto. El bot NO ve el calendario real — medido en vivo que hoy
# ALUCINA ("¡Claro que sí! Tenemos disponibilidad para el sábado") porque el
# guard de grounding revisa precios/URLs pero no una afirmación de
# disponibilidad en prosa. Respuesta canónica honesta: operamos a diario (verdad
# general), el cupo exacto para esa fecha lo confirma el equipo, y se mantiene el
# impulso hacia la reserva. Respaldo LLM `availability_question` para lo que la
# lista no cace.
_AVAILABILITY_RE = re.compile(
    r"\b(?:hay\s+(?:cupo|lugar|espacio|disponibilidad|plaza|sitio)|"
    r"queda\s+(?:cupo|lugar|espacio|plaza|sitio)|quedan\s+(?:cupos|lugares|plazas|puestos)|"
    r"tienen?\s+(?:cupo|lugar|espacio|disponibilidad)|"
    r"est[aá]\s+disponible|hay\s+disponib|con\s+cupo|"
    r"availability|any\s+spots?|spots?\s+left|space\s+(?:for|left|available)|"
    r"do\s+you\s+have\s+(?:room|space|availability)|is\s+there\s+(?:room|space))\b",
    re.IGNORECASE,
)


def _asks_about_availability(msg_lower: str) -> bool:
    return bool(_AVAILABILITY_RE.search(_strip_accents(msg_lower)))


def _contact_number_deflection(lang: str) -> str:
    """Deflexión honesta para una petición de número/contacto directo: límite +
    lo que SÍ se puede + redirección a la reserva (no escala, no inventa)."""
    if lang == "es":
        return (
            "Por aquí no manejo un número de teléfono ni WhatsApp 🔒, pero puedo "
            "ayudarte con todo desde este chat: te armo la reserva ahora mismo y, "
            "si lo prefieres, un asesor del equipo te contacta directamente. "
            "¿Seguimos con tu reserva? 🌊"
        )
    return (
        "I don't hand out a phone or WhatsApp number here 🔒, but I can help you "
        "with everything right in this chat: I'll put your booking together now, "
        "and if you prefer, an advisor from the team can reach out to you "
        "directly. Shall we continue with your booking? 🌊"
    )


# A group where NOT everyone shares the same nationality (some Colombian/
# resident, some foreign) — pricing/currency is set per-conversation
# (state.is_colombian), so this is a real gap: not implemented as a feature
# (T013 in docs/archive/test-battery-edge-cases.md). Detect the contradiction
# explicitly instead of letting it fall through to a generic RAG fallback.
_MIXED_NATIONALITY_RE = re.compile(
    r"\bmi\s+(?:amig[oa]|parej[ao]|espos[oa]|hij[oa]|herman[oa]|novi[oa])\s+es\s+extranjer[oa]\b"
    r"|\bmi\s+(?:amig[oa]|parej[ao]|espos[oa]|hij[oa]|herman[oa]|novi[oa])\s+es\s+colombian[oa]\b"
    r"|\b(?:unos?|algunos?)\s+(?:somos\s+|son\s+)?colombian[oa]s?\s+y\s+(?:otros?|l[oa]s?\s+demas)\s+extranjer[oa]s?\b"
    r"|\bnacionalidad\s+mixta\b"
    r"|\bparte\s+del\s+grupo\s+es\s+extranjer[oa]\b"
    r"|\bsolo\s+yo\s+soy\s+(?:colombian[oa]|extranjer[oa])\b"
    # "dos de nosotros somos colombianos pero uno es extranjero" (hallazgo en
    # vivo, batería sintética contra PRE, 2026-08-26, lote 5, portado de
    # pre_gadea v0.21.14) — cantidad explícita + "pero"/"y" en vez del
    # "unos/algunos... y otros" ya cubierto arriba. Cubre ambos órdenes
    # (colombiano-primero / extranjero-primero).
    r"|\b(?:\d+|dos|tres|cuatro|cinco)\s+(?:de\s+(?:nosotros|el\s+grupo)\s+)?somos\s+colombian[oa]s?\s+"
    r"(?:pero|y)\s+(?:\d+|el\s+resto|otr[oa]s?|un[oa])\s*(?:es|son|somos)?\s*extranjer[oa]s?\b"
    r"|\b(?:\d+|dos|tres|cuatro|cinco)\s+(?:de\s+(?:nosotros|el\s+grupo)\s+)?somos\s+extranjer[oa]s?\s+"
    r"(?:pero|y)\s+(?:\d+|el\s+resto|otr[oa]s?|un[oa])\s*(?:es|son|somos)?\s*colombian[oa]s?\b"
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


def _booking_change_response(state: ConversationState, message: str, kind: str) -> str:
    """Copy + efecto de estado compartido para cancelación/reprogramación (Bloque
    2.1): texto de política de la KB + oferta asesor/menú + botones + historial.
    `kind` ∈ {"cancellation", "reschedule"}. Extraído (Fase 2.3) para que el nodo
    `changes` del grafo y la cascada usen una única fuente de copy/estado — sin
    duplicar los strings (garantiza la equivalencia por construcción)."""
    policy_text = (load_policies().get("policies", {}).get(kind) or {}).get(state.language, "")
    if kind == "cancellation":
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
    else:  # reschedule
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
    state.history.append({"role": "user", "content": message})
    state.history.append({"role": "assistant", "content": response})
    return response


# Verbs the LLM uses when offering to hand the user off ("te paso con un asesor",
# "contactes a un asesor", "connect you with an advisor"...). The exact phrasing
# varies run to run, so we anchor on advisor-noun + offer-verb + a question
# rather than fixed phrases.
_ADVISOR_OFFER_VERBS = (
    "pasar", "pase ", "paso ", "pasart", "contact", "conect", "hablar",
    "connect", "speak", "reach out", "put you in touch", "get you in touch",
)




LANGUAGE_SELECTION_KEYWORDS = {
    "1", "2", "es", "en", "español", "espanol", "spanish", "english",
}

GREETING_ONLY_KEYWORDS = {
    "hola", "hello", "hi", "buenas", "buenos dias", "buenos días",
    "buenas tardes", "buenas noches", "hey",
}

# --------------------------------------------------------------------------- #
# New-scenario memory reset (owner decision, 2026-07-20)
#
# A brand-new Chatwoot conversation already starts with empty memory. But within
# the SAME conversation, if the customer greets AND introduces a clearly new
# scenario (a new person/booking) while old memory is still around, that stale
# summary/facts/notes/slots would bleed into the new case. We reset ONLY in that
# narrow situation. Conservative on purpose (favors false-negatives): a bare
# "hola" mid-booking, or a greeting without a fresh self-introduction, does NOT
# reset — the customer usually greets and keeps going on the same reservation.
# --------------------------------------------------------------------------- #
_GREETING_START_RE = re.compile(
    r"^\s*[¡!]*\s*(?:hola|buenas|buenos\s+d[ií]as|buenas\s+tardes|buenas\s+noches|"
    r"hey|hi|hello|hey\s+there)\b",
    re.IGNORECASE,
)
# A fresh self-introduction — the strong signal that this is a new person/case.
# Name detection is CASE-SENSITIVE on purpose: "soy Sofía" (a capitalized name)
# is a new-person intro, but "soy certificado" (lowercase adjective) is a normal
# mid-booking answer and must NOT trigger a reset.
_NAME_INTRO_RE = re.compile(
    r"\bsoy\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
    r"|\bI'?m\s+[A-Z][a-z]+|\bI\s+am\s+[A-Z][a-z]+"
)
_INTRO_PHRASE_RE = re.compile(
    r"\bme\s+llamo\b|\bmi\s+nombre\s+es\b|\bmy\s+name\s+is\b"
    r"|\bsomos\s+\d|\bwe\s+are\s+\d",
    re.IGNORECASE,
)


def _has_accumulated_memory(state: ConversationState) -> bool:
    """True if the conversation already carries meaningful memory that would
    bleed into a new scenario if not cleared."""
    facts = state.remembered_facts or {}
    return bool(
        state.conversation_summary
        or any(v for v in facts.values())
        or state.is_certified is not None
        or getattr(state, "location", None)
        or getattr(state, "detected_group_size", None)
        or getattr(state, "mixed_cart", None)
        or len(state.history or []) >= 4
    )


def _is_new_scenario_restart(message: str, state: ConversationState) -> bool:
    """True only when the message greets AND introduces a clearly new scenario
    (self-introduction) while the conversation already holds accumulated memory.
    Deliberately narrow to never wipe legitimate mid-booking context."""
    if not (message and _GREETING_START_RE.match(message)):
        return False
    if not (_NAME_INTRO_RE.search(message) or _INTRO_PHRASE_RE.search(message)):
        return False
    # Needs some substance beyond "hola soy X" — a real new-scenario message.
    if len(message.strip()) < 25:
        return False
    return _has_accumulated_memory(state)


def _reset_to_fresh_scenario(state: ConversationState) -> None:
    """Wipe ALL conversation memory (summary, facts/notes, history, cart, every
    detected_* slot, adaptive context, step) while keeping only the stable
    identity: conversation_id and the already-detected language. Future-proof —
    resets to a fresh ConversationState's defaults, so new fields are covered
    automatically."""
    fresh = ConversationState(conversation_id=state.conversation_id, language=state.language)
    state.__dict__.update(fresh.__dict__)

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
        "nieto", "nieta", "nietos", "nietas",
        "bebe", "bebes",
        "kid", "kids", "child", "children",
        "grandchild", "grandchildren", "grandson", "granddaughter",
        "baby", "babies",
    }
    if tokens & kids_keywords:
        return True

    kids_patterns = (
        r"\bmi\s+(hij[oa]|sobrin[oa]|nin[oa]|niet[oa]|bebe)\b",
        r"\bmis\s+(hij[oa]s|sobrin[oa]s|nin[oa]s|niet[oa]s)\b",
        r"\bmi\s+familia\s+con\s+(hij[oa]s|nin[oa]s|menores)\b",
        r"\bmy\s+(grandchild|grandson|granddaughter|baby|kid|child)\b",
        r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+(hij[oa]s|nin[oa]s|sobrin[oa]s|menores)\b",
    )
    return any(re.search(pattern, normalized) for pattern in kids_patterns)




































































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
        "label": cart_render.cart_label_for(item_type, plan, lang),
    })




















































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


def _has_link_tech_context(message: str, state_history: list[dict] | None = None) -> bool:
    """True si el mensaje nombra un medio técnico (link/página/botón/pago/web...)
    o el bot acaba de enviar una URL. Backstop determinista para el respaldo LLM
    de link roto: sin este contexto, "no me funciona el buceo nocturno" (una
    queja de ACTIVIDAD, no de link) disparaba un falso positivo pese al ejemplo
    negativo en el prompt (el sesgo de escalar-ante-la-duda sobre-dispara)."""
    msg_lower = " ".join(message.strip().lower().split())
    if any(re.search(r"\b" + re.escape(tok) + r"\b", msg_lower) for tok in BROKEN_LINK_TARGET_TOKENS):
        return True
    if state_history:
        for entry in reversed(state_history):
            if entry.get("role") == "assistant":
                content = (entry.get("content") or "").lower()
                return "http://" in content or "https://" in content
    return False


def _broken_link_escalation_response(state: ConversationState, message: str) -> str:
    """Respuesta única para una queja de link/página/pago roto: avisa al equipo
    + escala a un asesor que confirma el paso o reenvía el link correcto.
    Compartida entre el fast-path por keyword y el respaldo LLM
    (`broken_link_complaint`), para no duplicar el copy ni el efecto de estado."""
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


def _infer_language(message: str, fallback: str = "es") -> str:
    # Verificado en vivo (2026-08-26, al validar el fix de idioma en el
    # bloque de cancelación, portado de pre_gadea): el padding literal
    # `f" {hint} "` fallaba con puntuación pegada al hint — "cancel my
    # booking, something came up" tiene "booking," (coma sin espacio), así
    # que " booking " nunca matcheaba y el mensaje entero se clasificaba
    # como español por defecto. `\b` (límite de palabra real, ciego a la
    # puntuación adyacente) es el criterio correcto.
    normalized = message.strip().lower()
    english_matches = sum(
        1 for hint in ENGLISH_HINTS if re.search(rf"\b{re.escape(hint)}\b", normalized)
    )
    spanish_matches = sum(
        1 for hint in SPANISH_HINTS if re.search(rf"\b{re.escape(hint)}\b", normalized)
    )
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

    # Resumen progresivo de la conversación (Fase B, ver
    # docs/archive/memory-context-improvement-plan.md): cubre detalles mencionados
    # hace muchos turnos que ya salieron de la ventana cruda de mensajes
    # recientes que usan rag_agent.py/orchestrator.py.
    if state.conversation_summary:
        if state.language == "es":
            parts.append(f"Resumen de la conversación hasta ahora: {state.conversation_summary}")
        else:
            parts.append(f"Summary of the conversation so far: {state.conversation_summary}")

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
            for k, v in facts.items() if v and k != "notes"
        ]
        if lines:
            header = (
                "El cliente ya ha dicho lo siguiente (tenlo en cuenta, no lo repreguntes): "
                if state.language == "es"
                else "The customer already told us the following (use it, don't re-ask): "
            )
            parts.append(header + "; ".join(lines) + ".")

        # "notes" (Fase C) es una lista abierta, no un único valor — se
        # renderiza aparte como viñetas en vez de aplanarla en la frase de
        # arriba (que asume un valor por clave).
        notes = facts.get("notes") or []
        if notes:
            header = (
                "Otros detalles que el cliente ya mencionó (tenlos en cuenta, no los ignores):"
                if state.language == "es"
                else "Other details the customer already mentioned (keep these in mind, don't ignore them):"
            )
            parts.append(header + "\n" + "\n".join(f"- {n}" for n in notes) + "\n")

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
            from src.flows.catalog import MULTI_DAY_SERVICES, SERVICES

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
            from src.flows.catalog import SERVICES

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
            from src.flows.catalog import SERVICES

            seen_service_ids: set[str] = set()
            for item in cart:
                cart_service_id = cart_render.cart_service_id(
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


_AGE_NUMBER_HINT = re.compile(r"\b\d{1,2}\b")
_AGE_PERSON_REF = re.compile(
    r"\b(mi\s+\w+|hij[oa]s?|niñ[oa]s?|nin[oa]s?|él|ella|ellos|ellas|"
    r"my\s+\w+|son|daughter|kids?|child(?:ren)?|he|she|they)\b",
    re.IGNORECASE,
)


def _looks_like_age_eligibility_question(message: str, state: ConversationState) -> bool:
    """Predicado PURO (read-only) para el router (Fase 2.4, cierre del hueco
    "patrón A" del audit §1.5): aproxima cuándo disparará
    `_maybe_answer_age_eligibility` SIN correr el intent detector ni mutar estado.

    Cue de elegibilidad + o bien un número de 1-2 dígitos plausible como edad, o
    bien una edad ya recordada (`state.detected_ages`) junto a una referencia a
    persona (caso multi-turno). El nodo `info` reproduce la lógica exacta y delega
    en la cascada si no dispara, así que sobre-disparar aquí es seguro (se
    autocorrige); quedarse corto solo mantiene el comportamiento actual (→ booking)
    para ese mensaje concreto, sin regresión."""
    if not _AGE_ELIGIBILITY_CUE.search(message):
        return False
    if _AGE_NUMBER_HINT.search(message):
        return True
    return bool(state.detected_ages) and bool(_AGE_PERSON_REF.search(message))


def _maybe_answer_age_eligibility(message: str, state: ConversationState) -> str | None:
    """Deterministic answer to an age-eligibility question.

    Fires only when the message both mentions a concrete age and reads like an
    eligibility question, so it never hijacks a plain booking phrase like
    "reservar para mi hijo de 14". Returns None otherwise.
    """
    if not _AGE_ELIGIBILITY_CUE.search(message):
        return None
    # NOTE (robustness review H4, deferred): LLM cutover not wired here for the
    # same reason as _apply_group_recomposition — this is a pre-dispatch
    # short-circuit; wiring it would double the LLM call on fall-through. See that
    # function's note.
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


# Cap on state.remembered_facts["notes"] (Fase C) — keeps the most recent
# entries so the list doesn't grow unbounded over a very long conversation.
_MAX_REMEMBERED_NOTES = 8


# Per-domain cutover field sets (docs/robustness/plan.md §4). Each domain has
# its own kill-switch flag (plan.md principle #7); a field is only applied from
# the LLM patch if its domain's flag is on. Fase 1 = certification, Fase 2 =
# group/quantity/ages. Future phases add their own entry here.
_CERTIFICATION_CUTOVER_FIELDS = {"is_certified", "activity"}
_GROUP_CUTOVER_FIELDS = {"group_size", "group_allocation", "ages"}
_LOCATION_CUTOVER_FIELDS = {"location", "island", "hotel"}
_LOGISTICS_CUTOVER_FIELDS = {"is_colombian", "duration", "last_dive_over_2_years"}


def _active_cutover_fields() -> set[str]:
    """Union of the cutover field sets whose per-domain flag is currently on.
    Empty when every domain flag is off (the default everywhere) — in that case
    the cutover is a no-op and never calls the LLM."""
    active: set[str] = set()
    if settings.llm_extraction_cutover_certification:
        active |= _CERTIFICATION_CUTOVER_FIELDS
    if settings.llm_extraction_cutover_group:
        active |= _GROUP_CUTOVER_FIELDS
    if settings.llm_extraction_cutover_location:
        active |= _LOCATION_CUTOVER_FIELDS
    if settings.llm_extraction_cutover_logistics:
        active |= _LOGISTICS_CUTOVER_FIELDS
    return active


def _log_safe_message(message: str, limit: int = 500) -> str:
    """Message text for [EXTRACT] log lines. Real bug found live (2026-07-21):
    truncating to 60 chars (as this used to) silently cut off the end of real
    customer messages, so candidates harvested by
    scripts/harvest_cutover_logs.py for the eval-set (Fase 6, bucle de datos
    reales) reproduced a DIFFERENT, truncated message — the opposite of what
    that tool needs. 500 chars comfortably covers real chat messages; only
    pathologically long ones get cut, and are marked with "…[truncated]" so
    it's never silently ambiguous.
    """
    if len(message) <= limit:
        return message
    return message[:limit] + "…[truncated]"


async def _maybe_apply_llm_extraction_cutover(
    message: str, regex_intent: DetectedIntent, state: ConversationState
) -> None:
    """Per-domain real cutover (docs/robustness/plan.md §4). Gated by the
    per-domain flags (`llm_extraction_cutover_certification` for Fase 1,
    `llm_extraction_cutover_group` for Fase 2 — all off by default everywhere).
    When at least one domain is on, and the regex left one of that domain's
    fields unresolved, asks the LLM gap-filler ONCE and — unlike the Fase 0
    shadow probe — actually MUTATES `regex_intent` in place, but ONLY for fields
    belonging to an enabled domain (any other field the LLM returns is
    discarded and stays shadow-only until its own domain's Fase N is cut over).
    A single LLM call covers every enabled domain at once (plan.md §3.3, cost/
    latency control). Must run BEFORE `_apply_detected_intent(intent, state)` so
    the filled values propagate to conversation state normally.

    The regex is still the primary/fast path: this only fills a genuine gap,
    never overrides a value the regex already resolved. Any error degrades
    silently to "regex-only", exactly like today — this can never make a reply
    worse than before the cutover existed.
    """
    active_fields = _active_cutover_fields()
    if not active_fields:
        return
    try:
        relevant_gaps = [f for f in missing_fields(regex_intent) if f in active_fields]
        if not relevant_gaps:
            return
        patch = await fill_gaps(message, regex_intent, history=state.history, lang=state.language)
        # Auditoría Fase B (2026-07-23): este cutover de extracción (gated por
        # LLM_EXTRACTION_CUTOVER_*) es el equivalente de la Capa 5 del núcleo
        # conversacional — y le faltaba el mismo saneamiento
        # que Gadea añadió allí (commit d3ecdba): con el historial real de la
        # conversación por delante, `fill_gaps` puede alucinar un
        # group_allocation/group_size completo para un mensaje de "se añade un
        # acompañante" sin ningún número real (p. ej. "también vienen mis
        # amigos a hacer snorkel" → {snorkel: 3} inventado). `LLM_EXTRACTION_
        # CUTOVER_GROUP` está en `"true"` en `docker-compose.vps.yml` (PRE), así
        # que este camino SÍ se ejecuta en producción, no es solo teórico.
        # Mismos regexes que `conversational_core._understand()` (import
        # perezoso: evita el ciclo módulo-a-módulo, mismo patrón ya usado en
        # este fichero para `conversational_core.maybe_handle_turn`).
        from src.agents.conversational_core import _ADDED_PERSON_RE, _EXPLICIT_NUMBER_RE
        if _ADDED_PERSON_RE.search(message) and not _EXPLICIT_NUMBER_RE.search(message):
            patch.pop("group_allocation", None)
            patch.pop("group_size", None)
        # Apply ONLY fields that were an actual gap in an enabled domain — never a
        # field the regex already resolved (fill_gaps guards this too, but the
        # cutover enforces the "never overwrite regex" property itself as well).
        applied = {k: v for k, v in patch.items() if k in relevant_gaps}
        for field, value in applied.items():
            setattr(regex_intent, field, value)
            if field not in regex_intent.detected_fields:
                regex_intent.detected_fields.append(field)
        if applied:
            logger.info(f"[EXTRACT][CUTOVER] applied={applied} msg={_log_safe_message(message)!r}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[EXTRACT][CUTOVER] failed, degrading to regex-only (ignored): {exc}")


async def _maybe_log_llm_extraction_shadow(
    message: str, regex_intent: DetectedIntent, state: ConversationState
) -> None:
    """Fase 0 shadow-mode measurement (docs/robustness/plan.md §4). Gated by
    `settings.llm_extraction_shadow_mode` (off by default everywhere) — when
    on, runs the LLM gap-filler in parallel and logs what it WOULD have added,
    purely for measuring agreement. Never mutates state, never affects the
    reply. Any exception here is swallowed — this is a measurement probe, not
    part of the response path, and must never be able to break a real turn.
    """
    if not settings.llm_extraction_shadow_mode:
        return
    try:
        gaps_before = missing_fields(regex_intent)
        if not gaps_before:
            return
        patch = await fill_gaps(message, regex_intent, history=state.history, lang=state.language)
        # No live ground truth to compare against here — this just records
        # what the LLM would have added on top of the regex result, for a
        # human to review later (or feed into docs/robustness/eval-set.json
        # as a new case if it looks like a real gap the regex should cover).
        logger.info(
            f"[EXTRACT][SHADOW] msg={_log_safe_message(message)!r} gaps_before={gaps_before} llm_patch={patch}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[EXTRACT][SHADOW] probe failed (ignored): {exc}")


# Cue de CORRECCIÓN explícita de un dato ya fijado ("en realidad revisamos y
# somos 4", "perdón, en realidad somos 3", "me equivoqué, somos 2",
# "actually we're 4"/"sorry, we're actually 3") — a diferencia de
# `_GROUP_RECOMPOSE_RE` (código legacy nunca conectado al núcleo actual),
# esta NO exige que "en realidad" preceda INMEDIATAMENTE a "somos": tolera
# relleno intermedio ("revisamos y", "lo pensamos y", "checamos y") —
# hallazgo en vivo (batería sintética contra PRE, 2026-08-26, lote 4,
# portado de pre_gadea v0.21.11) de que el fraseo real de una corrección
# casi nunca es tan limpio. Deliberadamente estrecho (exige el cue léxico
# explícito) para no convertir `detected_group_size` en escribible en
# cualquier mensaje — un número suelto sin este cue nunca lo sobreescribe.
_GROUP_SIZE_CORRECTION_CUE_RE = re.compile(
    r"\b(?:en\s+realidad|realmente|perd[oó]n|me\s+equivoqu[eé]|corrijo|"
    r"en\s+verdad|actually|sorry|my\s+mistake|i\s+made\s+a\s+mistake)\b",
    re.IGNORECASE,
)


def _apply_detected_intent(intent, state: ConversationState, message: str | None = None) -> None:
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
    elif (
        intent.group_size
        and intent.group_size != state.detected_group_size
        and message
        and _GROUP_SIZE_CORRECTION_CUE_RE.search(message)
    ):
        logger.info(
            f"[INTENT] Group size CORRECTED: {state.detected_group_size} -> {intent.group_size}"
        )
        state.detected_group_size = intent.group_size

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


_INTENT_TRIGGER_STEPS = {
    Step.WELCOME,
    Step.LANGUAGE,
    Step.MAIN_MENU,
}


def _should_skip_to_certified_flow(intent, state: ConversationState) -> bool:
    return (
        intent.activity == "certified_diving"
        and intent.is_certified is True
        and state.step in _INTENT_TRIGGER_STEPS
    )


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


async def route_message(state: ConversationState, message: str) -> str:
    """Public entry point. Delegates to the actual routing logic, then
    updates the rolling conversation summary (Fase B, see
    docs/archive/memory-context-improvement-plan.md) once per turn — a thin wrapper
    so the summary check runs regardless of which internal branch below
    handled the message, without threading it through every early return.

    Strangler-fig (Fase 1.4, docs/multi-agent-refactor-plan.md): con
    `settings.agent_arch` ON el turno pasa por el grafo LangGraph
    (`orchestration.graph` — router → 5 nodos-agente reales + subgrafo booking);
    OFF, la cascada directa (`_route_message_inner`), que los nodos reales
    conservan como handler compartido de fallback + tail post-núcleo. El flag es
    la red de rollback hasta que el grafo tenga confianza en producción.
    """
    if settings.agent_arch:
        from src.orchestration.graph import run_turn_via_graph
        response = await run_turn_via_graph(state, message)
    else:
        response = await _route_message_inner(state, message)
    await conversation_summarizer.maybe_update_summary(state)
    return response


async def _route_message_inner(
    state: ConversationState, message: str, routing_signals: dict | None = None
) -> str:
    """
    Supervisor: decides how to handle each incoming message.

    Routing rules (no LLM call):
    1. If user is in a menu step AND sends a number -> decision tree
    2. If user sends a menu/back keyword -> reset to main menu
    3. If user sends an escalation keyword -> escalate
    4. If user is in SUMMARY/ESCALATE/FREE_TEXT step -> RAG agent
    5. If user sends free text while in a menu step -> RAG agent

    `routing_signals`: si viene dado (grafo LangGraph, Fase 1 — el nodo router
    ya calculó `detect_routing_signals` una vez por turno), se reutiliza en vez
    de recomputar la llamada LLM. None (todos los callers legacy) = se calcula
    internamente igual que siempre (comportamiento idéntico).
    """
    msg_lower = message.strip().lower()

    # New-scenario restart: greeting + fresh self-introduction while old memory
    # is around → wipe it and reprocess this message as a fresh first turn, so
    # the previous booking's summary/facts/notes/slots don't bleed in. Narrow by
    # design (see _is_new_scenario_restart); a bare "hola" never triggers it.
    if _is_new_scenario_restart(message, state):
        logger.info("[SUPERVISOR] New-scenario restart -> wiping conversation memory")
        _reset_to_fresh_scenario(state)
        return await _route_message_inner(state, message)

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

    # Hallazgo (batería sintética contra PRE, 2026-08-26, lote 4, portado de
    # pre_gadea v0.21.11): "¿puedo tomarme una cerveza antes de bucear?" y
    # "soy alérgico a los mariscos, es un problema?" escalaban como
    # `medical_questions` — el LLM de sensitive_topic los interpreta como un
    # tema médico/de sustancias, pero son preguntas de POLÍTICA plana con
    # respuesta ya conocida en el catálogo (`no_alcohol_policy`,
    # `food_policy`: veganos/vegetarianos/celíacos reciben arroz con
    # vegetales, cualquier alergia alimentaria se avisa antes del tour).
    # Escalar es peor que responder: le hace perder tiempo al cliente por
    # algo que el bot ya sabe con certeza. Se comprueba ANTES de cualquier
    # gate de seguridad (misma prioridad que el link roto) para no dejar
    # que ninguno de los dos se adelante. Acotado a mención EXPLÍCITA de un
    # alérgeno alimentario conocido del catálogo (marisco/gluten/nueces/
    # maní/lactosa) — una alergia sin ese contexto ("tengo alergias
    # severas, es peligroso bucear?") sigue yendo al escalado médico
    # normal, sin tocar.
    if _ALCOHOL_BEFORE_DIVING_RE.search(msg_lower):
        policy_text = (load_policies().get("policies", {}).get("no_alcohol_policy") or {}).get(
            state.language, ""
        )
        logger.info("[SUPERVISOR] Alcohol-before-diving question -> real no_alcohol_policy, not medical escalation")
        return policy_text
    if _ALLERGY_WORD_RE.search(msg_lower) and _FOOD_ALLERGEN_RE.search(msg_lower):
        policy_text = (load_policies().get("policies", {}).get("food_policy") or {}).get(
            state.language, ""
        )
        logger.info("[SUPERVISOR] Food-allergy question -> real food_policy, not medical escalation")
        return policy_text

    # SAFETY FIRST: broken-link complaints and sensitive topics (medical,
    # weather, complaints) must escalate BEFORE the intent detector runs.
    # Otherwise a message like "Estoy embarazada, puedo bucear?" gets hijacked
    # by the booking intent ("bucear") and routed into the cart flow instead of
    # being handed to human staff. Broken-link runs before sensitive on purpose
    # (see the note at the original sensitive block below).
    if _detect_broken_link_complaint(message, state.history):
        return _broken_link_escalation_response(state, message)

    # Red de precisión (auditoría 2026-07-22/23): ESCALATION_KEYWORDS/
    # MENU_KEYWORDS/BACK_KEYWORDS/SENSITIVE_RULES/_ADAPTIVE_DIVING_PATTERN son
    # listas cerradas de palabras exactas — probado en vivo que NO reconocen
    # variantes regionales reales ("estoy embarazadita", "soy epiléptica",
    # "tengo una condición cardiaca" en femenino, "ataque de pánico", "perdí
    # una pierna", "uso prótesis"). Calculado ANTES del chequeo de keywords
    # (no después, como en la versión anterior) porque hace falta para
    # resolver una colisión real entre categorías: "accidente" es palabra
    # clave de SENSITIVE_RULES (queja/emergencia) pero también aparece en
    # backstories de discapacidad ("perdí una pierna en un accidente") que
    # deben ir a DIVE TO HEAL, no a un escalado médico genérico de urgencia.
    # Gasto cero para clics de botón puramente numéricos (nunca pueden
    # expresar un tema sensible/escalado/menú en ningún idioma). A diferencia
    # del extractor de reserva, el sesgo aquí es escalar/enrutar de más que
    # de menos — el propio prompt se lo pide al LLM.
    if routing_signals is None:
        routing_signals = {} if msg_lower.isdigit() else await detect_routing_signals(message, lang=state.language)

    # Respaldo LLM del gate de LINK ROTO (Bloque 2.3): el detector por keyword
    # de arriba exige frase-de-queja + token de link (o URL en el turno previo)
    # — medido en vivo que 10 de 10 quejas realistas se escapaban ("el link no
    # me deja pagar", "me sale página en blanco", "le doy al botón y no pasa
    # nada", "the payment page crashes"). La señal `broken_link_complaint`
    # (misma llamada de routing, sin coste extra) las recupera. Se coloca justo
    # tras calcular las señales y antes del bloque sensible, manteniendo la
    # prioridad "safety first" del gate por keyword de más arriba.
    if routing_signals.get("broken_link_complaint") and _has_link_tech_context(message, state.history):
        return _broken_link_escalation_response(state, message)

    sensitive_escalation_early = (
        None if routing_signals.get("adaptive_diving_topic")
        else detect_sensitive_escalation(message, state.language)
    )
    if sensitive_escalation_early:
        reason, response = sensitive_escalation_early
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.info(f"[SUPERVISOR] Sensitive escalation triggered (early) reason={reason}")
        return response

    if routing_signals.get("sensitive_topic"):
        found = sensitive_response_for(routing_signals["sensitive_topic"], state.language)
        if found:
            reason, response = found
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = reason
            state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Sensitive escalation triggered (LLM signal, early) reason={reason}")
            return response

    # Booking cancellation/reschedule requests: inform the policy text from
    # the KB and let the customer choose between talking to an advisor or
    # going back to the main menu, instead of the bot deciding on its own.
    # La lista de keywords (`_detect_cancellation_request`) solo caza frases
    # casi exactas — medido en vivo (2026-07-23) que 16 de 18 frases realistas
    # de cancelación/reprogramación (indirectas, jerga, typos, ES+EN) se
    # escapaban. Respaldo LLM `booking_change_topic` en la MISMA llamada
    # `detect_routing_signals` de arriba (sin coste extra), estricto como
    # wants_human (una pregunta por la política NO lo dispara). Mismo patrón
    # que DIVE TO HEAL (v0.20.58).
    if _detect_cancellation_request(msg_lower) or (
        routing_signals.get("booking_change_topic") == "cancellation"
        and not _in_active_cart_building(state)
    ):
        logger.info("[SUPERVISOR] Cancellation request detected -> policy info + escalate/home buttons")
        return _booking_change_response(state, message, "cancellation")

    if _detect_reschedule_request(msg_lower) or (
        routing_signals.get("booking_change_topic") == "reschedule"
        and not _in_active_cart_building(state)
    ):
        logger.info("[SUPERVISOR] Reschedule request detected -> policy info + escalate/home buttons")
        return _booking_change_response(state, message, "reschedule")

    # Deflexión (Bloque 2.2): petición de número/WhatsApp/correo o vía de
    # contacto directa. El bot no da un número (política); en vez de escalar o
    # dar el fallback evasivo, deflexión honesta: límite 🔒 + lo que SÍ puede +
    # redirige a la reserva. Keyword fast-path + respaldo LLM (misma llamada de
    # routing de arriba, sin coste extra), estricto. Se coloca ANTES del escalado
    # genérico para ser consistente (hoy a veces escalaba, a veces caía a RAG).
    # Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 4/hallazgo B,
    # portado de pre_gadea): este bloque (y el de dominio blindado, justo
    # debajo) corren ANTES de que `maybe_handle_turn` haga su detección de
    # idioma de apertura — en el PRIMER mensaje, `state.language` sigue en
    # su valor por defecto ("es"), así que "can you give me your whatsapp
    # number" (inglés) recibía la deflexión en español. `_infer_language`
    # es una heurística barata (sin LLM) — se usa aquí solo como mejor
    # estimación local para ESTA respuesta puntual, sin tocar
    # `state.language` de forma permanente.
    if _asks_for_contact_number(msg_lower) or routing_signals.get("asks_for_contact_number"):
        effective_lang = state.language if state.detected_language else _infer_language(message, state.language)
        response = _contact_number_deflection(effective_lang)
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        logger.info("[SUPERVISOR] Contact-number request -> deflection (limit + redirect, no escalation)")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    # Dominio blindado (Bloque 2.4): pregunta meta sobre qué IA/modelo/bot es.
    # No se revela nada (el prompt de RAG endurecido ya lo prohíbe); se responde
    # en persona (Coral) y se reconduce al buceo, en vez del fallback evasivo.
    if _asks_about_ai_identity(msg_lower):
        effective_lang = state.language if state.detected_language else _infer_language(message, state.language)
        response = _ai_identity_deflection(effective_lang)
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        logger.info("[SUPERVISOR] AI/model-identity meta-question -> in-persona redirect (no reveal)")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    # Mixed-nationality group (some Colombian/resident, some foreign) — not
    # implemented as a feature: pricing/currency is set once per conversation.
    # Answer honestly instead of falling through to a generic RAG fallback
    # (T013 in docs/archive/test-battery-edge-cases.md).
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
    age_answer = _maybe_answer_age_eligibility(message, state)
    if age_answer is not None:
        logger.info("[SUPERVISOR] Age-eligibility question answered deterministically")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": age_answer})
        return age_answer

    # Adaptive diving / DIVE TO HEAL. The topic is detected per-turn by keyword,
    # but must be REMEMBERED: a follow-up like "¿cuánto cuesta?" carries no
    # disability word, so without a persisted flag it fell through to the
    # generic price handler (dumping Cartagena prices and losing the thread —
    # the reported bug). So we (1) persist the context, and (2) route price/
    # booking follow-ups within it to a coherent advisor answer (no generic
    # prices), while non-price questions still get the program's factual info.
    # + red de precisión LLM (auditoría 2026-07-23): _ADAPTIVE_DIVING_PATTERN es
    # una lista cerrada que no reconoce amputación, prótesis, párkinson, lesión
    # medular, sordomuda, "no vidente"... routing_signals ya se calculó arriba
    # (mismo turno, sin llamada extra) y trae adaptive_diving_topic cuando la
    # lista de palabras no encontró nada.
    adaptive_now = bool(_ADAPTIVE_DIVING_PATTERN.search(message)) or bool(routing_signals.get("adaptive_diving_topic"))
    if adaptive_now:
        state.adaptive_diving_context = True

    if (
        state.adaptive_diving_context
        and _PRICE_OR_BOOKING_Q.search(message)
    ):
        logger.info("[SUPERVISOR] DIVE TO HEAL price/booking -> advisor (no generic prices)")
        # Advance out of WELCOME/LANGUAGE so a following "sí" is handled by the
        # bare-affirmation-accepts-advisor branch (which gates on MAIN_MENU).
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            state.step = Step.MAIN_MENU
        answer = _adaptive_diving_advisor_answer(state.language)
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": answer})
        return answer

    if adaptive_now:
        logger.info("[SUPERVISOR] Adaptive-diving/DIVE TO HEAL question -> RAG")
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            state.step = Step.MAIN_MENU
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Núcleo conversacional de slot-filling (docs/archive/conversational-refactor-plan.md).
    # Es el único camino de enrutado desde Fase 4. Corre DESPUÉS del gating de
    # seguridad de arriba (PII, sensibles, cancelación, DIVE TO HEAL, edad).
    # Devuelve None solo para las clases que deben seguir en los handlers
    # deterministas de abajo (keywords de escalado / menú / volver).
    from src.agents import conversational_core
    core_response = await conversational_core.maybe_handle_turn(
        state, message, routing_signals=routing_signals
    )
    if core_response is not None:
        # El núcleo mezcla reserva (slot-fill) e info (RAG interno); ambas mapean
        # a BOOKING en el router de Fase 1 (la frontera se separa en Fase 3.3).
        return core_response

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
            from src.flows.messages import MESSAGES
            logger.info("[SUPERVISOR] Bare affirmation accepted pending advisor offer -> escalate")
            return MESSAGES["escalate"][state.language]

    # Check for escalation keywords (+ red de precisión LLM, auditoría 2026-07-22)
    if _matches_escalation_keyword(msg_lower) or routing_signals.get("wants_human"):
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "solicitó asesor"
        state.pending_note = build_lead_summary(state, escalation_reason="solicitó asesor")
        from src.flows.messages import MESSAGES
        logger.info("[SUPERVISOR] Escalation triggered by keyword or LLM signal")
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
    #
    # Bloque 2.5 (2026-07-23): ampliado el disparador. El `_AVAILABILITY_PATTERN`
    # solo cazaba "qué días hay disponibles" y no las preguntas de fecha ESPECÍFICA
    # ("¿tienen disponibilidad el sábado?", "¿queda espacio el domingo?", "any spots
    # left saturday?") — medido en vivo que esas caían a RAG y ALUCINABAN una
    # confirmación de cupo ("¡Claro que sí! Tenemos disponibilidad para el sábado").
    # Añadidos `_asks_about_availability` (lista ampliada) y el respaldo LLM
    # `availability_question`, ambos al MISMO handler (conserva el resume mid-cart).
    # `_AVAILABILITY_PATTERN` (el original) va SIEMPRE — no confunde una pregunta
    # de plan multi-día con disponibilidad y los tests de resume mid-cart
    # dependen de él. Las adiciones de Bloque 2.5 (`_asks_about_availability` +
    # señal LLM `availability_question`) NO se aplican mientras se construye la
    # reserva: ahí "no teneis algo para mas dias?" es una pregunta de PLAN que el
    # interceptor multi-día debe manejar, y la señal LLM la marcaba como
    # disponibilidad, pisándolo (regresión: test_multiday_switch_by_text_at_
    # last_dive_step). Fuera del carrito (free-text) sí, para cerrar la
    # alucinación de cupo de fecha específica.
    if (
        _AVAILABILITY_PATTERN.search(msg_lower)
        or (
            (_asks_about_availability(msg_lower) or routing_signals.get("availability_question"))
            and not _in_active_cart_building(state)
        )
        or _CLOSED_DATE_RE.search(msg_lower)
    ) and state.step not in (Step.WELCOME, Step.LANGUAGE):
        # Hallazgo (batería sintética contra PRE, 2026-08-26, conv 395,
        # portado de pre_gadea v0.21.10): "¿abren el 25 de diciembre?"
        # caía en esta misma respuesta genérica ("las salidas son diarias,
        # siempre hay disponibilidad") — FALSA para esos dos días
        # concretos: `policies.json["closed_days"]` dice explícitamente
        # "Solo cerramos el 25 de diciembre y el 1 de enero". Se comprueba
        # ANTES del canned genérico para no darle al cliente información
        # incorrecta sobre un día que sí está cerrado.
        if _CLOSED_DATE_RE.search(msg_lower):
            policy_text = (load_policies().get("policies", {}).get("closed_days") or {}).get(
                state.language, ""
            )
            logger.info("[SUPERVISOR] Closed-date question detected -> real closed_days policy, not canned availability")
            return policy_text
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

    # (Fase 4 P2·paso2, 2026-07-28) Retirados los handlers menú-reset / back /
    # greeting-restart: con el núcleo on (paso 1) "menú"/"volver"/"back"/"hola"
    # son mensaje normal que el núcleo maneja, así que estos bloques eran código
    # muerto — y con ellos se van los DOS únicos callers vivos de
    # `decision_tree.process_message`, lo que habilita borrar el árbol (paso 3).
    # El escalado, la disponibilidad, el idioma y el gating de seguridad siguen.

    # Explicit language-switch request ("in english", "spanish please",
    # "me lo puedes decir en español?", etc.) at any step.
    language_intent = _detect_language_intent(message)
    if language_intent is not None:
        # Idioma/saludo → entrada de reserva (taxonomía §4.bis: greeting → booking).
        from src.flows.messages import MESSAGES
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            # Treat as language selection; advance to MAIN_MENU.
            state.language = language_intent
            state.step = Step.MAIN_MENU
            set_quick_replies(state, "main_menu")
            logger.info(f"[SUPERVISOR] Language intent at start -> lang={language_intent}")
            return MESSAGES["main_menu"][language_intent]
        if state.language != language_intent:
            # Mid-conversation switch: acknowledge in new language and re-show main menu.
            state.language = language_intent
            state.step = Step.MAIN_MENU
            set_quick_replies(state, "main_menu")
            ack = (
                "¡Listo! Sigamos en español. "
                if language_intent == "es"
                else "Got it! Continuing in English. "
            )
            logger.info(f"[SUPERVISOR] Language switch mid-conversation -> lang={language_intent}")
            return ack + MESSAGES["main_menu"][language_intent]

    # Núcleo = único camino (Fase 4): todo mensaje se resuelve arriba — el
    # núcleo (return en el hook), o los handlers de escalado/menú/back. Este
    # fallback defensivo no debería alcanzarse.
    logger.warning(f"[SUPERVISOR] fallthrough inesperado step={state.step.value}")
    from src.flows.messages import MESSAGES
    return MESSAGES["main_menu"][state.language]
