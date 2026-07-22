"""
Chatwoot webhook handler.

Receives incoming messages from Chatwoot and routes them through
the decision tree or LangGraph agents.
"""

import asyncio
import json
import logging
from time import time
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException, Request

from src import state_store
from src.agents.escalation import escalate_to_human
from src.agents.supervisor import route_message
from src.channels.audio import AUDIO_FALLBACK, first_audio_attachment, transcribe_audio_url
from src.config import settings
from src.flows.decision_tree import MESSAGE_SPLIT, ConversationState

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

# Button titles sent as quick replies, keyed by conversation.
# Used to suppress the automatic incoming-echo message Chatwoot creates when a user
# clicks a button (Chatwoot sends both a message_updated with submitted_values AND a
# message_created with the button title as content; we only want to process one of them).
# Kept in-memory (not Redis): only suppresses a 1-2s echo race, self-heals on the next
# turn if lost to a restart.
conversation_pending_echo_titles: dict[str, set[str]] = {}

# Per-conversation locks guarding the load -> route_message -> save sequence against
# the webhook handler and the 1s poller racing on the same conversation. Pure
# in-process concurrency control, not data — fine to lose on restart.
_conversation_locks: dict[str, asyncio.Lock] = {}


def _lock_for(conversation_id: str) -> asyncio.Lock:
    return _conversation_locks.setdefault(conversation_id, asyncio.Lock())


async def _resolve_voice_note(
    conversation_id: str,
    state: ConversationState,
    message_dict: dict,
    current_text: str | None,
) -> str | None:
    """Turn an incoming voice note into text so it can flow through the normal
    pipeline as if the customer had typed it.

    Shared by BOTH ingestion paths (webhook `handle_message` and the 1s poller),
    so audio works no matter which one delivers the message.

    Returns:
    - the text to route (the original typed text, or the transcript of a voice
      note), or
    - None if it was a voice note we could NOT transcribe — in that case a
      friendly fallback has already been sent to the customer, and the caller
      must skip routing this turn.
    """
    if (current_text or "").strip():
        return current_text  # normal typed text — untouched
    audio = first_audio_attachment(message_dict)
    if not (audio and audio.get("data_url")):
        return current_text  # not a voice note (image/system/empty) — unchanged behavior
    transcript = await transcribe_audio_url(audio["data_url"])
    if transcript:
        logger.info(f"[BOT] conv={conversation_id} voice note transcribed -> {transcript[:80]!r}")
        return transcript
    lang = state.language if state.language in AUDIO_FALLBACK else "es"
    await send_chatwoot_message(conversation_id, AUDIO_FALLBACK[lang])
    logger.info(f"[BOT] conv={conversation_id} voice note transcription failed; sent fallback")
    return None


def _is_plausible_typed_reply(content_lower: str) -> bool:
    """True if the content could be a genuine free-text reply the user typed,
    so it must NEVER be swallowed as a phantom button-echo.

    The echo-suppression matches on button *titles*. Some titles collide with
    what a user would legitimately type: bare numbers on quantity menus
    ("1".."5"), "0"/"ninguno" on the kids menus, "6+", and yes/no on qualifier
    menus. Typing any of these must reach the tree, not be dropped. Real button
    *clicks* are unaffected — they still carry submitted_values and go through
    the interactive path before this check runs.
    """
    if content_lower in {"si", "sí", "no", "0", "6+", "ninguno", "ninguna", "none"}:
        return True
    return content_lower.isdigit()


@router.post("/chatwoot")
async def chatwoot_webhook(request: Request):
    """
    Webhook endpoint that Chatwoot calls when a new message arrives.

    Chatwoot sends events like:
    - message_created: New message from customer or agent
    - conversation_created: New conversation started
    - conversation_status_changed: Conversation opened/resolved/pending
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")
    logger.info(f"[WEBHOOK] Event: {event}, message_type: {payload.get('message_type')}")

    if event in ("message_created", "message_updated"):
        await handle_message(payload)
    elif event == "conversation_created":
        logger.info(f"[WEBHOOK] New conversation: {payload.get('id')}")
    elif event == "conversation_status_changed":
        logger.info("[WEBHOOK] Status changed")

    return {"status": "ok"}


async def handle_message(payload: dict):
    """Process an incoming message from a customer."""
    message_type = payload.get("message_type")
    conversation = payload.get("conversation", {})
    conversation_id = str(conversation.get("id") or payload.get("conversation_id") or "")
    sender = payload.get("sender", {})

    message = extract_incoming_content(payload)
    if message is None:
        logger.info(f"[WEBHOOK] Skipping non-actionable message_type={message_type}")
        return

    message_id = str(payload.get("id"))
    if message_type in ("incoming", 0):
        content_lower = (payload.get("content", "") or "").strip().lower()
        pending = conversation_pending_echo_titles.get(conversation_id, set())
        # Only suppress the automatic button-echo message for titles that are
        # unlikely to be genuine free-text replies. Numbers, yes/no, "ninguno"
        # etc. must be processed normally even if they match a button title
        # (see _is_plausible_typed_reply).
        if content_lower and content_lower in pending and not _is_plausible_typed_reply(content_lower):
            pending.discard(content_lower)
            await state_store.check_and_mark_processed(f"{conversation_id}:{message_id}:incoming")
            logger.info(f"[WEBHOOK] Skipping button echo: {content_lower[:60]}")
            return
        dedupe_key = f"{conversation_id}:{message_id}:incoming"
        if await state_store.check_and_mark_processed(dedupe_key):
            logger.info(f"[WEBHOOK] Skipping already processed incoming message={message_id}")
            return
    else:
        dedupe_key = f"{conversation_id}:{message_id}:{message}"
        if await state_store.check_and_mark_processed(dedupe_key):
            logger.info(f"[WEBHOOK] Skipping already processed interactive message={message_id}")
            return

    logger.info(f"[BOT] Incoming from {sender.get('name', 'unknown')}: {message[:100]}")

    async with _lock_for(conversation_id):
        # Get or create conversation state
        state = await state_store.load_state(conversation_id)
        if state is None:
            state = ConversationState(
                conversation_id=conversation_id,
                language=settings.default_language,
            )
            await state_store.set_poll_started_at(conversation_id, int(time()))
            if settings.chatwoot_owner_agent_id:
                await assign_conversation_to_owner(conversation_id)

        # Voice note: transcribe now that state (and its language) is loaded. On
        # failure, a fallback was already sent — skip routing this turn.
        message = await _resolve_voice_note(conversation_id, state, payload, message)
        if message is None:
            await state_store.save_state(conversation_id, state)
            return

        # Route through supervisor (decision tree + RAG)
        response = await route_message(state, message)

        await finalize_chatwoot_delivery(conversation_id, state, response)
        await state_store.save_state(conversation_id, state)


async def poll_chatwoot_interactions():
    while True:
        try:
            await poll_active_conversations_once()
        except Exception as e:
            logger.error(f"[BOT] Chatwoot interaction poll error: {e}")
        await asyncio.sleep(1.0)


async def poll_active_conversations_once():
    conversation_ids = await state_store.list_active_conversation_ids()
    if not conversation_ids:
        return

    base_url = settings.chatwoot_api_url.rstrip("/")
    headers = {"api_access_token": settings.chatwoot_api_token}

    async with httpx.AsyncClient() as client:
        for conversation_id in conversation_ids:
            async with _lock_for(conversation_id):
                state = await state_store.load_state(conversation_id)
                if state is None:
                    continue

                poll_started_at = await state_store.get_poll_started_at(conversation_id)

                url = (
                    f"{base_url}/api/v1/accounts/{settings.chatwoot_account_id}"
                    f"/conversations/{conversation_id}/messages"
                )
                resp = await client.get(url, headers=headers, timeout=10.0)
                resp.raise_for_status()
                messages = resp.json().get("payload", [])
                routed = False
                for chatwoot_message in reversed(messages):
                    message_id = str(chatwoot_message.get("id"))
                    message_type = chatwoot_message.get("message_type")
                    created_at = int(chatwoot_message.get("created_at") or 0)
                    if created_at and created_at < poll_started_at:
                        continue
                    selected = extract_submitted_value(chatwoot_message)

                    if selected is not None:
                        dedupe_key = f"{conversation_id}:{message_id}:{selected}"
                        if await state_store.check_and_mark_processed(dedupe_key):
                            continue

                        logger.info(f"[BOT] Processing Chatwoot button conv={conversation_id} message_id={message_id} value={selected}")
                        response = await route_message(state, selected)
                        await finalize_chatwoot_delivery(conversation_id, state, response)
                        routed = True
                        continue

                    if message_type not in ("incoming", 0):
                        continue

                    content = chatwoot_message.get("content", "")
                    content_lower = (content or "").strip().lower()
                    dedupe_key = f"{conversation_id}:{message_id}:incoming"
                    if await state_store.check_and_mark_processed(dedupe_key):
                        continue

                    pending = conversation_pending_echo_titles.get(conversation_id, set())
                    if content_lower and content_lower in pending and not _is_plausible_typed_reply(content_lower):
                        pending.discard(content_lower)
                        logger.info(f"[BOT] Skipping button echo from poll: {content_lower[:60]}")
                        continue

                    # Voice note delivered via the poller (not the webhook):
                    # transcribe it. On failure the fallback was already sent.
                    content = await _resolve_voice_note(conversation_id, state, chatwoot_message, content)
                    if content is None:
                        routed = True
                        continue

                    logger.info(f"[BOT] Processing polled incoming conv={conversation_id} message_id={message_id}: {content[:100]}")
                    response = await route_message(state, content)
                    await finalize_chatwoot_delivery(conversation_id, state, response)
                    routed = True

                if routed:
                    await state_store.save_state(conversation_id, state)


async def finalize_chatwoot_delivery(conversation_id: str, state: ConversationState, response: str | None):
    note = state.pending_note
    reason = state.pending_escalation_reason

    if note:
        await send_chatwoot_note(conversation_id, note)
        state.pending_note = None

    if reason:
        handoff_ok = await escalate_to_human(conversation_id, reason, summary=note or "")
        if handoff_ok:
            state.pending_escalation_reason = None

    if response:
        # Si la respuesta contiene un separador especial, la dividimos en mensajes
        # independientes. Los quick_replies solo se adjuntan al último mensaje para
        # que los botones aparezcan junto al prompt final.
        if MESSAGE_SPLIT in response:
            parts = [p.strip() for p in response.split(MESSAGE_SPLIT) if p.strip()]
            for i, part in enumerate(parts):
                qr = state.quick_replies if i == len(parts) - 1 else None
                await send_chatwoot_message(conversation_id, part, qr)
        else:
            await send_chatwoot_message(conversation_id, response, state.quick_replies)


def extract_submitted_value(payload: dict) -> str | None:
    attributes = payload.get("content_attributes") or {}
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except json.JSONDecodeError:
            attributes = {}

    submitted_values = attributes.get("submitted_values") or []
    if not submitted_values:
        return None

    selected = submitted_values[-1]
    return str(selected.get("value") or selected.get("title") or "")


def extract_incoming_content(payload: dict) -> str | None:
    message_type = payload.get("message_type")
    if message_type in ("incoming", 0):
        return payload.get("content", "")

    return extract_submitted_value(payload)


async def assign_conversation_to_owner(conversation_id: str):
    """Assign a new conversation to the owner agent and set it to open so it appears in 'Mine'."""
    base_url = settings.chatwoot_api_url.rstrip("/")
    headers = {
        "api_access_token": settings.chatwoot_api_token,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        # Assign to owner
        assign_url = (
            f"{base_url}/api/v1/accounts/{settings.chatwoot_account_id}"
            f"/conversations/{conversation_id}/assignments"
        )
        try:
            resp = await client.post(
                assign_url,
                json={"assignee_id": settings.chatwoot_owner_agent_id},
                headers=headers,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[BOT] Conversation {conversation_id} assigned to agent {settings.chatwoot_owner_agent_id}")
        except httpx.HTTPError as e:
            logger.error(f"[BOT] Assignment error conv={conversation_id}: {e}")

        # Set status to open so it appears in the agent's inbox (not stuck in Pending)
        toggle_url = (
            f"{base_url}/api/v1/accounts/{settings.chatwoot_account_id}"
            f"/conversations/{conversation_id}/toggle_status"
        )
        try:
            resp = await client.post(
                toggle_url,
                json={"status": "open"},
                headers=headers,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[BOT] Conversation {conversation_id} set to open")
        except httpx.HTTPError as e:
            logger.error(f"[BOT] Status toggle error conv={conversation_id}: {e}")


async def send_chatwoot_message(conversation_id: str, message: str, quick_replies: list[dict] | None = None):
    """Send a message back to the customer via Chatwoot API."""
    base_url = settings.chatwoot_api_url.rstrip("/")
    url = (
        f"{base_url}/api/v1/accounts/{settings.chatwoot_account_id}"
        f"/conversations/{conversation_id}/messages"
    )
    headers = {
        "api_access_token": settings.chatwoot_api_token,
        "Content-Type": "application/json",
    }
    payload = {
        "content": message,
        "message_type": 1,  # 1 = outgoing in Chatwoot API
        "private": False,
    }
    if quick_replies:
        payload["content_type"] = "input_select"
        payload["content_attributes"] = {
            "items": [
                {"title": reply["title"], "value": reply["value"]}
                for reply in quick_replies
            ],
        }
        # Register button titles so the automatic incoming echo from Chatwoot is suppressed.
        # Skip titles that are themselves a plausible typed reply (e.g. the bare-number
        # titles on quantity menus, where title == value): suppressing those would eat a
        # user who TYPES the number instead of clicking. Real clicks still work — they
        # carry submitted_values and never depend on this echo set.
        pending = conversation_pending_echo_titles.setdefault(conversation_id, set())
        for reply in quick_replies:
            title = reply.get("title", "").strip().lower()
            value = str(reply.get("value", "")).strip().lower()
            if title and title != value and not _is_plausible_typed_reply(title):
                pending.add(title)

    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"[BOT] Sending Chatwoot message conv={conversation_id} url={url}")
            resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
            resp.raise_for_status()
            logger.info(f"[BOT] Message sent to conversation {conversation_id}")
            return
        except httpx.ConnectError as e:
            parsed = urlparse(url)
            if parsed.hostname == "localhost":
                alt_parsed = parsed._replace(netloc=parsed.netloc.replace("localhost", "127.0.0.1"))
                alt_url = urlunparse(alt_parsed)
                try:
                    logger.warning(
                        f"[BOT] ConnectError to localhost; retrying with 127.0.0.1 conv={conversation_id} url={alt_url} err={e}"
                    )
                    resp = await client.post(alt_url, json=payload, headers=headers, timeout=10.0)
                    resp.raise_for_status()
                    logger.info(f"[BOT] Message sent to conversation {conversation_id}")
                    return
                except httpx.HTTPError as e2:
                    logger.error(f"[BOT] Send error conv={conversation_id} url={alt_url}: {e2}")
                    return

            logger.error(f"[BOT] Send error conv={conversation_id} url={url}: {e}")
        except httpx.HTTPError as e:
            logger.error(f"[BOT] Send error conv={conversation_id} url={url}: {e}")


async def send_chatwoot_note(conversation_id: str, note: str):
    """Send a private internal note to Chatwoot (visible only to agents, not the customer)."""
    base_url = settings.chatwoot_api_url.rstrip("/")
    url = (
        f"{base_url}/api/v1/accounts/{settings.chatwoot_account_id}"
        f"/conversations/{conversation_id}/messages"
    )
    headers = {
        "api_access_token": settings.chatwoot_api_token,
        "Content-Type": "application/json",
    }
    payload = {
        "content": note,
        "message_type": 1,
        "private": True,
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
            resp.raise_for_status()
            logger.info(f"[BOT] Lead note sent conv={conversation_id}")
        except httpx.HTTPError as e:
            logger.error(f"[BOT] Note send error conv={conversation_id}: {e}")
