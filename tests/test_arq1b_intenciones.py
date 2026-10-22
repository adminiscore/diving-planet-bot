"""ARQ-1b (22-oct, flag `hechos_por_codigo`): Jev da las intenciones del mensaje (una pregunta sí/no por intención, en
la llamada de siempre) y el grafo las deja en el estado del turno para los hechos por código."""
from src.agents import jev_router as j
from src.config import settings
from src.flows import hechos
from src.orchestration import graph


def test_las_preguntas_solo_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "hechos_por_codigo", False)
    q = j._questions_for_turn()
    assert j.PIDE_REQUISITOS not in q and j.PIDE_QUE_INCLUYE not in q
    monkeypatch.setattr(settings, "hechos_por_codigo", True)
    q = j._questions_for_turn()
    assert {j.PIDE_REQUISITOS, j.PIDE_HORARIO, j.PIDE_DISPONIBILIDAD, j.PIDE_EDAD, j.PIDE_ENLACE,
            j.PIDE_QUE_INCLUYE, j.PIDE_PRECIO} <= set(q)


def test_umbral_de_cada_intencion():
    out = j.answers_to_signals({j.PIDE_EDAD: {"noul": 0.97}, j.PIDE_REQUISITOS: {"noul": 0.53}})
    assert out[j.PIDE_EDAD] is True and out[j.PIDE_REQUISITOS] is False


def test_cada_intencion_de_los_hechos_tiene_su_senal():
    assert set(graph._INTENCION_DE_SENAL) == set(hechos.INTENCIONES)


def test_las_intenciones_viajan_aunque_jev_dude_en_el_router():
    assert set(j._INTENCIONES_Q) <= set(j._TURN_SIGNALS) and set(j._INTENCIONES_Q) <= set(j._U34_QUESTIONS)


def test_flu1_la_pregunta_del_grupo_cuenta_una_persona(monkeypatch):
    """flu-1: «Es para una persona» daba 0,40 con la pregunta de antes (se repreguntaba «¿para cuántas personas?»)."""
    monkeypatch.setattr(settings, "grupo_de_una_persona", False)
    assert "it's for one person" not in j._questions_for_turn()[j.AFFIRMS_GROUP]["instructions"]
    monkeypatch.setattr(settings, "grupo_de_una_persona", True)
    assert "it's for one person" in j._questions_for_turn()[j.AFFIRMS_GROUP]["instructions"]
