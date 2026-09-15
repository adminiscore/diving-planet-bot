"""Grupo con nacionalidades mixtas leido por el LLM (hallazgo A, 2026-09-15).

Decision del owner: un grupo mixto paga todo en USD. La deteccion era una lista de fraseos
(`_MIXED_NATIONALITY_RE`) que no conocia gentilicios ("somos colombianos pero mi amigo es
aleman" cobraba en COP) y marcaba mixto "mi amigo es colombiano y yo tambien". Owner: que lo
lea el LLM. Viaja como `mixed_nationality` en la peticion que el turno ya hace, solo si el
mensaje habla de quien escribe y de otra persona (con un solo lado el LLM suponia la otra
mitad 2/2), y el tool de siempre no cambia.
"""

from unittest.mock import patch

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import mentions_writer_and_others
from src.flows.state import ConversationState
from src.prompts.booking import EXTRACTION_TOOL, extraction_tool


@pytest.mark.parametrize("message", [
    "yo soy colombiano y mi novia extranjera",
    "mi esposa es colombiana y yo no",
    "dos somos colombianos pero uno es extranjero",
    "somos colombianos pero mi amigo es aleman",
    "i'm colombian but my girlfriend is from spain",
    "yo vivo en bogota y mi amigo es gringo",
    "uno de nosotros es colombiano y los otros dos no",
    "one of us is colombian and the others are not",
    "somos alemanes pero mi esposa vive en medellin",
])
def test_both_sides_of_the_party_ask_the_llm(message):
    assert mentions_writer_and_others(message)


@pytest.mark.parametrize("message", [
    "ninguno colombiano",
    "mi novio es aleman y quiere hacer snorkel",
    "mi esposa es colombiana",
    "nadie es colombiano, somos de chile",
    "my girlfriend is from spain and she wants to dive",
    "we're all from germany",
    "somos colombianos, queremos bucear",
    "no soy colombiano pero vivo en colombia",
])
def test_one_side_only_never_asks(message):
    assert not mentions_writer_and_others(message)


def test_the_usual_tool_is_untouched():
    assert extraction_tool() is EXTRACTION_TOOL
    assert "mixed_nationality" not in EXTRACTION_TOOL["function"]["parameters"]["properties"]
    variant = extraction_tool(["mixed_nationality"])
    assert variant["function"]["parameters"]["properties"]["mixed_nationality"]["type"] == "boolean"


async def _understand(message, returned):
    calls = []

    async def fake_fill(*args, **kwargs):
        calls.append(tuple(kwargs.get("extra_fields") or ()))
        return dict(returned)

    async def fake_extract(*args, **kwargs):
        calls.append(tuple(kwargs.get("extra_fields") or ()))
        return dict(returned), {}

    state = ConversationState(conversation_id="mixed")
    state.language = "es"
    with patch.object(core, "fill_gaps", fake_fill), patch.object(core, "extract_and_verify", fake_extract):
        await core._understand(state, message)
    return state, calls


@pytest.mark.asyncio
async def test_mixed_group_pays_in_usd_even_if_the_regex_read_colombian():
    state, calls = await _understand("somos colombianos pero mi amigo es aleman", {"mixed_nationality": True})
    assert ("mixed_nationality",) in calls
    assert state.is_colombian is False
    assert state.mixed_nationality_notice is True


@pytest.mark.asyncio
async def test_one_sided_message_does_not_ask_for_the_mix():
    state, calls = await _understand("mi novio es aleman y quiere hacer snorkel", {"mixed_nationality": True})
    assert calls and all("mixed_nationality" not in c for c in calls)
    assert state.mixed_nationality_notice is False


@pytest.mark.asyncio
async def test_not_mixed_keeps_the_nationality_read():
    state, _ = await _understand("yo soy colombiano y mi novia tambien", {})
    assert state.is_colombian is True
    assert state.mixed_nationality_notice is False
