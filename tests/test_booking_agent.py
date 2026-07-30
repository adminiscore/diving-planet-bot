"""Fase 2.5 — nodo-agente `booking` real (envuelve el núcleo) + equivalencia.

Cubre: (a) el nodo en aislamiento resuelve un turno de reserva vía el núcleo,
(b) si el núcleo devuelve None el nodo delega en la cascada (resiliencia #10),
(c) equivalencia flag on == flag off para mensajes de booking.

El núcleo (`maybe_handle_turn`) llama a varias redes LLM; para que la
equivalencia pruebe el ENRUTADO y no la (no-)determinación del LLM, se mockean
a valores fijos (mismo binding que ven cascada y grafo).
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.booking_agent import booking_node
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step


def make_state(step: Step = Step.MAIN_MENU, **over) -> ConversationState:
    s = ConversationState(conversation_id="booking-test")
    s.language = "es"
    s.step = step
    for k, v in over.items():
        setattr(s, k, v)
    return s


@pytest.fixture
def _core_llm_offline(monkeypatch):
    """Deja las redes LLM del núcleo en valores fijos → maybe_handle_turn
    determinista (rag_answer ya lo stubea el conftest; detect_routing_signals
    se mockea aparte donde hace falta)."""
    import src.agents.conversational_core as core

    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))


# ── subgrafo (Fase 3.3, andamiaje) ──

def test_booking_subgraph_compiles_with_internal_nodes():
    from src.agents.booking_agent import _get_booking_subgraph

    sub = _get_booking_subgraph()
    nodes = sub.get_graph().nodes
    # 3.3b/c/d/e: el núcleo partido en 5 fases de responsabilidad única
    assert {"setup", "availability", "routing", "extraction", "slotfill_close"} <= set(nodes)


@pytest.mark.asyncio
async def test_availability_question_resolved_by_its_node(monkeypatch):
    """Una pregunta de disponibilidad la resuelve el nodo `availability`
    (respuesta canónica anti-alucinación), sin llegar al body/extracción."""
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(settings, "agent_arch", True)
    reply = (await route_message(make_state(), "¿qué días hay disponibles?"))
    assert "disponibilidad" in reply.lower() or "availability" in reply.lower()


# ── nodo en aislamiento ──

@pytest.mark.asyncio
async def test_node_resolves_booking_turn_via_core(_core_llm_offline):
    conv = make_state(step=Step.WELCOME)
    result = await booking_node({"conv_state": conv, "message": "hola", "signals": {}})
    assert result["reply"]
    # el núcleo mutó el estado por referencia (primer turno → sale de WELCOME)
    assert conv.step != Step.WELCOME
    assert conv.history and conv.history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_node_delegates_when_core_returns_none(monkeypatch):
    """Si el núcleo devuelve None (clase post-núcleo), el nodo delega en la
    cascada sin dropear el turno (#10)."""
    import src.agents.conversational_core as core

    monkeypatch.setattr(core, "maybe_handle_turn", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.agents.supervisor._route_message_inner",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await booking_node({"conv_state": conv, "message": "asesor", "signals": {}})
    assert result["reply"] == "respuesta de la cascada"


@pytest.mark.asyncio
async def test_node_reuses_signals_no_double_routing_call(monkeypatch, _core_llm_offline):
    """El nodo pasa las señales del router al núcleo; no recalcula routing."""
    sig_mock = AsyncMock(return_value={})
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", sig_mock)
    conv = make_state()
    await booking_node({"conv_state": conv, "message": "quiero bucear", "signals": {}})
    # el nodo no llama a detect_routing_signals (lo hace el router antes)
    assert sig_mock.await_count == 0


# ── equivalencia flag on/off ──

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step, message",
    [
        (Step.WELCOME, "hola"),
        (Step.MAIN_MENU, "quiero reservar buceo para 2 personas certificados"),
        (Step.FREE_TEXT, "cuentame sobre los cursos padi"),
    ],
)
async def test_booking_equivalent_graph_vs_cascade(monkeypatch, _core_llm_offline, step, message):
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(step=step), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(step=step), message)

    assert reply_graph == reply_cascade
    assert reply_graph
