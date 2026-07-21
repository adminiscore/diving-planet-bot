"""Invariant test for the bug class found live 2026-07-21 (docs/HISTORY.md
v0.20.39): a message whose data _was_ extracted correctly by the regex, but
that the orchestrator LLM misclassified as `answer_question`, must still
reach the guided flow if `_intent_would_route()` says it should — it must
never silently fall through to a generic RAG answer.

`_intent_would_route()` is the canonical enumeration of "would this route?"
(mixed group split, known-certified diver, a specific activity, unknown
certification). `_dispatch_conversation_agent` keeps a SEPARATE, hand-written
set of fallback checks that must mirror it — exactly the kind of duplication
that let one branch (specific activity) go uncovered until today. This test
parametrizes over every shape `_intent_would_route()` recognizes and asserts
the real dispatcher actually routes for each one, so any future branch added
to `_intent_would_route()` without an equivalent fallback fails the suite
instead of waiting to be found live in PRE again.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import orchestrator, supervisor
from src.agents.intent_detector import DetectedIntent
from src.flows.decision_tree import ConversationState, Step

_GENERIC_MESSAGE = "mensaje generico de prueba sin signo de interrogacion"

_CASES = [
    ("mixed_group_split", DetectedIntent(group_allocation={"certified_diving": 3, "minicourse": 2}, group_size=5)),
    ("certified_diver_known", DetectedIntent(activity="certified_diving", is_certified=True)),
    ("certified_diver_unknown", DetectedIntent(activity="certified_diving", is_certified=None)),
    ("minicourse", DetectedIntent(activity="minicourse")),
    ("snorkel", DetectedIntent(activity="snorkel")),
    ("padi_open_water", DetectedIntent(activity="padi_open_water")),
    ("padi_advanced", DetectedIntent(activity="padi_advanced")),
    ("padi_rescue", DetectedIntent(activity="padi_rescue")),
    ("padi_divemaster", DetectedIntent(activity="padi_divemaster")),
    ("padi_specialty", DetectedIntent(activity="padi_specialty")),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id,intent", _CASES, ids=[c[0] for c in _CASES])
async def test_dispatch_routes_whenever_intent_would_route_says_it_should(case_id, intent):
    state = ConversationState(conversation_id=f"invariant-{case_id}")
    state.language = "es"

    # Sanity check: if this ever fails, the test CASE is wrong (doesn't match
    # what _intent_would_route recognizes), not the assertion below.
    assert supervisor._intent_would_route(intent, state, _GENERIC_MESSAGE), (
        f"Test case {case_id!r} doesn't even satisfy _intent_would_route() itself — "
        "fix the case, this isn't testing the real invariant."
    )

    with patch.object(supervisor.intent_detector, "detect", return_value=intent), \
         patch.object(
             supervisor.orchestrator, "orchestrate",
             new=AsyncMock(return_value=orchestrator.OrchestratorDecision(tool=orchestrator.TOOL_ANSWER_QUESTION)),
         ):
        await supervisor.route_message(state, _GENERIC_MESSAGE)

    assert state.step != Step.MAIN_MENU, (
        f"Case {case_id!r}: _intent_would_route() says this should route into the "
        "guided flow, but the orchestrator classifying the message as answer_question "
        "made it fall through to a generic RAG answer instead — the exact bug class "
        "found live 2026-07-21 (data extracted correctly, message never reached the "
        "routing code). Add/fix the matching fallback in _dispatch_conversation_agent."
    )
