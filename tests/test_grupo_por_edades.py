"""Flag `grupo_por_edades` (9-oct, fallos del flujo de reserva): cada EDAD que da el mensaje cuenta como una persona
para respaldar el reparto del grupo, y el detector lee también "age 17" en singular (no "minimum age").

Caso: `familia-mixta-precio-descuento-refresher`, primer mensaje: "2 adults (ages 42, 19) / 1 youth (age 17) /
Snorkeling / 1 Adult (Age 43) / 2 kids (Ages 14, 10)". El reparto {buceo 3, snorkel 3} que devolvía el extractor era
correcto, pero ningún "3" está escrito: la guarda de cifras lo tiraba y el bot preguntaba "¿cuántos serían para buceo
certificado?" (repregunta en el golden). En PRE con el flag: 3/3 guardan 6 personas, 3 y 3.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState

FAMILIA = ("Hi There,\nI am looking to book 2 dives and snorkeling sessions for the following people.\n"
           "2 diving sessions - All PADI certified for open water.\n2 adults (ages 42, 19)\n1 youth (age 17)\n"
           "Snorkeling\n1 Adult (Age 43)\n2 kids (Ages 14, 10)\nCan you provide information and total price please")


def _edades(mensaje: str) -> list[int]:
    return sorted(core._detector.detect(mensaje, ConversationState(conversation_id="e")).ages or [])


@pytest.mark.parametrize("flag,mensaje,edades", [
    (True, FAMILIA, [10, 14, 17, 19, 42, 43]),
    (False, FAMILIA, [10, 14, 19, 42]),                      # sin el flag, "age 17" y "Age 43" se perdían
    (True, "my son (age 9) will snorkel", [9]),
    (True, "what's the minimum age 10 for snorkel?", []),   # una regla, no una persona
    (True, "kids aged 8 and 10", [8, 10]),                   # lo de siempre sigue igual
])
def test_edades_en_singular(monkeypatch, flag, mensaje, edades):
    monkeypatch.setattr(settings, "grupo_por_edades", flag)
    assert _edades(mensaje) == edades


@pytest.fixture
def extractor_reparte(monkeypatch):
    """La reserva entera sin red; el extractor devuelve el reparto correcto de la familia (3 bucean, 3 snorkel)."""
    reparto = {"group_size": 6, "group_allocation": {"certified_diving": 3, "snorkel": 3}}
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value=dict(reparto)))
    monkeypatch.setattr(core, "extract_and_verify", AsyncMock(return_value=(dict(reparto), {})))
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


@pytest.mark.parametrize("flag,reparto", [
    (True, {"certified_diving": 3, "snorkel": 3}),
    (False, None),  # sin el flag la guarda lo tira (no hay un "3" escrito)
])
async def test_el_reparto_lo_respaldan_las_edades(monkeypatch, extractor_reparte, flag, reparto):
    monkeypatch.setattr(settings, "grupo_por_edades", flag)
    st = ConversationState(conversation_id="familia", language="en")
    await route_message(st, FAMILIA)
    assert (st.detected_group_allocation or None) == reparto
