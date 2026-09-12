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
from src.llm_client import trace_openai
from src.prompts.booking import (
    EXTRACTION_TOOL,
    SIGNALS_TOOL,
    SLOT_RESOLVER_SPEC,
    acknowledgement_system_prompt,
    extraction_system_prompt,
    fields_verification_system_prompt,
    signals_system_prompt,
    slot_resolver_prompt,
    slot_resolver_tool,
)

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
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
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


def _clean_verified_value(field: str, llm_value):
    """Normaliza y valida el valor que devolvio el LLM para `field`.
    Devuelve None si no hay valor utilizable."""
    # `group_allocation` vuelve con las claves fijas del schema estricto y las
    # actividades no usadas a null -- mismo tratamiento que en `fill_gaps`.
    if isinstance(llm_value, dict):
        llm_value = {k: v for k, v in llm_value.items() if v}
    if llm_value in (None, "", [], {}):
        return None
    # Robustez (hallazgo en vivo, eval-set 2026-09-10): un tool_choice forzado
    # no obliga al modelo a respetar el `enum` declarado en EXTRACTION_TOOL --
    # se observo un caso real donde `activity` volvio 'certificarse' (ni
    # siquiera un valor del enum) en vez de un valor real como
    # 'padi_open_water'. Si el campo declara enum, se descarta cualquier
    # valor fuera de el (degrada a "nada que vetar", nunca a un valor
    # inventado) en vez de dejarlo pasar sin validar.
    field_schema = EXTRACTION_TOOL["function"]["parameters"]["properties"].get(field, {})
    enum = field_schema.get("enum")
    if enum is not None and llm_value not in enum:
        logger.warning(
            f"[LLM_EXTRACTOR][{field.upper()}_VETO] valor fuera de enum descartado: {llm_value!r}"
        )
        return None
    return llm_value


async def verify_fields(
    fields: list[str],
    message: str,
    regex_values: dict,
    *,
    history: list[dict] | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
) -> dict:
    """Verifica en UNA SOLA peticion varios campos que el regex ya resolvio
    (ver `supervisor._maybe_veto_resolved_fields_via_llm`). Devuelve un dict
    {campo: valor_del_llm} SOLO con los campos en los que el LLM DISCREPA del
    regex; {} si coincide en todos o si la llamada falla.

    Nacio como `verify_activity` (especifica de `activity`, hallazgo en vivo
    "purple-sun-590" 2026-09-03), se generalizo a `verify_field` por-campo
    (conversacion real 913, 2026-09-10) y finalmente se agrupo en una sola
    peticion el mismo dia, al medir que el recurso escaso de la cuenta son
    las PETICIONES/dia (limite RPD agotado con los tokens intactos), no los
    tokens: N campos en N peticiones gastaba justo el recurso limitado.

    A diferencia de `fill_gaps` (que solo rellena huecos y nunca toca un
    campo ya resuelto), esta funcion pregunta al LLM de forma independiente
    y solo reporta lo que discrepa. Cualquier fallo degrada a {} (el llamador
    se queda con el regex, mismo patron defensivo que `fill_gaps`: esto nunca
    puede dejar la respuesta peor que antes de que el veto existiera).
    """
    if not fields or not message or not message.strip():
        return {}
    log_tag = "_".join(f.upper() for f in fields) if len(fields) == 1 else "FIELDS"
    messages: list[dict] = [
        {"role": "system", "content": fields_verification_system_prompt(fields, lang)}
    ]
    for turn in (history or [])[-settings.history_retrieval_enrichment_window:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=messages,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "function", "function": {"name": "extract_fields"}},
            temperature=0.0,
            # Escala con el numero de campos pedidos (antes 100 fijo para 1).
            max_tokens=60 + 60 * len(fields),
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            return {}
        args = json.loads(tool_calls[0].function.arguments or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED][{log_tag}_VETO] malformed response: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED][{log_tag}_VETO] error: {exc}")
        return {}

    disagreements = {}
    for field in fields:
        value = _clean_verified_value(field, (args or {}).get(field))
        # `is_certified=False` / `is_colombian=False` son respuestas reales:
        # se comparan con `!=`, nunca por truthiness.
        if value is not None and value != regex_values.get(field):
            disagreements[field] = value
    return disagreements


async def verify_field(
    field: str,
    message: str,
    regex_value,
    *,
    history: list[dict] | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
):
    """Atajo de un solo campo sobre `verify_fields`. Devuelve el valor del
    LLM si discrepa, o None."""
    result = await verify_fields(
        [field], message, {field: regex_value},
        history=history, lang=lang, client=client,
    )
    return result.get(field)


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
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
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
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] ack error: {exc}")
        return ""
    # Backstop determinista: si el modelo se saltó las reglas (precio/link/pregunta),
    # descartar el acuse — nunca dejar que invente datos duros.
    if not text or "http" in text.lower() or "$" in text or "€" in text or "?" in text or "¿" in text:
        return ""
    return text
