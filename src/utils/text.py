"""Normalizacion de texto compartida (solo stdlib)."""

from __future__ import annotations

import unicodedata


def strip_accents(text: str) -> str:
    """Quita tildes y diacriticos sin tocar mayusculas ("está" -> "esta").

    No pasa a minusculas a proposito: tambien se aplica a patrones regex, donde
    `\\W` y `\\w` no significan lo mismo."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    )
