"""Mide al juez contra etiquetas humanas y compara modelos (plan maestro, M0 m0-3).

Lee el set de calibracion (`docs/robustness/golden-set/calibration/items.json`, dialogos y
criterios) y las etiquetas humanas exportadas de la pagina de calibracion (`labels.json`),
pasa cada modelo candidato por esos mismos veredictos (sin trafico a PRE: re-juzga las
conversaciones guardadas) y compara:

- acuerdo con la etiqueta humana (cumple / no_cumple / no_aplica),
- fallos falsos (el juez dice no_cumple y la persona no),
- fallos que se le escapan (la persona dice no_cumple y el juez no),
- `revisar` (fallo sin evidencia verificable) y errores,
- coste real y coste estimado de una ronda completa del golden-set.

Por separado en `tune` (para ajustar el juez) y `holdout` (solo para medir al final).

Uso:

    ENV_FILE=.env.dev python -m scripts.calibrate_judge --models gpt-5:low gpt-5-mini:low
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.judge_golden_set import (
    GOLDEN_FILE,
    cost_usd,
    criteria_for,
    latest_conversations,
    llm_judge_criterion,
    load_reference,
)
from scripts.langfuse_snapshot import _env

CALIBRATION_DIR = Path("docs/robustness/golden-set/calibration")


def consolidate(labels: list[dict], reference_labeler: str | None = None) -> tuple[dict, dict]:
    """Etiqueta de referencia por (dialogo, criterio) y acuerdo entre personas.

    Con una sola persona, su etiqueta. Con varias, la del etiquetador de referencia si se
    indica; si no, la mayoritaria (empate = la primera guardada). Devuelve tambien cuantos
    veredictos tienen dos o mas etiquetas y en cuantos coinciden."""
    by_item: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for lab in sorted(labels, key=lambda x: x.get("at", "")):
        if lab.get("label"):
            by_item[(lab["dialogue"], lab["criterion"])].append(lab)
    reference, shared, agreed = {}, 0, 0
    for item, labs in by_item.items():
        chosen = next((x for x in labs if x["by"] == reference_labeler), None)
        if chosen is None:
            chosen = max(labs, key=lambda x: (Counter(y["label"] for y in labs)[x["label"]], -labs.index(x)))
        reference[item] = chosen["label"]
        if len({x["by"] for x in labs}) > 1:
            shared += 1
            agreed += len({x["label"] for x in labs}) == 1
    return reference, {"items_with_2plus_labelers": shared, "labelers_agree": agreed}


def score(pairs: list[tuple[str, str]]) -> dict:
    """pairs = (humano, juez)."""
    n = len(pairs)
    return {
        "items": n,
        "agreement_pct": round(100 * sum(h == j for h, j in pairs) / n, 1) if n else None,
        "false_fail": sum(j == "no_cumple" and h != "no_cumple" for h, j in pairs),
        "missed_fail": sum(h == "no_cumple" and j != "no_cumple" for h, j in pairs),
        "human_fails": sum(h == "no_cumple" for h, _ in pairs),
        "to_review": sum(j == "revisar" for _, j in pairs),
        "errors": sum(j == "error" for _, j in pairs),
    }


def llm_calls_per_round() -> int:
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    return sum(1 for d in golden["dialogues"] for c in criteria_for(d, golden["global_criteria"]) if not c.get("auto"))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=["gpt-5:low", "gpt-5-mini:low"], help="modelo:esfuerzo")
    parser.add_argument("--labels", nargs="+", default=[str(CALIBRATION_DIR / "labels-claude.json"), str(CALIBRATION_DIR / "labels-gadea.json")], help="uno o varios ficheros de etiquetas")
    parser.add_argument("--reference-labeler", help="id del etiquetador que manda si hay varias etiquetas")
    parser.add_argument("--split", choices=["tune", "holdout", "all"], default="all", help="tune para iterar; holdout solo para la medicion final")
    args = parser.parse_args(argv)

    from openai import OpenAI

    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        print("Falta OPENAI_API_KEY (entorno o ENV_FILE).", file=sys.stderr)
        return 2

    calib = json.loads((CALIBRATION_DIR / "items.json").read_text(encoding="utf-8"))
    all_labels = [lab for path in args.labels for lab in json.loads(Path(path).read_text(encoding="utf-8"))]
    reference, human_agreement = consolidate(all_labels, args.reference_labeler)
    runs = latest_conversations(calib["run_file"])
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    dialogues = {d["id"]: d for d in golden["dialogues"]}
    client, ref_text = OpenAI(api_key=api_key), load_reference()

    todo = []
    for item in calib["items"]:
        records = runs[item["dialogue"]]
        if records[0]["conv"] != item["conv"]:
            print(f"!!! {item['dialogue']}: la conversacion del run ({records[0]['conv']}) no es la etiquetada ({item['conv']})", file=sys.stderr)
            return 1
        if args.split != "all" and item["split"] != args.split:
            continue
        for crit in item["criteria"]:
            if (item["dialogue"], crit["id"]) in reference:
                todo.append((item, records, crit))
    print(f"{len(todo)} veredictos etiquetados; acuerdo entre personas: {human_agreement}", flush=True)

    per_round = llm_calls_per_round()
    report = {"judged_at": datetime.now(UTC).isoformat(timespec="seconds"), "human_agreement": human_agreement, "models": {}}
    for spec in args.models:
        model, _, effort = spec.partition(":")
        pairs = defaultdict(list)
        rows, usage = [], Counter()
        for n, (item, records, crit) in enumerate(todo, 1):
            dialogue = dialogues[item["dialogue"]]
            v = llm_judge_criterion(client, model, effort or None, ref_text, dialogue, records, crit, criteria_for(dialogue, golden["global_criteria"]))
            human = reference[(item["dialogue"], crit["id"])]
            pairs[item["split"]].append((human, v["verdict"]))
            usage.update(v["usage"])
            rows.append({"dialogue": item["dialogue"], "criterion": crit["id"], "split": item["split"], "human": human, "judge": v["verdict"], "reason": v.get("reason"), "evidencia_bot": v.get("evidencia_bot")})
            print(f"  [{spec} {n}/{len(todo)}] {item['dialogue']} · {crit['id']}: humano={human} juez={v['verdict']}", flush=True)
            time.sleep(0.2)
        spent = cost_usd(model, dict(usage))
        report["models"][spec] = {
            "tune": score(pairs["tune"]),
            "holdout": score(pairs["holdout"]),
            "all": score(pairs["tune"] + pairs["holdout"]),
            "usage": dict(usage),
            "cost_usd": spent,
            "est_cost_per_round_usd": round(spent / len(todo) * per_round, 2) if spent is not None and todo else None,
            "rows": rows,
        }

    out = CALIBRATION_DIR / f"results-{datetime.now(UTC):%Y-%m-%d-%H%M}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\nmodelo            split    acuerdo  fallos-falsos  fallos-escapados  revisar  coste-ronda")
    for spec, r in report["models"].items():
        for split in ("tune", "holdout", "all"):
            s = r[split]
            print(f"{spec:<17} {split:<8} {s['agreement_pct']!s:>6} % {s['false_fail']:>8} {s['missed_fail']:>16} {s['to_review']:>10}   {r['est_cost_per_round_usd']} $")
    print(f"\nResultado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
