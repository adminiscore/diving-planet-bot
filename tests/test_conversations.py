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
    resp = await route_message(state, "zzz")  # truly ambiguous: no language signal at all
    assert state.step == Step.LANGUAGE
    assert "Español" in resp
    assert "English" in resp


@pytest.mark.asyncio
async def test_hola_detects_spanish_and_skips_language_step():
    state = make_state()
    resp = await route_message(state, "hola")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU
    assert "Diving Planet" in resp


@pytest.mark.asyncio
async def test_hello_detects_english_and_skips_language_step():
    state = make_state()
    resp = await route_message(state, "hello")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU
    assert "Diving Planet" in resp


@pytest.mark.asyncio
async def test_buenas_detects_spanish_and_skips_language_step():
    """"buenas" carries no English meaning at all, so it's not actually
    ambiguous: the bot should detect Spanish and skip the language question,
    same as "hola"."""
    state = make_state()
    resp = await route_message(state, "buenas")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_generic_spanish_phrase_at_welcome_detects_spanish():
    """Any free text that reveals the language ("qué pasó", no greeting word
    at all) should skip the language question too, not just exact greetings."""
    state = make_state()
    resp = await route_message(state, "que paso")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_generic_english_phrase_at_welcome_detects_english():
    state = make_state()
    resp = await route_message(state, "welcome")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_unrecognized_first_message_falls_back_to_llm_language_detection(monkeypatch):
    """Fase 1: the conversation agent answers the first message directly (via RAG),
    inferring language from the text itself rather than asking the LLM language
    fallback or the explicit language question."""
    state = make_state()
    resp = await route_message(state, "g'day mate, tell me about your diving courses")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_select_spanish_by_number():
    state = make_state()
    await route_message(state, "zzz")
    await route_message(state, "1")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_select_english_by_number():
    state = make_state()
    await route_message(state, "zzz")
    await route_message(state, "2")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_language_detection_english_text():
    state = make_state()
    await route_message(state, "zzz")
    resp = await route_message(state, "english")
    assert state.language == "en"


@pytest.mark.asyncio
async def test_language_detection_spanish_text():
    state = make_state()
    await route_message(state, "zzz")
    resp = await route_message(state, "español")
    assert state.language == "es"


@pytest.mark.asyncio
async def test_invalid_language_choice_shows_not_understood():
    state = make_state()
    await route_message(state, "zzz")
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
    await route_message(state, "zzz")
    assert state.step == Step.LANGUAGE
    await route_message(state, "in english?")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_text_espanol_at_language_step_selects_spanish():
    state = make_state()
    await route_message(state, "zzz")
    assert state.step == Step.LANGUAGE
    await route_message(state, "español")
    assert state.language == "es"
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_back_from_free_text_certification_question_returns_to_mixed_entry():
    """Regression: 'quiero bucear' jumps straight into MIXED_ASK_CERTIFICATION
    via the IntentDetector (no prior button click). Typing 'volver' there used
    to skip the special-case back routing (the step wasn't registered in
    MENU_STEPS/_MIXED_FLOW_STEPS) and reset all the way to MAIN_MENU instead
    of going one step back."""
    state = await reach_main_menu("es")
    r1 = await route_message(state, "quiero bucear")
    assert state.step == Step.MIXED_ASK_CERTIFICATION
    r2 = await route_message(state, "volver")
    assert state.step == Step.MIXED_ENTRY


@pytest.mark.asyncio
async def test_text_reservar_at_main_menu_advances_to_reserva_menu():
    state = await reach_main_menu("es")
    await route_message(state, "reservar")
    assert state.step == Step.MIXED_ENTRY


@pytest.mark.asyncio
async def test_text_informacion_at_main_menu_advances_to_info_menu():
    state = await reach_main_menu("es")
    await route_message(state, "información")
    assert state.step == Step.INFO_MENU


@pytest.mark.asyncio
async def test_text_book_at_english_main_menu_advances_to_reserva_menu():
    state = await reach_main_menu("en")
    await route_message(state, "book")
    assert state.step == Step.MIXED_ENTRY


@pytest.mark.asyncio
async def test_text_quiero_reservar_un_tour_advances_to_reserva_menu():
    state = await reach_main_menu("es")
    await route_message(state, "quiero reservar un tour")
    assert state.step == Step.MIXED_ENTRY


@pytest.mark.asyncio
async def test_question_with_button_keyword_routes_to_rag_not_menu():
    state = await reach_main_menu("es")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "cuánto cuesta reservar un tour?")
    # Question word "cuánto" must keep us out of the menu branch
    assert state.step != Step.MIXED_ENTRY


@pytest.mark.asyncio
async def test_irrelevant_free_text_at_main_menu_does_not_jump_branch():
    state = await reach_main_menu("es")
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        await route_message(state, "hola que tal me llamo juan")
    assert state.step not in (Step.MIXED_ENTRY, Step.INFO_MENU)


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
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
    resp = await route_message(state, "in english please")
    assert state.language == "en"
    assert state.step == Step.MAIN_MENU
    assert "English" in resp or "what" in resp.lower() or "book" in resp.lower()


@pytest.mark.asyncio
async def test_mid_conversation_language_switch_en_to_es():
    state = await reach_main_menu("en")
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
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
    """After a pricing answer, typing 'quiero reservar' must navigate to the unified booking cart."""
    state = await reach_pricing_menu("es")
    await route_message(state, "1")
    assert state.step == Step.PRICING_CARTAGENA
    await route_message(state, "quiero reservar")
    assert state.step == Step.MIXED_ENTRY


# ---------------------------------------------------------------------------
# Back navigation in the Reservar branch (button value="back" or keyword)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_back_button_value_from_reserva_menu_returns_to_main_menu():
    state = await reach_main_menu("es")
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
    await route_message(state, "back")  # Chatwoot sends value="back" when button is clicked
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_tours_skips_to_group_type():
    state = await reach_main_menu("es")
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
    await route_message(state, "back")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_back_button_value_from_courses_menu_returns_to_reserva_menu():
    state = await reach_courses_menu()
    await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_ACTIVITY


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
async def test_back_button_present_in_reservar_quick_replies():
    state = await reach_main_menu("es")
    await route_message(state, "1")  # RESERVA_MENU
    titles = [qr["title"] for qr in state.quick_replies]
    assert any("Volver" in t or "Back" in t for t in titles)


@pytest.mark.asyncio
async def test_back_button_not_present_in_info_menu():
    """INFO_MENU back goes to MAIN_MENU, same as Inicio — so the redundant
    Volver button is removed and only Inicio remains."""
    state = await reach_main_menu("es")
    await route_message(state, "2")  # INFO_MENU
    titles = [qr["title"] for qr in state.quick_replies]
    assert not any("Volver" in t or "Back" in t for t in titles)
    assert any("Inicio" in t or "Home" in t for t in titles)


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

@pytest.mark.asyncio
async def test_open_water_from_cartagena_enough_time():
    state = await reach_courses_menu()
    responses = await send(state, "1", "1", "1")  # Open Water > qty 1 > 2 días completos
    resp = responses[-1]
    assert state.selected_service == "open_water"
    assert state.location == "cartagena"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "open water" in resp.lower()


@pytest.mark.asyncio
async def test_divemaster_summary_contact_button_escalates_to_manager():
    state = await reach_courses_menu()
    responses = await send(state, "2", "3", "2")  # go pro > divemaster > qty 2
    resp = responses[-1]
    assert state.selected_service == "divemaster"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "divemaster" in resp.lower() or "dive master" in resp.lower()


@pytest.mark.asyncio
async def test_open_water_from_cartagena_not_enough_time():
    state = await reach_courses_menu()
    responses = await send(state, "1", "1", "2")  # Open Water > qty 1 > menos tiempo
    resp = responses[-1]
    assert state.selected_service == "open_water"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "open water" in resp.lower()
    assert "2 dias completos" in resp.lower() or "2 días completos" in resp.lower()
    assert "1 noche" in resp.lower()


@pytest.mark.asyncio
async def test_open_water_already_on_island():
    state = await reach_courses_menu(location="island")
    responses = await send(state, "1", "1", "2")  # Open Water > qty 1 > menos tiempo
    resp = responses[-1]
    assert state.location == "island"
    assert state.selected_service == "open_water_already_on_island"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "2 dias completos" in resp.lower() or "2 días completos" in resp.lower()
    assert "1 noche" not in resp.lower()


@pytest.mark.asyncio
async def test_advanced_course_selected():
    state = await reach_courses_menu()
    responses = await send(state, "2", "1", "1")  # go pro > advanced > qty 1
    resp = responses[-1]
    assert state.selected_service in ("advanced", "advanced_already_on_island")
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "advanced" in resp.lower() or "avanzado" in resp.lower()


@pytest.mark.asyncio
async def test_rescue_course_selected():
    state = await reach_courses_menu()
    responses = await send(state, "2", "2", "1")  # go pro > rescue > qty 1
    resp = responses[-1]
    assert state.selected_service == "rescue"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "rescate" in resp.lower() or "rescue" in resp.lower()


@pytest.mark.asyncio
async def test_divemaster_course_selected():
    state = await reach_courses_menu()
    responses = await send(state, "2", "3", "1")  # go pro > divemaster > qty 1
    resp = responses[-1]
    assert state.selected_service == "divemaster"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "divemaster" in resp.lower() or "dive master" in resp.lower()


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
    responses = await send(state, "3", "2", "1")  # specialties > fish id > qty 1
    resp = responses[-1]
    assert "fish" in state.selected_service or "peces" in state.selected_service
    assert state.step in (Step.MIXED_ADD_PREVIEW, Step.ESCALATE)


@pytest.mark.asyncio
async def test_nitrox_specialty():
    state = await reach_courses_menu()
    responses = await send(state, "3", "5", "1")  # specialties > nitrox > qty 1
    resp = responses[-1]
    assert "nitrox" in state.selected_service
    assert state.step in (Step.MIXED_ADD_PREVIEW, Step.ESCALATE)


@pytest.mark.asyncio
async def test_referral_reactivate_escalates():
    state = await reach_courses_menu()
    resp = await route_message(state, "4")
    assert state.step == Step.MIXED_ADD_QTY
    assert state.selected_service == "referral"
    resp = await route_message(state, "1")
    assert state.location == "cartagena"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "refer" in resp.lower()


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
async def test_pricing_menu_discounts():
    state = await reach_pricing_menu()
    resp = await route_message(state, "4")  # descuentos disponibles
    assert state.step == Step.PRICING_DISCOUNTS
    # Verifica que muestra los descuentos reales (online, grupo, equipo propio)
    assert "10%" in resp or "grupo" in resp.lower() or "discount" in resp.lower() or "descuento" in resp.lower()
    # No debe mencionar descuento especial colombiano
    assert "descuento colombian" not in resp.lower()
    assert "especial para colombian" not in resp.lower()


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
    state = make_state()
    state.location = "cartagena"
    state.step = Step.MIXED_ADD_ACTIVITY  # mid-flow in the cart
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
    state = make_state()
    state.location = "cartagena"
    state.step = Step.MIXED_ADD_CERT_PLAN  # deep in the cart flow
    resp = await route_message(state, "menu")
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
async def test_keyword_atras_goes_back_one_step():
    """'atrás' from COURSES_MENU must return to the cart activity selector, not MAIN_MENU."""
    state = await reach_courses_menu()
    await route_message(state, "atrás")
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_escalation_note_includes_service_if_known():
    state = make_state()
    state.location = "cartagena"
    state.selected_service = "2_dives_1_day"
    state.step = Step.MIXED_ADD_ACTIVITY
    resp = await route_message(state, "asesor")
    assert state.pending_note is not None
    # Advisor note shows the friendly service name, not the raw id.
    assert "2_dives_1_day" not in state.pending_note
    assert "Servicio de interés:" in state.pending_note
    assert "2 inmersiones" in state.pending_note or "Salidas de Buceo" in state.pending_note


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
    # A genuine info question (not a booking request, which the IntentDetector
    # would route into the cart flow) must reach RAG.
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "qué tortugas y peces se ven bajo el agua?")
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
    await route_message(state, "zzz")  # no language signal -> stays at LANGUAGE step
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "si")  # 1 palabra, sin "?" → tree, no RAG
    mock_rag.assert_not_called()


@pytest.mark.asyncio
async def test_post_summary_free_text_routes_to_rag():
    state = make_state()
    state.step = Step.SUMMARY
    state.selected_service = "2_dives_1_day"
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
async def test_en_open_water_from_island():
    state = await reach_courses_menu("en", location="island")
    responses = await send(state, "1", "1", "2")
    resp = responses[-1]
    assert state.location == "island"
    assert state.selected_service == "open_water_already_on_island"
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "2 full days" in resp.lower()
    assert "overnight stay" not in resp.lower()


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
async def test_invalid_island_menu_option():
    state = await reach_logistics_menu()
    await send(state, "2")
    resp = await route_message(state, "99")
    assert state.step == Step.ISLAND_MENU


@pytest.mark.asyncio
async def test_open_water_summary_back_returns_to_courses_menu():
    state = await reach_courses_menu()
    await send(state, "1", "1", "1")  # open water > qty 1 > 2 días
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_go_pro_summary_back_returns_to_go_pro_menu():
    state = await reach_courses_menu()
    await send(state, "2", "2", "1")  # go pro > rescue > qty 1
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_specialties_summary_back_returns_to_specialties_menu():
    state = await reach_courses_menu()
    await send(state, "3", "5", "1")  # specialties > nitrox > qty 1
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_go_pro_itinerary_back_returns_to_go_pro_menu():
    state = await reach_courses_menu()
    await send(state, "2", "1", "1")  # go pro > advanced > qty 1
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "itinerary")
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_specialties_itinerary_back_returns_to_specialties_menu():
    state = await reach_courses_menu()
    await send(state, "3", "1", "1")  # specialties > mindful diving > qty 1
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "itinerary")
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_ACTIVITY


# ===========================================================================
# BLOQUE 18 — QUICK REPLIES CORRECTOS
# ===========================================================================

@pytest.mark.asyncio
async def test_quick_replies_set_at_main_menu():
    state = await reach_main_menu()
    assert len(state.quick_replies) == 2  # Reservar / Información


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
async def test_summary_reservar_non_colombian_sends_link_directly():
    """Single-service booking: non-Colombian clients get the link immediately."""
    state = make_state()
    state.step = Step.SUMMARY
    state.summary_mode = "itinerary_offer"
    state.selected_service = "2_dives_1_day"
    state.is_colombian = False
    resp = await route_message(state, "reservar")
    assert state.step == Step.FREE_TEXT
    assert state.pending_escalation_reason is None
    assert "divingplanet.org" in resp
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_summary_reservar_colombian_still_escalates():
    """Colombian clients keep going through the advisor (split payment + discount)."""
    state = make_state()
    state.step = Step.SUMMARY
    state.summary_mode = "itinerary_offer"
    state.selected_service = "2_dives_1_day"
    state.is_colombian = True
    resp = await route_message(state, "reservar")
    assert state.step == Step.ESCALATE
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_summary_cash_payment_escalates_even_for_non_colombian():
    """The 'pay in person' button always escalates, regardless of nationality."""
    state = make_state()
    state.step = Step.SUMMARY
    state.summary_mode = "itinerary_offer"
    state.selected_service = "2_dives_1_day"
    state.is_colombian = False
    resp = await route_message(state, "cash")
    assert state.step == Step.ESCALATE
    assert "presencial" in resp.lower()
    assert "divingplanet.org" not in resp
    assert state.pending_note is not None


@pytest.mark.asyncio
async def test_post_summary_food_question_routes_to_rag():
    state = make_state()
    state.step = Step.SUMMARY
    state.selected_service = "2_dives_1_day"
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK) as mock_rag:
        resp = await route_message(state, "y qué hay para comer exactamente?")
    assert resp == RAG_MOCK


@pytest.mark.asyncio
async def test_post_summary_photos_question_routes_to_rag():
    state = make_state()
    state.step = Step.SUMMARY
    state.selected_service = "2_dives_1_day"
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
    responses = await send(state, "2", "3", "1")
    resp = responses[-1]
    assert state.selected_service == "divemaster"
    assert "divemaster" in resp.lower() or "professional" in resp.lower() or "profesional" in resp.lower()


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
async def test_open_water_cartagena_mentions_overnight_need():
    state = await reach_courses_menu()
    responses = await send(state, "1", "1", "1")
    resp = responses[-1]
    assert state.selected_service == "open_water"
    assert "open water" in resp.lower()


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


@pytest.mark.asyncio
async def test_single_open_water_can_upgrade_to_mixed_cart_preserving_course_plan():
    state = make_state("es")
    state.step = Step.SUMMARY
    state.selected_service = "open_water"
    state.location = "cartagena"
    state.history = []

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "voy con un amigo")

    assert "curso padi" in resp.lower()
    assert getattr(state, "mixed_from_single_offer_pending", False) is True

    confirm = await route_message(state, "1")

    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["type"] == "course"
    assert state.mixed_cart[0]["plan"] == "open_water"
    assert "carrito" in confirm.lower() or "cart" in confirm.lower()


@pytest.mark.asyncio
async def test_single_island_certified_package_can_upgrade_to_mixed_cart_preserving_exact_plan():
    state = make_state("es")
    state.step = Step.SUMMARY
    state.selected_service = "5_dives_2_days_already_on_island"
    state.location = "island"
    state.history = []

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "voy con mi pareja")

    assert "buceo certificado" in resp.lower()
    assert getattr(state, "mixed_from_single_offer_pending", False) is True

    await route_message(state, "1")

    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["plan"] == "5_dives_2_days_already_on_island"


@pytest.mark.asyncio
async def test_single_exact_certified_same_activity_preserves_exact_plan_for_companion():
    state = make_state("es")
    state.step = Step.SUMMARY
    state.selected_service = "5_dives_2_days_already_on_island"
    state.location = "island"
    state.history = []

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=RAG_MOCK):
        resp = await route_message(state, "voy con mi pareja y hará lo mismo")

    assert "buzo certificado" in resp.lower() or "buzos certificados" in resp.lower()
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True

    resp = await route_message(state, "1")
    assert "última inmersión" in resp.lower() or "ultima inmersion" in resp.lower()

    resp = await route_message(state, "2")
    assert getattr(state, "mixed_from_single_offer_pending", False) is True
    assert "5 inmersiones" in resp.lower()

    await route_message(state, "1")

    assert state.step == Step.MIXED_CART_REVIEW
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["plan"] == "5_dives_2_days_already_on_island"
    assert state.mixed_cart[0]["qty"] == 2


@pytest.mark.asyncio
async def test_mixed_flow_same_activity_on_exact_certified_plan_preserves_exact_plan():
    state = make_state("es")
    state.step = Step.MIXED_CART_REVIEW
    state.location = "island"
    state.mixed_cart = [
        {
            "type": "cert",
            "qty": 1,
            "plan": "5_dives_2_days_already_on_island",
            "label": "5 inmersiones / 2 días",
        }
    ]

    resp = await route_message(state, "mi pareja hace lo mismo")

    assert "buzo certificado" in resp.lower() or "buzos certificados" in resp.lower()
    assert getattr(state, "mixed_from_single_cert_question_pending", False) is True

    await route_message(state, "1")
    resp = await route_message(state, "2")

    assert getattr(state, "mixed_from_single_offer_pending", False) is True
    assert "5 inmersiones" in resp.lower()

    await route_message(state, "1")

    assert state.step == Step.MIXED_CART_REVIEW
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["plan"] == "5_dives_2_days_already_on_island"
    assert state.mixed_cart[0]["qty"] == 2


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

@pytest.mark.asyncio
async def test_free_text_cert_split_does_not_duplicate_minicourse_qty():
    """Regression: "somos 2 ... uno no esta certificado" detects
    group_allocation={certified_diving:1, minicourse:1} and queues the
    minicourse via mixed_pending_beginner_after_cert (added automatically once
    the certified subgroup is in the cart). _after_location_set() ALSO used to
    auto-add the same allocation immediately when the location question was
    answered, so the minicourse ended up in the cart with qty=2 instead of 1."""
    state = ConversationState(conversation_id="cert-split-no-dup-test")
    await route_message(state, "Hola somos dos personas y uno no esta certficado")
    assert state.step == Step.MIXED_LOCATION

    await route_message(state, "1")  # Cartagena -> triggers _after_location_set
    assert state.step == Step.MIXED_ADD_CERT_PLAN
    # The minicourse must NOT have been added yet here (still queued).
    assert state.mixed_cart == []
    assert state.mixed_pending_beginner_after_cert == 1

    await route_message(state, "1")  # 2 inmersiones / 1 dia
    await route_message(state, "2")  # last dive < 2 years -> No
    await route_message(state, "1")  # Añadir cert al carrito -> asks beginner activity next
    cert_item = next(it for it in state.mixed_cart if it["type"] == "cert")
    assert cert_item["qty"] == 1
    assert state.step == Step.MIXED_ASK_BEGINNER_ACTIVITY

    await route_message(state, "1")  # Minicurso de buceo
    await route_message(state, "3")  # kids: Todos 10+
    await route_message(state, "1")  # Añadir minicurso al carrito
    beginner_item = next(it for it in state.mixed_cart if it["type"] == "beginner")
    assert beginner_item["qty"] == 1
    assert len(state.mixed_cart) == 2


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
    await route_message(state, "1")
    assert state.step == Step.MIXED_ENTRY
    assert state.location is None

    resp = await route_message(state, "1")
    assert state.step == Step.MIXED_LOCATION
    assert "cartagena" in resp.lower() and "islas" in resp.lower()
    assert [item["value"] for item in state.quick_replies] == ["1", "2", "back"]


@pytest.mark.asyncio
async def test_mixed_add_cert_goes_to_cert_plan():
    state = await reach_mixed_add_activity()
    resp = await route_message(state, "1")  # Buceo certificado
    assert state.step == Step.MIXED_ADD_CERT_PLAN
    assert state.mixed_pending_qty_type == "cert"
    assert [item["title"] for item in state.quick_replies[:2]] == [
        "🤿 2 Inmersiones / 1 día",
        "📅 Paquete multi-día (3 o más inmersiones)",
    ]
    assert "qué idea tienes" in resp.lower()


@pytest.mark.asyncio
async def test_mixed_add_activity_uses_back_label_in_spanish():
    state = await reach_mixed_add_activity()
    assert state.quick_replies[-1]["title"] == "🔙 Volver"
    assert state.quick_replies[-1]["value"] == "back"


@pytest.mark.asyncio
async def test_mixed_add_activity_uses_back_label_in_english():
    state = await reach_mixed_add_activity("en")
    assert state.quick_replies[-1]["title"] == "🔙 Back"
    assert state.quick_replies[-1]["value"] == "back"


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
async def test_mixed_add_companion_offers_upsell_then_qty():
    """#8: choosing 'companion' first offers the mini-course/snorkel upsell; only
    after 'no, just accompany' does it add a pure companion and go to qty."""
    state = await reach_mixed_add_activity()
    await route_message(state, "5")  # Acompañante → upsell
    assert state.step == Step.MIXED_COMPANION_UPSELL
    await route_message(state, "3")  # "No, solo acompañar"
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_qty_type == "companion"


@pytest.mark.asyncio
async def test_mixed_certified_5_dives_goes_to_qty_and_keeps_exact_plan():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    resp = await route_message(state, "2")  # multi-day
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY
    resp = await route_message(state, "3")  # 5 inmersiones / 2 días
    assert state.step == Step.MIXED_ADD_QTY
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert "cuántas personas" in resp.lower() or "how many people" in resp.lower()


# --- Info link in the per-activity preview and the cart review -------------
# Requested by the owner: at both of these points the client doesn't need to
# wait for the nationality question (which only affects the BOOKING link with
# its 10% online discount) to get the informational page for the service —
# that link is the same regardless of nationality.

@pytest.mark.asyncio
async def test_individual_preview_includes_info_link_not_booking_link():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    await route_message(state, "1")  # 2 dives / 1 day
    await route_message(state, "1")  # qty 1
    resp = await route_message(state, "no")  # recent dive, no refresher
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "https://divingplanet.org/tours-buceo-snorkel-cartagena/2-buceos-1-dia/" in resp
    assert "book.divingplanet.org" not in resp, "booking link must stay deferred until after nationality"


@pytest.mark.asyncio
async def test_cart_review_includes_info_link_not_booking_link():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    await route_message(state, "1")  # 2 dives / 1 day
    await route_message(state, "1")  # qty 1
    await route_message(state, "no")  # recent dive, no refresher
    resp = await route_message(state, "1")  # add to cart
    assert state.step == Step.MIXED_CART_REVIEW
    assert "https://divingplanet.org/tours-buceo-snorkel-cartagena/2-buceos-1-dia/" in resp
    assert "book.divingplanet.org" not in resp


@pytest.mark.asyncio
async def test_cart_review_info_link_english():
    state = await reach_mixed_add_activity(lang="en")
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "no")
    resp = await route_message(state, "1")
    assert "more information" in resp.lower()
    assert "https://divingplanet.org/tours-buceo-snorkel-cartagena/2-buceos-1-dia/" in resp


@pytest.mark.asyncio
async def test_followup_question_at_preview_does_not_reset_flow(agent_decides):
    """Regression (found live 2026-07-09): a customer at the final preview
    ("¿Te la añado a tu reserva?") asked a natural follow-up that the LLM
    tool-router misclassified as start_booking for the SAME activity already
    being previewed. This used to unconditionally restart the cert sub-flow
    from its very first "which plan?" question, discarding the
    already-resolved plan/qty/last-dive answers. Must now stay at the preview
    and answer via RAG instead.

    Uses a group-discount question rather than the original "vale y como
    reservo?" wording — that phrase is now intercepted earlier by the
    deterministic "how do I book" shortcut (2026-07-16), which is covered by
    its own dedicated tests below; this one isolates the orchestrator
    reset-guard fix specifically.
    """
    from src.agents import orchestrator

    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    await route_message(state, "1")  # 2 dives / 1 day
    await route_message(state, "1")  # qty 1
    await route_message(state, "no")  # recent dive, no refresher
    assert state.step == Step.MIXED_ADD_PREVIEW
    plan_before = state.mixed_pending_qty_plan

    agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "certified"})
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        resp = await route_message(state, "y hay descuento por grupo?")

    assert resp == "CANNED_RAG_ANSWER"
    assert state.step == Step.MIXED_ADD_PREVIEW, "must not reset to the cert-plan question"
    assert state.mixed_pending_qty_plan == plan_before


# --- "Cómo reservo?" with a known activity -> direct info link, no RAG -----
# Owner request (2026-07-16): reduce friction — when we already know exactly
# which activity the client wants, a booking-process question should get the
# activity's own info link directly, not the generic RAG answer (exoneration
# form + manual 50% payment + advisor confirmation) and not a nudge toward
# "confirmar carrito".

@pytest.mark.asyncio
async def test_how_to_book_at_preview_gives_direct_info_link():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")  # cert
    await route_message(state, "1")  # 2 dives / 1 day
    await route_message(state, "1")  # qty 1
    resp = await route_message(state, "no")  # recent dive, no refresher
    assert state.step == Step.MIXED_ADD_PREVIEW

    resp = await route_message(state, "Vale y como reservo?")
    assert state.step == Step.MIXED_ADD_PREVIEW, "must not move to cart/confirm"
    assert "https://divingplanet.org/tours-buceo-snorkel-cartagena/2-buceos-1-dia/" in resp
    assert "exoneraci" not in resp.lower()
    assert "50%" not in resp
    assert "confirmar carrito" not in resp.lower()
    assert "más concreto" in resp, "must invite the client to re-ask if they meant something else"


@pytest.mark.asyncio
async def test_how_to_book_at_cart_review_gives_direct_info_link():
    state = await reach_mixed_add_activity()
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "no")
    await route_message(state, "1")  # add to cart
    assert state.step == Step.MIXED_CART_REVIEW

    resp = await route_message(state, "y como reservo?")
    assert state.step == Step.MIXED_CART_REVIEW
    assert "https://divingplanet.org/tours-buceo-snorkel-cartagena/2-buceos-1-dia/" in resp
    assert "exoneraci" not in resp.lower()


@pytest.mark.asyncio
async def test_how_to_book_english():
    state = await reach_mixed_add_activity(lang="en")
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "no")
    resp = await route_message(state, "ok how do i book this")
    assert "https://divingplanet.org/tours-buceo-snorkel-cartagena/2-buceos-1-dia/" in resp
    assert "any other questions" in resp.lower()
    assert "more specific" in resp.lower()


@pytest.mark.asyncio
async def test_real_booking_request_still_reaches_normal_flow():
    """"Si quiero reservar" is an action, not a process-question — must NOT be
    hijacked by the how-to-book shortcut. It matches the preview's "add to
    cart" quick-reply text instead, proceeding to the cart review as normal
    (which already carries its own info link from the earlier fix)."""
    state = await reach_mixed_add_activity()
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "1")
    await route_message(state, "no")
    assert state.step == Step.MIXED_ADD_PREVIEW
    resp = await route_message(state, "si quiero reservar")
    assert state.step == Step.MIXED_CART_REVIEW
    assert "🛒" in resp


@pytest.mark.asyncio
async def test_mixed_certified_island_menu_shows_both_4_dive_variants():
    state = await reach_mixed_add_activity(location="island")
    resp = await route_message(state, "1")

    assert state.step == Step.MIXED_ADD_CERT_PLAN
    assert "paquete multi-día" in resp.lower()
    assert [item["title"] for item in state.quick_replies[:2]] == [
        "🤿 2 Inmersiones / 1 día",
        "📅 Paquete multi-día (3 o más inmersiones)",
    ]

    resp = await route_message(state, "2")

    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY
    assert "3 o más inmersiones" in resp
    assert [item["title"] for item in state.quick_replies[:6]] == [
        "🤿 3 inmersiones (1 día)*",
        "🤿 4 inmersiones (2 días) · 4 diurnas",
        "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna",
        "🤿 5 inmersiones (2 días)",
        "🤿 7 inmersiones (3 días)",
        "🤿 9 inmersiones (4 días)",
    ]


@pytest.mark.asyncio
async def test_mixed_certified_island_night_variant_is_added_to_cart_with_exact_service():
    state = await reach_mixed_add_activity(location="island")
    await route_message(state, "1")  # cert
    await route_message(state, "2")  # multi-day
    await route_message(state, "3")  # 4 dives island variant with night dive
    await route_message(state, "2")  # qty 2
    await route_message(state, "2")  # recent dive / no refresher
    await route_message(state, "1")  # add to cart

    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["plan"] == "4_dives_2_days_mixed_already_on_island"
    assert state.mixed_cart[0]["qty"] == 2


# --- Preview shows total price for a known group size -----------------------

@pytest.mark.asyncio
async def test_preview_shows_group_total_price_when_qty_known_from_free_text():
    """"somos 4 ... snorkel" already reveals qty=4 -> the pre-add preview card
    should show 4 × unit = total, not just the per-person price."""
    from src.flows.decision_tree import SERVICES

    state = ConversationState(conversation_id="preview-qty-test")
    await route_message(state, "hola")
    await route_message(state, "somos 4 que vamos a hacer snorkel")
    resp = await route_message(state, "1")  # Cartagena
    assert state.step == Step.MIXED_ADD_PREVIEW

    svc = SERVICES["snorkeling"]
    discount_total = round(svc["price_usd"] * 4)
    normal_total = round(svc["price_usd_normal"] * 4)
    assert "Tarifa normal" in resp
    # The final total of both the normal rate and the discounted rate are
    # bold ("**") — the labels and "× qty =" stay plain (this chat renderer
    # treats single "*" as italic, not bold).
    assert f"× 4 = **${normal_total}**" in resp
    assert "Reservando online **(10% off)**" in resp
    assert f"${round(svc['price_usd'])} × 4 = **${discount_total}**" in resp
    assert "**Reservando online" not in resp


@pytest.mark.asyncio
async def test_preview_shows_single_price_without_multiplication_when_qty_is_one():
    """A single-person booking keeps the plain per-person price (no "× 1" noise)."""
    state = await reach_mixed_add_activity()
    resp = await route_message(state, "3")  # snorkel
    resp = await route_message(state, "1")  # qty 1 -> preview
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "×" not in resp.split("💰 Precio:")[1].split("⏱")[0]


# --- Availability/dates questions mid-flow ----------------------------------

@pytest.mark.asyncio
async def test_availability_question_gets_canned_answer_and_resume_buttons():
    """A "what days/dates are available" question mid-flow must never invent a
    date — it gets a reassuring canned answer pointing to the booking link's
    calendar, plus a real "Continuar con la reserva" button (not free text)
    that resumes exactly where the client was."""
    state = ConversationState(conversation_id="availability-test")
    await route_message(state, "hola")
    await route_message(state, "somos 4 que vamos a hacer snorkel")
    await route_message(state, "1")  # Cartagena -> MIXED_ADD_PREVIEW
    assert state.step == Step.MIXED_ADD_PREVIEW

    resp = await route_message(state, "y que dias hay disponibles?")
    assert state.step == Step.MIXED_ADD_PREVIEW  # untouched -> can resume
    assert "diari" in resp.lower()
    assert "disponibilidad" in resp.lower()
    assert "calendario" in resp.lower() and "link" in resp.lower()
    assert [r["title"] for r in state.quick_replies] == [
        "✅ Continuar con la reserva",
        "🏠 Inicio",
    ]
    # The continue button reuses the original primary action's value (here
    # "1" = "Añadir al carrito"), so clicking it resumes, doesn't restart.
    assert state.quick_replies[0]["value"] == "1"

    resp = await route_message(state, state.quick_replies[0]["value"])
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart == [
        {"type": "snorkel", "qty": 4, "plan": None, "label": "Snorkel"}
    ]


@pytest.mark.asyncio
async def test_availability_question_english():
    state = await reach_mixed_add_activity("en")
    await route_message(state, "3")  # snorkel
    resp = await route_message(state, "1")  # qty 1 -> preview
    assert state.step == Step.MIXED_ADD_PREVIEW

    resp = await route_message(state, "what days are available?")
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "daily" in resp.lower()
    assert "availability" in resp.lower()
    assert [r["title"] for r in state.quick_replies] == [
        "✅ Continue with booking",
        "🏠 Home",
    ]


@pytest.mark.asyncio
async def test_urgent_availability_phrase_still_escalates():
    """"disponible mañana" / "hay cupo" are urgent real-time checks and must
    still escalate — the generic canned answer must not swallow them."""
    state = await reach_main_menu("es")
    resp = await route_message(state, "tienen cupo disponible mañana?")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_availability_question_home_button_returns_to_main_menu():
    state = ConversationState(conversation_id="availability-home-test")
    await route_message(state, "hola")
    await route_message(state, "somos 4 que vamos a hacer snorkel")
    await route_message(state, "1")  # Cartagena -> MIXED_ADD_PREVIEW
    await route_message(state, "y que dias hay disponibles?")
    home_value = state.quick_replies[1]["value"]
    resp = await route_message(state, home_value)
    assert state.step == Step.MAIN_MENU


# --- Info questions mid-cart never get misfired as cart actions ------------

@pytest.mark.asyncio
async def test_info_question_in_cart_review_answers_via_rag_not_orchestrator():
    """Regression: "Incluye algún servicio de comida y bebida" inside
    MIXED_CART_REVIEW was being misclassified by the tool-calling orchestrator
    as add_to_cart(companion, 4), silently adding 4 bogus companions. Plain
    info questions must go straight to RAG and leave the cart untouched."""
    state = ConversationState(conversation_id="info-question-cart-test")
    await route_message(state, "hola")
    await route_message(state, "somos 4 que vamos a hacer snorkel")
    await route_message(state, "1")  # Cartagena -> MIXED_ADD_PREVIEW
    await route_message(state, "1")  # Añadir al carrito -> MIXED_CART_REVIEW
    assert state.step == Step.MIXED_CART_REVIEW
    assert len(state.mixed_cart) == 1

    rag_text = "Sí, incluye almuerzo y bebidas durante el tour."
    with patch(
        "src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value=rag_text
    ) as mock_rag:
        resp = await route_message(state, "Incluye algún servicio de comida y bebida")

    mock_rag.assert_called_once()
    assert resp == rag_text
    assert state.step == Step.MIXED_CART_REVIEW
    assert len(state.mixed_cart) == 1  # untouched — no bogus companion added
    assert [r["title"] for r in state.quick_replies] == [
        "✅ Continuar con la reserva",
        "🏠 Inicio",
    ]


@pytest.mark.asyncio
async def test_action_phrased_as_polite_request_still_reaches_orchestrator():
    """"Puedo añadir otro snorkel?" is a real cart action (polite phrasing,
    not an info question) — must NOT be hijacked into the RAG/info-question
    shortcut just because it ends with "?". The orchestrator must still get a
    chance to turn it into a real cart_action."""
    from src.agents import orchestrator, supervisor
    from src.agents.orchestrator import OrchestratorDecision

    state = await reach_mixed_add_activity()
    await route_message(state, "3")  # snorkel
    await route_message(state, "2")  # qty 2 -> preview
    await route_message(state, "1")  # Añadir al carrito -> MIXED_CART_REVIEW
    assert state.step == Step.MIXED_CART_REVIEW

    decision = OrchestratorDecision(tool=orchestrator.TOOL_CART_ACTION, args={"action": "add"})
    with patch.object(supervisor.orchestrator, "orchestrate", new=AsyncMock(return_value=decision)) as mock_orch:
        await route_message(state, "puedo añadir otro snorkel?")
    mock_orch.assert_called_once()
    assert state.step == Step.MIXED_ADD_ACTIVITY


# --- extra_context injects ground-truth includes/not_included --------------

@pytest.mark.asyncio
async def test_extra_context_includes_pending_preview_service_ground_truth():
    """Regression: "Tengo que llevar equipo?" asked from the un-confirmed
    preview card (before clicking "Añadir al carrito") had no service context
    at all, so RAG had to guess via vector search and sometimes fell back to
    "no tengo información suficiente". The preview's includes/not_included
    must be injected directly into extra_context."""
    from src.agents.supervisor import _build_extra_context

    state = await reach_mixed_add_activity()
    await route_message(state, "3")  # snorkel
    await route_message(state, "1")  # qty 1 -> preview
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert state.mixed_pending_preview_service_id == "snorkeling"

    context = _build_extra_context(state)
    assert "Tour de Snorkeling" in context
    assert "SI incluye" in context
    assert "Equipo de snorkeling" in context
    assert "Seguro de la actividad" in context
    assert "NO incluye" in context


@pytest.mark.asyncio
async def test_extra_context_includes_cart_item_ground_truth():
    """Same ground truth, but for an item already confirmed into the cart."""
    from src.agents.supervisor import _build_extra_context

    state = await reach_mixed_add_activity()
    await route_message(state, "3")  # snorkel
    await route_message(state, "1")  # qty 1 -> preview
    await route_message(state, "1")  # Añadir al carrito -> MIXED_CART_REVIEW
    assert state.step == Step.MIXED_CART_REVIEW

    context = _build_extra_context(state)
    assert "'Tour de Snorkeling' SI incluye" in context
    assert "Equipo de snorkeling" in context
    assert "'Tour de Snorkeling' NO incluye" in context


@pytest.mark.asyncio
async def test_extra_context_includes_group_size_detected_from_free_text():
    """A group size mentioned anywhere ("somos 4") must reach the LLM context
    so a later free-text question doesn't get asked "para cuantas personas?"
    again — regardless of which tree step the question comes from."""
    from src.agents.supervisor import _build_extra_context

    state = ConversationState(conversation_id="extra-context-group-size")
    await route_message(state, "hola")
    await route_message(state, "somos 4 que vamos a hacer snorkel")
    await route_message(state, "1")  # Cartagena -> MIXED_ADD_PREVIEW
    assert state.step == Step.MIXED_ADD_PREVIEW

    context = _build_extra_context(state)
    assert "4 persona" in context


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


@pytest.mark.asyncio
async def test_extra_context_includes_kids_and_private_boat_flags():
    from src.agents.supervisor import _build_extra_context

    state = await reach_mixed_add_activity()
    state.kids_under_8_count = 2
    state.kids_eight_to_ten_count = 1
    state.mixed_final_wants_private = True

    context = _build_extra_context(state)
    assert "2 menor(es) de 8" in context
    assert "1 de 8 a 10" in context
    assert "lancha privada" in context.lower()


# --- Qty handling ----------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_qty_appends_to_cart_and_goes_to_review():
    state = await reach_mixed_add_activity()
    await route_message(state, "2")  # beginner
    resp = await route_message(state, "3")  # qty 3 → kids question (inline)
    assert state.step == Step.MIXED_FINAL_KIDS
    assert state.mixed_cart == []
    resp = await route_message(state, "3")  # ten_plus → preview
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "añado a tu reserva" in resp.lower() or "add it to your booking" in resp.lower()
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
    resp = await route_message(state, "2")  # recent dive / no refresher needed
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert "añado a tu reserva" in resp.lower() or "add it to your booking" in resp.lower()
    await route_message(state, "1")  # add to cart
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["plan"] == "2_dives_1_day"
    assert state.mixed_cart[0]["qty"] == 2


# --- Cart review actions ---------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_cart_add_more_returns_to_add_activity():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # beginner, qty 3, kids ten_plus, preview add
    await route_message(state, "2")  # add another (cart-action 2)
    assert state.step == Step.MIXED_ADD_ACTIVITY


@pytest.mark.asyncio
async def test_mixed_cart_add_two_items_accumulates():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # 3 beginners (kids 10+)
    await send(state, "2", "1", "1", "2", "2", "1")  # add: cart-action 2, cert, 2-dives, qty 2, recent dive, preview add
    assert len(state.mixed_cart) == 2
    types = [it["type"] for it in state.mixed_cart]
    assert "beginner" in types and "cert" in types


@pytest.mark.asyncio
async def test_mixed_cart_modify_item_updates_qty():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # 3 beginners (kids 10+) → CART_REVIEW
    await route_message(state, "3")  # modify item (cart-action 3)
    assert state.step == Step.MIXED_CART_MODIFY_PICK
    await route_message(state, "1")  # pick item 1
    assert state.step == Step.MIXED_ADD_QTY
    await route_message(state, "5")  # new qty → kids re-asked inline
    assert state.step == Step.MIXED_FINAL_KIDS
    await route_message(state, "3")  # ten_plus → cart_review
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.mixed_cart[0]["qty"] == 5
    assert state.mixed_pending_modify_idx is None


@pytest.mark.asyncio
async def test_mixed_cart_remove_item_drops_it():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # add beginner x3 (kids 10+)
    await send(state, "2", "3", "2", "1")  # add (cart-action 2) snorkel x2
    assert len(state.mixed_cart) == 2
    await route_message(state, "4")  # remove item (cart-action 4)
    await route_message(state, "1")  # remove item #1 (beginner)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "snorkel"


@pytest.mark.asyncio
async def test_mixed_cart_restart_wipes_state():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # 3 beginners (kids 10+)
    state.mixed_final_is_colombian = True  # something to wipe
    await route_message(state, "5")  # restart (cart-action 5)
    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_cart == []
    assert state.mixed_final_is_colombian is None


@pytest.mark.asyncio
async def test_mixed_cart_confirm_advances_to_colombian():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # 3 beginners (kids 10+)
    await route_message(state, "6")  # confirmar carrito (cart-action 6)
    assert state.step == Step.MIXED_FINAL_COLOMBIAN


@pytest.mark.asyncio
async def test_mixed_cart_confirm_empty_does_not_advance():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # add then remove
    await send(state, "4", "1")  # remove (cart-action 4) item 1
    assert state.mixed_cart == []
    await route_message(state, "6")  # confirmar (cart-action 6)
    assert state.step != Step.MIXED_FINAL_COLOMBIAN


# --- Final questions -------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_final_kids_skipped_when_no_beginner():
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await route_message(state, "6")  # confirm cart (cart-action 6)
    await route_message(state, "2")  # not colombian → per-activity summary + link
    assert state.step == Step.FREE_TEXT
    assert state.mixed_final_has_kids_8_10 is None


@pytest.mark.asyncio
async def test_mixed_final_kids_asked_inline_when_adding_beginner():
    """Kids fires INLINE after qty when adding a Minicurso (not at checkout)."""
    state = await reach_mixed_add_activity()
    await route_message(state, "2")  # beginner
    await route_message(state, "3")  # qty 3 → kids inline
    assert state.step == Step.MIXED_FINAL_KIDS


@pytest.mark.asyncio
async def test_mixed_final_kids_not_asked_again_at_checkout():
    """Kids was answered inline; checkout no longer fires the kids step."""
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # 3 beginners, kids ten_plus inline
    await route_message(state, "6")  # confirm cart (cart-action 6)
    await route_message(state, "2")  # not colombian → per-activity summary + link
    assert state.step == Step.FREE_TEXT


@pytest.mark.asyncio
async def test_mixed_full_path_lands_on_per_activity_link():
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "3", "1")  # 3 beginners, kids 10+ inline
    await route_message(state, "6")  # confirm (cart-action 6)
    resp = await route_message(state, "2")  # not colombian → per-activity summary + link
    assert state.step == Step.FREE_TEXT
    assert "clic aquí" in resp.lower() or "click here" in resp.lower()
    assert "divingplanet.org" in resp


@pytest.mark.asyncio
async def test_final_summary_is_per_activity_with_link_no_bill():
    """New flow: the closing is one message per activity with its price + booking
    link — no combined 'restaurant bill' / total / payment buttons."""
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2, recent dive, preview add
    await send(state, "2", "3", "1", "1")  # add (cart-action 2) snorkel x1
    await send(state, "6", "2")  # confirm, not colombian
    assert state.step == Step.FREE_TEXT
    summary = state.mixed_last_summary or ""
    assert "clic aquí" in summary.lower() or "click here" in summary.lower()
    assert "divingplanet.org" in summary
    assert "ESTIMADO" not in summary and "TOTAL ESTIMADO" not in summary
    # both activities present in the per-activity messages
    assert "inmersiones" in summary.lower() or "buceo" in summary.lower()
    assert "snorkel" in summary.lower()


@pytest.mark.asyncio
async def test_final_summary_no_payment_buttons():
    """No cart/itinerary/payment buttons at the close — just the links."""
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "6", "2")  # confirm, not colombian
    assert state.step == Step.FREE_TEXT
    assert state.quick_replies == []


@pytest.mark.asyncio
async def test_final_large_group_still_gives_link():
    state = await reach_mixed_add_activity()
    await send(state, "3", "6+")
    await route_message(state, "8")  # 8 snorkelers
    await route_message(state, "1")  # preview add
    await send(state, "6", "2")  # confirm, not colombian
    summary = state.mixed_last_summary or ""
    assert "8 ×" in summary or "8 x" in summary.lower()
    assert "divingplanet.org" in summary


@pytest.mark.asyncio
async def test_final_kids_8_10_labeled_bubble_makers():
    """Kids 8-10 are split into their own activity message, labelled Bubble Makers."""
    state = await reach_mixed_add_activity()
    await send(state, "2", "3", "2", "2", "1")  # beginner qty3, kids 8-10 x2, preview add
    await send(state, "6", "2")  # confirm, not colombian
    assert state.step == Step.FREE_TEXT
    assert state.mixed_final_has_kids_8_10 is True
    summary = state.mixed_last_summary or ""
    assert "Bubble Makers" in summary


@pytest.mark.asyncio
async def test_private_boat_question_no_longer_asked():
    """#3: the proactive 'private boat?' question is removed — after nationality
    the flow closes with the per-activity links, no private line."""
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "6", "2")  # confirm, not colombian
    assert state.step == Step.FREE_TEXT
    assert state.mixed_final_wants_private is None
    summary = state.mixed_last_summary or ""
    assert "lancha privada" not in summary.lower()


@pytest.mark.asyncio
async def test_final_summary_colombian_shows_cop_and_link():
    state = await reach_mixed_add_activity()
    await send(state, "2", "2", "3", "1")  # 2 beginners, kids 10+ inline, preview add
    await send(state, "6", "1")  # COLOMBIAN
    summary = state.mixed_last_summary or ""
    assert "COP" in summary
    assert "divingplanet.org" in summary


@pytest.mark.asyncio
async def test_final_summary_cartagena_shows_includes_note():
    state = await reach_mixed_add_activity(location="cartagena")
    await send(state, "3", "2", "1")  # snorkel x2
    await send(state, "6", "2")  # confirm, not colombian
    summary = state.mixed_last_summary or ""
    assert "transporte" in summary.lower() or "transport" in summary.lower()


@pytest.mark.asyncio
async def test_final_summary_two_activities_are_separate_messages():
    """Two activities → two separate messages (joined with MESSAGE_SPLIT)."""
    from src.flows.decision_tree import MESSAGE_SPLIT
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2
    await send(state, "2", "3", "1", "1")  # add snorkel x1
    resp = await send(state, "6", "2")  # confirm, not colombian
    final = resp[-1]
    assert MESSAGE_SPLIT in final  # sent as two separate messages
    assert final.count("divingplanet.org") >= 2


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
async def test_final_summary_generic_link_uses_info_plus_whatsapp():
    """A plan without a direct book.divingplanet.org checkout (info-only page)
    must NOT promise 'book online' — it shows the info link + WhatsApp to book."""
    from src.flows.decision_tree import DecisionTree
    state = make_state()
    state.mixed_cart = [{"type": "cert", "qty": 2, "plan": "3_dives_1_day", "label": "3 dives"}]
    state.mixed_display_currency = "USD"
    resp = DecisionTree()._goto_mixed_final_summary(state)
    assert "divingplanet.org/tours" in resp          # generic info page
    assert "book.divingplanet.org" not in resp        # no fake checkout link
    assert "WhatsApp" in resp                          # booking channel offered
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


@pytest.mark.asyncio
async def test_final_summary_builds_lead_note_for_advisor():
    state = await reach_mixed_add_activity()
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2
    await send(state, "2", "2", "3", "3", "1")  # add beginner x3 (kids 10+ inline)
    await send(state, "6", "2")  # confirm, not colombian → per-activity links
    note = state.pending_note or ""
    assert "Grupo mixto" in note
    assert (
        "Buceo certificado" in note
        or "2 inmersiones" in note
        or "buzos certificados" in note.lower()
    )
    assert "Minicurso" in note or "principiantes" in note.lower() or "beginner" in note.lower()


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
async def test_bare_certified_statement_offers_diving_options(agent_decides):
    """#1: 'soy certificado' must offer the diving options (enter the certified
    flow), not a vague RAG reply — even when the conversation agent tags it as a
    plain question rather than a booking."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()  # WELCOME (an intent-trigger step)
    resp = await route_message(state, "soy certificado")
    assert state.step == Step.MIXED_LOCATION      # entered cert flow (asks origin)
    assert state.quick_replies                    # offers origin buttons
    assert "certificad" in resp.lower()


@pytest.mark.asyncio
async def test_bare_certified_question_still_answered_not_hijacked(agent_decides):
    """A certified diver ASKING something ('soy certificado, ¿tienen wifi?') must
    NOT be force-routed into the booking flow — the '?' guard keeps it a question."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    await route_message(state, "soy certificado, ¿qué precios manejan?")
    assert state.step != Step.MIXED_LOCATION


@pytest.mark.asyncio
async def test_booking_statement_with_unknown_certification_asks_certification(agent_decides):
    """Real bug (live PRE, 2026-07-17): a clear booking statement with group
    size + activity + duration, but WITHOUT stating certification ("queremos
    bucear 2 días" — never says "somos certificados"), must still enter the
    guided flow (ask certification) instead of falling to a RAG-generated
    recommendation that ends by offering an advisor. The existing fallback
    (_should_skip_to_certified_flow) only covers the case where certification
    IS already known to be true — this is the parallel case where it's
    unknown, which had no equivalent deterministic fallback."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    resp = await route_message(
        state,
        "Hola, somos 4, mi padre tiene la rodilla operada así que mejor evitar "
        "planes muy físicos. Queremos bucear 2 días",
    )
    assert state.step == Step.MIXED_ASK_CERTIFICATION
    assert "certificad" in resp.lower()
    assert "asesor" not in resp.lower()


@pytest.mark.asyncio
async def test_pure_companion_mention_routes_to_upsell(agent_decides):
    """#8: a free-text mention of a companion who only accompanies proactively
    offers them the mini-course/snorkel upsell (after asking the origin)."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    await route_message(state, "voy con mi novia que solo va a acompañar")
    assert state.step == Step.MIXED_LOCATION
    await route_message(state, "1")  # Cartagena → companion upsell
    assert state.step == Step.MIXED_COMPANION_UPSELL
    values = [b["value"] for b in state.quick_replies]
    assert values[:3] == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_companion_question_not_hijacked_to_upsell(agent_decides):
    """A QUESTION about companions stays a RAG question, not the upsell flow."""
    from src.agents import orchestrator
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
    state = make_state()
    await route_message(state, "¿el acompañante paga lo mismo?")
    assert state.step != Step.MIXED_LOCATION
    assert state.step != Step.MIXED_COMPANION_UPSELL


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
async def test_intent_classifier_restart_wipes_and_returns_to_entry(agent_decides):
    from src.agents import orchestrator
    # This exercises the legacy classify_menu_intent path, reached only when the
    # orchestrator defers (answer_question).
    agent_decides(orchestrator.TOOL_ANSWER_QUESTION)
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
async def test_kids_question_three_age_buttons_when_adding_beginner():
    """Picking minicurso + qty fires kids question with 3 age-range buttons (+ Varios)."""
    state = await _arrive_at_kids_inline(2)
    assert state.step == Step.MIXED_FINAL_KIDS
    titles_lower = [b["title"].lower() for b in state.quick_replies]
    assert any("menores de 8" in t for t in titles_lower)
    assert any("8 a 10" in t for t in titles_lower)
    assert any("10+" in t for t in titles_lower)


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
async def test_kids_under_8_with_dive_cart_shows_warning():
    """Range under_8 inline + dive cart → summary warns 'cannot dive, snorkel from 6'."""
    state = await _arrive_at_kids_inline(2)
    await route_message(state, "1")              # under_8 inline
    assert state.kids_age_group == "under_8"
    await route_message(state, "1")              # 1 kid under 8 → preview
    assert state.kids_count == 1
    await route_message(state, "1")              # preview confirm → cart_review
    # checkout (cart-action 6) → no colombian → no private → summary
    await send(state, "6", "2")
    summary = state.mixed_last_summary or ""
    assert "menores de 8" in summary.lower() or "under 8" in summary.lower()
    assert "no pueden bucear" in summary.lower() or "cannot dive" in summary.lower()


@pytest.mark.asyncio
async def test_kids_ten_plus_adds_no_warning():
    """Range 10+ inline → summary has no kids-related warning."""
    state = await _arrive_at_kids_inline(2)
    await route_message(state, "3")              # 10+ → preview
    assert state.kids_age_group == "ten_plus"
    assert state.mixed_final_has_kids_8_10 is False
    await route_message(state, "1")              # preview confirm
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    summary = state.mixed_last_summary or ""
    assert "menores de 8" not in summary.lower()
    assert "bubble makers" not in summary.lower()


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


@pytest.mark.asyncio
async def test_kids_re_asked_when_modifying_beginner_item():
    """Modify a beginner cart item → kids question re-fires inline after the new qty."""
    state = make_state()
    await _put_beginner_in_cart(state, 3)  # 3 beginners (kids 10+ default)
    # Simulate user had answered something different
    state.kids_age_group = "eight_to_ten"
    state.kids_eight_to_ten_count = 2
    state.mixed_final_has_kids_8_10 = True
    # Modify the beginner from qty 3 → 1
    await route_message(state, "3")  # modify pick (cart-action 3)
    await route_message(state, "1")  # pick item 1 (beginner)
    await route_message(state, "1")  # new qty = 1 → kids inline re-asked
    assert state.step == Step.MIXED_FINAL_KIDS
    # Previous kids answer was invalidated on modify
    assert state.kids_age_group is None
    assert state.mixed_final_has_kids_8_10 is None
    assert state.kids_eight_to_ten_count == 0


@pytest.mark.asyncio
async def test_kids_age_group_invalidated_on_beginner_remove():
    """Remove a beginner cart item → kids answer is cleared."""
    state = make_state()
    state.mixed_cart = [
        {"type": "cert", "qty": 2, "plan": "2_dives_1_day", "label": "Buceo certificado"},
        {"type": "beginner", "qty": 3, "plan": None, "label": "Minicurso"},
    ]
    state.location = "cartagena"
    state.mixed_entry_path = "diving_snorkel"
    state.step = Step.MIXED_CART_REVIEW
    state.kids_age_group = "under_8"
    state.mixed_final_has_kids_8_10 = False
    await route_message(state, "4")  # remove pick (cart-action 4)
    await route_message(state, "2")  # pick second visible (beginner)
    assert state.kids_age_group is None
    assert state.mixed_final_has_kids_8_10 is None
    # Cart now cert-only without kids mention → next checkout skips question
    await route_message(state, "6")  # checkout (cart-action 6)
    await route_message(state, "2")
    assert state.step != Step.MIXED_FINAL_KIDS


@pytest.mark.asyncio
async def test_kids_question_text_explains_each_range():
    """The kids question body lists each range so user can decide informed."""
    state = await _arrive_at_kids_inline(2)
    assert state.step == Step.MIXED_FINAL_KIDS
    # Re-render the kids question text to inspect content
    from src.flows.decision_tree import MESSAGES
    resp = MESSAGES["mixed_final_kids"]["es"]
    assert "Bubble Makers" in resp
    assert "menores de 8" in resp.lower() or "under 8" in resp.lower()
    assert "snorkel" in resp.lower()


@pytest.mark.asyncio
async def test_kids_under_8_or_8_10_asks_for_count_then_shows_sub_bullet():
    """After picking <8 or 8-10 inline, bot asks 'how many kids?' then shows sub-bullet in cart."""
    state = await _arrive_at_kids_inline(3)
    assert state.step == Step.MIXED_FINAL_KIDS
    await route_message(state, "2")              # 8-10
    assert state.step == Step.MIXED_FINAL_KIDS_QTY
    titles = [b["title"] for b in state.quick_replies]
    assert "1" in titles and "2" in titles and "3" in titles  # clipped to beginner qty=3
    assert "4" not in titles
    await route_message(state, "2")              # 2 kids in that range → preview
    assert state.kids_count == 2
    assert state.step == Step.MIXED_ADD_PREVIEW
    await route_message(state, "1")              # preview confirm → cart_review
    # Cart shows sub-bullet under beginner row
    from src.flows.decision_tree import DecisionTree
    cart = DecisionTree()._format_cart_lines(state, "es")
    assert "↳" in cart and "2 niños" in cart and "Bubble Makers" in cart


@pytest.mark.asyncio
async def test_kids_ten_plus_skips_qty_question():
    """Selecting 10+ does not trigger the count question — goes straight to preview."""
    state = await _arrive_at_kids_inline(3)
    await route_message(state, "3")              # 10+ → preview
    assert state.step != Step.MIXED_FINAL_KIDS_QTY
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert state.kids_count is None


@pytest.mark.asyncio
async def test_kids_qty_rejects_value_above_beginner_qty():
    """If beginner qty is 4, selecting 5 returns specific error."""
    state = await _arrive_at_kids_inline(4)
    await route_message(state, "1")              # under_8 → KIDS_QTY
    resp = await route_message(state, "5")
    assert state.step == Step.MIXED_FINAL_KIDS_QTY  # didn't advance
    assert "máximo" in resp.lower() or "at most" in resp.lower() or "between 1 and 4" in resp.lower()


@pytest.mark.asyncio
async def test_final_summary_shows_bubble_makers_split_rows():
    """RESERVA summary splits beginner row: adult Minicurso + Bubble Makers rows (no sub-bullet)."""
    state = await _arrive_at_kids_inline(3)
    await route_message(state, "2")              # 8-10
    await route_message(state, "2")              # 2 kids → preview
    await route_message(state, "1")              # preview confirm → cart_review
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    summary = state.mixed_last_summary or ""
    assert "Minicurso" in summary
    assert "Bubble Makers" in summary
    # Split rows are used — no ↳ sub-bullet in the final summary
    assert "↳" not in summary


@pytest.mark.asyncio
async def test_kids_eight_to_ten_keeps_bubble_makers_warning():
    """Range 8-10 inline still triggers the existing Bubble Makers warning."""
    state = await _arrive_at_kids_inline(2)
    await route_message(state, "2")              # 8-10 (Bubble Makers)
    assert state.kids_age_group == "eight_to_ten"
    assert state.mixed_final_has_kids_8_10 is True
    await route_message(state, "2")              # 2 kids in 8-10 → preview
    await route_message(state, "1")              # preview confirm
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    summary = state.mixed_last_summary or ""
    assert "bubble makers" in summary.lower()


# ────────────────────────────────────────────────────────────────────────
# Mixed-age ranges within a single beginner cart item (Varios rangos)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kids_mixed_button_appears_in_kids_step():
    """MIXED_FINAL_KIDS (inline) shows a 4th button 'Varios rangos' alongside the 3 ranges."""
    state = await _arrive_at_kids_inline(3)
    assert state.step == Step.MIXED_FINAL_KIDS
    titles_lower = [b["title"].lower() for b in state.quick_replies]
    assert any("menores de 8" in t for t in titles_lower)
    assert any("8 a 10" in t for t in titles_lower)
    assert any("10+" in t for t in titles_lower)
    assert any("varios rangos" in t or "mezcla" in t for t in titles_lower)


@pytest.mark.asyncio
async def test_kids_mixed_path_collects_two_counts():
    """Pick 'Varios rangos' inline → two count questions → state has both counters set."""
    state = await _arrive_at_kids_inline(5)
    assert state.step == Step.MIXED_FINAL_KIDS
    await route_message(state, "4")              # Varios rangos
    assert state.step == Step.MIXED_FINAL_KIDS_U8
    await route_message(state, "2")              # 2 menores de 8
    assert state.kids_under_8_count == 2
    assert state.step == Step.MIXED_FINAL_KIDS_810
    await route_message(state, "1")              # 1 entre 8-10 → preview
    assert state.kids_eight_to_ten_count == 1
    assert state.kids_age_group == "mixed"
    assert state.kids_count == 3
    assert state.mixed_final_has_kids_8_10 is True


@pytest.mark.asyncio
async def test_kids_mixed_summary_shows_three_split_rows():
    """RESERVA summary splits a mixed beginner row into adult + snorkel-kids + bubble-makers."""
    state = await _arrive_at_kids_inline(5)
    await route_message(state, "4")              # Varios rangos
    await route_message(state, "2")              # 2 menores de 8
    await route_message(state, "1")              # 1 entre 8-10 → preview
    await route_message(state, "1")              # preview confirm → cart_review
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    summary = state.mixed_last_summary or ""
    assert "Minicurso" in summary
    assert "Snorkel" in summary
    assert "menores de 8" in summary.lower() or "[menores de 8]" in summary
    assert "Bubble Makers" in summary
    # Adult portion = 2 (5 - 2 - 1) at minicurso, kids u8=2 at snorkel, e10=1 at minicurso.
    # New per-activity format: label on its own line, quantity on the price line.
    assert "[menores de 8]*" in summary   # snorkel block for u8 (qty 2)
    assert "[Bubble Makers]*" in summary  # bubble-makers block for e10 (qty 1)
    assert "2 ×" in summary               # adult minicurso qty 2 (qty-1 blocks say "por persona")


@pytest.mark.asyncio
async def test_kids_mixed_summary_shows_both_warnings():
    """Both 'under 8 cannot dive' and 'Bubble Makers' warnings appear together."""
    state = await _arrive_at_kids_inline(4)
    await route_message(state, "4")              # Varios rangos
    await route_message(state, "1")              # 1 menor de 8
    await route_message(state, "1")              # 1 entre 8-10 → preview
    await route_message(state, "1")              # preview confirm
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    summary = (state.mixed_last_summary or "").lower()
    assert "menores de 8" in summary
    assert "no pueden bucear" in summary
    assert "bubble makers" in summary


@pytest.mark.asyncio
async def test_kids_mixed_lead_note_lists_two_lines():
    """build_lead_summary emits separate lines for u8 and 8-10 when both present."""
    from src.agents.lead_summary import build_lead_summary
    state = await _arrive_at_kids_inline(4)
    await route_message(state, "4")              # Varios rangos
    await route_message(state, "2")              # 2 menores de 8
    await route_message(state, "1")              # 1 entre 8-10 → preview
    await route_message(state, "1")              # preview confirm
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    note = build_lead_summary(state)
    assert "2 menores de 8" in note
    assert "1 niños 8-10" in note or "1 niño 8-10" in note


@pytest.mark.asyncio
async def test_kids_mixed_both_zero_collapses_to_ten_plus():
    """If user picks 'Varios rangos' and answers 0 + 0, downgrades to ten_plus (no warnings)."""
    state = await _arrive_at_kids_inline(3)
    await route_message(state, "4")              # Varios rangos
    await route_message(state, "0")              # 0 menores de 8
    await route_message(state, "0")              # 0 entre 8-10 → preview
    assert state.kids_age_group == "ten_plus"
    assert state.kids_under_8_count == 0
    assert state.kids_eight_to_ten_count == 0
    assert state.kids_count is None
    await route_message(state, "1")              # preview confirm
    await send(state, "6", "2")             # checkout (cart-action 6), not colombian, no private
    summary = (state.mixed_last_summary or "").lower()
    assert "menores de 8" not in summary
    assert "bubble makers" not in summary


@pytest.mark.asyncio
async def test_kids_mixed_810_cap_respects_remaining():
    """KIDS_810 buttons are capped to beginner_qty - kids_under_8_count."""
    state = await _arrive_at_kids_inline(5)
    await route_message(state, "4")              # Varios rangos
    await route_message(state, "3")              # 3 menores de 8 → remaining = 2
    assert state.step == Step.MIXED_FINAL_KIDS_810
    button_values = [int(b["value"]) for b in state.quick_replies if b["value"].isdigit()]
    assert max(button_values) == 2  # cap = 5 - 3 = 2


@pytest.mark.asyncio
async def test_kids_single_range_path_unchanged():
    """The single-range branch still sets the per-range counter (legacy path intact)."""
    state = await _arrive_at_kids_inline(3)
    await route_message(state, "1")              # menores de 8 (single)
    await route_message(state, "2")              # 2 niños → preview
    assert state.kids_under_8_count == 2
    assert state.kids_eight_to_ten_count == 0
    assert state.kids_age_group == "under_8"
    assert state.kids_count == 2


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


@pytest.mark.asyncio
async def test_kids_qty_single_range_shows_6plus_for_large_group():
    """When beginner qty > 9, KIDS_QTY buttons show 1..5 + '6+' instead of clipping at 9."""
    state = await _arrive_at_kids_inline_large(20)
    assert state.step == Step.MIXED_FINAL_KIDS
    await route_message(state, "1")              # under_8 → KIDS_QTY
    assert state.step == Step.MIXED_FINAL_KIDS_QTY
    values = [b["value"] for b in state.quick_replies]
    assert "6+" in values
    # Numeric buttons stop at 5 (the rest is via exact input)
    numeric = [int(v) for v in values if v.isdigit()]
    assert max(numeric) == 5


@pytest.mark.asyncio
async def test_kids_qty_single_range_accepts_exact_above_9_for_large_group():
    """For beginner qty=20, user can pick '6+' then type '12' as kids under 8."""
    state = await _arrive_at_kids_inline_large(20)
    await route_message(state, "1")              # under_8 → KIDS_QTY
    resp = await route_message(state, "6+")      # ask exact
    assert state.mixed_pending_exact is True
    assert "6 o más" in resp or "6 or more" in resp
    await route_message(state, "12")             # type 12 → preview
    assert state.kids_count == 12
    assert state.kids_under_8_count == 12
    assert state.mixed_pending_exact is False
    assert state.step == Step.MIXED_ADD_PREVIEW


@pytest.mark.asyncio
async def test_kids_qty_single_range_rejects_above_cap():
    """For beginner qty=20, typing 25 is rejected."""
    state = await _arrive_at_kids_inline_large(20)
    await route_message(state, "1")              # under_8 → KIDS_QTY
    await route_message(state, "6+")             # ask exact
    resp = await route_message(state, "25")      # over cap
    assert state.step == Step.MIXED_FINAL_KIDS_QTY  # still here
    assert "20" in resp  # error message mentions the cap


@pytest.mark.asyncio
async def test_kids_u8_shows_6plus_for_large_group():
    """For beginner qty=20, KIDS_U8 buttons cap at 5 + '6+'."""
    state = await _arrive_at_kids_inline_large(20)
    await route_message(state, "4")              # Varios rangos → KIDS_U8
    assert state.step == Step.MIXED_FINAL_KIDS_U8
    values = [b["value"] for b in state.quick_replies]
    assert "6+" in values
    numeric = [int(v) for v in values if v.isdigit()]
    assert max(numeric) == 5
    assert 0 in numeric  # Ninguno button still present


@pytest.mark.asyncio
async def test_kids_u8_and_810_accept_typed_numbers_for_large_group():
    """For beginner qty=20, Varios → 6+ → type 10 → 6+ → type 5 captures 10 + 5."""
    state = await _arrive_at_kids_inline_large(20)
    await route_message(state, "4")              # Varios → KIDS_U8
    await route_message(state, "6+")             # exact prompt
    await route_message(state, "10")             # u8 = 10 → KIDS_810
    assert state.kids_under_8_count == 10
    assert state.step == Step.MIXED_FINAL_KIDS_810
    # Remaining cap = 20 - 10 = 10, still > 8 so 6+ button is shown
    values = [b["value"] for b in state.quick_replies]
    assert "6+" in values
    await route_message(state, "6+")
    await route_message(state, "5")              # e10 = 5
    assert state.kids_eight_to_ten_count == 5
    assert state.kids_age_group == "mixed"
    assert state.kids_count == 15
    assert state.step == Step.MIXED_ADD_PREVIEW


# ────────────────────────────────────────────────────────────────────────
# Cambiar origen desde el carrito
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cart_change_location_action_appears_in_cart_review():
    """mixed_cart_actions includes a 'Cambiar origen' option."""
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")             # snorkel x2 → CART_REVIEW
    titles = [b["title"].lower() for b in state.quick_replies]
    assert any("cambiar origen" in t or "change origin" in t for t in titles)


@pytest.mark.asyncio
async def test_cart_change_location_cartagena_to_island_remaps_prices():
    """Changing from Cartagena to Islas asks for the hotel (unknown yet, needed
    for pickup) before swapping service IDs and updating summary prices."""
    state = await reach_mixed_add_activity(location="cartagena")
    await send(state, "1", "1", "2", "2", "1")   # cert 2-dives x2 (Cartagena)
    assert state.location == "cartagena"
    await route_message(state, "1")              # Cambiar origen (cart-action 1)
    assert state.step == Step.MIXED_CART_LOCATION
    await route_message(state, "2")              # Ya estoy en las islas
    assert state.location == "island"
    assert state.step == Step.ISLAND_MENU         # hotel unknown -> ask island/hotel first
    await route_message(state, "1")               # Isla Grande
    assert state.step == Step.ISLAND_HOTEL_MENU
    resp = await route_message(state, "1")         # first hotel
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.hotel == "San Pedro de Majagua"
    assert "actualizado" in resp.lower() or "updated" in resp.lower()
    # Cart item's plan should have been remapped to the island variant.
    from src.flows.decision_tree import DecisionTree, SERVICES
    dt = DecisionTree()
    cert_item = next(it for it in state.mixed_cart if it["type"] == "cert")
    assert cert_item["plan"] == "2_dives_1_day_already_on_island"
    svc_id = dt._cart_service_id("cert", cert_item["plan"], state)
    assert svc_id == "2_dives_1_day_already_on_island"
    cartagena_price = SERVICES["2_dives_1_day"]["price_usd"]
    island_price = SERVICES["2_dives_1_day_already_on_island"]["price_usd"]
    assert island_price < cartagena_price


@pytest.mark.asyncio
async def test_orchestrator_set_location_to_island_asks_hotel_before_remapping():
    """Same regression via free text mid-cart ("estoy en las islas") routed
    through the tool-calling orchestrator, not the Cambiar-origen button."""
    from src.agents import orchestrator, supervisor
    from src.agents.orchestrator import OrchestratorDecision

    state = await reach_mixed_add_activity(location="cartagena")
    await send(state, "1", "1", "2", "2", "1")  # cert 2-dives x2 (Cartagena)
    assert state.step == Step.MIXED_CART_REVIEW

    decision = OrchestratorDecision(tool=orchestrator.TOOL_SET_LOCATION, args={"origin": "island"})
    with patch.object(supervisor.orchestrator, "orchestrate", new=AsyncMock(return_value=decision)):
        await route_message(state, "estoy en las islas")
    assert state.step == Step.ISLAND_MENU
    assert state.location == "island"

    await route_message(state, "1")   # Isla Grande
    assert state.step == Step.ISLAND_HOTEL_MENU
    resp = await route_message(state, "1")  # first hotel
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.hotel == "San Pedro de Majagua"
    cert_item = next(it for it in state.mixed_cart if it["type"] == "cert")
    assert cert_item["plan"] == "2_dives_1_day_already_on_island"


@pytest.mark.asyncio
async def test_cart_change_location_same_value_is_noop():
    """Picking the same origin shows a 'no changes' ack and stays at cart_review."""
    state = await reach_mixed_add_activity(location="cartagena")
    await send(state, "3", "2", "1")             # snorkel x2
    await route_message(state, "1")              # Cambiar origen (cart-action 1)
    resp = await route_message(state, "1")       # Cartagena (same)
    assert state.location == "cartagena"
    assert state.step == Step.MIXED_CART_REVIEW
    assert "sin cambios" in resp.lower() or "no changes" in resp.lower()


@pytest.mark.asyncio
async def test_cart_change_location_back_returns_to_cart_review_unchanged():
    """Pressing 'Volver' from the location prompt returns without changing state."""
    state = await reach_mixed_add_activity(location="cartagena")
    await send(state, "3", "2", "1")             # snorkel x2
    await route_message(state, "1")              # Cambiar origen (cart-action 1)
    assert state.step == Step.MIXED_CART_LOCATION
    resp = await route_message(state, "back")
    assert state.step == Step.MIXED_CART_REVIEW
    assert state.location == "cartagena"
    # Cart contents must still be visible after back (regression for bug
    # where supervisor's intent=back wiped the cart view, only showing prompt).
    assert "carrito" in resp.lower() or "cart" in resp.lower()
    assert "snorkel" in resp.lower() or "tour de snorkel" in resp.lower()


@pytest.mark.asyncio
async def test_cart_remove_pick_back_keeps_cart_visible():
    """Cancel from the 'pick item to remove' prompt returns to cart with cart_lines visible."""
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")             # snorkel x2
    await route_message(state, "4")              # Quitar item (cart-action 4) → REMOVE_PICK
    assert state.step == Step.MIXED_CART_REMOVE_PICK
    resp = await route_message(state, "back")
    assert state.step == Step.MIXED_CART_REVIEW
    # Regression: cart must still be rendered (not just the prompt).
    assert "carrito" in resp.lower() or "cart" in resp.lower()
    assert "snorkel" in resp.lower() or "tour de snorkel" in resp.lower()


@pytest.mark.asyncio
async def test_cart_modify_pick_back_keeps_cart_visible():
    """Cancel from the 'pick item to modify' prompt returns to cart with cart_lines visible."""
    state = await reach_mixed_add_activity()
    await send(state, "3", "2", "1")             # snorkel x2
    await route_message(state, "3")              # Modificar item (cart-action 3) → MODIFY_PICK
    assert state.step == Step.MIXED_CART_MODIFY_PICK
    resp = await route_message(state, "back")
    assert state.step == Step.MIXED_CART_REVIEW
    assert "carrito" in resp.lower() or "cart" in resp.lower()
    assert "snorkel" in resp.lower() or "tour de snorkel" in resp.lower()


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
    resp = await route_message(state, "Hola quiero hacer el minicurso de buceo, es mi primera vez")
    
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
    resp = await route_message(state, "Hola quiero hacer el curso PADI Open Water")
    
    # Should detect Spanish and PADI course intent
    assert state.detected_activity == "padi_open_water"
    assert state.detected_service_id == "open_water"


@pytest.mark.asyncio
async def test_intent_specialty_detection():
    """'Quiero hacer el curso de nitrox' should detect specialty."""
    state = make_state()
    resp = await route_message(state, "Hola quiero hacer el curso de nitrox")
    
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
async def test_intent_does_not_trigger_on_digit_input():
    """Intent detection should not run on digit inputs (menu selections)."""
    state = await reach_main_menu()
    
    # Clear any previous detections
    state.detected_activity = None
    
    # Send digit (menu choice)
    await route_message(state, "1")
    
    # Should not have triggered intent detection
    assert state.detected_activity is None


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

@pytest.mark.asyncio
async def test_refresher_split_adds_full_cert_group_with_correct_plan():
    """Regression: 3 people book 5 inmersiones, 2 want refresher.
    Split review must show the right plan; final cart must have 3 × 5_dives_2_days
    (not only 1 person) with the refresh sub-item for 2 people.
    """
    state = make_state()
    state.location = "cartagena"
    state.mixed_entry_path = "booking"

    # Drive state to MIXED_ADD_CERT_MULTI_DAY manually then select 5 dives
    state.step = Step.MIXED_ADD_CERT_PLAN
    state.mixed_pending_qty_type = "cert"
    await route_message(state, "2")         # multi-day option
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY

    # Choose "5 inmersiones (2 días)" — option index 3 in the Cartagena map
    await route_message(state, "3")
    assert state.mixed_pending_qty_plan == "5_dives_2_days"

    # Qty
    await route_message(state, "3")         # 3 people → MIXED_CERT_LAST_DIVE

    # Last dive > 2 years → yes
    await route_message(state, "1")         # Sí → MIXED_CERT_REFRESH_INTEREST

    # Wants refresher → yes
    await route_message(state, "1")         # Sí → MIXED_CERT_REFRESH_QTY

    # 2 of 3 want refresher → split scenario
    resp = await route_message(state, "2")
    assert state.step == Step.MIXED_CERT_SPLIT_REVIEW

    # Split review must mention the correct plan and not show any previous cert
    assert "5" in resp, f"Plan missing from split review: {resp!r}"
    assert "Paquete de 4" not in resp, f"Wrong plan in split review: {resp!r}"
    # And show both group sizes clearly
    assert "2" in resp and "1" in resp

    # Continue → preview for ALL 3 people with correct plan
    resp = await route_message(state, "1")
    assert state.step == Step.MIXED_ADD_PREVIEW
    assert state.mixed_pending_qty_value == 3, "Preview must cover full group (3 people)"
    assert state.mixed_pending_qty_plan == "5_dives_2_days"

    # Confirm → add to cart
    await route_message(state, "1")
    assert state.step == Step.MIXED_CART_REVIEW

    cert_items = [it for it in state.mixed_cart if it.get("type") == "cert"]
    refresh_items = [it for it in state.mixed_cart if it.get("type") == "refresh"]

    # Exactly one cert line for all 3 people with the correct plan
    assert len(cert_items) == 1, f"Expected 1 cert item, got {cert_items}"
    assert cert_items[0]["plan"] == "5_dives_2_days", f"Wrong plan: {cert_items[0]}"
    assert cert_items[0]["qty"] == 3, f"Wrong qty: {cert_items[0]}"

    # Refresh sub-item for exactly 2 people
    assert len(refresh_items) == 1, f"Expected 1 refresh item, got {refresh_items}"
    assert refresh_items[0]["qty"] == 2, f"Wrong refresh qty: {refresh_items[0]}"
    # Refresh plan must match the cert so _format_cart_lines attaches it correctly
    assert refresh_items[0]["plan"] == "5_dives_2_days", f"Wrong refresh plan: {refresh_items[0]}"


@pytest.mark.asyncio
async def test_refresher_attaches_to_correct_cert_when_cart_has_multiple_certs():
    """Regression: previous cert item in cart must NOT steal the refresh sub-bullet.

    Flow: add 7 inmersiones (no refresher), then add 2 inmersiones for 3 people
    with 1 wanting refresher.  The final cart display must show the refresh under
    the '2 inmersiones' line, not under '7 inmersiones'.
    """
    state = make_state()
    state.location = "cartagena"
    state.mixed_entry_path = "booking"

    # 1. Add 7 inmersiones × 3, no refresher
    await _put_cert_in_cart(state, qty=3)   # 2_dives_1_day × 3, no refresh — used as first cert
    # Swap the plan to simulate 7_dives_3_days already in cart
    state.mixed_cart[0]["plan"] = "7_dives_3_days"
    state.mixed_cart[0]["label"] = "Paquete de 7 inmersiones (3 dias)"

    assert state.step == Step.MIXED_CART_REVIEW

    # 2. Add another cert (2 inmersiones / 1 día) for 3 people, 1 wants refresher
    await route_message(state, "2")          # "Añadir otra actividad"
    await route_message(state, "1")          # Buceo certificado → MIXED_ADD_CERT_PLAN
    await route_message(state, "1")          # 2 inmersiones / 1 día → MIXED_ADD_QTY
    await route_message(state, "3")          # 3 people → MIXED_CERT_LAST_DIVE
    await route_message(state, "1")          # last dive > 2 years → MIXED_CERT_REFRESH_INTEREST
    await route_message(state, "1")          # yes refresher → MIXED_CERT_REFRESH_QTY
    resp = await route_message(state, "1")   # 1 person with refresher → MIXED_CERT_SPLIT_REVIEW
    assert state.step == Step.MIXED_CERT_SPLIT_REVIEW

    # Split review shows 1 with refresh, 2 without — for '2 inmersiones', NOT '7 inmersiones'
    assert "7" not in resp.split("Resumen")[1] if "Resumen" in resp else True
    assert "2 inmersiones" in resp or "Salidas" in resp or "2" in resp

    # Confirm → add all 3 cert people
    await route_message(state, "1")          # Continuar con el buceo → MIXED_ADD_PREVIEW
    await route_message(state, "1")          # Añadir al carrito → MIXED_CART_REVIEW

    cert_items = [it for it in state.mixed_cart if it.get("type") == "cert"]
    refresh_items = [it for it in state.mixed_cart if it.get("type") == "refresh"]

    # Two cert items: 7 inmersiones and 2 inmersiones (merged 2+3=5 or separate)
    cert_plans = [it["plan"] for it in cert_items]
    assert "7_dives_3_days" in cert_plans, f"7-dive cert missing: {cert_items}"
    assert any("2_dives" in p for p in cert_plans), f"2-dive cert missing: {cert_items}"

    # Refresh must be for the 2-dives cert, not the 7-dives one
    assert len(refresh_items) == 1
    assert refresh_items[0]["qty"] == 1
    assert "7_dives" not in (refresh_items[0].get("plan") or ""), (
        f"Refresh wrongly linked to 7-dives cert: {refresh_items[0]}"
    )

    # Cart display: refresh sub-bullet must appear under 2-inmersiones line, not 7
    from src.flows.decision_tree import DecisionTree
    dt = DecisionTree()
    cart_text = dt._format_cart_lines(state, "es")
    lines = cart_text.split("\n")
    seven_idx = next((i for i, l in enumerate(lines) if "7 inmersiones" in l), -1)
    two_idx = next((i for i, l in enumerate(lines) if "2 inmersiones" in l or "Salidas" in l), -1)
    refresh_idx = next((i for i, l in enumerate(lines) if "refresher" in l), -1)
    assert refresh_idx != -1, "Refresh sub-bullet missing from cart"
    assert refresh_idx > two_idx, "Refresh sub-bullet must come after the 2-dive cert line"
    if seven_idx != -1 and two_idx != -1:
        assert seven_idx < two_idx, "7-dive cert should appear before 2-dive cert"
        assert refresh_idx > seven_idx + 1 or two_idx < refresh_idx, (
            "Refresh must NOT be immediately under the 7-dive cert"
        )


# ===========================================================================
# BLOQUE — TYPO TOLERANCE: cantidad con typo en MIXED_ADD_QTY
# Regression test for the bug where "somos cuatr personas" (typo of "cuatro")
# was routed to the LLM orchestrator instead of the tree handler, causing
# the bot to re-show the cert plan selection instead of accepting the quantity.
# ===========================================================================

@pytest.mark.asyncio
async def test_qty_phrase_with_word_typo_advances_past_qty_step():
    """'somos cuatr personas' must be parsed as 4 at MIXED_ADD_QTY."""
    state = await reach_booking_cart(location="cartagena")
    # Select certified diving
    await route_message(state, "1")
    assert state.step == Step.MIXED_ADD_CERT_PLAN
    # Select 2 dives / 1 day
    await route_message(state, "1")
    # Bot should now be at qty step or skipped to last-dive if group_size was pre-filled
    # Either way, if it lands at MIXED_ADD_QTY, send the typo phrase
    if state.step == Step.MIXED_ADD_QTY:
        resp = await route_message(state, "somos cuatr personas")
        # Must NOT be re-showing the cert plan — must have advanced
        assert "qué idea tienes" not in resp, (
            "Bot re-showed cert plan selection: quantity was not parsed from typo phrase"
        )
        assert state.step != Step.MIXED_ADD_CERT_PLAN, (
            "Step regressed to MIXED_ADD_CERT_PLAN: quantity routing bug"
        )
        assert state.step != Step.MIXED_ADD_QTY, (
            "Step stayed at MIXED_ADD_QTY: quantity was not parsed"
        )


@pytest.mark.asyncio
async def test_qty_phrase_exact_word_in_phrase_advances_past_qty_step():
    """'somos cuatro personas' (exact word) must also work."""
    state = await reach_booking_cart(location="cartagena")
    await route_message(state, "1")
    assert state.step == Step.MIXED_ADD_CERT_PLAN
    await route_message(state, "1")
    if state.step == Step.MIXED_ADD_QTY:
        resp = await route_message(state, "somos cuatro personas")
        assert "qué idea tienes" not in resp
        assert state.step != Step.MIXED_ADD_CERT_PLAN
        assert state.step != Step.MIXED_ADD_QTY


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
    resp = await route_message(state, "cancelar la reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_quisiera_variant_es():
    """'quisiera cancelar mi reserva' también activa la detección."""
    state = make_state()
    resp = await route_message(state, "quisiera cancelar mi reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_anular_variant_es():
    """'anular mi reserva' debe activar el detector."""
    state = make_state()
    resp = await route_message(state, "anular mi reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_booking_accent_insensitive_es():
    """Con tildes ('cancelar mi reservación') también debe detectarse."""
    state = make_state()
    resp = await route_message(state, "necesito cancelar mi reservación")
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
    resp = await route_message(state, "how do i cancel my booking")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_advisor_button_escalates():
    """After the cancel-info response, clicking 'asesor' escalates correctly."""
    state = make_state()
    await route_message(state, "quiero cancelar mi reserva")
    resp = await route_message(state, "asesor")
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
    resp = await route_message(state, "quisiera cambiar la fecha")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_reschedule_reprogramar_variant_es():
    """'reprogramar mi reserva' activa la detección."""
    state = make_state()
    resp = await route_message(state, "reprogramar mi reserva")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_reschedule_explicit_en_shows_policy_and_buttons():
    """'reschedule my booking' → reschedule policy text + advisor/home buttons (EN)."""
    state = make_state(lang="en")
    resp = await route_message(state, "reschedule my booking")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values
    assert "inicio" in button_values


@pytest.mark.asyncio
async def test_reschedule_i_would_like_to_reschedule_en():
    """'i'd like to reschedule' triggers detection (EN)."""
    state = make_state(lang="en")
    resp = await route_message(state, "i'd like to reschedule my booking")
    button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" in button_values


@pytest.mark.asyncio
async def test_cancel_does_not_trigger_mid_booking_navigation():
    """The word 'cancelar' typed during navigation (e.g. as back) must NOT be
    confused with cancelling an existing booking when no other cancel-booking
    phrase is present."""
    state = await reach_booking_cart(location="cartagena")
    # At MIXED_ADD_ACTIVITY, typing "cancelar" alone = back navigation, not booking-cancel
    await route_message(state, "cancelar")
    # Should have navigated back, NOT shown cancellation policy buttons
    cancel_button_values = [b["value"] for b in state.quick_replies]
    assert "asesor" not in cancel_button_values or state.step in (
        Step.MIXED_ENTRY, Step.MAIN_MENU, Step.MIXED_ADD_ACTIVITY
    )




# --- Bare affirmation after the bot offered advisor contact ------------------


@pytest.mark.asyncio
async def test_bare_si_after_advisor_offer_escalates():
    """Real PRE bug (2026-07-07): bot offered "puedo pasarte el contacto de un
    asesor... te gustaria?", customer replied "si", and the bot fell to the
    generic RAG fallback instead of fulfilling its own offer."""
    state = ConversationState(conversation_id="si-offer-1")
    state.step = Step.MAIN_MENU
    state.language = "es"
    state.history = [
        {"role": "user", "content": "quiero ser rescue diver"},
        {"role": "assistant", "content": "Si quieres, puedo pasarte el contacto de un asesor. ¿Te gustaria eso?"},
    ]
    response = await route_message(state, "si")
    assert state.step == Step.ESCALATE
    assert "asesor" in response.lower()


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
# list of "critical steps", assuming the handler can parse free text. True for
# MIXED_LOCATION/MIXED_ADD_QTY/MIXED_CERT_REFRESH_QTY (they have real free-text
# parsing), but MIXED_CERT_LAST_DIVE and MIXED_CERT_REFRESH_INTEREST are pure
# yes/no button steps with no fallback — any genuine question got silently
# swallowed into "no entendí", blocking the conversation entirely (and, as a
# side effect, never reaching RAG/_build_extra_context where Fase B's rolling
# summary would apply).

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


@pytest.mark.asyncio
async def test_question_at_last_dive_step_reaches_rag_not_stuck():
    state = await _reach_mixed_cert_last_dive()
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        resp = await route_message(state, "¿Hay descuento por grupo?")
    assert resp == "CANNED_RAG_ANSWER"
    assert state.step == Step.MIXED_CERT_LAST_DIVE, "must not lose the pending yes/no question"


@pytest.mark.asyncio
async def test_question_at_refresh_interest_step_reaches_rag_not_stuck():
    state = await _reach_mixed_cert_last_dive()
    await route_message(state, "1")  # "sí, más de 2 años" -> MIXED_CERT_REFRESH_INTEREST
    assert state.step == Step.MIXED_CERT_REFRESH_INTEREST
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        resp = await route_message(state, "¿Y si llueve ese día?")
    assert resp == "CANNED_RAG_ANSWER"


@pytest.mark.asyncio
async def test_button_answer_at_last_dive_step_still_advances():
    """The fix must not break the normal button-driven path."""
    state = await _reach_mixed_cert_last_dive()
    await route_message(state, "2")  # "no, menos de 2 años"
    assert state.step != Step.MIXED_CERT_LAST_DIVE
