"""Nodo-agente `changes` (Fase 2.3) — el tercer nodo REAL del grafo.

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.3 y §4.bis (taxonomía).

## Qué maneja

La ruta `ROUTE_CHANGE` (cambios sobre una reserva existente). Tres gates, y —como
en el nodo `escalation`— lo que decide cómo reproducirlos es su posición respecto
al núcleo conversacional (`maybe_handle_turn`):

**Gates PRE-núcleo** (predicados puros → se reproducen directamente, equivalencia
exacta):

1. **Cancelación** (`_detect_cancellation_request` o la señal LLM
   `booking_change_topic == "cancellation"` fuera de construcción de carrito) →
   texto de política + botones asesor/menú.
2. **Reprogramación** (`_detect_reschedule_request` o la señal LLM
   `booking_change_topic == "reschedule"` fuera de carrito) → misma forma con la
   política de cambio de fecha.

Ambos usan `supervisor._booking_change_response` (copy + estado + historial), la
MISMA función que la cascada — una sola fuente de verdad, sin strings duplicados.

**Gate POST-núcleo** (disponibilidad): en la cascada el handler de disponibilidad
está DESPUÉS de `maybe_handle_turn`, así que el núcleo intercepta las preguntas de
disponibilidad "frescas" primero. Esto es la **divergencia documentada patrón B**
del audit del shadow (§1.5): router→changes, cascada→booking (3/14). Reproducir el
gate aquí sin correr el núcleo cambiaría el comportamiento respecto a la cascada.
Por eso NO se reproduce: se **delega en la cascada** (que corre el núcleo y luego,
si procede, el handler de disponibilidad) → equivalencia garantizada. Si en el
cutover (Fase 5.2) se decide que la disponibilidad debe ganar al núcleo, se
reproducirá aquí; por ahora se preserva la conducta actual.

Detectores y copys viven todavía en `supervisor.py` (import perezoso, patrón del
repo); migrarán a un módulo propio del router en Fase 3.

## Resiliencia (principio #10, "sin fugas")

El caso por defecto (ningún gate pre-núcleo matchea) delega en la cascada, que
siempre responde — nunca se dropea el turno.
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
