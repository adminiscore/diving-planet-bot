"""Tracing del cliente OpenAI para LangSmith (Fase 5.3 — observabilidad).

`trace_openai(client)` envuelve un cliente `AsyncOpenAI` ya instanciado con
`langsmith.wrappers.wrap_openai` **solo si LangSmith está activo** (hay
`langsmith_api_key` + `langchain_tracing_v2`), para que **cada llamada LLM**
(chat + embeddings) se trace en LangSmith con tokens/latencia/coste — el detalle
por-llamada que el grafo LangGraph no captura solo.

Se envuelve el cliente en su sitio (`trace_openai(AsyncOpenAI(...))`) en vez de
una fábrica que instancia, para NO cambiar el punto donde cada módulo referencia
`AsyncOpenAI` (los tests lo mockean vía `monkeypatch.setattr(mod, "AsyncOpenAI",
...)`; con tracing off, `trace_openai` devuelve el mock intacto).

Diseño:
- **Cero overhead/cambio cuando el tracing está off** (dev sin cuenta, CI con key
  falsa, tests): devuelve el cliente tal cual.
- **Nunca rompe las llamadas por el tracing**: si `wrap_openai` fallara, degrada
  al cliente sin envolver.
- Import perezoso de `langsmith` dentro de la función (no se paga a import).
"""

from __future__ import annotations

import logging
from typing import TypeVar

from src.config import settings

logger = logging.getLogger("uvicorn.error")

_C = TypeVar("_C")


def trace_openai(client: _C) -> _C:
    """Devuelve `client` envuelto para LangSmith si el tracing está activo; si no,
    lo devuelve sin tocar (no-op)."""
    if settings.langchain_tracing_v2 and settings.langsmith_api_key:
        try:
            from langsmith.wrappers import wrap_openai

            return wrap_openai(client)
        except Exception as exc:  # noqa: BLE001 — el tracing nunca debe romper el bot
            logger.warning(f"[LANGSMITH] wrap_openai falló, sigo sin trazar el cliente: {exc}")
    return client
