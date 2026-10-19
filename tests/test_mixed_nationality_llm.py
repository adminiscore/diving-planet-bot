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
from src.agents.nucleo import extraction as core_extraction
from src.flows.state import ConversationState
from src.prompts.booking import EXTRACTION_TOOL, extraction_tool


@pytest.fixture(autouse=True)
def _camino_viejo_de_actividad(monkeypatch):
    """Estos tests prueban el camino viejo (regex + veto/relleno). Con ex-8 (`extraccion_llm_actividad`) la actividad y
    la nacionalidad las decide el extractor "LLM primero": tests/test_ex8_actividad_nacionalidad.py."""


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
    with patch.object(core_extraction, "fill_gaps", fake_fill), patch.object(core, "extract_and_verify", fake_extract, create=True):
        await core._understand(state, message)
    return state, calls


@pytest.mark.asyncio
async def test_not_mixed_keeps_the_nationality_read(extractor_dice):
    # ex-9b paso 3: la nacionalidad y el grupo mixto los lee el extractor del turno (`extractor_dice`, conftest); sin él,
    # en los tests la nacionalidad iba por la pista del regex. No mixto: se queda la nacionalidad leída.
    extractor_dice({"yo soy colombiano y mi novia tambien": {"is_colombian": True}})
    state, _ = await _understand("yo soy colombiano y mi novia tambien", {})
    assert state.is_colombian is True
    assert state.mixed_nationality_notice is False
