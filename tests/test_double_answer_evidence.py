"""Respuesta doble con otra pregunta pendiente (hallazgo B, 2026-09-15).

"desde cartagena, somos paisas" con la ubicacion pendiente perdia `is_colombian`: la guarda
(b) descarta el booleano que viaja con la respuesta a otra pregunta, porque "Desde
Cartagena" rellenaba `is_colombian=True` 3/3. El extractor cita ahora, en la misma peticion,
las palabras del mensaje que dicen cada booleano, y la cita lo respalda si esta en el
mensaje, no es el mensaje entero y el detector no lee en ella la respuesta pendiente.
ex-9b: `_quote_backs_boolean` y `_boolean_patch_is_anchored` no tenían llamador desde ex-9 (0.31.28) y se
borraron con su test.
lat-11 T6e (26-oct): el tool y el prompt de la extracción del relleno (`fill_gaps`) se quitaron, y sus tests.
"""

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _camino_viejo_de_actividad(monkeypatch):
    """Estos tests prueban el camino viejo (regex + veto/relleno). Con ex-8 (`extraccion_llm_actividad`) la actividad y
    la nacionalidad las decide el extractor "LLM primero": tests/test_ex8_actividad_nacionalidad.py."""


LOC = core.SLOT_LOCATION


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

    await core._understand(state, message)
    return calls


@pytest.mark.asyncio
async def test_boolean_quoting_the_pending_answer_is_still_dropped(extractor_dice):
    # ex-9b paso 3 (limpieza ex9b): el origen ya no sale de la pista del regex sino del extractor del turno.
    extractor_dice({"Desde Cartagena": {"location": "cartagena"}})
    state = _waiting_location()
    await _understand(state, "Desde Cartagena", {"is_colombian": True, "evidence": {"is_colombian": "Desde Cartagena"}})
    assert state.location == "cartagena"
    assert state.is_colombian is None


