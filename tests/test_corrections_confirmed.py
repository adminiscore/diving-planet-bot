"""Un dato que contradice lo guardado no se ignora ni se aplica a ciegas (tareas 7b y
7c, 2026-09-15).

Los campos se escribian una sola vez: "espera, en realidad no somos colombianos" tras
el precio re-emitia COP, y "al final mi suegra tambien bucea" no cambiaba el reparto.
Decision del owner: con cue explicito se aplica; sin el, se confirma con el cliente.
El regex propone y la verificacion LLM de campos sabidos arbitra (entiende la jerga y
se abstiene si habla de otra persona); aqui el LLM va mockeado con lo que devolvio en
la sonda real.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.nucleo import slotfill_close as core_close
from src.agents.supervisor import route_message
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _grupo_camino_antiguo(monkeypatch):
    """Estos tests fijan el grupo por el camino de antes de ex-7 (regex y redes LLM); con `extraccion_llm_grupo` lo
    decide el extractor (tests/test_ex7_grupo.py)."""


@pytest.fixture(autouse=True)
def _camino_viejo_de_actividad(monkeypatch):
    """Estos tests prueban el camino viejo (regex + veto/relleno). Con ex-8 (`extraccion_llm_actividad`) la actividad y
    la nacionalidad las decide el extractor "LLM primero": tests/test_ex8_actividad_nacionalidad.py."""


def _closed(allocation=None, colombian=True):
    state = ConversationState(conversation_id="t7b")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "resumen"}]
    state.detected_activity = "certified_diving"
    state.detected_service_id = "2_dives_1_day"
    state.is_certified = state.detected_is_certified = True
    state.detected_group_size = sum(allocation.values()) if allocation else 2
    state.detected_group_allocation = allocation
    state.location = state.detected_location = "cartagena"
    state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
    state.is_colombian = colombian
    core._build_cart_from_slots(state)
    return state


async def _send(state, message, verify=None):
    # En la peticion del turno, el valor de un campo sabido vuelve en el relleno y la
    # contradiccion sale de compararlo con lo guardado (hallazgo J, 2026-09-15).
    _senales = AsyncMock(return_value={})
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})), \
         patch.object(core_extraction, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "extract_and_verify", create=True,
                      new=AsyncMock(side_effect=lambda *a, **k: (dict(verify or {}), {}))), \
         patch.object(core, "verify_fields", create=True, new=AsyncMock(return_value=verify or {})), \
         patch.object(core_routing, "detect_special_signals", new=_senales), patch.object(core_extraction, "detect_special_signals", new=_senales), \
         patch.object(core_close, "_acuse_por_codigo", new=lambda *a, **k: ""), \
         patch.object(core_extraction, "resolve_slot_answer", new=AsyncMock(return_value={})):
        return await route_message(state, message)


@pytest.mark.asyncio
async def test_explicit_correction_after_the_price_changes_the_currency(extractor_dice):
    # ex-9b paso 3: la nacionalidad la lee el extractor del turno (`extractor_dice`, conftest); sin él, en los tests iba
    # por la pista del regex.
    extractor_dice({"espera, en realidad no somos colombianos": {"is_colombian": False}})
    state = _closed()
    await _send(state, "espera, en realidad no somos colombianos", verify={"is_colombian": False})
    assert state.is_colombian is False
    assert state.mixed_display_currency == "USD"
    assert state.pending_correction is None


@pytest.mark.asyncio
async def test_same_value_does_not_ask(extractor_dice):
    # ex-9b paso 3: la nacionalidad, leída por el extractor del turno (con el flag y el extractor caído no se leía nada y
    # el test pasaba sin comparar).
    extractor_dice({"somos colombianos, sí": {"is_colombian": True}})
    state = _closed()
    await _send(state, "somos colombianos, sí")
    assert state.pending_correction is None


def _waiting_location():
    state = ConversationState(conversation_id="t7b-anclada")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola, somos 3 buzos certificados y colombianos"}]
    state.detected_activity = "certified_diving"
    state.is_certified = state.detected_is_certified = True
    state.detected_group_size = 3
    state.is_colombian = True
    state.core_pending_slot = core.SLOT_LOCATION
    return state


@pytest.mark.asyncio
async def test_known_field_proposals_riding_on_the_answer_to_another_question_are_dropped():
    """Guarda (b): "desde cartagena" contesta la ubicacion; lo que el LLM re-derive del
    historial para otros campos no se confirma (medido en conversacion real)."""
    state = _waiting_location()
    await _send(state, "desde cartagena", verify={"group_size": 9})
    assert state.location == "cartagena"
    assert state.pending_correction is None
    assert state.detected_group_size == 3


@pytest.mark.asyncio
async def test_split_with_an_ambiguous_course_level_waits_for_the_answer(extractor_dice):
    """b05 (owner): "2 open water y 3 snorkel" no dice si tienen el nivel o lo quieren;
    se pregunta y no se guarda el reparto con el curso aunque el LLM lo rellene."""
    # ex-9b paso 3: el mismo reparto, leído por el extractor del turno (con el flag y el extractor caído no se leía
    # nada y el test pasaba sin probar la guarda).
    extractor_dice({"2 open water y 3 snorkel": {"group_allocation": {"padi_open_water": 2, "snorkel": 3}}})
    state = ConversationState(conversation_id="t7b-b05")
    state.language = "es"
    state.detected_group_size = 5
    split = {"group_allocation": {"padi_open_water": 2, "snorkel": 3}}
    with patch.object(core, "extract_and_verify", create=True, new=AsyncMock(return_value=(split, {}))), \
         patch.object(core_extraction, "fill_gaps", new=AsyncMock(return_value=split)):
        await core._understand(state, "2 open water y 3 snorkel")
    assert state.needs_cert_or_course is True
    assert state.detected_group_allocation is None


@pytest.mark.asyncio
async def test_own_change_of_activity_carries_a_single_activity_split(extractor_dice):
    extractor_dice({"mejor snorkel": {"activity": "snorkel"}})  # ex-9b paso 3: la actividad elegida, del extractor
    state = ConversationState(conversation_id="t7b-mejor")
    state.language = "es"
    state.history = [{"role": "user", "content": "hola"}]
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.detected_group_size = 2
    state.detected_group_allocation = {"certified_diving": 2}
    state.location = state.detected_location = "cartagena"
    state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_NATIONALITY
    await _send(state, "mejor snorkel")
    assert state.detected_group_allocation == {"snorkel": 2}
