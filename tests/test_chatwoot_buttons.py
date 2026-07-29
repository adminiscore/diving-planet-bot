import pytest

from src.channels import chatwoot


@pytest.fixture
def fake_store(monkeypatch):
    """In-memory stand-in for state_store, so these tests don't need real Redis."""
    states = {}
    processed = set()
    poll_started = {}

    async def fake_load_state(conversation_id):
        return states.get(conversation_id)

    async def fake_save_state(conversation_id, state):
        states[conversation_id] = state

    async def fake_check_and_mark_processed(dedupe_key):
        if dedupe_key in processed:
            return True
        processed.add(dedupe_key)
        return False

    async def fake_set_poll_started_at(conversation_id, epoch_seconds):
        poll_started[conversation_id] = epoch_seconds

    async def fake_get_poll_started_at(conversation_id):
        return poll_started.get(conversation_id, 0)

    async def fake_list_active_conversation_ids():
        return list(states.keys())

    monkeypatch.setattr(chatwoot.state_store, "load_state", fake_load_state)
    monkeypatch.setattr(chatwoot.state_store, "save_state", fake_save_state)
    monkeypatch.setattr(chatwoot.state_store, "check_and_mark_processed", fake_check_and_mark_processed)
    monkeypatch.setattr(chatwoot.state_store, "set_poll_started_at", fake_set_poll_started_at)
    monkeypatch.setattr(chatwoot.state_store, "get_poll_started_at", fake_get_poll_started_at)
    monkeypatch.setattr(chatwoot.state_store, "list_active_conversation_ids", fake_list_active_conversation_ids)
    return {"states": states, "processed": processed, "poll_started": poll_started}


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
async def test_webhook_marks_incoming_as_processed(monkeypatch, fake_store):
    sent = []

    async def fake_route_message(state, message):
        return "response"

    async def fake_send_message(conversation_id, message, quick_replies=None):
        sent.append((conversation_id, message, quick_replies))

    monkeypatch.setattr(chatwoot, "route_message", fake_route_message)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)

    await chatwoot.handle_message({
        "id": 123,
        "message_type": "incoming",
        "content": "hola",
        "conversation": {"id": 99},
        "sender": {"name": "test"},
    })

    assert "99:123:incoming" in fake_store["processed"]
    assert sent == [("99", "response", [])]


def test_is_plausible_typed_reply():
    # Numbers and known bare replies must never be treated as button echoes.
    for c in ("1", "2", "5", "10", "0", "6+", "si", "sí", "no", "ninguno", "ninguna", "none"):
        assert chatwoot._is_plausible_typed_reply(c), c
    # Decorated button labels are safe to echo-suppress.
    for c in ("🤿 reservar", "salgo desde cartagena", "ver itinerario completo"):
        assert not chatwoot._is_plausible_typed_reply(c), c


@pytest.mark.asyncio
async def test_bare_number_titles_not_registered_as_echo(monkeypatch):
    """Quantity menus use bare-number titles (title == value). Registering them
    would eat a user who TYPES the number instead of clicking it."""
    monkeypatch.setattr(chatwoot.httpx, "AsyncClient", DummyAsyncClient)
    chatwoot.conversation_pending_echo_titles.pop("77", None)

    await chatwoot.send_chatwoot_message(
        "77",
        "¿Para cuántas personas?",
        [
            {"title": "1", "value": "1"},
            {"title": "2", "value": "2"},
            {"title": "6 o mas", "value": "6+"},
            {"title": "🔙 Volver", "value": "back"},
        ],
    )

    pending = chatwoot.conversation_pending_echo_titles.get("77", set())
    assert "1" not in pending and "2" not in pending  # bare numbers skipped
    assert "6+" not in pending                          # value form skipped
    assert "🔙 volver" in pending                       # real label still registered


@pytest.mark.asyncio
async def test_typed_number_at_qty_step_is_not_swallowed(monkeypatch, fake_store):
    """Regression: typing '2' after a quantity prompt must reach the tree, even
    though a button titled '2' is pending. Real clicks were unaffected; typed
    numbers used to be dropped as phantom echoes."""
    routed = []

    async def fake_route_message(state, message):
        routed.append(message)
        return "ok"

    async def fake_send_message(conversation_id, message, quick_replies=None):
        return None

    monkeypatch.setattr(chatwoot, "route_message", fake_route_message)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)
    # Simulate a qty prompt having been sent: number titles would previously land here.
    chatwoot.conversation_pending_echo_titles["55"] = {"1", "2", "3", "🔙 volver"}

    await chatwoot.handle_message({
        "id": 4242,
        "message_type": "incoming",
        "content": "2",
        "conversation": {"id": 55},
        "sender": {"name": "test"},
    })

    assert routed == ["2"], "typed qty '2' must be routed, not suppressed as echo"


@pytest.mark.asyncio
async def test_decorated_button_echo_still_suppressed(monkeypatch, fake_store):
    """A genuine click-echo of a decorated label (e.g. '🤿 Reservar') must still
    be dropped so it is not double-processed as free text."""
    routed = []

    async def fake_route_message(state, message):
        routed.append(message)
        return "ok"

    async def fake_send_message(conversation_id, message, quick_replies=None):
        return None

    monkeypatch.setattr(chatwoot, "route_message", fake_route_message)
    monkeypatch.setattr(chatwoot, "send_chatwoot_message", fake_send_message)
    chatwoot.conversation_pending_echo_titles["66"] = {"🤿 reservar"}

    await chatwoot.handle_message({
        "id": 4343,
        "message_type": "incoming",
        "content": "🤿 Reservar",
        "conversation": {"id": 66},
        "sender": {"name": "test"},
    })

    assert routed == [], "decorated button echo should be suppressed"


@pytest.mark.asyncio
async def test_handle_message_executes_handoff_when_supervisor_escalates(monkeypatch, fake_store):
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
    from src.flows.state import MESSAGE_SPLIT, ConversationState
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
    from src.flows.state import ConversationState
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
