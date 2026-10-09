"""s4-33 (9-oct): el revisor de grounding contra el banco de juicios REALES de PRE etiquetado con Gadea.

Banco: las 142 respuestas (ya escritas por Luna) con su contexto entero (`docs/robustness/juez/s4-33/
juicios-reales-142.jsonl`) y su etiqueta (`etiquetas-142.json`): "invento" = debe rechazarse; "falso" y "aprobada" =
deben pasar; "dudoso" no cuenta; "fuera-contexto" (cierto, pero el contexto del juez no lo trae) no cuenta para
ajustar y se informa aparte: rechazarlo es lo correcto para un juez de grounding. Grupos por DIÁLOGO (las versiones CONS-/CONS2-/ON-/V2- del mismo diálogo van al mismo):
`sha1(diálogo) % 2`, fijado antes de medir. Diseño = 1 (4 inventos, 23 verdades), ciego = 0 (1 invento, 15 verdades).
Ajustar SOLO mirando el diseño; el ciego se mide al final sin tocar nada. Como el ciego tiene un solo invento, comprobar
también el banco del 1-oct (`scripts.sonda_juez_modelo --grupo ciego`), que tiene 18.

    python -m scripts.banco_juez_reales --modelo gpt-6-luna --flag juez_v3_luna --grupo diseño --detalle
    python -m scripts.banco_juez_reales --modelo gpt-4.1                                  # el de PRE, de referencia

Los inventos y las verdades se juzgan `--reps` veces (el juez no es determinista); las aprobadas, una.
Corre en local (`.env.dev`).
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")

from src.agents import grounding_check  # noqa: E402
from src.config import settings  # noqa: E402

DIR = Path("docs/robustness/juez/s4-33")
GRUPOS = {1: "diseño", 0: "ciego"}


def dialogo(origen: str) -> str:
    return re.sub(r"^(CONS2?|ON|V2)-", "", origen.rsplit(" t", 1)[0])


def grupo(origen: str) -> str:
    return GRUPOS[int(hashlib.sha1(dialogo(origen).encode()).hexdigest(), 16) % 2]


def banco() -> list[dict]:
    filas = [json.loads(ln) for ln in (DIR / "juicios-reales-142.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    etiquetas = {v["i"]: v["etiqueta"] for v in json.loads((DIR / "etiquetas-142.json").read_text(encoding="utf-8"))["etiquetas"].values()}
    out = []
    for i, f in enumerate(filas):
        if etiquetas[i] == "dudoso":
            continue
        lang = "en" if any(w in f["answer"].lower() for w in (" the ", " you ", " and ")) else "es"
        out.append({"i": i, "origen": f["origen"], "grupo": grupo(f["origen"]), "etiqueta": etiquetas[i], "lang": lang,
                    "answer": f["answer"], "context": f["context"]})
    return out


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--modelo", default=settings.grounding_v3_model)
    ap.add_argument("--flag", action="append", default=[], help="interruptor de settings a encender (repetible)")
    ap.add_argument("--ajuste", action="append", default=[], metavar="CLAVE=VALOR", help="ajuste de settings (texto)")
    ap.add_argument("--grupo", choices=("diseño", "ciego", "todos"), default="diseño")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--detalle", action="store_true", help="imprime cada juicio equivocado con lo que marcó NO")
    ap.add_argument("--concurrencia", type=int, default=6)
    a = ap.parse_args()
    settings.grounding_v3_model = a.modelo
    for f in a.flag:
        setattr(settings, f, True)
    for kv in a.ajuste:
        k, v = kv.split("=", 1)
        setattr(settings, k, v)

    items = [x for x in banco() if a.grupo == "todos" or x["grupo"] == a.grupo]
    sem = asyncio.Semaphore(a.concurrencia)
    tiempos: list[float] = []

    async def uno(x: dict) -> list[tuple[bool, str]]:
        reps = 1 if x["etiqueta"] in ("aprobada", "fuera-contexto") else a.reps
        out = []
        for _ in range(reps):
            async with sem:
                t = time.perf_counter()
                out.append(await grounding_check.is_grounded(x["answer"], x["context"], x["lang"]))
                tiempos.append(time.perf_counter() - t)
        return out

    resultados = await asyncio.gather(*(uno(x) for x in items))
    print(f"{a.modelo} {a.flag} {a.ajuste} · grupo {a.grupo} · {len(items)} respuestas")
    for g in ("diseño", "ciego"):
        tabla = {"invento": [0, 0], "falso": [0, 0], "aprobada": [0, 0], "fuera-contexto": [0, 0]}
        for x, rs in zip(items, resultados):
            if x["grupo"] == g:
                for ok, _ in rs:
                    tabla[x["etiqueta"]][0] += ok
                    tabla[x["etiqueta"]][1] += 1
        if any(n for _, n in tabla.values()):
            print(f"  {g:6}: inventos que deja pasar {tabla['invento'][0]}/{tabla['invento'][1]} (mejor 0) · "
                  f"verdades que pasan {tabla['falso'][0]}/{tabla['falso'][1]} · "
                  f"aprobadas que pasan {tabla['aprobada'][0]}/{tabla['aprobada'][1]} (mejor todas) · "
                  f"[fuera de contexto que pasan {tabla['fuera-contexto'][0]}/{tabla['fuera-contexto'][1]}, no cuenta]")
    print(f"  tiempo por juicio: mediana {statistics.median(tiempos):.2f}s · p90 {sorted(tiempos)[int(0.9 * len(tiempos))]:.2f}s")
    if a.detalle:
        for x, rs in zip(items, resultados):
            for ok, motivo in rs:
                if x["etiqueta"] != "fuera-contexto" and ok == (x["etiqueta"] == "invento"):
                    print(f"\n[{x['etiqueta']} -> {'PASA' if ok else 'RECHAZA'}] #{x['i']} {x['origen']}")
                    print(f"    respuesta: {x['answer'][:300]!r}")
                    print(f"    juez: {motivo[:400]}")


if __name__ == "__main__":
    asyncio.run(main())
