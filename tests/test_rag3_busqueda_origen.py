"""rag-3 (30-sep): con el origen del cliente, la búsqueda baja las fichas del OTRO origen (flag `rag_busqueda_origen`).
El origen viene de `state.location`, no de leer el resumen (esa detección por frases solo casaba en español)."""
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.knowledge import vector_store


def _doc(i, origin, score):
    return {"id": i, "content": f"doc {i}", "metadata": {"source": "services", "origin": origin} if origin else
            {"source": "faqs"}, "score": score, "score_vector": score, "retrieval_branches": ["vector"]}


def test_penalizar_otro_origen_solo_toca_las_fichas_del_otro_origen():
    docs = [dict(_doc(1, "islas", 0.7), score_final=0.7), dict(_doc(2, "cartagena", 0.6), score_final=0.6),
            dict(_doc(3, None, 0.5), score_final=0.5)]
    out = {d["id"]: d["score_final"] for d in vector_store.penalizar_otro_origen(docs, "cartagena")}
    assert out == {1: pytest.approx(0.7 - vector_store.PENALIZACION_OTRO_ORIGEN), 2: 0.6, 3: 0.5}
    assert vector_store.penalizar_otro_origen(docs, None) is docs


@pytest.mark.asyncio
async def test_la_ficha_del_otro_origen_baja_solo_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "rag_kb_v2", True)
    monkeypatch.setattr(vector_store, "_vector_search",
                        AsyncMock(return_value=[_doc(1, "islas", 0.62), _doc(2, "cartagena", 0.60)]))
    monkeypatch.setattr(vector_store, "_bm25_search", AsyncMock(return_value=[]))
    for flag, primero in ((False, 1), (True, 2)):
        monkeypatch.setattr(settings, "rag_busqueda_origen", flag)
        docs = await vector_store.search_knowledge_base("¿qué incluye?", lang="es", origin="cartagena")
        assert docs[0]["id"] == primero


@pytest.mark.asyncio
async def test_rag_answer_pasa_el_origen_del_estado_a_la_busqueda(monkeypatch):
    from src.agents import rag_agent

    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    for flag, esperado in ((False, None), (True, "islas")):
        monkeypatch.setattr(settings, "rag_busqueda_origen", flag)
        buscar.reset_mock()
        await rag_agent.rag_answer("what is included in the snorkel tour?", lang="en", origin="island",
                                   verify_grounding=False)
        assert buscar.await_args.kwargs.get("origin") == esperado
