"""CAL-B (15-oct, flag `moneda_sin_nacionalidad_usd`; decisión de Gadea del 15-oct): sin saber la nacionalidad, el
precio va en USD. La regla del catálogo decía "da las dos monedas" y el resumen del estado no decía nada.
"""
import pytest

from src.agents import supervisor
from src.config import settings
from src.flows import catalog
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _sin_cache(monkeypatch):
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})


@pytest.mark.parametrize("flag", [True, False])
def test_la_regla_del_catalogo(monkeypatch, flag):
    monkeypatch.setattr(settings, "moneda_sin_nacionalidad_usd", flag)
    es, en = catalog.catalog_facts("es"), catalog.catalog_facts("en")
    for lang, texto in (("es", es), ("en", en)):
        vieja, nueva = catalog.MONEDA_SIN_NACIONALIDAD[lang]
        assert (vieja in texto) is (not flag)
        assert (nueva in texto) is flag


def test_la_cache_distingue_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "moneda_sin_nacionalidad_usd", False)
    antes = catalog.catalog_facts("es")
    monkeypatch.setattr(settings, "moneda_sin_nacionalidad_usd", True)
    assert catalog.catalog_facts("es") != antes


@pytest.mark.parametrize("flag,colombiano,espera", [
    (True, None, "en USD"),                 # sin nacionalidad: USD, resuelto en el código
    (False, None, None),                    # antes no se decía nada
    (True, True, "precios en COP"),         # lo de siempre
    (True, False, "precios en USD"),
])
def test_el_resumen_da_la_moneda_resuelta(monkeypatch, flag, colombiano, espera):
    monkeypatch.setattr(settings, "moneda_sin_nacionalidad_usd", flag)
    st = ConversationState(conversation_id="moneda", language="es")
    st.is_colombian = colombiano
    resumen = supervisor._build_extra_context(st) or ""
    if espera:
        assert espera in resumen
    else:
        assert "nacionalidad del cliente" not in resumen
