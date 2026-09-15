"""Un reparto de personas nombradas y los tramos de un total ya sabido (hallazgos F.2 y H,
2026-09-15).

F.2: "vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel" nombra a 3 personas y el
LLM las reparte {2, 1}, pero la guarda de cifras solo aceptaba cifras 1 de personas
sueltas y tiraba el reparto. H: al preguntar despues "¿cuantos serian para X?", la
respuesta se sumaba encima del total (3 -> 4 -> 5). Regla unica: con el total sabido, la
actividad principal se queda con el resto.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState


async def _understand(state, message, patch_value):
    with patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(patch_value, {}))), \
         patch.object(core, "fill_gaps", new=AsyncMock(return_value=patch_value)), \
         patch.object(core, "verify_fields", new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor._maybe_veto_resolved_fields_via_llm", new=AsyncMock(return_value=None)):
        await core._understand(state, message)


def _new():
    state = ConversationState(conversation_id="split")
    state.language = "es"
    return state


@pytest.mark.asyncio
async def test_split_that_partitions_the_named_people_is_kept():
    state = _new()
    await _understand(state, "vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel",
                      {"group_size": 3, "group_allocation": {"certified_diving": 2, "snorkel": 1}})
    assert state.detected_group_allocation == {"certified_diving": 2, "snorkel": 1}
    assert state.detected_group_size == 3
    assert state.pending_companion_queue == []


@pytest.mark.asyncio
async def test_named_people_partition_keeps_the_total_with_undecided_members():
    """F.3: "my wife and i dive" con dos hijos: el total 4 ya no se tira con el reparto."""
    state = _new()
    await _understand(state, "my daughter is 9 and my son is 12, my wife and i dive",
                      {"group_size": 4, "group_allocation": {"certified_diving": 2, "undecided": 2}})
    assert state.detected_group_size == 4
    assert state.detected_group_allocation == {"certified_diving": 2}
    assert state.pending_undecided_qty == 2


@pytest.mark.asyncio
async def test_main_activity_takes_the_rest_of_a_known_total():
    """Solo la principal no tiene respaldo ("mis amigos bucean"): con "vamos 4", es el resto."""
    state = _new()
    await _understand(state, "vamos 4, mis amigos bucean y mi hermana hace snorkel",
                      {"group_size": 4, "group_allocation": {"certified_diving": 3, "snorkel": 1}})
    assert state.detected_group_allocation == {"certified_diving": 3, "snorkel": 1}
    assert state.detected_group_size == 4


@pytest.mark.asyncio
async def test_queued_shares_of_a_known_total_do_not_add_on_top():
    """Tramos sin respaldo con el total sabido: no se pregunta la principal y la respuesta se
    reparte dentro del total."""
    state = _new()
    await _understand(state, "vamos 5, mis amigos bucean y mis primos hacen snorkel",
                      {"group_size": 5, "group_allocation": {"certified_diving": 3, "snorkel": 2}})
    assert state.pending_companion_queue == ["snorkel"]
    assert state.pending_split_total == 5
    state.pending_companion_activity = state.pending_companion_queue.pop(0)
    state.core_pending_slot = core.SLOT_COMPANION_QTY
    assert core._apply_short_answer(state, "2")
    assert state.detected_group_allocation == {"snorkel": 2, "certified_diving": 3}
    assert state.detected_group_size == 5
    assert state.pending_split_total is None


def test_a_share_larger_than_the_total_asks_whether_someone_joins():
    state = _new()
    state.detected_activity = "certified_diving"
    state.detected_group_size = 3
    state.pending_split_total = 3
    state.pending_companion_activity = "snorkel"
    state.core_pending_slot = core.SLOT_COMPANION_QTY
    assert core._apply_short_answer(state, "5")
    assert state.pending_companion_in_group == {"activity": "snorkel", "qty": 5}
    assert state.detected_group_size == 3


def test_main_rest_is_a_single_helper():
    assert core._with_main_rest({"snorkel": 1}, "certified_diving", 3) == {"snorkel": 1, "certified_diving": 2}
    assert core._with_main_rest({"snorkel": 1}, "certified_diving", 3, taken=2) == {"snorkel": 1}
