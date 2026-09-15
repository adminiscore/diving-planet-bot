"""Palabras numericas ES/EN con una sola fuente (solo stdlib).

Cada consumidor elige su rango ("somos dos".."diez", edades 2-19, paquetes 1-9) y
anade en su sitio lo que no es un numero ("un", "otros", "varios", "couple").
"""

from __future__ import annotations

from functools import cache
from types import MappingProxyType

_ES = (
    ("uno", "una"), ("dos",), ("tres",), ("cuatro",), ("cinco",), ("seis",), ("siete",),
    ("ocho",), ("nueve",), ("diez",), ("once",), ("doce",), ("trece",), ("catorce",),
    ("quince",), ("dieciseis", "dieciséis"), ("diecisiete",), ("dieciocho",), ("diecinueve",),
)
_EN = (
    ("one",), ("two",), ("three",), ("four",), ("five",), ("six",), ("seven",), ("eight",),
    ("nine",), ("ten",), ("eleven",), ("twelve",), ("thirteen",), ("fourteen",), ("fifteen",),
    ("sixteen",), ("seventeen",), ("eighteen",), ("nineteen",),
)
_BY_LANG = {"es": (_ES,), "en": (_EN,), None: (_ES, _EN)}


@cache
def number_words(lo: int = 1, hi: int = 19, lang: str | None = None) -> MappingProxyType:
    """Palabra -> valor entre `lo` y `hi`, de menor a mayor valor y, en cada valor, ES
    antes que EN. `lang` "es"/"en" limita a un idioma."""
    words = {}
    for n in range(lo, hi + 1):
        for table in _BY_LANG[lang]:
            words.update(dict.fromkeys(table[n - 1], n))
    return MappingProxyType(words)


@cache
def number_alt(lo: int = 1, hi: int = 19, lang: str | None = None) -> str:
    """Alternancia regex de `number_words`, la palabra mas larga primero para que
    "seventeen" no se quede en "seven"."""
    return "|".join(sorted(number_words(lo, hi, lang), key=len, reverse=True))
