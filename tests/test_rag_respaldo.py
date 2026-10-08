"""8-oct (cambio de modelos): la respuesta del RAG con respaldo (`rag_agent.generar_con_respaldo`). Si el modelo
principal (GPT-6 Luna) tarda más de `rag_respaldo_segundos`, se lanza el de respaldo en paralelo y gana el primero."""

import asyncio
from types import SimpleNamespace

import pytest

from src.agents.rag_agent import generar_con_respaldo
from src.config import settings


class _Cliente:
    def __init__(self, tiempos: dict, fallan: tuple = ()):
        self.tiempos, self.fallan, self.llamadas, self.canceladas = tiempos, fallan, [], []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, model, **_):
        self.llamadas.append(model)
        try:
            await asyncio.sleep(self.tiempos[model])
        except asyncio.CancelledError:
            self.canceladas.append(model)
            raise
        if model in self.fallan:
            raise RuntimeError("caido")
        return model


@pytest.fixture
def _modelos(monkeypatch):
    monkeypatch.setattr(settings, "rag_answer_model", "luna")
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "mini")
    monkeypatch.setattr(settings, "rag_respaldo_segundos", 0.05)


async def test_sin_respaldo_es_la_llamada_de_siempre(monkeypatch, _modelos):
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "")
    c = _Cliente({"luna": 0.1})
    assert await generar_con_respaldo(c, []) == "luna" and c.llamadas == ["luna"]


async def test_principal_rapido_no_lanza_el_respaldo(_modelos):
    c = _Cliente({"luna": 0.01, "mini": 0.01})
    assert await generar_con_respaldo(c, []) == "luna" and c.llamadas == ["luna"]


async def test_principal_lento_gana_el_respaldo_y_se_cancela_el_principal(_modelos):
    c = _Cliente({"luna": 0.5, "mini": 0.02})
    assert await generar_con_respaldo(c, []) == "mini"
    await asyncio.sleep(0)
    assert c.llamadas == ["luna", "mini"] and c.canceladas == ["luna"]


async def test_principal_lento_pero_termina_antes_que_el_respaldo(_modelos):
    c = _Cliente({"luna": 0.07, "mini": 0.5})
    assert await generar_con_respaldo(c, []) == "luna"
    await asyncio.sleep(0)
    assert c.canceladas == ["mini"]


async def test_si_el_principal_falla_contesta_el_respaldo(_modelos):
    c = _Cliente({"luna": 0.01, "mini": 0.01}, fallan=("luna",))
    assert await generar_con_respaldo(c, []) == "mini"


async def test_si_fallan_los_dos_sube_el_error(_modelos):
    c = _Cliente({"luna": 0.5, "mini": 0.06}, fallan=("luna", "mini"))
    with pytest.raises(RuntimeError):
        await generar_con_respaldo(c, [])
