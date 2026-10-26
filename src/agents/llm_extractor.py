"""Fase 0 gap-filler LLM extractor (docs/robustness/plan.md).

Runs ALONGSIDE the regex-based IntentDetector (src/agents/intent_detector.py),
never replacing it. Its gap-filler `fill_gaps()` was removed in lat-11 (26-oct): it only
filled the children's ages when the turn extractor failed (0 calls in
465 turns of the 26-oct round). What is left here: the special-signals net,
the slot resolver and the eval helpers.

During Fase 0 this was wired in SHADOW mode only (logged for comparison, never
applied); that probe (`supervisor._maybe_log_llm_extraction_shadow` and its
flag `llm_extraction_shadow_mode`) was removed in s4-1: nothing called it since
28-jul. See docs/robustness/plan.md §3-4.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI, OpenAIError

from src.config import settings
from src.llm_client import tool_arguments, trace_openai
from src.observability import con_pieza_llm
from src.prompts.booking import (
    SIGNALS_TOOL,
    SLOT_RESOLVER_CONTRADICCION,
    SLOT_RESOLVER_SPEC,
    signals_system_prompt,
    slot_resolver_prompt,
    slot_resolver_tool,
)
from src.prompts.booking import lugar_sin_baru as _lugar_sin_baru


def _sin_baru(texto: str) -> str:
    """G3-06: los textos de lugar de estos prompts, sin Barú entre "las islas"."""
    return _lugar_sin_baru(texto, True)


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
