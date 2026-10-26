"""u3-5 paso 1 (flag `corrections_v2`, quitado en s4-25): el "¿lo cambio?" se pregunta una vez y solo si cambia algo.

Ronda A del paso 3 (27-sep, golden completo): de 12 "¿lo cambio?", 6 eran la MISMA confirmación
repetida porque el cliente no contestaba sí/no, y 2 proponían cambiar X por X.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.nucleo import slotfill_close as core_close
from src.agents.supervisor import route_message
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    for modulo, name in ((core_routing, "detect_special_signals"),
                         (core_extraction, "detect_special_signals"), (core_extraction, "resolve_slot_answer")):
        monkeypatch.setattr(modulo, name, AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core_close, "_acuse_por_codigo", lambda *a, **k: "")


def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="u35")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _route(st, message, proposed):
    intent = core._detector.detect(message, st)
    core._route_contradictions(st, message, intent, proposed)


def test_mismo_valor_para_el_cliente_no_se_pregunta(monkeypatch):
    st = _state(detected_group_allocation={"certified_diving": 1, "snorkel": 1}, detected_group_size=2)
    _route(st, "somos los dos solamente", {"group_allocation": {"snorkel": 1, "certified_diving": 1, "minicourse": 0}})
    assert not st.pending_correction


def test_un_cambio_real_si_se_pregunta(monkeypatch):
    st = _state(detected_group_size=3)
    _route(st, "somos 4", {"group_size": 4})
    assert st.pending_correction == {"group_size": 4}
    assert st.asked_corrections == {"group_size": 4}


def test_lo_ya_preguntado_no_se_vuelve_a_preguntar(monkeypatch):
    st = _state(location="cartagena", asked_corrections={"location": "island"})
    _route(st, "I apologize for the change and confusion!", {"location": "island"})
    assert not st.pending_correction


# ex-9b paso 3: lo que lee el extractor del turno en los mensajes de reserva de estos tests (fixture `extractor_dice` de
# conftest); sin él, en los tests (sin red) el extractor falla. Las respuestas cortas ("sí",
# "no") las resuelve el núcleo.
LEE_EL_EXTRACTOR = {
    "queremos bucear, somos certificados, desde cartagena, somos 3":
        {"quiere_bucear": True, "is_certified": True, "activity": "certified_diving", "location": "cartagena",
         "group_size": 3},
    # "quiero probar" sin nombrar el minicurso: el extractor no elige actividad (la recomienda el bot).
    "nunca he buceado y quiero probar, somos 2": {"quiere_bucear": True, "is_certified": False, "group_size": 2},
    "queremos hacer el minicurso, somos 2": {"activity": "minicourse", "group_size": 2},
}


async def _con_confirmacion_pendiente(extractor_dice):
    extractor_dice(LEE_EL_EXTRACTOR)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena, somos 3")
    st.pending_correction = {"group_size": 4}
    st.asked_corrections = {"group_size": 4}
    st.core_pending_slot = core.SLOT_CONFIRM_CORRECTION
    return st


async def test_si_no_contesta_si_o_no_se_queda_lo_guardado_y_no_se_repite(monkeypatch, extractor_dice):
    st = await _con_confirmacion_pendiente(extractor_dice)
    resp = await route_message(st, "Me compartes el link por favor")
    assert st.pending_correction is None
    assert st.detected_group_size == 3
    assert "lo cambio" not in resp


async def test_un_si_aunque_siga_una_pregunta_acepta_el_cambio(monkeypatch, extractor_dice):
    st = await _con_confirmacion_pendiente(extractor_dice)
    await route_message(st, "sí, ¿y cuánto sería?")
    assert st.detected_group_size == 4 and st.pending_correction is None


async def test_un_no_mantiene_lo_guardado(monkeypatch, extractor_dice):
    st = await _con_confirmacion_pendiente(extractor_dice)
    await route_message(st, "no")
    assert st.detected_group_size == 3 and st.pending_correction is None


# ── u3-5 paso 2: Jev como señal de corrección ────────────────────────────────────────────────

from src.agents import jev_router  # noqa: E402


def test_jev_recibe_la_pregunta_de_correccion():
    assert jev_router.CORRECTS in jev_router._questions_for_turn()
    assert jev_router.uncertain_answers({jev_router.CORRECTS: {"type": "noul", "noul": 0.5}}) == []


def test_la_senal_se_emite_en_verdadero_y_en_falso():
    assert jev_router.answers_to_signals({"corrects": {"type": "noul", "noul": 0.98}})["corrects"] is True
    assert jev_router.answers_to_signals({"corrects": {"type": "noul", "noul": 0.45}})["corrects"] is False


def test_correccion_clara_segun_jev_se_aplica_sin_preguntar(monkeypatch):
    """"esperate, somos 4 al final, se sumo uno mas": sin palabra del regex, se preguntaba."""
    st = _state(detected_group_size=3)
    st._jev_corrects = True
    msg = "esperate, somos 4 al final, se sumo uno mas"
    intent = core._detector.detect(msg, st)
    core._route_contradictions(st, msg, intent, {"group_size": 4})
    assert not st.pending_correction
    assert intent.group_size == 4 and "group_size" in intent.overwrite


def test_si_jev_no_esta_seguro_se_pregunta_como_hoy(monkeypatch):
    st = _state(detected_group_size=3)
    st._jev_corrects = False
    _route(st, "somos 4", {"group_size": 4})
    assert st.pending_correction == {"group_size": 4}


def test_una_correccion_ya_aplicada_en_el_turno_no_se_pregunta(monkeypatch):
    st = _state(detected_group_size=2, detected_group_allocation={"certified_diving": 1, "snorkel": 1})
    st.pending_correction = {"group_allocation": {"snorkel": 1, "certified_diving": 1}, "group_size": 3}
    core._prune_applied_corrections(st)
    assert st.pending_correction == {"group_size": 3}
    st.pending_correction = {"group_allocation": {"snorkel": 1, "certified_diving": 1}}
    core._prune_applied_corrections(st)
    assert st.pending_correction is None


# ── u3-5 paso 3: la nacionalidad no se deduce del idioma ─────────────────────────────────────


async def test_la_nacionalidad_que_jev_no_ve_afirmada_no_se_rellena(monkeypatch, extractor_dice):
    """"Busco el seguinte: Vamos en família a Cartagena..." (portugués): el relleno ponía
    is_colombian=False; Jev dice que el mensaje no la afirma. Los demás campos rellenados se quedan."""

    async def _combined(fields, veto, msg, *_a, **_k):
        return {f: v for f, v in {"is_colombian": False, "location": "cartagena"}.items() if f in fields}, {}

    monkeypatch.setattr(core, "extract_and_verify", _combined, raising=False)

    async def _signals(message, **_k):
        return {"affirms_nationality": False, "affirms_location": True}

    from src.agents import supervisor
    monkeypatch.setattr(supervisor, "detect_routing_signals", _signals)
    # ex-9b paso 3: con el extractor caído dos turnos seguidos se pasa a un asesor.
    extractor_dice({"quiero bucear, soy certificado":
                    {"quiere_bucear": True, "is_certified": True, "activity": "certified_diving"},
                    "vamos en familia a cartagena": {"location": "cartagena"}})
    st = _state()
    await route_message(st, "quiero bucear, soy certificado")
    await route_message(st, "vamos en familia a cartagena")
    assert st.is_colombian is None


# ── u3-5: el minicurso deducido se recomienda y lo confirma el cliente (Gadea, 27-sep) ─────────


async def test_el_minicurso_deducido_se_recomienda_y_no_se_guarda(monkeypatch, extractor_dice):
    # ex-9b paso 3: la recomendación no sale del minicurso deducido por el regex sino de lo que dice el extractor
    # (CAL-C1: quiere bucear y no es certificado); la conducta es la misma.
    extractor_dice(LEE_EL_EXTRACTOR)
    st = _state()
    resp = await route_message(st, "nunca he buceado y quiero probar, somos 2")
    assert st.detected_activity is None
    assert st.suggested_activity == "minicourse"
    assert st.core_pending_slot == core.SLOT_ACTIVITY
    assert "minicurso" in resp.lower() and "open water" in resp.lower()


async def test_un_si_confirma_el_minicurso_recomendado(monkeypatch, extractor_dice):
    extractor_dice(LEE_EL_EXTRACTOR)
    st = _state()
    await route_message(st, "nunca he buceado y quiero probar, somos 2")
    await route_message(st, "sí, dale")
    assert st.detected_activity == "minicourse" and st.suggested_activity is None


async def test_nombrarlo_es_elegirlo(monkeypatch, extractor_dice):
    extractor_dice(LEE_EL_EXTRACTOR)
    st = _state()
    await route_message(st, "queremos hacer el minicurso, somos 2")
    assert st.detected_activity == "minicourse"


def test_el_plural_minicursos_tambien_es_nombrarlo():
    assert core._EXPLICIT_MINICOURSE_NAME_RE.search("MINI CURSOS")
    assert core._EXPLICIT_MINICOURSE_NAME_RE.search("mini courses for two")


def test_el_minicurso_elegido_borra_la_recomendacion():
    """ex-9b paso 3 (limpieza ex9b): sin la pista del regex ya no hay minicurso DEDUCIDO ("es la primera vez") que
    `_recommend_inferred_minicourse` convierta en recomendación (lo recomienda CAL-C1, arriba); el minicurso solo llega
    ELEGIDO por el cliente (extractor) y entonces la recomendación pendiente se borra."""
    from src.agents.intent_detector import DetectedIntent

    st = _state()
    st.suggested_activity = "minicourse"
    intent = DetectedIntent(activity="minicourse")
    intent._actividad_elegida = True
    core._recommend_inferred_minicourse(intent, st, "sí, el minicurso")
    assert intent.activity == "minicourse" and st.suggested_activity is None
