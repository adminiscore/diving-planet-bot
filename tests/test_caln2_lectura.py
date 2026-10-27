"""CALN-2 (27-oct, tanda de precios de Gadea q1/q2 contra b26392c): lectura del grupo.

(A) «I'd do the 2 dives and she the mini course»: el minicurso se nombra por su nombre del catálogo en inglés.
(B) «I told you, she wants the mini course», con la pregunta de quien no ha elegido pendiente: es su elección; la
    actividad de quien escribe sigue.
(C) La pregunta de quien no ha elegido no supone que sea quien no está certificado."""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor as core_extractor
from src.domain import activities as dom
from src.flows.state import ConversationState


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln2-lectura", language="en")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("texto, nombra", [
    ("I'd do the 2 dives and she the mini course", True),
    ("she wants the minicourse", True),
    ("ella hace el minicurso", True),
    ("I want to do the dive", False),
    ("quiero un plan de buceo", False),
])
def test_el_minicurso_por_su_nombre_del_catalogo(texto, nombra):
    assert dom.nombra_el_producto("minicourse", texto) is nombra


def test_frases_comunes_no_nombran_productos():
    assert not dom.nombra_el_producto("companion", "as a gift")
    assert not dom.nombra_el_producto("companion", "ir de compras")


def test_a_el_reparto_con_el_minicurso_en_ingles_se_acepta():
    st = _estado(detected_activity="certified_diving", detected_group_size=2)
    valido = core_extractor._reparto_valido({"certified_diving": 1, "minicourse": 1},
                                            "I'd do the 2 dives and she the mini course", st)
    assert valido == {"certified_diving": 1, "minicourse": 1}


def test_b_contesta_la_pregunta_de_quien_no_ha_elegido():
    st = _estado(detected_activity="certified_diving", detected_group_size=2, pending_undecided_qty=1,
                 core_pending_slot=core.SLOT_COMPANION_ACTIVITY, detected_group_allocation={"certified_diving": 1})
    it = DetectedIntent()
    core_extractor._poner_actividad(it, st, {"activity": "minicourse"}, "I told you, she wants the mini course")
    assert it.activity is None  # la principal no cambia
    assert st.pending_companion_activity == "minicourse" and st.needs_companion_activity is False


def test_b_sin_la_pregunta_pendiente_cambia_la_principal_como_siempre():
    st = _estado(detected_activity="certified_diving", detected_group_size=1)
    it = DetectedIntent()
    core_extractor._poner_actividad(it, st, {"activity": "minicourse"}, "actually I'd rather do the mini course")
    assert it.activity == "minicourse"


@pytest.mark.parametrize("lang, plural, esperado", [
    ("es", 1, "quien aún no ha elegido"), ("es", 2, "quienes aún no han elegido"),
    ("en", 1, "the one who hasn't chosen yet"), ("en", 2, "those who haven't chosen yet"),
])
def test_c_la_pregunta_no_supone_que_no_este_certificado(lang, plural, esperado):
    st = _estado(language=lang, pending_undecided_qty=plural)
    texto = core.ask_slot(st, core.SLOT_COMPANION_ACTIVITY)
    assert esperado in texto and "certific" not in texto.lower()


@pytest.fixture(autouse=True)
def _sin_llm(monkeypatch):
    from src.agents.nucleo import extraction as core_extraction

    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))
