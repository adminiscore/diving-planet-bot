"""gen-9 (21-oct, decisión de Gadea): la nota de un resultado de G9 sin los criterios desfasados.

Los criterios que chocan con decisiones del negocio posteriores al examen (docs/robustness/golden-set/
g9-criterios-desfasados.json) no puntúan: aquí cuentan como "no aplica". El examen no se toca ni se abre; esto lee
solo el resultado del juez. Con `--con-sin-respaldo` quita también los que piden un dato que la base no tiene.

    python -m scripts.puntuar_sin_desfasados docs/robustness/golden-set/results/2026-10-19-g9__gpt-5-mini-medium.json
"""

import argparse
import json
import sys
from pathlib import Path

LISTA = Path("docs/robustness/golden-set/g9-criterios-desfasados.json")


def puntuar(resultado: dict, fuera: set[tuple[str, str]]) -> dict:
    juzgados = fallos = sin_fallos = 0
    for dl in resultado["dialogues"]:
        malos = 0
        for c in dl["criteria"]:
            if (dl["id"], c["id"]) in fuera or c["verdict"] not in ("cumple", "no_cumple"):
                continue
            juzgados += 1
            malos += c["verdict"] == "no_cumple"
        fallos += malos
        sin_fallos += malos == 0
    n = len(resultado["dialogues"])
    return {"criterios": round(100 * (juzgados - fallos) / juzgados, 1) if juzgados else 0.0, "fallos": fallos,
            "juzgados": juzgados, "dialogos_sin_fallos": sin_fallos, "dialogos": n}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("resultado", help="JSON de judge_golden_set sobre G9")
    ap.add_argument("--lista", default=str(LISTA))
    ap.add_argument("--con-sin-respaldo", action="store_true", help="quita también los criterios sin respaldo en la base")
    args = ap.parse_args()
    lista = json.loads(Path(args.lista).read_text(encoding="utf-8"))
    claves = ["desfasados"] + (["sin_respaldo_en_la_base"] if args.con_sin_respaldo else [])
    fuera = {(x["dialogo"], x["criterio"]) for k in claves for x in lista.get(k, [])}
    res = json.loads(Path(args.resultado).read_text(encoding="utf-8"))
    tal_cual = puntuar(res, set())
    sin = puntuar(res, fuera)
    for nombre, p in (("tal cual", tal_cual), (f"sin {' ni '.join(claves)}", sin)):
        print(f"{nombre}: {p['criterios']} % de criterios ({p['fallos']} fallos de {p['juzgados']}), "
              f"{p['dialogos_sin_fallos']}/{p['dialogos']} diálogos sin fallos")


if __name__ == "__main__":
    main()
