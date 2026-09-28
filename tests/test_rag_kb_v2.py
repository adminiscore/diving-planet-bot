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
    fichas = [d for d in docs if d["metadata"]["key"].startswith("ficha:")]
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
