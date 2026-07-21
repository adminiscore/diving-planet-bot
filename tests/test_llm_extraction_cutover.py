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


# ---------------------------------------------------------------------------
# Fase 2 — dominio grupo/cantidad/edades (group_size/group_allocation/ages).
# Gated by settings.llm_extraction_cutover_group, independent kill switch from
# the Fase 1 certification flag. Same properties to prove as Fase 1, plus the
# generalization: with only the group flag on, certification fields are NOT
# applied even if the LLM returns them, and vice-versa.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_cutover_off_by_default_does_not_call_llm():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="group-cutover-off-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos 3, dos bucean y uno snorkel", intent, state)
    assert intent.group_size is None
    assert intent.group_allocation is None
    assert intent.ages == []


@pytest.mark.asyncio
async def test_group_cutover_on_fills_only_group_domain_fields():
    """With ONLY the group flag on, even if the LLM patch also carries
    certification fields, only group_size/group_allocation/ages get applied —
    is_certified/activity stay for the (independent) Fase 1 flag."""
    intent = DetectedIntent()
    state = ConversationState(conversation_id="group-cutover-on-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_group", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "group_size": 3, "group_allocation": {"certified_diving": 2, "snorkel": 1},
             "ages": [8, 34], "is_certified": True, "activity": "certified_diving",
         })) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover(
            "somos 3, dos buceamos certificados y uno hace snorkel, uno tiene 8", intent, state
        )

    mocked.assert_awaited_once()
    assert intent.group_size == 3
    assert intent.group_allocation == {"certified_diving": 2, "snorkel": 1}
    assert intent.ages == [8, 34]
    assert intent.is_certified is None  # out of scope: certification flag is off
    assert intent.activity is None
    assert "group_size" in intent.detected_fields
    assert "group_allocation" in intent.detected_fields
    assert "ages" in intent.detected_fields


@pytest.mark.asyncio
async def test_group_cutover_never_overrides_already_resolved_group_size():
    """Regex already resolved group_size — with the flag on, the LLM is never
    consulted if that's the only group field and nothing else is missing."""
    intent = DetectedIntent(group_size=2, group_allocation={"certified_diving": 2}, ages=[30, 32])
    state = ConversationState(conversation_id="group-cutover-resolved-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_group", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos 2", intent, state)

    assert intent.group_size == 2
    assert intent.group_allocation == {"certified_diving": 2}
    assert intent.ages == [30, 32]


@pytest.mark.asyncio
async def test_group_cutover_skips_llm_when_only_out_of_scope_fields_missing():
    """Only certification fields are missing; the group flag is on but the
    certification flag is off — must not call the LLM just for a domain that
    isn't cut over."""
    intent = DetectedIntent(group_size=2, group_allocation={"certified_diving": 2}, ages=[30])
    state = ConversationState(conversation_id="group-cutover-out-of-scope-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_group", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("no estoy certificado", intent, state)

    assert intent.is_certified is None


@pytest.mark.asyncio
async def test_group_cutover_on_failure_degrades_to_regex_only():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="group-cutover-failure-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_group", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_apply_llm_extraction_cutover("somos un grupo", intent, state)

    assert intent.group_size is None
    assert intent.group_allocation is None
    assert intent.ages == []


@pytest.mark.asyncio
async def test_group_cutover_result_propagates_to_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="group-cutover-propagation-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_group", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
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
    """Generalization: with BOTH flags on, a single fill_gaps call fills fields
    from both domains (certification + group) — no double LLM call."""
    intent = DetectedIntent()
    state = ConversationState(conversation_id="both-cutovers-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor.settings, "llm_extraction_cutover_group", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
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
# Fase 3 — dominio ubicación (location/island/hotel). Gated by
# settings.llm_extraction_cutover_location, independent kill switch. `location`
# (cartagena|island) drives logistics routing; island/hotel are display/context.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_location_cutover_off_by_default_does_not_call_llm():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="loc-cutover-off-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("salimos desde bocagrande", intent, state)
    assert intent.location is None
    assert intent.island is None
    assert intent.hotel is None


@pytest.mark.asyncio
async def test_location_cutover_on_fills_only_location_domain_fields():
    """With ONLY the location flag on, even if the LLM patch also carries group/
    certification fields, only location/island/hotel get applied."""
    intent = DetectedIntent()
    state = ConversationState(conversation_id="loc-cutover-on-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_location", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "location": "island", "island": "Barú", "hotel": "Las Islas",
             "group_size": 4, "is_certified": True,
         })) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover(
            "estamos en el hotel Las Islas en Barú, somos 4", intent, state
        )

    mocked.assert_awaited_once()
    assert intent.location == "island"
    assert intent.island == "Barú"
    assert intent.hotel == "Las Islas"
    assert intent.group_size is None  # out of scope: group flag is off
    assert intent.is_certified is None
    assert "location" in intent.detected_fields


@pytest.mark.asyncio
async def test_location_cutover_never_overrides_already_resolved_location():
    intent = DetectedIntent(location="cartagena")
    state = ConversationState(conversation_id="loc-cutover-resolved-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_location", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={"location": "island"})) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover("estoy en cartagena", intent, state)

    # island/hotel were still missing, so the LLM is consulted, but location
    # (already resolved by regex) must never be overwritten.
    mocked.assert_awaited_once()
    assert intent.location == "cartagena"


@pytest.mark.asyncio
async def test_location_cutover_on_failure_degrades_to_regex_only():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="loc-cutover-failure-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_location", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_apply_llm_extraction_cutover("estoy en algún sitio", intent, state)

    assert intent.location is None


@pytest.mark.asyncio
async def test_location_cutover_result_propagates_to_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="loc-cutover-propagation-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_location", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "location": "cartagena",
         })):
        await supervisor._maybe_apply_llm_extraction_cutover("salimos desde bocagrande", intent, state)
    supervisor._apply_detected_intent(intent, state)

    assert state.detected_location == "cartagena"
    assert state.location == "cartagena"


# ---------------------------------------------------------------------------
# Fase 8 — dominio perfil/logística (is_colombian/duration/last_dive_over_2_years).
# Gated by settings.llm_extraction_cutover_logistics, independent kill switch.
# is_colombian drives currency + Colombian discount.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logistics_cutover_off_by_default_does_not_call_llm():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="logi-cutover-off-test")

    with patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("soy paisa", intent, state)
    assert intent.is_colombian is None
    assert intent.duration is None
    assert intent.last_dive_over_2_years is None


@pytest.mark.asyncio
async def test_logistics_cutover_on_fills_only_logistics_fields():
    """With ONLY the logistics flag on, other domains' fields in the patch are
    ignored — only is_colombian/duration/last_dive_over_2_years get applied."""
    intent = DetectedIntent()
    state = ConversationState(conversation_id="logi-cutover-on-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_logistics", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
             "is_colombian": True, "duration": "multi_day", "last_dive_over_2_years": True,
             "group_size": 3, "location": "cartagena",
         })) as mocked:
        await supervisor._maybe_apply_llm_extraction_cutover(
            "soy paisa, toda la semana en las islas, hace 4 años que no buceo", intent, state
        )

    mocked.assert_awaited_once()
    assert intent.is_colombian is True
    assert intent.duration == "multi_day"
    assert intent.last_dive_over_2_years is True
    assert intent.group_size is None   # out of scope
    assert intent.location is None
    assert "is_colombian" in intent.detected_fields


@pytest.mark.asyncio
async def test_logistics_cutover_treats_false_as_resolved_not_a_gap():
    """is_colombian=False / last_dive_over_2_years=False are RESOLVED values, not
    gaps — the LLM must not be consulted to 'fill' them (regression guard for the
    falsy-vs-missing bug that motivated the whole plan)."""
    intent = DetectedIntent(is_colombian=False, duration="single_day", last_dive_over_2_years=False)
    state = ConversationState(conversation_id="logi-cutover-false-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_logistics", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_apply_llm_extraction_cutover("cualquier cosa", intent, state)

    assert intent.is_colombian is False
    assert intent.last_dive_over_2_years is False


@pytest.mark.asyncio
async def test_logistics_cutover_result_propagates_to_state():
    intent = DetectedIntent()
    state = ConversationState(conversation_id="logi-cutover-propagation-test")

    with patch.object(supervisor.settings, "llm_extraction_cutover_logistics", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
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

    with patch.object(supervisor.settings, "llm_extraction_cutover_certification", True), \
         patch.object(supervisor, "fill_gaps", new=AsyncMock(return_value={
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
