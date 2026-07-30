"""Nodo-agente `booking` (Fase 2.5) + subgrafo del núcleo (Fase 3.3, en curso).

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.5/3.3, §4 (subgrafo booking)
y `docs/agent-arch-design.md` §4.

## Qué maneja

La ruta `ROUTE_BOOKING`: el tráfico central del bot (reserva slot-fill,
multi-ítem/acompañantes, y las preguntas de info que el núcleo resuelve por
RAG interno). El "gate" de booking en la cascada ES el núcleo conversacional
(`conversational_core.maybe_handle_turn`).

## Subgrafo (strangler de Fase 3.3)

El plan (§3.3) parte el núcleo monolítico (~2.249 líneas) en nodos internos de
responsabilidad única: **routing interno → extracción → slot-fill → cierre
determinista**. Ese corte se hace de forma incremental sobre un **subgrafo
LangGraph** que vive aquí, igual que el esqueleto de la Fase 1 fue el
contenedor del grafo principal.

**Estado actual del corte:** *andamiaje*. El subgrafo tiene UN nodo (`core`)
que envuelve `maybe_handle_turn` — equivalente por construcción, cero cambio de
conducta. Los siguientes pasos de 3.3 extraen fases del núcleo a nodos propios
del subgrafo, una a una, con equivalencia probada en cada corte. Hasta
entonces, el núcleo sigue resolviendo el turno completo dentro de `core`.

## PRE/POST-núcleo (patrón del handoff de Fase 2)

- **PRE-núcleo:** `core` llama a `maybe_handle_turn(conv, message,
  routing_signals=signals)`, reutilizando las señales del router (sin doble
  llamada LLM) y mutando `conv` por referencia (step/history/slots) igual que
  la cascada.
- **POST-núcleo (resiliencia #10):** si el núcleo devuelve `None`, `core`
  delega en `_route_message_inner`. Ese `None` solo ocurre para
  escalado-keyword/`wants_human` (que el router manda a SAFETY, no a BOOKING) y
  es pre-mutación → aquí no se dispara y sería seguro si lo hiciera.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


async def _core_node(state: BotState) -> dict:
    """Nodo único del subgrafo (por ahora): envuelve el núcleo completo. Los
    cortes de 3.3 irán extrayendo fases de aquí a nodos hermanos."""
    from src.agents import conversational_core
    from src.agents.supervisor import _route_message_inner

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}

    core_response = await conversational_core.maybe_handle_turn(
        conv, message, routing_signals=signals
    )
    if core_response is not None:
        logger.info("[NODE:booking/core] núcleo resolvió el turno")
        return {"reply": core_response}

    logger.info("[NODE:booking/core] núcleo devolvió None -> delego en la cascada")
    return {"reply": await _route_message_inner(conv, message, routing_signals=signals)}


def _build_booking_subgraph():
    """Subgrafo del booking. Hoy `START → core → END`; los cortes de 3.3 añaden
    nodos (routing interno / extracción / slot-fill / cierre) y edges entre
    ellos, sin tocar el grafo padre ni la firma de `booking_node`."""
    builder = StateGraph(BotState)
    builder.add_node("core", _core_node)
    builder.add_edge(START, "core")
    builder.add_edge("core", END)
    return builder.compile()


_BOOKING_SUBGRAPH = None


def _get_booking_subgraph():
    """Subgrafo compilado (lazy singleton — no se compila a import)."""
    global _BOOKING_SUBGRAPH
    if _BOOKING_SUBGRAPH is None:
        _BOOKING_SUBGRAPH = _build_booking_subgraph()
    return _BOOKING_SUBGRAPH


async def booking_node(state: BotState) -> dict:
    """Entrada de la ruta BOOKING en el grafo principal: invoca el subgrafo del
    núcleo. `conv_state` viaja por referencia, así que las mutaciones in-place
    del núcleo se propagan al objeto del caller igual que antes."""
    result = await _get_booking_subgraph().ainvoke(state)
    return {"reply": result["reply"]}
