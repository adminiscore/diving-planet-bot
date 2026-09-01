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
        "src.agents.supervisor._shared_turn_handler",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "que dias hay disponibles?", "signals": {}}
    )
    assert result["reply"] == "respuesta de la cascada"


# ── grupo B (post-núcleo): comportamiento final directo, SIN mockear
# `_shared_turn_handler` (Fase 5.2, prep del corte — ver docs/multi-agent-
# refactor-plan.md §5). La disponibilidad/días cerrados los intercepta hoy
# `conversational_core._availability_phase` (portado el mismo día que el
# resto de hallazgos de la batería sintética) — la delegación del nodo llega
# ahí a través del núcleo, no de la copia duplicada en la cola de
# `_shared_turn_handler` (que en la práctica queda como red de resiliencia,
# no como el camino real). Cobertura que hoy solo existe indirectamente vía
# los tests de `_shared_turn_handler`/núcleo en otros archivos y los
# `*_equivalent_graph_vs_cascade` (que dejarán de existir cuando se quite el
# flag `agent_arch`).

@pytest.mark.asyncio
async def test_node_availability_question_gives_canned_answer_directly():
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "¿tienen disponibilidad el sábado?", "signals": {}}
    )
    assert "disponibilidad" in result["reply"].lower()
    assert "siempre hay disponibilidad" in result["reply"].lower()


@pytest.mark.asyncio
async def test_node_closed_date_question_gives_real_policy_directly():
    """Hallazgo (batería sintética contra PRE, 2026-08-26, portado hoy):
    "¿abren el 25 de diciembre?" no debe dar el canned genérico de
    disponibilidad ("las salidas son diarias, siempre hay disponibilidad")
    — ese día está cerrado según `policies.json["closed_days"]`."""
    conv = make_state()
    result = await changes_node(
        {"conv_state": conv, "message": "¿abren el 25 de diciembre?", "signals": {}}
    )
    assert "siempre hay disponibilidad" not in result["reply"].lower()
    assert "25 de diciembre" in result["reply"] or "cerramos" in result["reply"].lower()


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
