"""Unit tests for src/utils/fuzzy.py — typo-tolerant input matching."""

import pytest
from src.utils.fuzzy import (
    is_back,
    is_affirmative,
    is_negative,
    is_agree,
    is_none_selection,
    fuzzy_word_number,
)


# ---------------------------------------------------------------------------
# is_back
# ---------------------------------------------------------------------------

class TestIsBack:
    @pytest.mark.parametrize("msg", [
        "back", "cancel", "cancelar", "volver", "atras", "atrás", "salir",
    ])
    def test_exact_matches(self, msg):
        assert is_back(msg)

    @pytest.mark.parametrize("msg", [
        "bak",           # missing 'c'
        "cancellar",     # double 'l'
        "cancell",       # double 'l' truncated
        "Cancelar",      # uppercase
        "BACK",          # all caps
        " back ",        # spaces
        "volveer",       # double 'e'
    ])
    def test_typos(self, msg):
        assert is_back(msg), f"Expected is_back({msg!r}) to be True"

    @pytest.mark.parametrize("msg", [
        "si", "sí", "yes", "no", "ok", "buceo", "snorkel", "hola",
        "1", "2", "tres",
    ])
    def test_no_false_positives(self, msg):
        assert not is_back(msg), f"Expected is_back({msg!r}) to be False"


# ---------------------------------------------------------------------------
# is_affirmative
# ---------------------------------------------------------------------------

class TestIsAffirmative:
    @pytest.mark.parametrize("msg", [
        "si", "sí", "yes", "sip", "yep", "yeah",
    ])
    def test_exact_matches(self, msg):
        assert is_affirmative(msg)

    @pytest.mark.parametrize("msg", [
        "sii",    # double 'i' — most common WhatsApp typo
        "sii!",   # with punctuation
        " sí ",   # spaces
        "Sí",     # uppercase
        "YES",    # caps
        "yess",   # double 's'
        "yeap",   # common variant
    ])
    def test_typos(self, msg):
        assert is_affirmative(msg), f"Expected is_affirmative({msg!r}) to be True"

    @pytest.mark.parametrize("msg", [
        "no", "nope", "2", "back", "cancel", "buceo",
        # 2-char strings that could be confused — must NOT match
        "so", "sa", "ia",
    ])
    def test_no_false_positives(self, msg):
        assert not is_affirmative(msg), f"Expected is_affirmative({msg!r}) to be False"


# ---------------------------------------------------------------------------
# is_negative
# ---------------------------------------------------------------------------

class TestIsNegative:
    @pytest.mark.parametrize("msg", [
        "no", "nope", "nop",
    ])
    def test_exact_matches(self, msg):
        assert is_negative(msg)

    @pytest.mark.parametrize("msg", [
        "nno",   # double 'n'
        "noo",   # double 'o'
        "NO",    # caps
        " no ",  # spaces
        "nopee", # double 'e'
    ])
    def test_typos(self, msg):
        assert is_negative(msg), f"Expected is_negative({msg!r}) to be True"

    @pytest.mark.parametrize("msg", [
        "si", "sí", "yes", "1", "ok", "back", "buceo",
        # 2-char strings that could be confused
        "mi", "lo", "de",
    ])
    def test_no_false_positives(self, msg):
        assert not is_negative(msg), f"Expected is_negative({msg!r}) to be False"


# ---------------------------------------------------------------------------
# is_agree
# ---------------------------------------------------------------------------

class TestIsAgree:
    @pytest.mark.parametrize("msg", [
        "si", "sí", "yes", "ok", "okey", "k", "vale",
        "start", "empezar", "claro", "venga", "dale", "vamos",
    ])
    def test_exact_matches(self, msg):
        assert is_agree(msg)

    @pytest.mark.parametrize("msg", [
        "sii",      # typo of "sí"
        "okk",      # double 'k'  — "okk" len=3 vs "ok" len=2 → fuzzy needed
        "valee",    # double 'e'
        "vamoss",   # double 's'
        "empezarr", # double 'r'
        "cllaro",   # double 'l'
        "Ok",       # uppercase
    ])
    def test_typos(self, msg):
        assert is_agree(msg), f"Expected is_agree({msg!r}) to be True"

    @pytest.mark.parametrize("msg", [
        "no", "nope", "back", "cancelar", "buceo", "2",
    ])
    def test_no_false_positives(self, msg):
        assert not is_agree(msg), f"Expected is_agree({msg!r}) to be False"


# ---------------------------------------------------------------------------
# is_none_selection
# ---------------------------------------------------------------------------

class TestIsNoneSelection:
    @pytest.mark.parametrize("msg", [
        "0", "ninguno", "ninguna", "none", "no",
    ])
    def test_exact_matches(self, msg):
        assert is_none_selection(msg)

    @pytest.mark.parametrize("msg", [
        "ningun",   # truncated
        "ningunn",  # double 'n'
        "Ninguno",  # uppercase
        "NONE",     # caps
    ])
    def test_typos(self, msg):
        assert is_none_selection(msg), f"Expected is_none_selection({msg!r}) to be True"

    @pytest.mark.parametrize("msg", [
        "si", "yes", "1", "back", "tres", "cuatro",
    ])
    def test_no_false_positives(self, msg):
        assert not is_none_selection(msg), f"Expected is_none_selection({msg!r}) to be False"


# ---------------------------------------------------------------------------
# fuzzy_word_number
# ---------------------------------------------------------------------------

class TestFuzzyWordNumber:
    @pytest.mark.parametrize("msg,expected", [
        ("uno", 1), ("una", 1), ("one", 1),
        ("dos", 2), ("two", 2),
        ("tres", 3), ("three", 3),
        ("cuatro", 4), ("four", 4),
        ("cinco", 5), ("five", 5),
        ("seis", 6), ("six", 6),
        ("siete", 7), ("seven", 7),
        ("ocho", 8), ("eight", 8),
        ("nueve", 9), ("nine", 9),
        ("diez", 10), ("ten", 10),
    ])
    def test_exact_matches(self, msg, expected):
        assert fuzzy_word_number(msg) == expected

    @pytest.mark.parametrize("msg,expected", [
        ("doss", 2),    # double 's'
        ("tre", 3),     # missing 's'
        ("cuatr", 4),   # missing 'o'
        ("cico", 5),    # missing 'n'  — "cico" vs "cinco": ratio=2*4/9≈0.89 ✓
        ("siet", 7),    # missing 'e'
        ("occho", 8),   # double 'c'
        ("nuev", 9),    # missing 'e'
        ("diex", 10),   # 'x' instead of 'z'
    ])
    def test_typos(self, msg, expected):
        result = fuzzy_word_number(msg)
        assert result == expected, f"fuzzy_word_number({msg!r}) = {result}, expected {expected}"

    @pytest.mark.parametrize("msg", [
        "hola", "buceo", "si", "no", "ok", "back",
        "1", "2",  # digits handled separately — not by word parser
        "xy",      # too short and no match
    ])
    def test_returns_none_for_non_numbers(self, msg):
        assert fuzzy_word_number(msg) is None, f"Expected None for {msg!r}"


# ---------------------------------------------------------------------------
# Integration: yes/no in conversation context
# ---------------------------------------------------------------------------

class TestConversationalTypos:
    """Simulate the most common real WhatsApp typos reported in production."""

    def test_sii_is_affirmative(self):
        assert is_affirmative("sii")

    def test_nno_is_negative(self):
        assert is_negative("nno")

    def test_cancellar_is_back(self):
        assert is_back("cancellar")

    def test_doss_is_two(self):
        assert fuzzy_word_number("doss") == 2

    def test_cuatr_is_four(self):
        assert fuzzy_word_number("cuatr") == 4

    def test_back_does_not_match_affirmative(self):
        assert not is_affirmative("back")
        assert not is_affirmative("cancel")

    def test_affirmative_does_not_match_back(self):
        assert not is_back("si")
        assert not is_back("sii")
        assert not is_back("yes")

    def test_negative_does_not_match_back(self):
        assert not is_back("no")
        assert not is_back("nno")
