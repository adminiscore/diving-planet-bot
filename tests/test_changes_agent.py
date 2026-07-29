"""Fase 2.3 — nodo-agente `changes` real + equivalencia con la cascada.

Cubre: (a) el nodo en aislamiento por gate (cancelación, reprogramación,
delegación de disponibilidad), (b) equivalencia flag on (grafo con el nodo real)
== flag off (cascada) para mensajes de cada gate CHANGE — el corte strangler no
cambia la respuesta (incl. la divergencia documentada patrón B de disponibilidad,
que se preserva delegando).
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.changes_agent import changes_node
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="changes-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── nodo en aislamiento (State in → update out) ──

@pytest.mark.asyncio
async def test_node_cancellation_shows_policy_and_buttons():
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "quiero cancelar mi reserva", "signals": {}}
    )
    assert result["reply"]
    assert conv.quick_replies  # botones asesor/menú
    assert conv.history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_node_cancellation_via_signal_outside_cart():
    """La señal LLM `booking_change_topic=cancellation` fuera de construcción de
    carrito también dispara el gate, aunque la keyword no matchee."""
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "ya no voy a poder ir al final",
         "signals": {"booking_change_topic": "cancellation"}}
    )
    assert result["reply"]
    assert conv.quick_replies


@pytest.mark.asyncio
async def test_node_reschedule_shows_policy_and_buttons():
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "quiero cambiar la fecha de mi reserva", "signals": {}}
    )
    assert result["reply"]
    assert conv.quick_replies


@pytest.mark.asyncio
async def test_node_availability_delegates_to_cascade(monkeypatch):
    """Disponibilidad es un gate POST-núcleo (patrón B): el nodo NO lo reproduce
    → delega en la cascada (que corre el núcleo primero)."""
    monkeypatch.setattr(
        "src.agents.supervisor._route_message_inner",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "que dias hay disponibles?", "signals": {}}
    )
    assert result["reply"] == "respuesta de la cascada"


# ── equivalencia flag on/off (el corte strangler no cambia la respuesta) ──

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "quiero cancelar mi reserva",                  # cancelación (pre-núcleo)
    "quiero cambiar la fecha de mi reserva",       # reprogramación (pre-núcleo)
    "que dias hay disponibles?",                   # disponibilidad (post-núcleo → delega)
])
async def test_changes_equivalent_graph_vs_cascade(monkeypatch, message):
    # Routing LLM offline → determinista (los detectores regex manejan cada gate).
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(), message)

    assert reply_graph == reply_cascade
    assert reply_graph  # no se dropea el turno
