"""CALN-18 (4-nov): en el cierre en pesos, la oferta del asesor una vez (src/agents/compositor.py)."""
from types import SimpleNamespace

from src.agents.compositor import componer
from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR

TARJETA = "🤿 *Tour de Snorkeling*\n💰 *448.000 COP* por persona · 4 personas"
PAGO = ("El pago es en pesos colombianos (COP): pueden pagar *100 % online* o un *anticipo del 50 %* con el enlace, el QR "
        "o Llave que envía el asesor, y el *otro 50 % el día de la actividad*.")


def _turno():
    return SimpleNamespace(core_pending_slot=None, _preguntas_del_turno=[])


def test_la_pregunta_del_escritor_sale_y_queda_la_oferta():
    """Sparring s04d, Cali t2: el escritor pregunta por el asesor y la tarjeta en pesos lo ofrece debajo."""
    escritor = ("El Tour de Snorkeling cuesta *$448.000 COP por persona reservando online*.\n\n"
                "Para el domingo 15, la reserva se coordina con un asesor. ¿Quieres que te pase con un asesor para "
                "continuar la reserva?")
    oferta = _OFERTA_DEL_ASESOR["es_grupo"]
    r = componer(_turno(), f"{escritor}\n\n{TARJETA}\n\n{PAGO}\n\n{oferta}", escribio=True)
    assert r == (f"El Tour de Snorkeling cuesta *$448.000 COP por persona reservando online*.\n\n"
                 f"Para el domingo 15, la reserva se coordina con un asesor.\n\n{TARJETA}\n\n{PAGO}\n\n{oferta}")
    assert r.count("?") == 1


def test_en_ingles_y_un_parrafo_que_solo_pregunta():
    oferta = _OFERTA_DEL_ASESOR["en"]
    r = componer(_turno(), f"Would you like to book with an advisor?\n\n{TARJETA}\n\n{oferta}", escribio=True)
    assert r == f"{TARJETA}\n\n{oferta}"


def test_sin_la_oferta_no_se_toca():
    r = f"¿Quieres que te pase con un asesor?\n\n{TARJETA}\n\n{PAGO}"
    assert componer(_turno(), r, escribio=True) == r
    oferta = _OFERTA_DEL_ASESOR["es_uno"]
    assert componer(_turno(), f"{TARJETA}\n\n{oferta}", escribio=True) == f"{TARJETA}\n\n{oferta}"
