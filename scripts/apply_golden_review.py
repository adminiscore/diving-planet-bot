"""Aplica la revision humana a una ronda juzgada del golden-set (plan maestro, M0 m0-3).

El juez oficial (gpt-5-mini medium) acierta ~91 % en la calibracion, asi que cada ronda sale
con una lista de revision humana (`human_review`). Este script toma las decisiones de la
persona (fichero JSON: lista de {dialogue, criterion, verdict, note}), corrige esos veredictos,
recalcula la nota (`summary_reviewed`), mide cuanto acerto el juez en lo revisado y, con
`--snapshot`, deja la nota REVISADA en la foto de la linea temporal.

Uso:

    python -m scripts.apply_golden_review \\
        --results docs/robustness/golden-set/results/2026-09-17-golden__gpt-5-mini-medium.json \\
        --decisions docs/robustness/golden-set/results/2026-09-17-golden__review.json [--snapshot foto.json]
"""

import argparse
import copy
import json
import sys
from pathlib import Path

from scripts.judge_golden_set import summarize


def apply_review(report: dict, decisions: list[dict]) -> dict:
    """Devuelve el informe con los veredictos corregidos, `summary_reviewed` y `judge_accuracy_on_review`."""
    by_key = {(d["dialogue"], d["criterion"]): d for d in decisions}
    reviewed = copy.deepcopy(report["dialogues"])
    changed, confirmed = 0, 0
    for dialogue in reviewed:
        for crit in dialogue["criteria"]:
            decision = by_key.get((dialogue["id"], crit["id"]))
            if not decision:
                continue
            if decision["verdict"] == crit["verdict"]:
                confirmed += 1
            else:
                changed += 1
                crit["judge_verdict"], crit["verdict"] = crit["verdict"], decision["verdict"]
            crit["human_note"] = decision.get("note", "")
    missing = [k for k in by_key if not any(d["id"] == k[0] and any(c["id"] == k[1] for c in d["criteria"]) for d in reviewed)]
    if missing:
        raise ValueError(f"decisiones que no casan con ningun criterio: {missing}")
    return {
        **report,
        "reviewed_dialogues": reviewed,
        "summary_reviewed": summarize(reviewed),
        "judge_accuracy_on_review": {"reviewed": len(decisions), "confirmed": confirmed, "corrected": changed},
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--snapshot")
    args = parser.parse_args(argv)

    report = json.loads(Path(args.results).read_text(encoding="utf-8"))
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    out = apply_review(report, decisions)
    Path(args.results).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    s, acc = out["summary_reviewed"], out["judge_accuracy_on_review"]
    if args.snapshot:
        snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        snap["quality"] = {
            "results_file": args.results.replace("\\", "/"),
            "model": f"{report['model']} ({report['effort']}) + revision humana",
            **{k: v for k, v in s.items() if k != "by_category"},
            "by_category": {k: v["criteria_pass_pct"] for k, v in s["by_category"].items()},
            "judge_raw_pass_pct": report["summary"]["criteria_pass_pct"],
            "judge_accuracy_on_review": acc,
        }
        Path(args.snapshot).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"Nota revisada: {s['criteria_pass_pct']} % de criterios ({s['criteria_failed']} fallos de {s['criteria_judged']}); "
        f"dialogos sin fallos: {s['dialogues_passed']}/{s['dialogues']}. "
        f"Juez en lo revisado: {acc['confirmed']} confirmados, {acc['corrected']} corregidos.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
