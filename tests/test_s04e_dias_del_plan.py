"""Sparring s04e (4-nov, Lima; igual en PRE 0.48): los días del plan del buzo certificado salen del extractor
(`dias_de_buceo`), no solo del regex. «queremos bucear tres días seguidos» recibía el plan de 2 inmersiones en 1 día."""
import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


def _intent(datos, regex_dias=None):
    intent = DetectedIntent()
    intent.cert_days = regex_dias
    core_extractor._poner_duracion(intent, ConversationState(conversation_id="s04e"), datos, "")
    return intent


@pytest.mark.parametrize("datos, regex, dias", [
    ({"dias_de_buceo": 3}, None, 3),       # «bucear tres días seguidos»: el regex no lo lee
    ({"dias_de_buceo": 2}, None, 2),
    ({"dias_de_buceo": 3}, 2, 2),          # lo que ya leyó el regex no se pisa
    ({"dias_de_buceo": 6}, None, None),    # sin paquete de 6 días
    ({"dias_de_estancia": 3}, None, None),  # la estancia no son días de buceo
    ({}, None, None),
])
def test_los_dias_de_buceo_del_extractor_son_los_del_plan(datos, regex, dias):
    assert _intent(datos, regex).cert_days == dias


def test_con_tres_dias_el_plan_es_el_de_tres_dias():
    st = ConversationState(conversation_id="s04e", language="es")
    st.detected_activity, st.location, st.detected_cert_days = "certified_diving", "cartagena", 3
    assert core._recommended_plan_intro(st) == ""
    assert core._resolve_cert_plan(st) == "7_dives_3_days"
