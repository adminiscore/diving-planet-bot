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

import logging
import re
import time

import httpx
import structlog

from src.config import settings
from src.domain.calendario import dias_cerrados
from src.prompts.router import ROUTING_TOOL, con_lo_que_no_es_medico

con_lo_que_no_es_medico(ROUTING_TOOL)  # gen-3 (20-oct): el enrutador de respaldo, con la misma definición que Jev

logger = structlog.get_logger()
_llm_logger = logging.getLogger("uvicorn.error")

SENSITIVE_RULES = {
    "medical_questions": {
        "keywords": {
            "asma", "corazón", "corazon", "cardíaco", "cardiaco",
            "cirugía", "cirugia", "medicamento", "medicación", "medicacion", "diabetes",
            "epilepsia", "presión", "presion", "oído", "oido", "medical", "asthma",
            "heart", "surgery", "medication", "medicine",
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
            # lat-deuda-u (26-oct): fuera «hay cupo», «cupo mañana», «disponible mañana» (y en inglés): pasaban a un asesor
            # con «depende de disponibilidad en tiempo real» y siempre hay disponibilidad (decisión del negocio).
            # payment PROBLEMS only — the bare verb "pagar"/"pago" wrongly caught
            # info questions like "¿puedo pagar en euros?" / "¿cómo pago?".
            "no puedo pagar", "no me deja pagar", "pago no", "pago fallo", "pago falló",
            "pago fallido", "error de pago", "error en el pago", "pago rechazado",
            "falla el pago", "falló el pago", "reserva no",
            "error reserva", "no puedo reservar",
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
        # s4-16 (paso 6, 27-sep): el pase es correcto, pero sin reconocer el problema sonaba frio
        # (golden `queja`, criterio "empatia"). Vale igual para una emergencia.
        "es_v2": (
            "Siento mucho lo que ha pasado 🙏 y entiendo tu molestia. Voy a pasarte ahora mismo con un "
            "miembro de nuestro staff para que lo revise contigo y te dé una solución."
        ),
        "en_v2": (
            "I'm really sorry about what happened 🙏 and I understand your frustration. I'm passing you right "
            "now to a member of our staff so they can look into it with you and sort it out."
        ),
    },
}


# ex-2 (fase EX, `escalado_solo_emergencias`, promocionado): la lista que pasa a un asesor ANTES de que opine la IA se queda
# con las EMERGENCIAS (red rápida: perder una es grave; una falsa alarma cuesta poco) y las INCIDENCIAS en tiempo real
# ("hay cupo mañana", "no puedo pagar": frases concretas, 0 falsas alarmas en el banco, y Jev solo marca los fallos, no
# "¿hay cupo mañana?"). Lo médico, el tiempo y las quejas los decide Jev con `sensitive_topic` (la misma llamada del
# enrutador), que lee la frase entera: con la lista, "completed the medical form", "he oído que…" o "mi amigo es
# abogado" pasaban a un asesor. Banco ex2 (2 rondas de 2 pasadas): falsas alarmas 32-33 -> 11-12; perdidas 4-5 ->
# 5-7, la diferencia solo en el tiempo ("hoy hace mucho viento, ¿sale la lancha?": Jev no lo marca).
EMERGENCY_KEYWORDS = {
    "emergencia", "emergencias", "accidente", "urgencia", "no respira", "inconsciente", "se desmayó",
    "se desmayo", "sangrando", "sangra", "ahogando", "ahogó", "ahogo",
    "emergency", "accident", "unconscious", "not breathing", "can't breathe", "cant breathe", "bleeding",
    "fainted", "passed out", "drowning",
}


def _active_rules() -> dict:
    """Las reglas de palabras clave que pasan a un asesor (ex-2): las emergencias y las incidencias."""
    emergencias = SENSITIVE_RULES["complaints_or_emergencies"]
    return {"complaints_or_emergencies": {**emergencias, "keywords": EMERGENCY_KEYWORDS},
            "real_time_issues": SENSITIVE_RULES["real_time_issues"]}


# 13-oct (promocionado): el aviso médico PASA la conversación a una persona (Step.ESCALATE en los dos
# caminos, palabra clave y Jev) pero solo decía "es importante que hables con nuestro staff": el cliente no sabía que
# alguien iba a escribirle (cambio-fecha-por-enfermedad: `pasa-a-persona-por-enfermedad` no_cumple en ex8-B2 y ex7-B).
_PASE_MEDICO = {
    "es": " Te paso ahora con alguien del equipo, que te escribe por aquí enseguida.",
    "en": " I'm passing you now to someone from our team, who will write to you here shortly.",
}


# gen-3 (20-oct, flag `clima_con_politica`, decisión de Gadea): el aviso del clima decía solo "las condiciones pueden
# cambiar, te conecto con el equipo". Antes del pase, lo que la base ya dice (FAQ 3 y 10): cuándo operamos y qué pasa si
# el mar no está apto. La previsión de un día concreto sigue siendo del equipo.
_CLIMA_CON_POLITICA = {
    "es": (f"Operamos todos los días del año salvo {dias_cerrados('es')}, y la seguridad va primero: si el "
           "mar no está apto, la salida se reprograma y, si no es posible reagendarla, se reembolsa el 100 %. "
           "La previsión de un día concreto te la confirma el equipo: te "
           "paso ahora con alguien que te escribe por aquí enseguida."),
    "en": (f"We operate every day of the year except {dias_cerrados('en')}, and safety comes first: if the sea is "
           "not suitable, the trip is rescheduled and, if that is not possible, it is refunded 100%. "
           "The forecast for a specific day is confirmed by our team: I'm "
           "passing you now to someone who will write to you here shortly."),
}


def _rule_message(rule: dict, lang: str) -> str:
    key = "es" if lang == "es" else "en"
    if f"{key}_v2" in rule:
        return rule[f"{key}_v2"]
    if rule is SENSITIVE_RULES.get("weather_conditions"):
        return _CLIMA_CON_POLITICA[key]
    if rule is SENSITIVE_RULES.get("medical_questions"):
        return rule[key] + _PASE_MEDICO[key]
    return rule[key]


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
    for reason, rule in _active_rules().items():
        haystack = scrubbed if reason == "medical_questions" else msg_lower
        if _matches_any_keyword(haystack, rule["keywords"]):
            return reason, _rule_message(rule, lang)
    return None


def clima_general_al_redactor(reason: str | None, signals: dict | None) -> bool:
    """arq-1i (decisión de Gadea #1312): una pregunta GENERAL del clima («¿y si hace mal
    tiempo se cancela?») no va a la ruta sensible: la contesta el redactor de hechos con la política (se reprograma o se
    reembolsa el 100 % si Capitanía cierra) y ofrece un asesor. Con un día concreto o una reserva hecha Jev no la marca
    (`pide_clima`) y sigue el pase. Lo miran el router y la cascada, con el mismo criterio."""
    return reason == "weather_conditions" and (signals or {}).get("pide_clima") is True


def sensitive_response_for(category: str, lang: str = "es") -> tuple[str, str] | None:
    """El mismo (reason, texto) que devolvería detect_sensitive_escalation para
    esta categoría — usado por la red de precisión LLM (detect_routing_signals)
    para que ambos caminos (keyword y LLM) den exactamente la misma respuesta."""
    if isinstance(category, dict):
        # ex-2 (12-oct): el router LLM de respaldo a veces devuelve la categoría anidada
        # (`{"weather_conditions": true}`, 1 de 152 llamadas del banco ex2) y como clave de diccionario
        # rompía el turno (TypeError). Vale si trae UNA categoría conocida a true.
        marcadas = [k for k, v in category.items() if v is True and k in SENSITIVE_RULES]
        category = marcadas[0] if len(marcadas) == 1 else None
    if not isinstance(category, str):
        return None
    rule = SENSITIVE_RULES.get(category)
    if not rule:
        return None
    return category, _rule_message(rule, lang)


async def detect_routing_signals(
    message: str, *, lang: str = "es", pending_slot: str | None = None, history: list[dict] | None = None,
) -> dict:
    """Las señales del turno, de Jev (U3, ~0,3 s): las 9 del enrutador y las del turno (u3-4/u3-5, intenciones…).
    lat-11 T2 (26-oct): sin router LLM de respaldo. Si Jev duda, decide igual con lo que tiene; si no contesta (sin
    clave de OpenRouter, OpenRouter cortado, tiempo agotado), {} y deciden las listas de siempre (`regex_decide`).
    Nunca lanza excepción."""
    if not message or not message.strip():
        return {}
    from src.agents.jev_router import ASKS_QUESTION, UNCERTAIN, detect_routing_signals_jev_full
    from src.observability import note_turn

    t0 = time.perf_counter()
    jev, turn_signals = await detect_routing_signals_jev_full(
        message, lang=lang, pending_slot=pending_slot, history=history)
    if isinstance(turn_signals, bool):  # contrato anterior (solo asks_question)
        turn_signals = {ASKS_QUESTION: True} if turn_signals else {}
    router = "jev" if isinstance(jev, dict) else ("jev_duda" if jev == UNCERTAIN else "sin_ia")
    note_turn(router=router, router_ms=round((time.perf_counter() - t0) * 1000))
    result = {**(jev if isinstance(jev, dict) else {}), **turn_signals}
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
