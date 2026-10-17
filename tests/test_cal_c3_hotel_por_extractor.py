"""CAL-C3 (17-oct), flag `hotel_por_extractor`: el extractor lee el HOTEL donde se aloja el cliente, sin lista cerrada.

Banco CAL: "staying at Isla Mulata on Isla Grande" (cal-41) y "We will be staying at Bodegas de Santa Clara" (cal-67/68)
se perdían (el regex solo conoce los hoteles de las islas) y el bot preguntaba "¿En qué hotel o isla te hospedas?".
Se fija:
1. sin el flag, la llamada es la de siempre (ni el campo ni su regla);
2. con el flag, el hotel vale solo si su nombre está en el mensaje (cita comprobada);
3. el núcleo lo guarda si la conversación aún no tiene hotel; el del regex (con su isla) manda.
"""

import json

import pytest

from src.agents import conversational_core as core
from src.agents import extractor_turno as ex
from src.config import settings
from src.flows.state import ConversationState


def _cliente(datos: dict, llamadas: list):
    class _C:
        async def create(self, **kw):
            llamadas.append(kw)
            msg = type("M", (), {"content": json.dumps(datos)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


MSG = "We will be staying at Bodegas de Santa Clara. June 6-13"


@pytest.mark.asyncio
async def test_sin_flag_ni_campo_ni_regla(monkeypatch):
    monkeypatch.setattr(settings, "hotel_por_extractor", False)
    llamadas = []
    out = await ex.extraer_turno(MSG, lang="en", client=_cliente(
        {"hotel": {"valor": "Bodegas de Santa Clara", "cita": "Bodegas de Santa Clara"}}, llamadas))
    assert "hotel" not in out
    assert "hotel" not in llamadas[0]["response_format"]["json_schema"]["schema"]["properties"]
    assert ex.REGLA_HOTEL_EN not in llamadas[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_con_flag_el_hotel_con_su_cita(monkeypatch):
    monkeypatch.setattr(settings, "hotel_por_extractor", True)
    llamadas = []
    out = await ex.extraer_turno(MSG, lang="en", client=_cliente(
        {"hotel": {"valor": "Bodegas de Santa Clara", "cita": "staying at Bodegas de Santa Clara"}}, llamadas))
    assert out["hotel"] == "Bodegas de Santa Clara"
    esquema = llamadas[0]["response_format"]["json_schema"]["schema"]
    assert "hotel" in esquema["properties"] and "hotel" in esquema["required"]
    assert ex.REGLA_HOTEL_EN in llamadas[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_un_hotel_que_no_esta_en_el_mensaje_se_descarta(monkeypatch):
    monkeypatch.setattr(settings, "hotel_por_extractor", True)
    out = await ex.extraer_turno(MSG, lang="en", client=_cliente(
        {"hotel": {"valor": "Sofitel Legend Santa Clara", "cita": "Bodegas de Santa Clara"}}, []))
    assert "hotel" not in out
    assert "hotel" in ex.extraer_turno.ultimo_motivo


def _intent():
    return type("I", (), {"hotel": None, "detected_fields": []})()


def test_el_nucleo_guarda_el_hotel_si_no_hay_otro(monkeypatch):
    monkeypatch.setattr(settings, "hotel_por_extractor", True)
    st, it = ConversationState(conversation_id="c3"), _intent()
    core._poner_hotel(it, st, {"hotel": "Isla Mulata"})
    assert it.hotel == "Isla Mulata" and "hotel" in it.detected_fields


def test_manda_el_hotel_que_ya_hay_y_sin_flag_nada(monkeypatch):
    monkeypatch.setattr(settings, "hotel_por_extractor", True)
    st, it = ConversationState(conversation_id="c3"), _intent()
    it.hotel = "hotel_san_pedro_de_majagua"  # el del regex, con su isla
    core._poner_hotel(it, st, {"hotel": "Majagua"})
    assert it.hotel == "hotel_san_pedro_de_majagua"
    st2, it2 = ConversationState(conversation_id="c3", hotel="Coral Sand"), _intent()
    core._poner_hotel(it2, st2, {"hotel": "Otro"})
    assert it2.hotel is None
    monkeypatch.setattr(settings, "hotel_por_extractor", False)
    it3 = _intent()
    core._poner_hotel(it3, ConversationState(conversation_id="c3"), {"hotel": "Isla Mulata"})
    assert it3.hotel is None
