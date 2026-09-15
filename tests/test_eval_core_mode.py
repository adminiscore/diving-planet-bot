"""Modo --core del eval-set (2026-09-15).

Cada caso pasa por `conversational_core._understand` sobre un estado sembrado y se
puntua lo que el turno cambio. Sin LLM: se mockean las peticiones.
"""

import copy
from unittest.mock import patch

import pytest

from scripts import run_extraction_eval as ev
from src.agents import conversational_core as cc


def _mock_llm(merged=None, fill=None):
    async def fake_merged(*args, **kwargs):
        return copy.deepcopy(merged) if merged is not None else ({}, {})

    async def fake_fill(*args, **kwargs):
        return copy.deepcopy(fill or {})

    async def fake_veto(*args, **kwargs):
        return None

    return (
        patch.object(cc, "extract_and_verify", new=fake_merged),
        patch.object(cc, "fill_gaps", new=fake_fill),
        patch("src.agents.supervisor._maybe_veto_resolved_fields_via_llm", new=fake_veto),
    )


async def _run(case, **llm):
    a, b, c = _mock_llm(**llm)
    with a, b, c:
        return (await ev._core_turn(case))[0]


@pytest.mark.asyncio
async def test_a_field_the_state_already_had_is_not_produced_again():
    case = {
        "id": "t", "lang": "es", "message": "desde cartagena",
        "state": {"core_pending_slot": "location", "detected_group_size": 6,
                  "detected_group_allocation": {"certified_diving": 2, "minicourse": 2, "snorkel": 2}},
    }
    produced = await _run(case)
    assert produced == {"location": "cartagena"}


@pytest.mark.asyncio
async def test_undecided_members_are_scored_inside_the_allocation():
    case = {"id": "t", "lang": "es", "message": "somos 3, uno no esta certificado"}
    produced = await _run(case, fill={"group_allocation": {"certified_diving": 2, "undecided": 1}})
    assert produced["group_allocation"] == {"certified_diving": 2, "undecided": 1}
    assert produced["group_size"] == 3


def test_every_seeded_state_key_exists_in_the_conversation_state():
    from src.flows.state import ConversationState

    state = ConversationState(conversation_id="t")
    cases = __import__("json").load(open(ev.EVAL_SET_PATH, encoding="utf-8"))["cases"]
    for case in cases:
        for key in case.get("state") or {}:
            assert hasattr(state, key), f"{case['id']}: {key} no existe en ConversationState"
