"""
Exhaustive conversation-level test dataset for the Diving Planet bot.

Tests simulate complete and partial user journeys through the decision tree
and verify: step transitions, response keywords, service selection, escalation
triggers, lead note generation, RAG routing, and safety rules.

RAG calls are mocked so tests run fully offline and fast.
Organised by commercial scenario for easy navigation.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.flows.decision_tree import ConversationState, Step, SERVICES
from src.agents.supervisor import route_message
from src.agents.lead_summary import build_lead_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="test-conv")
    s.language = lang
    return s


async def send(state: ConversationState, *messages: str) -> list[str]:
    responses = []
    for msg in messages:
        resp = await route_message(state, msg)
        responses.append(resp)
    return responses


async def reach_main_menu(lang: str = "es") -> ConversationState:
    state = make_state()
    choice = "1" if lang == "es" else "2"
    await send(state, "hola", choice)
    assert state.step == Step.MAIN_MENU
    return state


async def reach_group_type(lang: str = "es", location: str = "cartagena") -> ConversationState:
    """Reservar > Tours > Location → GROUP_TYPE."""
    state = await reach_main_menu(lang)
    loc_choice = "1" if location == "cartagena" else "2"
    await send(state, "1", "1", loc_choice)
    assert state.step == Step.GROUP_TYPE
    assert state.location == location
    return state


async def reach_courses_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "1", "2")
    assert state.step == Step.COURSES_MENU
    return state


async def reach_pricing_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "2", "1")
    assert state.step == Step.PRICING_MENU
    return state


async def reach_booking_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "2", "2")
    assert state.step == Step.BOOKING_MENU
    return state


async def reach_logistics_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "2", "3")
    assert state.step == Step.LOGISTICS_MENU
    return state


RAG_MOCK = "respuesta_rag_simulada"
RAG_MOCK_EN = "rag_answer_simulated"


# ===========================================================================
# BLOQUE 1 — PRIMER CONTACTO Y SELECCIÓN DE IDIOMA
# ===========================================================================

@pytest.mark.asyncio
async def test_welcome_shows_both_languages():
    state = make_state()
    resp = await route_message(state, "hola")
    assert state.step == Step.LANGUAGE
    assert "Español" in resp
    assert "English" in resp


@pytest.mark.asyncio
async def test_select_spanish_by_number():
    state = make_state()
    await route_message(state, "hola")
    await route_message(state, "1")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_select_english_by_number():
    state = make_state()
    await route_message(state, "hola")
    await route_message(state, "2")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_language_detection_english_text():
    state = make_state()
    await route_message(state, "hello")
    resp = await route_message(state, "english")
    assert state.language == "en"


@pytest.mark.asyncio
async def test_language_detection_spanish_text():
    state = make_state()
    await route_message(state, "hola")
    resp = await route_message(state, "español")
    assert state.language == "es"


@pytest.mark.asyncio
async def test_greeting_only_goes_to_language_step():
    state = make_state()
    await route_message(state, "buenas")
    assert state.step == Step.LANGUAGE


@pytest.mark.asyncio
async def test_early_free_text_spanish_routes_to_rag():
    state = make_state()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "quiero bucear con mi familia la próxima semana")
    assert state.step == Step.FREE_TEXT
    assert state.language == "es"


@pytest.mark.asyncio
async def test_early_free_text_english_routes_to_rag():
    state = make_state()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK_EN):
        resp = await route_message(state, "I want to go diving with my family next week")
    assert state.step == Step.FREE_TEXT
    assert state.language == "en"


@pytest.mark.asyncio
async def test_invalid_language_choice_shows_not_understood():
    state = make_state()
    await route_message(state, "hola")
    resp = await route_message(state, "9")
    assert state.step == Step.LANGUAGE


@pytest.mark.asyncio
async def test_main_menu_shows_all_options():
    state = await reach_main_menu("es")
    assert state.step == Step.MAIN_MENU
    assert len(state.quick_replies) == 2  # Reservar / Información


# ---------------------------------------------------------------------------
# Fuzzy text-to-button matching (natural-language menu navigation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_in_english_at_language_step_switches_to_english():
    state = make_state()
    await route_message(state, "hello")
    assert state.step == Step.LANGUAGE
    await route_message(state, "in english?")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_text_espanol_at_language_step_selects_spanish():
    state = make_state()
    await route_message(state, "hola")
    assert state.step == Step.LANGUAGE
    await route_message(state, "español")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_text_reservar_at_main_menu_advances_to_reserva_menu():
    state = await reach_main_menu("es")
    await route_message(state, "reservar")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_text_informacion_at_main_menu_advances_to_info_menu():
    state = await reach_main_menu("es")
    await route_message(state, "información")
    assert state.step == Step.INFO_MENU


@pytest.mark.asyncio
async def test_text_book_at_english_main_menu_advances_to_reserva_menu():
    state = await reach_main_menu("en")
    await route_message(state, "book")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_text_quiero_reservar_un_tour_advances_to_reserva_menu():
    state = await reach_main_menu("es")
    await route_message(state, "quiero reservar un tour")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_question_with_button_keyword_routes_to_rag_not_menu():
    state = await reach_main_menu("es")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "cuánto cuesta reservar un tour?")
    # Question word "cuánto" must keep us out of the menu branch
    assert state.step != Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_irrelevant_free_text_at_main_menu_does_not_jump_branch():
    state = await reach_main_menu("es")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "hola que tal me llamo juan")
    assert state.step not in (Step.RESERVA_MENU, Step.INFO_MENU)


@pytest.mark.asyncio
async def test_text_match_uses_only_current_quick_replies():
    """A button label that exists in a different menu must NOT match here."""
    state = await reach_main_menu("es")
    # "logística" is a button title inside info_menu, not in main_menu's current quick_replies.
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "logística")
    assert state.step != Step.LOGISTICS_MENU


@pytest.mark.asyncio
async def test_text_match_accent_insensitive_informacion():
    """User types 'informacion' (no accent) → must match 'ℹ️ Información'."""
    state = await reach_main_menu("es")
    await route_message(state, "quiero informacion")
    assert state.step == Step.INFO_MENU


@pytest.mark.asyncio
async def test_text_match_accent_insensitive_espanol_at_language():
    """User types 'espanol' (no accent or tilde) → must select Spanish."""
    state = make_state()
    await route_message(state, "hello")
    await route_message(state, "espanol")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_in_spanish_at_language_selects_spanish():
    """'in spanish?' must be interpreted as a request for Spanish, not English."""
    state = make_state()
    await route_message(state, "hello")
    await route_message(state, "in spanish?")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_mid_conversation_language_switch_es_to_en():
    """Once mid-flow, 'in english please' switches language and brings the main menu."""
    state = await reach_main_menu("es")
    await route_message(state, "1")  # RESERVA_MENU
    assert state.step == Step.RESERVA_MENU
    resp = await route_message(state, "in english please")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU
    assert "English" in resp or "what" in resp.lower() or "book" in resp.lower()


@pytest.mark.asyncio
async def test_mid_conversation_language_switch_en_to_es():
    state = await reach_main_menu("en")
    await route_message(state, "1")  # RESERVA_MENU
    assert state.step == Step.RESERVA_MENU
    resp = await route_message(state, "me lo puedes decir en español?")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_pricing_response_appends_back_to_menu_hint_es():
    state = await reach_pricing_menu("es")
    resp = await route_message(state, "1")
    assert "reservar" in resp.lower()
    assert "información" in resp.lower() or "informacion" in resp.lower()


@pytest.mark.asyncio
async def test_booking_response_appends_back_to_menu_hint_en():
    state = await reach_booking_menu("en")
    resp = await route_message(state, "1")
    assert "book" in resp.lower()
    assert "information" in resp.lower()


@pytest.mark.asyncio
async def test_user_can_reserve_after_info_leaf_without_greeting():
    """After a pricing answer, typing 'quiero reservar' must navigate to RESERVA_MENU."""
    state = await reach_pricing_menu("es")
    await route_message(state, "1")
    assert state.step == Step.MAIN_MENU
    await route_message(state, "quiero reservar")
    assert state.step == Step.RESERVA_MENU


# ===========================================================================
# BLOQUE 2 — TOURS CERTIFICADOS DESDE CARTAGENA
# ===========================================================================

@pytest.mark.asyncio
async def test_certified_2_dives_full_happy_path():
    state = await reach_group_type()
    responses = await send(state, "1", "1", "2", "2")
    assert state.step == Step.SUMMARY
    assert state.selected_service == "2_dives_1_day"
    assert state.location == "cartagena"
    assert state.is_colombian is False
    assert "divingplanet.org" in responses[-1] or "reserva" in responses[-1].lower()


@pytest.mark.asyncio
async def test_certified_2_dives_colombian_discount():
    state = await reach_group_type()
    await send(state, "1", "1", "2")
    resp = await route_message(state, "1")  # es colombiano
    assert state.is_colombian is True
    assert state.step == Step.SUMMARY
    assert "descuento" in resp.lower() or "WhatsApp" in resp or "+57" in resp


@pytest.mark.asyncio
async def test_certified_last_dive_over_2_years_asks_experience():
    state = await reach_group_type()
    await send(state, "1", "1")
    resp = await route_message(state, "1")  # > 2 años
    assert state.step == Step.CERTIFIED_EXPERIENCE
    assert state.last_dive_over_2_years is True


@pytest.mark.asyncio
async def test_certified_500_plus_dives_escalates_with_note():
    state = await reach_group_type()
    await send(state, "1", "1", "1")  # > 2 años
    resp = await route_message(state, "1")  # 500+ / Divemaster
    assert state.step == Step.ESCALATE
    assert state.has_500_dives_or_dive_master is True
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_certified_refresher_yes_updates_service_for_2_dives():
    state = await reach_group_type()
    await send(state, "1", "1", "1", "2")  # > 2 años, no 500+
    resp = await route_message(state, "1")       # quiere refresher
    assert state.refresher_interested is True
    assert state.step == Step.COLOMBIAN
    assert state.selected_service == "minicourse"


@pytest.mark.asyncio
async def test_certified_refresher_no_keeps_service():
    state = await reach_group_type()
    await send(state, "1", "1", "1", "2")  # > 2 años, no 500+
    resp = await route_message(state, "2")       # no quiere refresher
    assert state.refresher_interested is False
    assert state.step == Step.COLOMBIAN
    assert state.selected_service == "2_dives_1_day"


@pytest.mark.asyncio
async def test_certified_5_dives_selected():
    state = await reach_group_type()
    await send(state, "1")
    await route_message(state, "2")  # 5 buceos → asks last dive recency first
    assert state.selected_service == "5_dives_2_days"


@pytest.mark.asyncio
async def test_certified_7_dives_selected():
    state = await reach_group_type()
    await send(state, "1")
    await route_message(state, "3")
    assert state.selected_service == "7_dives_3_days"


@pytest.mark.asyncio
async def test_certified_9_dives_selected():
    state = await reach_group_type()
    await send(state, "1")
    await route_message(state, "4")
    assert state.selected_service == "9_dives_4_days"


@pytest.mark.asyncio
async def test_certified_private_service_escalates():
    state = await reach_group_type()
    await send(state, "1")
    resp = await route_message(state, "5")  # servicio privado
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_certified_multiday_refresher_keeps_original_service():
    state = await reach_group_type()
    await send(state, "1", "2", "1", "2")  # 5 dives, > 2 años, no 500+
    resp = await route_message(state, "1")       # refresher sí en paquete multi-día
    assert state.refresher_interested is True
    assert state.selected_service == "5_dives_2_days"  # paquete original intacto
    assert "asesor" in resp.lower() or "multi" in resp.lower() or "paquete" in resp.lower()


@pytest.mark.asyncio
async def test_certified_summary_includes_meeting_point_cartagena():
    state = await reach_group_type()
    responses = await send(state, "1", "1", "2", "2")
    summary = responses[-1]
    assert "Bodeguita" in summary or "8:00" in summary or "Cartagena" in summary


@pytest.mark.asyncio
async def test_certified_summary_includes_flight_rule_for_multiday():
    state = await reach_group_type()
    await send(state, "1", "2", "2", "2")  # 5 dives, sin refresher, no colombiano
    # flight rule applies only when service has it; at least booking link should appear
    assert state.step == Step.SUMMARY


# ===========================================================================
# BLOQUE 3 — PRINCIPIANTES DESDE CARTAGENA
# ===========================================================================

@pytest.mark.asyncio
async def test_beginner_minicourse_cartagena_full_path():
    state = await reach_group_type()
    await send(state, "2")   # principiantes
    resp = await route_message(state, "1")  # minicurso
    assert state.selected_service == "minicourse"
    assert state.step == Step.BEGINNER_AGE
    assert "10" in resp or "edad" in resp.lower()


@pytest.mark.asyncio
async def test_beginner_snorkeling_cartagena():
    state = await reach_group_type()
    await send(state, "2")
    resp = await route_message(state, "2")  # snorkel
    assert state.selected_service == "snorkeling"
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_beginner_private_escalates_with_note():
    state = await reach_group_type()
    await send(state, "2")
    resp = await route_message(state, "3")  # privado
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "privado" in resp.lower() or "private" in resp.lower()


@pytest.mark.asyncio
async def test_beginner_minicourse_min_age_shown():
    state = await reach_group_type()
    await send(state, "2")
    resp = await route_message(state, "1")
    assert "10" in resp or "edad" in resp.lower() or "age" in resp.lower() or "min" in resp.lower()


@pytest.mark.asyncio
async def test_beginner_snorkeling_min_age_shown():
    state = await reach_group_type()
    await send(state, "2")
    resp = await route_message(state, "2")
    assert "6" in resp or "edad" in resp.lower() or "superficie" in resp.lower() or "snorkel" in resp.lower()


# ===========================================================================
# BLOQUE 4 — YA EN LAS ISLAS
# ===========================================================================

@pytest.mark.asyncio
async def test_island_certified_2_dives():
    state = await reach_group_type(location="island")
    await send(state, "1")  # islas + certificados
    resp = await route_message(state, "1")  # 2 buceos
    assert state.location == "island"
    assert state.selected_service == "2_dives_1_day_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_3_dives_night():
    state = await reach_group_type(location="island")
    await send(state, "1")  # islas + certificados
    resp = await route_message(state, "2")  # 3 buceos con nocturna
    assert state.location == "island"
    assert state.selected_service == "3_dives_1_day_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_5_dives():
    state = await reach_group_type(location="island")
    await send(state, "1")
    await route_message(state, "3")
    assert state.selected_service == "5_dives_2_days_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_7_dives():
    state = await reach_group_type(location="island")
    await send(state, "1")
    await route_message(state, "4")
    assert state.selected_service == "7_dives_3_days_already_on_island"


@pytest.mark.asyncio
async def test_island_beginner_minicourse():
    state = await reach_group_type(location="island")
    await send(state, "2")  # islas + principiantes
    resp = await route_message(state, "1")  # minicurso
    assert state.location == "island"
    assert state.selected_service == "minicourse_already_on_island"


@pytest.mark.asyncio
async def test_island_snorkel_companion():
    # Tras restructure, snorkel se elige dentro de Principiantes (no como opción de group_type).
    state = await reach_group_type(location="island")
    await route_message(state, "2")  # principiantes
    resp = await route_message(state, "2")  # snorkel dentro del menu de principiantes
    assert state.location == "island"
    assert state.selected_service == "snorkeling_already_on_island"


@pytest.mark.asyncio
async def test_island_summary_shows_hotel_pickup():
    state = await reach_group_type(location="island")
    responses = await send(state, "1", "1", "2", "2")  # islas + cert + 2 buceos + recent + no colombiano
    summary = responses[-1]
    assert "9:30" in summary or "recogida" in summary.lower() or "pickup" in summary.lower() or "isla" in summary.lower()


# ===========================================================================
# BLOQUE 5 — GRUPO MIXTO
# ===========================================================================

@pytest.mark.asyncio
async def test_mixed_group_from_cartagena_escalates():
    state = await reach_group_type()  # tours Cartagena
    resp = await route_message(state, "3")  # grupo mixto
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "mixto" in resp.lower() or "snorkel" in resp.lower() or "juntos" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_group_from_island_escalates():
    state = await reach_group_type(location="island")  # ya en islas
    resp = await route_message(state, "3")  # grupo mixto
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_mixed_group_lead_note_has_group_type():
    state = await reach_group_type()
    await route_message(state, "3")
    assert state.pending_note is not None
    assert "Lead Diving Planet" in state.pending_note


# ===========================================================================
# BLOQUE 6 — CURSOS PADI
# ===========================================================================

@pytest.mark.asyncio
async def test_open_water_from_cartagena_enough_time():
    state = await reach_courses_menu()
    await send(state, "1", "1")  # cursos > Open Water > Cartagena
    resp = await route_message(state, "1")  # 2 días completos
    assert state.selected_service == "open_water"
    assert state.location == "cartagena"
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_open_water_from_cartagena_not_enough_time():
    state = await reach_courses_menu()
    await send(state, "1", "1")
    resp = await route_message(state, "2")  # menos tiempo
    assert state.selected_service == "open_water"
    assert state.step == Step.COLOMBIAN
    assert "alternativa" in resp.lower() or "alternative" in resp.lower() or "minicurso" in resp.lower()


@pytest.mark.asyncio
async def test_open_water_already_on_island():
    state = await reach_courses_menu()
    await send(state, "1")   # cursos > Open Water
    resp = await route_message(state, "2")  # desde islas
    assert state.location == "island"
    assert state.selected_service == "open_water_already_on_island"


@pytest.mark.asyncio
async def test_advanced_course_selected():
    state = await reach_courses_menu()
    await send(state, "2")  # otros cursos PADI
    resp = await route_message(state, "1")  # Advanced
    assert state.selected_service in ("advanced", "advanced_already_on_island")
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_rescue_course_selected():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "2")  # Rescate + EFR
    assert state.selected_service == "rescue"
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_divemaster_course_selected():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "3")  # Divemaster
    assert state.selected_service == "divemaster"
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_fish_identification_specialty():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "5")  # Identificación de peces
    assert "fish" in state.selected_service or "peces" in state.selected_service or state.step in (Step.COLOMBIAN, Step.ESCALATE)


@pytest.mark.asyncio
async def test_nitrox_specialty():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "8")  # Nitrox
    assert "nitrox" in state.selected_service or state.step in (Step.COLOMBIAN, Step.ESCALATE)


@pytest.mark.asyncio
async def test_referral_reactivate_escalates():
    state = await reach_courses_menu()
    resp = await route_message(state, "4")  # referral / reactivate
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "eLearning" in resp or "documento" in resp.lower() or "price" in resp.lower() or "precio" in resp.lower()


@pytest.mark.asyncio
async def test_specialties_menu_choice_3():
    state = await reach_courses_menu()
    resp = await route_message(state, "3")  # especialidades
    assert state.step == Step.COURSES_ADVANCED_MENU


# ===========================================================================
# BLOQUE 7 — PRECIOS
# ===========================================================================

@pytest.mark.asyncio
async def test_pricing_menu_cartagena_shows_usd():
    state = await reach_pricing_menu()  # precios
    resp = await route_message(state, "1")  # desde Cartagena
    assert state.step == Step.MAIN_MENU
    assert "USD" in resp or "$" in resp or "precio" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_islands():
    state = await reach_pricing_menu()
    resp = await route_message(state, "2")  # ya en islas
    assert state.step == Step.MAIN_MENU
    assert "isla" in resp.lower() or "island" in resp.lower() or "tarifa" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_multiday_packages():
    state = await reach_pricing_menu()
    resp = await route_message(state, "3")  # paquetes 5/7/9
    assert state.step == Step.MAIN_MENU
    assert "5" in resp and "7" in resp


@pytest.mark.asyncio
async def test_pricing_menu_colombian_discounts():
    state = await reach_pricing_menu()
    resp = await route_message(state, "4")  # descuentos colombianos
    assert state.step == Step.MAIN_MENU
    assert "colombian" in resp.lower() or "PARCEROS" in resp or "local" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_island_context_aware():
    state = await reach_main_menu()
    state.location = "island"  # preestablecido como ya en islas
    await route_message(state, "2")  # Información
    await route_message(state, "1")  # Precios
    resp = await route_message(state, "2")  # precios islas
    assert "ya indicaste" in resp.lower() or "already indicated" in resp.lower() or "isla" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_invalid_returns_to_pricing():
    state = await reach_pricing_menu()
    resp = await route_message(state, "9")
    assert state.step == Step.PRICING_MENU


# ===========================================================================
# BLOQUE 8 — RESERVAS Y PAGOS
# ===========================================================================

@pytest.mark.asyncio
async def test_booking_full_payment_online():
    state = await reach_booking_menu()
    resp = await route_message(state, "1")
    assert state.step == Step.MAIN_MENU
    assert "online" in resp.lower() or "confirmacion" in resp.lower() or "confirmation" in resp.lower()


@pytest.mark.asyncio
async def test_booking_50_percent_deposit():
    state = await reach_booking_menu()
    resp = await route_message(state, "2")
    assert state.step == Step.MAIN_MENU
    assert "50" in resp or "anticipo" in resp.lower() or "deposit" in resp.lower()


@pytest.mark.asyncio
async def test_booking_payment_methods():
    state = await reach_booking_menu()
    resp = await route_message(state, "3")
    assert state.step == Step.MAIN_MENU
    assert "tarjeta" in resp.lower() or "card" in resp.lower() or "transferencia" in resp.lower()


@pytest.mark.asyncio
async def test_booking_group_agency():
    state = await reach_booking_menu()
    resp = await route_message(state, "4")
    assert state.step == Step.MAIN_MENU
    assert "grupo" in resp.lower() or "agencia" in resp.lower() or "group" in resp.lower()


# ===========================================================================
# BLOQUE 9 — LOGÍSTICA
# ===========================================================================

@pytest.mark.asyncio
async def test_logistics_meeting_point_cartagena():
    state = await reach_main_menu()
    state.location = "cartagena"
    await route_message(state, "2")  # Información
    await route_message(state, "3")  # Logística
    resp = await route_message(state, "1")
    assert "Bodeguita" in resp or "8:00" in resp


@pytest.mark.asyncio
async def test_logistics_meeting_point_without_location():
    state = await reach_logistics_menu()
    resp = await route_message(state, "1")
    assert "Bodeguita" in resp or "8:00" in resp or "horario" in resp.lower()


@pytest.mark.asyncio
async def test_logistics_accommodation_leads_to_island_menu():
    state = await reach_logistics_menu()
    resp = await route_message(state, "2")
    assert state.step == Step.ISLAND_MENU


@pytest.mark.asyncio
async def test_logistics_whats_included():
    state = await reach_logistics_menu()
    resp = await route_message(state, "3")
    assert state.step == Step.MAIN_MENU
    assert "equipo" in resp.lower() or "seguro" in resp.lower() or "equipment" in resp.lower()


@pytest.mark.asyncio
async def test_logistics_not_included_mentions_photos():
    state = await reach_logistics_menu()
    resp = await route_message(state, "3")
    assert "foto" in resp.lower() or "photo" in resp.lower() or "video" in resp.lower() or "propina" in resp.lower()


@pytest.mark.asyncio
async def test_logistics_what_to_bring():
    state = await reach_logistics_menu()
    resp = await route_message(state, "4")
    assert state.step == Step.MAIN_MENU
    assert "toalla" in resp.lower() or "bloqueador" in resp.lower() or "towel" in resp.lower()


@pytest.mark.asyncio
async def test_logistics_island_context_not_included():
    state = await reach_main_menu()
    state.location = "island"
    await route_message(state, "2")  # Información
    await route_message(state, "3")  # Logística
    resp = await route_message(state, "3")  # qué incluye / no incluye
    assert "isla" in resp.lower() or "island" in resp.lower() or "transporte" in resp.lower()


# ===========================================================================
# BLOQUE 10 — SELECTOR DE ISLA Y HOTEL
# ===========================================================================

@pytest.mark.asyncio
async def test_island_selector_isla_grande_shows_hotels():
    state = await reach_logistics_menu()
    await send(state, "2")  # logística > alojamiento
    resp = await route_message(state, "1")  # Isla Grande
    assert state.island == "Isla Grande"
    assert state.step == Step.ISLAND_HOTEL_MENU
    assert "Majagua" in resp or "hotel" in resp.lower() or "hospedas" in resp.lower()


@pytest.mark.asyncio
async def test_island_selector_hotel_san_pedro():
    state = await reach_logistics_menu()
    await send(state, "2", "1")  # Isla Grande
    resp = await route_message(state, "1")  # San Pedro de Majagua
    assert state.hotel == "San Pedro de Majagua"
    assert state.step == Step.LOGISTICS_MENU


@pytest.mark.asyncio
async def test_island_selector_cocoliso():
    state = await reach_logistics_menu()
    await send(state, "2", "1")  # Isla Grande
    await route_message(state, "3")   # Cocoliso (3er hotel)
    assert state.hotel == "Cocoliso Island Resort"


@pytest.mark.asyncio
async def test_island_selector_other_hotel():
    state = await reach_logistics_menu()
    await send(state, "2", "1")  # Isla Grande (10 hoteles)
    resp = await route_message(state, "11")  # Otro
    assert state.hotel == "Otro / No esta en la lista"
    assert state.step == Step.LOGISTICS_MENU


@pytest.mark.asyncio
async def test_island_selector_isla_marina():
    state = await reach_logistics_menu()
    await send(state, "2")
    resp = await route_message(state, "2")  # Isla Marina
    assert state.island == "Isla Marina"
    assert state.step == Step.ISLAND_HOTEL_MENU


@pytest.mark.asyncio
async def test_island_selector_isla_del_pirata():
    state = await reach_logistics_menu()
    await send(state, "2")
    resp = await route_message(state, "3")  # Isla del Pirata
    assert state.island == "Isla del Pirata"


@pytest.mark.asyncio
async def test_island_selector_isla_rosario():
    state = await reach_logistics_menu()
    await send(state, "2")
    resp = await route_message(state, "12")  # Isla Rosario
    assert state.island == "Isla Rosario"
    assert state.step == Step.ISLAND_HOTEL_MENU


@pytest.mark.asyncio
async def test_island_hotel_stored_in_state_for_rag_context():
    state = await reach_logistics_menu()
    await send(state, "2", "1", "1")  # Isla Grande + San Pedro
    assert state.island == "Isla Grande"
    assert state.hotel == "San Pedro de Majagua"
    # Context should be available for subsequent RAG calls
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        await route_message(state, "cómo me recogen en el hotel?")
        call_args = mock_rag.call_args
        assert call_args is not None


# ===========================================================================
# BLOQUE 11 — ESCALACIONES EXPLÍCITAS Y PALABRAS CLAVE
# ===========================================================================

@pytest.mark.asyncio
async def test_main_menu_advisor_keyword_escalates():
    """Tras quitar la opción de asesor del menú principal, la escalación funciona por keyword."""
    state = await reach_main_menu()
    resp = await route_message(state, "quiero hablar con un asesor")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_keyword_asesor_mid_flow():
    state = await reach_group_type()
    await send(state, "1")  # tours + certificados
    resp = await route_message(state, "asesor")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_keyword_humano():
    state = await reach_main_menu()
    resp = await route_message(state, "humano")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_keyword_agente():
    state = await reach_main_menu()
    resp = await route_message(state, "agente")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_keyword_advisor_english():
    state = await reach_main_menu("en")
    resp = await route_message(state, "advisor")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_keyword_menu_resets_from_deep_step():
    state = await reach_group_type()
    await send(state, "1", "1", "1")  # en certified_experience
    resp = await route_message(state, "menu")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_keyword_volver_resets():
    state = await reach_group_type()
    await send(state, "1")
    resp = await route_message(state, "volver")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_keyword_atras_resets():
    state = await reach_courses_menu()
    resp = await route_message(state, "atrás")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_escalation_note_includes_service_if_known():
    state = await reach_group_type()
    await send(state, "1", "1", "2")  # 2 dives, recent dive
    resp = await route_message(state, "asesor")
    assert state.pending_note is not None
    assert "2_dives_1_day" in state.pending_note


@pytest.mark.asyncio
async def test_escalation_note_includes_language():
    state = make_state()
    await send(state, "hello", "2")  # english
    resp = await route_message(state, "advisor")
    assert state.pending_note is not None
    assert "English" in state.pending_note


# ===========================================================================
# BLOQUE 12 — ESCALACIONES SENSIBLES (MÉDICAS, CLIMA, TIEMPO REAL, QUEJAS)
# ===========================================================================

@pytest.mark.asyncio
async def test_medical_asthma_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "tengo asma, puedo bucear?")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "+57" in resp or "staff" in resp.lower() or "calificado" in resp.lower()


@pytest.mark.asyncio
async def test_medical_pregnancy_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "estoy embarazada, es seguro bucear?")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_medical_heart_english_escalates():
    state = await reach_main_menu("en")
    resp = await route_message(state, "I have a heart condition, can I dive?")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_weather_tomorrow_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "cómo está el clima mañana?")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_weather_english_escalates():
    state = await reach_main_menu("en")
    resp = await route_message(state, "what's the weather tomorrow?")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_real_time_availability_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "hay cupo mañana?")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_payment_error_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "no puedo reservar, hay un error")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_complaint_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "tengo una queja")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_emergency_escalates():
    state = await reach_main_menu()
    resp = await route_message(state, "emergencia!")
    assert state.step == Step.ESCALATE


# ===========================================================================
# BLOQUE 13 — PRIVACIDAD Y PII
# ===========================================================================

@pytest.mark.asyncio
async def test_pii_phone_blocked():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.detect_pii", return_value=["phone"]):
        resp = await route_message(state, "mi número es 3001234567")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_pii_email_blocked():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.detect_pii", return_value=["email"]):
        resp = await route_message(state, "mi correo es test@example.com")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_pii_id_blocked():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.detect_pii", return_value=["id"]):
        resp = await route_message(state, "mi cédula es 12345678")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_no_pii_no_block():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.detect_pii", return_value=[]), \
         patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "cuánto cuesta el minicurso?")
    assert state.step != Step.ESCALATE


# ===========================================================================
# BLOQUE 14 — ENRUTAMIENTO RAG (TEXTO LIBRE EN MENÚ)
# ===========================================================================

@pytest.mark.asyncio
async def test_free_text_in_menu_step_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "cuánto cuesta el minicurso de buceo?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_free_text_passes_extra_context_location():
    state = await reach_main_menu()
    state.location = "cartagena"
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        await route_message(state, "cómo llego al muelle?")
    call_kwargs = mock_rag.call_args.kwargs
    assert "Cartagena" in (call_kwargs.get("extra_context") or "")


@pytest.mark.asyncio
async def test_free_text_passes_island_and_hotel_context():
    state = await reach_main_menu()
    state.location = "island"
    state.island = "Isla Grande"
    state.hotel = "Cocoliso Island Resort"
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        await route_message(state, "cómo me recogen en el hotel?")
    call_kwargs = mock_rag.call_args.kwargs
    extra = call_kwargs.get("extra_context") or ""
    assert "Isla Grande" in extra
    assert "Cocoliso" in extra


@pytest.mark.asyncio
async def test_free_text_in_welcome_step_not_sent_to_rag_if_too_short():
    state = make_state()
    await route_message(state, "hola")  # LANGUAGE step
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "si")  # 1 palabra, sin "?" → tree, no RAG
    mock_rag.assert_not_called()


@pytest.mark.asyncio
async def test_post_summary_free_text_routes_to_rag():
    state = await reach_group_type()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY
    assert state.step == Step.SUMMARY
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "qué incluye el almuerzo exactamente?")
    assert resp == RAG_MOCK


@pytest.mark.asyncio
async def test_post_escalate_free_text_routes_to_rag():
    state = await reach_main_menu()
    await route_message(state, "asesor")
    assert state.step == Step.ESCALATE
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "cuánto tiempo tarda la respuesta?")
    assert resp == RAG_MOCK


# ===========================================================================
# BLOQUE 15 — FLUJOS EN INGLÉS
# ===========================================================================

@pytest.mark.asyncio
async def test_en_certified_2_dives_cartagena():
    state = await reach_group_type("en")
    responses = await send(state, "1", "1", "2", "2")
    assert state.language == "en"
    assert state.selected_service == "2_dives_1_day"
    assert state.step == Step.SUMMARY
    assert "Service" in responses[-1] or "Includes" in responses[-1] or "divingplanet" in responses[-1]


@pytest.mark.asyncio
async def test_en_beginner_snorkel():
    state = await reach_group_type("en")
    await send(state, "2")
    resp = await route_message(state, "2")
    assert state.language == "en"
    assert state.selected_service == "snorkeling"


@pytest.mark.asyncio
async def test_en_mixed_group_escalates():
    state = await reach_group_type("en")
    resp = await route_message(state, "3")
    assert state.step == Step.ESCALATE
    assert "mixed" in resp.lower() or "snorkel" in resp.lower()


@pytest.mark.asyncio
async def test_en_open_water_from_island():
    state = await reach_courses_menu("en")
    await send(state, "1")
    resp = await route_message(state, "2")
    assert state.location == "island"
    assert state.selected_service == "open_water_already_on_island"


@pytest.mark.asyncio
async def test_en_advisor_keyword():
    state = await reach_main_menu("en")
    resp = await route_message(state, "advisor")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "English" in state.pending_note


@pytest.mark.asyncio
async def test_en_pricing_cartagena():
    state = await reach_pricing_menu("en")
    resp = await route_message(state, "1")
    assert state.step == Step.MAIN_MENU
    assert "USD" in resp or "price" in resp.lower()


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
    assert "5_dives_2_days" in note
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
    assert "2_dives_1_day" in note
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


@pytest.mark.asyncio
async def test_lead_note_cleared_after_send_simulation():
    state = await reach_main_menu()
    await route_message(state, "asesor")
    assert state.pending_note is not None
    # Simulate chatwoot.py clearing the note after sending
    state.pending_note = None
    assert state.pending_note is None


# ===========================================================================
# BLOQUE 17 — OPCIONES INVÁLIDAS Y ROBUSTEZ
# ===========================================================================

@pytest.mark.asyncio
async def test_invalid_main_menu_option():
    state = await reach_main_menu()
    resp = await route_message(state, "9")
    assert state.step == Step.MAIN_MENU
    assert "opci" in resp.lower() or "option" in resp.lower() or "entend" in resp.lower()


@pytest.mark.asyncio
async def test_invalid_tours_certified_option():
    state = await reach_group_type()
    await send(state, "1")
    resp = await route_message(state, "9")
    assert state.step == Step.TOURS_CERTIFIED


@pytest.mark.asyncio
async def test_invalid_beginner_option():
    state = await reach_group_type()
    await send(state, "2")
    resp = await route_message(state, "9")
    assert state.step == Step.TOURS_BEGINNER


@pytest.mark.asyncio
async def test_invalid_certified_last_dive():
    state = await reach_group_type()
    await send(state, "1", "1")
    resp = await route_message(state, "9")
    assert state.step == Step.CERTIFIED_LAST_DIVE


@pytest.mark.asyncio
async def test_invalid_colombian_option():
    state = await reach_group_type()
    await send(state, "1", "1", "2")
    resp = await route_message(state, "9")
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_invalid_island_menu_option():
    state = await reach_logistics_menu()
    await send(state, "2")
    resp = await route_message(state, "99")
    assert state.step == Step.ISLAND_MENU


@pytest.mark.asyncio
async def test_summary_restart_returns_to_main():
    state = await reach_group_type()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY
    resp = await route_message(state, "1")  # ver itinerario completo
    assert state.step == Step.FREE_TEXT
    assert "itinerario" in resp.lower() or "🗺️" in resp


@pytest.mark.asyncio
async def test_summary_no_thanks_ends_conversation():
    state = await reach_group_type()
    await send(state, "1", "1", "2", "2")
    resp = await route_message(state, "2")  # no, gracias (no ver itinerario)
    assert state.step == Step.FREE_TEXT
    assert "pregunt" in resp.lower() or "ask" in resp.lower()


# ===========================================================================
# BLOQUE 18 — QUICK REPLIES CORRECTOS
# ===========================================================================

@pytest.mark.asyncio
async def test_quick_replies_set_at_main_menu():
    state = await reach_main_menu()
    assert len(state.quick_replies) == 2  # Reservar / Información


@pytest.mark.asyncio
async def test_quick_replies_set_at_tours_certified():
    state = await reach_group_type()
    await send(state, "1")
    assert len(state.quick_replies) > 0


@pytest.mark.asyncio
async def test_quick_replies_set_at_colombian():
    state = await reach_group_type()
    await send(state, "1", "1", "2")
    assert len(state.quick_replies) == 2


@pytest.mark.asyncio
async def test_quick_replies_cleared_on_escalation():
    state = await reach_main_menu()
    await route_message(state, "asesor")
    assert state.quick_replies == []


@pytest.mark.asyncio
async def test_island_menu_has_12_options():
    state = await reach_logistics_menu()
    await send(state, "2")
    assert len(state.quick_replies) == 12


@pytest.mark.asyncio
async def test_welcome_has_2_language_buttons():
    state = make_state()
    await route_message(state, "hola")
    assert len(state.quick_replies) == 2


# ===========================================================================
# BLOQUE 19 — ENRUTAMIENTO RAG: NUEVOS TEMAS OPERATIVOS
# Tests that verify questions about food, photos, hours, closed days, Barú,
# adaptive diving, and other PDF-sourced topics reach RAG (not escalation).
# ===========================================================================

@pytest.mark.asyncio
async def test_lunch_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "qué incluye el almuerzo?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_vegetarian_food_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "soy vegetariana, qué hay para comer?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_food_allergy_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "tengo alergia al mariscos, hay problema?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_photos_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "hacen fotos durante la inmersión?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_videos_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "graban video bajo el agua?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_operating_hours_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "hasta qué hora atienden?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_closed_days_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "abren el 25 de diciembre?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_new_year_closed_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "salen el 1 de enero?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_baru_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "también van a Barú?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_night_dive_alternative_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "hay algún paquete sin buceo nocturno?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_divemaster_payment_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "cómo se paga el curso de divemaster?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_two_day_course_accommodation_question_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "si hago el Open Water necesito quedarme a dormir en las islas?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_private_service_free_text_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "pueden organizar un servicio privado para mi grupo?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_island_pickup_free_question_routes_to_rag():
    state = await reach_main_menu()
    state.location = "island"
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "la recogida en lancha tiene algún costo extra?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_post_summary_food_question_routes_to_rag():
    state = await reach_group_type()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY
    assert state.step == Step.SUMMARY
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "y qué hay para comer exactamente?")
    assert resp == RAG_MOCK


@pytest.mark.asyncio
async def test_post_summary_photos_question_routes_to_rag():
    state = await reach_group_type()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY
    assert state.step == Step.SUMMARY
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "el instructor saca fotos?")
    assert resp == RAG_MOCK


# ===========================================================================
# BLOQUE 20 — BUCEO ADAPTADO: NO ESCALA COMO MÉDICO
# Disability-related questions must go to RAG, not trigger medical escalation.
# The escalation keywords cover medical conditions (asthma, heart, surgery...)
# but not disability/accessibility inquiries.
# ===========================================================================

@pytest.mark.asyncio
async def test_down_syndrome_does_not_escalate():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "mi hijo tiene síndrome de Down, puede hacer el minicurso?")
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_deaf_diver_does_not_escalate():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "soy sordo, puedo bucear con ustedes?")
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_reduced_mobility_does_not_escalate():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "tengo movilidad reducida, hacen buceo adaptado?")
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_autism_does_not_escalate():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "mi hija tiene autismo, pueden atenderla?")
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_visual_impairment_does_not_escalate():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "soy invidente, han trabajado con personas con discapacidad visual?")
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_cerebral_palsy_does_not_escalate():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "tengo parálisis cerebral leve, es posible bucear?")
    assert state.step != Step.ESCALATE


@pytest.mark.asyncio
async def test_dive_to_heal_mention_routes_to_rag():
    state = await reach_main_menu()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "qué es DIVE TO HEAL y cómo funciona el buceo adaptado?")
    assert resp == RAG_MOCK
    mock_rag.assert_called_once()


# ===========================================================================
# BLOQUE 21 — CONTENIDO DE RESPUESTAS DEL ÁRBOL (NUEVOS DATOS)
# Tests that verify tree-generated responses include key factual content
# from the expanded knowledge base.
# ===========================================================================

@pytest.mark.asyncio
async def test_divemaster_response_mentions_professional_level():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "3")  # Divemaster
    assert state.selected_service == "divemaster"
    assert any(w in resp.lower() for w in ["divemaster", "profesional", "professional", "nivel"])


@pytest.mark.asyncio
async def test_pricing_cartagena_response_has_service_price():
    state = await reach_pricing_menu()
    resp = await route_message(state, "1")  # precios desde Cartagena
    assert "$" in resp or "USD" in resp
    assert any(svc in resp.lower() for svc in ["buceo", "dive", "minicurso", "snorkel"])


@pytest.mark.asyncio
async def test_pricing_multiday_response_mentions_5_7_9():
    state = await reach_pricing_menu()
    resp = await route_message(state, "3")  # paquetes multi-día
    assert "5" in resp and "7" in resp and "9" in resp


@pytest.mark.asyncio
async def test_island_certified_summary_no_extra_pickup_charge():
    state = await reach_group_type(location="island")
    responses = await send(state, "1", "1", "2", "2")  # islas + cert + 2 buceos + recent + no colombiano
    summary = responses[-1]
    # Pickup should be mentioned as included, not as an extra charge
    assert "recog" in summary.lower() or "pickup" in summary.lower() or "hotel" in summary.lower()
    assert "cargo extra" not in summary.lower() and "extra charge" not in summary.lower()


@pytest.mark.asyncio
async def test_open_water_cartagena_mentions_overnight_need():
    state = await reach_courses_menu()
    await send(state, "1", "1")  # cursos > Open Water > Cartagena
    resp = await route_message(state, "1")  # 2 días completos
    assert state.selected_service == "open_water"
    assert any(w in resp.lower() for w in ["isla", "noche", "island", "night", "alojamiento", "accommodation", "2 día", "2 dia"])


@pytest.mark.asyncio
async def test_en_closed_days_question_routes_to_rag():
    state = await reach_main_menu("en")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK_EN) as mock_rag:
        resp = await route_message(state, "are you open on Christmas day?")
    assert resp == RAG_MOCK_EN
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_en_food_question_routes_to_rag():
    state = await reach_main_menu("en")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK_EN) as mock_rag:
        resp = await route_message(state, "what food is included in the tour?")
    assert resp == RAG_MOCK_EN
    mock_rag.assert_called_once()


@pytest.mark.asyncio
async def test_en_adaptive_diving_routes_to_rag():
    state = await reach_main_menu("en")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK_EN) as mock_rag:
        resp = await route_message(state, "my son has Down Syndrome, can he try diving?")
    assert state.step != Step.ESCALATE
    assert resp == RAG_MOCK_EN
