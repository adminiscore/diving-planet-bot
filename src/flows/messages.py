"""
Plantillas de mensajes y menús de botones.

Extraído de ``decision_tree.py`` (reorg §1): el diccionario ``MESSAGES``, los
``BUTTON_OPTIONS``, el helper ``get_button_options`` y la clase ``DecisionTree``
(arma los quick-replies del supervisor). Depende de ``state`` para
``ButtonOption``/``ConversationState``.
"""

from src.flows.state import ButtonOption, ConversationState

# --- Messages templates ---

MESSAGES = {
    "main_menu": {
        "es": (
            "¡Cuéntame! ¿Qué te gustaría hacer?"
        ),
        "en": (
            "What would you like to do?"
        ),
    },
    "escalate": {
        "es": (
            "Te paso con un asesor del equipo de Diving Planet.\n"
            "Enseguida se pone en contacto contigo. ¡Gracias! :)"
        ),
        "en": (
            "I'll connect you with an advisor from the Diving Planet team.\n"
            "They will contact you shortly. Thanks! :)"
        ),
    },
}

BUTTON_OPTIONS = {
    "main_menu": {
        "es": [
            {"title": "🤿 Reservar", "value": "1"},
            {"title": "ℹ️ Información", "value": "2"},
        ],
        "en": [
            {"title": "🤿 Book", "value": "1"},
            {"title": "ℹ️ Information", "value": "2"},
        ],
    },
}


def get_button_options(key: str, language: str) -> list[dict]:
    return [
        ButtonOption(title=option["title"], value=option["value"]).as_chatwoot_item()
        for option in BUTTON_OPTIONS.get(key, {}).get(language, [])
    ]


class DecisionTree:
    """
    Stateful decision tree that guides customers through predefined flows.
    No LLM calls — pure logic for Phase 1.
    """

    # Booking-cart menus that must NOT show a "Volver" button (owner decision
    # 2026-07-21): a certified diver who already said what they want shouldn't be
    # sent back into menus — changes are handled by natural language, and typing
    # "volver" still works (is_back). Info/navigation menus keep their Back.
    _CART_MENU_KEYS = frozenset({
        "mixed_entry", "mixed_ask_certification", "mixed_ask_certification_group",
        "mixed_add_activity", "mixed_companion_upsell", "mixed_add_cert_plan",
        "mixed_add_cert_multi_day", "mixed_add_cert_4dive_variant",
        "mixed_add_cert_1day_variant", "mixed_add_cert_2day_variant",
        "mixed_quantity", "mixed_preview_actions", "mixed_kids_age",
        "courses_menu", "courses_open_water_origin", "courses_open_water_time",
        "courses_advanced_menu", "courses_specialties_menu",
    })

    def set_quick_replies(self, state: ConversationState, key: str):
        options = get_button_options(key, state.language)
        if key in self._CART_MENU_KEYS:
            options = [o for o in options if o.get("value") != "back"]
        state.quick_replies = options
