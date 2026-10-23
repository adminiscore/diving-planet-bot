"""El juez con `--paralelo` (23-oct): mismas preguntas, mismos veredictos y mismo orden que en serie.

En serie iba a ~7 criterios por minuto; ahora juzga varios dialogos a la vez. Dentro de cada dialogo
el orden no cambia (concretos y despues generales) y la huella de la cache tampoco.
"""

import json
import random
import threading
import time

from scripts import judge_golden_set as jg

GOLDEN = {
    "version": "test",
    "global_criteria": [{"id": "sin-invenciones", "check": "no inventa"}],
    "dialogues": [
        {"id": f"d{n}", "category": "reserva" if n % 2 else "info", "criteria": [{"id": "dato", "check": "da el dato"}]}
        for n in range(1, 13)
    ],
}


def _run_file(path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for d in GOLDEN["dialogues"]:
            for turn in (1, 2):
                fh.write(json.dumps({"tag": d["id"], "conv": 7, "turn": turn, "msg": f"hola {turn}",
                                     "reply": f"respuesta {d['id']} {turn}"}) + "\n")


def _judge_main(monkeypatch, tmp_path, paralelo):
    golden = tmp_path / "golden.json"
    golden.write_text(json.dumps(GOLDEN), encoding="utf-8")
    run = tmp_path / "ronda.jsonl"
    _run_file(run)
    calls = []

    def _judge(client, model, effort, reference, dialogue, records, criterion, others=None, counted=None):
        time.sleep(random.random() * 0.02)  # que los dialogos terminen en otro orden que el del golden
        calls.append((dialogue["id"], criterion["id"]))
        verdict = "no_cumple" if (dialogue["id"], criterion["id"]) in {("d3", "dato"), ("d8", "global:sin-invenciones")} else "cumple"
        return {"verdict": verdict, "reason": "ok", "usage": {"input": 10, "cached": 0, "output": 5}}

    monkeypatch.setattr(jg, "GOLDEN_FILE", golden)
    monkeypatch.setattr(jg, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(jg, "_env", lambda name: "sk-test")
    monkeypatch.setattr(jg, "load_reference", lambda referencia=None: "REF")
    monkeypatch.setattr(jg, "llm_judge_criterion", _judge)
    assert jg.main(["--run", str(run), "--golden", str(golden), "--no-cache", "--paralelo", str(paralelo)]) == 0
    report = json.loads((tmp_path / "ronda__gpt-5-mini-medium.json").read_text(encoding="utf-8"))
    return report, calls


def test_en_paralelo_sale_lo_mismo_que_en_serie(monkeypatch, tmp_path):
    serie, calls_serie = _judge_main(monkeypatch, tmp_path, 1)
    paralelo, calls_paralelo = _judge_main(monkeypatch, tmp_path, 4)
    assert paralelo["dialogues"] == serie["dialogues"]
    assert [d["id"] for d in paralelo["dialogues"]] == [d["id"] for d in GOLDEN["dialogues"]], "en el orden del golden"
    assert paralelo["summary"] == serie["summary"] and paralelo["usage"] == serie["usage"]
    assert sorted(calls_paralelo) == sorted(calls_serie) and len(calls_serie) == 24
    for d in GOLDEN["dialogues"]:  # dentro de cada dialogo, el concreto antes que el general
        mine = [c for dd, c in calls_paralelo if dd == d["id"]]
        assert mine == ["dato", "global:sin-invenciones"]


def test_varios_hilos_no_pisan_lineas_de_la_cache(tmp_path):
    path = tmp_path / "cache.jsonl"

    def write(n):
        for i in range(50):
            jg.save_to_cache(f"k{n}-{i}", {"verdict": "cumple", "reason": "x" * 2000}, path)

    hilos = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 400 and len(jg.load_cache(path)) == 400
