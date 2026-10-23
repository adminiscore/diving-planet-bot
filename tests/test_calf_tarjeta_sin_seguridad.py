"""CAL-F pareja-certificados-cop-descuento-almuerzo (18-oct, decisión de Gadea; promocionado, su flag `tarjeta_sin_seguridad` se borró en sim-5).

Si solo falta la respuesta de seguridad y el cliente no la contestó, la tarjeta con el precio sale igualmente, con la
pregunta una vez dentro y el precio del refresher en UNA sola moneda (COP a colombianos y residentes; USD al resto).
"""

import pytest

from src.agents import conversational_core as core
from src.flows import cart_render
from src.flows.state import ConversationState


def _pareja(colombianos=True):
    st = ConversationState(conversation_id="calf-pareja")
    st.language = "es"
    st.detected_activity = "certified_diving"
    st.is_certified = st.detected_is_certified = True
    st.location = st.detected_location = "cartagena"
    st.detected_group_size = 2
    st.is_colombian = colombianos
    return st


@pytest.mark.parametrize("prev, sale", [(core.SLOT_SAFETY, True), (None, False)])
def test_la_tarjeta_sale_si_solo_falta_la_seguridad_sin_contestar(prev, sale):
    st = _pareja()
    nxt = core.next_missing_slot(st)
    assert nxt == core.SLOT_SAFETY
    assert core._tarjeta_sin_seguridad(st, nxt, prev) is sale


def test_si_falta_otra_cosa_no_sale(monkeypatch):
    st = _pareja(colombianos=None)  # falta también la nacionalidad
    assert core._tarjeta_sin_seguridad(st, core.SLOT_SAFETY, core.SLOT_SAFETY) is False


@pytest.mark.parametrize("colombianos, moneda, otra", [(True, "COP", "USD"), (False, "USD", "COP")])
def test_la_nota_lleva_una_sola_moneda(colombianos, moneda, otra):
    nota = core._nota_seguridad(_pareja(colombianos))
    assert moneda in nota and otra not in nota and "2 años" in nota


def test_sin_una_moneda_el_precio_de_siempre():
    texto = cart_render.refresher_price_text(_pareja())
    assert "USD" in texto and "COP" in texto

