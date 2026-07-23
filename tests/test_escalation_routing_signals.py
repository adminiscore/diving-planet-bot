"""Tests para la red de precisión LLM de los gates de enrutado/seguridad
(auditoría 2026-07-22): escalado a humano, menú/volver, y temas sensibles —
las 3 listas de palabras clave (ESCALATION_KEYWORDS, MENU_KEYWORDS/
BACK_KEYWORDS, SENSITIVE_RULES) no reconocían variantes regionales reales
("estoy embarazadita", "soy epiléptica", "tengo una condición cardiaca").

Mismo patrón fake-client que test_llm_extractor.py.
"""

import json

import pytest

from src.agents.escalation import (
    SENSITIVE_RULES,
    detect_routing_signals,
    sensitive_response_for,
)


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


def test_sensitive_response_for_matches_keyword_path_text():
    """El texto de respuesta de la señal LLM debe ser IDÉNTICO al de la lista
    de palabras clave — mismo caso, misma respuesta, venga de donde venga."""
    keyword_reason, keyword_text = ("medical_questions", SENSITIVE_RULES["medical_questions"]["es"])
    llm_reason, llm_text = sensitive_response_for("medical_questions", "es")
    assert llm_reason == keyword_reason
    assert llm_text == keyword_text


def test_sensitive_response_for_unknown_category_returns_none():
    assert sensitive_response_for("no_existe", "es") is None


@pytest.mark.asyncio
async def test_detect_routing_signals_wants_human():
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_routing_signals", json.dumps({"wants_human": True})
    )])
    result = await detect_routing_signals("quisiera que me atendiera una persona real", client=_make_client(msg))
    assert result == {"wants_human": True}


@pytest.mark.asyncio
async def test_detect_routing_signals_wants_menu():
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_routing_signals", json.dumps({"wants_menu_or_restart": True})
    )])
    result = await detect_routing_signals("mejor empecemos de cero", client=_make_client(msg))
    assert result == {"wants_menu_or_restart": True}


@pytest.mark.asyncio
async def test_detect_routing_signals_sensitive_topic():
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_routing_signals", json.dumps({"sensitive_topic": "medical_questions"})
    )])
    result = await detect_routing_signals("estoy embarazadita, puedo bucear?", client=_make_client(msg))
    assert result == {"sensitive_topic": "medical_questions"}


@pytest.mark.asyncio
async def test_detect_routing_signals_no_signal_returns_empty():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("detect_routing_signals", json.dumps({}))])
    result = await detect_routing_signals("hola, quiero bucear mañana", client=_make_client(msg))
    assert result == {}


@pytest.mark.asyncio
async def test_detect_routing_signals_empty_message_no_llm_call():
    class _ShouldNotBeCalled:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise AssertionError("must not call the LLM for an empty message")

    result = await detect_routing_signals("   ", client=_ShouldNotBeCalled())
    assert result == {}


@pytest.mark.asyncio
async def test_detect_routing_signals_error_returns_empty():
    class _BoomClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("boom")

    result = await detect_routing_signals("algo raro", client=_BoomClient())
    assert result == {}


@pytest.mark.asyncio
async def test_detect_routing_signals_bad_json_returns_empty():
    msg = _FakeMessage(tool_calls=[_FakeToolCall("detect_routing_signals", "not-json")])
    result = await detect_routing_signals("hola", client=_make_client(msg))
    assert result == {}


@pytest.mark.asyncio
async def test_detect_routing_signals_adaptive_diving_topic():
    """DIVE TO HEAL / discapacidad: mismo audit method — _ADAPTIVE_DIVING_PATTERN
    es una lista cerrada que no reconoce amputación, prótesis, párkinson,
    lesión medular, sordomuda, "no vidente"... nueva señal en la MISMA llamada
    (sin coste extra) que ya cubre escalado/menú/sensibles."""
    msg = _FakeMessage(tool_calls=[_FakeToolCall(
        "detect_routing_signals", json.dumps({"adaptive_diving_topic": True})
    )])
    result = await detect_routing_signals("perdi una pierna en un accidente, puedo bucear igual?", client=_make_client(msg))
    assert result == {"adaptive_diving_topic": True}
