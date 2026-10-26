"""
Plantillas de mensajes y menús de botones.

Extraído de ``decision_tree.py`` (reorg §1): el diccionario ``MESSAGES``, los
``BUTTON_OPTIONS``, el helper ``get_button_options`` y ``set_quick_replies``
(arma los quick-replies del supervisor). Depende de ``state`` para
``ButtonOption``/``ConversationState``.
"""


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


