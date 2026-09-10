"""Documenta un hallazgo real (eval-set contra PRE, 2026-09-10, ver
docs/robustness/progress-log.md Fase 11): el trigger GENERICO del veto
por-campo (`field in regex_intent.detected_fields`, sin exigir ambiguedad)
tiene el MISMO fallo que se midio y se revirtio en produccion para
`activity` -- el LLM se llama en TODO turno donde el campo se resuelve,
incluidos los casos claros, y su propio sesgo puede pisar una respuesta ya
correcta del regex.

`activity` recupero un `should_verify` propio (ambiguedad real, ver
test_activity_veto.py). `is_certified`/`is_colombian`/`location` SIGUEN
usando el trigger generico sin restriccion -- seguro HOY solo porque sus 6
flags (llm_certification/nationality/location_veto_shadow_mode/_cutover)
estan en False en todas partes (paridad preventiva, sin evidencia de bug
real que los motive). Este test deja constancia, con un caso real del
eval-set, de que activar `llm_nationality_veto_cutover` TAL COMO ESTA HOY
repetiria el mismo error: NO activarlo sin antes darle a `is_colombian` (y
revisar `location`) un `should_verify` como el de `activity`, o sin verificar
primero que el problema no se reproduce con el modelo/prompt actuales.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState

# Caso real del eval-set (docs/robustness/eval-set.json,
# "hist-nationality-answer-must-not-fill-pending-safety"): el regex YA
# resuelve esto bien via su guarda de negacion -- "ninguno colombiano" =
# nadie es colombiano.
_NEGATION_MSG = "ninguno colombiano"


@pytest.mark.asyncio
async def test_generic_trigger_would_let_llm_override_correct_negation_case():
    """Caracteriza el riesgo actual: con el trigger generico (sin
    should_verify), si el LLM se equivoca en un caso de negacion compacta
    -- comportamiento real observado en el eval-set contra PRE -- el veto
    en cutover SI sobreescribe el valor correcto del regex por el
    incorrecto. Este test debe seguir en verde mientras is_colombian no
    tenga su propio should_verify: es la prueba de que el flag de cutover
    NO debe activarse todavia tal como esta montado el mecanismo."""
    detector = IntentDetector()
    state = ConversationState(conversation_id="veto-risk-is-colombian-test")
    intent = detector.detect(_NEGATION_MSG, state)

    # El regex ya acierta por si solo, sin ayuda del LLM.
    assert intent.is_colombian is False
    assert "is_colombian" in intent.detected_fields

    # Simula el error real observado del LLM en este tipo de mensaje
    # (negacion compacta mal interpretada como afirmacion).
    with patch.object(supervisor.settings, "llm_nationality_veto_cutover", True), \
         patch.object(supervisor, "verify_field", new=AsyncMock(return_value=True)):
        await supervisor._maybe_veto_resolved_field_via_llm("is_colombian", _NEGATION_MSG, intent, state)

    # Comportamiento actual (sin should_verify): el LLM pisa la respuesta
    # correcta. Si esta asercion alguna vez falla porque is_colombian ganó
    # su propio should_verify (o porque el flag esta protegido de otra
    # forma), actualizar este test para reflejar el nuevo diseño -- no
    # borrarlo sin mas: su proposito es impedir que se active el cutover
    # sin resolver esto primero.
    assert intent.is_colombian is True
