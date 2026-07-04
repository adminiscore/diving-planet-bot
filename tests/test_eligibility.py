"""Age & certification eligibility: rules, age detection, and the deterministic
supervisor responder that informs what each person can/can't do."""

import pytest
from unittest.mock import AsyncMock

from src.flows import eligibility as elig
from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState, Step
from src.agents.supervisor import route_message


detector = IntentDetector()


@pytest.fixture(autouse=True)
def _no_llm_language_fallback(monkeypatch):
    monkeypatch.setattr(
        "src.agents.supervisor.detect_language_llm",
        AsyncMock(return_value=None),
    )


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
])
def test_age_note_mentions_right_activity_es(age, must_include):
    note = elig.age_eligibility_note(age, "es")
    assert must_include.lower() in note.lower()


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
async def test_teen_14_can_do_everything_positive():
    resp = await route_message(_state(), "una persona de 14 años puede bucear?")
    assert "Open Water" in resp or "minicurso" in resp.lower()


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
