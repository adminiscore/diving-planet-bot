"""Un numero de otra magnitud no es la respuesta a "¿cuantos?" (hallazgo G, 2026-09-15).

Con la pregunta del total pendiente, "hace 3 años que no buceo" fijaba 3 personas y "a
las 8" fijaba 8; con "¿cuantos para snorkel?", "mi hijo tiene 9 años" sumaba 9. Solo es
respuesta lo que ES la cantidad o lo que el detector ya lee como total del grupo.
"""

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState

NOT_A_COUNT = [
    "no, buceamos hace 6 meses",
    "hace 3 años que no buceo",
    "mi hijo tiene 9 años",
    "llegamos el 12",
    "a las 8",
    "2 inmersiones",
]
COUNTS = [("4", 4), ("dos", 2), ("3 😊", 3), ("6+", 6), ("somos 4", 4), ("4 personas", 4),
          ("we are 4", 4), ("vamos 2", 2), ("yo y mi pareja", 2)]


def _pending(slot):
    state = ConversationState(conversation_id="g")
    state.language = "es"
    state.detected_activity = "certified_diving"
    state.core_pending_slot = slot
    if slot == core.SLOT_COMPANION_QTY:
        state.detected_group_size = 3
        state.pending_companion_activity = "snorkel"
    return state


@pytest.mark.parametrize("slot", [core.SLOT_QTY, core.SLOT_COMPANION_QTY])
@pytest.mark.parametrize("message", NOT_A_COUNT)
def test_a_number_of_something_else_is_not_the_answer(slot, message):
    state = _pending(slot)
    assert core._apply_short_answer(state, message) is False
    assert state.detected_group_allocation is None
    assert state.detected_group_size == (3 if slot == core.SLOT_COMPANION_QTY else None)


@pytest.mark.parametrize("message, n", COUNTS)
def test_counts_still_answer_the_total_question(message, n):
    state = _pending(core.SLOT_QTY)
    assert core._apply_short_answer(state, message) is True
    assert state.detected_group_size == n


@pytest.mark.parametrize("typed, value", [("seguimos siendo 2", "2"), ("Somos 3!", "3"), ("seguimos siendo dos", None)])
def test_typing_a_button_title_is_pressing_it(typed, value):
    state = _pending(core.SLOT_QTY)
    state.quick_replies = [{"title": "Seguimos siendo 2", "value": "2"}, {"title": "Somos 3", "value": "3"}]
    assert core._button_value(state, typed) == value


def test_typed_title_with_accents_and_emoji():
    state = _pending(core.SLOT_CONFIRM_CORRECTION)
    state.quick_replies = [{"title": "✅ Sí, cámbialo", "value": "sí"}, {"title": "↩️ No, como estaba", "value": "no"}]
    assert core._button_value(state, "si cambialo") == "sí"
    assert core._button_value(state, "no, como estaba") == "no"


@pytest.mark.parametrize("message, value, other", [
    ("2 inmersiones", 2, True),         # el resolutor LLM lo leia como 2 personas
    ("mi hijo tiene 9 años", 9, True),
    ("2 adultos y un niño", 3, False),  # composicion legitima que resuelve el LLM
    ("unos 3", 3, False),
])
def test_resolver_count_that_the_detector_reads_as_something_else(message, value, other):
    assert core._number_of_something_else(ConversationState(conversation_id="g"), message, value) is other


@pytest.mark.asyncio
async def test_llm_fill_does_not_take_a_dive_count_as_the_group_total():
    """Medido con el LLM real: con el total pendiente, "2 inmersiones" volvia del relleno
    como group_size=2 (la guarda del resolutor no lo veia porque entraba por la extraccion)."""
    from unittest.mock import AsyncMock, patch

    state = _pending(core.SLOT_QTY)
    state.location = state.detected_location = "cartagena"
    state.is_certified = state.detected_is_certified = True
    fill = {"group_size": 2}
    with patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(fill, {}))), \
         patch.object(core, "fill_gaps", new=AsyncMock(return_value=fill)), \
         patch.object(core, "verify_fields", new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor._maybe_veto_resolved_fields_via_llm", new=AsyncMock(return_value=None)):
        await core._understand(state, "2 inmersiones")
    assert state.detected_group_size is None
    assert state.detected_cert_dives == 2


@pytest.mark.parametrize("message", NOT_A_COUNT)
def test_quantity_answer_helper(message):
    assert core._quantity_answer(ConversationState(conversation_id="g"), message) is None
