"""Tener un nivel PADI en tercera persona, con la persona nombrada (2026-09-15).

`_HOLDS_CERT_RE` solo conocia "tengo"/"tenemos": "mi pareja tiene el advanced y quiere
bucear" salia curso Advanced, cuando ya lo tiene. La tercera persona dice que NO se pide
el curso, pero nada del estado de quien escribe: "mi pareja tiene el advanced y yo no
tengo nada" marcaba al cliente como certificado. Quien lo tiene dentro del grupo es
cosa del reparto.
"""

import pytest

from src.agents.intent_detector import IntentDetector, certification_status, holds_padi_cert
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "mi pareja tiene el advanced y quiere bucear",
    "mi novia tiene el open water y quiere bucear conmigo",
    "mis amigos tienen el advanced",
])
def test_third_person_holds_the_level_but_not_the_writer(message):
    assert holds_padi_cert(message, about_writer=False) is True
    assert holds_padi_cert(message) is False
    assert certification_status(message) is None


def test_holding_advanced_is_not_the_advanced_course():
    intent = IntentDetector().detect("mi pareja tiene el advanced y quiere bucear", ConversationState(conversation_id="c"))
    assert intent.activity == "certified_diving"
    assert intent.is_certified is None


@pytest.mark.parametrize("message", [
    "¿tienen el advanced?",
    "tiene el open water?",
    "hola, tienen el advanced disponible mañana?",
])
def test_asking_the_shop_is_not_holding(message):
    """Sin persona nombrada, "tienen el advanced" es preguntar si el centro lo ofrece."""
    assert holds_padi_cert(message, about_writer=False) is False
    assert IntentDetector().detect(message, ConversationState(conversation_id="c")).activity != "certified_diving"


def test_wanting_the_course_still_wins():
    assert holds_padi_cert("mi pareja quiere hacer el advanced", about_writer=False) is False


@pytest.mark.parametrize("message", ["mi amigo tiene licencia, yo no", "mis amigos tienen licencia, yo no"])
def test_someone_elses_licence_is_not_the_writers(message):
    assert certification_status(message) is None


def test_someone_elses_licence_still_splits_the_group():
    intent = IntentDetector().detect("somos 4 y dos no tienen licencia", ConversationState(conversation_id="c"))
    assert intent.group_allocation == {"certified_diving": 2, "undecided": 2}
    assert intent.is_certified is None
    assert intent.activity == "certified_diving"
