"""Nodo-agente `booking` (Fase 2.5) — el quinto y último nodo REAL del grafo.

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.5 + el 🤝 HANDOFF, y §4.bis.

## Qué maneja

La ruta `ROUTE_BOOKING`: el tráfico central del bot (reserva slot-fill,
multi-ítem/acompañantes, y las preguntas de info que el núcleo resuelve por
RAG interno). En la cascada, este "gate" ES el núcleo conversacional
(`conversational_core.maybe_handle_turn`) — el router manda a BOOKING todo lo
que las rutas periféricas (SAFETY/CHANGE/DEFLECT/INFO) no capturaron.

## El corte (patrón PRE/POST del handoff)

- **PRE-núcleo = el núcleo mismo:** se reproduce directamente llamando a
  `maybe_handle_turn(conv, message, routing_signals=signals)`. Muta `conv` por
  referencia (step/history/quick_replies/slots) igual que en la cascada, y
  reutiliza las señales que ya calculó el router (sin doble llamada LLM).
- **POST-núcleo = delegar:** si el núcleo devuelve `None`, la cascada sigue a
  sus handlers deterministas de después (escalado por keyword, idioma, etc.).
  Reproducirlos aquí sin el orden de la cascada cambiaría la conducta → se
  **delega en `_route_message_inner`** (equivalencia exacta, resiliencia #10).

## Por qué el `None` es seguro y raro aquí

`maybe_handle_turn` devuelve `None` en un ÚNICO punto (su primera línea):
`_matches_escalation_keyword(msg) or wants_human` — y **antes de mutar nada**.
Esa condición es exactamente la que el router manda a SAFETY, no a BOOKING, así
que para un mensaje enrutado a BOOKING el núcleo nunca devuelve `None`: la rama
de delegación es una red de seguridad que no debería dispararse. Y si lo
hiciera, el `None` es sin efectos secundarios (retorno temprano pre-mutación),
así que la re-ejecución vía `_route_message_inner` es segura (no duplica el
mensaje en el historial).

## Partir el núcleo NO es 2.5

Convertir el núcleo en un subgrafo LangGraph (routing interno → extracción →
slot-fill → cierre determinista) es **Fase 3.3**. Aquí 2.5 solo necesita el
nodo envolvente equivalente para completar el despacho a los 5 nodos (2.6).

## Divergencias del audit §1.5 — NO tocar aquí

Disponibilidad fresca (patrón B, hoy la intercepta el núcleo → booking) y la
afirmación que acepta la oferta de asesor se **preservan** delegando; su
resolución es decisión del cutover (Fase 5.2), no de 2.5.
"""

from __future__ import annotations

import logging

from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


async def booking_node(state: BotState) -> dict:
    from src.agents import conversational_core
    from src.agents.supervisor import _route_message_inner

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}

    # PRE-núcleo: el núcleo ES el gate de booking. Reproducirlo = llamarlo.
    core_response = await conversational_core.maybe_handle_turn(
        conv, message, routing_signals=signals
    )
    if core_response is not None:
        logger.info("[NODE:booking] núcleo resolvió el turno")
        return {"reply": core_response}

    # POST-núcleo (resiliencia #10): el núcleo declinó — clases que la cascada
    # resuelve DESPUÉS (escalado-keyword/idioma/…), que el router ya manda a
    # SAFETY, así que esto casi nunca ocurre. Delegar preserva la equivalencia.
    logger.info("[NODE:booking] núcleo devolvió None -> delego en la cascada")
    return {"reply": await _route_message_inner(conv, message, routing_signals=signals)}
