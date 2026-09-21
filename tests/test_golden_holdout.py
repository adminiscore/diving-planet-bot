"""Anti-contaminacion del golden-set (Fase G, G1).

Los chats reales reservados como EXAMEN no pueden aparecer como few-shot del RAG: si el
modelo ve en el prompt la conversacion que luego le vamos a puntuar, la nota sube sin que
el bot sea mejor. `_load_conversations_cached` es el unico punto de carga, asi que filtrar
ahi cubre todos los caminos.
"""

import src.agents.rag_agent as rag
from src.knowledge.loader import load_golden_holdout_chats


def _reset_cache():
    rag._CONVERSATIONS_CACHE = None


def test_holdout_existe_y_no_esta_vacio():
    """Si el minador ya corrio, debe haber chats de examen reservados."""
    ids = (load_golden_holdout_chats() or {}).get("holdout_chat_ids") or []
    assert ids, "no hay chats de examen: corre docs/robustness/golden-set/mine_conversations.py"


def test_ningun_chat_de_examen_llega_al_fewshot():
    _reset_cache()
    holdout = set((load_golden_holdout_chats() or {}).get("holdout_chat_ids") or [])
    cargados = {rag._holdout_chat_of(e.get("id", "")) for e in rag._load_conversations_cached()}
    assert not (cargados & holdout), f"chats de examen visibles para el few-shot: {cargados & holdout}"
    _reset_cache()


def test_el_fewshot_sigue_devolviendo_ejemplos():
    """El filtro no puede dejar el few-shot seco: debe quedar material de entrenamiento."""
    _reset_cache()
    assert rag._load_conversations_cached(), "el holdout se ha comido todos los ejemplos"
    ejemplos = rag._select_fewshot_examples("cuanto cuesta bucear certificado", "es", k=2)
    holdout = set((load_golden_holdout_chats() or {}).get("holdout_chat_ids") or [])
    assert all(rag._holdout_chat_of(e.get("id", "")) not in holdout for e in ejemplos)
    _reset_cache()
