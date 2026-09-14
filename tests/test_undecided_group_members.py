"""Personas del grupo sin actividad elegida (decision del owner 2026-09-15).

"somos 3, uno no esta certificado": no se asume minicurso ni snorkel (el LLM suponia
snorkel 3/3). El LLM marca ese tramo `undecided`, el resto del grupo hace la
actividad principal (aritmetica con el total) y el bot recomienda opciones (F6).
Al elegir, se fusiona con la cantidad ya conocida, sin volver a preguntar.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState


def _state():
    s = ConversationState(conversation_id="undecided")
    s.language = "es"
    return s


@pytest.mark.asyncio
async def test_undecided_member_is_not_assumed_and_rest_follow_main_activity():
    state = _state()
    llm = {"group_allocation": {"undecided": 1}}
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value=llm)), \
         patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(llm, {}))):
        await core._understand(state, "somos 3, uno no está certificado")
    assert state.detected_group_allocation == {"certified_diving": 2}
    assert state.pending_undecided_qty == 1
    assert state.needs_companion_activity is True
    assert "minicourse" not in (state.detected_group_allocation or {})
    assert "snorkel" not in (state.detected_group_allocation or {})


def test_choice_merges_with_the_known_quantity():
    state = _state()
    state.detected_activity = "certified_diving"
    state.detected_group_allocation = {"certified_diving": 2}
    state.detected_group_size = 3
    state.pending_undecided_qty = 1
    state.pending_companion_activity = "snorkel"
    assert core._merge_pending_undecided(state) is True
    assert state.detected_group_allocation == {"certified_diving": 2, "snorkel": 1}
    assert state.detected_group_size == 3
    assert state.pending_undecided_qty is None and state.pending_companion_activity is None


def test_without_undecided_quantity_the_bot_still_asks_how_many():
    state = _state()
    state.pending_companion_activity = "snorkel"
    assert core._merge_pending_undecided(state) is False
    assert state.pending_companion_activity == "snorkel"


@pytest.mark.asyncio
async def test_invented_undecided_quantity_is_ignored():
    """La cifra de `undecided` del LLM tiene que estar en el texto: "uno" no avala un 2."""
    state = _state()
    llm = {"group_allocation": {"undecided": 2}}
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value=llm)), \
         patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(llm, {}))):
        await core._understand(state, "uno de nosotros no está certificado")
    assert state.pending_undecided_qty is None
    assert state.needs_companion_activity is False


def test_regex_marks_attribute_only_split_as_undecided():
    """El regex ya no asume minicurso para "y 1 no" / "uno no esta certificado"."""
    from src.agents.intent_detector import IntentDetector
    for message in ("somos 3, uno no esta certificado", "somos 3, 2 con open water y 1 no",
                    "5 certificados y 2 principiantes"):
        intent = IntentDetector().detect(message, _state())
        assert "minicourse" not in intent.group_allocation, message
        assert intent.group_allocation.get("undecided"), message
    intent = IntentDetector().detect("uno certificado y dos minicurso", _state())
    assert intent.group_allocation == {"certified_diving": 1, "minicourse": 2}


@pytest.mark.asyncio
async def test_without_known_total_the_main_group_is_not_guessed():
    """Sin total del grupo no hay aritmetica: no se inventa el tramo principal, pero
    la recomendacion para quien no eligio sigue pendiente."""
    state = _state()
    llm = {"group_allocation": {"undecided": 1}}
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value=llm)), \
         patch.object(core, "extract_and_verify", new=AsyncMock(return_value=(llm, {}))):
        await core._understand(state, "uno de nosotros no está certificado")
    assert not state.detected_group_allocation
    assert state.pending_undecided_qty == 1
    assert state.needs_companion_activity is True


def test_recommendation_speaks_to_the_uncertified_group_members():
    state = _state()
    state.pending_undecided_qty = 2
    state.detected_duration = "single_day"
    text = core.ask_slot(state, core.SLOT_COMPANION_ACTIVITY)
    assert "quienes no están certificados" in text and "acompañante" not in text.splitlines()[0]
    state.pending_undecided_qty = None
    assert "tu acompañante" in core.ask_slot(state, core.SLOT_COMPANION_ACTIVITY)
