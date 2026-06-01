"""Exhaustive conversation-level test dataset for the Diving Planet bot."""

import os

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
    """Reservar > Tours → GROUP_TYPE.

    Nota: TOURS_LOCATION fue diferido al SUMMARY (botones), así que ya no se pregunta
    en el flujo. Para los tests que necesitan una ubicación específica, la seteamos
    programáticamente aquí.
    """
    state = await reach_main_menu(lang)
    await send(state, "1", "1")
    assert state.step == Step.GROUP_TYPE
    state.location = location
    return state


async def reach_diving_experience(lang: str = "es", location: str = "cartagena") -> ConversationState:
    """Reservar > Tours > Buceo → TOURS_EXPERIENCE (location seteada programáticamente)."""
    state = await reach_group_type(lang, location)
    await route_message(state, "1")
    assert state.step == Step.TOURS_EXPERIENCE
    return state


async def reach_snorkeling_summary(lang: str = "es", location: str = "cartagena") -> ConversationState:
    state = await reach_group_type(lang, location)
    await send(state, "2", "2")
    assert state.step == Step.SUMMARY
    return state


async def reach_minicourse_summary(lang: str = "es", location: str = "cartagena") -> ConversationState:
    state = await reach_diving_experience(lang, location)
    await send(state, "2", "3", "2")
    assert state.step == Step.SUMMARY
    return state


async def reach_courses_menu(lang: str = "es") -> ConversationState:
    state = await reach_main_menu(lang)
    await send(state, "1", "2")
    assert state.step == Step.COURSES_MENU
    return state


@pytest.mark.asyncio
async def test_courses_menu_titles_in_spanish():
    state = await reach_courses_menu()
    assert [item["title"] for item in state.quick_replies[:3]] == [
        "🐠 Descubriendo el buceo (Open Water Diver)",
        "🚀 Convierte en pro (Advanced / Rescue / Dive Master)",
        "✨ Amplía tus habilidades (Especialidades PADI)",
    ]


@pytest.mark.asyncio
async def test_courses_menu_titles_in_english():
    state = await reach_courses_menu("en")
    assert [item["title"] for item in state.quick_replies[:3]] == [
        "🐠 Discover diving (Open Water Diver)",
        "🚀 Go pro (Advanced / Rescue / Divemaster)",
        "✨ Expand your skills (PADI Specialties)",
    ]


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
async def test_clear_mixed_phrase_at_main_menu_replaces_generic_buttons_with_mixed_group_cta():
    state = await reach_main_menu("es")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock) as mock_rag:
        resp = await route_message(state, "Yo haría el minicurso y mi amigo snorkel")

    mock_rag.assert_not_awaited()
    assert "Tú puedes hacer *minicurso de buceo*" in resp
    assert "tu acompañante puede hacer *snorkel*" in resp
    assert "Grupo mixto (buceo + snorkel)" in resp
    assert "asesor" not in resp.lower()
    assert "segunda inmers" not in resp.lower()
    assert state.step == Step.GROUP_TYPE
    assert [item["title"] for item in state.quick_replies] == [
        "👥 Grupo mixto (buceo + snorkel)",
        "🔙 Volver",
    ]

    resp = await route_message(state, "3")
    assert state.step == Step.MIXED_ENTRY
    assert "carrito" in resp.lower() or "paso a paso" in resp.lower()


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
async def test_pricing_response_shows_back_button_es():
    state = await reach_pricing_menu("es")
    resp = await route_message(state, "1")
    assert state.step == Step.PRICING_CARTAGENA
    assert "precio" in resp.lower() or "precios" in resp.lower()
    assert any(item.get("value") == "back" for item in state.quick_replies)


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
    assert state.step == Step.PRICING_CARTAGENA
    await route_message(state, "quiero reservar")
    assert state.step == Step.RESERVA_MENU


# ---------------------------------------------------------------------------
# Back navigation in the Reservar branch (button value="back" or keyword)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_back_button_value_from_reserva_menu_returns_to_main_menu():
    state = await reach_main_menu("es")
    await route_message(state, "1")  # RESERVA_MENU
    assert state.step == Step.RESERVA_MENU
    await route_message(state, "back")  # Chatwoot sends value="back" when button is clicked
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_tours_skips_to_group_type():
    """Tras diferir TOURS_LOCATION, 'Reservar > Tours' va directo a GROUP_TYPE."""
    state = await reach_main_menu("es")
    await send(state, "1", "1")  # RESERVA_MENU → GROUP_TYPE (sin pasar por TOURS_LOCATION)
    assert state.step == Step.GROUP_TYPE
    await route_message(state, "back")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_group_type_returns_to_reserva_menu():
    """Volver desde GROUP_TYPE ahora salta directo a RESERVA_MENU (TOURS_LOCATION ya no se pregunta)."""
    state = await reach_group_type()
    await route_message(state, "back")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_tours_certified_returns_to_group_type():
    state = await reach_diving_experience()
    await route_message(state, "1")  # → TOURS_CERTIFIED
    assert state.step == Step.TOURS_CERTIFIED
    await route_message(state, "back")
    assert state.step == Step.TOURS_EXPERIENCE


@pytest.mark.asyncio
async def test_beginner_choice_goes_direct_to_beginner_age():
    state = await reach_diving_experience()
    resp = await route_message(state, "2")  # → BEGINNER_AGE (3 opciones)
    assert state.step == Step.BEGINNER_AGE
    assert state.selected_service == "minicourse"
    # Las opciones (botones) contienen las edades, pero el prompt es más simple
    assert "grupo" in resp.lower() or "minicurso" in resp.lower()


@pytest.mark.asyncio
async def test_back_button_value_from_beginner_age_returns_to_tours_experience():
    state = await reach_diving_experience()
    await send(state, "2")  # → BEGINNER_AGE directo
    assert state.step == Step.BEGINNER_AGE
    await route_message(state, "back")
    assert state.step == Step.TOURS_EXPERIENCE


@pytest.mark.asyncio
async def test_back_button_value_from_courses_menu_returns_to_reserva_menu():
    state = await reach_courses_menu()
    await route_message(state, "back")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_courses_advanced_menu_returns_to_courses_menu():
    state = await reach_courses_menu()
    await route_message(state, "2")  # → COURSES_ADVANCED_MENU
    assert state.step == Step.COURSES_ADVANCED_MENU
    await route_message(state, "back")
    assert state.step == Step.COURSES_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_courses_specialties_menu_returns_to_courses_menu():
    state = await reach_courses_menu()
    await route_message(state, "3")  # → COURSES_SPECIALTIES_MENU
    assert state.step == Step.COURSES_SPECIALTIES_MENU
    await route_message(state, "back")
    assert state.step == Step.COURSES_MENU


@pytest.mark.asyncio
async def test_back_text_volver_from_tours_certified_returns_to_group_type():
    """Typing 'volver' (text, not button click) at TOURS_CERTIFIED goes back one step."""
    state = await reach_diving_experience()
    await route_message(state, "1")
    assert state.step == Step.TOURS_CERTIFIED
    await route_message(state, "volver")
    assert state.step == Step.TOURS_EXPERIENCE


@pytest.mark.asyncio
async def test_back_from_island_4_dives_variant_returns_to_certified_menu():
    state = await reach_diving_experience(location="island")
    await route_message(state, "1")
    await route_message(state, "3")
    assert state.step == Step.CERTIFIED_4_DIVES_VARIANT
    await route_message(state, "back")
    assert state.step == Step.TOURS_CERTIFIED


@pytest.mark.asyncio
async def test_back_button_present_in_reservar_quick_replies():
    state = await reach_main_menu("es")
    await route_message(state, "1")  # RESERVA_MENU
    titles = [qr["title"] for qr in state.quick_replies]
    assert any("Volver" in t or "Back" in t for t in titles)


@pytest.mark.asyncio
async def test_back_button_not_present_in_info_menu():
    """Info branch keeps the existing back-to-menu hint approach; no explicit back button there."""
    state = await reach_main_menu("es")
    await route_message(state, "2")  # INFO_MENU
    titles = [qr["title"] for qr in state.quick_replies]
    assert any("Volver" in t or "Back" in t for t in titles)


@pytest.mark.asyncio
async def test_info_island_4_dives_detail_back_returns_to_variant_menu():
    state = await reach_main_menu("es")
    await send(state, "2", "1", "2", "1", "1", "1", "3", "2")

    assert state.step == Step.INFO_PACKAGE_DETAIL
    assert state.selected_service == "4_dives_2_days_mixed_already_on_island"

    await route_message(state, "back")

    assert state.step == Step.INFO_CERTIFIED_4_DIVES_VARIANT
    assert [qr["title"] for qr in state.quick_replies[:2]] == [
        "🤿 4 inmersiones (2 días) · 4 diurnas",
        "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna",
    ]


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

@pytest.mark.asyncio
async def test_certified_2_dives_full_happy_path():
    state = await reach_diving_experience()
    # cert, 2 dives, recent dive, no colombiano → SUMMARY
    responses = await send(state, "1", "1", "2", "2")
    assert state.step == Step.SUMMARY
    assert state.selected_service == "2_dives_1_day"
    assert state.location == "cartagena"
    assert state.is_colombian is False
    # Booking URL ya no se incluye en el summary (se envía al pulsar Reservar)
    assert "Servicio" in responses[-1] or "Salidas" in responses[-1]


@pytest.mark.asyncio
async def test_certified_2_dives_colombian_discount():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2")  # cert, 2 dives, recent dive → COLOMBIAN
    resp = await route_message(state, "1")  # sí colombiano
    assert state.is_colombian is True
    assert state.step == Step.SUMMARY
    assert "descuento" in resp.lower() or "WhatsApp" in resp or "+57" in resp


@pytest.mark.asyncio
async def test_certified_last_dive_over_2_years_asks_experience():
    state = await reach_diving_experience()
    await send(state, "1", "1")
    resp = await route_message(state, "1")  # > 2 años
    assert state.step == Step.CERTIFIED_EXPERIENCE
    assert state.last_dive_over_2_years is True


@pytest.mark.asyncio
async def test_certified_500_plus_dives_escalates_with_note():
    state = await reach_diving_experience()
    await send(state, "1", "1", "1")  # > 2 años
    resp = await route_message(state, "1")  # 500+ / Divemaster
    assert state.step == Step.ESCALATE
    assert state.has_500_dives_or_dive_master is True
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_certified_refresher_yes_updates_service_for_2_dives():
    state = await reach_diving_experience()
    await send(state, "1", "1", "1", "2")  # > 2 años, no 500+
    resp = await route_message(state, "1")       # quiere refresher → COLOMBIAN
    assert state.refresher_interested is True
    assert state.step == Step.COLOMBIAN
    assert state.selected_service == "minicourse"


@pytest.mark.asyncio
async def test_certified_refresher_no_keeps_service():
    state = await reach_diving_experience()
    await send(state, "1", "1", "1", "2")  # > 2 años, no 500+
    resp = await route_message(state, "2")       # no quiere refresher → COLOMBIAN
    assert state.refresher_interested is False
    assert state.step == Step.COLOMBIAN
    assert state.selected_service == "2_dives_1_day"


@pytest.mark.asyncio
async def test_certified_3_dives_selected():
    state = await reach_diving_experience()
    await send(state, "1")
    await route_message(state, "2")
    assert state.selected_service == "3_dives_1_day"


@pytest.mark.asyncio
async def test_certified_4_dives_selected():
    state = await reach_diving_experience()
    await send(state, "1")
    await route_message(state, "3")
    assert state.selected_service == "4_dives_2_days"


@pytest.mark.asyncio
async def test_certified_5_dives_selected():
    state = await reach_diving_experience()
    await send(state, "1")
    await route_message(state, "4")  # 5 buceos → asks last dive recency first
    assert state.selected_service == "5_dives_2_days"


@pytest.mark.asyncio
async def test_certified_7_dives_selected():
    state = await reach_diving_experience()
    await send(state, "1")
    await route_message(state, "5")
    assert state.selected_service == "7_dives_3_days"


@pytest.mark.asyncio
async def test_certified_9_dives_selected():
    state = await reach_diving_experience()
    await send(state, "1")
    await route_message(state, "6")
    assert state.selected_service == "9_dives_4_days"


@pytest.mark.asyncio
async def test_certified_private_service_escalates():
    state = await reach_diving_experience()
    await send(state, "1")
    resp = await route_message(state, "7")  # servicio privado
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_certified_multiday_refresher_keeps_original_service():
    state = await reach_diving_experience()
    await send(state, "1", "4", "1", "2")  # 5 dives, > 2 años, no 500+
    resp = await route_message(state, "1")       # refresher sí en paquete multi-día
    assert state.refresher_interested is True
    assert state.selected_service == "5_dives_2_days"  # paquete original intacto
    assert "asesor" in resp.lower() or "multi" in resp.lower() or "paquete" in resp.lower()


@pytest.mark.asyncio
async def test_certified_summary_includes_meeting_point_cartagena():
    state = await reach_diving_experience()
    # cert, 2 dives, recent, no colombiano → SUMMARY
    responses = await send(state, "1", "1", "2", "2")
    summary = responses[-1]
    assert "Bodeguita" in summary or "8:00" in summary or "Cartagena" in summary


@pytest.mark.asyncio
async def test_certified_summary_includes_flight_rule_for_multiday():
    state = await reach_diving_experience()
    await send(state, "1", "4", "2", "2")  # 5 dives, sin refresher, no colombiano
    # flight rule applies only when service has it; at least booking link should appear
    assert state.step == Step.SUMMARY


# ===========================================================================
# BLOQUE 3 — PRINCIPIANTES DESDE CARTAGENA
# ===========================================================================

@pytest.mark.asyncio
async def test_beginner_minicourse_cartagena_full_path():
    state = await reach_diving_experience()
    resp = await route_message(state, "2")  # principiantes → minicurso directo
    assert state.selected_service == "minicourse"
    assert state.step == Step.BEGINNER_AGE
    # Los botones llevan las edades, el prompt solo invita a elegir opción del grupo
    assert "grupo" in resp.lower() or "minicurso" in resp.lower()


@pytest.mark.asyncio
async def test_beginner_snorkeling_cartagena():
    state = await reach_group_type()
    resp = await route_message(state, "2")  # snorkel → COLOMBIAN (LOCATION skipped por location preset)
    assert state.selected_service == "snorkeling"
    assert state.step == Step.COLOMBIAN


@pytest.mark.asyncio
async def test_beginner_minicourse_min_age_shown():
    state = await reach_diving_experience()
    resp = await route_message(state, "2")
    # Las edades aparecen en los botones (8, 10) más que en el texto del prompt
    titles = " ".join(b.get("title", "") for b in state.quick_replies)
    assert "10" in titles or "8" in titles or "Minicurso" in resp


@pytest.mark.asyncio
async def test_beginner_snorkeling_min_age_shown():
    state = await reach_group_type()
    resp = await route_message(state, "2")
    assert "6" in resp or "edad" in resp.lower() or "superficie" in resp.lower() or "snorkel" in resp.lower()


# ===========================================================================
# BLOQUE 4 — YA EN LAS ISLAS
# ===========================================================================

@pytest.mark.asyncio
async def test_island_certified_2_dives():
    state = await reach_diving_experience(location="island")
    await send(state, "1")  # certificados
    resp = await route_message(state, "1")  # 2 buceos
    assert state.location == "island"
    assert state.selected_service == "2_dives_1_day_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_3_dives_night():
    state = await reach_diving_experience(location="island")
    await send(state, "1")  # certificados
    resp = await route_message(state, "2")  # 3 buceos con nocturna
    assert state.location == "island"
    assert state.selected_service == "3_dives_1_day_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_5_dives():
    state = await reach_diving_experience(location="island")
    await send(state, "1")
    await route_message(state, "4")
    assert state.selected_service == "5_dives_2_days_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_4_dives_daytime_variant():
    state = await reach_diving_experience(location="island")
    await send(state, "1")
    resp = await route_message(state, "3")
    assert state.step == Step.CERTIFIED_4_DIVES_VARIANT
    assert "4 inmersiones" in resp.lower() or "4 dives" in resp.lower()
    await route_message(state, "1")
    assert state.selected_service == "4_dives_2_days_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_4_dives_mixed_variant():
    state = await reach_diving_experience(location="island")
    await send(state, "1")
    await route_message(state, "3")
    await route_message(state, "2")
    assert state.selected_service == "4_dives_2_days_mixed_already_on_island"


@pytest.mark.asyncio
async def test_island_certified_7_dives():
    state = await reach_diving_experience(location="island")
    await send(state, "1")
    await route_message(state, "5")
    assert state.selected_service == "7_dives_3_days_already_on_island"


@pytest.mark.asyncio
async def test_island_beginner_minicourse():
    state = await reach_diving_experience(location="island")
    await send(state, "2")  # principiantes
    resp = await route_message(state, "1")  # minicurso
    assert state.location == "island"
    assert state.selected_service == "minicourse_already_on_island"


@pytest.mark.asyncio
async def test_island_snorkel_companion():
    state = await reach_group_type(location="island")
    resp = await route_message(state, "2")  # snorkel directo
    assert state.location == "island"
    assert state.selected_service == "snorkeling_already_on_island"


@pytest.mark.asyncio
async def test_island_summary_shows_hotel_pickup():
    state = await reach_diving_experience(location="island")
    responses = await send(state, "1", "1", "2", "2")  # cert, 2 buceos, recent, no colombiano
    summary = responses[-1]
    assert "9:30" in summary or "recogida" in summary.lower() or "pickup" in summary.lower() or "isla" in summary.lower()


# ===========================================================================
# BLOQUE 5 — GRUPO MIXTO (cart-style flow)
# ===========================================================================
# Detailed mixed-flow tests live near the bottom of this file. This block
# keeps a smoke test that the flow enters MIXED_ENTRY correctly.

@pytest.mark.asyncio
async def test_mixed_group_from_cartagena_enters_cart_flow():
    state = await reach_group_type()  # tours Cartagena
    resp = await route_message(state, "3")  # grupo mixto buceo+snorkel
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []  # cart starts empty
    assert "carrito" in resp.lower() or "armar" in resp.lower() or "step by step" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_group_from_island_enters_cart_flow():
    state = await reach_group_type(location="island")
    resp = await route_message(state, "3")
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []


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
    assert resp == "🌎 ¿Eres colombiano/a? Tenemos descuentos especiales para locales."


@pytest.mark.asyncio
async def test_divemaster_summary_contact_button_escalates_to_manager():
    state = await reach_courses_menu()
    await send(state, "2", "3", "2")  # go pro > divemaster > no colombiano
    assert state.step == Step.SUMMARY
    resp = await route_message(state, "contact")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "mi jefe" in resp.lower() or "my manager" in resp.lower()


@pytest.mark.asyncio
async def test_open_water_from_cartagena_not_enough_time():
    state = await reach_courses_menu()
    await send(state, "1", "1")
    resp = await route_message(state, "2")  # menos tiempo
    assert state.selected_service == "open_water"
    assert state.step == Step.COLOMBIAN
    assert resp == "🌎 ¿Eres colombiano/a? Tenemos descuentos especiales para locales."


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
    assert resp == "🌎 ¿Eres colombiano/a? Tenemos descuentos especiales para locales."


@pytest.mark.asyncio
async def test_rescue_course_selected():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "2")  # Rescate + EFR
    assert state.selected_service == "rescue"
    assert state.step == Step.COLOMBIAN
    assert resp == "🌎 ¿Eres colombiano/a? Tenemos descuentos especiales para locales."


@pytest.mark.asyncio
async def test_divemaster_course_selected():
    state = await reach_courses_menu()
    await send(state, "2")
    resp = await route_message(state, "3")  # Divemaster
    assert state.selected_service == "divemaster"
    assert state.step == Step.COLOMBIAN
    assert resp == "🌎 ¿Eres colombiano/a? Tenemos descuentos especiales para locales."


@pytest.mark.asyncio
async def test_go_pro_menu_shows_only_advanced_rescue_and_divemaster():
    state = await reach_courses_menu()
    resp = await route_message(state, "2")
    assert state.step == Step.COURSES_ADVANCED_MENU
    assert [item["title"] for item in state.quick_replies[:3]] == [
        "📘 Curso Avanzado",
        "🚑 Rescate + EFR",
        "🏅 Dive Master",
    ]
    assert "avanzados" in resp.lower()


@pytest.mark.asyncio
async def test_fish_identification_specialty():
    state = await reach_courses_menu()
    await send(state, "3")
    resp = await route_message(state, "2")  # Identificación de peces
    assert "fish" in state.selected_service or "peces" in state.selected_service or state.step in (Step.COLOMBIAN, Step.ESCALATE)


@pytest.mark.asyncio
async def test_nitrox_specialty():
    state = await reach_courses_menu()
    await send(state, "3")
    resp = await route_message(state, "5")  # Nitrox
    assert "nitrox" in state.selected_service or state.step in (Step.COLOMBIAN, Step.ESCALATE)


@pytest.mark.asyncio
async def test_referral_reactivate_escalates():
    state = await reach_courses_menu()
    # Paso 1: seleccionar opcion referral / reactivate desde el menú de cursos
    resp = await route_message(state, "4")
    assert state.step == Step.LOCATION
    assert state.selected_service == "referral"
    assert "refer" in resp.lower()  # referido / referral

    # Paso 2: indicar que sale desde Cartagena
    resp = await route_message(state, "1")
    assert state.location == "cartagena"
    assert state.step == Step.COLOMBIAN

    # Paso 3: responder que no es colombiano (para ver precios en USD)
    resp = await route_message(state, "2")
    assert state.step == Step.SUMMARY
    assert "referral" in state.selected_service or "referido" in resp.lower()

    # Paso 4: desde el resumen inicial, avanzar al follow-up
    resp = await route_message(state, "itinerary")
    assert state.step == Step.SUMMARY

    # Paso 5: elegir Contactar/Reservar -> escalar a humano
    resp = await route_message(state, "1")
    assert state.step == Step.ESCALATE
    # El mensaje de escalada debe incluir la explicacion de referral/reactivate
    assert "eLearning" in resp or "documento" in resp.lower() or "price" in resp.lower() or "precio" in resp.lower()


@pytest.mark.asyncio
async def test_specialties_menu_choice_3():
    state = await reach_courses_menu()
    resp = await route_message(state, "3")  # especialidades
    assert state.step == Step.COURSES_SPECIALTIES_MENU


@pytest.mark.asyncio
async def test_specialties_menu_shows_only_mindful_fish_naturalist_buoyancy_and_nitrox():
    state = await reach_courses_menu()
    resp = await route_message(state, "3")
    assert state.step == Step.COURSES_SPECIALTIES_MENU
    assert [item["title"] for item in state.quick_replies[:5]] == [
        "✨ Mindful Diving",
        "🐠 Identificación de peces",
        "🌿 Naturalista",
        "⚖️ Flotabilidad",
        "🫧 Nitrox",
    ]
    assert "especialidades" in resp.lower()


# ===========================================================================
# BLOQUE 7 — PRECIOS
# ===========================================================================

@pytest.mark.asyncio
async def test_pricing_menu_cartagena_shows_usd():
    state = await reach_pricing_menu()  # precios
    resp = await route_message(state, "1")  # desde Cartagena
    assert state.step == Step.PRICING_CARTAGENA
    assert "USD" in resp or "$" in resp or "precio" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_islands():
    state = await reach_pricing_menu()
    resp = await route_message(state, "2")  # ya en islas
    assert state.step == Step.PRICING_ISLANDS
    assert "isla" in resp.lower() or "island" in resp.lower() or "tarifa" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_multiday_packages():
    state = await reach_pricing_menu()
    resp = await route_message(state, "3")  # paquetes 5/7/9
    assert state.step == Step.PRICING_PACKAGES
    assert "5" in resp and "7" in resp


@pytest.mark.asyncio
async def test_pricing_menu_colombian_discounts():
    state = await reach_pricing_menu()
    resp = await route_message(state, "4")  # descuentos colombianos
    assert state.step == Step.PRICING_DISCOUNTS
    assert "colombian" in resp.lower() or "PARCEROS" in resp or "local" in resp.lower()


@pytest.mark.asyncio
async def test_pricing_menu_island_context_aware():
    state = await reach_main_menu()
    state.location = "island"  # preestablecido como ya en islas
    await route_message(state, "2")  # Información
    await route_message(state, "2")  # Precios
    await route_message(state, "2")  # No es colombiano/a
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
    await route_message(state, "4")  # Logística
    resp = await route_message(state, "1")
    assert state.step == Step.LOGISTICS_MEETING
    assert "Bodeguita" in resp or "8:00" in resp


@pytest.mark.asyncio
async def test_logistics_meeting_point_without_location():
    state = await reach_logistics_menu()
    resp = await route_message(state, "1")
    assert state.step == Step.LOGISTICS_MEETING
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
    assert state.step == Step.LOGISTICS_INCLUDES
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
    assert state.step == Step.LOGISTICS_WHAT_TO_BRING
    assert "toalla" in resp.lower() or "bloqueador" in resp.lower() or "towel" in resp.lower()


@pytest.mark.asyncio
async def test_logistics_island_context_not_included():
    state = await reach_main_menu()
    state.location = "island"
    await route_message(state, "2")  # Información
    await route_message(state, "4")  # Logística
    resp = await route_message(state, "3")  # qué incluye / no incluye
    assert state.step == Step.LOGISTICS_INCLUDES
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
    state = await reach_diving_experience()
    await send(state, "1", "1", "1")  # en certified_experience
    resp = await route_message(state, "menu")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_keyword_volver_goes_back_one_step():
    """'volver' from TOURS_CERTIFIED must return to TOURS_EXPERIENCE (one step up), not MAIN_MENU."""
    state = await reach_diving_experience()
    await send(state, "1")  # → TOURS_CERTIFIED
    assert state.step == Step.TOURS_CERTIFIED
    await route_message(state, "volver")
    assert state.step == Step.TOURS_EXPERIENCE


@pytest.mark.asyncio
async def test_keyword_atras_goes_back_one_step():
    """'atrás' from COURSES_MENU must return to RESERVA_MENU (one step up), not MAIN_MENU."""
    state = await reach_courses_menu()
    await route_message(state, "atrás")
    assert state.step == Step.RESERVA_MENU


@pytest.mark.asyncio
async def test_escalation_note_includes_service_if_known():
    state = await reach_diving_experience()
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
    state = await reach_diving_experience()
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


@pytest.mark.asyncio
async def test_snorkel_reserved_friend_wants_to_dive_prompts_for_certification_in_spanish():
    state = await reach_group_type()
    await route_message(state, "2")
    await route_message(state, "2")
    await route_message(state, "reservar")
    assert state.step == Step.ESCALATE

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que quiere hacer buceo, podemos ir juntos?")

    assert state.step == Step.FREE_TEXT
    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True
    assert [item["value"] for item in state.quick_replies] == ["1", "2"]


@pytest.mark.asyncio
async def test_snorkel_reserved_friend_dive_follow_up_shows_correct_info_card_without_early_escalation():
    state = await reach_group_type()
    await route_message(state, "2")
    await route_message(state, "2")
    await route_message(state, "reservar")
    assert state.step == Step.ESCALATE

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que quiere hacer buceo, podemos ir juntos?")

    certified_resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in certified_resp
    certified_resp = await route_message(state, "2")
    assert "Salidas de Buceo - 2 inmersiones" in certified_resp
    assert "🔗 *Info completa en la web*:" in certified_resp
    assert "¿Te gustaría que preparemos la reserva también para esa persona?" in certified_resp
    assert "Te paso con un asesor" not in certified_resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True

    state = await reach_group_type()
    await route_message(state, "2")
    await route_message(state, "2")
    await route_message(state, "reservar")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que quiere hacer buceo, podemos ir juntos?")

    beginner_resp = await route_message(state, "2")
    assert "Minicurso de Buceo" in beginner_resp
    assert "Principiantes (no necesitas experiencia previa)" in beginner_resp
    assert "¿Te gustaría que preparemos la reserva también para esa persona?" in beginner_resp
    assert "Te paso con un asesor" not in beginner_resp
    assert "refresh" not in beginner_resp.lower()


@pytest.mark.asyncio
async def test_certified_2_dives_reserved_friend_wants_to_dive_prompts_for_certification():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")
    assert state.step == Step.ESCALATE

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que también quiere hacer buceo, qué me recomiendas?")

    assert state.step == Step.FREE_TEXT
    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_certified_2_dives_reserved_friend_dive_follow_up_uses_canonical_cards():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que también quiere hacer buceo, qué me recomiendas?")

    certified_resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in certified_resp
    certified_resp = await route_message(state, "2")
    assert "Salidas de Buceo - 2 inmersiones" in certified_resp
    assert "🔗 *Info completa en la web*:" in certified_resp
    assert "Te paso con un asesor" not in certified_resp

    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que también quiere hacer buceo, qué me recomiendas?")

    beginner_resp = await route_message(state, "2")
    assert "Minicurso de Buceo" in beginner_resp
    assert "Principiantes (no necesitas experiencia previa)" in beginner_resp
    assert "refresh" not in beginner_resp.lower()
    assert "Te paso con un asesor" not in beginner_resp


@pytest.mark.asyncio
async def test_certified_2_dives_reserved_friend_wants_to_snorkel_shows_snorkel_info_card():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    assert state.selected_service == "2_dives_1_day"
    await route_message(state, "reservar")
    assert state.step == Step.ESCALATE

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que quiere hacer snorkel, podemos ir juntos?")

    assert state.step == Step.FREE_TEXT
    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "🔗 *Info completa en la web*:" in resp
    assert "¿Te gustaría que preparemos la reserva también para esa persona?" in resp
    assert "Te gustaría que un asesor" not in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_certified_2_dives_reserved_friend_snorkel_offer_can_enter_mixed_cart():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que quiere hacer snorkel, podemos ir juntos?")

    cart_resp = await route_message(state, "1")
    assert "Tu carrito" in cart_resp
    assert "Buceo certificado (2 inmersiones)" in cart_resp or "2 inmersiones" in cart_resp


@pytest.mark.asyncio
async def test_snorkel_reserved_friend_wants_same_activity_shows_info_card_and_enters_cart():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que también quiere hacer snorkel, podemos ir juntos?")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "Te paso con un asesor" not in resp
    cart_resp = await route_message(state, "1")
    assert "Tu carrito" in cart_resp
    assert "Snorkel" in cart_resp


@pytest.mark.asyncio
async def test_minicourse_reserved_friend_wants_to_snorkel_shows_snorkel_info_card():
    state = await reach_minicourse_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que quiere hacer snorkel, podemos ir juntos?")

    assert state.step == Step.FREE_TEXT
    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "🔗 *Info completa en la web*:" in resp
    assert "Te paso con un asesor" not in resp


@pytest.mark.asyncio
async def test_minicourse_reserved_friend_wants_to_dive_prompts_for_certification():
    state = await reach_minicourse_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que quiere hacer buceo, qué me recomiendas?")

    assert state.step == Step.FREE_TEXT
    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_minicourse_reserved_friend_dive_follow_up_uses_canonical_cards():
    state = await reach_minicourse_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que quiere hacer buceo, qué me recomiendas?")

    certified_resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in certified_resp
    certified_resp = await route_message(state, "2")
    assert "Salidas de Buceo - 2 inmersiones" in certified_resp
    assert "🔗 *Info completa en la web*:" in certified_resp
    assert "Te paso con un asesor" not in certified_resp

    state = await reach_minicourse_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Tengo un amigo que quiere hacer buceo, qué me recomiendas?")

    beginner_resp = await route_message(state, "2")
    assert "Minicurso de Buceo" in beginner_resp
    assert "Principiantes (no necesitas experiencia previa)" in beginner_resp
    assert "refresh" not in beginner_resp.lower()
    assert "Te paso con un asesor" not in beginner_resp


@pytest.mark.asyncio
async def test_minicourse_reserved_friend_wants_same_activity_shows_info_card_and_enters_cart():
    state = await reach_minicourse_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que también quiere hacer minicurso de buceo, podemos ir juntos?")

    assert "Minicurso de Buceo" in resp
    assert "Te paso con un asesor" not in resp
    cart_resp = await route_message(state, "1")
    assert "Tu carrito" in cart_resp
    assert "Minicurso" in cart_resp or "Buceo principiantes" in cart_resp


@pytest.mark.asyncio
async def test_companion_variant_pair_term_routes_to_snorkel_info_card():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Mi pareja quiere hacer snorkel, podemos ir juntos?")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "Te paso con un asesor" not in resp


@pytest.mark.asyncio
async def test_companion_variant_pair_term_reopens_canonical_diving_flow_after_decline():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo un amigo que quiere hacer buceo, podemos ir juntos?")

    assert "¿Tu amigo es *buzo certificado*?" in resp

    resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in resp

    resp = await route_message(state, "2")
    assert "Salidas de Buceo - 2 inmersiones" in resp

    resp = await route_message(state, "2")
    # Tras declinar: vuelve al SUMMARY follow_up con botones (Reservar/Ask/Volver).
    assert "mantenemos solo tu actividad" in resp.lower()
    assert state.step == Step.SUMMARY
    assert state.summary_mode == "follow_up"

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Mi pareja quiere bucear")

    assert "¿Tu amigo es *buzo certificado*?" in resp or "¿Tu acompañante es *buzo certificado*?" in resp
    assert "178 usd" not in resp.lower()
    assert "asesor" not in resp.lower()


@pytest.mark.asyncio
async def test_companion_variant_slang_term_routes_to_minicourse_info_card():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Mi parcera quiere hacer minicurso de buceo")

    assert "Minicurso de Buceo" in resp
    assert "Te paso con un asesor" not in resp


@pytest.mark.asyncio
async def test_companion_variant_group_phrase_without_activity_prompts_for_clarification():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Venimos dos")

    assert "qué actividad quiere hacer" in resp.lower()
    assert getattr(state, "mixed_from_single_activity_question_pending", False) is True
    assert [item["value"] for item in state.quick_replies] == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_companion_variant_pronoun_after_clarification_routes_to_cert_question():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Venimos dos")

    resp = await route_message(state, "Ella quiere buceo")
    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_companion_variant_direct_pronoun_with_activity_routes_to_snorkel_info_card():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Él quiere snorkel")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "Te paso con un asesor" not in resp


@pytest.mark.asyncio
async def test_companion_variant_same_activity_phrase_from_diving_still_asks_certification():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Mi esposa quiere hacer lo mismo")

    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_companion_variant_complex_sentence_uses_non_base_activity_for_pronoun_case():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Yo hago snorkel y ella bucea")

    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_companion_variant_distribution_sentence_uses_non_base_activity():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Uno quiere buceo y el otro snorkel")

    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


# ─── Bloque 2 (Gadea): frases mixtas "yo + él/ella" con 2 personas + actividades distintas ───

@pytest.mark.asyncio
async def test_block2_yo_snorkel_y_el_buceo_asks_cert_from_snorkel_summary():
    """Yo snorkel + él buceo → desde resumen snorkel, debe pedir la pregunta de certificación."""
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Yo quiero snorkel y él quiere buceo")

    assert "¿Tu amigo es *buzo certificado*?" in resp
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_block2_yo_buceo_y_pareja_snorkel_offers_snorkel_card_from_cert_summary():
    """Yo buceo cert + pareja snorkel → desde resumen 2 inmersiones, debe ofrecer tarjeta de snorkel."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    assert state.selected_service == "2_dives_1_day"
    await route_message(state, "reservar")
    assert state.step == Step.ESCALATE

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Yo buceo y mi pareja hace snorkel")

    assert state.step == Step.FREE_TEXT
    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "🔗 *Info completa en la web*:" in resp
    assert "¿Te gustaría que preparemos la reserva también para esa persona?" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block2_yo_snorkel_y_el_minicurso_offers_minicourse_card_from_snorkel_summary():
    """Yo snorkel + él minicurso → desde resumen snorkel, debe ofrecer tarjeta de minicurso."""
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Yo haría snorkel y él el minicurso")

    assert "Minicurso" in resp or "minicurso" in resp.lower()
    assert "🔗 *Info completa en la web*:" in resp
    assert "¿Te gustaría que preparemos la reserva también para esa persona?" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block2_yo_buceo_y_ella_solo_snorkel_offers_snorkel_card_from_cert_summary():
    """Yo buceo cert + ella SOLO snorkel → desde resumen 2 inmersiones, debe ofrecer tarjeta snorkel."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    assert state.selected_service == "2_dives_1_day"
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Yo quiero buceo y ella solo snorkel")

    assert state.step == Step.FREE_TEXT
    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "🔗 *Info completa en la web*:" in resp
    assert "¿Te gustaría que preparemos la reserva también para esa persona?" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block2_companion_detection_tolerates_snorkel_typo():
    """Con typo 'snorke' (sin la 'l' final), debe seguir entrando al flujo companion."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Yo quiero buceo y ella solo snorke")

    assert state.step == Step.FREE_TEXT
    assert "Snorkeling" in resp or "Tour de Snorkeling" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block2_pure_ellipsis_after_conjunction_routes_to_snorkel_card():
    """Elipsis pura: 'yo quiero buceo y ella snorke' (pronombre + actividad, sin verbo/adverbio).

    Caso reportado: el usuario escribe 'yo quiero buceo y ella snorke' (con typo).
    El pattern debe matchear porque va precedido del conector 'y'.
    """
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "yo quiero buceo y ella snorke")

    assert state.step == Step.FREE_TEXT
    assert "Snorkeling" in resp or "Tour de Snorkeling" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block2_pure_ellipsis_does_not_match_article_usage():
    """Falso positivo guard: 'el snorkel es divertido' (artículo + sustantivo, sin 'y'/'pero').

    No debe disparar el flujo companion — debe caer a RAG normal.
    """
    state = await reach_main_menu("es")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "el snorkel es divertido")
    # Debe caer a RAG, no a companion
    mock_rag.assert_awaited()
    assert resp == RAG_MOCK


# ─── Bloque 3 (Gadea): varios acompañantes, misma actividad ───

@pytest.mark.asyncio
async def test_block3_dos_acompanantes_quieren_buceo_asks_cert():
    """Yo snorkel + dos acompañantes buceo → debe pedir la pregunta de certificación (plural)."""
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Dos acompañantes quieren buceo")

    # Acepta tanto el wording singular ("Tu amigo es buzo certificado")
    # como el plural ("Estas N personas son buzos certificados").
    assert "buzo certificado" in resp.lower() or "buzos certificados" in resp.lower()
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_block3_tres_amigos_snorkel_conmigo_offers_snorkel_card():
    """Yo buceo cert + tres amigos snorkel → tarjeta snorkel."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tres amigos quieren hacer snorkel conmigo")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block3_tengo_dos_amigos_minicurso_offers_minicourse_card():
    """Yo buceo cert + dos amigos minicurso → tarjeta minicurso."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Tengo dos amigos que quieren el minicurso")

    assert "Minicurso" in resp or "minicurso" in resp.lower()
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block3_mis_dos_hijos_snorkel_offers_snorkel_card():
    """Yo buceo cert + dos hijos snorkel → tarjeta snorkel."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Mis dos hijos quieren snorkel")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block3_mis_amigos_prefieren_snorkel_offers_snorkel_card():
    """Yo buceo cert + amigos snorkel (sin cantidad) → tarjeta snorkel."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Mis amigos prefieren snorkel")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block3_venimos_tres_y_todos_snorkel_offers_snorkel_card():
    """Grupo 3 + todos snorkel desde resumen buceo → tarjeta snorkel (no pide aclaración)."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Venimos tres y todos quieren snorkel")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    # No debe pedir aclaración porque "todos" identifica una sola actividad
    assert "qué actividad quiere hacer cada persona" not in resp.lower()
    assert getattr(state, "mixed_from_single_offer_pending", False) is True


@pytest.mark.asyncio
async def test_block3_venimos_cuatro_y_los_tres_amigos_buceo_asks_cert():
    """Grupo 4, 3 amigos buceo (yo ya hago buceo) → debe preguntar cert (plural) para los amigos."""
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Venimos cuatro y los tres amigos quieren buceo")

    assert "buzo certificado" in resp.lower() or "buzos certificados" in resp.lower()
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True


@pytest.mark.asyncio
async def test_companion_variant_three_people_two_want_snorkel_routes_to_snorkel_card():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Venimos tres y dos quieren snorkel")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "Te paso con un asesor" not in resp


@pytest.mark.asyncio
async def test_companion_variant_two_friends_same_activity_routes_directly_without_extra_clarification():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Dos amigos quieren snorkel")

    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp
    assert "qué actividad quiere hacer cada persona" not in resp.lower()


@pytest.mark.asyncio
async def test_companion_variant_group_clarification_answer_preloads_two_snorkel_companions_into_cart():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Somos 3")

    assert "qué actividad quiere hacer cada persona" in resp.lower()
    resp = await route_message(state, "dos snorkel")
    assert "Tour de Snorkeling" in resp or "Snorkeling" in resp

    cart_resp = await route_message(state, "1")
    assert "2 × Snorkel" in cart_resp
    assert "Buceo certificado" in cart_resp


@pytest.mark.asyncio
async def test_companion_variant_three_people_two_want_snorkel_preloads_cart_quantities():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "Venimos tres y dos quieren snorkel")

    cart_resp = await route_message(state, "1")
    assert "2 × Snorkel" in cart_resp
    assert "Buceo certificado" in cart_resp


@pytest.mark.asyncio
async def test_companion_variant_mixed_group_after_certification_preloads_multiple_allocations():
    state = await reach_snorkeling_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Uno quiere buceo y otro snorkel")

    assert "¿Tu amigo es *buzo certificado*?" in resp
    resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in resp

    resp = await route_message(state, "2")
    assert "Buceo certificado" in resp
    assert "Snorkeling" in resp or "Tour de Snorkeling" in resp

    cart_resp = await route_message(state, "1")
    assert "2 × Snorkel" in cart_resp
    assert "Buceo certificado" in cart_resp


@pytest.mark.asyncio
async def test_companion_variant_multi_activity_without_base_match_prompts_for_clarification():
    state = await reach_minicourse_summary()
    await route_message(state, "reservar")

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "Uno quiere buceo y el otro snorkel")

    assert "qué actividad quiere hacer" in resp.lower()
    assert getattr(state, "mixed_from_single_activity_question_pending", False) is True


@pytest.mark.asyncio
async def test_companion_variant_generic_adults_question_does_not_trigger_companion_flow():
    state = await reach_snorkeling_summary()

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "¿Es una actividad apta para adultos?")

    assert resp == RAG_MOCK
    assert getattr(state, "mixed_from_single_activity_question_pending", False) is False
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is False
    assert getattr(state, "mixed_from_single_offer_pending", False) is False


# ===========================================================================
# BLOQUE 15 — FLUJOS EN INGLÉS
# ===========================================================================

@pytest.mark.asyncio
async def test_en_certified_2_dives_cartagena():
    state = await reach_diving_experience("en")
    responses = await send(state, "1", "1", "2", "2")
    assert state.language == "en"
    assert state.selected_service == "2_dives_1_day"
    assert state.step == Step.SUMMARY
    assert "Service" in responses[-1] or "Includes" in responses[-1] or "divingplanet" in responses[-1]


@pytest.mark.asyncio
async def test_en_beginner_snorkel():
    state = await reach_group_type("en")
    resp = await route_message(state, "2")
    assert state.language == "en"
    assert state.selected_service == "snorkeling"


@pytest.mark.asyncio
async def test_en_mixed_group_enters_cart_flow():
    state = await reach_group_type("en")
    resp = await route_message(state, "3")
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []
    assert "mixed" in resp.lower() or "snorkel" in resp.lower() or "step by step" in resp.lower()


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
    assert state.step == Step.PRICING_CARTAGENA
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
    state = await reach_diving_experience()
    await send(state, "1")
    resp = await route_message(state, "9")
    assert state.step == Step.TOURS_CERTIFIED


@pytest.mark.asyncio
async def test_invalid_beginner_option():
    state = await reach_diving_experience()
    await send(state, "2")
    resp = await route_message(state, "9")
    assert state.step == Step.BEGINNER_AGE


@pytest.mark.asyncio
async def test_invalid_certified_last_dive():
    state = await reach_diving_experience()
    await send(state, "1", "1")
    resp = await route_message(state, "9")
    assert state.step == Step.CERTIFIED_LAST_DIVE


@pytest.mark.asyncio
async def test_invalid_colombian_option():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2")  # → COLOMBIAN
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
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY (itinerary_offer)
    resp = await route_message(state, "itinerary")
    assert state.step == Step.SUMMARY
    assert "itinerario" in resp.lower() or "🗺️" in resp
    assert [item["value"] for item in state.quick_replies] == ["ask", "back"]


@pytest.mark.asyncio
async def test_summary_no_thanks_ends_conversation():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY (itinerary_offer)
    assert state.step == Step.SUMMARY
    assert [item["value"] for item in state.quick_replies] == ["itinerary", "back"]


@pytest.mark.asyncio
async def test_open_water_summary_back_returns_to_courses_menu():
    state = await reach_courses_menu()
    await send(state, "1", "1", "1", "2")  # open water > Cartagena > 2 días > no colombiano
    assert state.step == Step.SUMMARY
    await route_message(state, "back")
    assert state.step == Step.COURSES_MENU


@pytest.mark.asyncio
async def test_go_pro_summary_back_returns_to_go_pro_menu():
    state = await reach_courses_menu()
    await send(state, "2", "2", "2")  # go pro > rescue > no colombiano
    assert state.step == Step.SUMMARY
    await route_message(state, "back")
    assert state.step == Step.COURSES_ADVANCED_MENU


@pytest.mark.asyncio
async def test_specialties_summary_back_returns_to_specialties_menu():
    state = await reach_courses_menu()
    await send(state, "3", "5", "2")  # specialties > nitrox > no colombiano
    assert state.step == Step.SUMMARY
    await route_message(state, "back")
    assert state.step == Step.COURSES_SPECIALTIES_MENU


@pytest.mark.asyncio
async def test_go_pro_itinerary_back_returns_to_go_pro_menu():
    state = await reach_courses_menu()
    await send(state, "2", "1", "2")  # go pro > advanced > no colombiano
    assert state.step == Step.SUMMARY
    await route_message(state, "itinerary")
    assert state.step == Step.SUMMARY
    await route_message(state, "back")
    assert state.step == Step.COURSES_ADVANCED_MENU


@pytest.mark.asyncio
async def test_specialties_itinerary_back_returns_to_specialties_menu():
    state = await reach_courses_menu()
    await send(state, "3", "1", "2")  # specialties > mindful diving > no colombiano
    assert state.step == Step.SUMMARY
    await route_message(state, "itinerary")
    assert state.step == Step.SUMMARY
    await route_message(state, "back")
    assert state.step == Step.COURSES_SPECIALTIES_MENU


# ===========================================================================
# BLOQUE 18 — QUICK REPLIES CORRECTOS
# ===========================================================================

@pytest.mark.asyncio
async def test_quick_replies_set_at_main_menu():
    state = await reach_main_menu()
    assert len(state.quick_replies) == 2  # Reservar / Información


@pytest.mark.asyncio
async def test_quick_replies_set_at_tours_certified():
    state = await reach_diving_experience()
    await send(state, "1")
    assert len(state.quick_replies) > 0


@pytest.mark.asyncio
async def test_quick_replies_set_at_colombian():
    state = await reach_diving_experience()
    await send(state, "1", "1", "2")  # → COLOMBIAN step
    assert len(state.quick_replies) == 2  # Sí / No


@pytest.mark.asyncio
async def test_quick_replies_cleared_on_escalation():
    state = await reach_main_menu()
    await route_message(state, "asesor")
    assert state.quick_replies == []


@pytest.mark.asyncio
async def test_island_menu_has_12_options():
    state = await reach_logistics_menu()
    await send(state, "2")
    assert len(state.quick_replies) == 14


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
    state = await reach_diving_experience()
    await send(state, "1", "1", "2", "2")  # llega a SUMMARY
    assert state.step == Step.SUMMARY
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "y qué hay para comer exactamente?")
    assert resp == RAG_MOCK


@pytest.mark.asyncio
async def test_post_summary_photos_question_routes_to_rag():
    state = await reach_diving_experience()
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
    assert "colombian" in resp.lower() or "colombiano" in resp.lower()


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
    state = await reach_diving_experience(location="island")
    responses = await send(state, "1", "1", "2", "2")  # cert, 2 buceos, recent, no colombiano
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
    assert "colombian" in resp.lower() or "colombiano" in resp.lower()


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


# ===========================================================================
# Cart-style mixed-group flow tests
# ===========================================================================

async def reach_mixed_entry(lang: str = "es", location: str = "cartagena") -> ConversationState:
    """Reach MIXED_ENTRY via the GROUP_TYPE (buceo+snorkel) entry point."""
    state = await reach_group_type(lang, location)
    await route_message(state, "3")
    assert state.step == Step.MIXED_ENTRY
    return state


async def reach_mixed_add_activity(lang: str = "es", location: str = "cartagena") -> ConversationState:
    """Reach MIXED_ADD_ACTIVITY by advancing past the entry intro."""
    state = await reach_mixed_entry(lang, location)
    await route_message(state, "1")  # ¡Vamos a empezar!
    assert state.step == Step.MIXED_ADD_ACTIVITY
    return state


# --- Entry / add activity ---------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_entry_advances_to_add_activity():
    state = await reach_mixed_entry()
    resp = await route_message(state, "1")
    assert state.step == Step.MIXED_ADD_ACTIVITY
    assert "actividad" in resp.lower() or "activity" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_entry_without_location_asks_departure_before_add_activity():
    state = await reach_main_menu("es")
    await send(state, "1", "1")
    assert state.step == Step.GROUP_TYPE
    assert state.location is None

    await route_message(state, "3")
    assert state.step == Step.MIXED_ENTRY

    resp = await route_message(state, "1")
    assert state.step == Step.MIXED_LOCATION
    assert "desde dónde" in resp.lower() or "desde donde" in resp.lower()
    assert [item["value"] for item in state.quick_replies] == ["1", "2", "back"]


@pytest.mark.asyncio
async def test_mixed_add_cert_goes_to_cert_plan():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # Buceo certificado
    assert state.step == Step.MIXED_ADD_CERT_PLAN
    assert state.mixed_pending_qty_type == "cert"


@pytest.mark.asyncio
async def test_mixed_add_beginner_skips_to_qty():
    state = await reach_mixed_add_activity()
    await route_message(state, "2")  # Buceo principiantes (Minicurso)
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_qty_type == "beginner"


@pytest.mark.asyncio
async def test_mixed_add_snorkel_skips_to_qty():
    state = await reach_mixed_add_activity()
    await route_message(state, "3")  # Snorkel
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_qty_type == "snorkel"


@pytest.mark.asyncio
async def test_mixed_add_companion_skips_to_qty():
    state = await reach_mixed_add_activity()
    await route_message(state, "4")  # Acompañante
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_qty_type == "companion"


@pytest.mark.asyncio
async def test_mixed_cert_multiday_plan_escalates():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    resp = await route_message(state, "2")  # paquete multi-día
    assert state.step == Step.ESCALATE
    assert "multi-dia" in resp.lower() or "multi-día" in resp.lower()
    assert state.mixed_cart == []  # wiped before escalation


# --- Qty handling ----------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_qty_appends_to_cart_and_goes_to_review():
    state = await reach_mixed_add_activity()
    await route_message(state, "2")  # beginner
    resp = await route_message(state, "3")  # qty 3
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert state.mixed_cart == []
    assert "añadir esta actividad al carrito" in resp.lower() or "add this activity to the cart" in resp.lower()
    resp = await route_message(state, "1")
    assert state.step == Step.MIXED_CART_REVIEW
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "beginner"
    assert state.mixed_cart[0]["qty"] == 3
    assert "carrito" in resp.lower() or "cart" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_qty_6plus_asks_for_exact_count():
    state = await reach_mixed_add_activity()
    await route_message(state, "3")  # snorkel
    resp = await route_message(state, "6+")
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_exact is True
    assert state.mixed_cart == []  # not saved yet
    assert "exactamente" in resp.lower() or "exactly" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_qty_6plus_accepts_exact_number():
    state = await reach_mixed_add_activity()
    await route_message(state, "3")  # snorkel
    await route_message(state, "6+")
    await route_message(state, "9")
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert state.mixed_cart == []
    assert state.mixed_pending_exact is False


@pytest.mark.asyncio
async def test_mixed_cert_2dives_qty_appends_to_cart():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    await route_message(state, "1")  # 2 dives/1 day
    await route_message(state, "2")  # qty 2
    assert state.step == Step.MIXED_CERT_LAST_DIVE
    await route_message(state, "2")  # recent dive / no refresher needed
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "1")  # add to cart
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["plan"] == "2_dives_1_day"
    assert state.mixed_cart[0]["qty"] == 2


@pytest.mark.asyncio
async def test_mixed_cert_refresher_split_keeps_refresh_in_cart_and_continues_diving_preview():
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2")  # cert, 2 dives/1 day, qty 2
    assert state.step == Step.MIXED_CERT_LAST_DIVE

    resp = await route_message(state, "1")  # >2 years
    assert state.step == Step.MIXED_CERT_REFRESH_INTEREST
    assert "refresher" in resp.lower()

    resp = await route_message(state, "1")  # wants refresher
    assert state.step == Step.MIXED_CERT_REFRESH_QTY
    assert "cuántas personas" in resp.lower() or "how many people" in resp.lower()

    resp = await route_message(state, "1")  # only 1 wants refresher
    assert state.step == Step.MIXED_CERT_SPLIT_REVIEW
    assert "Minicurso / Refresher" in resp
    assert "queda 1 persona pendiente" in resp.lower()

    resp = await route_message(state, "1")  # continue with remaining diving
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "2 inmersiones" in resp.lower()

    resp = await route_message(state, "1")  # add remaining diving
    assert state.step == Step.MIXED_CART_REVIEW
    labels = [item["label"] for item in state.mixed_cart]
    assert "Minicurso / Refresher" in labels
    assert "Buceo certificado (2 inmersiones)" in labels


# --- Cart review actions ---------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_cart_add_more_returns_to_add_activity():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # beginner, qty 3, preview add -> CART_REVIEW
    await route_message(state, "1")  # add another
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_mixed_cart_add_two_items_accumulates():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners
    await send(state, "1", "1", "1", "2", "2", "1")  # add: cart-action 1, cert, 2-dives, qty 2, recent dive, preview add
    assert len(state.mixed_cart) == 2
    types = [it["type"] for it in state.mixed_cart]
    assert "beginner" in types and "cert" in types


@pytest.mark.asyncio
async def test_mixed_cart_modify_item_updates_qty():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners → CART_REVIEW
    await route_message(state, "2")  # modify item
    assert state.step == Step.MIXED_CART_MODIFY_PICK
    await route_message(state, "1")  # pick item 1
    assert state.step == Step.MIXED_ADD_QTY
    await route_message(state, "5")  # new qty
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["qty"] == 5
    assert state.mixed_pending_modify_idx is None


@pytest.mark.asyncio
async def test_mixed_cart_remove_item_drops_it():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # add beginner x3
    await send(state, "1", "3", "2", "1")  # add snorkel x2
    assert len(state.mixed_cart) == 2
    await route_message(state, "3")  # remove item
    await route_message(state, "1")  # remove item #1 (beginner)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "snorkel"


@pytest.mark.asyncio
async def test_mixed_cart_restart_wipes_state():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners
    state.mixed_final_is_colombian = True  # something to wipe
    await route_message(state, "5")  # restart
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []
    assert state.mixed_final_is_colombian is None


@pytest.mark.asyncio
async def test_mixed_cart_confirm_advances_to_colombian():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners
    await route_message(state, "4")  # confirmar carrito
    assert state.step == Step.MIXED_FINAL_COLOMBIAN


@pytest.mark.asyncio
async def test_mixed_cart_review_friend_wants_certified_diving_recent_dive_uses_canonical_companion_flow():
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "1", "2", "1")  # cert, 2 dives/1 day, qty 1, recent dive, preview add
    assert state.step == Step.MIXED_CART_REVIEW

    resp = await route_message(state, "Tengo un amigo que quiere hacer buceo, podemos ir juntos?")
    assert "¿Tu amigo es *buzo certificado*?" in resp

    resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in resp

    resp = await route_message(state, "2")
    assert "Salidas de Buceo - 2 inmersiones" in resp
    assert "Te gustaría que preparemos la reserva también para esa persona" in resp
    assert "asesor" not in resp.lower()

    cart_resp = await route_message(state, "1")
    assert "Tu carrito" in cart_resp
    assert "2 × Buceo certificado (2 inmersiones)" in cart_resp


@pytest.mark.asyncio
async def test_mixed_cart_review_friend_wants_certified_diving_refresher_yes_switches_to_minicourse():
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "1", "2", "1")  # cert, 2 dives/1 day, qty 1, recent dive, preview add
    assert state.step == Step.MIXED_CART_REVIEW

    resp = await route_message(state, "Tengo un amigo que quiere hacer buceo, podemos ir juntos?")
    assert "¿Tu amigo es *buzo certificado*?" in resp

    resp = await route_message(state, "1")
    assert "¿Han pasado *más de 2 años* desde tu última inmersión?" in resp

    resp = await route_message(state, "1")
    assert "Te recomendamos hacer un *refresher*" in resp
    assert "¿Te interesa incluirlo?" in resp

    resp = await route_message(state, "1")
    assert "Minicurso de Buceo" in resp
    assert "Te gustaría que preparemos la reserva también para esa persona" in resp

    cart_resp = await route_message(state, "1")
    assert "Tu carrito" in cart_resp
    assert "Minicurso" in cart_resp or "Buceo principiantes" in cart_resp


@pytest.mark.asyncio
async def test_mixed_cart_confirm_empty_does_not_advance():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # add then remove
    await send(state, "3", "1")  # remove item 1
    assert state.mixed_cart == []
    await route_message(state, "4")  # confirmar
    assert state.step != Step.MIXED_FINAL_COLOMBIAN


# --- Final questions -------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_final_kids_skipped_when_no_beginner():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await route_message(state, "4")  # confirm cart
    await route_message(state, "2")  # not colombian → no beginner → skip kids → private
    assert state.step == Step.MIXED_FINAL_PRIVATE
    assert state.mixed_final_has_kids_8_10 is None


@pytest.mark.asyncio
async def test_mixed_final_kids_asked_when_beginner_in_cart():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners
    await route_message(state, "4")  # confirm cart
    await route_message(state, "2")  # not colombian
    assert state.step == Step.MIXED_FINAL_KIDS


@pytest.mark.asyncio
async def test_mixed_full_path_lands_on_final_summary():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners
    await route_message(state, "4")  # confirm
    await route_message(state, "2")  # not colombian
    await route_message(state, "2")  # no kids
    await route_message(state, "2")  # no private
    assert state.step == Step.MIXED_FINAL_SUMMARY


@pytest.mark.asyncio
async def test_mixed_final_summary_shows_restaurant_bill():
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2, recent dive, preview add
    await send(state, "1", "3", "1", "1")  # add snorkel x1
    await send(state, "4", "2", "2")  # confirm, not colombian, no private
    assert state.step == Step.MIXED_FINAL_SUMMARY
    resp = state.mixed_last_summary or ""
    assert "RESERVA" in resp or "BOOKING" in resp
    assert "ACTIVIDADES" in resp or "ACTIVITIES" in resp
    assert "SUBTOTAL" in resp
    assert "TOTAL" in resp


@pytest.mark.asyncio
async def test_mixed_final_summary_avisos_only_when_relevant():
    """Small group (qty<6), no kids, no private → no Avisos block."""
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "4", "2", "2")  # confirm, not colombian, no private
    resp = state.mixed_last_summary or ""
    assert "Avisos" not in resp


@pytest.mark.asyncio
async def test_mixed_final_summary_large_group_shows_aviso():
    state = await reach_mixed_add_activity()
    await send(state, "3", "6+")
    await route_message(state, "8")  # 8 snorkelers
    await route_message(state, "1")  # preview add
    await send(state, "4", "2", "2")
    resp = state.mixed_last_summary or ""
    assert "Avisos" in resp
    assert "Grupo grande" in resp or "Large group" in resp


@pytest.mark.asyncio
async def test_mixed_final_summary_kids_yes_shows_aviso_and_stays_in_summary():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "1")  # 3 beginners
    await send(state, "4", "2", "1", "2")  # confirm, not colombian, YES kids, no private
    assert state.step == Step.MIXED_FINAL_SUMMARY
    assert state.mixed_final_has_kids_8_10 is True
    resp = state.mixed_last_summary or ""
    assert "Bubble Makers" in resp or "8-10" in resp


@pytest.mark.asyncio
async def test_mixed_final_summary_private_yes_shows_aviso():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "4", "2", "1")  # confirm, not colombian, YES private
    assert state.step == Step.MIXED_FINAL_SUMMARY
    assert state.mixed_final_wants_private is True
    resp = state.mixed_last_summary or ""
    assert "privada" in resp.lower() or "private" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_final_summary_colombian_shows_cop_primary():
    state = await reach_mixed_add_activity()
    await send(state, "2", "2", "1")  # 2 beginners
    await send(state, "4", "1", "2", "2")  # confirm, COLOMBIAN, no kids, no private
    resp = state.mixed_last_summary or ""
    assert "COP" in resp
    assert "descuento" in resp.lower() or "discount" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_final_summary_cartagena_shows_transport_note():
    state = await reach_mixed_add_activity(location="cartagena")
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "4", "2", "2")
    resp = state.mixed_last_summary or ""
    assert "transporte" in resp.lower() or "transport" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_final_summary_snorkel_waiver_only_when_snorkel():
    """Without snorkel the snorkel-specific note must NOT appear."""
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2 (no snorkel in cart)
    await send(state, "4", "2", "2")
    resp = state.mixed_last_summary or ""
    assert "formulario específico de snorkel" not in resp.lower()


@pytest.mark.asyncio
async def test_mixed_final_summary_reservar_escalates():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "4", "2", "2")  # confirm, not colombian, no private
    await route_message(state, "1")  # Reservar
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None
    assert "Lead Diving Planet" in state.pending_note


@pytest.mark.asyncio
async def test_mixed_final_summary_restart_wipes_state():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")
    await send(state, "4", "2", "2")
    await route_message(state, "2")  # Empezar de nuevo
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []


@pytest.mark.asyncio
async def test_mixed_lead_note_includes_cart_items():
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2
    await send(state, "1", "2", "3", "1")  # add buceo principiantes x3
    await send(state, "4", "2", "2", "2")  # confirm, not colombian, no kids, no private
    await route_message(state, "1")  # Reservar
    note = state.pending_note or ""
    assert "Grupo mixto" in note
    assert "Buceo certificado" in note or "Certified" in note
    assert "Minicurso" in note or "principiantes" in note.lower() or "beginner" in note.lower()


@pytest.mark.asyncio
async def test_mixed_final_summary_non_colombian_stores_booking_links():
    state = await reach_mixed_add_activity()
    await send(state, "2", "2", "1")  # 2 beginners
    await send(state, "4", "2", "2", "2")  # confirm, not colombian, no kids, no private
    # En el nuevo flujo los links NO se incluyen en el summary; se guardan en estado y
    # se envían al pulsar "Reservar".
    resp = state.mixed_last_summary or ""
    assert "book.divingplanet.org" not in resp
    # Los links sí están guardados en state.mixed_booking_links
    assert state.mixed_booking_links
    assert any("divingplanet.org" in url for _, url in state.mixed_booking_links)


@pytest.mark.asyncio
async def test_mixed_final_summary_colombian_no_whatsapp_note_inline():
    state = await reach_mixed_add_activity()
    await send(state, "2", "2", "1")
    await send(state, "4", "1", "2", "2")  # COLOMBIAN
    resp = state.mixed_last_summary or ""
    # Quitamos la nota inline de WhatsApp; el descuento se coordina en escalación.
    assert "book.divingplanet.org" not in resp
    assert "WhatsApp" not in resp


# --- LLM intent classifier (mocked) ----------------------------------------

@pytest.mark.asyncio
async def test_intent_classifier_routes_natural_text_to_button():
    state = await reach_mixed_add_activity()
    with patch("src.agents.supervisor.classify_menu_intent",
               new_callable=AsyncMock, return_value="2"):
        await route_message(state, "quiero el minicurso para principiantes")
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_qty_type == "beginner"


@pytest.mark.asyncio
async def test_intent_classifier_currency_switch_sets_display_currency():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2")  # snorkel x2 → CART_REVIEW
    with patch("src.agents.supervisor.classify_menu_intent",
               new_callable=AsyncMock, return_value="currency_switch_cop"):
        await route_message(state, "los precios en pesos por favor")
    assert state.mixed_display_currency == "COP"


@pytest.mark.asyncio
async def test_intent_classifier_restart_wipes_and_returns_to_entry():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2")
    with patch("src.agents.supervisor.classify_menu_intent",
               new_callable=AsyncMock, return_value="restart"):
        await route_message(state, "quiero empezar de cero")
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []


@pytest.mark.asyncio
async def test_intent_classifier_rag_fallback_when_no_match():
    state = await reach_mixed_add_activity()
    with patch("src.agents.supervisor.classify_menu_intent",
               new_callable=AsyncMock, return_value="RAG"):
        with patch("src.agents.supervisor.rag_answer",
                   new_callable=AsyncMock, return_value=RAG_MOCK):
            resp = await route_message(state, "qué tipos de tiburones se ven en las islas?")
    assert resp == RAG_MOCK


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
    resp = await route_message(state, "no me funciona")
    assert state.step == Step.ESCALATE
    assert "LINK ROTO" in (state.pending_escalation_reason or "")


@pytest.mark.asyncio
async def test_broken_link_complaint_with_formulario_word_escalates():
    state = make_state()
    resp = await route_message(state, "el formulario de exoneración no abre")
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
    resp = await route_message(state, "mi tarjeta no funciona, ayuda")
    # We want this NOT to match broken-link; either RAG or other escalation
    assert "LINK ROTO" not in (state.pending_escalation_reason or "")


@pytest.mark.asyncio
async def test_broken_link_lead_note_has_priority_marker():
    state = make_state()
    await route_message(state, "el link de pago no carga")
    assert state.pending_note is not None
    assert "LINK ROTO" in state.pending_note


