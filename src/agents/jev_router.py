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


def _questions_for_turn() -> dict:
    if settings.answer_and_continue:
        return {**_QUESTIONS, ASKS_QUESTION: _ASKS_QUESTION_Q}
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
        # La pregunta de u3-4 no es una señal del router: su duda no manda el turno al LLM.
        if name.startswith("opt_") or name == ASKS_QUESTION or not isinstance(a, dict):
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
