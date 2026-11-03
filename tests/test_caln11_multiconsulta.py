"""CALN-11 (3-nov, Gadea #2783): con varias preguntas en el mensaje se busca también por cada una y lo que solo trae
cada pregunta va detrás de lo de siempre («¿Cuánto es por persona? ¿Se puede llevar cava a bordo?»)."""
from unittest.mock import AsyncMock

import pytest

from src.agents import rag_agent


@pytest.mark.parametrize("texto, preguntas", [
    ("Somos 7 chicas de Madrid. ¿Cuánto es por persona? ¿Se puede llevar cava a bordo?",
     ["Somos 7 chicas de Madrid. ¿Cuánto es por persona?", "¿Se puede llevar cava a bordo?"]),
    ("How much is it? Can we bring beer on the boat?", ["How much is it?", "Can we bring beer on the boat?"]),
    ("¿Cuánto cuesta el snorkel?", []),  # una sola: lo de siempre
    ("Quiero bucear el sábado", []),
    ("¿Cuánto es lo mío? ¿y? ¿El bebé paga?", ["¿Cuánto es lo mío?", "¿El bebé paga?"]),  # «¿y?» no es pregunta
    ("¿a? ¿Precio del minicurso? ¿Hay baño? ¿Hay parqueadero? ¿Puedo llevar a mi perro?",
     ["¿Precio del minicurso?", "¿Hay baño?", "¿Hay parqueadero?"]),  # como mucho MAX_PREGUNTAS
])
def test_las_preguntas_del_mensaje(texto, preguntas):
    assert rag_agent.preguntas_del_mensaje(texto) == preguntas


def _docs(prefijo, n):
    return [{"id": f"{prefijo}{i}", "content": f"{prefijo} {i}", "metadata": {"source": "faqs"},
             "score": 0.9, "score_vector": 0.9} for i in range(n)]


@pytest.mark.asyncio
async def test_se_busca_tambien_por_cada_pregunta(monkeypatch):
    buscar = AsyncMock(return_value=[])  # sin piezas no se llama al escritor
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    mensaje = "Somos 7 chicas de Madrid. ¿Cuánto es por persona? ¿Se puede llevar cava a bordo?"
    await rag_agent.rag_answer(mensaje, lang="es")
    consultas = [c.args[0] for c in buscar.await_args_list]
    assert consultas[0] == mensaje and "¿Se puede llevar cava a bordo?" in consultas
    assert "Somos 7 chicas de Madrid. ¿Cuánto es por persona?" in consultas


def test_lo_de_cada_pregunta_entra_hasta_el_limite():
    out = rag_agent.fusionar_busquedas(_docs("grupo", 8), _docs("alcohol", 3), extra=rag_agent.POR_PREGUNTA_EXTRA)
    assert [d["id"] for d in out[8:]] == ["alcohol0", "alcohol1"]


@pytest.mark.asyncio
async def test_con_una_pregunta_no_hay_busquedas_de_mas(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    await rag_agent.rag_answer("¿Se puede llevar cava a bordo?", lang="es")
    assert buscar.await_count == 1
