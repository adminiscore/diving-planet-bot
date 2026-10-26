"""Las decisiones de Gadea sobre la conducta del bot (`data/knowledge_base/decisiones.json`, 26-oct): UN sitio para la
decisión, lo que el juez da por correcto (`texto`) y lo que se le dice al escritor (`instruccion_es`/`instruccion_en`).
Lo leen los prompts de los escritores (lat-9 paso 1, `src/prompts/info.reglas_del_escritor`)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DECISIONES_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "decisiones.json"


@lru_cache(maxsize=1)
def _por_id() -> dict[str, dict]:
    datos = json.loads(DECISIONES_PATH.read_text(encoding="utf-8"))["decisiones"]
    return {d["id"]: d for d in datos}


def instruccion(decision: str, lang: str) -> str:
    """El texto que lee el escritor para aplicar la decisión. KeyError si la decisión no existe o no lleva instrucción."""
    return _por_id()[decision][f"instruccion_{'es' if lang == 'es' else 'en'}"]
