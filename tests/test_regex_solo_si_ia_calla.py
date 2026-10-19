"""ex-9b paso 5 (19-oct). Dos flags con la misma idea: si la IA ha contestado este turno, manda la IA, y la lista de
palabras o el regex solo decide si la IA calla.

- `regex_solo_si_ia_calla`: link roto, tema sensible, cancelar/cambiar, contacto, "hablar con" y DIVE TO HEAL. La regla
  única es `supervisor.regex_decide`, y la usan el router, los nodos, `setup` y la cascada. Si solo la mirara el router,
  el nodo de reserva volvía a ver "hablar con" y pasaba a una persona igualmente.
- `pregunta_y_correccion_por_jev`: "¿trae una pregunta?" (`asks_question`) y "¿corrige un dato?" (`corrects`) en el
  núcleo."""

import pytest

from src.agents import supervisor
from src.agents.conversational_core import _turn_has_question
from src.agents.nucleo.extractor import _has_correction_cue
from src.agents.nucleo.setup import _setup_phase
from src.config import settings
from src.flows.state import ConversationState
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_BOOKING, ROUTE_SAFETY

# Lo que deja Jev cuando contesta y no marca nada (siempre trae al menos `asks_question`).
JEV_CONTESTA = {"asks_question": False}
ESPOSA = "quiero hablar con mi esposa antes de reservar"


def _estado() -> ConversationState:
    return ConversationState(conversation_id="ex9b-5", language="es")


@pytest.mark.parametrize("encendido, senales, decide", [
    (False, {}, True), (False, JEV_CONTESTA, True), (True, {}, True), (True, JEV_CONTESTA, False),
])
def test_la_regla_unica(monkeypatch, encendido, senales, decide):
    monkeypatch.setattr(settings, "regex_solo_si_ia_calla", encendido)
    assert supervisor.regex_decide(senales) is decide


@pytest.mark.parametrize("encendido, senales, ruta", [
    (False, JEV_CONTESTA, ROUTE_SAFETY),  # hoy: "hablar con" pasa a una persona aunque Jev diga que no
    (True, JEV_CONTESTA, ROUTE_BOOKING),  # con el flag manda Jev
    (True, {}, ROUTE_SAFETY),             # la IA calla: decide la lista, como hoy
])
def test_el_router(monkeypatch, encendido, senales, ruta):
    monkeypatch.setattr(settings, "regex_solo_si_ia_calla", encendido)
    assert classify_route(_estado(), ESPOSA, senales) == ruta


@pytest.mark.parametrize("encendido, senales, declina", [
    (False, JEV_CONTESTA, True), (True, JEV_CONTESTA, False), (True, {}, True),
])
async def test_setup_no_declina_la_reserva_si_jev_dice_que_no_pide_una_persona(monkeypatch, encendido, senales, declina):
    monkeypatch.setattr(settings, "regex_solo_si_ia_calla", encendido)
    resultado = await _setup_phase(_estado(), ESPOSA, dict(senales))
    assert (resultado is None) is declina


async def test_wants_human_de_jev_sigue_pasando_a_una_persona(monkeypatch):
    monkeypatch.setattr(settings, "regex_solo_si_ia_calla", True)
    assert await _setup_phase(_estado(), "pásame con alguien", {"wants_human": True, "asks_question": False}) is None


@pytest.mark.parametrize("encendido, senales, pregunta", [
    (False, {"asks_question": False}, True),  # hoy: el regex ve "hay" y lo toma por pregunta
    (True, {"asks_question": False}, False),  # con el flag manda Jev
    (True, {}, True),                         # Jev calla: el regex de siempre
])
def test_trae_una_pregunta(monkeypatch, encendido, senales, pregunta):
    monkeypatch.setattr(settings, "pregunta_y_correccion_por_jev", encendido)
    assert _turn_has_question("hay un niño de 5 años", senales) is pregunta


def test_el_signo_de_interrogacion_sigue_contando(monkeypatch):
    monkeypatch.setattr(settings, "pregunta_y_correccion_por_jev", True)
    assert _turn_has_question("somos 4, sale el sábado?", {"asks_question": False}) is True


def test_jev_encuentra_la_pregunta_que_el_regex_no_ve(monkeypatch):
    monkeypatch.setattr(settings, "pregunta_y_correccion_por_jev", True)
    assert _turn_has_question("perfecto, como pago", {"asks_question": True}) is True


@pytest.mark.parametrize("encendido, jev, corrige", [
    (False, False, True),  # hoy: "perdón" basta para aplicar el dato sin confirmarlo
    (True, False, False),  # con el flag manda Jev
    (True, None, True),    # Jev calla: el regex de siempre
    (True, True, True),
])
def test_corrige_un_dato(monkeypatch, encendido, jev, corrige):
    monkeypatch.setattr(settings, "pregunta_y_correccion_por_jev", encendido)
    estado = _estado()
    estado._jev_corrects = jev
    assert _has_correction_cue(estado, "perdón, ¿cuánto cuesta?") is corrige
