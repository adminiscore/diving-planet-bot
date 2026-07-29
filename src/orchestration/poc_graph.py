"""Fase 0.5 (docs/multi-agent-refactor-plan.md) — PoC de-risk de LangGraph.

Grafo trivial de 2 nodos que valida, DENTRO de la app real (no un script
aislado), que LangGraph instala/compila/ejecuta correctamente en el mismo
event loop que Chatwoot — antes de construir el grafo real (State/router/
nodos-agente, Fases 1-2). No persiste nada (sin checkpointer: esa decisión
es de la Fase 4.2) y no toca `ConversationState` — es un side-channel puro,
cableado detrás de `settings.agent_arch` en `supervisor.route_message`.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class _PocState(TypedDict):
    message: str
    upper: str
    reply: str


async def _node_uppercase(state: _PocState) -> dict:
    return {"upper": state["message"].upper()}


async def _node_reply(state: _PocState) -> dict:
    return {"reply": f"poc-graph saw: {state['upper']}"}


def _build_graph():
    builder = StateGraph(_PocState)
    builder.add_node("uppercase", _node_uppercase)
    builder.add_node("reply", _node_reply)
    builder.add_edge(START, "uppercase")
    builder.add_edge("uppercase", "reply")
    builder.add_edge("reply", END)
    return builder.compile()


_COMPILED_GRAPH = _build_graph()


async def run_poc_graph(message: str) -> str:
    """Corre el grafo trivial con un mensaje real y devuelve su `reply`."""
    result = await _COMPILED_GRAPH.ainvoke({"message": message})
    return result["reply"]
