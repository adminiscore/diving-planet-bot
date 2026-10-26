"""Regression tests for the minor fixes found during the live Chatwoot pass:
1. Language detection used substring matching ("ahi" -> matched "hi" -> English).
2. Bare "pagar"/"pago" escalated info questions like "¿puedo pagar en euros?".
3. RAG answers offering an advisor showed generic main-menu buttons.
lat-11 T6d (26-oct): fuera los tests del nit 1 (idioma de IntentDetector.detect; la clase se quitó y el idioma lo fija
la apertura).
"""

import pytest

from src.agents.escalation import detect_sensitive_escalation

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
