"""CAL (17-oct): el catálogo del RAG pinta lo que la FICHA de cada producto ya dice, cada cosa con su flag.

Diagnóstico (banco reparado, `scripts/sonda_senales.py` y el verificador): en dos casos de CAL-A el bot no decía algo
porque el dato NO estaba en nada que viera el RAG, aunque la base lo tenía:

- cal-18 "¿cuántos metros bajan?" (un buzo certificado): la profundidad por nivel solo estaba en el registro interno de
  actividades ("habilita para bucear de forma autónoma hasta 18 m"; Advanced "hasta 30 metros").
- cal-49 el formulario de traspaso del curso referido: "traer la carta de referido firmada por un instructor PADI"
  estaba en la ficha (`preparation_*`), pero el catálogo no pintaba la preparación.

Medido (banco CAL-A 16x3): pintar la PREPARACIÓN de los 18 productos en todos los turnos arregla cal-49 pero rompe
cal-26 y cal-64 (41/48 frente a 38/48). Se quedó la profundidad (cuatro números); la preparación se descartó y su
flag `catalogo_preparacion` se borró en sim-6.
"""

import json
import re
from pathlib import Path

from src.flows import catalog

KB = Path(__file__).resolve().parents[1] / "data" / "knowledge_base"


def _linea(texto: str, nombre: str) -> str:
    return next(l for l in texto.splitlines() if l.startswith(f"- {nombre}:"))


def test_el_catalogo_no_pinta_la_preparacion():
    assert "preparación:" not in catalog.catalog_facts("es")


def test_con_la_profundidad_cada_certificacion_dice_hasta_donde_certifica():
    """cal-18: Open Water hasta 18 m y Advanced hasta 30 m, en la línea de cada curso."""
    es = catalog.catalog_facts("es")
    assert "certifica para bucear hasta 18 m" in _linea(es, "Curso Básico PADI (Open Water)")
    assert "certifica para bucear hasta 30 m" in _linea(es, "Curso Avanzado PADI")
    assert "preparación:" not in es, "la profundidad no arrastra la preparación"
    en = catalog.catalog_facts("en")
    assert "certifies you to dive down to 18 m" in en and "certifies you to dive down to 30 m" in en


def test_la_profundidad_tambien_va_como_regla_general_para_los_ya_certificados():
    """cal-18 siguió fallando con solo "certifica hasta 18 m" en la línea del CURSO: quien pregunta es un buzo ya
    certificado por una SALIDA. La regla va también como línea general, construida desde las fichas de los cursos."""
    ultima = catalog.catalog_facts("es").splitlines()[-1]
    assert "Profundidad máxima de cada buzo según su certificación" in ultima
    assert "hasta 18 m" in ultima and "hasta 30 m" in ultima
    assert "Maximum depth for each diver" in catalog.catalog_facts("en")


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
