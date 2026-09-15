"""Palabras numericas con una sola fuente (2026-09-15).

Habia una lista "dos|tres|cuatro..." copiada en el detector, el nucleo, el supervisor,
el RAG, el carrito y fuzzy, cada una con su rango. Ahora salen de
`src.utils.number_words`; cada consumidor conserva su rango y sus extras ("un", "otros").
"""

import re

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import AGE_WORDS
from src.flows import cart_render
from src.utils import fuzzy
from src.utils.number_words import number_alt, number_words


def test_ranges_and_languages():
    assert dict(number_words(1, 3)) == {"uno": 1, "una": 1, "one": 1, "dos": 2, "two": 2, "tres": 3, "three": 3}
    assert list(number_words(2, 4, "es")) == ["dos", "tres", "cuatro"]
    assert list(number_words(2, 4, "en")) == ["two", "three", "four"]
    assert number_words(16, 16, "es") == {"dieciseis": 16, "dieciséis": 16}


def test_longest_word_first_in_the_alternation():
    assert re.fullmatch(r"(?:" + number_alt(7, 17, "en") + r")", "seventeen")
    assert re.match(r"(?:" + number_alt(7, 17, "en") + r")", "seventeen").group(0) == "seventeen"


def test_consumers_share_the_source():
    assert dict(AGE_WORDS) == dict(number_words(2, 19))
    assert fuzzy._WORD_NUMBERS == core._WORD_TO_NUM == number_words(1, 10)


@pytest.mark.parametrize("message, qty", [("dos", 2), ("somos cuatro", 4), ("ten", 10), ("doss", 2)])
def test_quantity_parsing_unchanged(message, qty):
    assert cart_render.parse_quantity(message) == qty
