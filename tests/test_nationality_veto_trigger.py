"""Trigger PROPIO del veto de `is_colombian` (tarea 3 de
docs/robustness/NEXT-SESSION-PROMPT.md, 2026-09-14).

Con el trigger generico ("resuelto este turno") el LLM se consultaba en TODO
turno donde el regex resolvia la nacionalidad, incluidas las negaciones
compactas que el regex acierta y el LLM confunde ("ninguno colombiano" -> True,
visto en el eval-set). El veto se borró en MEJ-1 (21-oct); la señal de
ambigüedad sigue porque la usa `_detect_nationality`. Es el mismo
fallo que se midio con `activity` (89%->73%) y la misma salida: verificar solo
cuando el propio mensaje se delata como ambiguo.

La senal de ambiguedad reutiliza los MISMOS patrones que `_detect_nationality`
(nunca una lista nueva de fraseos): hay polaridad contradictoria si, ademas de
lo que el detector eligio, queda una marca de la polaridad contraria fuera del
tramo que la produjo.
lat-11 T6d (26-oct): fuera los tests de `nationality_is_ambiguous` e IntentDetector.detect (se quitaron; la
nacionalidad la decide el extractor). Queda la regla del grupo mixto.
"""

from src.agents import supervisor
from src.flows.state import ConversationState


def test_mixed_nationality_group_pays_in_usd():
    """Decision del owner (2026-09-14): grupo con nacionalidades mixtas -> USD para
    todo el grupo (antes: pago individual por nacionalidad)."""
    state = ConversationState(conversation_id="mixed")
    state.language = "es"
    resp = supervisor._mixed_nationality_response(state, "dos somos colombianos pero uno es extranjero")
    assert state.is_colombian is False
    assert "USD" in resp and "todo el grupo" in resp
