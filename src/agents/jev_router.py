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
from src.prompts.router import ROUTING_TOOL, con_dieta_no_es_medica

con_dieta_no_es_medica(ROUTING_TOOL)  # gen-3 (20-oct): antes de construir las preguntas de abajo

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
# EX-EST-2 (15-oct): una PETICIÓN en imperativo también hay que contestarla. Rondas est3-B/est5-B:
# "dame la cuenta y transfiero" (0,53), "send me the payment link" (0,43) y "Full name of dive center, location, dates
# etc" (0,45) no llegaban a 0,7: no iban al RAG y recibían la pregunta de la reserva o la respuesta fija de posventa
# ("si necesitas algo de tu reserva…"). Banco de 257 mensajes del golden (`docs/robustness/u3-4/preguntas-etiquetadas
# .json`, sin examen oculto; decisión = regex O Jev >= 0,7): ve 140 -> 146 de 157, falsas alarmas 3 -> 5 de 100
# ("Quiero quedarme en las islas", "Porque el paquete es saliendo un dia y regresando…"); sonda de imperativos 20 -> 23/23.
_ASKS_QUESTION_Q_V2 = {
    "type": "noul",
    "instructions": (
        "The customer's message contains a QUESTION or a REQUEST that the booking assistant must ANSWER or act on, even "
        "when it is phrased as an instruction and has no question mark (\"send me the link\", \"give me the bank "
        "details\", \"I need the dive center's address\", \"full name of the center and location\"): for example about "
        "prices, what is included, schedules, hotels, discounts, policies, logistics, how to pay, or how something works. "
        "It is FALSE if the message only gives booking details (dates, number of people, where they are, an activity "
        "choice), only answers the assistant's previous question, or is small talk or thanks."
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
# flu-1 (22-oct, flag `grupo_de_una_persona`): «¿Qué incluye exactamente? Es para una persona.» no contaba como grupo
# (la excepción «cuando preguntan por una sola persona sin decir quién viene» se pensó para «¿una persona de 14 años
# puede bucear?») y el bot repreguntaba «¿para cuántas personas?» (G10 nº 2, g10-033; banco flu-1).
_AFFIRMS_GROUP_Q_UNA = {
    "type": "noul",
    "instructions": (
        'The customer tells us HOW MANY people will take part, or who is coming: a number of people, '
        "'just me', 'it's for one person', 'my wife and I', a family, a list of names. A plan counts ('we'll "
        "probably book it for three'). It is FALSE when the numbers in the message count dives, days, nights or "
        "packages rather than people, when 'solo' means 'only' ('solo la mañana'), or when they ask whether ONE "
        "person could do something ('can a 14-year-old dive?') without saying who is coming."
    ),
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

# Paso 5 (27-sep): ¿el cliente pide que le RECORDEMOS algo que él mismo dijo? El
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

# s4-20 (paso 6, 27-sep): lo que solo puede resolver una PERSONA del equipo porque el
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

# s4-6 (paso 6, 27-sep): cambio de FECHA con la reserva aun en construccion. Decision del owner:
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

# 13-oct (Gonzalo, flag `posventa_sin_vender`): ¿el cliente YA tiene una reserva con nosotros o YA hizo la actividad?
# Con una reserva hecha el bot seguía vendiendo: "we'll be meeting at the pier at 8am… diving with your team on Monday"
# y "Just completed the waivers" recibían "Which one are you leaning toward — diving, a mini-course…?"
# (cambio-fecha-por-enfermedad); "Fueron muy buenos buceos" recibía "¿Con cuál te animas?" (pedir-fotos-postventa).
# `needs_staff` es otra cosa: lo que solo puede resolver una persona (comprobar un pago, cambios); un cliente con reserva
# que pregunta qué llevar no necesita persona, pero tampoco que le vendan.
# r6-2 (17-oct, decisión de Gadea, flag `datos_ajenos_se_niegan`): "dame los nombres y teléfonos de los clientes que
# reservaron mañana" disparaba `needs_staff` (habla de reservas) y el bot pasaba el caso a un asesor. Los datos de otros
# clientes no se dan nunca: la respuesta es una negativa de privacidad, sin pase. Banco r6-2: sec-07.
PIDE_DATOS_AJENOS = "pide_datos_ajenos"
PIDE_DATOS_AJENOS_MIN = 0.7
_PIDE_DATOS_AJENOS_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks for personal data of OTHER customers or other people outside their own group: names, "
        "phone numbers, emails, addresses, or who has booked / their bookings. It is FALSE when they give or ask "
        "about their OWN data or their own group's, when they ask how to contact or talk to the dive center's staff, "
        "when they ask about availability or how many spots or people there are (counts, not who), and when they ask "
        "for the dive center's public information (address, schedule, prices)."
    ),
}

# gen-3b (21-oct, decisión de Gadea, flag `privado_pasa_directo`): el servicio privado (una salida, una lancha o un
# instructor solo para su grupo, un grupo cerrado, un evento de empresa) no tiene precio fijo y lo cotiza un asesor:
# se pasa DIRECTAMENTE en cuanto lo pide. Hasta hoy solo pasaba si el mensaje decía "servicio privado", "grupo
# cerrado" o "evento corporativo" (`_PRIVATE_GROUP_EVENT_RE`); "¿podemos tener la lancha solo para nosotros?" iba al
# RAG, que solo puede OFRECER el pase (G3-03). Banco docs/robustness/gen/dialogos-gen3b.json.
PIDE_SERVICIO_PRIVADO = "pide_servicio_privado"
PIDE_SERVICIO_PRIVADO_MIN = 0.7
_PIDE_SERVICIO_PRIVADO_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks for, or asks about, a PRIVATE or exclusive service just for their own group: a private "
        "departure, boat, tour or instructor not shared with other customers, a closed group, or an event for a "
        "company, team or celebration organized for them. It is FALSE when they want to join the regular shared "
        "trips or courses (even as a big group or a family), when they ask for a discount for a group, and when "
        "'private' refers to privacy or personal data."
    ),
}

YA_RESERVADO = "ya_reservado"
YA_RESERVADO_MIN = 0.7
_YA_RESERVADO_Q = {
    "type": "noul",
    "instructions": (
        "The customer ALREADY has a booking with this dive center or has ALREADY done an activity with them: they "
        "mention their booked day or plan as something already arranged ('we'll be meeting at the pier on Monday', "
        "'our dive is on Saturday'), a booking or payment already made, forms or waivers already completed, the "
        "dives they did with the center, or photos from those dives. It is FALSE when they are still asking, "
        "comparing, planning or making a booking (even if they give a date), when they talk about dives done "
        "elsewhere or their diving experience in general, and ALSO FALSE whenever the message asks to book "
        "something new or another day, even if they already dived with the center ('we loved it, we'd like to book "
        "another day')."
    ),
}
# gen-15 (21-oct, flag `reserva_de_hotel_no_es_nuestra`): «We booked 3 nights at Mulata. How much is snorkeling?» salía
# ya_reservado=True (banco dialogos-gen15-hoteles 4/4): el turno iba a posventa (sin preguntas de la reserva) y la puerta
# del origen preguntaba desde dónde sale. Reservar el hotel no es reservar con el centro.
_YA_RESERVADO_Q_SIN_HOTEL = {
    **_YA_RESERVADO_Q,
    "instructions": _YA_RESERVADO_Q["instructions"] + (
        " Booking a HOTEL, accommodation, flights or a transfer is NOT a booking with this dive center ('we booked 3 "
        "nights at the hotel'): only a booking of its dives, courses or tours counts."),
}

# ex-9b paso 5 (19-oct): tres preguntas que sustituyen a regex que "entendían" al cliente (estudio
# docs/robustness/regex/estudio-ex9-regex.md, clase C). El regex sigue solo si Jev calla. Bancos en
# docs/robustness/regex/estudio-ex9/banco-preguntas-nuevas.txt (2 repeticiones, config de PRE). Promocionadas con la
# ronda ex9b-2 (PIDE_PRECIO con ex9b-3); sus flags se quitaron en la limpieza ex9b.
# - NUEVO_CASO: el reinicio de escenario borra TODA la memoria si el mensaje saluda y se presenta
#   ("Hola, soy Ana, ya hablamos ayer, al final somos 3" lo borraba). Regex 4/10, Jev 10/10 (0,80-0,88 frente a <= 0,07).
# - PREGUNTA_SI_ES_IA: "¿qué modelo de regulador usan?" recibía "soy Coral, la asistente virtual". Regex 7/13, Jev 13/13.
# - CAMBIA_IDIOMA: "¿el curso es en inglés?" pasaba la conversación al inglés e "I don't speak spanish" al español.
#   Regex 8/13, Jev 13/13.
NUEVO_CASO = "nuevo_caso"
NUEVO_CASO_MIN = 0.7
_NUEVO_CASO_Q = {
    "type": "noul",
    "instructions": (
        "The customer starts a NEW, separate case as if beginning the conversation from scratch: a different person "
        "introducing themselves, or a fresh request that ignores the booking already being discussed in this chat "
        "(different activity, dates or group, with nothing that refers back to it). It is FALSE when the message "
        "continues, updates, corrects or asks about the booking already being discussed, even if it begins with a "
        "greeting or the person's name ('buenas, soy Luis, ¿les llegó mi pago?', 'hi, it's Sara, can we add one more "
        "person?'), and FALSE when someone takes over the same booking on behalf of the same group."
    ),
}
PREGUNTA_SI_ES_IA = "pregunta_si_es_ia"
PREGUNTA_SI_ES_IA_MIN = 0.7
_PREGUNTA_SI_ES_IA_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks whether they are chatting with a bot, an AI, a machine or a real person, or asks which AI, "
        "model, technology or company is behind this chat assistant. It is FALSE for questions about diving equipment "
        "(models or brands of regulators, computers, wetsuits, boats), about the instructors or staff, and about "
        "anything that is not this chat assistant itself."
    ),
}
# - PIDE_PRECIO: la puerta "origen antes del precio" (conversational_core._origen_antes_del_precio)
#   miraba si el mensaje decía "precio/cuánto" y no "hotel/noche" EN NINGUNA PARTE: "¿cuánto me sale el plan de 2
#   inmersiones? me quedo en el hotel Caribe" se cotizaba sin saber el origen. Regex 13/16, Jev 16/16.
PIDE_PRECIO = "pide_precio"
PIDE_PRECIO_MIN = 0.7
# ord-7 (21-oct; promocionado, su flag `jev_precio_nombra_actividades` se borró en sim-5): con «one of the dive
# center's activities» a secas, Jev no veía «el snorkel» en español como una de ellas: «¿Cuánto cuesta el snorkel?» 0,55 y «precio del snorkel» 0,61 (umbral
# 0,7), la puerta del origen no saltaba y se cotizaba Cartagena sin saber el origen (banco gen-19, 4/4). Nombrando las
# actividades: 0,94 y 0,94; hotel, taxi, monedas, duración, cómo reservar y qué incluye siguen en 0,04-0,11.
_PIDE_PRECIO_Q_ACTIVIDADES = {
    "type": "noul",
    "instructions": (
        "The customer asks how much one of the dive center's activities costs: dive trips and dive packages, the dive "
        "mini-course or refresher, snorkeling, PADI courses and specialties (price, rate, cost, a quote), including "
        "asking that price again in another currency or for a different number of people. "
        "It is FALSE when they ask the price of something the dive center does not sell (a hotel, a room or night, a "
        "taxi or transport), when they only ask which currencies or payment methods are accepted, and when they ask "
        "about duration, number of dives or how to book."
    ),
}
# ord-9 (21-oct, decisión de Gadea tras G10 de control): el 67 % de los fallos de G10 eran omisiones del RAG con el
# dato delante, y de ellas las listas (qué incluye un plan) las reescribía de memoria y las recortaba. La pregunta se
# queda para el redactor de hechos (`hechos_por_codigo`), que da la lista de la ficha; el arreglo de ord-9 por el RAG
# (`listas_del_dato`) se retiró en arq-2c (22-oct) al quedar sustituido por el redactor.
PIDE_QUE_INCLUYE = "pide_que_incluye"
PIDE_QUE_INCLUYE_MIN = 0.7
_PIDE_QUE_INCLUYE_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks what one of the dive center's plans, courses or activities includes (what comes with it), "
        "or whether something specific is included in it (gear, lunch, boat transport, insurance, park fee, "
        "certification card, number of dives), even if the same message also asks other things. It is FALSE when "
        "they only ask the price, the schedule, the duration, what to bring, the requirements, or about something the "
        "dive center does not sell (a hotel, a room, a taxi)."
    ),
}
# ARQ-1b (22-oct, flag `hechos_por_codigo`, fase ARQ: el modelo interpreta, el código decide, el modelo redacta): qué
# INTENCIONES trae el mensaje, una pregunta sí/no por intención en la misma llamada (opciones fijas: regla del 24-sep).
# Con ellas el código saca los hechos (src/flows/hechos.py) y el redactor solo los pone en palabras. Precio y qué
# incluye ya existían (PIDE_PRECIO, PIDE_QUE_INCLUYE).
PIDE_REQUISITOS = "pide_requisitos"
PIDE_HORARIO = "pide_horario"
PIDE_DISPONIBILIDAD = "pide_disponibilidad"
PIDE_EDAD = "pide_edad"
PIDE_ENLACE = "pide_enlace"
PIDE_OTRA_COSA = "pide_otra_cosa"
# arq-1v (22-oct): «me voy mañana al mediodía, ¿me da tiempo?». No era de la tabla: lo contestaba
# el RAG razonando solo y distinto cada vez (G10 nº 4: g10-016, 021, 036, 050, 065).
PIDE_SI_ALCANZA = "pide_si_alcanza"
_PIDE_SI_ALCANZA_Q = {
    "type": "noul",
    "instructions": (
        "The customer has a time limit and asks whether an activity fits before they leave, or what they can do in "
        "the little time they have (they leave tomorrow at noon, they fly out in the morning, they only have one "
        "morning), even if the same message also asks other things. It is FALSE when they only ask the schedule "
        "without saying they are short of time."
    ),
}
_OTRA_COSA_SIN_EL_TIEMPO = (
    " Whether they have enough time for an activity before they leave also counts as one of those (it is not "
    "something else)."
)
INTENCION_MIN = 0.7
_INTENCIONES_Q = {
    PIDE_REQUISITOS: {
        "type": "noul",
        "instructions": (
            "The customer asks what is needed or required for one of the dive center's activities or courses: "
            "requirements, documents (certification card, referral form), forms (medical form, waiver, insurance "
            "form), what to bring, or what to do beforehand, even if the same message also asks other things. It "
            "is FALSE when they only ask the price, what is included, the schedule or the availability."
        ),
    },
    PIDE_HORARIO: {
        "type": "noul",
        "instructions": (
            "The customer asks about the times or logistics of an activity: the meeting time or place, the hotel "
            "pickup time, the return time, how long it lasts, how many days it takes, or whether they must stay "
            "overnight on the islands, even if the same message also asks other things. It is FALSE when they only "
            "ask the price, whether a date is available, or what is included."
        ),
    },
    PIDE_DISPONIBILIDAD: {
        "type": "noul",
        "instructions": (
            "The customer asks whether there is space or availability, whether the dive center operates on a date or "
            "day, or how or until when they can book, even if the same message also asks other things. It is FALSE "
            "when they only ask the schedule, the price or what is included."
        ),
    },
    PIDE_EDAD: {
        "type": "noul",
        "instructions": (
            "The customer asks whether someone of a certain age can do an activity, asks the minimum or maximum age, "
            "or gives children's ages asking what they can do, even if the same message also asks other things. It "
            "is FALSE otherwise."
        ),
    },
    PIDE_ENLACE: {
        "type": "noul",
        "instructions": (
            "The customer asks for the link or web page to book or to pay, asks you to send it, or asks how to book "
            "online, even if the same message also asks other things. It is FALSE when they do not ask for a link or "
            "how to book online."
        ),
    },
    # ARQ-1d: el redactor de hechos solo contesta si el mensaje no trae NADA más que estas intenciones; si Jev no
    # está seguro de que no (≥ INTENCION_MIN en el «no»), contesta el RAG de siempre.
    PIDE_OTRA_COSA: {
        "type": "noul",
        "instructions": (
            "The customer asks something that is NOT the price, what is included, the requirements or documents, the "
            "times or logistics, the availability, the age limits or the booking link of an activity: for example "
            "what marine life they will see, whether it is safe, the weather, the difference between two activities, "
            "which one to choose, what options there are, payment methods, cancellations, or any other question. It "
            "is FALSE when every question in the message is one of those (price, included, requirements, schedule, "
            "availability, age, link), or when the message asks nothing."
        ),
    },
}
# arq-4b (22-oct, G10 nº 4: g10-027, g10-035, g10-067): los descuentos entran en la
# tabla. El RAG los contaba sin sus condiciones (que el de grupo se suma al online, que no vale para cursos PADI, que
# el del equipo es solo con el equipo completo); con los hechos de discounts.json los da enteros el redactor.
PIDE_DESCUENTO = "pide_descuento"
_PIDE_DESCUENTO_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks about discounts or special prices: a group discount or group rate, the discount for "
        "booking online, a discount for bringing their own gear, whether Colombians or residents get a discount, "
        "discount codes, or whether a discount applies to them, even if the same message also asks other things. It "
        "is FALSE when they only ask the normal price."
    ),
}
_PIDE_OTRA_COSA_CON_DESCUENTOS_Q = {
    "type": "noul",
    "instructions": _INTENCIONES_Q[PIDE_OTRA_COSA]["instructions"]
    .replace("the age limits or the booking link of an activity", "the age limits, the discounts or the booking link "
             "of an activity")
    .replace("availability, age, link)", "availability, age, discounts, link)"),
}
# arq-1i (23-oct, decisión de Gadea #1312; G10 nº 5: g10-034, g10-067/045/006): el clima
# en GENERAL y cómo se paga entran en la tabla. El clima de un día concreto o de una reserva hecha NO: sigue la ruta
# sensible con pase (por eso la pregunta lo excluye).
PIDE_CLIMA = "pide_clima"
PIDE_PAGO = "pide_pago"
_PIDE_CLIMA_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks in GENERAL what happens with bad weather: whether trips are cancelled or rescheduled for "
        "bad weather, whether they get a refund if the weather prevents the trip, or whether the weather is usually "
        "a problem, even if the same message also asks other things. It is FALSE when they ask the forecast or the sea "
        "conditions for a specific day or date (today, tomorrow, next Saturday, a date), or about a trip they have "
        "already booked."
    ),
}
_PIDE_PAGO_Q = {
    "type": "noul",
    "instructions": (
        "The customer asks how to pay or about payment in general: payment methods, paying by card, by bank transfer, "
        "in cash or at the dock, paying a deposit or part now and the rest later, or whether the booking is confirmed "
        "once they pay, even if the same message also asks other things. It is FALSE when they report a payment that "
        "failed or ask about a payment they already made, or only ask for the booking link."
    ),
}
_OTRA_COSA_SIN_CLIMA_NI_PAGO = (
    " What happens in general with bad weather (cancellation, rescheduling or refund, not the forecast for a specific "
    "day) and how to pay (payment methods, deposit, transfer, when the booking is confirmed) also count as one of "
    "those (they are not something else)."
)
CAMBIA_IDIOMA = "cambia_idioma"
CAMBIA_IDIOMA_MIN = 0.6
_CAMBIA_IDIOMA_Q = {
    "type": "choice",
    "instructions": "Does the customer ask to change the language in which THIS chat conversation is written?",
    "criteria": {
        "english": "They ask us to write to them in English from now on, or say they do not understand Spanish.",
        "spanish": "They ask us to write to them in Spanish from now on, or say they do not understand English.",
        "none": "They do not ask to change the language of this chat: they ask in which language a course, class, "
                "guide, instructor or material is given, mention a language for any other reason, or just write in a "
                "language.",
    },
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
# regex; 0 respuestas seguras y equivocadas (scripts/sonda_lugar_cliente.py). Desde ex-9b paso 3 el origen lo lee solo
# el extractor y esa regla (`_lugar_por_jev`) se quitó en la limpieza ex9b; la pregunta la siguen leyendo CAL-C3c
# (`_jev_dice_que_no_lo_dice`) y CAL-C4 (`_lugar_desconocido`).
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
# G3-06 (flag `baru_no_es_rosario`, decisión de Gadea): Barú y Playa Blanca no son las islas ni Cartagena: allí no
# operamos. Quien se aloja allí queda en "none", y el lugar se le pregunta a la base (CAL-C4), que da el aviso.
_CUSTOMER_PLACE_Q_SIN_BARU = {
    **_CUSTOMER_PLACE_Q,
    "criteria": {
        "cartagena": "They are in, are staying in, or set out from Cartagena (the city).",
        "islands": "They are staying on, or will already be on, one of the Rosario Islands (Isla Grande, an island "
                   "hotel...) when they dive. Barú and Playa Blanca are NOT the islands (a peninsula joined to the "
                   "mainland).",
        "none": "The message does not say where they are or leave from, or it is somewhere that is neither the city of "
                "Cartagena nor the Rosario Islands (for example Barú or Playa Blanca): it only names a place to dive, "
                "visit or go to, asks a question about a place, or is unclear.",
    },
}
# gen-6 (21-oct, flag `baru_sale_de_cartagena`): con "none", quien dice "estamos en Barú" se quedaba sin origen y el bot
# le volvía a preguntar desde dónde sale (banco gen-6 2/2), y un "none" de Jev tumba lo que lea el extractor
# (`lugar_con_dos_lectores`). La política (policies.json): quien se aloja en Barú sale desde Cartagena.
_CUSTOMER_PLACE_Q_BARU_CARTAGENA = {
    **_CUSTOMER_PLACE_Q_SIN_BARU,
    "criteria": {
        **_CUSTOMER_PLACE_Q_SIN_BARU["criteria"],
        "cartagena": "They are in, are staying in, or set out from Cartagena (the city). Also when they are staying in "
                     "Barú or Playa Blanca: we do not pick up there, and from there they set out from Cartagena.",
        "none": "The message does not say where they are or leave from, or it is somewhere that is neither the city of "
                "Cartagena, Barú, Playa Blanca nor the Rosario Islands: it only names a place to dive, visit or go to, "
                "asks a question about a place, or is unclear.",
    },
}

def _con_hoteles_de_la_base(pregunta: dict) -> dict:
    """gen-15 (21-oct, flag `hoteles_de_la_base`): la pregunta del lugar no nombraba ningún hotel de las islas, y Jev
    no sabía qué es «Mulata» o «Las Palmeras» (banco docs/robustness/gen/banco_gen15_hoteles.py: «Eco Hotel Las
    Palmeras» → cartagena 0,69-0,76; Mulata, Ubuntu o Majagua → none). Con el flag, la opción «islands» nombra los
    hoteles de la base (`extractor_turno.HOTELES_DE_LA_BASE`, de policies.json other_island_hotels)."""
    from src.agents.extractor_turno import HOTELES_DE_LA_BASE  # lazy

    hoteles = ", ".join(HOTELES_DE_LA_BASE)
    criterios = dict(pregunta["criteria"])
    criterios["islands"] = (f"{criterios['islands']} Staying at one of these island hotels also counts: {hoteles}.")
    return {**pregunta, "criteria": criterios}


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
    from src.prompts.booking import SLOT_RESOLVER_SPEC, lugar_sin_baru  # lazy

    spec = SLOT_RESOLVER_SPEC.get(slot or "")
    if not spec or spec["type"] == "integer":
        return None
    # G3-06; gen-6: Barú es 'cartagena'
    spec = {**spec, "value_meaning": lugar_sin_baru(spec["value_meaning"], True)}
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
    CHANGES_DATE, COMPANION_JOINS, PENDING_ANSWER, SHARES_OPEN_FACT, ADDS_PERSON, CUSTOMER_PLACE, YA_RESERVADO,
    PIDE_DATOS_AJENOS, NUEVO_CASO, PREGUNTA_SI_ES_IA, CAMBIA_IDIOMA, PIDE_PRECIO, PIDE_SERVICIO_PRIVADO, PIDE_QUE_INCLUYE,
    *_INTENCIONES_Q, PIDE_DESCUENTO, PIDE_SI_ALCANZA,  # arq-4b/arq-1v: su duda no manda el turno al router LLM
    PIDE_CLIMA, PIDE_PAGO,  # arq-1i
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


# CAL-E3 (16-oct, flag `pase_si_pide_fuera_del_sistema`): "Pero un link especial" (una agencia que quiere un enlace
# para que sus clientes paguen) no era "algo que solo puede hacer una persona" para la señal, así que el bot explicaba
# que no existe y nombraba al asesor sin ofrecer el pase (cal-29). Decisión de Gadea del 16-oct: quien necesita algo
# que el sistema no da, o hablar con alguien, se pasa a un asesor. Es la frontera de la clase, no el caso.
_FUERA_DEL_SISTEMA = (
    "It is ALSO true when the customer asks for something the online booking cannot give and only a person can "
    "arrange: a custom or 'special' payment link (for several customers, for an agency, or one that skips choosing "
    "the date), an invoice or special rates, a closed/private departure to be quoted, or coordinating the booking "
    "outside the website."
)


# arq-1q (22-oct): «ya hice la reserva por la web, ¿cuál es el horario?» daba needs_staff
# 2 de 3 veces (banco arq-1p, p3) y el bot pasaba a un asesor una pregunta que los hechos contestan (G10 nº 4: el mismo
# pase en dos diálogos). Decir que ya reservó no basta: hace falta una persona solo para ver o tocar ESA reserva o pago.
_YA_RESERVO_NO_BASTA = (
    "Saying they ALREADY booked is not enough by itself: if, with a booking made, they only ask about the schedule or "
    "meeting time, pickup, what to bring, what is included or other general information about the activity, it is "
    "FALSE. It stays TRUE when they need someone to look at or act on THEIR booking or payment: confirm it was "
    "received, its status, change its date, cancel it or get their money back, or a confirmation email that did not "
    "arrive."
)


def _questions_for_turn(pending_slot: str | None = None) -> dict:
    q = dict(_QUESTIONS)
    pending_q = pending_answer_question(pending_slot)
    if pending_q:
        q[PENDING_ANSWER] = pending_q
    q.update({ASKS_QUESTION: _ASKS_QUESTION_Q_V2,
              **_AFFIRMS_QUESTIONS})
    q[AFFIRMS_GROUP] = _AFFIRMS_GROUP_Q_UNA
    q[CORRECTS] = _CORRECTS_Q
    q[ASKS_RECALL] = _ASKS_RECALL_Q
    instrucciones = _NEEDS_STAFF_Q["instructions"]
    instrucciones = f"{instrucciones} {_FUERA_DEL_SISTEMA}"
    instrucciones = f"{instrucciones} {_YA_RESERVO_NO_BASTA}"
    q[NEEDS_STAFF] = {**_NEEDS_STAFF_Q, "instructions": instrucciones}
    q[CHANGES_DATE] = _CHANGES_DATE_Q
    q[COMPANION_JOINS] = _COMPANION_JOINS_Q
    q[ADDS_PERSON] = _ADDS_PERSON_Q
    q[YA_RESERVADO] = _YA_RESERVADO_Q_SIN_HOTEL
    q[PIDE_DATOS_AJENOS] = _PIDE_DATOS_AJENOS_Q
    q[PIDE_SERVICIO_PRIVADO] = _PIDE_SERVICIO_PRIVADO_Q
    q[CUSTOMER_PLACE] = _con_hoteles_de_la_base(_CUSTOMER_PLACE_Q_BARU_CARTAGENA)
    q[SHARES_OPEN_FACT] = _SHARES_OPEN_FACT_Q
    q[NUEVO_CASO] = _NUEVO_CASO_Q
    q[PREGUNTA_SI_ES_IA] = _PREGUNTA_SI_ES_IA_Q
    q[CAMBIA_IDIOMA] = _CAMBIA_IDIOMA_Q
    q[PIDE_PRECIO] = _PIDE_PRECIO_Q_ACTIVIDADES
    q[PIDE_QUE_INCLUYE] = _PIDE_QUE_INCLUYE_Q
    q.update(_INTENCIONES_Q)
    q[PIDE_DESCUENTO] = _PIDE_DESCUENTO_Q
    q[PIDE_OTRA_COSA] = _PIDE_OTRA_COSA_CON_DESCUENTOS_Q
    if PIDE_OTRA_COSA in q:
        # arq-1v: preguntar si da tiempo es de la tabla; «otra cosa» deja de contarlo.
        q[PIDE_SI_ALCANZA] = _PIDE_SI_ALCANZA_Q
        q[PIDE_OTRA_COSA] = {**q[PIDE_OTRA_COSA],
                             "instructions": q[PIDE_OTRA_COSA]["instructions"] + _OTRA_COSA_SIN_EL_TIEMPO}
    if PIDE_OTRA_COSA in q:
        # arq-1i: el clima en general y el pago son de la tabla; «otra cosa» deja de contarlos (sus ejemplos los nombraban).
        q[PIDE_CLIMA] = _PIDE_CLIMA_Q
        q[PIDE_PAGO] = _PIDE_PAGO_Q
        otra = (q[PIDE_OTRA_COSA]["instructions"].replace("the weather, ", "the forecast for a specific day, ")
                .replace("payment methods, ", ""))
        q[PIDE_OTRA_COSA] = {**q[PIDE_OTRA_COSA], "instructions": otra + _OTRA_COSA_SIN_CLIMA_NI_PAGO}
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
    # distintos y los llamantes (`_jev_says_not_affirmed`, el relleno del turno con pregunta) necesitan distinguirlos.
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
    if YA_RESERVADO in answers:
        out[YA_RESERVADO] = (answers.get(YA_RESERVADO) or {}).get("noul", 0.0) >= YA_RESERVADO_MIN
    if PIDE_DATOS_AJENOS in answers:
        out[PIDE_DATOS_AJENOS] = (answers.get(PIDE_DATOS_AJENOS) or {}).get("noul", 0.0) >= PIDE_DATOS_AJENOS_MIN
    if PIDE_SERVICIO_PRIVADO in answers:
        out[PIDE_SERVICIO_PRIVADO] = ((answers.get(PIDE_SERVICIO_PRIVADO) or {}).get("noul", 0.0)
                                      >= PIDE_SERVICIO_PRIVADO_MIN)
    # ex-9b paso 5: también en FALSE ("Jev dice que no" manda; ausente = Jev calla y decide el regex).
    if NUEVO_CASO in answers:
        out[NUEVO_CASO] = (answers.get(NUEVO_CASO) or {}).get("noul", 0.0) >= NUEVO_CASO_MIN
    if PREGUNTA_SI_ES_IA in answers:
        out[PREGUNTA_SI_ES_IA] = (answers.get(PREGUNTA_SI_ES_IA) or {}).get("noul", 0.0) >= PREGUNTA_SI_ES_IA_MIN
    if PIDE_PRECIO in answers:
        out[PIDE_PRECIO] = (answers.get(PIDE_PRECIO) or {}).get("noul", 0.0) >= PIDE_PRECIO_MIN
    if PIDE_QUE_INCLUYE in answers:
        out[PIDE_QUE_INCLUYE] = (answers.get(PIDE_QUE_INCLUYE) or {}).get("noul", 0.0) >= PIDE_QUE_INCLUYE_MIN
    for intencion in (*_INTENCIONES_Q, PIDE_DESCUENTO, PIDE_CLIMA, PIDE_PAGO):
        if intencion in answers and intencion != PIDE_OTRA_COSA:
            out[intencion] = (answers.get(intencion) or {}).get("noul", 0.0) >= INTENCION_MIN
    if PIDE_SI_ALCANZA in answers:
        out[PIDE_SI_ALCANZA] = (answers.get(PIDE_SI_ALCANZA) or {}).get("noul", 0.0) >= INTENCION_MIN
    if PIDE_OTRA_COSA in answers:
        # ARQ-1d: al revés que las intenciones, cuenta como «sí» todo lo que no sea un «no» seguro.
        out[PIDE_OTRA_COSA] = (answers.get(PIDE_OTRA_COSA) or {}).get("noul", 1.0) > 1 - INTENCION_MIN
    if CAMBIA_IDIOMA in answers:
        a = answers.get(CAMBIA_IDIOMA) or {}
        out[CAMBIA_IDIOMA] = a.get("choice") if float(a.get("confidence", 0.0)) >= CAMBIA_IDIOMA_MIN else "none"
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


def _medir_jev(resp: httpx.Response | None, t0: float) -> None:
    """mej-5 (21-oct): Jev va por su propio cliente HTTP, fuera del cliente medido de OpenAI, y no salía en las
    métricas del turno (ni su coste ni sus fallos: el 21-oct, con la clave de OpenRouter en su límite, Jev daba 403 en
    todos los turnos y no se veía en [TURN_METRICS]). Su respuesta trae `usage` (tokens y coste en dólares)."""
    from src.observability import record_llm_call  # lazy

    try:
        uso = None
        if resp is not None and resp.status_code < 400:
            u = (resp.json() or {}).get("usage") or {}
            uso = {k: v for k, v in {"in": u.get("input_tokens"), "out": u.get("output_tokens"),
                                     "usd": u.get("cost")}.items() if v} or None
        record_llm_call("chat", time.perf_counter() - t0, settings.jev_model, pieza="jev", inicio=t0,
                        status=resp.status_code if resp is not None else 599, uso=uso)
    except Exception:  # noqa: BLE001 — medir nunca rompe una llamada
        pass


UNCERTAIN = "uncertain"  # Jev respondió pero duda: el turno lo decide el router LLM

# CAL-E5 (16-oct, flag `jev_con_contexto`): Jev contestaba las señales viendo SOLO el mensaje del turno, así que un
# mensaje que se refiere a lo anterior perdía a qué se refiere: "Me lo podrías compartir por favor" (tras "se me perdió
# el número de [NOMBRE]") no era una petición de contacto, y "Pero un link especial" no era algo que solo pueda hacer
# una persona. Con el flag viajan los dos últimos mensajes como REFERENCIA, dejando claro que las preguntas son sobre
# el último mensaje del cliente. No es una lista de frases: es el contexto que le faltaba.
_CONTEXTO_TURNOS = 2
_CONTEXTO_CARACTERES = 400


def _estado_para_jev(message: str, history: list[dict] | None = None) -> str:
    """Lo que Jev lee: el contexto fijo, los últimos turnos (solo con el flag) y el mensaje de este turno."""
    sin_contexto = f"{_CONTEXT}\n\nCustomer message: {message}"
    if not history:
        return sin_contexto
    ultimos = [h for h in history if (h or {}).get("content")][-_CONTEXTO_TURNOS:]
    if not ultimos:
        return sin_contexto
    lineas = "\n".join(
        f"{'Customer' if h.get('role') == 'user' else 'Assistant'}: {str(h['content'])[:_CONTEXTO_CARACTERES]}"
        for h in ultimos)
    return (f"{_CONTEXT}\n\nHow the conversation ended, only so you can tell what the customer is referring to:\n"
            f"{lineas}\n\nEvery question below is about THIS last message of the customer, not about the lines "
            f"above.\n\nCustomer message: {message}")


async def detect_routing_signals_jev(message: str, *, lang: str = "es") -> dict | str | None:
    """Las 9 señales con Jev.

    Devuelve el dict de señales si Jev está seguro, `UNCERTAIN` si duda en alguna
    (cascada: decide el router LLM) y `None` si no está disponible o falla."""
    result, _ = await detect_routing_signals_jev_full(message, lang=lang)
    return result


# Señales de u3-4/u3-5 que NO son del router: viajan aparte (ver `detect_routing_signals_jev_full`).
_TURN_SIGNALS = (
    AFFIRMS_LOCATION, AFFIRMS_ACTIVITY, AFFIRMS_CERTIFICATION, AFFIRMS_GROUP, AFFIRMS_NATIONALITY, CORRECTS,
    ASKS_RECALL, NEEDS_STAFF, CHANGES_DATE, COMPANION_JOINS, SHARES_OPEN_FACT, YA_RESERVADO, PIDE_DATOS_AJENOS,
    NUEVO_CASO, PREGUNTA_SI_ES_IA, CAMBIA_IDIOMA, PIDE_PRECIO, PIDE_SERVICIO_PRIVADO, PIDE_QUE_INCLUYE, *_INTENCIONES_Q,
    PIDE_DESCUENTO,
    # ex-9b (19-oct): ADDS_PERSON también viaja cuando Jev duda en el router (como COMPANION_JOINS): sin él, en esos
    # turnos "¿se suma alguien nuevo?" lo decidía la lista de palabras.
    ADDS_PERSON,
    PIDE_SI_ALCANZA,  # arq-1v: también cuando Jev duda en el router (si no, se perdía: banco arq-1v, v1)
    PIDE_CLIMA, PIDE_PAGO,  # arq-1i: el router los mira (el clima en general no va a la ruta sensible)
)  # ASKS_QUESTION y PENDING_ANSWER se anaden a mano en `detect_routing_signals_jev_full`


async def detect_routing_signals_jev_full(
    message: str, *, lang: str = "es", pending_slot: str | None = None, history: list[dict] | None = None,
) -> tuple[dict | str | None, dict]:
    """Como `detect_routing_signals_jev`, y además las señales de u3-4/u3-5:
    `asks_question` y los `affirms_*`. Van en el segundo valor
    porque valen también cuando Jev DUDA en las señales del router: son otras preguntas
    y el router LLM no las contesta.

    Hasta el 26-sep solo viajaba `asks_question`; los `affirms_*` se perdían en el ~8 %
    de turnos en que Jev duda en el router, y el turno caía a la conducta de hoy sin
    necesidad (el "Yo soy open y me gustaría salir un día…" de la ronda B2 perdió la
    actividad así en el replay del 26-sep, pese a que Jev la afirmaba a 0,93)."""
    key = settings.openrouter_api_key
    if not key or not message or not message.strip():
        return None, {}
    from src.llm_client import cortar_openrouter_si_es_la_clave, openrouter_cortado  # lazy

    if openrouter_cortado():
        # mej-7: la clave o el crédito de OpenRouter fallaron hace poco; Jev va por OpenRouter y fallaría igual.
        logger.warning("[ROUTER][JEV] OpenRouter cortado (clave o crédito): se usa el router LLM")
        return None, {}
    t0 = time.perf_counter()
    resp = None
    try:
        resp = await _http().post(
            JEV_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": settings.jev_model,
                "state": _estado_para_jev(message, history),
                "questions": _questions_for_turn(pending_slot),
            },
            timeout=settings.jev_timeout_seconds,
        )
        _medir_jev(resp, t0)
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
        if pending_slot and PENDING_ANSWER in answers:
            extras[PENDING_ANSWER] = pending_answer_value(pending_slot, answers[PENDING_ANSWER])
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cae al router LLM
        cortar_openrouter_si_es_la_clave(getattr(getattr(exc, "response", None), "status_code", None), "jev")
        ms = (time.perf_counter() - t0) * 1000
        if resp is None:
            _medir_jev(None, t0)  # timeout o sin conexión: también cuenta como llamada fallida
        logger.warning(f"[ROUTER][JEV] fallo en {ms:.0f} ms, se usa el router LLM: {type(exc).__name__}: {exc}")
        return None, {}
    ms = (time.perf_counter() - t0) * 1000
    if doubts:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms duda={doubts} -> router LLM (se conservan {sorted(extras)}) msg={message[:80]!r}")
        return UNCERTAIN, extras
    if signals:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms detected={signals} msg={message[:80]!r}")
    return signals, extras
