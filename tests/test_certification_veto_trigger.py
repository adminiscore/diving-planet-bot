"""Polaridad de certificacion contradictoria (tarea 9, 2026-09-14).

El trigger del veto de `is_certified` se borro con la maquinaria de vetos (MEJ-1, 21-oct; el veto salio del camino real
en ex-9). Queda lo que sigue vivo: el detector NO se abstiene en los mensajes ambiguos de certificacion (el regex
acierta, medido con LLM real) y la nacionalidad usa la regla comun `polarity_is_ambiguous`.
"""

from src.agents.intent_detector import IntentDetector, nationality_is_ambiguous
from src.flows.state import ConversationState


def test_detector_does_not_abstain_on_ambiguous_certification():
    """El regex acierta en los ambiguos de certificacion (medido): no se abstiene."""
    message = "no es que no estemos certificados, si lo estamos, los 2"
    intent = IntentDetector().detect(message, ConversationState(conversation_id="c"))
    assert intent.is_certified is True


def test_nationality_uses_the_same_common_rule():
    assert nationality_is_ambiguous("somos extranjeros pero vivimos en colombia") is True
    assert nationality_is_ambiguous("soy colombiano") is False
