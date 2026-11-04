"""Sparring s04c (4-nov, jubilados t2): la puerta del origen de la respuesta en paralelo, al recogerla, con el origen que
la extracción de ESE mensaje ya guardó (`conversational_core._con_la_puerta`)."""
import asyncio
from unittest.mock import patch

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState, Step

MENSAJE = "Desde Cartagena. Somos argentinos. ¿Y mi esposa qué puede hacer?"


def _estado() -> ConversationState:
    s = ConversationState(conversation_id="s04c", language="es")
    s.step = Step.FREE_TEXT
    s.history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"},
                 {"role": "user", "content": MENSAJE}]
    return s


async def _rag(query, **kw):
    return "Tu esposa puede hacer el minicurso: 183 USD."


def _puerta_que_apunta(vistos):
    def puerta(st, mensaje, answer, sin_precio=False, pieza_pedida=False):
        vistos.append((st.location, mensaje, sin_precio))
        return f"{answer} [puerta]"
    return puerta


@pytest.mark.asyncio
@pytest.mark.parametrize("adelantado", [False, True])
async def test_el_escritor_acaba_antes_que_la_extraccion_y_la_puerta_ve_el_origen(adelantado):
    """En PRE, el escritor acabó antes que el extractor (2,2 s): la puerta no veía «Desde Cartagena», ponía los precios
    de los dos orígenes y la pregunta del origen, y debajo otra vez la de la reserva."""
    state, vistos = _estado(), []
    with patch("src.agents.supervisor.rag_answer", new=_rag), \
         patch("src.agents.supervisor._build_extra_context", return_value="X"), \
         patch.object(core, "_puerta_del_origen", side_effect=_puerta_que_apunta(vistos)):
        if adelantado:
            state.history = state.history[:-1]
            core.lanzar_rag_adelantado(state, MENSAJE)
            state.history.append({"role": "user", "content": MENSAJE})
        core._maybe_launch_answer(state, MENSAJE, {})
        await asyncio.wait([state._pending_answer])  # la respuesta, lista antes que la extracción
        assert vistos == []
        state.location = "cartagena"  # la extracción de este mensaje
        respuesta = await core._take_parallel_answer(state)
    assert vistos == [("cartagena", MENSAJE, False)]
    assert respuesta.endswith("[puerta]")
    assert state._puerta_al_recoger is None


@pytest.mark.asyncio
async def test_fuera_del_paralelo_la_puerta_va_dentro_como_siempre():
    state, vistos = _estado(), []
    with patch("src.agents.supervisor.rag_answer", new=_rag), \
         patch("src.agents.supervisor._build_extra_context", return_value="X"), \
         patch.object(core, "_puerta_del_origen", side_effect=_puerta_que_apunta(vistos)):
        respuesta = await core._rag_answer(state, MENSAJE)
    assert vistos == [(None, MENSAJE, False)] and respuesta.endswith("[puerta]")
    assert getattr(state, "_puerta_al_recoger", None) is None


@pytest.mark.asyncio
async def test_si_el_turno_no_la_recoge_no_queda_puerta_para_el_siguiente():
    state, vistos = _estado(), []
    with patch("src.agents.supervisor.rag_answer", new=_rag), \
         patch("src.agents.supervisor._build_extra_context", return_value="X"), \
         patch.object(core, "_puerta_del_origen", side_effect=_puerta_que_apunta(vistos)):
        core._maybe_launch_answer(state, MENSAJE, {})
        await asyncio.wait([state._pending_answer])
        core.cancel_pending_answer(state)
    assert state._puerta_al_recoger is None and vistos == []
