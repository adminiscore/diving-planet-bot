"""Causa 4 del análisis del juez (`docs/robustness/juez/README.md`): ¿por qué el juez rechaza "no lo tengo a la
mano, un asesor te lo confirma", si su prompt dice que eso no es un dato del negocio?

El juez real (gpt-4.1) con el catálogo que ve en PRE (`para_el_juez`), N=5 por frase. Variantes de la misma frase:
sola, con el tema genérico y con el tema concreto que nombran las respuestas rechazadas en las rondas.

    python -m scripts.sonda_juez_asesor
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agents.grounding_check import is_grounded  # noqa: E402
from src.flows.catalog import catalog_booking_links, catalog_facts, para_el_juez  # noqa: E402

FRASES = {
    "sola": "Ese detalle puntual no lo tengo a la mano, pero un asesor puede confirmártelo sin problema.",
    "tema generico": "Sobre eso, ese detalle puntual no lo tengo a la mano, pero un asesor puede confirmártelo.",
    "tema: transferencia": "Sobre si hay descuento por pagar por transferencia, ese detalle puntual no lo tengo a la mano, "
                           "pero un asesor puede confirmártelo.",
    "tema: precio exacto": "El precio exacto y el descuento online te lo puede confirmar un asesor.",
    "tema: metodos de pago": "I can connect you with an advisor to confirm the payment methods available.",
    "tema: acompanante islas": "Sobre el pago y detalles específicos para acompañantes en las islas, ese dato puntual no lo "
                               "tengo a la mano, pero un asesor puede confirmártelo.",
    "negativa deducible": "El pago por transferencia no tiene un descuento especial.",
}
N = 5


async def main() -> None:
    ctx = para_el_juez(catalog_facts("es") + "\n" + catalog_booking_links("es"), "es")
    for nombre, frase in FRASES.items():
        lang = "en" if frase.startswith("I can") else "es"
        res = await asyncio.gather(*(is_grounded(frase, ctx, lang) for _ in range(N)))
        ok = sum(g for g, _ in res)
        motivo = next((m for g, m in res if not g), "")
        print(f"{nombre:24s} aceptada {ok}/{N}  {motivo[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
