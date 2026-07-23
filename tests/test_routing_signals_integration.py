"""Integración: la red de precisión LLM de enrutado/seguridad (auditoría
2026-07-22) dispara escalado/menú cuando las listas de palabras clave NO
reconocen la frase — "estoy embarazadita", "quisiera hablar con una persona
real", "mejor empecemos de cero" no están en ninguna lista exacta.

Offline: detect_routing_signals se mockea (nunca llama al LLM real); se
prueba con el flag conversational_core tanto ON como OFF para confirmar que
la red aplica en ambos caminos (núcleo nuevo y árbol legacy).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.supervisor import route_message
from src.config import settings
from src.flows.decision_tree import ConversationState, Step


def make_state(lang: str = "es", step: Step = Step.FREE_TEXT) -> ConversationState:
    s = ConversationState(conversation_id="routing-test")
    s.language = lang
    s.step = step
    return s


@pytest.mark.asyncio
async def test_sensitive_medical_signal_escalates_when_keyword_list_misses():
    """"estoy embarazadita" no está en SENSITIVE_RULES (diminutivo) — la
    señal LLM debe escalar igual que si hubiera dicho "embarazada"."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"sensitive_topic": "medical_questions"})):
        resp = await route_message(state, "estoy embarazadita, puedo bucear?")
    assert state.step == Step.ESCALATE
    assert "personal" in resp.lower() or "staff" in resp.lower() or "calificado" in resp.lower()


@pytest.mark.asyncio
async def test_wants_human_signal_escalates_when_keyword_list_misses():
    """"quisiera que me atendiera una persona real" no matchea
    ESCALATION_KEYWORDS (humano/agente/asesor/"hablar con") pero la
    intención es la misma."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"wants_human": True})):
        resp = await route_message(state, "quisiera que me atendiera una persona real")
    assert state.step == Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_wants_menu_signal_resets_when_keyword_list_misses():
    """"mejor empecemos de cero" no está en MENU_KEYWORDS pero pide lo mismo
    que "menu"/"inicio"."""
    state = make_state()
    state.step = Step.MIXED_LOCATION
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"wants_menu_or_restart": True})):
        await route_message(state, "mejor empecemos de cero")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_no_signal_keeps_normal_behavior():
    """Regresión: si detect_routing_signals no encuentra nada, el
    comportamiento sigue siendo exactamente el de antes."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "hola, quiero hacer buceo mañana")
    assert state.step != Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_digit_only_message_skips_llm_call_entirely():
    """Clic de botón puramente numérico: coste cero, nunca llama al LLM."""
    state = make_state()
    signals_mock = AsyncMock(return_value={})
    with patch("src.agents.supervisor.detect_routing_signals", new=signals_mock):
        await route_message(state, "1")
    signals_mock.assert_not_called()


@pytest.mark.asyncio
async def test_sensitive_signal_escalates_with_conversational_core_on(monkeypatch):
    """La red aplica también cuando el núcleo conversacional está activo —
    se calcula UNA vez en _route_message_inner y se pasa a maybe_handle_turn,
    nunca se pierde por el camino."""
    monkeypatch.setattr(settings, "conversational_core", True)
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"sensitive_topic": "complaints_or_emergencies"})), \
         patch("src.agents.conversational_core.fill_gaps", new=AsyncMock(return_value={})):
        resp = await route_message(state, "esto es un robo, quiero mi dinero")
    assert state.step == Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_adaptive_diving_signal_routes_to_dive_to_heal_when_keyword_list_misses():
    """"perdi una pierna en un accidente, puedo bucear igual?" no matchea
    _ADAPTIVE_DIVING_PATTERN (no menciona "discapacidad" ni ninguna palabra de
    la lista) — la señal LLM debe enrutarlo igual al contexto DIVE TO HEAL,
    NO a un escalado médico genérico."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"adaptive_diving_topic": True})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG adaptativa")):
        resp = await route_message(state, "perdi una pierna en un accidente, puedo bucear igual?")
    assert state.adaptive_diving_context is True
    assert state.step != Step.ESCALATE  # no es un escalado médico genérico
    assert "Respuesta RAG adaptativa" in resp


@pytest.mark.asyncio
async def test_adaptive_diving_signal_persists_for_price_followup():
    """Tras detectar el tema por señal LLM, una pregunta de precio en el mismo
    contexto debe dar la respuesta coherente de asesor (no precios genéricos)."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"adaptive_diving_topic": True})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG adaptativa")):
        await route_message(state, "uso protesis en la pierna, hay problema para bucear?")
    assert state.adaptive_diving_context is True

    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp2 = await route_message(state, "¿cuánto cuesta?")
    assert "DIVE TO HEAL" in resp2
    assert "asesor" in resp2.lower()


# --- Bloque 2.1: cancelación/reprogramación por señal LLM (2026-07-23) ---
# La lista de keywords (_detect_cancellation_request/_detect_reschedule_request)
# solo caza frases casi exactas; medido en vivo que 16/18 frases realistas se
# escapaban. La señal booking_change_topic las recupera, misma llamada.

@pytest.mark.asyncio
async def test_cancellation_signal_routes_to_policy_when_keyword_list_misses():
    """"ya no voy a poder ir al buceo" no matchea CANCEL_BOOKING_PHRASES (frase
    indirecta) — la señal LLM debe dar la info de política + botones asesor/menú."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": "cancellation"})):
        resp = await route_message(state, "ya no voy a poder ir al buceo")
    assert resp
    assert state.quick_replies  # botones asesor/menú presentes


@pytest.mark.asyncio
async def test_reschedule_signal_routes_to_policy_when_keyword_list_misses():
    """"se puede correr la fecha?" no matchea RESCHEDULE_BOOKING_PHRASES — la
    señal LLM lo enruta a la política de reprogramación."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": "reschedule"})):
        resp = await route_message(state, "se puede correr la fecha?")
    assert resp
    assert state.quick_replies


@pytest.mark.asyncio
async def test_cancellation_policy_question_does_not_trigger_change_flow():
    """Regresión/estrictez: preguntar POR la política ("false"/omitido en la
    señal) NO debe disparar el flujo de cambio de reserva."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": False})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="La política de cancelación es...")):
        resp = await route_message(state, "cual es la politica de cancelacion?")
    assert state.step != Step.ESCALATE
    assert resp
