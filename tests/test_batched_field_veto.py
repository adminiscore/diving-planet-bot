"""Tests del veto AGRUPADO: varios campos verificados en UNA sola peticion
(`supervisor._maybe_veto_resolved_fields_via_llm` + `llm_extractor.verify_fields`).

Por que agrupado (medido en vivo, 2026-09-10, docs/robustness/progress-log.md):
el recurso escaso de la cuenta OpenAI son las PETICIONES/dia (se agoto el
limite de 10.000 RPD con los tokens intactos: 199.997 de 200.000 libres,
reponiendose cada minuto). Verificar N campos en N peticiones gastaba justo
el recurso limitado; agrupados dan la misma informacion por 1 peticion.

Lo critico a demostrar aqui es que agrupar NO mezcla las semanticas por
campo: la LLAMADA se hace si algun campo tiene alguna bandera encendida,
pero la APLICACION es POR CAMPO segun SU PROPIA bandera de cutover.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.state import ConversationState

# Mensaje ambiguo para `activity` (dispara 2+ categorias, su should_verify)
# y que ademas trae certificacion y ubicacion.
_MSG = "somos 4 certificados, estamos en bocagrande y queremos el open water aunque nunca hemos buceado"


def _intent() -> DetectedIntent:
    return DetectedIntent(
        activity="minicourse", service_id="minicourse",
        is_certified=False, location="island", group_size=2,
        detected_fields=["activity", "is_certified", "location", "group_size"],
    )


@pytest.mark.asyncio
async def test_all_flags_off_makes_no_call_at_all():
    intent, state = _intent(), ConversationState(conversation_id="batch-off")
    with patch.object(supervisor, "verify_fields",
                      new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_veto_resolved_fields_via_llm(_MSG, intent, state)
    assert intent.activity == "minicourse"


@pytest.mark.asyncio
async def test_one_call_covers_every_eligible_field():
    """El punto de todo el rediseño: N campos elegibles = 1 peticion."""
    intent, state = _intent(), ConversationState(conversation_id="batch-one-call")
    fake = AsyncMock(return_value={})
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor.settings, "llm_certification_veto_shadow_mode", True), \
         patch.object(supervisor.settings, "llm_location_veto_shadow_mode", True), \
         patch.object(supervisor.settings, "llm_group_size_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=fake):
        await supervisor._maybe_veto_resolved_fields_via_llm(_MSG, intent, state)

    assert fake.await_count == 1, "debe ser UNA sola peticion para todos los campos"
    requested = fake.await_args.args[0]
    assert set(requested) == {"activity", "is_certified", "location", "group_size"}


@pytest.mark.asyncio
async def test_shadow_and_cutover_fields_in_the_same_call_keep_their_own_semantics():
    """El matiz critico de agrupar: en la MISMA peticion, un campo en cutover
    se aplica y otro en shadow-mode NO, aunque ambos discrepen."""
    intent, state = _intent(), ConversationState(conversation_id="batch-mixed-modes")
    disagreements = {
        "activity": "padi_open_water",   # cutover -> se aplica
        "is_certified": True,            # shadow  -> NO se aplica
        "location": "cartagena",         # shadow  -> NO se aplica
        "group_size": 4,                 # cutover -> se aplica
    }
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor.settings, "llm_certification_veto_shadow_mode", True), \
         patch.object(supervisor.settings, "llm_certification_veto_cutover", False), \
         patch.object(supervisor.settings, "llm_location_veto_shadow_mode", True), \
         patch.object(supervisor.settings, "llm_location_veto_cutover", False), \
         patch.object(supervisor.settings, "llm_group_size_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value=disagreements)):
        await supervisor._maybe_veto_resolved_fields_via_llm(_MSG, intent, state)

    # Cutover: aplicados (activity ademas arrastra su service_id)
    assert intent.activity == "padi_open_water"
    assert intent.service_id == "open_water"
    assert intent.group_size == 4
    # Shadow: medidos pero NO aplicados
    assert intent.is_certified is False
    assert intent.location == "island"


@pytest.mark.asyncio
async def test_only_eligible_fields_are_requested():
    """Un campo con banderas encendidas pero que no se resolvio este turno no
    entra en la peticion (no se paga por verificar lo que no cambio)."""
    intent = DetectedIntent(
        activity="minicourse", is_certified=False,
        detected_fields=["activity"],   # is_certified NO se resolvio este turno
    )
    state = ConversationState(conversation_id="batch-eligible")
    fake = AsyncMock(return_value={})
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor.settings, "llm_certification_veto_shadow_mode", True), \
         patch.object(supervisor, "verify_fields", new=fake):
        await supervisor._maybe_veto_resolved_fields_via_llm(_MSG, intent, state)

    assert fake.await_args.args[0] == ["activity"]


@pytest.mark.asyncio
async def test_failure_degrades_silently_leaving_every_field_untouched():
    intent, state = _intent(), ConversationState(conversation_id="batch-error")
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor.settings, "llm_group_size_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_veto_resolved_fields_via_llm(_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.group_size == 2
