"""Sparring s04b (4-nov, la 9.ª tanda, contra PRE 0.47; hallazgos CALN-S04B-01): familia en las islas, los padres
snorkel y los niños de 9 y 11 sin elegir. «Can our 11-year-old do the mini course?» metía a los 2 en el minicurso (el de
9 no tiene edad: desde 10) y la tarjeta cobraba 2. Ahora eligen solo los que nombra el mensaje y tienen edad. Sin red."""
from src.agents import conversational_core as core
from src.agents.nucleo.extractor import _cuantos_eligen
from src.flows.state import ConversationState


def _familia() -> ConversationState:
    st = ConversationState(conversation_id="s04b", language="en")
    st.detected_activity, st.location, st.detected_ages = "snorkel", "island", [9, 11]
    st.detected_group_size = 4
    st.detected_group_allocation = {"snorkel": 2}
    st.pending_undecided_qty = 2
    return st


def test_eligen_solo_los_que_nombra_el_mensaje_y_tienen_edad():
    assert _cuantos_eligen("minicourse", {"edades": [11]}, 2) == 1
    assert _cuantos_eligen("minicourse", {"edades": [9, 11]}, 2) == 1
    assert _cuantos_eligen("minicourse", {"edades": [9]}, 2) == 0
    assert _cuantos_eligen("snorkel", {"edades": [9, 11]}, 2) == 2
    assert _cuantos_eligen("minicourse", {}, 2) is None
    assert _cuantos_eligen("minicourse", {"edades": [40, 11, 9]}, 2) is None


def test_el_de_11_al_minicurso_y_el_de_9_sigue_sin_elegir():
    st = _familia()
    core._elige_quien_falta(st, "minicourse", 1)
    assert st.detected_group_allocation == {"snorkel": 2, "minicourse": 1}
    assert st.pending_undecided_qty == 1 and st.needs_companion_activity
    assert st.detected_group_size == 4
    st = _familia()
    core._elige_quien_falta(st, "minicourse")
    assert st.detected_group_allocation == {"snorkel": 2, "minicourse": 2} and not st.pending_undecided_qty


def test_bubble_makers_sale_con_su_servicio_y_no_como_otro_minicurso():
    """Con el reparto bien, la tarjeta pintaba dos «Dive Mini Course» con enlace: Bubble Makers comparte el tipo
    «beginner» con el minicurso y se resolvía como él. Ahora lleva su servicio y, sin enlace, va al asesor."""
    from src.flows import cart_render

    st = _familia()
    st.is_colombian = False
    st.mixed_cart = [core._cart_item(st, "snorkel", 2), core._cart_item(st, "minicourse", 1),
                     core._cart_item(st, "bubble_makers", 1)]
    bloques = [(b["label"], b["qty"], b["url"]) for b in cart_render.cart_booking_blocks(st)]
    assert [q for _, q, _ in bloques] == [2, 1, 1]
    assert "Mini" in bloques[1][0] and bloques[1][2]
    assert "Bubble Makers" in bloques[2][0] and bloques[2][2] is None
