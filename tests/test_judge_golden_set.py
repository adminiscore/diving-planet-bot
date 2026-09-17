"""Juez del golden-set: golden-set coherente, comprobaciones auto, evidencia y nota."""

import json

from scripts.judge_golden_set import (
    AUTO_CHECKS,
    GOLDEN_FILE,
    catalog_units,
    check_amounts_match_catalog,
    check_evidence,
    check_last_reply_has_booking_link,
    check_single_greeting,
    criteria_for,
    load_reference,
    parse_verdict,
    quote_found,
    summarize,
    transcript,
)
from scripts.run_synthetic_pre import load_batches, select_cases


def _rec(turn, msg, reply):
    return {"turn": turn, "msg": msg, "reply": reply, "conv": 1}


def test_every_golden_dialogue_resolves_to_turns_and_auto_checks_exist():
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    cases = select_cases(load_batches(), "golden", None)
    assert [tag for _, tag, _ in cases] == [d["id"] for d in golden["dialogues"]]
    assert all(turns for _, _, turns in cases)
    assert len({d["id"] for d in golden["dialogues"]}) == len(golden["dialogues"])
    autos = [c["auto"] for d in golden["dialogues"] for c in d["criteria"] if "auto" in c]
    autos += [c["auto"] for c in golden["global_criteria"] if "auto" in c]
    assert autos and all(a in AUTO_CHECKS for a in autos)


def test_reference_includes_the_business_sources():
    ref = load_reference()
    for name in ("pricing.json", "policies.json", "discounts.json", "availability.json", "escalation_rules.json", "activities.json"):
        assert name in ref
    assert "mixed_nationality_group" in ref


def test_own_criterion_overrides_global_with_same_id():
    dialogue = {"criteria": [{"id": "un-saludo", "check": "propio"}]}
    ids = [c["id"] for c in criteria_for(dialogue, [{"id": "un-saludo", "check": "g"}, {"id": "idioma", "check": "g"}])]
    assert ids == ["global:idioma", "un-saludo"]


def test_single_greeting_counts_presentations_not_exclamations():
    ok = [_rec(1, "hola", "¡Hola! 🪸 Soy *Coral*, de *Diving Planet*"), _rec(2, "x", "¡Genial! ¡Con gusto te ayudo!")]
    assert check_single_greeting(ok)["verdict"] == "cumple"
    twice = ok + [_rec(3, "y", "Hi! 🪸 I'm *Coral* from *Diving Planet*")]
    assert check_single_greeting(twice)["verdict"] == "no_cumple"


def test_booking_link_in_last_reply():
    assert check_last_reply_has_booking_link([_rec(1, "como pago", "clic: https://book.divingplanet.org/book/x")])["verdict"] == "cumple"
    assert check_last_reply_has_booking_link([_rec(1, "como pago", "¿lo cambio?")])["verdict"] == "no_cumple"
    assert check_last_reply_has_booking_link([_rec(1, "como pago", None)])["verdict"] == "no_cumple"


def test_amounts_from_catalog_units_totals_and_sums():
    units = catalog_units()
    assert 178 in units["USD"] and 630000 in units["COP"]
    catalog = [_rec(1, "precio", "💰 4 × 126 USD p.p. = *504 USD* · 4 × 448.000 COP p.p. = *1.792.000 COP*")]
    assert check_amounts_match_catalog(catalog)["verdict"] == "cumple"
    mixed_total = [_rec(1, "total", "2 × 178 USD + 2 × 183 USD + 2 × 126 USD = *974 USD*")]
    assert check_amounts_match_catalog(mixed_total)["verdict"] == "cumple"
    assert check_amounts_match_catalog([_rec(1, "precio", "cuesta 999999 COP")])["verdict"] == "revisar"
    assert check_amounts_match_catalog([_rec(1, "hola", "sin precios")])["verdict"] == "no_aplica"


def test_quote_found_ignores_markdown_emojis_and_accepts_ellipsis():
    text = "¡Hola! 🪸 Soy *Coral*.\n\n¿Han pasado *más de 2 años* desde tu última inmersión?"
    assert quote_found("¿Han pasado más de 2 años desde tu última inmersión?", text)
    assert quote_found("Soy Coral ... más de 2 años", text)
    assert not quote_found("te doy un descuento del 50%", text)
    assert not quote_found(None, text)


def test_failure_without_verifiable_evidence_goes_to_review():
    records = [_rec(1, "somos 2", "¿Desde dónde saldrías?")]
    good = {"verdict": "no_cumple", "evidencia_bot": "¿Desde dónde saldrías?", "evidencia_cliente": "somos 2", "reason": "r"}
    assert check_evidence(good, records)["verdict"] == "no_cumple"
    invented_bot = {**good, "evidencia_bot": "somos una estafa"}
    assert check_evidence(invented_bot, records)["verdict"] == "revisar"
    invented_client = {**good, "evidencia_cliente": "desde cartagena"}
    assert check_evidence(invented_client, records)["verdict"] == "revisar"
    assert check_evidence({"verdict": "cumple"}, records)["verdict"] == "cumple"


def test_parse_verdict():
    assert parse_verdict(json.dumps({"verdict": "no_aplica", "motivo": "m"}))["verdict"] == "no_aplica"
    assert parse_verdict(json.dumps({"verdict": "quizas"}))["verdict"] == "error"
    assert parse_verdict("no es json")["verdict"] == "error"


def test_summary_counts_review_apart():
    results = [
        {"category": "info", "criteria": [{"verdict": "cumple"}, {"verdict": "no_aplica"}]},
        {"category": "info", "criteria": [{"verdict": "cumple"}, {"verdict": "no_cumple"}]},
        {"category": "escalado", "criteria": [{"verdict": "cumple"}, {"verdict": "revisar"}]},
    ]
    s = summarize(results)
    assert s["criteria_judged"] == 4
    assert s["criteria_pass_pct"] == 75.0
    assert s["dialogues_passed"] == 2
    assert s["to_review"] == 1
    assert s["by_category"]["info"]["criteria_pass_pct"] == 66.7


def test_transcript_splits_bubbles_and_marks_no_reply():
    records = [_rec(2, "somos 2", None), _rec(1, "hola", "Hola\n---\nPrecio")]
    assert transcript(records) == "CLIENTE: hola\nBOT: Hola\nBOT: Precio\nCLIENTE: somos 2\nBOT: [sin respuesta en el tiempo de espera]"


def test_calibration_consolidates_labels_and_scores():
    from scripts.calibrate_judge import consolidate, llm_calls_per_round, score

    labels = [
        {"dialogue": "d", "criterion": "c", "label": "cumple", "by": "u_a", "at": "1"},
        {"dialogue": "d", "criterion": "c", "label": "no_cumple", "by": "u_b", "at": "2"},
        {"dialogue": "d", "criterion": "k", "label": "no_cumple", "by": "u_a", "at": "3"},
        {"dialogue": "d", "criterion": "z", "label": None, "by": "u_a", "at": "4"},
    ]
    ref, agreement = consolidate(labels, reference_labeler="u_b")
    assert ref == {("d", "c"): "no_cumple", ("d", "k"): "no_cumple"}
    assert agreement == {"items_with_2plus_labelers": 1, "labelers_agree": 0}

    s = score([("cumple", "cumple"), ("cumple", "no_cumple"), ("no_cumple", "revisar"), ("no_aplica", "no_aplica")])
    assert s["agreement_pct"] == 50.0
    assert (s["false_fail"], s["missed_fail"], s["to_review"]) == (1, 1, 1)
    assert llm_calls_per_round() > 41


def test_calibration_items_match_golden_criteria():
    from scripts.calibrate_judge import CALIBRATION_DIR

    calib = json.loads((CALIBRATION_DIR / "items.json").read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in golden["dialogues"]}
    for item in calib["items"]:
        known = {c["id"] for c in criteria_for(by_id[item["dialogue"]], golden["global_criteria"])}
        assert {c["id"] for c in item["criteria"]} <= known
    assert {i["split"] for i in calib["items"]} == {"tune", "holdout"}
