"""Mapa de Coral (`scripts/arquitectura.py`, 29-sep): el mapa no puede quedarse atrás del código.

1. Hoy todo cuadra: cada nodo del grafo y del subgrafo de la reserva tiene descripción, y cada fichero, función,
   interruptor y modelo citado en `docs/arquitectura/componentes.json` existe.
2. Si alguien añade un nodo al grafo sin describirlo, o borra una función que el mapa cita, la validación lo dice.
3. El historial solo cuenta cambios de estructura (piezas, flechas, interruptores, modelos), no de tiempos.
"""

import copy
import json

from scripts import arquitectura as arq


def _entradas():
    curado = json.loads(arq.CURADO.read_text(encoding="utf-8"))
    bools, modelos, _ = arq.ajustes()
    return curado, arq.grafos(), bools, modelos


def test_el_mapa_esta_al_dia_con_el_codigo():
    curado, g, bools, modelos = _entradas()
    assert arq.validar(curado, g, bools, modelos) == []


def test_un_nodo_nuevo_sin_describir_hace_fallar():
    curado, g, bools, modelos = _entradas()
    g = copy.deepcopy(g)
    g["general"]["nodos"].append("pagos")
    errores = arq.validar(curado, g, bools, modelos)
    assert any("'pagos'" in e and "componentes.json" in e for e in errores)


def test_una_funcion_citada_que_ya_no_existe_hace_fallar():
    curado, g, bools, modelos = _entradas()
    curado = copy.deepcopy(curado)
    curado["componentes"][0]["donde"] = "src/agents/rag_agent.py:funcion_que_no_existe"
    curado["componentes"][1]["interruptores"] = ["flag_inventado"]
    errores = arq.validar(curado, g, bools, modelos)
    assert any("funcion_que_no_existe" in e for e in errores)
    assert any("flag_inventado" in e for e in errores)


def test_el_historial_ignora_los_tiempos():
    curado, g, bools, modelos = _entradas()
    _, _, pre = arq.ajustes()
    sin = arq.construir(curado, g, bools, modelos, pre, None, {})
    con = arq.construir(curado, g, bools, modelos, pre, None, {"nodes": {"router": {"n": 9, "p50": 1.0, "p95": 2.0}}})
    assert arq.estructura(sin) == arq.estructura(con)
    delta = arq.cambios(arq.estructura(sin), {**arq.estructura(sin), "interruptores": {}})
    assert delta["interruptores"] and not delta["piezas_nuevas"]


def test_un_interruptor_nuevo_sin_frase_en_llano_hace_fallar():
    curado, g, bools, modelos = _entradas()
    bools = {**bools, "flag_nuevo_de_prueba": False}
    errores = arq.validar(curado, g, bools, modelos)
    assert any("flag_nuevo_de_prueba" in e and "llano" in e for e in errores)


def test_cada_pieza_con_modelo_o_servicio_lleva_un_logo_que_existe():
    curado, g, bools, modelos = _entradas()
    _, _, pre = arq.ajustes()
    datos = arq.construir(curado, g, bools, modelos, pre, None, {})
    logos = json.loads(arq.LOGOS.read_text(encoding="utf-8"))["logos"]
    for c in datos["componentes"]:
        if c["modelos"]:
            assert c.get("marca") in logos, c["id"]
    assert {c["id"]: c["marca"] for c in datos["componentes"] if c["id"] in ("router", "r_revisor")} == {
        "router": "openrouter", "r_revisor": "openai"}
    curado = copy.deepcopy(curado)
    curado["componentes"][0]["marca"] = "logo_inventado"
    assert any("logo_inventado" in e for e in arq.validar(curado, g, bools, modelos))


def test_reparto_del_rag_medido_con_los_logs_de_la_ronda(tmp_path, monkeypatch):
    """Cada escritura pasa por las comprobaciones y el revisor; cada rechazo es un intento más. Las cuentas cuadran:
    aprobadas + rechazos = intentos, y los repartos de cada pieza suman 1."""
    logs = tmp_path / "docs" / "robustness"
    logs.mkdir(parents=True)
    lineas = (["INFO: [RAG] Query: x... | Docs: 8"] * 37
              + ["INFO: [RAG][GROUNDING] attempt 1 rejected (HALLUCINATED - x NO) query=y"] * 7
              + ["WARNING: [RAG][GROUNDING] Rejecting after 2 attempts query=y reason=HALLUCINATED - x NO"] * 3)
    (logs / "logs-pre-ronda-x.txt").write_text("\n".join(lineas), encoding="utf-8")
    monkeypatch.setattr(arq, "ROOT", tmp_path)
    r = arq.conteos_rag(tmp_path / "ronda-x.json")
    assert r["conteos"] == {"r_escribir": 47, "r_guardas": 47, "r_revisor": 47, "r_reintento": 10, "r_nolotengo": 3, "r_salida": 37}
    pesos = r["pesos"]
    assert pesos[("r_revisor", "r_reintento")] == round(10 / 47, 4)
    assert pesos[("r_reintento", "r_nolotengo")] == 0.3
    for origen in ("r_guardas", "r_revisor", "r_reintento"):
        assert abs(sum(v for (de, _), v in pesos.items() if de == origen) - 1) < 1e-3
    assert arq.conteos_rag(tmp_path / "sin-log.json") is None
