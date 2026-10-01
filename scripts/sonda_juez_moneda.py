"""Banco del juez para la regla de moneda y el acompañante (análisis del 1-oct, `docs/robustness/juez/README.md`).

El juez de grounding de verdad (gpt-4.1), con el catálogo que ve en PRE (`para_el_juez`), sobre respuestas que
SÍ se apoyan en el catálogo (deben pasar) y respuestas inventadas (deben rechazarse). N=3 por respuesta.

    python -m scripts.sonda_juez_moneda
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agents.grounding_check import is_grounded  # noqa: E402
from src.flows.catalog import catalog_booking_links, catalog_facts, para_el_juez  # noqa: E402

ORIGEN = ("\nOrigen: si el contexto no dice desde dónde sale el cliente, da el precio desde Cartagena y el de 'ya en "
          "las islas', cada uno rotulado, o pregúntale desde dónde saldría.")
BIEN = [
    "Para colombianos, el paquete de 5 inmersiones cuesta 1.429.000 COP si reservas online con el 10% de descuento, "
    "o 1.587.000 COP en tarifa normal.",
    "Para colombianos, el Curso Básico PADI (Open Water) tiene un costo de 2.450.000 COP si reservas online con el "
    "10% de descuento, o 2.722.000 COP si reservas normal.",
    "El detalle exacto del costo para colombianos te lo puede confirmar un asesor con gusto.",
    "Si eres residente en Colombia, pagas en pesos colombianos (COP), igual que los colombianos.",
    "El acompañante, si ya están en las islas, cuesta 80 USD (288.000 COP) online; incluye seguro y entrada al "
    "parque, sin almuerzo.",
]
MAL = [
    "Para colombianos hay un 20% de descuento: el paquete de 5 inmersiones queda en 1.143.000 COP.",
    "Los colombianos tienen una tarifa especial más barata en todos los planes.",
    "El costo para acompañante es 50 USD (167.000 COP) si ya están en las islas.",
    "Si ya están en las islas, el plan de acompañante incluye el almuerzo.",
]
N = 3


async def main() -> None:
    ctx = para_el_juez(catalog_facts("es") + ORIGEN + "\n" + catalog_booking_links("es"), "es")
    for grupo, respuestas in (("BIEN", BIEN), ("MAL", MAL)):
        for r in respuestas:
            res = await asyncio.gather(*(is_grounded(r, ctx, "es") for _ in range(N)))
            ok = sum(g for g, _ in res)
            print(f"{grupo} aceptada {ok}/{N}  {r[:90]}")


if __name__ == "__main__":
    asyncio.run(main())
