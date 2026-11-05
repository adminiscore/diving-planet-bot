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


def test_con_dos_dias_no_se_supone_el_paquete_con_nocturna():
    """CALN-39: «dos mañanas» recibía el paquete de 5 con nocturna. Se propone el de 4 y se le dice qué más hay."""
    st = ConversationState(conversation_id="c39", language="es")
    st.detected_activity, st.location, st.detected_cert_days = "certified_diving", "cartagena", 2
    assert core._resolve_cert_plan(st) == "4_dives_2_days"
    intro = core._recommended_plan_intro(st)
    assert "*4 inmersiones*" in intro and "*5*" in intro and "sueltas" in intro


def test_si_dice_cuantas_inmersiones_no_se_le_propone_otro_paquete():
    st = ConversationState(conversation_id="c39", language="es")
    st.detected_activity, st.location, st.detected_cert_days, st.detected_cert_dives = "certified_diving", "cartagena", 2, 5
    assert core._resolve_cert_plan(st) == "5_dives_2_days"
    assert core._recommended_plan_intro(st) == ""


def _plan_dicho(st, senales=None, **campos):
    from src.agents.rutas.booking import _poner_el_plan_dicho

    st._senales_router = senales or {}
    intent = DetectedIntent()
    for campo, valor in campos.items():
        setattr(intent, campo, valor)
    _poner_el_plan_dicho(st, intent)


def test_lo_ultimo_que_afirma_manda_y_el_carrito_se_rehace():
    """CALN-39: el paquete de 5 se quedaba pegado a quien luego pide las dos inmersiones de un día."""
    from src.agents.jev_router import ELIGE_SEGURO

    st = ConversationState(conversation_id="c39", language="en", detected_cert_dives=5, detected_cert_days=2, mixed_cart=[{"type": "cert"}])
    _plan_dicho(st, {ELIGE_SEGURO: True}, cert_dives=2)
    assert st.detected_cert_dives == 2 and st.detected_cert_days is None and st.mixed_cart == []
    assert core._resolve_cert_plan(st) == "2_dives_1_day"


def test_si_cambia_a_un_dia_el_paquete_de_dos_dias_se_olvida():
    from src.agents.jev_router import ELIGE_SEGURO

    st = ConversationState(conversation_id="c39", language="es", detected_cert_dives=5, detected_cert_days=2)
    _plan_dicho(st, {ELIGE_SEGURO: True}, cert_days=1)
    assert st.detected_cert_days == 1 and st.detected_cert_dives is None


def test_una_pregunta_no_cambia_lo_elegido_pero_la_primera_cifra_vale():
    from src.agents.jev_router import ASKS_QUESTION, ELIGE_SEGURO

    st = ConversationState(conversation_id="c39", language="es", detected_cert_dives=2, mixed_cart=[{"type": "cert"}])
    _plan_dicho(st, {ELIGE_SEGURO: True, ASKS_QUESTION: True}, cert_dives=4)
    assert st.detected_cert_dives == 2 and st.mixed_cart
    _plan_dicho(st, {}, cert_dives=5)  # «llevo 5 inmersiones»: Jev no dice que elija
    assert st.detected_cert_dives == 2 and st.mixed_cart
    st = ConversationState(conversation_id="c39", language="es")
    _plan_dicho(st, {ASKS_QUESTION: True}, cert_dives=4)
    assert st.detected_cert_dives == 4


def test_dias_e_inmersiones_que_casan_se_quedan_los_dos():
    st = ConversationState(conversation_id="c39", language="es")
    _plan_dicho(st, cert_dives=5, cert_days=2)
    assert st.detected_cert_dives == 5 and st.detected_cert_days == 2


def test_el_refresher_ocupa_uno_de_los_dias_que_queria_bucear():
    """Tanda s05f (6947): refresher el 8 y bucear el 9 recibía el paquete de dos días."""
    st = ConversationState(conversation_id="c39", language="es", detected_cert_days=2, refresher_interested=True, detected_group_size=1)
    st.location = "cartagena"
    assert core._resolve_cert_plan(st) == "2_dives_1_day"
    st.detected_cert_days = 3
    assert core._resolve_cert_plan(st) == "4_dives_2_days"
    st.detected_group_size = 2  # en un grupo no se sabe quién lo hace
    assert core._resolve_cert_plan(st) == "7_dives_3_days"


def test_con_un_dia_no_revienta():
    """Mini y panel de la 0.60: «KeyError: 1» en un turno. Hay dos paquetes de un día, y `_DAYS_TO_DIVES` no los lleva."""
    st = ConversationState(conversation_id="c39", language="es", detected_cert_days=1)
    st.location = "cartagena"
    assert "2 inmersiones en 1 día" in core._recommended_plan_intro(st)
    assert core._resolve_cert_plan(st) == "2_dives_1_day"
