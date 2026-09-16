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

import json
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


def _is_empty_for(spec: dict, value) -> bool:
    """¿Es `value` la forma del LLM de decir "nada" en un campo con este esquema? En un
    booleano `false` es un dato; en el resto (enum de texto, objeto, lista, numero) el LLM
    rellena con `false` o null lo que no tiene (medido en el hallazgo D)."""
    if value is None:
        return True
    if spec.get("type") == "boolean":
        return False
    return value is False or value == "" or value == [] or value == {}


def tool_arguments(tool_call, tool: dict) -> dict:
    """Argumentos de una llamada a tool, reencajados en el esquema de ESE tool. Punto
    unico de lectura para todos los tools del bot (2026-09-15).

    Por que (hallazgo D): con "¿va a llover mañana en cartagena?" el LLM del router
    devolvia `{"weather_conditions": true}` -- un valor del enum de `sensitive_topic`
    sacado a clave propia -- en vez de `{"sensitive_topic": "weather_conditions"}`.
    Nadie leia esa clave y la pregunta de pronostico no se escalaba. Es un fallo de
    FORMA, no de vocabulario, asi que se arregla desde el esquema: una clave que el tool
    no declara, con valor `true`, que es valor del enum de UN solo campo, vuelve a ese
    campo si este no trae ya un valor valido de su enum. Medido con el LLM real: rellena
    TODOS los campos, tambien los de enum de texto con `false`
    (`"sensitive_topic": false, ..., "weather_conditions": true`), asi que "vacio" es "sin
    valor valido del enum", no solo None. Con un valor de texto en la clave no se toca
    (seria otra cosa, no un flag aplanado), ni si el valor pertenece a varios enums, ni
    si el campo ya trae un valor valido.

    Claves repetidas (2026-09-16, medido al probar las notas en el tool del router): el
    LLM detectaba el pronostico pero escribia la clave dos veces en el mismo objeto
    (`"sensitive_topic": "weather_conditions", ..., "sensitive_topic": false`) y
    `json.loads` se queda con la ultima. Ya pasaba sin notas (la cadena real de la sonda
    del hallazgo D repite `sensitive_topic`). Mismo tipo de fallo de forma: una clave
    repetida nunca borra un valor real con el "nada" de ese campo (ver `_is_empty_for`).
    Entre dos valores reales gana el ultimo, como en JSON.

    Deja pasar `json.JSONDecodeError` como antes: cada llamador ya lo gestiona."""
    objects: list[tuple[dict, list]] = []

    def _record(pairs: list) -> dict:
        obj = dict(pairs)
        objects.append((obj, pairs))
        return obj

    args = json.loads(tool_call.function.arguments or "{}", object_pairs_hook=_record)
    if not isinstance(args, dict):
        return args
    properties = tool.get("function", {}).get("parameters", {}).get("properties", {})
    # El objeto de nivel superior es el ultimo que se cierra al parsear.
    top_pairs = objects[-1][1] if objects and objects[-1][0] is args else []
    repeated: dict[str, list] = {}
    for key, value in top_pairs:
        repeated.setdefault(key, []).append(value)
    for key, values in repeated.items():
        if len(values) < 2:
            continue
        spec = properties.get(key, {})
        real = [v for v in values if not _is_empty_for(spec, v)]
        if real and args[key] is not real[-1]:
            logger.info(f"[LLM_TOOL] clave repetida: {key}={values!r} -> {real[-1]!r}")
            args[key] = real[-1]
    owners: dict[str, list[str]] = {}
    for name, spec in properties.items():
        for value in spec.get("enum") or ():
            if isinstance(value, str):
                owners.setdefault(value, []).append(name)
    for key in [k for k in args if k not in properties]:
        fields = owners.get(key, [])
        if (
            args[key] is True and len(fields) == 1
            and args.get(fields[0]) not in properties[fields[0]]["enum"]
        ):
            args[fields[0]] = key
            del args[key]
            logger.info(f"[LLM_TOOL] clave aplanada reencajada: {key}=true -> {fields[0]}={key!r}")
    return args
