"""
Predefined decision tree for Diving Planet customer interactions.

Phase 1: No LLM required. Handles the most common customer flows
using structured menus and pattern matching. This covers ~80% of
interactions at zero LLM cost.

The tree guides customers through:
1. Language selection (ES/EN)
2. Intent classification (Tours / Courses / Info / Human)
3. Experience level (Certified / Beginner)
4. Service selection with details
5. Booking link generation
"""

import json
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from src.utils.fuzzy import fuzzy_word_number

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
    # Flujo antiguo eliminado - ahora todo va por el carrito (MIXED_*)
    COURSES_MENU = "courses_menu"
    COURSES_OPEN_WATER_ORIGIN = "courses_open_water_origin"
    COURSES_OPEN_WATER_TIME = "courses_open_water_time"
    COURSES_ADVANCED_MENU = "courses_advanced_menu"
    COURSES_SPECIALTIES_MENU = "courses_specialties_menu"
    # Cart-style mixed-group flow
    MIXED_ENTRY = "mixed_entry"
    MIXED_LOCATION = "mixed_location"
    MIXED_ASK_CERTIFICATION = "mixed_ask_certification"
    MIXED_ASK_CERT_COUNT = "mixed_ask_cert_count"
    MIXED_ASK_BEGINNER_ACTIVITY = "mixed_ask_beginner_activity"
    MIXED_ADD_ACTIVITY = "mixed_add_activity"
    MIXED_COMPANION_UPSELL = "mixed_companion_upsell"
    MIXED_ADD_CERT_PLAN = "mixed_add_cert_plan"
    MIXED_ADD_CERT_MULTI_DAY = "mixed_add_cert_multi_day"
    MIXED_ADD_QTY = "mixed_add_qty"
    MIXED_CERT_LAST_DIVE = "mixed_cert_last_dive"
    MIXED_CERT_REFRESH_INTEREST = "mixed_cert_refresh_interest"
    MIXED_CERT_REFRESH_QTY = "mixed_cert_refresh_qty"
    MIXED_CERT_SPLIT_REVIEW = "mixed_cert_split_review"
    MIXED_ADD_PREVIEW = "mixed_add_preview"
    MIXED_CART_REVIEW = "mixed_cart_review"
    MIXED_CART_MODIFY_PICK = "mixed_cart_modify_pick"
    MIXED_CART_REMOVE_PICK = "mixed_cart_remove_pick"
    MIXED_CART_LOCATION = "mixed_cart_location"
    MIXED_FINAL_COLOMBIAN = "mixed_final_colombian"
    MIXED_FINAL_KIDS = "mixed_final_kids"
    MIXED_FINAL_KIDS_QTY = "mixed_final_kids_qty"
    MIXED_FINAL_KIDS_U8 = "mixed_final_kids_u8"
    MIXED_FINAL_KIDS_810 = "mixed_final_kids_810"
    MIXED_FINAL_PRIVATE = "mixed_final_private"
    MIXED_FINAL_SUMMARY = "mixed_final_summary"
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
    mixed_pending_course_question: str | None = None
    mixed_pending_preview_service_id: str | None = None
    mixed_pending_cert_total_qty: int | None = None
    mixed_pending_cert_remaining_qty: int | None = None
    mixed_pending_refresh_added_qty: int | None = None
    # When the group is "some certified, some not": how many non-certified people
    # still need a minicurso added AFTER the certified subgroup is committed.
    mixed_pending_beginner_after_cert: int = 0
    # A companion was mentioned in free text: after location is set, show the
    # mini-course/snorkel upsell for them instead of the generic activity menu.
    mixed_pending_companion_upsell: bool = False
    mixed_pending_modify_idx: int | None = None  # cart index when editing an item
    mixed_pending_modify_refresh: bool = False   # cert qty just changed → re-ask refresher
    # Which 2-option cert sub-menu is currently showing, if any:
    # "4dive_island" (4-dive daytime vs night variant on the islands),
    # "1day" (2 vs 3 dives, both are "1 day" plans),
    # "2day" (4 vs 5 dives, both are "2 day" plans).
    mixed_pending_cert_narrow_kind: str | None = None
    mixed_pending_exact: bool = False            # waiting for exact count after "6+"
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
    # True while the client is being asked for hotel/island after changing the
    # cart's origin to "island" mid-flow (Step.MIXED_CART_LOCATION or the
    # orchestrator's set_location). Tells _handle_island_hotel_menu to remap
    # the existing cart prices and return to the cart review afterward,
    # instead of resuming an add-activity flow that was never pending.
    mixed_pending_location_change: bool = False
    # Intent detection fields - información detectada automáticamente de texto libre
    detected_language: str | None = None
    # Nombre del cliente para el trato cercano (persona Coral). Hoy solo se
    # captura del propio mensaje ("soy Rocío" / "me llamo..."); el de WhatsApp
    # (sender['name']) queda diferido hasta que el canal WhatsApp esté disponible
    # (el widget web no lo da de forma fiable). Ver docs/conversational-refactor-plan.md.
    client_name: str | None = None
    detected_activity: str | None = None
    detected_service_id: str | None = None
    detected_is_certified: bool | None = None
    detected_group_size: int | None = None
    detected_group_allocation: dict | None = None
    detected_ages: list = field(default_factory=list)   # person ages mentioned across the conversation
    mixed_beginner_child_age: int | None = None          # age of the single non-cert minor being offered activities
    mixed_pending_beginner_queue: list = field(default_factory=list)  # per-person ages of non-cert people still to place (auto-build)
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
    # docs/memory-context-improvement-plan.md): once `history` grows past the
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
    # against it (contextual slot carryover) instead of being unparseable. Only
    # used when settings.conversational_core is on; None otherwise.
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


# Common Spanish/English words used to guess the language of ANY free-text
# first message (not just exact greetings), so the bot never re-asks something
# the user already revealed implicitly. Single-letter tokens are intentionally
# excluded (too ambiguous / often punctuation leftovers).
_SPANISH_STOPWORDS = {
    "hola", "buenas", "buenos", "dias", "días", "tardes", "noches", "como",
    "estas", "está", "esta", "que", "pasa", "paso", "quiero", "quisiera",
    "necesito", "somos", "queremos", "tengo", "gracias", "favor", "hacer",
    "puedo", "podemos", "disponible", "disponibilidad", "cuanto", "cuánto",
    "cuesta", "precio", "reservar", "reserva", "informacion", "información",
    "ayuda", "el", "la", "los", "las", "de", "en", "un", "una", "unos",
    "unas", "es", "son", "con", "por", "para", "no", "si", "sí", "mi", "tu",
    "su", "nos", "les", "mas", "más", "pero", "cuando", "donde", "dónde",
    "quien", "quién", "porque", "aqui", "aquí", "alli", "allí", "esto",
    "eso", "esa", "ese", "esos", "esas", "estos", "estas", "yo", "tú",
    "él", "ella", "nosotros", "ustedes", "ellos", "ellas", "te", "me",
    "lo", "nuestro", "vamos", "estamos", "estoy", "tenemos", "podria",
    "podría", "bien", "muy", "todo", "todos", "buceo", "bucear", "buzo",
    "snorkel", "curso", "minicurso", "certificado", "personas", "día",
    "días", "inmersión", "información", "viaje", "isla", "islas",
}

_ENGLISH_STOPWORDS = {
    "hello", "hi", "hey", "welcome", "good", "morning", "afternoon",
    "evening", "want", "wanna", "need", "we", "are", "is", "the", "to",
    "of", "and", "in", "that", "have", "it", "for", "not", "on", "with",
    "as", "you", "do", "at", "this", "but", "his", "from", "they", "say",
    "her", "she", "or", "will", "my", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "just", "him", "know", "take",
    "people", "into", "your", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first",
    "well", "way", "even", "new", "because", "any", "these", "give",
    "day", "most", "us", "please", "thanks", "thank", "book", "booking",
    "price", "cost", "diving", "dive", "snorkel", "course", "certified",
    "beginner", "group", "trip", "island", "islands", "people",
}


def _detect_language_heuristic(message: str) -> str | None:
    """Guess "es"/"en" from common stopwords in ANY free-text message.

    Falls back to None when there's no usable signal (digits-only, emoji-only,
    a single unrecognized word) so the caller can still ask explicitly.
    """
    normalized = " ".join(message.strip().lower().split())
    if not normalized:
        return None
    words = {word.strip(".,!?¡¿:;()[]{}\"'") for word in normalized.split()}
    es_count = len(words & _SPANISH_STOPWORDS)
    en_count = len(words & _ENGLISH_STOPWORDS)
    if es_count > en_count:
        return "es"
    if en_count > es_count:
        return "en"
    return None


def _detect_language_from_text(message: str) -> str | None:
    normalized = " ".join(message.strip().lower().split())
    words = {word.strip(".,!?¡¿:;()[]{}\"'") for word in normalized.split()}

    if normalized in {"en", "english"} or words.intersection({"english", "hello", "hi"}):
        return "en"
    if normalized in {"es", "espanol", "español", "spanish"} or words.intersection({"espanol", "español", "spanish", "hola"}):
        return "es"
    return _detect_language_heuristic(message)


def _join_items(items: list[str] | str | None) -> str:
    if isinstance(items, list):
        return ", ".join(items)
    return items or ""


def _sanitize_includes(items: list[str] | None) -> list[str] | None:
    """Remove DIVE TO HEAL eco-social contribution from includes lists."""
    if not isinstance(items, list):
        return items
    # Filter any language variant containing 'DIVE TO HEAL'
    return [it for it in items if "DIVE TO HEAL" not in it.upper()]


def _format_price(service: dict) -> str:
    price = service.get("price_usd")
    normal = service.get("price_usd_normal")
    note = service.get("price_note")
    def _round_usd_display(v):
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return v
    if price and normal:
        return f"U${_round_usd_display(price)} online / U${_round_usd_display(normal)} normal"
    if price:
        return f"U${_round_usd_display(price)}"
    if note:
        return note
    return "Consultar precio actualizado en la web"


def _format_duration(service: dict, lang: str) -> str:
    days = service.get("duration_days")
    if days == 1:
        return "1 dia" if lang == "es" else "1 day"
    if days:
        return f"{days} dias" if lang == "es" else f"{days} days"
    return "Multi-dia / variable" if lang == "es" else "Multi-day / variable"


def _flight_rule(service: dict, lang: str) -> str:
    requirements = service.get(f"requirements_{lang}", [])
    for requirement in requirements:
        lowered = requirement.lower()
        if "vuelo" in lowered or "flying" in lowered or "fly" in lowered:
            return requirement
    return ""


def _is_contact_only_service(service_id: str | None) -> bool:
    return service_id == "divemaster"


def _resolve_service_booking_url(service: dict, state: "ConversationState") -> str | None:
    """Pick the right booking link for the service's catalog entry given location,
    localized to the conversation language (the catalog stores ?language=es)."""
    if state.location == "island" and service.get("booking_url_island"):
        url = service["booking_url_island"]
    else:
        url = service.get("booking_url")
    if url and state.language == "en":
        url = url.replace("language=es", "language=en")
    return url




def _extra_notes(service: dict, lang: str) -> str:
    parts = []
    description = service.get(f"description_{lang}")
    preparation = service.get(f"preparation_{lang}")
    not_included = service.get(f"not_included_{lang}", [])
    if description:
        parts.append(description)
    if preparation:
        title = "Preparacion: " if lang == "es" else "Preparation: "
        parts.append(title + preparation)
    if lang == "es":
        if "Minicurso" in service.get("name_es", "") and "No necesitas experiencia previa" not in " ".join(parts):
            parts.append("No necesitas experiencia previa.")
        if "Snorkeling" in service.get("name_es", "") and "Actividad de superficie" not in " ".join(parts):
            parts.append("Actividad de superficie ideal para acompañantes o personas que no quieren bucear.")
        if service.get("includes_night_dive") and "quitar la nocturna" not in " ".join(parts):
            parts.append("Si quieres quitar la nocturna, cambiar noches o personalizar el paquete, lo revisamos con un asesor.")
        if any("Hotel/alojamiento" in item for item in not_included) and "alojamiento no esta incluido" not in " ".join(parts):
            parts.append("El alojamiento no esta incluido y se reserva aparte con el hotel.")
    return " ".join(parts)


def _extra_notes_multiline(service: dict, lang: str) -> str:
    lines: list[str] = []
    description = service.get(f"description_{lang}")
    preparation = service.get(f"preparation_{lang}")
    itinerary = service.get(f"itinerary_{lang}", [])
    not_included = service.get(f"not_included_{lang}", [])
    requirements = service.get(f"requirements_{lang}", [])

    if description:
        lines.append(description)

    if preparation:
        title = "Preparacion:" if lang == "es" else "Preparation:"
        lines.append(title)
        lines.append(f"- {preparation}")

    if itinerary:
        title = "Itinerario:" if lang == "es" else "Itinerary:"
        lines.append(title)
        for item in itinerary:
            lines.append(f"- {item}")

    if requirements:
        title = "Requisitos:" if lang == "es" else "Requirements:"
        lines.append(title)
        for item in requirements:
            lines.append(f"- {item}")

    if not_included:
        title = "No incluye:" if lang == "es" else "Not included:"
        lines.append(title)
        for item in not_included:
            lines.append(f"- {item}")

    if lang == "es":
        name_es = service.get("name_es", "")
        if "Minicurso" in name_es and not any("No necesitas experiencia previa" in ln for ln in lines):
            lines.append("No necesitas experiencia previa.")
        if "Snorkeling" in name_es and not any("Actividad de superficie" in ln for ln in lines):
            lines.append("Actividad de superficie ideal para acompañantes o personas que no quieren bucear.")
        if service.get("includes_night_dive") and not any("nocturna" in ln for ln in lines):
            lines.append("Si quieres quitar la nocturna, cambiar noches o personalizar el paquete, lo revisamos con un asesor.")
        if any("Hotel/alojamiento" in item for item in not_included) and not any("alojamiento no esta incluido" in ln for ln in lines):
            lines.append("El alojamiento no esta incluido y se reserva aparte con el hotel.")

    return "\n".join(lines)






def _load_services() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "services.json"
    raw_services = json.loads(path.read_text(encoding="utf-8-sig")).get("services", {})
    services = {}
    for service_id, service in raw_services.items():
        inferred_min_age = service.get("min_age")
        if inferred_min_age is None:
            if service_id == "divemaster":
                inferred_min_age = 18
            elif service_id in {"advanced", "advanced_already_on_island", "rescue"}:
                inferred_min_age = 12
            elif service_id in {"open_water", "open_water_already_on_island"}:
                inferred_min_age = 10
            elif service.get("requires_certification"):
                inferred_min_age = 10
            elif "Minicurso" in service.get("name_es", ""):
                inferred_min_age = 10
            elif "Snorkeling" in service.get("name_es", ""):
                inferred_min_age = 6

        services[service_id] = {
            "name_es": service.get("name_es", service_id),
            "name_en": service.get("name_en", service.get("name_es", service_id)),
            "requires_cert": service.get("requires_certification", False),
            "price": _format_price(service),
            # Precios crudos para poder elegir COP/USD segun el cliente
            "price_usd": service.get("price_usd"),
            "price_usd_normal": service.get("price_usd_normal"),
            "price_cop": service.get("price_cop"),
            "price_cop_normal": service.get("price_cop_normal"),
            "price_note": service.get("price_note"),
            "price_note_es": service.get("price_note_es"),
            "price_note_en": service.get("price_note_en"),
            "duration_es": _format_duration(service, "es"),
            "duration_en": _format_duration(service, "en"),
            "includes_es": _join_items(_sanitize_includes(service.get("included_es"))),
            "includes_en": _join_items(_sanitize_includes(service.get("included_en"))),
            "description_es": service.get("description_es", ""),
            "description_en": service.get("description_en", ""),
            "preparation_es": service.get("preparation_es", ""),
            "preparation_en": service.get("preparation_en", ""),
            "itinerary_es": service.get("itinerary_es", []) or [],
            "itinerary_en": service.get("itinerary_en", []) or [],
            "summary_intro_es": service.get("summary_intro_es", []) or [],
            "summary_intro_en": service.get("summary_intro_en", []) or [],
            "itinerary_overview_es": service.get("itinerary_overview_es", []) or [],
            "itinerary_overview_en": service.get("itinerary_overview_en", []) or [],
            "requirements_es": service.get("requirements_es", []) or [],
            "requirements_en": service.get("requirements_en", []) or [],
            "not_included_es": service.get("not_included_es", []) or [],
            "not_included_en": service.get("not_included_en", []) or [],
            "min_age": inferred_min_age,
            "extra_notes_es": _extra_notes(service, "es"),
            "extra_notes_en": _extra_notes(service, "en"),
            "extra_block_es": _extra_notes_multiline(service, "es"),
            "extra_block_en": _extra_notes_multiline(service, "en"),
            "flight_rule_es": _flight_rule(service, "es"),
            "flight_rule_en": _flight_rule(service, "en"),
            "includes_night_dive": service.get("includes_night_dive", False),
            "web_url": service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url": service.get("booking_url") or service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url_island": "",
            "category": service.get("category"),
            "contact_only": service.get("contact_only", False),
        }
    return services


SERVICES = _load_services()

ISLAND_SERVICE_MAP = {
    "2_dives_1_day": "2_dives_1_day_already_on_island",
    "minicourse": "minicourse_already_on_island",
    "snorkeling": "snorkeling_already_on_island",
    "5_dives_2_days": "5_dives_2_days_already_on_island",
    "7_dives_3_days": "7_dives_3_days_already_on_island",
    "9_dives_4_days": "9_dives_4_days_already_on_island",
    "open_water": "open_water_already_on_island",
    "advanced": "advanced_already_on_island",
    "fish_identification_specialty": "fish_identification_specialty_already_on_island",
    "nitrox_specialty": "nitrox_specialty_already_on_island",
    "naturalist_specialty": "naturalist_specialty_already_on_island",
    "buoyancy_specialty": "buoyancy_specialty_already_on_island",
    "referral": "referral_already_on_island",
}

# Maps service_id (from the info detail card) to the cart activity type used by
# orchestrator_start_activity. Services not listed here (contact_only, referral,
# private) are excluded on purpose — they still escalate.
SERVICE_TO_CART_TYPE: dict[str, str] = {
    # Certified diving plans
    "2_dives_1_day": "cert", "3_dives_1_day": "cert",
    "4_dives_2_days": "cert", "5_dives_2_days": "cert",
    "7_dives_3_days": "cert", "9_dives_4_days": "cert",
    "1_dive_1_day_already_on_island": "cert",
    "2_dives_1_day_already_on_island": "cert",
    "3_dives_1_day_already_on_island": "cert",
    "4_dives_2_days_already_on_island": "cert",
    "4_dives_2_days_mixed_already_on_island": "cert",
    "5_dives_2_days_already_on_island": "cert",
    "7_dives_3_days_already_on_island": "cert",
    "9_dives_4_days_already_on_island": "cert",
    # Beginner / minicourse
    "minicourse": "beginner", "minicourse_already_on_island": "beginner",
    # Snorkel
    "snorkeling": "snorkel", "snorkeling_already_on_island": "snorkel",
    # PADI courses and specialties
    "open_water": "course", "open_water_already_on_island": "course",
    "advanced": "course", "advanced_already_on_island": "course",
    "rescue": "course", "divemaster": "course",
    "nitrox_specialty": "course", "nitrox_specialty_already_on_island": "course",
    "buoyancy_specialty": "course", "buoyancy_specialty_already_on_island": "course",
    "naturalist_specialty": "course", "naturalist_specialty_already_on_island": "course",
    "fish_identification_specialty": "course",
    "fish_identification_specialty_already_on_island": "course",
    "mindful_diving": "course",
}

MULTI_DAY_SERVICES = {
    "4_dives_2_days",
    "5_dives_2_days",
    "7_dives_3_days",
    "9_dives_4_days",
    "4_dives_2_days_already_on_island",
    "4_dives_2_days_mixed_already_on_island",
    "5_dives_2_days_already_on_island",
    "7_dives_3_days_already_on_island",
    "9_dives_4_days_already_on_island",
}

# Above this many people in one line item, nudge toward a human-coordinated
# private/group service instead of silently treating it like a normal small
# group (T123 in docs/test-battery-edge-cases.md). Deliberately does NOT state
# a maximum boat/group capacity (the KB has none — inventing one is forbidden,
# see rag_agent.py's "never invent capacity numbers" rule); it only suggests
# advisor coordination while continuing the flow normally.
LARGE_GROUP_ADVISOR_THRESHOLD = 15

REFRESHER_PRESERVE_SERVICES = {
    "2_dives_1_day",
    "2_dives_1_day_already_on_island",
    "3_dives_1_day",
    "4_dives_2_days",
    "5_dives_2_days",
    "7_dives_3_days",
    "9_dives_4_days",
    "3_dives_1_day_already_on_island",
    "4_dives_2_days_already_on_island",
    "4_dives_2_days_mixed_already_on_island",
    "5_dives_2_days_already_on_island",
    "7_dives_3_days_already_on_island",
    "9_dives_4_days_already_on_island",
}

SPECIALTY_SERVICE_IDS = {
    "mindful_diving",
    "naturalist_specialty",
    "fish_identification_specialty",
    "buoyancy_specialty",
    "nitrox_specialty",
    "fish_identification_specialty_already_on_island",
    "nitrox_specialty_already_on_island",
    "naturalist_specialty_already_on_island",
    "buoyancy_specialty_already_on_island",
}


def _load_companion_price() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "pricing.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"usd_online": 80.44, "usd_normal": 89.38, "cop_online": 288000, "cop_normal": 320000}
    for origin in ("from_cartagena", "from_islands"):
        section = data.get(origin, {}).get("servicios_buceo_snorkel", {})
        comp = section.get("acompanante") if isinstance(section, dict) else None
        if comp:
            return {
                "usd_online": float(comp.get("usd_online", 80.44)),
                "usd_normal": float(comp.get("usd_normal", 89.38)),
                "cop_online": int(comp.get("cop_online", 288000)),
                "cop_normal": int(comp.get("cop_normal", 320000)),
            }
    return {"usd_online": 80.44, "usd_normal": 89.38, "cop_online": 288000, "cop_normal": 320000}


COMPANION_PRICE = _load_companion_price()


# --- Messages templates ---

MESSAGES = {
    "welcome": {
        "es": (
            "¡Hola! Soy *Coral* 🪸 y te doy la bienvenida a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 años de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "Selecciona tu idioma / Select your language:\n\n"
            "🌎 Español\n"
            "🌐 English"
        ),
        "en": (
            "Hi! I'm *Coral* 🪸, welcome to *Diving Planet* — Colombia's first "
            "PADI 5 Star Dive Center, with 30 years of experience in "
            "the Rosario Islands, Cartagena.\n\n"
            "Select your language / Selecciona tu idioma:\n\n"
            "🌎 Español\n"
            "🌐 English"
        ),
    },
    "main_menu": {
        "es": (
            "¡Cuéntame! ¿Qué te gustaría hacer?"
        ),
        "en": (
            "What would you like to do?"
        ),
    },
    "welcome_detected": {
        "es": (
            "¡Hola! Soy *Coral* 🪸 y te doy la bienvenida a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 años de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "¡Cuéntame! ¿Qué te gustaría hacer?"
        ),
        "en": (
            "Hi! I'm *Coral* 🪸, welcome to *Diving Planet* — Colombia's first "
            "PADI 5 Star Dive Center, with 30 years of experience in "
            "the Rosario Islands, Cartagena.\n\n"
            "What would you like to do?"
        ),
    },
    "reserva_menu": {
        "es": (
            "¡Perfecto! Vamos a armar tu reserva *paso a paso* desde el carrito.\n\n"
            "Cuando quieras, empezamos."
        ),
        "en": (
            "Great! Let's build your booking *step by step* from the cart flow.\n\n"
            "Whenever you're ready, let's begin."
        ),
    },
    "info_menu": {
        "es": (
            "¿Qué información te gustaría ver?"
        ),
        "en": (
            "What information do you need?"
        ),
    },
    "info_activity_location": {
        "es": (
            "Para darte información más precisa, ¿desde dónde harías la actividad?"
        ),
        "en": (
            "To share more accurate info, where would you do the activity from?"
        ),
    },
    "info_activities_menu": {
        "es": (
            "🧭 Dentro de actividades, ¿qué te gustaría explorar?"
        ),
        "en": (
            "🧭 Within activities, what would you like to explore?"
        ),
    },
    "info_tours_menu": {
        "es": (
            "Genial, cuéntame qué tipo de plan buscas:\n"
            "Elige la opción que mejor se ajuste."
        ),
        "en": (
            "Great! Tell me what kind of plan you're looking for:\n"
            "Choose the option that fits best."
        ),
    },
    "info_packages_menu": {
        "es": (
            "Perfecto. Dentro de buceo, ¿cómo está compuesto tu grupo?"
        ),
        "en": (
            "Perfect. Within diving, how is your group made up?"
        ),
    },
    "info_courses_menu": {
        "es": (
            "Nuestros cursos PADI en las Islas del Rosario:\n\n"
            "Todos combinan teoria online + practica en las islas."
        ),
        "en": (
            "Our PADI courses in the Rosario Islands:\n\n"
            "All combine online theory + island practice."
        ),
    },
    "info_specialties_menu": {
        "es": (
            "Estas son nuestras especialidades PADI disponibles.\n"
            "Elige una para ver la informacion del servicio."
        ),
        "en": (
            "These are our available PADI specialties.\n"
            "Choose one to see the service information."
        ),
    },
    "info_tours_certified_menu": {
        "es": (
            "Excelente! Estas son nuestras opciones para buzos certificados:\n\n"
            "🏨 *Importante*: si eliges un plan con inmersiones en días distintos, debes hospedarte en un hotel en las islas entre jornadas.\n"
            "- *4 inmersiones (2 días)* y *5 inmersiones (2 días)*: al menos *1 noche*\n"
            "- *7 inmersiones (3 días)*: al menos *2 noches*\n"
            "- *9 inmersiones (4 días)*: al menos *3 noches*\n\n"
            "✳️ *3 inmersiones (1 día)*: también se requiere hospedaje en la isla por la noche, porque incluye inmersión nocturna."
        ),
        "en": (
            "Excellent! Here are our options for certified divers:\n\n"
            "🏨 *Important*: if you choose a plan with dives on different days, you must stay at a hotel on the islands between dive days.\n"
            "- *4 dives (2 days)* and *5 dives (2 days)*: at least *1 night*\n"
            "- *7 dives (3 days)*: at least *2 nights*\n"
            "- *9 dives (4 days)*: at least *3 nights*\n\n"
            "✳️ *3 dives (1 day)*: island accommodation is also required that night because it includes a night dive."
        ),
    },
    "info_courses_advanced_menu": {
        "es": (
            "Estos son nuestros cursos PADI avanzados y profesionales.\n"
            "Elige el que más te interese."
        ),
        "en": (
            "These are our advanced and professional PADI courses.\n"
            "Choose the one you are most interested in."
        ),
    },
    "info_mixed_activity_menu": {
        "es": (
            "Perfecto. Para grupos mixtos *buceo + snorkel* combinamos actividades en un mismo tour.\n\n"
            "¿Sobre qué actividad quieres ver información primero?"
        ),
        "en": (
            "Great. For *diving + snorkeling* mixed groups we combine activities in a single tour.\n\n"
            "Which activity would you like to see information about first?"
        ),
    },
    "info_mixed_cert_beg_menu": {
        "es": (
            "Perfecto. Para grupos mixtos *certificados + principiantes* combinamos actividades en un mismo tour.\n\n"
            "¿Qué parte quieres revisar primero?"
        ),
        "en": (
            "Great. For *certified + beginners* mixed groups we combine activities in a single tour.\n\n"
            "Which part would you like to review first?"
        ),
    },
    "info_certified_4_dives_variant": {
        "es": (
            "Perfecto. Para *4 inmersiones (2 días)* desde las islas, ¿qué opción prefieres?"
        ),
        "en": (
            "Perfect. For *4 dives (2 days)* from the islands, which option would you prefer?"
        ),
    },
    "courses_menu": {
        "es": (
            "Nuestros cursos PADI en las Islas del Rosario:\n\n"
            "Todos combinan teoria online + practica en las islas."
        ),
        "en": (
            "Our PADI courses in the Rosario Islands:\n\n"
            "All combine online theory + island practice."
        ),
    },
    "courses_open_water_origin": {
        "es": (
            "Perfecto, vamos a ver tu curso Open Water.\n\n"
            "Primero, ¿desde dónde harías la parte práctica?"
        ),
        "en": (
            "Great, let's check your Open Water course.\n\n"
            "First, where would you do the practical part?"
        ),
    },
    "courses_open_water_time": {
        "es": (
            "¿Tienes al menos *2 días completos* para hacer la parte práctica del curso?"
        ),
        "en": (
            "Do you have at least *2 full days* for the practical part of the course?"
        ),
    },
    "courses_advanced_menu": {
        "es": (
            "Estos son nuestros cursos PADI avanzados y profesionales.\n"
            "Elige el que más te interese."
        ),
        "en": (
            "These are our advanced and professional PADI courses.\n"
            "Choose the one you are most interested in."
        ),
    },
    "courses_specialties_menu": {
        "es": (
            "Estas son nuestras especialidades PADI disponibles.\n"
            "Elige una para ver la información del servicio."
        ),
        "en": (
            "These are our available PADI specialties.\n"
            "Choose one to see the service information."
        ),
    },
    # ─── Cart-style mixed-group MESSAGES ───
    "mixed_entry": {
        "es": (
            "¡Genial! Vamos a armar tu reserva paso a paso. 🛒\n\n"
            "Puedes añadir varias reservas (buceo certificado, snorkel, minicurso, cursos PADI, acompañantes) "
            "y al final revisamos todo antes de confirmar."
        ),
        "en": (
            "Great! Let's build your booking step by step. 🛒\n\n"
            "You can add several bookings (certified diving, snorkeling, mini-course, PADI courses, companions) "
            "and we'll review everything before you confirm."
        ),
    },
    "mixed_entry_cert_beg": {
        "es": (
            "¡Genial! Vamos a armar tu reserva paso a paso. 🛒\n\n"
            "Puedes añadir varias actividades (buceo certificado, minicurso, acompañantes) "
            "y al final revisamos todo antes de confirmar."
        ),
        "en": (
            "Great! Let's build your booking step by step. 🛒\n\n"
            "You can add several activities (certified diving, mini-course, companions) "
            "and we'll review everything before you confirm."
        ),
    },
    "mixed_location": {
        "es": (
            "Genial 🤿 Para armarlo bien, dime desde dónde saldrías:\n\n"
            "🚤 *Desde Cartagena* — nosotros te llevamos a las Islas del Rosario (ida y vuelta el mismo día).\n"
            "🏝️ *Ya en las islas* — coordinamos la recogida en tu hotel.\n\n"
            "Elige una opción 👇"
        ),
        "en": (
            "Great 🤿 To set it up right, tell me where you'd be departing from:\n\n"
            "🚤 *From Cartagena* — we take you to the Rosario Islands (round trip, same day).\n"
            "🏝️ *Already on the islands* — we arrange pickup at your hotel.\n\n"
            "Pick an option 👇"
        ),
    },
    "mixed_ask_certification": {
        "es": (
            "Perfecto, te ayudo con el buceo. Para continuar necesito saber:\n\n"
            "¿Eres buzo certificado?"
        ),
        "en": (
            "Perfect, I'll help you with diving. To continue I need to know:\n\n"
            "Are you a certified diver?"
        ),
    },
    "mixed_ask_certification_group": {
        "es": (
            "Perfecto, os ayudo con el buceo. Para continuar necesito saber:\n\n"
            "¿Estáis certificados?"
        ),
        "en": (
            "Perfect, I'll help you with diving. To continue I need to know:\n\n"
            "Are you all certified divers?"
        ),
    },
    "mixed_add_activity": {
        "es": "¿Qué actividad quieres *añadir* al carrito?",
        "en": "Which activity would you like to *add* to the cart?",
    },
    "mixed_companion_upsell": {
        "es": (
            "¡Qué bueno que venga acompañante! 🌊 Te recomiendo apuntarle el *minicurso de buceo* "
            "(bautismo con instructor, sin experiencia previa) — es la opción más popular para quien "
            "viene acompañando. Si prefiere *snorkel* o *solo acompañar* sin hacer actividad en el agua, "
            "dímelo y lo ajusto. ¿Te parece?"
        ),
        "en": (
            "Love that a companion is coming along! 🌊 I'd recommend signing them up for the "
            "*dive mini-course* (Discover Scuba with an instructor, no experience needed) — it's the "
            "most popular pick for someone tagging along. If they'd rather *snorkel* or *just accompany* "
            "without any water activity, let me know and I'll adjust it. Sound good?"
        ),
    },
    "mixed_add_cert_plan": {
        "es": (
            "Para *buceo certificado*, ¿qué idea tienes?\n\n"
            "🤿 *2 inmersiones / 1 día*: salida de día completo a las Islas del Rosario con 2 inmersiones guiadas.\n"
            "📅 *Paquete multi-día (3 o más inmersiones)*: varios días seguidos para profundizar tu experiencia. "
            "Requiere dormir en las islas entre jornadas."
        ),
        "en": (
            "For *certified diving*, what do you have in mind?\n\n"
            "🤿 *2 dives / 1 day*: full-day trip to the Rosario Islands with 2 guided dives.\n"
            "📅 *Multi-day package (3 or more dives)*: several consecutive days to deepen your experience. "
            "Requires staying on the islands between dive days."
        ),
    },
    "mixed_add_cert_multi_day": {
        "es": (
            "Para *buceo certificado*, estas son las opciones de *3 o más inmersiones*:\n\n"
            "🏨 *Importante*: si eliges un plan con inmersiones en días distintos, debes hospedarte en un hotel en las islas entre jornadas.\n"
            "- *4 inmersiones (2 días)* y *5 inmersiones (2 días)*: al menos *1 noche*\n"
            "- *7 inmersiones (3 días)*: al menos *2 noches*\n"
            "- *9 inmersiones (4 días)*: al menos *3 noches*\n\n"
            "✳️ *3 inmersiones (1 día)*: también se requiere hospedaje en la isla por la noche, porque incluye inmersión nocturna.\n\n"
            "¿Qué paquete quieres añadir al carrito?"
        ),
        "en": (
            "For *certified diving*, these are the *3 or more dives* options:\n\n"
            "🏨 *Important*: if you choose a plan with dives on different days, you must stay at a hotel on the islands between dive days.\n"
            "- *4 dives (2 days)* and *5 dives (2 days)*: at least *1 night*\n"
            "- *7 dives (3 days)*: at least *2 nights*\n"
            "- *9 dives (4 days)*: at least *3 nights*\n\n"
            "✳️ *3 dives (1 day)*: island accommodation is also required that night because it includes a night dive.\n\n"
            "Which package would you like to add to the cart?"
        ),
    },
    "mixed_add_cert_4dive_variant": {
        "es": "🤿 Para las *4 inmersiones (2 días)*, ¿prefieres 🌞 *4 diurnas* o 🌙 *3 diurnas + 1 nocturna*?",
        "en": "🤿 For the *4-dive (2-day)* plan, would you prefer 🌞 *4 daytime dives* or 🌙 *3 daytime + 1 night dive*?",
    },
    "mixed_add_cert_1day_variant": {
        "es": "🤿 Para el plan de *1 día*, ¿prefieres 🤿 *2 inmersiones* o 🌙 *3 inmersiones (con nocturna)*?",
        "en": "🤿 For the *1-day* plan, would you prefer 🤿 *2 dives* or 🌙 *3 dives (with a night dive)*?",
    },
    "mixed_add_cert_2day_variant": {
        "es": "🤿 Para el plan de *2 días*, ¿prefieres 🤿 *4 inmersiones* o 🤿 *5 inmersiones*?",
        "en": "🤿 For the *2-day* plan, would you prefer 🤿 *4 dives* or 🤿 *5 dives*?",
    },
    "mixed_add_qty": {
        "es": "¿Para *cuántas personas*?",
        "en": "For *how many people*?",
    },
    "mixed_add_preview": {
        "es": "¿Te la *añado a tu reserva*? (al terminar te paso el enlace para reservarla)",
        "en": "Shall I *add it to your booking*? (at the end I'll send you the link to book it)",
    },
    "mixed_cert_last_dive": {
        "es": (
            "¿Han pasado *más de 2 años* desde tu última inmersión?\n\n"
            "Si es así, te recomendamos hacer un *refresher* antes de la salida."
        ),
        "en": (
            "Has it been *more than 2 years* since your last dive?\n\n"
            "If so, we recommend doing a *refresher* before the trip."
        ),
    },
    "mixed_cert_last_dive_group": {
        "es": (
            "¿Ha pasado *más de 2 años* desde la última inmersión de alguno del grupo?\n\n"
            "Si es así, recomendamos un *refresher* antes de la salida."
        ),
        "en": (
            "Has it been *more than 2 years* since any diver in the group last dived?\n\n"
            "If so, we recommend a *refresher* before the trip."
        ),
    },
    "refresher_info": {
        "es": (
            "El *refresher* es una sesión corta de repaso en el agua antes de la inmersión. "
            "Sin coste adicional — el guía adapta el ritmo a tu nivel.\n\n"
            "¿Te interesa el refresher?"
        ),
        "en": (
            "The *refresher* is a short in-water review session before the dive. "
            "No extra cost — the guide adapts the pace to your level.\n\n"
            "Are you interested in the refresher?"
        ),
    },
    "refresher_info_group": {
        "es": (
            "El *refresher* es una sesión corta de repaso en el agua antes de la inmersión. "
            "Sin coste adicional — el guía adapta el ritmo a vuestro nivel.\n\n"
            "¿Os interesa el refresher?"
        ),
        "en": (
            "The *refresher* is a short in-water review session before the dive. "
            "No extra cost — the guide adapts the pace to your group's level.\n\n"
            "Is your group interested in the refresher?"
        ),
    },
    "mixed_cert_refresh_qty": {
        "es": "¿Cuántas de estas personas quieren hacer el *refresher*?\n_(Sin coste adicional — el guía adapta la inmersión a su nivel)_",
        "en": "How many of these people want to do the *refresher*?\n_(No extra cost — the guide adapts the dive to their level)_",
    },
    "mixed_cart_empty": {
        "es": "Tu carrito está vacío. Añade al menos una actividad para continuar.",
        "en": "Your cart is empty. Add at least one activity to continue.",
    },
    "mixed_cart_actions": {
        "es": "¿Cómo quieres continuar?",
        "en": "How would you like to continue?",
    },
    "mixed_cart_modify_pick": {
        "es": "¿Qué *item del carrito* quieres modificar?",
        "en": "Which *cart item* do you want to modify?",
    },
    "mixed_cart_remove_pick": {
        "es": "¿Qué *item del carrito* quieres quitar?",
        "en": "Which *cart item* do you want to remove?",
    },
    "mixed_cart_location": {
        "es": "¿Desde dónde tomarán la salida? Los precios se actualizarán según tu elección.",
        "en": "Where will you depart from? Prices will update according to your choice.",
    },
    "mixed_final_colombian": {
        "es": (
            "Para terminar, ¿eres *colombiano/a o residente en Colombia*?\n"
            "_Es solo para mostrarte el precio en tu moneda: el precio es el mismo, "
            "no hay ningún cobro extra por el cambio de divisa — pesos (COP) o dólares (USD)._"
        ),
        "en": (
            "Last question: are you *Colombian / resident in Colombia*?\n"
            "_It's only to show the price in your currency: the price is the same, "
            "there's no extra charge for the currency — COP or USD._"
        ),
    },
    "mixed_final_kids": {
        "es": (
            "¿Hay *niños menores de 10 años* en el grupo? Dime el rango para planificar bien la actividad:\n\n"
            "• 👶 *Menores de 8 años*: solo pueden hacer *snorkel* (mín. 6 años); no pueden bucear.\n"
            "• 👦 *De 8 a 10 años*: programa *Bubble Makers* — sesión especializada en piscina y mar poco profundo "
            "(máx. 2 m de profundidad) con un instructor dedicado.\n"
            "• 🧑 *Todos 10+*: pueden hacer el minicurso normal sin cambios.\n"
            "• 🧒 *Varios rangos (mezcla)*: te pregunto cuántos hay en cada rango."
        ),
        "en": (
            "Are there any *children under 10* in the group? Tell me the range so I can plan the activity properly:\n\n"
            "• 👶 *Under 8*: snorkeling only (min. 6 years); cannot dive.\n"
            "• 👦 *Ages 8-10*: *Bubble Makers* program — specialized pool + shallow-water session "
            "(max. 2 m depth) with a dedicated instructor.\n"
            "• 🧑 *Everyone 10+*: regular mini-course, no changes.\n"
            "• 🧒 *Multiple ranges (mix)*: I'll ask how many are in each range."
        ),
    },
    "mixed_final_kids_qty": {
        "es": "¿*Cuántos niños* son en ese rango? Esto nos ayuda a desglosar bien la actividad:",
        "en": "*How many kids* in that range? This helps us break down the activity properly:",
    },
    "mixed_kids_age": {
        "es": (
            "¿Hay *niños menores de 10 años* en el grupo? Dime el rango para planificar bien la actividad:\n\n"
            "• 👶 *Menores de 8 años*: solo pueden hacer *snorkel* (mín. 6 años); no pueden bucear.\n"
            "• 👦 *De 8 a 10 años*: programa *Bubble Makers* — sesión especializada en piscina y mar poco profundo "
            "(máx. 2 m de profundidad) con un instructor dedicado.\n"
            "• 🧑 *Todos 10+*: pueden hacer el minicurso normal sin cambios.\n"
            "• 🧒 *Varios rangos (mezcla)*: te pregunto cuántos hay en cada rango."
        ),
        "en": (
            "Are there any *children under 10* in the group? Tell me the range so I can plan the activity properly:\n\n"
            "• 👶 *Under 8*: snorkeling only (min. 6 years); cannot dive.\n"
            "• 👦 *Ages 8-10*: *Bubble Makers* program — specialized pool + shallow-water session "
            "(max. 2 m depth) with a dedicated instructor.\n"
            "• 🧑 *Everyone 10+*: regular mini-course, no changes.\n"
            "• 🧒 *Multiple ranges (mix)*: I'll ask how many are in each range."
        ),
    },
    "mixed_final_kids_u8": {
        "es": "¿Cuántos *menores de 8* hay en el grupo? (no pueden bucear, snorkel desde 6 años)",
        "en": "How many *under 8* are in the group? (cannot dive, snorkel from age 6)",
    },
    "mixed_final_kids_810": {
        "es": "¿Y cuántos *entre 8 y 10*? (Bubble Makers — supervisor especializado)",
        "en": "And how many *between 8 and 10*? (Bubble Makers — specialized supervisor)",
    },
    "mixed_final_private": {
        "es": "¿Os interesa una *lancha privada exclusiva* para el grupo?",
        "en": "Are you interested in an *exclusive private boat* for the group?",
    },
    "mixed_final_summary_actions": {
        "es": "¿Cómo quieres continuar?",
        "en": "How would you like to continue?",
    },
    "pricing_menu": {
        "es": (
            "Sobre que tipo de plan quieres ver *precios y descuentos*?"
        ),
        "en": (
            "What would you like *prices and discounts* for?"
        ),
    },
    "booking_menu": {
        "es": (
            "Te explico como funcionan las *reservas y pagos*.\n"
            "Selecciona lo que mas se acerque a tu duda."
        ),
        "en": (
            "Let me explain how *bookings and payments* work.\n"
            "Choose what matches your question best."
        ),
    },
    "logistics_menu": {
        "es": (
            "Te ayudo con la *logistica* de tu experiencia: horarios, punto de encuentro, "
            "alojamiento, que llevar, clima y cancelaciones.\n"
            "¿Por donde empezamos?"
        ),
        "en": (
            "I can help with the *logistics* of your experience: schedule, meeting point, "
            "accommodation, what to bring, weather and cancellations.\n"
            "Where would you like to start?"
        ),
    },
    "island_menu": {
        "es": (
            "Perfecto, dime en que isla te estas hospedando o vas a hospedarte.\n"
            "Esto nos ayuda a coordinar mejor la recogida y la logistica."
        ),
        "en": (
            "Great, tell me on which island you are staying or will be staying.\n"
            "This helps us coordinate pickup and logistics."
        ),
    },
    "location": {
        "es": (
            "Genial 🤿 Para armarlo bien, dime desde dónde saldrías:\n\n"
            "🚤 *Desde Cartagena* — nosotros te llevamos a las Islas del Rosario (ida y vuelta el mismo día).\n"
            "🏝️ *Ya en las islas* — coordinamos la recogida en tu hotel.\n\n"
            "Elige una opción 👇"
        ),
        "en": (
            "Great 🤿 To set it up right, tell me where you'd be departing from:\n\n"
            "🚤 *From Cartagena* — we take you to the Rosario Islands (round trip, same day).\n"
            "🏝️ *Already on the islands* — we arrange pickup at your hotel.\n\n"
            "Pick an option 👇"
        ),
    },
    "colombian": {
        "es": (
            "🌎 ¿Eres colombiano/a o residente en Colombia? Así te mostramos el precio en pesos o en dólares."
        ),
        "en": (
            "🌎 Are you Colombian or a resident in Colombia? That way we show you the price in COP or USD."
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
    "not_understood": {
        "es": (
            "¡Uy! No te entendí bien 🙈 ¿Puedes elegir una de las opciones de abajo?"
        ),
        "en": (
            "Hmm, I didn't quite get that. Could you pick one of the options below?"
        ),
    },
}

BUTTON_OPTIONS = {
    "welcome": {
        "es": [
            {"title": "🌎 Español", "value": "1"},
            {"title": "🌐 English", "value": "2"},
        ],
        "en": [
            {"title": "🌎 Español", "value": "1"},
            {"title": "🌐 English", "value": "2"},
        ],
    },
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
    "reserva_menu": {
        "es": [
            {"title": "🛒 Empezar reserva paso a paso", "value": "1"},
            {"title": "🔙 Volver al menú principal", "value": "back"},
        ],
        "en": [
            {"title": "🛒 Start booking step by step", "value": "1"},
            {"title": "🔙 Back to main menu", "value": "back"},
        ],
    },
    "info_menu": {
        "es": [
            {"title": "🧭 Actividades y cursos", "value": "1"},
            {"title": "💰 Precios y descuentos", "value": "2"},
            {"title": "💳 Reservas y pago", "value": "3"},
            {"title": "📍 Logística", "value": "4"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🧭 Activities and courses", "value": "1"},
            {"title": "💰 Prices and discounts", "value": "2"},
            {"title": "💳 Bookings and payment", "value": "3"},
            {"title": "📍 Logistics", "value": "4"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_activity_location": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_activities_menu": {
        "es": [
            {"title": "🤿 Tours de buceo / snorkel", "value": "1"},
            {"title": "📘 Cursos PADI y certificaciones", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Diving / snorkel tours", "value": "1"},
            {"title": "📘 PADI courses and certifications", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_tours_menu": {
        "es": [
            {"title": "🤿 Buceo", "value": "1"},
            {"title": "🐠 Snorkel", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Diving", "value": "1"},
            {"title": "🐠 Snorkeling", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_packages_menu": {
        "es": [
            {"title": "🤿 Solo buzos certificados", "value": "1"},
            {"title": "🆕 Solo principiantes", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Only certified divers", "value": "1"},
            {"title": "🆕 Only beginners", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_courses_menu": {
        "es": [
            {"title": "🐠 Descubriendo el buceo (Open Water Diver)", "value": "1"},
            {"title": "🚀 Convierte en pro (Advanced / Rescue / Dive Master)", "value": "2"},
            {"title": "✨ Amplía tus habilidades (Especialidades PADI)", "value": "3"},
            {"title": "Ya empece un curso en otro centro (referral / reactivate)", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🐠 Discover diving (Open Water Diver)", "value": "1"},
            {"title": "🚀 Go pro (Advanced / Rescue / Divemaster)", "value": "2"},
            {"title": "✨ Expand your skills (PADI Specialties)", "value": "3"},
            {"title": "I already started a course elsewhere (referral / reactivate)", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_specialties_menu": {
        "es": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Identificación de peces", "value": "2"},
            {"title": "🌿 Naturalista", "value": "3"},
            {"title": "⚖️ Flotabilidad", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Fish Identification", "value": "2"},
            {"title": "🌿 Naturalist", "value": "3"},
            {"title": "⚖️ Buoyancy", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_tours_certified_menu": {
        "es": [
            {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
            {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
            {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
            {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
            {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
            {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
            {"title": "🧑‍💬 Servicio Privado", "value": "7"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 2 Dives (1 day)", "value": "1"},
            {"title": "🤿 3 Dives (1 day)*", "value": "2"},
            {"title": "🤿 4 Dives (2 days)", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🧑‍💬 Private Service", "value": "7"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_courses_advanced_menu": {
        "es": [
            {"title": "📘 Curso Avanzado", "value": "1"},
            {"title": "🚑 Rescate + EFR", "value": "2"},
            {"title": "🏅 Dive Master", "value": "3"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "📘 Advanced Course", "value": "1"},
            {"title": "🚑 Rescue + EFR", "value": "2"},
            {"title": "🏅 Divemaster", "value": "3"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_mixed_activity_menu": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "🐠 Snorkel", "value": "3"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "🐠 Snorkeling", "value": "3"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_mixed_cert_beg_menu": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_certified_4_dives_variant": {
        "es": [
            {"title": "🤿 4 inmersiones (2 días) · 4 diurnas", "value": "1"},
            {"title": "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 4 Dives (2 days) · 4 daytime dives", "value": "1"},
            {"title": "🤿 4 Dives (2 days) · 3 daytime + 1 night dive", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_detail_actions": {
        "es": [
            {"title": "🤿 Reservar esta opción", "value": "1"},
            {"title": "🗺️ Ver itinerario", "value": "itinerary"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Book this option", "value": "1"},
            {"title": "🗺️ View itinerary", "value": "itinerary"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "tours_location": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "group_type": {
        "es": [
            {"title": "🤿 Buceo", "value": "1"},
            {"title": "🐠 Snorkel", "value": "2"},
            {"title": "👥 Grupo mixto (buceo + snorkel)", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Diving", "value": "1"},
            {"title": "🐠 Snorkeling", "value": "2"},
            {"title": "👥 Mixed group (diving + snorkel)", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "tours_experience": {
        "es": [
            {"title": "🤿 Solo buzos certificados", "value": "1"},
            {"title": "🆕 Solo principiantes", "value": "2"},
            {"title": "👥 Grupo mixto (certificados + principiantes)", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Only certified divers", "value": "1"},
            {"title": "🆕 Only beginners", "value": "2"},
            {"title": "👥 Mixed group (certified + beginners)", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    # ─── Cart-style mixed-group buttons ───
    "mixed_entry": {
        "es": [
            {"title": "🤿 Añadir actividades", "value": "1"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Add activities", "value": "1"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_ask_certification": {
        "es": [
            {"title": "✅ Sí, estoy certificado", "value": "1"},
            {"title": "❌ No, soy principiante", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ Yes, I'm certified", "value": "1"},
            {"title": "❌ No, I'm a beginner", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_ask_certification_group": {
        "es": [
            {"title": "✅ Todos certificados", "value": "1"},
            {"title": "❌ Ninguno certificado", "value": "2"},
            {"title": "⚠️ Algunos sí, otros no", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ All certified", "value": "1"},
            {"title": "❌ None certified", "value": "2"},
            {"title": "⚠️ Some yes, some no", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_activity": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "🐠 Snorkel", "value": "3"},
            {"title": "🤿 Curso PADI", "value": "4"},
            {"title": "👤 Acompañante (sin actividad)", "value": "5"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "🐠 Snorkeling", "value": "3"},
            {"title": "🤿 PADI course", "value": "4"},
            {"title": "👤 Companion (no activity)", "value": "5"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_companion_upsell": {
        "es": [
            {"title": "✅ Perfecto, minicurso", "value": "1"},
            {"title": "🐠 Mejor snorkel", "value": "2"},
            {"title": "👤 No, solo acompañar", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ Perfect, mini-course", "value": "1"},
            {"title": "🐠 Snorkeling instead", "value": "2"},
            {"title": "👤 No, just accompany", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_plan": {
        "es": [
            {"title": "🤿 2 Inmersiones / 1 día", "value": "1"},
            {"title": "📅 Paquete multi-día (3 o más inmersiones)", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 2 Dives / 1 day", "value": "1"},
            {"title": "📅 Multi-day package (3 or more dives)", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_multi_day": {
        "es": [
            {"title": "🤿 3 inmersiones (1 día)*", "value": "1"},
            {"title": "🤿 4 inmersiones (2 días)", "value": "2"},
            {"title": "🤿 5 inmersiones (2 días)", "value": "3"},
            {"title": "🤿 7 inmersiones (3 días)", "value": "4"},
            {"title": "🤿 9 inmersiones (4 días)", "value": "5"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 3 Dives (1 day)*", "value": "1"},
            {"title": "🤿 4 Dives (2 days)", "value": "2"},
            {"title": "🤿 5 Dives (2 days)", "value": "3"},
            {"title": "🤿 7 Dives (3 days)", "value": "4"},
            {"title": "🤿 9 Dives (4 days)", "value": "5"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_4dive_variant": {
        "es": [
            {"title": "🌞 4 diurnas", "value": "1"},
            {"title": "🌙 3 diurnas + 1 nocturna", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🌞 4 daytime dives", "value": "1"},
            {"title": "🌙 3 daytime + 1 night dive", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_1day_variant": {
        "es": [
            {"title": "🤿 2 inmersiones", "value": "1"},
            {"title": "🌙 3 inmersiones (con nocturna)", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 2 dives", "value": "1"},
            {"title": "🌙 3 dives (with a night dive)", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_2day_variant": {
        "es": [
            {"title": "🤿 4 inmersiones", "value": "1"},
            {"title": "🤿 5 inmersiones", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 4 dives", "value": "1"},
            {"title": "🤿 5 dives", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_quantity": {
        "es": [
            {"title": "1", "value": "1"},
            {"title": "2", "value": "2"},
            {"title": "3", "value": "3"},
            {"title": "4", "value": "4"},
            {"title": "5", "value": "5"},
            {"title": "6 o mas", "value": "6+"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "1", "value": "1"},
            {"title": "2", "value": "2"},
            {"title": "3", "value": "3"},
            {"title": "4", "value": "4"},
            {"title": "5", "value": "5"},
            {"title": "6 or more", "value": "6+"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_preview_actions": {
        "es": [
            {"title": "✅ Sí, añadir a mi reserva", "value": "1"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ Yes, add to my booking", "value": "1"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_cert_split_review": {
        "es": [
            {"title": "🎓 Continuar con el buceo", "value": "1"},
            {"title": "❌ Quitar el refresher", "value": "2"},
            {"title": "🔄 Empezar de nuevo", "value": "3"},
        ],
        "en": [
            {"title": "🎓 Continue with diving", "value": "1"},
            {"title": "❌ Remove the refresher", "value": "2"},
            {"title": "🔄 Start over", "value": "3"},
        ],
    },
    "mixed_cert_last_dive": {
        "es": [
            {"title": "Sí", "value": "1"},
            {"title": "No", "value": "2"},
        ],
        "en": [
            {"title": "Yes", "value": "1"},
            {"title": "No", "value": "2"},
        ],
    },
    "refresher_interest": {
        "es": [
            {"title": "✅ Sí, quiero el refresher", "value": "1"},
            {"title": "❌ No, lo saltamos", "value": "2"},
        ],
        "en": [
            {"title": "✅ Yes, I want the refresher", "value": "1"},
            {"title": "❌ No, skip it", "value": "2"},
        ],
    },
    "mixed_yes_no": {
        "es": [
            {"title": "✅ Si", "value": "1"},
            {"title": "❌ No", "value": "2"},
        ],
        "en": [
            {"title": "✅ Yes", "value": "1"},
            {"title": "❌ No", "value": "2"},
        ],
    },
    "mixed_cart_actions": {
        "es": [
            {"title": "📍 Cambiar origen", "value": "1"},
            {"title": "➕ Añadir otra actividad", "value": "2"},
            {"title": "🔧 Modificar item", "value": "3"},
            {"title": "❌ Quitar item", "value": "4"},
            {"title": "🔄 Empezar de nuevo", "value": "5"},
            {"title": "✅ Confirmar carrito", "value": "6"},
        ],
        "en": [
            {"title": "📍 Change origin", "value": "1"},
            {"title": "➕ Add another activity", "value": "2"},
            {"title": "🔧 Modify item", "value": "3"},
            {"title": "❌ Remove item", "value": "4"},
            {"title": "🔄 Start over", "value": "5"},
            {"title": "✅ Confirm cart", "value": "6"},
        ],
    },
    "mixed_final_summary_actions": {
        "es": [
            {"title": "🧑‍💼 Reservar / contactar asesor", "value": "1"},
            {"title": "🔄 Empezar de nuevo", "value": "2"},
            {"title": "💵 Pagar en persona", "value": "3"},
        ],
        "en": [
            {"title": "🧑‍💼 Book / contact advisor", "value": "1"},
            {"title": "🔄 Start over", "value": "2"},
            {"title": "💵 Pay in person", "value": "3"},
        ],
    },
    "mixed_kids_age": {
        "es": [
            {"title": "👶 Hay menores de 8 años", "value": "1"},
            {"title": "👦 De 8 a 10 (Bubble Makers)", "value": "2"},
            {"title": "🧑 Todos tienen 10+ años", "value": "3"},
            {"title": "🧒 Varios rangos (mezcla)", "value": "4"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "👶 Under 8 years old", "value": "1"},
            {"title": "👦 Ages 8-10 (Bubble Makers)", "value": "2"},
            {"title": "🧑 Everyone 10+ years old", "value": "3"},
            {"title": "🧒 Multiple ranges (mix)", "value": "4"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_menu": {
        "es": [
            {"title": "🐠 Descubriendo el buceo (Open Water Diver)", "value": "1"},
            {"title": "🚀 Convierte en pro (Advanced / Rescue / Dive Master)", "value": "2"},
            {"title": "✨ Amplía tus habilidades (Especialidades PADI)", "value": "3"},
            {"title": "Ya empece un curso en otro centro (referral / reactivate)", "value": "4"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🐠 Discover diving (Open Water Diver)", "value": "1"},
            {"title": "🚀 Go pro (Advanced / Rescue / Divemaster)", "value": "2"},
            {"title": "✨ Expand your skills (PADI Specialties)", "value": "3"},
            {"title": "I already started a course elsewhere (referral / reactivate)", "value": "4"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_open_water_origin": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_open_water_time": {
        "es": [
            {"title": "Si, tengo al menos 2 dias completos", "value": "1"},
            {"title": "No estoy seguro / tengo menos tiempo", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "Yes, I have at least 2 full days", "value": "1"},
            {"title": "Not sure / I have less time", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_advanced_menu": {
        "es": [
            {"title": "📘 Curso Avanzado", "value": "1"},
            {"title": "🚑 Rescate + EFR", "value": "2"},
            {"title": "🏅 Dive Master", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "📘 Advanced Course", "value": "1"},
            {"title": "🚑 Rescue + EFR", "value": "2"},
            {"title": "🏅 Divemaster", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_specialties_menu": {
        "es": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Identificación de peces", "value": "2"},
            {"title": "🌿 Naturalista", "value": "3"},
            {"title": "⚖️ Flotabilidad", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Fish Identification", "value": "2"},
            {"title": "🌿 Naturalist", "value": "3"},
            {"title": "⚖️ Buoyancy", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "pricing_menu": {
        "es": [
            {"title": "🚤 Precios saliendo desde Cartagena", "value": "1"},
            {"title": "🏝️ Precios si ya estoy en las islas", "value": "2"},
            {"title": "📦 Paquetes 5/7/9 inmersiones (multi-día)", "value": "3"},
            {"title": "🎁 Descuentos disponibles", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🚤 Prices departing from Cartagena", "value": "1"},
            {"title": "🏝️ Prices if I'm already on the islands", "value": "2"},
            {"title": "📦 5/7/9-dive multi-day packages", "value": "3"},
            {"title": "🎁 Available discounts", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "pricing_leaf": {
        "es": [
            {"title": "🤿 Reservar", "value": "reserve"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Book", "value": "reserve"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "booking_menu": {
        "es": [
            {"title": "💳 Pagar todo online", "value": "1"},
            {"title": "🤝 Pagar 50% ahora y 50% después", "value": "2"},
            {"title": "💰 Formas de pago (tarjeta / transferencia)", "value": "3"},
            {"title": "👥 Reservas de grupo o agencia", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "💳 Pay everything online", "value": "1"},
            {"title": "🤝 Pay 50% now and 50% later", "value": "2"},
            {"title": "💰 Payment methods (card / transfer)", "value": "3"},
            {"title": "👥 Group or agency bookings", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "logistics_menu": {
        "es": [
            {"title": "📍 Punto de encuentro y horarios", "value": "1"},
            {"title": "🏨 Alojamiento en islas y recogida en hotel", "value": "2"},
            {"title": "✅ Qué incluye / qué no incluye el plan", "value": "3"},
            {"title": "🎒 Qué llevar y recomendaciones", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "📍 Meeting point and schedule", "value": "1"},
            {"title": "🏨 Accommodation on the islands & hotel pickup", "value": "2"},
            {"title": "✅ What's included / not included", "value": "3"},
            {"title": "🎒 What to bring & recommendations", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "logistics_leaf": {
        "es": [
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "island_menu": {
        "es": [
            {"title": "Isla Grande", "value": "1"},
            {"title": "Isla Marina", "value": "2"},
            {"title": "Isla del Pirata", "value": "3"},
            {"title": "Isla del Sol", "value": "4"},
            {"title": "Isleta", "value": "5"},
            {"title": "Isla Arena", "value": "6"},
            {"title": "Isla Pavitos", "value": "7"},
            {"title": "Isla Lizamar", "value": "8"},
            {"title": "Isla Gigi", "value": "9"},
            {"title": "Isla Rosa", "value": "10"},
            {"title": "Isla Pelicano", "value": "11"},
            {"title": "Isla Rosario", "value": "12"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "Isla Grande", "value": "1"},
            {"title": "Isla Marina", "value": "2"},
            {"title": "Isla del Pirata", "value": "3"},
            {"title": "Isla del Sol", "value": "4"},
            {"title": "Isleta", "value": "5"},
            {"title": "Isla Arena", "value": "6"},
            {"title": "Isla Pavitos", "value": "7"},
            {"title": "Isla Lizamar", "value": "8"},
            {"title": "Isla Gigi", "value": "9"},
            {"title": "Isla Rosa", "value": "10"},
            {"title": "Isla Pelicano", "value": "11"},
            {"title": "Isla Rosario", "value": "12"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "location": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
        ],
    },
    "colombian": {
        "es": [
            {"title": "Si", "value": "1"},
            {"title": "No", "value": "2"},
        ],
        "en": [
            {"title": "Yes", "value": "1"},
            {"title": "No", "value": "2"},
        ],
    },
    "summary": {
        "es": [
            {"title": "❓ Sí, tengo más preguntas", "value": "ask"},
            {"title": "💵 Pagar en persona", "value": "cash"},
            {"title": "🔙 Volver al menú", "value": "back"},
        ],
        "en": [
            {"title": "❓ Yes, I have more questions", "value": "ask"},
            {"title": "💵 Pay in person", "value": "cash"},
            {"title": "🔙 Back to menu", "value": "back"},
        ],
    },
    "summary_referral": {
        "es": [
            {"title": "🧑‍💼 Contactar/Reservar", "value": "contact"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🧑‍💼 Contact / Book", "value": "contact"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "summary_contact": {
        "es": [
            {"title": "🧑‍💼 Contactar/Reservar", "value": "contact"},
            {"title": "❓ Tengo mas preguntas", "value": "ask"},
            {"title": "🙏 No, gracias", "value": "done"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🧑‍💼 Contact / Book", "value": "contact"},
            {"title": "❓ I have more questions", "value": "ask"},
            {"title": "🙏 No, thanks", "value": "done"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "itinerary_offer": {
        "es": [
            {"title": "🗺️ Ver itinerario completo", "value": "itinerary"},
            {"title": "💵 Pagar en persona", "value": "cash"},
            {"title": "🔙 Volver al menú", "value": "back"},
        ],
        "en": [
            {"title": "🗺️ View full itinerary", "value": "itinerary"},
            {"title": "💵 Pay in person", "value": "cash"},
            {"title": "🔙 Back to menu", "value": "back"},
        ],
    },
    "itinerary_offer_contact": {
        "es": [
            {"title": "🗺️ Ver itinerario completo", "value": "itinerary"},
            {"title": "🧑‍💼 Contactar/Reservar", "value": "contact"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🗺️ View full itinerary", "value": "itinerary"},
            {"title": "🧑‍💼 Contact / Book", "value": "contact"},
            {"title": "🔙 Back", "value": "back"},
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
        if key == "tours_certified" and state.location == "island":
            options = self._island_certified_options(state.language)
        elif key == "info_tours_certified_menu" and state.location == "island":
            options = self._info_island_certified_options(state.language)
        elif key == "mixed_add_cert_multi_day" and state.location == "island":
            options = self._mixed_island_certified_multiday_options(state.language)
        elif key == "mixed_add_activity" and state.mixed_entry_path == "cert_beg":
            # Filtramos snorkel cuando entran por la rama de certificados + principiantes.
            options = [
                opt for opt in get_button_options(key, state.language)
                if opt.get("value") != "3"
            ]
        else:
            options = get_button_options(key, state.language)
        if key in self._CART_MENU_KEYS:
            options = [o for o in options if o.get("value") != "back"]
        state.quick_replies = options

    @staticmethod
    def _info_island_certified_options(lang: str) -> list[dict]:
        if lang == "es":
            options = [
                {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
                {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
                {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
                {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
                {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
                {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
                {"title": "🧑‍💬 Servicio Privado", "value": "7"},
                {"title": "⬅️ Volver", "value": "back"},
                {"title": "🏠 Inicio", "value": "inicio"},
            ]
        else:
            options = [
                {"title": "🤿 2 Dives (1 day)", "value": "1"},
                {"title": "🤿 3 Dives (1 day)*", "value": "2"},
                {"title": "🤿 4 Dives (2 days)", "value": "3"},
                {"title": "🤿 5 Dives (2 days)", "value": "4"},
                {"title": "🤿 7 Dives (3 days)", "value": "5"},
                {"title": "🤿 9 Dives (4 days)", "value": "6"},
                {"title": "🧑‍💬 Private Service", "value": "7"},
                {"title": "⬅️ Back", "value": "back"},
                {"title": "🏠 Home", "value": "inicio"},
            ]
        return [ButtonOption(title=option["title"], value=option["value"]).as_chatwoot_item() for option in options]


    def _service_for_location(self, service_id: str, state: ConversationState) -> str:
        if state.location == "island":
            return ISLAND_SERVICE_MAP.get(service_id, service_id)
        return service_id

    def _island_certified_options(self, lang: str) -> list[dict]:
        if lang == "es":
            return [
                {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
                {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
                {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
                {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
                {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
                {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
                {"title": "🧑‍💬 Servicio Privado", "value": "7"},
                {"title": "🔙 Volver", "value": "back"},
            ]
        return [
            {"title": "🤿 2 Dives (1 day)", "value": "1"},
            {"title": "🤿 3 Dives (1 day)*", "value": "2"},
            {"title": "🤿 4 Dives (2 days)", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🧑‍💬 Private Service", "value": "7"},
            {"title": "🔙 Back", "value": "back"},
        ]

    def _mixed_island_certified_multiday_options(self, lang: str) -> list[dict]:
        if lang == "es":
            return [
                {"title": "🤿 3 inmersiones (1 día)*", "value": "1"},
                {"title": "🤿 4 inmersiones (2 días) · 4 diurnas", "value": "2"},
                {"title": "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna", "value": "3"},
                {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
                {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
                {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
                {"title": "🔙 Volver", "value": "back"},
            ]
        return [
            {"title": "🤿 3 Dives (1 day)*", "value": "1"},
            {"title": "🤿 4 Dives (2 days) · 4 daytime dives", "value": "2"},
            {"title": "🤿 4 Dives (2 days) · 3 daytime + 1 night dive", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🔙 Back", "value": "back"},
        ]

    # ───────────────────── Cart-style mixed group flow ─────────────────────


    def _cart_label_for(self, item_type: str, plan: str | None, lang: str) -> str:
        """Human-readable label for a cart item."""
        if item_type == "cert":
            service = SERVICES.get(plan) or {}
            label = service.get(f"name_{lang}") or service.get("name_es")
            if label:
                return label
            if lang == "es":
                return "Salidas de Buceo - 2 inmersiones (1 día)" if plan == "2_dives_1_day" else "Buceo certificado"
            return "Fun Dives - 2 dives (1 day)" if plan == "2_dives_1_day" else "Certified diving"
        if item_type == "beginner":
            return "Buceo principiantes (Minicurso)" if lang == "es" else "Beginner diving (Mini-course)"
        if item_type == "refresh":
            return "Refresher para certificados" if lang == "es" else "Certified diver refresher"
        if item_type == "snorkel":
            return "Snorkel" if lang == "es" else "Snorkeling"
        if item_type == "course":
            service = SERVICES.get(plan) or {}
            return service.get(f"name_{lang}") or service.get("name_es") or ("Curso PADI" if lang == "es" else "PADI course")
        if item_type == "companion":
            return "Acompañante (sin actividad)" if lang == "es" else "Companion (no activity)"
        return item_type

    def _cart_service_id(self, item_type: str, plan: str | None, state: ConversationState) -> str | None:
        """Map a cart item to the catalog service ID (for prices and booking URLs)."""
        if item_type == "cert":
            return plan or self._service_for_location("2_dives_1_day", state)
        if item_type == "beginner":
            return self._service_for_location("minicourse", state)
        if item_type == "refresh":
            return self._service_for_location("minicourse", state)
        if item_type == "snorkel":
            return self._service_for_location("snorkeling", state)
        if item_type == "course":
            return plan
        return None  # companion has its own pricing from pricing.json





    def _append_mixed_cart_item(self, state: ConversationState, item_type: str, plan: str | None, qty: int) -> None:
        if qty <= 0:
            return
        lang = state.language
        label = self._cart_label_for(item_type, plan, lang)
        existing = next(
            (it for it in state.mixed_cart if it["type"] == item_type and it.get("plan") == plan),
            None,
        )
        if existing is not None:
            existing["qty"] += qty
            existing["label"] = label
            return
        state.mixed_cart.append({
            "type": item_type,
            "qty": qty,
            "plan": plan,
            "label": label,
        })
        # NOTE: kids info is now collected INLINE before append (in
        # `_handle_mixed_add_qty` for the beginner branch), so we do NOT
        # invalidate here — that would wipe the answer the user just gave.
        # Invalidation lives in the add/modify entry handlers instead.



    def _parse_mixed_quantity(self, message: str) -> int | None:
        import re as _re
        msg = " ".join(message.strip().lower().split())
        if msg in {"6+", "6 o mas", "6 o más", "6 or more", "more"}:
            return 6
        try:
            n = int(msg)
            if 1 <= n <= 99:
                return n
        except ValueError:
            pass
        # Accept word numbers (with typo tolerance via fuzzy helper)
        _word_num = {
            'uno': 1, 'una': 1, 'one': 1,
            'dos': 2, 'two': 2,
            'tres': 3, 'three': 3,
            'cuatro': 4, 'four': 4,
            'cinco': 5, 'five': 5,
            'seis': 6, 'six': 6,
            'siete': 7, 'seven': 7,
            'ocho': 8, 'eight': 8,
            'nueve': 9, 'nine': 9,
            'diez': 10, 'ten': 10,
        }
        _fuzzy_n = fuzzy_word_number(msg)
        if _fuzzy_n is not None:
            return _fuzzy_n
        # Extract number from phrases like "somos 3", "vamos 2", "3 personas", "we are 4"
        m = _re.search(r'\b(\d+)\b', msg)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 99:
                return n
        # Extract word number from phrase — exact match first, then fuzzy per token
        for word, val in _word_num.items():
            if _re.search(rf'\b{word}\b', msg):
                return val
        for token in msg.split():
            _n = fuzzy_word_number(token)
            if _n is not None:
                return _n
        # "Self + companion" phrasings with no explicit number → 2 people.
        # e.g. "yo y mi pareja", "voy yo y mi novia", "vengo con mi amiga",
        # "mi hijo y yo", "me acompaña mi esposo". Fixes the qty step answering
        # "no te entendí" to a perfectly clear two-person answer. "familia" is
        # excluded on purpose (its size is unknown — don't guess 2).
        _norm = "".join(
            c for c in unicodedata.normalize("NFD", msg) if unicodedata.category(c) != "Mn"
        )
        _comp = r"(?:pareja|novi[oa]|espos[oa]|amig[oa]|herman[oa]|hij[oa]|mama|papa|acompanante)"
        _self_companion = [
            rf"\byo\s+y\s+mi\s+{_comp}",
            rf"\bmi\s+{_comp}\s+y\s+yo\b",
            rf"\b(?:vengo|voy|vamos|venimos)\s+con\s+mi\s+{_comp}",
            rf"\bcon\s+mi\s+{_comp}\b",
            rf"\bme\s+acompana\s+mi\s+{_comp}",
            rf"\bmi\s+{_comp}\s+me\s+acompana",
        ]
        if any(_re.search(p, _norm) for p in _self_companion):
            return 2
        return None

    # ─── Step handlers ───



    # Emojis numéricos para listas dinámicas (botones de modificar/quitar item)
    _NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


    # ─── Cambiar origen desde el carrito ───


    # ─── Final-question handlers ───

    def _cart_booking_blocks(self, state: ConversationState) -> list[dict]:
        """One block per bookable activity in the cart (kids split into their real
        activity by age), each with price + booking URL — for the per-activity
        summary + link that closes the flow."""
        lang = state.language
        blocks: list[dict] = []

        def add(svc: dict, qty: int, label: str, url: str | None, note: str | None = None, kind: str = "day"):
            blocks.append({
                "label": label, "qty": qty,
                "usd": svc.get("price_usd"), "cop": svc.get("price_cop"), "url": url,
                "note": note, "kind": kind,
            })

        for item in state.mixed_cart:
            qty = item.get("qty", 0)
            it = item.get("type")
            if it == "refresh" or qty <= 0:
                continue
            if it == "beginner":
                beg = SERVICES.get(self._cart_service_id("beginner", None, state)) or {}
                beg_name = beg.get(f"name_{lang}") or ("Minicurso de Buceo" if lang == "es" else "Dive Mini-Course")
                beg_url = _resolve_service_booking_url(beg, state)
                u8 = min(state.kids_under_8_count or 0, qty)
                e10 = min(state.kids_eight_to_ten_count or 0, max(0, qty - u8))
                if u8 > 0 or e10 > 0:
                    adult = max(0, qty - u8 - e10)
                    if adult > 0:
                        add(beg, adult, beg_name, beg_url)
                    if u8 > 0:
                        snk = SERVICES.get(self._service_for_location("snorkeling", state)) or {}
                        nm = (snk.get(f"name_{lang}") or "Snorkel") + (" [menores de 8]" if lang == "es" else " [under 8]")
                        u8_note = (
                            "_Los menores de 8 no pueden bucear; hacen snorkel (desde 6 años)._"
                            if lang == "es"
                            else "_Under 8 cannot dive; they snorkel instead (from age 6)._"
                        )
                        add(snk, u8, nm, _resolve_service_booking_url(snk, state), u8_note)
                    if e10 > 0:
                        e10_note = (
                            "_Programa Bubble Makers (8-10 años), con supervisor especializado._"
                            if lang == "es"
                            else "_Bubble Makers program (ages 8-10), with a specialized supervisor._"
                        )
                        add(beg, e10, beg_name + " [Bubble Makers]", beg_url, e10_note)
                    continue
                add(beg, qty, beg_name, beg_url)
                continue
            if it == "companion":
                blocks.append({
                    "label": self._cart_label_for(it, None, lang), "qty": qty,
                    "usd": COMPANION_PRICE.get("usd_online"), "cop": COMPANION_PRICE.get("cop_online"), "url": None,
                    "note": None, "kind": "day",
                })
                continue
            svc_id = self._cart_service_id(it, item.get("plan"), state)
            svc = SERVICES.get(svc_id) or {}
            label = svc.get(f"name_{lang}") or item.get("label") or self._cart_label_for(it, item.get("plan"), lang)
            url = None if _is_contact_only_service(svc_id) else _resolve_service_booking_url(svc, state)
            add(svc, qty, label, url, kind=("course" if it == "course" else "day"))
        return blocks

    def _format_activity_booking_messages(self, state: ConversationState) -> list[str]:
        """One message per cart activity: summary + price + '👉 click here' + link.
        Sent as separate WhatsApp messages (joined with MESSAGE_SPLIT upstream)."""
        lang = state.language
        primary = state.mixed_display_currency

        def money(usd, cop, qty=1):
            # Round the per-person price first, then multiply, so the arithmetic
            # shown to the client always adds up (e.g. "2 × $126 = $252", never $251).
            if primary == "COP":
                return f"COP {int(round(cop or 0)) * qty:,}".replace(",", ".") if cop else None
            return f"${int(round(float(usd))) * qty} USD" if usd else None

        includes = (
            "✅ Incluye: transporte Cartagena-Islas-Cartagena, almuerzo, equipo y seguro."
            if lang == "es"
            else "✅ Includes: Cartagena-Islands transport, lunch, gear and insurance."
        )
        if state.location == "island":
            includes = (
                "✅ Incluye: equipo, seguro y acompañamiento de un profesional PADI (sin transporte desde Cartagena ni almuerzo)."
                if lang == "es"
                else "✅ Includes: gear, insurance and a PADI professional (no Cartagena transport or lunch)."
            )
        depart = (
            ("📍 Salida desde Cartagena (Muelle de la Bodeguita, 8:00 a.m.)." if lang == "es"
             else "📍 Departure from Cartagena (Muelle de la Bodeguita, 8:00 a.m.).")
            if state.location != "island"
            else ("📍 Recogida en tu hotel de las islas." if lang == "es" else "📍 Pickup at your island hotel.")
        )
        cta = ("👉 *Para más información y hacer tu reserva, haz clic aquí:*"
               if lang == "es" else "👉 *For more information and to book, click here:*")
        info_cta = ("ℹ️ Más información aquí:" if lang == "es" else "ℹ️ More information here:")
        wa = ("👉 Para reservar esto, dime y te paso con un asesor que coordina los detalles contigo."
              if lang == "es" else "👉 To book this, let me know and I'll connect you with an advisor who arranges the details with you.")

        msgs: list[str] = []
        for b in self._cart_booking_blocks(state):
            qty = b["qty"]
            url = b["url"]
            # A direct booking checkout ("book.divingplanet.org") lets the client
            # pay online; a plain divingplanet.org page is info-only → book via WhatsApp.
            direct = bool(url) and "book.divingplanet.org" in url
            online = (" (reservando online)" if lang == "es" else " (online rate)") if direct else ""
            lines = [f"🤿 *{b['label']}*"]
            pp = money(b["usd"], b["cop"])
            if pp:
                if qty > 1:
                    sub = money(b["usd"], b["cop"], qty)
                    lines.append(f"💰 {qty} × {pp} p.p. = *{sub}*{online}")
                else:
                    lines.append(
                        f"💰 *{pp}* por persona{online}" if lang == "es"
                        else f"💰 *{pp}* per person{online}"
                    )
            if b.get("kind") == "course":
                # Multi-day PADI courses aren't the standard 8 a.m. day-tour: dates,
                # sessions and logistics are arranged with you, so skip the day-tour
                # "includes / 8 a.m. departure" boilerplate.
                lines.append(
                    "📚 Curso PADI: las fechas, sesiones y detalles se coordinan contigo."
                    if lang == "es"
                    else "📚 PADI course: dates, sessions and details are arranged with you."
                )
            else:
                lines.append(includes)
                lines.append(depart)
            if b.get("note"):
                lines.append(b["note"])
            lines.append("")
            if direct:
                lines.extend([cta, url])
            elif url:
                lines.extend([info_cta, url, "", wa])
            else:
                lines.append(wa)
            msgs.append("\n".join(lines))
        return msgs


    def _goto_mixed_final_summary(self, state: ConversationState) -> str:
        """Close the flow with ONE message per activity: summary + price + the
        booking link for that activity's web page (no cart/itinerary/payment
        buttons). Multiple activities → multiple separate messages."""
        lang = state.language
        msgs = self._format_activity_booking_messages(state)
        state.quick_replies = []
        state.pending_lead_note_reason = "grupo mixto - resumen por actividad + links de reserva enviados"
        if not msgs:
            state.step = Step.ESCALATE
            state.pending_escalation_reason = "grupo mixto - cierre de reserva sin link directo"
            return (
                "¡Perfecto! Te paso con un asesor para cerrar los detalles de tu reserva. 🌊"
                if lang == "es"
                else "Perfect! I'll connect you with an advisor to finalize your booking. 🌊"
            )
        state.step = Step.FREE_TEXT
        # Keep a plain-text copy for the lead note / extra_context.
        state.mixed_last_summary = "\n\n———\n\n".join(msgs)
        # Cierre profesional tras los links (pedido del owner 2026-07-23): en vez
        # de una despedida pasiva, una PREGUNTA cálida que invita a seguir —
        # añadir otra actividad, resolver dudas o ajustar la reserva. Con varias
        # actividades es un único cierre al final de todos los mensajes (no uno
        # por actividad). Sin precios/links aquí: van en los `msgs` de arriba.
        closing = (
            "\n\n_El precio es el mismo en pesos (COP) o dólares (USD), sin cobro extra por la divisa._"
            "\n\n¿Te ayudo con algo más? Puedo *añadir otra actividad*, resolver dudas o "
            "ajustar la reserva. 🤿"
            if lang == "es"
            else "\n\n_The price is the same in COP or USD, with no extra charge for the currency._"
            "\n\nIs there anything else I can help you with? I can *add another activity*, "
            "answer questions, or adjust your booking. 🤿"
        )
        return MESSAGE_SPLIT.join(msgs) + closing





























