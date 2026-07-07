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


# --- Bubble Makers is a kids beginner activity (not certified diving) --------

@pytest.mark.parametrize("msg", [
    "quiero saber del bubble makers",
    "bubble makers para mi hijo de 9",
    "cuentame del bubblemaker",
    "el bubble maker",
])
def test_bubble_makers_is_minicourse_not_certified(msg):
    i = _d(msg)
    assert i.activity == "minicourse"
    assert i.is_certified is False


# --- Latest concrete activity wins (customer changes their mind) -------------

def _apply_seq(msgs):
    from src.agents.supervisor import _apply_detected_intent
    st = ConversationState(conversation_id="seq"); st.language = "es"
    for m in msgs:
        _apply_detected_intent(_d(m), st)
    return st


def test_activity_updates_when_customer_switches_to_minicourse():
    """After 'quiero bucear' (certified) then 'mejor un minicurso', the stored
    activity must follow the latest intent — else clicking Reservar routes a
    beginner into the certified flow (the Bubble Makers bug)."""
    st = _apply_seq(["quiero bucear", "mejor un minicurso para el niño"])
    assert st.detected_activity == "minicourse"
    assert st.detected_is_certified is False


def test_activity_updates_bucear_then_bubble_makers():
    st = _apply_seq(["quiero bucear", "cuentame del bubble makers"])
    assert st.detected_activity == "minicourse"


def test_activity_stays_certified_when_no_new_activity():
    st = _apply_seq(["somos 2 buzos certificados", "y cuanto cuesta?"])
    assert st.detected_activity == "certified_diving"
    assert st.detected_is_certified is True


# --- Language: Spanish question with an English activity name ---------------

@pytest.mark.parametrize("msg", [
    "¿qué es el Mindful Diving?",
    "que es el open water",
    "¿cómo funciona el discover scuba?",
])
def test_spanish_question_with_english_term_stays_spanish(msg):
    assert _d(msg).language == "es"


@pytest.mark.parametrize("msg", [
    "cuentame del fun dive",   # tie (del vs dive) -> None, must NOT flip to English
    "el diving",
])
def test_ambiguous_spanish_never_flips_to_english(msg):
    assert _d(msg).language != "en"


@pytest.mark.parametrize("msg", [
    "how much is diving",
    "i want to dive",
    "what is the mindful diving course",
    "hello, how much is snorkeling",
])
def test_english_messages_still_english(msg):
    assert _d(msg).language == "en"


# --- English family / kids-age extraction -----------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("we are a family of 4", 4),
    ("a family of 5 wants to dive", 5),
    ("family of three, all certified", 3),
])
def test_english_family_of_n_group_size(msg, expected):
    assert _d(msg).group_size == expected


@pytest.mark.parametrize("msg,expected", [
    ("our kids are 7 and 11", [7, 11]),
    ("the children are 6 and 9", [6, 9]),
    ("we are a family of 4, kids are 7 and 11, staying at pao pao", [7, 11]),
])
def test_english_kids_are_ages(msg, expected):
    assert _d(msg).ages == expected
