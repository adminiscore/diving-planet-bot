"""Detectores y respuestas fijas de la ruta `info` (`info_agent.py`): alcohol y alergias, grupo privado o evento de
empresa, "¿cambia el precio por nacionalidad?" y la elegibilidad por edad.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.intent_detector import IntentDetector
from src.agents.lead_summary import build_lead_summary
from src.config import settings
from src.flows import eligibility
from src.flows.state import ConversationState, Step
from src.knowledge.loader import load_policies

logger = logging.getLogger("uvicorn.error")


intent_detector = IntentDetector()


# Hallazgo (batería sintética contra PRE, 2026-08-26, lote 4, portado de
# pre_gadea v0.21.11): pregunta directa de si se puede tomar alcohol antes
# de bucear — respuesta plana ya conocida
# (`policies.json["no_alcohol_policy"]`), no un tema médico a evaluar caso
# por caso.
# Ventana ampliada 25->60 (hallazgo en vivo, lote 9, 2026-09-02): "queremos
# bucear manana, anoche tomamos algo de alcohol y uno de nosotros es
# alergico a los mariscos" tiene un hueco real de 32 caracteres entre
# "bucear" y "alcohol" (una clausula intermedia normal en español), por
# encima del limite anterior -> el aviso de alcohol se perdia por completo
# cuando llegaba junto con otro tema (alergia) en el mismo mensaje. 60 sigue
# acotado (no hace match a traves de parrafos largos no relacionados) pero
# cubre clausulas intermedias tipicas.
_ALCOHOL_BEFORE_DIVING_RE = re.compile(
    r"\b(?:alcohol|cerveza|tragos?|copas?|vino|licor|beer|alcoholic)\b.{0,60}"
    r"\b(?:bucear|buceo|buzos?|dive|diving)\b"
    r"|\b(?:bucear|buceo|buzos?|dive|diving)\b.{0,60}"
    r"\b(?:alcohol|cerveza|tragos?|copas?|vino|licor|beer|alcoholic)\b",
    re.IGNORECASE,
)

# Palabra de alergia + alérgeno alimentario conocido del catálogo (marisco/
# gluten/nueces/maní/lactosa) -> pregunta de política de comida del tour, ya
# respondida en `policies.json["food_policy"]`. Deliberadamente acotado: una
# alergia sin alérgeno alimentario explícito ("tengo alergias severas, es
# peligroso bucear?") sigue yendo al escalado médico normal.
_ALLERGY_WORD_RE = re.compile(r"\b(?:al[eé]rgic[oa]s?|alergias?|allergic|allergy|allergies)\b", re.IGNORECASE)
_FOOD_ALLERGEN_RE = re.compile(
    r"\b(?:mariscos?|gluten|nueces|man[ií]|cacahuates?|lactosa|"
    r"shellfish|nuts?|peanuts?|dairy|gluten[- ]free)\b",
    re.IGNORECASE,
)


def _alcohol_and_food_policy_answer(msg_lower: str, lang: str) -> str | None:
    """Politica de alcohol y/o de alimentacion segun lo que mencione el mensaje.

    Hallazgo en vivo (lote 9, 2026-09-02): antes eran dos `if` independientes
    con `return` inmediato en cuanto matcheaba el primero -- un mensaje que
    mencionaba AMBOS temas a la vez ("tomamos alcohol anoche y uno de
    nosotros es alergico a los mariscos") solo recibia la politica de
    alcohol (el primer `if`), y la de alergia se perdia por completo. Ahora
    se comprueban los dos y se concatenan si aplican ambos -- ninguno pisa
    al otro. Usado tanto por el nodo `info` como por `_shared_turn_handler`
    (cascada) para que se comporten igual.
    """
    policies = load_policies().get("policies", {})
    parts: list[str] = []
    if _ALCOHOL_BEFORE_DIVING_RE.search(msg_lower):
        text = (policies.get("no_alcohol_policy") or {}).get(lang, "")
        if text:
            parts.append(text)
    # ex-3 (`atajo_alergia_por_rag`): la alergia sola la contesta el RAG (FAQ curada); con alcohol en el mismo
    # mensaje va junta, como hoy (la política de alcohol no está en la base del RAG).
    alergia_por_rag = settings.atajo_alergia_por_rag and not parts
    if not alergia_por_rag and _ALLERGY_WORD_RE.search(msg_lower) and _FOOD_ALLERGEN_RE.search(msg_lower):
        text = (policies.get("food_policy") or {}).get(lang, "")
        if text:
            parts.append(text)
    if not parts:
        return None
    return "\n\n".join(parts)


# Hallazgo en vivo (lote 11, bateria de cobertura tematica, 2026-09-02):
# "somos una empresa y queremos llevar 20 empleados a bucear como evento
# corporativo, es posible?" hacia que RAG generara una respuesta ("necesito
# saber en que hotel se hospedan...") SIN retrieval real -- el juez de
# grounding la rechazo como HALLUCINATED las 2 veces, y el turno se quedaba
# inventando en vez de usar la politica real (`policies.json
# ["private_services"]`: sin precio fijo, se cotiza por WhatsApp). Ademas esa
# politica en crudo NO se puede dar tal cual: lleva el numero de WhatsApp
# +57 320 231515, y la politica ya establecida (owner, 2026-07-20) es que el
# bot NUNCA da el numero de telefono/WhatsApp -- el contacto va siempre por
# el handoff interno de Chatwoot. Mismo patron que `_alcohol_and_food_
# policy_answer`: respuesta determinista, sin pasar por RAG/retrieval, pero
# aqui ademas REDACTADA (no el texto crudo de policies.json) para no filtrar
# el numero, con la misma frase que ya usa `_contact_number_deflection`.
_PRIVATE_GROUP_EVENT_RE = re.compile(
    r"evento\s+corporativo|grupo\s+cerrado|servicio\s+privado|"
    r"team[\s-]?building|"
    r"private\s+(?:event|group|service|charter)|corporate\s+event|"
    r"\b(?:empresa|compa[ñn][ií]a|company)\b.{0,30}\b(?:emplead[oa]s?|"
    r"evento|employees?|event)\b",
    re.IGNORECASE,
)


def _private_group_event_answer(lang: str) -> str:
    if lang == "es":
        return (
            "¡Con gusto! 🌊 Para grupos privados o eventos corporativos coordinamos todo a "
            "medida (instructor disponible, fecha, actividades) — no tiene un precio fijo, "
            "depende del tamaño del grupo y la fecha. Te paso con un asesor del equipo para "
            "armar la cotización."
        )
    return (
        "Happy to help! 🌊 For private groups or corporate events we coordinate everything "
        "custom (available instructor, date, activities) — there's no fixed price, it depends "
        "on group size and date. I'll connect you with an advisor from the team to put "
        "together a quote."
    )


def private_group_event_reply(state: ConversationState) -> str:
    """La respuesta del grupo privado / evento de empresa, la misma desde el supervisor y desde el nodo `info`.

    13-oct (flag `grupo_privado_pase`; hallazgo de ex-3, HISTORY 0.31.17): la respuesta dice "Te paso con un asesor"
    pero no marcaba el pase; solo llegaba a una persona si el cliente contestaba "sí/ok" justo después. Con el flag se
    marca como cualquier otro pase (motivo + resumen para el asesor); `channels/chatwoot` lo ejecuta al enviar."""
    if settings.grupo_privado_pase:
        reason = "grupo privado o evento de empresa: cotización a medida"
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.info("[SUPERVISOR] grupo privado / empresa -> pase a un asesor")
    return _private_group_event_answer(state.language)


# Hallazgo en vivo (lote 12, bateria "natural/deictica", 2026-09-02, conv.
# real 853): "cuanto cuesta el paquete de 7 inmersiones?" (turno 1) ya
# responde con el precio real Y la politica "mismo precio para todos,
# sin cobro extra por la divisa" -- pero "lo mismo pero para mi amigo que
# es colombiano, cambia algo?" (turno 2, referencia deictica a lo que el
# bot ACABA de decir) hacia que RAG intentara re-generar el numero desde
# cero, y ambos intentos ALUCINARON un precio EQUIVOCADO ($630.000 COP,
# el precio de OTRO paquete distinto) -- el juez de grounding los rechazo
# correctamente las 2 veces (asi que no llego al cliente el numero
# incorrecto), pero el turno cayo al fallback generico en vez de
# responder. La pregunta real ("¿cambia el precio por nacionalidad?")
# SIEMPRE tiene la misma respuesta fija (politica de negocio, no depende
# del paquete): no cambia, solo la moneda. Respuesta determinista, sin
# necesidad de recalcular ningun numero -- evita el riesgo de alucinacion
# por completo en vez de confiar en que el juez de grounding la atrape.
# ex-3/ex-9b: esa respuesta fija se apagó con `atajo_nacionalidad_por_rag` (la contesta el RAG con la regla de
# moneda del catálogo) y se borró; el patrón sigue porque `orchestration/router.classify_route` manda la pregunta
# a la ruta INFO.
_SAME_PRICE_DIFFERENT_NATIONALITY_RE = re.compile(
    r"(?:lo\s+mismo|el\s+mismo\s+precio|mismo\s+precio).{0,40}"
    r"(?:colombian[oa]|extranjer[oa]|residente)|"
    r"(?:colombian[oa]|extranjer[oa]).{0,40}(?:cambia|diferente|distinto)|"
    r"same\s+(?:price|thing).{0,40}(?:colombian|foreign)",
    re.IGNORECASE,
)


# Cues that turn an age mention into an eligibility QUESTION we should answer
# from the rules ("puede bucear?", "hay edad mínima?", "can my son dive?").
_AGE_ELIGIBILITY_CUE = re.compile(
    r"(edad\s+m[ií]nima|edad\s+minima|minimum\s+age|hay\s+(?:una\s+)?edad|"
    r"a\s+partir\s+de\s+qu[eé]\s+edad|desde\s+qu[eé]\s+edad|"
    r"\bpued[eo](?:n|s)?\b|\bpodemos\b|\bpodr[íi]a[n]?\b|se\s+puede|es\s+posible|"
    r"\bcan\s+(?:my|he|she|they|the|a|i|we|kids?|children)\b|"
    r"\bis\s+it\s+possible|old\s+enough|too\s+young|"
    r"dejan?\s+(?:bucear|entrar)|permit|allowed|"
    # options / what-can-they-do questions (valuable when a minor is involved)
    r"qu[eé]\s+opciones|qu[eé]\s+(?:actividad(?:es)?|plan(?:es)?)|"
    r"qu[eé]\s+(?:puede[n]?|podemos|pueden)\s+hacer|"
    r"what\s+(?:can|activities|options)|which\s+activities)",
    re.IGNORECASE,
)


_AGE_NUMBER_HINT = re.compile(r"\b\d{1,2}\b")
_AGE_PERSON_REF = re.compile(
    r"\b(mi\s+\w+|hij[oa]s?|niñ[oa]s?|nin[oa]s?|él|ella|ellos|ellas|"
    r"my\s+\w+|son|daughter|kids?|child(?:ren)?|he|she|they)\b",
    re.IGNORECASE,
)


def _looks_like_age_eligibility_question(message: str, state: ConversationState) -> bool:
    """Predicado PURO (read-only) para el router (Fase 2.4, cierre del hueco
    "patrón A" del audit §1.5): aproxima cuándo disparará
    `_maybe_answer_age_eligibility` SIN correr el intent detector ni mutar estado.

    Cue de elegibilidad + o bien un número de 1-2 dígitos plausible como edad, o
    bien una edad ya recordada (`state.detected_ages`) junto a una referencia a
    persona (caso multi-turno). El nodo `info` reproduce la lógica exacta y delega
    en la cascada si no dispara, así que sobre-disparar aquí es seguro (se
    autocorrige); quedarse corto solo mantiene el comportamiento actual (→ booking)
    para ese mensaje concreto, sin regresión."""
    if not _AGE_ELIGIBILITY_CUE.search(message):
        return False
    if _AGE_NUMBER_HINT.search(message):
        return True
    return bool(state.detected_ages) and bool(_AGE_PERSON_REF.search(message))


def _maybe_answer_age_eligibility(message: str, state: ConversationState) -> str | None:
    """Deterministic answer to an age-eligibility question.

    Fires only when the message both mentions a concrete age and reads like an
    eligibility question, so it never hijacks a plain booking phrase like
    "reservar para mi hijo de 14". Returns None otherwise.
    """
    if not _AGE_ELIGIBILITY_CUE.search(message):
        return None
    # NOTE (robustness review H4, deferred): LLM cutover not wired here because this
    # is a pre-dispatch short-circuit; wiring it would double the LLM call on
    # fall-through (the turn is extracted again later by the core).
    intent = intent_detector.detect(message, state)
    ages = sorted({a for a in (intent.ages or []) if 1 <= a <= 99})
    # Persist any age mentioned here so a later follow-up can reuse it (this
    # responder returns before the conversation agent's _apply_detected_intent).
    if ages:
        state.detected_ages = sorted(set((state.detected_ages or []) + ages))
    # Multi-turn: if this message has no age but refers to a specific person
    # ("pero mi hijo puede bucear?" after "mi hijo tiene 9 años"), reuse the
    # remembered age. Guarded by a person reference so a bare "¿puede bucear?"
    # is not answered with a stale age.
    if not ages and _AGE_PERSON_REF.search(message):
        ages = sorted({a for a in (state.detected_ages or []) if 1 <= a <= 99})
    if not ages:
        return None
    lang = state.language or "es"

    if len(ages) >= 2:
        # Several people -> a clear per-person plan (who can do what), using any
        # detected certified count so the divers appear in the breakdown too.
        alloc = intent.group_allocation or state.detected_group_allocation or {}
        certified = int(alloc.get("certified_diving", 0) or 0)
        plans = eligibility.plan_group(certified=certified, noncert_ages=ages)
        header = ("¡Con gusto! Esto es lo que puede hacer cada quien: 🐠\n"
                  if lang == "es" else
                  "Happy to help! Here's what each person can do: 🐠\n")
        body = header + eligibility.format_group_plan(plans, lang)
    else:
        # Single person -> the fuller, warmer eligibility note.
        body = eligibility.age_eligibility_note(ages[0], lang)

    if lang == "es":
        outro = (
            "\n\n¿Quieres que te ayude a armar el plan para tu grupo? "
            "Escribe *reservar* o cuéntame qué actividad les interesa. 🐠"
            "\n\nSi además preguntabas por algo más concreto, cuéntamelo con más detalle "
            "y te confirmo con exactitud."
        )
    else:
        outro = (
            "\n\nWant me to help put together the plan for your group? "
            "Type *book* or tell me which activity you're interested in. 🐠"
            "\n\nIf you were also asking about something more specific, tell me more "
            "and I'll confirm the exact details."
        )
    # Stay conversational: leave the welcome/language step so a later reply isn't
    # misread, but don't force menu buttons.
    if state.step in (Step.WELCOME, Step.LANGUAGE):
        state.step = Step.MAIN_MENU
    state.quick_replies = []
    return body + outro
