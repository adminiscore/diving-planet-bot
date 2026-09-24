"""g-7: interruptor generico para que la busqueda ignore fuentes del indice.

Nacio en el paso 1 de g-7 para medir el RAG sin los chats antiguos de WhatsApp. En el
paso 4 (2026-09-24) esos chats (conversations.json) y su few-shot se borraron del codigo
y del indice; el interruptor de fuentes se queda como mecanismo generico, sin reindexar.
"""

from src.config import Settings, settings
from src.knowledge import vector_store


def test_por_defecto_no_se_excluye_ninguna_fuente():
    assert Settings().rag_exclude_sources == ""
    assert vector_store.excluded_sources() == []


def test_exclusion_admite_varias_fuentes_y_espacios(monkeypatch):
    monkeypatch.setattr(settings, "rag_exclude_sources", " faqs , services,, ")
    assert vector_store.excluded_sources() == ["faqs", "services"]


def test_el_interruptor_del_few_shot_ya_no_existe():
    """El few-shot salia de conversations.json: se retiro con el fichero (g-7 paso 4)."""
    assert not hasattr(Settings(), "rag_fewshot_enabled")
