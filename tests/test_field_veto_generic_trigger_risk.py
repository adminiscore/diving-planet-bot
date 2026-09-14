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
async def test_own_trigger_keeps_the_llm_away_from_the_correct_negation_case():
    """El riesgo que caracterizaba este test: con el trigger generico, si el
    LLM se equivoca en una negacion compacta -- comportamiento real observado
    en el eval-set contra PRE -- el veto en cutover sobreescribia el valor
    correcto del regex por el incorrecto.

    Desde 2026-09-14 `is_colombian` tiene `should_verify` propio
    (`_nationality_should_verify`, polaridad contradictoria), que era la
    condicion que este test pedia. "ninguno colombiano" no es ambiguo, asi que
    el LLM ni se consulta y el valor correcto se conserva aunque el LLM
    hubiera contestado mal. `is_certified` y `location` siguen con el trigger
    generico: el aviso de arriba sigue valiendo para ellos."""
    detector = IntentDetector()
    state = ConversationState(conversation_id="veto-risk-is-colombian-test")
    intent = detector.detect(_NEGATION_MSG, state)

    # El regex ya acierta por si solo, sin ayuda del LLM.
    assert intent.is_colombian is False
    assert "is_colombian" in intent.detected_fields

    # Simula el error real observado del LLM en este tipo de mensaje
    # (negacion compacta mal interpretada como afirmacion). Si el trigger
    # dejara pasar el caso, este mock lo pisaria.
    llm = AsyncMock(return_value={"is_colombian": True})
    with patch.object(supervisor.settings, "llm_nationality_veto_cutover", True), \
         patch.object(supervisor, "verify_fields", new=llm):
        await supervisor._maybe_veto_resolved_field_via_llm("is_colombian", _NEGATION_MSG, intent, state)

    # Si esto vuelve a fallar es que alguien quito o ensancho el trigger propio:
    # no "arreglar" el test, sino volver a medir (eval-set) antes de tocarlo.
    llm.assert_not_called()
    assert intent.is_colombian is False
