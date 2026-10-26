"""Los valores oficiales del negocio que se repiten en muchos textos (`data/knowledge_base/valores.json`, lat-deuda-u,
26-oct): el horario y el umbral del refresh. El código lee de aquí sus horas (la tarjeta del flujo, los ejemplos de los
prompts) y tests/test_valores_de_la_base.py vigila que la base diga lo mismo."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

VALORES_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "valores.json"


@lru_cache(maxsize=1)
def _datos() -> dict:
    return json.loads(VALORES_PATH.read_text(encoding="utf-8-sig"))


def hora(clave: str) -> str:
    """La hora oficial (la primera, si es un intervalo): «8:00», «4:30»…"""
    return _datos()["horario"][clave][0]


def anos_sin_bucear_refresh() -> int:
    return int(_datos()["anos_sin_bucear_refresh"])


def horas_oficiales() -> set[str]:
    return {h for horas in _datos()["horario"].values() for h in horas}


