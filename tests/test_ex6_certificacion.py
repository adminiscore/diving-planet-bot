"""ex-6 (fase EX, flag `extraccion_llm_certificacion`): la certificación y la última inmersión las decide el extractor.

Banco ex0 (diseño, 12-oct): el regex leía "take the PADI Open Water Diver course" como YA certificado (4 casos) y "ya he
buceado con ustedes" también; el relleno sacaba la certificación de un "gracias". Aquí, con el extractor simulado: lo
del regex es pista, un cambio se confirma, y un nivel nombrado sin decir si lo tiene o lo quiere se sigue preguntando.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _grupo_camino_antiguo(monkeypatch):
    """Estos tests fijan el grupo por el camino de antes de ex-7 (regex y redes LLM); con `extraccion_llm_grupo` lo
    decide el extractor (tests/test_ex7_grupo.py)."""
    from src.config import settings as _flags

    monkeypatch.setattr(_flags, "extraccion_llm_grupo", False)


@pytest.fixture
def ex6(monkeypatch):
    monkeypatch.setattr(settings, "extraccion_llm_certificacion", True)

    def con(datos):
        monkeypatch.setattr(core, "datos_del_extractor", AsyncMock(return_value=datos))

    return con


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or ConversationState(conversation_id="ex6", language="en")
    await core._understand(state, mensaje)
    return state


@pytest.mark.asyncio
async def test_querer_sacarse_el_open_water_no_es_estar_certificado(ex6):
    ex6({"activity": "padi_open_water"})
    st = await _entender("Hi, I'm interested in taking PADI Open Water Diver certification course.")
    assert st.is_certified is None


@pytest.mark.asyncio
async def test_la_certificacion_y_la_ultima_inmersion_las_pone_el_extractor(ex6):
    ex6({"is_certified": True, "last_dive_over_2_years": True})
    st = await _entender("I'm certified, last dive was 3 years ago")
    assert st.is_certified is True
    assert st.last_dive_over_2_years is True


@pytest.mark.asyncio
async def test_un_cambio_de_certificacion_se_confirma(ex6):
    ex6({"is_certified": False})
    st = ConversationState(conversation_id="ex6", language="es")
    st.is_certified = True
    st = await _entender("vale, perfecto", st)
    assert st.is_certified is True
    assert (st.pending_correction or {}).get("is_certified") is False


@pytest.mark.asyncio
async def test_nivel_nombrado_sin_cita_se_sigue_preguntando(ex6):
    """"somos 4 open water": no dice si lo tienen o lo quieren sacar; el extractor no lo afirma -> se pregunta."""
    ex6({"group_size": 4})
    st = await _entender("hola somos 4 open water", ConversationState(conversation_id="ex6", language="es"))
    assert st.needs_cert_or_course is True
    assert st.is_certified is None


@pytest.mark.asyncio
async def test_nivel_nombrado_con_cita_no_se_pregunta(ex6):
    ex6({"is_certified": True, "group_size": 2})
    st = await _entender("somos 2 open water certificados", ConversationState(conversation_id="ex6", language="es"))
    assert not st.needs_cert_or_course
    assert st.is_certified is True


@pytest.mark.asyncio
async def test_apagado_no_cambia_nada(monkeypatch):
    monkeypatch.setattr(settings, "extraccion_llm_certificacion", False)
    monkeypatch.setattr(settings, "extraccion_llm_actividad", False)
    monkeypatch.setattr(settings, "extraccion_llm_ubicacion", False)
    llamada = AsyncMock(return_value={"is_certified": False})
    monkeypatch.setattr(core, "datos_del_extractor", llamada)
    await _entender("I'm a certified diver")
    llamada.assert_not_called()


@pytest.mark.asyncio
async def test_los_campos_del_extractor_no_van_al_veto(monkeypatch):
    """ex-9 (ronda atencion-B2): con los dominios del extractor encendidos, el veto del camino viejo no se pide para
    sus campos (la llamada iba en serie y su resultado se tiraba)."""
    from src.agents import supervisor

    for flag in ("extraccion_llm_ubicacion", "extraccion_llm_actividad", "extraccion_llm_certificacion",
                 "extraccion_llm_grupo"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(core, "datos_del_extractor", AsyncMock(return_value={}))
    verificar = AsyncMock(return_value={})
    monkeypatch.setattr(supervisor, "verify_fields", verificar)
    monkeypatch.setattr(core, "verify_fields", verificar, raising=False)
    await _entender("Hi, I am looking to book 2 dives and snorkeling for 6 people, all PADI certified")
    for llamada in verificar.await_args_list:
        assert not set(llamada.args[0]) & set(core.campos_del_extractor()), llamada.args[0]
