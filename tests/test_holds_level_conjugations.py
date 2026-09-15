"""Tener un nivel PADI con cualquier verbo de posesion o de haberlo hecho (hallazgo F.1, 2026-09-15).

"ya llevo el rescue, quiero seguir buceando": el LLM daba `is_certified=True` 3/3, pero la
pieza de tener un nivel solo conocia "tengo/tenemos/tiene(n)", el nivel quedaba sin decir
si lo tienen y `_flag_cert_or_course` borraba el valor para preguntar. Mismo hueco en "hice
mi open water" (conversacion real) o "I did my open water". La clase de verbos es cerrada:
tener y llevar, y haberlo hecho (hacer, sacar, terminar, completar).
"""

import pytest

from src.agents.intent_detector import (
    IntentDetector,
    certification_status,
    course_level_is_ambiguous,
    holds_padi_cert,
)
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "ya llevo el rescue, quiero seguir buceando",
    "llevamos el advanced",
    "hola soy Sofia de chile, hice mi open water y quiero bucear",
    "hicimos el open water en mexico",
    "saqué el advanced el año pasado",
    "terminé el rescue en 2019",
    "I did my open water last year",
    "I completed the advanced",
    "we finished our rescue course",
    "we have done the open water",
])
def test_writer_holds_the_level(message):
    assert holds_padi_cert(message) is True
    assert not course_level_is_ambiguous(message)
    assert certification_status(message) is True


def test_holding_the_level_is_certified_diving_not_the_course():
    intent = IntentDetector().detect("ya llevo el rescue, quiero seguir buceando", ConversationState(conversation_id="f1"))
    assert intent.activity == "certified_diving"
    assert intent.is_certified is True


@pytest.mark.parametrize("message", [
    "mi novia hizo el open water",
    "mi novia lleva el advanced",
    "my wife completed the advanced",
])
def test_other_person_holds_the_level_but_not_the_writer(message):
    assert holds_padi_cert(message, about_writer=False) is True
    assert holds_padi_cert(message) is False
    assert certification_status(message) is None


@pytest.mark.parametrize("message", [
    "hice el open water y quiero hacer el advanced",   # querer sacar otro gana
    "quiero hacer el open water",
    "I'd like to take the advanced course",
    "ya hice la teoria y la piscina en mi centro PADI y traigo la carta de referido para terminar el open water",
])
def test_wanting_a_level_is_not_holding_it(message):
    assert holds_padi_cert(message) is False


@pytest.mark.parametrize("message", [
    "hola somos 4 open water",     # nivel sin verbo: se sigue preguntando
    "2 advanced and 2 snorkel",
    "¿tienen el advanced?",        # preguntar al centro no es tenerlo
])
def test_bare_level_or_question_is_not_holding(message):
    assert holds_padi_cert(message) is False
