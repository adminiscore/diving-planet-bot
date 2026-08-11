"""Voice-note transcription for incoming Chatwoot messages.

When a customer sends an audio (voice note), Chatwoot delivers it as an
attachment with `file_type == "audio"` and a downloadable `data_url`, while the
message `content` is empty. This module downloads that audio and transcribes it
to text via OpenAI, so the transcript can be fed into the existing pipeline
exactly as if the customer had typed it (see docs/archive/audio-voice-transcription-plan.md).

Design notes:
- Never raises: any failure (network, API, empty result) returns None so the
  caller can fall back gracefully instead of crashing the webhook.
- Language is auto-detected by the model (the center is bilingual es/en); a
  hint can be passed but is optional.
"""

from __future__ import annotations

import logging

import httpx
from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai

logger = logging.getLogger("uvicorn.error")

# Friendly fallback when we receive a voice note but cannot transcribe it.
# Sent to the customer so the turn is never silently dropped.
AUDIO_FALLBACK: dict[str, str] = {
    "es": (
        "Recibí tu audio pero no logré entenderlo bien 🙏 "
        "¿Me lo puedes escribir en un mensaje?"
    ),
    "en": (
        "I got your voice note but couldn't quite make it out 🙏 "
        "Could you type it out for me?"
    ),
}

# Max audio we'll download/transcribe. WhatsApp voice notes are small; this
# guards against a pathological/huge file tying up the request.
_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB (OpenAI's per-file limit)
_DOWNLOAD_TIMEOUT = 20.0
_TRANSCRIBE_TIMEOUT = 60.0


def first_audio_attachment(message: dict) -> dict | None:
    """Return the first attachment with file_type == 'audio', or None.

    Works for both the webhook payload (message is the top-level dict) and the
    poller (each message object in the messages API response), since both carry
    the same `attachments` array.
    """
    for att in (message.get("attachments") or []):
        if isinstance(att, dict) and att.get("file_type") == "audio":
            return att
    return None


def _filename_from_url(data_url: str) -> str:
    """Best-effort filename (OpenAI uses the extension to sniff the format)."""
    path = data_url.split("?", 1)[0]
    name = path.rsplit("/", 1)[-1] or "audio"
    # WhatsApp/Chatwoot voice notes are usually .oga/.ogg (opus). If there's no
    # extension the API can still infer from content, but a sane default helps.
    return name if "." in name else f"{name}.ogg"


async def transcribe_audio_bytes(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    lang_hint: str | None = None,
) -> str | None:
    """Transcribe raw audio bytes to text via OpenAI. Returns the transcript
    (stripped) or None on any failure — never raises.

    Shared by `transcribe_audio_url` (Chatwoot voice notes) and the /audio-test
    endpoint (browser mic recordings). The `filename` extension helps OpenAI
    sniff the container format (ogg/webm/mp4/m4a/mp3/wav all supported).
    """
    if not settings.openai_api_key:
        logger.warning("[AUDIO] No OPENAI_API_KEY set; cannot transcribe audio.")
        return None
    if not audio_bytes:
        logger.warning("[AUDIO] Empty audio bytes; nothing to transcribe.")
        return None
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        logger.warning(f"[AUDIO] Audio too large ({len(audio_bytes)} bytes); skipping.")
        return None

    kwargs: dict = {
        "model": settings.openai_transcription_model,
        "file": (filename, audio_bytes),
    }
    if lang_hint:
        kwargs["language"] = lang_hint  # ISO-639-1; optional, model auto-detects otherwise
    try:
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        result = await client.audio.transcriptions.create(**kwargs, timeout=_TRANSCRIBE_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — never let transcription break the caller
        logger.error(f"[AUDIO] Transcription failed: {exc}")
        return None

    text = (getattr(result, "text", "") or "").strip()
    if not text:
        logger.warning("[AUDIO] Transcription returned empty text.")
        return None
    logger.info(f"[AUDIO] Transcribed audio ({len(audio_bytes)} bytes) -> {text[:80]!r}")
    return text


async def transcribe_audio_url(data_url: str, lang_hint: str | None = None) -> str | None:
    """Download an audio file (e.g. a Chatwoot voice-note attachment) and
    transcribe it. Returns the transcript or None on any failure — never raises.
    """
    if not data_url:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(data_url, timeout=_DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            audio_bytes = resp.content
    except httpx.HTTPError as exc:
        logger.error(f"[AUDIO] Download failed url={data_url[:80]}: {exc}")
        return None

    return await transcribe_audio_bytes(audio_bytes, _filename_from_url(data_url), lang_hint)
