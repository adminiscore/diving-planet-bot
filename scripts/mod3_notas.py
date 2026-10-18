"""mod-3, notas (NOTAS_MODEL): el extractor de notas con los casos etiquetados de scripts/sonda_notas.py.

POSITIVOS (diseño + ciegos): debe apuntar algo. NEGATIVOS: no debe apuntar nada (cada nota es basura: la pregunta del
cliente, un invento o un dato de la reserva). 3 pasadas; cuenta los casos con nota en las 3, en alguna y en ninguna.
"""
import asyncio
import os
import sys
import time

os.environ.setdefault("ENV_FILE", ".env.dev")
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts import sonda_notas as s  # noqa: E402
from src.agents.notes_extractor import extract_notes  # noqa: E402
from src.config import settings  # noqa: E402


def _texto(c):
    return c[0] if isinstance(c, (tuple, list)) else (c.get("message") if isinstance(c, dict) else c)


async def main():
    pasadas = 3
    grupos = {"POS": [*s.POSITIVOS_DISENO, *s.POSITIVOS_CIEGOS], "NEG": list(s.NEGATIVOS)}
    tiempos, res = [], {}
    for g, casos in grupos.items():
        res[g] = []
        for c in casos:
            m = _texto(c)
            lang = "en" if any(w in f" {m.lower()} " for w in (" the ", " i ", " we ", " you ", " is ")) else "es"

            async def una(m=m, lang=lang):
                t0 = time.perf_counter()
                notas = await extract_notes(m, lang=lang)
                tiempos.append(time.perf_counter() - t0)
                return notas

            notas = await asyncio.gather(*[una() for _ in range(pasadas)])
            res[g].append((m, [len(n) > 0 for n in notas], notas))
    pos, neg = res["POS"], res["NEG"]
    pos_ok = sum(all(v) for _, v, _ in pos)
    neg_ok = sum(not any(v) for _, v, _ in neg)
    tiempos.sort()
    print(f"MODELO {settings.notas_model}: positivos con nota 3/3 {pos_ok}/{len(pos)} | negativos sin nota 3/3 "
          f"{neg_ok}/{len(neg)} | p50 {tiempos[len(tiempos) // 2]:.2f} s")
    for m, v, n in pos:
        if not all(v):
            print(f"   POS perdido {sum(v)}/3: {m[:80]!r}")
    for m, v, n in neg:
        if any(v):
            print(f"   NEG basura {sum(v)}/3: {m[:60]!r} -> {next(x for x in n if x)[:2]}")


asyncio.run(main())
