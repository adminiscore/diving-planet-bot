"""CAL-F (18-oct), flag `refresher_por_extractor`: el extractor lee si el cliente quiere o no el REFRESHER.

refresher-rechaza-acepta (3/3 en PRE): "mejor no quiero el refresher" y luego "espera, en realidad sí lo quiero, mejor
prevenir" antes de que el bot preguntara el refresher: la decisión se perdía, el bot volvía a preguntar "¿Os
interesa?" y nunca cerraba el plan con la salida y el refresher. Se fija:
1. sin el flag, la llamada es la de siempre (ni el campo ni su regla);
2. con el flag, la decisión vale con su cita, y querer el refresher siendo certificado es querer bucear;
3. el núcleo guarda lo último que decide el cliente.
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


MSG = "espera, en realidad si lo quiero, mejor prevenir"
SI = {"refresher_interested": {"valor": True, "cita": "en realidad si lo quiero"}}


@pytest.mark.asyncio
async def test_sin_flag_ni_campo_ni_regla(monkeypatch):
    monkeypatch.setattr(settings, "refresher_por_extractor", False)
    llamadas = []
    out = await ex.extraer_turno(MSG, sabido={"is_certified": True, "last_dive_over_2_years": True}, client=_cliente(SI, llamadas))
    assert "refresher_interested" not in out
    assert "refresher_interested" not in llamadas[0]["response_format"]["json_schema"]["schema"]["properties"]
    assert ex.REGLA_REFRESHER_ES not in llamadas[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_con_flag_la_decision_y_quiere_bucear(monkeypatch):
    monkeypatch.setattr(settings, "refresher_por_extractor", True)
    llamadas = []
    out = await ex.extraer_turno(MSG, sabido={"is_certified": True, "last_dive_over_2_years": True}, client=_cliente(SI, llamadas))
    assert out["refresher_interested"] is True
    assert out["activity"] == "certified_diving"  # certificado que quiere el repaso = quiere bucear
    esquema = llamadas[0]["response_format"]["json_schema"]["schema"]
    assert "refresher_interested" in esquema["properties"] and "refresher_interested" in esquema["required"]
    assert ex.REGLA_REFRESHER_ES in llamadas[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_una_cita_que_no_esta_en_el_mensaje_se_descarta(monkeypatch):
    monkeypatch.setattr(settings, "refresher_por_extractor", True)
    out = await ex.extraer_turno(MSG, sabido={"last_dive_over_2_years": True}, client=_cliente(
        {"refresher_interested": {"valor": True, "cita": "quiero el refresher"}}, []))
    assert "refresher_interested" not in out


@pytest.mark.asyncio
async def test_si_no_lleva_mas_de_2_anos_ni_campo_ni_regla(monkeypatch):
    monkeypatch.setattr(settings, "refresher_por_extractor", True)
    llamadas = []
    out = await ex.extraer_turno(MSG, sabido={"is_certified": True}, client=_cliente(SI, llamadas))
    assert "refresher_interested" not in out
    assert ex.REGLA_REFRESHER_ES not in llamadas[0]["messages"][0]["content"]


@pytest.mark.parametrize("flag, antes, dice, queda", [
    (True, False, True, True),    # "mejor no" y luego "en realidad sí": vale lo último
    (True, None, False, False),
    (False, None, True, None),    # sin el flag, como hoy
])
def test_el_nucleo_guarda_lo_ultimo(monkeypatch, flag, antes, dice, queda):
    monkeypatch.setattr(settings, "refresher_por_extractor", flag)
    st = ConversationState(conversation_id="calf-refresher")
    st.refresher_interested = antes
    core._poner_refresher(st, {"refresher_interested": dice})
    assert st.refresher_interested is queda
