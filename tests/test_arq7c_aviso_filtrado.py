"""ARQ-7c (23-oct, flag `aviso_final_filtrado`): el aviso final descarta el aviso que no casa con el turno (su tema no
está entre los de los documentos, o su actividad no está entre las que constan, si consta alguna). Con DeepSeek Flash
metía «el minicurso no certifica» de relleno (banco arq-7c: 9 avisos que no tocaban frente a 1 con Luna). Sin red."""
from src.flows import avisos


def _aviso(aviso_id):
    return avisos.por_id(aviso_id)


def test_sin_su_tema_no_casa():
    minicurso = _aviso("minicurso-no-certifica")
    hechos = {"actividades": {"minicourse"}}
    assert avisos.casa_con_el_turno(minicurso, hechos, {"certificacion"})
    assert not avisos.casa_con_el_turno(minicurso, hechos, {"fotos"})


def test_la_actividad_solo_cuenta_si_consta_alguna():
    minicurso = _aviso("minicurso-no-certifica")
    assert not avisos.casa_con_el_turno(minicurso, {"actividades": {"snorkel"}}, {"certificacion"})
    assert avisos.casa_con_el_turno(minicurso, {"actividades": set()}, {"certificacion"})
    assert avisos.casa_con_el_turno(minicurso, None, {"certificacion"})


def test_sin_condiciones_de_tema_ni_actividad_casa_siempre():
    assert avisos.casa_con_el_turno(_aviso("solo-operamos-en-rosario"), None, set())
