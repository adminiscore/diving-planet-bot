"""Intent-detector robustness regressions found auditing typos / ES-EN mix /
negations / multi-intent messages."""

import pytest

from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState, Step


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


# --- "para mí" / solo self → 1 person ---------------------------------------

@pytest.mark.parametrize("msg", [
    "Quiero el minicurso para mi, no se bucear, desde cartagena, soy colombiano",
    "Quiero el curso open water para mi, extranjero",
    "solo yo",
    "just me, open water course",
    "para mi, tengo 30 años",
])
def test_solo_self_means_one_person(msg):
    assert _d(msg).group_size == 1


@pytest.mark.parametrize("msg", [
    "para mi y mi novia",
    "para mi esposo y yo",
    "quiero 2 inmersiones para mi",   # other number present -> stay conservative
    "para mi familia",
])
def test_solo_self_not_triggered_with_companions_or_numbers(msg):
    assert _d(msg).group_size is None


# --- Explicit certified dive-count detection --------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("quiero 2 inmersiones saliendo de cartagena", 2),
    ("somos 2 buzos certificados, el paquete de 2 buceos", 2),
    ("we are 2 certified divers, 2-dive package", 2),
    ("dos inmersiones", 2),
    ("estoy en cocoliso, soy certificado, quiero 2 buceos", 2),
    ("paquete de 5 buceos", 5),
    ("7 buceos en 3 dias", 7),
    ("quiero 9 inmersiones", 9),
])
def test_cert_dive_count_detected(msg, expected):
    assert _d(msg).cert_dives == expected


@pytest.mark.parametrize("msg", [
    "soy open water desde hace 2 años",       # timeframe, not a dive count
    "mi ultima inmersion fue hace 2 años",    # ditto
    "somos 2 y queremos bucear",              # 2 is group size; 'bucear' is a verb
    "reservar para 4 personas",               # people, not dives
])
def test_cert_dive_count_no_false_positive(msg):
    assert _d(msg).cert_dives is None


def test_explicit_two_dives_skips_cert_plan_question():
    """A certified request that already names the 2-dive plan must NOT re-ask
    '¿qué plan?' — it should advance to the last-dive safety question."""
    from src.agents.supervisor import _route_detected_intent
    st = ConversationState(conversation_id="2dive"); st.language = "es"
    intent = _d("somos 2 buzos certificados, quiero 2 inmersiones, desde cartagena")
    _route_detected_intent(intent, st, "somos 2 buzos certificados, quiero 2 inmersiones, desde cartagena")
    assert st.step != Step.MIXED_ADD_CERT_PLAN
    assert st.step == Step.MIXED_CERT_LAST_DIVE


def test_five_dives_resolves_exact_plan_with_lodging_note():
    """An explicit, unambiguous multi-day count must NOT re-ask "which plan" —
    the overnight requirement is still shown, but only as a short note for the
    exact plan, and the flow advances (it doesn't loop back to the menu)."""
    from src.agents.supervisor import _route_detected_intent
    st = ConversationState(conversation_id="5dive"); st.language = "es"
    intent = _d("somos 2 buzos certificados, paquete de 5 buceos, desde cartagena")
    resp = _route_detected_intent(intent, st, "somos 2 buzos certificados, paquete de 5 buceos, desde cartagena")
    assert st.step == Step.MIXED_CERT_LAST_DIVE
    assert st.mixed_pending_qty_plan == "5_dives_2_days"
    assert "noche" in resp.lower()


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


# --- Ages written without the enye ("9 anos") --------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("Somos gemelos de 9 años", [9]),
    ("Somos gemelos de 9 anos", [9]),          # common no-tilde typo
    ("mi hijo tiene 9 anos", [9]),
    ("hijos de 5, 8, 11 y 15 anos", [5, 8, 11, 15]),
])
def test_ages_detected_without_tilde(msg, expected):
    assert _d(msg).ages == expected


def test_last_dive_years_not_an_age_without_tilde():
    # "hace 5 anos" is a last-dive timeframe, not a person age.
    intent = _d("soy open water desde hace 5 anos")
    assert 5 not in (intent.ages or [])


@pytest.mark.parametrize("msg,expected", [
    ("y mi hijo, tiene 12", [12]),
    ("mi hija tiene 9", [9]),
    ("y mi otro hijo, tiene 7", [7]),
])
def test_kid_noun_tiene_age(msg, expected):
    assert _d(msg).ages == expected


# --- Mixed-group split with a count phrase inserted mid-sentence ------------
# Regression: "somos 5, 3 buceamos certificados 5 inmersiones y 2 hacen
# snorkel" used to produce NO group_allocation (the injected dive-count broke
# the split-pattern's adjacency requirement), silently dropping the 2
# snorkelers when it fell through to the certified-only path downstream.

@pytest.mark.parametrize("msg,expected", [
    ("somos 5, 3 buceamos certificados 5 inmersiones y 2 hacen snorkel", {"certified_diving": 3, "snorkel": 2}),
    ("3 buceamos certificados y 2 hacen snorkel, queremos 5 inmersiones", {"certified_diving": 3, "snorkel": 2}),
    ("somos 5, 3 bucean 2 dias y 2 hacen snorkel", {"certified_diving": 3, "snorkel": 2}),
    ("we are 5, 3 diving 3 dives and 2 snorkel", {"certified_diving": 3, "snorkel": 2}),
    ("3 de buceo certificado 7 inmersiones y 2 de snorkel", {"certified_diving": 3, "snorkel": 2}),
])
def test_group_split_survives_injected_count_phrase(msg, expected):
    assert _d(msg).group_allocation == expected
