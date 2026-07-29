"""Cobertura de los helpers de render que el núcleo conserva (Fase 4).

Estos helpers eran métodos de `DecisionTree` usados por el flujo legacy `MIXED_*`
(retirado en Fase 4) Y por el núcleo conversacional (los conserva). Al eliminar
`test_decision_tree.py` (que probaba el flujo muerto), estos tests fijan la
cobertura del código CONSERVADO: catálogo/precios/links deterministas.
"""

from src.flows import cart_render
from src.flows.state import ConversationState


def _state(lang="es", location="cartagena", is_colombian=False):
    s = ConversationState(conversation_id="cart-render-test")
    s.language = lang
    s.location = location
    s.is_colombian = is_colombian
    return s


def test_cart_label_for_each_type():
    assert "inmersion" in cart_render.cart_label_for("cert", "2_dives_1_day", "es").lower()
    assert cart_render.cart_label_for("beginner", None, "es")
    assert "snorkel" in cart_render.cart_label_for("snorkel", None, "es").lower()
    assert cart_render.cart_label_for("beginner", None, "en")


def test_service_for_location_variants():
    s_ctg = _state(location="cartagena")
    s_isl = _state(location="island")
    # Desde Cartagena mantiene el id base; en isla resuelve a su variante.
    assert cart_render.service_for_location("2_dives_1_day", s_ctg) == "2_dives_1_day"
    island_variant = cart_render.service_for_location("2_dives_1_day", s_isl)
    assert island_variant.endswith("already_on_island") or island_variant == "2_dives_1_day"


def test_parse_quantity_digits_words_and_none():
    assert cart_render.parse_quantity("2") == 2
    assert cart_render.parse_quantity("dos") == 2
    assert cart_render.parse_quantity("tres personas") == 3
    assert cart_render.parse_quantity("bla bla") is None


def test_cart_booking_blocks_has_link():
    s = _state()
    s.mixed_cart = [{"type": "cert", "qty": 2, "plan": "2_dives_1_day",
                     "label": cart_render.cart_label_for("cert", "2_dives_1_day", "es")}]
    blocks = cart_render.cart_booking_blocks(s)
    assert blocks
    assert any("http" in (b.get("url") or "") for b in blocks)


def test_goto_final_summary_renders_price_and_link():
    s = _state()
    s.mixed_cart = [{"type": "cert", "qty": 2, "plan": "2_dives_1_day",
                     "label": cart_render.cart_label_for("cert", "2_dives_1_day", "es")}]
    summary = cart_render.goto_final_summary(s)
    assert summary
    assert ("USD" in summary or "U$" in summary)
    assert "http" in summary
