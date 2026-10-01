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


def test_no_se_adelanta_con_el_flag_apagado(flags, monkeypatch):
    state = _estado()
    monkeypatch.setattr(settings, "rag_adelantado", False)
    core.lanzar_rag_adelantado(state, "¿qué incluye?")
    assert getattr(state, "_rag_adelantado", None) is None


def _primer_turno() -> ConversationState:
    s = ConversationState(conversation_id="rag5-primero")
    s.step = Step.WELCOME
    return s


def test_primer_mensaje_sin_idioma_claro_no_se_adelanta(flags):
    """Si la regla rápida no sabe el idioma, `_setup_phase` preguntará al LLM: no se adivina."""
    state = _primer_turno()
    core.lanzar_rag_adelantado(state, "👍")
    assert getattr(state, "_rag_adelantado", None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mensaje, idioma", [("hola, cuánto cuesta el minicurso?", "es"),
                                             ("how much is the mini course?", "en")])
async def test_primer_mensaje_se_adelanta_con_el_idioma_y_el_paso_que_dejara_setup(flags, monkeypatch, mensaje, idioma):
    """La foto queda como la dejará `_setup_phase` (idioma y conversación libre): la huella coincide y el RAG corre
    una sola vez, en el idioma bueno. El resumen falso depende del idioma y del paso, para que se note si no."""
    async def _sin_notas(*a, **k):
        return None

    monkeypatch.setattr(core, "_maybe_capture_notes", _sin_notas)
    rag = _RagFalso()
    state = _primer_turno()
    with patch("src.agents.supervisor.rag_answer", new=rag), \
         patch("src.agents.supervisor._build_extra_context", side_effect=lambda s: f"{s.language}|{s.step}"):
        core.lanzar_rag_adelantado(state, mensaje)
        await core._setup_phase(state, mensaje, {})
        core._maybe_launch_answer(state, mensaje, {})
        await core._take_parallel_answer(state)
    assert len(rag.llamadas) == 1
    assert rag.llamadas[0][1]["lang"] == idioma and state.language == idioma


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
