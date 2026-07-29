"""Tests for Capa 2 typo-tolerance in IntentDetector activity patterns."""

import pytest
from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState


def detect(message: str) -> str | None:
    state = ConversationState(conversation_id="test-typo")
    return IntentDetector().detect(message, state).activity


# ---------------------------------------------------------------------------
# certified_diving — typos and synonyms
# ---------------------------------------------------------------------------

class TestCertifiedDivingTypos:
    @pytest.mark.parametrize("msg", [
        "quiero buceo",          # exact
        "quiero bucear",         # verb form
        "quiero bucereo",        # typo: extra 'r'
        "me gusta buceando",     # gerund
        "quiero bucea mañana",   # stem variant
        "hacemos buseo mañana",  # u/c swap typo
        "submarinismo",          # synonym
    ])
    def test_certified_diving_detected(self, msg):
        assert detect(msg) == "certified_diving", f"Expected certified_diving for: {msg!r}"

    @pytest.mark.parametrize("msg", [
        "hacen fotos durante la inmersión?",   # question, not booking intent
        "qué incluye la inmersión?",           # question about content
        "cuánto dura la inmersión?",           # question about duration
    ])
    def test_no_false_positive_on_inmersion_question(self, msg):
        result = detect(msg)
        assert result != "certified_diving", f"Unexpected certified_diving for: {msg!r}"


# ---------------------------------------------------------------------------
# minicourse — variants
# ---------------------------------------------------------------------------

class TestMinicourseVariants:
    @pytest.mark.parametrize("msg", [
        "quiero hacer el minicurso",     # exact
        "quiero hacer mini curso",       # with space
        "quiero hacer mini-curso",       # with hyphen
        "quiero hacer un bautismo",      # exact
        "quiero hacer un bautizo",       # common alternative
        "es mi primera vez buceando",    # first time
        "nunca he buceado",              # exact
        "nunca buceado en mi vida",      # without "he"
        "nunca ha buceado",              # third person (no sé bucear variant)
        "no sé bucear",                  # "I don't know how to dive"
        "no se bucear",                  # without accent
    ])
    def test_minicourse_detected(self, msg):
        assert detect(msg) == "minicourse", f"Expected minicourse for: {msg!r}"


# ---------------------------------------------------------------------------
# snorkel — typos and phonetic variants
# ---------------------------------------------------------------------------

class TestSnorkelTypos:
    @pytest.mark.parametrize("msg", [
        "quiero hacer snorkel",          # exact
        "quiero hacer snorkeling",       # English form
        "quiero hacer snorkle",          # transposed 'le'
        "quiero hacer esnorkel",         # Spanish phonetic variant
        "quiero hacer esnorquel",        # Spanish phonetic variant alt
        "quiero hacer snorqueling",      # mixed phonetic
        "quiero hacer snorquel",         # another phonetic
        "queremos careteo",              # exact synonym
        "queremos caretear",             # verb form
    ])
    def test_snorkel_detected(self, msg):
        assert detect(msg) == "snorkel", f"Expected snorkel for: {msg!r}"


# ---------------------------------------------------------------------------
# Precedence: minicourse before certified_diving
# ---------------------------------------------------------------------------

class TestMinicourseBeforeCertifiedDiving:
    """Minicourse patterns are checked first — messages that contain BOTH
    certified-sounding words and beginner indicators should go to minicourse."""

    def test_bautismo_wins_over_buceo(self):
        assert detect("quiero hacer bautismo de buceo") == "minicourse"

    def test_primera_vez_wins_over_buceo(self):
        assert detect("es mi primera vez haciendo buceo") == "minicourse"

    def test_nunca_buceado_wins_over_buceo_mention(self):
        assert detect("nunca he buceado, quiero intentar bucear") == "minicourse"
