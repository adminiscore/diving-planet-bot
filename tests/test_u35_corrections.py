"""u3-5 paso 1 (flag `corrections_v2`): el "¿lo cambio?" se pregunta una vez y solo si cambia algo.

Ronda A del paso 3 (27-sep, golden completo): de 12 "¿lo cambio?", 6 eran la MISMA confirmación
repetida porque el cliente no contestaba sí/no, y 2 proponían cambiar X por X.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import route_message
from src.config import Settings, settings
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    for name in ("fill_gaps", "detect_special_signals", "resolve_slot_answer"):
        monkeypatch.setattr(core, name, AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))
    monkeypatch.setattr(settings, "answer_and_continue", False)


def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="u35")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _route(st, message, proposed):
    intent = core._detector.detect(message, st)
    core._route_contradictions(st, message, intent, proposed)


def test_el_flag_nace_apagado():
    assert Settings().corrections_v2 is False


def test_mismo_valor_para_el_cliente_no_se_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state(detected_group_allocation={"certified_diving": 1, "snorkel": 1}, detected_group_size=2)
    _route(st, "somos los dos solamente", {"group_allocation": {"snorkel": 1, "certified_diving": 1, "minicourse": 0}})
    assert not st.pending_correction


def test_un_cambio_real_si_se_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state(detected_group_size=3)
    _route(st, "somos 4", {"group_size": 4})
    assert st.pending_correction == {"group_size": 4}
    assert st.asked_corrections == {"group_size": 4}


def test_lo_ya_preguntado_no_se_vuelve_a_preguntar(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state(location="cartagena", asked_corrections={"location": "island"})
    _route(st, "I apologize for the change and confusion!", {"location": "island"})
    assert not st.pending_correction


def test_con_el_flag_apagado_todo_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", False)
    st = _state(location="cartagena", asked_corrections={"location": "island"})
    _route(st, "gracias", {"location": "island"})
    assert st.pending_correction == {"location": "island"}


async def _con_confirmacion_pendiente(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena, somos 3")
    st.pending_correction = {"group_size": 4}
    st.asked_corrections = {"group_size": 4}
    st.core_pending_slot = core.SLOT_CONFIRM_CORRECTION
    return st


async def test_si_no_contesta_si_o_no_se_queda_lo_guardado_y_no_se_repite(monkeypatch):
    st = await _con_confirmacion_pendiente(monkeypatch)
    resp = await route_message(st, "Me compartes el link por favor")
    assert st.pending_correction is None
    assert st.detected_group_size == 3
    assert "lo cambio" not in resp


async def test_un_si_aunque_siga_una_pregunta_acepta_el_cambio(monkeypatch):
    st = await _con_confirmacion_pendiente(monkeypatch)
    await route_message(st, "sí, ¿y cuánto sería?")
    assert st.detected_group_size == 4 and st.pending_correction is None


async def test_un_no_mantiene_lo_guardado(monkeypatch):
    st = await _con_confirmacion_pendiente(monkeypatch)
    await route_message(st, "no")
    assert st.detected_group_size == 3 and st.pending_correction is None
