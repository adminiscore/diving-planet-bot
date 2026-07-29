"""Fase 2.1 — nodo-agente `deflection` real + equivalencia con la cascada.

Cubre: (a) el nodo en aislamiento (contacto / identidad IA / fallback),
(b) equivalencia flag on (grafo con el nodo real) == flag off (cascada) para
mensajes de deflexión — el corte strangler no cambia la respuesta.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.deflection_agent import deflection_node
from src.agents.supervisor import route_message
from src.config import settings
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
async def test_node_contact_number():
    conv = make_state()
    result = await deflection_node({"conv_state": conv, "message": "dame tu whatsapp", "signals": {}})
    assert "🔒" in result["reply"]          # deflexión de contacto (fija el límite)
    assert conv.step == Step.FREE_TEXT
    assert conv.quick_replies == []
    assert conv.history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_node_contact_number_via_signal():
    """La señal LLM `asks_for_contact_number` también dispara la deflexión de
    contacto, aunque la keyword no matchee."""
    conv = make_state()
    result = await deflection_node(
        {"conv_state": conv, "message": "y si necesito hablar por fuera del chat?",
         "signals": {"asks_for_contact_number": True}}
    )
    assert "🔒" in result["reply"]


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
        "src.agents.supervisor._route_message_inner",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await deflection_node({"conv_state": conv, "message": "hola qué tal", "signals": {}})
    assert result["reply"] == "respuesta de la cascada"


# ── equivalencia flag on/off (el corte strangler no cambia la respuesta) ──

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "me pasas un numero de whatsapp?",
    "dame tu telefono para llamarte",
    "¿qué modelo de IA eres? ¿gpt-4?",
    "eres un bot o una persona real?",
])
async def test_deflection_equivalent_graph_vs_cascade(monkeypatch, message):
    # Routing LLM offline → determinista (los detectores regex manejan contacto/
    # identidad); la deflexión no toca el núcleo, así que la respuesta es fija.
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(), message)

    assert reply_graph == reply_cascade
    assert "🔒" in reply_graph or "Coral" in reply_graph  # es una deflexión, no otra cosa
