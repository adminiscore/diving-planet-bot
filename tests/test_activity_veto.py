"""Tests for the LLM activity-veto (docs/multi-agent-refactor-plan.md, hallazgo
en vivo conversacion real "purple-sun-590", 2026-09-03):
`supervisor._maybe_veto_activity_via_llm`.

Unlike `_maybe_apply_llm_extraction_cutover` (fills gaps only), this CAN
correct an `activity` the regex already resolved -- but only for genuinely
ambiguous messages (2+ activity categories matched). Critical properties to
prove: off by default (no LLM call), not ambiguous (no LLM call even with
flags on), shadow mode logs but never mutates, cutover mode mutates activity
+ service_id, agreement means no mutation, and any failure degrades silently
to regex-only.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.state import ConversationState

_AMBIGUOUS_MSG = "Me gustaria sacarme el open water, pero nunca he buceado"
_UNAMBIGUOUS_MSG = "quiero hacer snorkel"


@pytest.mark.asyncio
async def test_off_by_default_does_not_call_llm():
    intent = DetectedIntent(activity="minicourse")
    state = ConversationState(conversation_id="veto-off-test")

    with patch.object(supervisor, "verify_activity", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_veto_activity_via_llm(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"


@pytest.mark.asyncio
async def test_no_activity_resolved_skips_veto():
    """Sin `activity` resuelto no hay nada que vetar -- eso lo cubre el
    cutover de huecos (_maybe_apply_llm_extraction_cutover), no este veto."""
    intent = DetectedIntent(activity=None)
    state = ConversationState(conversation_id="veto-no-activity-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_veto_activity_via_llm(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity is None


@pytest.mark.asyncio
async def test_unambiguous_message_skips_llm_call():
    """0 o 1 categoria = no ambiguo -- se confia en el regex sin gastar una
    llamada LLM."""
    intent = DetectedIntent(activity="snorkel")
    state = ConversationState(conversation_id="veto-unambiguous-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_veto_activity_via_llm(_UNAMBIGUOUS_MSG, intent, state)
    assert intent.activity == "snorkel"


@pytest.mark.asyncio
async def test_shadow_mode_logs_but_never_mutates():
    intent = DetectedIntent(activity="minicourse", service_id="minicourse")
    state = ConversationState(conversation_id="veto-shadow-test")

    with patch.object(supervisor.settings, "llm_activity_veto_shadow_mode", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(return_value="padi_open_water")):
        await supervisor._maybe_veto_activity_via_llm(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.service_id == "minicourse"


@pytest.mark.asyncio
async def test_cutover_mode_applies_llm_activity_and_service_id():
    intent = DetectedIntent(activity="minicourse", service_id="minicourse")
    state = ConversationState(conversation_id="veto-cutover-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(return_value="padi_open_water")):
        await supervisor._maybe_veto_activity_via_llm(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "padi_open_water"
    assert intent.service_id == "open_water"
    assert "activity" in intent.detected_fields


@pytest.mark.asyncio
async def test_cutover_mode_no_mutation_when_llm_agrees():
    """verify_activity devuelve None cuando el LLM coincide con el regex --
    nada que aplicar."""
    intent = DetectedIntent(activity="minicourse", service_id="minicourse")
    state = ConversationState(conversation_id="veto-agree-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(return_value=None)):
        await supervisor._maybe_veto_activity_via_llm(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.service_id == "minicourse"


@pytest.mark.asyncio
async def test_veto_failure_degrades_silently_to_regex_only():
    intent = DetectedIntent(activity="minicourse", service_id="minicourse")
    state = ConversationState(conversation_id="veto-error-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_veto_activity_via_llm(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.service_id == "minicourse"


@pytest.mark.asyncio
async def test_real_bug_message_end_to_end_via_understand():
    """Reproduce el flujo real (_understand, conversational_core.py) con el
    mensaje real del hallazgo en vivo -- con el veto en cutover, la actividad
    final debe ser padi_open_water/open_water, no minicourse."""
    from src.agents.conversational_core import _understand

    state = ConversationState(conversation_id="veto-e2e-test")
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_activity", new=AsyncMock(return_value="padi_open_water")):
        intent, _carry = await _understand(state, _AMBIGUOUS_MSG)
    assert intent.activity == "padi_open_water"
    assert intent.service_id == "open_water"
