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


async def detect_routing_signals_jev(message: str, *, lang: str = "es") -> dict | None:
    """Las 9 señales con Jev. `None` = no disponible o fallo: usar el router LLM."""
    key = settings.openrouter_api_key
    if not key or not message or not message.strip():
        return None
    t0 = time.perf_counter()
    try:
        resp = await _http().post(
            JEV_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": settings.jev_model,
                "state": f"{_CONTEXT}\n\nCustomer message: {message}",
                "questions": _QUESTIONS,
            },
            timeout=settings.jev_timeout_seconds,
        )
        resp.raise_for_status()
        answers = resp.json()["answers"]
        signals = answers_to_signals(answers)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cae al router LLM
        ms = (time.perf_counter() - t0) * 1000
        logger.warning(f"[ROUTER][JEV] fallo en {ms:.0f} ms, se usa el router LLM: {type(exc).__name__}: {exc}")
        return None
    ms = (time.perf_counter() - t0) * 1000
    if signals:
        logger.info(f"[ROUTER][JEV] {ms:.0f} ms detected={signals} msg={message[:80]!r}")
    return signals
