"""Tests for the Fase 0 gap-filler LLM extractor (docs/robustness/plan.md).

Mirrors the fake-client pattern already used in test_orchestrator.py — no real
OpenAI calls, full control over the tool-call response.
"""

import json

import pytest

from src.agents.llm_extractor import (
    compare_with_ground_truth,
    detect_special_signals,
    resolve_slot_answer,
)

# ---------------------------------------------------------------------------
# Fake OpenAI client (same shape as test_orchestrator.py's)
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
# compare_with_ground_truth()
# ---------------------------------------------------------------------------

def test_compare_all_agree():
    result = compare_with_ground_truth(
        {"is_certified": False, "group_size": 1},
        {"is_certified": False, "group_size": 1},
    )
    assert result == {"agree": ["is_certified", "group_size"], "disagree": {}, "missed": []}


def test_compare_disagreement():
    result = compare_with_ground_truth(
        {"is_certified": True}, {"is_certified": False},
    )
    assert result["disagree"] == {"is_certified": (True, False)}
    assert result["agree"] == []


def test_compare_missed_field():
    result = compare_with_ground_truth({}, {"group_size": 2})
    assert result["missed"] == ["group_size"]


# ---------------------------------------------------------------------------
# detect_special_signals() — fallback de recordar/acompañante (núcleo)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_signals_recall_field():
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_signals", json.dumps({"recall_field": "group_size"})
    )])
    result = await detect_special_signals(
        "cuantas personas somos, me lo recuerdas?", client=_make_client(msg)
    )
    assert result == {"recall_field": "group_size"}


@pytest.mark.asyncio
async def test_detect_signals_companion_activity_and_qty():
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_signals", json.dumps({"companion_activity": "minicourse", "companion_qty": 1})
    )])
    result = await detect_special_signals(
        "mi acompañante quiere hacer buceo pero no es certificado", client=_make_client(msg)
    )
    assert result == {"companion_activity": "minicourse", "companion_qty": 1}


@pytest.mark.asyncio
async def test_detect_signals_no_signal_returns_empty():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("detect_signals", json.dumps({}))])
    result = await detect_special_signals("hola, gracias por la ayuda", client=_make_client(msg))
    assert result == {}


@pytest.mark.asyncio
async def test_detect_signals_empty_message_no_llm_call():
    class _ShouldNotBeCalled:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise AssertionError("must not call the LLM for an empty message")

    result = await detect_special_signals("   ", client=_ShouldNotBeCalled())
    assert result == {}


@pytest.mark.asyncio
async def test_detect_signals_error_returns_empty():
    class _BoomClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("boom")

    result = await detect_special_signals("algo raro", client=_BoomClient())
    assert result == {}


@pytest.mark.asyncio
async def test_detect_signals_drops_null_values():
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_signals", json.dumps({"recall_field": None, "companion_activity": "snorkel"})
    )])
    result = await detect_special_signals("un amigo quiere snorkel", client=_make_client(msg))
    assert result == {"companion_activity": "snorkel"}


# ---------------------------------------------------------------------------
# resolve_slot_answer() — red anti-bucle de slot booleano/escalar (Fase C)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_slot_boolean_value():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("resolve_slot", json.dumps({"value": True}))])
    result = await resolve_slot_answer("safety", "uf, hace muchísimo", client=_make_client(msg))
    assert result == {"value": True}


@pytest.mark.asyncio
async def test_resolve_slot_integer_value():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("resolve_slot", json.dumps({"value": 2}))])
    result = await resolve_slot_answer("qty", "un par", client=_make_client(msg))
    assert result == {"value": 2}


@pytest.mark.asyncio
async def test_resolve_slot_abstains_when_no_value():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("resolve_slot", json.dumps({}))])
    result = await resolve_slot_answer("nationality", "cuánto cuesta?", client=_make_client(msg))
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_slot_unknown_slot_no_llm_call():
    class _ShouldNotBeCalled:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise AssertionError("must not call the LLM for an unsupported slot")

    result = await resolve_slot_answer("location", "cartagena", client=_ShouldNotBeCalled())
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_slot_empty_message_no_llm_call():
    class _ShouldNotBeCalled:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise AssertionError("must not call the LLM for an empty message")

    result = await resolve_slot_answer("safety", "   ", client=_ShouldNotBeCalled())
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_slot_error_returns_empty():
    class _BoomClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("boom")

    result = await resolve_slot_answer("safety", "hace años", client=_BoomClient())
    assert result == {}
