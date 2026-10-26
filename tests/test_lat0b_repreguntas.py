"""LAT-0b (26-oct; Gadea #2029): repreguntas de integra5-B. Banco docs/robustness/lat/banco-lat0b.json.

1. «Quiero bucear certificado» → «¿Eres buzo certificado?» sonaba a no haberle escuchado. mod-2 se queda (elegir el
   buceo certificado no dice que lo esté); la pregunta dice que es para confirmar y se hace una vez (Gadea #2040).
2. «El plan de 5 buceos» con el extractor diciendo padi_course (curso sin nivel) era el bucle de «¿qué curso?»: un
   paquete de buceos sin ningún curso ni especialidad nombrados es buceo certificado.
3. «Soy residente» a secas cuenta para el precio de residentes (regla del extractor; ver ex0 en el commit).
"""

import pytest

from src.agents import conversational_core as core
from src.agents import extractor_turno as ex
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="lat0b", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("mensaje", [
    "¿Hay cupo en el plan de 5 buceos para el puente de noviembre?",
    "Do you have availability for the four dive package next month?",
])
def test_un_paquete_de_buceos_no_es_un_curso_sin_nivel(mensaje):
    it = DetectedIntent()
    core_extractor._poner_actividad(it, _estado(), {"activity": "padi_course"}, mensaje)
    assert it.activity == "certified_diving"


@pytest.mark.parametrize("mensaje", [
    "quiero un curso, ¿el de 4 inmersiones?",
    "la especialidad de 3 buceos",
    "el curso avanzado tiene 5 inmersiones?",
])
def test_con_un_curso_nombrado_sigue_siendo_curso(mensaje):
    it = DetectedIntent()
    core_extractor._poner_actividad(it, _estado(), {"activity": "padi_course"}, mensaje)
    assert it.activity == "padi_course"


@pytest.mark.parametrize("sistema", [ex.SISTEMA_ES, ex.SISTEMA_EN])
def test_residente_a_secas_esta_en_la_regla(sistema):
    regla = next(ln for ln in sistema.splitlines() if ln.startswith("- is_colombian:"))
    assert "residente" in regla.lower() or "resident" in regla.lower()
    assert '"soy residente"' in regla or "\"I'm a resident\"" in regla


def test_la_certificacion_se_confirma_una_vez_por_idioma():
    st = _estado(detected_activity="certified_diving", location="cartagena", history=[])
    assert core.next_missing_slot(st) == core.SLOT_CERTIFICATION
    pregunta = core.ask_slot(st, core.SLOT_CERTIFICATION)
    assert "me confirmas" in pregunta and "Eres buzo" not in pregunta
    assert core.next_missing_slot(st) == core.SLOT_CERTIFICATION  # preparada no cuenta: puede salir otra (el origen)
    st.history.append({"role": "assistant", "content": "¡Hola! 🪸\n\n" + pregunta})
    assert core.next_missing_slot(st) != core.SLOT_CERTIFICATION
    st.language = "en"  # pide otro idioma: no la entendió
    assert core.next_missing_slot(st) == core.SLOT_CERTIFICATION
    assert "can you confirm" in core.ask_slot(st, core.SLOT_CERTIFICATION)


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("actividad", ["certified_diving", None])
@pytest.mark.parametrize("personas", [1, 3])
def test_cada_forma_de_la_pregunta_se_reconoce(lang, actividad, personas):
    st = _estado(language=lang, detected_activity=actividad, detected_group_size=personas, quiere_bucear=True,
                 history=[])
    st.history.append({"role": "assistant", "content": core.ask_slot(st, core.SLOT_CERTIFICATION)})
    assert core._certificacion_ya_preguntada(st)


def test_sin_el_buceo_certificado_elegido_sigue_la_recomendacion():
    st = _estado(quiere_bucear=True)
    assert "me confirmas" not in core.ask_slot(st, core.SLOT_CERTIFICATION)
