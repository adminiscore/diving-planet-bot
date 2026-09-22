"""g-7 paso 1: interruptores para retirar los chats antiguos del RAG sin cambiar la conducta por defecto.

Con los valores por defecto el bot debe comportarse exactamente como antes: ninguna fuente excluida
y el bloque de ejemplos (few-shot) en el prompt del RAG. Los interruptores solo cambian algo cuando
se activan por variable de entorno (ver docs/robustness/g7-retirar-conversations-plan.md).
"""

import src.agents.rag_agent as rag
from src.config import Settings, settings
from src.knowledge import vector_store

FEWSHOT_HEADER_ES = "Situaciones reales del centro"


def test_por_defecto_no_se_excluye_ninguna_fuente():
    assert Settings().rag_exclude_sources == ""
    assert vector_store.excluded_sources() == []


def test_por_defecto_el_fewshot_sigue_encendido():
    assert Settings().rag_fewshot_enabled is True


def test_exclusion_admite_varias_fuentes_y_espacios(monkeypatch):
    monkeypatch.setattr(settings, "rag_exclude_sources", " conversations , services,, ")
    assert vector_store.excluded_sources() == ["conversations", "services"]


def test_prompt_por_defecto_igual_que_antes(monkeypatch):
    """Con el interruptor encendido el prompt lleva el bloque de ejemplos cuando hay alguno."""
    monkeypatch.setattr(settings, "rag_fewshot_enabled", True)
    monkeypatch.setattr(
        rag,
        "_select_fewshot_examples",
        lambda q, lang, k=2: [{"scenario": "Cliente pregunta el punto de encuentro", "diving_planet": {"messages": ["Muelle de la Bodeguita"]}}],
    )
    assert FEWSHOT_HEADER_ES in rag.build_system_prompt("es", "¿dónde es el punto de encuentro?")


def test_fewshot_apagado_no_entra_en_el_prompt(monkeypatch):
    monkeypatch.setattr(settings, "rag_fewshot_enabled", False)
    called = []
    monkeypatch.setattr(rag, "_select_fewshot_examples", lambda *a, **k: called.append(1) or [])
    prompt = rag.build_system_prompt("es", "¿dónde es el punto de encuentro?")
    assert FEWSHOT_HEADER_ES not in prompt
    assert not called, "con el few-shot apagado no se deben ni seleccionar ejemplos"
