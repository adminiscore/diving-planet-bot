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
                        "people referred to by relationship. Infer the count ONLY "
                        "when the message enumerates a specific, countable number of "
                        "individuals: 'my wife and I' = 2, 'me plus 3 friends' = 4, "
                        "'my daughter, my son and us two' = 4, 'four adults and a "
                        "kid' = 5. Do NOT set this field when companions are "
                        "mentioned as a vague, uncounted plural with no number given "
                        "at all — e.g. 'my friends'/'mis amigos', 'some friends'/"
                        "'unos amigos', 'my family' with no headcount. A vague plural "
                        "implies more than one but NOT a specific total; guessing a "
                        "number here is exactly the kind of invented value you must "
                        "avoid — omit the field and let the bot ask how many."
                    ),
                },
                "group_allocation": {
                    "type": "object",
                    "description": (
                        "Split of the group by activity, ONLY when each activity's "
                        "headcount is explicitly countable, e.g. "
                        '{"certified_diving": 2, "snorkel": 1}. If the message '
                        "describes a mixed group but one side has no countable "
                        "number — e.g. 'yo buceo y mis amigos snorkel' (an "
                        "uncounted plural of companions) — omit this field "
                        "entirely rather than guessing a headcount for that side; "
                        "the bot will ask how many."
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
                        "booking_recap", "group_size", "activity", "location",
                        "is_certified", "is_colombian", "ages", "hotel",
                        "last_dive_over_2_years", "refresher_interested",
                    ],
                    "description": (
                        "Set ONLY if the customer is asking the bot to remind "
                        "them of something THEY ALREADY GAVE earlier in this "
                        "chat. Use 'booking_recap' for a GENERAL recap request "
                        "('¿qué te había pedido?', '¿qué llevamos?', 'what did "
                        "I ask for?', 'remind me what I said') — the bot then "
                        "recaps the WHOLE booking. Use a specific field only "
                        "for a specific question ('¿cuántas personas dije?' → "
                        "group_size). Do NOT set this for product/price/"
                        "logistics questions — those are answered elsewhere. "
                        "IMPORTANT distinction: a forward-looking RECOMMENDATION "
                        "question ('¿qué me recomiendas?', '¿cuál es mejor, "
                        "snorkel o buceo?', 'what do you suggest for us?') is "
                        "NOT a recall — it asks for NEW advice, not to repeat "
                        "past info. Leave this field unset for those; only set "
                        "it when the message is unambiguously asking to repeat "
                        "something already said."
                    ),
                },
                "companion_activity": {
                    "type": "string",
                    "enum": ["certified_diving", "minicourse", "snorkel"],
                    "description": (
                        "Set ONLY if the message introduces an ADDITIONAL, "
                        "SEPARATE person joining the booking (a friend/partner/"
                        "family member coming along, e.g. 'hay un amigo que "
                        "quiere hacer snorkel', 'viene mi primo a bucear', "
                        "'2 y uno hace snorkel', 'también mi novia'). Tolerate "
                        "typos and informal phrasing. Apply the business rule: "
                        "'minicourse' if that added person is NOT certified and "
                        "wants to dive/try diving, 'certified_diving' if they "
                        "ARE already certified, 'snorkel' if snorkel only. "
                        "CRITICAL — do NOT set this when the SPEAKER is simply "
                        "changing/correcting their OWN plan with no new person "
                        "('mejor snorkel', 'en realidad quiero snorkel', "
                        "'cambio a snorkel', 'just snorkel then', 'mejor "
                        "multi-día'): that is a change of mind, NOT a companion. "
                        "If in doubt about whether a NEW person exists, omit it."
                    ),
                },
                "mentions_other_person": {
                    "type": "boolean",
                    "description": (
                        "True if the message refers to someone OTHER than the "
                        "speaker joining the booking, in ANY phrasing or "
                        "regional slang for 'friend'/'buddy'/'companion' — "
                        "standard Spanish (amigo, novia, hermano, primo, "
                        "acompañante), regional Latin American slang (parce, "
                        "parcero, pana, cuate, carnal, compa, pata, causa), "
                        "English (friend, partner, someone), or any other way "
                        "of naming another person. False for a plain change of "
                        "mind by the SPEAKER with no other person involved "
                        "('mejor snorkel', 'en realidad quiero snorkel'). This "
                        "is a deliberately broad, language/region-agnostic "
                        "signal — the deterministic caller-side keyword list "
                        "cannot keep up with every regional term for 'friend', "
                        "so trust your own understanding here rather than "
                        "matching against a fixed vocabulary."
                    ),
                },
                "companion_is_singular": {
                    "type": "boolean",
                    "description": (
                        "True if the message describes EXACTLY ONE additional "
                        "person, regardless of the exact word used for "
                        "'friend'/'buddy' — standard Spanish (un amigo, mi "
                        "novia, mi acompañante), regional slang (mi parce, mi "
                        "cuate, mi pana, mi carnal, mi compa), or English (a "
                        "friend, someone). False (or omit) when the message "
                        "describes MORE than one person, an uncounted/vague "
                        "plural ('mis amigos', 'unos amigos', 'friends' with "
                        "no number), or when you're not sure it's exactly one. "
                        "The calling code has no fixed word list covering "
                        "every regional term for a single companion, so rely "
                        "on your own judgment here rather than matching "
                        "vocabulary — but if genuinely unsure, prefer False so "
                        "the calling code asks the customer instead of "
                        "guessing 1."
                    ),
                },
                "companion_qty": {
                    "type": "integer",
                    "description": (
                        "How many people want SPECIFICALLY the activity in "
                        "`companion_activity` — set ONLY when the message "
                        "gives an explicit, countable number for THAT "
                        "activity ('2 amigos' [same activity for both] -> 2, "
                        "'2 y uno hace snorkel' -> companion_qty=2 for the "
                        "diving side, with the snorkel side going in "
                        "`other_companions` instead, NOT added here). If "
                        "OTHER sub-groups exist (see `other_companions` "
                        "below), this number is ONLY for the first/main "
                        "sub-group, never the combined total across all "
                        "sub-groups — e.g. 'mi amigo bucea y mi otro amigo "
                        "hace snorkel' is ONE diver (companion_qty=1) and "
                        "ONE snorkeler (in other_companions), NOT "
                        "companion_qty=2. Omit this field entirely for a "
                        "single named companion ('a friend', 'mi novia' — "
                        "the calling code assumes 1 on its own) AND for a "
                        "vague, uncounted plural ('mis amigos', 'unos "
                        "amigos', 'friends' with no number) — do NOT guess a "
                        "total for an uncounted plural, the calling code "
                        "asks the customer how many instead."
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
                "other_companions": {
                    "type": "array",
                    "description": (
                        "Use ONLY when the message describes TWO OR MORE "
                        "DISTINCT companion sub-groups with DIFFERENT "
                        "activities (e.g. 'mi amigo bucea y mi otra amiga hace "
                        "snorkel' = one diver + one snorkeler; 'dos amigos "
                        "bucean y uno hace snorkel' = two divers + one "
                        "snorkeler). Put the FIRST/main sub-group in "
                        "companion_activity/companion_qty/"
                        "companion_is_singular as always, and list every "
                        "OTHER sub-group here, one item per distinct "
                        "activity. Each item MUST include an explicit, "
                        "countable qty for that sub-group (a single named "
                        "companion like 'mi otro amigo' counts as qty=1) — "
                        "if a sub-group's count is a vague/uncounted plural "
                        "with no number, omit that item entirely rather than "
                        "guessing (the calling code cannot yet ask a "
                        "follow-up quantity question per sub-group). Leave "
                        "this array empty/omitted when there's only one "
                        "companion sub-group."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "activity": {
                                "type": "string",
                                "enum": ["certified_diving", "minicourse", "snorkel"],
                            },
                            "qty": {"type": "integer"},
                        },
                        "required": ["activity", "qty"],
                    },
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
            "reserva (no el propio hablante). Cuando detectes (2), decide "
            "SIEMPRE estos CUATRO campos juntos, nunca solo alguno: "
            "`companion_activity` (la actividad del acompañante), "
            "`mentions_other_person=true`, `companion_is_singular` "
            "(true si es exactamente 1 persona, false si son más o no estás "
            "seguro), y `companion_qty` (el número EXACTO si el mensaje lo da "
            "explícito, p. ej. 'se apuntan 3 amigos' -> companion_qty=3 — "
            "ponlo SIEMPRE que el mensaje dé un número, no lo omitas solo "
            "porque ya pusiste companion_is_singular=false). Los CUATRO son "
            "la señal que el código usa para confiar en tu detección "
            "— especialmente `companion_activity`, sin el cual el código "
            "descarta todo el resto — así que no los omitas aunque el "
            "vocabulario sea informal o regional (parce, cuate, pana, "
            "carnal...); el código que te llama NO tiene una lista de "
            "palabras que cubra todas las variantes regionales, así que "
            "confía en tu propio criterio. Si el mensaje describe DOS O MÁS "
            "acompañantes con actividades DISTINTAS ('mi parce bucea y mi "
            "cuate hace snorkel'), pon el PRIMER grupo en "
            "companion_activity/companion_qty/companion_is_singular como "
            "siempre, y cada grupo ADICIONAL en `other_companions` (cada uno "
            "con su actividad y su cantidad exacta — omite un grupo si su "
            "cantidad no es un número real, nunca la adivines). Llama a "
            "`detect_signals` incluyendo SOLO los campos para los que el "
            "mensaje da señal real y explícita (recall_field, "
            "refresher_interested y other_companions solo si aplican). "
            "Omite cualquier campo ambiguo — nunca lo adivines."
        )
    return (
        "You are a signal-detection layer for a scuba diving bot. The "
        "customer's message did NOT advance the booking through the normal "
        "deterministic paths — your only job is to check whether it (1) "
        "asks the bot to recall something the customer ALREADY said earlier "
        "in this conversation, or (2) introduces an ADDITIONAL person "
        "joining the booking (not the speaker themself). When you detect "
        "(2), ALWAYS decide these FOUR fields together, never just some of "
        "them: `companion_activity` (the companion's activity), "
        "`mentions_other_person=true`, `companion_is_singular` (true "
        "if exactly one person, false if more or unsure), and "
        "`companion_qty` (the EXACT number if the message gives one "
        "explicitly, e.g. '3 friends are joining' -> companion_qty=3 — "
        "always set it when the message gives a number, don't skip it just "
        "because you already set companion_is_singular=false). All FOUR are "
        "the fields the calling code trusts — especially "
        "`companion_activity`, without which the code discards everything "
        "else — "
        "to confirm your detection, so don't omit them even for informal or "
        "regional slang; the calling code has no fixed word list covering "
        "every regional term, so rely on your own judgment. If the message "
        "describes TWO OR MORE companion sub-groups with DIFFERENT "
        "activities ('my friend dives and my other buddy snorkels'), put "
        "the FIRST sub-group in companion_activity/companion_qty/"
        "companion_is_singular as always, and every ADDITIONAL sub-group in "
        "`other_companions` (each with its activity and its exact qty — "
        "omit a sub-group if its count isn't a real number, never guess "
        "it). Call `detect_signals` including ONLY the fields the message "
        "gives real, explicit signal for (recall_field, "
        "refresher_interested and other_companions only when they apply). "
        "Omit anything ambiguous — never guess."
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

# Qué pregunta representa cada slot (para anclar la interpretación del LLM) y
# qué tipo de valor devolver. Claves = nombres de slot de conversational_core.
_SLOT_RESOLVER_SPEC = {
    "safety": {
        "question_es": "¿Han pasado más de 2 años desde tu última inmersión?",
        "question_en": "Has it been more than 2 years since your last dive?",
        "type": "boolean",
        "value_meaning": (
            "true if it HAS been more than 2 years (or the customer implies a "
            "very long time / doesn't remember / 'ages ago'); false if it has "
            "been 2 years or less (recent, 'last month', 'this year', or 'none "
            "of us has been that long')."
        ),
    },
    "nationality": {
        "question_es": "¿Eres colombiano o residente en Colombia?",
        "question_en": "Are you Colombian or a resident of Colombia?",
        "type": "boolean",
        "value_meaning": (
            "true if the customer is Colombian OR lives/resides in Colombia "
            "(e.g. 'vivo en bogotá', 'soy de medellín', 'residente aquí'); "
            "false if they are a foreigner / tourist / live abroad (e.g. 'soy "
            "de españa', 'somos de argentina', 'extranjero', 'just visiting')."
        ),
    },
    "qty": {
        "question_es": "¿Para cuántas personas armamos el plan?",
        "question_en": "How many people should I plan for?",
        "type": "integer",
        "value_meaning": (
            "the TOTAL number of people, counting the speaker — 'solo yo'/'just "
            "me' = 1, 'un par'/'a couple' = 2, 'unos tres'/'about three' = 3, "
            "'mi pareja y yo'/'my partner and I' = 2. Only set it when the "
            "answer implies a concrete count; omit if genuinely unknown."
        ),
    },
    "certification": {
        "question_es": "¿Eres buzo certificado?",
        "question_en": "Are you a certified diver?",
        "type": "boolean",
        "value_meaning": (
            "true if the customer is a certified diver (has any diving "
            "certification — Open Water, Advanced, PADI, SSI, etc., or says "
            "yes); false if they are NOT certified (beginner, never dived, "
            "'no', 'quiero probar')."
        ),
    },
    "refresher": {
        "question_es": "¿Quieres hacer el refresher (repaso en el agua)?",
        "question_en": "Would you like to do the refresher (in-water refresh)?",
        "type": "boolean",
        "value_meaning": "true if they want the refresher, false if not.",
    },
}


def _slot_resolver_prompt(slot: str, lang: str) -> str:
    spec = _SLOT_RESOLVER_SPEC[slot]
    q = spec["question_es"] if lang == "es" else spec["question_en"]
    return (
        "You are a single-slot answer interpreter for a scuba diving booking "
        f"bot. The bot asked the customer exactly this question: \"{q}\". "
        "Interpret the customer's reply as an answer to THAT question, in any "
        "regional Spanish or English phrasing, slang, typos, or indirect "
        f"wording. The value means: {spec['value_meaning']} "
        "Call `resolve_slot` with the `value` field ONLY if the reply really "
        "answers the question; if the reply is off-topic, a counter-question, "
        "or genuinely doesn't answer it, omit `value` entirely (do NOT guess)."
    )


def _slot_resolver_tool(slot: str) -> dict:
    spec = _SLOT_RESOLVER_SPEC[slot]
    return {
        "type": "function",
        "function": {
            "name": "resolve_slot",
            "description": "Report the interpreted answer to the single question the bot just asked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": spec["type"],
                        "description": "The interpreted answer. Omit if the reply doesn't actually answer the question.",
                    },
                },
            },
        },
    }


async def resolve_slot_answer(
    slot: str,
    message: str,
    *,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
) -> dict:
    """Interpreta `message` como respuesta al slot booleano/escalar `slot`
    cuando el parser canónico ya falló. Devuelve {"value": <bool|int>} o {} si
    no aplica / cualquier fallo. Nunca lanza. Ver `_SLOT_RESOLVER_SPEC`."""
    if slot not in _SLOT_RESOLVER_SPEC or not message or not message.strip():
        return {}
    try:
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=[
                {"role": "system", "content": _slot_resolver_prompt(slot, lang)},
                {"role": "user", "content": message},
            ],
            tools=[_slot_resolver_tool(slot)],
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

def _ack_system_prompt(lang: str, client_name: str | None) -> str:
    name_es = f" El cliente se llama {client_name}; salúdalo/nómbralo con naturalidad de vez en cuando (no en cada mensaje)." if client_name else ""
    name_en = f" The customer's name is {client_name}; address them by name naturally now and then (not every message)." if client_name else ""
    if lang == "es":
        return (
            "Eres *Coral*, de Diving Planet (buceo en las Islas del Rosario, Cartagena). "
            "Tono cálido, cercano y colombiano, con medida." + name_es + " "
            "Tu ÚNICA tarea: escribir UNA sola frase corta que RECONOZCA con calidez lo que "
            "el cliente acaba de decir (que se sienta escuchado y que la conversación fluye). "
            "PROHIBIDO: mencionar precios, cifras de dinero, enlaces/URLs, o hacer una pregunta "
            "(otra parte del sistema añade el dato y la pregunta). Si no hay nada natural que "
            "reconocer, responde con una cadena vacía."
        )
    return (
        "You are *Coral* from Diving Planet (diving in the Rosario Islands, Cartagena). "
        "Warm, friendly, measured tone." + name_en + " "
        "Your ONLY task: write ONE short sentence that warmly ACKNOWLEDGES what the customer "
        "just said (so they feel heard and the chat flows). FORBIDDEN: mentioning prices, money "
        "figures, links/URLs, or asking a question (another part of the system adds the data and "
        "the question). If there's nothing natural to acknowledge, reply with an empty string."
    )


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
                {"role": "system", "content": _ack_system_prompt(lang, client_name)},
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
