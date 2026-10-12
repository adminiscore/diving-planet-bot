"""ex-0 (fase EX, 12-oct): el banco de extracción y su puntuación (`scripts.run_extraction_eval --banco ex0`)."""
from scripts.run_extraction_eval import casos_ex0, puntuar_ex0


def test_el_banco_tiene_los_casos_y_los_dos_grupos():
    casos = casos_ex0()
    assert len(casos) >= 280
    grupos = {c["grupo"] for c in casos}
    assert grupos == {"diseño", "ciego"}
    # Un diálogo entero va a un solo grupo (si no, el ciego no sería ciego).
    por_dialogo = {}
    for c in casos:
        por_dialogo.setdefault(c["dialogo"], set()).add(c["grupo"])
    assert all(len(g) == 1 for g in por_dialogo.values())


def test_lo_ya_dicho_llega_como_estado_del_turno():
    casos = {c["id"]: c for c in casos_ex0()}
    # 'no, buceé hace poco' contesta la pregunta de seguridad: la actividad ya se sabía de antes.
    caso = casos["ex0-reserva-completa-saludo-a-pago-t5"]
    assert caso["sabido"]["activity"] == "certified_diving"
    assert caso["slot"] == "safety"


def test_un_dato_que_el_cliente_no_dijo_es_un_invento():
    r = puntuar_ex0({"location": "island"}, {})
    assert r["inventado"] == ["location"]


def test_lo_ya_sabido_y_lo_coherente_no_es_invento():
    assert puntuar_ex0({"activity": "certified_diving"}, {}, {"activity": "certified_diving"})["inventado"] == []
    assert puntuar_ex0({"is_certified": False}, {"activity": "minicourse"})["inventado"] == []
    assert puntuar_ex0({"group_allocation": {"snorkel": 2}}, {"activity": "snorkel", "group_size": 2})["inventado"] == []


def test_acierto_equivocado_y_perdido():
    r = puntuar_ex0({"group_size": 3, "location": "cartagena"},
                    {"group_size": 3, "location": "island", "is_colombian": True})
    assert r["acierto"] == ["group_size"]
    assert r["equivocado"] == ["location"]
    assert r["perdido"] == ["is_colombian"]
