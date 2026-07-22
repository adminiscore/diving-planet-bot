"""Tests for the Fase 0 shadow-mode wiring in supervisor.py
(docs/robustness/plan.md §4). The critical safety property: with the flag off
(the default everywhere), the LLM gap-filler must never be called and must
never affect the reply or conversation state.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.decision_tree import ConversationState


@pytest.mark.asyncio
async def test_shadow_mode_off_by_default_does_not_call_llm():
    intent = DetectedIntent()  # everything missing
    state = ConversationState(conversation_id="shadow-off-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_log_llm_extraction_shadow("hola", intent, state)
    # No exception raised means fill_gaps was never invoked.


@pytest.mark.asyncio
async def test_shadow_mode_on_calls_llm_but_does_not_mutate_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="shadow-on-test")
    original_step = state.step

    with patch.object(supervisor.settings, "llm_extraction_shadow_mode", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={"is_certified": False})) as mocked:
        await supervisor._maybe_log_llm_extraction_shadow("im not certfied", intent, state)

    mocked.assert_awaited_once()
    assert state.step == original_step
    assert intent.is_certified is None  # regex_intent itself is never mutated


@pytest.mark.asyncio
async def test_shadow_mode_on_skips_llm_when_nothing_missing():
    intent = DetectedIntent(
        activity="certified_diving", is_certified=True, group_size=2,
        group_allocation={"certified_diving": 2}, last_dive_over_2_years=False,
        duration="single_day", location="cartagena", island="x", hotel="y",
        ages=[30], cert_dives=2, cert_days=1, is_colombian=False,
    )
    state = ConversationState(conversation_id="shadow-nothing-missing-test")

    with patch.object(supervisor.settings, "llm_extraction_shadow_mode", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_log_llm_extraction_shadow("cualquier cosa", intent, state)


@pytest.mark.asyncio
async def test_shadow_mode_probe_failure_is_swallowed():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="shadow-failure-test")

    with patch.object(supervisor.settings, "llm_extraction_shadow_mode", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        # Must not raise — a probe failure can never break a real turn.
        await supervisor._maybe_log_llm_extraction_shadow("hola", intent, state)
