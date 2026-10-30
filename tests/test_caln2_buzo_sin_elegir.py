"""CALN-2 (27-oct, tanda de precios q1; Gadea #2208): quien falta por elegir puede ser un buzo certificado («uno es buzo
certificado y los otros dos queremos snorkel»). `personas` aún no guarda la certificación de cada uno: si nadie del grupo
ha dicho que no lo está, el buceo certificado también se recomienda, y elige el cliente."""

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import routing as core_routing
from src.flows.state import ConversationState


def _tres_amigos(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln2-buzo", language="es")
    st.detected_activity = "snorkel"
    st.detected_group_size = 3
    st.detected_group_allocation = {"snorkel": 2}
    st.pending_undecided_qty = 1
    st.detected_duration = "single_day"
    st.core_pending_slot = core.SLOT_COMPANION_ACTIVITY
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_sin_saber_si_es_principiante_tambien_se_recomienda_el_buceo_certificado():
    opciones = core._companion_activity_options(_tres_amigos())
    assert "certified_diving" in opciones and opciones[-1] == "companion"


def test_si_no_esta_certificado_solo_las_de_principiante():
    assert "certified_diving" not in core._companion_activity_options(_tres_amigos(acompanante_sin_certificar=True))


def test_el_buzo_que_lleva_tiempo_sin_bucear_va_primero():
    assert core._companion_activity_options(_tres_amigos(acompanante_certificado_inactivo=True))[0] == "certified_diving"


@pytest.mark.parametrize("lang, texto", [("es", "Buceo certificado"), ("en", "Certified diving")])
def test_la_pregunta_lo_muestra_con_su_texto(lang, texto):
    pregunta = core.ask_slot(_tres_amigos(language=lang), core.SLOT_COMPANION_ACTIVITY)
    assert texto in pregunta


@pytest.mark.parametrize("mensaje, eleccion", [
    ("Buceo certificado", "certified_diving"),  # el título del botón
    ("el minicurso", "minicourse"),
    ("snorkel", "snorkel"),
    ("quiere bucear", None),  # vale para el minicurso y para el buceo certificado: no se adivina
])
def test_la_respuesta_corta(mensaje, eleccion):
    st = _tres_amigos()
    core_routing._apply_short_answer(st, mensaje)
    # CALN-8 (2b): con su cantidad sabida (1), la elección entra ya en el reparto
    esperado = {"snorkel": 2} if eleccion is None else {"snorkel": 2 + (eleccion == "snorkel"),
                                                         **({eleccion: 1} if eleccion != "snorkel" else {})}
    assert st.detected_group_allocation == esperado and st.detected_group_size == 3
    assert bool(st.pending_undecided_qty) is (eleccion is None)
