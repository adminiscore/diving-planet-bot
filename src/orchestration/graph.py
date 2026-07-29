"""El grafo esqueleto (Fase 1.3) — StateGraph(BotState).

Ver `docs/agent-arch-design.md` §2 y `docs/multi-agent-refactor-plan.md` §1.3.

Estructura:

    START → router → [conditional edges por route] → {5 nodos de ruta} → END

En la Fase 1 los 5 nodos de ruta son **wrappers finos idénticos**: todos
delegan en `supervisor._route_message_inner` (la cascada actual). El grafo NO
cambia comportamiento — solo añade el enrutado por encima y valida la fontanería
(que LangGraph corre en la app, que el router clasifica, que un turno real
produce la misma respuesta que la cascada). En Fases 2-3 el cuerpo de cada nodo
se sustituye por su lógica real, una ruta a la vez (strangler-fig).

El `conv_state` viaja por referencia dentro del BotState; las mutaciones
in-place de la cascada (`state.step`, `state.history`, ...) se propagan al
objeto que tiene el caller — verificado empíricamente antes de escribir esto.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from src.orchestration.router import classify_route
from src.orchestration.state import ALL_ROUTES, BotState

logger = logging.getLogger("uvicorn.error")


async def _router_node(state: BotState) -> dict:
    """Calcula las señales de routing (1 vez/turno, con el mismo skip de clics
    numéricos que la cascada) y clasifica la ruta. Es el único sitio donde se
    llama a `detect_routing_signals` cuando el grafo está activo — el nodo de
    ruta reutiliza el resultado vía `state["signals"]` (evita la doble llamada
    LLM).

    Se importa `detect_routing_signals` DESDE `supervisor` (no desde
    `escalation`) a propósito: es el mismo binding que usa la cascada y que los
    tests parchean (`src.agents.supervisor.detect_routing_signals`), así un
    solo mock cubre los dos caminos (grafo y cascada) — la prueba de
    equivalencia (suite verde on/off) depende de ello."""
    from src.agents.supervisor import detect_routing_signals

    conv = state["conv_state"]
    message = state["message"]
    msg_lower = message.strip().lower()
    signals = {} if msg_lower.isdigit() else await detect_routing_signals(message, lang=conv.language)
    route = classify_route(conv, message, signals)
    logger.info(f"[GRAPH] conv={conv.conversation_id} route={route}")
    return {"signals": signals, "route": route}


def _make_legacy_delegate_node(route_name: str):
    """Fábrica de nodo-wrapper de Fase 1: delega en la cascada actual,
    reutilizando las señales ya calculadas por el router. Cada ruta registra
    su propio nodo (mismo cuerpo hoy) para que en Fase 2 se sustituyan uno a
    uno de forma independiente."""

    async def _node(state: BotState) -> dict:
        from src.agents.supervisor import _route_message_inner

        reply = await _route_message_inner(
            state["conv_state"], state["message"], routing_signals=state.get("signals")
        )
        return {"reply": reply}

    _node.__name__ = f"node_{route_name}"
    return _node


def _route_decision(state: BotState) -> str:
    return state["route"]


def _build_graph():
    builder = StateGraph(BotState)
    builder.add_node("router", _router_node)
    for route in ALL_ROUTES:
        builder.add_node(route, _make_legacy_delegate_node(route))
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router", _route_decision, {route: route for route in ALL_ROUTES}
    )
    for route in ALL_ROUTES:
        builder.add_edge(route, END)
    return builder.compile()


_COMPILED_GRAPH = None


def get_compiled_graph():
    """Grafo compilado (lazy singleton — se compila una vez al primer uso, no
    a import, para no pagarlo cuando `agent_arch` está apagado)."""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = _build_graph()
    return _COMPILED_GRAPH


async def run_turn_via_graph(conv_state, message: str) -> str:
    """Punto de entrada del grafo para `supervisor.route_message` (Fase 1.4).
    Devuelve la respuesta; el `conv_state` queda mutado in-place por el nodo
    de ruta (que delega en la cascada), igual que si se hubiera llamado a
    `_route_message_inner` directamente."""
    result = await get_compiled_graph().ainvoke({"conv_state": conv_state, "message": message})
    return result["reply"]
