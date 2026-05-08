import pytest

from src.channels import chatwoot


class DummyResponse:
    def raise_for_status(self):
        return None


class DummyAsyncClient:
    captured_payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, json, headers, timeout):
        DummyAsyncClient.captured_payload = json
        return DummyResponse()


@pytest.mark.asyncio
async def test_send_chatwoot_message_uses_input_select_buttons(monkeypatch):
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", DummyAsyncClient)

    await chatwoot.send_chatwoot_message(
        "1",
        "What would you like to do?",
        [
            {"title": "Diving and snorkel tours", "value": "1"},
            {"title": "PADI courses", "value": "2"},
        ],
    )

    payload = DummyAsyncClient.captured_payload
    assert payload["content_type"] == "input_select"
    assert payload["content_attributes"] == {
        "items": [
            {"title": "Diving and snorkel tours", "value": "1"},
            {"title": "PADI courses", "value": "2"},
        ],
    }


def test_extract_incoming_content_reads_submitted_values():
    payload = {
        "message_type": "template",
        "content_attributes": {
            "items": [
                {"title": "Espa?ol", "value": "1"},
                {"title": "English", "value": "2"},
            ],
            "submitted_values": [
                {"title": "Espa?ol", "value": "1"},
            ],
        },
    }

    assert chatwoot.extract_incoming_content(payload) == "1"


def test_extract_incoming_content_ignores_unsubmitted_template():
    payload = {
        "message_type": "template",
        "content_attributes": {
            "items": [{"title": "Espa?ol", "value": "1"}],
        },
    }

    assert chatwoot.extract_incoming_content(payload) is None


def test_extract_incoming_content_reads_plain_incoming_message():
    payload = {
        "message_type": "incoming",
        "content": "somos una familia de 6",
    }

    assert chatwoot.extract_incoming_content(payload) == "somos una familia de 6"


@pytest.mark.asyncio
async def test_webhook_marks_incoming_as_processed(monkeypatch):
    sent = []

    async def fake_route_message(state, message):
        return "response"

    async def fake_send_message(conversation_id, message, quick_replies=None):
        sent.append((conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "route_message", fake_route_message)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)
    chatwoot.conversations.clear()
    chatwoot.processed_chatwoot_messages.clear()

    await chatwoot.handle_message({
        "id": 123,
        "message_type": "incoming",
        "content": "hola",
        "conversation": {"id": 99},
        "sender": {"name": "test"},
    })

    assert "99:123:incoming" in chatwoot.processed_chatwoot_messages
    assert sent == [("99", "response", [])]
