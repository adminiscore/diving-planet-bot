"""La moneda cuando no se sabe la nacionalidad. CAL-B (15-oct) la dejó en USD; lat-deuda-u (26-oct, decisión de Gadea)
la cambia a USD y COP en TODOS los caminos («el mismo precio, solo cambia la moneda»), como ya hacía la tabla de
hechos (arq-5c). La regla del código está en `src/flows/moneda.py`; el catálogo y el resumen del estado la dicen igual.
"""
import pytest

from src.agents import supervisor
from src.flows import cart_render, catalog, moneda
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _sin_cache(monkeypatch):
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})


def _st(**campos) -> ConversationState:
    st = ConversationState(conversation_id="moneda", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("lang, vieja", [
    ("es", "Si no sabes la nacionalidad del cliente, da el precio en USD (si te dice"),
    ("en", "If you don't know the customer's nationality, give the price in USD (if they"),
])
def test_la_regla_del_catalogo(lang, vieja):
    texto = catalog.catalog_facts(lang)
    assert catalog.MONEDA_SIN_NACIONALIDAD[lang] in texto
    assert vieja not in texto


@pytest.mark.parametrize("colombiano,espera", [
    (None, "en USD y en COP"),        # sin nacionalidad: las dos (Gadea, 26-oct)
    (True, "precios en COP"),
    (False, "precios en USD"),
])
def test_el_resumen_da_la_moneda_resuelta(colombiano, espera):
    resumen = supervisor._build_extra_context(_st(is_colombian=colombiano)) or ""
    assert espera in resumen


@pytest.mark.parametrize("campos, monedas", [
    ({}, ("USD", "COP")),
    ({"is_colombian": True}, ("COP",)),
    ({"is_colombian": False}, ("USD",)),
    ({"is_colombian": True, "mixed_nationality_notice": True}, ("USD",)),  # grupo mixto: todo en USD
])
def test_una_sola_regla(campos, monedas):
    assert moneda.monedas(_st(**campos)) == monedas


def test_el_precio_en_su_moneda():
    assert moneda.precio(_st(), 183, 727000) == "183 USD / 727.000 COP"
    assert moneda.precio(_st(is_colombian=True), 183, 727000) == "727.000 COP"
    assert moneda.precio(_st(is_colombian=False), 183, 727000, qty=2) == "366 USD"
    assert moneda.precio(_st(is_colombian=True), 183, None) == "183 USD"  # sin tarifa en su moneda, la otra
    assert moneda.precio(_st(), None, None) is None


def test_el_refresher_y_la_comparacion_usan_la_misma_regla():
    from src.agents.nucleo.routing import _compose_comparison

    assert " / " in cart_render.refresher_price_text(_st(), una_moneda=True)
    assert "COP" not in cart_render.refresher_price_text(_st(is_colombian=False), una_moneda=True)
    comparacion = _compose_comparison(["minicourse", "snorkeling"], _st(is_colombian=True))
    assert "COP por persona" in comparacion and "USD" not in comparacion
