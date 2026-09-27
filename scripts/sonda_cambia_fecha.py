"""Banco de calibración de la pregunta de Jev `changes_date` (paso 6, s4-6, flag `s4_fixes`, 27-sep).

Positivos: cambios de fecha. Negativos: lo que la señal del router confundía con reprogramar mientras
se arma el carrito ("do it for 3 days instead", "en realidad somos 4") y fechas dichas o preguntadas
por primera vez.

    python -m scripts.sonda_cambia_fecha
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from scripts.sonda_afirma_vs_pregunta import _preguntar  # noqa: E402
from src.agents import jev_router  # noqa: E402

POSITIVOS = [
    "espera, mejor cambiemos la fecha",
    "can we move it to Sunday instead of Saturday?",
    "al final no podemos el 12, ¿puede ser el 14?",
    "mejor pásalo para la semana siguiente",
    "necesito cambiar el día del buceo",
    "Actually we'd prefer the 20th rather than the 18th",
    "¿Se puede correr para el viernes?",
    "we need to change the date, something came up",
]
NEGATIVOS = [
    "do it for 3 days instead",
    "mejor 3 días",
    "en realidad somos 4",
    "cámbialo a snorkel",
    "mejor el paquete de 5 inmersiones",
    "vamos el 20 de julio",
    "¿hay salidas el 24 de abril?",
    "Exactamente entre el 20 y 22 de julio",
    "We want to dive on April 5 and 6",
    "¿Tienen disponibilidad el sábado?",
    "Me dijiste que a las 7:30 am",
    "¿Cuál es la política para cambiar la fecha?",
]
N = 2


async def main() -> None:
    q = jev_router._CHANGES_DATE_Q["instructions"]
    async with httpx.AsyncClient() as cli:
        async def score(m):
            vals = [await _preguntar(cli, m, q) for _ in range(N)]
            return sum(vals) / len(vals)
        pos = await asyncio.gather(*(score(m) for m in POSITIVOS))
        neg = await asyncio.gather(*(score(m) for m in NEGATIVOS))
    for label, msgs, vals in (("POS", POSITIVOS, pos), ("NEG", NEGATIVOS, neg)):
        for m, v in sorted(zip(msgs, vals), key=lambda x: x[1]):
            print(f"{label} {v:.2f}  {m[:90]}")
    t = jev_router.CHANGES_DATE_MIN
    print(f"\numbral {t}: positivos {sum(v >= t for v in pos)}/{len(pos)}, "
          f"falsas alarmas {sum(v >= t for v in neg)}/{len(neg)}")


if __name__ == "__main__":
    asyncio.run(main())
