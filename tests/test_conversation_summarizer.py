"""Phase B (rolling conversation summary) — written before the implementation
exists, per docs/memory-context-improvement-plan.md. These tests capture the
TARGET behavior; they are expected to fail (RED) until the summarizer module
and the ConversationState fields it needs are implemented.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.flows.state import ConversationState


def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="summary-test")
    s.language = lang
    return s


def _fill_history(state: ConversationState, n_pairs: int) -> None:
    """Append n_pairs of (user, assistant) filler turns unrelated to the
    detail we care about, simulating a long meandering conversation."""
    for i in range(n_pairs):
        state.history.append({"role": "user", "content": f"pregunta de relleno numero {i}"})
        state.history.append({"role": "assistant", "content": f"respuesta de relleno numero {i}"})


class TestMaybeUpdateSummary:
    """Unit tests for src.agents.conversation_summarizer.maybe_update_summary,
    per the design in docs/memory-context-improvement-plan.md (Fase B)."""

    @pytest.mark.asyncio
    async def test_does_not_trigger_below_threshold(self, monkeypatch):
        from src.agents import conversation_summarizer

        generate_mock = AsyncMock(return_value="should not be called")
        monkeypatch.setattr(conversation_summarizer, "_generate_summary", generate_mock)

        state = make_state()
        state.history.append({"role": "user", "content": "hola"})
        state.history.append({"role": "assistant", "content": "hola, en que te ayudo"})

        await conversation_summarizer.maybe_update_summary(state)

        generate_mock.assert_not_called()
        assert state.conversation_summary is None

    @pytest.mark.asyncio
    async def test_triggers_once_threshold_reached_and_advances_marker(self, monkeypatch):
        from src.agents import conversation_summarizer

        generate_mock = AsyncMock(return_value="Resumen: grupo con padre con rodilla operada.")
        monkeypatch.setattr(conversation_summarizer, "_generate_summary", generate_mock)
        monkeypatch.setattr(conversation_summarizer, "_SUMMARY_TRIGGER_EVERY", 12)

        state = make_state()
        state.history.append({
            "role": "user",
            "content": "somos 4, mi padre tiene la rodilla operada, evitar planes fisicos",
        })
        _fill_history(state, 6)  # 1 + 12 = 13 messages, crosses the threshold of 12

        await conversation_summarizer.maybe_update_summary(state)

        generate_mock.assert_awaited_once()
        assert state.conversation_summary == "Resumen: grupo con padre con rodilla operada."
        assert state.conversation_summary_through == len(state.history)

    @pytest.mark.asyncio
    async def test_is_incremental_not_from_scratch(self, monkeypatch):
        """The second update must be given the PREVIOUS summary plus only the
        new segment, not the entire history from turn 1 again."""
        from src.agents import conversation_summarizer

        captured_args = {}

        async def fake_generate(existing_summary, new_turns_text, lang):
            captured_args["existing_summary"] = existing_summary
            captured_args["new_turns_text"] = new_turns_text
            return "resumen actualizado"

        monkeypatch.setattr(conversation_summarizer, "_generate_summary", fake_generate)
        monkeypatch.setattr(conversation_summarizer, "_SUMMARY_TRIGGER_EVERY", 12)

        state = make_state()
        state.conversation_summary = "Resumen previo: grupo de 4, uno con rodilla operada."
        state.conversation_summary_through = 13
        _fill_history(state, 13)  # 26 messages total, 13 new since through=13

        await conversation_summarizer.maybe_update_summary(state)

        assert captured_args["existing_summary"] == "Resumen previo: grupo de 4, uno con rodilla operada."
        assert "relleno" in captured_args["new_turns_text"]
        # The old detail must not need to be re-derived from raw text again —
        # it should only ever appear via existing_summary, not be re-sent in
        # new_turns_text (those messages are gone from history in this test).
        assert "rodilla" not in captured_args["new_turns_text"]

    @pytest.mark.asyncio
    async def test_llm_failure_leaves_previous_summary_untouched(self, monkeypatch):
        from src.agents import conversation_summarizer

        async def failing_generate(*args, **kwargs):
            raise RuntimeError("LLM unavailable")

        monkeypatch.setattr(conversation_summarizer, "_generate_summary", failing_generate)
        monkeypatch.setattr(conversation_summarizer, "_SUMMARY_TRIGGER_EVERY", 12)

        state = make_state()
        state.conversation_summary = "resumen anterior intacto"
        state.conversation_summary_through = 0
        _fill_history(state, 7)  # 14 messages, crosses threshold

        await conversation_summarizer.maybe_update_summary(state)  # must not raise

        assert state.conversation_summary == "resumen anterior intacto"


@pytest.mark.asyncio
async def test_build_extra_context_includes_summary_when_present():
    """The summary must be surfaced into the LLM-facing context, per the plan
    (injected in supervisor._build_extra_context alongside remembered_facts)."""
    from src.agents.supervisor import _build_extra_context

    state = make_state()
    state.conversation_summary = "Grupo de 4, uno con rodilla operada, evitar planes fisicos."

    context = _build_extra_context(state)

    assert context is not None
    assert "rodilla operada" in context


@pytest.mark.asyncio
async def test_end_to_end_long_conversation_recalls_early_detail(monkeypatch):
    """Full pre/post scenario from docs/memory-context-improvement-plan.md:
    a detail mentioned in turn 1 must still be reachable via extra_context by
    turn 16, even though it has long fallen out of the raw 12-message window.
    Today (pre-Fase-B) this detail is only in state.history, which nothing
    reads past the last 12 messages — this test fails until Fase B lands.
    """
    from src.agents import conversation_summarizer
    from src.agents.supervisor import route_message, _build_extra_context

    async def fake_generate(existing_summary, new_turns_text, lang):
        return "Grupo de 4, uno con rodilla operada, evitar planes fisicos."

    monkeypatch.setattr(conversation_summarizer, "_generate_summary", fake_generate)
    monkeypatch.setattr(conversation_summarizer, "_SUMMARY_TRIGGER_EVERY", 12)

    state = make_state()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        await route_message(
            state,
            "Hola, somos 4, mi padre tiene la rodilla operada, mejor evitar planes muy fisicos. Queremos bucear 2 dias.",
        )
        for i in range(7):
            await route_message(state, f"pregunta de relleno numero {i}")

    context = _build_extra_context(state)
    assert context is not None
    assert "rodilla" in context.lower()
