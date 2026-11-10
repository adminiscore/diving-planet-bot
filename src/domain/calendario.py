"""Los días del año que no operamos, de `data/knowledge_base/policies.json` (`closed_days.fechas`; lat-deuda-u, 26-oct).
La frase «el 25 de diciembre y el 1 de enero» estaba escrita a mano en seis sitios del código (catálogo, pase del clima,
prompts del RAG); si el negocio cambia un día, se cambia en la base y aquí se genera."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

# El dominio no importa nada del runtime (tests/test_prompts_surface.py); politicas.py es su vecino, solo stdlib.
from .politicas import politicas
from .valores import hora

_COLOMBIA = ZoneInfo("America/Bogota")

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


def nombre_del_dia(dia: date, lang: str) -> str:
    """«viernes 6 de noviembre» o «Friday, November 6»."""
    if lang == "es":
        semana = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[dia.weekday()]
        return f"{semana} {dia.day} de {_MESES['es'][dia.month - 1]}"
    return f"{dia.strftime('%A')}, {_MESES['en'][dia.month - 1]} {dia.day}"


def cerrado(dia: date) -> bool:
    return (dia.month, dia.day) in fechas_cerradas()


def cierre_de(dia: date) -> datetime:
    """Bloque 3.1 (10-nov): hasta cuándo se reserva `dia`, a las 4:30 p. m. del día anterior en Colombia (decisión de
    Gadea del 9-nov: el cierre es firme). La hora es la de la base (`valores`, «4:30»), de la tarde."""
    h, m = (int(x) for x in hora("cierre_reservas").split(":"))
    return datetime.combine(dia - timedelta(days=1), time(h + 12 if h < 12 else h, m), _COLOMBIA)


def primer_dia_reservable(ahora: datetime) -> date:
    """Bloque 3.1: el primer día, desde mañana, que no está cerrado y cuyo cierre aún no ha pasado (hoy nunca: su cierre
    fue ayer). `ahora` con zona horaria: es la hora que ve el escritor (`contexto_rag`), y así vale el reloj fijo."""
    if ahora.tzinfo is None:
        raise ValueError("primer_dia_reservable: `ahora` sin zona horaria")
    ahora = ahora.astimezone(_COLOMBIA)
    dia = ahora.date() + timedelta(days=1)
    while cerrado(dia) or ahora >= cierre_de(dia):
        dia += timedelta(days=1)
    return dia
