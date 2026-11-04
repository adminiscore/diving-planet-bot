"""Decisiones de Gadea del 4-nov. El minicurso no lleva teoría online ni por correo: la base decía lo contrario para el de
Cartagena. El colombiano no usa el enlace de la web: lo cierra un asesor (ya decidido el 21-oct, pero la política lo decía
solo del anticipo, y el escritor contestó «ese enlace es para reservar y pagar», sparring s04d)."""
import json
import re
from pathlib import Path

import pytest

from src.flows import hechos

BASE = Path(__file__).parent.parent / "data" / "knowledge_base"


@pytest.mark.parametrize("ruta", ["services.json", "policies.json", "curada/faqs.json"])
def test_el_minicurso_no_lleva_teoria_antes(ruta):
    texto = (BASE / ruta).read_text(encoding="utf-8-sig")
    # «teoría online» sí está en los cursos PADI con eLearning: aquí, solo las frases del minicurso.
    for frase in ("recibes por correo la parte teórica", "theory part by email", "parte teórica que se completa antes",
                  "theory section to be completed before", "recibirás un correo con instrucciones para completar la teoría"):
        assert frase not in texto, frase


def test_el_de_cartagena_no_pide_completar_la_teoria():
    datos = json.loads((BASE / "services.json").read_text(encoding="utf-8-sig"))
    servicios = datos.get("services", datos)
    mini = next(s for s in (servicios.values() if isinstance(servicios, dict) else servicios)
                if s.get("name_es") == "Minicurso de Buceo")
    assert mini["requirements_es"] == [] and mini["requirements_en"] == []
    assert not re.search(r"completar|correo", mini["preparation_es"], re.I)
    assert "online" not in mini["description_es"] and "online" not in mini["description_en"]


@pytest.mark.parametrize("lang, enlace, asesor", [("es", "no usan el enlace", "siempre la cierra un asesor"),
                                                  ("en", "do not use the website booking link", "always closes")])
def test_el_colombiano_no_usa_el_enlace_de_la_web(lang, enlace, asesor):
    politica = hechos._politica("payment_colombian", lang)
    assert enlace in politica and asesor in politica
