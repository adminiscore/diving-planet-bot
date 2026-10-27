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
CALN-6 paso 2 (27-oct): fuera el texto fijo del grupo mixto (`_mixed_nationality_response`, que cerraba con «¿…o
prefieres volver al menú principal?»); la regla la dicen el escritor con sus hechos y el aviso «grupo-mixto-todo-usd».
"""

from src.flows import hechos
from src.flows.state import ConversationState


def test_mixed_nationality_group_pays_in_usd():
    """Decision del owner (2026-09-14): grupo con nacionalidades mixtas -> USD para
    todo el grupo (antes: pago individual por nacionalidad). La regla llega al escritor en sus hechos."""
    state = ConversationState(conversation_id="mixed", language="es")
    state.mixed_nationality_notice, state.is_colombian, state.location = True, False, "cartagena"
    bloque = hechos.hechos(state, ["precio"], ["snorkel"])[0]
    assert bloque["moneda"] == "USD"
    assert "USD" in bloque["regla_moneda"] and "grupo" in bloque["regla_moneda"]
