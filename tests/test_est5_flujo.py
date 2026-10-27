"""EX-EST-2, tanda est5: arreglos del flujo por causa."""
import asyncio

import pytest

from src.agents.conversational_core import guardar_lo_dicho_en_el_pase
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
    # CALN (s2-familia-ninos-pequenos): también `location`, la que mira la reserva; si no, volvía a preguntar el origen.
    assert state.location == "island"
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
