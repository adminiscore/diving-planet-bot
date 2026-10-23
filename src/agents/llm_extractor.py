"""Fase 0 gap-filler LLM extractor (docs/robustness/plan.md).

Runs ALONGSIDE the regex-based IntentDetector (src/agents/intent_detector.py),
never replacing it. `fill_gaps()` only asks the LLM for fields the regex left
unresolved (None/empty) on a given DetectedIntent, and never overwrites a
field the regex already resolved. On any error, timeout, or malformed
response it returns an empty patch — the caller keeps whatever the regex
already found, so a failure here can never make the bot worse than today.

During Fase 0 this was wired in SHADOW mode only (logged for comparison, never
applied); that probe (`supervisor._maybe_log_llm_extraction_shadow` and its
flag `llm_extraction_shadow_mode`) was removed in s4-1: nothing called it since
28-jul. Today `fill_gaps()` is called by the conversational core
(`conversational_core._understand`). See docs/robustness/plan.md §3-4.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI, OpenAIError

from src.agents.intent_detector import DetectedIntent
from src.config import settings
from src.llm_client import tool_arguments, trace_openai
from src.observability import con_pieza_llm
from src.prompts.booking import (
    EXTRACTION_TOOL,  # noqa: F401 — se reexporta (tests/test_prompts_surface.py)
    SIGNALS_TOOL,
    SLOT_RESOLVER_CONTRADICCION,
    SLOT_RESOLVER_SPEC,
    acknowledgement_system_prompt,
    extraction_system_prompt,
    extraction_tool,
    signals_system_prompt,
    slot_resolver_prompt,
    slot_resolver_tool,
)
from src.prompts.booking import lugar_sin_baru as _lugar_sin_baru
from src.prompts.booking import tool_sin_baru as _tool_sin_baru


def _sin_baru(texto: str) -> str:
    """G3-06: los textos de lugar de estos prompts, sin Barú entre "las islas"."""
    return _lugar_sin_baru(texto, settings.baru_sale_de_cartagena)


def _acuse_en_su_numero(texto: str) -> str:
    """gen-8 (flag `acuse_en_su_numero`): el ejemplo del acuse, sin una frase en plural para copiar (ver booking)."""
    if not settings.acuse_en_su_numero:
        return texto
    from src.prompts.booking import (  # lazy
        ACUSE_EJEMPLO_EN,
        ACUSE_EJEMPLO_ES,
        ACUSE_EN_SU_NUMERO_EN,
        ACUSE_EN_SU_NUMERO_ES,
    )

    return texto.replace(ACUSE_EJEMPLO_ES, ACUSE_EN_SU_NUMERO_ES).replace(ACUSE_EJEMPLO_EN, ACUSE_EN_SU_NUMERO_EN)


def _tool(tool: dict) -> dict:
    return _tool_sin_baru(tool, settings.baru_sale_de_cartagena)

logger = logging.getLogger("uvicorn.error")

# Taxonomia de fallos en los logs (2026-09-12). Dos cosas muy distintas se
# veian igual desde fuera y eso invalidaba mediciones:
#
#   [LLM_EXTRACTOR][DEGRADED] ...  -> la LLAMADA fallo (red, 429, timeout,
#       respuesta malformada). No hubo opinion del modelo. En una medicion
#       el caso NO es evaluable: hay que excluirlo o abortar la tanda.
#
#   [LLM_EXTRACTOR][<CAMPO>_VETO] valor fuera de enum descartado: ...
#       -> la llamada FUNCIONO y el modelo respondio, pero con un valor que
#       no existe en el enum. Es conducta real y reproducible del modelo, y
#       cuenta como fallo suyo: debe puntuar en la medicion, no excluirse.
#
# El marcador es explicito a proposito: inferir la categoria por palabras
# ("error", "malformed"...) se queda corto en cuanto se añade un mensaje
# nuevo, y el fallo seria silencioso. Ver scripts/run_extraction_eval.py.

# Fields DetectedIntent exposes that are worth LLM gap-filling. Deliberately
# excludes `language` (already has a robust dedicated detector),
# `service_id`/`confidence`/`detected_fields` (derived/meta, not extracted
# from the message directly).
EXTRACTABLE_FIELDS = (
    "activity",
    "is_certified",
    "group_size",
    "group_allocation",
    "last_dive_over_2_years",
    "duration",
    "location",
    "island",
    "hotel",
    "ages",
    "cert_dives",
    "cert_days",
    "is_colombian",
)


def missing_fields(regex_intent: DetectedIntent) -> list[str]:
    """Fields EXTRACTABLE_FIELDS the regex-based detector left unresolved.

    Uses `in (None, [])` rather than plain truthiness: `is_certified=False` /
    `last_dive_over_2_years=False` / `is_colombian=False` are real, resolved
    answers, not "missing" — a bare `not value` check would wrongly treat
    them as gaps to fill.
    """
    return [f for f in EXTRACTABLE_FIELDS if getattr(regex_intent, f, None) in (None, [])]


def _build_messages(system: str, message: str, history: list[dict] | None) -> list[dict]:
    """system + ventana de historial + el mensaje del turno (fill_gaps; antes tambien el veto, que quito
    mej-1d)."""
    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in (history or [])[-settings.history_retrieval_enrichment_window:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


def _strip_schema_nulls(args: dict) -> dict:
    """`group_allocation` vuelve con las claves fijas del schema estricto y las
    actividades no usadas a null."""
    ga = (args or {}).get("group_allocation")
    if isinstance(ga, dict):
        args["group_allocation"] = {k: v for k, v in ga.items() if v}
    return args


@con_pieza_llm("red_fill_gaps")
async def fill_gaps(
    message: str,
    regex_intent: DetectedIntent,
    *,
    history: list[dict] | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
    only_fields: list[str] | None = None,
    extra_fields=(),
) -> dict:
    """Ask the LLM to fill ONLY the fields `regex_intent` left unresolved.

    Returns a dict patch (field -> value) with just the fields the LLM found
    real signal for. Never includes a field regex_intent already resolved,
    and never mutates regex_intent. On any error/timeout/malformed response,
    returns {} so the caller keeps the regex result untouched.

    `only_fields` (optional) further restricts the request to that subset —
    used by the conversational core (Fix B, conversational-refactor-handoff)
    to avoid asking the LLM for fields the conversation STATE already knows
    even though this turn's regex intent left them None. Fewer requested
    fields = fewer tokens and less misfill surface.
    """
    missing = missing_fields(regex_intent)
    if only_fields is not None:
        missing = [f for f in missing if f in only_fields]
    if not missing or not message or not message.strip():
        return {}
    # Campos que no salen del detector y solo viajan cuando se piden, con su propia
    # variante del tool (`extraction_tool`, hallazgo A): nunca abren una peticion solos.
    missing = missing + [f for f in extra_fields if f not in missing]
    tool = _tool(extraction_tool(extra_fields))

    messages: list[dict] = [{"role": "system", "content": _sin_baru(extraction_system_prompt(lang, missing))}]
    for turn in (history or [])[-settings.history_retrieval_enrichment_window:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.red_extractor_model,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "extract_fields"}},
            temperature=0.0,
            max_tokens=200,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            return {}
        args = tool_arguments(tool_calls[0], tool)
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] malformed response: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] error: {exc}")
        return {}

    # Strict schema: group_allocation comes back with fixed keys where the
    # unused activities are null — strip those so downstream sees only the
    # real split (and an all-null object counts as "no signal").
    ga = (args or {}).get("group_allocation")
    if isinstance(ga, dict):
        args["group_allocation"] = {k: v for k, v in ga.items() if v}

    # Belt and suspenders: only keep fields that were actually missing (never
    # let the LLM overwrite something regex already resolved) and that have a
    # real, non-empty value.
    patch = {
        k: v for k, v in (args or {}).items()
        if k in missing and v not in (None, "", [], {})
    }
    if patch:
        logger.info(f"[LLM_EXTRACTOR] filled gaps={list(patch.keys())} msg={message[:60]!r}")
    return patch


def compare_with_ground_truth(patch: dict, expected: dict) -> dict:
    """Shadow-mode / eval-set helper: compare an LLM patch against an expected
    dict (either hand-labeled eval-set data, or the regex result treated as
    ground truth). Returns {"agree": [...], "disagree": {field: (got, want)},
    "missed": [...]} — fields expected had that the patch didn't produce.

    An expected value of None means "the extractor MUST abstain on this field"
    (the message gives no real signal): absence counts as agreement, and a
    filled value counts as a disagreement — this is how the eval-set catches
    MISFILLS, the dangerous failure mode (found live 2026-07-22: 'quiero hacer
    buceo' with no place got location='cartagena' invented from the business's
    own base city)."""
    agree, disagree, missed = [], {}, []
    for field, want in expected.items():
        if want is None:
            if field in patch:
                disagree[field] = (patch[field], None)
            else:
                agree.append(field)
            continue
        if field not in patch:
            missed.append(field)
            continue
        got = patch[field]
        if got == want:
            agree.append(field)
        else:
            disagree[field] = (got, want)
    return {"agree": agree, "disagree": disagree, "missed": missed}


@con_pieza_llm("red_detect_special_signals")
async def detect_special_signals(
    message: str,
    *,
    history: list[dict] | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
) -> dict:
    """Fallback signal detector — only called by the conversational core when
    the normal regex+gap-fill path did NOT advance the booking. Same safety
    net as fill_gaps: never raises, returns {} on any error, malformed
    response, or empty message."""
    if not message or not message.strip():
        return {}
    messages: list[dict] = [{"role": "system", "content": signals_system_prompt(lang)}]
    for turn in (history or [])[-settings.history_retrieval_enrichment_window:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.red_extractor_model,
            messages=messages,
            tools=[SIGNALS_TOOL],
            tool_choice={"type": "function", "function": {"name": "detect_signals"}},
            temperature=0.0,
            max_tokens=100,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            return {}
        args = tool_arguments(tool_calls[0], SIGNALS_TOOL)
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] signals malformed response: {exc}")
        return {}
    except OpenAIError as exc:
        # Auditoría Fase B (2026-07-23): un timeout/error de red aquí degrada
        # a {} igual que una respuesta malformada, pero el efecto es distinto
        # — un acompañante mencionado por el cliente se pierde sin que nadie
        # se entere. Separado del warning genérico de abajo y a nivel ERROR
        # para que sea monitoreable/alertable (un pico de esto es una señal
        # real de degradación, no ruido de parseo). No se reintenta ni se
        # cambia el contrato ({} en cualquier fallo) — mismo patrón que
        # `fill_gaps`/`compose_acknowledgement`; cambiarlo es un rediseño de
        # resiliencia más amplio, no específico de acompañantes.
        logger.error(f"[LLM_EXTRACTOR][DEGRADED] signals API/network error (companion info may be lost silently this turn): {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] signals error: {exc}")
        return {}

    result = {k: v for k, v in (args or {}).items() if v not in (None, "", [], {})}
    if result:
        logger.info(f"[CORE][SIGNALS] detected={result} msg={message[:80]!r}")
    return result


# ──────────────── Resolutor genérico de respuesta de slot (Fase C) ────────────
# Red anti-bucle: cuando el parser canónico de un slot booleano/escalar
# (is_affirmative/is_negative/número) NO reconoce una respuesta válida pero
# no-canónica, el núcleo re-pregunta el MISMO slot para siempre (hallazgo Fase
# C 2026-07-23, en vivo: SLOT_SAFETY "uf, hace muchísimo" / SLOT_NATIONALITY
# "vivo en bogotá" / SLOT_QTY "un par" se quedaban en bucle). Gadea ya había
# cerrado este patrón SOLO para refresher_interested; esto lo generaliza a
# todos los slots de la misma forma. El LLM interpreta la respuesta EN EL
# CONTEXTO de la pregunta concreta que se hizo; devuelve un valor tipado o se
# abstiene. Misma red de seguridad que el resto: nunca lanza, {} ante cualquier
# fallo (el bot cae al re-preguntar de siempre, nunca peor que hoy).


@con_pieza_llm("red_resolve_slot_answer")
async def resolve_slot_answer(
    slot: str,
    message: str,
    *,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
) -> dict:
    """Interpreta `message` como respuesta al slot booleano/escalar `slot`
    cuando el parser canónico ya falló. Devuelve {"value": <bool|int>} o {} si
    no aplica / cualquier fallo. Nunca lanza. Ver `SLOT_RESOLVER_SPEC` en
    `src/prompts/booking.py`."""
    if slot not in SLOT_RESOLVER_SPEC or not message or not message.strip():
        return {}
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.resolutor_model,
            messages=[
                {"role": "system", "content": _sin_baru(slot_resolver_prompt(slot, lang)) + SLOT_RESOLVER_CONTRADICCION},
                {"role": "user", "content": message},
            ],
            tools=[slot_resolver_tool(slot)],
            tool_choice={"type": "function", "function": {"name": "resolve_slot"}},
            temperature=0.0,
            max_tokens=40,
        )
        tool_calls = getattr(response.choices[0].message, "tool_calls", None)
        if not tool_calls:
            return {}
        args = tool_arguments(tool_calls[0], slot_resolver_tool(slot))
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] slot-resolver malformed response ({slot}): {exc}")
        return {}
    except OpenAIError as exc:
        logger.error(f"[LLM_EXTRACTOR][DEGRADED] slot-resolver API/network error ({slot}, answer may loop): {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] slot-resolver error ({slot}): {exc}")
        return {}
    if "value" not in args or args["value"] in (None, ""):
        return {}
    logger.info(f"[CORE][SLOT-RESOLVER] slot={slot} value={args['value']!r} msg={message[:60]!r}")
    return {"value": args["value"]}


# ─────────────────────── Redactor cálido "acuse" (Parte 2 del plan) ──────────
# Genera UNA frase que reconoce lo que el cliente acaba de decir, con la persona
# Coral y su nombre si lo hay. NO menciona precios/links/cifras ni hace la
# pregunta: los datos DUROS y la pregunta van en la parte determinista que el
# núcleo concatena después. Red de seguridad idéntica al resto: nunca lanza,
# devuelve "" ante cualquier fallo (el bot sigue respondiendo con lo determinista).


def _regla_solo_mensaje(lang: str) -> str:
    """EX-EST-2 (14-oct): el acuse reconoce solo lo que dice el mensaje (ver ACUSE_SOLO_MENSAJE_*)."""
    from src.prompts.booking import ACUSE_SOLO_MENSAJE_EN, ACUSE_SOLO_MENSAJE_ES  # lazy

    return ACUSE_SOLO_MENSAJE_ES if lang == "es" else ACUSE_SOLO_MENSAJE_EN


@con_pieza_llm("acuse")
async def compose_acknowledgement(
    message: str,
    *,
    state_summary: str = "",
    client_name: str | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
) -> str:
    """Devuelve una frase de acuse cálida (o "" si no procede/falla)."""
    if not message or not message.strip():
        return ""
    user_content = message if not state_summary else f"{message}\n\n[contexto de la reserva: {state_summary}]"
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.acuse_model,
            messages=[
                {"role": "system", "content": _acuse_en_su_numero(acknowledgement_system_prompt(lang, client_name))
                 + _regla_solo_mensaje(lang)},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=60,
        )
        text = (response.choices[0].message.content or "").strip().strip('"')
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] ack error: {exc}")
        return ""
    # Backstop determinista: si el modelo se saltó las reglas (precio/link/pregunta),
    # descartar el acuse — nunca dejar que invente datos duros.
    if not text or "http" in text.lower() or "$" in text or "€" in text or "?" in text or "¿" in text:
        return ""
    # s4-21 (1): un acuse sin prosa ('{" "}', golden v7 del 22-sep) salia tal cual delante de la
    # respuesta. Mismo guard que el RAG (`is_coherent_text`).
    from src.agents.grounding_check import is_coherent_text  # lazy

    if not is_coherent_text(text):
        return ""
    return text
