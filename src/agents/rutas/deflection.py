"""Detectores y respuestas de la ruta `deflection` (`deflection_agent.py`): petición de un número o contacto
directo, y la pregunta de si es un bot o qué IA hay detrás.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.lead_summary import build_lead_summary
from src.config import settings
from src.flows.state import ConversationState, Step
from src.utils.text import strip_accents as _strip_accents

logger = logging.getLogger("uvicorn.error")


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


def pregunta_si_es_ia(msg_lower: str, signals: dict | None) -> bool:
    """¿Pregunta el cliente si habla con un bot o qué IA hay detrás? ex-9b paso 5 (flag `identidad_ia_por_jev`): si
    Jev contesta (`pregunta_si_es_ia`, también en False) manda Jev; el regex solo si Jev calla. El regex contestaba
    "soy Coral, la asistente virtual" a "¿qué modelo de regulador usan?". La usan el router, el nodo y la cascada."""
    from src.agents.jev_router import PREGUNTA_SI_ES_IA

    if settings.identidad_ia_por_jev and signals and PREGUNTA_SI_ES_IA in signals:
        return bool(signals[PREGUNTA_SI_ES_IA])
    return _asks_about_ai_identity(msg_lower)


def _ai_identity_deflection(lang: str) -> str:
    # s4-15: a "¿eres un bot?" se contesta con claridad que es la asistente virtual (golden
    # `es-un-bot`, criterio "honesto"), sin revelar la tecnologia y con la persona a mano.
    if lang == "es":
        return (
            "Sí, soy *Coral*, la asistente virtual de Diving Planet 🐠. Te ayudo con todo lo del buceo, "
            "precios y reservas en las Islas del Rosario, y si en algún momento prefieres hablar con una "
            "persona del equipo, dímelo y te paso. ¿Te ayudo a armar tu salida? 🌊"
        )
    return (
        "Yes, I'm *Coral*, Diving Planet's virtual assistant 🐠. I can help you with diving, prices and "
        "bookings in the Rosario Islands, and if at any point you'd rather talk to a person from the team, "
        "just tell me and I'll pass you over. Shall I help you set up your trip? 🌊"
    )


def _official_whatsapp() -> str | None:
    """El WhatsApp oficial, de la base de conocimiento (`escalation_rules.json`), nunca escrito aqui."""
    from src.knowledge.loader import load_json

    try:
        info = load_json("escalation_rules.json").get("handoff_protocol", {}).get("contact_info", {})
    except Exception:  # noqa: BLE001 — sin el dato, la deflexion de siempre
        return None
    return info.get("whatsapp") or None


def _contacto_pasa_a_persona(state: ConversationState, lang: str) -> str:
    """CAL-E1 (decisión de Gadea del 16-oct, flag `contacto_pasa_a_persona`): el bot no da números de teléfono ni de
    WhatsApp. Ante una petición de número o de hablar con alguien, la conversación se pasa a un asesor, igual que
    `_needs_staff_handoff`: mismo efecto en el estado (paso, nota del lead y motivo) para que el pase sea uno solo.

    Antes (17-sep) se daba el WhatsApp oficial de la base, y el texto le añadía "(solo mensajes, no llamadas)", que la
    base no dice: el juez lo marcaba como invención (cal-03). Ahora no hay número que afirmar."""
    razon = "el cliente pide un número o contacto directo: lo atiende una persona"
    state.step = Step.ESCALATE
    state.quick_replies = []
    state.pending_escalation_reason = razon
    state.pending_note = build_lead_summary(state, escalation_reason=razon)
    logger.info("[SUPERVISOR] petición de contacto -> pase a una persona (decisión de Gadea 16-oct)")
    if lang == "es":
        return (
            "Por aquí no manejo números de teléfono 🔒, pero te paso ahora con un asesor de Diving Planet para que "
            "hable contigo directamente. Enseguida se pone en contacto. ¡Gracias! 🙌"
        )
    return (
        "I don't hand out phone numbers here 🔒, but I'm passing you to a Diving Planet advisor so they can talk to "
        "you directly. They'll get in touch shortly. Thanks! 🙌"
    )


def _contact_number_deflection(lang: str) -> str:
    """Deflexión honesta para una petición de número/contacto directo: límite +
    lo que SÍ se puede + redirección a la reserva (no escala, no inventa).

    s4-14 (paso 6, decision de Gadea del 17-sep que sustituye a la del 20-jul): si lo piden, se
    da el WhatsApp OFICIAL (solo mensajes), sacado de la base de conocimiento."""
    # CAL-E1 (decisión de Gadea del 16-oct, que sustituye a la del 17-sep): esto es un chatbot y NO da números. Si el
    # cliente pide un número o quiere hablar con alguien, la conversación se PASA A UN ASESOR. El texto y el efecto en
    # el estado los pone `_contacto_pasa_a_persona` (una sola puerta); aquí solo queda el caso sin el flag.
    number = None if settings.contacto_pasa_a_persona else _official_whatsapp()
    if number:
        nota = "solo mensajes de WhatsApp, no llamadas" if lang == "es" else "WhatsApp messages only, no calls"
        if lang == "es":
            return (
                f"¡Claro! 😊 Nuestro WhatsApp oficial es *{number}* ({nota}). Y si quieres, aquí mismo te "
                "ayudo con todo: te armo la reserva o te paso con un asesor del equipo. ¿Seguimos? 🌊"
            )
        return (
            f"Sure! 😊 Our official WhatsApp is *{number}* ({nota}). And if you like, I can help you with "
            "everything right here: I'll put your booking together or pass you to an advisor from the team. "
            "Shall we continue? 🌊"
        )
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
