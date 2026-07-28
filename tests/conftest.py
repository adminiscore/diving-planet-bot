"""Shared test fixtures.

Con el núcleo conversacional como único camino (Fase 4), el orquestador legacy
se retiró; solo queda el stub offline de RAG (`_rag_answers_offline`) para que los
tests de flujo de conversación no peguen al pipeline real.
"""


import pytest

# Canned RAG answer for the default offline mock (see _rag_answers_offline below).
_RAG_STUB = "rag_answer_stub"

# Modules that legitimately exercise the real RAG pipeline (grounding, retrieval,
# fallback) and must NOT get the offline stub. test_rag_safety calls
# rag_agent.rag_answer directly (a different ref than supervisor.rag_answer, so
# it's unaffected anyway) but is listed for clarity; the FreeText/* suite is
# integration/live by nature.
_RAG_LIVE_MODULES = {"test_rag_safety"}

@pytest.fixture(autouse=True)
def _rag_answers_offline(request, monkeypatch):
    """Default: stub `supervisor.rag_answer` so conversation-flow tests that fall
    through to answer_question don't hit the real RAG LLM (slow + non-deterministic
    grounding → the source of flaky failures like test_go_pro_itinerary_back).

    A test that needs specific RAG behavior overrides this with its own
    `patch("src.agents.supervisor.rag_answer", ...)` (applied inside the test, so
    it wins). Modules in _RAG_LIVE_MODULES and any test marked `@pytest.mark.live`
    opt out and see the real pipeline.
    """
    module = request.node.module.__name__.rsplit(".", 1)[-1]
    if module in _RAG_LIVE_MODULES or request.node.get_closest_marker("live"):
        return

    from src.agents import supervisor

    async def _stub_rag(message, **kwargs):
        return _RAG_STUB

    monkeypatch.setattr(supervisor, "rag_answer", _stub_rag)


