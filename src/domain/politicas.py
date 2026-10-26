"""Las políticas del negocio, de `data/knowledge_base/policies.json`, en UN lector (lat-deuda-u, 26-oct). Antes las leían
por separado el catálogo y la tabla de hechos. Vive en el dominio (solo stdlib) para que también la puedan usar los
prompts, que no importan nada más de `src/`."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

POLICIES_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "policies.json"


@lru_cache(maxsize=1)
def politicas() -> dict:
    datos = json.loads(POLICIES_PATH.read_text(encoding="utf-8-sig"))
    return datos.get("policies", datos)


def politica(clave: str, lang: str) -> str | None:
    """El texto de una política en el idioma del cliente (en español si no está en el suyo)."""
    valor = politicas().get(clave)
    if isinstance(valor, dict):
        return valor.get("es" if lang == "es" else "en") or valor.get("es")
    return valor


def politica_breve(clave: str, lang: str) -> str | None:
    """La versión breve de una política (`breve_es` / `breve_en`), para un mensaje corto o un prompt."""
    valor = politicas().get(clave)
    return (valor.get(f"breve_{'es' if lang == 'es' else 'en'}") or None) if isinstance(valor, dict) else None
