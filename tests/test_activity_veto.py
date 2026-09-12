"""Tests for the LLM `activity` field-veto (docs/multi-agent-refactor-plan.md,
hallazgo en vivo conversacion real "purple-sun-590", 2026-09-03, y conversacion
real 913, 2026-09-10): `supervisor._maybe_veto_resolved_field_via_llm("activity", ...)`.

Unlike `_maybe_apply_llm_extraction_cutover` (fills gaps only), this CAN
correct an `activity` the regex already resolved -- but only when `activity`
was resolved THIS turn (`"activity" in intent.detected_fields`) AND the
message genuinely looks ambiguous (`activity`'s `should_verify`,
`matched_activity_categories(message) >= 2`). A broader trigger ("resolved
this turn" alone, no ambiguity required) was tried and measured live against
PRE with a real eval-set run: it regressed `activity` agreement from ~95% to
73%, because the LLM gets called on every clear-cut turn too and its own bias
(toward `minicourse` on bare messages) overrides the regex's correct default
-- see docs/robustness/progress-log.md, Fase 11 "Corrección urgente". The
genuinely-new-phrasing gap from conversation 913 ("primer nivel de buceo")
is closed a safer way instead: a new pattern in `_PADI_COURSE_PATTERNS`
(intent_detector.py) makes that message trigger 2 real categories, so the
restored ambiguity trigger catches it without widening the LLM call surface.
Critical properties to prove: off by default (no LLM call), no value
resolved (no LLM call), not resolved THIS turn (no LLM call even with flags
on), not ambiguous (no LLM call even with flags on and resolved this turn),
shadow mode logs but never mutates, cutover mode mutates activity +
service_id (via the `activity`-specific `apply` side-effect), agreement
means no mutation, and any failure degrades silently to regex-only.
"""

import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.state import ConversationState

_AMBIGUOUS_MSG = "Me gustaria sacarme el open water, pero nunca he buceado"
_UNAMBIGUOUS_MSG = "quiero hacer snorkel"


async def _veto(message: str, intent: DetectedIntent, state: ConversationState) -> None:
    await supervisor._maybe_veto_resolved_field_via_llm("activity", message, intent, state)


@pytest.mark.asyncio
async def test_off_by_default_does_not_call_llm():
    intent = DetectedIntent(activity="minicourse", detected_fields=["activity"])
    state = ConversationState(conversation_id="veto-off-test")

    with patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await _veto(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"


@pytest.mark.asyncio
async def test_no_activity_resolved_skips_veto():
    """Sin `activity` resuelto no hay nada que vetar -- eso lo cubre el
    cutover de huecos (_maybe_apply_llm_extraction_cutover), no este veto."""
    intent = DetectedIntent(activity=None)
    state = ConversationState(conversation_id="veto-no-activity-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await _veto(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity is None


@pytest.mark.asyncio
async def test_not_resolved_this_turn_skips_llm_call():
    """`activity` tiene un valor pero NO se marco como resuelto ESTE turno
    (detected_fields vacio) -- nada nuevo que verificar, se confia en el
    regex sin gastar una llamada LLM."""
    intent = DetectedIntent(activity="snorkel")  # detected_fields default: []
    state = ConversationState(conversation_id="veto-not-this-turn-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await _veto(_UNAMBIGUOUS_MSG, intent, state)
    assert intent.activity == "snorkel"


@pytest.mark.asyncio
async def test_resolved_this_turn_but_not_ambiguous_skips_llm_call():
    """Regresion medida en vivo (2026-09-10, docs/robustness/progress-log.md
    Fase 11): resuelto ESTE turno ya NO basta por si solo para `activity` --
    si el mensaje no dispara 2+ categorias (`_activity_should_verify`), no se
    llama al LLM aunque `detected_fields` lo marque como recien resuelto.
    Sin este segundo guard, el eval-set demostro una caida real de
    ~95% a 73% en produccion."""
    intent = DetectedIntent(activity="snorkel", detected_fields=["activity"])
    state = ConversationState(conversation_id="veto-resolved-not-ambiguous-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        await _veto(_UNAMBIGUOUS_MSG, intent, state)
    assert intent.activity == "snorkel"


@pytest.mark.asyncio
async def test_shadow_mode_logs_but_never_mutates():
    intent = DetectedIntent(activity="minicourse", service_id="minicourse", detected_fields=["activity"])
    state = ConversationState(conversation_id="veto-shadow-test")

    with patch.object(supervisor.settings, "llm_activity_veto_shadow_mode", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={"activity": "padi_open_water"})):
        await _veto(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.service_id == "minicourse"


@pytest.mark.asyncio
async def test_cutover_mode_applies_llm_activity_and_service_id():
    intent = DetectedIntent(activity="minicourse", service_id="minicourse", detected_fields=["activity"])
    state = ConversationState(conversation_id="veto-cutover-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={"activity": "padi_open_water"})):
        await _veto(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "padi_open_water"
    assert intent.service_id == "open_water"
    assert "activity" in intent.detected_fields


@pytest.mark.asyncio
async def test_cutover_mode_no_mutation_when_llm_agrees():
    """verify_fields no devuelve el campo cuando el LLM coincide con el regex --
    nada que aplicar."""
    intent = DetectedIntent(activity="minicourse", service_id="minicourse", detected_fields=["activity"])
    state = ConversationState(conversation_id="veto-agree-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(return_value={})):
        await _veto(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.service_id == "minicourse"


@pytest.mark.asyncio
async def test_veto_failure_degrades_silently_to_regex_only():
    intent = DetectedIntent(activity="minicourse", service_id="minicourse", detected_fields=["activity"])
    state = ConversationState(conversation_id="veto-error-test")

    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await _veto(_AMBIGUOUS_MSG, intent, state)
    assert intent.activity == "minicourse"
    assert intent.service_id == "minicourse"


@contextlib.contextmanager
def _veto_returns(disagreements: dict, gaps_patch: dict | None = None):
    """Mockea las DOS vias por las que `_understand` puede obtener el veto.

    Desde la fusion de peticiones (2026-09-12), un turno que tiene huecos Y
    campos que verificar pasa por `conversational_core.extract_and_verify`
    (1 peticion) en vez de por `supervisor.verify_fields` (2). Un test e2e que
    solo mockee una de las dos queda mudo -- y peor: se cuela hasta la API de
    verdad. Se mockean ambas con el mismo resultado para que el test siga
    probando la conducta y no la ruta interna que toque ese dia.
    """
    from src.agents import conversational_core as cc

    with patch.object(supervisor, "verify_fields",
                      new=AsyncMock(return_value=disagreements)), \
         patch.object(cc, "extract_and_verify",
                      new=AsyncMock(return_value=(gaps_patch or {}, disagreements))):
        yield


@pytest.mark.asyncio
async def test_real_bug_message_end_to_end_via_understand():
    """Reproduce el flujo real (_understand, conversational_core.py) con el
    mensaje real del hallazgo en vivo -- con el veto en cutover, la actividad
    final debe ser padi_open_water/open_water, no minicourse."""
    from src.agents.conversational_core import _understand

    state = ConversationState(conversation_id="veto-e2e-test")
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         _veto_returns({"activity": "padi_open_water"}):
        intent, _carry = await _understand(state, _AMBIGUOUS_MSG)
    assert intent.activity == "padi_open_water"
    assert intent.service_id == "open_water"


@pytest.mark.asyncio
async def test_real_conv_913_message_end_to_end_via_understand():
    """Conversacion real 913 (2026-09-10): 'primer nivel de buceo' solo
    matcheaba 1 categoria de `matched_activity_categories` (la incorrecta) --
    el veto ANTIGUO (trigger de ambiguedad) nunca se disparaba para este
    mensaje. El nuevo trigger ('resuelto este turno') si lo cubre."""
    from src.agents.conversational_core import _understand

    state = ConversationState(conversation_id="veto-conv913-test")
    msg = "Pues me gustaria sacarme el primer nivel de buceo"
    with patch.object(supervisor.settings, "llm_activity_veto_cutover", True), \
         _veto_returns({"activity": "padi_open_water"}):
        intent, _carry = await _understand(state, msg)
    assert intent.activity == "padi_open_water"
    assert intent.service_id == "open_water"



# Nota: los tests que fijaban "el prompt enumera el enum de `activity`" vivieron
# aqui un rato y se movieron a tests/test_prompt_enum_enumeration.py, que lo
# comprueba para TODOS los campos con enum y en los DOS prompts que los
# consumen (fill_gaps y el veto) en vez de solo para este campo. El hallazgo que
# los motivo (el modelo devolvia 'certificarse') esta documentado alli.
