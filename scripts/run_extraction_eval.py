"""Fase 0 eval-set runner (docs/robustness/plan.md §4-5).

Runs the REALISTIC end-to-end pipeline — regex IntentDetector first, then the
LLM gap-filler on whatever it left missing — against
docs/robustness/eval-set.json, and reports per-field agreement with the
hand-labeled `expected` values. This is the tool used to decide, per domain,
whether the Fase 1+ cutover criteria (plan.md §4) are met.

Cases may carry an optional `history` field (list of {"role", "content"}
turns) that is passed straight through to `fill_gaps`. This is what makes the
"extractor contesta de más" misfill family (fill_gaps re-deriving an answer
from a pending bot question in the history instead of abstaining — see
docs/multi-agent-refactor-plan.md §6.bis) measurable here: without history,
every case looks like a cold-start turn and that failure mode can't occur.

Needs a real OpenAI API key (uses settings.openai_api_key) — run against an
environment that has one, e.g.:

    ENV_FILE=.env.dev python -m scripts.run_extraction_eval
    ssh ... "docker exec -i dp-pre-bot python3 -m scripts.run_extraction_eval"

Usage: no arguments. Prints a per-case and a per-field summary to stdout.
"""

import asyncio
import json
from pathlib import Path

from src.agents.intent_detector import IntentDetector
from src.agents.llm_extractor import (
    EXTRACTABLE_FIELDS,
    compare_with_ground_truth,
    fill_gaps,
    verify_field,
)
from src.agents.supervisor import _VETO_FIELD_SPECS
from src.flows.state import ConversationState

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "eval-set.json"

# Reusa DIRECTAMENTE `supervisor._VETO_FIELD_SPECS` (mismo trigger `should_
# verify` por campo, p. ej. la ambiguedad real que `activity` exige) en vez
# de reimplementar la condicion de disparo aqui -- hallazgo en vivo,
# 2026-09-10: una primera version de este script SI la reimplemento
# ("resuelto este turno" a secas, sin el `should_verify` de `activity`), y
# ese drift exacto (logica duplicada, no sincronizada) hizo que este script
# midiera un trigger que ya no era el que corria en produccion, ocultando
# que el fix real (revertir el trigger de activity a ambiguedad) SI
# funcionaba. No repetir ese error aqui otra vez.


def _regex_resolved(intent) -> dict:
    return {
        f: getattr(intent, f)
        for f in EXTRACTABLE_FIELDS
        if getattr(intent, f, None) not in (None, [])
    }


async def run() -> None:
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    detector = IntentDetector()
    field_stats: dict[str, dict[str, int]] = {}
    total_agree = total_disagree = total_missed = 0

    for case in cases:
        state = ConversationState(conversation_id=f"eval-{case['id']}")
        regex_intent = detector.detect(case["message"], state)
        resolved = _regex_resolved(regex_intent)
        patch = await fill_gaps(
            case["message"], regex_intent, history=case.get("history"), lang=case.get("lang", "es"),
        )
        combined = {**resolved, **patch}

        # Veto por-campo (docs/multi-agent-refactor-plan.md, generalizacion
        # "A bien montado", 2026-09-10): se dispara para cada campo resuelto
        # por el regex ESTE turno Y que pase el `should_verify` de su spec
        # (para `activity`, ambiguedad real -- ver supervisor.py). Se aplica
        # siempre aqui (no gateado por settings) para medir el efecto REAL
        # del mecanismo sobre el eval-set completo, independientemente de
        # que flags esten on/off en el entorno donde se corre este script.
        for veto_field, spec in _VETO_FIELD_SPECS.items():
            if veto_field not in resolved or veto_field not in regex_intent.detected_fields:
                continue
            if spec.should_verify is not None and not spec.should_verify(case["message"], regex_intent):
                continue
            llm_value = await verify_field(
                veto_field, case["message"], resolved[veto_field],
                history=case.get("history"), lang=case.get("lang", "es"),
            )
            if llm_value is not None:
                combined[veto_field] = llm_value

        result = compare_with_ground_truth(combined, case["expected"])
        total_agree += len(result["agree"])
        total_disagree += len(result["disagree"])
        total_missed += len(result["missed"])

        for f in result["agree"]:
            field_stats.setdefault(f, {"agree": 0, "disagree": 0, "missed": 0})["agree"] += 1
        for f in result["disagree"]:
            field_stats.setdefault(f, {"agree": 0, "disagree": 0, "missed": 0})["disagree"] += 1
        for f in result["missed"]:
            field_stats.setdefault(f, {"agree": 0, "disagree": 0, "missed": 0})["missed"] += 1

        status = "OK" if not result["disagree"] and not result["missed"] else "GAP"
        print(f"[{status}] {case['id']}: {case['message'][:60]!r}")
        if result["disagree"]:
            print(f"       disagree={result['disagree']}")
        if result["missed"]:
            print(f"       missed={result['missed']} (regex_had={resolved}, llm_patch={patch})")

    print("\n--- Per-field summary ---")
    for f, stats in sorted(field_stats.items()):
        total = stats["agree"] + stats["disagree"] + stats["missed"]
        rate = stats["agree"] / total if total else 0.0
        print(f"{f:28s} agree={stats['agree']:3d} disagree={stats['disagree']:3d} missed={stats['missed']:3d}  ({rate:.0%})")

    total = total_agree + total_disagree + total_missed
    overall = total_agree / total if total else 0.0
    print(f"\nOverall: {total_agree}/{total} agree ({overall:.1%}), {total_disagree} disagree, {total_missed} missed")
    print(f"Cases: {len(cases)}")


if __name__ == "__main__":
    asyncio.run(run())
