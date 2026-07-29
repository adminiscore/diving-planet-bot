"""Fase 0.5 (docs/multi-agent-refactor-plan.md) — PoC de-risk de LangGraph.

Fija el contrato del flag `settings.agent_arch`: apagado por defecto, no
invoca el grafo; encendido, lo invoca pero NUNCA cambia la respuesta real al
cliente (side-channel puro) ni rompe el turno si el grafo falla.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState


def make_state() -> ConversationState:
    return ConversationState(conversation_id="agent-arch-poc-test")


def test_agent_arch_defaults_to_off():
    assert settings.agent_arch is False


@pytest.mark.asyncio
async def test_flag_off_does_not_run_poc_graph(monkeypatch):
    monkeypatch.setattr(settings, "agent_arch", False)
    with patch(
        "src.agents.supervisor._run_agent_arch_poc", new=AsyncMock()
    ) as poc:
        await route_message(make_state(), "hola")
    poc.assert_not_called()


@pytest.mark.asyncio
async def test_flag_on_runs_poc_graph_without_changing_reply(monkeypatch):
    state_off = make_state()
    monkeypatch.setattr(settings, "agent_arch", False)
    reply_off = await route_message(state_off, "hola")

    state_on = make_state()
    monkeypatch.setattr(settings, "agent_arch", True)
    with patch(
        "src.orchestration.poc_graph.run_poc_graph",
        new=AsyncMock(return_value="poc-graph saw: HOLA"),
    ) as poc:
        reply_on = await route_message(state_on, "hola")

    poc.assert_awaited_once_with("hola")
    assert reply_on == reply_off
    assert state_on.quick_replies == state_off.quick_replies


@pytest.mark.asyncio
async def test_flag_on_poc_graph_failure_does_not_break_the_turn(monkeypatch):
    """Principio #10 (sin fugas): un error del grafo PoC nunca debe tumbar
    el turno real ni cambiar la respuesta."""
    state_off = make_state()
    monkeypatch.setattr(settings, "agent_arch", False)
    reply_off = await route_message(state_off, "hola")

    state_on = make_state()
    monkeypatch.setattr(settings, "agent_arch", True)
    with patch(
        "src.orchestration.poc_graph.run_poc_graph",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        reply_on = await route_message(state_on, "hola")

    assert reply_on == reply_off
