"""Detectores y respuestas de la ruta `safety` (nodo `escalation`, `escalation_agent.py`): link roto, pase a una
persona por posventa o empresa (`_needs_staff_handoff`), precio dentro de DIVE TO HEAL, y el idioma de una
respuesta fija en la apertura (`_reply_language`).

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.lead_summary import build_lead_summary
from src.agents.supervisor import _infer_language
from src.config import settings
from src.flows.state import ConversationState, Step
from src.flows.textos import de_cartagena

logger = logging.getLogger("uvicorn.error")


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
    if _reply_language(state, message) == "es":
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


def _needs_staff_handoff(state: ConversationState, message: str, routing_signals: dict) -> str | None:
    """s4-20 (paso 6, 27-sep): post-venta y trato de empresa -> pase a una persona ANTES del
    nucleo. Jev (`needs_staff`, misma llamada) dice que el mensaje trata de una reserva o un pago ya
    hechos, una agencia, un correo sin contestar o documentos que el staff debe revisar: el bot no ve
    nada de eso. Antes seguia vendiendo ("¿desde dónde saldrías?") o confirmaba lo que no podia ver.
    Devuelve la respuesta del pase, o None.

    r6-2 (flag `datos_ajenos_se_niegan`, decisión de Gadea): si el cliente pide datos de OTROS clientes, la respuesta
    es una negativa de privacidad y NO hay pase (va aquí para que valga en el grafo y en la cascada, que llaman a esta
    misma función en el mismo punto)."""
    if settings.datos_ajenos_se_niegan and routing_signals.get("pide_datos_ajenos") is True:
        logger.info("[SUPERVISOR] pide datos de otros clientes (Jev) -> negativa de privacidad, sin pase")
        state.quick_replies = []
        if _reply_language(state, message) == "es":
            return (
                "No puedo compartir datos de otros clientes (nombres, teléfonos, correos ni reservas): es "
                "información privada y la cuidamos igual que la tuya. 🔒 Si quieres organizar un grupo, cuéntame "
                + de_cartagena("cuántas personas son y qué les gustaría hacer, y les ayudo a armar el plan. 🌊",
                               "cuántas personas sois y qué os gustaría hacer, y os ayudo a armar el plan. 🌊")
            )
        return (
            "I can't share other customers' details (names, phone numbers, emails or bookings): that information is "
            "private and we protect it just like yours. 🔒 If you'd like to put a group together, tell me how many "
            "people you are and what you'd like to do, and I'll help you plan it. 🌊"
        )
    if routing_signals.get("needs_staff") is not True:
        return None
    reason = "post-venta o empresa: lo revisa una persona (reserva/pago ya hechos, agencia, documentos)"
    state.step = Step.ESCALATE
    state.quick_replies = []
    state.pending_escalation_reason = reason
    state.pending_note = build_lead_summary(state, escalation_reason=reason)
    logger.info("[SUPERVISOR] needs_staff (Jev) -> pase a una persona")
    if _reply_language(state, message) == "es":
        return (
            "Esto tiene que revisarlo una persona del equipo, que sí puede ver las reservas, los pagos y los "
            "correos. Te paso ahora con un asesor de Diving Planet y enseguida se pone en contacto contigo. "
            "¡Gracias! 🙌"
        )
    return (
        "This needs to be checked by a person from our team, who can see bookings, payments and emails. "
        "I'm passing you to a Diving Planet advisor now and they'll get in touch with you shortly. Thanks! 🙌"
    )


def _reply_language(state: ConversationState, message: str) -> str:
    """Idioma para una respuesta fija de ESTE turno. Con el idioma ya fijado, ese; en la apertura
    (aun sin fijar), el del mensaje: primero por palabras vacias (`_detect_language_heuristic`, mas
    general) y si no hay senal, por las pistas de `_infer_language`. s4-21 (5): el aviso medico
    salia en espanol a "I completed the medical form, is that ok?"."""
    if state.detected_language:
        return state.language
    from src.flows.catalog import _detect_language_heuristic  # lazy

    lang = _detect_language_heuristic(message) or _infer_language(message, state.language)
    # Se guarda como idioma de la conversacion (sin darlo por detectado: el nucleo lo confirma cuando
    # le llegue un turno). Si no, tras una respuesta fija en la apertura el turno siguiente seguia en
    # espanol ("ah I see." -> menu en espanol, ronda B del paso 5).
    state.language = lang
    return lang
