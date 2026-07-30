"""Fase 0 gap-filler LLM extractor (docs/robustness/plan.md).

Runs ALONGSIDE the regex-based IntentDetector (src/agents/intent_detector.py),
never replacing it. `fill_gaps()` only asks the LLM for fields the regex left
unresolved (None/empty) on a given DetectedIntent, and never overwrites a
field the regex already resolved. On any error, timeout, or malformed
response it returns an empty patch — the caller keeps whatever the regex
already found, so a failure here can never make the bot worse than today.

During Fase 0 this is wired in SHADOW mode only (see
`_maybe_log_llm_extraction_shadow` in supervisor.py, gated by
`settings.llm_extraction_shadow_mode`): the result is logged for comparison,
never applied to conversation state. See docs/robustness/plan.md §3-4.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI, OpenAIError

from src.agents.intent_detector import DetectedIntent
from src.config import settings
from src.prompts.booking import (
    EXTRACTION_TOOL,
    SIGNALS_TOOL,
    SLOT_RESOLVER_SPEC,
    acknowledgement_system_prompt,
    extraction_system_prompt,
    signals_system_prompt,
    slot_resolver_prompt,
    slot_resolver_tool,
)

logger = logging.getLogger("uvicorn.error")

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


async def fill_gaps(
    message: str,
    regex_intent: DetectedIntent,
    *,
    history: list[dict] | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
    only_fields: list[str] | None = None,
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

    messages: list[dict] = [{"role": "system", "content": extraction_system_prompt(lang, missing)}]
    for turn in (history or [])[-settings.history_retrieval_enrichment_window:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=messages,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "function", "function": {"name": "extract_fields"}},
            temperature=0.0,
            max_tokens=200,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            return {}
        args = json.loads(tool_calls[0].function.arguments or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR] malformed response: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR] error: {exc}")
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
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
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
        args = json.loads(tool_calls[0].function.arguments or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR] signals malformed response: {exc}")
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
        logger.error(f"[LLM_EXTRACTOR] signals API/network error (companion info may be lost silently this turn): {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR] signals error: {exc}")
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
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=[
                {"role": "system", "content": slot_resolver_prompt(slot, lang)},
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
        args = json.loads(tool_calls[0].function.arguments or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR] slot-resolver malformed response ({slot}): {exc}")
        return {}
    except OpenAIError as exc:
        logger.error(f"[LLM_EXTRACTOR] slot-resolver API/network error ({slot}, answer may loop): {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR] slot-resolver error ({slot}): {exc}")
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
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=[
                {"role": "system", "content": acknowledgement_system_prompt(lang, client_name)},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=60,
        )
        text = (response.choices[0].message.content or "").strip().strip('"')
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR] ack error: {exc}")
        return ""
    # Backstop determinista: si el modelo se saltó las reglas (precio/link/pregunta),
    # descartar el acuse — nunca dejar que invente datos duros.
    if not text or "http" in text.lower() or "$" in text or "€" in text or "?" in text or "¿" in text:
        return ""
    return text
