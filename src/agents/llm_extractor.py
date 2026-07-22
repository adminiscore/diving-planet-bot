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

from openai import AsyncOpenAI

from src.agents.intent_detector import DetectedIntent
from src.config import settings

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

# NOTA (decisión con datos, 2026-07-22): se evaluó migrar este schema a
# strict function-calling (structured outputs: todas las claves required +
# nullable + additionalProperties:false) como pedía el plan conversacional, y
# se DESCARTÓ midiendo contra el eval-set con casos negativos: obligar al
# modelo a emitir cada clave y decidir valor-vs-null INDUCE misfills en los
# campos sin señal ("quiero hacer buceo" sin lugar → location='cartagena'
# inventada desde la sede del negocio; pasó con gpt-4o-mini Y gpt-4o). Con el
# schema libre (omitir clave = abstenerse), ambos casos negativos se abstienen
# limpio. El JSON malformado ocasional del modo no-strict ya degrada seguro a
# {} (regex-only) vía el try/except de fill_gaps. Ver
# docs/robustness/eval-set.json casos neg-* y docs/robustness/progress-log.md.
_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_fields",
        "description": (
            "Extract ONLY the requested fields from the customer's message for "
            "a scuba diving booking bot. Omit a field entirely (do not include "
            "the key) if the message doesn't give real, explicit signal for "
            "it — never guess speculatively or infer from general world "
            "knowledge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "activity": {
                    "type": "string",
                    "enum": [
                        "certified_diving", "minicourse", "snorkel",
                        "padi_open_water", "padi_advanced", "padi_rescue",
                        "padi_divemaster", "padi_specialty",
                    ],
                    "description": "The diving-related activity the customer wants.",
                },
                "is_certified": {
                    "type": "boolean",
                    "description": (
                        "True if the customer states they ALREADY hold a scuba "
                        "certification (any level/agency, e.g. having Open Water/"
                        "Rescue/Divemaster). False if they explicitly say they "
                        "are NOT certified / it's their first time diving."
                    ),
                },
                "group_size": {
                    "type": "integer",
                    "description": (
                        "Total number of people in the customer's party — count "
                        "EVERYONE mentioned, including children, non-divers, and "
                        "people referred to by relationship. Infer the count when "
                        "the message enumerates individuals instead of giving a "
                        "number: 'my wife and I' = 2, 'me plus 3 friends' = 4, "
                        "'my daughter, my son and us two' = 4, 'four adults and a "
                        "kid' = 5."
                    ),
                },
                "group_allocation": {
                    "type": "object",
                    "description": (
                        "Split of the group by activity when the message "
                        "explicitly describes a mixed group, e.g. "
                        '{"certified_diving": 2, "snorkel": 1}.'
                    ),
                    "additionalProperties": {"type": "integer"},
                },
                "last_dive_over_2_years": {
                    "type": "boolean",
                    "description": "True if the customer's last dive was more than 2 years ago.",
                },
                "duration": {
                    "type": "string",
                    "enum": ["single_day", "multi_day"],
                    "description": "Whether the customer is staying a single day or multiple days near the dive sites.",
                },
                "location": {
                    "type": "string",
                    "enum": ["cartagena", "island"],
                    "description": (
                        "Where the customer is based / departs from. 'cartagena' "
                        "if they're staying in Cartagena city or any of its "
                        "neighborhoods (Bocagrande, Getsemaní, Centro/Old City, "
                        "Manga, Castillogrande…). 'island' if they're staying on "
                        "or coming from the Rosario Islands, Barú, or a specific "
                        "island/island-hotel. Only set it when the message gives "
                        "a real place signal."
                    ),
                },
                "island": {"type": "string", "description": "Specific island name, if mentioned (e.g. Isla Grande, Barú, Isla del Sol)."},
                "hotel": {"type": "string", "description": "Specific hotel/lodging name on the islands, if mentioned."},
                "ages": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Ages of people in the group mentioned explicitly in the message.",
                },
                "cert_dives": {
                    "type": "integer",
                    "description": "Explicit number of dives requested for a certified-diving package.",
                },
                "cert_days": {
                    "type": "integer",
                    "description": "Explicit number of days requested for a multi-day certified-diving package.",
                },
                "is_colombian": {
                    "type": "boolean",
                    "description": "True if the customer states they are Colombian; false if they state they are a foreigner.",
                },
            },
        },
    },
}


def _system_prompt(lang: str, missing_fields: list[str]) -> str:
    fields_list = ", ".join(missing_fields)
    if lang == "es":
        return (
            "Eres una capa de extracción de datos para un bot de buceo (Diving "
            "Planet, Cartagena/Islas del Rosario). Un detector determinista ya "
            "extrajo lo que pudo del mensaje; tu única tarea es intentar rellenar "
            f"ESTOS campos que quedaron sin resolver: {fields_list}. Llama a "
            "`extract_fields` incluyendo SOLO los campos para los que el mensaje "
            "da señal real y explícita. Omite cualquier campo ambiguo o no "
            "mencionado — nunca lo adivines ni lo infieras de conocimiento "
            "general, solo de lo que el mensaje dice. OJO: que el negocio opere "
            "en Cartagena NO es señal de la ubicación del cliente — 'quiero "
            "bucear' sin lugar deja location fuera; sin mención de días/estancia, "
            "duration queda fuera. Abstenerse siempre es mejor que rellenar mal."
        )
    return (
        "You are a data-extraction layer for a scuba diving bot (Diving Planet, "
        "Cartagena/Rosario Islands). A deterministic detector already extracted "
        "what it could from the message; your only job is to try to fill these "
        f"fields that were left unresolved: {fields_list}. Call `extract_fields` "
        "including ONLY the fields the message gives real, explicit signal for. "
        "Omit any field that's ambiguous or not mentioned — never guess or infer "
        "from general knowledge, only from what the message says. NOTE: the "
        "business operating in Cartagena is NOT a signal of the customer's "
        "location — 'I want to dive' with no place leaves location out; no "
        "mention of days/stay leaves duration out. Abstaining is always better "
        "than a wrong fill."
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

    messages: list[dict] = [{"role": "system", "content": _system_prompt(lang, missing)}]
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
            tools=[_TOOL],
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


# ---------------------------------------------------------------------------
# Detección de señales de fallback (núcleo conversacional): "recordar un dato
# ya dado" y "se añade un acompañante". Herramienta SEPARADA de fill_gaps a
# propósito: estas no son campos persistentes de DetectedIntent (slots de la
# reserva), son EVENTOS de un turno concreto — solo se invoca cuando el turno
# no avanzó la reserva por los caminos normales (ver conversational_core.py,
# hallazgo en vivo 2026-07-22: "hay un amigo que quiere hacer snorkel" y "mi
# acompañante quiere hacer buceo pero no es certificado" no los reconocía
# ningún regex, y quedaban cayendo al escalado genérico de asesor). Decisión
# del owner: nada de listar más frases en regex — el LLM decide QUÉ pasó, el
# CÓDIGO decide la respuesta con el valor real del estado (nunca un valor
# inventado por el LLM), mismo reparto de responsabilidades que fill_gaps.
_SIGNALS_TOOL = {
    "type": "function",
    "function": {
        "name": "detect_signals",
        "description": (
            "The customer's message did NOT advance a scuba booking through "
            "the normal deterministic slot-filling. Check ONLY whether it (1) "
            "asks the bot to recall/remind something the customer ALREADY "
            "said earlier in this conversation, (2) introduces an "
            "ADDITIONAL person joining the booking, or (3) answers the "
            "refresher yes/no question with phrasing a simple parser "
            "wouldn't catch. Omit a field entirely if it doesn't apply — "
            "never guess."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recall_field": {
                    "type": "string",
                    "enum": [
                        "group_size", "activity", "location", "is_certified",
                        "is_colombian", "ages", "hotel", "last_dive_over_2_years",
                        "refresher_interested",
                    ],
                    "description": (
                        "Set ONLY if the customer is asking the bot to remind "
                        "them of a detail THEY ALREADY GAVE earlier in this "
                        "chat (e.g. 'how many people did I say?', '¿qué "
                        "actividad había pedido?', 'remind me what I said'). "
                        "Pick which field is being asked about. Do NOT set "
                        "this for product/price/logistics questions — those "
                        "are answered elsewhere."
                    ),
                },
                "companion_activity": {
                    "type": "string",
                    "enum": ["certified_diving", "minicourse", "snorkel"],
                    "description": (
                        "Set ONLY if the message introduces an ADDITIONAL "
                        "person joining the booking (a friend/partner/family "
                        "member coming along) — NOT the speaker restating or "
                        "changing their own plan. Use the activity that "
                        "ADDED person wants, applying the same business rule "
                        "as everywhere else: 'minicourse' if they are NOT "
                        "certified and want to dive/try diving, "
                        "'certified_diving' if they ARE already certified "
                        "and want to dive, 'snorkel' if they want snorkel "
                        "only."
                    ),
                },
                "companion_qty": {
                    "type": "integer",
                    "description": (
                        "How many additional people this describes. Default "
                        "1 for a bare 'a friend'/'a companion' if the message "
                        "doesn't give a number."
                    ),
                },
                "refresher_interested": {
                    "type": "boolean",
                    "description": (
                        "Set ONLY when the message answers whether the "
                        "customer wants the in-water refresher session, using "
                        "phrasing the simple yes/no parser wouldn't catch "
                        "(e.g. 'sí, no estaría mal', 'mejor no, gracias', "
                        "'claro que sí'). True if they want it, false if not."
                    ),
                },
            },
        },
    },
}


def _signals_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una capa de detección de señales para un bot de buceo. El "
            "mensaje del cliente NO avanzó la reserva por los caminos "
            "deterministas normales — tu única tarea es revisar si describe "
            "(1) un pedido de recordar algo que el cliente YA dijo antes en "
            "esta conversación, o (2) una persona ADICIONAL que se une a la "
            "reserva (no el propio hablante). Llama a `detect_signals` "
            "incluyendo SOLO los campos para los que el mensaje da señal "
            "real y explícita. Omite cualquier campo ambiguo — nunca "
            "lo adivines."
        )
    return (
        "You are a signal-detection layer for a scuba diving bot. The "
        "customer's message did NOT advance the booking through the normal "
        "deterministic paths — your only job is to check whether it (1) "
        "asks the bot to recall something the customer ALREADY said earlier "
        "in this conversation, or (2) introduces an ADDITIONAL person "
        "joining the booking (not the speaker themself). Call "
        "`detect_signals` including ONLY the fields the message gives real, "
        "explicit signal for. Omit anything ambiguous — never guess."
    )


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
    messages: list[dict] = [{"role": "system", "content": _signals_system_prompt(lang)}]
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
            tools=[_SIGNALS_TOOL],
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
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LLM_EXTRACTOR] signals error: {exc}")
        return {}

    result = {k: v for k, v in (args or {}).items() if v not in (None, "", [], {})}
    if result:
        logger.info(f"[CORE][SIGNALS] detected={result} msg={message[:80]!r}")
    return result
