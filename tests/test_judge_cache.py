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

    def _judge(client, model, effort, reference, dialogue, records, criterion, others=None, counted=None):
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


# ── g-8 (27-sep): "un fallo, un criterio" lo aplica el CODIGO, no el LLM ──────────────────────
# El general solo detecta y enumera problemas con cita; se descuentan los que citan lo mismo que un
# criterio concreto que ya suspendio (`discount_counted`).

RECS = [{"turn": 1, "msg": "quiero el curso", "conv": 1,
         "reply": "Me habias dicho: buceo certificado. Te cotizo el minicurso por 183 USD."}]


def test_el_general_no_ve_la_lista_de_fallos():
    msg = jg.judge_user_message(DIALOGUE, RECS, {"id": "global:sin-invenciones", "check": "no inventa"}, CRITERIA, [
        {"id": "precio-xyz", "reason": "MOTIVO-DEL-CONCRETO", "evidencia_bot": "Te cotizo el minicurso"}])
    assert "MOTIVO-DEL-CONCRETO" not in msg and "precio-xyz" not in msg and "problemas" in msg


def test_el_problema_con_la_misma_cita_se_descuenta():
    counted = [{"id": "precio", "evidencia_bot": "Te cotizo el minicurso por 183 USD"}]
    got = jg.discount_counted({"verdict": "no_cumple", "reason": "x", "problemas": [
        {"evidencia_bot": "Te cotizo el minicurso por 183 USD", "motivo": "cotiza otra cosa"}]}, counted, RECS)
    assert got["verdict"] == "cumple" and got["descontados"] == ["precio"]


def test_otro_hecho_en_la_misma_respuesta_no_se_descuenta():
    """El caso de la v7: el concreto suspende por el precio y el general por "Me habias dicho", que
    esta en la MISMA respuesta. Con la lista a la vista el LLM cedia; aqui no."""
    counted = [{"id": "precio", "evidencia_bot": "Me habias dicho: buceo certificado. Te cotizo el minicurso por 183 USD."}]
    got = jg.discount_counted({"verdict": "no_cumple", "reason": "x", "problemas": [
        {"evidencia_bot": "Me habias dicho: buceo certificado", "motivo": "dato no dicho"}]}, counted, RECS)
    assert got["verdict"] == "no_cumple" and "Me habias dicho" in got["evidencia_bot"]


def test_sin_cita_literal_el_problema_queda_en_revisar():
    got = jg.discount_counted({"verdict": "no_cumple", "reason": "x", "problemas": [
        {"evidencia_bot": "algo que el bot nunca dijo en esta charla", "motivo": "y"}]}, [], RECS)
    assert got["verdict"] == "revisar"


def test_el_descuento_se_aplica_en_judge_criteria(monkeypatch):
    def _judge(client, model, effort, reference, dialogue, records, criterion, others=None, counted=None):
        if criterion["id"] == "saludo":
            return {"verdict": "no_cumple", "reason": "dos saludos", "evidencia_bot": "Te cotizo el minicurso por 183 USD"}
        return {"verdict": "no_cumple", "reason": "igual", "problemas": [{"evidencia_bot": "Te cotizo el minicurso por 183 USD"}]}

    monkeypatch.setattr(jg, "llm_judge_criterion", _judge)
    crits = [{"id": "global:sin-invenciones", "check": "x"}, {"id": "saludo", "check": "y"}]
    out = jg.judge_criteria(object(), "m", None, "REF", DIALOGUE, RECS, crits, None, {"hits": 0, "misses": 0})
    assert [c["id"] for c in out] == ["global:sin-invenciones", "saludo"]
    assert out[0]["verdict"] == "cumple" and out[1]["verdict"] == "no_cumple"


def test_un_general_descuenta_lo_que_ya_conto_otro_general_anterior(monkeypatch):
    """Revision de la v7: el mismo "¿lo cambio?" suspendia sin-invenciones Y sin-repreguntas; las
    personas lo cuentan una vez, en sin-invenciones (va antes en el golden)."""
    cita = "Solo para confirmar, lo cambio? con certificacion de buceo"
    recs = [{"turn": 1, "msg": "como pago", "conv": 1, "reply": cita}]

    def _judge(client, model, effort, reference, dialogue, records, criterion, others=None, counted=None):
        return {"verdict": "no_cumple", "reason": "cambio sin motivo", "problemas": [{"evidencia_bot": cita}]}

    monkeypatch.setattr(jg, "llm_judge_criterion", _judge)
    crits = [{"id": "global:sin-invenciones", "check": "x"}, {"id": "global:sin-repreguntas", "check": "y"}]
    out = jg.judge_criteria(object(), "m", None, "REF", DIALOGUE, recs, crits, None, {"hits": 0, "misses": 0})
    assert out[0]["verdict"] == "no_cumple"
    assert out[1]["verdict"] == "cumple" and out[1]["descontados"] == ["global:sin-invenciones"]
