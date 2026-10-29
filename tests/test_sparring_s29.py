"""Sparring s29 (29-oct, contra PRE 0.38.0; docs/robustness/g3/hallazgos.md, CALN-S29): la nota de moneda de la tarjeta
solo cuando van las dos monedas, el cierre del colombiano sin repetir el pago que acaba de preguntar y la regla de la
transferencia en los hechos de pago del colombiano. Sin red."""
from src.flows import cart_render, hechos
from src.flows.catalog import politicas
from tests.test_conversations import make_state

NOTA = "El precio es el mismo en pesos (COP) o dólares (USD)"


def _tarjeta(is_colombian, mixto=False):
    state = make_state()
    state.mixed_cart = [{"type": "snorkel", "qty": 2, "label": "Snorkel"}]
    state.is_colombian = is_colombian
    state.mixed_nationality_notice = mixto
    return cart_render.goto_final_summary(state)


def test_la_nota_de_moneda_solo_sin_nacionalidad():
    assert NOTA in _tarjeta(None)
    assert NOTA not in _tarjeta(False)
    assert NOTA not in _tarjeta(None, mixto=True)


def test_el_pago_del_colombiano_incluye_la_regla_de_la_transferencia():
    state = make_state()
    state.is_colombian = True
    pago = hechos._clima_y_pago(state, ["pago"], "es")["pago"]
    assert politicas()["payment_fallback"]["es"] in pago


def test_el_cierre_del_colombiano_no_repite_el_pago_que_pregunta(monkeypatch):
    from src.agents.nucleo import slotfill_close

    monkeypatch.setattr(slotfill_close, "_build_cart_from_slots", lambda s: None)  # el carrito de la prueba, tal cual

    def cierre(intenciones):
        state = make_state()
        state.mixed_cart = [{"type": "snorkel", "qty": 2, "label": "Snorkel"}]
        state.is_colombian = True
        state.detected_group_size = 2
        state._intenciones = intenciones
        return slotfill_close._finalize(state)

    assert "El pago es en pesos colombianos" in cierre([])
    con_pregunta = cierre(["pago"])
    assert "El pago es en pesos colombianos" not in con_pregunta and "asesor" in con_pregunta
