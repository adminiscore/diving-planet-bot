"""Nodo `availability` del subgrafo de la reserva: `_availability_phase` (la puerta de disponibilidad), la posventa y
lo que va tras el pase a un asesor.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging

from src.agents.conversational_core import (
    _is_rag_fallback,
    _turn_has_question,
    rag_con_adelantado,
)
from src.flows.state import ConversationState, Step

logger = logging.getLogger("uvicorn.error")


def _reserva_nueva_en_curso(state: ConversationState) -> bool:
    """En esta conversación el cliente ya eligió una actividad (en turnos anteriores) y aún no se le ha mandado el
    enlace de reserva: está reservando algo nuevo."""
    from src.observability import BOOKING_LINK  # lazy

    if not state.detected_activity:
        return False
    return not any(
        t.get("role") == "assistant" and BOOKING_LINK in (t.get("content") or "") for t in (state.history or [])
    )


def _modo_posventa(state: ConversationState, routing_signals: dict) -> bool:
    """13-oct (flag `posventa_sin_vender`): ¿el cliente ya tiene una reserva o ya hizo la actividad? Lo dice Jev
    (`ya_reservado`, en la misma llamada del enrutador) y se recuerda; se olvida si en un turno sin ese dato el cliente
    AFIRMA una actividad (quiere reservar algo nuevo)."""
    ahora = routing_signals.get("ya_reservado")
    if ahora is True and not state.ya_reservado and _reserva_nueva_en_curso(state):
        # Ronda atencion-B2 (snorkel-precio-residente-y-pago-link): a mitad de reservar snorkel para dos, "ok ya he
        # buceado con ustedes" (cliente que vuelve) pasaba a posventa y "dame la cuenta y transfiero" recibía "si
        # necesitas algo de tu reserva…" sin el enlace de pago. Lo que esta conversación ya está reservando manda.
        logger.info("[CORE] posventa: Jev dice ya_reservado, pero hay una reserva nueva en curso -> se sigue con ella")
        return False
    if ahora is True:
        if not state.ya_reservado:
            logger.info("[CORE] posventa: el cliente ya tiene una reserva (Jev) -> sin preguntas de la reserva")
        state.ya_reservado = True
    elif state.ya_reservado and routing_signals.get("affirms_activity") is True:
        state.ya_reservado = False
        logger.info("[CORE] posventa: el cliente elige una actividad nueva -> vuelve la reserva")
    return state.ya_reservado


async def _tras_el_pase(
    state: ConversationState, message: str, routing_signals: dict, greeting: str, *, posventa: bool = False,
) -> str:
    """13-oct: con la conversación ya pasada a una persona, el bot no vuelve a vender.

    Antes solo una cortesía pura recibía la respuesta corta (la de s4-20, ya borrada); en cuanto el cliente daba un
    dato volvía la reserva: tras pasar al asesor "my husband has food poisoning… move our dive to Tuesday?", el bot
    preguntaba "Which one are you leaning toward — diving, a mini-course…?" a cada dato siguiente
    (cambio-fecha-por-enfermedad, rondas ex8-B2 y ex7-B). Ahora contesta lo que se pregunte (el RAG) y, si no hay
    pregunta, deja una nota corta: la persona ve toda la conversación."""
    state.quick_replies = []
    state._pregunta_del_escritor = None  # lat-9 paso 2: aquí no sigue la reserva
    answer = None
    if _turn_has_question(message, routing_signals):
        answer = await rag_con_adelantado(state, message, list(state.history))
    if (not answer or _is_rag_fallback(answer)) and posventa:
        answer = (
            "¡Perfecto, gracias! 🙌 Si necesitas algo de tu reserva, cuéntame; y si hay que cambiar algo, te paso con "
            "un asesor del equipo." if state.language == "es" else
            "Perfect, thank you! 🙌 If you need anything about your booking, just tell me; and if something needs to "
            "change, I'll pass you to an advisor from the team."
        )
    elif not answer or _is_rag_fallback(answer):
        answer = (
            "Anotado 🙌 Ya le pasé tu caso a un asesor del equipo: lo ve todo en esta conversación y te escribe por "
            "aquí enseguida." if state.language == "es" else
            "Noted 🙌 I've already passed your case to an advisor from the team: they can see this whole conversation "
            "and will write to you here shortly."
        )
    response = greeting + answer
    state.history.append({"role": "assistant", "content": response})
    logger.info(f"[CORE] {'posventa' if posventa else 'tras el pase a una persona'}: sin pregunta de la reserva")
    return response


async def _availability_phase(
    state: ConversationState, message: str, routing_signals: dict, greeting: str,
) -> str | None:
    """Fase 3.3c — gate de disponibilidad, extraído de `_body_phase`. Los días
    cerrados (25 dic y 1 ene) se contestan con la política; el resto de
    preguntas de disponibilidad las contesta el RAG (paso 5, 27-sep: el texto
    fijo de "siempre hay disponibilidad" se comía el resto del mensaje), con la
    regla de no confirmar cupos en el contexto, y la reserva sigue.
    Devuelve la respuesta o None para continuar al cuerpo.

    ⚠️ Patrón B del audit §1.5: hoy la disponibilidad la resuelve el núcleo
    (booking) y no el nodo `changes`; aislarla en su propia fase/nodo facilita
    reubicarla en el cutover (Fase 5.2)."""
    from src.agents import supervisor  # lazy

    if state.step == Step.ESCALATE:
        return await _tras_el_pase(state, message, routing_signals, greeting)
    if _modo_posventa(state, routing_signals):
        # gen-15: la puerta del origen del RAG mira dónde dice Jev que está el cliente (`_jev_lugar`), que se apunta en
        # el enrutado; en posventa no se llega ahí y se preguntaba el origen con Jev seguro (islands 0,97).
        state._jev_lugar = routing_signals.get("customer_place")
        return await _tras_el_pase(state, message, routing_signals, greeting, posventa=True)

    msg_lower = message.strip().lower()
    # Hallazgo (batería sintética contra PRE, 2026-08-26, conv 395, portado
    # de pre_gadea v0.21.10): "¿abren el 25 de diciembre?" recibía el texto
    # genérico de disponibilidad ("siempre hay disponibilidad") — FALSO para
    # esos dos días concretos (`policies.json["closed_days"]`: solo cerrado
    # 25 dic y 1 ene). `_CLOSED_DATE_RE` sola basta para contestar aquí. Esta
    # fase se ejecuta ANTES que la copia del supervisor; el mismo guard se
    # aplicó ahí también.
    # ex-9b paso 4 (medido y descartado): sin este texto fijo, "quiero bucear el 25 de diciembre, somos 2" no llega al
    # RAG (Jev: no pregunta nada) y nadie avisa de que ese día está cerrado (banco del paso 4).
    if supervisor._CLOSED_DATE_RE.search(msg_lower):
        from src.domain.politicas import politicas  # lazy
        policy_text = (politicas().get("closed_days") or {}).get(state.language, "")
        response = greeting + policy_text
        state.history.append({"role": "assistant", "content": response})
        return response
    # Paso 5 (27-sep): cualquier otra pregunta de disponibilidad ("¿el 6 de febrero ya es fijo que se sale?",
    # "¿las fotos tienen precio adicional?") sigue como cualquier otra: la contesta el RAG y la reserva sigue.
    return None
