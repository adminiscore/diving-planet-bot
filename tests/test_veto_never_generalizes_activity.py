"""El veto de actividad no cambia una actividad concreta por la generica de su familia
(2026-09-15).

"I'd like to do the mindful diving specialty": el regex da `specialty_mindful_diving`,
pero el mensaje toca 2 categorias, el veto dispara y el LLM (cuyo enum solo tiene
`padi_specialty`) lo generalizaba. Eso no es corregir, es perder lo que el cliente
nombro.
"""

from unittest.mock import patch

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent


def _intent(activity):
    intent = DetectedIntent()
    intent.activity = activity
    return intent


def test_generic_of_the_same_family_is_ignored():
    intent = _intent("specialty_mindful_diving")
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True):
        supervisor.apply_veto_disagreements(
            {"activity": "padi_specialty"}, intent, "mindful diving specialty",
            {"activity": "specialty_mindful_diving"},
        )
    assert intent.activity == "specialty_mindful_diving"


def test_real_corrections_still_apply():
    intent = _intent("padi_rescue")
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True):
        supervisor.apply_veto_disagreements(
            {"activity": "certified_diving"}, intent, "ya llevo el rescue, quiero seguir buceando",
            {"activity": "padi_rescue"},
        )
    assert intent.activity == "certified_diving"


def test_generalize_rule_comes_from_the_registry():
    assert supervisor._veto_would_generalize("specialty_nitrox", "padi_specialty") is True
    assert supervisor._veto_would_generalize("padi_open_water", "padi_course") is True
    assert supervisor._veto_would_generalize("padi_course", "padi_open_water") is False   # concreta mejora
    assert supervisor._veto_would_generalize("certified_diving", "padi_course") is False  # otra familia
