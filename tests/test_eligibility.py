"""Age & certification eligibility: rules and age detection. (El responder determinista de edades del supervisor y
el plan de grupo `plan_group`/`format_group_plan` se fueron el 27-oct, CALN2-04: lo contesta el flujo normal con
`age_eligibility_note` y `beginner_options_for_age`; banco docs/robustness/caln/banco-edades.json.)
lat-11 T6d (26-oct): las edades con `lectura_del_turno` (IntentDetector.detect se quitó; las edades las sigue leyendo
este lector)."""

import pytest

from src.agents.intent_detector import lectura_del_turno
from src.flows import eligibility as elig
from src.flows.state import ConversationState


def _detect(msg: str):
    return lectura_del_turno(msg)


# ---------------------------------------------------------------------------
# Eligibility rules (single source of truth)
# sim-8 (26-oct): `activities_for_age` y `can_*` no tenían llamador; las reglas de edad que se usan son
# `beginner_options_for_age` y `age_eligibility_note`.
# ---------------------------------------------------------------------------

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
# Opciones de quien empieza, por edad (las usa la recomendación por edad de CALN-2 3c)
# ---------------------------------------------------------------------------

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
