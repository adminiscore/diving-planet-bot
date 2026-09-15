"""Un dato que contradice lo guardado no se ignora ni se aplica a ciegas (tareas 7b y
7c, 2026-09-15).

Los campos se escribian una sola vez: "espera, en realidad no somos colombianos" tras
el precio re-emitia COP, y "al final mi suegra tambien bucea" no cambiaba el reparto.
Decision del owner: con cue explicito se aplica; sin el, se confirma con el cliente.
El regex propone y la verificacion LLM de campos sabidos arbitra (entiende la jerga y
se abstiene si habla de otra persona); aqui el LLM va mockeado con lo que devolvio en
la sonda real.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import route_message
from src.flows.state import ConversationState


def _closed(allocation=None, colombian=True):
    state = ConversationState(conversation_id="t7b")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "resumen"}]
    state.detected_activity = "certified_diving"
    state.detected_service_id = "2_dives_1_day"
    state.is_certified = state.detected_is_certified = True
    state.detected_group_size = sum(allocation.values()) if allocation else 2
    state.detected_group_allocation = allocation
    state.location = state.detected_location = "cartagena"
    state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
    state.is_colombian = colombian
    core._build_cart_from_slots(state)
    return state


async def _send(state, message, verify=None):
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})), \
         patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "extract_and_verify", new=AsyncMock(return_value=({}, verify or {}))), \
         patch.object(core, "verify_fields", new=AsyncMock(return_value=verify or {})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})), \
         patch.object(core, "compose_acknowledgement", new=AsyncMock(return_value="")), \
         patch.object(core, "resolve_slot_answer", new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor._maybe_veto_resolved_fields_via_llm", new=AsyncMock(return_value=None)):
        return await route_message(state, message)


@pytest.mark.asyncio
async def test_explicit_correction_after_the_price_changes_the_currency():
    state = _closed()
    await _send(state, "espera, en realidad no somos colombianos", verify={"is_colombian": False})
    assert state.is_colombian is False
    assert state.mixed_display_currency == "USD"
    assert state.pending_correction is None


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, colombian, currency", [("sí, cámbialo", False, "USD"), ("no, lo de antes", True, "COP")])
async def test_slang_correction_without_cue_is_confirmed(answer, colombian, currency):
    state = _closed()
    await _send(state, "ah no, somos gringos", verify={"is_colombian": False})
    assert state.is_colombian is True
    assert state.core_pending_slot == core.SLOT_CONFIRM_CORRECTION
    assert [b["value"] for b in state.quick_replies] == ["sí", "no"]
    await _send(state, answer)
    assert state.is_colombian is colombian
    assert state.mixed_display_currency == currency
    assert state.pending_correction is None


@pytest.mark.asyncio
async def test_split_change_is_confirmed_and_repriced():
    state = _closed(allocation={"certified_diving": 2, "snorkel": 1})
    await _send(state, "al final mi suegra tambien bucea, no hace snorkel",
                verify={"group_allocation": {"certified_diving": 3}})
    assert state.core_pending_slot == core.SLOT_CONFIRM_CORRECTION
    await _send(state, "sí")
    assert state.detected_group_allocation == {"certified_diving": 3}
    assert {item["type"]: item["qty"] for item in state.mixed_cart} == {"cert": 3}


@pytest.mark.asyncio
async def test_same_value_does_not_ask():
    state = _closed()
    await _send(state, "somos colombianos, sí")
    assert state.pending_correction is None


@pytest.mark.parametrize("message", [
    "mi novia no es buzo, ella viene y hace el minicurso",   # otra persona
    "mejor pensandolo bien quiero el minicurso",              # deducido del minicurso
])
def test_regex_does_not_take_inferences_or_other_people_as_the_writers_correction(message):
    state = ConversationState(conversation_id="t7b-regex")
    state.detected_activity = "certified_diving"
    state.is_certified = state.detected_is_certified = True
    intent = core._detector.detect(message, state)
    assert core._regex_contradictions(state, message, intent) == {}
    assert state.pending_correction is None
    assert intent.is_certified is None


def test_regex_correction_with_a_cue_is_accepted_in_the_same_turn():
    state = ConversationState(conversation_id="t7b-cue")
    state.is_colombian = True
    message = "espera, en realidad no somos colombianos"
    intent = core._detector.detect(message, state)
    assert core._regex_contradictions(state, message, intent) == {}
    assert intent.is_colombian is False
    assert "is_colombian" in intent.overwrite


def _waiting_location():
    state = ConversationState(conversation_id="t7b-anclada")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola, somos 3 buzos certificados y colombianos"}]
    state.detected_activity = "certified_diving"
    state.is_certified = state.detected_is_certified = True
    state.detected_group_size = 3
    state.is_colombian = True
    state.core_pending_slot = core.SLOT_LOCATION
    return state


@pytest.mark.asyncio
async def test_known_field_proposals_riding_on_the_answer_to_another_question_are_dropped():
    """Guarda (b): "desde cartagena" contesta la ubicacion; lo que el LLM re-derive del
    historial para otros campos no se confirma (medido en conversacion real)."""
    state = _waiting_location()
    await _send(state, "desde cartagena", verify={"group_size": 9})
    assert state.location == "cartagena"
    assert state.pending_correction is None
    assert state.detected_group_size == 3


@pytest.mark.asyncio
async def test_known_field_proposal_that_does_not_answer_the_pending_question_is_kept():
    state = _waiting_location()
    await _send(state, "ah no, somos gringos", verify={"is_colombian": False})
    assert state.pending_correction == {"is_colombian": False}
    assert state.core_pending_slot == core.SLOT_CONFIRM_CORRECTION


@pytest.mark.asyncio
async def test_split_with_an_ambiguous_course_level_waits_for_the_answer():
    """b05 (owner): "2 open water y 3 snorkel" no dice si tienen el nivel o lo quieren;
    se pregunta y no se guarda el reparto con el curso aunque el LLM lo rellene."""
    state = ConversationState(conversation_id="t7b-b05")
    state.language = "es"
    state.detected_group_size = 5
    split = {"group_allocation": {"padi_open_water": 2, "snorkel": 3}}
    with patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(split, {}))), \
         patch.object(core, "fill_gaps", new=AsyncMock(return_value=split)), \
         patch("src.agents.supervisor._maybe_veto_resolved_fields_via_llm", new=AsyncMock(return_value=None)):
        await core._understand(state, "2 open water y 3 snorkel")
    assert state.needs_cert_or_course is True
    assert state.detected_group_allocation is None


@pytest.mark.asyncio
async def test_own_change_of_activity_carries_a_single_activity_split():
    state = ConversationState(conversation_id="t7b-mejor")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola"}]
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.detected_group_size = 2
    state.detected_group_allocation = {"certified_diving": 2}
    state.location = state.detected_location = "cartagena"
    state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_NATIONALITY
    await _send(state, "mejor snorkel")
    assert state.detected_group_allocation == {"snorkel": 2}
