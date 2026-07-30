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

**Estado actual del corte (3.3c):** 3 nodos internos reales. `setup` (idioma/
saludo/nombre/append-historial/notas) → `availability` (gate de disponibilidad
anti-alucinación) → `body` (carryover → pregunta/recall → deliberación →
extracción → slot-fill → cierre). Los tres son funciones
`conversational_core._setup_phase`/`_availability_phase`/`_body_phase`
extraídas del monolito — y las llama TAMBIÉN la cascada (vía
`maybe_handle_turn`), así que cascada y subgrafo comparten la fuente de verdad
→ equivalencia por construcción. Los siguientes cortes de 3.3 parten el `body`
(extracción / slot-fill / cierre) en más nodos.

## PRE/POST-núcleo (patrón del handoff de Fase 2)

- **PRE-núcleo:** los nodos llaman a las fases del núcleo con las señales del
  router (sin doble llamada LLM) y mutan `conv` por referencia (step/history/
  slots) igual que la cascada.
- **POST-núcleo (resiliencia #10):** si `_setup_phase` devuelve `None`
  (escalado-keyword/`wants_human` — que el router manda a SAFETY, no a BOOKING,
  así que aquí no ocurre), el nodo `setup` delega en `_route_message_inner`.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


class _BookingSubState(BotState, total=False):
    """Estado del subgrafo del booking = BotState + los locales que `setup` pasa
    a `body` (antes eran variables de cierre dentro de `maybe_handle_turn`)."""

    greeting: str
    first_turn: bool


async def _setup_node(state: _BookingSubState) -> dict:
    """Primer nodo interno: setup del turno. Si el núcleo declinaría
    (escalado-keyword), delega en la cascada (resiliencia #10) — no ocurre para
    tráfico BOOKING. Si no, pasa `greeting`/`first_turn` al nodo `body`."""
    from src.agents.conversational_core import _setup_phase
    from src.agents.supervisor import _route_message_inner

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}

    result = await _setup_phase(conv, message, signals)
    if result is None:
        logger.info("[NODE:booking/setup] núcleo declinaría -> delego en la cascada")
        return {"reply": await _route_message_inner(conv, message, routing_signals=signals)}
    greeting, first_turn = result
    return {"greeting": greeting, "first_turn": first_turn}


async def _availability_node(state: _BookingSubState) -> dict:
    """Segundo nodo interno: gate de disponibilidad (anti-alucinación de
    calendario). Si dispara, resuelve el turno; si no, sigue al `body`."""
    from src.agents.conversational_core import _availability_phase

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}
    avail = await _availability_phase(conv, message, signals, state["greeting"])
    return {"reply": avail} if avail is not None else {}


async def _body_node(state: _BookingSubState) -> dict:
    """Tercer nodo interno: cuerpo del turno (carryover → … → cierre)."""
    from src.agents.conversational_core import _body_phase

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}
    reply = await _body_phase(conv, message, signals, state["greeting"], state["first_turn"])
    return {"reply": reply}


def _after_setup(state: _BookingSubState) -> str:
    """Si `setup` ya resolvió el turno (delegó por escalado), termina; si no,
    sigue a `availability`."""
    return "end" if state.get("reply") is not None else "availability"


def _after_availability(state: _BookingSubState) -> str:
    """Si la disponibilidad resolvió el turno, termina; si no, sigue al `body`."""
    return "end" if state.get("reply") is not None else "body"


def _build_booking_subgraph():
    """Subgrafo del booking (§3.3): `START → setup → availability → body → END`,
    con salida temprana a END en cuanto un nodo resuelve el turno. Los cortes
    siguientes parten el `body` en más nodos, sin tocar el grafo padre ni la
    firma de `booking_node`."""
    builder = StateGraph(_BookingSubState)
    builder.add_node("setup", _setup_node)
    builder.add_node("availability", _availability_node)
    builder.add_node("body", _body_node)
    builder.add_edge(START, "setup")
    builder.add_conditional_edges("setup", _after_setup, {"availability": "availability", "end": END})
    builder.add_conditional_edges("availability", _after_availability, {"body": "body", "end": END})
    builder.add_edge("body", END)
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
