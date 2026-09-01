"""Fase 1.3-1.4 (docs/multi-agent-refactor-plan.md) — grafo LangGraph tras el flag.

Prueba de equivalencia del strangler: con `agent_arch` ON el turno pasa por el
grafo (router + nodos-wrapper que delegan en la cascada); OFF, la cascada
directa. En Fase 1 ambos caminos deben producir la MISMA respuesta y el MISMO
efecto sobre el estado. También fija que el grafo reutiliza las señales del
router (una sola llamada LLM por turno, no dos).
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.supervisor import route_message
from src.config import Settings, settings
from src.flows.state import ConversationState, Step


def make_state() -> ConversationState:
    return ConversationState(conversation_id="graph-eq-test")


@pytest.fixture
def _signals_offline(monkeypatch):
    """Mockea detect_routing_signals (el binding del supervisor, que usan TANTO
    la cascada COMO el nodo router del grafo) a {} — determinista, sin red, para
    comparar los dos caminos limpiamente."""
    sup_mock = AsyncMock(return_value={})
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", sup_mock)
    return sup_mock


def test_agent_arch_defaults_to_off():
    # El DEFAULT del setting es off (robusto aunque la suite entera se corra con
    # AGENT_ARCH=true por env para la prueba de equivalencia flag-on).
    assert Settings.model_fields["agent_arch"].default is False


@pytest.mark.asyncio
async def test_graph_and_cascade_produce_same_reply(monkeypatch, _signals_offline):
    monkeypatch.setattr(settings, "agent_arch", False)
    reply_off = await route_message(make_state(), "hola")

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_on = await route_message(make_state(), "hola")

    assert reply_on == reply_off


@pytest.mark.asyncio
async def test_graph_and_cascade_same_reply_for_digit_click(monkeypatch, _signals_offline):
    # Clic de botón numérico: signals={} en ambos caminos, sin LLM.
    monkeypatch.setattr(settings, "agent_arch", False)
    s_off = make_state()
    s_off.step = Step.MAIN_MENU
    reply_off = await route_message(s_off, "2")

    monkeypatch.setattr(settings, "agent_arch", True)
    s_on = make_state()
    s_on.step = Step.MAIN_MENU
    reply_on = await route_message(s_on, "2")

    assert reply_on == reply_off


@pytest.mark.asyncio
async def test_graph_mutates_conv_state_in_place(monkeypatch, _signals_offline):
    monkeypatch.setattr(settings, "agent_arch", True)
    state = make_state()
    assert state.step == Step.WELCOME
    await route_message(state, "hola")
    # El nodo delega en la cascada, que muta el objeto in-place igual que sin grafo.
    assert state.step != Step.WELCOME
    assert len(state.history) > 0


@pytest.mark.asyncio
async def test_graph_reuses_router_signals_no_double_llm_call(monkeypatch, _signals_offline):
    sup_mock = _signals_offline
    monkeypatch.setattr(settings, "agent_arch", True)
    await route_message(make_state(), "quiero información de los tours")

    # El nodo router calcula las señales UNA sola vez; el nodo de ruta las pasa
    # a _shared_turn_handler, que NO recomputa (sin doble llamada LLM/turno).
    assert sup_mock.await_count == 1


@pytest.mark.asyncio
async def test_graph_result_carries_same_conv_state_object(monkeypatch, _signals_offline):
    """El grafo transporta el objeto vivo, no una copia (verificado además a
    nivel de LangGraph en el diseño)."""
    from src.orchestration.graph import run_turn_via_graph

    monkeypatch.setattr(settings, "agent_arch", True)
    state = make_state()
    reply = await run_turn_via_graph(state, "hola")
    assert isinstance(reply, str) and reply
    # el turno mutó el mismo objeto que pasó el caller
    assert state.history and state.history[-1]["role"] == "assistant"
