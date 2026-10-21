"""CAL-B (15-oct, `moneda_sin_nacionalidad_usd`; decisión de Gadea del 15-oct): sin saber la nacionalidad, el
precio va en USD. La regla del catálogo decía "da las dos monedas" y el resumen del estado no decía nada.
Promocionado el 16-oct; desde mej-1d (decisión de Gadea, Coral #976) la regla va escrita en el catálogo, sin interruptor.
"""
import pytest

from src.agents import supervisor
from src.flows import catalog
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _sin_cache(monkeypatch):
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})


@pytest.mark.parametrize("lang, vieja", [
    ("es", "Si no sabes la nacionalidad del cliente, da las dos monedas."),
    ("en", "If you don't know the customer's nationality, give both currencies."),
])
def test_la_regla_del_catalogo(lang, vieja):
    texto = catalog.catalog_facts(lang)
    assert catalog.MONEDA_SIN_NACIONALIDAD[lang] in texto
    assert vieja not in texto


@pytest.mark.parametrize("colombiano,espera", [
    (None, "en USD"),                 # sin nacionalidad: USD, resuelto en el código
    (True, "precios en COP"),         # lo de siempre
    (False, "precios en USD"),
])
def test_el_resumen_da_la_moneda_resuelta(colombiano, espera):
    st = ConversationState(conversation_id="moneda", language="es")
    st.is_colombian = colombiano
    resumen = supervisor._build_extra_context(st) or ""
    assert espera in resumen
