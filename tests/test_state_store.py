"""Pure serialize/deserialize round-trip tests for state_store — no Redis needed."""

from src.agents.intent_detector import DetectedIntent
from src.flows.decision_tree import ConversationState, Step
from src.state_store import deserialize_state, serialize_state


def make_state(**overrides) -> ConversationState:
    state = ConversationState(conversation_id="test-conv")
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def roundtrip(state: ConversationState) -> ConversationState:
    return deserialize_state(serialize_state(state))


def test_roundtrip_default_state():
    state = make_state()
    result = roundtrip(state)
    assert result == state


def test_roundtrip_non_default_step_and_back_step_override():
    state = make_state(step=Step.FREE_TEXT, back_step_override=Step.MAIN_MENU)
    result = roundtrip(state)
    assert result.step == Step.FREE_TEXT
    assert result.back_step_override == Step.MAIN_MENU


def test_roundtrip_back_step_override_none():
    state = make_state(back_step_override=None)
    result = roundtrip(state)
    assert result.back_step_override is None


def test_roundtrip_pending_intent_confirmation_with_detected_intent():
    intent = DetectedIntent(
        language="es",
        activity="padi_open_water",
        is_certified=True,
        group_size=2,
        detected_fields=["language", "activity"],
    )
    state = make_state(pending_intent_confirmation=intent)
    result = roundtrip(state)
    assert isinstance(result.pending_intent_confirmation, DetectedIntent)
    assert result.pending_intent_confirmation == intent


def test_roundtrip_pending_intent_confirmation_none():
    state = make_state(pending_intent_confirmation=None)
    result = roundtrip(state)
    assert result.pending_intent_confirmation is None


def test_roundtrip_mixed_booking_links_tuples():
    state = make_state(mixed_booking_links=[("Open Water", "https://roverd/ow"), ("Snorkel", "https://roverd/sn")])
    result = roundtrip(state)
    assert result.mixed_booking_links == [("Open Water", "https://roverd/ow"), ("Snorkel", "https://roverd/sn")]
    assert all(isinstance(item, tuple) for item in result.mixed_booking_links)


def test_roundtrip_various_none_fields():
    state = make_state(
        selected_service=None,
        is_certified=None,
        location=None,
        island=None,
        hotel=None,
        is_colombian=None,
    )
    result = roundtrip(state)
    assert result.selected_service is None
    assert result.is_certified is None
    assert result.location is None
    assert result.island is None
    assert result.hotel is None
    assert result.is_colombian is None


def test_roundtrip_mixed_cart_and_quick_replies():
    state = make_state(
        mixed_cart=[{"type": "cert", "qty": 2, "plan": "3_dives", "label": "Certified 3 dives"}],
        quick_replies=[{"title": "Sí", "value": "yes"}],
    )
    result = roundtrip(state)
    assert result.mixed_cart == state.mixed_cart
    assert result.quick_replies == state.quick_replies
