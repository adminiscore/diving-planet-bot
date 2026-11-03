"""CALN-12 (3-nov, respuestas de Gadea): los temas que la base no sabía, en el bloque que leen el bot y la base curada,
con sus formas de preguntarlas para que la búsqueda los encuentre. Sin red."""
import json
from pathlib import Path

import pytest

from src.domain.politicas import politica

TEMAS = ("older_divers", "safety_onboard", "group_ratio", "facilities", "parking", "gift_booking",
         "no_smoking_onboard", "no_pets")


@pytest.mark.parametrize("clave", TEMAS)
def test_cada_tema_tiene_politica_y_formas_de_preguntarlo(clave):
    assert politica(clave, "es") and politica(clave, "en")
    reglas = json.loads(Path("data/knowledge_base/curada/preguntas.json").read_text(encoding="utf-8"))["reglas"]
    assert len(reglas[f"politica:{clave}"]["es"]) == 3 and len(reglas[f"politica:{clave}"]["en"]) == 3


def test_los_grupos_sin_cifras():
    """Decisión de Gadea: los grupos son reducidos, sin dar un número."""
    assert not any(c.isdigit() for c in politica("group_ratio", "es") + politica("group_ratio", "en"))
