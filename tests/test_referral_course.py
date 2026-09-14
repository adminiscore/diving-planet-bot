"""Curso referido de Open Water (owner 2026-09-14).

Cuesta 474 USD frente a 693 del Open Water completo: leerlo como Open Water
cotizaba 219 USD de mas. Decision del owner: solo cuenta si el cliente lo dice, y
entonces se cierra con el asesor (sin link de reserva). Nada de listas: las
"hermanas" salen del registro y el cierre con asesor del campo `contact_only` de
services.json.
"""

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.intent_detector import IntentDetector
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState


def test_open_water_and_referral_are_siblings_derived_from_the_registry():
    assert dom.sibling_ids("padi_open_water") == ["padi_open_water_referral"]
    assert dom.sibling_ids("padi_open_water_referral") == ["padi_open_water"]
    assert dom.sibling_ids("padi_advanced") == []
    assert dom.sibling_ids("specialty_nitrox") == []


def test_regex_keeps_open_water_but_the_llm_checks_its_sibling():
    """v2 (2026-09-15): el veto de actividad dispara si la actividad tiene hermana
    en el registro. El regex se queda con el Open Water si el LLM falla o no
    discrepa; el LLM solo cambia al referido si el cliente lo describe (glosa que
    ya no nombra al Open Water: el v1 bajaba el eval-set)."""
    message = "quiero hacer el open water"
    intent = IntentDetector().detect(message, ConversationState(conversation_id="ow"))
    assert intent.activity == "padi_open_water"
    assert supervisor._activity_should_verify(message, intent) is True


def test_activities_without_siblings_keep_the_old_trigger():
    message = "quiero hacer snorkel"
    intent = IntentDetector().detect(message, ConversationState(conversation_id="snk"))
    assert supervisor._activity_should_verify(message, intent) is False


def test_referral_gloss_does_not_name_open_water():
    """La glosa del v1 decia "si no lo dice, es padi_open_water" y empujaba al
    modelo hacia el Open Water en mensajes de principiante."""
    gloss = dom.by_id("padi_open_water_referral").gloss
    assert gloss and all("padi_open_water" not in text for text in gloss.values())


def test_referral_closes_with_an_advisor_from_catalog_data():
    assert cart_render._is_contact_only_service("referral") is True
    assert cart_render._is_contact_only_service("referral_already_on_island") is True
    assert cart_render._is_contact_only_service("divemaster") is True
    assert cart_render._is_contact_only_service("open_water") is False


def test_referral_is_cartable_but_never_offered():
    assert "padi_open_water_referral" in dom.cart_activity_ids()
    assert dom.by_id("padi_open_water_referral").offer is False
    state = ConversationState(conversation_id="lvl")
    state.detected_activity = "padi_course"
    assert "padi_open_water_referral" not in core._course_level_options(state)
