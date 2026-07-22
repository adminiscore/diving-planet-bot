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
from dataclasses import asdict

import redis.asyncio as redis

from src.agents.intent_detector import DetectedIntent
from src.config import settings
from src.flows.decision_tree import ConversationState, Step

_redis_client: redis.Redis | None = None

_STATE_TTL = settings.conversation_state_ttl_seconds
_PROCESSED_TTL = 3600  # 1 hour: dedup only needs to survive the webhook/poll race window

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


def deserialize_state(raw: str) -> ConversationState:
    data = json.loads(raw)
    data["step"] = Step(data["step"])
    data["back_step_override"] = Step(data["back_step_override"]) if data["back_step_override"] else None
    data["mixed_booking_links"] = [tuple(item) for item in data["mixed_booking_links"]]

    wrapped_intent = data["pending_intent_confirmation"]
    if wrapped_intent is not None:
        data["pending_intent_confirmation"] = DetectedIntent(**wrapped_intent["data"])
    else:
        data["pending_intent_confirmation"] = None

    return ConversationState(**data)


async def load_state(conversation_id: str) -> ConversationState | None:
    client = get_redis()
    raw = await client.get(_STATE_KEY.format(id=conversation_id))
    if raw is None:
        return None
    return deserialize_state(raw)


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
