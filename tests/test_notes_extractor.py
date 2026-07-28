"""Tests para src/agents/notes_extractor.py (Fase C — memoria de 'notes'
re-cableada al núcleo). Mismo patrón de fake-client que test_llm_extractor.py:
sin llamadas reales a OpenAI, control total de la respuesta tool-call.
"""

import json

import pytest

from src.agents.notes_extractor import extract_notes


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name, arguments):
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


def _client(message):
    class _Completions:
        async def create(self, **kwargs):
            return _FakeResponse(message)

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


def _tool(notes):
    return _FakeMessage(tool_calls=[_FakeToolCall("capture_notes", json.dumps({"notes": notes}))])


@pytest.mark.asyncio
async def test_returns_captured_notes():
    got = await extract_notes(
        "mi papá tiene la rodilla operada, mejor evitar planes muy físicos",
        client=_client(_tool(["padre con rodilla operada, evitar planes físicos"])),
    )
    assert got == ["padre con rodilla operada, evitar planes físicos"]


@pytest.mark.asyncio
async def test_empty_when_no_open_facts():
    got = await extract_notes("quiero bucear, somos 2, desde cartagena", client=_client(_tool([])))
    assert got == []


@pytest.mark.asyncio
async def test_dedups_against_existing_notes():
    """Una nota ya conocida (case-insensitive) no se devuelve otra vez."""
    got = await extract_notes(
        "recordá que mi papá tiene la rodilla operada",
        existing_notes=["Padre con rodilla operada, evitar planes físicos"],
        client=_client(_tool([
            "padre con rodilla operada, evitar planes físicos",   # duplicada
            "es nuestro aniversario",                              # nueva
        ])),
    )
    assert got == ["es nuestro aniversario"]


@pytest.mark.asyncio
async def test_no_tool_call_returns_empty():
    got = await extract_notes("hola", client=_client(_FakeMessage(tool_calls=None)))
    assert got == []


@pytest.mark.asyncio
async def test_malformed_json_returns_empty():
    got = await extract_notes("hola", client=_client(_FakeMessage(
        tool_calls=[_FakeToolCall("capture_notes", "{not json")]
    )))
    assert got == []


@pytest.mark.asyncio
async def test_exception_returns_empty():
    class _BoomClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("boom")

    got = await extract_notes("mi papá tiene la rodilla operada", client=_BoomClient())
    assert got == []


@pytest.mark.asyncio
async def test_empty_message_skips_call():
    got = await extract_notes("   ", client=_client(_tool(["algo"])))
    assert got == []


@pytest.mark.asyncio
async def test_uses_extraction_model_and_forced_tool():
    captured = {}

    class _CapturingClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    return _tool(["nota"])

    from src.config import settings
    await extract_notes("es nuestra luna de miel", client=_CapturingClient())
    assert captured["model"] == settings.extraction_model
    assert captured["tool_choice"]["function"]["name"] == "capture_notes"
    assert captured["temperature"] == 0.0
