"""rag-5 (30-sep): el RAG arranca a la vez que el enrutador y solo se aprovecha con el MISMO contexto que tendría
la llamada de siempre (flag `rag_adelantado`)."""
import asyncio
from unittest.mock import patch

import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows.state import ConversationState, Step


def _estado() -> ConversationState:
    s = ConversationState(conversation_id="rag5", language="es")
    s.step = Step.FREE_TEXT
    s.history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"}]
    return s


class _RagFalso:
    """Cuenta las llamadas y devuelve el resumen del estado que recibió, para saber con qué contexto contestó."""

    def __init__(self):
        self.llamadas = []

    async def __call__(self, query, **kw):
        self.llamadas.append((query, kw))
        await asyncio.sleep(0)
        return f"respuesta con [{kw.get('extra_context')}]"


@pytest.fixture
def flags(monkeypatch):
    monkeypatch.setattr(settings, "rag_adelantado", True)
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "notes_in_parallel", False)


def _turno_hasta_la_reserva(state, message):
    """Lo que hacen el enrutador (lanza el adelantado) y `_setup_phase` (mete el mensaje en el historial)."""
    core.lanzar_rag_adelantado(state, message)
    state.history.append({"role": "user", "content": message})


@pytest.mark.asyncio
async def test_con_el_mismo_contexto_se_aprovecha_y_el_rag_corre_una_sola_vez(flags):
    rag = _RagFalso()
    state = _estado()
    with patch("src.agents.supervisor.rag_answer", new=rag), \
         patch("src.agents.supervisor._build_extra_context", side_effect=lambda s: "Fecha y hora actual: 2026-09-30 "
               "10:00 (hora de Cartagena/Colombia). Sale desde Cartagena."):
        _turno_hasta_la_reserva(state, "¿qué incluye?")
        core._maybe_launch_answer(state, "¿qué incluye?", {})
        respuesta = await core._take_parallel_answer(state)
    assert len(rag.llamadas) == 1
    assert "Sale desde Cartagena" in respuesta
    # el historial con el que contestó es el de siempre: con el mensaje del cliente dentro
    assert rag.llamadas[0][1]["history"][-1] == {"role": "user", "content": "¿qué incluye?"}


@pytest.mark.asyncio
async def test_la_hora_del_resumen_no_cuenta_para_la_huella(flags):
    rag = _RagFalso()
    state = _estado()
    horas = iter(["10:00", "10:01"])
    with patch("src.agents.supervisor.rag_answer", new=rag), \
         patch("src.agents.supervisor._build_extra_context",
               side_effect=lambda s: f"Fecha y hora actual: 2026-09-30 {next(horas)} (hora de Cartagena/Colombia). X."):
        _turno_hasta_la_reserva(state, "¿qué incluye?")
        core._maybe_launch_answer(state, "¿qué incluye?", {})
        await core._take_parallel_answer(state)
    assert len(rag.llamadas) == 1


@pytest.mark.asyncio
async def test_si_el_contexto_cambio_entre_medias_se_rehace_con_el_de_verdad(flags):
    rag = _RagFalso()
    state = _estado()
    resumenes = iter(["antes", "despues"])  # p. ej. una nota nueva de este mensaje
    with patch("src.agents.supervisor.rag_answer", new=rag), \
         patch("src.agents.supervisor._build_extra_context", side_effect=lambda s: next(resumenes)):
        _turno_hasta_la_reserva(state, "¿qué incluye?")
        core._maybe_launch_answer(state, "¿qué incluye?", {})
        with patch("src.observability.note_turn") as note:
            respuesta = await core._take_parallel_answer(state)
    assert len(rag.llamadas) == 2
    assert respuesta == "respuesta con [despues]"
    # queda apuntado QUÉ cambió, para saber por qué no se aprovechó
    assert note.call_args.kwargs == {"rag_adelantado": "rehecho", "rag_rehecho_por": "resumen"}


@pytest.mark.asyncio
async def test_si_el_turno_no_la_usa_se_cancela_al_cerrarlo(flags):
    state = _estado()

    async def lento(query, **kw):
        await asyncio.sleep(10)

    with patch("src.agents.supervisor.rag_answer", new=lento), \
         patch("src.agents.supervisor._build_extra_context", return_value="x"):
        core.lanzar_rag_adelantado(state, "vale, gracias")
        tarea = state._rag_adelantado["task"]
        core.cancelar_rag_adelantado(state)
        await asyncio.sleep(0)
    assert tarea.cancelled() and state._rag_adelantado is None


def test_no_se_adelanta_en_el_primer_turno_ni_con_el_flag_apagado(flags, monkeypatch):
    state = _estado()
    state.step = Step.WELCOME
    core.lanzar_rag_adelantado(state, "¿qué incluye?")
    assert getattr(state, "_rag_adelantado", None) is None
    state.step = Step.FREE_TEXT
    monkeypatch.setattr(settings, "rag_adelantado", False)
    core.lanzar_rag_adelantado(state, "¿qué incluye?")
    assert getattr(state, "_rag_adelantado", None) is None


@pytest.mark.asyncio
async def test_la_adelantada_no_marca_el_turno_como_rag_hasta_que_se_aprovecha(flags):
    from src.agents.rag_agent import RAG_ADELANTADO

    vistos = []

    async def rag(query, **kw):
        vistos.append(RAG_ADELANTADO.get())
        return "ok"

    state = _estado()
    with patch("src.agents.supervisor.rag_answer", new=rag), \
         patch("src.agents.supervisor._build_extra_context", return_value="x"):
        core.lanzar_rag_adelantado(state, "¿qué incluye?")
        await state._rag_adelantado["task"]
    assert vistos == [True] and RAG_ADELANTADO.get() is False
