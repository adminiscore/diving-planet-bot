"""
Test de detección de grupos mixtos.

Decisión de diseño confirmada: cuando se detecta un grupo mixto sin ubicación
conocida, el bot pregunta primero dónde sale el usuario (MIXED_LOCATION) antes
de montar el carrito. No hay mensaje de confirmación intermedio — va directo a
la pregunta, igual que haría un humano.
"""

import pytest
from unittest.mock import AsyncMock

from src.agents import orchestrator
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(
        "src.agents.supervisor.detect_language_llm",
        AsyncMock(return_value=None),
    )


@pytest.fixture(autouse=True)
def _agent_books(_agent_answers_by_default, agent_decides):
    """A mixed-group booking request makes the agent pick a booking tool, which
    reuses the deterministic mixed-flow entry (group split preserved)."""
    agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "certified"})


@pytest.mark.asyncio
async def test_mixed_group_asks_location_first():
    """Grupo mixto sin ubicación → bot pregunta origen antes de montar el carrito."""
    state = ConversationState(conversation_id="test-mixed")
    state.language = "es"

    resp = await route_message(state, "Somos dos, yo quiero buceo certificado y mi novia snorkel")

    assert state.step == Step.MIXED_LOCATION, (
        f"Esperaba MIXED_LOCATION, got {state.step.value}"
    )
    assert state.detected_group_allocation is not None
    assert "certified_diving" in state.detected_group_allocation
    assert "snorkel" in state.detected_group_allocation


@pytest.mark.asyncio
async def test_mixed_group_with_location_goes_to_cart():
    """Grupo mixto con ubicación ya conocida → salta la pregunta de origen."""
    state = ConversationState(conversation_id="test-mixed-loc")
    state.language = "es"
    state.location = "cartagena"

    await route_message(state, "Somos dos, yo quiero buceo certificado y mi novia snorkel")

    assert state.step != Step.MIXED_LOCATION, (
        "Con ubicación ya conocida no debe preguntar de nuevo"
    )
    assert state.detected_group_allocation is not None
    assert "certified_diving" in state.detected_group_allocation
    assert "snorkel" in state.detected_group_allocation


@pytest.mark.asyncio
async def test_mixed_group_en():
    """Same flow in English."""
    state = ConversationState(conversation_id="test-mixed-en")
    state.language = "en"

    await route_message(state, "There are two of us, I want certified diving and my partner wants snorkel")

    assert state.step == Step.MIXED_LOCATION
    assert state.detected_group_allocation is not None
