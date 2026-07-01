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
        response = self.tree.process_message(state, "zzz")
        assert "Diving Planet" in response
        assert state.step == Step.LANGUAGE

    def test_welcome_detects_spanish_greeting_and_skips_language_step(self):
        state = make_state()
        response = self.tree.process_message(state, "hola")
        assert "Diving Planet" in response
        assert state.language == "es"
        assert state.step == Step.MAIN_MENU

    def test_welcome_detects_english_greeting_and_skips_language_step(self):
        state = make_state()
        response = self.tree.process_message(state, "hello")
        assert "Diving Planet" in response
        assert state.language == "en"
        assert state.step == Step.MAIN_MENU

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
        assert state.step == Step.MIXED_ENTRY
        assert "paso a paso" in response.lower() or "step by step" in response.lower()

    def test_select_info(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "2")
        assert state.step == Step.INFO_MENU
        assert "información" in response.lower() or "information" in response.lower()

    def test_info_activities_menu_uses_booking_top_level_structure(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "2")
        self.tree.process_message(state, "1")
        response = self.tree.process_message(state, "1")

        assert state.step == Step.INFO_ACTIVITIES_MENU
        assert "actividades" in response.lower() or "activities" in response.lower()
        assert [item["title"] for item in state.quick_replies[:2]] == [
            "🤿 Tours de buceo / snorkel",
            "📘 Cursos PADI y certificaciones",
        ]

    def test_info_certified_menu_from_island_mirrors_booking_options(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "2")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "1")
        response = self.tree.process_message(state, "1")

        assert state.step == Step.INFO_TOURS_CERTIFIED_MENU
        assert "buzos certificados" in response.lower()
        assert [item["title"] for item in state.quick_replies[:4]] == [
            "🤿 2 inmersiones (1 día)",
            "🤿 3 inmersiones (1 día)*",
            "🤿 4 inmersiones (2 días)",
            "🤿 5 inmersiones (2 días)",
        ]

    def test_info_island_certified_4_dives_opens_variant_menu(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "2")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "2")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "1")
        response = self.tree.process_message(state, "3")

        assert state.step == Step.INFO_CERTIFIED_4_DIVES_VARIANT
        assert "4 inmersiones" in response.lower()
        assert [item["title"] for item in state.quick_replies[:2]] == [
            "🤿 4 inmersiones (2 días) · 4 diurnas",
            "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna",
        ]

    def test_select_courses_via_reservar(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")  # Reservar
        state.location = "cartagena"
        self.tree.process_message(state, "1")  # Añadir actividades
        response = self.tree.process_message(state, "4")  # Curso PADI
        assert state.step == Step.COURSES_MENU
        assert "PADI" in response

    def test_mixed_certified_menu_lists_all_packages_from_cartagena(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        response = self.tree.process_message(state, "1")

        assert state.step == Step.MIXED_ADD_CERT_PLAN
        assert "¿qué idea tienes" in response.lower()
        assert [item["title"] for item in state.quick_replies[:2]] == [
            "🤿 2 Inmersiones / 1 día",
            "📅 Paquete multi-día (3 o más inmersiones)",
        ]

        response = self.tree.process_message(state, "2")

        assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY
        assert "3 o más inmersiones" in response
        assert [item["title"] for item in state.quick_replies[:5]] == [
            "🤿 3 inmersiones (1 día)*",
            "🤿 4 inmersiones (2 días)",
            "🤿 5 inmersiones (2 días)",
            "🤿 7 inmersiones (3 días)",
            "🤿 9 inmersiones (4 días)",
        ]

    def test_mixed_certified_menu_lists_island_4_dive_variants(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        state.location = "island"
        self.tree.process_message(state, "1")
        response = self.tree.process_message(state, "1")

        assert state.step == Step.MIXED_ADD_CERT_PLAN
        assert "paquete multi-día" in response.lower()
        assert [item["title"] for item in state.quick_replies[:2]] == [
            "🤿 2 Inmersiones / 1 día",
            "📅 Paquete multi-día (3 o más inmersiones)",
        ]

        response = self.tree.process_message(state, "2")

        assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY
        assert "3 o más inmersiones" in response
        assert [item["title"] for item in state.quick_replies[:6]] == [
            "🤿 3 inmersiones (1 día)*",
            "🤿 4 inmersiones (2 días) · 4 diurnas",
            "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna",
            "🤿 5 inmersiones (2 días)",
            "🤿 7 inmersiones (3 días)",
            "🤿 9 inmersiones (4 días)",
        ]

    def test_courses_menu_quick_replies_use_new_titles_in_spanish(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "4")

        assert [item["title"] for item in state.quick_replies[:3]] == [
            "🐠 Descubriendo el buceo (Open Water Diver)",
            "🚀 Convierte en pro (Advanced / Rescue / Dive Master)",
            "✨ Amplía tus habilidades (Especialidades PADI)",
        ]

    def test_courses_menu_quick_replies_use_new_titles_in_english(self):
        state = self._go_to_menu("en")
        self.tree.process_message(state, "1")
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "4")

        assert [item["title"] for item in state.quick_replies[:3]] == [
            "🐠 Discover diving (Open Water Diver)",
            "🚀 Go pro (Advanced / Rescue / Divemaster)",
            "✨ Expand your skills (PADI Specialties)",
        ]

    def test_go_pro_submenu_shows_only_advanced_rescue_and_divemaster_in_spanish(self):
        state = self._go_to_menu()
        self.tree.process_message(state, "1")
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "4")
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
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "4")
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
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "4")
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
        state.location = "cartagena"
        self.tree.process_message(state, "1")
        self.tree.process_message(state, "4")
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
        assert "entend" in response.lower() or "get that" in response.lower()

    def test_invalid_option(self):
        state = self._go_to_menu()
        response = self.tree.process_message(state, "99")
        assert "entend" in response.lower() or "get that" in response.lower()


class TestSummaryFlow:
    def setup_method(self):
        self.tree = DecisionTree()

    def test_colombian_gets_cop_price_summary(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "es"
        state.selected_service = "2_dives_1_day"
        state.location = "cartagena"

        response = self.tree.process_message(state, "1")  # Yes, Colombian
        assert state.is_colombian is True
        # Should advance to SUMMARY with COP price shown; no discount claim
        assert state.step == Step.SUMMARY
        assert "COP" in response or "$" in response  # price shown in some currency

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
        assert [item["value"] for item in state.quick_replies] == ["itinerary", "cash", "back"]
        assert state.quick_replies[0]["title"] == "🗺️ Ver itinerario completo"

    def test_open_water_summary_skips_repeated_info_block_in_english(self):
        state = make_state()
        state.step = Step.COLOMBIAN
        state.language = "en"
        state.selected_service = "open_water"
        state.location = "cartagena"

        response = self.tree.process_message(state, "2")

        assert state.step == Step.SUMMARY
        assert "ℹ️" not in response
        assert [item["value"] for item in state.quick_replies] == ["itinerary", "cash", "back"]
        assert state.quick_replies[0]["title"] == "🗺️ View full itinerary"

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
        assert [item["value"] for item in state.quick_replies] == ["ask", "cash", "back"]

    def test_open_water_full_itinerary_skips_repeated_info_block(self):
        state = make_state()
        state.language = "es"
        state.selected_service = "open_water"
        state.location = "cartagena"
        state.is_colombian = False

        response = self.tree._format_full_itinerary(state)

        assert "ℹ️" not in response
        assert "🗺️" in response
        # El link de reserva/pago ya no se muestra al cliente: lo envía el asesor.
        assert "Link de reserva" not in response
        assert "Booking link" not in response


def test_decision_tree_sets_quick_replies_for_menu_steps():
    tree = DecisionTree()
    state = make_state()

    response = tree.process_message(state, "zzz")

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

    assert state.step == Step.MIXED_ENTRY
    assert "step by step" in response.lower()
    assert state.quick_replies[0]["value"] == "1"


class TestMixedCertificationSplit:
    """v0.17.1: a group with 'some certified, some not' must split into a
    certified subgroup + a minicurso for the non-certified people, instead of
    booking everyone as certified divers."""

    def setup_method(self):
        self.tree = DecisionTree()

    def _start(self, group_size=3):
        state = make_state()
        state.language = "es"
        state.location = "cartagena"
        state.detected_group_size = group_size
        state.detected_is_certified = None
        state.step = Step.MIXED_ASK_CERTIFICATION
        return state

    def test_some_certified_asks_how_many_are_certified(self):
        state = self._start(group_size=3)
        response = self.tree.process_message(state, "3")  # Algunos sí, otros no
        assert state.step == Step.MIXED_ASK_CERT_COUNT
        assert "certificados" in response.lower()
        values = [b["value"] for b in state.quick_replies]
        assert values == ["1", "2", "back"]

    def test_cert_count_records_split(self):
        state = self._start(group_size=3)
        self.tree.process_message(state, "3")
        self.tree.process_message(state, "2")  # 2 certified
        assert state.mixed_pending_beginner_after_cert == 1
        assert state.mixed_pending_cert_total_qty == 2

    def test_full_split_flow_builds_cert_plus_minicourse_cart(self):
        state = self._start(group_size=3)
        self.tree.process_message(state, "3")   # some certified
        self.tree.process_message(state, "2")   # 2 certified
        self.tree.process_message(state, "1")   # 2 dives / 1 day
        self.tree.process_message(state, "2")   # last dive < 2 years (No)
        resp = self.tree.process_message(state, "1")  # confirm cert preview
        assert state.step == Step.MIXED_ASK_BEGINNER_ACTIVITY
        assert "minicurso" in resp.lower()
        self.tree.process_message(state, "1")   # Minicurso de buceo
        self.tree.process_message(state, "3")   # kids: all 10+
        self.tree.process_message(state, "1")   # confirm minicourse preview
        assert state.step == Step.MIXED_CART_REVIEW
        types = sorted((it["type"], it["qty"]) for it in state.mixed_cart)
        assert types == [("beginner", 1), ("cert", 2)]

    def test_cert_count_back_returns_to_certification_question(self):
        """'back' from MIXED_ASK_CERT_COUNT must re-show the certification
        question (and reset state.step accordingly), not jump to MAIN_MENU."""
        state = self._start(group_size=3)
        self.tree.process_message(state, "3")  # some certified -> MIXED_ASK_CERT_COUNT
        resp = self.tree.process_message(state, "back")
        assert state.step == Step.MIXED_ASK_CERTIFICATION
        assert "certificados" in resp.lower()

    def test_cert_count_rejects_full_group(self):
        state = self._start(group_size=3)
        self.tree.process_message(state, "3")
        resp = self.tree.process_message(state, "3")  # all 3 invalid for mixed
        assert state.step == Step.MIXED_ASK_CERT_COUNT
        assert "entre 1 y 2" in resp.lower()

    def _reach_beginner_activity_question(self, cert_plan_choices: list[str]) -> tuple["DecisionTree", "ConversationState"]:
        """Drive the cert subgroup through to the point where the
        MIXED_ASK_BEGINNER_ACTIVITY question is shown for the non-certified
        person. `cert_plan_choices` are the answers for MIXED_ADD_CERT_PLAN
        (and, for multi-day, MIXED_ADD_CERT_MULTI_DAY)."""
        state = self._start(group_size=2)
        self.tree.process_message(state, "3")   # some certified
        self.tree.process_message(state, "1")   # 1 certified, 1 minicourse
        for choice in cert_plan_choices:
            self.tree.process_message(state, choice)
        resp = self.tree.process_message(state, "2")  # last dive < 2 years -> No
        resp = self.tree.process_message(state, "1")  # confirm cert preview -> ask beginner activity
        return state, resp

    def test_beginner_activity_question_one_day_plan_has_no_open_water_option(self):
        state, resp = self._reach_beginner_activity_question(["1"])  # 2 dives / 1 day
        assert state.step == Step.MIXED_ASK_BEGINNER_ACTIVITY
        assert "open water" not in resp.lower()
        values = [b["value"] for b in state.quick_replies]
        assert values == ["1", "2", "back"]

    def test_beginner_activity_question_multi_day_plan_offers_open_water(self):
        state, resp = self._reach_beginner_activity_question(["2", "1"])  # multi-day -> first package
        assert state.step == Step.MIXED_ASK_BEGINNER_ACTIVITY
        assert "open water" in resp.lower()
        values = [b["value"] for b in state.quick_replies]
        assert values == ["1", "2", "3", "back"]

    def test_beginner_activity_back_returns_to_cart_review(self):
        """'back' from MIXED_ASK_BEGINNER_ACTIVITY must return to the cart
        review (showing the cert items already added), not MAIN_MENU."""
        state, _ = self._reach_beginner_activity_question(["1"])
        resp = self.tree.process_message(state, "back")
        assert state.step == Step.MIXED_CART_REVIEW
        assert any(it.get("type") == "cert" for it in state.mixed_cart)

    def test_beginner_activity_choice_minicourse(self):
        state, _ = self._reach_beginner_activity_question(["1"])
        self.tree.process_message(state, "1")  # Minicurso de buceo
        self.tree.process_message(state, "3")  # kids: all 10+
        resp = self.tree.process_message(state, "1")  # confirm minicourse preview
        assert state.step == Step.MIXED_CART_REVIEW
        beginner_item = next(it for it in state.mixed_cart if it["type"] == "beginner")
        assert beginner_item["qty"] == 1

    def test_beginner_activity_choice_snorkel(self):
        state, _ = self._reach_beginner_activity_question(["1"])
        resp = self.tree.process_message(state, "2")  # Snorkel
        assert state.step == Step.MIXED_ADD_PREVIEW
        assert "snorkel" in resp.lower()
        self.tree.process_message(state, "1")  # confirm snorkel preview
        assert state.step == Step.MIXED_CART_REVIEW
        snorkel_item = next(it for it in state.mixed_cart if it["type"] == "snorkel")
        assert snorkel_item["qty"] == 1

    def test_beginner_activity_choice_open_water_only_offered_when_multi_day(self):
        state, _ = self._reach_beginner_activity_question(["2", "1"])  # multi-day
        resp = self.tree.process_message(state, "3")  # Curso Open Water
        assert state.step == Step.COURSES_OPEN_WATER_TIME
        assert "2 dias completos" in resp.lower() or "2 días completos" in resp.lower()

    def test_split_flow_on_island_asks_hotel_before_cert_plan(self):
        """Regression: choosing "Algunos sí, otros no" then answering the
        location question with "Ya estoy en las islas" skipped straight to the
        cert-plan question without ever asking which hotel — pickup couldn't
        be coordinated. Location is asked AFTER cert count here (group_size
        known up front, location still unset), so this exercises
        _handle_mixed_location's _after_location_set hotel check."""
        state = self._start(group_size=5)
        state.location = None
        self.tree.process_message(state, "3")   # some certified
        self.tree.process_message(state, "3")   # 3 certified, 2 minicourse
        assert state.step == Step.MIXED_LOCATION
        resp = self.tree.process_message(state, "2")  # Ya estoy en las islas
        assert state.step == Step.ISLAND_MENU
        assert "isla" in resp.lower()

        resp = self.tree.process_message(state, "1")  # Isla Grande
        assert state.step == Step.ISLAND_HOTEL_MENU

        resp = self.tree.process_message(state, "1")  # first hotel
        assert state.step == Step.MIXED_ADD_CERT_PLAN
        assert state.hotel == "San Pedro de Majagua"
        assert state.island == "Isla Grande"
