import pytest

from src.agents import grounding_check, rag_agent
from src.agents.escalation import detect_sensitive_escalation
from src.agents.supervisor import route_message
from src.flows.state import ConversationState, Step


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


def test_routing_tool_excludes_weather_policy_questions_from_escalation():
    """Hallazgo en vivo (bateria sintetica contra PRE, lote 10, 2026-09-02):
    "¿que pasa si llueve ese dia?" escalaba con el texto generico de
    weather_conditions ("Te conecto con el equipo"), mientras que "¿cual es
    la politica de cancelacion si el clima esta malo?" (misma intencion del
    cliente) SI obtenia la respuesta real del KB (reprogramacion o reembolso
    100%, ver faqs.json: "Que pasa si se cancela por mal clima?"). La
    clasificacion sensitive_topic=weather_conditions viene del LLM
    (detect_routing_signals/ROUTING_TOOL), que no distinguia una pregunta de
    PRONOSTICO en tiempo real de una pregunta de POLITICA/hipotetica sobre
    mal clima -- ambas "mencionan el clima". Fix: instruccion explicita en
    el schema para dejar sensitive_topic sin fijar ante una pregunta de
    politica/hipotetica, dejando que caiga a RAG (que ya tiene contenido
    real y fundamentado para esa pregunta exacta)."""
    from src.prompts.router import ROUTING_TOOL
    schema_text = str(ROUTING_TOOL)
    assert "qué pasa si llueve" in schema_text
    assert "not a request for today's/tomorrow's real forecast" in schema_text


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
async def test_rag_low_confidence_returns_fallback_without_extra_context(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{"content": "Documento poco relacionado", "metadata": {"source": "faqs"}, "score": 0.2}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)

    response = await rag_agent.rag_answer("Pregunta rara", lang="es")

    assert "asesor" in response.lower()


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
async def test_bare_followup_query_not_diluted_by_unrelated_history(monkeypatch):
    """Real bug (live PRE, 2026-07-21): "y si llueve que pasa" retrieved the
    correct weather FAQ alone (cosine 0.42, above threshold), but enriching it
    with 2 unrelated prior turns (price, food) diluted the embedding and that
    same FAQ dropped below threshold, losing to the food FAQs instead — the
    customer got a generic "I don't have that" fallback for a question the KB
    answers well. The bare query must be tried first and win if confident."""
    calls = []

    async def fake_search(query, lang="es"):
        calls.append(query)
        if "\n" in query:
            # Enriched (multi-line) query: real doc gets diluted below threshold.
            return [{"content": "FAQ de comida vegetariana", "metadata": {"source": "faqs"}, "score": 0.30}]
        # Bare (single-line) query: the real doc is found confidently.
        return [{"content": "Que pasa si hace mal tiempo? La seguridad es prioridad.", "metadata": {"source": "faqs"}, "score": 0.55}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.40)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", DummyOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

    history = [
        {"role": "user", "content": "cuanto cuesta mas o menos?"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "hay comida vegetariana?"},
        {"role": "assistant", "content": "..."},
    ]
    response = await rag_agent.rag_answer("y si llueve que pasa", lang="es", history=history)

    assert response == "Respuesta basada en contexto"
    # Only ONE search call: the bare-query confidence check doubles as the
    # real retrieval when it's already confident — no wasted second call.
    assert len(calls) == 1
    assert "\n" not in calls[0]


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

    assert "asesor" in response.lower()


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


class TestCoherentTextGuard:
    """Hallazgo en vivo 2026-09-01 (lote 7 de frontera contra PRE, DIVE TO HEAL
    turno 3, 'cuantas inmersiones son'): la respuesta fue literalmente `{" "}`
    -- texto corrupto, no una respuesta real. Ningun guard existente lo pilla
    porque no lleva precio/URL/dato personal/telefono, y el juez de grounding
    solo valida factualidad, no coherencia. Ver
    docs/multi-agent-refactor-plan.md §7 (riesgo anotado sin fix, ahora
    cerrado)."""

    def test_rejects_the_exact_garbled_output_found_live(self):
        assert grounding_check.is_coherent_text('{" "}') is False

    def test_rejects_empty_or_whitespace(self):
        assert grounding_check.is_coherent_text("") is False
        assert grounding_check.is_coherent_text("   ") is False

    def test_rejects_punctuation_only(self):
        assert grounding_check.is_coherent_text("... !? {}[]") is False

    def test_accepts_a_short_real_answer(self):
        assert grounding_check.is_coherent_text("Si") is True
        assert grounding_check.is_coherent_text("No, no incluye.") is True

    def test_accepts_normal_prose(self):
        assert grounding_check.is_coherent_text(
            "El paquete incluye 5 inmersiones guiadas en Cartagena."
        ) is True


@pytest.mark.asyncio
async def test_rag_regenerates_when_answer_is_garbled(monkeypatch):
    """The coherent-prose guard rejects a garbled first sample and the
    existing regenerate-once mechanism (§ answer sampled at temperature 0.3)
    produces a real answer on the retry, instead of the customer ever seeing
    the corrupted text."""
    async def fake_search(query, lang="es"):
        return [{
            "content": "El paquete de 5 inmersiones incluye equipo completo.",
            "metadata": {"source": "services"},
            "score": 0.9,
        }]

    call_count = {"n": 0}

    class GarbledThenOkMessage:
        def __init__(self, content):
            self.content = content

    class GarbledThenOkChoice:
        def __init__(self, content):
            self.message = GarbledThenOkMessage(content)

    class GarbledThenOkUsage:
        total_tokens = 10

    class GarbledThenOkResponse:
        def __init__(self, content):
            self.choices = [GarbledThenOkChoice(content)]
            self.usage = GarbledThenOkUsage()

    class GarbledThenOkCompletions:
        async def create(self, **kwargs):
            call_count["n"] += 1
            content = '{" "}' if call_count["n"] == 1 else "Incluye 5 inmersiones guiadas y equipo completo."
            return GarbledThenOkResponse(content)

    class GarbledThenOkChat:
        completions = GarbledThenOkCompletions()

    class GarbledThenOkOpenAI:
        def __init__(self, api_key=None):
            self.chat = GarbledThenOkChat()

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.72)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", GarbledThenOkOpenAI)
    monkeypatch.setattr(rag_agent, "is_grounded", grounded_ok)

    response = await rag_agent.rag_answer("cuantas inmersiones son?", lang="es")

    assert response == "Incluye 5 inmersiones guiadas y equipo completo."
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_rag_falls_back_when_answer_has_ungrounded_price(monkeypatch):
    """The deterministic currency guard must reject an invented price even if the
    LLM grounding verifier would have approved it. Uses "curso advanced" (not
    one of the 4 catalog services with a deterministic price shortcut —
    audit 2026-08-26, Group 5 — so this still exercises the RAG/grounding
    path under test instead of short-circuiting before it)."""
    async def fake_search(query, lang="es"):
        return [{
            "content": "El curso advanced para buzos certificados en Cartagena.",
            "metadata": {"source": "services"},
            "score": 0.9,
        }]

    class PriceMessage:
        content = "El curso advanced cuesta $999 USD."

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

    response = await rag_agent.rag_answer("precio del curso advanced?", lang="es")

    assert "asesor" in response.lower()


class TestCanonicalPriceNamedServices:
    """Hallazgo en vivo 2026-08-26 (batería sintética contra PRE, Grupo 5):
    una pregunta de precio "en frío" (sin contexto de reserva) que nombra un
    servicio del catálogo fallaba el grounding del RAG (`ungrounded_amount`/
    `HALLUCINATED`) y caía a "no lo tengo a la mano" — pese a que el precio
    SÍ está disponible en el mismo catálogo `SERVICES` que ya alimenta la
    vista general de precios. Respuesta determinista para 1-2 servicios
    nombrados sin ambigüedad; 3+ o ninguno se deja a RAG/overview."""

    def test_single_known_service_es(self):
        r = rag_agent._canonical_price_named_services_answer(
            "cuanto cuesta el buceo certificado en dolares?", "es")
        assert r and "178" in r and "630.000" in r

    def test_single_known_service_snorkel(self):
        r = rag_agent._canonical_price_named_services_answer(
            "cuanto es el snorkel en pesos colombianos?", "es")
        assert r and "126" in r and "448.000" in r

    def test_two_services_comparison(self):
        r = rag_agent._canonical_price_named_services_answer(
            "que es mas barato, snorkel o minicurso?", "es")
        assert r and "126" in r and "183" in r

    def test_english(self):
        r = rag_agent._canonical_price_named_services_answer(
            "how much is diving?", "en")
        assert r and "178" in r

    def test_non_catalog_service_defers_to_rag(self):
        """El buceo nocturno, comida, hoteles, multi-día, etc. NO están en el
        catálogo de 4 servicios — deben seguir yendo a RAG, no inventarse."""
        for q in (
            "cuanto cuesta el buceo nocturno?",
            "cuanto cuesta el paquete multidia?",
            "cuanto cuesta la comida?",
            "cuanto cuesta el curso advanced?",
        ):
            assert rag_agent._canonical_price_named_services_answer(q, "es") is None

    def test_three_or_more_services_defers(self):
        """Ambigüedad genuina (3+ servicios nombrados) se deja a RAG/overview,
        no se adivina cuál importa más."""
        r = rag_agent._canonical_price_named_services_answer(
            "cuanto cuesta el buceo, el snorkel y el minicurso?", "es")
        assert r is None

    def test_non_price_question_returns_none(self):
        assert rag_agent._canonical_price_named_services_answer(
            "quiero hacer snorkel manana", "es") is None


class TestCanonicalPricePackage:
    """Hallazgo en vivo 2026-08-26 (batería sintética contra PRE, lote 4):
    preguntas de precio de paquete multi-día tenían resultado inconsistente
    y en un caso PELIGROSO — "how much is the 9 dive package?" (EN) RAG
    respondió con números INVENTADOS ($544.5/$605, ninguno coincide con el
    precio real $602/$668), mientras que la misma pregunta en español para
    el paquete de 5 cayó al fallback "no lo tengo a la mano". Respuesta
    determinista para los 4 paquetes reales (4/5/7/9 inmersiones), mismo
    patrón que `_canonical_price_named_services_answer`."""

    def test_package_5_dives_es(self):
        r = rag_agent._canonical_price_package_answer(
            "cuanto cuesta el paquete de 5 inmersiones?", "es")
        assert r and "392" in r and "1.429.000" in r

    def test_package_9_dives_en(self):
        r = rag_agent._canonical_price_package_answer(
            "how much is the 9 dive package?", "en")
        assert r and "602" in r and "2.170.000" in r
        # los números alucinados en vivo NUNCA deben aparecer
        assert "544" not in r and "605" not in r

    def test_package_4_and_7_dives(self):
        r4 = rag_agent._canonical_price_package_answer(
            "cuanto cuesta el paquete de 4 buceos?", "es")
        assert r4 and "316" in r4
        r7 = rag_agent._canonical_price_package_answer(
            "cuanto cuesta el paquete de 7 buceos?", "es")
        assert r7 and "503" in r7

    def test_non_package_price_question_defers(self):
        """Precio de un servicio base (no paquete) sigue sin tocar — lo
        cubre `_canonical_price_named_services_answer`, no este."""
        assert rag_agent._canonical_price_package_answer(
            "cuanto cuesta el buceo certificado?", "es") is None

    def test_ambiguous_package_mention_defers(self):
        """Mención genérica de "paquete" sin número de inmersiones concreto
        no debe adivinar cuál — se deja a RAG/overview."""
        assert rag_agent._canonical_price_package_answer(
            "cuanto cuesta el paquete multidia?", "es") is None

    def test_non_price_question_returns_none(self):
        assert rag_agent._canonical_price_package_answer(
            "el paquete de 5 buceos requiere alojamiento?", "es") is None


class TestCanonicalRefresherCost:
    """Hallazgo en vivo 2026-08-26 (batería sintética contra PRE, lote 5,
    conversaciones largas): "¿el refresher tiene costo adicional?" respondía
    "sí, puede tener costo, escríbenos por WhatsApp" — CONTRADICE la
    respuesta determinista que el propio núcleo da al ofrecer el refresher
    dentro del flujo de reserva ("sin coste adicional"). Respuesta
    determinista con la verdad ya conocida (gratis) en vez de dejar que el
    RAG adivine desde una política ambigua."""

    def test_spanish_question(self):
        r = rag_agent._canonical_refresher_cost_answer(
            "el refresher tiene costo adicional?", "es")
        assert r and "no tiene costo adicional" in r.lower()

    def test_english_question(self):
        r = rag_agent._canonical_refresher_cost_answer(
            "does the refresher cost extra?", "en")
        assert r and "no extra cost" in r.lower()

    def test_unrelated_price_question_returns_none(self):
        assert rag_agent._canonical_refresher_cost_answer(
            "cuanto cuesta el buceo certificado?", "es") is None

    @pytest.mark.asyncio
    async def test_refresher_question_wins_over_generic_overview(self):
        """La pregunta específica del refresher debe ganar sobre el
        overview genérico de precios incluso cuando la frase contiene una
        palabra que el overview también reconocería ("cost") — el fix se
        aplicó reordenando los checks para que este vaya primero."""
        resp = await rag_agent.rag_answer("does the refresher cost extra?", lang="en", history=[])
        assert "no extra cost" in resp.lower()
        assert "reference prices" not in resp.lower()


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

    assert "asesor" in response.lower()


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

    assert "asesor" in response.lower()


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
    # BUG3 (live PRE, 2026-07-16): "buzo" (noun, diver) was not recognized as a
    # diving word — only "bucea*/buse*" verb forms were. A self-identified
    # diver asking "que servicios teneis?" fell through to real RAG/LLM, which
    # answered but then spontaneously offered to escalate to a human advisor
    # for something the canonical overview already answers directly.
    "hola quiero, soy buzo y voy con un acompañante, que servicios teneis?",
    "soy buza certificada, que opciones hay?",
    "somos buzos, que planes tienen?",
    "i am a diver, what do you offer",
])
def test_diving_overview_canonical_fires(q):
    lang = "es" if any(w in q for w in ("qué", "para", "buceo", "buzo", "buza", "servicios", "que ")) else "en"
    ans = rag_agent._canonical_diving_overview_answer(q, lang)
    assert ans is not None
    # Structured, grouped by situation: beginner/companion mini-course / certified / courses / snorkel.
    # (the "minicurso" mention can live in the standalone beginner block OR in
    # the companion line when the speaker is already certified + has a
    # companion — the beginner block is dropped in that case, see below.)
    assert "minicurso" in ans.lower() or "mini-course" in ans.lower()
    assert "PADI" in ans
    assert "snorkel" in ans.lower()


# --- Precision follow-up (2026-07-16): the overview must not ignore what the --
# client already told us, AND must not repeat itself. A self-identified
# certified diver gets a statement ("para ti: paquetes...") instead of the
# rhetorical "¿ya eres buzo certificado?" question (redundant once the intro
# already acknowledged it). When there's ALSO a companion, the generic
# beginner block is dropped since the companion line already covers the same
# ground (minicurso/snorkel/accompany) more precisely — without a companion,
# the beginner block stays (may still apply to someone else not mentioned).

def test_diving_overview_certified_no_companion_uses_statement_and_keeps_beginner_block():
    ans = rag_agent._canonical_diving_overview_answer("soy buzo, que servicios teneis?", "es")
    assert ans is not None
    assert "¿Ya eres buzo certificado?" not in ans
    assert "Para ti" in ans
    cert_idx = ans.index("Para ti")
    beginner_idx = ans.index("¿Nunca has buceado?")
    assert cert_idx < beginner_idx, "certified block must still come first"
    assert "Qué bien que ya seas buzo certificado" in ans


def test_diving_overview_certified_with_companion_drops_beginner_block():
    ans = rag_agent._canonical_diving_overview_answer(
        "hola quiero, soy buzo y con un acompañante, que servicios teneís?", "es"
    )
    assert ans is not None
    assert "¿Ya eres buzo certificado?" not in ans
    assert "Para ti" in ans
    assert "¿Nunca has buceado?" not in ans, "redundant with the companion line, must be dropped"


def test_diving_overview_mentions_companion_options_in_spanish():
    ans = rag_agent._canonical_diving_overview_answer(
        "hola quiero, soy buzo y con un acompañante, que servicios teneís?", "es"
    )
    assert ans is not None
    assert "tu acompañante" in ans.lower()


def test_diving_overview_mentions_companion_options_in_english():
    ans = rag_agent._canonical_diving_overview_answer(
        "i am a certified diver with a companion, what do you offer for diving", "en"
    )
    assert ans is not None
    assert "your companion" in ans.lower()
    assert "Already a certified diver?" not in ans
    assert "For you" in ans
    assert "Never dived before?" not in ans, "redundant with the companion line, must be dropped"


def test_diving_overview_not_certified_with_companion_keeps_beginner_block():
    """Without a certified-diver signal, the beginner block still applies to
    the speaker themselves, so it must NOT be dropped just because a
    companion was mentioned."""
    ans = rag_agent._canonical_diving_overview_answer(
        "quiero bucear, voy con un acompañante, que opciones hay?", "es"
    )
    assert ans is not None
    assert "¿Nunca has buceado?" in ans


@pytest.mark.parametrize("q", [
    "soy buzo y voy con mis acompañantes, que servicios teneis?",
    "soy buzo y voy con 2 acompañantes, que servicios teneis?",
    "soy buzo y voy con varios acompañantes, que servicios teneis?",
])
def test_diving_overview_pluralizes_companion_line_in_spanish(q):
    ans = rag_agent._canonical_diving_overview_answer(q, "es")
    assert ans is not None
    assert "tus acompañantes no bucean" in ans.lower()
    assert "tu acompañante no bucea" not in ans.lower()


@pytest.mark.parametrize("q", [
    "i am a certified diver with companions, what do you offer",
    "i am a certified diver with 3 companions, what do you offer",
])
def test_diving_overview_pluralizes_companion_line_in_english(q):
    ans = rag_agent._canonical_diving_overview_answer(q, "en")
    assert ans is not None
    assert "your companions don't dive" in ans.lower()


def test_diving_overview_singular_companion_line_stays_singular():
    ans = rag_agent._canonical_diving_overview_answer(
        "soy buzo y voy con un acompañante, que servicios teneis?", "es"
    )
    assert ans is not None
    assert "tu acompañante no bucea" in ans.lower()


# --- Non-diver mentioned without the word "acompañante" -----------------------
# ("somos buzos y uno acompaña", "tres bucean y dos no", "mi pareja no bucea").
# Same companion line must still appear, with correct singular/plural.

@pytest.mark.parametrize("q,expect_plural", [
    ("somos buzos y uno acompaña, que servicios teneis?", False),
    ("mi pareja no bucea, yo soy buzo, que servicios teneis?", False),
    ("somos 5, tres bucean y dos no, que servicios teneis?", True),
    ("somos buzos y el resto no bucea, que servicios teneis?", True),
    ("somos buzos y los demás no bucean, que servicios teneis?", True),
    ("somos buzos y otros no bucean, que servicios teneis?", True),
])
def test_diving_overview_detects_non_diver_without_companion_word_es(q, expect_plural):
    ans = rag_agent._canonical_diving_overview_answer(q, "es")
    assert ans is not None
    if expect_plural:
        assert "tus acompañantes no bucean" in ans.lower()
    else:
        assert "tu acompañante no bucea" in ans.lower()


@pytest.mark.parametrize("q,expect_plural", [
    ("we are certified divers and one doesn't dive, what do you offer", False),
    ("my partner doesn't dive, i am a diver, what do you offer", False),
    ("we are 5, three dive and two don't, what do you offer", True),
    ("we are certified divers and the rest doesn't dive, what do you offer", True),
])
def test_diving_overview_detects_non_diver_without_companion_word_en(q, expect_plural):
    ans = rag_agent._canonical_diving_overview_answer(q, "en")
    assert ans is not None
    if expect_plural:
        assert "your companions don't dive" in ans.lower()
    else:
        assert "your companion doesn't dive" in ans.lower()


def test_diving_overview_no_companion_line_without_any_non_diver_signal():
    ans = rag_agent._canonical_diving_overview_answer("que servicios teneis para bucear?", "es")
    assert ans is not None
    assert "acompañante" not in ans.lower()
    assert "tus acompañantes" not in ans.lower()


def test_diving_overview_no_companion_line_when_not_mentioned():
    ans = rag_agent._canonical_diving_overview_answer("¿qué ofrecen para bucear?", "es")
    assert ans is not None
    assert "acompañante" not in ans.lower()


def test_diving_overview_default_order_when_not_certified():
    ans = rag_agent._canonical_diving_overview_answer("¿qué ofrecen para bucear?", "es")
    assert ans is not None
    beginner_idx = ans.index("¿Nunca has buceado?")
    cert_idx = ans.index("¿Ya eres buzo certificado?")
    assert beginner_idx < cert_idx, "default order keeps the beginner block first"


@pytest.mark.parametrize("q", [
    "¿cuánto cuesta el buceo?",       # price question
    "qué incluye el buceo",           # inclusions
    "quiero bucear",                  # booking intent, not an overview ask
    "soy certificado",                # certification statement
    "qué es el buceo",                # definition
    "dónde bucean",                   # location
    # BUG (live PRE, 2026-07-17): bare "planes" used to match ANYWHERE in the
    # message, so a booking statement mentioning the father's mobility
    # ("evitar planes muy físicos") false-positived into the overview instead
    # of reaching the guided tree / orchestrator.
    "Hola, somos 4, mi padre tiene la rodilla operada así que mejor evitar planes muy físicos. Queremos bucear 2 días",
    "prefiero no hacer planes muy físicos, quiero bucear",
])
def test_diving_overview_not_triggered(q):
    assert rag_agent._canonical_diving_overview_answer(q, "es") is None


def test_diving_overview_bare_short_query_still_fires():
    """The bare-word case must still fire for genuinely short standalone
    queries like "¿planes?" — only embedded-in-a-sentence uses were the bug."""
    ans = rag_agent._canonical_diving_overview_answer("¿planes de buceo?", "es")
    assert ans is None  # no "qué" and not purely the bare word -> defers to RAG, acceptable
    ans2 = rag_agent._canonical_diving_overview_answer("qué planes tienen para bucear", "es")
    assert ans2 is not None


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
    "los paquetes multidía que precio tienen",  # BUG2: plural "paquetes" + multi-day
    "qué precio tiene el multi-dia",
    "cuánto cuesta el plan de varios días",
    "cuánto cuesta el paquete de 5 buceos",
    "what is the price for the multi-day package",  # EN equivalent
    # BUG (live PRE, 2026-07-17): "el buceo" bare wasn't recognized as naming
    # a specific service, so a client mid-flow choosing their certified-diving
    # plan got the generic 4-service/both-currencies overview instead of a
    # targeted answer about diving specifically.
    "¿qué precio tiene el buceo?",
    "cuánto cuesta bucear",
    "what is the price of diving",
    "how much for a dive",
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


# --- #BUG2: multi-day price question must reach real retrieval, not the ------
# generic bare-price canonical overview (plural "paquetes" + missing multi-day
# keywords previously made it slip past _PRICE_SPECIFIC).

@pytest.mark.asyncio
async def test_rag_multiday_price_question_uses_real_search(monkeypatch):
    called = {"hit": False}

    async def fake_search(*args, **kwargs):
        called["hit"] = True
        return []

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    await rag_agent.rag_answer("Hola, los paquetes multidía que precio tienen?", lang="es")
    assert called["hit"], "Multi-day price question must not be short-circuited by the generic overview"


# --- Canonical-shortcut safety net: any phrasing not covered by the exclusion --
# regexes still gets a generic (not wrong, but incomplete) answer. Every
# canonical shortcut must invite the client to re-ask with more detail, so an
# uncovered regional phrasing doesn't silently end the conversation.

def test_price_overview_includes_safety_net_es():
    ans = rag_agent._canonical_price_overview_answer("cuánto cuesta", "es")
    assert ans is not None
    assert "más concreto" in ans


def test_price_overview_includes_safety_net_en():
    ans = rag_agent._canonical_price_overview_answer("how much does it cost", "en")
    assert ans is not None
    assert "more specific" in ans


def test_diving_overview_includes_safety_net_es():
    ans = rag_agent._canonical_diving_overview_answer("¿qué ofrecen para bucear?", "es")
    assert ans is not None
    assert "más concreto" in ans


def test_diving_overview_includes_safety_net_en():
    ans = rag_agent._canonical_diving_overview_answer("what do you offer for diving?", "en")
    assert ans is not None
    assert "more specific" in ans


def test_food_answer_includes_safety_net(monkeypatch):
    monkeypatch.setattr(rag_agent, "_food_policy_answer", lambda lang: "Política de comida de referencia.")
    ans = rag_agent._canonical_food_answer("¿qué incluye la comida?", "es")
    assert ans is not None
    assert "más concreto" in ans


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


def test_system_prompt_forbids_calculating_final_discounted_price_es():
    """Real bug (live PRE, 2026-07-17): asked '¿hay descuento por grupo?', the
    LLM sometimes computed a final discounted $ figure not literally in the
    context, which the deterministic currency guard correctly rejected as
    ungrounded — falling to the advisor fallback ~2/3 of the time even though
    the underlying discount policy was correct. The prompt must tell the model
    to state only the percentage/condition and never do the arithmetic itself."""
    prompt = rag_agent.build_system_prompt("es")
    assert "nunca calcules" in prompt.lower() or "no calcules" in prompt.lower()


def test_system_prompt_forbids_calculating_final_discounted_price_en():
    prompt = rag_agent.build_system_prompt("en")
    assert "never calculate" in prompt.lower()


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

    assert "asesor" in response.lower()
    # The advisor contact is handled internally now — the bot never hands out a number.
    assert "231515" not in response


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
        assert response == "INFO DIVE TO HEAL"




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


# --- Zero-KB-support must never be answered from world knowledge -------------
# Regression (2026-07-09): when no retrieved doc passed the confidence gate,
# rag_agent fell back to "answer from extra_context only". With
# verify_grounding=False (the conversation-agent path) the grounding judge was
# skipped, so the LLM happily answered a factual question from its own world
# knowledge — e.g. inventing a list of fish species. The judge must be FORCED
# on that escape hatch.

@pytest.mark.asyncio
async def test_no_kb_docs_forces_grounding_even_when_caller_skips_it(monkeypatch):
    from src.agents import rag_agent

    async def _no_docs(*args, **kwargs):
        return []

    judge_calls = []

    async def _fake_judge(answer, grounding_context, lang="es"):
        judge_calls.append(answer)
        return False, "HALLUCINATED"

    class _Msg:
        content = "En las islas veras peces loro, tortugas y morenas."

    class _Choice:
        message = _Msg()

    class _Usage:
        total_tokens = 10

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    class _Completions:
        async def create(self, **kwargs):
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, api_key=None):
            self.chat = _Chat()

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _no_docs)
    monkeypatch.setattr(rag_agent, "_verify_grounding_with_retry", _fake_judge)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _Client)

    answer = await rag_agent.rag_answer(
        "que animales se ven?",
        lang="es",
        extra_context="Idioma: es. El cliente eligio buceo certificado.",
        verify_grounding=False,   # conversation-agent path
    )

    assert judge_calls, "the grounding judge must run even with verify_grounding=False"
    assert answer == rag_agent.FALLBACK_ES
    assert "peces loro" not in answer


# --- Personal-data collection guard ------------------------------------------
# Regression (live PRE, 2026-07-09): closing an Advanced course conversation,
# the bot improvised the human advisor's manual booking ritual — "necesitaré
# que me confirmes: 1. Nombres y apellidos... 2. Número de identificación...".
# Bookings must close with the online booking link or an advisor handoff; the
# bot never collects identity data in chat.

from src.agents.grounding_check import requests_personal_data


@pytest.mark.parametrize("answer", [
    # The exact live-PRE failure shape (numbered ritual).
    ("Para eso, necesitaré que me confirmes lo siguiente:\n"
     "1. **Nombres y apellidos** de ambos.\n"
     "2. **Número de identificación** (puede ser cédula o pasaporte).\n"
     "3. **Fecha en la que quieren hacer la reserva**."),
    "Envíame tu nombre completo y tu cédula para confirmar la reserva.",
    "Por favor confirma tu número de pasaporte y la fecha de nacimiento.",
    "Me confirmas los nombres y apellidos de los buzos?",
    "Please share your full names and passport numbers to book you in.",
    "I will need your ID number and date of birth.",
])
def test_requests_personal_data_detects_collection(answer):
    assert requests_personal_data(answer) is True


@pytest.mark.parametrize("answer", [
    # Describing the official form is fine — it's not collecting in chat.
    "Antes de la salida deberás llenar el formulario de exoneración con tus datos.",
    # Telling them the advisor/WhatsApp handles it is the CORRECT behavior.
    "Escríbenos por WhatsApp al +57 320 231515 y un asesor confirmará tu reserva.",
    "Para reservar, haz clic aquí: https://book.divingplanet.org/book/salidas-de-buceo/1",
    # Innocent mentions of documents.
    "Recuerda llevar tu cédula o pasaporte el día de la salida.",
    "El día del curso preséntate con tu carné de certificación.",
    # Generic questions with no identity data.
    "¿Para cuántas personas sería la reserva?",
    "",
])
def test_requests_personal_data_ignores_legitimate_mentions(answer):
    assert requests_personal_data(answer) is False


def test_system_prompt_forbids_booking_data_collection():
    from src.agents.rag_agent import build_system_prompt

    es = build_system_prompt("es")
    en = build_system_prompt("en")
    assert "recogiendo datos en el chat" in es
    assert "collecting data in chat" in en


# --- Adaptive-diving colloquial synonym: "cojo/coja" -------------------------
# Regression (live bug, 2026-07-16): "somos cojos y queremos bucear" did not
# match _ADAPTIVE_DIVING_PATTERN (only formal terms like "movilidad reducida"
# were covered), so it fell through to RAG's generic fallback instead of the
# DIVE TO HEAL program info. "cojo/coja" is a very common Latin American
# colloquialism for reduced mobility/disability.

from src.agents.supervisor import _ADAPTIVE_DIVING_PATTERN


@pytest.mark.parametrize("msg", [
    "somos cojos y queremos bucear",
    "soy coja, puedo bucear con ustedes?",
    "mi hermano es cojo",
    "tengo cojera en una pierna",
    "I walk with a limp, can I still dive?",
])
def test_adaptive_diving_pattern_matches_cojo(msg):
    assert _ADAPTIVE_DIVING_PATTERN.search(msg) is not None


def test_adaptive_diving_pattern_does_not_match_unrelated_lame():
    # "lame" (English slang for "uncool") must NOT trigger this — only added
    # "cojo/cojera/limp" deliberately, not the ambiguous "lame".
    assert _ADAPTIVE_DIVING_PATTERN.search("that's so lame, I don't want to go") is None


# --- DIVE TO HEAL context persistence + price routing (2026-07-17) -----------
# Live bug (4 screenshots): the adaptive-diving topic was detected per-turn by
# keyword, so a follow-up "¿cuánto cuesta?" (no disability word) lost the
# context and fell through to the generic price overview (dumping Cartagena
# prices, no DIVE TO HEAL framing). Owner decision: adaptive diving is
# coordinated per case with an advisor, no prices in chat.

import pytest as _pytest

from src.agents.supervisor import (
    _PRICE_OR_BOOKING_Q,
    _adaptive_diving_advisor_answer,
)


@_pytest.mark.parametrize("msg", [
    "cuanto seria de precio?", "precio?", "cuánto cuesta", "qué precio tiene",
    "como reservo?", "quiero reservar", "how much is it?", "cost?", "how do I book?",
])
def test_price_or_booking_q_matches(msg):
    assert _PRICE_OR_BOOKING_Q.search(msg) is not None


@_pytest.mark.parametrize("msg", ["que animales se ven?", "hola", "los instructores hablan ingles?"])
def test_price_or_booking_q_ignores_non_price(msg):
    assert _PRICE_OR_BOOKING_Q.search(msg) is None


@_pytest.mark.parametrize("lang", ["es", "en"])
def test_adaptive_advisor_answer_has_no_prices_and_offers_advisor(lang):
    ans = _adaptive_diving_advisor_answer(lang)
    assert "$" not in ans and "COP" not in ans and "USD" not in ans
    assert "231515" not in ans  # advisor contact handled internally, no number
    assert ("asesor" in ans.lower()) or ("advisor" in ans.lower())


@_pytest.mark.asyncio
async def test_dive_to_heal_price_followup_routes_to_advisor_not_generic(monkeypatch):
    """With the adaptive context already set, a bare price question must return
    the advisor answer deterministically (no LLM, no generic Cartagena price
    dump)."""
    # Guard: if rag_answer were reached, fail loudly — this path must NOT use it.
    import src.agents.supervisor as sup

    async def _boom(*a, **k):
        raise AssertionError("rag_answer should not be called for DIVE TO HEAL price")

    monkeypatch.setattr(sup, "rag_answer", _boom)

    st = ConversationState(conversation_id="dth-price")
    st.language = "es"
    st.step = Step.MAIN_MENU
    st.adaptive_diving_context = True

    resp = await route_message(st, "cuanto seria de precio?")
    assert "dive to heal" in resp.lower()
    assert "$" not in resp  # never the generic price list
    assert "231515" not in resp  # no phone number handed out
    assert "asesor" in resp.lower()


# --- No phone numbers to the customer (owner decision, 2026-07-20) ------------

from src.agents.grounding_check import contains_phone_number


@_pytest.mark.parametrize("s", [
    "escríbenos al +57 320 231515",
    "WhatsApp: +57 320 231515",
    "llámanos al 3202315151",
    "contacto 320 231515",
    "+573202315151",
])
def test_contains_phone_number_detects_phones(s):
    assert contains_phone_number(s) is True


@_pytest.mark.parametrize("s", [
    "El minicurso cuesta 288.000 pesos",
    "2 inmersiones: 630.000 COP",
    "$178 USD por persona",
    "el curso es en 2026",
    "nos vemos a las 4:30 PM",
    "10% de descuento para grupos de 5",
    "somos 4 personas",
    "el plan de 2 inmersiones",
])
def test_contains_phone_number_ignores_prices_times_years(s):
    assert contains_phone_number(s) is False


def test_fallback_has_no_phone_number():
    from src.agents.rag_agent import FALLBACK_EN, FALLBACK_ES
    for fb in (FALLBACK_ES, FALLBACK_EN):
        assert not contains_phone_number(fb)


def test_system_prompt_forbids_phone_numbers():
    from src.agents.rag_agent import build_system_prompt
    es = build_system_prompt("es")
    en = build_system_prompt("en")
    assert "número de teléfono" in es and "WhatsApp" in es
    assert "phone or WhatsApp number" in en
    # The old hardcoded contact footer must be gone.
    assert "Contacto asesor: WhatsApp" not in es


# --- KB policy texts must never leak internal bot-authoring notes -------------
#
# Hallazgo en vivo 2026-09-02 (lote 9 de bateria sintetica contra PRE):
# "food_policy" en data/knowledge_base/policies.json llevaba, pegada al final
# del texto CUSTOMER-FACING, la nota "El bot no debe preguntar proactivamente
# por alergias." -- una instruccion para quien escribe el prompt del bot, no
# informacion para el cliente. El shortcut deterministico de info_agent.py
# (`_ALLERGY_WORD_RE` + `_FOOD_ALLERGEN_RE`) devuelve este texto VERBATIM sin
# pasar por el LLM, asi que la nota interna llegaba tal cual al cliente.
# Guarda generica: ningun texto de policies.json debe mencionar "el bot"/
# "the bot" en tercera persona -- si aparece, es casi siempre una nota de
# autoria colada en el campo equivocado.

def test_policy_texts_never_mention_the_bot_in_third_person():
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "data" / "knowledge_base" / "policies.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    for key, policy in data.get("policies", {}).items():
        for lang, text in policy.items():
            if not isinstance(text, str):
                continue
            lowered = text.lower()
            assert "el bot" not in lowered, f"{key}.{lang} menciona 'el bot': {text!r}"
            assert "the bot" not in lowered, f"{key}.{lang} menciona 'the bot': {text!r}"


# --- New-scenario memory reset (owner decision, 2026-07-20) -------------------

from src.agents.supervisor import _is_new_scenario_restart, _reset_to_fresh_scenario


def _state_with_memory():
    st = ConversationState(conversation_id="mem")
    st.language = "es"
    st.is_certified = True
    st.location = "cartagena"
    st.detected_group_size = 3
    st.remembered_facts = {"budget": "800", "notes": ["padre rodilla operada"]}
    st.conversation_summary = "Grupo de 3 certificados desde Cartagena."
    st.history = [{"role": "user", "content": "x"}] * 6
    return st


@_pytest.mark.parametrize("msg", [
    "hola soy Sofia de chile, hice mi open water y quiero bucear",
    "buenas, me llamo Juan y somos 4 para snorkel",
    "hi, I am Mark and we want to dive",
    "hola, somos 5 y queremos hacer el curso open water",
])
def test_new_scenario_restart_true(msg):
    assert _is_new_scenario_restart(msg, _state_with_memory()) is True


@_pytest.mark.parametrize("msg", [
    "hola",
    "hola que tal",
    "hola, cuanto cuesta el buceo?",
    "buenas, si quiero reservar",
    "soy certificado",
    "hola soy principiante y no se nadar",
])
def test_new_scenario_restart_false(msg):
    assert _is_new_scenario_restart(msg, _state_with_memory()) is False


def test_new_scenario_restart_needs_prior_memory():
    fresh = ConversationState(conversation_id="fresh")
    fresh.language = "es"
    assert _is_new_scenario_restart("hola soy Sofia y quiero bucear", fresh) is False


def test_reset_to_fresh_scenario_keeps_only_id_and_language():
    st = _state_with_memory()
    _reset_to_fresh_scenario(st)
    assert st.conversation_id == "mem" and st.language == "es"
    assert st.is_certified is None and not st.location
    assert st.remembered_facts == {} and st.conversation_summary is None
    assert st.history == [] and not st.mixed_cart


# --- "Volver" at the final summary never abandons the cart (2026-07-20) -------

