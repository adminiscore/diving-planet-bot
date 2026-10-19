"""Tests for the per-domain real cutover (docs/robustness/plan.md §4): certification, group, location and
logistics. Unlike the Fase 0 shadow probe, this ACTUALLY mutates the regex intent when the regex left a field
unresolved; it never overrides a resolved one, and any failure degrades silently to regex-only.

s4-25 removed the per-domain flags (`llm_extraction_cutover_*`, all on) and the tests that pinned a domain off.
OJO: nothing calls `supervisor._maybe_apply_llm_extraction_cutover` since 308488d (28-jul); only these tests run
it. The "must not be called" mocks below do not prove much: the cutover swallows any exception (degrades to
regex-only), AssertionError included.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.state import ConversationState


@pytest.mark.asyncio
async def test_cutover_on_never_overrides_already_resolved_fields():
    """Regex already resolved is_certified=True — the LLM never overrides a
    field that isn't missing."""
    intent = DetectedIntent(is_certified=True, activity="certified_diving")
    state = ConversationState(conversation_id="cutover-nothing-missing-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos 2", intent, state)

    assert intent.is_certified is True
    assert intent.activity == "certified_diving"


@pytest.mark.asyncio
async def test_cutover_on_failure_degrades_to_regex_only():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-failure-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        # Must not raise — a cutover failure can never break a real turn, it
        # just leaves the regex result untouched.
        await supervisor._maybe_apply_llm_extraction_cutover("hola", intent, state)

    assert intent.is_certified is None
    assert intent.activity is None


@pytest.mark.asyncio
async def test_cutover_on_empty_llm_patch_leaves_intent_unmutated():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-empty-patch-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={})):
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

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_certified": False, "activity": "minicourse",
         })):
        await supervisor._maybe_apply_llm_extraction_cutover(
            "hi i wanna dive, im not certfied tho, just me", intent, state
        )
    supervisor._apply_detected_intent(intent, state)

    assert state.detected_activity == "minicourse"
    assert state.detected_is_certified is False
    assert state.is_certified is False


# ---------------------------------------------------------------------------
# Fase 2 — dominio grupo/cantidad/edades (group_size/group_allocation/ages).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_cutover_never_overrides_already_resolved_group_size():
    """Regex already resolved the group fields — the LLM never overrides them."""
    intent = DetectedIntent(group_size=2, group_allocation={"certified_diving": 2}, ages=[30, 32])
    state = ConversationState(conversation_id="group-cutover-resolved-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos 2", intent, state)

    assert intent.group_size == 2
    assert intent.group_allocation == {"certified_diving": 2}
    assert intent.ages == [30, 32]


@pytest.mark.asyncio
async def test_group_cutover_on_failure_degrades_to_regex_only():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="group-cutover-failure-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos un grupo", intent, state)

    assert intent.group_size is None
    assert intent.group_allocation is None
    assert intent.ages == []


@pytest.mark.asyncio
async def test_group_cutover_result_propagates_to_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="group-cutover-propagation-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "group_size": 4, "group_allocation": {"certified_diving": 2, "snorkel": 2}, "ages": [10, 12],
         })):
        await supervisor._maybe_apply_llm_extraction_cutover(
            "vamos 4, 2 buceamos y 2 hacen snorkel, dos niños de 10 y 12", intent, state
        )
    supervisor._apply_detected_intent(intent, state)

    assert state.detected_group_size == 4
    assert state.detected_group_allocation == {"certified_diving": 2, "snorkel": 2}
    assert state.detected_ages == [10, 12]


@pytest.mark.asyncio
async def test_both_cutovers_on_applies_both_domains_in_one_call():
    """A single fill_gaps call fills fields from several domains (certification
    + group) — no double LLM call."""
    intent = DetectedIntent()
    state = ConversationState(conversation_id="both-cutovers-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_certified": False, "activity": "minicourse", "group_size": 2, "ages": [7],
         })) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover(
            "first time, my kid is 7, just the two of us", intent, state
        )

    mocked.assert_awaited_once()  # ONE call covers both domains
    assert intent.is_certified is False
    assert intent.activity == "minicourse"
    assert intent.group_size == 2
    assert intent.ages == [7]


# ---------------------------------------------------------------------------
# Fase 3 — dominio ubicación (location/island/hotel). `location`
# (cartagena|island) drives logistics routing; island/hotel are display/context.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_location_cutover_never_overrides_already_resolved_location():
    intent = DetectedIntent(location="cartagena")
    state = ConversationState(conversation_id="loc-cutover-resolved-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={"location": "island"})) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover("estoy en cartagena", intent, state)

    # island/hotel were still missing, so the LLM is consulted, but location
    # (already resolved by regex) must never be overwritten.
    mocked.assert_awaited_once()
    assert intent.location == "cartagena"


@pytest.mark.asyncio
async def test_location_cutover_on_failure_degrades_to_regex_only():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="loc-cutover-failure-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_apply_llm_extraction_cutover("estoy en algún sitio", intent, state)

    assert intent.location is None


@pytest.mark.asyncio
async def test_location_cutover_result_propagates_to_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="loc-cutover-propagation-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "location": "cartagena",
         })):
        await supervisor._maybe_apply_llm_extraction_cutover("salimos desde bocagrande", intent, state)
    supervisor._apply_detected_intent(intent, state)

    assert state.detected_location == "cartagena"
    assert state.location == "cartagena"


# ---------------------------------------------------------------------------
# Fase 8 — dominio perfil/logística (is_colombian/duration/last_dive_over_2_years).
# is_colombian drives currency + Colombian discount.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logistics_cutover_treats_false_as_resolved_not_a_gap():
    """is_colombian=False / last_dive_over_2_years=False are RESOLVED values, not
    gaps — the LLM must not be consulted to 'fill' them (regression guard for the
    falsy-vs-missing bug that motivated the whole plan)."""
    intent = DetectedIntent(is_colombian=False, duration="single_day", last_dive_over_2_years=False)
    state = ConversationState(conversation_id="logi-cutover-false-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("cualquier cosa", intent, state)

    assert intent.is_colombian is False
    assert intent.last_dive_over_2_years is False


@pytest.mark.asyncio
async def test_logistics_cutover_result_propagates_to_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="logi-cutover-propagation-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_colombian": True, "duration": "multi_day",
         })):
        await supervisor._maybe_apply_llm_extraction_cutover("soy de barranquilla, toda la semana", intent, state)
    supervisor._apply_detected_intent(intent, state)

    assert state.is_colombian is True
    assert state.detected_duration == "multi_day"


@pytest.mark.asyncio
async def test_cutover_log_line_does_not_truncate_the_message(caplog):
    """Real bug found live (2026-07-21): the [EXTRACT][CUTOVER] log line cut the
    message to 60 chars, so candidates harvested by scripts/harvest_cutover_logs.py
    lost the end of the customer's actual message — the exact opposite of what
    Fase 6 (bucle de datos reales) needs. Full messages must survive in the log."""
    long_message = (
        "hey never been underwater before, kinda nervous, wanna give it a try, "
        "just me, is this a good idea for someone with no experience at all"
    )
    assert len(long_message) > 60
    intent = DetectedIntent()
    state = ConversationState(conversation_id="cutover-log-truncation-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_certified": False, "activity": "minicourse",
         })), \
         caplog.at_level("INFO"):
        await supervisor._maybe_apply_llm_extraction_cutover(long_message, intent, state)

    assert long_message in caplog.text


@pytest.mark.asyncio
async def test_shadow_log_line_does_not_truncate_the_message(caplog):
    long_message = (
        "hey never been underwater before, kinda nervous, wanna give it a try, "
        "just me, is this a good idea for someone with no experience at all"
    )
    assert len(long_message) > 60
    intent = DetectedIntent()
    state = ConversationState(conversation_id="shadow-log-truncation-test")

    with patch.object(supervisor.settings, "llm_extraction_shadow_mode", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={"is_certified": False})), \
         caplog.at_level("INFO"):
        await supervisor._maybe_log_llm_extraction_shadow(long_message, intent, state)

    assert long_message in caplog.text
