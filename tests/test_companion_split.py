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
    # Routes to the CERTIFIED path (not beginner). A pure-certified context with
    # no beginner companion now recommends the 2-dive plan and moves to quantity
    # (owner decision 2026-07-20) instead of showing the plan menu.
    assert st.mixed_pending_qty_type == "cert"
    assert st.step == Step.MIXED_ADD_QTY


# --- Family A: natural-language "self + companion" counts at the qty step ---
# Regression (screenshots 2026-07-08): "Voy yo y mi pareja me acompaña" and
# similar phrasings returned None -> the bot answered "no te entendí" to a
# perfectly clear 2-person answer.

@pytest.mark.parametrize("msg", [
    "Voy yo y mi pareja me acompana",
    "voy yo y mi novia",
    "yo y mi pareja",
    "mi hijo y yo",
    "vengo con mi amiga",
    "me acompana mi esposo",
    "mi esposa y yo",
])
def test_self_plus_companion_counts_as_two(msg):
    assert tree._parse_mixed_quantity(msg) == 2


@pytest.mark.parametrize("msg", ["mi plan", "con calma", "yo solo", "familia"])
def test_self_plus_companion_does_not_overfire(msg):
    # No companion noun / ambiguous -> must NOT be coerced to 2.
    assert tree._parse_mixed_quantity(msg) != 2


# --- Family B: dive count + another activity for part of the group ----------
# Regression (screenshots 2026-07-08): "2 y uno que quiere hacer snorkel" took
# only the 2 divers and silently dropped the snorkeler from the booking.

@pytest.mark.parametrize("msg,expected", [
    ("2 y uno que quiere hacer snorkel", (2, 1)),
    ("somos 2 y uno hace snorkel", (1, 1)),        # "somos N" = total
    ("somos 3 y 2 hacen snorkel", (1, 2)),
    ("3 buceamos y 1 hace snorkel", (3, 1)),
    ("yo buceo y mi novia snorkel", (1, 1)),
    ("2 y mi hijo minicurso", (2, 1)),
    ("4 y dos quieren snorkel", (4, 2)),
    ("somos 5 y 2 minicurso", (3, 2)),
])
def test_detect_cert_qty_activity_split(msg, expected):
    assert tree._detect_cert_qty_activity_split(msg) == expected


@pytest.mark.parametrize("msg", [
    "2", "somos 3", "5", "cuatro", "2 personas", "yo y mi pareja", "2 buceos",
    "somos 4 certificados",
])
def test_detect_cert_qty_activity_split_no_false_positive(msg):
    assert tree._detect_cert_qty_activity_split(msg) is None


def test_qty_step_mixed_activity_does_not_drop_snorkeler():
    """End-to-end at the qty step: 2 divers + 1 snorkeler must become a
    cert subgroup of 2 with 1 non-cert person queued (offered snorkel/etc.),
    never 2 alone with the snorkeler dropped."""
    st = _cert_qty_state()
    tree.process_message(st, "2 y uno que quiere hacer snorkel")
    assert st.step == Step.MIXED_CERT_LAST_DIVE
    assert st.mixed_pending_cert_total_qty == 2
    assert st.mixed_pending_beginner_after_cert == 1


def test_qty_step_self_plus_companion_proceeds():
    """"yo y mi pareja" at the qty step counts as 2 and proceeds (no 'no te
    entendí')."""
    st = _cert_qty_state()
    tree.process_message(st, "Voy yo y mi pareja me acompana")
    assert st.step == Step.MIXED_CERT_LAST_DIVE
    assert st.mixed_pending_cert_total_qty == 2


# --- Companion upsell (owner feedback #8): offer the companion diving --------

def _at_activity_menu(lang: str = "es") -> ConversationState:
    st = ConversationState(conversation_id="upsell-test")
    st.language = lang
    st.location = "cartagena"
    st.mixed_cart = []
    st.step = Step.MIXED_ADD_ACTIVITY
    return st


def test_companion_choice_triggers_upsell():
    """Picking 'companion' from the activity menu offers the mini-course/snorkel
    upsell instead of adding a pure companion straight away."""
    st = _at_activity_menu()
    resp = tree._handle_mixed_add_activity(st, "5")
    assert st.step == Step.MIXED_COMPANION_UPSELL
    assert "minicurso" in resp.lower() or "buceo" in resp.lower()
    values = [b["value"] for b in st.quick_replies]
    assert values[:3] == ["1", "2", "3"]  # mini-course / snorkel / just accompany


@pytest.mark.parametrize("pick,expected_type", [
    ("1", "beginner"),   # yes -> mini-course
    ("2", "snorkel"),    # yes -> snorkel
    ("3", "companion"),  # no  -> pure companion
])
def test_companion_upsell_branches(pick, expected_type):
    st = _at_activity_menu()
    tree._handle_mixed_add_activity(st, "5")
    tree._handle_mixed_companion_upsell(st, pick)
    assert st.mixed_pending_qty_type == expected_type
    assert st.step == Step.MIXED_ADD_QTY


def test_companion_upsell_back_returns_to_activity_menu():
    st = _at_activity_menu()
    tree._handle_mixed_add_activity(st, "5")
    tree._handle_mixed_companion_upsell(st, "back")
    assert st.step == Step.MIXED_ADD_ACTIVITY


def test_companion_upsell_not_understood_stays():
    st = _at_activity_menu()
    tree._handle_mixed_add_activity(st, "5")
    tree._handle_mixed_companion_upsell(st, "bla bla")
    assert st.step == Step.MIXED_COMPANION_UPSELL


def test_companion_declined_is_added_as_paid_seat_in_summary():
    """No -> the companion is added as a paid seat and appears in the final
    tariff at its real price (kept, not zeroed)."""
    from src.flows.decision_tree import COMPANION_PRICE
    st = _at_activity_menu()
    st.mixed_final_is_colombian = False
    tree._handle_mixed_add_activity(st, "5")     # companion
    tree._handle_mixed_companion_upsell(st, "3")  # just accompany
    tree._handle_mixed_add_qty(st, "1")           # qty 1 -> preview
    # confirm the preview add (option 1 = add to cart)
    tree.process_message(st, "1")
    assert any(it.get("type") == "companion" for it in st.mixed_cart)
    summary = tree._format_mixed_final_summary(st)
    # Companion line present with its non-zero price.
    assert "compañante" in summary.lower() or "companion" in summary.lower()
    usd = int(round(COMPANION_PRICE["usd_online"]))
    assert str(usd) in summary


# --- Proactive free-text companion mention -> upsell (owner feedback #8) ------

@pytest.mark.parametrize("msg", [
    "voy con mi novia que solo va a acompañar",
    "tengo pensado ir con alguien que solo acompaña",
    "va a venir mi hermano de acompañante",
    "mi pareja solo me acompaña",
    "viene mi amiga como acompañante",
    "someone is coming just to accompany",
    "my girlfriend will just watch",
])
def test_mentions_pure_companion_true(msg):
    from src.agents.supervisor import _mentions_pure_companion
    assert _mentions_pure_companion(msg) is True


@pytest.mark.parametrize("msg", [
    "¿el acompañante paga lo mismo?",   # question -> RAG, not the flow
    "quiero bucear",                     # no companion
    "somos 2 buzos certificados",        # no companion
    "quiero reservar buceo certificado", # no companion
    "voy con mi novia y los dos buceamos",  # companion but both dive (not pure)
])
def test_mentions_pure_companion_false(msg):
    from src.agents.supervisor import _mentions_pure_companion
    assert _mentions_pure_companion(msg) is False


# --- Free-text acceptance of the recommendation (2026-07-17) -----------------
# The upsell message was reframed from a neutral open question into a
# minicurso-led recommendation ("le apunto el minicurso... ¿te parece?"), so
# customers now reply with a bare "sí/vale/dale" much more than clicking the
# exact button title. These regression tests cover that free-text path.

@pytest.mark.parametrize("msg", ["vale", "si", "sí", "dale", "perfecto", "claro", "de una", "ok", "okay"])
def test_companion_upsell_bare_affirmation_accepts_minicourse(msg):
    st = _at_activity_menu()
    tree._handle_mixed_add_activity(st, "5")
    tree._handle_mixed_companion_upsell(st, msg)
    assert st.mixed_pending_qty_type == "beginner"
    assert st.step == Step.MIXED_ADD_QTY


@pytest.mark.parametrize("msg", [
    "mejor snorkel", "snorkel para ella", "quiero snorkel para ella", "esnorkel",
])
def test_companion_upsell_free_text_snorkel(msg):
    st = _at_activity_menu()
    tree._handle_mixed_add_activity(st, "5")
    tree._handle_mixed_companion_upsell(st, msg)
    assert st.mixed_pending_qty_type == "snorkel"


@pytest.mark.parametrize("msg", [
    "no", "no gracias", "no thanks", "no, solo que acompañe", "solo quiere acompañar",
])
def test_companion_upsell_free_text_decline(msg):
    """A bare 'no' must decline the mini-course recommendation (pure companion),
    NOT be misread as snorkel via _parse_choice's cross-menu 'No'->'2' title
    match (regression: a different menu's exact button title collided here)."""
    st = _at_activity_menu()
    tree._handle_mixed_add_activity(st, "5")
    tree._handle_mixed_companion_upsell(st, msg)
    assert st.mixed_pending_qty_type == "companion"


def test_companion_upsell_message_leads_with_minicourse_recommendation():
    st = _at_activity_menu()
    resp = tree._handle_mixed_add_activity(st, "5")
    low = resp.lower()
    assert "minicurso" in low
    # Recommendation framing, not a neutral open question.
    assert "recomiendo" in low or "te voy a apuntar" in low or "voy a apuntarle" in low


# --- Context recap when returning to "add another activity" (2026-07-17) ----
# Owner-reported: clicking "back"/"add another activity" from the cart review
# sometimes lands on a bare "¿Qué actividad quieres añadir al carrito?" with no
# acknowledgment of what's already known (cart items, origin) — the customer
# reads this as the bot having forgotten everything. The underlying state was
# never actually cleared (only the transient in-progress-item fields are), so
# the fix is a short recap prepended to that message, not a data fix.

def test_add_activity_recap_shows_cart_and_cartagena_origin():
    st = ConversationState(conversation_id="recap-1")
    st.language = "es"
    st.location = "cartagena"
    st.mixed_cart = [{"type": "beginner", "plan": None, "qty": 2, "label": "Minicurso de buceo"}]
    resp = tree._goto_mixed_add_activity(st)
    assert "minicurso" in resp.lower()
    assert "cartagena" in resp.lower()
    assert "qué actividad quieres" in resp.lower()


def test_add_activity_recap_shows_island_and_hotel():
    st = ConversationState(conversation_id="recap-2")
    st.language = "es"
    st.location = "island"
    st.island = "Isla Grande"
    st.hotel = "Cocoliso"
    st.mixed_cart = []
    resp = tree._goto_mixed_add_activity(st)
    assert "isla grande" in resp.lower()
    assert "cocoliso" in resp.lower()


def test_add_activity_recap_empty_when_nothing_known_yet():
    """A brand-new booking (no cart, no location) shows the plain question —
    no empty-cart placeholder or blank recap noise."""
    st = ConversationState(conversation_id="recap-3")
    st.language = "es"
    resp = tree._goto_mixed_add_activity(st)
    assert resp == "¿Qué actividad quieres *añadir* al carrito?"


def test_add_activity_recap_english():
    st = ConversationState(conversation_id="recap-4")
    st.language = "en"
    st.location = "cartagena"
    st.mixed_cart = [{"type": "snorkel", "plan": None, "qty": 3, "label": "Snorkeling"}]
    resp = tree._goto_mixed_add_activity(st)
    assert "snorkeling" in resp.lower()
    assert "cartagena" in resp.lower()
