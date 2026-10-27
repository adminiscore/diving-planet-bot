"""CALN-2 paso 1 (27-oct): el grupo se guarda como lista de personas y el reparto de siempre se calcula de ella."""
import json

import pytest

from src.flows import grupo
from src.flows.state import ConversationState
from src.state_store import deserialize_state, serialize_state


@pytest.mark.parametrize("reparto", [
    None,
    {"certified_diving": 2},
    {"certified_diving": 2, "snorkel": 1, "undecided": 1},
    {"undecided": 3},
    {"minicourse": 0, "snorkel": 2},
])
def test_ida_y_vuelta_exacta(reparto):
    st = ConversationState(conversation_id="caln2")
    st.detected_group_allocation = reparto
    assert st.detected_group_allocation == reparto
    if reparto:
        assert list(st.detected_group_allocation) == list(reparto)  # el mismo orden


def test_quien_no_ha_elegido_es_una_entrada_sin_actividad():
    st = ConversationState(conversation_id="caln2")
    st.detected_group_allocation = {"certified_diving": 1, "undecided": 1}
    assert st.personas == [{"actividad": "certified_diving", "cantidad": 1}, {"actividad": None, "cantidad": 1}]


def test_se_guarda_y_se_carga_como_lista():
    st = ConversationState(conversation_id="caln2")
    st.detected_group_allocation = {"snorkel": 2}
    datos = json.loads(serialize_state(st))
    assert datos["personas"] == [{"actividad": "snorkel", "cantidad": 2}]
    assert deserialize_state(serialize_state(st), "caln2").detected_group_allocation == {"snorkel": 2}


def test_una_conversacion_guardada_antes_trae_el_reparto_de_siempre():
    st = ConversationState(conversation_id="caln2")
    datos = json.loads(serialize_state(st))
    datos.pop("personas")
    datos["detected_group_allocation"] = {"certified_diving": 2, "undecided": 1}
    cargado = deserialize_state(json.dumps(datos), "caln2")
    assert cargado.detected_group_allocation == {"certified_diving": 2, "undecided": 1}


def test_sin_nadie_el_reparto_es_none():
    assert grupo.reparto_de([]) is None


def _grupo(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln2")
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_quien_no_esta_certificado_no_hereda_el_buceo():
    """«Quiero bucear, soy certificado. Voy con mi novia, que nunca ha buceado» (banco de grupos g02 y g18)."""
    st = _grupo(detected_activity="certified_diving", detected_group_size=2, acompanante_sin_certificar=True)
    assert grupo.sin_certificar_no_hereda(st)
    assert st.detected_group_allocation == {"certified_diving": 1, "undecided": 1}


@pytest.mark.parametrize("campos", [
    {"detected_activity": "snorkel", "detected_group_size": 2, "acompanante_sin_certificar": True},  # no pide certificado
    {"detected_activity": "certified_diving", "detected_group_size": 2},  # nadie dijo que no esté certificado
    {"detected_activity": "certified_diving", "acompanante_sin_certificar": True},  # sin total, se pregunta
    {"detected_activity": "certified_diving", "detected_group_size": 2, "acompanante_sin_certificar": True,
     "detected_group_allocation": {"certified_diving": 1, "snorkel": 1}},  # el reparto dicho manda
])
def test_si_no_toca_no_cambia_el_grupo(campos):
    st = _grupo(**campos)
    antes = st.detected_group_allocation
    assert not grupo.sin_certificar_no_hereda(st)
    assert st.detected_group_allocation == antes
