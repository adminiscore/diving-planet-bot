"""Bloque 4R (Plan Gadea): el momento de reservar. Banco sin IA (docs/robustness/caln/diseno-bloque4r.md)."""
import pytest

from src.agents.compositor import _una_oferta_del_asesor
from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR
from src.agents.redactor_hechos import con_la_pieza
from src.flows.que_preguntar import destapar_enlaces, tapar_enlaces

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
