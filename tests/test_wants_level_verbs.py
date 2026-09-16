"""Querer un nivel PADI con cualquier verbo de querer (hueco 1, 2026-09-16, reverso de F.1).

"quiero ser divemaster", "me interesa el rescue" o "me interesa el open water" nombraban el
nivel sin que la pieza de querer lo reconociera, asi que el nivel quedaba "sin decir si lo
tienen o lo quieren" y el bot preguntaba de mas ("¿ya la tienes o quieres sacarla?"). La
clase de verbos es cerrada, como la de tener: el deseo, el interes y llegar a serlo.
"""

import pytest

from src.agents.intent_detector import (
    certification_claim,
    certification_status,
    course_level_is_ambiguous,
)


@pytest.mark.parametrize("message", [
    "quiero ser divemaster",
    "quiero llegar a ser divemaster",
    "me gustaria ser divemaster",
    "i want to be a divemaster",
    "we want to become divemasters",
    "me interesa el rescue",
    "nos interesa el advanced",
    "estoy interesado en el rescue",
    "im interested in the advanced",
    "i'm interested in the rescue course",
    "quiero la especialidad de nitrox",     # nombra el producto (especialidad), del registro
    "me interesa la especialidad de nitrox",
])
def test_wanting_the_level_is_not_ambiguous(message):
    assert course_level_is_ambiguous(message) is False


@pytest.mark.parametrize("message", [
    "me interesa el open water",
    "nos interesa la certificacion",
    "estoy interesada en sacar la licencia",
])
def test_wanting_the_entry_level_means_not_certified_yet(message):
    assert certification_status(message) is False


@pytest.mark.parametrize("message", [
    "le interesa el open water a mi hijo",
    "my son is interested in the open water",
])
def test_the_interest_of_another_person_says_nothing_about_the_writer(message):
    assert certification_claim(message) is None
    assert certification_status(message) is None
    # Para repartir el grupo si cuenta: ese miembro aun no esta certificado.
    assert certification_claim(message, about_writer=False) is False


@pytest.mark.parametrize("message", [
    "hola somos 4 open water",      # nivel pelado: se sigue preguntando
    "2 advanced and 2 snorkel",
])
def test_a_bare_level_is_still_ambiguous(message):
    assert course_level_is_ambiguous(message) is True


@pytest.mark.parametrize("message", [
    "tengo el open water",
    "ya llevo el rescue, quiero seguir buceando",
])
def test_holding_the_level_is_untouched(message):
    assert certification_status(message) is True
