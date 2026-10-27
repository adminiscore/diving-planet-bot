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
    # como los deja `_take_undecided_members`: fuera del reparto, pendientes y con la recomendación marcada
    assert st.detected_group_allocation == {"certified_diving": 1}
    assert st.pending_undecided_qty == 1 and st.needs_companion_activity


@pytest.mark.parametrize("campos", [
    {"detected_activity": "snorkel", "detected_group_size": 2, "acompanante_sin_certificar": True},  # no pide certificado
    {"detected_activity": "certified_diving", "detected_group_size": 2},  # nadie dijo que no esté certificado
    {"detected_activity": "certified_diving", "acompanante_sin_certificar": True},  # sin total, se pregunta
    {"detected_activity": "certified_diving", "detected_group_size": 2, "acompanante_sin_certificar": True,
     "detected_group_allocation": {"certified_diving": 1, "snorkel": 1}},  # el reparto dicho manda
    {"detected_activity": "certified_diving", "detected_group_size": 2, "acompanante_sin_certificar": True,
     "pending_undecided_qty": 1},  # ya están pendientes de elegir
])
def test_si_no_toca_no_cambia_el_grupo(campos):
    st = _grupo(**campos)
    antes = st.detected_group_allocation
    assert not grupo.sin_certificar_no_hereda(st)
    assert st.detected_group_allocation == antes


@pytest.mark.parametrize("reparto,nuevo,total", [
    ({"certified_diving": 1}, {"certified_diving": 1, "snorkel": 1}, 2),  # «ella prefiere hacer snorkel» (g24)
    ({"certified_diving": 1, "undecided": 1}, {"certified_diving": 1, "minicourse": 1}, 2),
    ({"snorkel": 2}, {"snorkel": 2, "minicourse": 1}, 4),  # uno de los dos que faltaban
])
def test_dar_actividad_a_quien_no_la_tenia_completa_el_grupo(reparto, nuevo, total):
    assert grupo.completa(reparto, nuevo, total)


@pytest.mark.parametrize("reparto,nuevo,total", [
    ({"certified_diving": 2}, {"certified_diving": 1, "snorkel": 1}, 2),  # le quita el buceo a uno: corrección
    ({"certified_diving": 1}, {"certified_diving": 1, "snorkel": 2}, 2),  # más de los que faltaban
    ({"certified_diving": 1}, {"certified_diving": 1}, 2),  # no añade nada
    ({"certified_diving": 1}, {"certified_diving": 1, "snorkel": 1}, None),  # sin total no se sabe quién falta
])
def test_lo_demas_no_completa(reparto, nuevo, total):
    assert not grupo.completa(reparto, nuevo, total)


def test_quien_hace_que_va_antes_que_el_origen():
    """Paso 3a: el orden aprobado (quién hace qué, el origen, seguridad y edades, la nacionalidad); si no contesta dos
    veces, se aplaza hasta antes del resumen como las demás."""
    from src.agents import conversational_core as core

    st = _grupo(detected_activity="certified_diving", is_certified=True, needs_companion_activity=True)
    assert core.next_missing_slot(st) == core.SLOT_COMPANION_ACTIVITY
    assert core.next_missing_slot(st, saltar={core.SLOT_COMPANION_ACTIVITY}) == core.SLOT_LOCATION


def test_sin_contestar_el_origen_no_hay_acuse():
    """«Voy con una amiga que no está certificada» a la pregunta del origen: la de ella sale delante, pero el origen
    sigue sin contestar y no toca «¡Perfecto!» (banco g18 y g24)."""
    from src.agents import conversational_core as core
    from src.agents.nucleo import slotfill_close

    st = _grupo(detected_activity="certified_diving", is_certified=True, needs_companion_activity=True,
                core_pending_slot=core.SLOT_COMPANION_ACTIVITY)
    assert slotfill_close._acuse_por_codigo(st, core.SLOT_LOCATION) == ""
    st.location = "cartagena"
    assert slotfill_close._acuse_por_codigo(st, core.SLOT_LOCATION) != ""
