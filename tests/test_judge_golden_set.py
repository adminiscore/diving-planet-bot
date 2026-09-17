"""LLM-juez del golden-set: golden-set coherente con los lotes, parseo del juez y nota."""

import json

from scripts.judge_golden_set import (
    GOLDEN_FILE,
    criteria_for,
    load_reference,
    parse_verdicts,
    summarize,
    transcript,
)
from scripts.run_synthetic_pre import load_batches, select_cases


def test_every_golden_dialogue_resolves_to_turns():
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    cases = select_cases(load_batches(), "golden", None)
    assert [tag for _, tag, _ in cases] == [d["id"] for d in golden["dialogues"]]
    assert all(turns for _, _, turns in cases)
    assert len({d["id"] for d in golden["dialogues"]}) == len(golden["dialogues"])


def test_reference_includes_the_business_sources():
    ref = load_reference()
    for name in ("pricing.json", "policies.json", "discounts.json", "availability.json", "escalation_rules.json", "activities.json"):
        assert name in ref
    assert "mixed_nationality_group" in ref


def test_own_criterion_overrides_global_with_same_id():
    dialogue = {"criteria": [{"id": "un-saludo", "check": "propio"}]}
    ids = [c["id"] for c in criteria_for(dialogue, [{"id": "un-saludo", "check": "g"}, {"id": "idioma", "check": "g"}])]
    assert ids == ["global:idioma", "un-saludo"]


def test_parse_verdicts_marks_missing_or_invalid_as_error():
    raw = json.dumps({"criteria": [{"id": "a", "verdict": "cumple", "reason": "ok"}, {"id": "b", "verdict": "quizas"}]})
    out = parse_verdicts(raw, ["a", "b", "c"])
    assert [c["verdict"] for c in out] == ["cumple", "error", "error"]
    assert [c["verdict"] for c in parse_verdicts("no es json", ["a"])] == ["error"]


def test_summary_ignores_not_applicable_and_counts_failed_dialogues():
    results = [
        {"category": "info", "criteria": [{"verdict": "cumple"}, {"verdict": "no_aplica"}]},
        {"category": "info", "criteria": [{"verdict": "cumple"}, {"verdict": "no_cumple"}]},
        {"category": "escalado", "criteria": [{"verdict": "cumple"}, {"verdict": "error"}]},
    ]
    s = summarize(results)
    assert s["criteria_judged"] == 4
    assert s["criteria_pass_pct"] == 75.0
    assert s["dialogues_passed"] == 1
    assert s["errors"] == 1
    assert s["by_category"]["info"]["criteria_pass_pct"] == 66.7


def test_transcript_splits_bubbles_and_marks_no_reply():
    records = [
        {"turn": 2, "msg": "somos 2", "reply": None},
        {"turn": 1, "msg": "hola", "reply": "Hola\n---\nPrecio"},
    ]
    assert transcript(records) == "CLIENTE: hola\nBOT: Hola\nBOT: Precio\nCLIENTE: somos 2\nBOT: [sin respuesta en el tiempo de espera]"
