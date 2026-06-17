"""Fase 4 — tests for the tool-calling orchestrator (docs/conversation-orchestrator-plan.md).

Two layers:
1. orchestrate() parsing/fallback against a fake OpenAI client.
2. The supervisor dispatcher executing each tool against the real decision tree
   (the orchestrate() call itself is mocked so we control the chosen tool).
"""

import json

from unittest.mock import AsyncMock, patch

from src.agents import orchestrator
from src.agents.orchestrator import OrchestratorDecision, orchestrate
from src.agents import supervisor
from src.agents.supervisor import route_message, decision_tree, _build_extra_context
from src.flows.decision_tree import ConversationState, Step


# ---------------------------------------------------------------------------
# Fake OpenAI client for orchestrate() unit tests
# ---------------------------------------------------------------------------

class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name, arguments):
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls
        self.content = content


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


def _make_client(message):
    class _Completions:
        async def create(self, **kwargs):
            return _FakeResponse(message)

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


# ---------------------------------------------------------------------------
# Layer 1 — orchestrate() parsing
# ---------------------------------------------------------------------------

async def test_orchestrate_parses_tool_call():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("set_location", json.dumps({"origin": "island"}))])
    decision = await orchestrate("estoy en las islas", client=_make_client(msg))
    assert decision.tool == orchestrator.TOOL_SET_LOCATION
    assert decision.args == {"origin": "island"}
    assert not decision.is_answer


async def test_orchestrate_no_tool_call_is_answer():
    msg = _FakeMessage(tool_calls=None, content="solo una respuesta")
    decision = await orchestrate("¿cuánto cuesta?", client=_make_client(msg))
    assert decision.tool == orchestrator.TOOL_ANSWER_QUESTION
    assert decision.is_answer


async def test_orchestrate_bad_json_args_defaults_empty():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("cart_action", "not-json")])
    decision = await orchestrate("reservar", client=_make_client(msg))
    assert decision.tool == orchestrator.TOOL_CART_ACTION
    assert decision.args == {}


async def test_orchestrate_unknown_tool_falls_back():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("totally_made_up", "{}")])
    decision = await orchestrate("algo", client=_make_client(msg))
    assert decision.tool == orchestrator.TOOL_ANSWER_QUESTION


async def test_orchestrate_empty_message_is_answer():
    decision = await orchestrate("   ", client=_make_client(_FakeMessage()))
    assert decision.tool == orchestrator.TOOL_ANSWER_QUESTION


async def test_orchestrate_exception_falls_back():
    class _BoomClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("boom")

    decision = await orchestrate("algo", client=_BoomClient())
    assert decision.tool == orchestrator.TOOL_ANSWER_QUESTION


def test_allowed_tools_filters():
    tools = orchestrator._allowed_tools({orchestrator.TOOL_SET_LOCATION})
    names = {t["function"]["name"] for t in tools}
    # answer_question is always available as the fall-through.
    assert names == {orchestrator.TOOL_SET_LOCATION, orchestrator.TOOL_ANSWER_QUESTION}


# ---------------------------------------------------------------------------
# Layer 2 — dispatcher through route_message (orchestrate mocked)
# ---------------------------------------------------------------------------

def _cart_review_state(lang="es", cart=None, location="cartagena") -> ConversationState:
    s = ConversationState(conversation_id="orch-test")
    s.language = lang
    s.location = location
    s.step = Step.MIXED_CART_REVIEW
    s.mixed_cart = cart if cart is not None else []
    decision_tree.set_quick_replies(s, "mixed_cart_actions")
    return s


def _add_activity_state(lang="es", location="cartagena") -> ConversationState:
    s = ConversationState(conversation_id="orch-test")
    s.language = lang
    s.location = location
    s.step = Step.MIXED_ADD_ACTIVITY
    decision_tree.set_quick_replies(s, "mixed_add_activity")
    return s


def _patch_decision(decision: OrchestratorDecision):
    return patch.object(supervisor.orchestrator, "orchestrate", new=AsyncMock(return_value=decision))


async def test_dispatch_set_location_changes_state():
    state = _add_activity_state()
    decision = OrchestratorDecision(tool=orchestrator.TOOL_SET_LOCATION, args={"origin": "island"})
    with _patch_decision(decision):
        await route_message(state, "me cambio, estoy en las islas")
    assert state.location == "island"


async def test_dispatch_remove_item_drops_snorkel():
    cart = [
        {"type": "cert", "qty": 2, "plan": "2_dives_1_day", "label": "Buceo certificado"},
        {"type": "snorkel", "qty": 1, "plan": None, "label": "Snorkel"},
    ]
    state = _cart_review_state(cart=cart)
    decision = OrchestratorDecision(tool=orchestrator.TOOL_REMOVE_ITEM, args={"activity": "snorkel"})
    with _patch_decision(decision):
        await route_message(state, "quita el snorkel por favor")
    types = {it["type"] for it in state.mixed_cart}
    assert "snorkel" not in types
    assert "cert" in types


async def test_dispatch_cart_action_confirm_advances():
    cart = [{"type": "cert", "qty": 2, "plan": "2_dives_1_day", "label": "Buceo certificado"}]
    state = _cart_review_state(cart=cart)
    decision = OrchestratorDecision(tool=orchestrator.TOOL_CART_ACTION, args={"action": "confirm"})
    with _patch_decision(decision):
        await route_message(state, "listo, quiero reservarlo")
    # Confirm with a non-empty cart leaves the review step and enters checkout.
    assert state.step != Step.MIXED_CART_REVIEW


async def test_dispatch_escalate_sets_step_and_note():
    state = _cart_review_state(cart=[{"type": "cert", "qty": 1, "plan": "2_dives_1_day", "label": "Buceo certificado"}])
    decision = OrchestratorDecision(tool=orchestrator.TOOL_ESCALATE, args={"reason": "consulta especial"})
    with _patch_decision(decision):
        await route_message(state, "tengo una consulta puntual para el equipo")
    assert state.step == Step.ESCALATE
    assert state.pending_note


async def test_dispatch_start_booking_enters_subflow():
    state = _cart_review_state(cart=[])
    decision = OrchestratorDecision(tool=orchestrator.TOOL_START_BOOKING, args={"activity": "certified"})
    with _patch_decision(decision):
        await route_message(state, "quiero añadir buceo certificado")
    assert state.step == Step.MIXED_ADD_CERT_PLAN


async def test_dispatch_answer_question_routes_to_rag():
    state = _cart_review_state(cart=[{"type": "cert", "qty": 1, "plan": "2_dives_1_day", "label": "Buceo certificado"}])
    decision = OrchestratorDecision(tool=orchestrator.TOOL_ANSWER_QUESTION, args={})
    rag_mock = AsyncMock(return_value="RESPUESTA_RAG")
    with _patch_decision(decision), \
            patch.object(supervisor, "classify_menu_intent", new=AsyncMock(return_value="RAG")), \
            patch.object(supervisor, "rag_answer", new=rag_mock):
        response = await route_message(state, "¿qué incluye el tour exactamente?")
    rag_mock.assert_awaited()
    assert response == "RESPUESTA_RAG"


# ---------------------------------------------------------------------------
# Layer 3 — full-context snapshot (Fase 1 contract the orchestrator relies on)
# ---------------------------------------------------------------------------

def test_extra_context_includes_cart_and_step():
    state = ConversationState(conversation_id="ctx-test")
    state.language = "es"
    state.step = Step.MIXED_CART_REVIEW
    state.mixed_cart = [{"type": "cert", "qty": 3, "plan": "2_dives_1_day", "label": "Buceo certificado"}]
    ctx = _build_extra_context(state)
    assert ctx is not None
    assert "carrito" in ctx.lower()
    assert "3 x Buceo certificado" in ctx
    assert "mixed_cart_review" in ctx
