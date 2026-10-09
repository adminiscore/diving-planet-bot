"""Flag `origen_del_cliente` (s4-28, 9-oct): el origen (`location`) que rellena el extractor LLM solo vale si algún
mensaje del CLIENTE nombra un lugar o si Jev dice que este mensaje lo afirma.

Caso real (`familia-mixta-precio-descuento-refresher`, PRE): con la pregunta del origen pendiente, el cliente contesta
"May 3rd" y el extractor devuelve `location=cartagena`, sacado del texto del bot ("¿saldrías desde Cartagena…?"); el
bot contestaba entonces la pregunta guardada con el precio de Cartagena.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState

PREGUNTA_BOT = "¿Saldrías desde Cartagena o ya estás en las islas?"


def _estado(*mensajes_cliente: str) -> ConversationState:
    st = ConversationState(conversation_id="origen-cliente")
    st.history = []
    for m in mensajes_cliente:
        st.history += [{"role": "user", "content": m}, {"role": "assistant", "content": PREGUNTA_BOT}]
    return st


@pytest.mark.parametrize("antes,mensaje,nombra", [
    (["Hi, I want to book 2 dives"], "May 3rd", False),               # el caso: solo el BOT nombra Cartagena
    (["quiero bucear"], "el 3 de mayo", False),
    (["Hi, we arrive in Cartagena on Monday"], "May 3rd", True),      # lo dijo antes
    (["hola"], "estamos alojados en el Cocoliso", True),              # un hotel de las islas
    (["hola"], "nos quedamos en Barú", True),                         # las pistas de la puerta del origen
    (["hola"], "we'll be in the walled city", True),                  # apodo de Cartagena
    (["hola"], "we are staying on Isla Grande", True),
    (["El todo mar donde se van a encontrar donde es?"], "Me dijiste que a las 7:30 am", True),  # muelle de Cartagena
    (["hola"], "El de boca grande?", True),                                                     # barrio de Cartagena
])
def test_cliente_nombra_un_lugar(antes, mensaje, nombra):
    assert core._cliente_nombra_un_lugar(_estado(*antes), mensaje) is nombra


@pytest.fixture
def extractor_inventa_cartagena(monkeypatch):
    """La reserva entera sin red; el extractor (relleno y combinado) devuelve SIEMPRE location=cartagena."""
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={"location": "cartagena"}))
    monkeypatch.setattr(core, "extract_and_verify", AsyncMock(return_value=({"location": "cartagena"}, {})))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))
    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(settings, "ack_in_parallel", False)
    monkeypatch.setattr(settings, "rag_adelantado", False)

    async def _senales(message, **_k):
        return {}

    monkeypatch.setattr(supervisor, "detect_routing_signals", _senales)
    monkeypatch.setattr(supervisor, "rag_answer", AsyncMock(return_value="RESPUESTA_RAG"))


@pytest.mark.parametrize("flag,queda", [(True, None), (False, "cartagena")])
async def test_may_3rd_no_se_vuelve_cartagena(monkeypatch, extractor_inventa_cartagena, flag, queda):
    monkeypatch.setattr(settings, "origen_del_cliente", flag)
    st = ConversationState(conversation_id="may-3rd", language="en")
    await route_message(st, "Hi, I want to book 2 dives for my family, we are all certified")
    await route_message(st, "May 3rd")
    assert st.location == queda


async def test_si_el_cliente_lo_dijo_se_guarda(monkeypatch, extractor_inventa_cartagena):
    monkeypatch.setattr(settings, "origen_del_cliente", True)
    st = ConversationState(conversation_id="lo-dijo", language="en")
    await route_message(st, "Hi, we land in Cartagena on May 2nd and want to dive, we are certified")
    await route_message(st, "May 3rd")
    assert st.location == "cartagena"
