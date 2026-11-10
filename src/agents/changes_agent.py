"""Nodo-agente `changes` (Fase 2.3): la ruta `ROUTE_CHANGE`, cambios sobre una reserva existente.

**Antes del núcleo:** cancelar, reprogramar o cambiar el número de personas. Qué cambio es lo decide
`rutas.changes.cambio_de_reserva`, el mismo sitio que el router y la cascada (bloque 4P, C2); la respuesta,
`_booking_change_response`: la política de la KB y el pase directo a un asesor (gen-3b).

**Después del núcleo:** la disponibilidad. En la cascada va detrás de `maybe_handle_turn`, que intercepta antes las
preguntas de disponibilidad «frescas» (patrón B del audit del shadow, §1.5): reproducirla aquí sin el núcleo cambiaría la
conducta, así que se delega en la cascada, que siempre responde (nunca se pierde el turno).

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.3 y §4.bis.
"""

from __future__ import annotations

import logging

from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


async def changes_node(state: BotState) -> dict:
    from src.agents.rutas.changes import cambio_de_reserva
    from src.agents.supervisor import _booking_change_response, _shared_turn_handler

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}

    # 1-3 · Cancelar, reprogramar o cambiar el número de personas de una reserva (pre-núcleo). Bloque 4P (C2): qué cambio es
    #     se decide en el mismo sitio que el router y la cascada (`rutas.changes.cambio_de_reserva`); antes, tres copias.
    if cambio := cambio_de_reserva(conv, message, signals):
        logger.info(f"[NODE:changes] {cambio} -> política + pase a un asesor")
        return {"reply": _booking_change_response(conv, message, cambio)}

    # 4 · Disponibilidad (post-núcleo, patrón B) + defensa "sin fugas": delegar en
    #     la cascada preserva el orden exacto respecto al núcleo (que puede
    #     interceptar la pregunta de disponibilidad fresca → booking).
    logger.info("[NODE:changes] disponibilidad (post-núcleo) / sin match -> delego en la cascada")
    return {"reply": await _shared_turn_handler(conv, message, routing_signals=signals)}
