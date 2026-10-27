"""Detectores y respuestas fijas de la ruta `info` (`info_agent.py`): alcohol y alergias, grupo privado o evento de
empresa y "¿cambia el precio por nacionalidad?". (La elegibilidad por edad se fue el 27-oct, CALN2-04: la contesta el
flujo normal con las edades exactas del código; ver `contexto_rag` y `eligibility.beginner_options_for_age`.)

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.lead_summary import build_lead_summary
from src.domain.politicas import politicas
from src.flows.state import ConversationState, Step

logger = logging.getLogger("uvicorn.error")


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
    policies = politicas()
    parts: list[str] = []
    if _ALCOHOL_BEFORE_DIVING_RE.search(msg_lower):
        text = (policies.get("no_alcohol_policy") or {}).get(lang, "")
        if text:
            parts.append(text)
    # ex-3: la alergia sola la contesta el RAG (FAQ curada); con alcohol en el mismo mensaje va junta (la política de
    # alcohol no está en la base del RAG).
    if parts and _ALLERGY_WORD_RE.search(msg_lower) and _FOOD_ALLERGEN_RE.search(msg_lower):
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
# el numero, con la misma idea que `_contacto_pasa_a_persona` (no se dan números).
_PRIVATE_GROUP_EVENT_RE = re.compile(
    r"evento\s+corporativo|grupo\s+cerrado|servicio\s+privado|"
    r"team[\s-]?building|"
    r"private\s+(?:event|group|service|charter)|corporate\s+event|"
    r"\b(?:empresa|compa[ñn][ií]a|company)\b.{0,30}\b(?:emplead[oa]s?|"
    r"evento|employees?|event)\b",
    re.IGNORECASE,
)


def pide_servicio_privado(msg_lower: str, signals: dict) -> bool:
    """¿El cliente pide un servicio privado (salida, lancha o instructor solo para su grupo, grupo cerrado, evento de
    empresa)? La lista de siempre o (gen-3b, decisión de Gadea: pasa directo en cuanto lo pide) Jev
    (`pide_servicio_privado`). Lo usan el router y el nodo `info`, con el mismo criterio."""
    if _PRIVATE_GROUP_EVENT_RE.search(msg_lower):
        return True
    return (signals or {}).get("pide_servicio_privado") is True


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

    13-oct (`grupo_privado_pase`, promocionado; hallazgo de ex-3, HISTORY 0.31.17): la respuesta dice "Te paso con un
    asesor" pero no marcaba el pase; solo llegaba a una persona si el cliente contestaba "sí/ok" justo después. Se
    marca como cualquier otro pase (motivo + resumen para el asesor); `channels/chatwoot` lo ejecuta al enviar."""
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
