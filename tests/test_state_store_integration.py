"""Integration tests for state_store against a real Redis instance.

Requires REDIS_URL pointing at a live Redis (see .env.ci / docker-compose.yml).
Skipped automatically if no Redis is reachable, so local `pytest` runs without
Docker up don't fail — CI always has the `redis` service container.
"""

import pytest

from src import state_store
from src.config import settings
from src.flows.decision_tree import ConversationState, Step


def _redis_available() -> bool:
    import redis as redis_sync

    try:
        redis_sync.from_url(settings.redis_url).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="No Redis instance reachable")


@pytest.fixture(autouse=True)
async def _clean_redis():
    # Reset the module-level client singleton so it's bound to *this* test's
    # event loop — pytest-asyncio uses a fresh loop per test function, and a
    # client created on a previous (now-closed) loop breaks on Windows.
    state_store._redis_client = None
    client = state_store.get_redis()
    yield
    async for key in client.scan_iter(match=f"dp:{settings.app_env}:*"):
        await client.delete(key)
    await client.aclose()
    state_store._redis_client = None


async def test_save_and_load_state_roundtrip():
    state = ConversationState(conversation_id="int-1", step=Step.FREE_TEXT)
    await state_store.save_state("int-1", state)

    loaded = await state_store.load_state("int-1")
    assert loaded is not None
    assert loaded.step == Step.FREE_TEXT
    assert loaded.conversation_id == "int-1"


async def test_load_state_returns_none_when_missing():
    loaded = await state_store.load_state("does-not-exist")
    assert loaded is None


async def test_save_state_adds_to_active_conversations_set():
    state = ConversationState(conversation_id="int-2")
    await state_store.save_state("int-2", state)

    active = await state_store.list_active_conversation_ids()
    assert "int-2" in active


async def test_list_active_conversation_ids_prunes_expired_entries():
    client = state_store.get_redis()
    # Simulate a stale active-set entry whose state key already expired.
    await client.sadd(f"dp:{settings.app_env}:active_conversations", "int-stale")

    active = await state_store.list_active_conversation_ids()
    assert "int-stale" not in active

    still_member = await client.sismember(f"dp:{settings.app_env}:active_conversations", "int-stale")
    assert not still_member


async def test_save_state_refreshes_ttl():
    state = ConversationState(conversation_id="int-3")
    await state_store.save_state("int-3", state)

    client = state_store.get_redis()
    ttl = await client.ttl(f"dp:{settings.app_env}:state:int-3")
    assert 0 < ttl <= settings.conversation_state_ttl_seconds


async def test_delete_state_removes_state_and_active_membership():
    state = ConversationState(conversation_id="int-4")
    await state_store.save_state("int-4", state)

    await state_store.delete_state("int-4")

    assert await state_store.load_state("int-4") is None
    active = await state_store.list_active_conversation_ids()
    assert "int-4" not in active


async def test_poll_started_at_roundtrip():
    await state_store.set_poll_started_at("int-5", 1700000000)
    value = await state_store.get_poll_started_at("int-5")
    assert value == 1700000000


async def test_poll_started_at_defaults_to_zero_when_missing():
    value = await state_store.get_poll_started_at("never-set")
    assert value == 0


async def test_check_and_mark_processed_is_idempotent():
    first = await state_store.check_and_mark_processed("dedupe-key-1")
    second = await state_store.check_and_mark_processed("dedupe-key-1")
    assert first is False  # not previously processed
    assert second is True  # already processed
