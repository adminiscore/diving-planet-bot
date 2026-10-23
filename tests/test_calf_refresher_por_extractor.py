"""CAL-F (18-oct; promocionado, sus flags se borraron en sim-5): el extractor lee si el cliente quiere o no el REFRESHER.

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
async def test_la_decision_y_quiere_bucear():
    llamadas = []
    out = await ex.extraer_turno(MSG, sabido={"is_certified": True, "last_dive_over_2_years": True}, client=_cliente(SI, llamadas))
    assert out["refresher_interested"] is True
    assert out["activity"] == "certified_diving"  # certificado que quiere el repaso = quiere bucear
    esquema = llamadas[0]["response_format"]["json_schema"]["schema"]
    assert "refresher_interested" in esquema["properties"] and "refresher_interested" in esquema["required"]
    assert ex.REGLA_REFRESHER_ES in llamadas[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_una_cita_que_no_esta_en_el_mensaje_se_descarta(monkeypatch):
    out = await ex.extraer_turno(MSG, sabido={"last_dive_over_2_years": True}, client=_cliente(
        {"refresher_interested": {"valor": True, "cita": "quiero el refresher"}}, []))
    assert "refresher_interested" not in out


@pytest.mark.asyncio
async def test_si_no_lleva_mas_de_2_anos_ni_campo_ni_regla(monkeypatch):
    llamadas = []
    out = await ex.extraer_turno(MSG, sabido={"is_certified": True}, client=_cliente(SI, llamadas))
    assert "refresher_interested" not in out
    assert ex.REGLA_REFRESHER_ES not in llamadas[0]["messages"][0]["content"]


@pytest.mark.parametrize("antes, dice, queda", [
    (False, True, True),    # "mejor no" y luego "en realidad sí": vale lo último
    (None, False, False),
])
def test_el_nucleo_guarda_lo_ultimo(antes, dice, queda):
    st = ConversationState(conversation_id="calf-refresher")
    st.refresher_interested = antes
    core._poner_refresher(st, {"refresher_interested": dice})
    assert st.refresher_interested is queda


# CAL-F grupo-mixto-precio-cop-total (flag `actividad_del_reparto`): la actividad que no es de nadie del reparto -----

AVANZADO = {"activity": {"valor": "padi_advanced", "cita": "1 buzo avanzado"},
            "group_allocation": {"valor": {"certified_diving": 1, "minicourse": 2},
                                 "cita": "1 buzo avanzado y 2 para bautismo"}}


@pytest.mark.asyncio
async def test_la_actividad_sale_del_reparto():
    out = await ex.extraer_turno("Vamos en familia a Cartagena. 1 buzo avanzado y 2 para bautismo",
                                 client=_cliente(AVANZADO, []))
    assert out["activity"] == "certified_diving"


@pytest.mark.asyncio
async def test_si_la_actividad_esta_en_el_reparto_no_se_toca(monkeypatch):
    datos = {"activity": {"valor": "minicourse", "cita": "el de 12 minicurso"},
             "group_allocation": {"valor": {"minicourse": 1, "snorkel": 1}, "cita": "el de 12 minicurso y el de 8 snorkel"}}
    out = await ex.extraer_turno("el de 12 minicurso y el de 8 snorkel", client=_cliente(datos, []))
    assert out["activity"] == "minicourse"


# CAL-F precios-y-disponibilidad (flag `origen_neutro_con_dos_planes`): duda entre un plan de 1 día y uno de varios ---

def test_con_dos_planes_la_pregunta_del_origen_es_neutra():
    st = ConversationState(conversation_id="calf-origen")
    st.language = "es"
    st.detected_activity, st.detected_service_id, st.detected_duration = "certified_diving", "2_dives_1_day", "multi_day"
    texto = core.ask_slot(st, core.SLOT_LOCATION)
    assert "dormir en las islas" not in texto
    assert "dura 1 día" not in texto


def test_con_el_paquete_elegido_sigue_diciendo_que_hay_que_dormir(monkeypatch):
    from src.flows.catalog import OVERNIGHT_SERVICES

    st = ConversationState(conversation_id="calf-origen")
    st.language = "es"
    st.detected_activity, st.detected_duration = "certified_diving", "multi_day"
    st.detected_service_id = sorted(OVERNIGHT_SERVICES)[0]
    assert "dormir en las islas" in core.ask_slot(st, core.SLOT_LOCATION)
