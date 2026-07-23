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

import httpx
import structlog
from openai import AsyncOpenAI

from src.config import settings

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


def sensitive_response_for(category: str, lang: str = "es") -> tuple[str, str] | None:
    """El mismo (reason, texto) que devolvería detect_sensitive_escalation para
    esta categoría — usado por la red de precisión LLM (detect_routing_signals)
    para que ambos caminos (keyword y LLM) den exactamente la misma respuesta."""
    rule = SENSITIVE_RULES.get(category)
    if not rule:
        return None
    return category, rule["es"] if lang == "es" else rule["en"]


# ---------------------------------------------------------------------------
# Red de precisión LLM (auditoría 2026-07-22): los gates de arriba
# (SENSITIVE_RULES, ESCALATION_KEYWORDS en supervisor.py, MENU_KEYWORDS/
# BACK_KEYWORDS en supervisor.py, _ADAPTIVE_DIVING_PATTERN en supervisor.py)
# son listas cerradas de palabras exactas. Probado en vivo: "estoy
# embarazadita", "soy epiléptica", "tengo una condición cardiaca" (femenino),
# "ataque de pánico" (médico) y "perdí una pierna", "uso prótesis", "tengo
# párkinson", "lesión medular", "soy sordomuda", "no vidente" (discapacidad/
# DIVE TO HEAL, auditoría 2026-07-23) — NINGUNA se detectaba, pese a ser
# justo el tipo de caso que estos gates existen para atrapar.
# A diferencia del extractor de reserva (donde abstenerse es más seguro que
# inventar), aquí el sesgo correcto es el CONTRARIO para sensitive_topic y
# adaptive_diving_topic: mejor escalar/enrutar de más que de menos — no
# detectar una emergencia real o una necesidad de accesibilidad cuesta mucho
# más que un falso positivo. Nunca REEMPLAZA las listas (que siguen siendo el
# camino gratis para los casos claros); es una red que solo se llama cuando
# esas listas no encontraron nada.
_ROUTING_TOOL = {
    "type": "function",
    "function": {
        "name": "detect_routing_signals",
        "description": (
            "Classify a customer message for a scuba booking bot for 6 "
            "safety/routing signals, in ANY regional Spanish or English "
            "phrasing, slang, or diminutive form — not just the exact "
            "clinical/formal wording. Bias applies to sensitive_topic AND "
            "adaptive_diving_topic: when genuinely unsure whether a MEDICAL/"
            "weather/real-time/complaint issue or a DISABILITY/accessibility "
            "topic applies, still set it — missing a real medical emergency "
            "or a real accessibility need is worse than a false positive. "
            "wants_human, wants_menu_or_restart, booking_change_topic and "
            "asks_for_contact_number are the OPPOSITE: be STRICT, only set "
            "them on an explicit request (see their descriptions) — a normal "
            "booking message must never be misread as one."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "wants_human": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the customer EXPLICITLY asks to talk to "
                        "a human / real person / agent / advisor instead of the "
                        "bot ('quiero hablar con alguien', 'pásame con un "
                        "asesor', 'can I talk to a real person'). A message that "
                        "merely describes their booking — companions, group, "
                        "activities, plan, or a normal question ('tengo un amigo "
                        "que quiere bucear', 'somos 3', 'y uno hace snorkel') — "
                        "is NOT a request for a human. When unsure, leave it "
                        "false; another layer handles the booking."
                    ),
                },
                "wants_menu_or_restart": {
                    "type": "boolean",
                    "description": (
                        "True if the customer wants to go back to a "
                        "previous step, see the menu of options, or start "
                        "over."
                    ),
                },
                "sensitive_topic": {
                    "type": "string",
                    "enum": [
                        "medical_questions", "weather_conditions",
                        "real_time_issues", "complaints_or_emergencies",
                    ],
                    "description": (
                        "Set if the message raises a MEDICAL condition or "
                        "concern (pregnancy, heart/cardiac/respiratory/"
                        "psychiatric conditions, panic attacks, epilepsy, "
                        "surgery, medication...), a WEATHER-dependent "
                        "question, a REAL-TIME availability/payment "
                        "problem, or a COMPLAINT/emergency/fraud "
                        "accusation. Do NOT use 'medical_questions' for a "
                        "DISABILITY or accessibility topic (amputation, "
                        "prosthetic limb, wheelchair, blindness/deafness, "
                        "paralysis, reduced mobility, Down syndrome, "
                        "autism...) — those go in `adaptive_diving_topic` "
                        "instead, never both."
                    ),
                },
                "adaptive_diving_topic": {
                    "type": "boolean",
                    "description": (
                        "True if the message raises a DISABILITY or "
                        "accessibility topic in the context of diving — "
                        "amputation, missing limb, prosthetic/prótesis, "
                        "wheelchair, paralysis (parálisis, lesión medular), "
                        "blindness/low vision ('no vidente', invidente, "
                        "ciego), deafness ('sordomuda', sordo), Down "
                        "syndrome, autism, Parkinson's, cerebral palsy, "
                        "reduced mobility, or asking whether someone with a "
                        "disability can dive — in ANY regional phrasing, "
                        "even if it doesn't use the word 'discapacidad' "
                        "itself. This routes to the DIVE TO HEAL adaptive-"
                        "diving program, NOT a medical escalation — never "
                        "also set `sensitive_topic` for the same message."
                    ),
                },
                "asks_for_contact_number": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the customer is asking for a direct "
                        "contact channel to reach the business OUTSIDE this "
                        "chat — a phone number, WhatsApp number, a line to "
                        "call, or an email — in any phrasing ('¿me pasas un "
                        "número?', 'tienen WhatsApp?', '¿cómo los contacto?', "
                        "'a number to call you', 'how can I reach you'). Do "
                        "NOT set it for a normal booking message, for asking "
                        "to talk to a human IN this chat (that is "
                        "wants_human), or for giving THEIR own number. When "
                        "unsure, leave it false."
                    ),
                },
                "booking_change_topic": {
                    "type": "string",
                    "enum": ["cancellation", "reschedule"],
                    "description": (
                        "Set ONLY when the customer clearly wants to CANCEL "
                        "or CHANGE THE DATE of an EXISTING booking of theirs, "
                        "in any regional phrasing, slang, typo, or indirect "
                        "wording — 'cancellation' for cancelling/backing out/"
                        "not being able to come ('ya no puedo ir', 'me surgió "
                        "un imprevisto y no puedo asistir', 'quiero echar para "
                        "atrás la reserva', 'dar de baja', 'bórrame del buceo', "
                        "\"i can't make it anymore\", 'take me off the "
                        "booking'); 'reschedule' for moving it to another day "
                        "('mover mi reserva', 'pasar el buceo para otro día', "
                        "'correr la fecha', 'posponerlo', 'push it to "
                        "another day'). STRICT: do NOT set it for a general "
                        "question ABOUT the cancellation/refund policy "
                        "('¿cuál es la política de cancelación?', 'si cancelo "
                        "me devuelven?'), nor for the bare word 'cancelar'/"
                        "'cancel'/'atrás'/'volver' used to navigate the menu "
                        "(that is menu/back, not a booking change), nor for a "
                        "booking still being CREATED right now. When unsure, "
                        "leave it unset."
                    ),
                },
            },
        },
    },
}


def _routing_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una capa de seguridad para un bot de buceo. Las listas de "
            "palabras clave del bot no encontraron nada en este mensaje — tu "
            "única tarea es revisar si, en CUALQUIER forma regional de "
            "decirlo (México, Colombia, Chile, Argentina, España...), el "
            "mensaje (1) pide hablar con una persona humana, (2) pide volver "
            "al menú o reiniciar, (3) menciona un tema médico, del clima, "
            "de disponibilidad/pago en tiempo real, o una queja/emergencia/"
            "estafa, o (4) menciona una discapacidad o tema de accesibilidad "
            "(amputación, prótesis, silla de ruedas, ceguera/sordera, "
            "párkinson, parálisis, síndrome de Down, autismo...) en relación "
            "al buceo — esto va a `adaptive_diving_topic`, NUNCA junto con "
            "sensitive_topic, o (5) quiere CANCELAR o CAMBIAR LA FECHA de una "
            "reserva que YA tiene (booking_change_topic) — 'cancellation' o "
            "'reschedule'. IMPORTANTE: el sesgo de 'ante la duda, márcalo' "
            "vale para sensitive_topic Y adaptive_diving_topic (mejor "
            "escalar/enrutar de más). wants_human, wants_menu_or_restart y "
            "booking_change_topic son lo contrario: márcalos SOLO si el "
            "cliente lo pide explícitamente; un mensaje normal de reserva "
            "(acompañantes, grupo, actividades) NUNCA es wants_human, y una "
            "PREGUNTA por la política de cancelación NO es booking_change_topic. "
            "(6) si pide un número de teléfono/WhatsApp/correo o una vía de "
            "contacto FUERA de este chat → asks_for_contact_number (también "
            "estricto). Llama a `detect_routing_signals`."
        )
    return (
        "You are a safety layer for a scuba diving bot. The bot's keyword "
        "lists found nothing in this message — your only job is to check "
        "whether, in ANY regional way of phrasing it, the message (1) asks "
        "to talk to a human, (2) asks to go back to the menu or restart, "
        "(3) raises a medical, weather, real-time availability/payment, or "
        "complaint/emergency/fraud topic, or (4) raises a disability or "
        "accessibility topic (amputation, prosthetic, wheelchair, blindness/"
        "deafness, Parkinson's, paralysis, Down syndrome, autism...) in "
        "relation to diving — that goes in `adaptive_diving_topic`, NEVER "
        "together with sensitive_topic, or (5) wants to CANCEL or CHANGE THE "
        "DATE of a booking they ALREADY have (booking_change_topic — "
        "'cancellation' or 'reschedule'). IMPORTANT: the 'when unsure, flag "
        "it' bias applies to BOTH sensitive_topic and adaptive_diving_topic "
        "(better to over-escalate/over-route). wants_human, "
        "wants_menu_or_restart and booking_change_topic are the opposite: "
        "flag them ONLY on an explicit request; a normal booking message "
        "(companions, group, activities) is NEVER wants_human, and a "
        "QUESTION about the cancellation policy is NOT booking_change_topic. "
        "(6) if they ask for a phone/WhatsApp/email or a contact channel "
        "OUTSIDE this chat → asks_for_contact_number (also strict). Call "
        "`detect_routing_signals`."
    )


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
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=[
                {"role": "system", "content": _routing_system_prompt(lang)},
                {"role": "user", "content": message},
            ],
            tools=[_ROUTING_TOOL],
            tool_choice={"type": "function", "function": {"name": "detect_routing_signals"}},
            temperature=0.0,
            max_tokens=80,
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
