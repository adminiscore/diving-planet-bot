"""«Nunca se ha sumergido», con una sola fuente para sus dos usos (hueco 3, 2026-09-16).

La regla estaba escrita dos veces y divergia: la lista del minicurso admitia en espanol
hasta tres palabras por medio y en ingles cuatro frases cerradas, de las que la lista de
certificacion solo tenia una ("never dived"). Por eso "never been underwater before, wanna
give it a try, solo" no salia como no certificado. Ahora es la misma regla en los dos
idiomas: nunca + auxiliares + el tema de sumergirse.
"""

import pytest

from src.agents.intent_detector import IntentDetector, certification_status
from src.flows.state import ConversationState


def _intent(message: str):
    return IntentDetector().detect(message, ConversationState(conversation_id="nd"))


@pytest.mark.parametrize("message", [
    "never been underwater before, wanna give it a try, solo",
    "never been diving",
    "i have never been underwater",
    "we have never dived",
    "never tried, wanna give it a go",
    "never done it before",
    "nunca he buceado",
    "nunca hemos hecho buceo",
    "nunca he practicado buceo",
    "nunca he estado bajo el agua",
    "nunca nos hemos sumergido",
])
def test_never_underwater_means_not_certified(message):
    assert certification_status(message) is False


@pytest.mark.parametrize("message", [
    "never been underwater before, wanna give it a try, solo",
    "nunca he estado bajo el agua",
])
def test_never_underwater_is_the_minicourse(message):
    assert _intent(message).activity == "minicourse"


@pytest.mark.parametrize("message", [
    # "never" niega otro verbo, no la experiencia de bucear.
    "i will never stop diving",
    # El objeto nombrado es otro producto, no sumergirse.
    "never tried nitrox but i am advanced",
])
def test_never_about_something_else_is_not_a_claim(message):
    assert certification_status(message) is not False


def test_the_two_lists_share_one_source():
    from src.agents.intent_detector import (
        _MINICOURSE_PATTERNS,
        _NEVER_DIVED,
        _NOT_CERTIFIED_PATTERNS,
    )
    assert _NEVER_DIVED in _MINICOURSE_PATTERNS
    assert _NEVER_DIVED in _NOT_CERTIFIED_PATTERNS
