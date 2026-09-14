"""Trigger PROPIO del veto de `is_certified` (tarea 9, 2026-09-14).

Misma regla comun que la nacionalidad (`polarity_is_ambiguous`, con los patrones del
propio detector): el LLM solo se consulta si el mensaje trae polaridad de
certificacion contradictoria. Con el trigger generico se consultaba en todo turno
donde el regex resolvia la certificacion (ver test_field_veto_generic_trigger_risk).

Medido con LLM real (3 repeticiones): en los 6 mensajes ambiguos el regex acierta y
el veto coincide con el 6/6. Por eso, a diferencia de la nacionalidad, el detector no
se abstiene, y encender el flag no ganaria nada hoy.
"""

import pytest

from src.agents import supervisor
from src.agents.intent_detector import (
    IntentDetector,
    certification_is_ambiguous,
    nationality_is_ambiguous,
)
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "somos 3, 2 con open water y 1 no",
    "no es que no estemos certificados, si lo estamos, los 2",
    "Quiero el open water aunque no soy buzo certificado",
    "soy certificado, mi hijo no",
])
def test_contradictory_certification_is_ambiguous(message):
    assert certification_is_ambiguous(message) is True


@pytest.mark.parametrize("message", [
    "soy buzo certificado",
    "no estoy certificado",
    "mi amigo no está certificado",
    "quiero bucear, somos 2",
])
def test_clear_certification_is_not_ambiguous(message):
    assert certification_is_ambiguous(message) is False


def test_certification_spec_has_its_own_trigger():
    assert supervisor._VETO_FIELD_SPECS["is_certified"].should_verify is not None


def test_trigger_skips_clear_certification():
    intent = IntentDetector().detect("soy buzo certificado", ConversationState(conversation_id="c"))
    assert intent.is_certified is True
    assert supervisor._certification_should_verify("soy buzo certificado", intent) is False


def test_detector_does_not_abstain_on_ambiguous_certification():
    """El regex acierta en los ambiguos de certificacion (medido): no se abstiene."""
    message = "no es que no estemos certificados, si lo estamos, los 2"
    intent = IntentDetector().detect(message, ConversationState(conversation_id="c"))
    assert intent.is_certified is True


def test_nationality_uses_the_same_common_rule():
    assert nationality_is_ambiguous("somos extranjeros pero vivimos en colombia") is True
    assert nationality_is_ambiguous("soy colombiano") is False
