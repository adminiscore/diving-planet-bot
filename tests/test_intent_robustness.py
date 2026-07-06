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


# --- Group composition / auto-build understanding ---------------------------

@pytest.mark.parametrize("msg", [
    "los dos buzos",
    "somos buzos",
    "reservar para mi pareja y yo, los dos buzos",
    "vamos 3 buzos a las islas",
    "soy buza",
])
def test_bare_buzos_means_certified_diving(msg):
    i = _d(msg)
    assert i.activity == "certified_diving"
    assert i.is_certified is True


@pytest.mark.parametrize("msg", [
    "no somos buzos",
    "quiero ser buzo",
    "queremos hacernos buzos",
])
def test_wanting_to_become_or_not_being_a_diver_is_not_certified(msg):
    assert _d(msg).is_certified is False


def test_verb_form_activity_split():
    """'3 bucean y 2 hacen snorkel' -> allocation, not all-diving."""
    i = _d("somos 5, 3 bucean y 2 hacen snorkel")
    assert i.group_allocation == {"certified_diving": 3, "snorkel": 2}
    assert i.group_size == 5


def test_open_water_and_sin_certificar_is_cert_split():
    """'dos con open water y uno sin certificar' -> 2 certified + 1 beginner."""
    i = _d("somos 3, dos con open water y uno sin certificar")
    assert i.group_allocation == {"certified_diving": 2, "minicourse": 1}


def test_somos_dos_queremos_bucear_asks_cert_not_lost():
    """'somos dos y queremos bucear' -> diving intent for 2 (cert unknown)."""
    i = _d("somos dos y queremos bucear")
    assert i.activity == "certified_diving"
    assert i.group_size == 2
    assert i.is_certified is None


def test_plural_certificados_in_verb_split():
    """'3 buceamos certificados y 2 hacen snorkel' -> the plural 'certificados'
    between the activity verb and 'y' must not break the numeric split."""
    i = _d("somos 5, 3 buceamos certificados y 2 hacen snorkel")
    assert i.group_allocation == {"certified_diving": 3, "snorkel": 2}
