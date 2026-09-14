"""El carrito se deriva del registro de actividades (centralizacion, 2026-09-15).

Antes `conversational_core._cart_item`, `cart_render._cart_label_for` y
`_cart_service_id` tenian una rama escrita a mano por actividad. Ahora el tipo de
item, el servicio base y la etiqueta salen del registro (`cart_type`, `services`,
`texts.price_label`); solo el buceo certificado y los cursos llevan plan propio.
"""

import pytest

from src.agents import conversational_core as core
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState


@pytest.mark.parametrize("cart_type,activity", [
    ("cert", "certified_diving"),
    ("beginner", "minicourse"),       # Bubble Makers comparte tipo pero no tiene servicio
    ("snorkel", "snorkel"),
    ("refresh", "refresher"),         # se vende como el minicurso
    ("companion", "companion"),
])
def test_each_cart_type_has_one_registry_activity(cart_type, activity):
    assert dom.cart_activity_for_type(cart_type) == activity


@pytest.mark.parametrize("item_type,island,service", [
    ("cert", False, "2_dives_1_day"),
    ("cert", True, "2_dives_1_day_already_on_island"),
    ("beginner", False, "minicourse"),
    ("beginner", True, "minicourse_already_on_island"),
    ("refresh", True, "minicourse_already_on_island"),
    ("snorkel", False, "snorkeling"),
    ("companion", False, None),
    ("course", False, None),
])
def test_cart_service_comes_from_the_registry(item_type, island, service):
    state = ConversationState(conversation_id="cart")
    state.location = "island" if island else "cartagena"
    assert cart_render._cart_service_id(item_type, None, state) == service


def test_cart_labels_come_from_the_registry():
    assert cart_render._cart_label_for("beginner", None, "es") == dom.text("minicourse", "price_label", "es")
    assert cart_render._cart_label_for("companion", None, "en") == dom.text("companion", "price_label", "en")
    # con plan concreto manda el nombre del servicio del catalogo
    assert "Open Water" in cart_render._cart_label_for("course", "open_water", "es")
    # sin plan, un curso lleva la etiqueta generica (varias actividades comparten `course`)
    assert cart_render._cart_label_for("course", None, "es") == dom.label("padi_course", "es")


def test_cart_item_type_is_the_registry_cart_type():
    state = ConversationState(conversation_id="item")
    state.location = "cartagena"
    for activity in ("minicourse", "snorkel", "companion"):
        assert core._cart_item(state, activity, 1)["type"] == dom.by_id(activity).cart_type
    course = core._cart_item(state, "padi_advanced", 2)
    assert course["type"] == "course" and course["plan"] == dom.base_service_id("padi_advanced")
