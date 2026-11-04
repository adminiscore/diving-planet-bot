"""#3149 → #3183 (4-nov): una medida con el extractor en respaldo en 18 de 27 turnos se dio por limpia: los respaldos van dentro
de `llamadas` y cada uno los contaba a mano."""
from scripts.reproducir_juez_pre import _turno_con_lectura_de_respaldo, respaldos_por_pieza


def _fila(*piezas):
    return {"metricas": [{"llamadas": [{"p": p} for p in piezas]}]}


def test_cuenta_los_respaldos_por_pieza():
    filas = [_fila("jev", "extractor", "rag_escritor"), _fila("extractor_respaldo", "rag_respaldo"), _fila("extractor_respaldo")]
    assert respaldos_por_pieza(filas) == {"extractor_respaldo": 2, "rag_respaldo": 1}


def test_sin_respaldos_ni_metricas_no_cuenta_nada():
    assert respaldos_por_pieza([_fila("jev", "extractor"), {"metricas": None}, {}]) == {}


def test_el_del_extractor_y_el_del_lector_invalidan_el_del_escritor_no():
    assert _turno_con_lectura_de_respaldo(_fila("extractor_respaldo"))
    assert _turno_con_lectura_de_respaldo(_fila("lector_grupo_respaldo"))
    assert not _turno_con_lectura_de_respaldo(_fila("rag_respaldo", "extractor"))
