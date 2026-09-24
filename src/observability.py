"""Observabilidad con Langfuse (Fase 5.3 / robustez tarea 8).

Sustituye a LangSmith (cuota Developer agotada). Langfuse Cloud Hobby da más
margen; ver `docs/robustness/progress-log.md` "Tarea 8".

## Qué traza
- **Una traza raíz `turno` por mensaje** (`turn_trace`, abierta en
  `supervisor.route_message`): todo lo del turno cuelga de ella y lleva un
  RESUMEN del turno en la metadata (agente, tipo de turno, RAG, idioma, paso,
  link de pago, escalado, error) y `session_id` = conversación. Arranca en un
  contexto de OpenTelemetry LIMPIO y se cierra siempre: antes, el contexto de
  traza de un turno podía quedarse como "actual" en la tarea de larga duración
  que procesa los mensajes, y los turnos siguientes heredaban su id de traza (una
  traza de PRE juntó 8 turnos en 50 min el 2026-09-17).
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

import contextlib
import contextvars
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")

BOOKING_LINK = "book.divingplanet.org"

# Hechos del turno en curso (los apuntan el grafo y el RAG con `note_turn`). Un dict
# por turno: las tareas hijas (`asyncio.create_task`) heredan la MISMA referencia, asi
# que lo que apunten tambien cuenta.
_TURN_FACTS: contextvars.ContextVar[dict | None] = contextvars.ContextVar("coral_turn_facts", default=None)

# Agente del grafo -> tipo de turno (el RAG manda: una pregunta de informacion la
# resuelve el agente booking llamando al RAG, no el agente info).
_TURN_TYPE_BY_ROUTE = {
    "booking": "reserva",
    "info": "info",
    "safety": "escalado",
    "changes": "cambios",
    "deflection": "deflection",
}


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

        # r6-1: timeout por llamada YA en la construcción. Es el camino de PRE
        # (tracing on), así que aquí es donde de verdad protege al cliente: sin
        # esto el default del SDK es read=600 s con 2 reintentos (~30 min colgado).
        return _LangfuseAsyncOpenAI(
            api_key=s.openai_api_key,
            timeout=getattr(s, "llm_timeout_seconds", 30.0),
            http_client=metered_http_client(),  # medición propia (TURN_METRICS)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LANGFUSE] no se pudo envolver el cliente OpenAI: %s", exc)
        return None


# ── Medición propia, sin Langfuse (2026-09-24) ─────────────────────────────────────
# Se superó el plan gratuito de Langfuse (reinicio el 16-oct). Cada turno escribe en el
# log UNA línea `[TURN_METRICS] {json}` con su resumen, las llamadas al LLM (cuántas,
# cuánto tardan, modelo) y el tiempo de cada nodo del grafo; `scripts/turn_metrics.py`
# la lee por SSH y saca las mismas cifras que las fotos de Langfuse. Sin texto del
# cliente ni de la respuesta: solo etiquetas, contadores y tiempos. Nunca rompe el turno.
TURN_METRICS_TAG = "[TURN_METRICS]"
_METERED_HTTP: dict[int, Any] = {}


def record_llm_call(kind: str, seconds: float, model: str | None = None) -> None:
    """Apunta una llamada al LLM (`chat` o `embedding`) en el turno en curso."""
    current = _TURN_FACTS.get()
    if current is not None:
        current.setdefault("_llm", []).append({"kind": kind, "s": round(seconds, 4), "model": model})


async def _on_request(request) -> None:
    request.extensions["coral_t0"] = time.perf_counter()


async def _on_response(response) -> None:
    try:
        request = response.request
        t0 = request.extensions.get("coral_t0")
        path = request.url.path
        kind = "chat" if path.endswith("/chat/completions") else "embedding" if path.endswith("/embeddings") else None
        if t0 is None or kind is None:
            return
        model = None
        try:
            model = json.loads(request.content or b"{}").get("model")
        except Exception:  # noqa: BLE001
            pass
        record_llm_call(kind, time.perf_counter() - t0, model)
    except Exception:  # noqa: BLE001 — medir nunca rompe una llamada
        pass


def metered_http_client():
    """Cliente HTTP para los clientes OpenAI que cronometra cada llamada al LLM. Uno por
    bucle de eventos (un cliente httpx no se comparte entre bucles)."""
    import asyncio

    from openai import DefaultAsyncHttpxClient

    try:
        key = id(asyncio.get_running_loop())
    except RuntimeError:
        key = 0
    client = _METERED_HTTP.get(key)
    if client is None or client.is_closed:
        client = DefaultAsyncHttpxClient(event_hooks={"request": [_on_request], "response": [_on_response]})
        _METERED_HTTP[key] = client
    return client


def node_timer(facts: dict):
    """Callback de LangChain que cronometra los nodos del grafo en `facts` (mismo criterio
    que la foto de Langfuse: se ignoran `LangGraph` y las funciones de ruta `_...`)."""
    from langchain_core.callbacks import BaseCallbackHandler

    class _NodeTimer(BaseCallbackHandler):
        run_inline = True  # en el bucle del turno, no en un hilo

        def __init__(self):
            self._open: dict = {}

        def on_chain_start(self, serialized, inputs, *, run_id, **kwargs):
            name = kwargs.get("name") or (serialized or {}).get("name") or ""
            if name and name != "LangGraph" and not name.startswith("_"):
                self._open[run_id] = (name, time.perf_counter())

        def _close(self, run_id):
            started = self._open.pop(run_id, None)
            if started:
                name, t0 = started
                nodes = facts.setdefault("_nodes", {})
                nodes[name] = round(nodes.get(name, 0.0) + time.perf_counter() - t0, 4)

        def on_chain_end(self, outputs, *, run_id, **kwargs):
            self._close(run_id)

        def on_chain_error(self, error, *, run_id, **kwargs):
            self._close(run_id)

    return _NodeTimer()


def current_turn_facts() -> dict | None:
    return _TURN_FACTS.get()


def turn_metrics_line(conversation_id: str, facts: dict, started_at: str, seconds: float) -> str:
    """La línea `[TURN_METRICS]` del turno: el resumen (sin texto) + llamadas + nodos."""
    calls = facts.get("_llm") or []
    chats = [c for c in calls if c["kind"] == "chat"]
    models: dict[str, int] = {}
    for c in chats:
        if c.get("model"):
            models[c["model"]] = models.get(c["model"], 0) + 1
    payload = {
        "conv": str(conversation_id),
        "start": started_at,
        "latency": round(seconds, 3),
        **turn_summary(facts, facts.get("reply")),
        "llm_calls": len(chats),
        "embeddings": len(calls) - len(chats),
        "llm_seconds": round(sum(c["s"] for c in chats), 3),
        "models": models,
        "nodes": facts.get("_nodes") or {},
    }
    return f"{TURN_METRICS_TAG} {json.dumps(payload, ensure_ascii=False, default=str)}"


def note_turn(**facts: Any) -> None:
    """Apunta hechos del turno en curso para su resumen (no-op fuera de un turno).
    Barato y sin dependencias: se puede llamar desde cualquier capa."""
    current = _TURN_FACTS.get()
    if current is not None:
        current.update(facts)


def turn_summary(facts: dict, reply: str | None) -> dict:
    """Resumen de un turno a partir de sus hechos y la respuesta final. Sin PII:
    solo etiquetas, booleanos y el paso de la reserva."""
    route = facts.get("route")
    if facts.get("rag_used"):
        turn_type = "rag"
    elif facts.get("greeting"):
        turn_type = "saludo"
    else:
        turn_type = _TURN_TYPE_BY_ROUTE.get(route or "", "otro")
    return {
        "turn_type": turn_type,
        "route": route,
        "rag_used": bool(facts.get("rag_used")),
        "language": facts.get("language"),
        "step": facts.get("step"),
        # Embudo de negocio (m0-5): actividad elegida -> carrito con personas -> link de pago.
        "activity_chosen": bool(facts.get("activity_chosen")),
        "cart_items": facts.get("cart_items"),
        "booking_link_sent": bool(reply and BOOKING_LINK in reply),
        "escalated": bool(facts.get("escalated")),
        "fallback": bool(facts.get("fallback")),
        "error": facts.get("error"),
        # U3 (u3-1): "jev" o "llm_fallback" cuando Jev está encendido; None = router LLM de siempre.
        "router": facts.get("router"),
        "router_ms": facts.get("router_ms"),
    }


@contextlib.asynccontextmanager
async def turn_trace(s: Any, conversation_id: str, message: str) -> AsyncIterator[dict]:
    """Envuelve UN turno: traza raiz `turno` en un contexto de OpenTelemetry limpio,
    que se cierra siempre (tambien con error o cancelacion), con el resumen del
    turno y `session_id` = conversacion. Devuelve el dict de hechos del turno; el
    llamador pone `facts["reply"]` al terminar.

    Sin tracing activo no importa nada y solo recoge los hechos. Si Langfuse
    falla, el turno sigue sin trazar: la observabilidad nunca rompe el bot."""
    facts: dict = {}
    facts_token = _TURN_FACTS.set(facts)
    t0 = time.perf_counter()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    span_cm = span = otel_context = otel_token = None
    if langfuse_enabled(s):
        try:
            from langfuse import get_client
            from opentelemetry import context as otel_context

            otel_token = otel_context.attach(otel_context.Context())  # raiz limpia
            span_cm = get_client().start_as_current_span(name="turno", input={"message": message})
            span = span_cm.__enter__()
            span.update_trace(name="turno", session_id=conversation_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LANGFUSE] no se pudo abrir la traza del turno: %s", exc)
            span_cm = span = None
    try:
        yield facts
    except BaseException as exc:  # incluye CancelledError: queda en el resumen y se relanza
        facts["error"] = type(exc).__name__
        raise
    finally:
        if span is not None:
            try:
                reply = facts.get("reply")
                summary = turn_summary(facts, reply)
                tags = [f"tipo:{summary['turn_type']}", f"lang:{summary['language']}"]
                # Claves PLANAS: Langfuse devuelve la metadata anidada como texto y la
                # recorta (~200 caracteres); un resumen anidado llegaba cortado e ilegible.
                flat = {("turn_type" if k == "turn_type" else f"turn_{k}"): v for k, v in summary.items()}
                span.update(output={"reply": reply}, metadata=flat)
                span.update_trace(output={"reply": reply}, metadata=flat, tags=tags)
                span_cm.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[LANGFUSE] no se pudo cerrar la traza del turno: %s", exc)
        if otel_token is not None:
            try:
                otel_context.detach(otel_token)
            except Exception:  # noqa: BLE001 — un detach fuera de orden no debe romper el turno
                pass
        try:  # medición propia: una línea por turno, con o sin Langfuse
            logger.info(turn_metrics_line(conversation_id, facts, started_at, time.perf_counter() - t0))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[TURN_METRICS] no se pudo escribir: %s", exc)
        _TURN_FACTS.reset(facts_token)


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
