"""ex-9b paso 5 (19-oct). La misma idea en dos sitios: si la IA ha contestado este turno, manda la IA, y la lista de
palabras o el regex solo decide si la IA calla (el respaldo a propósito). Los flags `regex_solo_si_ia_calla` y
`pregunta_y_correccion_por_jev` se promocionaron y se quitaron en la limpieza ex9b: aquí se prueban los dos lados,
la IA contesta y la IA calla.

- Link roto, tema sensible, cancelar/cambiar, contacto, "hablar con" y DIVE TO HEAL. La regla única es
  `supervisor.regex_decide`, y la usan el router, los nodos, `setup` y la cascada. Si solo la mirara el router, el nodo
  de reserva volvía a ver "hablar con" y pasaba a una persona igualmente.
- "¿Trae una pregunta?" (`asks_question`) y "¿corrige un dato?" (`corrects`) en el núcleo."""

import pytest

from src.agents import supervisor
from src.agents.conversational_core import _turn_has_question
from src.agents.nucleo.extractor import _has_correction_cue
from src.agents.nucleo.setup import _setup_phase
from src.flows.state import ConversationState
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_BOOKING, ROUTE_SAFETY

# Lo que deja Jev cuando contesta y no marca nada (siempre trae al menos `asks_question`).
JEV_CONTESTA = {"asks_question": False}
ESPOSA = "quiero hablar con mi esposa antes de reservar"


def _estado() -> ConversationState:
    return ConversationState(conversation_id="ex9b-5", language="es")


@pytest.mark.parametrize("senales, decide", [({}, True), (None, True), (JEV_CONTESTA, False)])
def test_la_regla_unica(senales, decide):
    assert supervisor.regex_decide(senales) is decide


@pytest.mark.parametrize("senales, ruta", [
    (JEV_CONTESTA, ROUTE_BOOKING),  # manda Jev
    ({}, ROUTE_SAFETY),             # la IA calla: decide la lista
])
def test_el_router(senales, ruta):
    assert classify_route(_estado(), ESPOSA, senales) == ruta


@pytest.mark.parametrize("senales, declina", [(JEV_CONTESTA, False), ({}, True)])
async def test_setup_no_declina_la_reserva_si_jev_dice_que_no_pide_una_persona(senales, declina):
    resultado = await _setup_phase(_estado(), ESPOSA, dict(senales))
    assert (resultado is None) is declina


async def test_wants_human_de_jev_sigue_pasando_a_una_persona():
    assert await _setup_phase(_estado(), "pásame con alguien", {"wants_human": True, "asks_question": False}) is None


@pytest.mark.parametrize("senales, pregunta", [
    ({"asks_question": False}, False),  # manda Jev (el regex veía "hay" y lo tomaba por pregunta)
    ({}, True),                         # Jev calla: el regex de siempre
])
def test_trae_una_pregunta(senales, pregunta):
    assert _turn_has_question("hay un niño de 5 años", senales) is pregunta


def test_el_signo_de_interrogacion_sigue_contando():
    assert _turn_has_question("somos 4, sale el sábado?", {"asks_question": False}) is True


def test_jev_encuentra_la_pregunta_que_el_regex_no_ve():
    assert _turn_has_question("perfecto, como pago", {"asks_question": True}) is True


@pytest.mark.parametrize("jev, corrige", [
    (False, False),  # manda Jev ("perdón" solo ya no aplica el dato sin confirmarlo)
    (None, True),    # Jev calla: el regex de siempre
    (True, True),
])
def test_corrige_un_dato(jev, corrige):
    estado = _estado()
    estado._jev_corrects = jev
    assert _has_correction_cue(estado, "perdón, ¿cuánto cuesta?") is corrige
