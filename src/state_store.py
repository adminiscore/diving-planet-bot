"""
Redis-backed persistence for conversation state.

Replaces the in-memory dicts that used to live in src/channels/chatwoot.py
(conversations, processed_chatwoot_messages, conversation_poll_started_at),
which were wiped on every process restart/deploy — the root cause of the
"stuck conversation" bug. `conversation_pending_echo_titles` intentionally
stays in-memory (see chatwoot.py) — it only suppresses a 1-2s button echo
and is self-healing if lost.
"""

import json
import logging
from dataclasses import asdict, fields

import redis.asyncio as redis

from src.agents.intent_detector import DetectedIntent
from src.config import settings
from src.flows.state import ConversationState, Step

logger = logging.getLogger("uvicorn.error")

_redis_client: redis.Redis | None = None

_CONVERSATION_STATE_FIELDS = {f.name for f in fields(ConversationState)}
_DETECTED_INTENT_FIELDS = {f.name for f in fields(DetectedIntent)}


def _drop_unknown_fields(data: dict, known: set[str], *, cls_name: str, conversation_id: str = "") -> dict:
    """Descarta claves de un dict deserializado que ya no son campos validos
    del dataclass -- hallazgo en vivo (2026-09-10): un campo eliminado por
    limpieza de codigo muerto (`mixed_pending_course_question`, borrado
    2026-07-29, ver docs/multi-agent-refactor-plan.md) sigue vivo en estados
    viejos guardados en Redis (TTL largo, `conversation_state_ttl_seconds`),
    y `ConversationState(**data)`/`DetectedIntent(**data)` fallaban con
    TypeError en CADA poll de esa conversacion, para siempre, hasta que
    expirara el TTL. Esto hace la deserializacion forward-compatible con
    cualquier limpieza futura de campos muertos, sin perder el resto del
    estado."""
    unknown = data.keys() - known
    if unknown:
        logger.warning(
            f"[STATE_STORE] descartando campos desconocidos al deserializar {cls_name} "
            f"(conv={conversation_id!r}): {sorted(unknown)}"
        )
    return {k: v for k, v in data.items() if k in known}

_STATE_TTL = settings.conversation_state_ttl_seconds
# El dedup debe sobrevivir TANTO como la ventana en la que el mensaje puede
# volver a leerse, y esa ventana es la vida del estado (30 dias), no unos
# segundos de carrera webhook/poll.
#
# INCIDENTE REAL (PRE, detectado 2026-09-11): este valor era 3600 con el
# comentario "1 hour: dedup only needs to survive the webhook/poll race
# window". Esa suposicion es falsa: `poll_active_conversations_once`
# (channels/chatwoot.py) recorre CADA conversacion del set activo cada
# segundo y RELEE todos sus mensajes desde Chatwoot. Pasada 1 hora, el
# marcador de "ya respondi a este mensaje" caducaba, el mensaje volvia a
# parecer nuevo, y el bot lo respondia OTRA VEZ -- indefinidamente, mientras
# el estado siguiera vivo (30 dias). La guarda de antiguedad
# (`created_at < poll_started_at`) no protege de esto: solo descarta
# mensajes anteriores a cuando se empezo a vigilar la conversacion, no los
# que ya se respondieron.
#
# Efecto medido: ~110 mensajes/hora reprocesados de forma constante las 24h
# (incluida la madrugada), sobre conversaciones de hace dias, con respuesta
# ENVIADA a Chatwoot en proporcion 1:1. Son ~2.600 mensajes/dia ~= 14.000
# peticiones a OpenAI, que por si solas superan el limite de 10.000 RPD de
# la cuenta -- de ahi los agotamientos de cuota del 10 y el 11 de septiembre.
# En produccion habria sido reenviar respuestas a clientes reales cada hora.
_PROCESSED_TTL = _STATE_TTL

_PREFIX = f"dp:{settings.app_env}:"
_STATE_KEY = _PREFIX + "state:{id}"
_POLL_STARTED_KEY = _PREFIX + "poll_started:{id}"
_PROCESSED_KEY = _PREFIX + "processed:{key}"
_ACTIVE_SET_KEY = _PREFIX + "active_conversations"


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def serialize_state(state: ConversationState) -> str:
    data = asdict(state)
    data["step"] = state.step.value
    data["back_step_override"] = state.back_step_override.value if state.back_step_override else None

    intent = state.pending_intent_confirmation
    if intent is not None:
        data["pending_intent_confirmation"] = {
            "type": "DetectedIntent",
            "data": asdict(intent),
        }
    else:
        data["pending_intent_confirmation"] = None

    return json.dumps(data)


def deserialize_state(raw: str, conversation_id: str = "") -> ConversationState:
    data = json.loads(raw)
    data["step"] = Step(data["step"])
    data["back_step_override"] = Step(data["back_step_override"]) if data["back_step_override"] else None
    data["mixed_booking_links"] = [tuple(item) for item in data["mixed_booking_links"]]

    wrapped_intent = data["pending_intent_confirmation"]
    if wrapped_intent is not None:
        intent_data = _drop_unknown_fields(
            wrapped_intent["data"], _DETECTED_INTENT_FIELDS,
            cls_name="DetectedIntent", conversation_id=conversation_id,
        )
        data["pending_intent_confirmation"] = DetectedIntent(**intent_data)
    else:
        data["pending_intent_confirmation"] = None

    data = _drop_unknown_fields(
        data, _CONVERSATION_STATE_FIELDS, cls_name="ConversationState", conversation_id=conversation_id,
    )
    return ConversationState(**data)


async def load_state(conversation_id: str) -> ConversationState | None:
    client = get_redis()
    raw = await client.get(_STATE_KEY.format(id=conversation_id))
    if raw is None:
        return None
    return deserialize_state(raw, conversation_id)


async def save_state(conversation_id: str, state: ConversationState) -> None:
    client = get_redis()
    raw = serialize_state(state)
    await client.set(_STATE_KEY.format(id=conversation_id), raw, ex=_STATE_TTL)
    await client.sadd(_ACTIVE_SET_KEY, conversation_id)


async def delete_state(conversation_id: str) -> None:
    client = get_redis()
    await client.delete(_STATE_KEY.format(id=conversation_id))
    await client.delete(_POLL_STARTED_KEY.format(id=conversation_id))
    await client.srem(_ACTIVE_SET_KEY, conversation_id)


async def list_active_conversation_ids() -> list[str]:
    """Active conversation ids, self-pruning entries whose state already expired."""
    client = get_redis()
    ids = await client.smembers(_ACTIVE_SET_KEY)
    if not ids:
        return []

    active: list[str] = []
    stale: list[str] = []
    for conversation_id in ids:
        exists = await client.exists(_STATE_KEY.format(id=conversation_id))
        if exists:
            active.append(conversation_id)
        else:
            stale.append(conversation_id)

    if stale:
        await client.srem(_ACTIVE_SET_KEY, *stale)

    return active


async def get_poll_started_at(conversation_id: str) -> int:
    client = get_redis()
    value = await client.get(_POLL_STARTED_KEY.format(id=conversation_id))
    return int(value) if value is not None else 0


async def set_poll_started_at(conversation_id: str, epoch_seconds: int) -> None:
    client = get_redis()
    await client.set(_POLL_STARTED_KEY.format(id=conversation_id), str(epoch_seconds), ex=_STATE_TTL)


async def check_and_mark_processed(dedupe_key: str) -> bool:
    """Atomically check-and-mark a dedup key. Returns True if it was already processed."""
    client = get_redis()
    was_set = await client.set(_PROCESSED_KEY.format(key=dedupe_key), "1", ex=_PROCESSED_TTL, nx=True)
    return not was_set
