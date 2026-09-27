"""Vuelve a juzgar SOLO los criterios generales de una ronda ya juzgada (g-8, 27-sep).

Para probar un cambio en cómo se juzgan los criterios GENERALES sin pagar la ronda entera
(~75 min, ~1,4 $): reutiliza los veredictos de los criterios concretos de un resultado ya
guardado, vuelve a juzgar los generales con el código de ahora (dos pasadas: ven los concretos
que suspendieron) y escribe un resultado completo, comparable con `scripts.ab_judge_compare` o
con la revisión humana.

    ENV_FILE=.env.dev python -m scripts.rejudge_generals \\
        --from docs/robustness/golden-set/results/2026-09-26-g8-v7-juez8__gpt-5-mini-medium.json \\
        --only-reviewed docs/robustness/golden-set/results/2026-09-22-golden-v7__review.json \\
        --out docs/robustness/golden-set/results/2026-09-27-g8-v7-juez9-generales__gpt-5-mini-medium.json

`--only-reviewed`: solo los generales que tienen veredicto humano (los únicos que se pueden
puntuar); los demás se copian tal cual del resultado de partida.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.judge_golden_set import (
    GOLDEN_FILE,
    counted_failures,
    criteria_for,
    discount_counted,
    evaluate_criterion,
    is_general,
    latest_conversations,
    llm_same_error,
    load_reference,
)
from scripts.langfuse_snapshot import _env


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-reviewed")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)

    from openai import OpenAI

    src = json.loads(Path(a.src).read_text(encoding="utf-8"))
    model, effort = src["model"], src.get("effort")
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in golden["dialogues"]}
    runs = latest_conversations(src["run_file"])
    reference = load_reference()
    client = OpenAI(api_key=_env("OPENAI_API_KEY"))
    reviewed = None
    if a.only_reviewed:
        reviewed = {(r["dialogue"], r["criterion"]) for r in json.loads(Path(a.only_reviewed).read_text(encoding="utf-8"))}

    jobs = []
    for d in src["dialogues"]:
        dialogue, records = by_id.get(d["id"]), runs.get(d["id"])
        if not dialogue or not records:
            continue
        all_criteria = criteria_for(dialogue, golden["global_criteria"])
        verdicts = {c["id"]: c for c in d["criteria"]}
        todo = [c for c in all_criteria if is_general(c) and not c.get("auto")
                and (reviewed is None or (d["id"], c["id"]) in reviewed)]
        if todo:
            jobs.append((d, dialogue, records, todo, all_criteria, verdicts))

    def run(job):
        # Los generales de un dialogo en orden: cada uno descuenta lo que ya contaron los concretos
        # y los generales anteriores (como `judge_criteria`).
        d, dialogue, records, todo, all_criteria, verdicts = job
        verdicts = dict(verdicts)
        counted = counted_failures(all_criteria, verdicts)
        out = []
        for c in [x for x in all_criteria if is_general(x)]:
            if c in todo:
                raw = evaluate_criterion(client, model, effort, reference, dialogue, records, c, all_criteria, counted)
                verdicts[c["id"]] = discount_counted(raw, counted, records, llm_same_error(client, model))
                out.append(verdicts[c["id"]])
            counted = counted + counted_failures([c], verdicts, generals=True)
        return d["id"], out

    print(f"re-juzgando {sum(len(j[3]) for j in jobs)} criterios generales con {model} {effort or ''}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        new = {(did, r["id"]): {**r, "rejudged": True} for did, rs in ex.map(run, jobs) for r in rs}
    for d in src["dialogues"]:
        d["criteria"] = [new.get((d["id"], c["id"]), c) for c in d["criteria"]]
    src["rejudged_generals_from"] = a.src.replace("\\", "/")
    Path(a.out).write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"escrito {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
