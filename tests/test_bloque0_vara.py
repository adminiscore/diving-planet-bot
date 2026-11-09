"""Bloque 0 (10-nov): el reloj fijo del panel, la hora para el juez, la huella de su referencia y el marcador. Sin IA."""
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from scripts import marcador
from scripts.juez_claude import hora_de_la_charla, mensaje_del_dialogo
from scripts.reproducir_juez_pre import RELOJ_ANTES, RELOJ_DESPUES, relojes_de

RAIZ = Path(__file__).resolve().parents[1]
PANEL = RAIZ / "docs/robustness/caln/panel-graves.json"


def test_el_reloj_alterno_reparte_el_panel_en_las_dos_horas_y_no_cambia():
    ids = [d["id"] for d in json.loads(PANEL.read_text(encoding="utf-8"))["dialogos"]]
    una, otra = relojes_de(ids, "alterno"), relojes_de(ids, "alterno")
    assert una == otra
    assert set(una.values()) == {RELOJ_ANTES, RELOJ_DESPUES}
    antes = sum(v == RELOJ_ANTES for v in una.values())
    assert 0.25 * len(ids) <= antes <= 0.75 * len(ids)


def test_las_dos_horas_son_de_un_jueves_antes_y_despues_del_cierre():
    antes, despues = datetime.fromisoformat(RELOJ_ANTES), datetime.fromisoformat(RELOJ_DESPUES)
    assert antes.weekday() == despues.weekday() == 3
    assert (antes.hour, antes.minute) < (16, 30) < (despues.hour, despues.minute)


def test_sin_reloj_va_la_hora_real_y_sin_zona_no_vale():
    assert relojes_de(["x"], None) == {}
    assert relojes_de(["x"], "antes") == {"x": RELOJ_ANTES}
    with pytest.raises(SystemExit):
        relojes_de(["x"], "2026-11-12T10:30")


def test_el_juez_recibe_la_hora_y_sin_reloj_el_mensaje_no_cambia():
    sin = [{"turn": 1, "msg": "hola", "reply": "hola"}]
    con = [{**sin[0], "reloj": RELOJ_DESPUES}]
    assert hora_de_la_charla(sin) == ""
    assert "jueves 2026-11-12, 20:30" in hora_de_la_charla(con)
    dialogo = {"id": "d", "category": "sparring"}
    assert mensaje_del_dialogo(dialogo, sin, []).startswith("CONVERSACION")  # la caché de lo ya juzgado sigue valiendo
    assert mensaje_del_dialogo(dialogo, con, []).startswith("HORA DE LA CHARLA")


def test_la_hora_del_bot_solo_se_lee_en_contexto_rag():
    """El reloj fijo la sustituye ahí: otra lectura de la hora en src lo saltaría sin avisar."""
    lecturas = sorted(str(p.relative_to(RAIZ)).replace("\\", "/") for p in (RAIZ / "src").rglob("*.py")
                      if re.search(r"datetime\.now\(|date\.today\(", p.read_text(encoding="utf-8")))
    assert lecturas == ["src/agents/rutas/contexto_rag.py"]


def _juicio(tmp: Path, nombre: str, graves: set[str], huella: str | None = "h1") -> Path:
    ids = ["visto-1", "visto-2", "visto-3", "visto-4", "visto-5"]
    datos = {"huella_referencia": huella, "dialogues": [
        {"id": i, "criteria": [{"id": "sin-graves", "verdict": "no_cumple" if i in graves else "cumple"}]} for i in ids]}
    f = tmp / nombre
    f.write_text(json.dumps(datos), encoding="utf-8")
    return f


def test_el_marcador_cuenta_la_bajada_solo_si_pasa_del_ruido(tmp_path):
    a = marcador.lado([_juicio(tmp_path, "a1", {"visto-1", "visto-2", "visto-3", "visto-4", "visto-5"}),
                       _juicio(tmp_path, "a2", {"visto-1", "visto-2", "visto-3", "visto-4", "visto-5"})])
    b = marcador.lado([_juicio(tmp_path, "b1", set()), _juicio(tmp_path, "b2", {"visto-1"})])
    c = marcador.comparar(a, b)
    assert (a["media"], b["media"]) == (5, 0.5)
    assert c["cuenta"] and c["misma_referencia"]
    assert len(c["mejoran"]) == 5 and c["igual"] == 0  # visto-1 pasa de grave en los dos juicios a grave en uno
    poco = marcador.comparar(a, marcador.lado([_juicio(tmp_path, "b3", {"visto-1", "visto-2"})]))
    assert not poco["cuenta"]


def test_el_marcador_avisa_si_la_referencia_del_juez_no_es_la_misma(tmp_path):
    a = marcador.lado([_juicio(tmp_path, "a1", set(), "h1")])
    b = marcador.lado([_juicio(tmp_path, "b1", set(), None)])
    assert not marcador.comparar(a, b)["misma_referencia"]
    assert "OJO" in marcador.informe(a, b, None, None)


def test_el_estilo_frente_a_la_persona(tmp_path):
    filas = [{"reply": "El precio es 630.000 COP. ¿Te paso el enlace?",
              "metricas": [{"llamadas": [{"p": "jev"}, {"p": "extractor"}, {"p": "embedding"}]}]},
             {"reply": "Reserva aquí: https://book.divingplanet.org/x", "metricas": [{"llamadas": [{"p": "jev"}]}]}]
    f = tmp_path / "panel.jsonl"
    f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in filas), encoding="utf-8")
    e = marcador.estilo([f])
    assert (e["turnos"], e["llamadas_por_turno"], e["con_pregunta"], e["con_precio"], e["con_enlace"]) == (2, 1.5, 50, 50, 50)
