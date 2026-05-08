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
        assert state.step == Step.TOURS_EXPERIENCE
        assert "certificacion" in response.lower() or "certificación" in response.lower()

    def test_select_courses(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "2")
        assert state.step == Step.COURSES_MENU
        assert "PADI" in response

    def test_select_info(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "3")
        assert "Plaza de San Diego" in response

    def test_select_human(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "4")
        assert state.step == Step.ESCALATE
        assert "asesor" in response.lower() or "WhatsApp" in response

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
        assert state.step == Step.LOCATION
        assert "U$178" in response

    def test_select_private_escalates(self):
        state = self._go_to_certified()
        response = self.tree.process_message(state, "5")
        assert state.selected_service == "private"
        assert state.step == Step.ESCALATE


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
        assert "+57 320 2554961" in response

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
        assert state.step == Step.TOURS_EXPERIENCE

        # Step 4: Certified
        r = self.tree.process_message(state, "1")
        assert state.step == Step.TOURS_CERTIFIED

        # Step 5: 2 dives
        r = self.tree.process_message(state, "1")
        assert state.step == Step.LOCATION

        # Step 6: From Cartagena
        r = self.tree.process_message(state, "1")
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
        # Tours
        self.tree.process_message(state, "1")
        # Not certified
        self.tree.process_message(state, "2")
        assert state.step == Step.TOURS_BEGINNER
        # Snorkeling
        self.tree.process_message(state, "2")
        assert state.selected_service == "snorkeling"
        # Already on island
        self.tree.process_message(state, "2")
        assert state.location == "island"
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
    assert state.quick_replies[1] == {"title": "English", "value": "2"}


def test_decision_tree_accepts_quick_reply_title():
    tree = DecisionTree()
    state = make_state()
    state.step = Step.MAIN_MENU
    state.language = "en"

    response = tree.process_message(state, "Diving and snorkel tours")

    assert state.step == Step.TOURS_EXPERIENCE
    assert "certification" in response.lower()
    assert state.quick_replies[0]["title"] == "Yes, I'm certified"
