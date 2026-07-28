"""Exhaustive conversation-level test dataset for the Diving Planet bot."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.lead_summary import build_lead_summary
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="test-conv")
    s.language = lang
    return s


@pytest.fixture(autouse=True)
def _no_llm_language_fallback(monkeypatch):
    """Default the welcome-step LLM language fallback to "no detection" so
    existing tests stay deterministic and don't hit the network regardless of
    whether a real OPENAI_API_KEY is configured locally. Tests that exercise
    the LLM fallback path explicitly override this mock."""
    monkeypatch.setattr(
        "src.agents.supervisor.detect_language_llm",
        AsyncMock(return_value=None),
    )


async def send(state: ConversationState, *messages: str) -> list[str]:
    responses = []
    for msg in messages:
        resp = await route_message(state, msg)
        responses.append(resp)
    return responses


async def reach_main_menu(lang: str = "es") -> ConversationState:
    state = make_state()
    greeting = "hola" if lang == "es" else "hello"
    await send(state, greeting)
    assert state.step == Step.MAIN_MENU
    assert state.language == lang
    return state


async def reach_booking_cart(lang: str = "es", location: str = "cartagena") -> ConversationState:
    state = await reach_main_menu(lang)
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
    await route_message(state, "1")
    location_choice = "1" if location == "cartagena" else "2"
    await route_message(state, location_choice)
    if location == "island":
        # Unknown hotel yet -> asks island, then hotel, before the activity menu.
        assert state.step == Step.ISLAND_MENU
        await route_message(state, "1")  # Isla Grande
        assert state.step == Step.ISLAND_HOTEL_MENU
        await route_message(state, "1")  # first hotel in the list
    assert state.step == Step.MIXED_ADD_ACTIVITY
    return state




async def reach_courses_menu(lang: str = "es", location: str = "cartagena") -> ConversationState:
    state = await reach_booking_cart(lang, location)
    await route_message(state, "4")
    assert state.step == Step.COURSES_MENU
    return state






async def reach_pricing_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "2", "2", "2")
    assert state.step == Step.PRICING_MENU
    return state


async def reach_booking_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "2", "3")
    assert state.step == Step.BOOKING_MENU
    return state


async def reach_logistics_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "2", "4")
    assert state.step == Step.LOGISTICS_MENU
    return state


RAG_MOCK = "respuesta_rag_simulada"
RAG_MOCK_EN = "rag_answer_simulated"


# ===========================================================================
# BLOQUE 1 — PRIMER CONTACTO Y SELECCIÓN DE IDIOMA
# ===========================================================================





















@pytest.mark.asyncio
async def test_language_detection_spanish_text():
    state = make_state()
    await route_message(state, "zzz")
    await route_message(state, "español")
    assert state.language == "es"






# ---------------------------------------------------------------------------
# Fuzzy text-to-button matching (natural-language menu navigation)
# ---------------------------------------------------------------------------





































# ---------------------------------------------------------------------------
# Back navigation in the Reservar branch (button value="back" or keyword)
# ---------------------------------------------------------------------------

















@pytest.mark.asyncio
async def test_back_keyword_outside_reservar_branch_falls_back_to_main_menu():
    """When back keyword is used at a step with no BACK_STEP mapping, fall back to MAIN_MENU."""
    state = make_state()
    state.step = Step.FREE_TEXT
    await route_message(state, "volver")
    assert state.step == Step.MAIN_MENU


# ===========================================================================
# BLOQUE 2 — TOURS CERTIFICADOS DESDE CARTAGENA
# ===========================================================================

# ===========================================================================
# BLOQUE 3 — PRINCIPIANTES DESDE CARTAGENA
# ===========================================================================

# ===========================================================================
# BLOQUE 4 — YA EN LAS ISLAS
# ===========================================================================

# ===========================================================================
# BLOQUE 5 — GRUPO MIXTO (cart-style flow)
# ===========================================================================
# Detailed mixed-flow tests live near the bottom of this file. This block
# keeps a smoke test that the flow enters MIXED_ENTRY correctly.

# ===========================================================================
# BLOQUE 6 — CURSOS PADI
# ===========================================================================



























# ===========================================================================
# BLOQUE 7 — PRECIOS
# ===========================================================================













# ===========================================================================
# BLOQUE 8 — RESERVAS Y PAGOS
# ===========================================================================









# ===========================================================================
# BLOQUE 9 — LOGÍSTICA
# ===========================================================================















# ===========================================================================
# BLOQUE 10 — SELECTOR DE ISLA Y HOTEL
# ===========================================================================

















# ===========================================================================
# BLOQUE 11 — ESCALACIONES EXPLÍCITAS Y PALABRAS CLAVE
# ===========================================================================



@pytest.mark.asyncio
async def test_keyword_asesor_mid_flow():
    state = make_state()
    state.location = "cartagena"
    state.step = Step.MIXED_ADD_ACTIVITY  # mid-flow in the cart
    await route_message(state, "asesor")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None








@pytest.mark.asyncio
async def test_keyword_menu_resets_from_deep_step():
    state = make_state()
    state.location = "cartagena"
    state.step = Step.MIXED_ADD_CERT_PLAN  # deep in the cart flow
    await route_message(state, "menu")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_keyword_volver_goes_back_one_step():
    """'volver' from a deep cart step must go ONE step up, not to MAIN_MENU."""
    state = make_state()
    state.location = "cartagena"
    state.step = Step.MIXED_ADD_CERT_PLAN
    await route_message(state, "volver")
    assert state.step == Step.MIXED_ADD_ACTIVITY




@pytest.mark.asyncio
async def test_escalation_note_includes_service_if_known():
    state = make_state()
    state.location = "cartagena"
    state.selected_service = "2_dives_1_day"
    state.step = Step.MIXED_ADD_ACTIVITY
    await route_message(state, "asesor")
    assert state.pending_note is not None
    # Advisor note shows the friendly service name, not the raw id.
    assert "2_dives_1_day" not in state.pending_note
    assert "Servicio de interés:" in state.pending_note
    assert "2 inmersiones" in state.pending_note or "Salidas de Buceo" in state.pending_note


@pytest.mark.asyncio
async def test_escalation_note_includes_language():
    state = make_state()
    await send(state, "hello", "2")  # english
    await route_message(state, "advisor")
    assert state.pending_note is not None
    assert "English" in state.pending_note


# ===========================================================================
# BLOQUE 12 — ESCALACIONES SENSIBLES (MÉDICAS, CLIMA, TIEMPO REAL, QUEJAS)
# ===========================================================================



















# ===========================================================================
# BLOQUE 13 — PRIVACIDAD Y PII
# ===========================================================================









# ===========================================================================
# BLOQUE 14 — ENRUTAMIENTO RAG (TEXTO LIBRE EN MENÚ)
# ===========================================================================







@pytest.mark.asyncio
async def test_free_text_in_welcome_step_not_sent_to_rag_if_too_short():
    state = make_state()
    await route_message(state, "zzz")  # no language signal -> stays at LANGUAGE step
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        await route_message(state, "si")  # 1 palabra, sin "?" → tree, no RAG
    mock_rag.assert_not_called()






# ===========================================================================
# BLOQUE 15 — FLUJOS EN INGLÉS
# ===========================================================================







# ===========================================================================
# BLOQUE 16 — RESUMEN DE LEAD (CONTENIDO)
# ===========================================================================

@pytest.mark.asyncio
async def test_lead_summary_full_fields():
    state = make_state()
    state.language = "es"
    state.selected_service = "5_dives_2_days"
    state.location = "island"
    state.island = "Isla Grande"
    state.hotel = "Cocoliso Island Resort"
    state.is_certified = True
    state.is_colombian = True
    state.last_dive_over_2_years = True
    state.has_500_dives_or_dive_master = False
    state.refresher_interested = True
    state.history = [{"role": "user", "content": "hola, quiero bucear"}]
    note = build_lead_summary(state, "solicitó asesor")
    assert "Español" in note
    # Friendly service name, not the raw id, in the advisor note.
    assert "5_dives_2_days" not in note
    assert "Servicio de interés:" in note and "5 inmersiones" in note
    assert "Islas del Rosario" in note
    assert "Isla Grande" in note
    assert "Cocoliso" in note
    assert "Sí" in note       # is_certified
    assert "Colombiano" in note or "colombian" in note.lower()
    assert "más de 2 años" in note
    assert "refresher" in note.lower()
    assert "solicitó asesor" in note
    assert "hola, quiero bucear" in note


@pytest.mark.asyncio
async def test_lead_summary_english():
    state = make_state()
    state.language = "en"
    state.selected_service = "2_dives_1_day"
    state.location = "cartagena"
    state.is_certified = False
    note = build_lead_summary(state, "requested advisor")
    assert "English" in note
    # Friendly service name, not the raw id.
    assert "2_dives_1_day" not in note
    assert "Fun Dives" in note
    assert "Cartagena" in note
    assert "principiante" in note.lower() or "No" in note


@pytest.mark.asyncio
async def test_lead_summary_minimal_state():
    state = make_state()
    note = build_lead_summary(state, "test")
    assert "Lead Diving Planet" in note
    assert "test" in note


@pytest.mark.asyncio
async def test_lead_summary_truncates_long_messages():
    state = make_state()
    state.history = [{"role": "user", "content": "a" * 200}]
    note = build_lead_summary(state)
    assert "…" in note




# ===========================================================================
# BLOQUE 17 — OPCIONES INVÁLIDAS Y ROBUSTEZ
# ===========================================================================















# ===========================================================================
# BLOQUE 18 — QUICK REPLIES CORRECTOS
# ===========================================================================









# ===========================================================================
# BLOQUE 19 — ENRUTAMIENTO RAG: NUEVOS TEMAS OPERATIVOS
# Tests that verify questions about food, photos, hours, closed days, Barú,
# adaptive diving, and other PDF-sourced topics reach RAG (not escalation).
# ===========================================================================





































# ===========================================================================
# BLOQUE 20 — BUCEO ADAPTADO: NO ESCALA COMO MÉDICO
# Disability-related questions must go to RAG, not trigger medical escalation.
# The escalation keywords cover medical conditions (asthma, heart, surgery...)
# but not disability/accessibility inquiries.
# ===========================================================================















# ===========================================================================
# BLOQUE 21 — CONTENIDO DE RESPUESTAS DEL ÁRBOL (NUEVOS DATOS)
# Tests that verify tree-generated responses include key factual content
# from the expanded knowledge base.
# ===========================================================================

























# ===========================================================================
# Cart-style mixed-group flow tests
# ===========================================================================

async def reach_mixed_entry(lang: str = "es", location: str | None = "cartagena") -> ConversationState:
    """Reach MIXED_ENTRY from the unified booking entry."""
    state = await reach_main_menu(lang)
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
    if location is not None:
        state.location = location
    return state


async def reach_mixed_add_activity(lang: str = "es", location: str = "cartagena") -> ConversationState:
    """Reach MIXED_ADD_ACTIVITY by advancing past the entry intro."""
    state = await reach_mixed_entry(lang, location)
    await route_message(state, "1")  # ¡Vamos a empezar!
    assert state.step == Step.MIXED_ADD_ACTIVITY
    return state


# --- Free-text cert split: no double-add of the minicourse -----------------



# --- Entry / add activity ---------------------------------------------------



















# --- Info link in the per-activity preview and the cart review -------------
# Requested by the owner: at both of these points the client doesn't need to
# wait for the nationality question (which only affects the BOOKING link with
# its 10% online discount) to get the informational page for the service —
# that link is the same regardless of nationality.









# --- "Cómo reservo?" with a known activity -> direct info link, no RAG -----
# Owner request (2026-07-16): reduce friction — when we already know exactly
# which activity the client wants, a booking-process question should get the
# activity's own info link directly, not the generic RAG answer (exoneration
# form + manual 50% payment + advisor confirmation) and not a nudge toward
# "confirmar carrito".













# --- Preview shows total price for a known group size -----------------------





# --- Availability/dates questions mid-flow ----------------------------------









# --- Info questions mid-cart never get misfired as cart actions ------------





# --- extra_context injects ground-truth includes/not_included --------------







def test_extra_context_includes_current_datetime():
    """Regression: RAG had no real-time awareness, so it hallucinated that a
    time-based cutoff ("cierra a las 4:30 PM del dia anterior") had already
    passed regardless of the actual wall-clock time. The current date/time
    (Colombia) must be injected so the LLM can reason about it instead of
    guessing."""
    from src.agents.supervisor import _build_extra_context

    state = ConversationState(conversation_id="extra-context-datetime-es")
    context = _build_extra_context(state)
    assert "Fecha y hora actual:" in context
    assert "hora de Cartagena/Colombia" in context

    state_en = ConversationState(conversation_id="extra-context-datetime-en")
    state_en.language = "en"
    context_en = _build_extra_context(state_en)
    assert "Current date and time:" in context_en




# --- Qty handling ----------------------------------------------------------









# --- Cart review actions ---------------------------------------------------















# --- Final questions -------------------------------------------------------

























@pytest.mark.asyncio
async def test_final_summary_booking_link_localized_to_english():
    """English conversation → booking link uses ?language=en (catalog stores es)."""
    from src.flows.decision_tree import DecisionTree
    state = make_state(lang="en")
    state.mixed_cart = [{"type": "cert", "qty": 1, "plan": "2_dives_1_day", "label": "Diving"}]
    state.mixed_display_currency = "USD"
    resp = DecisionTree()._goto_mixed_final_summary(state)
    assert "language=en" in resp
    assert "language=es" not in resp


@pytest.mark.asyncio
async def test_final_summary_generic_link_uses_info_plus_advisor():
    """A plan without a direct book.divingplanet.org checkout (info-only page)
    must NOT promise 'book online' — it shows the info link + an advisor handoff
    to book (no WhatsApp number handed out, owner decision 2026-07-20)."""
    from src.flows.decision_tree import DecisionTree
    state = make_state()
    state.mixed_cart = [{"type": "cert", "qty": 2, "plan": "3_dives_1_day", "label": "3 dives"}]
    state.mixed_display_currency = "USD"
    resp = DecisionTree()._goto_mixed_final_summary(state)
    assert "divingplanet.org/tours" in resp          # generic info page
    assert "book.divingplanet.org" not in resp        # no fake checkout link
    assert "asesor" in resp.lower()                    # advisor handoff to book
    assert "231515" not in resp                        # never hand out the number
    assert "reservando online" not in resp             # no false online-booking claim
    assert "Más información" in resp


@pytest.mark.asyncio
async def test_final_summary_price_arithmetic_adds_up():
    """qty × per-person must equal the shown subtotal (round p.p. first, then
    multiply) — a fractional catalog price must not produce '2 × $126 = $251'."""
    import re

    from src.flows.decision_tree import DecisionTree
    state = make_state()
    state.mixed_cart = [{"type": "snorkel", "qty": 12, "label": "Snorkel"}]  # $125.57 p.p.
    state.mixed_display_currency = "USD"
    resp = DecisionTree()._goto_mixed_final_summary(state)
    m = re.search(r"(\d+) × \$(\d+) USD p\.p\. = \*\$(\d+) USD\*", resp)
    assert m, resp
    qty, pp, sub = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert pp * qty == sub  # shown arithmetic is internally consistent


@pytest.mark.asyncio
async def test_final_summary_direct_checkout_says_book_online():
    """A plan with a direct book.divingplanet.org checkout keeps the online CTA."""
    from src.flows.decision_tree import DecisionTree
    state = make_state()
    state.mixed_cart = [{"type": "cert", "qty": 1, "plan": "5_dives_2_days", "label": "5 dives"}]
    state.mixed_display_currency = "USD"
    resp = DecisionTree()._goto_mixed_final_summary(state)
    assert "book.divingplanet.org" in resp
    assert "reservando online" in resp
    assert "haz clic aquí" in resp.lower()




# --- LLM intent classifier (mocked) ----------------------------------------

@pytest.mark.parametrize("ans", [
    "no sé, tú qué recomiendas",
    "recomiéndame",
    "da igual",
    "cuál es mejor",
    "el que sea",
    "what do you recommend",
])
def test_vague_location_answer_recommends_cartagena(ans):
    """#BUG3: at the origin question, a deferring answer ('no sé, recomiéndame')
    must get a recommendation (Cartagena, the most common) and proceed, not
    'no te entendí'."""
    from src.flows.decision_tree import DecisionTree
    dt = DecisionTree()
    st = make_state()
    st.step = Step.MIXED_LOCATION
    st.mixed_pending_qty_type = "cert"
    st.mixed_cart = []
    dt.set_quick_replies(st, "tours_location")
    resp = dt._handle_mixed_location(st, ans)
    assert st.location == "cartagena"
    assert "no te entend" not in resp.lower()
    assert "cartagena" in resp.lower()




@pytest.mark.asyncio
async def test_bare_certified_question_still_answered_not_hijacked(agent_decides):
    """A certified diver ASKING something ('soy certificado, ¿tienen wifi?') must
    NOT be force-routed into the booking flow — the '?' guard keeps it a question."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    await route_message(state, "soy certificado, ¿qué precios manejan?")
    assert state.step != Step.MIXED_LOCATION


# --- Real bug (live PRE, 2026-07-21): pending certification question lost -----
# when the orchestrator reads the NEXT message as a location answer instead.









@pytest.mark.asyncio
async def test_mixed_group_split_statement_enters_guided_flow_not_rag(agent_decides):
    """Real bug (live PRE, 2026-07-21): "somos 5 amigos, 3 certificados y 2 sin
    certificar, queremos un paquete de varios dias" has a full group split
    (regex resolves group_allocation={certified_diving: 3, minicourse: 2}) but
    the orchestrator classified it as answer_question live, and NEITHER
    _should_skip_to_certified_flow (needs is_certified is True) NOR
    _should_ask_certification (needs is_certified is None) covers this case
    (aggregate is_certified is False here) — so _should_enter_mixed_flow, which
    already exists and is checked first inside _route_detected_intent, was
    never reached at all. The message fell entirely to RAG, which hallucinated
    a wrong policy ("the non-certified friends must do the Open Water course
    first") instead of the correct, already-implemented deterministic offer
    (minicourse always available; Open Water ALSO offered when the cert
    subgroup stays multiple days — see decision_tree._maybe_start_pending_beginner)."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    resp = await route_message(
        state,
        "somos 5 amigos, 3 certificados y 2 sin certificar, queremos un paquete de varios dias",
    )
    assert state.step != Step.MAIN_MENU, "must have entered the guided mixed-cart flow"
    assert "open water" not in resp.lower(), "must not fall to RAG inventing a policy"


def test_non_cert_companion_single_day_offers_minicourse_not_open_water():
    """Business rule confirmed by the owner (2026-07-21): a non-certified
    companion always gets the minicourse offer; Open Water is only ALSO
    offered when the certified subgroup's plan requires staying multiple days
    on the islands (they'd already be there). On a single-day plan, offering
    Open Water doesn't make sense (no extra days to actually do the course)."""
    from src.flows.decision_tree import DecisionTree
    state = make_state()
    state.mixed_pending_qty_plan = "2_dives_1_day"
    state.mixed_pending_beginner_after_cert = 1
    resp = DecisionTree()._maybe_start_pending_beginner(state)
    assert resp is not None
    assert "minicurso" in resp.lower()
    assert "open water" not in resp.lower()


def test_non_cert_companion_multi_day_offers_minicourse_and_open_water():
    from src.flows.decision_tree import DecisionTree
    state = make_state()
    state.mixed_pending_qty_plan = "5_dives_2_days"
    state.mixed_pending_beginner_after_cert = 1
    resp = DecisionTree()._maybe_start_pending_beginner(state)
    assert resp is not None
    assert "minicurso" in resp.lower()
    assert "open water" in resp.lower()


@pytest.mark.asyncio
async def test_specific_activity_statement_enters_guided_flow_not_rag(agent_decides):
    """Audit finding (2026-07-21), same class of bug as the mixed-group and
    certified-diver fallbacks: _intent_would_route() has 4 branches
    (_should_enter_mixed_flow, _should_skip_to_certified_flow, a bare
    "activity in (minicourse/snorkel/padi_*)" check, _should_ask_certification)
    but _dispatch_conversation_agent only had fallback coverage for 3 of them —
    the "specific activity" branch (snorkel/minicourse/PADI courses, regardless
    of certification) had NO fallback at all. So "quiero hacer snorkel, somos 2"
    misclassified by the orchestrator as answer_question fell entirely to RAG
    instead of entering the guided snorkel booking flow."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    await route_message(state, "quiero hacer snorkel, somos 2")
    assert state.step != Step.MAIN_MENU, "must have entered the guided snorkel flow"




@pytest.mark.asyncio
async def test_companion_question_not_hijacked_to_upsell(agent_decides):
    """A QUESTION about companions stays a RAG question, not the upsell flow."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    await route_message(state, "¿el acompañante paga lo mismo?")
    assert state.step != Step.MIXED_LOCATION
    assert state.step != Step.MIXED_COMPANION_UPSELL












# ===========================================================================
# Broken-link complaint detection
# ===========================================================================


@pytest.mark.asyncio
async def test_broken_link_explicit_complaint_escalates_es():
    state = make_state()
    resp = await route_message(state, "el link de reserva no funciona")
    assert state.step == Step.ESCALATE
    assert "LINK ROTO" in (state.pending_escalation_reason or "")
    assert "enlace no te haya funcionado" in resp.lower() or "link" in resp.lower()


@pytest.mark.asyncio
async def test_broken_link_explicit_complaint_escalates_en():
    state = make_state(lang="en")
    resp = await route_message(state, "the link is broken")
    assert state.step == Step.ESCALATE
    assert "LINK ROTO" in (state.pending_escalation_reason or "")
    assert "link" in resp.lower()


@pytest.mark.asyncio
async def test_broken_link_followup_after_bot_link_escalates():
    """Complaint without mentioning 'link' word, after the bot sent a URL → still detected."""
    state = make_state()
    state.history.append({"role": "user", "content": "que precios tienes"})
    state.history.append({
        "role": "assistant",
        "content": "Aquí tienes: https://book.divingplanet.org/book/salidas-de-buceo/1?language=es",
    })
    await route_message(state, "no me funciona")
    assert state.step == Step.ESCALATE
    assert "LINK ROTO" in (state.pending_escalation_reason or "")


@pytest.mark.asyncio
async def test_broken_link_complaint_with_formulario_word_escalates():
    state = make_state()
    await route_message(state, "el formulario de exoneración no abre")
    assert state.step == Step.ESCALATE
    assert "LINK ROTO" in (state.pending_escalation_reason or "")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_ADMIN_KEY")),
    reason="Requires OpenAI credentials to run RAG end-to-end.",
)
async def test_unrelated_complaint_does_not_escalate_as_broken_link():
    """Unrelated 'no funciona' phrases (no link context, no recent URL) should not trigger."""
    state = make_state()
    # No URL in history, no link word in message
    await route_message(state, "mi tarjeta no funciona, ayuda")
    # We want this NOT to match broken-link; either RAG or other escalation
    assert "LINK ROTO" not in (state.pending_escalation_reason or "")


@pytest.mark.asyncio
async def test_broken_link_lead_note_has_priority_marker():
    state = make_state()
    await route_message(state, "el link de pago no carga")
    assert state.pending_note is not None
    assert "LINK ROTO" in state.pending_note


# ---------------------------------------------------------------------------
# Kids age question (MIXED_FINAL_KIDS) — 3 ranges, smart trigger
# ---------------------------------------------------------------------------

async def _put_cert_in_cart(state: ConversationState, qty: int = 2) -> None:
    """Helper: enter mixed flow with a single cert × qty item, no refresher."""
    state.step = Step.MIXED_ADD_QTY
    state.mixed_pending_qty_type = "cert"
    state.mixed_pending_qty_plan = "2_dives_1_day"
    state.location = "cartagena"
    state.mixed_entry_path = "diving_snorkel"
    await route_message(state, str(qty))   # qty → cert_last_dive
    await route_message(state, "2")        # < 2 years
    await route_message(state, "1")        # add to cart → cart_review


async def _put_snorkel_in_cart(state: ConversationState, qty: int = 3) -> None:
    state.step = Step.MIXED_ADD_QTY
    state.mixed_pending_qty_type = "snorkel"
    state.location = "cartagena"
    state.mixed_entry_path = "diving_snorkel"
    await route_message(state, str(qty))   # qty → preview
    await route_message(state, "1")        # add to cart → cart_review


async def _put_beginner_in_cart(state: ConversationState, qty: int = 2, kids_choice: str = "3") -> None:
    """Helper: enter mixed flow with a single beginner × qty item.

    Inline kids question fires after qty; defaults to "3" (all 10+) so callers
    that don't care about kids context get a clean cart. Tests that DO care
    can pass kids_choice (and answer the count/U8/810 sub-questions themselves
    via subsequent route_message calls).
    """
    state.step = Step.MIXED_ADD_QTY
    state.mixed_pending_qty_type = "beginner"
    state.location = "cartagena"
    state.mixed_entry_path = "diving_snorkel"
    await route_message(state, str(qty))       # qty → kids question
    await route_message(state, kids_choice)    # kids range (default "3" = ten_plus → preview)
    await route_message(state, "1")            # add to cart → cart_review


async def _arrive_at_kids_inline(qty: int = 2) -> ConversationState:
    """Helper: reach MIXED_FINAL_KIDS step inline (after picking beginner + qty)."""
    state = await reach_mixed_add_activity()
    await route_message(state, "2")          # pick beginner
    await route_message(state, str(qty))     # qty → MIXED_FINAL_KIDS
    return state




@pytest.mark.asyncio
async def test_kids_question_not_asked_for_snorkel_only_cart():
    """Snorkel-only cart never goes through the kids inline flow."""
    state = make_state()
    await _put_snorkel_in_cart(state, 3)
    # Cart has only snorkel — never hit MIXED_FINAL_KIDS at any point.
    await route_message(state, "6")  # checkout (cart-action 6)
    await route_message(state, "2")  # No colombiano
    assert state.step != Step.MIXED_FINAL_KIDS


@pytest.mark.asyncio
async def test_kids_question_skipped_for_cert_only_adult_cart():
    """Cert-only cart never triggers kids question (inline only fires on beginner add)."""
    state = make_state()
    await _put_cert_in_cart(state, 2)
    await route_message(state, "6")  # checkout (cart-action 6)
    await route_message(state, "2")  # No colombiano → summary (private question removed)
    assert state.step != Step.MIXED_FINAL_KIDS
    assert state.step == Step.FREE_TEXT






@pytest.mark.asyncio
async def test_kids_mention_persists_across_turns():
    """Once kids_mention_detected, stays True for the rest of conversation."""
    state = make_state()
    await route_message(state, "1")
    await route_message(state, "tengo 3 hijos pequeños")
    assert state.kids_mention_detected is True
    await route_message(state, "menu")
    await route_message(state, "1")
    assert state.kids_mention_detected is True


@pytest.mark.asyncio
async def test_detect_kids_mention_excludes_friends():
    """Companion words alone (amigos, pareja) do NOT activate kids detection."""
    from src.agents.supervisor import _detect_kids_mention
    assert _detect_kids_mention("tengo 3 amigos") is False
    assert _detect_kids_mention("voy con mi pareja") is False
    assert _detect_kids_mention("vengo con mi esposo") is False
    # But explicit kid words do
    assert _detect_kids_mention("tengo 3 hijos") is True
    assert _detect_kids_mention("voy con mis sobrinos") is True
    assert _detect_kids_mention("with my children") is True


@pytest.mark.asyncio
async def test_detect_kids_mention_covers_grandchildren_and_baby():
    """'nieto'/'bebé' and EN 'grandchild'/'baby' were missing — real gap found
    2026-07-16 alongside several other narrow word-list bugs."""
    from src.agents.supervisor import _detect_kids_mention
    assert _detect_kids_mention("vengo con mis nietos de 8 y 10") is True
    assert _detect_kids_mention("traigo a mi bebe") is True
    assert _detect_kids_mention("coming with my grandson") is True
    assert _detect_kids_mention("coming with my baby") is True


@pytest.mark.asyncio
async def test_detect_companion_intent_covers_english_family_words():
    """The ES side already covered 'mi hermano/esposo/madre' via regex, but
    there was no English equivalent at all ('my brother'/'my wife' etc.) —
    real ES/EN asymmetry found 2026-07-16."""
    from src.agents.supervisor import _detect_companion_intent
    assert _detect_companion_intent("my brother is coming with me, what do you offer") is True
    assert _detect_companion_intent("my wife is coming with me too") is True
    assert _detect_companion_intent("mi hermano viene conmigo") is True


@pytest.mark.asyncio
async def test_mentions_diving_intent_covers_buzo_noun_and_diver():
    """_mentions_diving_intent only matched verb forms of 'bucear', not the
    noun 'buzo' or English 'diver' — same shape as the _OVERVIEW_DIVING_WORD
    bug fixed earlier this session (v0.20.12), found here too on 2026-07-16."""
    from src.agents.supervisor import _mentions_diving_intent, _mentions_snorkeling_intent
    assert _mentions_diving_intent("yo hago snorkel y mi amigo es buzo") is True
    assert _mentions_diving_intent("my friend is a certified diver") is True
    assert _mentions_snorkeling_intent("quiero hacer careteo") is True


















# ────────────────────────────────────────────────────────────────────────
# Mixed-age ranges within a single beginner cart item (Varios rangos)
# ────────────────────────────────────────────────────────────────────────


















# ────────────────────────────────────────────────────────────────────────
# Large-group kids quantity ("6+" → escribir número exacto)
# ────────────────────────────────────────────────────────────────────────


async def _arrive_at_kids_inline_large(qty: int) -> ConversationState:
    """Helper: reach MIXED_FINAL_KIDS with a beginner of qty > 6 (uses 6+ exact path)."""
    state = await reach_mixed_add_activity()
    await route_message(state, "2")              # pick beginner
    await route_message(state, "6+")             # 6 or more → ask exact
    await route_message(state, str(qty))         # exact qty → kids step
    return state












# ────────────────────────────────────────────────────────────────────────
# Cambiar origen desde el carrito
# ────────────────────────────────────────────────────────────────────────
















@pytest.mark.asyncio
async def test_cart_change_location_course_plan_remaps_to_island_variant():
    """For course items with location-variant plans, the plan field is swapped."""
    state = make_state()
    state.location = "cartagena"
    state.language = "es"
    state.mixed_cart = [
        {"type": "course", "qty": 1, "plan": "open_water", "label": "Curso Open Water Diver PADI"},
    ]
    from src.flows.decision_tree import DecisionTree
    dt = DecisionTree()
    state.location = "island"
    dt._remap_cart_for_location(state)
    assert state.mixed_cart[0]["plan"] == "open_water_already_on_island"
    # And back
    state.location = "cartagena"
    dt._remap_cart_for_location(state)
    assert state.mixed_cart[0]["plan"] == "open_water"


# ---------------------------------------------------------------------------
# Intent Detection - Smart Free Text Understanding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intent_minicourse_skips_certification():
    """'Quiero hacer el minicurso' should detect beginner and skip cert question."""
    state = make_state()
    await route_message(state, "Hola quiero hacer el minicurso de buceo, es mi primera vez")

    assert state.language == "es"
    assert state.detected_activity == "minicourse"
    assert state.detected_is_certified is False


@pytest.mark.asyncio
async def test_intent_group_size_detected():
    """'Somos tres personas' should detect group size."""
    state = make_state()
    await route_message(state, "Hola somos tres personas que queremos hacer snorkel")

    assert state.detected_group_size == 3
    assert state.detected_activity == "snorkel"


@pytest.mark.asyncio
async def test_intent_location_detected():
    """'Estoy en Cartagena' should detect location."""
    state = make_state()
    await route_message(state, "Hola quiero bucear, estoy en Cartagena y soy certificado")

    assert state.detected_location == "cartagena"
    assert state.location == "cartagena"
    assert state.detected_is_certified is True


@pytest.mark.asyncio
async def test_intent_padi_course_detection():
    """'Quiero hacer el curso Open Water' should detect PADI course."""
    state = make_state()
    await route_message(state, "Hola quiero hacer el curso PADI Open Water")

    # Should detect Spanish and PADI course intent
    assert state.detected_activity == "padi_open_water"
    assert state.detected_service_id == "open_water"


@pytest.mark.asyncio
async def test_intent_specialty_detection():
    """'Quiero hacer el curso de nitrox' should detect specialty."""
    state = make_state()
    await route_message(state, "Hola quiero hacer el curso de nitrox")

    assert state.language == "es"
    assert state.detected_activity == "padi_specialty"
    assert state.detected_service_id == "nitrox"


@pytest.mark.asyncio
async def test_intent_hotel_detection():
    """'Estoy en el hotel Pao Pao' should detect hotel."""
    state = make_state()
    await route_message(state, "Hola estoy en el hotel Pao Pao y quiero hacer snorkel")

    assert state.detected_hotel == "pao_pao"
    assert state.hotel == "pao_pao"


@pytest.mark.asyncio
async def test_intent_duration_multi_day():
    """'Estoy varios días' should detect multi-day."""
    state = make_state()
    await route_message(state, "Quiero bucear, estoy varios días en las islas")

    assert state.detected_duration == "multi_day"




@pytest.mark.asyncio
async def test_intent_does_not_trigger_on_very_short_input():
    """Intent detection should not run on very short inputs."""
    state = make_state()

    # Send very short message
    await route_message(state, "hi")

    # Should not have triggered significant intent detection
    # (might detect language but that's ok)


# ---------------------------------------------------------------------------
# Refresher split review — regression for wrong service in cart
# ---------------------------------------------------------------------------





# ===========================================================================
# BLOQUE — TYPO TOLERANCE: cantidad con typo en MIXED_ADD_QTY
# Regression test for the bug where "somos cuatr personas" (typo of "cuatro")
# was routed to the LLM orchestrator instead of the tree handler, causing
# the bot to re-show the cert plan selection instead of accepting the quantity.
# ===========================================================================





# ===========================================================================
# BLOQUE — CANCELACIÓN Y REPROGRAMACIÓN DE RESERVAS EXISTENTES
# Los clientes que piden cancelar o cambiar la fecha de una reserva existente
# deben recibir el texto de política + dos botones (asesor / menú principal),
# nunca entrar al flujo de reserva ni recibir una respuesta genérica de RAG.
# ===========================================================================

@pytest.mark.asyncio
async def test_cancel_booking_explicit_es_shows_policy_and_buttons():
    """'quiero cancelar mi reserva' → policy text + advisor/home buttons."""
    state = make_state()
    resp = await route_message(state, "quiero cancelar mi reserva")
    assert state.step != Step.ESCALATE, "Debe mostrar botones, no escalar automáticamente"
    assert "terminos" in resp.lower() or "condiciones" in resp.lower() or "cancelaci" in resp.lower()
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values
    assert "inicio" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_phrase_without_possessive_es():
    """'cancelar la reserva' (sin 'mi') también activa la detección."""
    state = make_state()
    await route_message(state, "cancelar la reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_quisiera_variant_es():
    """'quisiera cancelar mi reserva' también activa la detección."""
    state = make_state()
    await route_message(state, "quisiera cancelar mi reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_anular_variant_es():
    """'anular mi reserva' debe activar el detector."""
    state = make_state()
    await route_message(state, "anular mi reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_accent_insensitive_es():
    """Con tildes ('cancelar mi reservación') también debe detectarse."""
    state = make_state()
    await route_message(state, "necesito cancelar mi reservación")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_explicit_en_shows_policy_and_buttons():
    """'cancel my booking' → policy text + advisor/home buttons (EN)."""
    state = make_state(lang="en")
    resp = await route_message(state, "cancel my booking")
    assert "terms" in resp.lower() or "condition" in resp.lower() or "cancel" in resp.lower()
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values
    assert "inicio" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_how_do_i_cancel_en():
    """'how do i cancel my booking' also triggers detection (EN)."""
    state = make_state(lang="en")
    await route_message(state, "how do i cancel my booking")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_advisor_button_escalates():
    """After the cancel-info response, clicking 'asesor' escalates correctly."""
    state = make_state()
    await route_message(state, "quiero cancelar mi reserva")
    await route_message(state, "asesor")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_reschedule_explicit_es_shows_policy_and_buttons():
    """'cambiar la fecha' → reschedule policy text + advisor/home buttons."""
    state = make_state()
    resp = await route_message(state, "cambiar la fecha de mi reserva")
    assert "fecha" in resp.lower() or "disponibilidad" in resp.lower() or "condiciones" in resp.lower()
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values
    assert "inicio" in button_values


@pytest.mark.asyncio
async def test_reschedule_quisiera_variant_es():
    """'quisiera cambiar la fecha' también activa la detección."""
    state = make_state()
    await route_message(state, "quisiera cambiar la fecha")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_reschedule_reprogramar_variant_es():
    """'reprogramar mi reserva' activa la detección."""
    state = make_state()
    await route_message(state, "reprogramar mi reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_reschedule_explicit_en_shows_policy_and_buttons():
    """'reschedule my booking' → reschedule policy text + advisor/home buttons (EN)."""
    state = make_state(lang="en")
    await route_message(state, "reschedule my booking")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values
    assert "inicio" in button_values


@pytest.mark.asyncio
async def test_reschedule_i_would_like_to_reschedule_en():
    """'i'd like to reschedule' triggers detection (EN)."""
    state = make_state(lang="en")
    await route_message(state, "i'd like to reschedule my booking")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values






# --- Bare affirmation after the bot offered advisor contact ------------------




@pytest.mark.asyncio
async def test_bare_si_without_offer_does_not_escalate():
    state = ConversationState(conversation_id="si-offer-2")
    state.step = Step.MAIN_MENU
    state.language = "es"
    state.history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"},
    ]
    await route_message(state, "si")
    assert state.step != Step.ESCALATE


# --- Real bug (live PRE, 2026-07-17): questions ignored at MIXED_CERT_LAST_DIVE /
# MIXED_CERT_REFRESH_INTEREST ------------------------------------------------
# supervisor.py forces ANY message back into the raw tree handler for a fixed
# list of "critical steps", assuming the handler can parse free text.
# MIXED_CERT_LAST_DIVE and MIXED_CERT_REFRESH_INTEREST are pure yes/no button
# steps with NO fallback at all — any genuine question got silently swallowed
# into "no entendí", blocking the conversation entirely.
#
# CORRECTION (found later, same day, live PRE): MIXED_LOCATION/MIXED_ADD_QTY/
# MIXED_CERT_REFRESH_QTY were assumed "safe" here because they DO have real
# free-text parsing — but that parsing only covers THEIR OWN domain (location
# keywords, quantities). Anything outside that domain (a genuine unrelated
# question) still falls through to the same "no entendí" dead end inside
# those handlers. See the second block of tests below.

async def _reach_mixed_cert_last_dive(lang: str = "es") -> ConversationState:
    state = ConversationState(conversation_id="last-dive-question-test")
    state.language = lang
    msg = (
        "Hola, somos 2, certificados, queremos bucear desde Cartagena"
        if lang == "es"
        else "Hi, we are 2 certified divers, want to dive from Cartagena"
    )
    await route_message(state, msg)
    for _ in range(6):
        if state.step == Step.MIXED_CERT_LAST_DIVE:
            break
        await route_message(state, "1")
    assert state.step == Step.MIXED_CERT_LAST_DIVE
    return state








# --- Real bug (live PRE, 2026-07-17, second occurrence): same dead end at ----
# MIXED_LOCATION / MIXED_ADD_QTY / MIXED_CERT_REFRESH_QTY. These steps DO
# parse their own domain (location keywords / quantities), but any genuine
# off-topic question still fell to "no entendí" instead of RAG.









# ── Post-recommendation cert steps: multi-day switch & companion by text ──
# After the 2-dive recommendation the flow lands deep (last-dive / preview),
# past MIXED_ADD_QTY where these text handlers used to live. Regression from the
# owner's live test (2026-07-21): a multi-day request fell to a RAG blurb while
# the booking stayed 2-dive, and an added snorkel companion was dropped.







# --- Real bug (live PRE, 2026-07-21, second occurrence): same gap at an -----
# EVEN EARLIER step. A customer who keeps asking free-text questions (price,
# gear, cancellation) before ever resolving MIXED_LOCATION stays there — the
# multi-day-switch interceptor only covered 3 later steps, so an explicit
# "actually, 3 days instead" said from MIXED_LOCATION fell through unhandled.



@pytest.mark.asyncio
async def test_multiday_phrasing_at_location_step_does_not_misfire_for_other_activity(agent_decides):
    """The broadened step set must NOT hijack a customer whose activity isn't
    certified diving at all — MIXED_LOCATION is shared by every activity, and
    mixed_pending_qty_type isn't set yet at that point, so the guard must fall
    back to checking detected_activity instead of defaulting permissively."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = ConversationState(conversation_id="mday-no-misfire")
    state.language = "es"
    state.step = Step.MIXED_LOCATION
    state.detected_activity = "snorkel"
    state.mixed_pending_qty_type = None
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        await route_message(state, "en realidad quiero quedarme varios dias")
    # Must NOT have been silently rerouted into a cert multi-day plan resolution.
    assert state.mixed_pending_qty_plan not in ("5_dives_2_days", "7_dives_3_days", "9_dives_4_days")
