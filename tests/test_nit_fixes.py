"""Regression tests for the minor fixes found during the live Chatwoot pass:
1. Language detection used substring matching ("ahi" -> matched "hi" -> English).
2. Bare "pagar"/"pago" escalated info questions like "¿puedo pagar en euros?".
3. RAG answers offering an advisor showed generic main-menu buttons.
"""

import pytest

from src.agents.intent_detector import IntentDetector
from src.agents.escalation import detect_sensitive_escalation
from src.agents.supervisor import _answer_offers_advisor
from src.flows.decision_tree import ConversationState


# ---------------------------------------------------------------------------
# Nit 1 — language detection by whole word, not substring
# ---------------------------------------------------------------------------

def _lang(msg: str) -> str | None:
    return IntentDetector().detect(msg, ConversationState(conversation_id="t")).language


class TestLanguageWordBoundary:
    def test_ahi_does_not_trigger_english(self):
        # "ahi" contains "hi" but the sentence is Spanish.
        assert _lang("Estoy en el hotel Pao Pao, me recogen ahi?") == "es"

    @pytest.mark.parametrize("msg", [
        "Cuanto cuesta el buceo?",
        "Quiero reservar un minicurso",
        "Estoy en las islas, me pueden recoger?",
    ])
    def test_spanish_stays_spanish(self, msg):
        assert _lang(msg) == "es"

    @pytest.mark.parametrize("msg", [
        "Can you pick me up at the hotel?",
        "hi, how much is diving?",
        "I want to book a course",
    ])
    def test_english_stays_english(self, msg):
        assert _lang(msg) == "en"


# ---------------------------------------------------------------------------
# Nit 2 — payment info questions must not escalate; real failures still do
# ---------------------------------------------------------------------------

class TestPaymentEscalation:
    @pytest.mark.parametrize("msg", [
        "¿Puedo pagar en euros?",
        "¿Cómo puedo pagar?",
        "¿Puedo pagar en efectivo?",
        "quiero pagar con tarjeta",
    ])
    def test_payment_info_does_not_escalate(self, msg):
        assert detect_sensitive_escalation(msg, "es") is None

    @pytest.mark.parametrize("msg", [
        "No puedo pagar, el sistema falla",
        "el pago falló y no sé qué hacer",
        "payment failed on the website",
    ])
    def test_payment_failure_still_escalates(self, msg):
        result = detect_sensitive_escalation(msg, "es")
        assert result is not None and result[0] == "real_time_issues"


# ---------------------------------------------------------------------------
# Nit 3 — advisor-offer detection drives matching buttons
# ---------------------------------------------------------------------------

class TestAdvisorOfferDetection:
    @pytest.mark.parametrize("answer", [
        "Si te interesa, puedo pasarte con un asesor para que te explique. ¿Te gustaría?",
        "Te recomiendo que contactes a un asesor. ¿Te gustaría que te pase el contacto? 🐠",
        "I can connect you with an advisor. Would you like that?",
    ])
    def test_detects_advisor_offer(self, answer):
        assert _answer_offers_advisor(answer)

    @pytest.mark.parametrize("answer", [
        "Coordinamos recogida en Pao Pao. ¿Me escribes por WhatsApp?",   # no advisor noun
        "No manejamos euros, pagas en USD. ¿Quieres saber un precio?",   # no advisor noun
        "El curso dura 2 días y cuesta 250 USD.",                        # statement, no offer
        "Te conecto con un asesor. WhatsApp: +57 320 231515",            # gives contact, not a question
    ])
    def test_ignores_non_offers(self, answer):
        assert not _answer_offers_advisor(answer)
