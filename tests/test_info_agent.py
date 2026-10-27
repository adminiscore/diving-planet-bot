"""Fase 2.4 — nodo-agente `info` real + rama edad→INFO del router.

Cubre: (a) el router enruta las preguntas de edad a INFO (cierre patrón A),
(b) el nodo en aislamiento (edad determinista / DIVE TO HEAL no-precio → RAG /
delegación). La equivalencia flag on == flag off se fue con el flag `agent_arch`
(s4-1).
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.info_agent import info_node
from src.flows.state import ConversationState, Step
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_BOOKING


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="info-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── router: la edad ya no va a INFO (CALN2-04, 27-oct: la contesta el flujo normal) ──

def test_router_age_question_goes_to_booking():
    conv = make_state()
    assert classify_route(conv, "mi hijo de 9 años puede bucear?", {}) == ROUTE_BOOKING
    assert classify_route(conv, "quiero reservar para 3 personas", {}) == ROUTE_BOOKING


# ── nodo en aislamiento ──

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
async def test_node_dive_to_heal_context_persists_for_generic_followup(monkeypatch):
    """Hallazgo en vivo (batería de frontera contra PRE, 2026-09-01): un
    seguimiento genérico dentro de DIVE TO HEAL SIN palabra de discapacidad
    en ESE mensaje ("¿qué incluye el programa?") perdía el contexto — el
    chequeo usaba `adaptive_now` (solo la señal de este turno) en vez del
    flag persistido `conv.adaptive_diving_context`, y caía al menú genérico
    de actividades en vez de seguir dando info factual del programa
    adaptado."""
    monkeypatch.setattr("src.agents.supervisor.rag_answer", AsyncMock(return_value="RAG-INFO"))
    conv = make_state()
    conv.adaptive_diving_context = True  # persistido de un turno anterior
    result = await info_node(
        {"conv_state": conv, "message": "que incluye el programa", "signals": {}}
    )
    assert result["reply"] == "RAG-INFO"


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
