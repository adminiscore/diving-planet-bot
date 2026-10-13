"""ex-8 (fase EX, flag `extraccion_llm_actividad`): la actividad y la nacionalidad las decide el extractor "LLM primero".

Estudio de los inventos que quedaban con ex-5 (HISTORY 0.31.12): 23 de 28 actividades inventadas venían del regex
("bucear" = buceo certificado) y las 6 nacionalidades, del relleno de IA deduciéndola del idioma. Aquí, con el
extractor simulado: solo cuenta la actividad ELEGIDA (decisión de Gadea 14/27-sep), el minicurso deducido se recomienda,
la nacionalidad no se deduce, un cambio se confirma y el grupo mezclado paga en USD.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows.state import ConversationState


@pytest.fixture
def ex8(monkeypatch):
    monkeypatch.setattr(settings, "extraccion_llm_actividad", True)

    def con(datos):
        monkeypatch.setattr(core, "datos_del_extractor", AsyncMock(return_value=datos))

    return con


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or ConversationState(conversation_id="ex8", language="es")
    await core._understand(state, mensaje)
    return state


@pytest.mark.asyncio
async def test_bucear_a_secas_no_elige_actividad(ex8):
    ex8({})
    st = await _entender("hola, estoy embarazada de 4 meses, puedo bucear?")
    assert st.detected_activity is None


@pytest.mark.asyncio
async def test_la_actividad_elegida_la_pone_el_extractor(ex8):
    ex8({"activity": "snorkel"})
    st = await _entender("queremos hacer snorkel")
    assert st.detected_activity == "snorkel"
    assert st.detected_service_id == "snorkeling"  # el servicio sale del registro


@pytest.mark.asyncio
async def test_el_minicurso_deducido_se_recomienda_no_se_elige(ex8, monkeypatch):
    monkeypatch.setattr(settings, "recommend_inferred_minicourse", True)
    ex8({"is_certified": False})
    st = await _entender("es la primera vez que voy a hacer buceo")
    assert st.detected_activity is None
    assert st.suggested_activity in ("minicourse", "padi_open_water", None)


@pytest.mark.asyncio
async def test_la_nacionalidad_no_se_deduce_y_un_cambio_se_confirma(ex8):
    ex8({"is_colombian": False})
    st = ConversationState(conversation_id="ex8", language="es")
    st.is_colombian = True
    st = await _entender("ok perfecto", st)
    assert st.is_colombian is True
    assert (st.pending_correction or {}).get("is_colombian") is False


@pytest.mark.asyncio
async def test_grupo_mezclado_paga_en_usd(ex8):
    ex8({"mixed_nationality": True})
    st = await _entender("dos somos colombianos pero uno es extranjero")
    assert st.is_colombian is False
    assert st.mixed_nationality_notice is True


@pytest.mark.asyncio
async def test_apagado_no_cambia_nada(monkeypatch):
    monkeypatch.setattr(settings, "extraccion_llm_actividad", False)
    monkeypatch.setattr(settings, "extraccion_llm_ubicacion", False)
    monkeypatch.setattr(settings, "extraccion_llm_certificacion", False)
    llamada = AsyncMock(return_value={"activity": "snorkel"})
    monkeypatch.setattr(core, "datos_del_extractor", llamada)
    st = await _entender("quiero bucear certificado")
    assert st.detected_activity == "certified_diving"
    llamada.assert_not_called()


@pytest.mark.asyncio
async def test_el_minicurso_elegido_no_se_convierte_en_recomendacion(ex8, monkeypatch):
    """Escalón 0 de ex-8: "Buceo para principiantes" (lo elige, según el extractor) acababa como recomendación de u3-5."""
    monkeypatch.setattr(settings, "recommend_inferred_minicourse", True)
    ex8({"activity": "minicourse"})
    st = await _entender("Buceo para principiantes")
    assert st.detected_activity == "minicourse"
    assert st.suggested_activity is None


@pytest.mark.asyncio
async def test_quiere_bucear_se_recuerda_para_el_turno_de_la_certificacion(ex8):
    """Ronda ex8-B: "quiero bucear" (T1) y "soy certificado" (T3) llegan en turnos distintos; lo ya sabido lleva el
    "quiere bucear" al extractor, que con la certificación decide el buceo certificado."""
    ex8({"quiere_bucear": True})
    st = await _entender("hola quiero bucear, ya estoy en las islas")
    assert st.quiere_bucear is True and st.detected_activity is None
    assert core._sabido_para_extractor(st)["quiere_bucear"] is True


def test_la_regla_del_buceo_certificado_usa_lo_ya_sabido():
    import asyncio

    from src.agents import extractor_turno as ex
    from tests.test_extractor_turno import _cliente_que_devuelve, _si

    cliente = _cliente_que_devuelve({"is_certified": _si("soy certificado")})
    salida = asyncio.run(ex.extraer_turno("soy certificado, voy solo", sabido={"quiere_bucear": True}, client=cliente))
    assert salida["activity"] == "certified_diving"


@pytest.mark.asyncio
async def test_en_un_grupo_repartido_se_conserva_la_actividad_del_reparto(ex8):
    """Ronda ex8-B: "somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel" -> sin actividad principal, se
    repreguntaba la actividad."""
    ex8({"group_size": 6})
    st = await _entender("somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel")
    assert st.detected_activity in ("certified_diving", "minicourse", "snorkel")
