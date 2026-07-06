"""Intent-detector robustness regressions found auditing typos / ES-EN mix /
negations / multi-intent messages."""

import pytest

from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState


det = IntentDetector()


def _d(msg: str):
    return det.detect(msg, ConversationState(conversation_id="rob"))


# --- Negations --------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "no soy certificado todavía",
    "no somos certificados",
    "no es certificado mi acompañante",
    "todavía no soy certificada",
])
def test_no_soy_certificado_is_not_certified(msg):
    assert _d(msg).is_certified is False


@pytest.mark.parametrize("msg", [
    "no quiero bucear, solo snorkel",
    "solo quiero snorkel para mi familia",
    "solamente snorkel por favor",
    "just snorkel, no diving",
    "only snorkel please",
])
def test_only_snorkel_resolves_to_snorkel_not_diving(msg):
    assert _d(msg).activity == "snorkel"


# --- Certified detection still works (no over-correction) --------------------

@pytest.mark.parametrize("msg,expected", [
    ("somos 2 buzos certificados", True),
    ("soy buzo certificado con open water", True),
])
def test_certified_positive_still_detected(msg, expected):
    assert _d(msg).is_certified is expected


def test_nunca_hemos_buceado_still_beginner():
    i = _d("nunca hemos buceado")
    assert i.activity == "minicourse" and i.is_certified is False


# --- English age phrasings --------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("quiero snorkel for my kids ages 8 and 10", [8, 10]),
    ("my children aged 6 and 12", [6, 12]),
    ("a 5 year old and a 9 year old", [5, 9]),
])
def test_english_age_phrasings(msg, expected):
    assert _d(msg).ages == expected


# --- Mixed ES/EN headcount / certification ----------------------------------

def test_mixed_language_group_and_cert():
    i = _d("hi, somos 3 personas certified divers")
    assert i.group_size == 3
    assert i.is_certified is True
