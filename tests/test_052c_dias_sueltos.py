"""Sparring s04j y s04l (4-nov): quien quiere bucear 2 días sueltos recibía solo paquetes, sin la salida de un día."""
from src.flows import hechos
from src.flows.state import ConversationState


def _estado(**campos):
    st = ConversationState(conversation_id="052c", language="en", is_colombian=False, detected_duration="multi_day",
                           duracion_de_buceo=True, **campos)
    return st


def _planes(st):
    bloque = hechos.hechos(st, ["precio"], ["certified_diving"])[0]
    return [p["plan"] for p in bloque.get("otros_planes") or []]


def test_dos_dias_desde_cartagena_lleva_la_salida_de_un_dia():
    planes = _planes(_estado(location="cartagena"))
    assert any("2 dives (1 day)" in p for p in planes), planes
    assert any("days" in p for p in planes), planes  # y un paquete, que también le puede interesar


def test_dos_dias_desde_las_islas_lleva_la_salida_de_un_dia():
    planes = _planes(_estado(location="island"))
    assert any("2 dives (1 day" in p for p in planes), planes


def _familia_con_hijos(edades, carrito):
    st = ConversationState(conversation_id="s04m", language="es", is_colombian=False, location="cartagena")
    st.detected_ages = edades
    st.mixed_cart = carrito
    return st


def test_s04m_el_de_11_no_lleva_la_etiqueta_si_el_de_8_ya_tiene_bubble_makers():
    from src.flows import cart_render

    st = _familia_con_hijos([8, 11], [{"type": "beginner", "qty": 1, "plan": None, "label": "x"},
                                      {"type": "beginner", "qty": 1, "plan": "bubble_makers", "label": "x"}])
    bloques = cart_render.cart_booking_blocks(st)
    assert [b["qty"] for b in bloques] == [1, 1]
    assert "Bubble" not in bloques[0]["label"] and bloques[0]["url"]
    assert "Bubble" in bloques[1]["label"] and bloques[1]["url"] is None


def test_s04m_el_de_8_sin_plan_propio_va_a_bubble_makers_con_su_precio_y_al_asesor():
    from src.flows import cart_render

    st = _familia_con_hijos([8, 12], [{"type": "beginner", "qty": 2, "plan": None, "label": "x"}])
    bloques = cart_render.cart_booking_blocks(st)
    minicurso, bubble = bloques[0], bloques[1]
    assert "Bubble" not in minicurso["label"] and minicurso["url"]
    assert "Bubble" in bubble["label"] and bubble["url"] is None and bubble["usd"] != minicurso["usd"]


def test_s04m_con_10_anos_vale_el_minicurso():
    from src.flows import cart_render

    st = _familia_con_hijos([10], [{"type": "beginner", "qty": 2, "plan": None, "label": "x"}])
    bloques = cart_render.cart_booking_blocks(st)
    assert len(bloques) == 1 and "Bubble" not in bloques[0]["label"] and bloques[0]["qty"] == 2


def test_con_un_plan_elegido_no_se_fuerza():
    st = _estado(location="cartagena")
    st.detected_service_id = "7_dives_3_days"
    planes = _planes(st)
    assert len(planes) <= hechos._OTROS_POR_ORIGEN
