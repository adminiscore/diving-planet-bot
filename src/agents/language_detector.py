"""
LLM fallback for language detection at the welcome step.

The stopword heuristic in `src.flows.catalog._detect_language_from_text`
catches the vast majority of first messages instantly and for free (greetings,
common words). This module is only called when that heuristic finds no
signal at all, so we still avoid asking "Español/English" for a message that
genuinely reveals the language but uses words outside the curated list.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai
from src.prompts.booking import LANGUAGE_DETECT_PROMPT

logger = logging.getLogger("uvicorn.error")


async def detect_language_llm(message: str) -> str | None:
    """Return "es" or "en", or None if detection fails / is inconclusive."""
    if not message or not message.strip():
        return None

    try:
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": LANGUAGE_DETECT_PROMPT.format(message=message)}],
            temperature=0.0,
            max_tokens=5,
        )
        raw = (response.choices[0].message.content or "").strip().lower().strip('"').strip("'")
        if raw in ("es", "en"):
            return raw
        logger.info(f"[LANG_DETECT] unrecognized LLM response {raw!r} for msg={message[:40]!r}")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[LANG_DETECT] LLM detection failed: {exc}")
        return None
