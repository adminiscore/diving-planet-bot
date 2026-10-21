"""Curso referido de Open Water (owner 2026-09-14).

Cuesta 474 USD frente a 693 del Open Water completo: leerlo como Open Water
cotizaba 219 USD de mas. Decision del owner: solo cuenta si el cliente lo dice, y
entonces se cierra con el asesor (sin link de reserva); desde el 21-oct (Gadea) se reserva con su enlace. Nada de listas: las
"hermanas" salen del registro y el cierre con asesor del campo `contact_only` de
services.json.
"""

from src.agents import conversational_core as core
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState


def test_open_water_and_referral_are_siblings_derived_from_the_registry():
    assert dom.sibling_ids("padi_open_water") == ["padi_open_water_referral"]
    assert dom.sibling_ids("padi_open_water_referral") == ["padi_open_water"]
    assert dom.sibling_ids("padi_advanced") == []
    assert dom.sibling_ids("specialty_nitrox") == []


def test_referral_gloss_does_not_name_open_water():
    """La glosa del v1 decia "si no lo dice, es padi_open_water" y empujaba al
    modelo hacia el Open Water en mensajes de principiante."""
    gloss = dom.by_id("padi_open_water_referral").gloss
    assert gloss and all("padi_open_water" not in text for text in gloss.values())


def test_referral_books_online_like_the_other_courses():
    """gen-19 (21-oct, decisión de Gadea): el Referido se reserva con su enlace online, como los demás cursos (antes
    lo cerraba un asesor y el RAG daba la página de información como si fuera para reservar)."""
    assert cart_render._is_contact_only_service("referral") is False
    assert cart_render._is_contact_only_service("referral_already_on_island") is False
    assert cart_render._is_contact_only_service("divemaster") is True
    assert cart_render._is_contact_only_service("open_water") is False


def test_referral_is_cartable_but_never_offered():
    assert "padi_open_water_referral" in dom.cart_activity_ids()
    assert dom.by_id("padi_open_water_referral").offer is False
    state = ConversationState(conversation_id="lvl")
    state.detected_activity = "padi_course"
    assert "padi_open_water_referral" not in core._course_level_options(state)


def test_referral_booking_links_reach_the_rag():
    """gen-19 (21-oct): sin `contact_only`, los enlaces del Referido entran en los enlaces de reserva que ve el RAG
    (antes daba la página de información como si fuera para reservar)."""
    from src.flows.catalog import catalog_booking_links

    assert "book/referral/6" in catalog_booking_links("es")
    assert "referral-already-on-the-island" in catalog_booking_links("es")
