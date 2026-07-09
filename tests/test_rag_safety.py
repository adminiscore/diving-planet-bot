import pytest

from src.agents.escalation import detect_sensitive_escalation
from src.agents import grounding_check, rag_agent
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


@pytest.mark.parametrize("msg", [
    "esto es una estafa, quiero mi dinero",
    "me estafaron con la reserva",
    "this is a scam, i want my money back",
    "pésimo servicio, nadie contesta",
    "los voy a demandar",
])
def test_complaints_and_fraud_escalate(msg):
    result = detect_sensitive_escalation(msg, "es")
    assert result is not None
    assert result[0] == "complaints_or_emergencies"


@pytest.mark.parametrize("msg", [
    "cuál es su política de reembolso?",
    "quiero un reembolso porque no pude ir",
    "tienen algún descuento?",
])
def test_neutral_refund_policy_question_does_not_escalate_as_complaint(msg):
    result = detect_sensitive_escalation(msg, "es")
    # Either no escalation, or not a complaint (a neutral policy question).
    assert result is None or result[0] != "complaints_or_emergencies"


def test_build_retrieval_query_uses_recent_user_history():
    history = [
        {"role": "user", "content": "We are a family of 6. Three are certified divers and three want to snorkel."},
        {"role": "assistant", "content": "Yes, you can do it together."},
        {"role": "user", "content": "I'd like to learn more about these packages"},
    ]

    # Anaphoric follow-up ("these packages") must pull in the prior context.
    retrieval_query = rag_agent.build_retrieval_query(
        "I'd like to learn more about these packages",
        history,
    )

    assert "family of 6" in retrieval_query
    assert "these packages" in retrieval_query


def test_build_retrieval_query_does_not_pollute_self_contained_question():
    """Regression: a self-contained question after an unrelated one must NOT be
    polluted with the previous question (which diluted retrieval and caused a
    false fallback)."""
    history = [
        {"role": "user", "content": "¿A qué hora es la salida?"},
        {"role": "assistant", "content": "La salida es a las 8:00 AM desde el Muelle de la Bodeguita."},
        {"role": "user", "content": "¿Cuál es la diferencia entre Open Water y Advanced?"},
    ]

    retrieval_query = rag_agent.build_retrieval_query(
        "¿Cuál es la diferencia entre Open Water y Advanced?",
        history,
    )

    # The unrelated previous question must not leak into the retrieval query.
    assert "salida" not in retrieval_query.lower()
    assert retrieval_query == "¿Cuál es la diferencia entre Open Water y Advanced?"


def test_looks_like_follow_up_heuristic():
    # Self-contained questions
    assert rag_agent._looks_like_follow_up("¿Cuál es la diferencia entre Open Water y Advanced?") is False
    assert rag_agent._looks_like_follow_up("where is the meeting point?") is False
    assert rag_agent._looks_like_follow_up("cuánto cuesta el minicurso?") is False
    # Interrogative "en qué" must NOT be treated as a location statement
    assert rag_agent._looks_like_follow_up("¿En qué consiste el Open Water?") is False
    # Genuine follow-ups
    assert rag_agent._looks_like_follow_up("y los niños?") is True
    assert rag_agent._looks_like_follow_up("the prices") is True
    assert rag_agent._looks_like_follow_up("¿qué incluye ese plan?") is True
    assert rag_agent._looks_like_follow_up("I'd like to learn more about these packages") is True


def test_location_statement_answer_is_follow_up():
    """Regression: a bare hotel/location answer ("en el hotel Pao Pao") to the
    bot's "which hotel?" question must be treated as a follow-up so the pickup
    context from earlier is carried into retrieval."""
    assert rag_agent._looks_like_follow_up("en el hotel pao pao") is True
    assert rag_agent._looks_like_follow_up("estoy en el hotel pao pao") is True
    assert rag_agent._looks_like_follow_up("en isla grande") is True
    assert rag_agent._looks_like_follow_up("at the pao pao hotel") is True

    history = [
        {"role": "user", "content": "Si ya estoy en Isla Grande, ¿me recogen?"},
        {"role": "assistant", "content": "¿En qué hotel estás?"},
        {"role": "user", "content": "en el hotel pao pao"},
    ]
    retrieval_query = rag_agent.build_retrieval_query("en el hotel pao pao", history)
    # The pickup intent from the earlier turn must be present in the retrieval query.
    assert "recogen" in retrieval_query.lower()
    assert "pao pao" in retrieval_query.lower()


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
    async def fake_rag(message, lang="es", history=None, extra_context=None, **kwargs):
        assert lang == "en"
        # Ensure supervisor passes some context summary when available
        assert extra_context is not None
        return "Sure! We can help with that 🤿"

    monkeypatch.setattr("src.agents.supervisor.rag_answer", fake_rag)

    state = ConversationState(conversation_id="test")
    state.step = Step.LANGUAGE
    state.language = "es"

    # A genuine informational question (not a booking request, so the v0.17.0
    # IntentDetector does not route it into the cart flow) must still reach RAG.
    response = await route_message(
        state,
        "What marine life and corals can we usually see underwater in the Rosario Islands?",
    )

    # The conversation agent answers the question via RAG and starts the
    # conversation (leaves WELCOME/LANGUAGE); the exact resting step is MAIN_MENU.
    assert state.step == Step.MAIN_MENU
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


def test_is_confident_vector_branch_uses_cosine(monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.40)
    monkeypatch.setattr(rag_agent.settings, "rag_min_bm25_rank", 0.05)

    assert rag_agent._is_confident({"score_vector": 0.55, "score_bm25_raw": 0.0}) is True
    assert rag_agent._is_confident({"score_vector": 0.30, "score_bm25_raw": 0.0}) is False


def test_is_confident_bm25_branch_uses_raw_rank(monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.40)
    monkeypatch.setattr(rag_agent.settings, "rag_min_bm25_rank", 0.05)

    # Normalized BM25 top is always 1.0, but the raw rank is below the floor and
    # the cosine is low -> must NOT be considered confident.
    weak = {"score": 1.0, "score_bm25": 1.0, "score_bm25_raw": 0.01, "score_vector": 0.1}
    assert rag_agent._is_confident(weak) is False

    strong = {"score_bm25_raw": 0.20, "score_vector": 0.1}
    assert rag_agent._is_confident(strong) is True


def test_is_confident_legacy_shape_uses_generic_score(monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)

    assert rag_agent._is_confident({"score": 0.9}) is True
    assert rag_agent._is_confident({"score": 0.2}) is False


@pytest.mark.asyncio
async def test_rag_fallback_when_only_weak_lexical_match(monkeypatch):
    """Regression: a normalized BM25 top (score=1.0) with raw rank below the
    floor and a low cosine must not pass the confidence gate."""
    async def fake_search(query, lang="es"):
        return [{
            "content": "Doc con coincidencia lexica debil",
            "metadata": {"source": "faqs"},
            "score": 1.0,
            "score_bm25": 1.0,
            "score_bm25_raw": 0.01,
            "score_vector": 0.12,
        }]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.40)
    monkeypatch.setattr(rag_agent.settings, "rag_min_bm25_rank", 0.05)

    response = await rag_agent.rag_answer("algo raro", lang="es")

    assert "No tengo información suficiente" in response


@pytest.mark.asyncio
async def test_rag_answers_on_strong_lexical_match(monkeypatch):
    """A strong lexical hit (raw rank above the floor) should pass the gate even
    when the cosine is low — this is the value hybrid search adds."""
    async def fake_search(query, lang="es"):
        return [{
            "content": "San Pedro de Majagua: recogida incluida.",
            "metadata": {"source": "faqs"},
            "score": 1.0,
            "score_bm25": 1.0,
            "score_bm25_raw": 0.25,
            "score_vector": 0.20,
        }]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.40)
    monkeypatch.setattr(rag_agent.settings, "rag_min_bm25_rank", 0.05)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

    response = await rag_agent.rag_answer("San Pedro de Majagua recogida", lang="es")

    assert response == "Respuesta basada en contexto"


def test_currency_guard_accepts_matching_price():
    assert grounding_check.currency_amounts_grounded(
        "El minicurso cuesta $178 USD.",
        "Precio: 178.00 USD reservando online.",
    ) is True


def test_currency_guard_accepts_single_zero_decimal_equivalence():
    assert grounding_check.currency_amounts_grounded(
        "The plan costs $178 USD.",
        "Online price: 178.0 USD.",
    ) is True


def test_currency_guard_rejects_invented_price():
    assert grounding_check.currency_amounts_grounded(
        "El minicurso cuesta $180 USD.",
        "Precio: 178.00 USD reservando online.",
    ) is False


def test_currency_guard_handles_cop_thousands():
    assert grounding_check.currency_amounts_grounded(
        "Son $630.000 COP.",
        "Precio en COP: 630000 COP.",
    ) is True


def test_currency_guard_ignores_non_currency_numbers():
    assert grounding_check.currency_amounts_grounded(
        "El plan dura 2 días y bajas hasta 18 metros.",
        "Itinerario de 1 día en las islas.",
    ) is True


def test_currency_guard_rejects_percentage_not_in_context():
    assert grounding_check.currency_amounts_grounded(
        "Tienes 25% de descuento.",
        "Descuento del 10% reservando online.",
    ) is False


@pytest.mark.asyncio
async def test_rag_falls_back_when_answer_has_ungrounded_price(monkeypatch):
    """The deterministic currency guard must reject an invented price even if the
    LLM grounding verifier would have approved it."""
    async def fake_search(query, lang="es"):
        return [{
            "content": "El minicurso para principiantes en Cartagena.",
            "metadata": {"source": "services"},
            "score": 0.9,
        }]

    class PriceMessage:
        content = "El minicurso cuesta $999 USD."

    class PriceChoice:
        message = PriceMessage()

    class PriceUsage:
        total_tokens = 10

    class PriceResponse:
        choices = [PriceChoice()]
        usage = PriceUsage()

    class PriceCompletions:
        async def create(self, **kwargs):
            return PriceResponse()

    class PriceChat:
        completions = PriceCompletions()

    class PriceOpenAI:
        def __init__(self, api_key=None):
            self.chat = PriceChat()

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", PriceOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

    response = await rag_agent.rag_answer("precio del minicurso?", lang="es")

    assert "No tengo información suficiente" in response


def test_url_guard_accepts_link_present_in_context():
    assert grounding_check.urls_grounded(
        "Reserva aquí: https://divingplanet.org/reservar",
        "Link de reserva: https://divingplanet.org/reservar",
    ) is True


def test_url_guard_rejects_invented_link():
    assert grounding_check.urls_grounded(
        "Paga en https://pagos-falsos.com/checkout",
        "El asesor te enviará el enlace de pago.",
    ) is False


def test_url_guard_ignores_answers_without_links():
    assert grounding_check.urls_grounded(
        "Te paso con un asesor para coordinar el pago.",
        "El asesor confirma el pago.",
    ) is True


@pytest.mark.asyncio
async def test_rag_falls_back_when_answer_has_ungrounded_link(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{
            "content": "El minicurso para principiantes en Cartagena.",
            "metadata": {"source": "services"},
            "score": 0.9,
        }]

    class LinkMessage:
        content = "Reserva en https://link-inventado.com/checkout"

    class LinkChoice:
        message = LinkMessage()

    class LinkUsage:
        total_tokens = 10

    class LinkResponse:
        choices = [LinkChoice()]
        usage = LinkUsage()

    class LinkCompletions:
        async def create(self, **kwargs):
            return LinkResponse()

    class LinkChat:
        completions = LinkCompletions()

    class LinkOpenAI:
        def __init__(self, api_key=None):
            self.chat = LinkChat()

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", LinkOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

    response = await rag_agent.rag_answer("cómo reservo el minicurso?", lang="es")

    assert "No tengo información suficiente" in response


# --- Capacity guard: no invented "max N people" for the private tour ---------

@pytest.mark.parametrize("answer", [
    "El tour privado admite hasta 12 personas.",
    "La lancha tiene capacidad para 10 personas.",
    "Es un máximo de 8 buzos por salida.",
    "Caben 15 personas en el bote.",
    "The private tour holds up to 12 people.",
    "Maximum of 8 divers per boat.",
    "12 personas máximo por lancha.",
])
def test_capacity_guard_rejects_invented_max_people(answer):
    context = "El tour privado tiene cotización personalizada según el grupo."
    assert grounding_check.capacity_claims_grounded(answer, context) is False


@pytest.mark.parametrize("answer,context", [
    # Plain headcount echoes (no max/limit trigger) must pass.
    ("El plan para 4 personas cuesta $178 c/u.", "Precio por persona: 178 USD."),
    ("Ustedes son 5 personas, perfecto.", "Reserva de buceo certificado."),
    # Non-people 'hasta' numbers must pass.
    ("Bajas hasta 18 metros de profundidad.", "Buceo recreativo en el arrecife."),
    ("El Bubble Makers llega hasta 2 metros.", "Piscina o aguas poco profundas."),
    # A grounded capacity claim (number present in context as a capacity) passes.
    ("Son máximo 7 personas por instructor.", "El ratio es de máximo 7 personas por instructor."),
])
def test_capacity_guard_accepts_grounded_or_non_capacity(answer, context):
    assert grounding_check.capacity_claims_grounded(answer, context) is True


@pytest.mark.asyncio
async def test_rag_falls_back_when_answer_invents_private_tour_capacity(monkeypatch):
    """The private-tour 'max N personas' hallucination (risk #2) must be caught
    deterministically even if the LLM grounding verifier would approve it."""
    async def fake_search(query, lang="es"):
        return [{
            "content": "El tour privado tiene cotización personalizada según el grupo.",
            "metadata": {"source": "faqs"},
            "score": 0.9,
        }]

    class CapMessage:
        content = "El tour privado admite hasta 12 personas."

    class CapChoice:
        message = CapMessage()

    class CapUsage:
        total_tokens = 10

    class CapResponse:
        choices = [CapChoice()]
        usage = CapUsage()

    class CapCompletions:
        async def create(self, **kwargs):
            return CapResponse()

    class CapChat:
        completions = CapCompletions()

    class CapOpenAI:
        def __init__(self, api_key=None):
            self.chat = CapChat()

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", CapOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

    response = await rag_agent.rag_answer("¿cuántas personas caben en el tour privado?", lang="es")

    assert "No tengo información suficiente" in response


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


# --- Food canonical must not hijack broader booking queries ------------------

@pytest.mark.parametrize("q", [
    "¿qué comida incluye el tour?",
    "el almuerzo es vegetariano?",
    "hay opción vegana?",
    "tengo alergia al marisco, pueden atenderme?",
    "cuánto cuesta el almuerzo?",
])
def test_food_canonical_still_fires_for_plain_food_questions(q):
    assert rag_agent._canonical_food_answer(q, "es") is not None


@pytest.mark.parametrize("q", [
    # A booking/recommendation query that merely mentions a dietary word must NOT
    # be answered with only the food blurb (owner-found weird-battery bug D1).
    "Hola, somos 8, 3 con open water y 2 advanced, presupuesto 2000, uno es vegetariano y otro celiaco, ¿qué nos recomiendan y cuánto sale?",
    "we are 6 divers, one is vegan, which package do you recommend and how much",
    "quiero reservar para 4 personas, uno tiene alergia, ¿qué me recomiendas?",
])
def test_food_canonical_defers_for_broader_booking_query(q):
    assert rag_agent._canonical_food_answer(q, "es") is None


# --- #2: curated "what do you offer for diving?" overview -------------------

@pytest.mark.parametrize("q", [
    "¿qué ofrecen para bucear?",
    "qué opciones hay para bucear",
    "qué planes de buceo tienen",
    "qué actividades de buceo hay",
    "what do you offer for diving",
    "what diving options do you have",
])
def test_diving_overview_canonical_fires(q):
    lang = "es" if any(w in q for w in ("qué", "para", "buceo")) else "en"
    ans = rag_agent._canonical_diving_overview_answer(q, lang)
    assert ans is not None
    # Structured, grouped by situation: beginner / certified / courses / snorkel.
    assert "Minicurso" in ans or "Mini-Course" in ans or "Mini-course" in ans
    assert "PADI" in ans
    assert "snorkel" in ans.lower()


@pytest.mark.parametrize("q", [
    "¿cuánto cuesta el buceo?",       # price question
    "qué incluye el buceo",           # inclusions
    "quiero bucear",                  # booking intent, not an overview ask
    "soy certificado",                # certification statement
    "qué es el buceo",                # definition
    "dónde bucean",                   # location
])
def test_diving_overview_not_triggered(q):
    assert rag_agent._canonical_diving_overview_answer(q, "es") is None


@pytest.mark.asyncio
async def test_rag_diving_overview_served_without_search(monkeypatch):
    async def fail_search(*args, **kwargs):
        raise AssertionError("Overview must use the canonical answer before retrieval")

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fail_search)

    response = await rag_agent.rag_answer("¿qué ofrecen para bucear?", lang="es")
    assert "Islas del Rosario" in response
    assert "Minicurso" in response


# --- #BUG1: a bare price question gets a price overview -----------------------

@pytest.mark.parametrize("q", [
    "cuánto cuesta",
    "cuánto sería el precio",
    "precios",
    "qué precios manejan",
    "cuánto vale",
    "cuánto sale",
])
def test_price_overview_fires_for_bare_price_question(q):
    ans = rag_agent._canonical_price_overview_answer(q, "es")
    assert ans is not None
    # Real prices from SERVICES, grouped by service.
    assert "USD" in ans and "COP" in ans
    assert "Buceo certificado" in ans and "Minicurso" in ans and "Snorkel" in ans


@pytest.mark.parametrize("q", [
    "cuánto cuesta el minicurso",   # names a specific service -> RAG
    "precio del snorkel",
    "cuánto el open water",
    "cuánto cuesta un vuelo",        # off-topic
    "cuánto cuesta el acompañante",
])
def test_price_overview_defers_for_specific_or_offtopic(q):
    assert rag_agent._canonical_price_overview_answer(q, "es") is None


@pytest.mark.asyncio
async def test_rag_bare_price_served_without_search(monkeypatch):
    async def fail_search(*args, **kwargs):
        raise AssertionError("Bare price must use the canonical overview before retrieval")

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fail_search)
    response = await rag_agent.rag_answer("cuánto cuesta", lang="es")
    assert "USD" in response and "COP" in response


def test_ambiguous_location_helper_detects_ultra_short_place_only_queries():
    assert rag_agent._is_ultra_short_ambiguous_location_query("Pao Pao") is True
    assert rag_agent._is_ultra_short_ambiguous_location_query("Cocoliso") is True
    assert rag_agent._is_ultra_short_ambiguous_location_query("San Pedro de Majagua") is True
    assert rag_agent._is_ultra_short_ambiguous_location_query("Islabela") is True
    assert rag_agent._is_ultra_short_ambiguous_location_query("Bora Bora") is True
    assert rag_agent._is_ultra_short_ambiguous_location_query("Isla Grande") is True


def test_ambiguous_location_helper_ignores_queries_with_explicit_intent():
    assert rag_agent._is_ultra_short_ambiguous_location_query("Hotel Pao Pao recogida?") is False
    assert rag_agent._is_ultra_short_ambiguous_location_query("Pao Pao alojamiento") is False
    assert rag_agent._is_ultra_short_ambiguous_location_query("Cocoliso pickup") is False
    assert rag_agent._is_ultra_short_ambiguous_location_query("Islabela hotel pickup") is False


def test_ambiguous_location_helper_ignores_unknown_short_queries():
    assert rag_agent._is_ultra_short_ambiguous_location_query("Cartagena") is False
    assert rag_agent._is_ultra_short_ambiguous_location_query("Open Water") is False


@pytest.mark.asyncio
async def test_rag_returns_clarification_for_ambiguous_location_query_before_search(monkeypatch):
    async def fail_search(*args, **kwargs):
        raise AssertionError("Ambiguous ultra-short hotel queries should clarify before retrieval")

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fail_search)

    response = await rag_agent.rag_answer("Pao Pao", lang="es")

    assert "¿Te refieres a Pao Pao" in response
    assert "recogida" in response
    assert "alojamiento" in response


@pytest.mark.asyncio
async def test_rag_returns_clarification_for_catalog_location_alias_before_search(monkeypatch):
    async def fail_search(*args, **kwargs):
        raise AssertionError("Catalog place aliases should clarify before retrieval")

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fail_search)

    response = await rag_agent.rag_answer("Bora Bora", lang="es")

    assert "¿Te refieres a Bora Bora" in response
    assert "recogida" in response


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


def test_system_prompt_has_booking_cutoff_time_guard_es():
    """Regression: the bot must not assert a time cutoff 'already passed' without real time data."""
    prompt = rag_agent.build_system_prompt("es")
    assert "COMPARA la hora actual con ese corte" in prompt
    assert "NO afirmes que el corte" in prompt


def test_system_prompt_has_booking_cutoff_time_guard_en():
    prompt = rag_agent.build_system_prompt("en")
    assert "COMPARE the current time against that cutoff" in prompt
    assert 'do NOT claim the cutoff "has already passed"' in prompt


def test_system_prompt_has_partial_equipment_discount_guard_es():
    """Regression T081: partial gear (e.g. mask+fins only) must NOT get the own-equipment discount."""
    prompt = rag_agent.build_system_prompt("es")
    assert "equipo parcial" in prompt.lower()


def test_system_prompt_has_partial_equipment_discount_guard_en():
    prompt = rag_agent.build_system_prompt("en")
    assert "partial gear" in prompt.lower()


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


def test_fewshot_skips_stale_colombian_discount_examples(monkeypatch):
    """Examples where the ADVISOR offered the removed Colombian discount are
    excluded from few-shot, while examples that only quote a COP price for
    Colombians (still valid) are kept."""
    fake_examples = [
        {
            "id": "ex_colombian_cop_price",  # VALID: just COP pricing, no discount
            "lang": "es",
            "scenario": "Colombiano pregunta precio",
            "customer": {"messages": ["para colombianos cuanto es?"]},
            "diving_planet": {"messages": ["El valor para colombianos es de 630.000 pesos por persona."]},
            "extracted_topics": ["precio_colombianos"],
        },
        {
            "id": "ex_colombian_discount",  # STALE: advisor offers a Colombian discount/bono
            "lang": "es",
            "scenario": "Colombiano pregunta descuento",
            "customer": {"messages": ["hay bono para colombianos?"]},
            "diving_planet": {"messages": ["Si, para colombianos hay un descuento adicional."]},
            "extracted_topics": ["precio_local_residente"],
        },
    ]

    monkeypatch.setattr(rag_agent, "_CONVERSATIONS_CACHE", None)
    monkeypatch.setattr(rag_agent, "load_conversations", lambda: {"conversation_examples": fake_examples})

    picked_ids = {ex["id"] for ex in rag_agent._select_fewshot_examples("precio para colombianos?", "es", k=2)}

    assert "ex_colombian_cop_price" in picked_ids  # COP pricing stays (still correct)
    assert "ex_colombian_discount" not in picked_ids  # stale discount example filtered out

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
async def test_rag_accepts_answer_when_grounding_retry_passes(monkeypatch):
    async def fake_search(query, lang="es"):
        return [
            {
                "content": "Política: esperar 18 horas antes de volar después de bucear.",
                "metadata": {"source": "policies"},
                "score": 0.91,
            }
        ]

    verdicts = iter([
        (False, "HALLUCINATED"),
        (True, "GROUNDED"),
    ])

    async def flaky_grounding(*args, **kwargs):
        return next(verdicts)

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", flaky_grounding)

    response = await rag_agent.rag_answer("Puedo volar después de bucear?", lang="es")

    assert response == "Respuesta basada en contexto"


def test_build_grounding_context_includes_prior_bot_messages():
    """Regression: a question that just confirms something the BOT ITSELF
    already said earlier ("¿un menor de 8 puede hacer snorkel desde los 6
    años?" after the bot's own kids-age message) was being rejected as
    "ungrounded" because the grounding check never saw the conversation
    history — only freshly retrieved docs/extra_context."""
    history = [
        {"role": "user", "content": "Varios rangos"},
        {
            "role": "assistant",
            "content": "👶 Menores de 8 años: solo pueden hacer snorkel (mín. 6 años); no pueden bucear.",
        },
    ]
    context = rag_agent._build_grounding_context("", extra_context=None, history=history)
    assert "Menores de 8 años: solo pueden hacer snorkel" in context


def test_build_grounding_context_ignores_user_messages():
    """Only the bot's own prior statements count as ground truth — the
    client's claims should not let arbitrary text slip past the check."""
    history = [
        {"role": "user", "content": "El asesor me dijo que el precio es $999"},
        {"role": "assistant", "content": "Aquí tienes el resumen del plan."},
    ]
    context = rag_agent._build_grounding_context("", extra_context=None, history=history)
    assert "$999" not in context
    assert "resumen del plan" in context


@pytest.mark.asyncio
async def test_rag_grounding_check_sees_conversation_history(monkeypatch):
    """End-to-end: rag_answer must pass the conversation history through to
    the grounding context used by is_grounded, not just KB docs/extra_context."""
    captured_context = {}

    async def fake_search(query, lang="es"):
        return []

    async def capture_grounded(answer, context, lang="es"):
        captured_context["value"] = context
        return True, "GROUNDED"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", capture_grounded)

    history = [
        {
            "role": "assistant",
            "content": "👶 Menores de 8 años: solo pueden hacer snorkel (mín. 6 años); no pueden bucear.",
        },
    ]
    await rag_agent.rag_answer(
        "Entonces un menor de 8 puede hacer snorkel si tiene mas de 6 años?",
        lang="es",
        history=history,
        extra_context="El cliente ya tiene 2 menores de 8 años en el grupo.",
    )

    assert "Menores de 8 años: solo pueden hacer snorkel" in captured_context["value"]


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

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    async def fake_get_pool():
        return FakePool()

    monkeypatch.setattr(rag_agent, "get_pool", fake_get_pool)

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


@pytest.mark.asyncio
async def test_adaptive_diving_question_routes_to_rag_not_booking(monkeypatch):
    """v0.17.2: disability / DIVE TO HEAL questions must be ANSWERED via RAG
    (the documented exception), not hijacked by the booking IntentDetector into
    the certification question."""
    async def fake_rag(message, lang="es", history=None, extra_context=None):
        return "INFO DIVE TO HEAL"

    monkeypatch.setattr("src.agents.supervisor.rag_answer", fake_rag)

    for msg in [
        "puede bucear mi hijo con sindrome de down?",
        "do you offer adaptive diving for people with disabilities?",
        "mi madre va en silla de ruedas, puede hacer snorkel?",
    ]:
        state = ConversationState(conversation_id="test")
        state.step = Step.MAIN_MENU
        state.language = "es"
        response = await route_message(state, msg)
        assert state.step != Step.MIXED_ASK_CERTIFICATION
        assert response == "INFO DIVE TO HEAL"


@pytest.mark.asyncio
async def test_general_interest_query_answered_by_agent(monkeypatch):
    """Fase 1: 'que me recomiendas?' / 'qué servicios tienen?' and similar
    general-interest queries must be ANSWERED conversationally by the agent
    (recommendation), NOT forced into a canned catalog + menu buttons — that
    was exactly the 'router-first' behavior the owner flagged."""
    async def fake_rag(message, lang="es", history=None, extra_context=None, **kwargs):
        return "AGENT RECOMMENDATION"

    monkeypatch.setattr("src.agents.supervisor.rag_answer", fake_rag)

    for msg in [
        "hola buenas, he visto vuestra empresa, que me recomiendas?",
        "qué me recomendáis?",
        "¿qué actividades tienen?",
        "qué servicios ofrecen?",
        "what do you recommend?",
        "what activities do you have?",
    ]:
        state = ConversationState(conversation_id="test")
        state.step = Step.WELCOME
        state.language = "es" if not msg.startswith("what") else "en"
        response = await route_message(state, msg)
        assert response == "AGENT RECOMMENDATION", (
            f"Expected the agent to answer {msg!r}, got {response!r}"
        )


@pytest.mark.parametrize("msg", [
    "mi tía tiene un corazón de oro, ¿puede acompañarnos?",
    "los instructores tienen un corazón de oro",
    "te lo digo de todo corazón",
])
def test_heart_idioms_do_not_trigger_medical_escalation(msg):
    result = detect_sensitive_escalation(msg, "es")
    assert result is None or result[0] != "medical_questions"


@pytest.mark.parametrize("msg", [
    "tengo un problema en el corazón",
    "sufro del corazón, ¿puedo bucear?",
])
def test_real_heart_condition_still_escalates(msg):
    result = detect_sensitive_escalation(msg, "es")
    assert result is not None and result[0] == "medical_questions"


@pytest.mark.parametrize("msg", [
    "¿los instructores tienen buena presión para manejar grupos grandes?",
    "hay que saber manejar la presión en este trabajo",
])
def test_pressure_idioms_do_not_trigger_medical_escalation(msg):
    result = detect_sensitive_escalation(msg, "es")
    assert result is None or result[0] != "medical_questions"


@pytest.mark.parametrize("msg", [
    "mi presión arterial es un poco alta, nada grave",
    "tengo la presión alta",
])
def test_real_blood_pressure_still_escalates(msg):
    result = detect_sensitive_escalation(msg, "es")
    assert result is not None and result[0] == "medical_questions"
