"""LAT-9 paso 2 (26-oct): la pregunta de la reserva la escribe el escritor, y el acuse solo si contestó lo preguntado."""
import asyncio

from src.agents.conversational_core import SLOT_LOCATION, SLOT_QTY, _sin_la_pregunta_final
from src.agents.nucleo import slotfill_close as close
from src.flows.state import ConversationState


def _estado(**kw) -> ConversationState:
    st = ConversationState(conversation_id="lat9p2")
    st.detected_activity = "certified_diving"
    st.is_certified = True
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def test_sin_acuse_delante_de_la_misma_pregunta():
    st = _estado(core_pending_slot=SLOT_LOCATION)  # se vuelve a preguntar el origen: no contestó
    assert close._acuse_por_codigo(st, SLOT_LOCATION) == ""


def test_acuse_cuando_contesto_lo_preguntado():
    st = _estado(location="cartagena", core_pending_slot=SLOT_QTY)  # contestó el origen; ahora toca cuántos son
    assert close._acuse_por_codigo(st, SLOT_LOCATION).startswith("¡Perfecto!")


def test_sin_pendiente_no_hay_acuse():
    assert close._acuse_por_codigo(_estado(), None) == ""


def test_sin_la_pregunta_final_solo_quita_el_ultimo_parrafo_si_pregunta():
    assert _sin_la_pregunta_final("Cuesta 124 USD.\n\n¿Desde dónde saldrías?") == "Cuesta 124 USD."
    assert _sin_la_pregunta_final("Cuesta 124 USD.\n\nIncluye el equipo.") == "Cuesta 124 USD.\n\nIncluye el equipo."
    assert _sin_la_pregunta_final("¿Desde dónde saldrías?") == "¿Desde dónde saldrías?"  # sin otro texto, se queda


def _con(answer, response, escrita, finalized=False, cierre_igual=False):
    return asyncio.run(close._con_la_pregunta(_estado(), "msg", answer, response, escrita, finalized, cierre_igual))


def test_misma_pregunta_va_el_texto_del_escritor():
    assert _con("Sí, incluye el equipo.\n\n¿Cuántos serían?", "¿Cuántas personas son?", "¿Cuántas personas son?") \
        == "Sí, incluye el equipo.\n\n¿Cuántos serían?"


def test_otra_pregunta_el_codigo_la_cambia():
    assert _con("Sí, incluye el equipo.\n\n¿Cuántos serían?", "¿Eres buzo certificado?", "¿Cuántas personas son?") \
        == "Sí, incluye el equipo.\n\n¿Eres buzo certificado?"


def test_cierre_igual_va_sin_pregunta_ni_tarjeta():
    assert _con("Dura 4 horas.\n\n¿Cuántos serían?", "TARJETA", "¿Cuántos serían?", finalized=True,
                cierre_igual=True) == "Dura 4 horas."
