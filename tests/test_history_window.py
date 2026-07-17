"""Fase A (bigger raw history window) — written before the implementation
exists, per docs/memory-context-improvement-plan.md. These tests capture the
TARGET behavior: a single configurable setting (`settings.history_window_size`)
controls how many raw messages every consumer (RAG answer, grounding context,
orchestrator) reads, instead of the literal `12` repeated in 3+ places. The
rolling-summary trigger (Fase B) stays in sync by deriving from the same
setting, so there's never a gap of messages that are neither in the raw
window nor yet folded into the summary.
"""

import pytest

from src.agents.orchestrator import orchestrate
from src.config import settings


def _fill_history(n_pairs: int) -> list[dict]:
    history = []
    for i in range(n_pairs):
        history.append({"role": "user", "content": f"mensaje de usuario numero {i}"})
        history.append({"role": "assistant", "content": f"respuesta del bot numero {i}"})
    return history


def test_settings_has_history_window_size_default_24():
    assert settings.history_window_size == 24


class _CapturingCompletions:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _CapturingChat:
    def __init__(self, completions):
        self.completions = completions


class _CapturingClient:
    def __init__(self, response):
        self.chat = _CapturingChat(_CapturingCompletions(response))

    def __call__(self, *args, **kwargs):
        return self


class _Msg:
    content = "Respuesta de prueba"


class _Choice:
    message = _Msg()


class _Usage:
    total_tokens = 10


class _Resp:
    choices = [_Choice()]
    usage = _Usage()


@pytest.mark.asyncio
async def test_rag_answer_llm_call_respects_configured_window_size(monkeypatch):
    from src.agents import rag_agent

    monkeypatch.setattr(settings, "history_window_size", 3)
    client = _CapturingClient(_Resp())
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", client)

    async def _no_docs(*args, **kwargs):
        return []

    async def _fake_judge(answer, context, lang="es"):
        return True, "ok"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _no_docs)
    monkeypatch.setattr(rag_agent, "_verify_grounding_with_retry", _fake_judge)

    history = _fill_history(10)  # 20 raw messages, way more than the window of 3
    await rag_agent.rag_answer(
        "pregunta de seguimiento",
        lang="es",
        history=history,
        extra_context="Idioma: es.",
    )

    kwargs = client.chat.completions.calls[0]
    history_messages = [m for m in kwargs["messages"] if m["role"] in ("user", "assistant")]
    # -1 because the last "user" message is the current query, not history.
    assert len(history_messages) - 1 == 3


@pytest.mark.asyncio
async def test_grounding_context_respects_configured_window_size(monkeypatch):
    from src.agents import rag_agent

    # 6 raw messages = last 3 (user, assistant) pairs, so assistant 7/8/9 land
    # inside the window and 0-6 fall outside it.
    monkeypatch.setattr(settings, "history_window_size", 6)
    history = _fill_history(10)
    context = rag_agent._build_grounding_context("contexto base", history=history)
    for i in range(7):
        assert f"respuesta del bot numero {i}" not in context
    for i in range(7, 10):
        assert f"respuesta del bot numero {i}" in context


@pytest.mark.asyncio
async def test_orchestrator_respects_configured_window_size(monkeypatch):
    monkeypatch.setattr(settings, "history_window_size", 5)

    captured = {}

    class _Completions:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]

            class _FakeFunction:
                name = "answer_question"
                arguments = "{}"

            class _FakeToolCall:
                function = _FakeFunction()

            class _FakeMessage:
                tool_calls = [_FakeToolCall()]
                content = None

            class _FakeChoice:
                message = _FakeMessage()

            class _FakeResponse:
                choices = [_FakeChoice()]

            return _FakeResponse()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    history = _fill_history(10)
    await orchestrate("dato nuevo", history=history, client=_Client())

    history_messages = [m for m in captured["messages"] if m["role"] in ("user", "assistant")]
    assert len(history_messages) - 1 == 5


def test_summarizer_trigger_defaults_to_window_size():
    from src.agents import conversation_summarizer

    assert conversation_summarizer._SUMMARY_TRIGGER_EVERY == settings.history_window_size
