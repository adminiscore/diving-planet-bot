"""
Escalation Agent.

Handles handoff from bot to human agent in Chatwoot.

Triggers:
- User explicitly requests human agent
- Bot confidence is low (Phase 2, with LLM)
- Sensitive topics (medical conditions, complaints)
- Private/group service requests (need custom quote)
- 3+ failed attempts to understand user

Actions:
- Set Chatwoot conversation status to "pending" (triggers notification)
- Assign conversation to the owner agent in Chatwoot
- Send conversation summary to owner
- Log escalation reason for analytics
"""

import json
import logging
import re

import httpx
import structlog
from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai
from src.prompts.router import ROUTING_TOOL, routing_system_prompt

logger = structlog.get_logger()
_llm_logger = logging.getLogger("uvicorn.error")

SENSITIVE_RULES = {
    "medical_questions": {
        "keywords": {
            "asma", "embarazo", "embarazada", "corazón", "corazon", "cardíaco", "cardiaco",
            "cirugía", "cirugia", "medicamento", "medicación", "medicacion", "diabetes",
            "epilepsia", "presión", "presion", "oído", "oido", "medical", "asthma",
            "pregnant", "pregnancy", "heart", "surgery", "medication", "medicine",
        },
        "es": "Para preguntas médicas específicas, es importante que hables con nuestro staff calificado para evaluar tu situación particular.",
        "en": "For specific medical questions, it's important that you speak with our qualified staff so they can assess your particular situation.",
    },
    "weather_conditions": {
        "keywords": {
            "clima mañana", "clima hoy", "tiempo mañana", "tiempo hoy", "oleaje",
            "viento", "tormenta", "lluvia mañana", "weather tomorrow", "weather today",
            "wind", "storm", "waves", "rain tomorrow",
        },
        "es": "Las condiciones del tiempo pueden cambiar rápidamente. Te conecto con el equipo para darte información actualizada.",
        "en": "Weather conditions can change quickly. I'll connect you with the team for updated information.",
    },
    "real_time_issues": {
        "keywords": {
            "disponible mañana", "cupo mañana", "hay cupo",
            # payment PROBLEMS only — the bare verb "pagar"/"pago" wrongly caught
            # info questions like "¿puedo pagar en euros?" / "¿cómo pago?".
            "no puedo pagar", "no me deja pagar", "pago no", "pago fallo", "pago falló",
            "pago fallido", "error de pago", "error en el pago", "pago rechazado",
            "falla el pago", "falló el pago", "reserva no",
            "error reserva", "no puedo reservar", "available tomorrow", "availability tomorrow",
            "payment failed", "payment error", "payment didn't", "payment not going",
            "booking error", "can't book", "cannot book",
        },
        "es": "Esta consulta depende de disponibilidad o soporte en tiempo real. Te conecto con alguien del equipo para ayudarte ahora.",
        "en": "This depends on real-time availability or support. I'll connect you with someone from the team to help you now.",
    },
    "complaints_or_emergencies": {
        "keywords": {
            "queja", "reclamo", "emergencia", "accidente", "problema grave", "complaint",
            "emergency", "accident", "serious problem",
            # Fraud accusations & refund DEMANDS (not neutral "¿política de reembolso?").
            "estafa", "estafador", "estafadores", "fraude", "fraudulento", "timo",
            "me estafaron", "nos estafaron", "me timaron", "me engañaron", "nos engañaron",
            "quiero mi dinero", "mi dinero de vuelta", "devuelvan mi dinero",
            "devuélvanme", "devuelvanme", "quiero que me devuelvan",
            "pésimo servicio", "pesimo servicio", "muy mal servicio", "terrible servicio",
            "los voy a demandar", "voy a demandar", "demandarlos", "abogado",
            "scam", "fraud", "scammed", "ripped off", "rip off", "ripoff",
            "my money back", "want my money", "give me my money", "worst service",
            "terrible service", "i'll sue", "i will sue", "lawyer",
        },
        "es": "Voy a transferirte inmediatamente con un miembro de nuestro staff para ayudarte con esta situación.",
        "en": "I'm immediately transferring you to a staff member to help with this situation.",
    },
}


# Idioms that contain a medical keyword but are NOT medical (avoid false-positive
# escalation): "corazón de oro" (kind-hearted), "de todo corazón" (heartfelt)...
_MEDICAL_IDIOM_EXCLUSIONS = (
    "corazon de oro", "corazón de oro", "de todo corazon", "de todo corazón",
    "con el corazon en la mano", "heart of gold",
    # "presión" used colloquially for composure/stress handling, not blood pressure.
    "buena presion", "buena presión", "manejar la presion", "manejar la presión",
    "manejar presion", "manejar presión", "under pressure", "good under pressure",
)


def _matches_any_keyword(haystack: str, keywords) -> bool:
    """Hallazgo en vivo (bateria "natural/deictica", lote 12, 2026-09-02,
    conversacion 845): el chequeo anterior era `keyword in haystack`, un
    substring SIN limites de palabra -- la keyword "timo" (de "estafa") de
    `complaints_or_emergencies` hacia match dentro de "ulTIMO dia" ("¿podria
    hacer lo mismo... ese ultimo dia...?"), escalando una pregunta de
    logistica normal a "voy a transferirte con staff" como si fuera una
    denuncia de fraude. Mismo riesgo confirmado para "presion" (dentro de
    "impresion/expresion/depresion") y "cirugia" (dentro de "microcirugia").
    Fix: limites de palabra reales (`\\b`), igual que el resto de regex
    deterministas del repo -- "timo" ya NO matchea dentro de "ultimo" (no
    hay limite de palabra entre "l" y "t", ambos caracteres de palabra),
    pero SI matchea "el timo fue grande" (con espacios/limites alrededor)."""
    return any(re.search(rf"\b{re.escape(kw)}\b", haystack) for kw in keywords)


def detect_sensitive_escalation(message: str, lang: str = "es") -> tuple[str, str] | None:
    msg_lower = message.strip().lower()
    # Neutralize non-medical idioms so a word like "corazón" inside "corazón de
    # oro" doesn't trigger a medical escalation.
    scrubbed = msg_lower
    for idiom in _MEDICAL_IDIOM_EXCLUSIONS:
        scrubbed = scrubbed.replace(idiom, " ")
    for reason, rule in SENSITIVE_RULES.items():
        haystack = scrubbed if reason == "medical_questions" else msg_lower
        if _matches_any_keyword(haystack, rule["keywords"]):
            return reason, rule["es"] if lang == "es" else rule["en"]
    return None


def sensitive_response_for(category: str, lang: str = "es") -> tuple[str, str] | None:
    """El mismo (reason, texto) que devolvería detect_sensitive_escalation para
    esta categoría — usado por la red de precisión LLM (detect_routing_signals)
    para que ambos caminos (keyword y LLM) den exactamente la misma respuesta."""
    rule = SENSITIVE_RULES.get(category)
    if not rule:
        return None
    return category, rule["es"] if lang == "es" else rule["en"]


async def detect_routing_signals(
    message: str, *, lang: str = "es", client: AsyncOpenAI | None = None,
) -> dict:
    """Red de precisión para los 3 gates de arriba — solo se llama cuando las
    listas de palabras clave NO encontraron nada (ver supervisor.py). Nunca
    lanza excepción: {} en cualquier error, respuesta rara, o mensaje vacío,
    para que el caller siga con el comportamiento anterior (las listas)."""
    if not message or not message.strip():
        return {}
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=[
                {"role": "system", "content": routing_system_prompt(lang)},
                {"role": "user", "content": message},
            ],
            tools=[ROUTING_TOOL],
            tool_choice={"type": "function", "function": {"name": "detect_routing_signals"}},
            temperature=0.0,
            max_tokens=140,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            return {}
        args = json.loads(tool_calls[0].function.arguments or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        _llm_logger.warning(f"[ESCALATION] routing signals malformed response: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001
        _llm_logger.warning(f"[ESCALATION] routing signals error: {exc}")
        return {}

    result = {k: v for k, v in (args or {}).items() if v not in (None, "", [], {})}
    if result:
        _llm_logger.info(f"[ESCALATION][ROUTING_SIGNALS] detected={result} msg={message[:80]!r}")
    return result


async def escalate_to_human(
    conversation_id: str,
    reason: str,
    summary: str = "",
) -> bool:
    """
    Escalate a conversation to a human agent in Chatwoot.

    This toggles the conversation status so the owner gets notified
    via the Chatwoot app (mobile push notification + sound).
    """
    url = (
        f"{settings.chatwoot_api_url}/api/v1/accounts/{settings.chatwoot_account_id}"
        f"/conversations/{conversation_id}/toggle_status"
    )
    headers = {
        "api_access_token": settings.chatwoot_api_token,
        "Content-Type": "application/json",
    }
    payload = {"status": "pending"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
            resp.raise_for_status()

            logger.info(
                "escalated_to_human",
                conversation_id=conversation_id,
                reason=reason,
            )
            return True
        except httpx.HTTPError as e:
            logger.error(
                "escalation_failed",
                conversation_id=conversation_id,
                error=str(e),
            )
            return False
