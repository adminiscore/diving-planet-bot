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


async def grounded_ok(*args, **kwargs):
    return True, "GROUNDED"


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
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

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
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

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


def test_system_prompt_has_no_duplicated_currency_section_es():
    """Regression: 'Gestion de precios, monedas y pagos:' header must appear exactly once."""
    prompt = rag_agent.build_system_prompt("es")
    assert prompt.count("Gestión de precios, monedas y pagos:") == 1
    # The body of that section should also appear exactly once.
    assert prompt.count("Evita mezclar muchas monedas") == 1


def test_system_prompt_has_no_duplicated_currency_section_en():
    """Regression: 'Pricing, currencies, and payments:' header must appear exactly once."""
    prompt = rag_agent.build_system_prompt("en")
    assert prompt.count("Pricing, currencies, and payments:") == 1
    assert prompt.count("Avoid mixing several currencies") == 1


def test_brand_tone_injected_from_json_es(monkeypatch):
    """build_system_prompt must read brand_tone.json. Changes to the JSON must be reflected."""
    fake_tone = {
        "brand_tone": {
            "personality": {"es": "BrandPersonalityMarker"},
            "whatsapp_style": {
                "es": {
                    "message_shape": ["BrandShapeMarker"],
                    "human_touches": ["BrandTouchMarker"],
                },
            },
            "age_demographic_consideration": {"es": "BrandAgeMarker"},
        }
    }

    # Bust the module-level cache so the patch takes effect.
    monkeypatch.setattr(rag_agent, "_BRAND_TONE_CACHE", None)
    monkeypatch.setattr(rag_agent, "load_brand_tone", lambda: fake_tone)

    prompt = rag_agent.build_system_prompt("es")

    assert "BrandPersonalityMarker" in prompt
    assert "BrandShapeMarker" in prompt
    assert "BrandTouchMarker" in prompt
    assert "BrandAgeMarker" in prompt

    # Reset cache so other tests get the real values back.
    monkeypatch.setattr(rag_agent, "_BRAND_TONE_CACHE", None)


def test_fewshot_examples_selected_by_topic_overlap(monkeypatch):
    """_select_fewshot_examples picks examples whose extracted_topics overlap with query topics."""
    fake_examples = [
        {
            "id": "ex_pricing",
            "lang": "es",
            "scenario": "Cliente pregunta precio",
            "customer": {"messages": ["cuanto cuesta?"]},
            "diving_planet": {"messages": ["Se da precio en COP."]},
            "extracted_topics": ["precios"],
        },
        {
            "id": "ex_weather",
            "lang": "es",
            "scenario": "Cliente pregunta clima",
            "customer": {"messages": ["llueve manana?"]},
            "diving_planet": {"messages": ["Se escala a asesor."]},
            "extracted_topics": ["weather_cancellation"],
        },
        {
            "id": "ex_pricing_en",
            "lang": "en",
            "scenario": "EN pricing",
            "customer": {"messages": ["how much?"]},
            "diving_planet": {"messages": ["Price quoted in USD."]},
            "extracted_topics": ["pricing"],
        },
    ]

    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)
    monkeypatch.setattr(rag_agent, "load_conversations", lambda: {"conversation_examples": fake_examples})

    picked = rag_agent._select_fewshot_examples("cuanto cuesta para colombianos?", "es", k=2)
    picked_ids = {ex["id"] for ex in picked}

    assert "ex_pricing" in picked_ids  # topic 'precios' alias -> 'pricing' matches query 'pricing'
    assert "ex_weather" not in picked_ids  # no overlap with pricing query
    assert "ex_pricing_en" not in picked_ids  # wrong language

    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)


def test_fewshot_block_appended_when_query_provided(monkeypatch):
    """build_system_prompt appends the few-shot section only when query is provided AND examples match."""
    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)
    monkeypatch.setattr(
        rag_agent,
        "load_conversations",
        lambda: {
            "conversation_examples": [
                {
                    "id": "ex_pricing",
                    "lang": "es",
                    "scenario": "Test pricing scenario",
                    "customer": {"messages": ["cuanto cuesta?"]},
                    "diving_planet": {"messages": ["Precio dado en COP."]},
                    "extracted_topics": ["precios"],
                }
            ]
        },
    )

    # No query -> no few-shot block
    prompt_no_query = rag_agent.build_system_prompt("es")
    assert "Situaciones reales" not in prompt_no_query

    # With pricing-related query -> few-shot block appears
    prompt_with_query = rag_agent.build_system_prompt("es", query="cuanto cuesta el buceo?")
    assert "Situaciones reales" in prompt_with_query
    assert "Test pricing scenario" in prompt_with_query

    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)


def test_fewshot_no_examples_when_query_topics_unknown(monkeypatch):
    """Query with no detected topics -> no examples picked, no block appended."""
    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)
    monkeypatch.setattr(
        rag_agent,
        "load_conversations",
        lambda: {
            "conversation_examples": [
                {
                    "id": "ex_any",
                    "lang": "es",
                    "scenario": "x",
                    "customer": {"messages": ["x"]},
                    "diving_planet": {"messages": ["x"]},
                    "extracted_topics": ["precios"],
                }
            ]
        },
    )

    # "hola" has no topic match in TOPIC_PATTERNS -> nothing picked
    prompt = rag_agent.build_system_prompt("es", query="hola")
    assert "Situaciones reales" not in prompt

    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)


@pytest.mark.asyncio
async def test_rag_returns_fallback_when_grounding_check_rejects(monkeypatch):
    async def fake_search(query, lang="es"):
        return [
            {
                "content": "Política: esperar 18 horas antes de volar después de bucear.",
                "metadata": {"source": "policies"},
                "score": 0.91,
            }
        ]

    async def not_grounded(*args, **kwargs):
        return False, "HALLUCINATED"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", not_grounded)

    response = await rag_agent.rag_answer("Puedo volar después de bucear?", lang="es")

    assert "No tengo información suficiente" in response
    assert "+57 320 231515" in response


@pytest.mark.asyncio
async def test_query_rewriter_condenses_short_follow_up(monkeypatch):
    from src.agents import query_rewriter

    async def fake_create(**kwargs):
        return type(
            "R",
            (),
            {
                "choices": [
                    type(
                        "C",
                        (),
                        {"message": type("M", (), {"content": "Cuanto cuesta el minicurso para ninos?"})},
                    )
                ]
            },
        )()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type(
                "Chat",
                (),
                {"completions": type("Comp", (), {"create": staticmethod(fake_create)})()},
            )

    monkeypatch.setattr(query_rewriter, "AsyncOpenAI", FakeOpenAI)

    history = [
        {"role": "user", "content": "Cuanto cuesta el minicurso?"},
        {"role": "assistant", "content": "$183 USD por persona."},
        {"role": "user", "content": "Y para los ninos hay alguna diferencia?"},
        {"role": "assistant", "content": "Te confirmo solo la tarifa base actual."},
    ]

    result = await query_rewriter.condense_query("y los ninos?", history=history, lang="es")

    assert "ninos" in result.lower()
    assert "minicurso" in result.lower()


@pytest.mark.asyncio
async def test_query_rewriter_returns_original_on_llm_error(monkeypatch):
    from src.agents import query_rewriter

    class BrokenOpenAI:
        def __init__(self, **kwargs):
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Comp",
                        (),
                        {"create": staticmethod(lambda **kwargs: (_ for _ in ()).throw(RuntimeError("API down")))},
                    )()
                },
            )

    monkeypatch.setattr(query_rewriter, "AsyncOpenAI", BrokenOpenAI)

    result = await query_rewriter.condense_query(
        "y los ninos?",
        history=[
            {"role": "user", "content": "minicurso?"},
            {"role": "assistant", "content": "OK"},
        ],
        lang="es",
    )

    assert result == "y los ninos?"


@pytest.mark.asyncio
async def test_parent_doc_expansion_loads_summary_for_subchunk(monkeypatch):
    fetched = {}

    class FakeConn:
        async def fetch(self, query, lang, parent_ids):
            fetched["lang"] = lang
            fetched["parent_ids"] = parent_ids
            return [
                {
                    "id": 99,
                    "content": "Resumen del servicio",
                    "metadata": '{"source": "services", "key": "minicourse:summary", "lang": "es"}',
                }
            ]

        async def close(self):
            return None

    async def fake_connect(*args, **kwargs):
        return FakeConn()

    monkeypatch.setattr(rag_agent.asyncpg, "connect", fake_connect)

    docs = [
        {
            "id": 1,
            "content": "Itinerario del servicio",
            "metadata": {
                "source": "services",
                "key": "minicourse:itinerary",
                "parent_id": "minicourse:summary",
                "lang": "es",
            },
            "score": 0.88,
        }
    ]

    expanded = await rag_agent._expand_with_parent_context(docs, lang="es")

    assert expanded[0]["metadata"]["key"] == "minicourse:summary"
    assert expanded[1]["metadata"]["key"] == "minicourse:itinerary"
    assert fetched["parent_ids"] == ["minicourse:summary"]
