"""Prompts del nodo **booking** (`src/agents/booking_agent.py` y su subgrafo).

Uno por red, en el orden de las fases del subgrafo (`setup → availability →
routing → extraction → slotfill_close`, Fase 3.3):

- `LANGUAGE_DETECT_PROMPT` — fase `setup`, solo primer turno y solo si la
  heurística de stopwords no encontró señal (`detect_language_llm`).
- `EXTRACTION_TOOL` · `extraction_system_prompt` — fase `extraction`
  (`fill_gaps`): rellena SOLO los campos que el detector determinista dejó sin
  resolver. Regla central: **abstenerse es mejor que rellenar mal**.
- `SIGNALS_TOOL` · `signals_system_prompt` — fases `routing` y `extraction`
  (`detect_special_signals`): pedir recordar un dato ya dado, y acompañante
  añadido a mitad de flujo.
- `SLOT_RESOLVER_SPEC` · `slot_resolver_prompt` · `slot_resolver_tool` — red
  anti-bucle (`resolve_slot_answer`): interpreta la respuesta EN EL CONTEXTO de
  la pregunta concreta que se acaba de hacer, o se abstiene (y el bot
  re-pregunta como siempre — nunca peor que hoy).
- `acknowledgement_system_prompt` — fase `slotfill_close`
  (`compose_acknowledgement`): UNA frase cálida que reconoce lo que el cliente
  dijo. Los datos duros (precio, link, resumen) los pone la capa determinista
  que se concatena después — el prompt los tiene PROHIBIDOS.

Cada prompt es corto y enfocado a UN caso de uso (patrón IBM, §4 del plan);
ninguno "lo abarca todo".
"""

from __future__ import annotations

# ── Idioma del primer turno · `language_detector.detect_language_llm` ───────

LANGUAGE_DETECT_PROMPT = (
    'Detect whether this message is written in Spanish or English. '
    'Reply with ONLY "es" or "en", nothing else.\n\n'
    'Message: "{message}"'
)


# ── Extracción de campos de la reserva · `llm_extractor.fill_gaps` ──────────

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
EXTRACTION_TOOL = {
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
                        "the bot will ask how many. Same rule for the ACTIVITY "
                        "itself, not just the headcount: if a companion is "
                        "mentioned only by an attribute (e.g. 'mi amigo no está "
                        "certificado' / 'my friend isn't certified') with NO "
                        "stated activity or intent ('quiere bucear'/'wants to "
                        "try diving'/'quiere snorkel'), do NOT guess which "
                        "activity that companion wants (neither snorkel nor "
                        "minicourse) — leave that companion out of this field "
                        "entirely; the bot will ask what they'd like to do."
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


def extraction_system_prompt(lang: str, missing_fields: list[str]) -> str:
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


# ── Verificacion de `activity` en mensajes ambiguos · `llm_extractor.verify_activity` ──
#
# Distinta de `extraction_system_prompt` a proposito: esa asume que el campo
# quedo SIN resolver; aqui el regex SI resolvio `activity`, pero el mensaje
# dispara 2+ categorias de patrones a la vez (ver
# `intent_detector.matched_activity_categories`) -- candidato real a que el
# regex haya ganado por ORDEN de comprobacion, no porque sea lo que el
# cliente pidio (hallazgo en vivo, conversacion real "purple-sun-590",
# 2026-09-03: "quiero el open water, nunca he buceado" resolvia a minicurso).
# Reusa el mismo EXTRACTION_TOOL (el campo `activity` ya tiene el enum
# completo, incl. `padi_open_water` etc.) — no hace falta un tool nuevo.

def activity_verification_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una capa de VERIFICACIÓN para un bot de buceo (Diving Planet, "
            "Cartagena/Islas del Rosario). Un detector determinista ya asignó una "
            "actividad a este mensaje, pero el mensaje combina varias señales a "
            "la vez y el detector pudo haberse equivocado. Lee el mensaje entero "
            "con cuidado y decide tú, de forma independiente, qué actividad pidió "
            "el cliente — llama a `extract_fields` con SOLO el campo `activity`. "
            "Regla clave: si el cliente nombra explícitamente un curso PADI "
            "concreto (Open Water, Advanced, Rescue, Divemaster) o dice que "
            "quiere 'certificarse', ESO es lo que pidió, incluso si el mismo "
            "mensaje también dice que nunca ha buceado, que es su primera vez, o "
            "que no tiene experiencia — esas frases describen su NIVEL actual, "
            "no cambian el PRODUCTO que está pidiendo. Solo usa 'minicourse' "
            "cuando el mensaje NO nombra ningún curso PADI concreto y solo habla "
            "de probar el buceo sin certificarse. Si de verdad no hay señal "
            "clara, omite el campo — abstenerse es mejor que adivinar."
        )
    return (
        "You are a VERIFICATION layer for a scuba diving bot (Diving Planet, "
        "Cartagena/Rosario Islands). A deterministic detector already assigned "
        "an activity to this message, but the message combines several signals "
        "at once and the detector may have gotten it wrong. Read the whole "
        "message carefully and decide independently what activity the customer "
        "actually asked for — call `extract_fields` with ONLY the `activity` "
        "field. Key rule: if the customer explicitly names a specific PADI "
        "course (Open Water, Advanced, Rescue, Divemaster) or says they want to "
        "'get certified', THAT is what they asked for, even if the same message "
        "also says they've never dived, it's their first time, or they have no "
        "experience — those phrases describe their CURRENT level, they don't "
        "change the PRODUCT being requested. Only use 'minicourse' when the "
        "message does NOT name a specific PADI course and only talks about "
        "trying diving without certifying. If there's truly no clear signal, "
        "omit the field — abstaining is better than guessing."
    )


# ── Señales de turno: recall y acompañante · `llm_extractor.detect_special_signals` ────

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
SIGNALS_TOOL = {
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
                        "ARE already certified, 'snorkel' if snorkel only. That "
                        "business rule needs a stated ACTIVITY or intent, not "
                        "just a certification fact — 'mi amigo no está "
                        "certificado' / 'my friend isn't certified' with NO "
                        "mention of what they want to do (no 'quiere bucear', "
                        "no 'quiere snorkel') is NOT enough to guess minicourse "
                        "or snorkel: leave this field unset in that case, do "
                        "not guess between the two options. "
                        "CRITICAL — do NOT set this when the SPEAKER is simply "
                        "changing/correcting their OWN plan with no new person "
                        "('mejor snorkel', 'en realidad quiero snorkel', "
                        "'cambio a snorkel', 'just snorkel then', 'mejor "
                        "multi-día'): that is a change of mind, NOT a companion. "
                        "ALSO do NOT set this for an incidental mention of "
                        "family/friends that does NOT say they are JOINING "
                        "THIS booking — 'my family always talks about diving "
                        "here', 'mis amigos siempre hablan de este sitio', 'my "
                        "sister has done this before' are just conversation, "
                        "nobody is being added. Only set it when the message "
                        "actually proposes adding that person to THIS "
                        "reservation (wants to/quiere/would like to join, "
                        "come, dive, etc.) — mentioning a relative exists is "
                        "not the same as inviting them. If in doubt about "
                        "whether a NEW person is joining, omit it."
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
                        "('mejor snorkel', 'en realidad quiero snorkel'). Also "
                        "False for an incidental mention of family/friends "
                        "that does NOT propose adding them to THIS booking "
                        "('my family always talks about diving here', 'mis "
                        "amigos siempre hablan de este sitio') — that person "
                        "isn't joining, just being mentioned in conversation. "
                        "This is a deliberately broad, language/region-agnostic "
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
                        "asks the customer how many instead. MEASURED FAILURE "
                        "(audit 2026-07-23): models keep defaulting an "
                        "uncounted plural to 2 just because plural grammar "
                        "implies 'more than one' — 'mis amigos hacen snorkel' "
                        "does NOT mean exactly 2, it could be 2, 3, 5, or "
                        "more. Guessing 2 here is the exact invented-value "
                        "mistake you must avoid, just as much as guessing any "
                        "other number — omit the field, full stop."
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
                        "with no number, OMIT THAT ITEM ENTIRELY rather than "
                        "guessing (the calling code cannot yet ask a "
                        "follow-up quantity question per sub-group). Leave "
                        "this array empty/omitted when there's only one "
                        "companion sub-group. MEASURED FAILURES (audit "
                        "2026-07-23), both consistently reproduced — avoid "
                        "them: "
                        "(1) 'mi amigo bucea y mis amigos hacen snorkel' — "
                        "models keep guessing qty=2 for the vague 'mis "
                        "amigos' snorkel sub-group instead of omitting the "
                        "item. A vague plural is NOT '2' — it is UNKNOWN; "
                        "leave that item out of the array completely, even "
                        "though the array will then look incomplete. "
                        "(2) 'ocho personas hacen snorkel y yo buceo' — the "
                        "SPEAKER'S OWN activity ('yo buceo', stated at the "
                        "end) must NEVER appear as a companion item here "
                        "(e.g. a phantom {'activity': 'certified_diving', "
                        "'qty': 1}) — the speaker is captured by the main "
                        "`activity` field elsewhere, not by this array. This "
                        "array is ONLY for OTHER people, never the speaker, "
                        "regardless of where in the sentence their own plan "
                        "is mentioned."
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


def signals_system_prompt(lang: str) -> str:
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


# ── Resolutor de UN slot (red anti-bucle) · `llm_extractor.resolve_slot_answer` ────

# Qué pregunta representa cada slot (para anclar la interpretación del LLM) y
# qué tipo de valor devolver. Claves = nombres de slot de conversational_core.
SLOT_RESOLVER_SPEC = {
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
    "companion_activity_choice": {
        "question_es": "¿Qué le gustaría hacer a tu acompañante — el minicurso de buceo o snorkel?",
        "question_en": "What would your companion like to do — the beginner mini-course or snorkeling?",
        "type": "string",
        "enum": ["snorkel", "minicourse"],
        "value_meaning": (
            "'minicourse' if the companion wants to TRY diving / go underwater "
            "with an instructor (bautizo, discover scuba, 'probar el buceo', "
            "'bajar con tanque', 'que se anime a bucear'); 'snorkel' if they "
            "want to stay at the surface with mask and fins (snorkel, careteo, "
            "'ver los peces desde arriba', 'solo nadar'). Omit if the reply "
            "doesn't clearly choose one (e.g. 'lo que sea mejor', 'no sé')."
        ),
    },
    "companion_qty": {
        "question_es": "¿Cuántas personas serían para esa actividad?",
        "question_en": "How many people would that be for that activity?",
        "type": "integer",
        "value_meaning": (
            "the number of people for THIS activity sub-group — 'un par'/'a "
            "couple'/'los dos'/'both of them' = 2, 'solo uno'/'just one' = 1, "
            "'un trío' = 3, 'unos tres'/'about three' = 3. Only set it when the "
            "answer implies a concrete count; omit if genuinely unclear."
        ),
    },
    "location": {
        "question_es": "¿Desde dónde saldrías — desde Cartagena o ya estás en las islas?",
        "question_en": "Where would you depart from — from Cartagena or are you already on the islands?",
        "type": "string",
        "enum": ["cartagena", "island"],
        "value_meaning": (
            "'cartagena' if the customer departs FROM Cartagena / the mainland "
            "/ a Cartagena hotel, neighborhood or landmark (Bocagrande, "
            "Getsemaní, Centro, Manga, the old city...), or delegates the "
            "choice / asks for a recommendation (Cartagena is the default and "
            "most common departure); 'island' if they are ALREADY staying on "
            "the islands (Barú, Isla Grande, Islas del Rosario, Playa Blanca, "
            "an island hotel or eco-hostel). Omit only if the reply is truly "
            "unrelated to where they are coming from."
        ),
    },
}


def slot_resolver_prompt(slot: str, lang: str) -> str:
    spec = SLOT_RESOLVER_SPEC[slot]
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


def slot_resolver_tool(slot: str) -> dict:
    spec = SLOT_RESOLVER_SPEC[slot]
    value_schema = {
        "type": spec["type"],
        "description": "The interpreted answer. Omit if the reply doesn't actually answer the question.",
    }
    if "enum" in spec:
        value_schema["enum"] = spec["enum"]
    return {
        "type": "function",
        "function": {
            "name": "resolve_slot",
            "description": "Report the interpreted answer to the single question the bot just asked.",
            "parameters": {
                "type": "object",
                "properties": {"value": value_schema},
            },
        },
    }


# ── Acuse cálido de una frase · `llm_extractor.compose_acknowledgement` ─────

def acknowledgement_system_prompt(lang: str, client_name: str | None) -> str:
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
            "reconocer, responde con una cadena vacía. "
            "IMPORTANTE — idioma: responde SIEMPRE en español, sea cual sea el idioma del "
            "mensaje del cliente (auditoría 2026-08-26: un cliente que ya acordó hablar en "
            "inglés puede escribir una frase suelta en español — 'voy solo' — sin que eso "
            "signifique que cambió de idioma; el idioma de la CONVERSACIÓN es el que manda, no "
            "el del último mensaje). "
            "IMPORTANTE — no reinterpretes un HECHO como una PREFERENCIA (hallazgo en vivo, "
            "batería contra PRE, 2026-09-01): cuando el cliente declara un dato objetivo "
            "(nacionalidad, cantidad de personas, ubicación...), reconócelo tal cual, sin "
            "convertirlo en una opinión o elección suya. Ejemplo real: 'ninguno colombiano' "
            "(responde sobre nacionalidad del grupo) generó 'entiendo que prefieres no incluir "
            "a colombianos en tu grupo' — mal, suena a una elección excluyente que el cliente "
            "nunca expresó. Mejor: 'entendido, ninguno es colombiano' o similar, neutro y literal."
        )
    return (
        "You are *Coral* from Diving Planet (diving in the Rosario Islands, Cartagena). "
        "Warm, friendly, measured tone." + name_en + " "
        "Your ONLY task: write ONE short sentence that warmly ACKNOWLEDGES what the customer "
        "just said (so they feel heard and the chat flows). FORBIDDEN: mentioning prices, money "
        "figures, links/URLs, or asking a question (another part of the system adds the data and "
        "the question). If there's nothing natural to acknowledge, reply with an empty string. "
        "IMPORTANT — language: ALWAYS reply in English, regardless of what language the "
        "customer's message is in (audit 2026-08-26: a customer who already agreed to speak "
        "English may type a stray phrase in another language — 'voy solo' — that doesn't mean "
        "they switched languages; the CONVERSATION's language rules, not the last message's). "
        "IMPORTANT — don't reinterpret a FACT as a PREFERENCE (live finding, PRE battery, "
        "2026-09-01): when the customer states an objective fact (nationality, group size, "
        "location...), acknowledge it as-is, don't turn it into an opinion or choice they made. "
        "Real example: 'none of us are Colombian' (a nationality statement) produced 'I "
        "understand you'd rather not include Colombians in your group' — wrong, it sounds like "
        "an exclusionary choice the customer never expressed. Better: 'got it, none of you are "
        "Colombian' or similar — neutral and literal."
    )
