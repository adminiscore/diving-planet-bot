"""
Estado y tipos de la conversación.

Extraído de ``decision_tree.py`` (reorg §1): contiene el enum ``Step``, el
dataclass ``ConversationState`` y ``ButtonOption``, más el separador de mensajes
``MESSAGE_SPLIT``. Módulo hoja — sin dependencias de catálogo ni de mensajes.
"""

from dataclasses import dataclass, field
from enum import Enum

# Separador interno: si una respuesta del bot contiene este token, el canal
# (Chatwoot) la divide en mensajes independientes. Útil para mandar el itinerario
# completo en un mensaje y las opciones de follow-up en otro.
MESSAGE_SPLIT = "<<<SPLIT>>>"


class Step(str, Enum):
    WELCOME = "welcome"
    LANGUAGE = "language"
    MAIN_MENU = "main_menu"
    RESERVA_MENU = "reserva_menu"
    INFO_MENU = "info_menu"
    INFO_ACTIVITY_LOCATION = "info_activity_location"
    INFO_ACTIVITIES_MENU = "info_activities_menu"
    INFO_TOURS_MENU = "info_tours_menu"
    INFO_PACKAGES_MENU = "info_packages_menu"
    INFO_COURSES_MENU = "info_courses_menu"
    INFO_SPECIALTIES_MENU = "info_specialties_menu"
    INFO_TOUR_DETAIL = "info_tour_detail"
    INFO_PACKAGE_DETAIL = "info_package_detail"
    INFO_COURSE_DETAIL = "info_course_detail"
    INFO_SPECIALTY_DETAIL = "info_specialty_detail"
    INFO_TOURS_CERTIFIED_MENU = "info_tours_certified_menu"
    INFO_COURSES_ADVANCED_MENU = "info_courses_advanced_menu"
    INFO_MIXED_ACTIVITY_MENU = "info_mixed_activity_menu"
    INFO_MIXED_CERT_BEG_MENU = "info_mixed_cert_beg_menu"
    INFO_CERTIFIED_4_DIVES_VARIANT = "info_certified_4_dives_variant"
    # Pasos legacy de menú de cursos (el flujo guiado se retiró en Fase 4).
    COURSES_MENU = "courses_menu"
    COURSES_OPEN_WATER_ORIGIN = "courses_open_water_origin"
    COURSES_OPEN_WATER_TIME = "courses_open_water_time"
    COURSES_ADVANCED_MENU = "courses_advanced_menu"
    COURSES_SPECIALTIES_MENU = "courses_specialties_menu"
    PRICING_MENU = "pricing_menu"
    PRICING_COLOMBIAN = "pricing_colombian"
    PRICING_CARTAGENA = "pricing_cartagena"
    PRICING_ISLANDS = "pricing_islands"
    PRICING_PACKAGES = "pricing_packages"
    PRICING_DISCOUNTS = "pricing_discounts"
    BOOKING_MENU = "booking_menu"
    LOGISTICS_MENU = "logistics_menu"
    LOGISTICS_MEETING = "logistics_meeting"
    LOGISTICS_INCLUDES = "logistics_includes"
    LOGISTICS_WHAT_TO_BRING = "logistics_what_to_bring"
    ISLAND_MENU = "island_menu"
    ISLAND_HOTEL_MENU = "island_hotel_menu"
    SERVICE_DETAIL = "service_detail"
    LOCATION = "location"
    COLOMBIAN = "colombian"
    SUMMARY = "summary"
    ESCALATE = "escalate"
    FREE_TEXT = "free_text"


@dataclass(frozen=True)
class ButtonOption:
    title: str
    value: str

    def as_chatwoot_item(self) -> dict:
        return {"title": self.title, "value": self.value}


@dataclass
class ConversationState:
    conversation_id: str
    language: str = "es"
    step: Step = Step.WELCOME
    selected_service: str | None = None
    is_certified: bool | None = None
    location: str | None = None
    island: str | None = None
    hotel: str | None = None
    is_colombian: bool | None = None
    last_dive_over_2_years: bool | None = None
    has_500_dives_or_dive_master: bool | None = None
    refresher_interested: bool | None = None
    original_service: str | None = None
    history: list[dict] = None
    quick_replies: list[dict] = field(default_factory=list)
    pending_note: str | None = None
    pending_escalation_reason: str | None = None
    # Set when a lead note should be generated WITHOUT escalating to a human
    # (e.g. a booking link was sent directly to a non-Colombian client) — the
    # conversation stays open instead of being toggled to "pending" in Chatwoot.
    pending_lead_note_reason: str | None = None
    summary_mode: str | None = None
    back_step_override: Step | None = None
    back_quick_replies_key: str | None = None
    # Cart-style mixed-group state (replaces all previous mixed_* per-subgroup fields)
    mixed_cart: list[dict] = field(default_factory=list)
    # Each item: {"type": "cert"|"beginner"|"snorkel"|"course"|"companion", "qty": int,
    #             "plan": service-specific plan/service_id, "label": str}
    mixed_pending_qty_type: str | None = None    # which type is being added/edited
    mixed_pending_qty_plan: str | None = None    # holds cert plan while qty is collected
    mixed_pending_qty_value: int | None = None
    mixed_pending_preview_service_id: str | None = None
    mixed_display_currency: str = "USD"          # "USD" | "COP"
    mixed_final_is_colombian: bool | None = None
    mixed_final_has_kids_8_10: bool | None = None
    mixed_final_wants_private: bool | None = None
    # Kids age question — disparada en el cart-mixto si hay actividad para niños
    # o si el cliente mencionó hijos/familia en texto libre.
    kids_mention_detected: bool = False
    kids_age_group: str | None = None  # "under_8" | "eight_to_ten" | "ten_plus" | "mixed"
    kids_count: int | None = None  # cuántos niños (derivado para single-rango / mixed)
    kids_under_8_count: int = 0
    kids_eight_to_ten_count: int = 0
    mixed_last_summary: str | None = None        # final summary text (for lead note)
    # Ruta de entrada al flujo carrito: "booking" (entrada principal),
    # "diving_snorkel" (grupo mixto legacy) o "cert_beg" (certificados + principiantes).
    # Si es "cert_beg" no ofrecemos snorkel.
    mixed_entry_path: str | None = None
    # Lista de (label, booking_url) para enviar al cliente cuando pulse "Reservar"
    # en el resumen final del flujo mixto.
    mixed_booking_links: list[tuple[str, str]] = field(default_factory=list)
    # Intent detection fields - información detectada automáticamente de texto libre
    detected_language: str | None = None
    # Nombre del cliente para el trato cercano (persona Coral). Hoy solo se
    # captura del propio mensaje ("soy Rocío" / "me llamo..."); el de WhatsApp
    # (sender['name']) queda diferido hasta que el canal WhatsApp esté disponible
    # (el widget web no lo da de forma fiable). Ver docs/archive/conversational-refactor-plan.md.
    client_name: str | None = None
    detected_activity: str | None = None
    detected_service_id: str | None = None
    detected_is_certified: bool | None = None
    detected_group_size: int | None = None
    detected_group_allocation: dict | None = None
    detected_ages: list = field(default_factory=list)   # person ages mentioned across the conversation
    detected_last_dive_over_2_years: bool | None = None
    detected_duration: str | None = None
    detected_location: str | None = None
    detected_island: str | None = None
    detected_hotel: str | None = None
    # Explicit cert dive/day-count ("5 inmersiones" / "paquete de 3 dias") given
    # before location was known — consumed once (see _pop_detected_cert_counts)
    # so the plan isn't lost/re-asked.
    detected_cert_dives: int | None = None
    detected_cert_days: int | None = None
    # Low-confidence intent detection (0.2 < confidence < 0.30): awaiting a
    # yes/no confirmation from the user before applying it (Capa 3, typo plan).
    pending_intent_confirmation: object | None = None
    # Free-form facts the customer volunteered in natural language that don't map
    # to a structured field (budget, literal day count, child ages, experience
    # level, preferences like "quieren ir juntos"). Written by the conversation
    # agent's `remember` tool and injected into every RAG/answer context so the
    # bot never re-asks or ignores what the customer already said. Persists for
    # the whole conversation (NOT cleared with the cart).
    remembered_facts: dict | None = None
    # Rolling summary of the conversation so far (Fase B, see
    # docs/archive/memory-context-improvement-plan.md): once `history` grows past the
    # raw window every RAG/orchestrator call actually reads, details mentioned
    # earlier would otherwise be silently unreachable even though they're
    # still stored. `conversation_summary_through` is the index into
    # `history` up to which the summary already accounts for, so updates are
    # incremental (previous summary + only the new segment) instead of
    # re-summarizing the whole conversation every time.
    conversation_summary: str | None = None
    conversation_summary_through: int = 0

    # True once the conversation has entered the DIVE TO HEAL / adaptive-diving
    # topic. Persisted so follow-up questions ("¿cuánto cuesta?", "¿cómo
    # reservo?") that carry no disability keyword are still handled coherently
    # within that context, instead of falling through to the generic price/
    # booking handlers (which would dump generic Cartagena prices and lose the
    # thread). Set in supervisor when _ADAPTIVE_DIVING_PATTERN fires.
    adaptive_diving_context: bool = False

    # Slot the conversational core (src/agents/conversational_core.py) asked for
    # in its last turn, so a short answer ("sí", "no", "2", "cartagena") resolves
    # against it (contextual slot carryover) instead of being unparseable.
    # None when there is no pending slot.
    core_pending_slot: str | None = None

    # Actividad del acompañante detectada por la red de precisión LLM
    # (detect_special_signals) cuando la cantidad quedó pendiente de preguntar
    # (plural sin número, p. ej. "mis amigos" — nunca se debe adivinar cuántos
    # son). Se consume en cuanto la respuesta llega (core_pending_slot ==
    # SLOT_COMPANION_QTY) y se fusiona con `_merge_companion_activity`.
    pending_companion_activity: str | None = None

    # Cola de sub-grupos ADICIONALES (más de un acompañante con actividades
    # distintas en el mismo mensaje, `other_companions` del LLM) cuya cantidad
    # también quedó ambigua (plural vago sin número) — se preguntan uno a uno,
    # igual que `pending_companion_activity` pero para el 2º/3º/... grupo.
    # Auditoría 2026-07-23: mismo hallazgo que motivó pending_companion_activity,
    # extendido a "3 o más actividades, algunas con plural vago".
    pending_companion_queue: list = field(default_factory=list)

    # Auditoría 2026-07-23: un acompañante mencionado solo por un ATRIBUTO
    # ("mi amigo no está certificado") sin actividad ni intención declarada
    # ("quiere bucear"/"quiere snorkel") no da pie a adivinar snorkel o
    # minicurso — dos extractores distintos adivinaban cosas distintas para
    # la MISMA frase ambigua. Marca que hay que preguntar qué actividad
    # quiere ese acompañante (SLOT_COMPANION_ACTIVITY) antes de poder
    # preguntar la cantidad.
    needs_companion_activity: bool = False

    def __post_init__(self):
        if self.history is None:
            self.history = []
        if self.remembered_facts is None:
            self.remembered_facts = {}
