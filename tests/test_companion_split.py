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


# --- Age-aware offering for a non-certified minor ---------------------------

def _cert_qty_state_with_child(age: int) -> ConversationState:
    st = _cert_qty_state()
    st.detected_ages = [age]
    return st


def _reach_child_offer(age: int) -> tuple[ConversationState, str]:
    st = _cert_qty_state_with_child(age)
    tree.process_message(st, "somos 2, yo buzo y mi hijo no bucea")
    tree.process_message(st, "2")             # last dive <2y -> preview
    offer = tree.process_message(st, "1")     # add cert -> child offer
    return st, offer


def test_child_5_offered_companion_only():
    st, offer = _reach_child_offer(5)
    assert st.step == Step.MIXED_ASK_BEGINNER_ACTIVITY
    titles = [b["title"] for b in st.quick_replies]
    assert not any("minicurso" in t.lower() for t in titles)
    assert not any("snorkel" in t.lower() for t in titles)   # <6 cannot snorkel
    assert any("acompañante" in t.lower() for t in titles)
    assert "acompañar" in offer.lower()


def test_child_7_offered_snorkel_not_minicourse():
    st, _ = _reach_child_offer(7)
    titles = [b["title"] for b in st.quick_replies]
    assert any("snorkel" in t.lower() for t in titles)
    assert not any("minicurso" in t.lower() for t in titles)
    assert not any("bubble" in t.lower() for t in titles)


def test_child_9_offered_bubble_makers_and_snorkel_not_adult_minicourse():
    st, offer = _reach_child_offer(9)
    titles = [b["title"] for b in st.quick_replies]
    assert any("bubble" in t.lower() for t in titles)
    assert any("snorkel" in t.lower() for t in titles)
    assert not any("minicurso" in t.lower() for t in titles)
    assert "Bubble Makers" in offer


def test_child_14_uses_general_offer_with_minicourse():
    """14 >= diving age -> the normal offer (incl. minicourse) applies."""
    st, _ = _reach_child_offer(14)
    assert st.mixed_beginner_child_age is None
    titles = [b["title"] for b in st.quick_replies]
    assert any("minicurso" in t.lower() for t in titles)


def test_child_9_pick_snorkel_adds_snorkel_line():
    st, _ = _reach_child_offer(9)
    # options for 9: 1=bubble, 2=snorkel, 3=companion
    tree.process_message(st, "2")
    assert st.step == Step.MIXED_CART_REVIEW
    assert any(it.get("type") == "snorkel" for it in st.mixed_cart)


def test_child_9_pick_bubble_makers_adds_beginner_line():
    st, _ = _reach_child_offer(9)
    tree.process_message(st, "1")   # Bubble Makers
    assert st.step == Step.MIXED_CART_REVIEW
    assert any(it.get("type") == "beginner" for it in st.mixed_cart)
    assert st.kids_eight_to_ten_count == 1


# --- Auto-build: several non-cert people of different ages, placed one by one -

def _cert_state_with_beginners(ages, cert_qty=2, beg_qty=2) -> ConversationState:
    st = ConversationState(conversation_id="queue")
    st.language = "es"
    st.step = Step.MIXED_CERT_LAST_DIVE
    st.mixed_pending_qty_type = "cert"
    st.mixed_pending_qty_plan = "2_dives_1_day"
    st.location = "cartagena"
    st.mixed_entry_path = "diving_snorkel"
    st.detected_ages = ages
    st.mixed_pending_cert_total_qty = cert_qty
    st.mixed_pending_cert_remaining_qty = cert_qty
    st.mixed_pending_qty_value = cert_qty
    st.mixed_pending_beginner_after_cert = beg_qty
    return st


def _start_queue(st: ConversationState) -> str:
    tree.process_message(st, "2")        # last dive <2y -> preview
    return tree.process_message(st, "1")  # add cert -> begin auto-build queue


def test_autobuild_two_ages_offered_one_by_one():
    st = _cert_state_with_beginners([9, 14])
    _start_queue(st)
    # First: the 9-year-old (child offer, Bubble Makers available, no adult minicourse)
    assert st.mixed_pending_beginner_queue == [9, 14]
    titles = [b["title"].lower() for b in st.quick_replies]
    assert any("bubble" in t for t in titles)
    assert not any("minicurso" in t for t in titles)
    tree.process_message(st, "1")        # 9 -> Bubble Makers
    # Next: the 14-year-old (general offer, minicourse available)
    assert st.mixed_pending_beginner_queue == [14]
    titles = [b["title"].lower() for b in st.quick_replies]
    assert any("minicurso" in t for t in titles)
    tree.process_message(st, "1")        # 14 -> minicourse
    assert st.mixed_pending_beginner_queue == []
    assert st.step == Step.MIXED_CART_REVIEW


def test_autobuild_under_six_auto_companion_no_question():
    st = _cert_state_with_beginners([5, 8])
    _start_queue(st)
    # The 5-year-old is auto-added as companion; only the 8-year-old is asked.
    assert st.mixed_pending_beginner_queue == [8]
    assert any(it.get("type") == "companion" for it in st.mixed_cart)
    tree.process_message(st, "2")        # 8 -> snorkel
    assert st.step == Step.MIXED_CART_REVIEW
    types = [it.get("type") for it in st.mixed_cart]
    assert "companion" in types and "snorkel" in types


def test_autobuild_only_fires_when_ages_match_count():
    """If we don't know every non-cert person's age, fall back to the grouped
    offer (no per-person queue)."""
    st = _cert_state_with_beginners([9], beg_qty=2)   # 2 non-cert but only 1 age known
    _start_queue(st)
    assert st.mixed_pending_beginner_queue == []


def test_autobuild_back_cancels_queue_to_cart():
    st = _cert_state_with_beginners([6, 7])
    _start_queue(st)
    tree.process_message(st, "back")
    assert st.step == Step.MIXED_CART_REVIEW
    assert st.mixed_pending_beginner_queue == []


# --- "Reservar" respects the detected activity (Bubble Makers bug) -----------

def test_reservar_with_minicourse_context_routes_to_beginner():
    """After talking about Bubble Makers / minicurso (detected_activity=minicourse),
    clicking Reservar must enter the BEGINNER flow, not certified diving."""
    st = ConversationState(conversation_id="r1")
    st.language = "es"
    st.step = Step.MAIN_MENU
    st.detected_activity = "minicourse"
    st.detected_is_certified = False
    tree._enter_booking_cart(st)          # click "Reservar"
    tree.process_message(st, "1")         # Cartagena
    assert st.mixed_pending_qty_type == "beginner"
    assert st.step != Step.MIXED_ADD_CERT_PLAN


def test_reservar_with_certified_context_still_routes_to_cert():
    st = ConversationState(conversation_id="r2")
    st.language = "es"
    st.step = Step.MAIN_MENU
    st.detected_activity = "certified_diving"
    st.detected_is_certified = True
    tree._enter_booking_cart(st)
    tree.process_message(st, "1")
    assert st.step == Step.MIXED_ADD_CERT_PLAN
