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
