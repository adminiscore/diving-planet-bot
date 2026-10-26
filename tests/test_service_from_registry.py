"""F4 (paso 1) del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

El servicio de una actividad sale SIEMPRE del registro, en el unico punto que la
guarda (`supervisor._apply_detected_intent`). Antes cada detector ponia el suyo:

- el relleno LLM no ponia ninguno: un Open Water decidido por el LLM llegaba al
  carrito como curso sin precio ni link;
- el regex escribia nombres a mano que no existian en el catalogo ("nitrox" en vez
  de "nitrox_specialty"), con el mismo resultado.
lat-11 T6d (26-oct): fuera los tests de IntentDetector.detect (la clase se quitó; la actividad la decide el extractor).
"""


import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _camino_viejo_de_actividad(monkeypatch):
    """Estos tests prueban el camino viejo (regex + veto/relleno). Con ex-8 (`extraccion_llm_actividad`) la actividad y
    la nacionalidad las decide el extractor "LLM primero": tests/test_ex8_actividad_nacionalidad.py."""


def test_apply_derives_the_service_even_if_the_detector_gave_none():
    """El caso del relleno LLM: actividad sin service_id."""
    state = ConversationState(conversation_id="svc-apply")
    supervisor._apply_detected_intent(DetectedIntent(activity="padi_open_water"), state, "x")
    assert state.detected_service_id == "open_water"


def test_apply_ignores_a_wrong_service_from_a_detector():
    state = ConversationState(conversation_id="svc-apply-wrong")
    intent = DetectedIntent(activity="specialty_nitrox", service_id="nitrox")
    supervisor._apply_detected_intent(intent, state, "x")
    assert state.detected_service_id == "nitrox_specialty"


def test_generic_activity_has_no_service_until_the_level_is_decided():
    state = ConversationState(conversation_id="svc-generic")
    supervisor._apply_detected_intent(DetectedIntent(activity="padi_course"), state, "x")
    assert state.detected_service_id is None


