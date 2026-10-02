"""Nota del juez del golden por grupo: sintéticos, reales (visibles) y examen oculto (2-oct).

Las rondas COMPLETAS (`run_synthetic_pre --sample golden`) se resumían a mano en estos tres grupos (paso 8: sintéticos
96,7 %, reales 83,2 %, oculto 76,4 %). Este script lo hace con la misma cuenta que `judge_golden_set.summarize`:
  oculto      `suite == "oculto"` en golden-dialogues.json
  reales      conversaciones de WhatsApp (`source.kind == "whatsapp"`) que no son del oculto
  sinteticos  el resto (casos de los lotes sintéticos y diálogos propios)

    python -m scripts.golden_por_grupo docs/robustness/golden-set/results/<A>__gpt-5-mini-medium.json [<B>...]

Solo lee resultados ya juzgados: no llama a ninguna API.
"""
import argparse
import json
import sys
from pathlib import Path

from scripts.judge_golden_set import summarize

GOLDEN = Path(__file__).resolve().parent.parent / "docs/robustness/golden-set/golden-dialogues.json"
GRUPOS = ("sinteticos", "reales", "oculto")


def grupo_de() -> dict[str, str]:
    dialogos = json.loads(GOLDEN.read_text(encoding="utf-8"))["dialogues"]
    grupo = {}
    for d in dialogos:
        if d.get("suite") == "oculto":
            grupo[d["id"]] = "oculto"
        elif (d.get("source") or {}).get("kind") == "whatsapp":
            grupo[d["id"]] = "reales"
        else:
            grupo[d["id"]] = "sinteticos"
    return grupo


def _resumen(dialogos: list[dict]) -> dict:
    """`summarize` + diálogos sin fallos contando también `revisar` como fallo (así se dieron los grupos del paso 8 en
    HISTORY 0.29.59: 35/43, 9/52, 4/21; el total 55/116 era el de `summarize`)."""
    s = summarize(dialogos)
    s["dialogues_passed_strict"] = sum(
        1 for d in dialogos if not any(c["verdict"] in ("no_cumple", "error", "revisar") for c in d["criteria"]))
    return s


def por_grupo(resultado: dict, grupo: dict[str, str]) -> dict[str, dict]:
    filas = {"total": _resumen(resultado["dialogues"])}
    for g in GRUPOS:
        filas[g] = _resumen([d for d in resultado["dialogues"] if grupo.get(d["id"]) == g])
    return filas


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("resultados", nargs="+", help="ficheros __gpt-5-mini-medium.json de judge_golden_set")
    args = ap.parse_args()
    grupo = grupo_de()
    for ruta in args.resultados:
        res = json.loads(Path(ruta).read_text(encoding="utf-8"))
        print(f"\n{Path(ruta).name}  (juzgado {res.get('judged_at', '?')})")
        for nombre, s in por_grupo(res, grupo).items():
            print(f"  {nombre:11s} criterios {s['criteria_pass_pct']} % ({s['criteria_failed']} fallos de "
                  f"{s['criteria_judged']}) · diálogos sin fallos {s['dialogues_passed']}/{s['dialogues']} "
                  f"(sin fallos ni 'revisar' {s['dialogues_passed_strict']}) · a revisar {s['to_review']}")


if __name__ == "__main__":
    main()
