"""La moneda del precio, en UN sitio (lat-deuda-u, 26-oct; decisión de Gadea).

COP a colombianos y residentes en Colombia (también con cédula de extranjería); USD a los extranjeros y a un grupo
mixto (toda la reserva en USD, decisión del 14-sep); si no se sabe la nacionalidad, las DOS («el mismo precio, solo
cambia la moneda»). Hasta hoy convivían tres reglas para el cliente sin nacionalidad: las dos monedas en la tabla de
hechos (arq-5c, 23-oct), solo USD en el RAG (CAL-B, 15-oct) y una sola moneda en la tarjeta y la comparación del flujo
(G3-07a, 18-oct). Gadea eligió la de las dos monedas para todos los caminos.
"""
from __future__ import annotations

from src.utils import money


def monedas(state) -> tuple[str, ...]:
    """Las monedas en las que se le da el precio a este cliente."""
    if getattr(state, "mixed_nationality_notice", False):
        return ("USD",)
    colombiano = getattr(state, "is_colombian", None)
    if colombiano is True:
        return ("COP",)
    if colombiano is False:
        return ("USD",)
    return ("USD", "COP")


def precio(state, usd, cop, qty: int = 1) -> str | None:
    """El precio en su moneda («183 USD», «630.000 COP» o «183 USD / 630.000 COP»). Si falta la tarifa de su moneda,
    la otra; None si no hay ninguna."""
    formato = {"USD": money.usd(usd, qty), "COP": money.cop(cop, qty)}
    partes = [formato[m] for m in monedas(state) if formato[m]]
    if not partes:
        partes = [p for p in formato.values() if p][:1]
    return " / ".join(partes) or None
