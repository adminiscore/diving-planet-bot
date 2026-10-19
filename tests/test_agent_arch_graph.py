"""Fase 1.3-1.4 (docs/multi-agent-refactor-plan.md) — el turno pasa por el grafo LangGraph.

Fija que el grafo muta el estado del caller en el sitio y que reutiliza las señales del router (una sola llamada LLM
por turno, no dos). s4-1 (19-oct) quitó el flag `agent_arch` y con él la cascada directa: se fueron también los
tests de equivalencia grafo/cascada y el que fijaba el flag encendido por defecto.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.supervisor import route_message
from src.flows.state import ConversationState, Step


def make_state() -> ConversationState:
    return ConversationState(conversation_id="graph-eq-test")


@pytest.fixture
def _signals_offline(monkeypatch):
    """Mockea detect_routing_signals (el binding del supervisor, que usa el nodo router del grafo) a {} —
    determinista, sin red."""
    sup_mock = AsyncMock(return_value={})
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", sup_mock)
    return sup_mock


@pytest.mark.asyncio
async def test_graph_mutates_conv_state_in_place(_signals_offline):
    state = make_state()
    assert state.step == Step.WELCOME
    await route_message(state, "hola")
    # El nodo muta el objeto in-place.
    assert state.step != Step.WELCOME
    assert len(state.history) > 0


@pytest.mark.asyncio
async def test_graph_reuses_router_signals_no_double_llm_call(_signals_offline):
    sup_mock = _signals_offline
    await route_message(make_state(), "quiero información de los tours")

    # El nodo router calcula las señales UNA sola vez; el nodo de ruta las pasa
    # a _shared_turn_handler, que NO recomputa (sin doble llamada LLM/turno).
    assert sup_mock.await_count == 1


@pytest.mark.asyncio
async def test_graph_result_carries_same_conv_state_object(_signals_offline):
    """El grafo transporta el objeto vivo, no una copia (verificado además a
    nivel de LangGraph en el diseño)."""
    from src.orchestration.graph import run_turn_via_graph

    state = make_state()
    reply = await run_turn_via_graph(state, "hola")
    assert isinstance(reply, str) and reply
    # el turno mutó el mismo objeto que pasó el caller
    assert state.history and state.history[-1]["role"] == "assistant"
