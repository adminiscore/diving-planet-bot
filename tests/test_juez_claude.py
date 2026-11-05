"""El juez con Claude Code: nunca factura a la API, va aislado y no toca el examen oculto sin pedirlo."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from scripts import juez_claude as jc


def _respuesta(veredictos):
    salida = {"result": json.dumps({"veredictos": veredictos}), "usage": {"input_tokens": 1}, "total_cost_usd": 0.0, "duration_ms": 10}
    return SimpleNamespace(stdout=json.dumps(salida), stderr="", returncode=0)


def test_el_entorno_no_lleva_claves_de_api(monkeypatch):
    for clave in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        monkeypatch.setenv(clave, "x")
    monkeypatch.setenv("OTRA", "y")
    entorno = jc.entorno()
    assert not {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"} & set(entorno)
    assert entorno["OTRA"] == "y"


def test_la_llamada_va_aislada_y_con_la_suscripcion(monkeypatch, tmp_path):
    vistos = {}

    def falso_run(cmd, **kw):
        vistos.update(cmd=cmd, **kw)
        return _respuesta([{"id": "c1", "verdict": "cumple"}])

    monkeypatch.setattr(subprocess, "run", falso_run)
    veredictos, _uso = jc.llamar("claude", tmp_path / "s.txt", "opus", "medium", "MENSAJE", str(tmp_path))
    assert veredictos == [{"id": "c1", "verdict": "cumple"}]
    assert "--bare" not in vistos["cmd"]  # anula la suscripción
    assert "--safe-mode" in vistos["cmd"] and "--no-session-persistence" in vistos["cmd"]
    assert vistos["cmd"][vistos["cmd"].index("--tools") + 1] == ""
    assert vistos["input"] == "MENSAJE" and vistos["cwd"] == str(tmp_path)


def test_al_agotar_el_uso_para_en_vez_de_insistir(monkeypatch, tmp_path):
    llamadas = []

    def falso_run(cmd, **kw):
        llamadas.append(cmd)
        return SimpleNamespace(stdout=json.dumps({"is_error": True, "result": "Usage limit reached"}), stderr="", returncode=1)

    monkeypatch.setattr(subprocess, "run", falso_run)
    with pytest.raises(jc.LimiteDeUsoError):
        jc.llamar("claude", tmp_path / "s.txt", "opus", "medium", "M", str(tmp_path))
    assert len(llamadas) == 1


@pytest.mark.parametrize(("con_oculto", "esperados"), [(False, ["visible"]), (True, ["visible", "oculto-1"])])
def test_el_oculto_no_se_juzga_sin_pedirlo(monkeypatch, tmp_path, capsys, con_oculto, esperados):
    golden = {"version": 1, "global_criteria": [], "dialogues": [
        {"id": "visible", "category": "x", "criteria": [{"id": "c1", "check": "algo"}]},
        {"id": "oculto-1", "category": "x", "suite": "oculto", "criteria": [{"id": "c1", "check": "algo"}]},
    ]}
    fichero = tmp_path / "golden.json"
    fichero.write_text(json.dumps(golden), encoding="utf-8")
    monkeypatch.setattr(jc, "GOLDEN_FILE", fichero)
    monkeypatch.setattr(jc, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(jc, "CACHE", tmp_path / "cache.jsonl")
    filas = [{"turn": 1, "msg": "hola", "reply": "hola", "conv": 1}]
    monkeypatch.setattr(jc, "latest_conversations", lambda _run: {"visible": filas, "oculto-1": filas})
    monkeypatch.setattr(jc, "preparar", lambda _args: {})
    juzgados = []

    def falso_juzgar(d, _records, _criterios, _ctx):
        juzgados.append(d["id"])
        return [{"id": "c1", "verdict": "cumple", "by": "claude-opus"}], {}

    monkeypatch.setattr(jc, "juzgar_dialogo", falso_juzgar)
    args = SimpleNamespace(run="x/ronda.jsonl", ids=None, con_oculto=con_oculto, paralelo=1, modelo="opus", esfuerzo="medium", sufijo="")
    assert jc.juzgar_ronda(args) == 0
    assert juzgados == esperados
    assert "oculto-1" not in capsys.readouterr().out


def test_una_tanda_se_juzga_con_los_generales_y_el_de_graves(monkeypatch, tmp_path, capsys):
    golden = {"version": 1, "global_criteria": [{"id": "x", "check": "algo"}], "dialogues": []}
    fichero = tmp_path / "golden.json"
    fichero.write_text(json.dumps(golden), encoding="utf-8")
    charlas = tmp_path / "charlas"
    charlas.mkdir()
    (charlas / "6908.jsonl").write_text(json.dumps({"turno": 1, "conv": 6908, "msg": "hola", "reply": "hola"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(jc, "GOLDEN_FILE", fichero)
    monkeypatch.setattr(jc, "CHARLAS", charlas)
    monkeypatch.setattr(jc, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(jc, "preparar", lambda _args: {})
    vistos = []

    def falso_juzgar(d, records, criterios, _ctx):
        vistos.append(([c["id"] for c in criterios], records[0]["turn"]))
        return [{"id": "sin-graves", "verdict": "no_cumple", "reason": "importe", "by": "claude-opus"}], {}

    monkeypatch.setattr(jc, "juzgar_dialogo", falso_juzgar)
    args = SimpleNamespace(charlas="6908", panel=None, nombre="s05d", paralelo=1, modelo="opus", esfuerzo="medium", sufijo="")
    assert jc.juzgar_charlas(args) == 0
    assert set(vistos[0][0]) == {"sin-graves", "global:x"} and vistos[0][1] == 1
    assert "1 de 1" in capsys.readouterr().out


def test_el_modelo_va_fijado_y_otro_modelo_no_se_cuenta(monkeypatch, tmp_path):
    """5-nov (Álvaro, #3513): el alias `opus` da modelos distintos según la versión de Claude Code."""
    pedidos, responde = [], ["claude-opus-5-5"]

    def correr(cmd, **_k):
        pedidos.append(cmd[cmd.index("--model") + 1])
        salida = {"result": json.dumps({"veredictos": []}), "modelUsage": {responde[0]: {}}}
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(salida))

    monkeypatch.setattr(jc.subprocess, "run", correr)
    assert jc.llamar("claude", tmp_path / "s.txt", "opus", "medium", "m", str(tmp_path))[0] == []
    assert pedidos == ["claude-opus-5-5"]
    responde[0] = "claude-opus-4-7"
    with pytest.raises(RuntimeError, match="no se compararía"):
        jc.llamar("claude", tmp_path / "s.txt", "opus", "medium", "m", str(tmp_path))


def test_el_panel_agrupa_cada_cliente_con_sus_turnos(tmp_path):
    fichero = tmp_path / "panel.jsonl"
    filas = [{"dialogo": "visto-1", "turn": 1, "msg": "a", "reply": "b"}, {"dialogo": "ciego-a01", "turn": 1, "msg": "c", "reply": "d"},
             {"dialogo": "visto-1", "turn": 2, "msg": "e", "reply": "f"}]
    fichero.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    clientes = jc._clientes_del_panel(str(fichero))
    assert [d["id"] for d, _ in clientes] == ["visto-1", "ciego-a01"]
    assert [r["turn"] for r in clientes[0][1]] == [1, 2]
    assert clientes[0][0]["criteria"] == [jc.CRITERIO_GRAVES]
