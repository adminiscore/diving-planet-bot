import pytest

from src.agents.escalation import detect_sensitive_escalation
from src.agents import rag_agent
from src.flows.decision_tree import ConversationState, Step
from src.agents.supervisor import route_message


class DummyMessage:
    content = "Respuesta basada en contexto"


class DummyChoice:
    message = DummyMessage()


class DummyUsage:
    total_tokens = 42


class DummyResponse:
    choices = [DummyChoice()]
    usage = DummyUsage()


class DummyCompletions:
    async def create(self, **kwargs):
        return DummyResponse()


class DummyChat:
    completions = DummyCompletions()


class DummyOpenAI:
    def __init__(self, api_key=None):
        self.chat = DummyChat()


def test_detect_medical_escalation_spanish():
    result = detect_sensitive_escalation("Tengo asma, puedo bucear?", "es")

    assert result is not None
    reason, response = result
    assert reason == "medical_questions"
    assert "staff calificado" in response


def test_detect_weather_escalation_english():
    result = detect_sensitive_escalation("How is the weather tomorrow?", "en")

    assert result is not None
    reason, response = result
    assert reason == "weather_conditions"
    assert "updated information" in response


def test_build_retrieval_query_uses_recent_user_history():
    history = [
        {"role": "user", "content": "We are a family of 6. Three are certified divers and three want to snorkel."},
        {"role": "assistant", "content": "Yes, you can do it together."},
        {"role": "user", "content": "I'd like to learn more about these packages"},
    ]

    retrieval_query = rag_agent.build_retrieval_query(
        "I'd like to learn more about these packages",
        history,
    )

    assert "family of 6" in retrieval_query
    assert "these packages" in retrieval_query


@pytest.mark.asyncio
async def test_supervisor_escalates_sensitive_message_before_rag(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("RAG should not be called for sensitive escalation")

    monkeypatch.setattr("src.agents.supervisor.rag_answer", fail_if_called)

    state = ConversationState(conversation_id="test")
    state.step = Step.MAIN_MENU
    state.language = "es"

    response = await route_message(state, "Estoy embarazada, puedo bucear?")

    assert state.step == Step.ESCALATE
    assert "staff calificado" in response


@pytest.mark.asyncio
async def test_supervisor_routes_early_free_text_to_rag(monkeypatch):
    async def fake_rag(message, lang="es", history=None, extra_context=None):
        assert lang == "en"
        # Ensure supervisor passes some context summary when available
        assert extra_context is not None
        return "Sure! We can help with that 🤿"

    monkeypatch.setattr("src.agents.supervisor.rag_answer", fake_rag)

    state = ConversationState(conversation_id="test")
    state.step = Step.LANGUAGE
    state.language = "es"

    response = await route_message(
        state,
        "We are a family of 6. Three are certified divers and three want to snorkel. Can we do it together?",
    )

    assert state.step == Step.FREE_TEXT
    assert state.language == "en"
    assert response == "Sure! We can help with that 🤿"


@pytest.mark.asyncio
async def test_rag_low_confidence_returns_fallback_without_extra_context(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{"content": "Documento poco relacionado", "metadata": {"source": "faqs"}, "score": 0.2}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)

    response = await rag_agent.rag_answer("Pregunta rara", lang="es")

    assert "No tengo información suficiente" in response


@pytest.mark.asyncio
async def test_rag_low_confidence_uses_extra_context_when_available(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{"content": "Documento poco relacionado", "metadata": {"source": "faqs"}, "score": 0.2}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)

    # Con extra_context deberia intentar responder usando el LLM en lugar de devolver el fallback
    response = await rag_agent.rag_answer("Pregunta rara", lang="es", extra_context="Resumen de estado")

    assert response == "Respuesta basada en contexto"


@pytest.mark.asyncio
async def test_rag_uses_sources_when_confident(monkeypatch):
    async def fake_search(query, lang="es"):
        return [
            {
                "content": "Política: esperar 18 horas antes de volar después de bucear.",
                "metadata": {"source": "policies"},
                "score": 0.91,
            }
        ]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)

    response = await rag_agent.rag_answer("Puedo volar después de bucear?", lang="es")

    assert response == "Respuesta basada en contexto"


@pytest.mark.asyncio
async def test_rag_food_query_returns_canonical_kb_answer_without_search(monkeypatch):
    async def fail_search(*args, **kwargs):
        raise AssertionError("Food queries should use the canonical KB answer before retrieval")

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fail_search)

    response = await rag_agent.rag_answer("¿Qué comida incluye el tour?", lang="es")

    assert "arroz con pollo o arroz con vegetales" in response
    assert "Pescado a la plancha" not in response
    assert "Ensaladas frescas" not in response
    assert "Frutas de temporada" not in response
