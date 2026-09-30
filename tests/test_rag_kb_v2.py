"""rag-2: la base curada (scripts/kb_v2.py) y el flag `rag_kb_v2` (sin red ni base de datos)."""
import re
from unittest.mock import AsyncMock, patch

import pytest

from scripts.kb_v2 import build_kb_v2
from src.config import settings
from src.knowledge import vector_store


@pytest.fixture(scope="module")
def docs():
    return build_kb_v2()


def test_una_ficha_por_servicio_y_origen_en_cada_idioma(docs):
    fichas = [d for d in docs if d["metadata"]["key"].startswith("ficha:")
              and not d["metadata"]["key"].startswith("ficha:refresher:")]  # las del refresher, en su test
    por_idioma = {lang: {d["metadata"]["service_id"] for d in fichas if d["metadata"]["lang"] == lang}
                  for lang in ("es", "en")}
    assert por_idioma["es"] == por_idioma["en"] and len(por_idioma["es"]) == len(fichas) // 2
    ow = next(d for d in fichas if d["metadata"]["key"] == "ficha:open_water" and d["metadata"]["lang"] == "es")
    assert "saliendo desde Cartagena" in ow["content"] and "2.450.000 COP" in ow["content"]
    assert ow["metadata"]["origin"] == "cartagena"


def test_sin_telefono_ni_trozos_de_precios(docs):
    assert not [d["metadata"]["key"] for d in docs if re.search(r"\+57|whats\s?app|320\s?231", d["content"], re.I)]
    assert not [d for d in docs if d["metadata"]["source"] == "pricing"]
    # las 25 FAQs de servicio, la instrucción para el bot (87) y las listas de precios (120-121) no están
    faqs = {d["metadata"]["key"] for d in docs if d["metadata"]["source"] == "faqs"}
    assert not {"faq:31", "faq:55", "faq:87", "faq:120", "faq:121"} & faqs


def test_cada_regla_con_sus_formas_de_preguntarla(docs):
    reglas = [d for d in docs if d["metadata"]["source"] == "policies"]
    assert reglas and all(d["content"].startswith(("Pregunta:", "Question:")) for d in reglas)


@pytest.mark.asyncio
async def test_el_flag_elige_el_esquema_de_la_busqueda(monkeypatch):
    for flag, esperado in ((False, None), (True, {"search_path": "kb_v2,public"})):
        monkeypatch.setattr(vector_store, "_pool", None)
        monkeypatch.setattr(settings, "rag_kb_v2", flag)
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=object())) as crear:
            await vector_store._get_pool()
        assert crear.call_args.kwargs["server_settings"] == esperado
    monkeypatch.setattr(vector_store, "_pool", None)


@pytest.mark.asyncio
async def test_con_la_base_v2_no_hay_empujones_por_regex(monkeypatch):
    """Una política con más similitud no puede quedar por debajo de una FAQ por el empujón de su tema."""
    politica = {"id": 1, "content": "maleta", "metadata": {"source": "policies", "topics": []},
                "score": 0.60, "score_vector": 0.60, "retrieval_branches": ["vector"]}
    faq = {"id": 2, "content": "equipo", "metadata": {"source": "faqs", "topics": ["equipment"]},
           "score": 0.55, "score_vector": 0.55, "retrieval_branches": ["vector"]}
    monkeypatch.setattr(vector_store, "_vector_search", AsyncMock(return_value=[politica, faq]))
    monkeypatch.setattr(vector_store, "_bm25_search", AsyncMock(return_value=[]))
    for flag, primero in ((True, 1), (False, 2)):
        monkeypatch.setattr(settings, "rag_kb_v2", flag)
        docs = await vector_store.search_knowledge_base("¿qué equipo llevo?", lang="es")
        assert docs[0]["id"] == primero


def test_el_refresher_tiene_ficha_propia_por_origen_y_es_la_del_minicurso(docs):
    """rag-3 (30-sep, Gadea: "el refresher es la misma info que el minicurso"): una ficha por origen e idioma, con
    el formulario médico que piden cursos y minicursos."""
    fichas = {(d["metadata"]["origin"], d["metadata"]["lang"]): d for d in docs
              if d["metadata"]["key"].startswith("ficha:refresher:")}
    assert set(fichas) == {(o, lang) for o in ("cartagena", "islas") for lang in ("es", "en")}
    es = fichas[("cartagena", "es")]
    assert es["content"].startswith("Ficha del servicio: Refresher") and "Minicurso de Buceo" in es["content"]
    assert "formulario médico" in es["content"] and es["metadata"]["service_id"] == "minicourse"


@pytest.mark.asyncio
async def test_el_esquema_de_la_base_v2_se_puede_cambiar_para_medir(monkeypatch):
    monkeypatch.setattr(vector_store, "_pool", None)
    monkeypatch.setattr(settings, "rag_kb_v2", True)
    monkeypatch.setattr(settings, "rag_kb_esquema", "kb_v2_prueba")
    with patch("asyncpg.create_pool", new=AsyncMock(return_value=object())) as crear:
        await vector_store._get_pool()
    assert crear.call_args.kwargs["server_settings"] == {"search_path": "kb_v2_prueba,public"}
    monkeypatch.setattr(vector_store, "_pool", None)
