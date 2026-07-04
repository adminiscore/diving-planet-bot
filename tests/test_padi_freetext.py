"""Regression tests: PADI sub-course set from free-text intent.

Bug: IntentDetector emitted activity="padi_course" (generic) regardless of
which specific course the user mentioned.  supervisor._route_detected_intent
only handled "padi_open_water" / "padi_advanced" / "padi_rescue" /
"padi_divemaster" / "padi_specialty", so free-text PADI requests never entered
the course flow and mixed_pending_qty_plan was never populated.

Two routing paths:
- confidence >= 0.30  → direct routing (enough signal in the message)
- 0.20 < confidence < 0.30 → bot asks "¿Te refieres a X?" first (Capa 3),
  then routes after user confirms with "sí" / "yes"
"""

import pytest
from unittest.mock import AsyncMock

from src.agents import orchestrator
from src.agents.intent_detector import DetectedIntent, IntentDetector
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect(msg: str) -> "DetectedIntent":  # noqa: F821
    state = ConversationState(conversation_id="t")
    state.language = "es"
    return IntentDetector().detect(msg, state)


def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="test-padi")
    s.language = lang
    return s


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(
        "src.agents.supervisor.detect_language_llm",
        AsyncMock(return_value=None),
    )


# ---------------------------------------------------------------------------
# Part 1 — IntentDetector emits specific activity names
# ---------------------------------------------------------------------------

class TestIntentDetectorPadiActivity:
    """IntentDetector must emit a specific activity, not the generic 'padi_course'."""

    def test_open_water_es(self):
        intent = _detect("quiero hacer el curso open water")
        assert intent.activity == "padi_open_water"
        assert intent.service_id == "open_water"

    def test_open_water_en(self):
        intent = _detect("I want to do the open water course")
        assert intent.activity == "padi_open_water"
        assert intent.service_id == "open_water"

    def test_advanced_es(self):
        intent = _detect("me interesa el curso advanced")
        assert intent.activity == "padi_advanced"
        assert intent.service_id == "advanced"

    def test_advanced_en(self):
        intent = _detect("I want to do the advanced course")
        assert intent.activity == "padi_advanced"
        assert intent.service_id == "advanced"

    def test_rescue_es(self):
        intent = _detect("quiero hacer el curso rescue diver")
        assert intent.activity == "padi_rescue"
        assert intent.service_id == "rescue"

    def test_divemaster_es(self):
        intent = _detect("información sobre el divemaster")
        assert intent.activity == "padi_divemaster"
        assert intent.service_id == "divemaster"

    def test_generic_padi_stays_generic(self):
        """If the user mentions PADI without a specific course, stays generic."""
        intent = _detect("quiero certificarme con padi")
        assert intent.activity == "padi_course"


# ---------------------------------------------------------------------------
# Part 2 — supervisor sets mixed_pending_qty_plan after free-text PADI intent
# ---------------------------------------------------------------------------

class TestSupervisorPadiFreetextFlow:
    """After a free-text PADI message the bot must enter the course flow
    and populate mixed_pending_qty_plan with the specific service_id.

    The conversation agent (Fase 1) now gates entry routing: a clear booking
    intent makes it pick a booking tool, which reuses the deterministic
    `_route_detected_intent` (IntentDetector still resolves the exact course)."""

    @pytest.fixture(autouse=True)
    def _agent_books(self, _agent_answers_by_default, agent_decides):
        agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "course"})

    @pytest.mark.asyncio
    async def test_open_water_sets_plan_with_location(self):
        state = make_state()
        state.location = "cartagena"
        await route_message(state, "quiero hacer el curso open water")
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "open_water"

    @pytest.mark.asyncio
    async def test_advanced_sets_plan_with_location(self):
        state = make_state()
        state.location = "cartagena"
        await route_message(state, "me interesa el curso advanced")
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "advanced"

    @pytest.mark.asyncio
    async def test_rescue_sets_plan_with_location(self):
        state = make_state()
        state.location = "cartagena"
        await route_message(state, "quiero hacer el curso rescue diver")
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "rescue"

    @pytest.mark.asyncio
    async def test_divemaster_sets_plan_with_location(self):
        state = make_state()
        state.location = "cartagena"
        await route_message(state, "información sobre el divemaster")
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "divemaster"

    @pytest.mark.asyncio
    async def test_open_water_without_location_asks_location(self):
        """Without location the bot must ask where, not skip the flow."""
        state = make_state()
        resp = await route_message(state, "quiero hacer el curso open water")
        assert state.step == Step.MIXED_LOCATION
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "open_water"


# ---------------------------------------------------------------------------
# Part 3 — confirmation flow (confidence 0.20 < c < 0.30)
# ---------------------------------------------------------------------------
# Messages with an equal number of ES/EN signals produce a tie → no language
# detected → confidence = 0.25 (activity only) → bot asks "¿Te refieres a X?"
# before routing.  After the user says "sí" the plan must be set identically
# to the direct-routing path.
# "quiero hacer el rescue diver": quiero=1 ES, diver=1 EN → tie → 0.25
# ---------------------------------------------------------------------------

_AMBIGUOUS_RESCUE_ES = "quiero hacer el rescue diver"   # 0.25 confidence
_AMBIGUOUS_RESCUE_EN = "I want to do rescue diver"      # "I", "want", "do" not in EN keyword list; "diver"=1 EN, no ES → 0.35, routes directly — use a truly ambiguous EN variant
# For EN we force the scenario by pre-seeding pending_intent_confirmation.


class TestConfirmationFlow:
    """Bot asks for confirmation when confidence is 0.20 < c < 0.30,
    then routes correctly after the user confirms."""

    # --- Step 1: bot emits the confirmation question ---

    @pytest.mark.skip(reason="low-confidence '¿Te refieres a X?' trigger removed in Fase 1 — the conversation agent gates entry routing now")
    @pytest.mark.asyncio
    async def test_ambiguous_message_triggers_confirmation_question(self):
        state = make_state("es")
        resp = await route_message(state, _AMBIGUOUS_RESCUE_ES)
        assert "rescue" in resp.lower() or "padi_rescue" in resp.lower(), (
            f"Expected a confirmation question about rescue, got: {resp!r}"
        )
        assert state.pending_intent_confirmation is not None
        assert state.pending_intent_confirmation.activity == "padi_rescue"
        assert state.pending_intent_confirmation.service_id == "rescue"

    @pytest.mark.skip(reason="low-confidence confirmation trigger removed in Fase 1")
    @pytest.mark.asyncio
    async def test_confirmation_question_is_not_final_routing(self):
        """The plan must NOT be set yet after the ambiguous message — only after 'sí'."""
        state = make_state("es")
        state.location = "cartagena"
        await route_message(state, _AMBIGUOUS_RESCUE_ES)
        assert state.mixed_pending_qty_plan is None, (
            "Plan should not be set before the user confirms"
        )

    # --- Step 2a: user says "sí" → plan is set ---

    @pytest.mark.skip(reason="low-confidence confirmation trigger removed in Fase 1")
    @pytest.mark.asyncio
    async def test_si_after_confirmation_sets_plan_with_location(self):
        state = make_state("es")
        state.location = "cartagena"
        await route_message(state, _AMBIGUOUS_RESCUE_ES)   # triggers confirmation
        await route_message(state, "sí")
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "rescue"
        assert state.selected_service == "rescue"

    @pytest.mark.skip(reason="low-confidence confirmation trigger removed in Fase 1")
    @pytest.mark.asyncio
    async def test_si_after_confirmation_without_location_asks_location(self):
        """After confirming with 'sí', if location is unknown the bot must ask for it."""
        state = make_state("es")
        await route_message(state, _AMBIGUOUS_RESCUE_ES)   # triggers confirmation
        await route_message(state, "sí")
        assert state.step == Step.MIXED_LOCATION
        assert state.mixed_pending_qty_plan == "rescue"

    @pytest.mark.asyncio
    async def test_yes_en_after_confirmation_sets_plan(self):
        """English 'yes' also resolves the confirmation."""
        state = make_state("en")
        state.location = "cartagena"
        # Pre-seed pending confirmation (EN ambiguous messages route directly, so we
        # simulate the confirmation state the same way the bot would produce it).
        intent = DetectedIntent(
            activity="padi_rescue",
            service_id="rescue",
            confidence=0.25,
            detected_fields=["activity"],
        )
        state.pending_intent_confirmation = intent
        await route_message(state, "yes")
        assert state.mixed_pending_qty_type == "course"
        assert state.mixed_pending_qty_plan == "rescue"

    # --- Step 2b: user says "no" → main menu, plan never set ---

    @pytest.mark.skip(reason="low-confidence confirmation trigger removed in Fase 1")
    @pytest.mark.asyncio
    async def test_no_after_confirmation_goes_to_main_menu(self):
        state = make_state("es")
        state.location = "cartagena"
        await route_message(state, _AMBIGUOUS_RESCUE_ES)   # triggers confirmation
        resp = await route_message(state, "no")
        assert state.step == Step.MAIN_MENU
        assert state.mixed_pending_qty_plan is None

    @pytest.mark.asyncio
    async def test_no_after_confirmation_clears_pending_intent(self):
        state = make_state("es")
        await route_message(state, _AMBIGUOUS_RESCUE_ES)
        await route_message(state, "no")
        assert state.pending_intent_confirmation is None

    # --- Step 2c: other courses through the same confirmation path ---

    @pytest.mark.asyncio
    async def test_advanced_via_confirmation(self):
        """advanced with low-confidence message → confirm → plan set."""
        state = make_state("es")
        state.location = "cartagena"
        intent = DetectedIntent(
            activity="padi_advanced",
            service_id="advanced",
            confidence=0.25,
            detected_fields=["activity"],
        )
        state.pending_intent_confirmation = intent
        await route_message(state, "sí")
        assert state.mixed_pending_qty_plan == "advanced"
        assert state.selected_service == "advanced"

    @pytest.mark.asyncio
    async def test_divemaster_via_confirmation(self):
        state = make_state("es")
        state.location = "cartagena"
        intent = DetectedIntent(
            activity="padi_divemaster",
            service_id="divemaster",
            confidence=0.25,
            detected_fields=["activity"],
        )
        state.pending_intent_confirmation = intent
        await route_message(state, "sí")
        assert state.mixed_pending_qty_plan == "divemaster"
        assert state.selected_service == "divemaster"

    @pytest.mark.asyncio
    async def test_open_water_via_confirmation(self):
        state = make_state("es")
        state.location = "cartagena"
        intent = DetectedIntent(
            activity="padi_open_water",
            service_id="open_water",
            confidence=0.25,
            detected_fields=["activity"],
        )
        state.pending_intent_confirmation = intent
        await route_message(state, "sí")
        assert state.mixed_pending_qty_plan == "open_water"
        assert state.selected_service == "open_water"
