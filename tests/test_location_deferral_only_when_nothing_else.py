"""La duda con la ubicacion pendiente solo delega si el mensaje no dice nada mas
(2026-09-15).

"no sé si hacer el minicurso o el snorkel" contiene "no sé": con la ubicacion
pendiente, `_apply_short_answer` fijaba Cartagena sin que nadie la eligiera y el
turno se saltaba la comparacion de opciones. Un "no sé" o "da igual" a secas sigue
delegando en Cartagena, como antes.
"""

import pytest

from src.agents import conversational_core as cc
from src.flows.state import ConversationState


def _answer(message):
    state = ConversationState(conversation_id="c")
    state.core_pending_slot = cc.SLOT_LOCATION
    resolved = cc._apply_short_answer(state, message)
    return resolved, state.location


@pytest.mark.parametrize("message", [
    "no sé si hacer el minicurso o el snorkel",
    "Me interesa el curso PADI, no se bucear",
    "no sé si hacer el open water o el advanced",
])
def test_doubt_about_something_else_does_not_pick_cartagena(message):
    assert _answer(message) == (False, None)


@pytest.mark.parametrize("message", ["no sé", "da igual", "tú decides", "lo que recomiendes", "up to you"])
def test_plain_deferral_still_recommends_cartagena(message):
    assert _answer(message) == (True, "cartagena")


@pytest.mark.parametrize("message, location", [("cartagena", "cartagena"), ("ya estamos en la isla", "island"), ("1", "cartagena"), ("2", "island")])
def test_real_answers_unchanged(message, location):
    assert _answer(message) == (True, location)


@pytest.mark.parametrize("message", [
    "que solo nos acompañe en la lancha, no se mete al agua",   # "se" reflexivo, no "sé"
    "no se todavía donde nos vamos a quedar",
])
def test_doubt_inside_a_longer_answer_is_not_a_deferral(message):
    """La duda solo delega si es la respuesta entera (2026-09-15): quitadas sus frases
    quedan como mucho 4 palabras. Sin tildes, "no se mete" y "no sé" se escriben igual;
    lo que las separa es que la primera trae contenido propio."""
    assert _answer(message) == (False, None)


@pytest.mark.parametrize("message", ["lo que tú me recomiendes", "no sé la verdad, tú decides"])
def test_short_deferrals_with_filler_still_recommend_cartagena(message):
    assert _answer(message) == (True, "cartagena")
