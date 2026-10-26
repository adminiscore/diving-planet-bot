"""LAT-9 paso 0 (26-oct): el banco fijo del escritor único, con el formato de `scripts/banco_fallos.py`.

Cada caso es un TURNO de una ronda juzgada (la conversación real hasta ese turno, el mensaje del cliente y el criterio
que falló), para medir cada paso de lat-9 sin una ronda completa (decisión de Gadea, 26-oct: los cambios de conducta
se miden con su banco ×3; la ronda completa solo al integrar):

    python -m scripts.banco_lat9 construir --rondas 2026-10-26-integra2-A,2026-10-26-integra2-B
    ENV_FILE=.env.dev python -m scripts.banco_fallos medir --banco docs/robustness/lat/banco-lat9.json \\
        --etiqueta lat9-p1 --codigo-local --reps 3

- Solo del golden visible y de las tandas rotativas: NUNCA del examen oculto.
- El turno es el que cita el juez (`evidencia_bot`), como en `scripts/fallos_por_turno.py`; sin cita, fuera.
- Se reparte por el camino que escribió el turno (las métricas de la ronda: el redactor de hechos, el RAG con hechos,
  el RAG sin intenciones, la reserva...), hasta `--max` casos, para que el banco mire todos los caminos que lat-9 junta.
Sin API: solo lee los ficheros de las rondas.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from scripts.fallos_por_turno import _turno_de_la_cita

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "docs/robustness/synthetic-runs"
RESULTS = ROOT / "docs/robustness/golden-set/results"
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"
BANCO = ROOT / "docs/robustness/lat/banco-lat9.json"


def _checks(golden_file: Path) -> dict:
    golden = json.loads(golden_file.read_text(encoding="utf-8-sig"))
    globales = {f"global:{c['id']}": c["check"] for c in golden.get("global_criteria") or []}
    out = {}
    for d in golden["dialogues"]:
        out.update({(d["id"], g): check for g, check in globales.items()})
        out.update({(d["id"], c["id"]): c["check"] for c in d["criteria"]})
    return out


def _camino(m: dict) -> str:
    """El camino que escribió el turno, con las etiquetas de las métricas."""
    if m.get("turn_type") != "rag":
        return m.get("turn_type") or "?"
    return m.get("hechos") or "rag"


def _casos_de(ronda: str, golden_file: Path, ocultos: set[str]) -> list[dict]:
    run = [json.loads(ln) for ln in (RUNS / f"{ronda}.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    res = json.loads((RESULTS / f"{ronda}__gpt-5-mini-medium.json").read_text(encoding="utf-8"))
    metricas = collections.defaultdict(list)
    for ln in (RUNS / f"{ronda}.metricas").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            m = json.loads(ln)
            metricas[str(m["conv"])].append(m)
    for lista in metricas.values():
        lista.sort(key=lambda m: m["start"])
    por_tag = collections.defaultdict(list)
    for r in run:
        por_tag[r["tag"]].append(r)
    checks = _checks(golden_file)
    casos = []
    for d in res["dialogues"]:
        if d["id"] in ocultos:
            continue
        turnos = sorted(por_tag.get(d["id"], []), key=lambda r: r["turn"])
        for c in d["criteria"]:
            if c["verdict"] != "no_cumple":
                continue
            citas = [p.get("evidencia_bot") for p in c.get("problemas") or []] + [c.get("evidencia_bot")]
            # Si el bot repitió la misma respuesta en varios turnos («¡Perfecto! 🙌 ¿Te animas…?»), el fallo suele ser
            # el último: se busca la cita de atrás adelante.
            t = next((t for cita in citas if cita for t in [_turno_de_la_cita(cita, turnos[::-1])] if t), None)
            if t is None:
                continue
            mets = metricas.get(str(t["conv"]), [])
            m = mets[t["turn"] - 1] if t["turn"] - 1 < len(mets) else {}
            historial = []
            for previo in turnos[:t["turn"] - 1]:
                historial += [{"role": "user", "content": previo["msg"]},
                              {"role": "assistant", "content": previo["reply"] or ""}]
            casos.append({
                "dialogo": d["id"], "criterio": c["id"], "pedia": checks.get((d["id"], c["id"]), ""),
                "veredicto": "no_cumple", "motivo_juez": (c.get("reason") or "")[:600], "turno": str(t["turn"]),
                "pieza": _camino(m), "mensaje_cliente": t["msg"], "respuesta_ronda": t["reply"],
                "historial": historial, "ronda": ronda, "tarea": "LAT-9",
            })
    return casos


def construir(rondas: list[str], maximo: int, golden_file: Path) -> list[dict]:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8-sig"))
    ocultos = {d["id"] for d in golden["dialogues"] if d.get("suite") == "oculto"}
    vistos, por_camino = set(), collections.defaultdict(list)
    for ronda in rondas:
        for caso in _casos_de(ronda, golden_file, ocultos):
            clave = (caso["dialogo"], caso["criterio"])
            if clave not in vistos:
                vistos.add(clave)
                por_camino[caso["pieza"]].append(caso)
    # Reparto por camino: uno de cada camino por vuelta hasta llegar al máximo (los caminos raros no se quedan fuera).
    elegidos = []
    while len(elegidos) < maximo and any(por_camino.values()):
        for camino in sorted(por_camino):
            if por_camino[camino] and len(elegidos) < maximo:
                elegidos.append(por_camino[camino].pop(0))
    for i, caso in enumerate(elegidos, 1):
        caso["id"] = f"l9-{i:02d}"
    return elegidos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("accion", choices=["construir"])
    ap.add_argument("--rondas", required=True, help="rondas juzgadas, separadas por comas")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--golden", default=str(GOLDEN), help="el golden de los criterios (o una tanda rotativa)")
    args = ap.parse_args()
    casos = construir(args.rondas.split(","), args.max, Path(args.golden))
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    BANCO.write_text(json.dumps({
        "about": __doc__.split("\n\n")[0], "rondas": args.rondas.split(","), "fallos": casos,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(casos)} casos → {BANCO.relative_to(ROOT)}: "
          + ", ".join(f"{k} {v}" for k, v in collections.Counter(c["pieza"] for c in casos).most_common()))


if __name__ == "__main__":
    main()
