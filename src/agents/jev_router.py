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
}
# Las preguntas de u3-4 no son señales del router: su duda NO manda el turno al router LLM.
_U34_QUESTIONS = (ASKS_QUESTION, AFFIRMS_LOCATION, AFFIRMS_ACTIVITY, ACTIVITY_HYPOTHESIS)


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


def _questions_for_turn() -> dict:
    if settings.answer_and_continue:
        return {**_QUESTIONS, ASKS_QUESTION: _ASKS_QUESTION_Q, **_AFFIRMS_QUESTIONS}
    return _QUESTIONS


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
    if AFFIRMS_LOCATION in answers:
        out[AFFIRMS_LOCATION] = (answers.get(AFFIRMS_LOCATION) or {}).get("noul", 0.0) >= AFFIRMS_MIN
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


async def detect_routing_signals_jev_full(
    message: str, *, lang: str = "es",
) -> tuple[dict | str | None, bool]:
    """Como `detect_routing_signals_jev`, y además si el mensaje trae algo que contestar
    (u3-4, solo con `answer_and_continue`). Lo segundo vale también cuando Jev duda en
    las señales del router: es otra pregunta y el router LLM no la contesta."""
    key = settings.openrouter_api_key
    if not key or not message or not message.strip():
        return None, False
    t0 = time.perf_counter()
    try:
        resp = await _http().post(
            JEV_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": settings.jev_model,
                "state": f"{_CONTEXT}\n\nCustomer message: {message}",
                "questions": _questions_for_turn(),
            },
            timeout=settings.jev_timeout_seconds,
        )
        resp.raise_for_status()
        answers = resp.json()["answers"]
        signals = answers_to_signals(answers)
        doubts = uncertain_answers(answers)
        asks = (answers.get(ASKS_QUESTION) or {}).get("noul", 0.0) >= ASKS_QUESTION_MIN
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cae al router LLM
        ms = (time.perf_counter() - t0) * 1000
        logger.warning(f"[ROUTER][JEV] fallo en {ms:.0f} ms, se usa el router LLM: {type(exc).__name__}: {exc}")
        return None, False
    ms = (time.perf_counter() - t0) * 1000
    if doubts:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms duda={doubts} -> router LLM msg={message[:80]!r}")
        return UNCERTAIN, asks
    if signals:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms detected={signals} msg={message[:80]!r}")
    return signals, asks
