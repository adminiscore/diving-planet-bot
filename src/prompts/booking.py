"""Prompts del nodo **booking** (`src/agents/booking_agent.py` y su subgrafo).

Uno por red, en el orden de las fases del subgrafo (`setup → availability →
routing → extraction → slotfill_close`, Fase 3.3):

- `LANGUAGE_DETECT_PROMPT` — fase `setup`, solo primer turno y solo si la
  heurística de stopwords no encontró señal (`detect_language_llm`).
- (lat-11 T6e, 26-oct) `EXTRACTION_TOOL` · `extraction_system_prompt` (el relleno `fill_gaps`) se quitaron: el
  extractor del turno es `extractor_turno`.
- `SIGNALS_TOOL` · `signals_system_prompt` — fases `routing` y `extraction`
  (`detect_special_signals`): pedir recordar un dato ya dado, y acompañante
  añadido a mitad de flujo.
- `SLOT_RESOLVER_SPEC` · `slot_resolver_prompt` · `slot_resolver_tool` — red
  anti-bucle (`resolve_slot_answer`): interpreta la respuesta EN EL CONTEXTO de
  la pregunta concreta que se acaba de hacer, o se abstiene (y el bot
  re-pregunta como siempre — nunca peor que hoy).
- (lat-B, 24-oct) el acuse cálido de una frase ya no es un modelo: lo pone el código en `slotfill_close`.

Cada prompt es corto y enfocado a UN caso de uso (patrón IBM, §4 del plan);
ninguno "lo abarca todo".
"""

from __future__ import annotations

from src.domain import activities as _activities

# ── Idioma del primer turno · `language_detector.detect_language_llm` ───────

LANGUAGE_DETECT_PROMPT = (
    'Detect whether this message is written in Spanish or English. '
    'Reply with ONLY "es" or "en", nothing else.\n\n'
    'Message: "{message}"'
)


# ── Lugares sin Barú · `lugar_sin_baru` (lo usan el resolutor y la pregunta de Jev) ──────────
# lat-11 T6e (26-oct): el tool y el prompt de la extracción del relleno (`fill_gaps`, quitado en lat-11 T1a) se fueron.

# G3-06 (18-oct, decisión de Gadea, flag `baru_no_es_rosario`): Barú (y Playa Blanca, que está en Barú) NO es Islas del
# Rosario: es una península unida a tierra, y allí no operamos. Estos textos lo contaban como "las islas", y el bot
# decía a la vez "en Barú no operamos" y "la recogida está incluida", con precios de las islas (conv 5572).
_BARU_EN = " Barú and Playa Blanca are NOT the islands: they are a peninsula joined to the mainland, where we do not operate."
_BARU_ES = " Barú y Playa Blanca NO son las islas: son una península unida a tierra, donde no operamos."
_SIN_BARU = (
    ("staying on or coming from the Rosario Islands, Barú, or a specific island/island-hotel.",
     "staying on or coming from the Rosario Islands or a specific island/island-hotel." + _BARU_EN),
    ("Islas del Rosario, Barú, o una isla/hotel de isla concreto.",
     "Islas del Rosario o una isla/hotel de isla concreto." + _BARU_ES),
    ("se hospeda en o viene de Islas del Rosario, Baru o un hotel de isla",
     "se hospeda en o viene de Islas del Rosario o un hotel de isla (Barú y Playa Blanca no)"),
    ("staying on or coming from the Rosario Islands, Baru or an island hotel",
     "staying on or coming from the Rosario Islands or an island hotel (not Barú or Playa Blanca)"),
    ("the islands (Barú, Isla Grande, Islas del Rosario, Playa Blanca, an island hotel or eco-hostel).",
     "the islands (Isla Grande, Islas del Rosario, an island hotel or eco-hostel)." + _BARU_EN),
    ("(e.g. Isla Grande, Barú, Isla del Sol)", "(e.g. Isla Grande, Isla del Sol)"),
)


# gen-6 (21-oct, flag `baru_sale_de_cartagena`): con G3-06 Barú dejó de ser "las islas", pero tampoco era nada: el lugar
# quedaba sin saber y el bot volvía a preguntar "¿desde dónde saldrías?" a quien acababa de decir "estamos en Barú"
# (banco gen-6 2/2). La política (policies.json, transporte): quien se aloja en Barú sale desde Cartagena (Muelle de la
# Bodeguita). Se añade a cada texto de Barú, para todos los lectores del lugar.
_BARU_A_CARTAGENA = (
    (_BARU_EN, _BARU_EN + " Someone staying there sets out from Cartagena (Muelle de la Bodeguita): that is 'cartagena'."),
    (_BARU_ES, _BARU_ES + " Quien se aloja allí sale desde Cartagena (Muelle de la Bodeguita): eso es 'cartagena'."),
    ("(Barú y Playa Blanca no)", "(Barú y Playa Blanca no: quien se aloja allí sale desde Cartagena)"),
    ("(not Barú or Playa Blanca)", "(not Barú or Playa Blanca: someone staying there sets out from Cartagena)"),
)


def lugar_sin_baru(texto: str, sale_de_cartagena: bool = False) -> str:
    """Los textos de lugar sin Barú ni Playa Blanca entre "las islas". Lo aplica quien lee el flag `baru_no_es_rosario`
    (este módulo no importa `src`); con `sale_de_cartagena` (flag `baru_sale_de_cartagena`, gen-6), además, quien se
    aloja allí es 'cartagena'."""
    if not isinstance(texto, str):
        return texto
    for antes, despues in _SIN_BARU:
        texto = texto.replace(antes, despues)
    if sale_de_cartagena:
        for antes, despues in _BARU_A_CARTAGENA:
            texto = texto.replace(antes, despues)
    return texto


# ── Señales de turno: «¿me recuerdas…?» · `llm_extractor.detect_special_signals` ────

# ---------------------------------------------------------------------------
# Detección de un pedido de RECORDAR un dato ya dado (núcleo conversacional): el LLM dice QUÉ campo se pide y el
# CÓDIGO contesta con el valor real del estado (nunca un valor que el LLM crea que se dijo). Hasta el 28-oct esta
# herramienta también buscaba acompañantes y el refresher (la «red de señales»); CALN-8 la quitó: a quien viene lo
# leen el extractor y el lector del grupo, y el refresher el extractor (CAL-F).
SIGNALS_TOOL = {
    "type": "function",
    "function": {
        "name": "detect_signals",
        "description": (
            "Check ONLY whether the customer's message asks the bot to recall/remind something the customer ALREADY "
            "said earlier in this conversation. Omit the field entirely if it doesn't apply — never guess."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recall_field": {"type": "string", "enum": ["booking_recap", "group_size", "activity", "location", "is_certified", "is_colombian", "ages", "hotel", "last_dive_over_2_years", "refresher_interested"], "description": "Set ONLY if the customer is asking the bot to remind them of something THEY ALREADY GAVE earlier in this chat. Use 'booking_recap' for a GENERAL recap request ('¿qué te había pedido?', '¿qué llevamos?', 'what did I ask for?', 'remind me what I said') — the bot then recaps the WHOLE booking. Use a specific field only for a specific question ('¿cuántas personas dije?' → group_size). Do NOT set this for product/price/logistics questions — those are answered elsewhere. IMPORTANT distinction: a forward-looking RECOMMENDATION question ('¿qué me recomiendas?', '¿cuál es mejor, snorkel o buceo?', 'what do you suggest for us?') is NOT a recall — it asks for NEW advice, not to repeat past info. Leave this field unset for those; only set it when the message is unambiguously asking to repeat something already said."},
            },
        },
    },
}


def signals_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una capa de detección para un bot de buceo. Tu única tarea es ver si el mensaje del cliente pide que "
            "le recordemos algo que él YA dijo antes en esta conversación. Llama a `detect_signals` con recall_field "
            "solo si es así; si no, sin campos. Nunca lo adivines."
        )
    return (
        "You are a detection layer for a scuba diving bot. Your only job is to check whether the customer's message "
        "asks the bot to recall something the customer ALREADY said earlier in this conversation. Call "
        "`detect_signals` with recall_field only if so; otherwise with no fields. Never guess."
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
    "course_level": {
        "question_es": "¿Qué curso o especialidad te interesa?",
        "question_en": "Which course or specialty are you interested in?",
        "type": "string",
        # Generado desde el registro de actividades (F4): cursos y especialidades
        # concretos y reservables. Un valor nuevo en el registro llega solo aqui.
        "enum": [
            a.id for a in _activities.registry().activities
            if a.family in ("course", "specialty") and not a.generic and a.cart_type and a.sold_as is None
            and a.offer
        ],
        "value_meaning": (
            "the id of the course or specialty the customer picks from the options "
            "the bot offered (Open Water is the first certification course, then "
            "Advanced, Rescue, Divemaster; specialties are Nitrox, Buoyancy, "
            "Naturalist, Fish Identification, Mindful Diving). Omit if the reply "
            "does not clearly pick one, and ALSO omit it when the customer hands the "
            "choice back to the bot instead of choosing (asks you to pick or "
            "recommend): do not choose for them."
        ),
    },
    "companion_activity_choice": {
        "question_es": "¿Qué le gustaría hacer a tu acompañante?",
        "question_en": "What would your companion like to do?",
        "type": "string",
        # Lo que el bot puede recomendar a un acompañante sin certificación
        # (owner 2026-09-14). El nucleo valida la respuesta contra las opciones
        # que de verdad ofrecio (Open Water solo si se quedan varios dias).
        "enum": ["minicourse", "padi_open_water", "snorkel", "companion"],
        "value_meaning": (
            "'minicourse' if the companion wants to TRY diving / go underwater "
            "with an instructor (bautizo, discover scuba, 'probar el buceo', "
            "'bajar con tanque', 'que se anime a bucear'); 'padi_open_water' if "
            "they want to get CERTIFIED (the Open Water course); 'snorkel' if they "
            "want to stay at the surface with mask and fins (snorkel, careteo, "
            "'ver los peces desde arriba', 'solo nadar'); 'companion' if they will "
            "just come along without any in-water activity ('solo acompaña', "
            "'no se mete al agua'). Omit if the reply doesn't clearly choose one "
            "(e.g. 'lo que sea mejor', 'no sé'), and omit it when the customer hands "
            "the choice back to the bot: do not choose for them."
        ),
    },
    "cert_or_course": {
        "question_es": "¿Ya tienen esa certificación o quieren sacarla con el curso?",
        "question_en": "Do you already hold that certification, or do you want to get it with the course?",
        "type": "string",
        "enum": ["already_certified", "wants_course"],
        "value_meaning": (
            "'already_certified' if they say they already hold that PADI level (ya lo "
            "tenemos, somos buzos, we have it); 'wants_course' if they want to take the "
            "course to get it (queremos sacarlo, hacer el curso, we want to get "
            "certified). Omit if the reply doesn't say, or if it hands the choice back "
            "to the bot."
        ),
    },
    "stay_duration": {
        "question_es": "¿Van a estar un solo día o varios días?",
        "question_en": "Will you be here for a single day or several days?",
        "type": "string",
        "enum": ["single_day", "multi_day"],
        "value_meaning": (
            "'single_day' if they only have one day for the activity; 'multi_day' "
            "if they stay two or more days near the dive sites (several days, a "
            "weekend, 'nos quedamos 3 noches'). Omit if the reply doesn't say."
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


# 18-oct (flag `resolutor_sin_contradicciones`; ronda mod-D, reserva-solo-link): a "¿Eres buzo certificado?" el cliente
# contestó "no, buceé hace poco" (su "no" era para otra pregunta) y el resolutor fijó "no certificado" → minicurso. Una
# respuesta que se contradice no fija nada: el bot vuelve a preguntar en vez de adivinar (decisión de Gadea 18-oct).
SLOT_RESOLVER_CONTRADICCION = (
    " If the reply contradicts itself — a yes/no next to details that point to the opposite answer (for example "
    "\"no, I dived recently\" to a question about being certified), or the yes/no seems to answer something else — "
    "omit `value` (do NOT pick one side)."
)


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
