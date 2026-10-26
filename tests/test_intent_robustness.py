"""Intent-detector robustness regressions found auditing typos / ES-EN mix /
negations / multi-intent messages.
lat-11 T6d (26-oct): fuera los tests de IntentDetector.detect (actividad, certificacion, grupo, reparto, ultima
inmersion, nacionalidad e idioma; la clase se quito y esos campos los decide el extractor). Las edades, el lugar y la
cifra de inmersiones o de dias se leen con `lectura_del_turno`."""

import copy

import pytest

from src.agents.intent_detector import DetectedIntent, lectura_del_turno
from src.flows.state import ConversationState


def _d(msg: str):
    return lectura_del_turno(msg)


# --- English age phrasings --------------------------------------------------

@pytest.mark.parametrize("msg,expected", [
    ("quiero snorkel for my kids ages 8 and 10", [8, 10]),
    ("my children aged 6 and 12", [6, 12]),
    ("a 5 year old and a 9 year old", [5, 9]),
])
def test_english_age_phrasings(msg, expected):
    assert _d(msg).ages == expected


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


# --- Latest concrete activity wins (customer changes their mind) -------------

# Lo que leia el regex de cada mensaje (IntentDetector.detect, quitado en lat-11 T6d).
_LECTURAS = {
    "quiero bucear": DetectedIntent(
        language="es", activity="certified_diving", service_id="2_dives_1_day",
        detected_fields=["language", "activity"]),
    "mejor un minicurso para el niño": DetectedIntent(
        language="es", activity="minicourse", service_id="minicourse", is_certified=False,
        detected_fields=["language", "activity", "is_certified"]),
    "cuentame del bubble makers": DetectedIntent(
        language="es", activity="minicourse", service_id="minicourse", is_certified=False,
        detected_fields=["language", "activity", "is_certified"]),
    "somos 2 buzos certificados": DetectedIntent(
        language="es", activity="certified_diving", service_id="2_dives_1_day", is_certified=True, group_size=2,
        detected_fields=["language", "activity", "is_certified", "group_size"]),
    "y cuanto cuesta?": DetectedIntent(language="es", detected_fields=["language"]),
}


def _apply_seq(msgs):
    from src.agents.supervisor import _apply_detected_intent
    st = ConversationState(conversation_id="seq"); st.language = "es"
    for m in msgs:
        _apply_detected_intent(copy.deepcopy(_LECTURAS[m]), st)
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


# --- English family / kids-age extraction -----------------------------------

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


# --- Fase 7: 3 bugs reales de regex hallados por las baterías (2026-07-21/22)
# Decisión documentada en docs/robustness/plan.md §Fase 7: estos casos eran
# patrones concretos y deterministas → se arregla el REGEX (no un override LLM
# no-determinista). El eval-set los tenía registrados como regresión permanente.

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
