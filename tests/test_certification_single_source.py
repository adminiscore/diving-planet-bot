"""Certificacion con una sola fuente (2026-09-15).

El deseo de certificarse vivia en tres listas que no coincidian (detector, lista
negativa y RAG) y el RAG tenia su propia lista de "ya certificado":
- "quiere sacarse la certificacion" o "me quiero certificar" salian certificados;
- el RAG leia "no soy certificado" como certificado y descartaba "tengo el open water
  y quiero hacer buceo" por el "quiero hacer".
Ahora `certification_status` decide para el detector y para el RAG.
"""

import pytest

from src.agents import rag_agent
from src.agents.intent_detector import IntentDetector, certification_status
from src.flows.state import ConversationState


@pytest.mark.parametrize("message", [
    "quiere sacarse la certificación de buceo",
    "queremos sacarnos la licencia",
    "me quiero certificar",
    "quisiera obtener la certificación",
    "we want to get our certification",
    "quiero hacer el curso open water",
])
def test_wanting_the_certification_is_not_certified(message):
    assert certification_status(message) is False


@pytest.mark.parametrize("message", [
    "no sé si hacer el open water o el advanced",   # duda, no deseo
    "I want to do the advanced course",              # el Advanced exige Open Water
])
def test_doubt_or_higher_course_does_not_decide(message):
    assert certification_status(message) is None


def test_wish_to_certify_leaves_the_activity_open():
    intent = IntentDetector().detect("quisiera obtener la certificación", ConversationState(conversation_id="c"))
    assert intent.is_certified is False
    assert intent.activity is None


@pytest.mark.parametrize("message, expected", [
    ("no soy certificado, es mi primera vez", False),
    ("no tengo licencia de buceo", False),
    ("tengo el open water y quiero hacer buceo", True),
    ("i'm certified but haven't dived in like 4 years", True),
])
def test_rag_uses_the_detector_source(message, expected):
    assert rag_agent._mentions_already_certified(message.lower()) is expected
    assert not hasattr(rag_agent, "_ALREADY_CERTIFIED_RE")
    assert not hasattr(rag_agent, "_WANTS_CERT_EXCLUDE_RE")
