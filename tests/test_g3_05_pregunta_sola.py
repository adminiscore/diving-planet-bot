"""G3-05 (17-oct, Claude contra el chatbot): "Precisa saber nadar?" (portugués, conv 5571) recibía "I don't have that
specific requirement handy" aunque la FAQ de saber nadar existe. En el banco G3 pasa igual en español y en inglés:
"salimos de Cartagena el día 30. ¿Hace falta saber nadar?" -> "no tengo ese dato", 3 de 3.

Medido en la búsqueda de PRE: la pregunta sola trae la FAQ la primera; con el origen y la fecha delante, la FAQ no
entra entre las 8 primeras (la tapan las fichas que salen desde Cartagena), y la consulta reescrita, que nombra el
asunto (CAL-D), tampoco la trae. Con el flag `busqueda_con_la_pregunta_sola`, la búsqueda doble usa la PREGUNTA SOLA
(sin los datos que da el cliente, en el idioma de la respuesta) en vez del mensaje entero. Un mensaje corto en el
idioma de la respuesta ya es la pregunta: ni llamada de más ni otra búsqueda.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import query_rewriter as qr
from src.agents import rag_agent
from src.config import settings


def _fake_openai(respuesta, llamadas):
    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            msg = type("M", (), {"content": respuesta})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    return _OpenAI


@pytest.mark.asyncio
async def test_la_pregunta_sola_de_un_mensaje_largo_o_en_otro_idioma(monkeypatch):
    llamadas: list[dict] = []
    monkeypatch.setattr(qr, "AsyncOpenAI", _fake_openai("Do you need to know how to swim?", llamadas))
    monkeypatch.setattr(settings, "busqueda_con_la_pregunta_sola", True)
    assert await qr.pregunta_sola("saímos de Cartagena, dia 30. Precisa saber nadar?", "en") \
        == "Do you need to know how to swim?"
    assert "only the QUESTION" in llamadas[0]["messages"][0]["content"]
    assert await qr.pregunta_sola("we leave from Cartagena on the 30th. Do we need to know how to swim?", "en") \
        == "Do you need to know how to swim?"
    assert len(llamadas) == 2


@pytest.mark.asyncio
async def test_un_mensaje_corto_en_el_idioma_de_la_respuesta_ya_es_la_pregunta(monkeypatch):
    llamadas: list[dict] = []
    monkeypatch.setattr(qr, "AsyncOpenAI", _fake_openai("x", llamadas))
    monkeypatch.setattr(settings, "busqueda_con_la_pregunta_sola", True)
    assert await qr.pregunta_sola("do we need to swim?", "en") is None
    assert await qr.pregunta_sola("¿hace falta saber nadar?", "es") is None
    assert llamadas == []


@pytest.mark.asyncio
async def test_sin_el_flag_no_hay_llamada(monkeypatch):
    llamadas: list[dict] = []
    monkeypatch.setattr(qr, "AsyncOpenAI", _fake_openai("Do you need to know how to swim?", llamadas))
    monkeypatch.setattr(settings, "busqueda_con_la_pregunta_sola", False)
    assert await qr.pregunta_sola("saímos de Cartagena, dia 30. Precisa saber nadar?", "en") is None
    assert llamadas == []


@pytest.mark.asyncio
async def test_la_busqueda_doble_usa_la_pregunta_sola_en_vez_del_mensaje(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    monkeypatch.setattr(rag_agent, "pregunta_sola", AsyncMock(return_value="¿Hace falta saber nadar?"))
    monkeypatch.setattr(settings, "rag_busqueda_doble", True)
    mensaje = "salimos de Cartagena el día 30 y somos dos. ¿Hace falta saber nadar?"
    await rag_agent.rag_answer(mensaje, lang="es", verify_grounding=False)
    assert {c.args[0] for c in buscar.await_args_list} == {mensaje, "¿Hace falta saber nadar?"}


@pytest.mark.asyncio
async def test_sin_pregunta_sola_la_busqueda_doble_sigue_con_el_mensaje(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(return_value="How do I pay for the Fun Dives?"))
    monkeypatch.setattr(rag_agent, "pregunta_sola", AsyncMock(return_value=None))
    monkeypatch.setattr(settings, "rag_busqueda_doble", True)
    await rag_agent.rag_answer("great, how do i pay", lang="en", verify_grounding=False)
    assert {c.args[0] for c in buscar.await_args_list} == {"How do I pay for the Fun Dives?", "great, how do i pay"}
