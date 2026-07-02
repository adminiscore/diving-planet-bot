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
async def test_finalize_chatwoot_delivery_sends_note_handoff_and_message(monkeypatch):
    actions = []

    async def fake_send_note(conversation_id, note):
        actions.append(("note", conversation_id, note))

    async def fake_escalate(conversation_id, reason, summary=""):
        actions.append(("handoff", conversation_id, reason, summary))
        return True

    async def fake_send_message(conversation_id, message, quick_replies=None):
        actions.append(("message", conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "send_chatwoot_note", fake_send_note)
    monkeypatch.setattr(chatwoot, "escalate_to_human", fake_escalate)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)

    state = chatwoot.ConversationState(conversation_id="55")
    state.pending_note = "lead summary"
    state.pending_escalation_reason = "solicitó asesor"
    state.quick_replies = [{"title": "Volver", "value": "menu"}]

    await chatwoot.finalize_chatwoot_delivery("55", state, "te conecto con el equipo")

    assert actions == [
        ("note", "55", "lead summary"),
        ("handoff", "55", "solicitó asesor", "lead summary"),
        ("message", "55", "te conecto con el equipo", [{"title": "Volver", "value": "menu"}]),
    ]
    assert state.pending_note is None
    assert state.pending_escalation_reason is None


@pytest.mark.asyncio
async def test_finalize_chatwoot_delivery_keeps_pending_reason_when_handoff_fails(monkeypatch):
    actions = []

    async def fake_send_note(conversation_id, note):
        actions.append(("note", conversation_id, note))

    async def fake_escalate(conversation_id, reason, summary=""):
        actions.append(("handoff", conversation_id, reason, summary))
        return False

    async def fake_send_message(conversation_id, message, quick_replies=None):
        actions.append(("message", conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "send_chatwoot_note", fake_send_note)
    monkeypatch.setattr(chatwoot, "escalate_to_human", fake_escalate)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)

    state = chatwoot.ConversationState(conversation_id="77")
    state.pending_note = "lead summary"
    state.pending_escalation_reason = "solicitó asesor"

    await chatwoot.finalize_chatwoot_delivery("77", state, "te conecto con el equipo")

    assert actions == [
        ("note", "77", "lead summary"),
        ("handoff", "77", "solicitó asesor", "lead summary"),
        ("message", "77", "te conecto con el equipo", []),
    ]
    assert state.pending_note is None
    assert state.pending_escalation_reason == "solicitó asesor"


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


@pytest.mark.asyncio
async def test_handle_message_executes_handoff_when_supervisor_escalates(monkeypatch):
    actions = []

    async def fake_route_message(state, message):
        state.pending_note = "lead note"
        state.pending_escalation_reason = "medical_questions"
        return "te conecto con el equipo"

    async def fake_send_note(conversation_id, note):
        actions.append(("note", conversation_id, note))

    async def fake_escalate(conversation_id, reason, summary=""):
        actions.append(("handoff", conversation_id, reason, summary))
        return True

    async def fake_send_message(conversation_id, message, quick_replies=None):
        actions.append(("message", conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "route_message", fake_route_message)
    monkeypatch.setattr(chatwoot, "send_chatwoot_note", fake_send_note)
    monkeypatch.setattr(chatwoot, "escalate_to_human", fake_escalate)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)
    chatwoot.conversations.clear()
    chatwoot.processed_chatwoot_messages.clear()

    await chatwoot.handle_message({
        "id": 999,
        "message_type": "incoming",
        "content": "estoy embarazada, puedo bucear?",
        "conversation": {"id": 321},
        "sender": {"name": "test"},
    })

    assert actions == [
        ("note", "321", "lead note"),
        ("handoff", "321", "medical_questions", "lead note"),
        ("message", "321", "te conecto con el equipo", []),
    ]


@pytest.mark.asyncio
async def test_finalize_chatwoot_delivery_splits_message_on_sentinel(monkeypatch):
    """MESSAGE_SPLIT sentinel must produce two separate send_chatwoot_message calls.
    Quick replies are attached only to the last part.
    """
    from src.flows.decision_tree import MESSAGE_SPLIT, ConversationState
    from src.channels.chatwoot import finalize_chatwoot_delivery

    sent = []

    async def fake_send(conversation_id, message, quick_replies=None):
        sent.append((conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send)

    state = ConversationState(conversation_id="test-split")
    state.quick_replies = [{"title": "Sí", "value": "1"}]

    response = f"Primera parte del itinerario{MESSAGE_SPLIT}¿Quieres saber algo más?"
    await finalize_chatwoot_delivery("42", state, response)

    assert len(sent) == 2, "Should dispatch exactly 2 messages when MESSAGE_SPLIT present"
    assert sent[0] == ("42", "Primera parte del itinerario", None)
    assert sent[1] == ("42", "¿Quieres saber algo más?", [{"title": "Sí", "value": "1"}])


@pytest.mark.asyncio
async def test_finalize_chatwoot_delivery_single_message_without_sentinel(monkeypatch):
    """Without MESSAGE_SPLIT, a single send_chatwoot_message call is made with quick_replies."""
    from src.flows.decision_tree import ConversationState
    from src.channels.chatwoot import finalize_chatwoot_delivery

    sent = []

    async def fake_send(conversation_id, message, quick_replies=None):
        sent.append((conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send)

    state = ConversationState(conversation_id="test-single")
    state.quick_replies = [{"title": "Ok", "value": "1"}]

    await finalize_chatwoot_delivery("99", state, "Respuesta normal sin split")

    assert len(sent) == 1
    assert sent[0] == ("99", "Respuesta normal sin split", [{"title": "Ok", "value": "1"}])
