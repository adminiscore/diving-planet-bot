"""Fase 3.4 — reducción de llamadas LLM/turno.

Fija la primera optimización: un saludo puro no dispara `fill_gaps` (no hay
slots que extraer), pero un mensaje con contenido de reserva sí. Así el ahorro
de 1 llamada en el turno de saludo no se pierde en una regresión futura.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.conversational_core import _is_greeting_only, _understand
from src.flows.state import ConversationState, Step


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="reduction-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


@pytest.mark.parametrize("msg, expected", [
    ("hola", True),
    ("¡Hola!", True),
    ("  buenas   tardes  ", True),
    ("hi", True),
    ("hey", True),
    # saludo + cortesía / combinaciones (bug en vivo 2026-09-16): también es saludo
    ("hola buenas", True),
    ("hola buenas que tal?", True),
    ("¿qué tal?", True),
    ("buenas que tal", True),
    ("hi how are you", True),
    ("hola quiero bucear", False),      # saludo + contenido → NO es puro
    ("que tal el buceo nocturno?", False),  # cortesía + contenido real → NO
    ("somos 2 personas", False),
    ("buenos días, ya soy certificada", False),
])
def test_is_greeting_only(msg, expected):
    assert _is_greeting_only(msg) is expected


@pytest.mark.asyncio
async def test_greeting_smalltalk_first_turn_does_not_hit_rag(monkeypatch):
    """Bug en vivo (2026-09-16): "hola buenas que tal?" daba saludo + el fallback
    de asesor de RAG ("ese detalle no lo tengo a la mano..."). Un saludo+cortesía
    NO es una pregunta de info → no debe llegar a RAG (`_answer_question`)."""
    answer_q = AsyncMock(return_value="RAG-NO-DEBERIA-LLAMARSE")
    monkeypatch.setattr(core, "_answer_question", answer_q)
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))

    reply = await core.maybe_handle_turn(make_state(step=Step.WELCOME), "hola buenas que tal?",
                                         routing_signals={})
    answer_q.assert_not_awaited()          # no se fue a RAG
    assert reply and "RAG-NO-DEBERIA-LLAMARSE" not in reply  # respondió (el saludo)


@pytest.mark.asyncio
async def test_greeting_only_skips_fill_gaps(monkeypatch):
    fake = AsyncMock(return_value={})
    monkeypatch.setattr(core, "fill_gaps", fake)
    await _understand(make_state(), "hola")
    fake.assert_not_awaited()  # saludo puro → sin llamada LLM de extracción


@pytest.mark.asyncio
async def test_message_with_content_still_calls_fill_gaps(monkeypatch):
    fake = AsyncMock(return_value={})
    monkeypatch.setattr(core, "fill_gaps", fake)
    # Mensaje con intención de reserva pero sin reparto explícito → hay gaps que
    # el regex no cierra, así que fill_gaps DEBE correr.
    await _understand(make_state(), "hola, nos gustaría explorar el mundo submarino")
    fake.assert_awaited()
