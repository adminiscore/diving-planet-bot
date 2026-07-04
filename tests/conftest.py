"""Shared test fixtures.

The conversation agent (Fase 1) calls the LLM orchestrator on substantive free
text at entry steps. To keep the suite deterministic and offline, we mock
`orchestrator.orchestrate` by default so the agent simply *answers* (no booking
action) — matching how most free-text tests expect info questions to flow to RAG.

Tests that need the agent to take a booking/action decision override this with
the `agent_decides` helper (see below), which returns a chosen tool. Modules
that exercise the orchestrator directly are excluded.
"""

import re

import pytest
from unittest.mock import AsyncMock

from src.agents import orchestrator

# Modules whose tests call orchestrator.orchestrate directly and must see the
# real implementation.
_ORCHESTRATOR_LIVE_MODULES = {"test_orchestrator"}

# Heuristic stand-in for the LLM's decision so entry free-text tests are
# deterministic/offline: a clear "I want to do/book an activity" statement (not a
# question) -> start_booking (reuses the deterministic router); everything else,
# including any question, -> answer_question (routes to RAG).
_BOOKING_INTENT = re.compile(
    r"\b(quiero|queremos|quisiera|somos|hacer|reservar|bucear|buceo|snorkel|"
    r"minicurso|curso|open\s*water|advanced|rescue|divemaster|certificad|bautismo|"
    r"i want|we are|book|dive|diving|course)\b",
    re.IGNORECASE,
)
_LOOKS_LIKE_QUESTION = re.compile(
    r"\?|^\s*(cu[aá]nto|cu[aá]l|qu[eé]|c[oó]mo|d[oó]nde|hay\b|incluye|tienen|"
    r"puedo|se\s+puede|what|how|where|do\s+you|can\s+i|is\s+there)",
    re.IGNORECASE,
)


def _default_agent_decision(message: str):
    m = (message or "").strip()
    if not _LOOKS_LIKE_QUESTION.search(m) and _BOOKING_INTENT.search(m):
        return orchestrator.OrchestratorDecision(
            tool=orchestrator.TOOL_START_BOOKING, args={"activity": "certified"}
        )
    return orchestrator.OrchestratorDecision(tool=orchestrator.TOOL_ANSWER_QUESTION)


@pytest.fixture(autouse=True)
def _agent_answers_by_default(request, monkeypatch):
    """Default: deterministic offline stand-in for the conversation agent's LLM
    decision (booking statement -> book, question -> answer)."""
    module = request.node.module.__name__.rsplit(".", 1)[-1]
    if module in _ORCHESTRATOR_LIVE_MODULES:
        return

    async def _fake_orchestrate(message, **kwargs):
        return _default_agent_decision(message)

    monkeypatch.setattr(orchestrator, "orchestrate", _fake_orchestrate)


@pytest.fixture
def agent_decides(monkeypatch):
    """Return a setter to make the conversation agent pick a specific tool.

    Usage:
        agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "certified"})
        agent_decides(orchestrator.TOOL_ESCALATE, {"reason": "..."})
        agent_decides(orchestrator.TOOL_ANSWER_QUESTION, remembered={"group_size": 5})
    """

    def _set(tool, args=None, remembered=None):
        async def _fake_orchestrate(message, **kwargs):
            # `tool` may be a callable router (message -> (tool, args)) for
            # multi-turn flows where each turn has a different intent.
            if callable(tool):
                t, a = tool(message)
                return orchestrator.OrchestratorDecision(tool=t, args=a or {})
            return orchestrator.OrchestratorDecision(
                tool=tool, args=args or {}, remembered=remembered
            )

        monkeypatch.setattr(orchestrator, "orchestrate", _fake_orchestrate)

    return _set
