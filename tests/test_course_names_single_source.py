"""Nombres de curso con una sola fuente (centralizacion, 2026-09-15).

Antes el detector buscaba subcadenas en una cadena if/elif ("open water" antes que
"advanced", asi que "advanced open water" salia Open Water) y el nucleo tenia su
propia `_COURSE_MENTION_RE` con variantes que el detector no conocia. Ahora hay una
tabla en el detector que usan los dos, y el nombre compuesto se reconoce con la
etiqueta del registro, sin lista escrita a mano.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import IntentDetector, _distinct_course_levels, courses_mentioned
from src.flows.state import ConversationState


def _activity(message):
    return IntentDetector().detect(message, ConversationState(conversation_id="course")).activity


def test_compound_course_name_is_the_higher_course():
    assert _activity("quiero hacer el advanced open water") == "padi_advanced"
    assert _distinct_course_levels("quiero hacer el advanced open water") == ["padi_advanced"]


@pytest.mark.parametrize("message,expected", [
    ("quiero hacer el curso open water", "padi_open_water"),
    ("I want to do the advanced course", "padi_advanced"),
    # duda entre dos cursos: se conserva el orden del registro (no se elige el mas alto)
    ("no sé si open water o advanced", "padi_open_water"),
    ("no se si hacer el rescue o el divemaster", "padi_rescue"),
])
def test_course_activity_keeps_registry_order(message, expected):
    assert _activity(message) == expected


def test_core_uses_the_same_course_table():
    message = "no sé si open water o advanced"
    assert core._mentioned_courses(message) == courses_mentioned(message) == ["padi_open_water", "padi_advanced"]
    assert not hasattr(core, "_COURSE_MENTION_RE")
