"""Rolling conversation summary — Fase B of docs/archive/memory-context-improvement-plan.md.

Every RAG/orchestrator call only ever reads the last N messages of
`state.history` (see rag_agent.py / orchestrator.py). Once a conversation
grows past that window, anything mentioned earlier is still stored in Redis
but effectively unreachable. This module keeps a short, incrementally
updated summary of everything that has fallen out of the raw window, so it
can be injected into the LLM context alongside it (see
`supervisor._build_extra_context`).
"""

import logging

from openai import AsyncOpenAI

from src.config import settings
from src.flows.state import ConversationState
from src.llm_client import trace_openai
from src.privacy import redact_pii
from src.prompts.memory import SUMMARY_SYSTEM_EN, SUMMARY_SYSTEM_ES

logger = logging.getLogger("uvicorn.error")

# How many NEW messages must accumulate since the last summary update before
# generating another one. Derived from settings.history_window_size (Fase A,
# docs/archive/memory-context-improvement-plan.md) so it stays in sync with the raw
# history window used by rag_agent.py/orchestrator.py — there is never a gap
# of messages that are neither in the raw window nor yet folded into the
# summary. Snapshotted at import time (like settings.openai_model elsewhere);
# tests override it directly via monkeypatch on this module attribute.
_SUMMARY_TRIGGER_EVERY = settings.history_window_size


def _format_turns(turns: list[dict], lang: str) -> str:
    customer_label = "Cliente" if lang == "es" else "Customer"
    assistant_label = "Asistente" if lang == "es" else "Assistant"
    lines: list[str] = []
    for msg in turns:
        content = redact_pii((msg.get("content") or "").strip())
        if not content:
            continue
        role = customer_label if msg.get("role") == "user" else assistant_label
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def _generate_summary(existing_summary: str | None, new_turns_text: str, lang: str) -> str:
    system = SUMMARY_SYSTEM_ES if lang == "es" else SUMMARY_SYSTEM_EN
    previous_label = "Resumen anterior" if lang == "es" else "Previous summary"
    segment_label = "Tramo nuevo de la conversación" if lang == "es" else "New conversation segment"
    user_content = (
        f"{previous_label}:\n{existing_summary or '(vacío / empty)'}\n\n"
        f"{segment_label}:\n{new_turns_text}"
    )

    client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        max_tokens=300,
    )
    return (response.choices[0].message.content or "").strip()


async def maybe_update_summary(state: ConversationState) -> None:
    """Update `state.conversation_summary` if enough new messages have
    accumulated since the last update. Never raises — a failure here must
    never break the customer-facing response, so the previous summary (or
    None) is left untouched on any error."""
    history = state.history or []
    new_count = len(history) - state.conversation_summary_through
    if new_count < _SUMMARY_TRIGGER_EVERY:
        return

    new_turns = history[state.conversation_summary_through:]
    lang = state.language or "es"
    new_turns_text = _format_turns(new_turns, lang)
    if not new_turns_text:
        # Nothing substantive in the new segment (e.g. all empty content) —
        # still advance the marker so we don't re-check the same empty span
        # every turn, but don't bother calling the LLM.
        state.conversation_summary_through = len(history)
        return

    try:
        updated = await _generate_summary(state.conversation_summary, new_turns_text, lang)
    except Exception as exc:
        logger.warning(f"[SUMMARY] failed, keeping previous summary: {exc}")
        return

    if updated:
        state.conversation_summary = updated
        state.conversation_summary_through = len(history)
        logger.info(f"[SUMMARY] updated through={state.conversation_summary_through} summary={updated[:200]!r}")
