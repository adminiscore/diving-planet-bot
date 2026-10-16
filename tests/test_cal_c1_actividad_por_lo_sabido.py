"""CAL-C1 (16-oct), flag `actividad_por_lo_sabido`: quien ya dijo que quiere bucear no recibe el menú de actividades.

Banco CAL (10 casos): "5 inmersiones", "Muchas gracias!", "no estamos certificados" → "¿Con cuál te animas — buceo,
minicurso, snorkel o un curso PADI?". Regla de Gadea (14/27-sep): recomendar según lo que se sabe. Se fija:
1. quiere bucear y no está certificado → se recomienda el minicurso (lo confirma el cliente);
2. quiere bucear y no se sabe la certificación → se pregunta la certificación;
3. certificado → el menú de certificados de siempre; sin "quiere bucear" o sin el flag → el menú de siempre.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.conversational_core import SLOT_ACTIVITY, SLOT_CERTIFICATION, ask_slot
from src.config import settings
from src.flows.state import ConversationState

MENU = "¿Con cuál te animas — *buceo*, *minicurso*, *snorkel* o un *curso PADI*?"


@pytest.fixture
def flag(monkeypatch):
    monkeypatch.setattr(settings, "actividad_por_lo_sabido", True)
    monkeypatch.setattr(settings, "recommend_inferred_minicourse", True)
    monkeypatch.setattr(settings, "recomendar_a_certificados", True)


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="c1", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_quiere_bucear_sin_certificacion_recomienda_el_minicurso(flag):
    st = _estado(quiere_bucear=True, is_certified=False)
    texto = ask_slot(st, SLOT_ACTIVITY, reasking=True)
    assert "minicurso" in texto and MENU not in texto
    assert st.suggested_activity == "minicourse"
    assert st.core_pending_slot == SLOT_ACTIVITY


def test_quiere_bucear_sin_saber_la_certificacion_la_pregunta(flag):
    st = _estado(quiere_bucear=True)
    texto = ask_slot(st, SLOT_ACTIVITY, reasking=True)
    assert "¿Eres buzo certificado?" in texto and MENU not in texto
    assert st.core_pending_slot == SLOT_CERTIFICATION
    st = _estado(quiere_bucear=True, detected_group_size=2)
    assert "¿Sois buzos certificados?" in ask_slot(st, SLOT_ACTIVITY)


def test_certificado_recibe_el_menu_de_certificados(flag):
    texto = ask_slot(_estado(quiere_bucear=True, is_certified=True), SLOT_ACTIVITY, reasking=True)
    assert "*salida de 2 inmersiones*" in texto


def test_sin_quiere_bucear_o_sin_flag_el_menu_de_siempre(flag, monkeypatch):
    assert MENU in ask_slot(_estado(), SLOT_ACTIVITY, reasking=True)
    monkeypatch.setattr(settings, "actividad_por_lo_sabido", False)
    assert MENU in ask_slot(_estado(quiere_bucear=True), SLOT_ACTIVITY, reasking=True)


def test_con_reparto_de_grupo_no_cambia(flag):
    st = _estado(quiere_bucear=True, detected_group_allocation={"certified_diving": 1, "undecided": 1})
    assert ask_slot(st, SLOT_ACTIVITY, reasking=True) == ask_slot(
        _estado(detected_group_allocation={"certified_diving": 1, "undecided": 1}), SLOT_ACTIVITY, reasking=True)


def test_la_certificacion_conocida_por_el_campo_detectado(flag):
    st = _estado(quiere_bucear=True, detected_is_certified=False)
    assert core._known_field_values(st).get("is_certified") is False
    assert "minicurso" in ask_slot(st, SLOT_ACTIVITY, reasking=True)
