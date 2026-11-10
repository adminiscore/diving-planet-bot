"""Bloque 4R (Plan Gadea): el momento de reservar. Banco sin IA (docs/robustness/caln/diseno-bloque4r.md)."""
import pytest

from src.agents.compositor import _una_oferta_del_asesor
from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR
from src.agents.redactor_hechos import con_la_pieza
from src.flows.como_reserva import (
    ASESOR,
    ENLACE,
    HOTEL_PRIMERO,
    ORIGEN_PRIMERO,
    RECOGIDA_POR_CONFIRMAR,
    Entrega,
    entrega,
    recogida_por_confirmar,
)
from src.flows.que_preguntar import destapar_enlaces, tapar_enlaces
from src.flows.state import ConversationState

URL = "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"


# --- C5: el código no rompe enlaces -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    f"Reserva aquí: {URL}. ¿Te ayudo con algo?",
    f"*Reserva:* {URL}",
    f"Link: {URL}?",
    f"({URL})",
    f"Uno: {URL}, y otro: {URL.replace('/1?', '/2?')}.",
])
def test_tapar_y_destapar_devuelve_el_texto_y_el_enlace_entero(texto):
    tapado, enlaces = tapar_enlaces(texto)
    assert "book.divingplanet.org" not in tapado and "language=es" not in tapado
    assert all(e.startswith("https://book.divingplanet.org/book/") and e.endswith("language=es") for e in enlaces)
    assert destapar_enlaces(tapado, enlaces) == texto


@pytest.mark.parametrize("oferta", list(_OFERTA_DEL_ASESOR.values()))
def test_la_oferta_del_asesor_no_rompe_el_enlace_de_delante(oferta):
    # Antes: «https://book.divingplanet.language=es» (diseño 4R, M7).
    salida = _una_oferta_del_asesor(f"Reserva aquí: {URL}. ¿Te ayudo con algo?\n\n{oferta}")
    assert URL in salida
    assert "¿Te ayudo con algo?" not in salida and salida.endswith(oferta)


def test_la_pieza_no_parte_un_enlace_con_pregunta():
    salida = con_la_pieza(f"Aquí tienes: {URL}\n\nTe va? Seguro que sí. ¿Te ayudo?", "PIEZA")
    assert URL in salida
    assert salida.index("PIEZA") < salida.index("¿Te ayudo?")


# --- C1: una sola decisión del momento de reservar ----------------------------------------------------------------------------------

def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="4r")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize(("campos", "esperado"), [
    ({}, Entrega(ORIGEN_PRIMERO)),  # nunca el enlace de un origen supuesto (#3738)
    ({"is_colombian": False}, Entrega(ORIGEN_PRIMERO)),
    ({"pending_correction": {"location": "cartagena"}}, Entrega(ORIGEN_PRIMERO)),  # se le está confirmando
    ({"location": "cartagena"}, Entrega(ENLACE, nacionalidad_por_saber=True)),  # con la línea del colombiano (#3741)
    ({"location": "cartagena", "is_colombian": False}, Entrega(ENLACE)),
    ({"location": "cartagena", "is_colombian": True, "mixed_nationality_notice": True}, Entrega(ENLACE)),  # grupo mixto: USD
    ({"location": "cartagena", "is_colombian": True}, Entrega(ASESOR)),
    ({"is_colombian": True}, Entrega(ORIGEN_PRIMERO)),  # P5 (#3747): primero el origen, también para el colombiano
    ({"detected_activity": "certified_diving", "detected_group_size": 6}, Entrega(ORIGEN_PRIMERO)),  # y para el grupo
    ({"location": "cartagena", "detected_activity": "certified_diving", "detected_group_size": 6, "is_colombian": False},
     Entrega("grupo")),
    ({"location": "island"}, Entrega(HOTEL_PRIMERO)),
    ({"pending_correction": {"location": "island"}}, Entrega(HOTEL_PRIMERO)),
    ({"location": "island", "hotel": "Casa Azul", "is_colombian": False}, Entrega(RECOGIDA_POR_CONFIRMAR)),
    ({"location": "island", "hotel": "Hotel Cocoliso", "is_colombian": False}, Entrega(ENLACE)),
])
def test_entrega(campos, esperado):
    assert entrega(_estado(**campos)) == esperado


@pytest.mark.parametrize(("campos", "lugar", "esperado"), [
    ({"location": "island", "hotel": "Casa Azul"}, None, True),
    ({"location": "island", "hotel": "Hotel Cocoliso"}, None, False),
    ({"location": "island", "hotel": "Hotel Cocoliso"}, "un Airbnb en Isla Grande", True),  # quien ya reservó y pide otro sitio (4P)
    ({"location": "island"}, None, False),  # sin hotel: es HOTEL_PRIMERO, no hay recogida que confirmar
    ({"location": "cartagena", "hotel": "Casa Azul"}, None, False),  # desde Cartagena se va al muelle
])
def test_recogida_por_confirmar(campos, lugar, esperado):
    assert recogida_por_confirmar(_estado(**campos), lugar) is esperado
