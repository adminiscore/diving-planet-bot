"""mej-5 (21-oct): precios de los modelos de OpenAI, para calcular el coste de una ronda con sus métricas de tokens.

OpenRouter ya devuelve el coste de cada llamada ("usd" en las métricas); OpenAI no, así que se calcula con esta tabla.
Los precios cambian: cuando se actualicen, cambiad también FECHA y FUENTE.
"""

FECHA = "2026-10-21"
FUENTE = "developers.openai.com/api/docs/pricing (contexto corto, precio estándar; consultado por Gadea a las 16:20)"

# USD por millón de tokens: (entrada, entrada en caché, salida).
PRECIOS_OPENAI: dict[str, tuple[float, float, float]] = {
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5": (1.25, 0.125, 10.00),
    "gpt-4.1": (2.00, 0.50, 8.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
}


def coste_openai(modelo: str | None, entrada: int = 0, cache: int = 0, salida: int = 0) -> float | None:
    """(entrada − caché) × precio de entrada + caché × precio de caché + salida × precio de salida, en dólares.
    None si el modelo no está en la tabla."""
    precio = PRECIOS_OPENAI.get(modelo or "")
    if precio is None:
        return None
    p_in, p_cache, p_out = precio
    cache = min(cache or 0, entrada or 0)
    return ((entrada or 0) - cache) * p_in / 1e6 + cache * p_cache / 1e6 + (salida or 0) * p_out / 1e6
