"""Mid-flow group recomposition: adding people / restating the group size via
free text inside the booking flow must be captured (not answered with
'no te entendí')."""

import pytest

from src.agents.supervisor import _apply_group_recomposition, _GROUP_RECOMPOSE_RE, _strip_accents
from src.flows.decision_tree import ConversationState


def _state(size=2, ages=None):
    st = ConversationState(conversation_id="recompose")
    st.language = "es"
    st.detected_group_size = size
    st.detected_ages = list(ages or [])
    return st


# --- Detector: what should / should not look like a recomposition -----------

@pytest.mark.parametrize("msg", [
    "y mi hijo de 12",
    "y mi otra hija de 7",
    "ah se suma mi hermano, ya seríamos 3",
    "también viene mi esposa",
    "ahora somos 4",
    "se nos suma mi prima",
    "y otro amigo",
])
def test_recompose_regex_fires(msg):
    assert _GROUP_RECOMPOSE_RE.search(_strip_accents(msg)) is not None


@pytest.mark.parametrize("msg", [
    "somos 3",           # a normal count answer, not a change
    "y desde cartagena",  # location answer starting with 'y'
    "quiero el paquete de 5",
    "2 inmersiones",
    "cartagena",
    "ya me voy",
])
def test_recompose_regex_does_not_fire(msg):
    assert _GROUP_RECOMPOSE_RE.search(_strip_accents(msg)) is None


# --- Apply: updates size / ages and acknowledges ----------------------------

def test_recompose_new_total():
    st = _state(size=2)
    ack = _apply_group_recomposition("ah se suma mi hermano, ya seríamos 3", st)
    assert ack is not None
    assert st.detected_group_size == 3
    assert "3" in ack


def test_recompose_adds_person_with_age():
    st = _state(size=2)
    ack = _apply_group_recomposition("y mi hijo de 12", st)
    assert ack is not None
    assert st.detected_group_size == 3
    assert st.detected_ages == [12]


def test_recompose_person_without_age_increments():
    st = _state(size=2)
    ack = _apply_group_recomposition("también viene mi esposa", st)
    assert ack is not None
    assert st.detected_group_size == 3


def test_recompose_from_unknown_size_assumes_speaker():
    st = _state(size=None)
    ack = _apply_group_recomposition("y mi esposa", st)
    assert ack is not None
    assert st.detected_group_size == 2   # speaker (1) + added (1)


def test_non_recomposition_returns_none():
    st = _state(size=2)
    assert _apply_group_recomposition("somos 3", st) is None
    assert _apply_group_recomposition("cartagena", st) is None
    assert st.detected_group_size == 2   # unchanged
