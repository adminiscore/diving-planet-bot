"""rag-3 (30-sep): con el origen del cliente, la búsqueda baja las fichas del OTRO origen (sin flag desde s4-25).
El origen viene de `state.location`, no de leer el resumen (esa detección por frases solo casaba en español)."""
from unittest.mock import AsyncMock

import pytest

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
async def test_la_ficha_del_otro_origen_baja(monkeypatch):
    monkeypatch.setattr(vector_store, "_vector_search",
                        AsyncMock(return_value=[_doc(1, "islas", 0.62), _doc(2, "cartagena", 0.60)]))
    monkeypatch.setattr(vector_store, "_bm25_search", AsyncMock(return_value=[]))
    docs = await vector_store.search_knowledge_base("¿qué incluye?", lang="es", origin="cartagena")
    assert docs[0]["id"] == 2
    # sin origen conocido no cambia nada: la más parecida va primero
    docs = await vector_store.search_knowledge_base("¿qué incluye?", lang="es")
    assert docs[0]["id"] == 1


@pytest.mark.asyncio
async def test_rag_answer_pasa_el_origen_del_estado_a_la_busqueda(monkeypatch):
    from src.agents import rag_agent

    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    await rag_agent.rag_answer("what is included in the snorkel tour?", lang="en", origin="island")
    assert buscar.await_args.kwargs.get("origin") == "islas"


def test_r1_la_rama_de_palabras_busca_la_pregunta_sin_la_marca_y_sin_tildes():
    """RAG R1 (3-nov): con el origen sabido, la última línea de la consulta era la marca del código
    («[origen_cliente]=desde Cartagena») y la rama de palabras buscaba eso (R0)."""
    q = "¿hay que saber nadar?\n\n[origen_cliente]=desde Cartagena"
    assert vector_store.texto_para_palabras(q) == "¿hay que saber nadar?"
    assert vector_store.texto_para_palabras("Do you go out on December 25th?\n\n[origin]=from Cartagena") == \
        "Do you go out on December 25th?"
    # con los mensajes anteriores delante (`build_retrieval_query`), solo la pregunta de ahora
    assert vector_store.texto_para_palabras("somos 3\nquiero el minicurso\n¿cuánto dura la inmersión?") == \
        "¿cuanto dura la inmersion?"


def test_r1_la_fusion_es_por_posiciones_y_un_acierto_suelto_de_palabras_no_tapa_al_vector():
    """RAG R1: antes la nota era max(coseno, palabras normalizadas) + RRF, y la mejor de palabras valía siempre 1,0."""
    vector = [_doc(1, None, 0.80), _doc(2, None, 0.78), _doc(3, None, 0.76)]
    palabras = [dict(_doc(9, None, 1.0), score_bm25=1.0, score_bm25_raw=0.02, retrieval_branches=["bm25"])]
    fusion = vector_store._reciprocal_rank_fusion([(vector, 1.0), (palabras, vector_store.PESO_PALABRAS)])
    orden = [d["id"] for d in fusion]
    assert orden[:2] == [1, 2] and 9 in orden  # entra, pero no por delante de los dos primeros del vector
    # un documento que traen las dos ramas sube
    ambas = vector_store._reciprocal_rank_fusion([(vector, 1.0), ([dict(_doc(3, None, 1.0), retrieval_branches=["bm25"])],
                                                                  vector_store.PESO_PALABRAS)])
    assert [d["id"] for d in ambas][0] == 3


def test_r1_la_base_guarda_el_texto_sin_tildes_con_raices_del_idioma():
    from scripts import kb_v2

    ddl = kb_v2._ddl("kb_v2_r1")
    assert "DROP TABLE IF EXISTS kb_v2_r1.kb_documents" in ddl  # una columna nueva llega también a la base que ya existe
    assert "'english'::regconfig" in ddl and "'spanish'::regconfig" in ddl and "texto_busqueda" in ddl
    assert set(vector_store.CONFIG_DEL_IDIOMA.values()) == {"spanish", "english"}
