"""Sparring s03h (3-nov, contra PRE 0.44; docs/robustness/g3/hallazgos.md, CALN-S03H-01): pedía el nocturno («I'd love
to do a night dive», «yes, the night dive package») y la tarjeta era la de 2 inmersiones de día con su enlace. El
extractor dice si lo quiere (`plan_nocturno`) y el paquete sale del catálogo. Sin red."""
from src.agents.extractor_turno import campos_paso6
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor
from src.domain import activities as dom
from src.flows.state import ConversationState


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="s03h", language="en")
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_el_paquete_con_nocturna_de_cada_duracion_sale_del_catalogo():
    assert [dom.paquete_con_nocturna(d) for d in (1, 2, 3, 4)] == [3, 5, 7, 9]


def test_el_campo_va_en_la_llamada_del_extractor():
    assert "plan_nocturno" in campos_paso6(None)


def test_pedir_el_nocturno_sin_cifra_elige_el_paquete_de_un_dia():
    intent = DetectedIntent()
    extractor._poner_plan_nocturno(intent, _estado(), {"plan_nocturno": True}, "Yes, I want the night dive package")
    assert intent.cert_dives == 3 and intent._plan_nocturno


def test_con_sus_dias_de_buceo_el_de_esos_dias():
    intent = DetectedIntent()
    extractor._poner_plan_nocturno(intent, _estado(), {"plan_nocturno": True, "dias_de_buceo": 2},
                                   "Two days of diving, with the night dive")
    assert intent.cert_dives == 5


def test_si_nombra_la_cifra_manda_la_cifra_y_varios_dias_sin_cuantos_no_elige():
    intent = DetectedIntent()
    extractor._poner_plan_nocturno(intent, _estado(), {"plan_nocturno": True}, "The 5-dive package with the night dive")
    assert intent.cert_dives is None
    extractor._poner_plan_nocturno(intent, _estado(detected_duration="multi_day"), {"plan_nocturno": True},
                                   "A few days diving, with a night dive")
    assert intent.cert_dives is None
    extractor._poner_plan_nocturno(intent, _estado(), {"plan_nocturno": None}, "What is a night dive like?")
    assert intent.cert_dives is None


def test_lo_que_elige_ahora_cambia_el_plan_guardado_y_la_tarjeta():
    from src.agents import conversational_core as core
    from src.agents.rutas.booking import _apply_detected_intent

    st = _estado(detected_activity="certified_diving", is_certified=True, location="cartagena", detected_cert_dives=2,
                 mixed_cart=[{"service_id": "2_dives_1_day"}])
    intent = DetectedIntent()
    intent.cert_dives, intent._plan_nocturno = 3, True
    _apply_detected_intent(intent, st, "Yes, I want the night dive package")
    assert st.detected_cert_dives == 3 and st.mixed_cart == []
    assert core._resolve_cert_plan(st) == "3_dives_1_day"


def test_los_hechos_de_este_mensaje_son_los_del_paquete_con_nocturna():
    from src.agents.redactor_hechos import _foto

    foto = _foto(_estado(detected_activity="certified_diving"), {"plan_nocturno": True}, "cartagena",
                 "I'd love to do a night dive. How much?", [{"role": "user", "content": "I want 2 dives"}])
    assert foto.detected_service_id == "3_dives_1_day"
