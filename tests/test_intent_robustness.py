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


# --- Generic "las islas" location (no specific island/hotel named) ---------

@pytest.mark.parametrize("msg", [
    "vamos desde las islas",
    "ya estoy en las islas",
    "estamos en la isla",
    "salimos desde la isla",
])
def test_generic_islands_phrase_sets_island_location(msg):
    """Regression (found live on PRE, 2026-07-09): a customer saying they're
    on/from "las islas" without naming a specific island/hotel never set
    intent.location — the bot kept re-asking '¿desde dónde sales?' even after
    the customer had just answered it in the same message."""
    assert _d(msg).location == "island"


def test_screenshot_message_detects_island_location():
    """Exact message from the PRE bug report."""
    i = _d("Hola queremos bucear somos 5 certificados y queremos el paqiete de 7, vamos desde las islas")
    assert i.location == "island"
    assert i.activity == "certified_diving"
    assert i.is_certified is True
    assert i.group_size == 5


@pytest.mark.parametrize("msg", [
    "we are going from the islands",
    "we are already on the islands",
    "I am on the island",
    "we come from the islands",
    "leaving from the islands",
])
def test_generic_islands_phrase_sets_island_location_english(msg):
    """Same gap as the Spanish regression above, confirmed to affect the
    English phrasing too."""
    assert _d(msg).location == "island"


# --- Real-world nicknames for Cartagena / the islands (found via web search,
# 2026-07-09) ------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "salimos de la heroica",
    "estamos en el corralito de piedra",
    "venimos de la ciudad redentora",
    "cartagena de indias",
    "salimos de la ciudad amurallada",
    "estamos en el centro amurallado",
])
def test_cartagena_nicknames_set_cartagena_location(msg):
    """"La Heroica" (title Simón Bolívar gave the city after the 1815 Siege of
    Morillo), "Corralito de Piedra" (its colonial stone walls), "Ciudad
    Redentora", and "Ciudad Amurallada" (its historic walled center — the
    Spanish equivalent of "the Walled City") are real, commonly used
    nicknames for Cartagena — none were recognized before."""
    assert _d(msg).location == "cartagena"


def test_los_rosarios_informal_plural_sets_island_location():
    """"Los rosarios" is a common informal way to refer to the whole Rosario
    Islands archipelago, distinct from a specific island."""
    assert _d("vamos a los rosarios").location == "island"


@pytest.mark.parametrize("msg", [
    "rezar el rosario todos los dias",
    "voy a la iglesia a rezar el rosario",
])
def test_praying_the_rosary_does_not_trigger_island_location(msg):
    """Regression: bare "rosario" matching the island pre-dates this session
    and already collided with "rezar el rosario" (the Catholic prayer, a
    common phrase in Colombia) — found while auditing location nicknames."""
    assert _d(msg).location is None


@pytest.mark.parametrize("msg", [
    "we leave from the walled city",
    "we are in the heroic city",
    "cartagena is the queen of the caribbean",
])
def test_cartagena_nicknames_english(msg):
    """English equivalents of the Spanish nicknames above — "the Heroic
    City"/"the Walled City"/"Queen of the Caribbean" are real, commonly used
    English-language nicknames for Cartagena."""
    assert _d(msg).location == "cartagena"


@pytest.mark.parametrize("msg", [
    "coming from the rosarios",
    "we are at the rosarios",
])
def test_the_rosarios_english_sets_island_location(msg):
    """English equivalent of "los rosarios" — confirmed in use by English-
    language tour sites."""
    assert _d(msg).location == "island"


def test_praying_the_rosary_english_does_not_trigger_island_location():
    assert _d("I pray the rosary every day").location is None


# --- Holding a PADI certification level => certified diver -------------------

@pytest.mark.parametrize("msg", [
    "soy open water",
    "tengo el open water",
    "soy advanced",
    "tengo el advanced",
    "soy rescue diver",
    "soy divemaster",
    "i am open water",
    "i have my advanced",
    "tengo nitrox",
    "soy aguas abiertas",
    "estoy certificado en open water",
    "hola soy open water y quiero hacer dos inmersiones",
    "somos advanced y queremos 2 inmersiones",
])
def test_holding_padi_level_is_certified(msg):
    assert _d(msg).is_certified is True


@pytest.mark.parametrize("msg", [
    "quiero el curso open water",
    "quiero sacarme el advanced",
    "quiero hacer el rescue",
    "quiero certificarme",
    "curso de open water",
    "quiero el advanced",
    "me interesa el divemaster",
])
def test_wanting_a_course_is_not_certified(msg):
    # Wanting to TAKE a course != holding the certification.
    assert _d(msg).is_certified is not True


def test_holding_openwater_is_not_the_course_activity():
    """"soy open water" is a certified diver wanting fun dives, not someone
    taking the Open Water course."""
    i = _d("soy open water")
    assert i.is_certified is True
    assert i.activity != "padi_open_water"


# --- Group size from "N divers" / "N certified" ------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("2 certified divers", 2),
    ("3 divers from cartagena", 3),
    ("somos 3 buzos", 3),
    ("3 buceadores", 3),
    ("4 certificados", 4),
    ("2 certified divers, 2 dives, we dived last month", 2),
])
def test_group_size_from_divers_or_certified(msg, expected):
    assert _d(msg).group_size == expected


# --- Nationality captured from the message (COP vs USD, don't re-ask) ---------

@pytest.mark.parametrize("msg,expected", [
    ("somos colombianos", True),
    ("soy colombiano", True),
    ("i am colombian", True),
    ("resident in colombia", True),
    ("soy de colombia", True),
    ("we are foreigners", False),
    ("somos extranjeros", False),
    ("no soy colombiano", False),
    ("not colombian, from spain", False),
])
def test_nationality_detected(msg, expected):
    assert _d(msg).is_colombian is expected


@pytest.mark.parametrize("msg", [
    "quiero bucear",
    "las mejores islas de colombia",   # country name, not a nationality claim
])
def test_nationality_not_falsely_detected(msg):
    assert _d(msg).is_colombian is None


# --- Info retention: last-dive stated in the message --------------------------

@pytest.mark.parametrize("msg,expected", [
    ("somos 2 buzos certificados, buceamos hace un mes", False),
    ("buceamos hace 6 meses", False),
    ("no hace mas de 2 anos que buceamos", False),
    ("we dived recently", False),
    ("dived last month", False),
    ("llevo 5 anos sin bucear", True),
    ("hace mas de 3 anos que no buceo", True),
    ("mi ultima inmersion fue hace 3 anos", True),
    ("buceamos hace 2 anos", True),
    ("buceo hace 18 meses", False),
])
def test_last_dive_captured_from_message(msg, expected):
    assert _d(msg).last_dive_over_2_years is expected


@pytest.mark.parametrize("msg", [
    "soy certificado",              # no last-dive info
    "reserve hace un mes",          # not a diving context
    "quiero bucear 2 dias",
])
def test_last_dive_not_falsely_detected(msg):
    assert _d(msg).last_dive_over_2_years is None


def test_recent_dive_skips_last_dive_question_end_to_end():
    """A fully-specified cert booking that states a recent last dive must NOT be
    re-asked the '¿más de 2 años?' question — it goes straight to the preview."""
    from src.agents.supervisor import _route_detected_intent
    st = ConversationState(conversation_id="ret"); st.language = "es"
    msg = "somos 2 buzos certificados, 2 inmersiones, desde cartagena, buceamos hace un mes"
    _route_detected_intent(_d(msg), st, msg)
    assert st.step != Step.MIXED_CERT_LAST_DIVE
    assert st.step == Step.MIXED_ADD_PREVIEW


# --- Info retention: "N persona" singular counts as group size ---------------

@pytest.mark.parametrize("msg,expected", [
    ("quiero el minicurso para 1 persona", 1),
    ("snorkel para 2 persona", 2),
    ("just 1 person", 1),
])
def test_singular_persona_counts_as_group_size(msg, expected):
    assert _d(msg).group_size == expected


# --- Under-10 kids can't be certified (safe split) --------------------------

def test_under_10_kids_split_out_of_certified_group():
    """'familia de 5: papá y mamá certificados, 3 niños de 6, 9 y 13' — the 6- and
    9-year-olds cannot hold a certification (OW min age 10), so they become
    beginners; the 13yo (who CAN be certified) stays in the cert count."""
    i = _d("familia de 5: papa y mama certificados, 3 ninos de 6, 9 y 13, desde cartagena")
    assert i.group_allocation == {"certified_diving": 3, "minicourse": 2}


def test_single_under_10_kid_split_from_certified_pair():
    i = _d("somos 2 buzos certificados y mi hijo de 6")
    assert i.group_allocation == {"certified_diving": 1, "minicourse": 1}


@pytest.mark.parametrize("msg", [
    "somos 3 buzos certificados",                       # no ages at all
    "somos 4 certificados, dos adolescentes de 14 y 16",  # teens CAN be certified
    "somos 3 certificados de 25, 30 y 35",              # adults
    "soy buzo certificado, tengo 30 años",              # single adult
])
def test_no_kid_split_when_no_under_10_age(msg):
    assert _d(msg).group_allocation is None


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


# --- Bare "paquete/pack/plan de N" with no unit word at all -----------------
# Regression: found live on PRE (2026-07-09) — "queremos bucear el pack de 5"
# never resolved a dive count (no "inmersiones"/"buceos" after the 5), so the
# bot forgot the "5" the customer had just given and re-asked which plan.

@pytest.mark.parametrize("msg,expected", [
    ("el pack de 5", 5),
    ("el paquete de 5", 5),
    ("queremos bucear el pack de 7", 7),
    ("el paquete de 9", 9),
    ("the pack of 7", 7),
    ("the package of five", 5),
])
def test_bare_package_number_resolves_unambiguous_dive_count(msg, expected):
    """5/7/9 are never valid as a day-count (max day package is 4 days), so a
    bare number with no unit word is still unambiguous."""
    assert _d(msg).cert_dives == expected


@pytest.mark.parametrize("msg", [
    "el pack de 2",
    "el pack de 3",
    "el pack de 4",
])
def test_bare_package_number_stays_conservative_when_ambiguous(msg):
    """2/3/4 are valid as EITHER a dive count or a day count (e.g. "el pack de
    3" could mean 3 dives, or 3 days = 7 dives) — must NOT guess."""
    i = _d(msg)
    assert i.cert_dives is None
    assert i.cert_days is None


def test_bare_package_number_does_not_hijack_explicit_day_count():
    """"paquete de 3 dias" must still resolve as a DAY count (3), not get
    stolen by the new bare-dive fallback matching just "paquete de 3"."""
    i = _d("el paquete de 3 dias")
    assert i.cert_dives is None
    assert i.cert_days == 3


def test_pack_qualifier_recognized_for_day_count():
    """"pack" was missing entirely from the day-count qualifier word list
    (only "paquete"/"plan" were recognized) — found in the same audit."""
    assert _d("el pack de 3 dias").cert_days == 3
    assert _d("el pack de 2 dias").cert_days == 2


@pytest.mark.asyncio
async def test_bare_pack_de_5_full_flow_resolves_plan():
    """Exact scenario reported live: group + cert + bare pack number in one
    message, location given on the next turn — must resolve the exact plan
    without re-asking "which idea"."""
    from src.flows.decision_tree import ConversationState as _CS, Step as _Step
    from src.agents.supervisor import route_message

    state = _CS(conversation_id="pack-de-5-e2e")
    await route_message(
        state, "Hola somos una pareja de dos certificados, queremos bucear el pack de 5"
    )
    assert state.step == _Step.MIXED_LOCATION

    resp = await route_message(state, "Salgo desde Cartagena")
    assert state.step == _Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.mixed_pending_cert_total_qty == 2


# --- Exhaustive audit: bare "pack/paquete de N" for every N 1-10, digit and
# word form, ES and EN (2026-07-09). Only 5/7/9 are unambiguous package sizes
# (never valid as a day-count too) — everything else must stay None and let
# the flow ask instead of guessing.

_BARE_PACK_ES_WORDS = {
    1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
    6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez",
}
_BARE_PACK_EN_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}
_UNAMBIGUOUS_BARE_PACK = {5, 7, 9}


@pytest.mark.parametrize("n", range(1, 11))
def test_bare_pack_es_digit_all_numbers(n):
    expected = n if n in _UNAMBIGUOUS_BARE_PACK else None
    assert _d(f"el pack de {n}").cert_dives == expected


@pytest.mark.parametrize("n", range(1, 11))
def test_bare_pack_es_word_all_numbers(n):
    expected = n if n in _UNAMBIGUOUS_BARE_PACK else None
    assert _d(f"el pack de {_BARE_PACK_ES_WORDS[n]}").cert_dives == expected


@pytest.mark.parametrize("n", range(1, 11))
def test_bare_pack_en_digit_all_numbers(n):
    expected = n if n in _UNAMBIGUOUS_BARE_PACK else None
    assert _d(f"the pack of {n}").cert_dives == expected


@pytest.mark.parametrize("n", range(1, 11))
def test_bare_pack_en_word_all_numbers(n):
    expected = n if n in _UNAMBIGUOUS_BARE_PACK else None
    assert _d(f"the pack of {_BARE_PACK_EN_WORDS[n]}").cert_dives == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("n", range(1, 11))
async def test_bare_pack_es_full_flow_all_numbers(n):
    """End-to-end: for 5/7/9 the plan resolves without re-asking; for
    everything else the flow safely falls back to the generic cert-plan
    question (never silently books the wrong plan)."""
    from src.flows.decision_tree import ConversationState as _CS, Step as _Step
    from src.agents.supervisor import route_message

    state = _CS(conversation_id=f"bare-pack-es-{n}")
    resp = await route_message(
        state, f"somos 2 certificados, queremos bucear el pack de {n}, desde cartagena"
    )
    if n in _UNAMBIGUOUS_BARE_PACK:
        assert state.step == _Step.MIXED_CERT_LAST_DIVE, (n, resp)
        assert state.mixed_pending_qty_plan == f"{n}_dives_{ {5: 2, 7: 3, 9: 4}[n] }_days"
    else:
        # Non-5/7/9 "pack of N" isn't a real package: we recommend the 2-dive
        # plan (owner decision 2026-07-20) instead of a menu. Group size (2) is
        # known, so it advances to the last-dive safety question.
        assert state.step == _Step.MIXED_CERT_LAST_DIVE, (n, resp)
        assert state.mixed_pending_qty_plan == "2_dives_1_day"


@pytest.mark.asyncio
@pytest.mark.parametrize("n", range(1, 11))
async def test_bare_pack_en_full_flow_all_numbers(n):
    from src.flows.decision_tree import ConversationState as _CS, Step as _Step
    from src.agents.supervisor import route_message

    state = _CS(conversation_id=f"bare-pack-en-{n}")
    resp = await route_message(
        state,
        f"we are 2 certified divers, we want to dive the pack of {n}, from cartagena",
    )
    if n in _UNAMBIGUOUS_BARE_PACK:
        assert state.step == _Step.MIXED_CERT_LAST_DIVE, (n, resp)
        assert state.mixed_pending_qty_plan == f"{n}_dives_{ {5: 2, 7: 3, 9: 4}[n] }_days"
    else:
        # See ES twin: non-5/7/9 now recommends the 2-dive plan.
        assert state.step == _Step.MIXED_CERT_LAST_DIVE, (n, resp)
        assert state.mixed_pending_qty_plan == "2_dives_1_day"


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


# --- Fase 7: 3 bugs reales de regex hallados por las baterías (2026-07-21/22)
# Decisión documentada en docs/robustness/plan.md §Fase 7: estos casos eran
# patrones concretos y deterministas → se arregla el REGEX (no un override LLM
# no-determinista). El eval-set los tenía registrados como regresión permanente.

@pytest.mark.parametrize("msg,expected", [
    # el hablante es ADICIONAL al conteo de acompañantes
    ("me plus 3 friends, ppl wanna try diving first time", 4),
    ("me plus 3 friends want to snorkel", 4),
    ("vienen 3 amigos conmigo, queremos bucear", 4),
    ("3 amigos y yo queremos hacer snorkel", 4),
    ("voy con 2 amigos a bucear", 3),
    # controles: los totales explícitos NO se incrementan
    ("somos 4, mi novia y yo buceamos", 4),
    ("we are 3 people", 3),
    ("4 friends want to dive", 4),
])
def test_speaker_additional_to_companion_count(msg, expected):
    assert _d(msg).group_size == expected


@pytest.mark.parametrize("msg", [
    "hace como 3 años que no buceo, seré yo solo",
    "i'm certified but haven't dived in like 4 years",
    "i dived 5 years ago in thailand",
    "llevo 4 años sin bucear",
])
def test_timeframe_years_are_not_ages(msg):
    """'hace X años'/'in like X years'/'X years ago' son marcos temporales de
    la última inmersión, no edades de personas — capturarlos como edad metía
    un niño fantasma en el split del checkout."""
    assert _d(msg).ages == []


@pytest.mark.parametrize("msg,expected", [
    ("mi hijo de 8 años quiere snorkel", [8]),
    ("kids aged 8 and 10", [8, 10]),
    ("my kids are 6 and 12 years old", [6, 12]),
])
def test_real_ages_still_detected(msg, expected):
    assert _d(msg).ages == expected


def test_already_have_card_is_certified_not_course():
    """'i already have my open water card, want to do more dives' clasificaba
    como CURSO Open Water a quien ya lo tiene y quiere bucear."""
    it = _d("i already have my open water card, want to do more dives")
    assert it.is_certified is True
    assert it.activity == "certified_diving"


def test_we_already_have_advanced_is_certified():
    it = _d("we already have the advanced, want to dive tomorrow")
    assert it.is_certified is True
    assert it.activity != "padi_advanced"
