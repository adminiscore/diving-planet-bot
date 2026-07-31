"""Fase 5.1 — test-harness de los 5 nodos INTERNOS del subgrafo booking en
aislamiento (State in → update out, fases del núcleo mockeadas).

Complementa `test_booking_agent.py` (que prueba `booking_node`/el subgrafo de
punta a punta): aquí se fija el CONTRATO de cada nodo interno y de las funciones
de edge `_after_*`, sin correr las fases reales del núcleo — así una regresión en
el cableado del subgrafo (reply vs carry, salida temprana a END) se detecta
aislada, no enterrada en un flujo completo.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import booking_agent as ba
from src.agents import conversational_core as core
from src.flows.state import ConversationState, Step


def make_bot_state(**over):
    conv = ConversationState(conversation_id="subgraph-test")
    conv.language = "es"
    conv.step = Step.MAIN_MENU
    state = {"conv_state": conv, "message": "hola", "signals": {}}
    state.update(over)
    return state


# ── _setup_node ──

@pytest.mark.asyncio
async def test_setup_node_passes_greeting_and_first_turn(monkeypatch):
    monkeypatch.setattr(core, "_setup_phase", AsyncMock(return_value=("GREET ", True)))
    out = await ba._setup_node(make_bot_state())
    assert out == {"greeting": "GREET ", "first_turn": True}


@pytest.mark.asyncio
async def test_setup_node_delegates_when_core_declines(monkeypatch):
    monkeypatch.setattr(core, "_setup_phase", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.agents.supervisor._route_message_inner", AsyncMock(return_value="CASCADA")
    )
    out = await ba._setup_node(make_bot_state())
    assert out == {"reply": "CASCADA"}


# ── _availability_node ──

@pytest.mark.asyncio
async def test_availability_node_resolves_or_passes(monkeypatch):
    monkeypatch.setattr(core, "_availability_phase", AsyncMock(return_value="AVAIL"))
    out = await ba._availability_node(make_bot_state(greeting=""))
    assert out == {"reply": "AVAIL"}

    monkeypatch.setattr(core, "_availability_phase", AsyncMock(return_value=None))
    out = await ba._availability_node(make_bot_state(greeting=""))
    assert out == {}


# ── _routing_node (str → reply, dict → carry) ──

@pytest.mark.asyncio
async def test_routing_node_reply_vs_carry(monkeypatch):
    monkeypatch.setattr(core, "_routing_phase", AsyncMock(return_value="RESUELTO"))
    out = await ba._routing_node(make_bot_state(greeting=""))
    assert out == {"reply": "RESUELTO"}

    carry = {"prev_activity": None, "resolved_short": False}
    monkeypatch.setattr(core, "_routing_phase", AsyncMock(return_value=carry))
    out = await ba._routing_node(make_bot_state(greeting=""))
    assert out == {"carry": carry}


# ── _extraction_node ──

@pytest.mark.asyncio
async def test_extraction_node_resolves_or_passes(monkeypatch):
    monkeypatch.setattr(core, "_extraction_phase", AsyncMock(return_value="EXTRACT"))
    out = await ba._extraction_node(make_bot_state(greeting="", carry={}))
    assert out == {"reply": "EXTRACT"}

    monkeypatch.setattr(core, "_extraction_phase", AsyncMock(return_value=None))
    out = await ba._extraction_node(make_bot_state(greeting="", carry={}))
    assert out == {}


# ── _slotfill_close_node (siempre devuelve reply — nodo terminal) ──

@pytest.mark.asyncio
async def test_slotfill_close_node_always_replies(monkeypatch):
    monkeypatch.setattr(core, "_slotfill_close_phase", AsyncMock(return_value="CIERRE"))
    out = await ba._slotfill_close_node(make_bot_state(greeting="", first_turn=False, carry={}))
    assert out == {"reply": "CIERRE"}


# ── edges _after_* (salida temprana a END si un nodo ya resolvió el turno) ──

def test_after_edges_route_to_end_when_reply_set():
    assert ba._after_setup({"reply": "x"}) == "end"
    assert ba._after_setup({}) == "availability"
    assert ba._after_availability({"reply": "x"}) == "end"
    assert ba._after_availability({}) == "routing"
    assert ba._after_routing({"reply": "x"}) == "end"
    assert ba._after_routing({}) == "extraction"
    assert ba._after_extraction({"reply": "x"}) == "end"
    assert ba._after_extraction({}) == "slotfill_close"
