"""CALN-2 (27-oct, sparring b2 / banco-sparring s03): tras el cierre, si el reparto cambia, la tarjeta se rehace entera
desde el reparto. Antes solo se añadían los tipos nuevos: «no, él es buzo; solo yo hago el minicurso» dejaba
«minicurso × 2» y sumaba el buceo (tres plazas para dos)."""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.supervisor import route_message
from src.flows.state import ConversationState, Step


@pytest.fixture(autouse=True)
def _sin_llm(monkeypatch):
    senales = AsyncMock(return_value={})
    monkeypatch.setattr(core_routing, "detect_special_signals", senales)
    monkeypatch.setattr(core_extraction, "detect_special_signals", senales)
    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))


def _pareja_cerrada_con_dos_minicursos() -> ConversationState:
    st = ConversationState(conversation_id="caln2-tarjeta")
    st.language = "en"
    st.step = Step.FREE_TEXT
    st.detected_activity = "minicourse"
    st.location = "island"
    st.hotel = "Isla Grande"
    st.detected_group_size = 2
    st.is_colombian = False
    st.last_dive_over_2_years = True
    st.mixed_cart = [core._cart_item(st, "minicourse", 2)]
    st.core_pending_slot = None
    return st


def _por_tipo(st) -> dict:
    return {i["type"]: i["qty"] for i in st.mixed_cart}


@pytest.mark.asyncio
async def test_corregir_el_reparto_rehace_la_tarjeta(extractor_dice):
    mensaje = "No wait, he's a certified diver, he wants the fun dives. Only I'm doing the mini course."
    extractor_dice({mensaje: {"group_allocation": {"certified_diving": 1, "minicourse": 1}}})
    st = _pareja_cerrada_con_dos_minicursos()
    await route_message(st, mensaje)
    tipos = _por_tipo(st)
    assert sum(tipos.values()) == 2, tipos  # dos personas, dos plazas
    assert tipos.get(core._cart_item(st, "minicourse", 1)["type"]) == 1
    assert tipos.get(core._cart_item(st, "certified_diving", 1)["type"]) == 1


def test_si_cuadra_no_se_toca():
    st = _pareja_cerrada_con_dos_minicursos()
    st.detected_group_allocation = {"minicourse": 2}
    antes = list(st.mixed_cart)
    assert core_extraction._rehacer_la_tarjeta_si_no_cuadra(st) is False
    assert st.mixed_cart == antes


def test_sin_reparto_no_se_toca():
    st = _pareja_cerrada_con_dos_minicursos()
    assert core_extraction._rehacer_la_tarjeta_si_no_cuadra(st) is False
