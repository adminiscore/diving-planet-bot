"""Detectores y respuestas de la ruta `changes` (`changes_agent.py`): cancelar, reprogramar o cambiar el número de
personas de una reserva hecha, y las preguntas de disponibilidad que el router manda a esta ruta.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.lead_summary import build_lead_summary
from src.agents.supervisor import _infer_language
from src.domain.politicas import politicas
from src.flows.state import ConversationState, Step
from src.utils.text import strip_accents as _strip_accents

logger = logging.getLogger("uvicorn.error")

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

# Phrases that indicate the customer wants to change the HEADCOUNT of an
# existing booking (add/remove people) — distinct from stating group size
# while a booking is still being built (that's normal booking info, handled
# by the cart interceptors, never this list). Hallazgo G (batería sintética
# contra PRE, 2026-08-26): "ya tengo una reserva hecha, quiero agregar una
# persona más" caía al menú genérico de bienvenida, sin ningún reconocimiento
# — asimetría con cancelación/reprogramación, que sí se reconocían.
MODIFY_BOOKING_PHRASES = {
    # ES
    "agregar una persona a mi reserva", "agregar una persona mas a mi reserva",
    "anadir una persona a mi reserva", "anadir una persona mas a mi reserva",
    "sumar una persona a mi reserva", "sumar a alguien a mi reserva",
    "quitar una persona de mi reserva", "quitar a alguien de mi reserva",
    "eliminar una persona de mi reserva", "restar una persona de mi reserva",
    "cambiar el numero de personas de mi reserva",
    "cambiar la cantidad de personas de mi reserva",
    "modificar el numero de personas de mi reserva",
    "ya tengo una reserva y quiero agregar", "ya tengo una reserva y quiero anadir",
    "ya reserve y quiero agregar", "ya reserve y quiero anadir",
    "ya hice mi reserva y quiero agregar",
    "reserva hecha, quiero agregar", "reserva hecha y quiero agregar",
    "reserva hecha, quiero anadir", "reserva hecha y quiero anadir",
    "reserva hecha, quiero sumar",
    # EN
    "add a person to my booking", "add a person to my reservation",
    "add someone to my booking", "add someone to my reservation",
    "remove a person from my booking", "remove someone from my booking",
    "change the number of people on my booking",
    "change the headcount on my booking",
    "i already booked and want to add", "i already have a booking and want to add",
}


def _detect_cancellation_request(msg_lower: str) -> bool:
    # Accent-insensitive so "cancelar mi reservación" also matches the
    # accent-free phrases; CANCEL_BOOKING_PHRASES are stored without accents.
    normalized = _strip_accents(msg_lower)
    return any(phrase in normalized for phrase in CANCEL_BOOKING_PHRASES)


def _detect_reschedule_request(msg_lower: str) -> bool:
    normalized = _strip_accents(msg_lower)
    return any(phrase in normalized for phrase in RESCHEDULE_BOOKING_PHRASES)


def _detect_modify_booking_request(msg_lower: str) -> bool:
    normalized = _strip_accents(msg_lower)
    return any(phrase in normalized for phrase in MODIFY_BOOKING_PHRASES)


def _jev_changes_date(signals: dict) -> bool:
    """s4-6 (paso 6, 27-sep): Jev dice que el cliente quiere cambiar el DIA. Vale tambien
    con el carrito en construccion (decision del owner: sin reserva pagada, un cambio de fecha va a un
    asesor), a diferencia de `booking_change_topic`, que ahi confunde "hazlo para 3 dias" con
    reprogramar. Banco `scripts/sonda_cambia_fecha.py`: 7/8 cambios, 0/12 falsas."""
    return signals.get("changes_date") is True


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


def _booking_change_response(state: ConversationState, message: str, kind: str) -> str:
    """Copy + efecto de estado compartido para cancelación/reprogramación/
    modificación de headcount (Bloque 2.1 + hallazgo G): texto de política de la
    KB + oferta asesor/menú + botones + historial. `kind` ∈ {"cancellation",
    "reschedule", "modify_headcount"}. Extraído (Fase 2.3) para que el nodo
    `changes` del grafo y la cascada usen una única fuente de copy/estado — sin
    duplicar los strings (garantiza la equivalencia por construcción).

    `effective_lang` (hallazgo G, batería sintética contra PRE, 2026-08-26,
    portado de pre_gadea v0.21.13): en el mensaje de APERTURA
    `state.detected_language` todavía no está fijado — usar `state.language`
    directo hacía que "hi, I need to cancel my booking" cayera en la
    respuesta en español pese a ser el primer mensaje en inglés. Mismo patrón
    que la deflexión de contacto/identidad IA."""
    effective_lang = state.language if state.detected_language else _infer_language(message, state.language)
    policy_kind = {"modify_headcount": "modify_booking"}.get(kind, kind)
    policy_text = (politicas().get(policy_kind) or {}).get(effective_lang, "")
    # El mensaje va al historial ANTES del resumen del pase, para que el asesor lo lea.
    state.history.append({"role": "user", "content": message})
    response = _pase_por_cambio_de_reserva(state, policy_text, kind, effective_lang)
    state.history.append({"role": "assistant", "content": response})
    return response


# gen-3b (21-oct; promocionado, su flag `cambio_de_reserva_pasa` se borró en sim-5): cambiar la fecha, cancelar o
# cambiar el número de personas de una reserva ya hecha solo lo puede hacer una persona del equipo (el bot no ve las reservas). La respuesta OFRECÍA el pase
# («¿quieres que te conecte con un asesor o prefieres volver al menú principal?», un menú que ya no existe) y no lo
# marcaba: si el cliente no contestaba «sí», nadie se enteraba. Ahora se da la política y se PASA, como
# `needs_staff`.
_PASE_POR_CAMBIO = {
    "cancellation": ("cancelación de reserva: la gestiona una persona", "la cancelación", "the cancellation"),
    "reschedule": ("cambio de fecha de una reserva: lo gestiona una persona", "el cambio de fecha", "the date change"),
    "modify_headcount": ("cambio en el número de personas de una reserva: lo gestiona una persona",
                         "el cambio en el número de personas", "the change in the number of people"),
}


def _pase_por_cambio_de_reserva(state: ConversationState, policy_text: str, kind: str, lang: str) -> str:
    reason, que_es, que_en = _PASE_POR_CAMBIO[kind]
    state.step = Step.ESCALATE
    state.quick_replies = []
    state.pending_escalation_reason = reason
    state.pending_note = build_lead_summary(state, escalation_reason=reason)
    logger.info(f"[SUPERVISOR] {kind} de una reserva hecha -> pase a un asesor")
    if lang == "es":
        pase = (f"Te paso ahora con un asesor de Diving Planet para gestionar {que_es}; enseguida se pone en contacto "
                "contigo por aquí. 🙌")
    else:
        pase = (f"I'm passing you now to a Diving Planet advisor to handle {que_en}; they'll get in touch with you "
                "here shortly. 🙌")
    return f"{policy_text}\n\n{pase}" if policy_text else pase
