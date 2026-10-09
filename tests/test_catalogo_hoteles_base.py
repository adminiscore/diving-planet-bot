"""9-oct (Gadea, flag `catalogo_hoteles_base`): en los hoteles base la recogida esta confirmada; lo dice el catalogo
que ven siempre el RAG y el revisor (paquete-5-buceos-islas-residente-sin-recogida: "el equipo confirma si Cocoliso
tiene acceso maritimo")."""
import pytest

from src.config import settings
from src.flows import catalog
from src.flows.catalog import catalog_facts


@pytest.mark.parametrize("lang", ["es", "en"])
def test_hoteles_base_en_el_catalogo(monkeypatch, lang):
    monkeypatch.setattr(settings, "catalogo_hoteles_base", True)
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})  # el catalogo se calcula una vez por proceso
    linea = next(x for x in catalog_facts(lang).splitlines() if "Rosario" in x and x.endswith(":"))
    assert "San Pedro de Majagua" in linea and "Cocoliso" in linea


@pytest.mark.parametrize("lang", ["es", "en"])
def test_apagado_deja_la_linea_de_antes(monkeypatch, lang):
    monkeypatch.setattr(settings, "catalogo_hoteles_base", False)
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})
    linea = next(x for x in catalog_facts(lang).splitlines() if "Rosario" in x and x.endswith(":"))
    assert "Cocoliso" not in linea
