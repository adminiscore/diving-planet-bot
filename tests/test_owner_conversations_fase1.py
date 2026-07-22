"""Regression tests for the 8 owner conversation scenarios that motivated the
"understanding-first" conversation agent (Fase 1, commit 59a90ae) and its
live-verify fixes (e70a8cb).

These lock in the DETERMINISTIC layer that the 4 live-testing bugs lived in:
- the escalation keyword matcher must not false-positive on headcount phrases
  containing "persona"/"person" (scenarios 5 and 8);
- the intent detector must classify never-dived / bautismo groups as beginners,
  not certified divers (scenarios 1, 2, 5), including the "nunca hemos hecho
  buceo" auxiliary+noun variant;
- headcount extraction (scenarios 1, 3, 8);
- "quiero certificarme" (wants to GET certified) must NOT read as already
  certified (scenario 7).

The full LLM-mediated routing (orchestrator answer/book/escalate) is exercised
live and in the async supervisor tests; here we pin only the regex/keyword layer
so it stays fast, deterministic, and free of network/DB dependencies.
"""

import pytest

from src.agents.intent_detector import IntentDetector
from src.agents.supervisor import _matches_escalation_keyword
from src.flows.decision_tree import ConversationState


detector = IntentDetector()


def _detect(msg: str):
    return detector.detect(msg, ConversationState(conversation_id="owner-test"))


# Every owner message, indexed by scenario, for the escalation-keyword guard.
OWNER_MESSAGES = {
    "1_budget_5_no_exp": "estoy pensando en hacer una reserva para bucear, sería para 5 personas, nunca hemos hecho buceo antes, que ofreceis y que presupuesto seria?",
    "2_never_dived_reco": "nunca he hecho buceo y no se muy bien como funciona, que me recomiendas?",
    "3a_couple_budget": "hola, quiero hacer buceo con mi pareja, tenemos un presupuesto inferior a 300 € y disponemos de 4 dias, que teneis?",
    "3b_ow_and_none": "yo tengo el open water y el no tiene nada",
    "3c_dont_split_us": "somos dos si, uno certificado con el open water y otro sin certificar, a poder ser, nos gustaria ir juntos y hacer lo mismo, no queremos separarlos, al no tener certificado, le da un poco de yuyu",
    "4_outside_cartagena": "hola, teneis centros de buceo en otro lado que no sea cartagena?",
    "5_family_14_baptism": "hola, voy a hacer buceo con mi familia, hay una persona que tiene 14 años, queremos hacer un bautismo, hay edad minima?",
    "6a_son_9_options": "hola, estoy pensando en hacer buceo estos dias con mi hijo, tiene 9 años, que opciones teneis?",
    "6b_son_can_dive": "pero mi hijo puede hacer buceo?",
    "7_open_water_detail": "quiero certificarme de open water, cuantos dias necesito y cuantas inmersiones son? me puedes detallar el programa profa?",
    "8_group_5_one_14": "quiero hacer buceo con 5 personas, uno tiene 14 años, puede?",
}


@pytest.mark.parametrize("key,msg", list(OWNER_MESSAGES.items()))
def test_no_owner_message_false_positives_escalation(key, msg):
    """None of the 8 owner messages may trigger a bare-keyword escalation.

    Regression for the "persona"/"person" false positive (scenarios 5 & 8:
    "hay una persona que tiene 14 años" escalated with an empty reply).
    """
    assert _matches_escalation_keyword(msg.lower()) is False


# --- Scenario 1: budget + 5 people + no experience --------------------------

def test_scenario1_five_beginners_detected():
    intent = _detect(OWNER_MESSAGES["1_budget_5_no_exp"])
    assert intent.is_certified is False  # "nunca hemos hecho buceo" -> not certified
    assert intent.activity == "minicourse"
    assert intent.group_size == 5


# --- Scenario 2: never dived, asks for a recommendation ---------------------

def test_scenario2_never_dived_is_beginner():
    intent = _detect(OWNER_MESSAGES["2_never_dived_reco"])
    assert intent.is_certified is False
    assert intent.activity == "minicourse"


# --- Scenario 3: couple, one certified (OW) + one not, don't split them ------

def test_scenario3a_couple_group_size_two():
    intent = _detect(OWNER_MESSAGES["3a_couple_budget"])
    assert intent.group_size == 2


def test_scenario3c_mixed_cert_split_not_all_certified():
    """'uno certificado con el open water y otro sin certificar' must NOT read
    as a fully-certified group (the '... sin certificar' half must win)."""
    intent = _detect(OWNER_MESSAGES["3c_dont_split_us"])
    assert intent.is_certified is False
    assert intent.group_size == 2


# --- Scenario 5: family, someone 14, baptism, minimum age -------------------

def test_scenario5_family_baptism_is_beginner_and_no_escalation():
    intent = _detect(OWNER_MESSAGES["5_family_14_baptism"])
    assert intent.is_certified is False   # bautismo -> beginner
    assert intent.activity == "minicourse"
    # The headcount word "persona" must not escalate (main scenario-5 bug).
    assert _matches_escalation_keyword(OWNER_MESSAGES["5_family_14_baptism"].lower()) is False


# --- Scenario 7: wants to GET certified (Open Water) ------------------------

def test_scenario7_wants_to_get_certified_is_not_certified():
    """'quiero certificarme de open water' = wants to obtain the certification,
    so is_certified must be False, not True (reflexive certificar* fix)."""
    intent = _detect(OWNER_MESSAGES["7_open_water_detail"])
    assert intent.activity == "padi_open_water"
    assert intent.is_certified is False


@pytest.mark.parametrize("msg", [
    "quiero certificarme",
    "queremos certificarnos con ustedes",
    "me gustaría certificarme en buceo",
    "i want to get certified",
])
def test_reflexive_certificar_means_not_yet_certified(msg):
    intent = _detect(msg)
    assert intent.is_certified is False


# --- Scenario 8: group of 5, one is 14 --------------------------------------

def test_scenario8_group_five_no_escalation():
    intent = _detect(OWNER_MESSAGES["8_group_5_one_14"])
    assert intent.group_size == 5
    assert _matches_escalation_keyword(OWNER_MESSAGES["8_group_5_one_14"].lower()) is False
