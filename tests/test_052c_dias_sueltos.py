"""Sparring s04j y s04l (4-nov): quien quiere bucear 2 días sueltos recibía solo paquetes, sin la salida de un día."""
from src.flows import hechos
from src.flows.state import ConversationState


def _estado(**campos):
    st = ConversationState(conversation_id="052c", language="en", is_colombian=False, detected_duration="multi_day",
                           duracion_de_buceo=True, **campos)
    return st


def _planes(st):
    bloque = hechos.hechos(st, ["precio"], ["certified_diving"])[0]
    return [p["plan"] for p in bloque.get("otros_planes") or []]


def test_dos_dias_desde_cartagena_lleva_la_salida_de_un_dia():
    planes = _planes(_estado(location="cartagena"))
    assert any("2 dives (1 day)" in p for p in planes), planes
    assert any("days" in p for p in planes), planes  # y un paquete, que también le puede interesar


def test_dos_dias_desde_las_islas_lleva_la_salida_de_un_dia():
    planes = _planes(_estado(location="island"))
    assert any("2 dives (1 day" in p for p in planes), planes


def test_con_un_plan_elegido_no_se_fuerza():
    st = _estado(location="cartagena")
    st.detected_service_id = "7_dives_3_days"
    planes = _planes(st)
    assert len(planes) <= hechos._OTROS_POR_ORIGEN
