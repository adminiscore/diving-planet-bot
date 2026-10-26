"""DEUDA-EXT (26-oct): quien se suma a un grupo que aún no tiene actividad principal (banco
docs/robustness/lat/banco-lat11.json, medido A/B ×2 con el estado final).

- a3 «two certified divers» + «my wife will join us but she'll just snorkel»: el total bajaba a 1 ({snorkel: 1}) y la
  reserva se cerraba como snorkel. Ahora el total cuenta a todos, la principal se pregunta y, al elegirla, el resto del
  grupo va con ella.
- a4 «Somos 3 buzos certificados» + «Además vienen dos amigos que quieren probar el minicurso»: se pedía confirmar
  «3 → 5». Ahora los dos se suman por el punto único del acompañante, y al grupo no se le ofrece su minicurso.
- a5 «mi parcero se anima al snorkel»: «parcero» en singular contaba como plural y se preguntaba cuántos.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import extractor as core_extractor
from src.agents.rutas import booking
from src.flows.state import ConversationState


def _grupo_sin_actividad(total: int, **campos) -> ConversationState:
    st = ConversationState(conversation_id="deuda-ext", language="es")
    st.detected_group_size = total
    st.is_certified = st.detected_is_certified = True
    st.location = st.detected_location = "cartagena"
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_sumar_a_alguien_sin_principal_no_pierde_a_los_de_antes():
    st = _grupo_sin_actividad(2)
    core._merge_companion_activity(st, "snorkel", 1)
    assert st.detected_group_allocation == {"snorkel": 1}
    assert st.detected_group_size == 3


def test_con_principal_sigue_igual():
    st = _grupo_sin_actividad(2, detected_activity="certified_diving")
    core._merge_companion_activity(st, "snorkel", 1)
    assert st.detected_group_allocation == {"certified_diving": 2, "snorkel": 1}
    assert st.detected_group_size == 3


def test_ya_contado_sin_principal_pasa_a_su_actividad():
    st = _grupo_sin_actividad(2, pending_companion_in_group={"activity": "snorkel", "qty": 1})
    assert core._apply_group_total(st, 2) is True
    assert st.detected_group_allocation == {"snorkel": 1}
    assert None not in st.detected_group_allocation


def test_al_elegir_la_principal_el_resto_va_con_ella():
    st = _grupo_sin_actividad(3, detected_group_allocation={"snorkel": 1}, detected_activity="certified_diving")
    booking._resto_a_la_principal(st, None)
    assert st.detected_group_allocation == {"snorkel": 1, "certified_diving": 2}


def test_cambiar_de_principal_no_reparte_el_resto():
    st = _grupo_sin_actividad(3, detected_group_allocation={"snorkel": 1}, detected_activity="minicourse")
    booking._resto_a_la_principal(st, "certified_diving")
    assert st.detected_group_allocation == {"snorkel": 1}


@pytest.mark.parametrize("reparto,total,esperado", [
    ({"minicourse": 2}, 5, "nuevos"),
    ({"minicourse": 2, "undecided": 3}, 5, "nuevos"),
    ({"minicourse": 2, "undecided": 1}, 5, "nuevos"),   # el extractor cuenta a quien escribe, no a su grupo
    ({"certified_diving": 3, "minicourse": 2}, 5, "todos"),
    ({"minicourse": 2}, 2, None),                      # cambia el total: se confirma, como siempre
    ({"minicourse": 2}, 4, None),
])
def test_cuando_es_una_suma_a_un_grupo_sin_actividad(reparto, total, esperado):
    st = _grupo_sin_actividad(3)
    assert core_extractor._suma_a_un_grupo_sin_actividad(st, reparto, total) == esperado


def test_con_actividad_o_reparto_no_es_este_caso():
    assert core_extractor._suma_a_un_grupo_sin_actividad(
        _grupo_sin_actividad(3, detected_activity="certified_diving"), {"minicourse": 2}, 5) is None
    assert core_extractor._suma_a_un_grupo_sin_actividad(
        _grupo_sin_actividad(3, detected_group_allocation={"snorkel": 1}), {"minicourse": 2}, 5) is None


@pytest.mark.asyncio
async def test_a4_los_que_se_suman_no_piden_confirmar_el_total(monkeypatch):
    datos = {"group_size": 5, "group_allocation": {"minicourse": 2, "undecided": 1}}
    monkeypatch.setattr(core_extractor, "datos_del_extractor", AsyncMock(return_value=datos))
    st = _grupo_sin_actividad(3)
    st._jev_adds_person = 0.9
    await core._understand(st, "Además vienen dos amigos que quieren probar el minicurso")
    assert st.detected_group_size == 5
    assert st.detected_group_allocation == {"minicourse": 2}
    assert not st.pending_correction


def test_a4_no_se_ofrece_al_grupo_la_actividad_de_los_que_se_suman():
    st = _grupo_sin_actividad(5, detected_group_allocation={"minicourse": 2}, actividad_preguntada="minicourse")
    assert core._ofrecer_la_actividad_preguntada(st) is None
    assert st.suggested_activity is None


@pytest.mark.parametrize("mensaje,plural", [
    ("mi parcero se anima al snorkel", False),
    ("mis parceros se animan al snorkel", True),
    ("mi parcera viene también", False),
])
def test_parcero_en_singular_es_una_persona(mensaje, plural):
    assert bool(core_extraction._PLURAL_COMPANION_RE.search(mensaje)) is plural
