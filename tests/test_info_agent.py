"""Fase 2.4 — nodo-agente `info` real + rama edad→INFO del router + equivalencia.

Cubre: (a) el router enruta las preguntas de edad a INFO (cierre patrón A),
(b) el nodo en aislamiento (edad determinista / DIVE TO HEAL no-precio → RAG /
delegación), (c) equivalencia flag on == flag off para mensajes INFO.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.info_agent import info_node
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_BOOKING, ROUTE_INFO


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="info-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── router: rama edad→INFO (patrón A cerrado) ──

def test_router_routes_age_question_to_info():
    conv = make_state()
    assert classify_route(conv, "mi hijo de 9 años puede bucear?", {}) == ROUTE_INFO
    assert classify_route(conv, "una persona de 14 puede bucear?", {}) == ROUTE_INFO


def test_router_does_not_overfire_on_plain_booking_number():
    """Un número sin cue de elegibilidad NO va a INFO (sigue a booking)."""
    conv = make_state()
    assert classify_route(conv, "quiero reservar para 3 personas", {}) == ROUTE_BOOKING


def test_router_age_cue_without_number_stays_booking():
    """Cue sin edad concreta (la cascada devolvería None → núcleo) → booking."""
    conv = make_state()
    assert classify_route(conv, "hay edad minima para bucear?", {}) == ROUTE_BOOKING


# ── nodo en aislamiento ──

@pytest.mark.asyncio
async def test_node_age_eligibility_deterministic():
    conv = make_state()
    result = await info_node(
        {"conv_state": conv, "message": "mi hijo de 9 años puede bucear?", "signals": {}}
    )
    assert result["reply"]
    assert conv.history[-1]["role"] == "assistant"
    assert conv.history[-1]["content"] == result["reply"]


@pytest.mark.asyncio
async def test_node_dive_to_heal_nonprice_uses_rag(monkeypatch):
    monkeypatch.setattr("src.agents.supervisor.rag_answer", AsyncMock(return_value="RAG-INFO"))
    conv = make_state()
    result = await info_node(
        {"conv_state": conv, "message": "voy en silla de ruedas, en que consiste el buceo adaptado?",
         "signals": {}}
    )
    assert result["reply"] == "RAG-INFO"
    assert conv.adaptive_diving_context is True  # el contexto persiste


@pytest.mark.asyncio
async def test_node_fallback_delegates_without_dropping_turn(monkeypatch):
    """Si el router aproximó INFO pero ningún gate dispara, delega en la cascada."""
    monkeypatch.setattr(
        "src.agents.supervisor._shared_turn_handler",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await info_node({"conv_state": conv, "message": "hola que tal", "signals": {}})
    assert result["reply"] == "respuesta de la cascada"


# ── equivalencia flag on/off ──

@pytest.mark.asyncio
async def test_info_age_equivalent_graph_vs_cascade(monkeypatch):
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))
    message = "mi hijo de 9 años puede bucear?"

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(), message)

    assert reply_graph == reply_cascade
    assert reply_graph


@pytest.mark.asyncio
async def test_info_dive_to_heal_equivalent_graph_vs_cascade(monkeypatch):
    # RAG es no-determinista → se mockea al MISMO binding (supervisor.rag_answer)
    # que usan la cascada y el nodo, para que ambos devuelvan lo mismo y la
    # igualdad pruebe el enrutado, no la (no-)determinación del RAG.
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))
    monkeypatch.setattr("src.agents.supervisor.rag_answer", AsyncMock(return_value="RAG-FIXED"))
    message = "voy en silla de ruedas, en que consiste el buceo adaptado?"

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(), message)

    assert reply_graph == reply_cascade == "RAG-FIXED"
