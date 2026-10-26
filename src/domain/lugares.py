"""Los lugares de las Islas del Rosario, de `data/knowledge_base/lugares.json` (lat-deuda-u, 26-oct): una sola fuente
para los hoteles con recogida y para los sitios que se reconocen como «de las islas». Antes eran seis listas en el código
(extractor, Jev, redactor, detector del RAG, catálogo y transcripción), cada una con nombres distintos."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LUGARES_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "lugares.json"


@lru_cache(maxsize=1)
def _datos() -> dict:
    return json.loads(LUGARES_PATH.read_text(encoding="utf-8-sig"))


def hoteles_con_recogida() -> tuple[str, ...]:
    """Los hoteles de las islas donde recogemos, con los de la base primero."""
    return tuple(h["nombre"] for h in _datos()["hoteles_con_recogida"])


def hoteles_base() -> tuple[str, ...]:
    """Los hoteles base (en Isla Grande): la recogida está confirmada e incluida."""
    return tuple(h["nombre"] for h in _datos()["hoteles_con_recogida"] if h.get("base"))


def lugares_de_las_islas() -> tuple[str, ...]:
    """Islas, hoteles y clubes de playa que están en las islas."""
    return tuple(_datos()["lugares_de_las_islas"])
