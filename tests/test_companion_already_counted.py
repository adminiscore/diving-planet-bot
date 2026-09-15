"""La actividad de otra persona no pisa la principal ni se cuenta dos veces (tarea 7a,
2026-09-15).

"él quiere hacer snorkel" con la nacionalidad pendiente cambiaba la actividad principal
a snorkel y el resumen cobraba 2 inmersiones. Quien es otra persona lo decide el LLM de
señales (reconoce pronombres y jerga); si ya estaba contada no lo dice nadie, asi que
se pregunta el total y la respuesta decide mover o añadir. Sin frases nuevas.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import route_message
from src.flows.state import ConversationState

COMPANION_SNORKEL = {"companion_activity": "snorkel", "mentions_other_person": True,
                     "companion_is_singular": True, "companion_qty": 1}


def _two_divers_waiting_nationality():
    state = ConversationState(conversation_id="t7a")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola, quiero bucear con mi amigo, yo soy certificado"}]
    state.detected_activity = "certified_diving"
    state.detected_service_id = "2_dives_1_day"
    state.is_certified = True
    state.detected_group_size = 2
    state.detected_group_allocation = {"certified_diving": 2}
    state.location = state.detected_location = "cartagena"
    state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_NATIONALITY
    return state


async def _send(state, message, signals):
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})), \
         patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "extract_and_verify", new=AsyncMock(return_value=({}, {}))), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value=signals)), \
         patch.object(core, "compose_acknowledgement", new=AsyncMock(return_value="")), \
         patch.object(core, "resolve_slot_answer", new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor._maybe_veto_resolved_fields_via_llm", new=AsyncMock(return_value=None)):
        return await route_message(state, message)


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["él quiere hacer snorkel", "mi parce se anima al snorkel", "ella prefiere snorkel"])
async def test_other_persons_activity_asks_the_total_instead_of_guessing(message):
    state = _two_divers_waiting_nationality()
    await _send(state, message, COMPANION_SNORKEL)
    assert state.detected_activity == "certified_diving"
    assert state.detected_group_allocation == {"certified_diving": 2}
    assert state.core_pending_slot == core.SLOT_QTY
    assert [b["value"] for b in state.quick_replies] == ["2", "3"]


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, allocation, total", [
    ("seguimos siendo 2", {"certified_diving": 1, "snorkel": 1}, 2),
    ("somos 3", {"certified_diving": 2, "snorkel": 1}, 3),
])
async def test_the_total_decides_move_or_add(answer, allocation, total):
    state = _two_divers_waiting_nationality()
    await _send(state, "él quiere hacer snorkel", COMPANION_SNORKEL)
    await _send(state, answer, {})
    assert state.detected_group_allocation == allocation
    assert state.detected_group_size == total
    assert state.pending_companion_in_group is None
    assert state.core_pending_slot == core.SLOT_NATIONALITY


@pytest.mark.asyncio
async def test_an_explicit_addition_is_added_without_asking():
    state = _two_divers_waiting_nationality()
    await _send(state, "también viene mi hermana que quiere hacer snorkel", COMPANION_SNORKEL)
    assert state.detected_group_allocation == {"certified_diving": 2, "snorkel": 1}
    assert state.detected_group_size == 3
    assert state.core_pending_slot == core.SLOT_NATIONALITY


def test_with_a_total_of_one_the_other_person_is_new():
    state = ConversationState(conversation_id="t7a-solo")
    state.detected_activity = "certified_diving"
    state.detected_group_size = 1
    core._add_or_ask_companion(state, "mi acompañante quiere hacer el minicurso", "minicourse", 1)
    assert state.pending_companion_in_group is None
    assert state.detected_group_allocation == {"certified_diving": 1, "minicourse": 1}


def test_allocation_without_the_main_activity_does_not_explain_the_group():
    state = ConversationState(conversation_id="t7a-breaker")
    state.detected_activity = "snorkel"
    state.detected_group_size = 2
    state.detected_group_allocation = {"certified_diving": 2}
    assert not core._group_allocation_fully_resolved(state)
    state.detected_activity = "certified_diving"
    assert core._group_allocation_fully_resolved(state)
