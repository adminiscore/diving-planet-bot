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

    def test_select_tours(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "1")
        assert state.step == Step.GROUP_TYPE
        assert state.location == "cartagena"
        assert "grupo" in response.lower()

    def test_select_courses(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "2")
        assert state.step == Step.GROUP_TYPE
        assert state.location == "island"
        assert "grupo" in response.lower()

    def test_select_info(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "3")
        assert state.step == Step.COURSES_MENU
        assert "PADI" in response

    def test_select_human(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "7")
        assert state.step == Step.ESCALATE
        assert "jefe" in response.lower() or "manager" in response.lower()

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
        return state

    def test_select_2_dives(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "1")
        assert state.selected_service == "2_dives_1_day"
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
        assert state.step == Step.COLOMBIAN
        assert "descuent" in r.lower() or "colomb" in r.lower()

    def test_select_private_escalates(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "5")
        assert state.selected_service == "private"
        assert state.step == Step.ESCALATE

    def test_select_5_dives_shows_multiday_context(self):
        state = self._go_to_certified()

        response = self.tree.process_message(state, "2")

        assert state.selected_service == "5_dives_2_days"
        assert state.step == Step.CERTIFIED_LAST_DIVE
        assert "1 noche" in response
        assert "buceo nocturno" in response
        assert "alojamiento no esta incluido" in response
        assert "quitar la nocturna" in response

    def test_5_dives_recent_last_dive_summary_keeps_package(self):
        state = self._go_to_certified()
        state.location = "cartagena"
        self.tree.process_message(state, "2")

        self.tree.process_message(state, "2")
        summary = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert state.selected_service == "5_dives_2_days"
        assert "2-days-5-dives" in summary
        assert "buceo nocturno" in summary
        assert "18 horas" in summary

    def test_7_and_9_dives_show_correct_nights(self):
        state_7 = self._go_to_certified()
        response_7 = self.tree.process_message(state_7, "3")
        assert state_7.selected_service == "7_dives_3_days"
        assert "2 noches" in response_7
        assert "6 buceos diurnos" in response_7

        state_9 = self._go_to_certified()
        response_9 = self.tree.process_message(state_9, "4")
        assert state_9.selected_service == "9_dives_4_days"
        assert "3 noches" in response_9
        assert "8 buceos diurnos" in response_9

    def test_multiday_refresher_keeps_original_package(self):
        state = self._go_to_certified()
        state.location = "cartagena"
        self.tree.process_message(state, "2")
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

    def _go_to_beginner(self) -> ConversationState:
        state = make_state()
        state.step = Step.TOURS_BEGINNER
        state.language = "es"
        state.is_certified = False
        return state

    def test_select_minicourse(self):
        state = self._go_to_beginner()
        response = self.tree.process_message(state, "1")
        assert state.selected_service == "minicourse"
        assert state.step == Step.LOCATION

    def test_select_snorkeling(self):
        state = self._go_to_beginner()
        response = self.tree.process_message(state, "2")
        assert state.selected_service == "snorkeling"
        assert state.step == Step.LOCATION

    def test_beginner_menu_copy_explains_minicourse_vs_snorkel(self):
        state = make_state()
        state.step = Step.GROUP_TYPE
        state.language = "es"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")

        assert state.step == Step.TOURS_BEGINNER
        assert "probar buceo" in response
        assert "Tour de Snorkeling" in response
        assert state.quick_replies[0]["title"] == "🤿 Minicurso de Buceo"

    def test_minicourse_from_cartagena_summary_includes_beginner_details(self):
        state = self._go_to_beginner()
        state.location = "cartagena"

        detail = self.tree.process_message(state, "🤿 Minicurso de Buceo")
        assert state.selected_service == "minicourse"
        assert state.step == Step.COLOMBIAN
        assert "No necesitas experiencia previa" in detail
        assert "piscina" in detail
        assert "1 inmersion" in detail
        assert "Edad minima recomendada" in detail

        summary = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY
        assert "minicurso-de-buceo" in summary
        assert "12 horas" in summary
        assert "Almuerzo" in summary
        assert "Muelle de la Bodeguita" in summary

    def test_snorkeling_from_cartagena_summary_has_no_flight_rule(self):
        state = self._go_to_beginner()
        state.location = "cartagena"

        detail = self.tree.process_message(state, "🐠 Tour de Snorkeling")
        assert state.selected_service == "snorkeling"
        assert state.step == Step.COLOMBIAN
        assert "Actividad de superficie" in detail
        assert "acompanantes" in detail

        summary = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY
        assert "superfic" in summary
        assert "2 salidas guiadas" in summary
        assert "18 horas" not in summary
        assert "12 horas" not in summary

    def test_beginner_private_service_escalates_without_service_detail(self):
        state = self._go_to_beginner()
        state.location = "cartagena"

        response = self.tree.process_message(state, "🧑‍💬 Servicio Privado")

        assert state.selected_service == "private"
        assert state.step == Step.ESCALATE
        assert "servicio privado" in response.lower()
        assert "fecha" in response.lower()
        assert "Cotizacion personalizada" not in response


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

        response = self.tree.process_message(state, "2")  # Not Colombian
        assert state.is_colombian is False
        assert "book.divingplanet.org" in response

    def test_island_location_different_link(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "island"

        response = self.tree.process_message(state, "2")
        assert "already-on-island" in response

    def test_flight_rule_shown(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")
        assert "18 horas" in response


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

        # Step 3: Tours
        r = self.tree.process_message(state, "1")
        assert state.step == Step.GROUP_TYPE

        # Step 4: Only certified divers
        r = self.tree.process_message(state, "1")
        assert state.step == Step.TOURS_CERTIFIED

        # Step 5: 2 dives
        r = self.tree.process_message(state, "1")
        assert state.step == Step.CERTIFIED_LAST_DIVE

        # Step 6: Last dive not over 2 years
        r = self.tree.process_message(state, "2")
        assert state.step == Step.COLOMBIAN

        # Step 7: Not Colombian
        r = self.tree.process_message(state, "2")
        assert state.step == Step.SUMMARY
        assert "book.divingplanet.org" in r
        assert "18 horas" in r

    def test_beginner_english_from_island(self):
        state = make_state("e2e-002")

        # Welcome
        self.tree.process_message(state, "hi")
        # English
        self.tree.process_message(state, "2")
        assert state.language == "en"
        # Already on island
        self.tree.process_message(state, "2")
        assert state.location == "island"

        # Only beginners
        self.tree.process_message(state, "2")
        assert state.step == Step.TOURS_BEGINNER
        # Snorkeling
        self.tree.process_message(state, "2")
        assert state.selected_service == "snorkeling_already_on_island"
        # Not Colombian
        r = self.tree.process_message(state, "2")
        assert "already-on-the-island" in r


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

    response = tree.process_message(state, "🤿 Diving and snorkel tours (from Cartagena)")

    assert state.step == Step.GROUP_TYPE
    assert "group" in response.lower()
    assert state.quick_replies[0]["value"] == "1"
