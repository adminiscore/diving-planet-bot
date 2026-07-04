"""Regression tests for the certified-diver + non-certified-companion split.

Scenario (owner request): the speaker has already said they are a certified
diver; when the bot asks how many people, they reply that a companion (e.g. a
girlfriend) is coming who is NOT certified. The bot must:
  - understand it is 2 people = 1 certified + 1 non-certified,
  - run the certified subgroup flow,
  - then offer the non-certified companion the beginner options
    (minicurso / snorkel / just-a-companion), with a proactive, positive nudge.
"""

import pytest

from src.flows.decision_tree import DecisionTree, ConversationState, Step


tree = DecisionTree()


def _cert_qty_state(lang: str = "es") -> ConversationState:
    """State parked at MIXED_ADD_QTY for a certified speaker who already picked
    a plan (2 dives / 1 day) and a Cartagena origin."""
    st = ConversationState(conversation_id="companion-test")
    st.language = lang
    st.step = Step.MIXED_ADD_QTY
    st.mixed_pending_qty_type = "cert"
    st.mixed_pending_qty_plan = "2_dives_1_day"
    st.location = "cartagena"
    st.mixed_entry_path = "diving_snorkel"
    return st


# --- Detection helper -------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "somos 2, yo buzo y mi novia no lo es",
    "yo tengo el open water y ella no bucea",
    "mi novia no esta certificada",
    "uno certificado con open water y otro sin certificar",
    "solo yo soy buzo, ella no",
    "my girlfriend isn't certified",
    "she doesn't dive",
])
def test_reveals_non_certified_companion_true(msg):
    assert tree._reveals_non_certified_companion(msg) is True


@pytest.mark.parametrize("msg", [
    "3",
    "somos 3 personas",
    "somos 2 y no queremos separarnos",   # both certified, 'no' not about cert
    "cuatro por favor",
    "we are four",
])
def test_reveals_non_certified_companion_false(msg):
    assert tree._reveals_non_certified_companion(msg) is False


# --- Split routing at the qty step ------------------------------------------

def test_companion_split_with_number():
    st = _cert_qty_state()
    tree.process_message(st, "somos 2, yo buzo y mi novia no lo es")
    assert st.step == Step.MIXED_CERT_LAST_DIVE
    assert st.mixed_pending_cert_total_qty == 1
    assert st.mixed_pending_beginner_after_cert == 1


def test_companion_split_without_number_defaults_to_two():
    st = _cert_qty_state()
    tree.process_message(st, "mi novia no esta certificada")
    assert st.step == Step.MIXED_CERT_LAST_DIVE
    assert st.mixed_pending_cert_total_qty == 1
    assert st.mixed_pending_beginner_after_cert == 1


def test_plain_number_does_not_trigger_split():
    st = _cert_qty_state()
    tree.process_message(st, "3")
    assert st.mixed_pending_cert_total_qty == 3
    assert (st.mixed_pending_beginner_after_cert or 0) == 0


def test_no_split_when_group_stays_together_all_certified():
    """'no queremos separarnos' must NOT be read as a non-certified companion."""
    st = _cert_qty_state()
    tree.process_message(st, "somos 2 y no queremos separarnos")
    assert (st.mixed_pending_beginner_after_cert or 0) == 0


# --- Companion is offered the beginner options afterwards -------------------

def _drive_to_beginner_offer(st: ConversationState) -> str:
    """From the split at MIXED_CERT_LAST_DIVE, add the cert subgroup and reach
    the beginner-activity offer for the non-certified companion."""
    tree.process_message(st, "2")   # last dive: <2 years -> preview
    return tree.process_message(st, "1")   # preview: add to cart -> beginner offer


def test_companion_offered_minicurso_snorkel_and_companion_option():
    st = _cert_qty_state()
    tree.process_message(st, "somos 2, yo buzo y mi novia no lo es")
    offer = _drive_to_beginner_offer(st)
    assert st.step == Step.MIXED_ASK_BEGINNER_ACTIVITY
    titles = [b["title"] for b in st.quick_replies]
    assert any("Minicurso" in t for t in titles)
    assert any("Snorkel" in t for t in titles)
    assert any("acompañante" in t.lower() for t in titles)
    # Proactive, positive nudge toward trying an activity.
    assert "iniciarse" in offer.lower() or "perfecta" in offer.lower()


def test_companion_choice_adds_companion_cart_line():
    st = _cert_qty_state()
    tree.process_message(st, "somos 2, yo buzo y mi novia no lo es")
    _drive_to_beginner_offer(st)
    # Pick the "just a companion" option (value 3 when Open Water is not offered).
    tree.process_message(st, "3")
    assert st.step == Step.MIXED_CART_REVIEW
    types = [it.get("type") for it in st.mixed_cart]
    assert "cert" in types
    assert "companion" in types


def test_companion_can_choose_minicourse():
    st = _cert_qty_state()
    tree.process_message(st, "somos 2, yo buzo y mi novia no lo es")
    _drive_to_beginner_offer(st)
    tree.process_message(st, "1")  # minicurso
    # Beginner qty question fires (kids inline) or beginner item pending.
    assert st.mixed_pending_qty_type == "beginner" or any(
        it.get("type") == "beginner" for it in st.mixed_cart
    )


# --- Feminine-speaker understanding (group size) ----------------------------

@pytest.mark.parametrize("msg,expected", [
    ("vamos 3 amigas de viaje", 3),
    ("somos 4 compañeras", 4),
    ("2 amigas quieren bucear", 2),
])
def test_group_size_detects_feminine_nouns(msg, expected):
    from src.agents.intent_detector import IntentDetector
    intent = IntentDetector().detect(msg, ConversationState(conversation_id="fem"))
    assert intent.group_size == expected
