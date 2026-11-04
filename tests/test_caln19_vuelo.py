"""CALN-19 (decisión de Gadea, 4-nov; sparring s04h): el escritor echaba mal la cuenta del vuelo: «Wednesday's dive would be too
close to your Friday 10:00 flight». La hora desde la que se puede volar va ya calculada en la base."""
import json
from pathlib import Path

import pytest

BASE = Path(__file__).parent.parent / "data" / "knowledge_base"


@pytest.mark.parametrize("lang, frase", [("es", "desde las 7:00 a. m. del día siguiente"), ("en", "from 7:00 a.m. the next day")])
def test_la_hora_de_volar_esta_en_la_politica_y_en_la_faq(lang, frase):
    politica = json.loads((BASE / "policies.json").read_text(encoding="utf-8-sig"))["policies"]["flight_after_diving"]
    faq = next(f for f in json.loads((BASE / "curada/faqs.json").read_text(encoding="utf-8-sig"))["faqs"]
               if str(f.get("origen")) == "9")
    assert frase in politica[lang] and frase in faq[f"answer_{lang}"]


@pytest.mark.parametrize("lang, medianoche, nocturna", [("es", "desde la medianoche", "nocturna"), ("en", "from midnight", "night dive")])
def test_el_minicurso_y_la_nocturna_tienen_su_regla(lang, medianoche, nocturna):
    politica = json.loads((BASE / "policies.json").read_text(encoding="utf-8-sig"))["policies"]["flight_after_diving"][lang]
    assert medianoche in politica and nocturna in politica
