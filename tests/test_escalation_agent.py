"""Fase 2.2 — nodo-agente `escalation` real + equivalencia con la cascada.

Cubre: (a) el nodo en aislamiento por gate (PII, link roto, sensible, DIVE TO
HEAL precio, delegación post-núcleo), (b) equivalencia flag on (grafo con el
nodo real) == flag off (cascada) para mensajes de cada gate SAFETY — el corte
strangler no cambia la respuesta.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.escalation_agent import escalation_node
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="escalation-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── nodo en aislamiento (State in → update out) ──

@pytest.mark.asyncio
async def test_node_pii_blocks_and_escalates():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "mi correo es juan.perez@gmail.com", "signals": {}}
    )
    assert result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason == "datos sensibles detectados"


@pytest.mark.asyncio
async def test_node_broken_link_keyword():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "el link de pago no me funciona", "signals": {}}
    )
    assert "asesor" in result["reply"].lower()
    assert conv.step == Step.ESCALATE
    assert "LINK ROTO" in conv.pending_escalation_reason


@pytest.mark.asyncio
async def test_node_broken_link_via_signal():
    """La señal LLM `broken_link_complaint` + contexto técnico también escala,
    aunque la keyword del fast-path no matchee."""
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "le doy al boton de pagar y no pasa nada",
         "signals": {"broken_link_complaint": True}}
    )
    assert conv.step == Step.ESCALATE
    assert "LINK ROTO" in conv.pending_escalation_reason
    assert result["reply"]


@pytest.mark.asyncio
async def test_node_sensitive_keyword():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "estoy embarazada, puedo bucear?", "signals": {}}
    )
    assert result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason
    assert conv.pending_note  # lead summary construido


@pytest.mark.asyncio
async def test_node_dive_to_heal_price_to_advisor():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "voy en silla de ruedas, cuanto cuesta bucear?", "signals": {}}
    )
    assert result["reply"]
    assert conv.adaptive_diving_context is True  # el contexto persiste
    # No vuelca precios genéricos de Cartagena — es una respuesta de asesor.
    assert "$" not in result["reply"]
    assert conv.history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_node_wants_human_delegates_to_cascade(monkeypatch):
    """Gate SAFETY post-núcleo (wants_human/keyword): el nodo NO lo reproduce
    (cambiaría el orden respecto al núcleo) → delega en la cascada."""
    monkeypatch.setattr(
        "src.agents.supervisor._route_message_inner",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "quiero hablar con una persona", "signals": {}}
    )
    assert result["reply"] == "respuesta de la cascada"


# ── equivalencia flag on/off (el corte strangler no cambia la respuesta) ──

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "mi correo es juan.perez@gmail.com",           # PII (pre-núcleo)
    "el link de pago no me funciona",              # link roto keyword (pre-núcleo)
    "estoy embarazada, puedo bucear?",             # sensible keyword (pre-núcleo)
    "voy en silla de ruedas, cuanto cuesta bucear?",  # DIVE TO HEAL precio (pre-núcleo)
    "quiero hablar con una persona",               # wants_human (post-núcleo → delega)
])
async def test_escalation_equivalent_graph_vs_cascade(monkeypatch, message):
    # Routing LLM offline → determinista (los detectores regex manejan cada gate);
    # la ruta SAFETY no toca el núcleo salvo en el caso wants_human (que delega).
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(), message)

    assert reply_graph == reply_cascade
    assert reply_graph  # no se dropea el turno
