"""F4 (paso 2) del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

Un curso o una especialidad sin nivel (`padi_course`, `padi_specialty`) nunca se
cierra sin decidir cual: antes acababa en un curso sin precio ni link. Decision del
owner (2026-09-14): el bot aclara cual, con las opciones del registro. Si el estado
ya lo decide (sin certificacion -> `default_level`, Open Water), no pregunta.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.agents.supervisor import route_message
from src.domain import activities as dom
from src.flows.state import ConversationState

COURSES = ["padi_open_water", "padi_advanced", "padi_rescue", "padi_divemaster"]
SPECIALTIES = ["specialty_nitrox", "specialty_buoyancy", "specialty_naturalist",
               "specialty_fish_identification", "specialty_mindful_diving"]


def _state(lang="es", activity=None):
    state = ConversationState(conversation_id=f"course-level-{lang}-{activity}")
    state.language = lang
    state.detected_language = lang
    state.detected_activity = activity
    return state


@pytest.mark.parametrize("generic", ["padi_course", "padi_specialty"])
def test_generic_activity_asks_which_one_before_anything_else(generic):
    assert core.next_missing_slot(_state(activity=generic)) == core.SLOT_COURSE_LEVEL


def test_concrete_course_does_not_ask_the_level():
    assert core.next_missing_slot(_state(activity="padi_advanced")) != core.SLOT_COURSE_LEVEL


def test_options_come_from_the_registry_ordered_by_level():
    assert core._course_level_options(_state(activity="padi_course")) == COURSES
    assert core._course_level_options(_state(activity="padi_specialty")) == SPECIALTIES


@pytest.mark.parametrize(("lang", "head"), [("es", "¿Qué curso te interesa?"), ("en", "Which course are you interested in?")])
def test_question_lists_the_registry_options_with_buttons(lang, head):
    state = _state(lang, "padi_course")
    text = core.ask_slot(state, core.SLOT_COURSE_LEVEL)
    assert head in text
    for option in COURSES:
        assert dom.label(option, lang) in text
    assert [qr["value"] for qr in state.quick_replies] == COURSES


def test_specialty_question_says_specialty():
    text = core.ask_slot(_state("es", "padi_specialty"), core.SLOT_COURSE_LEVEL)
    assert "¿Qué especialidad te interesa?" in text


@pytest.mark.parametrize(("answer", "expected"), [
    ("padi_advanced", "padi_advanced"),          # valor del boton
    ("1", "padi_open_water"),                    # numero de la opcion
    ("curso rescue diver + efr", "padi_rescue"), # nombre exacto de la opcion
])
def test_exact_answers_resolve_the_level_and_its_service(answer, expected):
    state = _state(activity="padi_course")
    state.core_pending_slot = core.SLOT_COURSE_LEVEL
    assert core._apply_short_answer(state, answer) is True
    assert state.detected_activity == expected
    assert state.detected_service_id == dom.base_service_id(expected)


def test_a_non_exact_answer_is_left_to_the_llm_resolver():
    state = _state(activity="padi_course")
    state.core_pending_slot = core.SLOT_COURSE_LEVEL
    assert core._apply_short_answer(state, "el que sea para empezar") is False
    assert state.detected_activity == "padi_course"


def test_llm_resolved_value_applies_only_if_it_is_an_offered_option():
    state = _state(activity="padi_course")
    assert core._apply_resolved_slot_value(state, core.SLOT_COURSE_LEVEL, "snorkel") is False
    assert core._apply_resolved_slot_value(state, core.SLOT_COURSE_LEVEL, "padi_open_water") is True
    assert state.detected_service_id == "open_water"


def test_owner_rule_uncertified_generic_course_goes_to_its_default_level():
    state = ConversationState(conversation_id="course-rule")
    supervisor._apply_detected_intent(DetectedIntent(activity="padi_course", is_certified=False), state, "x")
    assert state.detected_activity == "padi_open_water"
    assert state.detected_service_id == "open_water"


def test_unknown_certification_keeps_the_generic_course_so_the_bot_asks():
    state = ConversationState(conversation_id="course-rule-unknown")
    supervisor._apply_detected_intent(DetectedIntent(activity="padi_course"), state, "x")
    assert state.detected_activity == "padi_course"


@pytest.mark.asyncio
async def test_conversation_asks_the_course_and_continues_after_the_choice():
    state = _state("es")
    no_llm = {
        "fill_gaps": AsyncMock(return_value={}),
        "extract_and_verify": AsyncMock(return_value=({}, {})),
        "detect_special_signals": AsyncMock(return_value={}),
    }
    with patch.object(core, "fill_gaps", new=no_llm["fill_gaps"]), \
         patch.object(core, "extract_and_verify", new=no_llm["extract_and_verify"]), \
         patch.object(core, "detect_special_signals", new=no_llm["detect_special_signals"]):
        first = await route_message(state, "quiero hacer un curso PADI")
        assert state.detected_activity == "padi_course"
        assert state.core_pending_slot == core.SLOT_COURSE_LEVEL
        assert "curso" in first.lower()

        await route_message(state, "padi_rescue")
    assert state.detected_activity == "padi_rescue"
    assert state.detected_service_id == "rescue"
    assert state.core_pending_slot != core.SLOT_COURSE_LEVEL
