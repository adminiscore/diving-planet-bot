"""La pregunta de informacion se reconoce por su estructura, no por abrir el mensaje
(tarea 7d, 2026-09-15).

"primero dime qué incluye el tour" recibia un acuse generico: la deteccion iba anclada
al inicio del mensaje. Ahora cuentan el imperativo de pedir informacion en cualquier
posicion y la palabra interrogativa al inicio de una clausula, con clases gramaticales
cerradas (sin frases nuevas).
"""

import pytest

from src.agents.supervisor import _looks_like_info_question


@pytest.mark.parametrize("message", [
    "primero dime qué incluye el tour",
    "antes de nada, dime qué horario tienen",
    "bueno, cuéntame del minicurso",
    "hola, quiero saber el precio del snorkel",
    "vale, cuánto cuesta el minicurso",
    "perfecto, y cómo pago",
    "ok y dónde nos recogen",
    "genial y qué llevamos",
    "great, what's included",
    "ok and how many dives are there",
    # Lo que ya se reconocia sigue igual.
    "que incluye el tour",
    "cuánto cuesta",
    "what does it include",
])
def test_questions_anywhere_in_the_message(message):
    assert _looks_like_info_question(message)


@pytest.mark.parametrize("message", [
    "genial, lo que tú digas",
    "me encanta lo que hacen",
    "creo que somos 3",
    "es que mi novia no bucea",
    "somos 3, hay un niño de 7",
    "somos 3, como te dije",
    "quiero bucear y que mi hijo haga snorkel",
    "vale, cuando lleguemos te escribo",
    "we will book and when we arrive we pay",
    "somos 2 y queremos snorkel",
    "gracias!",
])
def test_statements_are_not_questions(message):
    assert not _looks_like_info_question(message)
