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


# ── u3-5 paso 2: Jev como señal de corrección ────────────────────────────────────────────────

from src.agents import jev_router  # noqa: E402


def test_con_el_flag_jev_recibe_la_pregunta_de_correccion(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", False)
    assert jev_router.CORRECTS not in jev_router._questions_for_turn()
    monkeypatch.setattr(settings, "corrections_v2", True)
    assert jev_router.CORRECTS in jev_router._questions_for_turn()
    assert jev_router.uncertain_answers({jev_router.CORRECTS: {"type": "noul", "noul": 0.5}}) == []


def test_la_senal_se_emite_en_verdadero_y_en_falso():
    assert jev_router.answers_to_signals({"corrects": {"type": "noul", "noul": 0.98}})["corrects"] is True
    assert jev_router.answers_to_signals({"corrects": {"type": "noul", "noul": 0.45}})["corrects"] is False


def test_correccion_clara_segun_jev_se_aplica_sin_preguntar(monkeypatch):
    """"esperate, somos 4 al final, se sumo uno mas": sin palabra del regex, se preguntaba."""
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state(detected_group_size=3)
    st._jev_corrects = True
    msg = "esperate, somos 4 al final, se sumo uno mas"
    intent = core._detector.detect(msg, st)
    core._route_contradictions(st, msg, intent, {"group_size": 4})
    assert not st.pending_correction
    assert intent.group_size == 4 and "group_size" in intent.overwrite


def test_si_jev_no_esta_seguro_se_pregunta_como_hoy(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state(detected_group_size=3)
    st._jev_corrects = False
    _route(st, "somos 4", {"group_size": 4})
    assert st.pending_correction == {"group_size": 4}


def test_la_senal_de_otro_turno_no_cuenta_con_el_flag_apagado(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", False)
    st = _state(detected_group_size=3)
    st._jev_corrects = True
    _route(st, "somos 4", {"group_size": 4})
    assert st.pending_correction == {"group_size": 4}


def test_una_correccion_ya_aplicada_en_el_turno_no_se_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "corrections_v2", True)
    st = _state(detected_group_size=2, detected_group_allocation={"certified_diving": 1, "snorkel": 1})
    st.pending_correction = {"group_allocation": {"snorkel": 1, "certified_diving": 1}, "group_size": 3}
    core._prune_applied_corrections(st)
    assert st.pending_correction == {"group_size": 3}
    st.pending_correction = {"group_allocation": {"snorkel": 1, "certified_diving": 1}}
    core._prune_applied_corrections(st)
    assert st.pending_correction is None


# ── u3-5 paso 3: la nacionalidad no se deduce del idioma ─────────────────────────────────────


async def test_la_nacionalidad_que_jev_no_ve_afirmada_no_se_rellena(monkeypatch):
    """"Busco el seguinte: Vamos en família a Cartagena..." (portugués): el relleno ponía
    is_colombian=False; Jev dice que el mensaje no la afirma. Los demás campos rellenados se quedan."""
    monkeypatch.setattr(settings, "corrections_v2", True)
    monkeypatch.setattr(settings, "answer_and_continue", True)

    async def _fill(msg, *_a, only_fields=None, **_k):
        return {f: v for f, v in {"is_colombian": False, "location": "cartagena"}.items() if f in (only_fields or [])}

    async def _combined(fields, veto, msg, *_a, **_k):
        return {f: v for f, v in {"is_colombian": False, "location": "cartagena"}.items() if f in fields}, {}

    monkeypatch.setattr(core, "fill_gaps", _fill)
    monkeypatch.setattr(core, "extract_and_verify", _combined)

    async def _signals(message, **_k):
        return {"affirms_nationality": False, "affirms_location": True}

    from src.agents import supervisor
    monkeypatch.setattr(supervisor, "detect_routing_signals", _signals)
    st = _state()
    await route_message(st, "quiero bucear, soy certificado")
    await route_message(st, "vamos en familia a cartagena")
    assert st.is_colombian is None
