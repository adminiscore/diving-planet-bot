"""CAL (17-oct, flag `catalogo_fichas_completas`): el catálogo del RAG pinta lo que la FICHA de cada producto ya dice.

Diagnóstico (banco reparado, `scripts/sonda_senales.py` y el verificador): en dos casos de CAL-A el bot no decía algo
porque el dato NO estaba en nada que viera el RAG, aunque la base lo tenía:

- cal-18 "¿cuántos metros bajan?" (un buzo certificado): la profundidad por nivel solo estaba en el registro interno de
  actividades ("habilita para bucear de forma autónoma hasta 18 m"; Advanced "hasta 30 metros").
- cal-49 el formulario de traspaso del curso referido: "traer la carta de referido firmada por un instructor PADI"
  estaba en la ficha (`preparation_*`) y en una pregunta frecuente, pero el catálogo no pintaba la preparación y la
  búsqueda no traía esa pregunta.

El arreglo es de datos y en un solo sitio: el catálogo muestra, de cada producto, hasta dónde certifica y qué
preparación pide. Nada inventado, ninguna lista de frases, ninguna regla nueva en el prompt.
"""

import json
import re
from pathlib import Path

import pytest

from src.config import settings
from src.flows import catalog

KB = Path(__file__).resolve().parents[1] / "data" / "knowledge_base"


@pytest.fixture
def fichas(monkeypatch):
    def poner(valor: bool):
        monkeypatch.setattr(settings, "catalogo_fichas_completas", valor)
    return poner


def _linea(texto: str, nombre: str) -> str:
    return next(l for l in texto.splitlines() if l.startswith(f"- {nombre}:"))


def test_sin_el_flag_el_catalogo_es_el_de_siempre(fichas):
    fichas(False)
    es = catalog.catalog_facts("es")
    assert "preparación:" not in es
    assert "certifica para bucear hasta" not in es


def test_con_el_flag_el_curso_referido_dice_la_carta(fichas):
    """cal-49: la carta de referido es un requisito del producto y ahora está en su línea del catálogo."""
    fichas(True)
    referido = _linea(catalog.catalog_facts("es"), "Curso Referido (Open Water)")
    assert "carta de referido firmada" in referido
    referral = _linea(catalog.catalog_facts("en"), "Open Water Referral Course")
    assert "referral paperwork signed" in referral


def test_con_el_flag_cada_certificacion_dice_hasta_donde_certifica(fichas):
    """cal-18: Open Water hasta 18 m y Advanced hasta 30 m, en la línea de cada curso."""
    fichas(True)
    es = catalog.catalog_facts("es")
    assert "certifica para bucear hasta 18 m" in _linea(es, "Curso Basico PADI (Open Water)")
    assert "certifica para bucear hasta 30 m" in _linea(es, "Curso Avanzado PADI")
    en = catalog.catalog_facts("en")
    assert "certifies you to dive down to 18 m" in en and "certifies you to dive down to 30 m" in en


def test_la_preparacion_sale_de_la_ficha_de_cada_producto(fichas):
    """Todos los productos con preparación en su ficha la llevan en el catálogo: es un dato, no un caso."""
    fichas(True)
    es = catalog.catalog_facts("es")
    con_preparacion = [s for s, v in catalog.RAW_SERVICES.items()
                       if v.get("preparation_es") and v.get("category") != "private"]
    assert len(con_preparacion) >= 10
    for sid in con_preparacion:
        primeras = catalog.RAW_SERVICES[sid]["preparation_es"].strip()[:40]
        assert primeras in es, f"la preparación de {sid} no está en el catálogo"


def test_la_cache_distingue_el_flag(fichas):
    """La caché del catálogo llevaba solo la moneda en la clave: cambiar otro flag devolvía el texto de antes."""
    fichas(False)
    apagado = catalog.catalog_facts("es")
    fichas(True)
    encendido = catalog.catalog_facts("es")
    assert apagado != encendido
    fichas(False)
    assert catalog.catalog_facts("es") == apagado


def test_la_profundidad_de_las_fichas_es_la_que_dice_el_registro_de_actividades():
    """El dato vive en dos sitios (la ficha, que lo pinta; el registro, que describe el curso): este test los mantiene
    de acuerdo. Si alguien cambia uno, falla."""
    servicios = json.loads((KB / "services.json").read_text(encoding="utf-8-sig"))["services"]
    registro = (KB / "activities.json").read_text(encoding="utf-8-sig")
    con_profundidad = {sid: v["max_depth_m"] for sid, v in servicios.items() if v.get("max_depth_m")}
    assert con_profundidad, "ninguna ficha dice hasta dónde certifica"
    for sid, metros in con_profundidad.items():
        assert re.search(rf"hasta {metros} (m\b|metros)", registro), f"{sid}: {metros} m no consta en activities.json"
    assert con_profundidad.get("open_water") == 18 and con_profundidad.get("advanced") == 30
