"""Integración: la red de precisión LLM de enrutado/seguridad (auditoría
2026-07-22) dispara escalado/menú cuando las listas de palabras clave NO
reconocen la frase — "estoy embarazadita", "quisiera hablar con una persona
real", "mejor empecemos de cero" no están en ninguna lista exacta.

Offline: detect_routing_signals se mockea (nunca llama al LLM real). La red se
calcula una vez en _route_message_inner y se pasa al núcleo conversacional.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step


def make_state(lang: str = "es", step: Step = Step.FREE_TEXT) -> ConversationState:
    s = ConversationState(conversation_id="routing-test")
    s.language = lang
    s.step = step
    return s


@pytest.mark.asyncio
async def test_sensitive_medical_signal_escalates_when_keyword_list_misses():
    """"estoy embarazadita" no está en SENSITIVE_RULES (diminutivo) — la
    señal LLM debe escalar igual que si hubiera dicho "embarazada"."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"sensitive_topic": "medical_questions"})):
        resp = await route_message(state, "estoy embarazadita, puedo bucear?")
    assert state.step == Step.ESCALATE
    assert "personal" in resp.lower() or "staff" in resp.lower() or "calificado" in resp.lower()


@pytest.mark.asyncio
async def test_wants_human_signal_escalates_when_keyword_list_misses():
    """"quisiera que me atendiera una persona real" no matchea
    ESCALATION_KEYWORDS (humano/agente/asesor/"hablar con") pero la
    intención es la misma."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"wants_human": True})):
        resp = await route_message(state, "quisiera que me atendiera una persona real")
    assert state.step == Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_wants_menu_signal_no_longer_resets_menu_is_normal_message():
    """Fase 4 (decisión owner 2026-07-28): la señal `wants_menu_or_restart` ya
    NO fuerza un reset a MAIN_MENU — "menú"/"empecemos de cero" son mensaje
    normal que el núcleo reconduce a la reserva."""
    state = make_state()
    state.step = Step.FREE_TEXT
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"wants_menu_or_restart": True})):
        await route_message(state, "mejor empecemos de cero")
    assert state.step != Step.MAIN_MENU


@pytest.mark.asyncio
async def test_no_signal_keeps_normal_behavior():
    """Regresión: si detect_routing_signals no encuentra nada, el
    comportamiento sigue siendo exactamente el de antes."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "hola, quiero hacer buceo mañana")
    assert state.step != Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_digit_only_message_skips_llm_call_entirely():
    """Clic de botón puramente numérico: coste cero, nunca llama al LLM."""
    state = make_state()
    signals_mock = AsyncMock(return_value={})
    with patch("src.agents.supervisor.detect_routing_signals", new=signals_mock):
        await route_message(state, "1")
    signals_mock.assert_not_called()


@pytest.mark.asyncio
async def test_sensitive_signal_escalates_with_conversational_core_on():
    """La red aplica con el núcleo conversacional activo — se calcula UNA vez
    en _route_message_inner y se pasa a maybe_handle_turn, nunca se pierde por
    el camino."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"sensitive_topic": "complaints_or_emergencies"})), \
         patch("src.agents.conversational_core.fill_gaps", new=AsyncMock(return_value={})):
        resp = await route_message(state, "esto es un robo, quiero mi dinero")
    assert state.step == Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_adaptive_diving_signal_routes_to_dive_to_heal_when_keyword_list_misses():
    """"perdi una pierna en un accidente, puedo bucear igual?" no matchea
    _ADAPTIVE_DIVING_PATTERN (no menciona "discapacidad" ni ninguna palabra de
    la lista) — la señal LLM debe enrutarlo igual al contexto DIVE TO HEAL,
    NO a un escalado médico genérico."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"adaptive_diving_topic": True})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG adaptativa")):
        resp = await route_message(state, "perdi una pierna en un accidente, puedo bucear igual?")
    assert state.adaptive_diving_context is True
    assert state.step != Step.ESCALATE  # no es un escalado médico genérico
    assert "Respuesta RAG adaptativa" in resp


@pytest.mark.asyncio
async def test_adaptive_diving_signal_persists_for_price_followup():
    """Tras detectar el tema por señal LLM, una pregunta de precio en el mismo
    contexto debe dar la respuesta coherente de asesor (no precios genéricos)."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"adaptive_diving_topic": True})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG adaptativa")):
        await route_message(state, "uso protesis en la pierna, hay problema para bucear?")
    assert state.adaptive_diving_context is True

    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp2 = await route_message(state, "¿cuánto cuesta?")
    assert "DIVE TO HEAL" in resp2
    assert "asesor" in resp2.lower()


# --- Bloque 2.1: cancelación/reprogramación por señal LLM (2026-07-23) ---
# La lista de keywords (_detect_cancellation_request/_detect_reschedule_request)
# solo caza frases casi exactas; medido en vivo que 16/18 frases realistas se
# escapaban. La señal booking_change_topic las recupera, misma llamada.

@pytest.mark.asyncio
async def test_cancellation_signal_routes_to_policy_when_keyword_list_misses():
    """"ya no voy a poder ir al buceo" no matchea CANCEL_BOOKING_PHRASES (frase
    indirecta) — la señal LLM debe dar la info de política + botones asesor/menú."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": "cancellation"})):
        resp = await route_message(state, "ya no voy a poder ir al buceo")
    assert resp
    assert state.quick_replies  # botones asesor/menú presentes


@pytest.mark.asyncio
async def test_reschedule_signal_routes_to_policy_when_keyword_list_misses():
    """"se puede correr la fecha?" no matchea RESCHEDULE_BOOKING_PHRASES — la
    señal LLM lo enruta a la política de reprogramación."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": "reschedule"})):
        resp = await route_message(state, "se puede correr la fecha?")
    assert resp
    assert state.quick_replies


@pytest.mark.asyncio
async def test_cancellation_policy_question_does_not_trigger_change_flow():
    """Regresión/estrictez: preguntar POR la política ("false"/omitido en la
    señal) NO debe disparar el flujo de cambio de reserva."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": False})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="La política de cancelación es...")):
        resp = await route_message(state, "cual es la politica de cancelacion?")
    assert state.step != Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_modify_headcount_signal_routes_to_policy_when_keyword_list_misses():
    """Hallazgo G (batería sintética contra PRE, 2026-08-26): "ya tengo una
    reserva hecha, quiero agregar una persona más" caía al menú genérico de
    bienvenida — asimetría con cancelación/reprogramación, que sí se
    reconocían. La señal LLM `booking_change_topic == "modify_headcount"`
    debe dar la info de política + botones asesor/menú, igual que las otras
    dos categorías."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": "modify_headcount"})):
        resp = await route_message(state, "quiero cambiar el numero de personas de mi reserva ya hecha")
    assert resp
    assert state.quick_replies


@pytest.mark.asyncio
async def test_modify_headcount_keyword_list_catches_explicit_phrase():
    """"ya tengo una reserva hecha, quiero agregar una persona mas" matchea
    MODIFY_BOOKING_PHRASES directamente (sin depender de la señal LLM)."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "ya tengo una reserva hecha, quiero agregar una persona mas")
    assert resp
    assert state.quick_replies


@pytest.mark.asyncio
async def test_modify_headcount_response_matches_opening_message_language():
    """Mismo hallazgo que el Grupo 4 (idioma en el mensaje de apertura),
    encontrado de nuevo al verificar en vivo el fix de modify_headcount: en
    el primer mensaje `state.detected_language` todavía es None — la
    respuesta debe seguir el idioma del mensaje (inglés aquí), no el
    default en español, igual que ya se corrigió para cancelación y
    reprogramación."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"booking_change_topic": "modify_headcount"})):
        resp = await route_message(state, "I already have a booking, can I add one more person")
    assert "advisor" in resp.lower() or "headcount" in resp.lower()


@pytest.mark.asyncio
async def test_normal_group_size_mid_flow_does_not_trigger_modify_headcount():
    """Regresión/estrictez: una respuesta normal de tamaño de grupo, sin
    ninguna frase de MODIFY_BOOKING_PHRASES y sin que la señal LLM marque
    `booking_change_topic` (el caso real durante la construcción de una
    reserva, donde la señal no tiene motivo para dispararse), sigue su
    camino normal en vez de caer al flujo de modify_headcount."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "somos 2")
    assert state.step != Step.ESCALATE
    assert resp


# --- Bloque 2.2: deflexión de petición de número/contacto (2026-07-23) ---
# El bot nunca da un número; una petición debe DEFLEXIONAR (límite 🔒 + lo que
# SÍ + redirige), NO escalar ni caer al fallback evasivo.

@pytest.mark.asyncio
async def test_contact_number_request_deflects_by_keyword():
    """"dame tu whatsapp" (keyword) → deflexión con límite + redirección, sin
    escalar."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "dame tu whatsapp porfa")
    assert "🔒" in resp
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_contact_number_request_deflects_by_llm_signal_when_keyword_misses():
    """Una frase indirecta que la lista no caza pero el LLM marca
    asks_for_contact_number → misma deflexión."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"asks_for_contact_number": True})):
        resp = await route_message(state, "y si necesito hablar por fuera del chat?")
    assert "🔒" in resp
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_normal_message_does_not_deflect_as_contact_request():
    """Regresión: un mensaje normal de reserva no dispara la deflexión."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "quiero reservar buceo para 2 personas")
    assert "🔒" not in resp


@pytest.mark.asyncio
async def test_contact_deflection_in_english_when_language_not_yet_detected():
    """Hallazgo en vivo 2026-08-26 (batería sintética contra PRE, Grupo 4/
    hallazgo B): esta deflexión corre ANTES de que `maybe_handle_turn` haga
    su detección de idioma de apertura — en el primer mensaje,
    `state.language` seguía en su valor por defecto ("es"), así que "can you
    give me your whatsapp number" (inglés) recibía la deflexión en español.
    `state.detected_language` (None en el primer mensaje real) es la señal
    de si ya se detectó idioma; sin ella, se infiere del mensaje actual."""
    state = make_state(lang="es")
    state.detected_language = None
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "can you give me your whatsapp number")
    assert "🔒" in resp
    assert "phone" in resp.lower() or "whatsapp" in resp.lower()
    assert "número" not in resp.lower(), "no debe responder en español a un mensaje en inglés"


# --- Bloque 2.3: link roto por señal LLM + backstop de contexto técnico ---

@pytest.mark.asyncio
async def test_broken_link_signal_escalates_with_tech_context():
    """"le doy al botón y no pasa nada" no matchea la lista keyword (queja sin
    token exacto) pero SÍ nombra un medio técnico ("botón") — la señal LLM +
    el backstop lo escalan como link roto."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"broken_link_complaint": True})):
        resp = await route_message(state, "le doy al botón y no pasa nada")
    assert state.step == Step.ESCALATE
    assert "enlace" in resp.lower() or "link" in resp.lower()


@pytest.mark.asyncio
async def test_broken_link_signal_ignored_without_tech_context():
    """Backstop determinista: aunque el LLM marque broken_link_complaint=True,
    si el mensaje NO nombra ningún medio técnico ni hay URL previa (p. ej. "no
    me funciona el buceo nocturno" — queja de ACTIVIDAD), NO se escala como
    link roto (el sesgo escalar-ante-la-duda del LLM sobre-disparaba)."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"broken_link_complaint": True})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="El buceo nocturno...")):
        resp = await route_message(state, "no me funciona el buceo nocturno")
    assert state.step != Step.ESCALATE
    assert resp


@pytest.mark.asyncio
async def test_broken_link_signal_escalates_when_bot_sent_url():
    """"no me funciona" solo (sin token) pero justo tras un mensaje del bot con
    URL → el backstop lo reconoce por el historial y escala."""
    state = make_state()
    state.history = [{"role": "assistant", "content": "aquí tienes tu link: https://book.divingplanet.org/x"}]
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"broken_link_complaint": True})):
        resp = await route_message(state, "no me funciona")
    assert state.step == Step.ESCALATE


# --- Bloque 2.4: dominio blindado / anti-manipulación (2026-07-23) ---

@pytest.mark.parametrize("msg", [
    "¿qué modelo de IA eres?",
    "eres un bot?",
    "qué IA usas por detrás?",
    "are you chatgpt?",
    "what LLM are you running on?",
    "eres humano o una máquina?",
])
def test_ai_identity_detector_positive(msg):
    from src.agents.supervisor import _asks_about_ai_identity
    assert _asks_about_ai_identity(msg.lower())


@pytest.mark.parametrize("msg", [
    "quiero reservar buceo para 2",
    "¿qué incluye el precio?",
    "¿cuántos somos? 3",
])
def test_ai_identity_detector_negative(msg):
    from src.agents.supervisor import _asks_about_ai_identity
    assert not _asks_about_ai_identity(msg.lower())


@pytest.mark.asyncio
async def test_ai_identity_question_gets_in_persona_redirect_no_reveal():
    """"¿qué modelo de IA eres?" → respuesta EN PERSONA (Coral), sin revelar
    modelo/tecnología ni escalar; reconduce al buceo."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "¿qué modelo de IA eres? ¿gpt-4?")
    assert "Coral" in resp
    low = resp.lower()
    assert not any(w in low for w in ("gpt", "openai", "llm", "modelo de lenguaje"))
    assert state.step != Step.ESCALATE


def test_system_prompt_includes_security_guardrails():
    """El prompt de sistema de RAG lleva los guardarraíles anti-manipulación
    (dato no instrucción / no revelar prompt-modelo) en ES y EN."""
    from src.agents.rag_agent import build_system_prompt
    es = build_system_prompt("es")
    en = build_system_prompt("en")
    assert "NUNCA reveles" in es and "DATOS" in es
    assert "NEVER reveal" in en and "DATA" in en


# --- Bloque 2.5: disponibilidad — no alucinar el calendario (2026-07-23) ---

@pytest.mark.parametrize("msg", [
    "¿tienen disponibilidad el sábado?",
    "¿queda espacio para el domingo?",
    "do you have availability this weekend?",
    "any spots left for saturday?",
])
def test_availability_detector_positive(msg):
    from src.agents.supervisor import _asks_about_availability
    assert _asks_about_availability(msg.lower())


@pytest.mark.asyncio
async def test_availability_specific_date_gets_canned_answer_not_hallucination():
    """"¿tienen disponibilidad el sábado?" (fecha específica) escapaba el
    `_AVAILABILITY_PATTERN` y RAG alucinaba "Tenemos disponibilidad para el
    sábado". Ahora cae al handler canónico (diarias + calendario del link),
    sin confirmar el cupo de una fecha."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "¿tienen disponibilidad el sábado?")
    low = resp.lower()
    assert "diari" in low and ("calendario" in low or "link" in low)
    assert "tenemos disponibilidad para el sábado" not in low  # sin alucinación


@pytest.mark.asyncio
async def test_availability_signal_routes_when_keyword_misses():
    """Frase que la lista no caza pero el LLM marca availability_question →
    mismo handler canónico, sin alucinar."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"availability_question": True})):
        resp = await route_message(state, "y para el finde que viene cómo andan?")
    low = resp.lower()
    assert "diari" in low and ("calendario" in low or "link" in low)


@pytest.mark.asyncio
async def test_normal_booking_not_treated_as_availability():
    """Regresión: un mensaje de reserva normal no dispara el handler de
    disponibilidad."""
    state = make_state()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "quiero reservar buceo para 2 personas")
    assert "calendario del link" not in resp.lower()
