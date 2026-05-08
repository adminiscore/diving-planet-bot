"""
Chatwoot webhook handler.

Receives incoming messages from Chatwoot and routes them through
the decision tree or LangGraph agents.
"""

import logging
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, Request, HTTPException

from src.config import settings
from src.flows.decision_tree import ConversationState
from src.agents.supervisor import route_message

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

# In-memory conversation states (will migrate to Redis/PostgreSQL later)
conversations: dict[str, ConversationState] = {}


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

    if event == "message_created":
        await handle_message(payload)
    elif event == "conversation_created":
        logger.info(f"[WEBHOOK] New conversation: {payload.get('id')}")
    elif event == "conversation_status_changed":
        logger.info("[WEBHOOK] Status changed")

    return {"status": "ok"}


async def handle_message(payload: dict):
    """Process an incoming message from a customer."""
    message = payload.get("content", "")
    message_type = payload.get("message_type")
    conversation = payload.get("conversation", {})
    conversation_id = str(conversation.get("id", ""))
    sender = payload.get("sender", {})

    # Chatwoot sends message_type as integer: 0=incoming, 1=outgoing, 2=activity
    # Only process incoming messages (from customer)
    if message_type not in ("incoming", 0):
        logger.info(f"[WEBHOOK] Skipping non-incoming message_type={message_type}")
        return

    logger.info(f"[BOT] Incoming from {sender.get('name', 'unknown')}: {message[:100]}")

    # Get or create conversation state
    if conversation_id not in conversations:
        conversations[conversation_id] = ConversationState(
            conversation_id=conversation_id,
            language=settings.default_language,
        )

    state = conversations[conversation_id]

    # Route through supervisor (decision tree + RAG)
    response = await route_message(state, message)

    # Send response back via Chatwoot API
    if response:
        await send_chatwoot_message(conversation_id, response)


async def send_chatwoot_message(conversation_id: str, message: str):
    """Send a message back to the customer via Chatwoot API."""
    base_url = settings.chatwoot_base_url.rstrip("/")
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
