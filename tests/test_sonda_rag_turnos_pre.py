"""`scripts/sonda_rag_turnos_pre.py` (escalón 0 del RAG dentro de PRE): arma los casos sin tocar PRE.

Se fija lo que protege la medida: el examen oculto se salta siempre, el historial es el real de la ronda (solo
turnos anteriores de la misma conversación) y los turnos del RAG se sacan de las líneas `[RAG] Query` del log.
"""

from scripts.sonda_rag_turnos_pre import construir_casos, resumen, turnos_del_log

ROWS = [
    {"tag": "d1", "conv": 1, "turn": 1, "msg": "hola", "reply": "¡Hola!"},
    {"tag": "d1", "conv": 1, "turn": 2, "msg": "¿cuánto cuesta el minicurso?", "reply": "183 USD"},
    {"tag": "d1", "conv": 1, "turn": 3, "msg": "and how do i pay?", "reply": "..."},
    {"tag": "d2", "conv": 2, "turn": 1, "msg": "¿dónde nos vemos?", "reply": "Muelle"},
    {"tag": "secreto", "conv": 3, "turn": 1, "msg": "hola", "reply": "..."},
]


def test_historial_real_e_idioma():
    casos, saltados = construir_casos(ROWS, ["d1#3"], oculto=set())
    assert saltados == []
    (c,) = casos
    assert c["lang"] == "en"
    assert [m["content"] for m in c["history"]] == ["hola", "¡Hola!", "¿cuánto cuesta el minicurso?", "183 USD"]


def test_el_examen_oculto_se_salta_siempre():
    casos, saltados = construir_casos(ROWS, ["secreto#1", "d2#1"], oculto={"secreto"})
    assert [c["id"] for c in casos] == ["d2#1"] and saltados == ["secreto#1"]


def test_turnos_del_log(tmp_path):
    log = tmp_path / "logs.txt"
    log.write_text("INFO: [RAG] Query: ¿cuánto cuesta el minic... | Docs: 8 | Tokens: 1\n"
                   "INFO: [RAG] Query: ¿dónde nos vemos?... | Docs: 3 | Tokens: 1\n", encoding="utf-8")
    assert turnos_del_log(log, ROWS) == ["d1#2", "d2#1"]


def test_resumen():
    filas = [{"chars": 100, "s": 2.0, "fallback": False, "error": False, "juicios": [{"ok": False}, {"ok": True}]},
             {"chars": 300, "s": 4.0, "fallback": True, "error": False, "juicios": [{"ok": False}, {"ok": False}]}]
    txt = resumen(filas)
    assert '"no lo tengo" 1' in txt and "rechazos del juez 3" in txt
