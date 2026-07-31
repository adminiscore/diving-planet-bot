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
    ("hola quiero bucear", False),      # saludo + contenido → NO es puro
    ("somos 2 personas", False),
    ("buenos días, ya soy certificada", False),
])
def test_is_greeting_only(msg, expected):
    assert _is_greeting_only(msg) is expected


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
