"""Cache de veredictos del juez (protocolo de medición, 24-sep-2026).

No se vuelve a pagar por juzgar lo ya juzgado: un veredicto se reutiliza SOLO si la
pregunta al juez es exactamente la misma (modelo, esfuerzo, referencia, prompt y mensaje).
"""

from scripts import judge_golden_set as jg

DIALOGUE = {"id": "d1", "category": "reserva"}
RECORDS = [{"turn": 1, "msg": "hola", "reply": "¡Hola! Soy Coral", "conv": 1}]
CRITERIA = [{"id": "saludo", "check": "saluda una vez"}, {"id": "global:idioma", "check": "responde en el idioma"}]


def test_la_clave_cambia_con_lo_que_cambia_la_pregunta():
    base = jg.cache_key("gpt-5-mini", "medium", "REF", "mensaje")
    assert base == jg.cache_key("gpt-5-mini", "medium", "REF", "mensaje")
    assert base != jg.cache_key("gpt-5-mini", "medium", "REF 2", "mensaje")  # otra base de conocimiento
    assert base != jg.cache_key("gpt-5-mini", "low", "REF", "mensaje")  # otro esfuerzo
    assert base != jg.cache_key("gpt-5", "medium", "REF", "mensaje")  # otro juez
    assert base != jg.cache_key("gpt-5-mini", "medium", "REF", "mensaje distinto")  # otro texto del bot


def _fake_judge(monkeypatch, verdict="cumple"):
    calls = []

    def _judge(client, model, effort, reference, dialogue, records, criterion, others=None):
        calls.append(criterion["id"])
        return {"verdict": verdict, "reason": "ok", "usage": {"input": 10, "cached": 0, "output": 5}}

    monkeypatch.setattr(jg, "llm_judge_criterion", _judge)
    saved = []
    monkeypatch.setattr(jg, "save_to_cache", lambda key, result, path=None: saved.append(key))
    return calls, saved


def test_lo_ya_juzgado_no_se_vuelve_a_pagar(monkeypatch):
    calls, saved = _fake_judge(monkeypatch)
    cache, stats = {}, {"hits": 0, "misses": 0}
    first = jg.judge_criteria(object(), "gpt-5-mini", "medium", "REF", DIALOGUE, RECORDS, CRITERIA, cache, stats)
    assert calls == ["saludo", "global:idioma"] and len(saved) == 2
    second = jg.judge_criteria(object(), "gpt-5-mini", "medium", "REF", DIALOGUE, RECORDS, CRITERIA, cache, stats)
    assert calls == ["saludo", "global:idioma"], "la segunda vez no llama al juez"
    assert stats == {"hits": 2, "misses": 2}
    assert [c["verdict"] for c in second] == [c["verdict"] for c in first]
    assert all(c.get("cached") for c in second)


def test_si_cambia_el_texto_del_bot_se_juzga_de_nuevo(monkeypatch):
    calls, _ = _fake_judge(monkeypatch)
    cache, stats = {}, {"hits": 0, "misses": 0}
    jg.judge_criteria(object(), "gpt-5-mini", "medium", "REF", DIALOGUE, RECORDS, CRITERIA, cache, stats)
    otro = [{**RECORDS[0], "reply": "¡Hola! Soy Coral, ¿en qué te ayudo?"}]
    jg.judge_criteria(object(), "gpt-5-mini", "medium", "REF", DIALOGUE, otro, CRITERIA, cache, stats)
    assert len(calls) == 4 and stats["hits"] == 0


def test_los_errores_no_se_guardan(tmp_path):
    path = tmp_path / "cache.jsonl"
    jg.save_to_cache("k1", {"verdict": "error", "reason": "sin json"}, path)
    jg.save_to_cache("k2", {"verdict": "no_cumple", "reason": "x", "usage": {"input": 1}}, path)
    cache = jg.load_cache(path)
    assert set(cache) == {"k2"} and "usage" not in cache["k2"]


def test_sin_cache_se_juzga_todo(monkeypatch):
    calls, _ = _fake_judge(monkeypatch)
    stats = {"hits": 0, "misses": 0}
    for _ in range(2):
        jg.judge_criteria(object(), "gpt-5-mini", "medium", "REF", DIALOGUE, RECORDS, CRITERIA, None, stats)
    assert len(calls) == 4
