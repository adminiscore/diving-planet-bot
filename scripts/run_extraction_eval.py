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
from src.agents.llm_extractor import EXTRACTABLE_FIELDS, compare_with_ground_truth, fill_gaps
from src.flows.state import ConversationState

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "eval-set.json"


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
