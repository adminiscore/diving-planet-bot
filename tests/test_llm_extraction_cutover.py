"""Tests for the Fase 1 real cutover (docs/robustness/plan.md §4, dominio
certificación): `settings.llm_extraction_cutover_certification`. Unlike the
Fase 0 shadow probe, this ACTUALLY mutates the regex intent for
`is_certified`/`activity` when the regex left them unresolved — the critical
properties to prove: off by default (no LLM call), on but nothing missing in
scope (no LLM call), on with a real gap (mutates only the 2 in-scope fields,
never anything else), and any failure degrades silently to regex-only.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.decision_tree import ConversationState


@pytest.mark.asyncio
async def test_cutover_off_by_default_does_not_call_llm():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-off-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("im not certfied", intent, state)
    assert intent.is_certified is None
    assert intent.activity is None


@pytest.mark.asyncio
async def test_cutover_on_fills_only_in_scope_fields():
    """Even if the LLM patch includes fields outside the certification domain
    (group_size, location...), only is_certified/activity get applied — the
    rest stay for their own future Fase N cutover."""
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-on-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_certified": False, "activity": "minicourse", "group_size": 2,
         })) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover(
            "hi i wanna dive, im not certfied tho, just me", intent, state
        )

    mocked.assert_awaited_once()
    assert intent.is_certified is False
    assert intent.activity == "minicourse"
    assert intent.group_size is None  # out of scope for this domain's cutover
    assert "is_certified" in intent.detected_fields
    assert "activity" in intent.detected_fields


@pytest.mark.asyncio
async def test_cutover_on_never_overrides_already_resolved_fields():
    """Regex already resolved is_certified=True — even with the flag on, the
    LLM is never even consulted for a field that isn't missing."""
    intent = DetectedIntent(is_certified=True, activity="certified_diving")
    state = ConversationState(conversation_id="cutover-nothing-missing-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos 2", intent, state)

    assert intent.is_certified is True
    assert intent.activity == "certified_diving"


@pytest.mark.asyncio
async def test_cutover_on_skips_llm_when_only_out_of_scope_fields_missing():
    """is_certified/activity are already resolved; only group_size (a
    different domain, not yet cut over) is missing — must not call the LLM
    just for that, since this cutover only covers certification."""
    intent = DetectedIntent(is_certified=False, activity="minicourse")
    state = ConversationState(conversation_id="cutover-out-of-scope-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("cualquier cosa", intent, state)


@pytest.mark.asyncio
async def test_cutover_on_failure_degrades_to_regex_only():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-failure-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        # Must not raise — a cutover failure can never break a real turn, it
        # just leaves the regex result untouched.
        await supervisor._maybe_apply_llm_extraction_cutover("hola", intent, state)

    assert intent.is_certified is None
    assert intent.activity is None


@pytest.mark.asyncio
async def test_cutover_on_empty_llm_patch_leaves_intent_unmutated():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-empty-patch-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={})):
        await supervisor._maybe_apply_llm_extraction_cutover("hola", intent, state)

    assert intent.is_certified is None
    assert intent.activity is None


# ---------------------------------------------------------------------------
# End-to-end: the filled intent must actually propagate to conversation state
# through the normal _apply_detected_intent path used in _dispatch_conversation_agent.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cutover_result_propagates_to_state_via_apply_detected_intent():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-propagation-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_certified": False, "activity": "minicourse",
         })):
        await supervisor._maybe_apply_llm_extraction_cutover(
            "hi i wanna dive, im not certfied tho, just me", intent, state
        )
    supervisor._apply_detected_intent(intent, state)

    assert state.detected_activity == "minicourse"
    assert state.detected_is_certified is False
    assert state.is_certified is False
