"""Tests for the Fase 0 gap-filler LLM extractor (docs/robustness/plan.md).

Mirrors the fake-client pattern already used in test_orchestrator.py — no real
OpenAI calls, full control over the tool-call response.
"""

import json

import pytest

from src.agents.intent_detector import DetectedIntent
from src.agents.llm_extractor import (
    compare_with_ground_truth,
    detect_special_signals,
    fill_gaps,
    missing_fields,
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
# missing_fields()
# ---------------------------------------------------------------------------

def test_missing_fields_all_when_intent_empty():
    intent = DetectedIntent()
    missing = missing_fields(intent)
    assert "activity" in missing
    assert "is_certified" in missing
    assert "group_size" in missing


def test_missing_fields_excludes_already_resolved():
    intent = DetectedIntent(activity="certified_diving", is_certified=True, group_size=2)
    missing = missing_fields(intent)
    assert "activity" not in missing
    assert "is_certified" not in missing
    assert "group_size" not in missing
    assert "location" in missing


def test_missing_fields_treats_false_as_resolved():
    """is_certified=False is a real, resolved value — not "missing" just
    because it's falsy. Must use `is None`, not truthiness, under the hood."""
    intent = DetectedIntent(is_certified=False)
    missing = missing_fields(intent)
    assert "is_certified" not in missing


# ---------------------------------------------------------------------------
# fill_gaps()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fill_gaps_returns_patch_for_missing_fields():
    intent = DetectedIntent(language="en")  # everything else missing
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "extract_fields", json.dumps({"is_certified": False, "group_size": 1})
    )])
    patch = await fill_gaps(
        "hi i wanna dive, im not certfied tho, just me", intent,
        lang="en", client=_make_client(msg),
    )
    assert patch == {"is_certified": False, "group_size": 1}


@pytest.mark.asyncio
async def test_fill_gaps_only_fields_restricts_request_and_patch():
    """Fix B (conversational-refactor-handoff): `only_fields` restringe tanto lo
    que se le pide al LLM (el prompt solo lista esos campos) como lo que se
    acepta del patch — un campo devuelto fuera del subconjunto se descarta."""
    captured = {}

    class _CapturingClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    return _FakeResponse(_FakeMessage(tool_calls=[_FakeToolCall(
                        "extract_fields",
                        json.dumps({"location": "cartagena", "group_size": 2}),
                    )]))

    intent = DetectedIntent(language="es")  # everything missing
    patch = await fill_gaps(
        "estamos por el centro histórico", intent,
        lang="es", client=_CapturingClient(), only_fields=["location"],
    )
    # Solo location aceptado; group_size (fuera del subconjunto) descartado.
    assert patch == {"location": "cartagena"}
    # Y el prompt solo pide ese campo (no los ~13 de siempre).
    system = captured["messages"][0]["content"]
    assert "location" in system
    assert "group_size" not in system


@pytest.mark.asyncio
async def test_fill_gaps_only_fields_empty_intersection_skips_call():
    intent = DetectedIntent(group_size=2)  # group_size resuelto por regex
    patch = await fill_gaps(
        "somos 2", intent,
        client=None, only_fields=["group_size"],  # ya resuelto → nada que pedir
    )
    assert patch == {}


@pytest.mark.asyncio
async def test_fill_gaps_uses_extraction_model_not_orchestrator_model():
    """Fase 4: the gap-filler runs on settings.extraction_model (a cheaper/faster
    model), kept separate from settings.openai_model used by the orchestrator."""
    from src.config import settings

    captured = {}

    class _CapturingClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    return _FakeResponse(_FakeMessage(tool_calls=[_FakeToolCall(
                        "extract_fields", json.dumps({"group_size": 2})
                    )]))

    intent = DetectedIntent(language="en")
    await fill_gaps("just the two of us", intent, lang="en", client=_CapturingClient())
    assert captured["model"] == settings.extraction_model


@pytest.mark.asyncio
async def test_fill_gaps_never_overwrites_already_resolved_field():
    """Even if the LLM (buggy or not) returns a field regex already resolved,
    fill_gaps must strip it out of the patch — the regex result always wins."""
    intent = DetectedIntent(is_certified=True)
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "extract_fields", json.dumps({"is_certified": False, "group_size": 2})
    )])
    patch = await fill_gaps("somos 2", intent, client=_make_client(msg))
    assert "is_certified" not in patch
    assert patch == {"group_size": 2}


@pytest.mark.asyncio
async def test_fill_gaps_no_tool_call_returns_empty():
    intent = DetectedIntent()
    msg = _FakeMessage(tool_calls=None, content="just chatting")
    patch = await fill_gaps("hola", intent, client=_make_client(msg))
    assert patch == {}


@pytest.mark.asyncio
async def test_fill_gaps_bad_json_returns_empty():
    intent = DetectedIntent()
    msg = _FakeMessage(tool_calls=[_FakeToolCall("extract_fields", "not-json")])
    patch = await fill_gaps("hola", intent, client=_make_client(msg))
    assert patch == {}


@pytest.mark.asyncio
async def test_fill_gaps_exception_returns_empty():
    class _BoomClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("boom")

    intent = DetectedIntent()
    patch = await fill_gaps("hola", intent, client=_BoomClient())
    assert patch == {}


@pytest.mark.asyncio
async def test_fill_gaps_empty_message_returns_empty_without_calling_llm():
    intent = DetectedIntent()

    class _ShouldNotBeCalled:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise AssertionError("must not call the LLM for an empty message")

    patch = await fill_gaps("   ", intent, client=_ShouldNotBeCalled())
    assert patch == {}


@pytest.mark.asyncio
async def test_fill_gaps_nothing_missing_returns_empty_without_calling_llm():
    intent = DetectedIntent(
        activity="certified_diving", is_certified=True, group_size=2,
        group_allocation={"certified_diving": 2}, last_dive_over_2_years=False,
        duration="single_day", location="cartagena", island="x", hotel="y",
        ages=[30], cert_dives=2, cert_days=1, is_colombian=False,
    )

    class _ShouldNotBeCalled:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise AssertionError("must not call the LLM when nothing is missing")

    patch = await fill_gaps("cualquier cosa", intent, client=_ShouldNotBeCalled())
    assert patch == {}


@pytest.mark.asyncio
async def test_fill_gaps_drops_null_and_empty_values_from_patch():
    intent = DetectedIntent()
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "extract_fields",
        json.dumps({"is_certified": None, "ages": [], "group_size": 3}),
    )])
    patch = await fill_gaps("somos 3", intent, client=_make_client(msg))
    assert patch == {"group_size": 3}


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
