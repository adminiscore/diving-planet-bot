"""Lanzador de conversaciones sinteticas: los lotes del repo y la muestra de M0."""

import scripts.run_synthetic_pre as rsp
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


def test_core_sample_is_the_coverage_core():
    """El golden core (G2) sale de coverage.json: todos sus ids existen en el golden-set y la
    muestra rapida de latencia va dentro (un core sin ella no sirve de red de seguridad)."""
    import json
    from pathlib import Path

    core = json.loads(Path("docs/robustness/golden-set/coverage.json").read_text(encoding="utf-8"))["core"]
    picked = {tag for _, tag, _ in select_cases(load_batches(), "core", None)}
    assert picked == set(core)
    assert {tag for _, tag, _ in select_cases(load_batches(), "rapida", None)} <= picked


def _fake_urlopen(fallos: int, llamadas: list):
    import io
    import json as _json
    import urllib.error

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _open(req, timeout=None, context=None):
        llamadas.append(req.get_method())
        if len(llamadas) <= fallos:
            raise urllib.error.URLError("timed out")
        return _Resp(_json.dumps({"payload": []}).encode())

    return _open


def test_las_lecturas_de_chatwoot_se_reintentan(monkeypatch):
    """24-sep: un timeout puntual de Chatwoot tumbo la ronda completa en el turno 262."""
    llamadas = []
    monkeypatch.setattr(rsp.urllib.request, "urlopen", _fake_urlopen(2, llamadas))
    monkeypatch.setattr(rsp.time, "sleep", lambda s: None)
    cw = rsp.Chatwoot("https://x", "t", 1, 2)
    assert cw._req("GET", "/conversations/1/messages") == {"payload": []}
    assert llamadas == ["GET", "GET", "GET"]


def test_los_envios_no_se_reintentan(monkeypatch):
    """Reintentar un POST podria duplicar el mensaje del cliente."""
    import urllib.error

    import pytest

    llamadas = []
    monkeypatch.setattr(rsp.urllib.request, "urlopen", _fake_urlopen(1, llamadas))
    cw = rsp.Chatwoot("https://x", "t", 1, 2)
    with pytest.raises(urllib.error.URLError):
        cw._req("POST", "/conversations/1/messages", {"content": "hola"})
    assert llamadas == ["POST"]
