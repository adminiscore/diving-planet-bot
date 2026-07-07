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

import httpx
import structlog

from src.config import settings

logger = structlog.get_logger()

SENSITIVE_RULES = {
    "medical_questions": {
        "keywords": {
            "asma", "embarazo", "embarazada", "corazón", "corazon", "cardíaco", "cardiaco",
            "cirugía", "cirugia", "medicamento", "medicación", "medicacion", "diabetes",
            "epilepsia", "presión", "presion", "oído", "oido", "medical", "asthma",
            "pregnant", "pregnancy", "heart", "surgery", "medication", "medicine",
        },
        "es": "Para preguntas médicas específicas, es importante que hables con nuestro staff calificado para evaluar tu situación particular.\nWhatsApp: +57 320 231515",
        "en": "For specific medical questions, it's important that you speak with our qualified staff so they can assess your particular situation.\nWhatsApp: +57 320 231515",
    },
    "weather_conditions": {
        "keywords": {
            "clima mañana", "clima hoy", "tiempo mañana", "tiempo hoy", "oleaje",
            "viento", "tormenta", "lluvia mañana", "weather tomorrow", "weather today",
            "wind", "storm", "waves", "rain tomorrow",
        },
        "es": "Las condiciones del tiempo pueden cambiar rápidamente. Te conecto con el equipo para darte información actualizada.\nWhatsApp: +57 320 231515",
        "en": "Weather conditions can change quickly. I'll connect you with the team for updated information.\nWhatsApp: +57 320 231515",
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
        "es": "Esta consulta depende de disponibilidad o soporte en tiempo real. Te conecto con alguien del equipo para ayudarte ahora.\nWhatsApp: +57 320 231515",
        "en": "This depends on real-time availability or support. I'll connect you with someone from the team to help you now.\nWhatsApp: +57 320 231515",
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
        "es": "Voy a transferirte inmediatamente con un miembro de nuestro staff para ayudarte con esta situación.\nWhatsApp: +57 320 231515",
        "en": "I'm immediately transferring you to a staff member to help with this situation.\nWhatsApp: +57 320 231515",
    },
}


# Idioms that contain a medical keyword but are NOT medical (avoid false-positive
# escalation): "corazón de oro" (kind-hearted), "de todo corazón" (heartfelt)...
_MEDICAL_IDIOM_EXCLUSIONS = (
    "corazon de oro", "corazón de oro", "de todo corazon", "de todo corazón",
    "con el corazon en la mano", "heart of gold",
)


def detect_sensitive_escalation(message: str, lang: str = "es") -> tuple[str, str] | None:
    msg_lower = message.strip().lower()
    # Neutralize non-medical idioms so a word like "corazón" inside "corazón de
    # oro" doesn't trigger a medical escalation.
    scrubbed = msg_lower
    for idiom in _MEDICAL_IDIOM_EXCLUSIONS:
        scrubbed = scrubbed.replace(idiom, " ")
    for reason, rule in SENSITIVE_RULES.items():
        haystack = scrubbed if reason == "medical_questions" else msg_lower
        if any(keyword in haystack for keyword in rule["keywords"]):
            return reason, rule["es"] if lang == "es" else rule["en"]
    return None


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
