"""La duracion se compone: cantidad x unidad (hueco 2, 2026-09-16).

Antes eran dos listas de fraseos ("un dia", "varios dias", "\\d+ days"), asi que
"estaremos toda la semana en las islas" o "just here for the day" no se leian y el bot
volvia a preguntar cuanto se quedan. Ahora la cantidad multiplica los dias de la unidad y
el total decide. Las noches quedan fuera a proposito, y el tiempo transcurrido ("hace 3
dias que llegamos") no es estancia.
"""

import pytest

from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState


def _duration(message: str) -> str | None:
    return IntentDetector().detect(message, ConversationState(conversation_id="dur")).duration


@pytest.mark.parametrize("message", [
    "estaremos toda la semana en las islas",
    "nos quedamos una semana",
    "estamos tres dias en cartagena",
    "un par de dias",
    "a couple of days",
    "a few days",
    "we're staying for a week",
    "we'll be here the whole weekend",
    "estamos un mes",
    "estamos 5 dias en la isla",          # ya funcionaba: los digitos
    "varios dias",
    "quiero el paquete de 3 dias",        # el producto es multi-dia por definicion
])
def test_more_than_one_day_is_multi_day(message):
    assert _duration(message) == "multi_day"


@pytest.mark.parametrize("message", [
    "just here for the day",
    "solo por el dia",
    "estamos todo el dia",
    "un dia",
    "un solo dia",
    "one day",
    "solo hoy",
    "just today",
])
def test_one_day_is_single_day(message):
    assert _duration(message) == "single_day"


@pytest.mark.parametrize("message", [
    # Tiempo transcurrido, no estancia.
    "hace 3 dias que llegamos",
    "3 days ago",
    # Decir CUANDO no es decir CUANTO: no se supone lo que el cliente no dijo.
    "venimos el fin de semana",
    "la semana que viene",
    "todos los dias buceamos",
    # Una noche no dice cuantos dias se bucea.
    "nos quedamos 2 noches",
    # Ni una fecha ni una pregunta son una duracion.
    "que dia salen las lanchas?",
    "el dia 5 de octubre",
    "cuantos dias dura el curso?",
    "hola, quiero bucear",
])
def test_no_stay_stated(message):
    assert _duration(message) is None


def test_the_longest_stay_wins():
    assert _duration("un dia de buceo y 3 dias en las islas") == "multi_day"
