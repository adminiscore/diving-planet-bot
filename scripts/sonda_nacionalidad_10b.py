"""CALN-10b: ¿leer la nacionalidad dos veces y quedarse con ella solo si las dos lecturas coinciden la hace más fiable?
Banco ex0 (diseño): los casos que esperan is_colombian, más una muestra de los que no la dicen (para contar inventos), más
dos frases del sparring. Cada caso ×N con el extractor de siempre; la variante 10b se arma con las lecturas de dos en dos
(si no coinciden, null: el bot pregunta). Uso: python scripts/sonda_nacionalidad_10b.py [pasadas=12] [muestra=15]"""
import asyncio
import random
import sys
from collections import Counter

sys.path.insert(0, ".")
from scripts.run_extraction_eval import casos_ex0
from src.agents import extractor_turno as et

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
MUESTRA = int(sys.argv[2]) if len(sys.argv) > 2 else 15
PROPIOS = [  # frases del sparring s29c; lo esperado sigue la política de la moneda (policies.json, colombian_pricing)
    {"id": "cali", "lang": "es", "esperado": True,
     "message": "Buenas, una amiga hizo el minicurso con ustedes hace un año y le costó 500.000 pesos. Sigue igual? Soy de Cali y salgo de Cartagena"},
    {"id": "nacio-madrid", "lang": "es", "esperado": None,
     "message": "Hola! Nací en Colombia pero vivo en Madrid desde pequeña. Cuánto cuesta el snorkel desde Cartagena? Pago en pesos?"},
]


def _casos() -> list[dict]:
    todos = casos_ex0("diseño")
    con = [{**c, "esperado": c["expected"]["is_colombian"]} for c in todos if "is_colombian" in (c.get("expected") or {})]
    sin = [c for c in todos if "is_colombian" not in (c.get("expected") or {}) and (c.get("sabido") or {}).get("is_colombian") is None]
    sin = [{**c, "esperado": None} for c in random.Random(10).sample(sin, min(MUESTRA, len(sin)))]
    return con + sin + PROPIOS


def _clase(leido, esperado) -> str:
    if leido == esperado:
        return "bien"
    if esperado is None:
        return "inventa"  # da la nacionalidad sin que el cliente la diga
    return "pregunta" if leido is None else "equivocada"  # equivocada = precio en la moneda que no es


async def main() -> int:
    casos = _casos()
    sem = asyncio.Semaphore(8)

    async def una(c):
        async with sem:
            d = await et.extraer_turno(c["message"], history=c.get("history"), sabido=c.get("sabido") or {}, lang=c["lang"])
            return (d or {}).get("is_colombian")

    lecturas = await asyncio.gather(*[asyncio.gather(*[una(c) for _ in range(N)]) for c in casos])
    sola, doble = Counter(), Counter()
    for c, ls in zip(casos, lecturas, strict=True):
        for x in ls:
            sola[_clase(x, c["esperado"])] += 1
        for a, b in zip(ls[0::2], ls[1::2], strict=True):
            doble[_clase(a if a == b else None, c["esperado"])] += 1
        if len(set(map(repr, ls))) > 1:
            print(f"  varía: {c['id']:55} esperado {c['esperado']!r:5}  {dict(Counter(map(repr, ls)))}")
    for nombre, t in (("una lectura", sola), ("dos que coinciden (10b)", doble)):
        n = sum(t.values())
        print(f"{nombre:24} n={n:3}  " + "  ".join(f"{k} {t[k]} ({100 * t[k] / n:.1f} %)" for k in ("bien", "equivocada", "inventa", "pregunta")))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
