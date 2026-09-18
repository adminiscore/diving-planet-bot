"""Lanzador de conversaciones sinteticas: los lotes del repo y la muestra de M0."""

from scripts.run_synthetic_pre import load_batches, main, select_cases


def test_batches_file_has_the_eight_lots():
    batches = load_batches()
    assert sorted(batches) == [str(i) for i in range(1, 9)]
    assert sum(len(cases) for cases in batches.values()) == 265


def test_m0_sample_is_the_baseline_selection():
    cases = select_cases(load_batches(), "m0", None)
    assert len(cases) == 108
    assert sum(len(turns) for _, _, turns in cases) == 336


def test_dry_run_sends_nothing(capsys):
    assert main(["--name", "prueba", "--batches", "7", "--dry"]) == 0
    assert "18 conversaciones, 45 turnos" in capsys.readouterr().out


def test_quick_sample_is_one_golden_dialogue_per_graph_path():
    from scripts.run_synthetic_pre import QUICK_IDS

    cases = select_cases(load_batches(), "rapida", None)
    assert [tag for _, tag, _ in cases] == list(QUICK_IDS)
    golden = {tag: turns for _, tag, turns in select_cases(load_batches(), "golden", None)}
    assert all(turns == golden[tag] for _, tag, turns in cases)
    assert sum(len(t) for _, _, t in cases) <= 15
