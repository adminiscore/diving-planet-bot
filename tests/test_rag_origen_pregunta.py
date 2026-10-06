"""6-oct, flag `rag_origen_pregunta` (punto 3: el ORIGEN del cliente).

Con el origen desconocido el contexto del RAG no decía nada y el modelo cotizaba "desde Cartagena" (o "ya en las
islas") por su cuenta: 15 de 63 fallos visibles de la ronda 2026-10-02-completa. Se fija:
1. el contexto lo dice (y pide preguntarlo antes de cotizar) solo si NO sabemos el origen y con el flag;
2. si la reserva iba a preguntar el origen y la respuesta ya lo pregunta, la pregunta sale UNA vez, con sus botones.
"""
import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import _build_extra_context
from src.config import settings
from src.flows.state import ConversationState, Step
from src.prompts.info import RAG_ORIGEN_DESCONOCIDO_ES

PREGUNTA_RAG = ("El precio depende de desde dónde salgan. ¿Saldrían desde Cartagena o ya están en las islas?")


def _estado(location=None) -> ConversationState:
    s = ConversationState(conversation_id="origen", language="es")
    s.step = Step.FREE_TEXT
    s.location = location
    s.history = [{"role": "user", "content": "¿cuánto cuesta el minicurso?"}]
    return s


@pytest.mark.parametrize("flag,location,dice", [
    (True, None, True), (False, None, False), (True, "cartagena", False), (True, "island", False)])
def test_el_contexto_avisa_del_origen_desconocido_solo_si_no_lo_sabemos(monkeypatch, flag, location, dice):
    monkeypatch.setattr(settings, "rag_origen_pregunta", flag)
    assert (RAG_ORIGEN_DESCONOCIDO_ES in (_build_extra_context(_estado(location)) or "")) is dice


@pytest.mark.parametrize("flag,slot,respuesta,va_sola", [
    (True, core.SLOT_LOCATION, PREGUNTA_RAG, True),
    (True, core.SLOT_LOCATION, "Where would you be departing from: Cartagena or the islands?", True),
    # escalón 0 en PRE (6-oct): formas reales del RAG que la primera versión no reconocía
    (True, core.SLOT_LOCATION, "¿Desde dónde prefieren salir ustedes? Así te paso el link correcto.", True),
    (True, core.SLOT_LOCATION, "¿me confirmas si saldrían desde Cartagena o si ya están en las islas?", True),
    (False, core.SLOT_LOCATION, PREGUNTA_RAG, False),
    (True, core.SLOT_QTY, PREGUNTA_RAG, False),
    (True, core.SLOT_LOCATION, "El minicurso cuesta 655.000 COP desde Cartagena.", False),
])
def test_la_respuesta_que_ya_pregunta_el_origen_va_sola(monkeypatch, flag, slot, respuesta, va_sola):
    monkeypatch.setattr(settings, "rag_origen_pregunta", flag)
    state = _estado()
    state.core_pending_slot = slot
    assert core._answer_asks_the_origin(state, respuesta) is va_sola


@pytest.mark.asyncio
async def test_sin_doble_pregunta_del_origen_y_con_sus_botones(monkeypatch):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    state = _estado()
    pregunta_reserva = core.ask_slot(state, core.SLOT_LOCATION)
    botones = list(state.quick_replies)

    async def _respuesta(_state):
        return PREGUNTA_RAG

    monkeypatch.setattr(core, "_take_parallel_answer", _respuesta)
    final = await core._prepend_parallel_answer(state, pregunta_reserva, "")
    assert final == PREGUNTA_RAG
    assert state.quick_replies == botones and botones
