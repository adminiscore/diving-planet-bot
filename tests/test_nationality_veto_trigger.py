"""Trigger PROPIO del veto de `is_colombian` (tarea 3 de
docs/robustness/NEXT-SESSION-PROMPT.md, 2026-09-14).

Con el trigger generico ("resuelto este turno") el LLM se consultaba en TODO
turno donde el regex resolvia la nacionalidad, incluidas las negaciones
compactas que el regex acierta y el LLM confunde ("ninguno colombiano" -> True,
visto en el eval-set; ver test_field_veto_generic_trigger_risk.py). Es el mismo
fallo que se midio con `activity` (89%->73%) y la misma salida: verificar solo
cuando el propio mensaje se delata como ambiguo.

La senal de ambiguedad reutiliza los MISMOS patrones que `_detect_nationality`
(nunca una lista nueva de fraseos): hay polaridad contradictoria si, ademas de
lo que el detector eligio, queda una marca de la polaridad contraria fuera del
tramo que la produjo.
"""

import pytest

from src.agents import supervisor
from src.agents.intent_detector import IntentDetector, nationality_is_ambiguous
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "ninguno colombiano",
    "ninguno es colombiano",
    "no soy colombiano",
    "no, somos extranjeros",
    "soy extranjero",
    "i'm not colombian",
    "nadie es colombiano, todos extranjeros",
    "soy colombiano",
    "somos colombianos",
    "soy de Medellin, quiero bucear",
])
def test_unambiguous_nationality_is_not_ambiguous(message):
    assert nationality_is_ambiguous(message) is False


@pytest.mark.parametrize("message", [
    # las dos polaridades a la vez, fuera del tramo negado
    "dos somos colombianos pero uno es extranjero",
    "yo soy colombiano y mi novia extranjera",
    "somos extranjeros pero vivimos en colombia",
    "no soy colombiano pero vivo en colombia",
    # afirmacion + negacion suelta que el detector no ve como tal
    "mi pareja es colombiana, yo no",
    "colombiano no, soy venezolano",
])
def test_contradictory_polarity_is_ambiguous(message):
    assert nationality_is_ambiguous(message) is True


def test_message_without_nationality_is_not_ambiguous():
    assert nationality_is_ambiguous("somos 4 y queremos bucear") is False
    assert nationality_is_ambiguous("no tenemos certificado") is False


def _intent(message):
    state = ConversationState(conversation_id="nat-trigger")
    return IntentDetector().detect(message, state), state


def test_nationality_spec_has_its_own_trigger():
    assert supervisor._VETO_FIELD_SPECS["is_colombian"].should_verify is not None


def test_trigger_skips_the_compact_negation_the_llm_gets_wrong():
    intent, state = _intent("ninguno colombiano")
    assert intent.is_colombian is False
    spec = supervisor._VETO_FIELD_SPECS["is_colombian"]
    assert spec.should_verify("ninguno colombiano", intent, state) is False


def test_trigger_fires_on_real_ambiguity():
    msg = "dos somos colombianos pero uno es extranjero"
    intent, state = _intent(msg)
    spec = supervisor._VETO_FIELD_SPECS["is_colombian"]
    assert spec.should_verify(msg, intent, state) is True


@pytest.mark.parametrize("message", [
    "somos extranjeros pero vivimos en colombia",
    "no soy colombiano pero vivo en colombia",
    "colombiano no, soy venezolano",
    "mi pareja es colombiana, yo no",
])
def test_detector_abstains_on_contradictory_nationality(message):
    """2026-09-14: con polaridad contradictoria el regex no decide (daba False a
    residentes, que pagan en COP, y True a "soy venezolano"). El hueco lo resuelve
    el LLM en la misma peticion del turno o el bot lo pregunta."""
    intent, _state = _intent(message)
    assert intent.is_colombian is None
    assert "is_colombian" not in intent.detected_fields


def test_mixed_nationality_group_pays_in_usd():
    """Decision del owner (2026-09-14): grupo con nacionalidades mixtas -> USD para
    todo el grupo (antes: pago individual por nacionalidad)."""
    state = ConversationState(conversation_id="mixed")
    state.language = "es"
    resp = supervisor._mixed_nationality_response(state, "dos somos colombianos pero uno es extranjero")
    assert state.is_colombian is False
    assert "USD" in resp and "todo el grupo" in resp
