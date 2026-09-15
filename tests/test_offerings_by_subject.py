"""Reparto de ofertas por persona leido como comparacion (hallazgo E, 2026-09-15).

"tengo un amigo que quiere bucear y yo hago snorkel": el router marcaba
`comparing_options` 3/3 con el LLM real y el nucleo lo aceptaba (2 ofertas, sin cifra ni
"quiero"), asi que iba a RAG a explicar la diferencia en vez de a la reserva. Cada oferta
tiene su propio sujeto, como en un reparto: esa es la senal, no una lista de verbos.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import clause_subject

COMPARING = {"comparing_options": {"comparing": True}}


@pytest.mark.parametrize("message", [
    "tengo un amigo que quiere bucear y yo hago snorkel",
    "mi novia hace el minicurso y yo buceo",
    "yo buceo y mi hijo hace snorkel",
    "my wife wants to snorkel and I'll dive",
    "mis amigos bucean, yo prefiero snorkel",
])
def test_each_offering_with_its_own_subject_is_a_split(message):
    assert core._offerings_with_own_subject(message)
    assert core._is_deliberation_between_options(message, COMPARING) is False


@pytest.mark.parametrize("message", [
    "mi amigo no sabe si bucear o hacer snorkel",       # una sola persona duda
    "mi pareja se lo está pensando, buceo y snorkel",   # las ofertas no llevan sujeto
    "yo y mi novia dudamos, buceo o snorkel",           # la misma frase nombra a los dos
])
def test_one_subject_weighing_offerings_is_still_a_comparison(message):
    assert not core._offerings_with_own_subject(message)
    assert core._is_deliberation_between_options(message, COMPARING) is True


def test_same_offerings_for_both_is_not_a_split():
    assert not core._offerings_with_own_subject("mi amigo quiere snorkel y yo tambien snorkel")


def test_explicit_doubt_wins_over_the_split():
    # La duda escrita se comprueba antes: sigue siendo comparacion.
    assert core._is_deliberation_between_options("mi novia bucea y yo no sé si snorkel o minicurso", {}) is True


@pytest.mark.parametrize("clause, subject", [
    ("tengo un amigo que quiere bucear", "other"),
    ("mis amigos bucean", "other"),
    (" yo hago snorkel", "writer"),
    (" i'll dive", "writer"),
    ("yo buceo con mi novia", None),
    ("buceo y snorkel", None),
])
def test_clause_subject(clause, subject):
    assert clause_subject(clause) == subject
