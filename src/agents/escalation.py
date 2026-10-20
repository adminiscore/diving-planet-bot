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
import time

import httpx
import structlog
from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import tool_arguments, trace_openai
from src.observability import con_pieza_llm
from src.prompts.router import ROUTING_TOOL, con_dieta_no_es_medica, routing_system_prompt

if settings.dieta_no_es_medica:  # gen-3 (20-oct): el enrutador de respaldo, con la misma definición que Jev
    con_dieta_no_es_medica(ROUTING_TOOL)

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


# ex-2 (fase EX, flag `escalado_solo_emergencias`): la lista que pasa a un asesor ANTES de que opine la IA se queda
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
    """Las reglas de palabras clave que pasan a un asesor: todas, o (ex-2) las emergencias y las incidencias."""
    if not settings.escalado_solo_emergencias:
        return SENSITIVE_RULES
    emergencias = SENSITIVE_RULES["complaints_or_emergencies"]
    return {"complaints_or_emergencies": {**emergencias, "keywords": EMERGENCY_KEYWORDS},
            "real_time_issues": SENSITIVE_RULES["real_time_issues"]}


# 13-oct (flag `aviso_medico_dice_pase`): el aviso médico PASA la conversación a una persona (Step.ESCALATE en los dos
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
    "es": ("Operamos todos los días del año salvo el 25 de diciembre y el 1 de enero, y la seguridad va primero: si el "
           "mar no está apto, la salida se reprograma. La previsión de un día concreto te la confirma el equipo: te "
           "paso ahora con alguien que te escribe por aquí enseguida."),
    "en": ("We operate every day of the year except December 25 and January 1, and safety comes first: if the sea is "
           "not suitable, the trip is rescheduled. The forecast for a specific day is confirmed by our team: I'm "
           "passing you now to someone who will write to you here shortly."),
}


def _rule_message(rule: dict, lang: str) -> str:
    key = "es" if lang == "es" else "en"
    if f"{key}_v2" in rule:
        return rule[f"{key}_v2"]
    if settings.clima_con_politica and rule is SENSITIVE_RULES.get("weather_conditions"):
        return _CLIMA_CON_POLITICA[key]
    if settings.aviso_medico_dice_pase and rule is SENSITIVE_RULES.get("medical_questions"):
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


def _mensaje_con_contexto(message: str, history: list[dict] | None) -> str:
    """CAL-E5: lo que lee el enrutador LLM de respaldo. Con el flag, los dos últimos mensajes como referencia (para
    que un mensaje referido no pierda a qué se refiere) y después el mensaje de este turno; sin el flag, el mensaje
    tal cual, como siempre."""
    from src.config import settings as _settings

    if not (_settings.jev_con_contexto and history):
        return message
    ultimos = [h for h in history if (h or {}).get("content")][-2:]
    if not ultimos:
        return message
    lineas = "\n".join(
        f"{'Cliente' if h.get('role') == 'user' else 'Bot'}: {str(h['content'])[:400]}" for h in ultimos)
    return (f"Así acabó la conversación, solo para saber a qué se refiere el cliente:\n{lineas}\n\n"
            f"Clasifica SOLO este último mensaje del cliente:\n{message}")


@con_pieza_llm("senales_router")
async def detect_routing_signals(
    message: str, *, lang: str = "es", client: AsyncOpenAI | None = None, pending_slot: str | None = None,
    history: list[dict] | None = None,
) -> dict:
    """Red de precisión para los 3 gates de arriba — solo se llama cuando las
    listas de palabras clave NO encontraron nada (ver supervisor.py). Nunca
    lanza excepción: {} en cualquier error, respuesta rara, o mensaje vacío,
    para que el caller siga con el comportamiento anterior (las listas)."""
    if not message or not message.strip():
        return {}
    # U3 (u3-1): Jev contesta las mismas 9 señales en ~0,27 s. Si está apagado, no hay
    # clave o falla, sigue el router LLM de siempre (y el turno lo apunta en su resumen).
    # Si Jev DUDA (cascada por confianza), decide el router LLM: la conducta de hoy.
    turn_signals: dict = {}
    if settings.jev_router_enabled and client is None:
        from src.agents.jev_router import ASKS_QUESTION, UNCERTAIN, detect_routing_signals_jev_full
        from src.observability import note_turn

        t0 = time.perf_counter()
        jev, turn_signals = await detect_routing_signals_jev_full(
            message, lang=lang, pending_slot=pending_slot, history=history)
        if isinstance(turn_signals, bool):  # contrato anterior (solo asks_question)
            turn_signals = {ASKS_QUESTION: True} if turn_signals else {}
        router = "jev" if isinstance(jev, dict) else ("llm_uncertain" if jev == UNCERTAIN else "llm_fallback")
        note_turn(router=router, router_ms=round((time.perf_counter() - t0) * 1000))
        if isinstance(jev, dict):
            return {**jev, **turn_signals}
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.senales_model,
            messages=[
                {"role": "system", "content": routing_system_prompt(lang)},
                # CAL-E5 (flag `jev_con_contexto`): el mismo contexto que Jev. Medido el 16-oct con
                # `scripts/sonda_senales.py`: con los últimos turnos, "Me lo podrías compartir por favor" (tras "se me
                # perdió el número") sube a 0,63 en Jev, cae en la zona de duda y la decide este enrutador, que veía
                # solo el mensaje y decía que no. La mitad del arreglo estaba aquí.
                {"role": "user", "content": _mensaje_con_contexto(message, history)},
            ],
            tools=[ROUTING_TOOL],
            tool_choice={"type": "function", "function": {"name": "detect_routing_signals"}},
            temperature=0.0,
            max_tokens=140,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        args = tool_arguments(tool_calls[0], ROUTING_TOOL) if tool_calls else {}
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        _llm_logger.warning(f"[ESCALATION] routing signals malformed response: {exc}")
        args = {}
    except Exception as exc:  # noqa: BLE001
        _llm_logger.warning(f"[ESCALATION] routing signals error: {exc}")
        args = {}

    # "none" es la opción "nada" de los enums (ex-9b, 19-oct): para el resto del código, como si no viniera.
    result = {k: v for k, v in (args or {}).items() if v not in (None, "", [], {}, "none")}
    if turn_signals:
        # u3-4/u3-5: Jev dudó en las señales del router, pero sus respuestas a "¿hay algo que
        # contestar?" y a los "¿lo afirma?" siguen valiendo (son otras preguntas y el router
        # LLM no las contesta).
        result.update(turn_signals)
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
