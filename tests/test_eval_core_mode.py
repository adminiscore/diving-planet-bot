"""Modo --core del eval-set (2026-09-15).

Cada caso pasa por `conversational_core._understand` sobre un estado sembrado y se
puntua lo que el turno cambio. Sin LLM: se mockean las peticiones.
"""

import contextlib
import copy
from unittest.mock import patch

import pytest

from scripts import run_extraction_eval as ev
from src.agents import conversational_core as cc


def _mock_llm(merged=None):
    async def fake_merged(*args, **kwargs):
        return copy.deepcopy(merged) if merged is not None else ({}, {})

    return (
        patch.object(cc, "extract_and_verify", create=True, new=fake_merged),
        contextlib.nullcontext(),  # el veto de campos se borró en MEJ-1 (21-oct)
    )


async def _run(case, **llm):
    a, b = _mock_llm(**llm)
    with a, b:
        return (await ev._core_turn(case))[0]


# ex-9b paso 3: los campos los lee el extractor del turno (`extractor_dice`, conftest); sin él, en
# los tests (sin red) fallaba y el turno iba por la pista del regex. Lo que se prueba es la puntuación del modo --core.


@pytest.mark.asyncio
async def test_a_field_the_state_already_had_is_not_produced_again(extractor_dice):
    extractor_dice({"desde cartagena": {"location": "cartagena"}})
    # Con su actividad principal: sin ella, el turno del extractor la saca del reparto ya sabido (ex-9b paso 3,
    # `_principal_del_grupo_repartido`) y la puntuaría como producida, aunque es otro campo.
    case = {
        "id": "t", "lang": "es", "message": "desde cartagena",
        "state": {"core_pending_slot": "location", "detected_group_size": 6, "detected_activity": "certified_diving",
                  "detected_group_allocation": {"certified_diving": 2, "minicourse": 2, "snorkel": 2}},
    }
    produced = await _run(case)
    assert produced == {"location": "cartagena"}


@pytest.mark.asyncio
async def test_undecided_members_are_scored_inside_the_allocation(extractor_dice):
    extractor_dice({"somos 3, uno no esta certificado":
                    {"group_size": 3, "group_allocation": {"certified_diving": 2, "undecided": 1}}})
    case = {"id": "t", "lang": "es", "message": "somos 3, uno no esta certificado"}
    produced = await _run(case)
    assert produced["group_allocation"] == {"certified_diving": 2, "undecided": 1}
    assert produced["group_size"] == 3


def test_every_seeded_state_key_exists_in_the_conversation_state():
    from src.flows.state import ConversationState

    state = ConversationState(conversation_id="t")
    cases = __import__("json").load(open(ev.EVAL_SET_PATH, encoding="utf-8"))["cases"]
    for case in cases:
        for key in case.get("state") or {}:
            assert hasattr(state, key), f"{case['id']}: {key} no existe en ConversationState"
