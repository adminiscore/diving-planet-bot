"""F4 (paso 1) del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

El servicio de una actividad sale SIEMPRE del registro, en el unico punto que la
guarda (`supervisor._apply_detected_intent`). Antes cada detector ponia el suyo:

- el relleno LLM no ponia ninguno: un Open Water decidido por el LLM llegaba al
  carrito como curso sin precio ni link;
- el regex escribia nombres a mano que no existian en el catalogo ("nitrox" en vez
  de "nitrox_specialty"), con el mismo resultado.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent, IntentDetector
from src.domain import activities as dom
from src.flows.catalog import SERVICES
from src.flows.state import ConversationState


def _detect(message):
    return IntentDetector().detect(message, ConversationState(conversation_id="svc"))


@pytest.mark.parametrize("message", [
    "quiero bucear", "quiero hacer snorkel", "quiero el minicurso", "quiero el open water",
    "quiero hacer el advanced", "me interesa el rescue", "quiero ser divemaster",
    "quiero la especialidad de nitrox", "me interesa la especialidad de flotabilidad",
    "quiero la especialidad naturalista",
])
def test_every_service_the_detector_emits_exists_in_the_catalog(message):
    intent = _detect(message)
    assert intent.activity in dom.activity_ids()
    if intent.service_id is not None:
        assert intent.service_id in SERVICES, f"{message!r} -> {intent.service_id}"
    assert intent.service_id == dom.base_service_id(intent.activity)


@pytest.mark.parametrize(("message", "activity_id"), [
    ("quiero la especialidad de nitrox", "specialty_nitrox"),
    ("me interesa la especialidad de flotabilidad", "specialty_buoyancy"),
    ("quiero la especialidad naturalista", "specialty_naturalist"),
])
def test_named_specialty_becomes_its_registry_activity(message, activity_id):
    intent = _detect(message)
    assert intent.activity == activity_id
    assert intent.service_id in SERVICES


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


def test_llm_filled_activity_reaches_the_state_with_its_service():
    """Reproduce el fallo por el camino real del turno (LLM simulado)."""
    message = "quisiera sacarme la licencia de buzo"
    assert _detect(message).activity is None  # el regex no lo resuelve
    state = ConversationState(conversation_id="svc-llm")
    state.language = "es"
    patch_llm = {"activity": "padi_open_water"}

    async def run():
        with patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(dict(patch_llm), {}))), \
             patch.object(core, "fill_gaps", new=AsyncMock(return_value=dict(patch_llm))), \
             patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={})):
            await core._understand(state, message)

    asyncio.run(run())
    assert state.detected_activity == "padi_open_water"
    assert state.detected_service_id == "open_water"
