"""Respuesta doble con otra pregunta pendiente (hallazgo B, 2026-09-15).

"desde cartagena, somos paisas" con la ubicacion pendiente perdia `is_colombian`: la guarda
(b) descarta el booleano que viaja con la respuesta a otra pregunta, porque "Desde
Cartagena" rellenaba `is_colombian=True` 3/3. El extractor cita ahora, en la misma peticion,
las palabras del mensaje que dicen cada booleano, y la cita lo respalda si esta en el
mensaje, no es el mensaje entero y el detector no lee en ella la respuesta pendiente.
"""

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState
from src.prompts.booking import EVIDENCE_FIELDS, extraction_tool

LOC = core.SLOT_LOCATION


@pytest.mark.parametrize("field, pending, message, evidence, backed", [
    ("is_colombian", LOC, "desde cartagena, somos paisas", {"is_colombian": "somos paisas"}, True),
    ("is_certified", LOC, "salimos de bocagrande, ya tenemos el AOWD", {"is_certified": "ya tenemos el AOWD"}, True),
    ("is_colombian", core.SLOT_QTY, "somos 3, todos colombianos", {"is_colombian": "todos colombianos"}, True),
    ("is_colombian", LOC, "Desde Cartagena", {"is_colombian": "Desde Cartagena"}, False),         # el mensaje entero
    ("is_colombian", LOC, "desde cartagena, gracias", {"is_colombian": "desde cartagena"}, False),  # es la respuesta pendiente
    ("is_certified", LOC, "desde cartagena, somos paisas", {"is_certified": "si los dos"}, False),  # cita del historial
    ("is_colombian", LOC, "desde cartagena, somos paisas", {}, False),                              # sin cita
    ("is_colombian", None, "desde cartagena, somos paisas", {"is_colombian": "somos paisas"}, False),  # nada pendiente
    ("is_certified", core.SLOT_CERTIFICATION, "si, somos paisas", {"is_certified": "si"}, False),   # slot booleano: guarda (a)
])
def test_quote_backs_boolean(field, pending, message, evidence, backed):
    assert core._quote_backs_boolean(field, pending, message, evidence) is backed


def test_one_list_of_quoted_booleans():
    assert set(EVIDENCE_FIELDS) == core._BOOL_PATCH_FIELDS
    assert set(extraction_tool(["evidence"])["function"]["parameters"]["properties"]["evidence"]["properties"]) == set(EVIDENCE_FIELDS)


def _waiting_location():
    state = ConversationState(conversation_id="doble")
    state.language = "es"
    state.detected_activity = "certified_diving"
    state.is_certified = state.detected_is_certified = True
    state.detected_group_size = 2
    state.core_pending_slot = LOC
    return state


async def _understand(state, message, returned):
    calls = []

    async def fake(*args, **kwargs):
        calls.append(tuple(kwargs.get("extra_fields") or ()))
        return (dict(returned), {}) if "gaps" not in kwargs else dict(returned)

    async def fake_fill(*args, **kwargs):
        calls.append(tuple(kwargs.get("extra_fields") or ()))
        return dict(returned)

    from unittest.mock import patch
    with patch.object(core, "extract_and_verify", fake), patch.object(core, "fill_gaps", fake_fill):
        await core._understand(state, message)
    return calls


@pytest.mark.asyncio
async def test_double_answer_keeps_the_quoted_boolean():
    state = _waiting_location()
    calls = await _understand(state, "desde cartagena, somos paisas",
                              {"is_colombian": True, "evidence": {"is_colombian": "somos paisas"}})
    assert any("evidence" in c for c in calls)
    assert state.location == "cartagena"
    assert state.is_colombian is True


@pytest.mark.asyncio
async def test_boolean_quoting_the_pending_answer_is_still_dropped():
    state = _waiting_location()
    await _understand(state, "Desde Cartagena", {"is_colombian": True, "evidence": {"is_colombian": "Desde Cartagena"}})
    assert state.location == "cartagena"
    assert state.is_colombian is None


@pytest.mark.asyncio
async def test_no_quote_requested_without_a_pending_question():
    state = ConversationState(conversation_id="apertura")
    state.language = "es"
    calls = await _understand(state, "soy paisa", {"is_colombian": True})
    assert calls and all("evidence" not in c for c in calls)
    assert state.is_colombian is True
