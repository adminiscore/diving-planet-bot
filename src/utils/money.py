"""Formato UNICO de precios para el cliente (owner 2026-09-14: "183 USD").

Antes habia cinco formateadores repartidos (RAG, catalogo, carrito, resumen
colombiano, refresher) con dos formatos de COP distintos ("COP 1.260.000" y
"630.000 COP"). Solo stdlib.

Regla de redondeo: se redondea el precio POR PERSONA y despues se multiplica, para
que la cuenta mostrada cuadre siempre ("2 × 126 USD = 252 USD", nunca 251).
"""

from __future__ import annotations


def _per_person(value) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def usd(value, qty: int = 1) -> str | None:
    """"183 USD" (o `qty` × por persona). None si no hay precio."""
    amount = _per_person(value)
    return f"{amount * qty} USD" if amount else None


def cop(value, qty: int = 1) -> str | None:
    """"630.000 COP" con punto de miles (o `qty` × por persona). None si no hay precio."""
    amount = _per_person(value)
    return f"{amount * qty:,} COP".replace(",", ".") if amount else None


def usd_cop(usd_value, cop_value, missing: str = "consultar") -> str:
    """"183 USD / 630.000 COP". Cada moneda que falte se sustituye por `missing`."""
    return f"{usd(usd_value) or missing} / {cop(cop_value) or missing}"
