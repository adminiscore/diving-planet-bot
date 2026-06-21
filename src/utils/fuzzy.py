"""Fuzzy matching helpers for structured user inputs.

Used to tolerate common typos in navigation commands (yes/no, cancel, numbers).
Relies only on stdlib `difflib` — no extra dependencies.

Rules:
- Exact match is always tried first; fuzzy only enters on miss.
- Strings ≤ 2 chars → exact match only (avoids false positives on "si"/"no").
- Strings 3–4 chars → ratio ≥ 0.72  ("sii"→"si", "bak"→"back", "doss"→"dos").
- Strings ≥ 5 chars → ratio ≥ 0.82  ("cancellar"→"cancelar").
- Proper nouns and arbitrary content are never passed here — only known command words.
"""

from __future__ import annotations
import re as _re
from difflib import SequenceMatcher

# Strip punctuation that users append to command words ("sii!", "cancelar.")
_PUNCT = _re.compile(r"[¿¡?!.,;:()\[\]\"'/\\]")


# ---------------------------------------------------------------------------
# Canonical command sets
# ---------------------------------------------------------------------------

_BACK: frozenset[str] = frozenset({
    "back", "cancel", "cancelar", "volver", "atras", "atrás", "salir",
})

# Strict yes — for binary yes/no questions only
_YES: frozenset[str] = frozenset({
    "si", "sí", "yes", "sip", "yep", "yeah",
})

# Strict no — for binary yes/no questions only
_NO: frozenset[str] = frozenset({
    "no", "nope", "nop",
})

# Broad agreement — "I want to proceed / start / ok"
_AGREE: frozenset[str] = frozenset({
    "si", "sí", "yes", "sip", "yep", "yeah",
    "ok", "okey", "k", "vale", "start", "empezar",
    "claro", "venga", "dale", "vamos", "adelante",
})

# "None / zero" selection (e.g. "ninguno de ellos")
_NONE_ZERO: frozenset[str] = frozenset({
    "0", "ninguno", "ninguna", "none", "no",
})

# Word → integer mapping (1–10, ES + EN)
_WORD_NUMBERS: dict[str, int] = {
    "uno": 1, "una": 1, "one": 1,
    "dos": 2, "two": 2,
    "tres": 3, "three": 3,
    "cuatro": 4, "four": 4,
    "cinco": 5, "five": 5,
    "seis": 6, "six": 6,
    "siete": 7, "seven": 7,
    "ocho": 8, "eight": 8,
    "nueve": 9, "nine": 9,
    "diez": 10, "ten": 10,
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_CUTOFF_SHORT = 0.72   # 3–4 char strings
_CUTOFF_LONG  = 0.82   # 5+ char strings
_MIN_FUZZY    = 3      # strings shorter than this: exact match only


# ---------------------------------------------------------------------------
# Core matching primitive
# ---------------------------------------------------------------------------

def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_in(value: str, candidates: frozenset[str]) -> bool:
    """Return True if *value* exactly or fuzzily matches any candidate.

    Short strings (< _MIN_FUZZY chars) are compared by exact match only to
    avoid false positives between 2-char words like "si" / "no" / "ok".
    """
    v = _PUNCT.sub("", value).strip().lower()
    if v in candidates:
        return True
    n = len(v)
    if n < _MIN_FUZZY:
        return False
    cutoff = _CUTOFF_SHORT if n <= 4 else _CUTOFF_LONG
    return any(
        _ratio(v, c) >= cutoff
        for c in candidates
        if len(c) >= _MIN_FUZZY - 1   # skip 1-char candidates like "k"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_back(msg: str) -> bool:
    """True if msg means 'go back / cancel'  (e.g. 'cancellar', 'bak')."""
    return _fuzzy_in(msg, _BACK)


def is_affirmative(msg: str) -> bool:
    """True if msg is a strict yes answer  (e.g. 'sii', 'yess', 'sip')."""
    return _fuzzy_in(msg, _YES)


def is_negative(msg: str) -> bool:
    """True if msg is a strict no answer  (e.g. 'nno', 'nope')."""
    return _fuzzy_in(msg, _NO)


def is_agree(msg: str) -> bool:
    """True if msg signals general agreement/proceed  ('ok', 'vale', 'sii', 'dale')."""
    return _fuzzy_in(msg, _AGREE)


def is_none_selection(msg: str) -> bool:
    """True if msg means 'none / zero'  ('ninguno', 'ninguna', 'none', '0')."""
    return _fuzzy_in(msg, _NONE_ZERO)


def fuzzy_word_number(msg: str) -> int | None:
    """Parse a word number (uno–diez / one–ten) with typo tolerance.

    Returns int 1–10 or None.  Always tries exact match first.
    Examples: 'doss' → 2,  'tre' → 3,  'cuatr' → 4,  'nuev' → 9.
    """
    v = msg.strip().lower()
    if v in _WORD_NUMBERS:
        return _WORD_NUMBERS[v]
    if len(v) < _MIN_FUZZY:
        return None
    cutoff = _CUTOFF_SHORT if len(v) <= 4 else _CUTOFF_LONG
    best_ratio, best_val = 0.0, None
    for word, val in _WORD_NUMBERS.items():
        r = _ratio(v, word)
        if r > best_ratio:
            best_ratio, best_val = r, val
    return best_val if best_ratio >= cutoff else None
