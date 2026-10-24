"""s4-26 (punto 4, 7-oct): supuestos sueltos del flujo de reserva, arreglados por causa.

Casos visibles del golden (el examen oculto no se usa para ajustar): manual-duracion-curso, acompanante-goteo,
minicurso-islas-y-acompanante-lancha, logistica-isla-fragata-regreso-otro-dia.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.nucleo import slotfill_close as core_close
from src.agents.supervisor import route_message
from src.flows.state import ConversationState


def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="s4-26")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# --- s4-26, Jev manda en el acompañante: "¿cuántos días son?" no es "son" (hijo) -----------------------------------------------

def test_con_jev_seguro_de_que_no_la_regex_no_inventa_acompanante(monkeypatch):
    st = _state()
    st._jev_companion = 0.04
    assert core._mentions_person("Si cuantos días son?")  # la regex sola sí lo ve
    assert not core._menciona_a_alguien(st, "Si cuantos días son?")


def test_sin_veredicto_de_jev_manda_la_regex(monkeypatch):
    st = _state()
    st._jev_companion = None
    assert core._menciona_a_alguien(st, "voy con mi amigo")


def test_jev_dudoso_no_tapa_un_acompanante_real(monkeypatch):
    st = _state()
    st._jev_companion = 0.85
    assert core._menciona_a_alguien(st, "el quiere hacer snorkel con mi hijo")


# --- s4-26, el cierre no se repite: tras el cierre, "¿cuánto dura?" se contesta sola --------------------------------------

@pytest.fixture
def _offline(monkeypatch):
    for modulo, name in ((core_extraction, "fill_gaps"), (core_routing, "detect_special_signals"),
                         (core_extraction, "detect_special_signals"), (core_extraction, "resolve_slot_answer")):
        monkeypatch.setattr(modulo, name, AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core_close, "_acuse_por_codigo", lambda *a, **k: "")


async def _cerrada(extractor_dice):
    # ex-9b paso 3: lo que lee el extractor del turno (sin él, en los tests iba por la pista del regex); "para mi" es la
    # respuesta corta a la cantidad, que resuelve el núcleo.
    extractor_dice({"quiero hacer el curso open water, estoy en cartagena":
                    {"activity": "padi_open_water", "location": "cartagena"},
                    "no soy colombiano": {"is_colombian": False},
                    "para mi": {"group_size": 1}})  # ex-9b paso 4: la respuesta corta la lee el extractor
    st = _state()
    for m in ("quiero hacer el curso open water, estoy en cartagena", "para mi", "no soy colombiano"):
        await route_message(st, m)
    assert "book.divingplanet.org" in st.history[-1]["content"]
    return st


async def test_el_cierre_igual_no_se_repite_tras_una_respuesta(_offline, extractor_dice):
    st = await _cerrada(extractor_dice)
    r = await route_message(st, "¿Cuánto tiempo dura?")
    assert r.startswith("rag_answer_stub")  # la respuesta del RAG (stub del conftest) va siempre
    assert "book.divingplanet.org" not in r


# --- jev_persona_ya_contada: "él quiere hacer snorkel" no es una persona nueva ----------------------------------

def _grupo_de_dos():
    return _state(detected_activity="certified_diving", detected_group_size=2,
                  detected_group_allocation={"certified_diving": 2})


@pytest.mark.parametrize("p, pregunta", [(0.05, False), (0.45, True), (None, True)])
def test_persona_ya_contada_se_mueve_sin_preguntar(monkeypatch, p, pregunta):
    st = _grupo_de_dos()
    st._jev_adds_person = p
    core._add_or_ask_companion(st, "él quiere hacer snorkel", "snorkel", 1)
    assert bool(st.pending_companion_in_group) is pregunta
    if not pregunta:
        assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 1}
        assert st.detected_group_size == 2


def test_jev_pide_la_pregunta():
    from src.agents import jev_router

    assert jev_router.ADDS_PERSON in jev_router._questions_for_turn()
    assert jev_router.answers_to_signals({jev_router.ADDS_PERSON: {"type": "noul", "noul": 0.05}})[
        jev_router.ADDS_PERSON] == 0.05


# --- s4-26: condiciones abiertas y «el plan», no «el carrito» --------------------------------------------------------------

def test_la_regla_de_condiciones_va_en_el_prompt_del_rag(monkeypatch):
    from src.agents import rag_agent

    assert "Condiciones del cliente" in rag_agent.build_system_prompt("es")
    assert "Customer conditions" in rag_agent.build_system_prompt("en")


def test_el_contexto_del_rag_no_dice_carrito():
    from src.agents import supervisor

    st = _state(mixed_cart=[{"type": "course", "qty": 1, "label": "Curso Basico PADI (Open Water)"}])
    ctx = supervisor._build_extra_context(st) or ""
    assert "plan que está armando" in ctx and "carrito" not in ctx


# --- s4-27: la ubicacion deducida del hotel pasa por la puerta de Jev --------------

def test_la_ubicacion_del_hotel_se_declara():
    intent = core._detector.detect("¿Me pasas el contacto del hotel cocoliso?", _state())
    assert intent.location == "island" and intent.hotel == "cocoliso"
    assert "location" in intent.detected_fields


# --- jev_lugar_cliente (s4-28): la pregunta de Jev (la leen CAL-C3c y CAL-C4; `_lugar_por_jev` se quitó con la
# pista del regex en la limpieza ex9b) ---------------------------------------------------------------------------

def test_jev_pide_el_lugar():
    from src.agents import jev_router

    assert jev_router.CUSTOMER_PLACE in jev_router._questions_for_turn()
    out = jev_router.answers_to_signals({jev_router.CUSTOMER_PLACE: {"type": "choice", "choice": "none", "confidence": 0.9}})
    assert out[jev_router.CUSTOMER_PLACE] == {"choice": "none", "confidence": 0.9}
    assert jev_router.uncertain_answers({jev_router.CUSTOMER_PLACE: {"type": "choice", "choice": "none", "confidence": 0.3}}) == []
