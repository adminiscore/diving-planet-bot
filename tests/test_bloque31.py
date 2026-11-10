"""Bloque 3.1 del Plan Gadea (10-nov): el cierre de las 4:30, con el reloj y la base. Banco sin IA, con el reloj fijo.

Diseño: `docs/robustness/caln/diseno-bloque31.md`. Decisión de Gadea del 9-nov: el cierre es firme (4:30 p. m. del día anterior);
se opera todos los días salvo los cerrados de la base.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domain.calendario import cierre_de, primer_dia_reservable

COLOMBIA = ZoneInfo("America/Bogota")


def _a(texto: str, zona=COLOMBIA) -> datetime:
    return datetime.fromisoformat(texto).replace(tzinfo=zona)


@pytest.mark.parametrize(("ahora", "primero"), [
    ("2026-11-05 10:30", date(2026, 11, 6)),   # jueves por la mañana: mañana se puede
    ("2026-11-05 16:29", date(2026, 11, 6)),
    ("2026-11-05 16:30", date(2026, 11, 7)),   # a las 4:30 justas ya cerró
    ("2026-11-05 20:30", date(2026, 11, 7)),   # jueves por la noche: el sábado
    ("2026-11-08 23:59", date(2026, 11, 10)),  # domingo por la noche
    ("2026-12-24 10:00", date(2026, 12, 26)),  # el 25 está cerrado; el 26 cierra el 25 a las 4:30
    ("2026-12-24 20:00", date(2026, 12, 26)),
    ("2026-12-31 20:00", date(2027, 1, 2)),    # el 1-ene está cerrado
])
def test_el_primer_dia_que_se_puede_reservar(ahora, primero):
    assert primer_dia_reservable(_a(ahora)) == primero


def test_la_hora_se_pasa_a_colombia_y_sin_zona_es_un_error():
    assert primer_dia_reservable(_a("2026-11-05 22:00", ZoneInfo("UTC"))) == date(2026, 11, 7)  # las 17:00 en Colombia
    with pytest.raises(ValueError):
        primer_dia_reservable(datetime(2026, 11, 5, 10, 30))


def test_el_cierre_es_a_las_cuatro_y_media_de_la_tarde_del_dia_anterior():
    assert cierre_de(date(2026, 11, 7)) == _a("2026-11-06 16:30")


@pytest.mark.parametrize(("ahora", "lang", "dice"), [
    ("2026-11-05 10:30", "es", "Mañana, viernes 6 de noviembre, todavía se puede reservar, hasta hoy a las 4:30 p. m."),
    ("2026-11-05 20:30", "es", "Mañana, viernes 6 de noviembre, ya no se puede reservar: el cierre fue hoy a las 4:30 p. m. "
                               "El primer día que se puede reservar es el sábado 7 de noviembre."),
    ("2026-12-24 10:00", "es", "Mañana, viernes 25 de diciembre, no operamos; el primer día que se puede reservar es el sábado "
                               "26 de diciembre."),
    ("2026-11-05 10:30", "en", "Tomorrow, Friday, November 6, can still be booked, until 4:30 p.m. today."),
    ("2026-11-05 20:30", "en", "Tomorrow, Friday, November 6, can no longer be booked: booking closed today at 4:30 p.m. The "
                               "first day that can be booked is Saturday, November 7."),
])
def test_la_linea_del_cierre_en_sus_tres_casos(ahora, lang, dice):
    from src.agents.rutas.contexto_rag import _el_cierre

    assert _el_cierre(_a(ahora), lang) == dice


def test_la_linea_llega_al_contexto_del_escritor_con_el_reloj_fijo_del_arnes(monkeypatch):
    """Como `reproducir_juez_pre --reloj`: se sustituye `datetime` en `contexto_rag`, y la cuenta usa esa misma hora."""
    import src.agents.rutas.contexto_rag as ctx
    from src.flows.state import ConversationState

    fijo = _a("2026-11-05 20:30")

    class _Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return fijo.astimezone(tz) if tz else fijo

    monkeypatch.setattr(ctx, "datetime", _Reloj)
    contexto = ctx._build_extra_context(ConversationState(conversation_id="b31", language="es")) or ""
    assert "Mañana, viernes 6 de noviembre, ya no se puede reservar" in contexto
    assert "el sábado 7 de noviembre" in contexto
