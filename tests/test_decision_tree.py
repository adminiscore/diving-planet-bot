"""
Tests for the predefined decision tree flow.

Simulates common customer journeys to verify the bot
responds correctly at each step.
"""

from src.flows.decision_tree import DecisionTree, ConversationState, Step


def make_state(conversation_id: str = "test-001") -> ConversationState:
    return ConversationState(conversation_id=conversation_id)


class TestLanguageSelection:
    def setup_method(self):
        self.tree = DecisionTree()

    def test_welcome_message(self):
        state = make_state()
        response = self.tree.process_message(state, "hola")
        assert "Diving Planet" in response
        assert state.step == Step.LANGUAGE

    def test_select_spanish(self):
        state = make_state()
        state.step = Step.LANGUAGE
        response = self.tree.process_message(state, "1")
        assert state.language == "es"
        assert state.step == Step.MAIN_MENU

    def test_select_english(self):
        state = make_state()
        state.step = Step.LANGUAGE
        response = self.tree.process_message(state, "2")
        assert state.language == "en"
        assert state.step == Step.MAIN_MENU

    def test_detect_english_text(self):
        state = make_state()
        state.step = Step.LANGUAGE
        response = self.tree.process_message(state, "hello")
        assert state.language == "en"

    def test_detect_spanish_text(self):
        state = make_state()
        state.step = Step.LANGUAGE
        response = self.tree.process_message(state, "hola")
        assert state.language == "es"

    def test_spanish_phrase_with_en_substring_is_not_detected_as_english(self):
        state = make_state()
        state.step = Step.LANGUAGE
        response = self.tree.process_message(state, "en español")
        assert state.language == "es"
        assert state.step == Step.MAIN_MENU


class TestMainMenu:
    def setup_method(self):
        self.tree = DecisionTree()

    def _go_to_menu(self, lang: str = "es") -> ConversationState:
        state = make_state()
        state.step = Step.MAIN_MENU
        state.language = lang
        return state

    def test_select_reservar(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "1")
        assert state.step == Step.RESERVA_MENU
        assert "reservar" in response.lower() or "book" in response.lower()

    def test_select_info(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "2")
        assert state.step == Step.INFO_MENU
        assert "información" in response.lower() or "information" in response.lower()

    def test_select_courses_via_reservar(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")  # Reservar
        response = self.tree.process_message(state, "2")  # Cursos PADI
        assert state.step == Step.COURSES_MENU
        assert "PADI" in response

    def test_courses_menu_quick_replies_use_new_titles_in_spanish(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")

        assert [item["title"] for item in state.quick_replies[:3]] == [
            "🐠 Descubriendo el buceo (Open Water Diver)",
            "🚀 Convierte en pro (Advanced / Rescue / Dive Master)",
            "✨ Amplía tus habilidades (Especialidades PADI)",
        ]

    def test_courses_menu_quick_replies_use_new_titles_in_english(self):
        state = self._go_to_menu("en")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")

        assert [item["title"] for item in state.quick_replies[:3]] == [
            "🐠 Discover diving (Open Water Diver)",
            "🚀 Go pro (Advanced / Rescue / Divemaster)",
            "✨ Expand your skills (PADI Specialties)",
        ]

    def test_go_pro_submenu_shows_only_advanced_rescue_and_divemaster_in_spanish(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "2")

        assert state.step == Step.COURSES_ADVANCED_MENU
        assert "avanzados" in response.lower()
        assert [item["title"] for item in state.quick_replies[:3]] == [
            "📘 Curso Avanzado",
            "🚑 Rescate + EFR",
            "🏅 Dive Master",
        ]

    def test_go_pro_submenu_shows_only_advanced_rescue_and_divemaster_in_english(self):
        state = self._go_to_menu("en")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "2")

        assert state.step == Step.COURSES_ADVANCED_MENU
        assert "advanced and professional" in response.lower()
        assert [item["title"] for item in state.quick_replies[:3]] == [
            "📘 Advanced Course",
            "🚑 Rescue + EFR",
            "🏅 Divemaster",
        ]

    def test_specialties_submenu_shows_only_specialties_in_spanish(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "3")

        assert state.step == Step.COURSES_SPECIALTIES_MENU
        assert "especialidades" in response.lower()
        assert [item["title"] for item in state.quick_replies[:5]] == [
            "✨ Mindful Diving",
            "🐠 Identificación de peces",
            "🌿 Naturalista",
            "⚖️ Flotabilidad",
            "🫧 Nitrox",
        ]

    def test_specialties_submenu_shows_only_specialties_in_english(self):
        state = self._go_to_menu("en")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "3")

        assert state.step == Step.COURSES_SPECIALTIES_MENU
        assert "specialties" in response.lower()
        assert [item["title"] for item in state.quick_replies[:5]] == [
            "✨ Mindful Diving",
            "🐠 Fish Identification",
            "🌿 Naturalist",
            "⚖️ Buoyancy",
            "🫧 Nitrox",
        ]

    def test_human_via_keyword(self):
        """Asesor ya no es opción del menú; se escala vía keyword."""
        state = self._go_to_menu()
        # Vía decision tree solo (sin supervisor), tecla numérica desconocida → not understood
        response = self.tree.process_message(state, "9")
        assert "No entendi" in response or "not understand" in response.lower()

    def test_invalid_option(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "99")
        assert "No entendi" in response or "not understand" in response.lower()


class TestCertifiedDiverFlow:
    def setup_method(self):
        self.tree = DecisionTree()

    def _go_to_certified(self) -> ConversationState:
        state = make_state()
        state.step = Step.TOURS_CERTIFIED
        state.language = "es"
        state.is_certified = True
        # location seteada programáticamente para tests del flujo histórico
        # (en producción se difiere al SUMMARY via botones).
        state.location = "cartagena"
        return state

    def test_select_2_dives(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "1")
        assert state.selected_service == "2_dives_1_day"
        assert state.step == Step.CERTIFIED_LAST_DIVE
        assert "2 años" in response

    def test_select_3_dives_cartagena(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "2")
        assert state.selected_service == "3_dives_1_day"
        assert state.step == Step.CERTIFIED_LAST_DIVE
        assert "2 años" in response

    def test_certified_menu_mentions_lodging_requirement(self):
        state = make_state()
        state.step = Step.TOURS_EXPERIENCE
        state.language = "es"
        state.location = "cartagena"

        response = self.tree.process_message(state, "1")

        assert state.step == Step.TOURS_CERTIFIED
        assert "hospedarte en un hotel en las islas" in response.lower()
        assert "3 inmersiones (1 día)" in response

    def test_3_dives_summary_mentions_night_stay_requirement(self):
        state = self._go_to_certified()
        state.location = "cartagena"

        self.tree.process_message(state, "2")
        self.tree.process_message(state, "2")
        summary = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "hospedaje requerido" in summary.lower()
        assert "inmersión nocturna" in summary.lower()

    def test_3_dives_cartagena_summary_uses_short_info_block(self):
        state = self._go_to_certified()
        state.location = "cartagena"

        self.tree.process_message(state, "2")
        self.tree.process_message(state, "2")
        summary = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "ℹ️ El alojamiento no esta incluido." in summary
        assert "ℹ️ Paquete para buzos certificados desde Cartagena" not in summary

    def test_select_4_dives_cartagena(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "3")
        assert state.selected_service == "4_dives_2_days"
        assert state.step == Step.CERTIFIED_LAST_DIVE
        assert "2 años" in response

    def test_last_dive_over_2_years_yes_then_interested_yes(self):
        state = self._go_to_certified()
        self.tree.process_message(state, "1")
        assert state.step == Step.CERTIFIED_LAST_DIVE

        r = self.tree.process_message(state, "1")
        assert state.last_dive_over_2_years is True
        assert state.step == Step.CERTIFIED_EXPERIENCE

        r = self.tree.process_message(state, "2")
        assert state.has_500_dives_or_dive_master is False
        assert state.step == Step.REFRESHER_INTEREST
        assert "refresher" in r.lower()

        r = self.tree.process_message(state, "1")
        assert state.refresher_interested is True
        assert state.step == Step.COLOMBIAN

    def test_last_dive_over_2_years_experienced_escalates(self):
        state = self._go_to_certified()
        self.tree.process_message(state, "1")
        assert state.step == Step.CERTIFIED_LAST_DIVE

        self.tree.process_message(state, "1")
        assert state.step == Step.CERTIFIED_EXPERIENCE

        r = self.tree.process_message(state, "1")
        assert state.has_500_dives_or_dive_master is True
        assert state.step == Step.ESCALATE

    def test_last_dive_over_2_years_no(self):
        state = self._go_to_certified()
        self.tree.process_message(state, "1")
        assert state.step == Step.CERTIFIED_LAST_DIVE

        r = self.tree.process_message(state, "2")
        assert state.last_dive_over_2_years is False
        # Recent dive → LOCATION (saltada por location preset) → COLOMBIAN
        assert state.step == Step.COLOMBIAN
        assert "descuent" in r.lower() or "colomb" in r.lower()

    def test_select_private_escalates(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "7")
        assert state.selected_service == "private"
        assert state.step == Step.ESCALATE

    def test_select_5_dives_shows_multiday_context(self):
        state = self._go_to_certified()

        response = self.tree.process_message(state, "4")

        assert state.selected_service == "5_dives_2_days"
        assert state.step == Step.CERTIFIED_LAST_DIVE
        # The current flow asks last-dive question before showing details
        assert "2 años" in response
        assert "refresher" in response.lower()

    def test_5_dives_recent_last_dive_summary_keeps_package(self):
        state = self._go_to_certified()
        state.location = "cartagena"
        self.tree.process_message(state, "4")

        # Recent dive → LOCATION (saltada) → COLOMBIAN
        self.tree.process_message(state, "2")
        # No colombiano → SUMMARY
        summary = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert state.selected_service == "5_dives_2_days"
        # Booking URL ya no se incluye (se envía al pulsar Reservar)
        assert "18 horas" in summary
        # Lodging note should be present for multi-day packages
        assert "alojamiento no esta incluido" in summary.lower()

    def test_island_3_dives_summary_uses_lodging_note_in_info_block(self):
        state = self._go_to_certified()
        state.location = "island"

        self.tree.process_message(state, "2")
        self.tree.process_message(state, "2")
        summary = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "ℹ️ El alojamiento no esta incluido." in summary
        assert "ℹ️ Plan para buzos certificados" not in summary

    def test_7_and_9_dives_show_correct_nights(self):
        state_7 = self._go_to_certified()
        response_7 = self.tree.process_message(state_7, "5")
        assert state_7.selected_service == "7_dives_3_days"
        # The current flow asks last-dive question before showing details
        assert "2 años" in response_7
        assert "refresher" in response_7.lower()

        state_9 = self._go_to_certified()
        response_9 = self.tree.process_message(state_9, "6")
        assert state_9.selected_service == "9_dives_4_days"
        assert "2 años" in response_9
        assert "refresher" in response_9.lower()

    def test_multiday_refresher_keeps_original_package(self):
        state = self._go_to_certified()
        state.location = "cartagena"
        self.tree.process_message(state, "4")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")

        response = self.tree.process_message(state, "1")

        assert state.refresher_interested is True
        assert state.original_service == "5_dives_2_days"
        assert state.selected_service == "5_dives_2_days"
        assert state.step == Step.COLOMBIAN
        assert "Mantengo el paquete multi-dia" in response


class TestBeginnerFlow:
    def setup_method(self):
        self.tree = DecisionTree()

    def _go_to_diving_experience(self) -> ConversationState:
        state = make_state()
        state.step = Step.TOURS_EXPERIENCE
        state.language = "es"
        state.location = "cartagena"
        return state

    def test_beginner_choice_goes_direct_to_minicourse_age_question(self):
        state = self._go_to_diving_experience()
        response = self.tree.process_message(state, "2")
        assert state.selected_service == "minicourse"
        assert state.step == Step.BEGINNER_AGE
        # El copy ahora pide elegir opción que describa al grupo (3 opciones)
        assert "grupo" in response.lower() or "minicurso" in response.lower()

    def test_tours_beginner_compatibility_menu_only_shows_minicourse(self):
        state = make_state()
        state.step = Step.TOURS_BEGINNER
        state.language = "es"
        state.location = "cartagena"

        response = self.tree.process_message(state, "1")

        assert state.selected_service == "minicourse"
        assert state.step == Step.BEGINNER_AGE
        assert "grupo" in response.lower() or "minicurso" in response.lower()

    def test_group_type_menu_routes_diving_to_diving_submenu(self):
        state = make_state()
        state.step = Step.GROUP_TYPE
        state.language = "es"
        state.location = "cartagena"

        response = self.tree.process_message(state, "1")

        assert state.step == Step.TOURS_EXPERIENCE
        assert "dentro de buceo" in response.lower()
        assert state.quick_replies[0]["title"] == "🤿 Solo buzos certificados"

    def test_snorkeling_from_top_activity_menu_goes_direct_to_colombian(self):
        # Snorkel → LOCATION (saltada por location preset) → COLOMBIAN
        state = make_state()
        state.step = Step.GROUP_TYPE
        state.language = "es"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")

        assert state.selected_service == "snorkeling"
        assert state.step == Step.COLOMBIAN
        assert "6" in response or "snorkel" in response.lower() or "superficie" in response.lower()

    def test_beginner_choice_sets_age_quick_replies_in_spanish(self):
        state = make_state()
        state.step = Step.TOURS_EXPERIENCE
        state.language = "es"
        state.location = "cartagena"

        self.tree.process_message(state, "2")

        assert state.step == Step.BEGINNER_AGE
        # Ahora son 3 opciones (menores 8 / 8-10 / 10+) + Volver
        values = [item["value"] for item in state.quick_replies]
        assert values == ["1", "2", "3", "back"]

    def test_beginner_choice_sets_age_quick_replies_in_english(self):
        state = make_state()
        state.step = Step.TOURS_EXPERIENCE
        state.language = "en"
        state.location = "cartagena"

        self.tree.process_message(state, "2")

        assert state.step == Step.BEGINNER_AGE
        values = [item["value"] for item in state.quick_replies]
        assert values == ["1", "2", "3", "back"]

    def test_minicourse_from_cartagena_summary_includes_beginner_details(self):
        state = self._go_to_diving_experience()

        # Elige solo principiantes → pregunta de edad del minicurso (3 opciones)
        age_resp = self.tree.process_message(state, "2")
        assert state.selected_service == "minicourse"
        assert state.step == Step.BEGINNER_AGE

        # Opción 3: todos 10+ → LOCATION (saltada) → COLOMBIAN
        self.tree.process_message(state, "3")
        assert state.step == Step.COLOMBIAN
        # No colombiano → SUMMARY
        summary = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY
        # Booking URL ya no se incluye en summary (se envía al pulsar Reservar)
        assert "Almuerzo" in summary
        assert "Muelle de la Bodeguita" in summary

    def test_snorkeling_from_cartagena_summary_has_no_flight_rule(self):
        state = make_state()
        state.step = Step.GROUP_TYPE
        state.language = "es"
        state.location = "cartagena"

        # Snorkel → LOCATION (saltada) → COLOMBIAN
        self.tree.process_message(state, "2")
        assert state.selected_service == "snorkeling"
        assert state.step == Step.COLOMBIAN
        # No colombiano → SUMMARY
        summary = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY
        assert "18 horas" not in summary
        assert "12 horas" not in summary

    def test_invalid_input_after_beginner_choice_keeps_age_question(self):
        state = self._go_to_diving_experience()

        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "9")

        assert state.selected_service == "minicourse"
        assert state.step == Step.BEGINNER_AGE
        assert "no entendi" in response.lower()


class TestSummaryFlow:
    def setup_method(self):
        self.tree = DecisionTree()

    def test_colombian_gets_discount_info(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "cartagena"

        response = self.tree.process_message(state, "1")  # Yes, Colombian
        assert state.is_colombian is True
        assert "+57 320 231515" in response

    def test_non_colombian_gets_booking_link(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")  # Not Colombian → SUMMARY
        assert state.is_colombian is False
        # Booking URL ya no en summary (ahora se envía al pulsar Reservar)
        assert state.step == Step.SUMMARY

    def test_island_location_different_link(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "island"

        response = self.tree.process_message(state, "2")
        # El servicio fue remapeado a la variante de isla
        assert state.selected_service == "2_dives_1_day_already_on_island"
        assert state.step == Step.SUMMARY

    def test_flight_rule_shown(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")
        assert "18 horas" in response

    def test_open_water_summary_skips_repeated_info_block_in_spanish(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "open_water"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "ℹ️" not in response
        # itinerary_offer ahora tiene: reservar + itinerary + back
        assert [item["value"] for item in state.quick_replies] == ["reservar", "itinerary", "back"]

    def test_open_water_summary_skips_repeated_info_block_in_english(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "en"
        state.selected_service = "open_water"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "ℹ️" not in response
        assert [item["value"] for item in state.quick_replies] == ["reservar", "itinerary", "back"]

    def test_divemaster_summary_in_spanish_uses_info_link_and_contact_prompt(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "divemaster"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "Los honorarios del instructor y los materiales PADI se pagan por separado" in response
        assert "Instructor fee and PADI materials are separate" not in response
        assert "👉 Reserva aqui con 10% de descuento:" not in response
        assert "🔗 Más información del programa:" in response
        assert "https://divingplanet.org/curso-padi-cartagena/dive-master/" in response
        assert "Es el primer nivel profesional de PADI" in response
        assert "¿Quieres ver el itinerario completo o prefieres contactar con nuestro jefe" in response
        assert [item["value"] for item in state.quick_replies] == ["itinerary", "contact", "back"]

    def test_divemaster_itinerary_in_spanish_adds_overview_and_contact_options(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "divemaster"
        state.location = "cartagena"

        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "itinerary")

        assert state.step == Step.SUMMARY
        assert "Resumen del programa" in response
        assert "El curso se divide en tres módulos" in response
        assert "La parte práctica solo comienza cuando toda la teoría está completa" in response
        assert "https://divingplanet.org/curso-padi-cartagena/dive-master/" in response
        assert "¿Quieres contactar con nuestro jefe para solicitar el curso de Dive Master?" in response
        assert [item["value"] for item in state.quick_replies] == ["contact", "ask", "done", "back"]

    def test_summary_follow_up_keeps_back_button_after_showing_itinerary(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "open_water"
        state.location = "cartagena"

        self.tree.process_message(state, "2")
        response = self.tree.process_message(state, "itinerary")

        assert state.step == Step.SUMMARY
        assert "itinerario" in response.lower() or "🗺️" in response
        # Follow-up ahora muestra Reservar como botón principal (no "done")
        assert [item["value"] for item in state.quick_replies] == ["reservar", "ask", "back"]

    def test_open_water_full_itinerary_skips_repeated_info_block(self):
        state = make_state()
        state.language = "es"
        state.selected_service = "open_water"
        state.location = "cartagena"
        state.is_colombian = False

        response = self.tree._format_full_itinerary(state)

        assert "ℹ️" not in response
        assert "🗺️" in response


class TestFullJourney:
    """End-to-end test simulating a complete customer interaction."""

    def setup_method(self):
        self.tree = DecisionTree()

    def test_certified_diver_from_cartagena(self):
        state = make_state("e2e-001")

        # Step 1: Welcome
        r = self.tree.process_message(state, "hola")
        assert state.step == Step.LANGUAGE

        # Step 2: Select Spanish
        r = self.tree.process_message(state, "1")
        assert state.step == Step.MAIN_MENU

        # Step 3: Reservar
        r = self.tree.process_message(state, "1")
        assert state.step == Step.RESERVA_MENU

        # Step 3b: Tours de buceo → ahora directo a GROUP_TYPE (TOURS_LOCATION se difiere al SUMMARY)
        r = self.tree.process_message(state, "1")
        assert state.step == Step.GROUP_TYPE

        # Para este test del flujo histórico Cartagena, seteamos location programáticamente
        state.location = "cartagena"

        # Step 4: Buceo
        r = self.tree.process_message(state, "1")
        assert state.step == Step.TOURS_EXPERIENCE

        # Step 5: Only certified divers
        r = self.tree.process_message(state, "1")
        assert state.step == Step.TOURS_CERTIFIED

        # Step 6: 2 dives
        r = self.tree.process_message(state, "1")
        assert state.step == Step.CERTIFIED_LAST_DIVE

        # Step 7: Last dive not over 2 years → LOCATION (saltada) → COLOMBIAN
        r = self.tree.process_message(state, "2")
        assert state.step == Step.COLOMBIAN

        # Step 8: Not Colombian → SUMMARY
        r = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY
        # Booking URL ya no se incluye en summary (se envía al pulsar Reservar)
        assert "18 horas" in r

    def test_beginner_english_from_island(self):
        state = make_state("e2e-002")

        # Welcome
        self.tree.process_message(state, "hi")
        # English
        self.tree.process_message(state, "2")
        assert state.language == "en"
        # Reservar
        self.tree.process_message(state, "1")
        assert state.step == Step.RESERVA_MENU
        # Tours → ahora directo a GROUP_TYPE (TOURS_LOCATION se difiere)
        self.tree.process_message(state, "1")
        assert state.step == Step.GROUP_TYPE
        # Seteamos location programáticamente para simular "ya en la isla"
        state.location = "island"

        # Snorkeling → LOCATION (saltada por location preset) → COLOMBIAN
        self.tree.process_message(state, "2")
        assert state.selected_service == "snorkeling_already_on_island"
        # Not Colombian → SUMMARY (booking URL ya no se incluye, ahora viene al pulsar Reservar)
        r = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY


def test_decision_tree_sets_quick_replies_for_menu_steps():
    tree = DecisionTree()
    state = make_state()

    response = tree.process_message(state, "hola")

    assert state.step == Step.LANGUAGE
    assert "1. Espanol" not in response
    assert state.quick_replies[0]["value"] == "1"
    assert state.quick_replies[1] == {"title": "🌐 English", "value": "2"}


def test_decision_tree_accepts_quick_reply_title():
    tree = DecisionTree()
    state = make_state()
    state.step = Step.MAIN_MENU
    state.language = "en"

    response = tree.process_message(state, "🤿 Book")

    assert state.step == Step.RESERVA_MENU
    assert "book" in response.lower()
    assert state.quick_replies[0]["value"] == "1"
