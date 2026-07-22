"""Fase C (open remembered facts) — written before the implementation exists,
per docs/memory-context-improvement-plan.md. These tests capture the TARGET
behavior; expected to fail (RED) until `_persist_remembered` accumulates a
"notes" list instead of only the 5 fixed overwriting keys.

Real-world motivation (live PRE, 2026-07-17): "mi padre tiene la rodilla
operada, evitar planes muy físicos" doesn't map cleanly to budget/days/
child_ages/experience_level/preference, so it was never captured anywhere
the bot could recall later.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.agents import orchestrator
from src.agents.supervisor import _build_extra_context, route_message
from src.flows.decision_tree import ConversationState, Step


def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="notes-test")
    s.language = lang
    s.step = Step.MAIN_MENU
    return s


@pytest.fixture(autouse=True)
def _mock_rag_answer():
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        yield


@pytest.mark.asyncio
async def test_single_note_persisted_and_surfaced_in_context(agent_decides):
    agent_decides(
        orchestrator.TOOL_ANSWER_QUESTION,
        remembered={"notes": ["padre con rodilla operada, evitar planes físicos"]},
    )
    state = make_state()
    await route_message(state, "mi padre tiene la rodilla operada, evitar planes físicos")

    assert state.remembered_facts.get("notes") == ["padre con rodilla operada, evitar planes físicos"]
    context = _build_extra_context(state)
    assert context is not None
    assert "rodilla operada" in context


@pytest.mark.asyncio
async def test_second_unrelated_note_does_not_erase_the_first(agent_decides):
    """Unlike the 5 fixed keys (which overwrite), notes must accumulate —
    this is the exact gap that lost the padre detail in the real PRE bug."""
    state = make_state()

    agent_decides(orchestrator.TOOL_ANSWER_QUESTION, remembered={"notes": ["padre con rodilla operada"]})
    await route_message(state, "mi padre tiene la rodilla operada")

    agent_decides(orchestrator.TOOL_ANSWER_QUESTION, remembered={"notes": ["es el cumpleaños de mi madre"]})
    await route_message(state, "es el cumpleaños de mi madre")

    notes = state.remembered_facts.get("notes") or []
    assert "padre con rodilla operada" in notes
    assert "es el cumpleaños de mi madre" in notes
    assert len(notes) == 2


@pytest.mark.asyncio
async def test_duplicate_note_is_not_repeated(agent_decides):
    state = make_state()
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION, remembered={"notes": ["padre con rodilla operada"]})
    await route_message(state, "mi padre tiene la rodilla operada")
    await route_message(state, "como decia, mi padre tiene la rodilla operada")

    notes = state.remembered_facts.get("notes") or []
    assert notes.count("padre con rodilla operada") == 1


@pytest.mark.asyncio
async def test_notes_capped_at_max(agent_decides):
    state = make_state()
    for i in range(10):
        agent_decides(orchestrator.TOOL_ANSWER_QUESTION, remembered={"notes": [f"nota numero {i}"]})
        await route_message(state, f"dato {i}")

    notes = state.remembered_facts.get("notes") or []
    assert len(notes) <= 8
    # Keeps the most RECENT notes, not the oldest.
    assert "nota numero 9" in notes
    assert "nota numero 0" not in notes


@pytest.mark.asyncio
async def test_existing_fixed_keys_still_work_alongside_notes(agent_decides):
    """The new notes list must not break the 5 existing fixed-key facts."""
    state = make_state()
    agent_decides(
        orchestrator.TOOL_ANSWER_QUESTION,
        remembered={"budget": "<300 USD", "notes": ["prefiere mañanas"]},
    )
    await route_message(state, "tenemos presupuesto de 300 dólares y preferimos ir por la mañana")

    assert state.remembered_facts.get("budget") == "<300 USD"
    assert state.remembered_facts.get("notes") == ["prefiere mañanas"]


def test_build_extra_context_renders_multiple_notes_as_bullets():
    state = make_state()
    state.remembered_facts = {"notes": ["padre con rodilla operada", "es el cumpleaños de mi madre"]}
    context = _build_extra_context(state)
    assert context is not None
    assert "padre con rodilla operada" in context
    assert "es el cumpleaños de mi madre" in context
