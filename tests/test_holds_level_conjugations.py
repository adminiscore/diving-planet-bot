"""Tener un nivel PADI con cualquier verbo de posesion o de haberlo hecho (hallazgo F.1, 2026-09-15).

"ya llevo el rescue, quiero seguir buceando": el LLM daba `is_certified=True` 3/3, pero la
pieza de tener un nivel solo conocia "tengo/tenemos/tiene(n)", el nivel quedaba sin decir
si lo tienen y `_flag_cert_or_course` borraba el valor para preguntar. Mismo hueco en "hice
mi open water" (conversacion real) o "I did my open water". La clase de verbos es cerrada:
tener y llevar, y haberlo hecho (hacer, sacar, terminar, completar).
lat-11 T6d (26-oct): fuera los tests de IntentDetector.detect, `holds_padi_cert` y `certification_status` (se quitaron;
la certificacion la decide el extractor); el verbo de tener un nivel se sigue probando en `_HOLDS_CERT_RE`.
"""

import pytest

from src.agents.intent_detector import _HOLDS_CERT_RE, _WANTS_CERT_RE, course_level_is_ambiguous


def _holds_a_level(message):
    """Lo que leia `holds_padi_cert(message, about_writer=False)` (se quito con IntentDetector en lat-11 T6d): alguien
    TIENE un nivel PADI, sin querer sacarlo. Sigue vivo en `course_level_is_ambiguous`."""
    return bool(_HOLDS_CERT_RE.search(message)) and not _WANTS_CERT_RE.search(message)


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
    assert _holds_a_level(message)
    assert not course_level_is_ambiguous(message)


@pytest.mark.parametrize("message", [
    "mi novia hizo el open water",
    "mi novia lleva el advanced",
    "my wife completed the advanced",
])
def test_other_person_holds_the_level(message):
    assert _holds_a_level(message)


@pytest.mark.parametrize("message", [
    "hice el open water y quiero hacer el advanced",   # querer sacar otro gana
    "quiero hacer el open water",
    "I'd like to take the advanced course",
    "ya hice la teoria y la piscina en mi centro PADI y traigo la carta de referido para terminar el open water",
])
def test_wanting_a_level_is_not_holding_it(message):
    assert not _holds_a_level(message)


@pytest.mark.parametrize("message", [
    "hola somos 4 open water",     # nivel sin verbo: se sigue preguntando
    "2 advanced and 2 snorkel",
    "¿tienen el advanced?",        # preguntar al centro no es tenerlo
])
def test_bare_level_or_question_is_not_holding(message):
    assert not _holds_a_level(message)
