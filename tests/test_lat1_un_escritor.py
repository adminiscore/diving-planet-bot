"""lat-1 (24-oct, fase LAT): cancelar una respuesta cancela también la llamada del escritor. Sin red."""
import asyncio

import pytest

from src.config import settings


@pytest.mark.asyncio
async def test_cancelar_la_respuesta_cancela_tambien_la_llamada_del_escritor(monkeypatch):
    """latb4-B: con la respuesta ya cancelada, el escritor lanzado con ensure_future seguía vivo y se pagaba entero."""
    from src.agents import rag_agent

    monkeypatch.setattr(settings, "rag_respaldo_segundos", 0.05)
    llamadas = []

    class _Lento:
        def __init__(self):
            self.chat = self
            self.completions = self

        async def create(self, **kw):
            evento = asyncio.Event()
            llamadas.append(evento)
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                evento.set()
                raise

    tarea = asyncio.ensure_future(rag_agent.generar_con_respaldo(_Lento(), [{"role": "user", "content": "hola"}]))
    await asyncio.sleep(0.1)  # ya están el principal y el respaldo en marcha
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea
    await asyncio.sleep(0)
    assert llamadas and all(e.is_set() for e in llamadas)
