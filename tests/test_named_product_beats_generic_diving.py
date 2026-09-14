"""Un producto nombrado gana a la palabra generica de buceo (2026-09-15).

Con el orden anterior de `_detect_activity`, "buce*"/"diving" casaba antes que los
cursos y especialidades: "quiero bucear y hacer la especialidad de flotabilidad"
salia buceo certificado. El LLM de verificacion no lo arreglaba para especialidades
(su enum no las tiene). Ahora curso y especialidad van antes; se conserva la
excepcion de quien YA tiene el nivel ("ya tengo el open water").
"""

import pytest

from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState


def _activity(message):
    return IntentDetector().detect(message, ConversationState(conversation_id="named")).activity


@pytest.mark.parametrize("message,expected", [
    ("quiero bucear y hacer la especialidad de flotabilidad", "specialty_buoyancy"),
    ("I'd like to do the mindful diving specialty", "specialty_mindful_diving"),
    ("somos buzos y queremos la especialidad de nitrox", "specialty_nitrox"),
    ("quiero hacer el curso open water de buceo", "padi_open_water"),
    ("quiero hacer el curso de buceo advanced", "padi_advanced"),
    ("soy buzo certificado y quiero hacer el advanced", "padi_advanced"),
])
def test_named_course_or_specialty_wins(message, expected):
    assert _activity(message) == expected


@pytest.mark.parametrize("message", [
    "ya tengo el open water, quiero seguir buceando",   # tiene el nivel: buceo certificado
    "hola quiero bucear",
])
def test_generic_diving_still_resolves_when_no_product_is_wanted(message):
    assert _activity(message) == "certified_diving"
