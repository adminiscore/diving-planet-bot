"""ARQ-5f (23-oct, flag `hechos_que_faltaban`, reparto de Gadea #1525; G10 nº 5): hechos de la base que la tabla no daba.
La excepción del refresher en los requisitos del buceo certificado, que el horario no se adelanta, buceo y snorkel en
la misma lancha si el turno trae los dos, y que alojados en Barú salen desde Cartagena. Sin red."""

from src.agents import redactor_hechos
from src.flows import hechos
from src.flows.state import ConversationState


def _st(**kw):
    return ConversationState(conversation_id="arq5f", language="es", **kw)


def test_requisitos_del_buceo_certificado_con_la_excepcion_del_refresher():
    [b] = hechos.hechos(_st(location="cartagena"), ["requisitos"], ["certified_diving"])
    assert hechos._politica("refresh_requirement", "es") in b["requisitos"]
    [mini] = hechos.hechos(_st(location="cartagena"), ["requisitos"], ["minicourse"])
    assert hechos._politica("refresh_requirement", "es") not in mini["requisitos"]


def test_el_horario_no_se_adelanta():
    [b] = hechos.hechos(_st(location="cartagena"), ["horario"], ["snorkel"])
    assert b["horario_general"][-1] == hechos._politica("schedule_not_adjustable", "es")
    [g] = hechos.hechos_sin_actividad(_st(), ["horario"])
    assert hechos._politica("schedule_not_adjustable", "es") in g["horario_general"]


def test_buceo_y_snorkel_en_la_misma_lancha():
    st = _st(location="cartagena", detected_group_allocation={"certified_diving": 2, "snorkel": 2})
    [b] = hechos.hechos(st, ["horario"], ["snorkel"])
    assert b["misma_lancha"] == hechos._politica("mixed_group_boat", "es")
    [solo] = hechos.hechos(_st(location="cartagena"), ["horario"], ["snorkel"])
    assert "misma_lancha" not in solo


def test_barú_sale_desde_cartagena():
    foto = redactor_hechos._foto(_st(), {}, "cartagena", "Nos alojamos en Barú, ¿a qué hora sale el snorkel?", [])
    [b] = hechos.hechos(foto, ["horario"], ["snorkel"])
    assert b["recogida"]["cartagena"][-1] == hechos._politica("baru_departs_from_cartagena", "es")
    assert "quien se aloja en Barú sale desde Cartagena" in b["recogida"]["cartagena"][-1]
    otra = redactor_hechos._foto(_st(), {}, "cartagena", "¿A qué hora sale el snorkel desde Cartagena?", [])
    assert not getattr(otra, "_aloja_en_baru", False)
