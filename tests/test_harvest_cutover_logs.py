"""Tests for scripts/harvest_cutover_logs.py (Fase 6, bucle de datos reales).

Log-line samples mirror the EXACT format supervisor.py emits:
  f"[EXTRACT][CUTOVER] applied={applied} msg={message[:60]!r}"
  f"[EXTRACT][SHADOW] msg={message[:60]!r} gaps_before={gaps_before} llm_patch={patch}"
"""

from scripts.harvest_cutover_logs import (
    parse_lines,
    summarize,
    to_candidates,
)

_CUTOVER_LINES = [
    "2026-07-21 10:00:00 [info] [EXTRACT][CUTOVER] applied={'location': 'cartagena'} msg='salimos desde bocagrande'",
    "2026-07-21 10:01:00 [info] [EXTRACT][CUTOVER] applied={'group_size': 2} msg='just the two of us wanna dive'",
    # nested dict (group_allocation) must be captured whole
    "2026-07-21 10:02:00 [info] [EXTRACT][CUTOVER] applied={'group_allocation': {'certified_diving': 4, 'snorkel': 2}} msg='four divers two snorkelers'",
    # duplicate message -> deduped
    "2026-07-21 10:03:00 [info] [EXTRACT][CUTOVER] applied={'location': 'cartagena'} msg='salimos desde bocagrande'",
]

_SHADOW_LINE = (
    "2026-07-21 10:04:00 [info] [EXTRACT][SHADOW] msg='mi hijo de ocho quiere probar' "
    "gaps_before=['group_size', 'ages'] llm_patch={'group_size': 2, 'ages': [8]}"
)

_NOISE = [
    "2026-07-21 10:05:00 [info] knowledge_loaded file=brand_tone.json items=1",
    "random unrelated log line",
    # truncated / malformed applied -> skipped, never crashes
    "2026-07-21 10:06:00 [info] [EXTRACT][CUTOVER] applied={'group_siz",
]


def test_parses_cutover_lines_including_nested_dict():
    records = parse_lines(_CUTOVER_LINES)
    assert len(records) == 4  # dup message still parsed as a record (dedup is in to_candidates)
    by_msg = {r["message"]: r["patch"] for r in records}
    assert by_msg["salimos desde bocagrande"] == {"location": "cartagena"}
    assert by_msg["four divers two snorkelers"] == {
        "group_allocation": {"certified_diving": 4, "snorkel": 2}
    }


def test_parses_shadow_line():
    records = parse_lines([_SHADOW_LINE])
    assert len(records) == 1
    assert records[0]["source_kind"] == "shadow"
    assert records[0]["patch"] == {"group_size": 2, "ages": [8]}


def test_ignores_noise_and_malformed_without_crashing():
    records = parse_lines(_NOISE)
    assert records == []


def test_summary_counts_by_field_and_domain():
    records = parse_lines(_CUTOVER_LINES + [_SHADOW_LINE])
    s = summarize(records)
    assert s["by_field"]["location"] == 2       # two cutover location lines
    assert s["by_field"]["group_size"] == 2     # one cutover + one shadow
    assert s["by_domain"]["location"] == 2
    assert s["by_domain"]["group"] == 4         # group_size x2 + group_allocation + ages
    assert s["by_kind"] == {"cutover": 4, "shadow": 1}


def test_candidates_are_deduped_and_flagged_unvalidated():
    records = parse_lines(_CUTOVER_LINES)
    cands = to_candidates(records)
    messages = [c["message"] for c in cands]
    assert messages.count("salimos desde bocagrande") == 1  # deduped
    assert len(cands) == 3
    # expected carries the LLM patch as a starting point, explicitly marked unvalidated
    baru = next(c for c in cands if c["message"] == "salimos desde bocagrande")
    assert baru["expected"] == {"location": "cartagena"}
    assert "sin validar" in baru["notes"].lower()
