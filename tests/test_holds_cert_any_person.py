"""Tener un nivel PADI en cualquier persona del verbo (2026-09-15).

`_HOLDS_CERT_RE` solo conocia "tengo"/"tenemos": "mi pareja tiene el advanced y quiere
bucear" salia curso Advanced, cuando ya lo tiene. Mismo hueco de conjugacion que "tener
licencia". Quien tiene el nivel no cambia: eso es reparto del grupo, no de esta lista.
"""

import pytest

from src.agents.intent_detector import IntentDetector, holds_padi_cert
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "mi pareja tiene el advanced y quiere bucear",
    "mi novia tiene el open water y quiere bucear conmigo",
    "mis amigos tienen el advanced",
])
def test_third_person_holds_the_level(message):
    assert holds_padi_cert(message) is True


def test_holding_advanced_is_not_the_advanced_course():
    intent = IntentDetector().detect("mi pareja tiene el advanced y quiere bucear", ConversationState(conversation_id="c"))
    assert intent.activity == "certified_diving"


@pytest.mark.parametrize("message", [
    "¿tienen el advanced?",
    "tiene el open water?",
    "hola, tienen el advanced disponible mañana?",
])
def test_asking_the_shop_is_not_holding(message):
    """Sin persona nombrada, "tienen el advanced" es preguntar si el centro lo ofrece."""
    assert holds_padi_cert(message) is False
    assert IntentDetector().detect(message, ConversationState(conversation_id="c")).activity != "certified_diving"


def test_wanting_the_course_still_wins():
    assert holds_padi_cert("mi pareja quiere hacer el advanced") is False
