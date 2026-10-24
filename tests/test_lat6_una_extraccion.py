"""lat-6 (24-oct, fase LAT): una sola extracción por turno. `datos_del_extractor` (en `_understand`) consumía la tarea
y la soltaba; si después el mismo turno volvía a leer (`lectura_del_extractor`: el redactor, el enrutado) se pedía OTRA
extracción en serie (~1 s; en real-1, el 13 % de los turnos)."""
import asyncio

from src.agents import extractor_turno
from src.agents.nucleo import extractor as nucleo
from src.flows.state import ConversationState


def _conv() -> ConversationState:
    return ConversationState(conversation_id="lat6", language="es")


def test_lo_que_lee_despues_el_turno_no_pide_otra_extraccion(monkeypatch):
    llamadas = []

    async def extraer(message, **kw):
        llamadas.append(message)
        return {"location": "island"}

    monkeypatch.setattr(extractor_turno, "extraer_turno", extraer)
    st = _conv()

    async def turno():
        assert await nucleo.datos_del_extractor(st, "nos quedamos en Mulata") == {"location": "island"}
        assert await nucleo.lectura_del_extractor(st, "nos quedamos en Mulata") == {"location": "island"}

    asyncio.run(turno())
    assert llamadas == ["nos quedamos en Mulata"]


def test_al_cerrar_el_turno_la_lectura_no_pasa_al_siguiente(monkeypatch):
    async def extraer(message, **kw):
        return {"group_size": 2}

    monkeypatch.setattr(extractor_turno, "extraer_turno", extraer)
    st = _conv()
    asyncio.run(nucleo.datos_del_extractor(st, "sí"))
    nucleo.cancelar_extraccion_adelantada(st)
    assert st._lectura_del_turno is None
