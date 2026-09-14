"""Pregunta aclaratoria "¿ya certificados o quieren certificarse?" (owner 2026-09-15).

Un nivel PADI nombrado sin decir si ya lo tienen o lo quieren sacar ("hola somos 4
open water", "2 advanced and 2 snorkel") no se da por curso ni por buceo certificado:
el bot pregunta. La senal reusa los patrones del detector, sin vocabulario nuevo.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import course_level_is_ambiguous
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "hola somos 4 open water",
    "2 open water y 3 snorkel",
    "2 advanced and 2 snorkel",
])
def test_level_named_without_holding_or_wanting_is_ambiguous(message):
    assert course_level_is_ambiguous(message) is True


@pytest.mark.parametrize("message", [
    "quiero el open water",                 # lo quiere
    "quiero hacer el advanced",
    "tengo el open water",                  # lo tiene
    "we are 2 open water divers",
    "somos 3, 2 con open water y 1 no",     # afirma certificacion
    "quiero bucear, somos 2",               # no nombra nivel
    "I'd like to take the advanced course",  # nombra el producto (curso)
    "quiero hacer el curso de advanced",
])
def test_clear_messages_are_not_ambiguous(message):
    assert course_level_is_ambiguous(message) is False


def _state():
    s = ConversationState(conversation_id="cert-or-course")
    s.language = "es"
    return s


@pytest.mark.asyncio
async def test_ambiguous_level_asks_before_quoting():
    state = _state()
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={"is_certified": True})), \
         patch.object(core, "extract_and_verify", new=AsyncMock(return_value=({"is_certified": True}, {}))):
        await core._understand(state, "hola somos 4 open water")
    assert state.needs_cert_or_course is True
    assert state.is_certified is None          # no se da por buena la suposicion del LLM
    assert core.next_missing_slot(state) == core.SLOT_CERT_OR_COURSE
    question = core.ask_slot(state, core.SLOT_CERT_OR_COURSE)
    assert "?" in question
    assert [q["value"] for q in state.quick_replies] == ["already_certified", "wants_course"]


def test_already_certified_answer_means_certified_diving():
    state = _state()
    state.needs_cert_or_course = True
    state.cert_or_course_level = "padi_open_water"
    state.detected_activity = "padi_open_water"
    state.core_pending_slot = core.SLOT_CERT_OR_COURSE
    assert core._apply_short_answer(state, "already_certified") is True
    assert state.is_certified is True
    assert state.detected_activity == "certified_diving"
    assert state.needs_cert_or_course is False


def test_wants_course_answer_keeps_the_named_level():
    state = _state()
    state.needs_cert_or_course = True
    state.cert_or_course_level = "padi_advanced"
    state.detected_activity = "padi_advanced"
    assert core._apply_resolved_slot_value(state, core.SLOT_CERT_OR_COURSE, "wants_course") is True
    assert state.is_certified is False
    assert state.detected_activity == "padi_advanced"


def test_course_noun_comes_from_the_registry_labels():
    from src.agents.intent_detector import _course_family_nouns
    assert {"curso", "course"} <= _course_family_nouns()
