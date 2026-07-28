"""Age & certification eligibility: rules, age detection, and the deterministic
supervisor responder that informs what each person can/can't do."""

import pytest

from src.flows import eligibility as elig
from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState, Step
from src.agents.supervisor import route_message


detector = IntentDetector()


def _detect(msg: str):
    return detector.detect(msg, ConversationState(conversation_id="elig"))


# ---------------------------------------------------------------------------
# Eligibility rules (single source of truth)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age,expected", [
    (4, []),
    (5, []),
    (6, [elig.SNORKEL]),
    (7, [elig.SNORKEL]),
    (8, [elig.SNORKEL, elig.BUBBLE_MAKERS]),
    (9, [elig.SNORKEL, elig.BUBBLE_MAKERS]),
    (10, [elig.SNORKEL, elig.MINICOURSE, elig.OPEN_WATER]),
    (14, [elig.SNORKEL, elig.MINICOURSE, elig.OPEN_WATER]),
    (30, [elig.SNORKEL, elig.MINICOURSE, elig.OPEN_WATER]),
])
def test_activities_for_age(age, expected):
    assert elig.activities_for_age(age) == expected


def test_can_fun_dive_requires_cert_and_age():
    assert elig.can_fun_dive(30, True) is True
    assert elig.can_fun_dive(30, False) is False
    assert elig.can_fun_dive(9, True) is False   # too young regardless of cert


def test_bubble_makers_window():
    assert elig.can_bubble_makers(7) is False
    assert elig.can_bubble_makers(8) is True
    assert elig.can_bubble_makers(10) is True
    assert elig.can_bubble_makers(11) is False


@pytest.mark.parametrize("age,must_include", [
    (5, "acompañar"),          # too young -> companion framing
    (7, "snorkel"),
    (9, "Bubble Makers"),
    (14, "Open Water"),
    (14, "Divemaster"),        # 12-17 -> Divemaster starts at 18
    (17, "Divemaster"),
    # 12-17 CAN do Advanced/Rescue (from 12) — the note must confirm it, not only
    # jump to the Divemaster-at-18 limit (weird-battery finding AG4).
    (12, "Advanced"),
    (14, "Advanced"),
    (17, "Rescue"),
    (10, "Advanced"),          # 10-11: mentions Advanced/Rescue start at 12
])
def test_age_note_mentions_right_activity_es(age, must_include):
    note = elig.age_eligibility_note(age, "es")
    assert must_include.lower() in note.lower()


@pytest.mark.parametrize("age", [12, 14, 17])
def test_age_note_12_to_17_confirms_advanced_available_now(age):
    """A 12-17 year old asking about Advanced must be told it's available (from 12),
    not implicitly denied by only mentioning the Divemaster-at-18 limit."""
    for lang in ("es", "en"):
        note = elig.age_eligibility_note(age, lang)
        assert "Advanced" in note
        assert "Rescue" in note


# ---------------------------------------------------------------------------
# Age detection in the intent detector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("mi hijo tiene 9 años", [9]),
    ("hay una persona que tiene 14 años", [14]),
    ("un niño de 6, uno de 9 y yo", [6, 9]),
    ("mi hija de 5 años", [5]),
    ("a 6 year old and a 12 year old", [6, 12]),
    ("kids aged 8 and 10", [8, 10]),
    ("tenemos 25 y 30 años", [25, 30]),
    ("familia de 4, un niño de 8 y otro de 5", [5, 8]),   # group-size 4 excluded
    ("dos niños de 8 y 10", [8, 10]),                      # coordinated kid ages
    ("mis hijos de 6, 8 y 11", [6, 8, 11]),
])
def test_age_detection(msg, expected):
    assert _detect(msg).ages == expected


@pytest.mark.parametrize("msg", [
    "mi última inmersión fue hace 2 años",
    "buceé hace 3 años",
    "el paquete es de 2 días",
    "quiero reservar para 4 personas",
])
def test_age_detection_no_false_positives(msg):
    assert _detect(msg).ages == []


# ---------------------------------------------------------------------------
# Deterministic supervisor responder (end-to-end via route_message)
# ---------------------------------------------------------------------------

def _state(lang="es"):
    s = ConversationState(conversation_id="elig-e2e")
    s.language = lang
    s.step = Step.MAIN_MENU
    return s


@pytest.mark.asyncio
async def test_child_9_cannot_full_dive_but_offered_alternatives():
    resp = await route_message(_state(), "mi hijo tiene 9 años, puede bucear?")
    assert "Bubble Makers" in resp
    assert "snorkel" in resp.lower()
    assert "10" in resp            # mentions the dive age threshold
    assert Step.ESCALATE != _state().step


@pytest.mark.asyncio
async def test_child_5_too_young_offered_companion():
    resp = await route_message(_state(), "mi hija de 5 años puede entrar al agua?")
    assert "acompañar" in resp.lower() or "companion" in resp.lower()
    assert "6" in resp             # snorkel-age reference


@pytest.mark.asyncio
async def test_first_person_puedo_with_baby_fires_responder():
    """'¿puedo bucear con mi bebé de 2 años?' (first-person 'puedo') must be
    answered deterministically, not fall through to RAG."""
    resp = await route_message(_state(), "puedo bucear con mi bebé de 2 años?")
    assert "acompañar" in resp.lower()   # 2yo -> companion framing
    assert "6" in resp                    # snorkel-age reference


@pytest.mark.asyncio
async def test_two_kids_different_ages_both_explained():
    resp = await route_message(_state(), "tengo un niño de 8 y otro de 12, qué pueden hacer?")
    assert "8 años" in resp and "12 años" in resp
    assert "Bubble Makers" in resp        # the 8-year-old's option


@pytest.mark.asyncio
async def test_teen_14_can_do_everything_positive():
    resp = await route_message(_state(), "una persona de 14 años puede bucear?")
    assert "Open Water" in resp or "minicurso" in resp.lower()


@pytest.mark.asyncio
async def test_age_eligibility_answer_includes_safety_net():
    """The deterministic eligibility responder covers only the age question;
    if the message packed in something else (discount, cancellation...) not
    addressed by this canned answer, the client must be invited to re-ask
    with detail instead of assuming the answer was complete."""
    resp = await route_message(_state(), "mi hijo tiene 9 años, puede bucear?")
    assert "más concreto" in resp


@pytest.mark.asyncio
async def test_owner_scenario5_family_14_baptism_minimum_age():
    resp = await route_message(
        _state(),
        "voy a hacer buceo con mi familia, hay una persona que tiene 14 años, "
        "queremos hacer un bautismo, hay edad minima?",
    )
    # 14 is old enough for the minicourse/bautismo — positive, not an escalation.
    assert "minicurso" in resp.lower() or "open water" in resp.lower()


@pytest.mark.asyncio
async def test_owner_scenario6a_child_9_options_question():
    resp = await route_message(
        _state(),
        "estoy pensando en hacer buceo estos dias con mi hijo, tiene 9 años, que opciones teneis?",
    )
    assert "Bubble Makers" in resp
    assert "snorkel" in resp.lower()


@pytest.mark.asyncio
async def test_multiturn_age_remembered_for_followup():
    """Owner scenario 6: '...mi hijo, tiene 9 años, qué opciones?' then a bare
    follow-up 'pero mi hijo puede hacer buceo?' must reuse the remembered age."""
    st = _state()
    await route_message(st, "estoy pensando en hacer buceo con mi hijo, tiene 9 años, que opciones teneis?")
    assert st.detected_ages == [9]
    resp = await route_message(st, "pero mi hijo puede hacer buceo?")
    assert "Bubble Makers" in resp        # answered about the 9-year-old
    assert "10" in resp


@pytest.mark.asyncio
async def test_bare_can_dive_without_person_ref_does_not_use_stale_age():
    """A generic '¿puede bucear?' with no person reference and no age must NOT
    be answered from a stale remembered age."""
    from src.agents.supervisor import _maybe_answer_age_eligibility
    st = _state()
    st.detected_ages = [9]
    assert _maybe_answer_age_eligibility("¿se puede bucear de noche?", st) is None


@pytest.mark.asyncio
async def test_plain_booking_with_age_is_not_hijacked():
    """'reservar para mi hijo de 14' has an age but no eligibility QUESTION, so
    the age responder must NOT fire (it should go to the normal flow)."""
    from src.agents.supervisor import _maybe_answer_age_eligibility
    s = _state()
    assert _maybe_answer_age_eligibility("quiero reservar para mi hijo de 14", s) is None


@pytest.mark.asyncio
async def test_eligibility_question_without_age_does_not_fire():
    """'hay edad mínima?' with no concrete age falls through to normal handling."""
    from src.agents.supervisor import _maybe_answer_age_eligibility
    s = _state()
    assert _maybe_answer_age_eligibility("hay edad mínima para bucear?", s) is None


# ---------------------------------------------------------------------------
# Group plan builder (auto-armado): who can do what, in one structured plan
# ---------------------------------------------------------------------------

def _total(plans):
    return sum(p.qty for p in plans)


def test_plan_group_certified_line_and_total():
    plans = elig.plan_group(certified=2, noncert_ages=[9, 14])
    assert _total(plans) == 4
    cert = plans[0]
    assert cert.who == "buzo certificado" and cert.qty == 2
    assert cert.auto == elig.CERTIFIED_DIVING


def test_plan_group_twins_merge_same_age():
    plans = elig.plan_group(certified=0, noncert_ages=[9, 9])
    assert len(plans) == 1
    assert plans[0].qty == 2 and plans[0].who == "9 años"


def test_plan_group_unknown_adults_not_merged_with_minor():
    """A lone 12-year-old must NOT be merged with unknown-age adults even though
    their option sets are identical."""
    plans = elig.plan_group(certified=1, noncert_ages=[12], noncert_unknown=2)
    assert _total(plans) == 4
    twelve = next(p for p in plans if p.who == "12 años")
    adults = next(p for p in plans if p.who == "sin certificar")
    assert twelve.qty == 1 and adults.qty == 2


def test_plan_group_under_six_is_companion_auto():
    plans = elig.plan_group(certified=1, noncert_ages=[3])
    three = next(p for p in plans if p.who == "3 años")
    assert three.options == [elig.COMPANION]
    assert three.auto == elig.COMPANION


@pytest.mark.parametrize("age,expected_first_option", [
    (5, elig.COMPANION),
    (6, elig.SNORKEL),
    (7, elig.SNORKEL),
    (8, elig.BUBBLE_MAKERS),
    (9, elig.BUBBLE_MAKERS),
    (10, elig.MINICOURSE),
    (14, elig.MINICOURSE),
])
def test_beginner_options_first_by_age(age, expected_first_option):
    assert elig.beginner_options_for_age(age)[0] == expected_first_option


def test_beginner_options_unknown_is_adult():
    assert elig.beginner_options_for_age(None) == [elig.MINICOURSE, elig.SNORKEL, elig.COMPANION]


def test_plan_group_preserves_headcount_complex():
    # 1 cert + ages 5,7,8,12 + 2 unknown adults = 7 people
    plans = elig.plan_group(certified=1, noncert_ages=[5, 7, 8, 12], noncert_unknown=2)
    assert _total(plans) == 7


def test_format_group_plan_is_readable_and_positive():
    plans = elig.plan_group(certified=2, noncert_ages=[9, 14])
    text = elig.format_group_plan(plans, "es")
    assert "buzo certificado" in text
    assert "9 años" in text and "14 años" in text
    assert "Bubble Makers" in text        # the 9-year-old
    assert "minicurso" in text            # the 14-year-old


@pytest.mark.asyncio
async def test_group_responder_uses_per_person_plan_for_multiple_ages():
    st = _state()
    resp = await route_message(st, "tengo un niño de 8 y otro de 12, qué pueden hacer?")
    assert "8 años" in resp and "12 años" in resp
    assert "Bubble Makers" in resp


# ---------------------------------------------------------------------------
# Lead note surfaces mentioned ages (so the advisor sees minors)
# ---------------------------------------------------------------------------

def test_lead_note_surfaces_minor_ages():
    from src.agents.lead_summary import build_lead_summary
    st = ConversationState(conversation_id="ln")
    st.language = "es"
    st.detected_ages = [9, 30]
    note = build_lead_summary(st, escalation_reason="prueba")
    assert "Edades mencionadas" in note
    assert "9" in note
    assert "menor" in note.lower()   # the 9-year-old flagged


def test_lead_note_no_ages_line_when_none():
    from src.agents.lead_summary import build_lead_summary
    st = ConversationState(conversation_id="ln2")
    st.language = "es"
    note = build_lead_summary(st, escalation_reason="prueba")
    assert "Edades mencionadas" not in note
