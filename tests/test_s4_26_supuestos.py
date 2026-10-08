"""s4-26 (punto 4, 7-oct): supuestos sueltos del flujo de reserva, arreglados por causa.

Casos visibles del golden (el examen oculto no se usa para ajustar): manual-duracion-curso, acompanante-goteo,
minicurso-islas-y-acompanante-lancha, logistica-isla-fragata-regreso-otro-dia.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState


def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="s4-26")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# --- jev_acompanante_manda: "¿cuántos días son?" no es "son" (hijo) -----------------------------------------------

def test_con_jev_seguro_de_que_no_la_regex_no_inventa_acompanante(monkeypatch):
    monkeypatch.setattr(settings, "jev_acompanante_manda", True)
    st = _state()
    st._jev_companion = 0.04
    assert core._mentions_person("Si cuantos días son?")  # la regex sola sí lo ve
    assert not core._menciona_a_alguien(st, "Si cuantos días son?")


def test_sin_veredicto_de_jev_manda_la_regex(monkeypatch):
    monkeypatch.setattr(settings, "jev_acompanante_manda", True)
    st = _state()
    st._jev_companion = None
    assert core._menciona_a_alguien(st, "voy con mi amigo")


def test_jev_dudoso_no_tapa_un_acompanante_real(monkeypatch):
    monkeypatch.setattr(settings, "jev_acompanante_manda", True)
    st = _state()
    st._jev_companion = 0.85
    assert core._menciona_a_alguien(st, "el quiere hacer snorkel con mi hijo")


def test_con_el_flag_apagado_la_regex_de_siempre(monkeypatch):
    monkeypatch.setattr(settings, "jev_acompanante_manda", False)
    st = _state()
    st._jev_companion = 0.04
    assert core._menciona_a_alguien(st, "Si cuantos días son?")


# --- red_menciones_con_principal: "buceo" no es un segundo plan -------------------------------------------------

def test_sin_actividad_principal_la_red_no_saca_acompanante():
    st = _state()
    assert core._menciones_de_otro_producto(st, "My husband and I are booked for the diving excursion",
                                            ["certified_diving"]) == []


def test_mencion_generica_de_buceo_es_del_producto_principal():
    st = _state(detected_activity="minicourse")
    msg = "quería regalarle a mi esposo una experiencia del buceo, no tiene experiencia"
    assert "certified_diving" not in core._menciones_de_otro_producto(st, msg, ["certified_diving", "minicourse"])


def test_mencion_especifica_de_otro_producto_si_cuenta():
    st = _state(detected_activity="minicourse")
    msg = "yo hago el minicurso y mi amigo es buzo certificado"
    assert "certified_diving" in core._menciones_de_otro_producto(st, msg, ["certified_diving", "minicourse"])


def test_snorkel_nombrado_siempre_cuenta():
    st = _state(detected_activity="certified_diving")
    assert core._menciones_de_otro_producto(st, "mis amigos hacen snorkel", ["snorkel"]) == ["snorkel"]


# --- cierre_sin_repetir: tras el cierre, "¿cuánto dura?" se contesta sola --------------------------------------

@pytest.fixture
def _offline(monkeypatch):
    for name in ("fill_gaps", "detect_special_signals", "resolve_slot_answer"):
        monkeypatch.setattr(core, name, AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))


async def _cerrada(monkeypatch):
    st = _state()
    for m in ("quiero hacer el curso open water, estoy en cartagena", "para mi", "no soy colombiano"):
        await route_message(st, m)
    assert "book.divingplanet.org" in st.history[-1]["content"]
    return st


@pytest.mark.parametrize("flag, repite", [(True, False), (False, True)])
async def test_el_cierre_igual_no_se_repite_tras_una_respuesta(monkeypatch, _offline, flag, repite):
    monkeypatch.setattr(settings, "cierre_sin_repetir", flag)
    st = await _cerrada(monkeypatch)
    r = await route_message(st, "¿Cuánto tiempo dura?")
    assert r.startswith("rag_answer_stub")  # la respuesta del RAG (stub del conftest) va siempre
    assert ("book.divingplanet.org" in r) is repite


# --- jev_persona_ya_contada: "él quiere hacer snorkel" no es una persona nueva ----------------------------------

def _grupo_de_dos():
    return _state(detected_activity="certified_diving", detected_group_size=2,
                  detected_group_allocation={"certified_diving": 2})


@pytest.mark.parametrize("p, pregunta", [(0.05, False), (0.45, True), (None, True)])
def test_persona_ya_contada_se_mueve_sin_preguntar(monkeypatch, p, pregunta):
    monkeypatch.setattr(settings, "jev_persona_ya_contada", True)
    st = _grupo_de_dos()
    st._jev_adds_person = p
    core._add_or_ask_companion(st, "él quiere hacer snorkel", "snorkel", 1)
    assert bool(st.pending_companion_in_group) is pregunta
    if not pregunta:
        assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 1}
        assert st.detected_group_size == 2


def test_persona_ya_contada_con_el_flag_apagado_se_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "jev_persona_ya_contada", False)
    st = _grupo_de_dos()
    st._jev_adds_person = 0.05
    core._add_or_ask_companion(st, "él quiere hacer snorkel", "snorkel", 1)
    assert st.pending_companion_in_group == {"activity": "snorkel", "qty": 1}


def test_jev_pide_la_pregunta_solo_con_el_flag(monkeypatch):
    from src.agents import jev_router

    monkeypatch.setattr(settings, "jev_persona_ya_contada", True)
    assert jev_router.ADDS_PERSON in jev_router._questions_for_turn()
    assert jev_router.answers_to_signals({jev_router.ADDS_PERSON: {"type": "noul", "noul": 0.05}})[
        jev_router.ADDS_PERSON] == 0.05
    monkeypatch.setattr(settings, "jev_persona_ya_contada", False)
    assert jev_router.ADDS_PERSON not in jev_router._questions_for_turn()


# --- rag_condiciones_abiertas / rag_plan_elegido --------------------------------------------------------------

def test_la_regla_de_condiciones_va_en_el_prompt_del_rag(monkeypatch):
    from src.agents import rag_agent

    monkeypatch.setattr(settings, "rag_condiciones_abiertas", True)
    assert "Condiciones del cliente" in rag_agent.build_system_prompt("es")
    assert "Customer conditions" in rag_agent.build_system_prompt("en")
    monkeypatch.setattr(settings, "rag_condiciones_abiertas", False)
    assert "Condiciones del cliente" not in rag_agent.build_system_prompt("es")


@pytest.mark.parametrize("flag, palabra", [(True, "plan que está armando"), (False, "carrito")])
def test_el_contexto_del_rag_no_dice_carrito(monkeypatch, flag, palabra):
    from src.agents import supervisor

    monkeypatch.setattr(settings, "rag_plan_elegido", flag)
    st = _state(mixed_cart=[{"type": "course", "qty": 1, "label": "Curso Basico PADI (Open Water)"}])
    ctx = supervisor._build_extra_context(st) or ""
    assert palabra in ctx


# --- hotel_ubicacion_declarada (s4-27): la ubicacion deducida del hotel pasa por la puerta de Jev --------------

@pytest.mark.parametrize("flag", [True, False])
def test_la_ubicacion_del_hotel_se_declara(monkeypatch, flag):
    monkeypatch.setattr(settings, "hotel_ubicacion_declarada", flag)
    intent = core._detector.detect("¿Me pasas el contacto del hotel cocoliso?", _state())
    assert intent.location == "island" and intent.hotel == "cocoliso"
    assert ("location" in intent.detected_fields) is flag


def test_con_la_ubicacion_declarada_jev_la_tira_si_nadie_la_afirma(monkeypatch):
    monkeypatch.setattr(settings, "hotel_ubicacion_declarada", True)
    st = _state()
    st._affirms_p = {"location": 0.05}
    intent = core._detector.detect("me pasas el contacto del hotel cocoliso", st)
    core._drop_regex_fields_jev_denies(intent, st)
    assert intent.location is None
