"""Los días del año que no operamos, de `data/knowledge_base/policies.json` (`closed_days.fechas`; lat-deuda-u, 26-oct).
La frase «el 25 de diciembre y el 1 de enero» estaba escrita a mano en seis sitios del código (catálogo, pase del clima,
prompts del RAG); si el negocio cambia un día, se cambia en la base y aquí se genera."""
from __future__ import annotations

from functools import lru_cache

# El dominio no importa nada del runtime (tests/test_prompts_surface.py); politicas.py es su vecino, solo stdlib.
from .politicas import politicas

_MESES = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"),
}


@lru_cache(maxsize=1)
def fechas_cerradas() -> tuple[tuple[int, int], ...]:
    """(mes, día) de cada día cerrado, en el orden de la base."""
    fechas = politicas()["closed_days"]["fechas"]
    return tuple((int(m), int(d)) for m, d in (f.split("-") for f in fechas))


def dias_cerrados(lang: str, articulo: bool = True) -> str:
    """«el 25 de diciembre y el 1 de enero» («25 de diciembre y 1 de enero» sin artículo) o «December 25 and January 1»."""
    if lang == "es":
        partes = [f"{'el ' if articulo else ''}{d} de {_MESES['es'][m - 1]}" for m, d in fechas_cerradas()]
        y = " y "
    else:
        partes = [f"{_MESES['en'][m - 1]} {d}" for m, d in fechas_cerradas()]
        y = " and "
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + y + partes[-1]
