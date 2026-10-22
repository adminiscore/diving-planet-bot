"""Tracing del cliente OpenAI para Langfuse (Fase 5.3 — observabilidad).

`trace_openai(client)` devuelve un cliente OpenAI **trazado por Langfuse** cuando
el tracing está activo (hay claves), para que **cada llamada LLM** (chat +
embeddings) se registre con tokens/latencia/coste — el detalle por-llamada que el
grafo LangGraph no captura solo.

Langfuse no "envuelve" un cliente ya instanciado: su integración es un drop-in
(`langfuse.openai.AsyncOpenAI`). Como TODOS los llamadores instancian
`AsyncOpenAI(api_key=settings.openai_api_key)` (uniforme), `trace_openai` con el
tracing activo devuelve el cliente equivalente de `langfuse.openai` y descarta el
pelado; con el tracing off devuelve el que le pasan **sin tocar** (los tests
mockean `AsyncOpenAI` en su módulo y siguen funcionando). La lógica de Langfuse
(y su import perezoso, 3.14-safe) vive en `src/observability.py`.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from openai import AsyncOpenAI as _RealAsyncOpenAI

from src.config import settings
from src.observability import metered_http_client, traced_openai_client

logger = logging.getLogger("uvicorn.error")

_C = TypeVar("_C")


def _with_timeout(client: _C) -> _C:
    """Aplica el timeout de r6-1 **solo a clientes REALES** de OpenAI.

    Por qué el `isinstance`: los tests parchean `AsyncOpenAI` en su módulo y pasan
    mocks. `with_options()` sobre un mock devuelve OTRO objeto, así que las
    aserciones del test (`client.chat.completions.create...`) mirarían a un mock
    distinto y fallarían. Un mock no es instancia del cliente real, así que se le
    devuelve intacto; en producción sí se aplica.

    El camino trazado (Langfuse, que es el de PRE) ya sale con el timeout puesto
    desde `observability.traced_openai_client`, donde se construye.
    """
    if not isinstance(client, _RealAsyncOpenAI):
        return client
    try:
        # Medición propia (TURN_METRICS, 2026-09-24): el cliente HTTP cronometra cada
        # llamada al LLM del turno. Mismo criterio que el timeout: solo clientes reales.
        return client.with_options(timeout=settings.llm_timeout_seconds, http_client=metered_http_client())
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno por el timeout
        logger.warning("[LLM] no se pudo fijar el timeout en el cliente: %s", exc)
        return client


def trace_openai(client: _C) -> _C:
    """Cliente OpenAI trazado por Langfuse si el tracing está activo; si no, el
    `client` que se pasa. En ambos casos con el timeout de r6-1 aplicado y los
    parámetros adaptados al modelo de cada llamada (`adaptar_parametros`)."""
    traced = traced_openai_client(settings)
    return _con_parametros_adaptados(_with_timeout(traced if traced is not None else client))


# Modelos de la API nueva (8-oct, fase 0 del cambio de modelos): gpt-5/gpt-6 y la serie o RECHAZAN `max_tokens`
# ("Use 'max_completion_tokens' instead", 400) y gpt-6 RAZONA por defecto (esfuerzo "medium"), lo que se come la
# latencia. Todas las llamadas del bot usan `max_tokens`, así que el cambio de modelo se hace aquí, en un sitio, y no
# en cada llamada. Los modelos de antes (gpt-4o-mini, gpt-4.1…) rechazan `reasoning_effort`: a ellos no se les toca.
_API_NUEVA = ("gpt-5", "gpt-6", "o1", "o3", "o4")
# MOD (18-oct): los modelos nuevos que aceptan razonamiento "none" y razonan por defecto. gpt-5/gpt-5-mini (ago-2025) no
# aceptan "none" (solo "minimal"): a ellos no se les impone esfuerzo.
_SIN_RAZONAR = ("gpt-6", "gpt-5.4", "gpt-5.5", "gpt-5.6")


def adaptar_parametros(kwargs: dict) -> dict:
    """Los parámetros de una llamada a `chat.completions.create`, adaptados a su modelo."""
    model = str(kwargs.get("model") or "")
    if not model.startswith(_API_NUEVA):
        return kwargs
    kw = dict(kwargs)
    if "max_tokens" in kw:
        kw["max_completion_tokens"] = kw.pop("max_tokens")
    if model.startswith(_SIN_RAZONAR) and "reasoning_effort" not in kw:
        kw["reasoning_effort"] = settings.razonamiento_modelos_nuevos
    return kw


def es_de_openrouter(model: str) -> bool:
    """Modelos con prefijo de proveedor ("deepseek/deepseek-v4.1-flash"): no son de OpenAI y salen por OpenRouter."""
    return "/" in (model or "")


def parametros_openrouter(kwargs: dict) -> dict:
    """Los parámetros para OpenRouter (8-oct, prueba de DeepSeek): solo los proveedores de
    `settings.openrouter_proveedores` (por latencia, saltando al siguiente si uno falla), SIN retención de datos ni
    entrenamiento (`data_collection: deny`) y sin razonamiento. El modelo y los pesos son los mismos en cada proveedor;
    lo que cambia es DÓNDE se procesan los mensajes y su latencia."""
    kw = dict(kwargs)
    # MOD-7 (18-oct, decisión de Gadea: OpenRouter con datos reales, con condiciones): nada sale por OpenRouter sin
    # tapar antes los datos personales de los mensajes del cliente y del bot, para TODAS las piezas en un solo sitio
    # (el detector de idioma mandaba el mensaje tal cual). Por líneas, para no tapar precios del contexto (ver
    # `privacy.redact_pii_por_lineas`); el prompt de sistema es nuestro y no se toca.
    if isinstance(kw.get("messages"), list):
        from src.privacy import redact_pii_por_lineas

        kw["messages"] = [{**m, "content": redact_pii_por_lineas(m["content"])}
                          if m.get("role") != "system" and isinstance(m.get("content"), str) else m
                          for m in kw["messages"]]
    if settings.cache_anthropic and str(kw.get("model") or "").startswith("anthropic/") and isinstance(
            kw.get("messages"), list):
        # ARQ-2b (22-oct): OpenAI y DeepSeek cachean solos el principio repetido del prompt; Anthropic solo si se le pide
        # con `cache_control`. El extractor (Haiku, dos llamadas por turno, ~7.000-7.800 tokens de prompt de sistema casi
        # igual en cada turno) salía sin caché: 0 de 197 llamadas en la ronda core arq1d-B3, el 45-49 % del coste del
        # turno. Se marca el prompt de sistema; el mensaje del turno va detrás, sin marcar.
        kw["messages"] = [{**m, "content": [{"type": "text", "text": m["content"],
                                             "cache_control": {"type": "ephemeral"}}]}
                          if m.get("role") == "system" and isinstance(m.get("content"), str) else m
                          for m in kw["messages"]]
    proveedores = [p.strip() for p in settings.openrouter_proveedores.split(",") if p.strip()]
    extra = dict(kw.pop("extra_body", None) or {})
    datos = "allow" if settings.openrouter_permitir_entrenamiento else "deny"
    if settings.cache_anthropic and str(kw.get("model") or "").startswith("anthropic/") and proveedores:
        # ARQ-2b: cada proveedor tiene su caché; con «el más rápido en cada llamada» Haiku saltaba entre Vertex,
        # Anthropic y Bedrock y la caché acertaba 3 de 5 (sonda del 22-oct). Orden fijo, con los demás de respaldo.
        orden = sorted(proveedores, key=lambda p: p != "anthropic")
        extra.setdefault("provider", {"only": proveedores, "order": orden, "allow_fallbacks": True,
                                      "data_collection": datos})
    extra.setdefault("provider", {"only": proveedores, "sort": "latency", "allow_fallbacks": True, "data_collection": datos}
                     if proveedores else {"sort": "latency", "data_collection": datos})
    extra.setdefault("reasoning", {"enabled": False})
    kw["extra_body"] = extra
    return kw


_cliente_openrouter: _RealAsyncOpenAI | None = None


def _openrouter() -> _RealAsyncOpenAI:
    global _cliente_openrouter
    if _cliente_openrouter is None:
        _cliente_openrouter = _with_timeout(_RealAsyncOpenAI(api_key=settings.openrouter_api_key,
                                                             base_url=settings.openrouter_base_url))
    return _cliente_openrouter


def _con_parametros_adaptados(client: _C) -> _C:
    """Envuelve `chat.completions.create` del cliente REAL con `adaptar_parametros` (mismo criterio que el timeout:
    a un mock de los tests no se le toca). Un modelo con prefijo de proveedor sale por OpenRouter."""
    if not isinstance(client, _RealAsyncOpenAI):
        return client
    try:
        completions = client.chat.completions
        original = completions.create

        async def create(*args, **kwargs):
            return await _por_proveedor(original, *args, **kwargs)

        completions.create = create
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno por esto
        logger.warning("[LLM] no se pudieron adaptar los parámetros del cliente: %s", exc)
    return client


_TOPE_MINIMO_ESTRUCTURADO = 400


def _tope_minimo_estructurado(kwargs: dict) -> dict:
    """19-oct (ex-9b): una respuesta estructurada (herramienta o JSON) con un tope de salida corto se cortaba a mitad y no
    se podía leer. El router LLM de respaldo pedía 140 tokens, pensados para gpt-4o-mini; DeepSeek escribe TODOS los
    campos (también los `false`) y el JSON salía sin cerrar en ~1 de cada 9 llamadas de PRE: el turno se quedaba sin
    señales de IA y decidían las listas de palabras. El tope es un máximo, no un gasto: en un solo sitio, toda llamada
    con `tools` o `response_format` tiene al menos `_TOPE_MINIMO_ESTRUCTURADO` tokens de salida."""
    if not (kwargs.get("tools") or kwargs.get("response_format")):
        return kwargs
    for clave in ("max_tokens", "max_completion_tokens"):
        valor = kwargs.get(clave)
        if isinstance(valor, int) and valor < _TOPE_MINIMO_ESTRUCTURADO:
            kwargs = {**kwargs, clave: _TOPE_MINIMO_ESTRUCTURADO}
    return kwargs


async def _por_proveedor(original, *args, **kwargs):
    """Un modelo con prefijo de proveedor sale por OpenRouter; el resto, por OpenAI (`original`).

    18-oct (ronda mod-G): la clave de OpenRouter llegó a su límite (402) y fallaron a la vez Jev, todo lo de DeepSeek y
    Haiku; el revisor, al fallar, dejaba pasar las respuestas SIN revisar. Con `respaldo_si_openrouter_falla`, si la
    llamada a OpenRouter falla (crédito, caída, error del proveedor) se repite la MISMA petición con ese modelo de OpenAI,
    para todas las piezas en un solo sitio. Vacío = sube el error como antes."""
    kwargs = _tope_minimo_estructurado(kwargs)
    modelo = str(kwargs.get("model") or "")
    if not es_de_openrouter(modelo):
        return await original(*args, **adaptar_parametros(kwargs))
    respaldo = settings.respaldo_si_openrouter_falla
    if respaldo and not es_de_openrouter(respaldo) and settings.openrouter_respaldo_segundos > 0:
        return await _openrouter_o_respaldo_por_tiempo(original, respaldo, modelo, args, kwargs)
    try:
        return await _openrouter().chat.completions.create(*args, **parametros_openrouter(kwargs))
    except Exception as exc:  # noqa: BLE001 — el respaldo decide; sin respaldo sube el error
        if not respaldo or es_de_openrouter(respaldo):
            raise
        logger.warning(f"[LLM][OPENROUTER] {modelo} falló ({str(exc)[:160]}): contesta {respaldo} por OpenAI")
        return await original(*args, **adaptar_parametros({**kwargs, "model": respaldo}))


async def _openrouter_o_respaldo_por_tiempo(original, respaldo: str, modelo: str, args, kwargs):
    """ex-9b (flag `openrouter_respaldo_segundos`): la llamada a OpenRouter con respaldo POR TIEMPO, como
    `crear_con_respaldo`. Si en esos segundos no ha terminado, sale la misma petición por OpenAI y gana la primera que
    termine bien (la otra se cancela); si OpenRouter falla antes, contesta el respaldo, como siempre. La del respaldo
    sale en [TURN_METRICS] como `<pieza>_respaldo`."""
    import asyncio

    from src.observability import _LLM_PIEZA, pieza_llm

    segundos = settings.openrouter_respaldo_segundos
    pieza = _LLM_PIEZA.get() or "llm"

    async def por_openai():
        with pieza_llm(f"{pieza}_respaldo"):
            return await original(*args, **adaptar_parametros({**kwargs, "model": respaldo}))

    t_openrouter = asyncio.ensure_future(_openrouter().chat.completions.create(*args, **parametros_openrouter(kwargs)))
    await asyncio.wait({t_openrouter}, timeout=segundos)
    if t_openrouter.done():
        if t_openrouter.exception() is None:
            return t_openrouter.result()
        logger.warning(f"[LLM][OPENROUTER] {modelo} falló ({str(t_openrouter.exception())[:160]}): contesta {respaldo}")
        return await por_openai()
    t_openai = asyncio.ensure_future(por_openai())
    pendientes = {t_openrouter, t_openai}
    while pendientes:
        hechas, pendientes = await asyncio.wait(pendientes, return_when=asyncio.FIRST_COMPLETED)
        buena = next((t for t in hechas if t.exception() is None), None)
        if buena is not None:
            for t in pendientes:
                t.cancel()
            gana = "OpenRouter" if buena is t_openrouter else respaldo
            logger.info(f"[LLM][OPENROUTER] {pieza}: {modelo} tardaba más de {segundos:g} s: gana {gana}")
            return buena.result()
    return t_openai.result()  # fallaron los dos: sube la excepción del respaldo


def _is_empty_for(spec: dict, value) -> bool:
    """¿Es `value` la forma del LLM de decir "nada" en un campo con este esquema? En un
    booleano `false` es un dato; en el resto (enum de texto, objeto, lista, numero) el LLM
    rellena con `false` o null lo que no tiene (medido en el hallazgo D)."""
    if value is None:
        return True
    if spec.get("type") == "boolean":
        return False
    if value == "none" and "none" in (spec.get("enum") or []):
        return True  # ex-9b (19-oct): la opcion "nada" de un enum (sensitive_topic, booking_change_topic)
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
    # Enum anidado (12-oct, ronda ex8-B: "hay algun problema de tiempo entre bucear y volar" -> `"sensitive_topic":
    # {"weather_conditions": true}`, y `sensitive_response_for` reventaba con un dict: turno sin respuesta). Mismo fallo
    # de forma: un campo de enum que trae un objeto con UN solo valor de su enum a true vuelve a ese valor; cualquier
    # otro valor que no sea del enum se descarta (nunca llega un tipo que el llamador no espera).
    for name, spec in properties.items():
        enum = spec.get("enum")
        value = args.get(name)
        if not enum or not isinstance(value, (dict, list)):
            continue
        marcados = [k for k, v in value.items() if v is True and k in enum] if isinstance(value, dict) else []
        args[name] = marcados[0] if len(marcados) == 1 else None
        logger.info(f"[LLM_TOOL] enum anidado: {name}={value!r} -> {args[name]!r}")
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


async def crear_con_respaldo(client, *, respaldo: str, segundos: float, pieza: str, **kwargs):
    """Una llamada con RESPALDO por si el modelo principal se queda en la cola (18-oct, mod-2). Lanza la petición a
    `kwargs["model"]`; si no ha terminado en `segundos`, lanza la MISMA petición a `respaldo` y usa la primera que
    termine bien (la otra se cancela). Si el principal falla antes, contesta el respaldo. Sin respaldo, o con el mismo
    modelo, la llamada de siempre. Es el mecanismo del RAG (`rag_agent.generar_con_respaldo`, 8-oct) hecho común: con
    un modelo de OpenRouter (Haiku en el extractor) y el respaldo en OpenAI, una caída o una cola de un proveedor no
    para el turno. Las llamadas salen en [TURN_METRICS] como `pieza` y `<pieza>_respaldo`."""
    import asyncio

    from src.observability import pieza_llm

    principal = kwargs.get("model")

    async def llamar(modelo: str, etiqueta: str):
        with pieza_llm(etiqueta):
            return await client.chat.completions.create(**{**kwargs, "model": modelo})

    if not respaldo or respaldo == principal or segundos <= 0:
        return await llamar(principal, pieza)
    t_principal = asyncio.ensure_future(llamar(principal, pieza))
    await asyncio.wait({t_principal}, timeout=segundos)
    if t_principal.done() and t_principal.exception() is None:
        return t_principal.result()
    if t_principal.done():
        logger.warning(f"[LLM][RESPALDO] {pieza}: {principal} falló ({t_principal.exception()}): contesta {respaldo}")
        return await llamar(respaldo, f"{pieza}_respaldo")
    t_respaldo = asyncio.ensure_future(llamar(respaldo, f"{pieza}_respaldo"))
    pendientes = {t_principal, t_respaldo}
    while pendientes:
        hechas, pendientes = await asyncio.wait(pendientes, return_when=asyncio.FIRST_COMPLETED)
        buena = next((t for t in hechas if t.exception() is None), None)
        if buena is not None:
            for t in pendientes:
                t.cancel()
            gana = "principal" if buena is t_principal else "respaldo"
            logger.info(f"[LLM][RESPALDO] {pieza}: {principal} tardaba más de {segundos:g} s: gana el {gana}")
            return buena.result()
    return t_respaldo.result()  # fallaron los dos: sube la excepción del respaldo
