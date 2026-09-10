"""Tests for the LLM `group_size` field-veto (docs/multi-agent-refactor-plan.md,
hallazgo en vivo bateria sintetica, 2026-09-10):
`supervisor._maybe_veto_resolved_field_via_llm("group_size", ...)`.

Motivo real: "vengo con mi pareja y nuestros dos hijos" resuelve
`group_size=2` (el patron `pareja`->2 gana y nunca suma a los hijos) -- el
regex CONTESTA CON CONFIANZA y se equivoca, a diferencia de un hueco (None)
que ya cubriria `fill_gaps` (cuya regla es nunca tocar un campo ya
resuelto). Un intento de arreglar esto por regex (excluir "mi/tu/su pareja")
rompio un caso real validado por el owner
(test_owner_conversations_fase1.py::test_scenario3a_couple_group_size_two,
donde "con mi pareja" SI debe valer 2 sola) -- revertido. Se deja en manos
de este mecanismo en su lugar.

`group_size` usa el trigger GENERICO (sin `should_verify` propio, como
`is_certified`/`is_colombian`/`location`) -- ambos flags en `False` por
defecto en todas partes: paridad con el resto, shadow-mode primero, nunca
cutover sin datos reales que lo respalden (leccion de la regresion de
`activity`, ver test_field_veto_generic_trigger_risk.py).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState

_REAL_BUG_MSG = "vengo con mi pareja y nuestros dos hijos"


@pytest.mark.asyncio
async def test_off_by_default_does_not_call_llm():
    detector = IntentDetector()
    state = ConversationState(conversation_id="gsize-veto-off-test")
    intent = detector.detect(_REAL_BUG_MSG, state)
    assert intent.group_size == 2  # el bug real: subcuenta

    with patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await supervisor._maybe_veto_resolved_field_via_llm("group_size", _REAL_BUG_MSG, intent, state)
    assert intent.group_size == 2


@pytest.mark.asyncio
async def test_shadow_mode_logs_the_real_undercounting_bug_but_never_mutates():
    """El caso real de hoy: shadow-mode debe DETECTAR la discrepancia (para
    que quede en los logs) sin aplicar nada."""
    detector = IntentDetector()
    state = ConversationState(conversation_id="gsize-veto-shadow-test")
    intent = detector.detect(_REAL_BUG_MSG, state)
    assert intent.group_size == 2

    with patch.object(supervisor.settings, "llm_group_size_veto_shadow_mode", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={"group_size": 4})):
        await supervisor._maybe_veto_resolved_field_via_llm("group_size", _REAL_BUG_MSG, intent, state)
    assert intent.group_size == 2  # shadow: nunca muta


@pytest.mark.asyncio
async def test_cutover_mode_would_correct_the_real_undercounting_bug():
    detector = IntentDetector()
    state = ConversationState(conversation_id="gsize-veto-cutover-test")
    intent = detector.detect(_REAL_BUG_MSG, state)
    assert intent.group_size == 2

    with patch.object(supervisor.settings, "llm_group_size_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={"group_size": 4})):
        await supervisor._maybe_veto_resolved_field_via_llm("group_size", _REAL_BUG_MSG, intent, state)
    assert intent.group_size == 4


@pytest.mark.asyncio
async def test_cutover_mode_no_mutation_when_llm_agrees():
    detector = IntentDetector()
    state = ConversationState(conversation_id="gsize-veto-agree-test")
    intent = detector.detect("somos pareja", state)
    assert intent.group_size == 2

    with patch.object(supervisor.settings, "llm_group_size_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={})):
        await supervisor._maybe_veto_resolved_field_via_llm("group_size", "somos pareja", intent, state)
    assert intent.group_size == 2


@pytest.mark.asyncio
async def test_veto_failure_degrades_silently_to_regex_only():
    detector = IntentDetector()
    state = ConversationState(conversation_id="gsize-veto-error-test")
    intent = detector.detect(_REAL_BUG_MSG, state)

    with patch.object(supervisor.settings, "llm_group_size_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_veto_resolved_field_via_llm("group_size", _REAL_BUG_MSG, intent, state)
    assert intent.group_size == 2
