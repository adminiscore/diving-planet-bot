"""ex-5 (fase EX, flag `extraccion_llm_ubicacion`): la ubicación del turno la decide el extractor "LLM primero".

Banco ex0 (escalón 0, grupo de diseño, turno de producción): la ubicación inventada pasa de 13 casos a 0, con los
mismos aciertos (19/20). Aquí, con el extractor simulado: el regex ya no decide, el extractor sí (y conserva el hotel
para la recogida), un origen nuevo dicho por el cliente sobrescribe, y si la llamada falla se queda lo de hoy.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows.state import ConversationState


@pytest.fixture
def ex5(monkeypatch):
    monkeypatch.setattr(settings, "extraccion_llm_ubicacion", True)

    def con(datos):
        monkeypatch.setattr(core, "datos_del_extractor", AsyncMock(return_value=datos))

    return con


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or ConversationState(conversation_id="ex5", language="es")
    await core._understand(state, mensaje)
    return state


@pytest.mark.asyncio
async def test_el_regex_ya_no_decide_la_ubicacion(ex5):
    # "el contacto del hotel Cocoliso": el regex lo leía como "ya está en las islas".
    ex5({})
    st = await _entender("Me pasas el contacto del hotel cocoliso?")
    assert st.location is None and st.detected_location is None
    assert st.hotel is None


@pytest.mark.asyncio
async def test_la_ubicacion_la_pone_el_extractor_y_conserva_el_hotel(ex5):
    ex5({"location": "island"})
    st = await _entender("estamos alojados en el Cocoliso")
    assert st.location == "island"
    assert st.hotel or st.detected_hotel  # la pista del regex (lista cerrada) queda para la recogida


@pytest.mark.asyncio
async def test_un_origen_nuevo_con_correccion_explicita_se_cambia(ex5):
    ex5({"location": "island"})
    st = ConversationState(conversation_id="ex5", language="es")
    st.location = st.detected_location = "cartagena"
    st = await _entender("espera, en realidad ya estaremos alojados en las islas", st)
    assert st.location == "island"


@pytest.mark.asyncio
async def test_un_origen_nuevo_sin_correccion_se_confirma(ex5):
    # Ronda ex5-B: "Ok, están en Isla Grande" (habla de la base) cambiaba Cartagena por las islas en silencio.
    ex5({"location": "island"})
    st = ConversationState(conversation_id="ex5", language="es")
    st.location = st.detected_location = "cartagena"
    st = await _entender("Ok, estan en isla grande", st)
    assert st.location == "cartagena"
    assert (st.pending_correction or {}).get("location") == "island"


@pytest.mark.asyncio
async def test_si_el_extractor_falla_se_queda_lo_de_hoy(ex5):
    ex5(None)
    st = await _entender("desde cartagena")
    assert st.location == "cartagena"


@pytest.mark.asyncio
async def test_apagado_no_cambia_nada(monkeypatch):
    monkeypatch.setattr(settings, "extraccion_llm_ubicacion", False)
    monkeypatch.setattr(settings, "extraccion_llm_actividad", False)
    llamada = AsyncMock(return_value={"location": "island"})
    monkeypatch.setattr(core, "datos_del_extractor", llamada)
    st = await _entender("desde cartagena")
    assert st.location == "cartagena"
    llamada.assert_not_called()
    assert core.campos_del_extractor() == ()


@pytest.mark.asyncio
async def test_en_las_islas_el_hotel_se_conserva_aunque_no_repita_la_ubicacion(ex5):
    # Ronda ex5-B2: "una noche en Coral Sand y la otra en Majagua" se perdía y el bot volvía a preguntar el hotel.
    ex5({})
    st = ConversationState(conversation_id="ex5", language="es")
    st.location = st.detected_location = "island"
    st = await _entender("una noche en el cocoliso", st)
    assert st.hotel or st.detected_hotel
