"""Calibración de J2 (`src/agents/juez_segunda_opinion.py`): ¿Jev distingue las frases que afirman algo del negocio
de las que solo dicen "no lo tengo", ofrecen un asesor o son cortesía?

Banco: `docs/robustness/juez/frases-etiquetas.json` (frases que el juez v3 marcó NO, etiquetadas a mano antes).
Condición dura: NINGUNA frase "afirma" puede quedar por debajo del umbral (sería un invento que pasa). Se mira el
peor caso de las repeticiones: para "afirma", la p más baja; para "no_afirma", la más alta.

    python -m scripts.sonda_juez_jev
"""
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agents import juez_segunda_opinion as j2  # noqa: E402

N = 2


async def main() -> None:
    frases = json.loads(Path("docs/robustness/juez/frases-etiquetas.json").read_text(encoding="utf-8"))["frases"]
    sem = asyncio.Semaphore(8)

    async def p(f):
        async with sem:
            return await j2.afirma(f)

    res = await asyncio.gather(*(asyncio.gather(*(p(x["frase"]) for _ in range(N))) for x in frases))
    for grupo in ("diseño", "ciego"):
        print(f"===== {grupo}")
        filas = [(x, r) for x, r in zip(frases, res, strict=True) if x["grupo"] == grupo]
        for x, r in sorted(filas, key=lambda t: (t[0]["etiqueta"], min(v or 0 for v in t[1]))):
            peor = min(r) if x["etiqueta"] == "afirma" else max(r)
            print(f"  {x['etiqueta']:9s} {peor:.2f} [{' '.join(f'{v:.2f}' for v in r)}]  {x['frase'][:100]}")
        for umbral in (0.1, 0.2, 0.3):
            fugas = sum(min(r) < umbral for x, r in filas if x["etiqueta"] == "afirma")
            pasan = sum(max(r) < umbral for x, r in filas if x["etiqueta"] == "no_afirma")
            tot_na = sum(1 for x, _ in filas if x["etiqueta"] == "no_afirma")
            print(f"  umbral {umbral}: inventos/datos que pasarían {fugas} · 'no lo tengo/asesor' rescatadas {pasan}/{tot_na}")


if __name__ == "__main__":
    asyncio.run(main())
