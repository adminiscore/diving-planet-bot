"""EX-EST-2, tanda est5: arreglos del flujo por causa."""
import asyncio

import pytest

from src.agents.conversational_core import guardar_lo_dicho_en_el_pase
from src.config import settings
from src.flows.state import ConversationState


def _con_extraccion(datos: dict | None, **estado) -> ConversationState:
    state = ConversationState(conversation_id="est5")
    for k, v in estado.items():
        setattr(state, k, v)

    async def _extrae():
        return datos

    state._extraccion_adelantada = asyncio.ensure_future(_extrae())
    return state


async def test_el_turno_del_pase_guarda_lo_que_dijo_el_cliente(monkeypatch):
    """`recogida-ubuntu` (est3-B): "We are staying at the Ubuntu Hotel" en el mensaje que pasa a una persona; en el
    turno siguiente el bot preguntaba desde dónde saldría."""
    state = _con_extraccion({"location": "island", "activity": "minicourse", "group_size": 2})
    await guardar_lo_dicho_en_el_pase(state)
    assert state.detected_location == "island"
    assert state.detected_activity == "minicourse"
    assert state.detected_group_size == 2
    assert state._extraccion_adelantada is None


async def test_no_pisa_lo_que_ya_se_sabia(monkeypatch):
    state = _con_extraccion({"location": "island", "group_size": 3}, detected_location="cartagena",
                            detected_group_size=2)
    await guardar_lo_dicho_en_el_pase(state)
    assert state.detected_location == "cartagena"
    assert state.detected_group_size == 2


@pytest.mark.parametrize("datos", [None, {}, {"location": "bogota", "group_size": 0}])
async def test_sin_datos_validos_no_cambia_nada(monkeypatch, datos):
    state = _con_extraccion(datos)
    await guardar_lo_dicho_en_el_pase(state)
    assert state.detected_location is None
    assert state.detected_group_size is None


def test_jev_cuenta_las_peticiones_en_imperativo():
    """"dame la cuenta y transfiero" o "send me the payment link" también son algo que contestar."""
    from src.agents import jev_router

    pregunta = jev_router._questions_for_turn()[jev_router.ASKS_QUESTION]
    assert pregunta is jev_router._ASKS_QUESTION_Q_V2
    assert "send me the link" in pregunta["instructions"]


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("flag", [True, False])
def test_el_rag_no_supone_la_hora_solo_con_el_flag(monkeypatch, flag, lang):
    """`rag_sin_hora`: "ya pasó esa hora" sobre el cierre de las 4:30 sin que el cliente dijera la hora."""
    from src.agents.rag_agent import build_system_prompt
    from src.prompts.info import RAG_SIN_HORA_EN, RAG_SIN_HORA_ES

    monkeypatch.setattr(settings, "rag_sin_hora", flag)
    regla = RAG_SIN_HORA_ES if lang == "es" else RAG_SIN_HORA_EN
    assert (regla in build_system_prompt(lang)) is flag
