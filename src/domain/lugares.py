"""Los lugares de las Islas del Rosario, de `data/knowledge_base/lugares.json` (lat-deuda-u, 26-oct): una sola fuente
para los hoteles con recogida y para los sitios que se reconocen como «de las islas». Antes eran seis listas en el código
(extractor, Jev, redactor, detector del RAG, catálogo y transcripción), cada una con nombres distintos."""
from __future__ import annotations

import json
import re
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


def _patron(alias: str) -> re.Pattern:
    """Un alias como palabras enteras, con cualquier espacio entre ellas."""
    return re.compile(r"\b" + r"\s+".join(map(re.escape, alias.split())) + r"\b")


@lru_cache(maxsize=1)
def _islas() -> tuple[tuple[str, tuple[re.Pattern, ...], tuple[re.Pattern, ...]], ...]:
    return tuple((i["id"], tuple(map(_patron, i["alias"])), tuple(map(_patron, i.get("alias_si_nombra_una_isla", ()))))
                 for i in _datos()["alias_de_las_islas"])


@lru_cache(maxsize=1)
def _hoteles() -> tuple[tuple[str, str | None, tuple[re.Pattern, ...]], ...]:
    return tuple((h["id"], h.get("isla"), tuple(map(_patron, h["alias"]))) for h in _datos()["alias_de_los_hoteles"])


def isla_nombrada(texto: str, *, nombra_una_isla: bool) -> str | None:
    """La primera isla de `alias_de_las_islas` que nombra `texto` (en minúsculas). Sus formas cortas («grande»,
    «marina») solo cuentan si `nombra_una_isla`: solas son palabras corrientes."""
    for isla, alias, cortos in _islas():
        if any(p.search(texto) for p in alias) or (nombra_una_isla and any(p.search(texto) for p in cortos)):
            return isla
    return None


def hotel_nombrado(texto: str) -> tuple[str, str | None] | None:
    """(hotel, isla) del primer hotel de `alias_de_los_hoteles` que nombra `texto` (en minúsculas); None si ninguno."""
    for hotel, isla, alias in _hoteles():
        if any(p.search(texto) for p in alias):
            return hotel, isla
    return None
