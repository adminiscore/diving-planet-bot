"""lat-11 T6b (26-oct): con «¿Cuántos serían para X?» pendiente, la cifra sola del cliente contesta esa pregunta.

Sin el atajo del detector entero, «3 personas» seguía el turno y el extractor la leía como el TOTAL del grupo: luego el
resolutor la repartía a X y salían 3 buzos + 3 de snorkel (banco docs/robustness/lat/banco-lat11-t6b.json, c1; c2
«son 2» ya fallaba así antes). El total solo cambia si el extractor trae también el reparto.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.conversational_core import SLOT_COMPANION_QTY, SLOT_QTY
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


@pytest.fixture
def extractor(monkeypatch):
    def con(datos):
        monkeypatch.setattr(core_extractor, "datos_del_extractor", AsyncMock(return_value=datos))
        monkeypatch.setattr(core_extractor, "lectura_del_extractor", AsyncMock(return_value=datos))

    return con


def _estado(slot: str) -> ConversationState:
    st = ConversationState(conversation_id="lat11-t6b", language="es")
    st.detected_activity = "certified_diving"
    st.is_certified = st.detected_is_certified = True
    st.location = st.detected_location = "cartagena"
    st.core_pending_slot = slot
    if slot == SLOT_COMPANION_QTY:
        st.pending_companion_activity = "snorkel"
    return st


@pytest.mark.asyncio
@pytest.mark.parametrize("mensaje,n", [("3 personas", 3), ("son 2", 2)])
async def test_la_cifra_que_contesta_cuantos_para_x_no_es_el_total(extractor, mensaje, n):
    extractor({"group_size": n})
    st = _estado(SLOT_COMPANION_QTY)
    await core._understand(st, mensaje)
    assert st.detected_group_size is None


@pytest.mark.asyncio
async def test_con_el_reparto_el_total_si_cuenta(extractor):
    extractor({"group_size": 4, "group_allocation": {"certified_diving": 2, "snorkel": 2}})
    st = _estado(SLOT_COMPANION_QTY)
    await core._understand(st, "somos 4: dos buceamos y dos hacen snorkel")
    assert st.detected_group_size == 4


@pytest.mark.asyncio
async def test_a_la_pregunta_del_total_la_cifra_es_el_total(extractor):
    extractor({"group_size": 3})
    st = _estado(SLOT_QTY)
    await core._understand(st, "3 personas")
    assert st.detected_group_size == 3
