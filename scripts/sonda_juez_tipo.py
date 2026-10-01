"""Banco del juez v4 (`juez_por_tipo`, 1-oct; `docs/robustness/juez/README.md`).

Respuestas REALES de las mediciones de rag_piezas del 1-oct, con el contexto que vio el juez reconstruido (el
catálogo del juez + las piezas encontradas y el resumen del estado, tal como los recibió el que redactaba).

- `--listar`: vuelca las respuestas que el juez v3 rechazó, para etiquetarlas a mano en
  `docs/robustness/juez/banco-etiquetas.json` ("invento" = debe rechazarse; "falso" = debe pasar).
- `--evaluar`: juez v3 y juez v4 sobre las rechazadas (N veces) y sobre una muestra de las aprobadas (que deben
  seguir pasando). Diseño y ciego por fichero de medición; se mira el ciego al final, sin cambiar nada.

    python -m scripts.sonda_juez_tipo --listar
    python -m scripts.sonda_juez_tipo --evaluar
"""
import argparse
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agents import grounding_check  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.catalog import catalog_booking_links, catalog_facts, para_el_juez  # noqa: E402

DIR = Path("docs/robustness/rag-piezas")
DISENO = ["2026-10-01-juez-A", "2026-10-01-juez-B", "2026-10-01-juez-A-moneda", "2026-10-01-juez-B-moneda"]
CIEGO = ["2026-10-01-juez-B2", "2026-10-01-juez-B3", "2026-10-01-juez-B4", "2026-10-01-juez-A-dif",
         "2026-10-01-juez-B4-dif", "2026-10-01-juez-B2-moneda"]
ETIQUETAS = Path("docs/robustness/juez/banco-etiquetas.json")
ORIGEN = {
    "es": ("\nOrigen: si el contexto no dice desde dónde sale el cliente, da el precio desde Cartagena y el de 'ya en "
           "las islas', cada uno rotulado, o pregúntale desde dónde saldría."),
    "en": ("\nOrigin: if the context doesn't say where the customer departs from, give the price from Cartagena and "
           "the 'already on the islands' one, each labelled, or ask where they'd leave from."),
}


def _lang(usuario: str) -> str:
    return "es" if "Pregunta del cliente:" in usuario and re.search(r"[áéíóúñ¿¡]", usuario.split("Pregunta del cliente:")[-1]) else "en"


def items() -> list[dict]:
    out = []
    for grupo, nombres in (("diseño", DISENO), ("ciego", CIEGO)):
        for nombre in nombres:
            filas = json.loads((DIR / f"{nombre}.json").read_text(encoding="utf-8"))["filas"]
            for f in filas:
                llamadas, juicios = f.get("llamadas") or [], f.get("juicios") or []
                if not llamadas or len(juicios) != len(llamadas):
                    continue  # un guard fijo cortó antes del juez: no hay juicio que alinear
                u = llamadas[0]["usuario"]
                lang = _lang(u)
                kb = re.sub(r"^Contexto:\n", "", u.split("\n\nPregunta del cliente:")[0])
                ctx = para_el_juez(catalog_facts(lang) + ORIGEN[lang] + "\n" + catalog_booking_links(lang), lang)
                for i, (ll, j) in enumerate(zip(llamadas, juicios, strict=True)):
                    out.append({"clave": f"{nombre}|{f['id']}|{f['rep']}|{i}", "grupo": grupo, "caso": f["id"],
                                "lang": lang, "respuesta": ll.get("respuesta") or "", "contexto": ctx + "\n\n" + kb,
                                "v3_original": j["ok"], "motivo_original": j.get("why", "")})
    return out


async def juez(item: dict, por_tipo: bool) -> tuple[bool, str]:
    settings.juez_por_tipo = por_tipo
    return await grounding_check.is_grounded(item["respuesta"], item["contexto"], item["lang"])


async def evaluar(n_rech: int, n_aprob: int, muestra: int) -> None:
    etiquetas = json.loads(ETIQUETAS.read_text(encoding="utf-8"))["etiquetas"]
    todos = items()
    rechazadas = [x for x in todos if not x["v3_original"]]
    falta = [x["clave"] for x in rechazadas if x["clave"] not in etiquetas]
    if falta:
        raise SystemExit(f"rechazadas sin etiqueta: {falta}")
    random.seed(1)
    aprobadas = random.sample([x for x in todos if x["v3_original"]], muestra)
    sem = asyncio.Semaphore(6)

    async def veces(x, por_tipo, n):
        async def una():
            async with sem:
                return await juez(x, por_tipo)
        return await asyncio.gather(*(una() for _ in range(n)))

    for grupo in ("diseño", "ciego"):
        print(f"\n===== {grupo}")
        filas = [x for x in rechazadas if x["grupo"] == grupo and etiquetas[x["clave"]]["etiqueta"] != "dudoso"]
        tabla = {"invento": {"v3": [0, 0], "v4": [0, 0]}, "falso": {"v3": [0, 0], "v4": [0, 0]}}
        for x in filas:
            et = etiquetas[x["clave"]]["etiqueta"]
            # secuencial por juez: `settings.juez_por_tipo` es global
            r3 = await veces(x, False, n_rech)
            r4 = await veces(x, True, n_rech)
            for nombre, res in (("v3", r3), ("v4", r4)):
                tabla[et][nombre][0] += sum(g for g, _ in res)
                tabla[et][nombre][1] += len(res)
            print(f"  {et:7s} v3 pasa {sum(g for g, _ in r3)}/{n_rech} · v4 pasa {sum(g for g, _ in r4)}/{n_rech}  "
                  f"{x['caso']}  {next((m for g, m in r4 if not g), '')[:110]}")
        for et, d in tabla.items():
            print(f"  -> {et}: v3 deja pasar {d['v3'][0]}/{d['v3'][1]} · v4 {d['v4'][0]}/{d['v4'][1]}"
                  + ("   (deben pasar)" if et == "falso" else "   (NO deben pasar)"))
        grupo_aprob = [x for x in aprobadas if x["grupo"] == grupo]
        r3 = [await veces(x, False, n_aprob) for x in grupo_aprob]
        r4 = [await veces(x, True, n_aprob) for x in grupo_aprob]
        p3 = sum(g for res in r3 for g, _ in res)
        p4 = sum(g for res in r4 for g, _ in res)
        tot = sum(len(res) for res in r3)
        print(f"  aprobadas por el v3 en la medición ({len(grupo_aprob)}): v3 vuelve a aprobar {p3}/{tot} · v4 {p4}/{tot}")
        for x, res in zip(grupo_aprob, r4, strict=True):
            for g, m in res:
                if not g:
                    print(f"     v4 rechaza una aprobada: {x['caso']}  {m[:140]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--evaluar", action="store_true")
    ap.add_argument("--n", type=int, default=2, help="repeticiones por respuesta rechazada")
    ap.add_argument("--muestra", type=int, default=60, help="aprobadas que se vuelven a juzgar")
    args = ap.parse_args()
    if args.listar:
        for x in items():
            if not x["v3_original"]:
                print(json.dumps({"clave": x["clave"], "grupo": x["grupo"], "motivo": x["motivo_original"][:300],
                                  "respuesta": x["respuesta"]}, ensure_ascii=False))
    if args.evaluar:
        asyncio.run(evaluar(args.n, 1, args.muestra))


if __name__ == "__main__":
    main()
