"""lat-1 (24-oct, fase LAT; Gadea #1731): un solo escritor por turno. Si Jev dice que el mensaje solo pide cosas de la
tabla (intenciones y nada más), lo contesta el redactor de hechos y la respuesta adelantada del RAG se cancela en el
enrutador, antes de que escriba y se revise. Si el mensaje trae otra cosa (o Jev calla), sigue como siempre. Sin red."""
import asyncio

import pytest

from src.agents import conversational_core as core
from src.agents import jev_router as j
from src.agents import supervisor
from src.config import settings
from src.flows.state import ConversationState
from src.orchestration import graph


@pytest.fixture
def adelantado(monkeypatch):
    monkeypatch.setattr(settings, "hechos_por_codigo", True)
    monkeypatch.setattr(core, "lanzar_extraccion_adelantada", lambda *a, **k: None)
    tareas = []

    def lanzar(state, message):
        async def _rag():
            await asyncio.sleep(10)
            return "respuesta del RAG"

        tarea = asyncio.ensure_future(_rag())
        tareas.append(tarea)
        state._rag_adelantado = {"task": tarea, "huella": (), "mensaje": message, "avisos_dados": []}

    monkeypatch.setattr(core, "lanzar_rag_adelantado", lanzar)
    return tareas


def _senales(monkeypatch, senales):
    async def detect(*a, **k):
        return senales

    monkeypatch.setattr(supervisor, "detect_routing_signals", detect)


async def _turno(mensaje):
    st = ConversationState(conversation_id="lat1", language="es")
    await graph._router_node({"conv_state": st, "message": mensaje})
    return st


@pytest.mark.asyncio
async def test_si_contesta_la_tabla_se_cancela_el_rag_adelantado(adelantado, monkeypatch):
    _senales(monkeypatch, {j.PIDE_PRECIO: True, j.PIDE_OTRA_COSA: False})
    st = await _turno("¿Cuánto cuesta el snorkel?")
    await asyncio.sleep(0)
    assert st._rag_adelantado is None and adelantado[0].cancelled()


@pytest.mark.asyncio
@pytest.mark.parametrize("otra_cosa", [True, None])
async def test_si_trae_otra_cosa_o_jev_calla_sigue_el_adelantado(adelantado, monkeypatch, otra_cosa):
    _senales(monkeypatch, {j.PIDE_PRECIO: True, j.PIDE_OTRA_COSA: otra_cosa})
    st = await _turno("¿Cuánto cuesta el snorkel y qué peces se ven?")
    assert st._rag_adelantado is not None and not adelantado[0].cancelled()
    adelantado[0].cancel()
