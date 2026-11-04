"""CALN-9 (4-nov): lo que el extractor lee como lugar y Jev no respalda no se guarda ni fija el precio: se confirma una vez."""
import asyncio

import pytest

from src.agents import conversational_core as core
from src.agents import redactor_hechos
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo.extractor import guardar_lo_dicho_sin_nucleo
from src.flows.state import ConversationState

HIPOTESIS = "¿Y si nos quedamos a dormir una noche más en las islas, nos traen de vuelta?"


def _st(confianza, eleccion="islands", **campos):
    st = ConversationState(conversation_id="caln9", language="es")
    st._jev_lugar = {"choice": eleccion, "confidence": confianza}
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("confianza", [0.16, 0.48])
def test_la_hipotesis_no_se_guarda_y_se_confirma_una_vez(confianza):
    st, intent = _st(confianza), DetectedIntent()
    core._poner_ubicacion(intent, st, HIPOTESIS, {"location": "island"}, {})
    assert intent.location is None and st.pending_correction == {"location": "island"}


def test_la_hipotesis_no_fija_el_precio():
    assert redactor_hechos._origen(_st(0.3), {"location": "island"}) is None


def test_quien_lo_afirma_se_guarda_y_fija_el_precio():
    st, intent = _st(0.98), DetectedIntent()
    core._poner_ubicacion(intent, st, "Estamos alojados en Isla Grande", {"location": "island"}, {})
    assert intent.location == "island" and not st.pending_correction
    assert redactor_hechos._origen(_st(0.98), {"location": "island"}) == "island"


def test_sin_jev_vale_el_extractor():
    st, intent = ConversationState(conversation_id="caln9", language="es"), DetectedIntent()
    core._poner_ubicacion(intent, st, "Estamos en las islas", {"location": "island"}, {})
    assert intent.location == "island"


def test_tras_preguntar_el_origen_la_hipotesis_tampoco_se_guarda():
    """h-stay-longer: el bot acaba de preguntar el origen y el cliente contesta con otra pregunta."""
    st, intent = _st(0.35, core_pending_slot=core.SLOT_LOCATION), DetectedIntent()
    core._poner_ubicacion(intent, st, "What if I decide to stay one day longer in rosario?", {"location": "island"}, {})
    assert intent.location is None
    st, intent = _st(1.0, "cartagena", core_pending_slot=core.SLOT_LOCATION), DetectedIntent()
    core._poner_ubicacion(intent, st, "Desde Cartagena", {"location": "cartagena"}, {})
    assert intent.location == "cartagena"


@pytest.mark.asyncio
async def test_sin_el_nucleo_tampoco_se_guarda_lo_que_jev_no_respalda():
    async def lectura():
        return {"location": "island"}

    st = _st(0.3)
    st._extraccion_adelantada = asyncio.create_task(lectura())
    await guardar_lo_dicho_sin_nucleo(st)
    assert st.location is None
    st = _st(0.99)
    st._extraccion_adelantada = asyncio.create_task(lectura())
    await guardar_lo_dicho_sin_nucleo(st)
    assert st.location == "island"


def test_un_hotel_de_las_islas_da_el_origen_aunque_jev_dude():
    """ARQ-8b: «the Ubuntu hotel» con Jev a 0,52."""
    st, intent = _st(0.52), DetectedIntent()
    core._poner_ubicacion(intent, st, "We'll be staying at the Ubuntu hotel", {"location": "island", "hotel": "Ubuntu hotel"}, {})
    assert intent.location == "island"


def test_con_un_origen_ya_guardado_no_se_confirma_por_la_duda():
    st, intent = _st(0.3, location="cartagena", detected_location="cartagena"), DetectedIntent()
    core._poner_ubicacion(intent, st, HIPOTESIS, {"location": "cartagena"}, {})
    assert not st.pending_correction
