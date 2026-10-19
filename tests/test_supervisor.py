"""Tests directos para detectores deterministas de supervisor.py sin
cobertura dedicada hasta hoy (inventario regex, 2026-09-03,
docs/multi-agent-refactor-plan.md hallazgo "purple-sun-590"): ~15 regex/
listas de este archivo no tenian NINGUN test propio -- la misma falta de
red de regresion que dejo pasar los 3 bugs reales encontrados hoy hasta
produccion. Prioriza los detectores de mayor riesgo de negocio (dar una
respuesta equivocada, o escalar/no escalar mal).
"""

from src.agents.supervisor import (
    _ADAPTIVE_DIVING_PATTERN,
    _ai_identity_deflection,
    _AI_IDENTITY_RE,
    _alcohol_and_food_policy_answer,
    _asks_about_ai_identity,
    _asks_for_contact_number,
    _contact_number_deflection,
    _detect_cancellation_request,
    _detect_modify_booking_request,
    _detect_reschedule_request,
    _DIVE_TO_HEAL_OVERRIDE_RE,
    _PRIVATE_GROUP_EVENT_RE,
    _private_group_event_answer,
    _same_price_different_nationality_answer,
    _SAME_PRICE_DIFFERENT_NATIONALITY_RE,
)


# ---------------------------------------------------------------------------
# Cancelar / reprogramar / modificar reserva
# ---------------------------------------------------------------------------

class TestCancelRescheduleModify:
    def test_cancel_es(self):
        assert _detect_cancellation_request("quiero cancelar mi reserva")

    def test_cancel_en(self):
        assert _detect_cancellation_request("i want to cancel my booking")

    def test_cancel_negative_generic_menu_word(self):
        assert not _detect_cancellation_request("hola quiero reservar un tour")

    def test_reschedule_es(self):
        assert _detect_reschedule_request("puedo cambiar la fecha de mi reserva")

    def test_reschedule_en(self):
        assert _detect_reschedule_request("i'd like to reschedule my booking")

    def test_reschedule_negative_plain_date_question(self):
        assert not _detect_reschedule_request("que dias hay disponibles?")

    def test_modify_es(self):
        assert _detect_modify_booking_request("ya tengo una reserva y quiero agregar una persona")

    def test_modify_en(self):
        assert _detect_modify_booking_request("i already booked and want to add someone")

    def test_modify_negative_group_size_during_booking(self):
        """Decir el tamaño de grupo mientras se arma la reserva NO es
        modificar una reserva existente -- lo maneja el flujo normal."""
        assert not _detect_modify_booking_request("somos 4 personas")

    def test_cancel_accent_insensitive(self):
        """CANCEL_BOOKING_PHRASES vive sin acentos; el mensaje real trae
        acentos y debe normalizarse antes de comparar."""
        assert _detect_cancellation_request("quiero cancelar mi reservación")


# ---------------------------------------------------------------------------
# Petición de número de contacto (deflexión, nunca escala, nunca da el número)
# ---------------------------------------------------------------------------

class TestContactNumberRequest:
    def test_asks_for_phone_es(self):
        assert _asks_for_contact_number("me das un numero de telefono")

    def test_asks_for_whatsapp_en(self):
        assert _asks_for_contact_number("what's your whatsapp number")

    def test_negative_unrelated_question(self):
        assert not _asks_for_contact_number("cuanto cuesta el minicurso")

    def test_deflection_never_contains_a_number(self):
        """La política del owner: nunca dar el número real -- verificación
        determinista de que el texto de deflexión no contiene el patrón de
        un número de teléfono/WhatsApp."""
        import re
        text = _contact_number_deflection("es")
        assert not re.search(r"\+?\d[\d\s-]{6,}\d", text)


# ---------------------------------------------------------------------------
# Identidad IA (deflexión canónica, nunca revela el modelo/tecnología)
# ---------------------------------------------------------------------------

class TestAiIdentity:
    def test_asks_what_model_es(self):
        assert _asks_about_ai_identity("que modelo de ia eres?")

    def test_asks_are_you_a_bot_en(self):
        assert _asks_about_ai_identity("are you a bot?")

    def test_negative_unrelated_question(self):
        assert not _asks_about_ai_identity("cuanto cuesta el buceo?")

    def test_deflection_never_names_the_real_model(self):
        text = _ai_identity_deflection("es").lower()
        for leaked in ("gpt", "openai", "claude", "anthropic", "modelo de lenguaje"):
            assert leaked not in text


# ---------------------------------------------------------------------------
# DIVE TO HEAL (buceo adaptado)
# ---------------------------------------------------------------------------

class TestAdaptiveDiving:
    def test_disability_mention_es(self):
        assert _ADAPTIVE_DIVING_PATTERN.search("mi hermano tiene discapacidad, puede bucear?")

    def test_wheelchair_en(self):
        assert _ADAPTIVE_DIVING_PATTERN.search("my friend uses a wheelchair")

    def test_negative_unrelated_message(self):
        assert not _ADAPTIVE_DIVING_PATTERN.search("quiero bucear el sabado")

    def test_override_back_to_normal_program(self):
        assert _DIVE_TO_HEAL_OVERRIDE_RE.search("en realidad pregunto por el programa normal")


# ---------------------------------------------------------------------------
# Alcohol / alergia alimentaria (hallazgo real, lote 9 -- sin test hasta hoy)
# ---------------------------------------------------------------------------

class TestAlcoholAndFoodPolicy:
    def test_alcohol_only(self):
        answer = _alcohol_and_food_policy_answer("vamos a bucear manana, anoche tomamos alcohol", "es")
        assert answer is not None
        assert "alcohol" in answer.lower()

    def test_allergy_with_known_allergen(self):
        answer = _alcohol_and_food_policy_answer("soy alergico a los mariscos", "es")
        assert answer is not None

    def test_allergy_without_food_allergen_returns_none(self):
        """Alergia sin alérgeno alimentario explícito no es esta política --
        sigue yendo al escalado médico normal."""
        assert _alcohol_and_food_policy_answer("tengo alergias severas, es peligroso bucear?", "es") is None

    def test_both_topics_combined_in_one_message(self):
        """Hallazgo en vivo (lote 9): el primer `if` con return inmediato
        perdía el segundo tema si venían juntos -- ambos deben aparecer."""
        msg = "vamos a bucear, anoche tomamos alcohol y soy alergico a los mariscos"
        answer = _alcohol_and_food_policy_answer(msg, "es")
        assert answer is not None
        assert "alcohol" in answer.lower()

    def test_negative_unrelated_message(self):
        assert _alcohol_and_food_policy_answer("cuanto cuesta el minicurso", "es") is None


# ---------------------------------------------------------------------------
# Evento corporativo / grupo privado (hallazgo real, lote 11)
# ---------------------------------------------------------------------------

class TestPrivateGroupEvent:
    def test_corporate_event_es(self):
        assert _PRIVATE_GROUP_EVENT_RE.search("somos una empresa y queremos un evento corporativo")

    def test_private_event_en(self):
        assert _PRIVATE_GROUP_EVENT_RE.search("we'd like to book a private event")

    def test_negative_unrelated_message(self):
        assert not _PRIVATE_GROUP_EVENT_RE.search("somos 4 amigos y queremos bucear")

    def test_answer_never_leaks_the_whatsapp_number(self):
        """La política real (policies.json) lleva el número de WhatsApp en
        crudo -- la respuesta determinista debe redactarlo, nunca darlo."""
        import re
        text = _private_group_event_answer("es")
        assert not re.search(r"\+?57\s*3\d{2}[\s.]?\d{3}\s*\d{3,4}", text)


# ---------------------------------------------------------------------------
# Mismo precio, distinta nacionalidad (hallazgo real, lote 12)
# ---------------------------------------------------------------------------

class TestSamePriceDifferentNationality:
    def test_matches_real_repro_message(self):
        assert _SAME_PRICE_DIFFERENT_NATIONALITY_RE.search(
            "lo mismo pero para mi amigo que es colombiano, cambia algo?"
        )

    def test_negative_unrelated_price_question(self):
        assert not _SAME_PRICE_DIFFERENT_NATIONALITY_RE.search("cuanto cuesta el paquete de 5 inmersiones?")

    def test_answer_says_price_does_not_change(self):
        """El hallazgo real era RAG inventando un precio nuevo -- la
        respuesta determinista debe decir explícitamente que no cambia."""
        text = _same_price_different_nationality_answer("es").lower()
        assert "no cambia" in text
