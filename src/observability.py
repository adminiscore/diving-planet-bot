"""Observabilidad con Langfuse (Fase 5.3 / robustez tarea 8).

Sustituye a LangSmith (cuota Developer agotada). Langfuse Cloud Hobby da más
margen; ver `docs/robustness/progress-log.md` "Tarea 8".

## Qué traza
- El **grafo LangGraph** (nodos + latencia/turno) vía `langfuse.langchain.CallbackHandler`,
  pasado como callback en `graph.run_turn_via_graph`.
- **Cada llamada LLM** (chat + embeddings) vía la integración drop-in
  `langfuse.openai` (`llm_client.trace_openai`).

## Privacidad (decisión del owner)
Las trazas salen a un tercero (Langfuse Cloud), así que se enmascara el PII con
`privacy.redact_pii` ANTES de enviarlo, vía el `mask` del cliente Langfuse
(`_mask`, recursivo sobre strings/dicts/listas).

## Seguro por diseño
- **`langfuse` SOLO se importa cuando hay claves** (= PRE, Python 3.11). Sin
  claves (dev/CI/tests, o el dev local en Python 3.14 donde el `api` generado de
  langfuse no importa por pydantic.v1), todo es no-op y `langfuse` nunca se
  importa → cero coste y sin el crash de import.
- Nunca rompe el bot: cada punto degrada a "sin trazar" si algo falla.
- Módulo hoja (solo importa `privacy`): no crea ciclos con `config`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")


def langfuse_enabled(s: Any) -> bool:
    """True si hay claves de Langfuse y el tracing no está desactivado por env
    (`LANGFUSE_TRACING_ENABLED=false`, que ponen las baterías/eval en
    `scripts/__init__.py` para no gastar cuota)."""
    if os.environ.get("LANGFUSE_TRACING_ENABLED", "").strip().lower() == "false":
        return False
    return bool(getattr(s, "langfuse_public_key", "") and getattr(s, "langfuse_secret_key", ""))


def _mask(*, data: Any, **_kwargs: Any) -> Any:
    """Máscara de PII para Langfuse (firma `MaskFunction`: keyword `data`).
    Aplica `redact_pii` recursivamente a los strings. Nunca lanza: ante un fallo
    devuelve un marcador, nunca el dato en claro."""
    try:
        if isinstance(data, str):
            return redact_pii(data)
        if isinstance(data, dict):
            return {k: _mask(data=v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return type(data)(_mask(data=v) for v in data)
        return data
    except Exception:  # noqa: BLE001 — la máscara nunca deja pasar PII sin enmascarar
        return "[REDACTED]"


def init_langfuse(s: Any) -> None:
    """Inicializa el cliente singleton de Langfuse con la máscara de PII, si el
    tracing está activo. Lo llama `config` al arrancar. Sin claves no importa
    langfuse (3.14-safe). Nunca rompe el arranque."""
    if not langfuse_enabled(s):
        return
    try:
        from langfuse import Langfuse

        Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=(getattr(s, "langfuse_host", "") or "https://cloud.langfuse.com"),
            environment=(getattr(s, "app_env", None) or "default"),
            mask=_mask,
        )
        logger.info("[LANGFUSE] tracing activado (environment=%s)", getattr(s, "app_env", "default"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LANGFUSE] no se pudo activar el tracing: %s", exc)


def traced_openai_client(s: Any):
    """Cliente `AsyncOpenAI` trazado por Langfuse (drop-in `langfuse.openai`) si
    el tracing está activo; si no, `None` (el caller usa el cliente pelado)."""
    if not langfuse_enabled(s):
        return None
    try:
        from langfuse.openai import AsyncOpenAI as _LangfuseAsyncOpenAI

        return _LangfuseAsyncOpenAI(api_key=s.openai_api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LANGFUSE] no se pudo envolver el cliente OpenAI: %s", exc)
        return None


def langfuse_callback_handler(s: Any):
    """`CallbackHandler` de Langfuse para la invocación del grafo LangGraph, o
    `None` si el tracing está off."""
    if not langfuse_enabled(s):
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LANGFUSE] no se pudo crear el callback handler: %s", exc)
        return None
