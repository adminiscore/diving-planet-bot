"""Contraste eliptico de certificacion (hallazgo I, 2026-09-15).

"mi amigo tiene licencia, yo no" o "soy certificado y mi hijo no" no repiten el
predicado: la regla por persona del detector necesitaba las dos certificaciones y el
reparto dependia de que el LLM contestara, que a veces devolvia `{}` entero (p02 1/2,
p05 1/2, p07 0/2 con el LLM real). La frase eliptica se lee por su propia polaridad.
"""

import pytest

from src.agents.intent_detector import IntentDetector, elided_certification
from src.flows.state import ConversationState


def _detect(message):
    return IntentDetector().detect(message, ConversationState(conversation_id="elided"))


@pytest.mark.parametrize("message", [
    "mi amigo tiene licencia, yo no",                     # p01
    "soy certificado y mi hijo no",                       # p02
    "somos 2, mi amigo es buzo y yo no",                  # p03
    "my wife is certified and I am not",                  # p05
    "mi pareja tiene el advanced y yo no tengo nada",     # p07
    "mi novia es buza certificada y yo nunca he buceado", # p06, ya funcionaba
    "yo tengo licencia y mi esposa no",
    "I'm certified and my son isn't",
    "yo no, pero mi pareja si tiene licencia",
    "my husband is not certified but I am",
    "mi novia no tiene licencia pero yo si",
])
def test_contrast_with_an_elided_side_splits_the_pair(message):
    intent = _detect(message)
    assert intent.group_allocation == {"certified_diving": 1, "undecided": 1}
    assert intent.group_size == 2


@pytest.mark.parametrize("message", [
    "mi amigo no tiene licencia y yo tampoco",   # misma polaridad: no es un contraste
    "mis amigos tienen licencia, yo no",         # plural vago: no se sabe cuantos
    "mi amigo no sabe si viene",                 # nadie dice su estado
    "mi hijo tiene 8 años",
    "yo no tengo licencia",                      # una sola persona
    "mi primo es certificado y mi tio no",       # dos personas nombradas, sin quien escribe
])
def test_no_split_without_a_real_contrast_of_the_pair(message):
    assert _detect(message).group_allocation is None


@pytest.mark.parametrize("message, about_writer, value", [
    ("mi amigo tiene licencia, yo no", True, False),
    ("soy certificado y mi hijo no", False, False),
    ("mi novia no tiene licencia pero yo si", True, True),
    ("mi hermano es buzo, yo si quiero bucear", True, None),   # "quiero bucear" no es solo afirmar
    ("mi amigo tiene licencia", True, None),
])
def test_elided_certification_reads_the_clause_polarity(message, about_writer, value):
    assert elided_certification(message, about_writer) is value
