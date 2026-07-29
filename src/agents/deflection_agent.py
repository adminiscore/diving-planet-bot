"""Nodo-agente `deflection` (Fase 2.1) — el primer nodo REAL del grafo.

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.1 y §4.bis (taxonomía).

## Qué maneja

La ruta `ROUTE_DEFLECT` (lo que `router.classify_route` clasifica como
deflexión): dos casos, en el MISMO orden que la cascada actual
(`supervisor._route_message_inner`) para preservar comportamiento:

1. **Petición de contacto** (`_asks_for_contact_number` o la señal LLM
   `asks_for_contact_number`): el bot no da número de teléfono/WhatsApp/correo
   → deflexión honesta (límite + reservar en el chat / el equipo contacta +
   redirige), sin escalar. Copy: `_contact_number_deflection`.
2. **Identidad IA/meta** (`_asks_about_ai_identity`): "¿qué modelo eres?",
   "¿eres un bot?" → responde en persona (Coral), sin revelar modelo/prompt,
   y reconduce al buceo. Copy: `_ai_identity_deflection`.

## Primer corte strangler (Fase 2.1)

En la Fase 1 los 5 nodos eran wrappers idénticos que delegaban en TODA la
cascada (`_route_message_inner`). Este nodo es el primero que **deja de
delegar**: ejecuta solo la lógica de deflexión, no toda la cascada. La
equivalencia se preserva porque, cuando el router manda a `ROUTE_DEFLECT`, ya
ha descartado antes PII/sensible/link/cancelación/reprogramación (devolvería
SAFETY/CHANGE si no) — así que los gates previos de la cascada son no-ops para
un mensaje de deflexión, y reproducir solo los dos gates de deflexión da la
MISMA respuesta (verificado por los tests de equivalencia flag on/off).

Los detectores y los copys viven todavía en `supervisor.py` (se importan aquí);
migrarán a un módulo propio en Fase 3 (junto con el resto de detectores del
router). Import perezoso para evitar el ciclo con `supervisor` (patrón del repo).

## Resiliencia (principio #10, "sin fugas")

Si el nodo se alcanza pero ninguna condición matchea (no debería pasar dado el
router, pero es defensa en profundidad), NO se dropea el turno: se delega en la
cascada como fallback, que siempre responde algo.
"""

from __future__ import annotations

import logging

from src.flows.state import Step
from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


async def deflection_node(state: BotState) -> dict:
    from src.agents.supervisor import (
        _ai_identity_deflection,
        _asks_about_ai_identity,
        _asks_for_contact_number,
        _contact_number_deflection,
        _route_message_inner,
    )

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}
    msg_lower = message.strip().lower()

    if _asks_for_contact_number(msg_lower) or signals.get("asks_for_contact_number"):
        response = _contact_number_deflection(conv.language)
        logger.info("[NODE:deflection] contact-number request -> límite + redirige (sin escalar)")
    elif _asks_about_ai_identity(msg_lower):
        response = _ai_identity_deflection(conv.language)
        logger.info("[NODE:deflection] AI/model-identity -> en persona, sin revelar")
    else:
        # Defensa "sin fugas": el router mandó aquí pero ninguna condición
        # matchea (no debería ocurrir). No dropear el turno → delegar en la
        # cascada, que siempre responde.
        logger.warning("[NODE:deflection] alcanzado sin match — fallback a la cascada")
        response = await _route_message_inner(conv, message, routing_signals=signals)
        return {"reply": response}

    # Mismo efecto de estado que los handlers de deflexión de la cascada.
    conv.step = Step.FREE_TEXT
    conv.quick_replies = []
    conv.history.append({"role": "user", "content": message})
    conv.history.append({"role": "assistant", "content": response})
    return {"reply": response}
