"""Fase 2.1 — nodo-agente `deflection` real.

Cubre el nodo en aislamiento (contacto / identidad IA / fallback). La equivalencia
flag on (grafo) == flag off (cascada) se fue con el flag `agent_arch` (s4-1).
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.deflection_agent import deflection_node
from src.flows.state import ConversationState, Step


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="deflection-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── nodo en aislamiento (State in → update out) ──

@pytest.mark.asyncio
async def test_node_contact_number(monkeypatch):
    """CAL-E1 (decisión de Gadea, 16-oct): el chatbot no da números y quien pide un contacto PASA con un asesor.
    PRE sirve el grafo, así que el pase tiene que estar en este nodo: el test de equivalencia grafo/cascada (retirado
    con el flag `agent_arch` en s4-1) fue justo lo que cazó que solo estaba en la cascada."""
    conv = make_state()
    result = await deflection_node({"conv_state": conv, "message": "dame tu whatsapp", "signals": {}})
    assert "320" not in result["reply"] and "+57" not in result["reply"], "ningún número"
    assert "asesor" in result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason
    assert conv.history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_node_contact_number_via_signal():
    """La señal LLM `asks_for_contact_number` también dispara el pase por contacto, aunque la keyword no matchee.
    (Hasta s4-25 fijaba los caminos de antes de s4-14 y CAL-E1: la deflexión con 🔒 y sin pase.)"""
    conv = make_state()
    result = await deflection_node(
        {"conv_state": conv, "message": "y si necesito hablar por fuera del chat?",
         "signals": {"asks_for_contact_number": True}}
    )
    assert "asesor" in result["reply"]
    assert conv.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_node_ai_identity():
    conv = make_state()
    result = await deflection_node({"conv_state": conv, "message": "¿qué modelo de IA eres?", "signals": {}})
    assert "Coral" in result["reply"]        # en persona, sin revelar modelo
    low = result["reply"].lower()
    assert not any(w in low for w in ("gpt", "openai", "llm", "modelo de lenguaje"))
    assert conv.step == Step.FREE_TEXT


@pytest.mark.asyncio
async def test_node_fallback_delegates_without_dropping_turn(monkeypatch):
    """Resiliencia (#10): si el nodo se alcanza sin match, delega en la cascada
    en vez de dropear el turno."""
    monkeypatch.setattr(
        "src.agents.supervisor._shared_turn_handler",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await deflection_node({"conv_state": conv, "message": "hola qué tal", "signals": {}})
    assert result["reply"] == "respuesta de la cascada"
