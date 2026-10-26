"""Nombres de curso con una sola fuente (centralizacion, 2026-09-15).

Antes el detector buscaba subcadenas en una cadena if/elif ("open water" antes que
"advanced", asi que "advanced open water" salia Open Water) y el nucleo tenia su
propia `_COURSE_MENTION_RE` con variantes que el detector no conocia. Ahora hay una
tabla en el detector que usan los dos, y el nombre compuesto se reconoce con la
etiqueta del registro, sin lista escrita a mano.
lat-11 T6d (26-oct): fuera los tests de IntentDetector.detect (la clase se quitó; la actividad la decide el
extractor).
"""

from src.agents import conversational_core as core
from src.agents.intent_detector import courses_mentioned


def test_core_uses_the_same_course_table():
    message = "no sé si open water o advanced"
    assert core._mentioned_courses(message) == courses_mentioned(message) == ["padi_open_water", "padi_advanced"]
    assert not hasattr(core, "_COURSE_MENTION_RE")
