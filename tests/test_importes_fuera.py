"""Simplificar (10-nov): el contador de importes fuera del catálogo."""
import json

from scripts.importes_fuera import contar


def test_un_precio_del_catalogo_con_decimales_no_cuenta_como_fuera(tmp_path):
    f = tmp_path / "x.jsonl"
    filas = [{"dialogo": "d1", "reply": "El snorkel sale en USD 125.57 por persona online.", "estado": {}},
             {"dialogo": "d1", "reply": "Para los tres serían 567.000 COP en total.", "estado": {}}]
    f.write_text("".join(json.dumps(x) + "\n" for x in filas), encoding="utf-8")
    c = contar([f])
    assert (c["importes_citados"], c["importes_fuera"]) == (2, 1)
