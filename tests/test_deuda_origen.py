"""DEUDA-ORIGEN (26-oct; decisión «no adivinar» de Gadea del 18-oct, frontera en Coral #1970/#1971).

«Estaremos visitando Cartagena y queríamos coordinar inmersiones en Isla del Rosario» ponía location=cartagena 3/3 (el
prompt del extractor traía «estaremos visitando Cartagena» y «vamos a Cartagena» como ejemplos de cartagena, de ex-5) y
Jev lo afirmaba. El viaje no dice la salida: sin origen van los dos precios y se pregunta una vez. Estar allí ahora,
salir de allí o bucear allí sí es cartagena; alojarse en las islas, island. Banco: docs/robustness/lat/banco-deuda-origen.json
(A = PRE 10/20, B 20/20).
"""

import pytest

from src.agents import conversational_core as core
from src.agents import extractor_turno as ex
from src.agents import redactor_hechos
from src.flows.state import ConversationState

MSG = "Estaremos visitando Cartagena y queremos bucear en las Islas del Rosario"


def _estado(lectura=None, jev=("cartagena", 0.95)) -> ConversationState:
    st = ConversationState(conversation_id="deuda-origen", language="es")
    if lectura is not None:
        st._lectura_del_turno = lectura
    st._jev_lugar = {"choice": jev[0], "confidence": jev[1]}
    return st


@pytest.mark.parametrize("lectura,calla", [
    ((MSG, {}), True),
    ((MSG, {"activity": "certified_diving"}), True),
    ((MSG, {"location": "cartagena"}), False),
    ((MSG, None), False),   # el extractor falló: no se sabe
])
def test_el_extractor_calla_el_lugar(lectura, calla):
    assert core._el_extractor_calla_el_lugar(_estado(lectura)) is calla


def test_sin_lectura_no_se_sabe():
    assert core._el_extractor_calla_el_lugar(_estado()) is False


def test_con_el_extractor_callado_jev_no_fija_el_origen():
    assert core._jev_dice_el_lugar(_estado((MSG, {}))) is False
    assert core._jev_dice_el_lugar(_estado((MSG, None))) is True     # sin lectura, Jev sigue de respaldo (gen-15)
    assert core._jev_dice_el_lugar(_estado()) is True


def test_el_redactor_no_cotiza_un_origen_que_solo_supone_jev():
    assert redactor_hechos._origen(_estado(), {}, leido=True) is None
    assert redactor_hechos._origen(_estado(), {}, leido=False) == "cartagena"
    assert redactor_hechos._origen(_estado(), {"location": "island"}, leido=True) == "island"


@pytest.mark.parametrize("sistema", [ex.SISTEMA_ES, ex.SISTEMA_EN])
def test_el_viaje_no_es_ejemplo_de_cartagena(sistema):
    regla = next(ln for ln in sistema.splitlines() if ln.startswith("- location:"))
    cartagena, _, resto = regla.partition("→ cartagena.")
    assert "visit" not in cartagena.lower() and "vamos a cartagena" not in cartagena.lower()
    assert "null" in resto.split("Alojado")[0].split("Staying")[0]
