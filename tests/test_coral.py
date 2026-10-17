"""Coral (tools/coral): el chat entre los Claude del equipo. El servidor con SQLite en memoria, el MCP y los hooks."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CORAL = Path(__file__).resolve().parent.parent / "tools" / "coral"
sys.path.insert(0, str(CORAL))

import cliente  # noqa: E402
import hook  # noqa: E402
import mcp_server  # noqa: E402

TOKENS = {"tok-g": "gadea", "tok-a": "alvaro", "tok-o": "gonzalo"}


def _cargar_app():
    spec = importlib.util.spec_from_file_location("coral_hub_app", CORAL / "hub" / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


hub = _cargar_app()


@pytest.fixture
def api():
    cliente_http = TestClient(hub.crear_app(":memory:", TOKENS))

    def como(token):
        def llamar(metodo, ruta, **kw):
            return cliente_http.request(metodo, ruta, headers={"Authorization": f"Bearer {token}"}, **kw)
        return llamar

    return {"g": como("tok-g"), "a": como("tok-a"), "o": como("tok-o"), "nadie": como("malo")}


def test_sin_token_no_entra(api):
    assert api["nadie"]("GET", "/api/yo").status_code == 401
    assert api["g"]("GET", "/api/yo").json() == {"persona": "gadea", "personas": ["alvaro", "gadea", "gonzalo"]}


def test_la_bandeja_entrega_una_vez_y_no_lo_propio(api):
    for p in "gao":  # cada uno nace con la bandeja al día
        api[p]("GET", "/api/yo")
    api["g"]("POST", "/api/mensajes", json={"texto": "voy con cal-a", "tipo": "aviso"})
    api["a"]("POST", "/api/mensajes", json={"texto": "solo para gonzalo", "para": "gonzalo"})
    assert api["g"]("GET", "/api/bandeja").json() == []
    a = api["a"]("GET", "/api/bandeja").json()
    assert [m["texto"] for m in a] == ["voy con cal-a"]
    assert api["a"]("GET", "/api/bandeja").json() == []  # ya entregado
    assert [m["texto"] for m in api["o"]("GET", "/api/bandeja").json()] == ["voy con cal-a", "solo para gonzalo"]


def test_el_que_llega_nuevo_no_recibe_el_historial(api):
    api["g"]("POST", "/api/mensajes", json={"texto": "viejo"})
    assert api["a"]("GET", "/api/bandeja").json() == []


def test_solo_se_responde_a_preguntas(api):
    aviso = api["g"]("POST", "/api/mensajes", json={"texto": "subo en 5 min"}).json()
    r = api["a"]("POST", "/api/mensajes", json={"texto": "ok", "tipo": "respuesta", "responde_a": aviso["id"]})
    assert r.status_code == 400
    pregunta = api["g"]("POST", "/api/mensajes", json={"texto": "¿mides?", "tipo": "pregunta", "para": "alvaro"}).json()
    r = api["a"]("POST", "/api/mensajes", json={"texto": "no", "tipo": "respuesta", "responde_a": pregunta["id"]})
    assert r.status_code == 200
    assert r.json()["para"] == "gadea"  # la respuesta va, por defecto, a quien preguntó


def _decir(api, quien, **campos):
    return api[quien]("POST", "/api/mensajes", json=campos)


def test_flujo_de_una_propuesta(api):
    """Álvaro propone; Gadea la ratifica y dice que la cambia (UNA vez), y al terminar le pasa el resultado."""
    p = _decir(api, "a", texto="Tu reescritura rompe el caso cal-22 (commit abc)", tipo="propuesta", para="gadea").json()
    assert _decir(api, "o", texto="yo no", tipo="respuesta", responde_a=p["id"]).status_code == 400  # no era para él
    r = _decir(api, "g", texto="Tienes razón, lo cambio así: ...", tipo="respuesta", responde_a=p["id"])
    assert r.status_code == 200 and r.json()["para"] == "alvaro"
    assert _decir(api, "g", texto="y otra cosa", tipo="respuesta", responde_a=p["id"]).status_code == 400
    hecho = _decir(api, "g", texto="Hecho en def456: cal-22 3/3", tipo="resultado", responde_a=p["id"])
    assert hecho.status_code == 200 and hecho.json()["para"] == "alvaro"
    assert _decir(api, "a", texto="gracias", tipo="respuesta", responde_a=hecho.json()["id"]).status_code == 400


def test_un_rechazo_se_rebate_una_sola_vez(api):
    p = _decir(api, "a", texto="cambia X", tipo="propuesta", para="gadea").json()
    no = _decir(api, "g", texto="No, porque Y", tipo="respuesta", responde_a=p["id"]).json()
    assert _decir(api, "o", texto="me meto", tipo="propuesta", responde_a=no["id"]).status_code == 400
    contra = _decir(api, "a", texto="Mira esta medida Z", tipo="propuesta", para="gadea", responde_a=no["id"])
    assert contra.status_code == 200
    no2 = _decir(api, "g", texto="Sigue sin ser", tipo="respuesta", responde_a=contra.json()["id"]).json()
    r = _decir(api, "a", texto="otra vez", tipo="propuesta", para="gadea", responde_a=no2["id"])
    assert r.status_code == 400 and "personas" in r.json()["detail"]


def test_texto_del_commit():
    ficheros = [f"f{i}.py" for i in range(10)]
    texto = hook.texto_commit("be0bc70", "feat(cal-a6): el aviso al final", "feature/pre_gadea", ficheros)
    assert texto.startswith("commit be0bc70 en feature/pre_gadea: feat(cal-a6): el aviso al final (10 ficheros: f0.py")
    assert texto.endswith("f7.py y 2 más)")


def test_para_desconocido_y_tope_de_mensajes(api):
    assert api["g"]("POST", "/api/mensajes", json={"texto": "x", "para": "pepe"}).status_code == 400
    for i in range(hub.MAX_POR_VENTANA):
        assert api["g"]("POST", "/api/mensajes", json={"texto": f"m{i}"}).status_code == 200
    assert api["g"]("POST", "/api/mensajes", json={"texto": "uno más"}).status_code == 429


def test_pre_ocupado_se_anuncia_y_caduca(api):
    api["a"]("GET", "/api/yo")
    e = api["g"]("PUT", "/api/estado", json={"tarea": "cal-a", "pre": "midiendo", "minutos": 30}).json()
    assert e["pre"] == "midiendo" and e["pre_hasta"]
    aviso = api["a"]("GET", "/api/bandeja").json()
    assert len(aviso) == 1 and aviso[0]["origen"] == "sistema" and aviso[0]["texto"].startswith("PRE: midiendo")
    api["g"]("PUT", "/api/estado", json={"pre": "libre"})
    assert api["a"]("GET", "/api/bandeja").json()[0]["texto"] == "PRE: libre"
    # Un estado caducado cuenta como libre aunque nadie lo haya soltado
    api["g"]("PUT", "/api/estado", json={"pre": "subiendo", "minutos": 1})
    hub_estado = {e["persona"]: e for e in api["a"]("GET", "/api/equipo").json()["equipo"]}
    assert hub_estado["gadea"]["pre"] == "subiendo"


def test_pre_caducado_es_libre():
    app = hub.crear_app(":memory:", TOKENS)
    c = TestClient(app)
    cab = {"Authorization": "Bearer tok-g"}
    c.put("/api/estado", json={"pre": "midiendo", "minutos": 5}, headers=cab)
    pasado = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    real = hub._ahora
    hub._ahora = lambda: datetime.fromisoformat(pasado)
    try:
        equipo = {e["persona"]: e for e in c.get("/api/equipo", headers=cab).json()["equipo"]}
    finally:
        hub._ahora = real
    assert equipo["gadea"]["pre"] == "libre"


def test_latido_detecta_solapes(api):
    api["a"]("POST", "/api/latido", json={"rama": "feature/pre_alvaro", "ficheros": ["src/config.py", "a.py"]})
    r = api["g"]("POST", "/api/latido", json={"rama": "feature/pre_gadea", "ficheros": ["src/config.py", "b.py"]})
    assert r.json()["solapes"] == [{"persona": "alvaro", "ficheros": ["src/config.py"]}]


def test_la_espera_devuelve_lo_que_ya_hay_sin_esperar(api):
    api["a"]("GET", "/api/yo")
    api["g"]("POST", "/api/mensajes", json={"texto": "hola"})
    assert [m["texto"] for m in api["a"]("GET", "/api/bandeja?esperar=20").json()] == ["hola"]


def test_mcp_initialize_y_herramientas(monkeypatch):
    monkeypatch.setattr(cliente, "config", lambda: {"CORAL_PERSONA": "gadea", "CORAL_URL": "x"})
    r = mcp_server.atender({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2025-06-18"}})
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert "Eres el Claude de gadea" in r["result"]["instructions"]
    assert len(r["result"]["instructions"]) < 4096  # el límite de Claude Code para instrucciones de servidor
    assert mcp_server.atender({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    nombres = [t["name"] for t in mcp_server.atender({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
               ["result"]["tools"]]
    assert nombres == ["decir", "bandeja", "historial", "equipo", "mi_estado"]


def test_mcp_un_fallo_de_red_es_error_de_herramienta(monkeypatch):
    def falla(*a, **k):
        raise cliente.CoralError("no hay conexión")
    monkeypatch.setattr(cliente, "llamar", falla)
    r = mcp_server.atender({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "bandeja", "arguments": {}}})
    assert r["result"]["isError"] and "no hay conexión" in r["result"]["content"][0]["text"]


@pytest.mark.parametrize("comando, rama, esperado", [
    ("git push", "feature/pre_gadea", "feature/pre_gadea"),
    ("git push origin", "feature/pre_gadea", "feature/pre_gadea"),
    ("git push -u origin feature/pre_alvaro", "main", "feature/pre_alvaro"),
    ("git push origin HEAD:feature/pre_gadea && echo ok", "feature/dev_gadea", "feature/pre_gadea"),
    ("git push origin feature/dev_gadea", "feature/pre_gadea", None),
    ("git push", "feature/dev_gadea", None),
    ("git status; git log", "feature/pre_gadea", None),
    ("git fetch origin; git push; echo pre_x", "feature/dev_gadea", None),
])
def test_destino_pre(comando, rama, esperado):
    assert hook.destino_pre(comando, rama) == esperado


def test_ficheros_con_cambios_ignora_salidas_de_medidas():
    porcelana = "\n".join([
        " M src/agents/rag_plan.py",
        " M docs/robustness/golden-set/results/judge-cache.jsonl",
        "?? docs/robustness/cal/medidas/x.json",
        "?? tests/test_nuevo.py",
        "?? notas.txt",
        "R  src/viejo.py -> src/nuevo.py",
    ])
    assert hook.ficheros_con_cambios(porcelana) == ["src/agents/rag_plan.py", "src/nuevo.py", "tests/test_nuevo.py"]


def test_push_bloquea_si_otro_mide(monkeypatch, capsys):
    equipo = {"yo": "gadea", "equipo": [
        {"persona": "gadea", "pre": "libre", "pre_hasta": None, "nota": "", "tarea": ""},
        {"persona": "alvaro", "pre": "midiendo", "pre_hasta": "2026-10-17T16:30:00+00:00", "nota": "", "tarea": "cal-c"}]}
    llamadas = []
    monkeypatch.setattr(cliente, "configurado", lambda: True)
    monkeypatch.setattr(cliente, "llamar", lambda m, r, d=None, timeout=10: llamadas.append((m, r)) or equipo)
    monkeypatch.setattr(hook, "rama_actual", lambda cwd: "feature/pre_gadea")
    hook.push({"tool_input": {"command": "git push"}, "cwd": "."})
    salida = json.loads(capsys.readouterr().out)
    assert salida["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "alvaro está midiendo" in salida["hookSpecificOutput"]["permissionDecisionReason"]
    assert ("PUT", "/api/estado") not in llamadas
    hook.push({"tool_input": {"command": "CORAL_FORZAR=1 git push"}, "cwd": "."})
    assert capsys.readouterr().out == "" and ("PUT", "/api/estado") in llamadas
