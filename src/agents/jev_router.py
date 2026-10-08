"""U3 (u3-1, paso 1): las 9 señales del router con Jev en vez de con el LLM.

Qué es Jev: un modelo de TypeSafe AI que contesta preguntas tipadas (sí/no con
probabilidad, elección entre opciones) sin generar texto. Se llama por el Decisions
API de OpenRouter. Evaluado en l2-4 (2026-09-24, `scripts/jev_router_eval.py` y
`scripts/jev_router_holdout.py`, salidas en `docs/robustness/l2-4-jev/`):

- batería de las 9 señales (37 casos × 8): 32/37 frente a 30/37 del router LLM, señales
  de seguridad 11/11 frente a 8/11, y siempre responde lo mismo (el router detecta
  "soy epiléptica" solo 3 de 8 veces);
- 257 mensajes del golden fuera de la batería: de los 50 desacuerdos con el router,
  Jev acierta ~41 (el router marca disponibilidad donde no la hay);
- ~0,27 s por llamada frente a ~1,3 s.

Aquí vive la configuración que ganó (la "v2" del script): las MISMAS descripciones
del tool del router (`src/prompts/router.py`) como preguntas, umbral 0,5, y dos
arreglos generales:

1. En Jev cada pregunta se contesta sin ver las demás, así que el "nunca las dos a la
   vez" que el LLM respeta al leer el tool entero se pierde. Se mete DENTRO de la
   elección: la opción "ninguno" del tema sensible nombra las señales específicas
   que tienen su propio campo (lo específico gana a lo general).
2. Las actividades se describen también con el vocabulario del cliente en español.

Nunca lanza excepción: devuelve `None` si Jev no está disponible, tarda más del
tiempo máximo o responde algo raro, y quien llama usa el router LLM de siempre.
"""

from __future__ import annotations

import logging
import time

import httpx

from src.config import settings
from src.prompts.router import ROUTING_TOOL

logger = logging.getLogger("uvicorn.error")

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
THRESHOLD = 0.5  # l2-4: el umbral bajo (0,3) para las señales "ante la duda" se descartó

_PROPS = ROUTING_TOOL["function"]["parameters"]["properties"]
_CONTEXT = (
    "Message from a customer to the booking chatbot of a scuba diving center "
    "(Diving Planet, Cartagena, Colombia). The message may be in Spanish or English."
)
_BOOLEAN_SIGNALS = (
    "wants_human", "wants_menu_or_restart", "adaptive_diving_topic",
    "availability_question", "broken_link_complaint", "asks_for_contact_number",
)
_NONE_SENSITIVE = (
    "None of the above. This includes messages that belong to a MORE SPECIFIC signal "
    "with its own field: asking to talk to a person without a complaint (that is "
    "wants_human), reporting that a link/page/button we sent is broken (that is "
    "broken_link_complaint), or a disability/accessibility topic (that is "
    "adaptive_diving_topic). Also general policy or catalog questions."
)
_ACTIVITY_ES = {
    "certified_diving": "scuba diving as a certified diver (Spanish: 'buceo', 'bucear', 'inmersiones')",
    "minicourse": "the first-time discover-scuba mini course (Spanish: 'minicurso', 'bautizo', 'primera vez')",
    "snorkel": "snorkeling (Spanish: 'snorkel', 'esnórquel')",
    "padi_course": "a full PADI certification course (Spanish: 'curso', 'Open Water', 'Advanced', 'certificarse')",
}


def routing_questions() -> dict:
    """El tool del router como preguntas de Jev, con las mismas descripciones."""
    q: dict = {}
    for name in _BOOLEAN_SIGNALS:
        q[name] = {"type": "noul", "instructions": _PROPS[name]["description"]}
    for name in ("sensitive_topic", "booking_change_topic"):
        spec = _PROPS[name]
        criteria = {v: f"The message is '{v}' as described." for v in spec["enum"]}
        criteria["none"] = (
            _NONE_SENSITIVE if name == "sensitive_topic" else "None of the above applies to this message."
        )
        q[name] = {"type": "choice", "instructions": spec["description"], "criteria": criteria}
    comp = _PROPS["comparing_options"]["properties"]
    q["comparing"] = {"type": "noul", "instructions": comp["comparing"]["description"]}
    for opt in comp["options"]["items"]["enum"]:
        q[f"opt_{opt}"] = {
            "type": "noul",
            "instructions": f"The customer is weighing {_ACTIVITY_ES[opt]} as one of the options. "
            + comp["options"]["description"],
        }
    return q


_QUESTIONS = routing_questions()

# u3-4: ¿trae el mensaje algo que haya que CONTESTAR? Va en la misma llamada (Jev contesta
# cada pregunta sin ver las demás, así que no cambia las otras respuestas). Escalón 0 del
# 24-sep, 257 mensajes del golden sin examen oculto: el regex de hoy ve 114 de 157
# preguntas; regex O Jev >= 0,7 ve 134 con 0 falsas alarmas.
ASKS_QUESTION = "asks_question"
ASKS_QUESTION_MIN = 0.7
_ASKS_QUESTION_Q = {
    "type": "noul",
    "instructions": (
        "The customer's message contains a QUESTION or a REQUEST FOR INFORMATION that the booking assistant must "
        "ANSWER (for example about prices, what is included, schedules, hotels, discounts, policies, logistics, "
        "how something works). It is FALSE if the message only gives booking details (dates, number of people, "
        "where they are, an activity choice), only answers the assistant's previous question, or is small talk "
        "or thanks."
    ),
}


# u3-4 (25-sep): la pregunta que NO existía en el sistema — ¿el cliente AFIRMA el dato, o
# solo lo NOMBRA dentro de su pregunta? Ni el relleno ni la verificación la hacen: las dos son
# extracción, y para un extractor "¿me recomiendas hoteles en la isla?" es una señal clara de
# `location=island` (la definición del campo dice justo eso). Meter el matiz en el prompt falló
# dos veces con medida (relleno 24-sep, verificación 25-sep). Jev sí la contesta: sonda de 12
# mensajes × 3 (`scripts/sonda_afirma_vs_pregunta.py`), 11/12 y con márgenes anchos — 0,07-0,48
# los que NO afirman frente a 0,75-0,97 los que sí. Van en la MISMA llamada del router, así que
# no gastan ninguna petición de más, igual que `asks_question`.
#
# La redacción está CALIBRADA contra los casos reales del escalón 0, no escrita a ojo: la primera
# versión descartaba de más (fijaba MENOS actividad que el propio flag apagado, y se comía datos
# afirmados como "I plan on being in Cartagena and do scuba diving… I have open water" o "estaremos
# en islas del rosario en junio"). Dos cosas lo arreglaron, las dos medidas: un plan de futuro
# CUENTA como decir dónde estarán, y nombrar un producto para preguntar su precio CUENTA como
# elegirlo (que es la regla de negocio del catálogo). 19/20 frente a 15/20 en
# `scripts/sonda_afirma_vs_pregunta.py`.
AFFIRMS_LOCATION = "affirms_location"
AFFIRMS_ACTIVITY = "affirms_activity"
ACTIVITY_HYPOTHESIS = "activity_hypothesis"
AFFIRMS_CERTIFICATION = "affirms_certification"
AFFIRMS_GROUP = "affirms_group"
AFFIRMS_NATIONALITY = "affirms_nationality"
AFFIRMS_P = "affirms_p"  # u3-3: probabilidades crudas de los affirms_*
AFFIRMS_DENY_MAX = 0.2  # u3-3: por debajo, Jev esta SEGURO de que el cliente no lo afirma
AFFIRMS_MIN = 0.7  # mismo umbral alto que `asks_question`: ante la duda, la conducta de hoy
_AFFIRMS_QUESTIONS = {
    AFFIRMS_LOCATION: {
        "type": "noul",
        "instructions": (
            "The customer tells us where THEY will be staying or will set out from for the diving "
            "— a hotel, a city, an island. A future plan counts ('I'll be in Cartagena in April', "
            "'estaremos en las islas en junio', 'reservaremos hotel en la isla'). It is FALSE when "
            "the place appears ONLY inside what they are asking about: asking which hotels there "
            "we recommend, wondering what if they stayed there, asking whether a place belongs to "
            "an area, or saying where SOMEONE ELSE will be."
        ),
    },
    # Recalibrada el 26-sep (Gadea, tras la ronda B2). La redacción anterior era demasiado
    # conservadora: en 57 mensajes del golden que NO están en el banco (etiquetados por un
    # anotador LLM aparte) tiraba 23 actividades que el cliente sí dice — "we just booked a
    # 5 dive package", "so excited for diving with your team on Monday", "I just booked a
    # beginner mini diving experience" — y la regresión de la ronda B2 ("Yo soy open y me
    # gustaría salir un día… No sé qué tienen", 0,33) era la misma familia. Ahora cuenta
    # también lo ya reservado o lo que viene a hacer, y preguntar qué salidas hay. Y no decide
    # sola: ver `ACTIVITY_HYPOTHESIS` y `activity_affirmed`.
    AFFIRMS_ACTIVITY: {
        "type": "noul",
        "instructions": (
            "The customer tells us which activity or course THEY want, are coming to do, or have already "
            "booked: diving, a mini course, snorkeling or a certification course. Naming it to ask its "
            "price, dates, schedule, what is included or how to book it counts, and so does saying they "
            "would like to do it and then asking which trips or options we have. It is FALSE only when "
            "they raise it as a hypothesis ('in case I decided to do the Open Water course'), ask whether "
            "it would be possible at all for someone, or ask us to recommend WHICH activity to do."
        ),
    },
    # La otra cara, en la misma llamada (coste 0): ¿aparece la actividad SOLO como hipótesis o
    # pregunta abierta? Los datos que hay que matar tienen esa forma, y Jev la reconoce con
    # márgenes anchos (0,75-0,94 en esos casos frente a 0,02-0,17 en los afirmados).
    ACTIVITY_HYPOTHESIS: {
        "type": "noul",
        "instructions": (
            "The customer mentions a diving activity or course ONLY as a hypothesis or an open question, "
            "without telling us they want it, are coming to do it or have booked it: 'in case I decided to "
            "do the course', 'would it be possible for my son to get certified?', 'which activity do you "
            "recommend for them?'. It is FALSE when they say they want it, plan to do it, are booked for "
            "it, or ask its price, dates, schedule or details as someone who is going to do it."
        ),
    },
    # u3-5 (calibradas por Álvaro el 25-sep, en el código desde el 26-sep): la misma puerta para
    # certificado, número de personas y nacionalidad. Banco `u35`: 66/67 sobre casos reales del
    # golden, 28 de ellos no usados para escribir las frases (`scripts/sonda_afirma_vs_pregunta.py`).
    # Matan los datos nombrados DENTRO de una pregunta ("in case I decided to do PADI Open Water"
    # -> certificado; "costo para colombianos" -> colombiano) y, con la de certificado, el "¿lo
    # cambio?" fantasma de la ronda B2 ("listo, como pago" -> 0,03): ver
    # `conversational_core._route_contradictions`.
    AFFIRMS_CERTIFICATION: {
        "type": "noul",
        "instructions": (
            'The customer tells us whether THEY, or the people who will dive with them, already hold a '
            "diving certification. Stating a level counts ('I'm Open Water certified', 'mi esposa es "
            "Advanced'), and so does saying that someone has never dived, that they want to get certified "
            'or are buying or booking a beginner course, that they are partway through a course '
            '(e-learning, referral), or that they need a refresher. A short answer of a few words that '
            'states it counts too. It is FALSE when a course or level is only mentioned as a hypothesis '
            "('if I ever decided to get certified'), when they only ask whether something would be "
            'possible for someone, or when they ask about dives, prices or options without saying '
            "anyone's level."
        ),
    },
    AFFIRMS_GROUP: {
        "type": "noul",
        "instructions": (
            'The customer tells us HOW MANY people will take part, or who is coming: a number of people, '
            "'just me', 'my wife and I', a family, a list of names. A plan counts ('we'll probably book "
            "it for three'). It is FALSE when the numbers in the message count dives, days, nights or "
            "packages rather than people, when 'solo' means 'only' ('solo la mañana'), or when they ask "
            'about one single person without saying who is coming.'
        ),
    },
    # 27-sep (u3-5 paso 3): cuenta también la RESIDENCIA (el campo es "colombiano o residente": COP) y
    # se dice que el idioma no cuenta. Banco `nac` + 8 casos reales: 20/20 frente a 17/20 (la anterior
    # no veía "yo soy residente", "tengo extranjería" ni "vivimos en Cartagena hace 5 años").
    AFFIRMS_NATIONALITY: {
        "type": "noul",
        "instructions": (
            "The customer tells us their nationality, where they come from, or that they live in Colombia "
            "('somos de Medellín', 'I'm from Canada', 'we are Mexican', 'vivo en Bogotá', 'soy residente', 'tengo "
            "cédula de extranjería'). Saying that they are, or are not, Colombian counts, even in a few words. It is "
            "FALSE when 'Colombian' only appears in what they ask about: prices or rates for Colombians, or whether a "
            "price is in pesos or in dollars; and the language they write in does not count."
        ),
    },
}
# u3-5 paso 2 (27-sep): ¿el mensaje CAMBIA o CORRIGE un dato que el cliente ya habia dado? Es la
# señal de corrección de la regla del owner (tarea 7b: con señal explícita se acepta; sin ella, se
# confirma), que hasta ahora solo leia un regex de palabras ("perdon", "en realidad", "actually"...):
# "esperate, somos 4 al final, se sumo uno mas" o "mejor pensandolo bien quiero el minicurso" se
# preguntaban. Banco (24 correcciones de Alvaro + 3 del golden frente a 20 mensajes que no corrigen
# nada: los fantasmas y repeticiones de la ronda A del paso 3), N=2: con 0,7, 20/25 correcciones y
# 0/20 falsas (los negativos no pasan de 0,20). Por debajo del umbral se pregunta, como hoy.
CORRECTS = "corrects"
CORRECTS_MIN = 0.7
_CORRECTS_Q = {
    "type": "noul",
    "instructions": (
        "The customer CHANGES or CORRECTS something they had already told us about their booking (how many "
        "people, who does which activity, where they stay or leave from, which activity, nationality, "
        "certification): for example 'actually...', 'al final...', 'mejor...', 'cambio de plan', 'ah no...', "
        "'perdón, somos 3', 'se sumó uno más', 'my wife is coming too'. It is FALSE when they only give or repeat "
        "a detail without saying that it changes, answer a question, thank us, apologise without stating a new "
        "detail, or ask something."
    ),
}

# Paso 5 (flag `rag_v2`, 27-sep): ¿el cliente pide que le RECORDEMOS algo que él mismo dijo? El
# "¿me recuerdas…?" (`recall_field` del detector de señales) contesta con el dato guardado y
# CANCELA la respuesta del RAG; en la ronda A salió 15 veces y casi ninguna lo era ("could you just
# confirm at what time and where…?", "Hope you are operating on Easter Sunday?"). Calibrado con
# `scripts/sonda_pide_recordar.py`.
ASKS_RECALL = "asks_recall"
ASKS_RECALL_MIN = 0.5
_ASKS_RECALL_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks the assistant to REMIND them of, or repeat back, something THE CUSTOMER "
        "THEMSELVES already said in this chat about their own booking ('¿cuántas personas te dije?', "
        "'¿qué te había pedido?', 'remind me what I told you', '¿qué llevamos hasta ahora?'). It is FALSE "
        "when they ask for information about the service, prices, schedules, meeting point, policies or "
        "dates (even if they say 'confirm' or 'right?'), when they check their understanding of what WE "
        "said, or when they give new details."
    ),
}

# s4-20 (paso 6, flag `s4_fixes`, 27-sep): lo que solo puede resolver una PERSONA del equipo porque el
# bot no ve reservas, pagos ni correos, o porque es trato de empresa: una reserva o un pago YA hechos
# ("ya hice una reserva, ¿la recibieron?", "¿está todo ok con mis reservas?"), una agencia o empresa que
# coordina tarifas, o que el staff apruebe o revise algo (logs de PADI, un correo enviado). Hoy seguia
# vendiendo o preguntaba el origen. Calibrado con `scripts/sonda_necesita_persona.py`.
NEEDS_STAFF = "needs_staff"
NEEDS_STAFF_MIN = 0.7
_NEEDS_STAFF_Q = {
    "type": "noul",
    "instructions": (
        "The message is about something only a PERSON from the dive center's staff can handle, because the "
        "assistant cannot see bookings, payments or emails: a booking or payment the customer ALREADY made "
        "(checking it was received, its status, 'is everything ok with my reservations?'), a travel agency, tour "
        "operator or company writing as a business (introducing their agency, asking for rates or group deals), an email they already sent that is waiting for an answer, or "
        "asking the staff to approve or review documents (dive logs, certifications). It is FALSE for questions "
        "about how booking or paying works, prices, policies (cancellation, refunds), availability, what to "
        "bring, or when the customer is still planning or making a new booking."
    ),
}

# s4-6 (paso 6, flag `s4_fixes`): cambio de FECHA con la reserva aun en construccion. Decision del owner:
# sin reserva pagada, un cambio de fecha pasa a un asesor. La senal del router (`booking_change_topic`)
# no vale aqui: confunde "hazlo para 3 dias" o "en realidad somos 4" con reprogramar, y por eso se
# ignora mientras se arma el carrito. Esta pregunta es SOLO el dia. Calibrada con
# `scripts/sonda_cambia_fecha.py`.
CHANGES_DATE = "changes_date"
CHANGES_DATE_MIN = 0.7
_CHANGES_DATE_Q = {
    "type": "noul",
    "instructions": (
        "The customer wants to CHANGE THE DATE (the day) of their dive or booking to a different day than the "
        "one already mentioned ('mejor cambiemos la fecha', 'can we move it to Sunday instead?', 'al final no "
        "podemos el 12, ¿puede ser el 14?'). It is FALSE when they change how many days or dives, the number of "
        "people or the activity, when they just state or ask about a date for the first time, or when they ask "
        "about availability."
    ),
}

# u3-6 (paso 7, promocionado el 27-sep): ¿el mensaje mete a OTRA persona en la reserva? Filtro previo de
# `detect_special_signals`: por debajo de COMPANION_NONE_MAX (Jev seguro de que no) no se llama al
# LLM. Calibrado con `scripts/sonda_acompanante.py`.
COMPANION_JOINS = "companion_joins"
COMPANION_NONE_MAX = 0.2
_COMPANION_JOINS_Q = {
    "type": "noul",
    "instructions": (
        "The message says that ANOTHER person besides the customer is joining or taking part in the booking, "
        "or describes what other people in their group will do (a friend, partner, family member, 'somos 3 y "
        "uno hace snorkel', 'viene mi novia', 'mi amigo no está certificado', 'my wife wants to try'). It is "
        "FALSE when the customer only talks about themselves, asks a question about the service, answers "
        "with a date, place, nationality or yes/no, says thanks, or merely mentions someone who is not "
        "coming."
    ),
}

# s4-26 (7-oct, flag `jev_persona_ya_contada`): ¿el mensaje SUMA a una persona nueva al grupo, o habla de alguien que
# ya estaba? "él quiere hacer snorkel" y "también viene mi hermana que quiere snorkel" dan la misma señal de
# acompañante y el flujo preguntaba el total ("¿seguís siendo 2?", acompanante-goteo). Solo se usa el lado seguro: por
# debajo de ADDS_PERSON_NOT_MAX (Jev seguro de que NO es nueva) se mueve dentro del grupo sin preguntar; si duda, se
# pregunta como hoy. Calibrada con un banco propio y otro ciego (frases distintas): nuevas 0/20 por debajo (la mas baja
# 0,45), ya contadas 18/20 por debajo.
ADDS_PERSON = "adds_person"
ADDS_PERSON_NOT_MAX = 0.2
_ADDS_PERSON_Q = {
    "type": "noul",
    "instructions": (
        "The message ADDS a new person to the group: someone who joins or comes too and was not counted before "
        "('también viene mi hermana', 'se suma un amigo', 'my cousin is coming too', 'y otro más que hace snorkel', "
        "'add one more person'). It is FALSE when it only says what someone ALREADY in the group will do or is like, "
        "referring to them with a pronoun or a role ('él quiere hacer snorkel', 'ella no está certificada', 'he'd "
        "rather snorkel', 'mi amigo al final hará snorkel', 'el otro prefiere el minicurso'), when it gives the total "
        "('somos 3'), or when it talks only about the customer."
    ),
}

# s4-28 (8-oct, flag `jev_lugar_cliente`): ¿DÓNDE está o desde dónde sale el cliente? La regex (`place_by_role`)
# lo decide por la preposición y lee "estamos en Cartagena y queremos bucear EN las islas" como islas. La regex sigue
# PROPONIENDO que el mensaje trae una ubicación; Jev decide CUÁL cuando está seguro (>= CUSTOMER_PLACE_MIN). Banco de
# los tests de place_by_role: 9/10 (1 dudoso, ninguno mal); banco ciego de frases nuevas: 12/12 frente a 4/12 de la
# regex; 0 respuestas seguras y equivocadas (scripts/sonda_lugar_cliente.py).
CUSTOMER_PLACE = "customer_place"
CUSTOMER_PLACE_MIN = 0.6
_CUSTOMER_PLACE_Q = {
    "type": "choice",
    "instructions": (
        "Where is the customer (or their group) staying, or setting out from, for the diving trip? Only count what "
        "they say about THEMSELVES: the city or hotel they are in or will stay at, or where they leave from. The "
        "Rosario Islands are where every dive happens, so naming them as the place to DIVE, VISIT or GO TO is not "
        "where the customer is."
    ),
    "criteria": {
        "cartagena": "They are in, are staying in, or set out from Cartagena (the city or the mainland).",
        "islands": "They are staying on, or will already be on, one of the islands (Rosario Islands, Isla Grande, "
                   "Baru...) when they dive.",
        "none": "The message does not say where they are or leave from: it only names a place to dive, visit or go "
                "to, asks a question about a place, or is unclear.",
    },
}

# rag-5 (1-oct): ¿el mensaje cuenta algo del cliente que haya que APUNTAR como nota? Puerta del extractor de
# notas (`conversational_core._maybe_capture_notes`): Gonzalo midió el 30-sep que de 26 notas nuevas solo 7
# eran buenas y 15 eran la pregunta del cliente apuntada como hecho, o inventada ("how much would that be" ->
# "not Colombian"), pese a que el prompt del extractor ya lo prohíbe. Redactada con la definición del propio
# extractor (`src/prompts/memory.py`), no con los casos de la prueba ciega. Solo se salta el extractor cuando
# Jev está SEGURO de que no hay nada (p < NOTES_SKIP_MAX): ante la duda, la conducta de hoy. Calibrada con
# `scripts/sonda_notas.py`.
SHARES_OPEN_FACT = "shares_open_fact"
NOTES_SKIP_MAX = 0.2
_SHARES_OPEN_FACT_Q = {
    "type": "noul",
    "instructions": (
        "The customer tells us something about THEMSELVES or the people travelling with them that a dive advisor "
        "should remember and that is NOT a booking detail: a health or medical condition, an injury, a pregnancy, "
        "medication or an allergy; a disability or accessibility need; not knowing how to swim, or fear or "
        "nerves about the water; a diet; a special occasion (birthday, honeymoon, anniversary); a language "
        "need; or a hard limit on their budget or their schedule. It counts even if the same message also asks "
        "a question. It is FALSE when the message only asks something (prices, schedules, what is included, "
        "discounts, hotels, whether something is possible), only gives booking details (which activity, how "
        "many people, where they stay or set out from, their nationality or city, their certification or last "
        "dive, dates), mentions something only as a hypothesis, or is thanks or small talk."
    ),
}

# u3-7 (paso 7, promocionado el 27-sep): la respuesta a la pregunta PENDIENTE cuando el parser no la
# entiende ("uf, hace muchisimo", "vivo en Bogota", "ya estamos por playa blanca"). Hoy la interpreta
# el LLM (`resolve_slot_answer`); los si/no y las listas los contesta Jev en la misma llamada. Las
# CIFRAS (cuantas personas) se quedan en el LLM: contar es un punto flojo de Jev. Cascada: con
# confianza >= PENDING_ANSWER_MIN vale lo de Jev (tambien "no contesta a eso"); si no, el LLM de hoy.
# Calibrado con `scripts/sonda_respuesta_pendiente.py`.
PENDING_ANSWER = "pending_answer"
PENDING_ANSWER_MIN = 0.8
_NONE = "none"


def pending_answer_question(slot: str | None) -> dict | None:
    """La pregunta de Jev para el slot pendiente, o None si no es de si/no o de lista."""
    from src.prompts.booking import SLOT_RESOLVER_SPEC  # lazy

    spec = SLOT_RESOLVER_SPEC.get(slot or "")
    if not spec or spec["type"] == "integer":
        return None
    asked = f"The assistant just asked the customer: \"{spec['question_en']}\""
    if spec["type"] == "boolean":
        criteria = {
            "yes": f"The message answers YES. What yes means here: {spec['value_meaning']}",
            "no": f"The message answers NO. What no means here: {spec['value_meaning']}",
        }
    else:
        criteria = {opt: f"The message's answer is '{opt}'. {spec['value_meaning']}" for opt in spec["enum"]}
    criteria[_NONE] = "The message does not answer that question (it asks something else, talks about something else, or is unclear)."
    return {"type": "choice", "instructions": f"{asked} How does the customer's message answer it?", "criteria": criteria}


def pending_answer_value(slot: str, answer: dict) -> dict:
    """{"slot", "value", "confidence"}: `value` es True/False o la opcion, o None si no contesta."""
    choice = (answer or {}).get("choice")
    value = {"yes": True, "no": False}.get(choice, choice) if choice != _NONE else None
    return {"slot": slot, "value": value, "confidence": float((answer or {}).get("confidence", 0.0))}


# Las preguntas de u3-4/u3-5 no son señales del router: su duda NO manda el turno al router LLM.
_U34_QUESTIONS = (
    ASKS_QUESTION, AFFIRMS_LOCATION, AFFIRMS_ACTIVITY, ACTIVITY_HYPOTHESIS,
    AFFIRMS_CERTIFICATION, AFFIRMS_GROUP, AFFIRMS_NATIONALITY, CORRECTS, ASKS_RECALL, NEEDS_STAFF,
    CHANGES_DATE, COMPANION_JOINS, PENDING_ANSWER, SHARES_OPEN_FACT, ADDS_PERSON, CUSTOMER_PLACE,
)


def activity_affirmed(p_affirms: float, p_hypothesis: float | None) -> bool:
    """¿El cliente afirma la actividad? Jev seguro de que sí (>= 0,7), o bastante probable
    (>= 0,4) y sin pinta de hipótesis (< 0,5).

    Medido el 26-sep con las dos preguntas de arriba, N=2 (`scripts/sonda_afirma_vs_pregunta.py`
    y 57 mensajes del golden fuera del banco): banco 12/12; fuera del banco 52/57 (tira 1
    dato bueno, deja 4 dudosos que el regex ya fijaba con el flag apagado), frente a 34/57 de
    la redacción anterior sola. Las 4 reglas probadas: solo la afirmativa >= 0,7 (48/57), solo
    la de hipótesis < 0,7 (48/57, pero deja 9 inventados), esta (52/57) y afirmativa >= 0,5 con
    hipótesis < 0,7 (50/57). Ojo: la regla se eligió mirando esos 57, así que ya no son
    una prueba ciega; la prueba ciega es el replay del golden."""
    if p_affirms >= AFFIRMS_MIN:
        return True
    if p_hypothesis is None:
        return False
    return p_affirms >= 0.4 and p_hypothesis < 0.5


def _questions_for_turn(pending_slot: str | None = None) -> dict:
    q = dict(_QUESTIONS)
    pending_q = pending_answer_question(pending_slot)
    if pending_q:
        q[PENDING_ANSWER] = pending_q
    if settings.answer_and_continue:
        q.update({ASKS_QUESTION: _ASKS_QUESTION_Q, **_AFFIRMS_QUESTIONS})
    if settings.corrections_v2:
        q[CORRECTS] = _CORRECTS_Q
    if settings.rag_v2:
        q[ASKS_RECALL] = _ASKS_RECALL_Q
    if settings.s4_fixes:
        q[NEEDS_STAFF] = _NEEDS_STAFF_Q
        q[CHANGES_DATE] = _CHANGES_DATE_Q
    q[COMPANION_JOINS] = _COMPANION_JOINS_Q
    if settings.jev_persona_ya_contada:
        q[ADDS_PERSON] = _ADDS_PERSON_Q
    if settings.jev_lugar_cliente:
        q[CUSTOMER_PLACE] = _CUSTOMER_PLACE_Q
    if settings.notas_puerta_jev:
        q[SHARES_OPEN_FACT] = _SHARES_OPEN_FACT_Q
    return q


# Cascada por confianza (A/B del 24-sep): Jev decide solo cuando está seguro; si duda,
# el turno lo decide el router LLM, o sea la conducta de hoy. En el A/B la única
# regresión de Jev ("the discount of 10% is not showing up" -> escalado por
# "real_time_issues") tenía confianza 0,38, frente a 0,92-1,00 de los problemas de pago
# reales. Umbrales fijados ANTES de medir; en los 257 mensajes del golden (sin examen
# oculto) solo el 8 % de los turnos cae en la zona de duda.
CHOICE_MIN_CONFIDENCE = 0.6
NOUL_DOUBT_ZONE = (0.3, 0.7)


def uncertain_answers(answers: dict) -> list[str]:
    """Respuestas de Jev en las que duda (las opciones de comparación no cuentan: solo
    importan si ya está comparando, y eso lo decide `comparing`)."""
    doubts = []
    for name, a in answers.items():
        # Las preguntas de u3-4 no son señales del router: su duda no manda el turno al LLM.
        if name.startswith("opt_") or name in _U34_QUESTIONS or not isinstance(a, dict):
            continue
        if a.get("type") == "choice" and a.get("confidence", 1.0) < CHOICE_MIN_CONFIDENCE:
            doubts.append(f"{name}={a.get('choice')}@{a.get('confidence', 0):.2f}")
        elif a.get("type") == "noul" and NOUL_DOUBT_ZONE[0] < a.get("noul", 0.0) < NOUL_DOUBT_ZONE[1]:
            doubts.append(f"{name}@{a['noul']:.2f}")
    return doubts


def answers_to_signals(answers: dict, threshold: float = THRESHOLD) -> dict:
    """Respuestas de Jev -> el mismo dict que devuelve el router LLM (solo lo marcado)."""
    out: dict = {}
    for name in _BOOLEAN_SIGNALS:
        if (answers.get(name) or {}).get("noul", 0.0) >= threshold:
            out[name] = True
    for name in ("sensitive_topic", "booking_change_topic"):
        choice = (answers.get(name) or {}).get("choice")
        if choice and choice != "none":
            out[name] = choice
    # u3-4: estas dos se emiten también en FALSE, a propósito. "ausente" (Jev apagado, o
    # dudó en el router y el turno se fue al LLM) significa "no lo sé" -> conducta de hoy;
    # `False` significa "Jev dice que el cliente NO lo afirma" -> el dato se cae. Son
    # distintos y el llamante (`_question_turn_fields`) necesita distinguirlos.
    if CORRECTS in answers:
        out[CORRECTS] = (answers.get(CORRECTS) or {}).get("noul", 0.0) >= CORRECTS_MIN
    if ASKS_RECALL in answers:
        out[ASKS_RECALL] = (answers.get(ASKS_RECALL) or {}).get("noul", 0.0) >= ASKS_RECALL_MIN
    if NEEDS_STAFF in answers:
        out[NEEDS_STAFF] = (answers.get(NEEDS_STAFF) or {}).get("noul", 0.0) >= NEEDS_STAFF_MIN
    if COMPANION_JOINS in answers:
        # Se emite la PROBABILIDAD: el filtro solo actua cuando Jev esta seguro de que NO.
        out[COMPANION_JOINS] = (answers.get(COMPANION_JOINS) or {}).get("noul", 1.0)
    if CUSTOMER_PLACE in answers:
        a = answers.get(CUSTOMER_PLACE) or {}
        out[CUSTOMER_PLACE] = {"choice": a.get("choice"), "confidence": float(a.get("confidence", 0.0))}
    if ADDS_PERSON in answers:
        # Ausente o sin respuesta = 1.0 ("puede ser nueva"): se pregunta el total, como hoy.
        out[ADDS_PERSON] = (answers.get(ADDS_PERSON) or {}).get("noul", 1.0)
    if SHARES_OPEN_FACT in answers:
        out[SHARES_OPEN_FACT] = (answers.get(SHARES_OPEN_FACT) or {}).get("noul", 1.0)
    if CHANGES_DATE in answers:
        out[CHANGES_DATE] = (answers.get(CHANGES_DATE) or {}).get("noul", 0.0) >= CHANGES_DATE_MIN
    for name in (AFFIRMS_LOCATION, AFFIRMS_CERTIFICATION, AFFIRMS_GROUP, AFFIRMS_NATIONALITY):
        if name in answers:
            out[name] = (answers.get(name) or {}).get("noul", 0.0) >= AFFIRMS_MIN
    if AFFIRMS_ACTIVITY in answers:
        hyp = answers.get(ACTIVITY_HYPOTHESIS)
        out[AFFIRMS_ACTIVITY] = activity_affirmed(
            (answers.get(AFFIRMS_ACTIVITY) or {}).get("noul", 0.0),
            (hyp or {}).get("noul") if hyp else None,
        )
    if (answers.get("comparing") or {}).get("noul", 0.0) >= threshold:
        opts = [
            n[4:] for n, a in answers.items()
            if n.startswith("opt_") and (a or {}).get("noul", 0.0) >= threshold
        ]
        out["comparing_options"] = {"comparing": True, "options": opts}
    return out


_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    # Un cliente compartido reutiliza la conexión TLS: abrir una por turno sumaría
    # ~100-200 ms a una llamada que tarda ~270 ms.
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient()
    return _client


UNCERTAIN = "uncertain"  # Jev respondió pero duda: el turno lo decide el router LLM


async def detect_routing_signals_jev(message: str, *, lang: str = "es") -> dict | str | None:
    """Las 9 señales con Jev.

    Devuelve el dict de señales si Jev está seguro, `UNCERTAIN` si duda en alguna
    (cascada: decide el router LLM) y `None` si no está disponible o falla."""
    result, _ = await detect_routing_signals_jev_full(message, lang=lang)
    return result


# Señales de u3-4/u3-5 que NO son del router: viajan aparte (ver `detect_routing_signals_jev_full`).
_TURN_SIGNALS = (
    AFFIRMS_LOCATION, AFFIRMS_ACTIVITY, AFFIRMS_CERTIFICATION, AFFIRMS_GROUP, AFFIRMS_NATIONALITY, CORRECTS,
    ASKS_RECALL, NEEDS_STAFF, CHANGES_DATE, COMPANION_JOINS, SHARES_OPEN_FACT,
)  # AFFIRMS_P y PENDING_ANSWER se anaden a mano en `detect_routing_signals_jev_full`


async def detect_routing_signals_jev_full(
    message: str, *, lang: str = "es", pending_slot: str | None = None,
) -> tuple[dict | str | None, dict]:
    """Como `detect_routing_signals_jev`, y además las señales de u3-4/u3-5 (solo con
    `answer_and_continue`): `asks_question` y los `affirms_*`. Van en el segundo valor
    porque valen también cuando Jev DUDA en las señales del router: son otras preguntas
    y el router LLM no las contesta.

    Hasta el 26-sep solo viajaba `asks_question`; los `affirms_*` se perdían en el ~8 %
    de turnos en que Jev duda en el router, y el turno caía a la conducta de hoy sin
    necesidad (el "Yo soy open y me gustaría salir un día…" de la ronda B2 perdió la
    actividad así en el replay del 26-sep, pese a que Jev la afirmaba a 0,93)."""
    key = settings.openrouter_api_key
    if not key or not message or not message.strip():
        return None, {}
    t0 = time.perf_counter()
    try:
        resp = await _http().post(
            JEV_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": settings.jev_model,
                "state": f"{_CONTEXT}\n\nCustomer message: {message}",
                "questions": _questions_for_turn(pending_slot),
            },
            timeout=settings.jev_timeout_seconds,
        )
        resp.raise_for_status()
        answers = resp.json()["answers"]
        signals = answers_to_signals(answers)
        doubts = uncertain_answers(answers)
        extras = {k: signals[k] for k in _TURN_SIGNALS if k in signals}
        if ASKS_QUESTION in answers:
            # Tambien en FALSE (27-sep): "Jev dice que no pregunta nada" es distinto de "no lo sabemos"
            # y lo necesita la respuesta corta tras el pase a una persona (paso 6). Para el resto del
            # codigo False y ausente se leen igual.
            extras[ASKS_QUESTION] = (answers.get(ASKS_QUESTION) or {}).get("noul", 0.0) >= ASKS_QUESTION_MIN
        # u3-3: la probabilidad cruda de cada `affirms_*` (el boolean de arriba corta en 0,7, pensado
        # para turnos con pregunta; en frases normales Jev da falsos "no" entre 0,3 y 0,7).
        affirms_p = {
            name: (answers.get(name) or {}).get("noul", 0.0)
            for name in (AFFIRMS_LOCATION, AFFIRMS_ACTIVITY, AFFIRMS_CERTIFICATION, AFFIRMS_GROUP, AFFIRMS_NATIONALITY)
            if name in answers
        }
        if affirms_p:
            extras[AFFIRMS_P] = affirms_p
        if pending_slot and PENDING_ANSWER in answers:
            extras[PENDING_ANSWER] = pending_answer_value(pending_slot, answers[PENDING_ANSWER])
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cae al router LLM
        ms = (time.perf_counter() - t0) * 1000
        logger.warning(f"[ROUTER][JEV] fallo en {ms:.0f} ms, se usa el router LLM: {type(exc).__name__}: {exc}")
        return None, {}
    ms = (time.perf_counter() - t0) * 1000
    if doubts:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms duda={doubts} -> router LLM (se conservan {sorted(extras)}) msg={message[:80]!r}")
        return UNCERTAIN, extras
    if signals:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms detected={signals} msg={message[:80]!r}")
    return signals, extras
