"""
Shim de compatibilidad — el contenido real se partió en módulos honestos (reorg §1).

Tras la Fase 4 este archivo dejó de ser un "árbol de decisión" (el árbol legacy
`MIXED_*` se borró). Su contenido se repartió en:

- ``src.flows.state``    → ``Step``, ``ConversationState``, ``ButtonOption``, ``MESSAGE_SPLIT``.
- ``src.flows.catalog``  → ``SERVICES`` + mapas + formateadores + heurística de idioma.
- ``src.flows.messages`` → ``MESSAGES``, ``BUTTON_OPTIONS``, ``get_button_options``, ``DecisionTree``.

Este módulo re-exporta todo para no romper los importadores existentes
(``from src.flows.decision_tree import X``) ni los monkeypatches de la suite.
Código nuevo: importar de los módulos concretos. Ver docs/future/decision-tree-reorg.md §1.
"""

from src.flows.catalog import (
    _ENGLISH_STOPWORDS,
    _SPANISH_STOPWORDS,
    COMPANION_PRICE,
    ISLAND_SERVICE_MAP,
    LARGE_GROUP_ADVISOR_THRESHOLD,
    MULTI_DAY_SERVICES,
    REFRESHER_PRESERVE_SERVICES,
    SERVICE_TO_CART_TYPE,
    SERVICES,
    SPECIALTY_SERVICE_IDS,
    _detect_language_from_text,
    _detect_language_heuristic,
    _extra_notes,
    _extra_notes_multiline,
    _flight_rule,
    _format_duration,
    _format_price,
    _join_items,
    _load_companion_price,
    _load_services,
    _sanitize_includes,
)
from src.flows.messages import (
    BUTTON_OPTIONS,
    MESSAGES,
    DecisionTree,
    get_button_options,
)
from src.flows.state import (
    MESSAGE_SPLIT,
    ButtonOption,
    ConversationState,
    Step,
)

__all__ = [
    # state
    "MESSAGE_SPLIT",
    "Step",
    "ButtonOption",
    "ConversationState",
    # catalog
    "SERVICES",
    "ISLAND_SERVICE_MAP",
    "SERVICE_TO_CART_TYPE",
    "MULTI_DAY_SERVICES",
    "LARGE_GROUP_ADVISOR_THRESHOLD",
    "REFRESHER_PRESERVE_SERVICES",
    "SPECIALTY_SERVICE_IDS",
    "COMPANION_PRICE",
    "_SPANISH_STOPWORDS",
    "_ENGLISH_STOPWORDS",
    "_detect_language_heuristic",
    "_detect_language_from_text",
    "_join_items",
    "_sanitize_includes",
    "_format_price",
    "_format_duration",
    "_flight_rule",
    "_extra_notes",
    "_extra_notes_multiline",
    "_load_services",
    "_load_companion_price",
    # messages
    "MESSAGES",
    "BUTTON_OPTIONS",
    "get_button_options",
    "DecisionTree",
]
