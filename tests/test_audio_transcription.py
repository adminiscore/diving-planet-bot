"""Tests for incoming voice-note transcription (docs/audio-voice-transcription-plan.md).

The OpenAI transcription call and the httpx download are always mocked — these
tests never hit the network or spend a cent.
"""

import pytest

from src.channels import audio, chatwoot


# --------------------------------------------------------------------------- #
# first_audio_attachment
# --------------------------------------------------------------------------- #

def test_first_audio_attachment_finds_audio():
    msg = {"attachments": [
        {"file_type": "image", "data_url": "http://x/img.jpg"},
        {"file_type": "audio", "data_url": "http://x/note.ogg"},
    ]}
    att = audio.first_audio_attachment(msg)
    assert att is not None
    assert att["data_url"] == "http://x/note.ogg"


def test_first_audio_attachment_ignores_non_audio():
    msg = {"attachments": [{"file_type": "image", "data_url": "http://x/img.jpg"}]}
    assert audio.first_audio_attachment(msg) is None


def test_first_audio_attachment_empty():
    assert audio.first_audio_attachment({}) is None
    assert audio.first_audio_attachment({"attachments": []}) is None


# --------------------------------------------------------------------------- #
# transcribe_audio_url
# --------------------------------------------------------------------------- #

class _DummyDownloadResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class _DummyDownloadClient:
    def __init__(self, content=b"FAKE_AUDIO_BYTES"):
        self._content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def get(self, url, timeout):
        return _DummyDownloadResponse(self._content)


class _DummyTranscript:
    def __init__(self, text):
        self.text = text


def _patch_openai(monkeypatch, text="somos 3 y queremos bucear"):
    """Patch AsyncOpenAI so .audio.transcriptions.create returns `text`."""
    captured = {}

    class _Transcriptions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _DummyTranscript(text)

    class _Audio:
        transcriptions = _Transcriptions()

    class _Client:
        def __init__(self, api_key=None):
            self.audio = _Audio()

    monkeypatch.setattr(audio, "AsyncOpenAI", _Client)
    return captured


@pytest.mark.asyncio
async def test_transcribe_audio_url_happy_path(monkeypatch):
    monkeypatch.setattr(audio.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(audio.httpx, "AsyncClient", lambda: _DummyDownloadClient())
    captured = _patch_openai(monkeypatch, text="somos 3 y queremos bucear")

    text = await audio.transcribe_audio_url("http://x/note.ogg")

    assert text == "somos 3 y queremos bucear"
    assert captured["model"] == audio.settings.openai_transcription_model
    # file passed as (filename, bytes) tuple
    assert captured["file"][0].endswith(".ogg")


@pytest.mark.asyncio
async def test_transcribe_audio_url_empty_transcript_returns_none(monkeypatch):
    monkeypatch.setattr(audio.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(audio.httpx, "AsyncClient", lambda: _DummyDownloadClient())
    _patch_openai(monkeypatch, text="   ")

    assert await audio.transcribe_audio_url("http://x/note.ogg") is None


@pytest.mark.asyncio
async def test_transcribe_audio_url_download_failure_returns_none(monkeypatch):
    monkeypatch.setattr(audio.settings, "openai_api_key", "sk-test")

    class _FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, timeout):
            raise audio.httpx.ConnectError("boom")

    monkeypatch.setattr(audio.httpx, "AsyncClient", lambda: _FailingClient())
    assert await audio.transcribe_audio_url("http://x/note.ogg") is None


@pytest.mark.asyncio
async def test_transcribe_audio_url_no_api_key_returns_none(monkeypatch):
    monkeypatch.setattr(audio.settings, "openai_api_key", "")
    assert await audio.transcribe_audio_url("http://x/note.ogg") is None


# --------------------------------------------------------------------------- #
# _resolve_voice_note (shared ingestion helper)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_resolve_voice_note_typed_text_untouched(monkeypatch):
    state = chatwoot.ConversationState(conversation_id="1")
    # Typed text must never trigger transcription.
    result = await chatwoot._resolve_voice_note("1", state, {"content": "hola"}, "hola")
    assert result == "hola"


@pytest.mark.asyncio
async def test_resolve_voice_note_transcribes_audio(monkeypatch):
    async def fake_transcribe(data_url, lang_hint=None):
        return "quiero reservar buceo"

    monkeypatch.setattr(chatwoot, "transcribe_audio_url", fake_transcribe)
    state = chatwoot.ConversationState(conversation_id="1")
    msg = {"attachments": [{"file_type": "audio", "data_url": "http://x/n.ogg"}]}

    result = await chatwoot._resolve_voice_note("1", state, msg, "")
    assert result == "quiero reservar buceo"


@pytest.mark.asyncio
async def test_resolve_voice_note_failed_transcription_sends_fallback(monkeypatch):
    sent = []

    async def fake_transcribe(data_url, lang_hint=None):
        return None

    async def fake_send(conversation_id, message, quick_replies=None):
        sent.append((conversation_id, message))

    monkeypatch.setattr(chatwoot, "transcribe_audio_url", fake_transcribe)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send)

    state = chatwoot.ConversationState(conversation_id="1")
    state.language = "es"
    msg = {"attachments": [{"file_type": "audio", "data_url": "http://x/n.ogg"}]}

    result = await chatwoot._resolve_voice_note("1", state, msg, "")
    assert result is None
    assert len(sent) == 1
    assert sent[0][1] == audio.AUDIO_FALLBACK["es"]


@pytest.mark.asyncio
async def test_resolve_voice_note_fallback_respects_language(monkeypatch):
    sent = []

    async def fake_transcribe(data_url, lang_hint=None):
        return None

    async def fake_send(conversation_id, message, quick_replies=None):
        sent.append(message)

    monkeypatch.setattr(chatwoot, "transcribe_audio_url", fake_transcribe)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send)

    state = chatwoot.ConversationState(conversation_id="1")
    state.language = "en"
    msg = {"attachments": [{"file_type": "audio", "data_url": "http://x/n.ogg"}]}

    await chatwoot._resolve_voice_note("1", state, msg, "")
    assert sent == [audio.AUDIO_FALLBACK["en"]]


@pytest.mark.asyncio
async def test_resolve_voice_note_no_audio_no_text_returns_empty(monkeypatch):
    # An image-only or empty message (no audio) must fall through unchanged.
    state = chatwoot.ConversationState(conversation_id="1")
    msg = {"attachments": [{"file_type": "image", "data_url": "http://x/i.jpg"}]}
    result = await chatwoot._resolve_voice_note("1", state, msg, "")
    assert result == ""


# --------------------------------------------------------------------------- #
# End-to-end through handle_message (webhook path)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_handle_message_transcribes_voice_note_end_to_end(monkeypatch):
    """A voice-note webhook must reach route_message with the transcript."""
    states = {}
    processed = set()
    routed = []

    async def fake_load_state(cid):
        return states.get(cid)

    async def fake_save_state(cid, st):
        states[cid] = st

    async def fake_mark(key):
        if key in processed:
            return True
        processed.add(key)
        return False

    async def fake_set_poll(cid, ts):
        pass

    async def fake_transcribe(data_url, lang_hint=None):
        return "somos 4 certificados"

    async def fake_route(state, message):
        routed.append(message)
        return "ok"

    async def fake_finalize(cid, state, response):
        pass

    monkeypatch.setattr(chatwoot.state_store, "load_state", fake_load_state)
    monkeypatch.setattr(chatwoot.state_store, "save_state", fake_save_state)
    monkeypatch.setattr(chatwoot.state_store, "check_and_mark_processed", fake_mark)
    monkeypatch.setattr(chatwoot.state_store, "set_poll_started_at", fake_set_poll)
    monkeypatch.setattr(chatwoot, "transcribe_audio_url", fake_transcribe)
    monkeypatch.setattr(chatwoot, "route_message", fake_route)
    monkeypatch.setattr(chatwoot, "finalize_chatwoot_delivery", fake_finalize)
    monkeypatch.setattr(chatwoot.settings, "chatwoot_owner_agent_id", 0)

    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "id": 999,
        "conversation": {"id": 77},
        "sender": {"name": "Ana"},
        "content": "",
        "attachments": [{"file_type": "audio", "data_url": "http://x/note.ogg"}],
    }

    await chatwoot.handle_message(payload)

    assert routed == ["somos 4 certificados"]


@pytest.mark.asyncio
async def test_handle_message_failed_voice_note_does_not_route(monkeypatch):
    states = {}
    processed = set()
    routed = []
    sent = []

    async def fake_load_state(cid):
        return states.get(cid)

    async def fake_save_state(cid, st):
        states[cid] = st

    async def fake_mark(key):
        if key in processed:
            return True
        processed.add(key)
        return False

    async def fake_set_poll(cid, ts):
        pass

    async def fake_transcribe(data_url, lang_hint=None):
        return None

    async def fake_route(state, message):
        routed.append(message)
        return "ok"

    async def fake_send(cid, message, quick_replies=None):
        sent.append(message)

    monkeypatch.setattr(chatwoot.state_store, "load_state", fake_load_state)
    monkeypatch.setattr(chatwoot.state_store, "save_state", fake_save_state)
    monkeypatch.setattr(chatwoot.state_store, "check_and_mark_processed", fake_mark)
    monkeypatch.setattr(chatwoot.state_store, "set_poll_started_at", fake_set_poll)
    monkeypatch.setattr(chatwoot, "transcribe_audio_url", fake_transcribe)
    monkeypatch.setattr(chatwoot, "route_message", fake_route)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send)
    monkeypatch.setattr(chatwoot.settings, "chatwoot_owner_agent_id", 0)

    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "id": 1000,
        "conversation": {"id": 78},
        "sender": {"name": "Ana"},
        "content": "",
        "attachments": [{"file_type": "audio", "data_url": "http://x/note.ogg"}],
    }

    await chatwoot.handle_message(payload)

    assert routed == []            # never routed an empty/garbage turn
    assert len(sent) == 1          # fallback sent instead
