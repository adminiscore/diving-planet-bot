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


# 9-oct (flag `catalogo_equipo_incluido`): cada plan del CATÁLOGO dice si el equipo va incluido; el Dive Master no.
# La ficha del servicio (base v2) no cambia: ya lo dice en "Incluye".
def _linea(lang, nombre):
    return next(x for x in catalog_facts(lang).splitlines() if x.startswith(f"- {nombre}:"))


def test_equipo_incluido_por_plan(monkeypatch):
    monkeypatch.setattr(settings, "catalogo_equipo_incluido", True)
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})
    assert "equipo incluido" in _linea("es", catalog.SERVICES["minicourse"]["name_es"])
    assert "gear included" in _linea("en", catalog.SERVICES["snorkeling"]["name_en"])
    assert "equipo NO incluido (hay que tener equipo propio)" in _linea("es", catalog.SERVICES["divemaster"]["name_es"])
    assert "equipo" not in catalog.service_fact_sheet("minicourse", "es").split("Incluye")[0]


def test_equipo_apagado(monkeypatch):
    monkeypatch.setattr(settings, "catalogo_equipo_incluido", False)
    monkeypatch.setattr(catalog, "_FACTS_CACHE", {})
    assert "equipo incluido" not in catalog_facts("es")
