"""Alcance de la negacion en `certification_claim` y "N inmersiones" como buceo
certificado (2026-09-15).

"2 no tienen certificación" y "two aren't certified" casaban el patron positivo y
salian True. No se anade cada frase negativa: una afirmacion precedida de cerca por
una negacion no cuenta, y la doble negacion se cancela.
"""

import pytest

from src.agents.intent_detector import IntentDetector, certification_claim
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "2 no tienen certificación",
    "two aren't certified",
    "no tenemos certificación",
    "we aren't certified divers",
    "no tengo licencia de buceo",
])
def test_negated_claim_is_not_certified(message):
    assert certification_claim(message) is False


@pytest.mark.parametrize("message", [
    "tengo certificación padi",
    "somos 2 buzos certificados",
    "no, ya soy certificado",
    "no es que no estemos certificados, si lo estamos, los 2",
])
def test_affirmative_claim_survives(message):
    assert certification_claim(message) is True


@pytest.mark.parametrize("message, dives", [
    ("quiero hacer 2 inmersiones", 2),
    ("want to do 3 dives", 3),
])
def test_dive_count_means_certified_diving(message, dives):
    intent = IntentDetector().detect(message, ConversationState(conversation_id="c"))
    assert intent.cert_dives == dives
    assert intent.activity == "certified_diving"
