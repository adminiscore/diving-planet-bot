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
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from src.flows import eligibility
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


def _format_price_from(service: dict, lang: str) -> str:
    price = service.get("price_usd")
    note = service.get("price_note")

    def _round_usd_display(v):
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return v

    if price:
        return f"${_round_usd_display(price)} USD (online)"
    if note:
        return note
    if lang == "es":
        return "Consultar en la web"
    return "Check the website"


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


def _accommodation_requirement_note(service_id: str | None, service: dict, lang: str) -> str:
    if service_id in {"3_dives_1_day", "3_dives_1_day_already_on_island"}:
        if lang == "es":
            return "🏨 *Hospedaje requerido*: para este tour debes hospedarte en la isla por la noche, porque incluye inmersión nocturna."
        return "🏨 *Accommodation required*: for this tour you need to stay on the island that night because it includes a night dive."

    days = service.get("duration_days")
    if isinstance(days, int) and days > 1:
        nights = days - 1
        if lang == "es":
            night_label = "noche" if nights == 1 else "noches"
            return f"🏨 *Hospedaje requerido*: para este plan debes alojarte en un hotel en las islas al menos *{nights} {night_label}* entre jornadas de inmersión."
        night_label = "night" if nights == 1 else "nights"
        return f"🏨 *Accommodation required*: for this plan you must stay at a hotel on the islands for at least *{nights} {night_label}* between dive days."

    return ""


def _is_contact_only_service(service_id: str | None) -> bool:
    return service_id == "divemaster"


def _divemaster_itinerary_offer_prompt(lang: str) -> str:
    if lang == "es":
        return "¿Quieres ver el itinerario completo o prefieres contactar con nuestro jefe para solicitar el curso de Dive Master?"
    return "Would you like to see the full itinerary or would you prefer to contact our manager to request the Dive Master course?"






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


def _is_padi_course_service(service_id: str | None) -> bool:
    service = SERVICES.get(service_id)
    return bool(service and service.get("category") == "course")


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


    def resolve_back_target(self, state: ConversationState) -> tuple[Step, str] | None:
        if state.step in {
            Step.SUMMARY,
            Step.INFO_TOUR_DETAIL,
            Step.INFO_PACKAGE_DETAIL,
            Step.INFO_COURSE_DETAIL,
            Step.INFO_SPECIALTY_DETAIL,
        } and state.back_step_override and state.back_quick_replies_key:
            return state.back_step_override, state.back_quick_replies_key
        return None




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

    def _mixed_cert_multi_day_service_map(self, state: ConversationState) -> dict[int, str]:
        if state.location == "island":
            return {
                1: "3_dives_1_day_already_on_island",
                2: "4_dives_2_days_already_on_island",
                3: "4_dives_2_days_mixed_already_on_island",
                4: "5_dives_2_days_already_on_island",
                5: "7_dives_3_days_already_on_island",
                6: "9_dives_4_days_already_on_island",
            }
        return {
            1: "3_dives_1_day",
            2: "4_dives_2_days",
            3: "5_dives_2_days",
            4: "7_dives_3_days",
            5: "9_dives_4_days",
        }

    def _current_mixed_cert_service_id(self, state: ConversationState) -> str:
        return state.mixed_pending_qty_plan or self._service_for_location("2_dives_1_day", state)

    def _cert_dives_to_multiday_choice(self, dives: int, state: ConversationState) -> int | None:
        """Multi-day menu button index for an explicit dive count, or None if the
        count doesn't map to a single unambiguous plan. The only ambiguous case is
        4 dives while already on the islands: two variants exist there (all-daytime
        vs 3 daytime + 1 night dive), so that one must still go through the menu."""
        if state.location == "island":
            if dives == 4:
                return None
            return {3: 1, 5: 4, 7: 5, 9: 6}.get(dives)
        return {3: 1, 4: 2, 5: 3, 7: 4, 9: 5}.get(dives)

    @staticmethod
    def _mixed_cert_lodging_note(dives: int, lang: str) -> str:
        nights = {3: 1, 4: 1, 5: 1, 7: 2, 9: 3}[dives]
        days = {3: 1, 4: 2, 5: 2, 7: 3, 9: 4}[dives]
        if lang == "es":
            night_word = "noche" if nights == 1 else "noches"
            if dives == 3:
                return (
                    "🏨 *Importante*: el plan de *3 inmersiones (1 día)* incluye una inmersión "
                    "nocturna, así que también requiere hospedarte esa noche en un hotel en las islas."
                )
            return (
                f"🏨 *Importante*: el plan de *{dives} inmersiones ({days} días)* requiere hospedarte "
                f"al menos *{nights} {night_word}* en un hotel en las islas entre jornadas."
            )
        night_word = "night" if nights == 1 else "nights"
        if dives == 3:
            return (
                "🏨 *Important*: the *3-dive (1-day)* plan includes a night dive, so it also "
                "requires staying that night at a hotel on the islands."
            )
        return (
            f"🏨 *Important*: the *{dives}-dive ({days}-day)* plan requires staying at least "
            f"*{nights} {night_word}* at a hotel on the islands between dive days."
        )



    @staticmethod
    def _truncate_text(text: str, max_len: int) -> str:
        cleaned = " ".join((text or "").strip().split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 1].rstrip() + "…"

    def _format_info_card(self, state: ConversationState, compact: bool = False) -> str:
        service = SERVICES.get(state.selected_service)
        if not service:
            return MESSAGES["not_understood"][state.language]

        lang = state.language
        name = service.get(f"name_{lang}") or service.get("name_es") or state.selected_service
        category = service.get("category")
        requires_cert = bool(service.get("requires_cert"))
        duration = service.get(f"duration_{lang}") or ""
        web_url = service.get("web_url") or "https://divingplanet.org/contacto/"
        description = service.get(f"description_{lang}") or ""

        if lang == "es":
            if requires_cert:
                audience = "Buzos certificados (Open Water o equivalente)."
            else:
                audience = "Principiantes (no necesitas experiencia previa)."
            if category == "course":
                audience = "Personas que quieren certificarse o seguir avanzando en PADI."
        else:
            if requires_cert:
                audience = "Certified divers (Open Water or equivalent)."
            else:
                audience = "Beginners (no previous experience needed)."
            if category == "course":
                audience = "People who want to get certified or continue advancing with PADI."

        includes_raw = service.get(f"includes_{lang}") or ""
        includes_items = [it.strip() for it in includes_raw.split(",") if it.strip()]
        includes_items = includes_items[:4]
        includes_lines = "\n".join(it for it in includes_items) if includes_items else ""

        not_included = service.get("not_included_es" if lang == "es" else "not_included_en", []) or []
        not_included_items = [it.strip() for it in not_included if isinstance(it, str) and it.strip()]
        not_included_items = not_included_items[:3]
        not_included_lines = "\n".join(it for it in not_included_items) if not_included_items else ""

        price_from = _format_price_from(service, lang)
        min_age = service.get("min_age")

        if lang == "es":
            lines: list[str] = []
            lines.append(f"🤿 *{name}*")
            lines.append("")
            lines.append(f"👥 *Para quién es*: {audience}")
            if description:
                lines.append("")
                lines.append("🫧 *Qué vas a hacer*:")
                lines.append(self._truncate_text(description, 240))
            if duration:
                lines.append("")
                cert_line = ""
                if category == "course":
                    cert_line = " (certificación PADI)"
                lines.append(f"⏱ *Duración*: {duration}{cert_line}")
            if min_age is not None:
                lines.append(f"👶 *Edad mínima*: {min_age} años")
            lines.append("")
            lines.append(f"💰 *Precio desde*: {price_from}")
            if not compact:
                if includes_lines:
                    lines.append("")
                    lines.append("✅ *Qué incluye* (resumen):")
                    lines.append(includes_lines)
                if not_included_lines:
                    lines.append("")
                    lines.append("❌ *Qué no incluye* (típico):")
                    lines.append(not_included_lines)
                lines.append("")
                lines.append("🔗 *Info completa en la web*:")
                lines.append(web_url)
            return "\n".join(lines)

        lines = []
        lines.append(f"🤿 *{name}*")
        lines.append("")
        lines.append(f"👥 *Who is it for*: {audience}")
        if description:
            lines.append("")
            lines.append("🫧 *What you'll do*:")
            lines.append(self._truncate_text(description, 240))
        if duration:
            lines.append("")
            cert_line = ""
            if category == "course":
                cert_line = " (PADI certification)"
            lines.append(f"⏱ *Duration*: {duration}{cert_line}")
        if min_age is not None:
            lines.append(f"👶 *Minimum age*: {min_age} years")
        lines.append("")
        lines.append(f"💰 *Price from*: {price_from}")
        if not compact:
            if includes_lines:
                lines.append("")
                lines.append("✅ *What's included* (summary):")
                lines.append(includes_lines)
            if not_included_lines:
                lines.append("")
                lines.append("❌ *Not included* (typical):")
                lines.append(not_included_lines)
            lines.append("")
            lines.append("🔗 *Full info on the website*:")
            lines.append(web_url)
        return "\n".join(lines)


























    # ───────────────────── Cart-style mixed group flow ─────────────────────


    @staticmethod
    def _cart_includes(state: ConversationState, item_type: str) -> bool:
        return any(it.get("type") == item_type for it in state.mixed_cart)



    def _reset_mixed_state(self, state: ConversationState) -> None:
        """Wipe all cart-flow state — used by 'empezar de nuevo' and after escalation."""
        state.mixed_cart = []
        state.mixed_pending_qty_type = None
        state.mixed_pending_qty_plan = None
        state.mixed_pending_qty_value = None
        state.mixed_pending_course_question = None
        state.mixed_pending_preview_service_id = None
        state.mixed_pending_cert_total_qty = None
        state.mixed_pending_cert_remaining_qty = None
        state.mixed_pending_refresh_added_qty = None
        state.mixed_pending_beginner_after_cert = 0
        state.mixed_beginner_child_age = None
        state.mixed_pending_beginner_queue = []
        state.mixed_pending_modify_idx = None
        state.mixed_pending_modify_refresh = False
        state.mixed_pending_exact = False
        state.mixed_pending_cert_narrow_kind = None
        state.detected_cert_dives = None
        state.detected_cert_days = None
        state.mixed_display_currency = "USD"
        state.mixed_final_is_colombian = None
        state.mixed_final_has_kids_8_10 = None
        state.mixed_final_wants_private = None
        # kids_mention_detected NO se resetea — es un atributo del speaker que
        # debe persistir entre flujos. Solo se limpia el age_group respondido.
        state.kids_age_group = None
        state.kids_count = None
        state.kids_under_8_count = 0
        state.kids_eight_to_ten_count = 0
        state.mixed_last_summary = None
        state.mixed_booking_links = []

    def _clear_mixed_pending_add(self, state: ConversationState) -> None:
        state.mixed_pending_qty_type = None
        state.mixed_pending_qty_plan = None
        state.mixed_pending_qty_value = None
        state.mixed_pending_course_question = None
        state.mixed_pending_preview_service_id = None
        state.mixed_pending_cert_total_qty = None
        state.mixed_pending_cert_remaining_qty = None
        state.mixed_pending_refresh_added_qty = None
        state.mixed_pending_exact = False

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

    def _mixed_preview_state(self, state: ConversationState, service_id: str) -> ConversationState:
        preview_state = ConversationState(conversation_id=state.conversation_id)
        preview_state.language = state.language
        preview_state.location = state.location
        preview_state.island = state.island  # Preservar isla para mostrar en resumen
        preview_state.hotel = state.hotel  # Preservar hotel para coordinar recogida
        preview_state.selected_service = service_id
        preview_state.is_colombian = False
        preview_state.is_certified = bool((SERVICES.get(service_id) or {}).get("requires_certification"))
        # Preservar la cantidad ya conocida (grupo detectado o respondida) para
        # que el resumen muestre el precio total del grupo, no solo el de 1 persona.
        preview_state.mixed_pending_qty_value = state.mixed_pending_qty_value
        return preview_state

    def _prepare_mixed_add_preview(self, state: ConversationState, service_id: str) -> str:
        state.mixed_pending_preview_service_id = service_id
        state.step = Step.MIXED_ADD_PREVIEW
        self.set_quick_replies(state, "mixed_preview_actions")
        preview_state = self._mixed_preview_state(state, service_id)
        if _is_contact_only_service(service_id):
            return self._format_info_card(preview_state) + "\n\n" + MESSAGES["mixed_add_preview"][state.language]
        return self._format_summary(preview_state, final_prompt=MESSAGES["mixed_add_preview"][state.language])


    # ─── Step handlers ───



    def _ask_certification_message(self, state: ConversationState) -> str:
        """Devuelve mensaje + quick replies de certificación adaptados a singular/plural/grupo."""
        lang = state.language
        state.step = Step.MIXED_ASK_CERTIFICATION
        group_qty = (state.mixed_pending_cert_total_qty or 0) + sum(
            it["qty"] for it in state.mixed_cart if it.get("type") == "cert"
        )
        is_group = group_qty > 1 or (state.detected_group_size or 0) > 1
        if is_group:
            self.set_quick_replies(state, "mixed_ask_certification_group")
            return MESSAGES["mixed_ask_certification_group"][lang]
        self.set_quick_replies(state, "mixed_ask_certification")
        return MESSAGES["mixed_ask_certification"][lang]




    def _goto_island_hotel_menu_or_unknown(self, state: ConversationState) -> str:
        """Ask for hotel to coordinate pickup when the client is on the islands.

        If we don't even know WHICH island yet (e.g. a generic "Ya estoy en
        las islas" button click, with no island mentioned in free text), ask
        that first via Step.ISLAND_MENU; _handle_island_hotel_menu already
        knows how to resume the pending mixed-cart flow afterward via
        state.mixed_pending_qty_type.
        """
        if state.island:
            return self._goto_island_hotel_menu(state)
        state.step = Step.ISLAND_MENU
        self.set_quick_replies(state, "island_menu")
        return MESSAGES["island_menu"][state.language]

    def _goto_island_hotel_menu(self, state: ConversationState) -> str:
        """Ir al menú de hoteles según la isla detectada."""
        lang = state.language

        # Mapeo de island_id a nombre de isla
        island_names = {
            "isla_grande": "Isla Grande",
            "isla_marina": "Isla Marina",
            "isla_del_pirata": "Isla del Pirata",
            "isla_del_sol": "Isla del Sol",
            "isleta": "Isleta",
            "isla_arena": "Isla Arena",
            "isla_pavitos": "Isla Pavitos",
            "isla_lizamar": "Isla Lizamar",
            "isla_gigi": "Isla Gigi",
            "isla_rosa": "Isla Rosa",
            "isla_pelicano": "Isla Pelicano",
            "isla_rosario": "Isla Rosario",
        }

        island_name = island_names.get(state.island, state.island)

        hotels_by_island: dict[str, list[str]] = {
            "Isla Grande": [
                "San Pedro de Majagua",
                "Bora Bora Beach Club",
                "Cocoliso Island Resort",
                "Pao Pao Hotel",
                "Fragata Island House",
                "Secreto Hostel",
                "Gente de Mar Resort",
                "Luxury Beach Club",
                "Ecohotel Las Flores",
                "Ecohostal Playa Libre",
            ],
            "Isla Marina": [
                "Islabela",
                "Hotel El Hamaquero",
                "Centro Ubuntu",
            ],
            "Isla del Pirata": [
                "Hotel Isla del Pirata",
            ],
            "Isla del Sol": [
                "Hotel Isla del Sol",
            ],
            "Isleta": [
                "Coralina Island",
                "Isleta Beach",
            ],
            "Isla Arena": [
                "Isla Arena Eco Resort",
            ],
            "Isla Pavitos": [
                "Isla Pavitos (Privada)",
            ],
            "Isla Lizamar": [
                "Hotel Lizamar",
            ],
            "Isla Gigi": [
                "Casa de Isla Gigi",
            ],
            "Isla Rosa": [
                "Isla Rosa (Privada)",
            ],
            "Isla Pelicano": [
                "Isla Pelicano",
            ],
            "Isla Rosario": [
                "Rosario EcoHotel",
                "Hotel San Tropel",
            ],
        }

        island_hotels = hotels_by_island.get(island_name, [])
        if island_hotels:
            quick_replies: list[dict] = []
            for idx, hotel_name in enumerate(island_hotels, start=1):
                quick_replies.append({"title": hotel_name, "value": str(idx)})
            other_title = "Otro / No esta en la lista" if lang == "es" else "Other / Not listed"
            quick_replies.append({"title": other_title, "value": str(len(island_hotels) + 1)})
            quick_replies.append({"title": "🔙 Volver" if lang == "es" else "🔙 Back", "value": "back"})

            state.step = Step.ISLAND_HOTEL_MENU
            state.quick_replies = quick_replies

            if lang == "es":
                return (
                    f"Perfecto, estás en *{island_name}*.\n\n"
                    "¿En qué hotel te hospedas? (Necesario para coordinar la recogida)"
                )
            return (
                f"Great, you are on *{island_name}*.\n\n"
                "Which hotel are you staying at? (Needed to coordinate pickup)"
            )

        # Si no hay hoteles para esa isla, continuar sin hotel
        if lang == "es":
            return f"Perfecto, tomamos nota de que estás en *{island_name}*."
        return f"Great, we've noted you are on *{island_name}*."

    def _mixed_context_recap(self, state: ConversationState, lang: str) -> str:
        """Short reminder of what's already known (cart items + origin), shown
        before re-asking "what activity do you want to add?" — e.g. after
        "Volver". The underlying state was never cleared here (only the
        transient in-progress-item fields are, via `_clear_mixed_pending_add`),
        but a bare "¿qué actividad quieres añadir?" with no recap reads to the
        customer as if the bot forgot everything they'd already said. Returns
        "" when there's nothing yet worth recapping (brand-new booking).
        """
        lines: list[str] = []
        if state.mixed_cart:
            lines.append(self._format_cart_lines(state, lang))
        if state.location == "island" and state.island:
            loc_line = (
                f"📍 Ya sabemos que estás en *{state.island}*"
                if lang == "es" else f"📍 We already know you're on *{state.island}*"
            )
            if state.hotel and state.hotel != "Otro / No esta en la lista":
                loc_line += f", hotel *{state.hotel}*" if lang == "es" else f", at *{state.hotel}*"
            lines.append(loc_line + ".")
        elif state.location == "cartagena":
            lines.append(
                "📍 Ya sabemos que sales desde *Cartagena*."
                if lang == "es" else "📍 We already know you're departing from *Cartagena*."
            )
        if not lines:
            return ""
        return "\n\n".join(lines) + "\n\n"

    def _goto_mixed_add_activity(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_ADD_ACTIVITY
        self.set_quick_replies(state, "mixed_add_activity")
        return self._mixed_context_recap(state, lang) + MESSAGES["mixed_add_activity"][lang]


    def _goto_mixed_companion_upsell(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_COMPANION_UPSELL
        self.set_quick_replies(state, "mixed_companion_upsell")
        return MESSAGES["mixed_companion_upsell"][lang]


    def _refresher_info_msg(self, state: ConversationState) -> str:
        """Devuelve el mensaje de refresher en singular o plural según el grupo."""
        lang = state.language
        qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
        is_group = qty > 1 or (state.detected_group_size or 0) > 1
        key = "refresher_info_group" if is_group else "refresher_info"
        return MESSAGES[key][lang]

    def _goto_mixed_cert_last_dive_or_qty(self, state: ConversationState) -> str:
        """Salta la pregunta de cantidad si ya la conocemos del mensaje inicial."""
        lang = state.language
        pre_qty = state.mixed_pending_cert_total_qty
        if pre_qty and pre_qty > 0:
            state.mixed_pending_qty_value = pre_qty
            # If the customer already told us when they last dived ("buceamos hace
            # un mes", "hace más de 3 años"), don't re-ask — apply it directly.
            skipped = self._skip_last_dive_if_known(state)
            if skipped is not None:
                return skipped
            # Cantidad ya conocida → ir directamente a última inmersión
            state.step = Step.MIXED_CERT_LAST_DIVE
            msg_key = "mixed_cert_last_dive_group" if pre_qty > 1 else "mixed_cert_last_dive"
            self.set_quick_replies(state, "mixed_cert_last_dive")
            return MESSAGES[msg_key][lang]
        return self._goto_mixed_add_qty(state)

    def _skip_last_dive_if_known(self, state: ConversationState) -> str | None:
        """If the last-dive answer is already known (from the initial message),
        route as if the customer had answered the question, so it isn't re-asked:
        over 2 years → offer the refresher; otherwise → straight to the preview.
        Returns the next message, or None if we still need to ask."""
        known = state.detected_last_dive_over_2_years
        if known is None:
            known = state.last_dive_over_2_years
        if known is None:
            return None
        state.last_dive_over_2_years = known
        if known is True:      # >2 years → refresher interest (same as answering "sí")
            state.step = Step.MIXED_CERT_REFRESH_INTEREST
            self.set_quick_replies(state, "refresher_interest")
            return self._refresher_info_msg(state)
        # <2 years → proceed straight to the preview (same as answering "no")
        return self._prepare_mixed_add_preview(state, self._current_mixed_cert_service_id(state))

    def _pop_detected_cert_counts(self, state: ConversationState) -> tuple[int | None, int | None]:
        """Consume (dives, days) detected before we knew enough to resolve the
        plan (e.g. location wasn't known yet), so they're applied exactly once."""
        dives = state.detected_cert_dives
        days = state.detected_cert_days
        state.detected_cert_dives = None
        state.detected_cert_days = None
        return dives, days

    def _resolve_or_ask_cert_plan(
        self,
        state: ConversationState,
        dives: int | None,
        days: int | None = None,
        *,
        fallback_multiday_menu: bool = False,
        recommend_default: bool = False,
    ) -> str:
        """Given an explicit dive count and/or day count (or neither), resolve
        straight to the matching plan when it's unambiguous, otherwise ask
        instead of guessing:
        - dives == 2 -> the single-day 2-dive plan, no question needed.
        - dives in (3,5,7,9), or 4 off-island -> exact multi-day plan is known;
          show only the relevant lodging note and move to the next step.
        - dives == 4 on-island -> two variants exist (all-daytime vs 3+1 night
          dive); ask the short follow-up instead of the full menu.
        - no dives but days == 3 or 4 -> maps to a single dive count (7 or 9
          respectively), resolved the same way as an explicit dive count.
        - no dives but days == 1 or 2 -> each maps to TWO plans (1 day = 2 or 3
          dives; 2 days = 4 or 5 dives); ask the short 2-option follow-up.
        - anything else (nothing recognized): if the customer already told us
          they want a multi-day package (fallback_multiday_menu=True, e.g. they
          clicked "multi-day" at the cert-plan question), show the full
          3/5/7/9-dive menu. Otherwise we don't even know 2-dive vs multi-day
          yet, so ask the generic "2 dives vs multi-day package" question.

        Shared by the cert-plan step itself (natural-language count typed there)
        and by every path that lands on the cert flow after learning the location/
        hotel/certification split, so a count given earlier isn't forgotten.
        """
        lang = state.language
        if dives is None and days is not None:
            if days == 3:
                dives = 7
            elif days == 4:
                dives = 9
            elif days == 1:
                state.step = Step.MIXED_ADD_CERT_MULTI_DAY
                state.mixed_pending_cert_narrow_kind = "1day"
                self.set_quick_replies(state, "mixed_add_cert_1day_variant")
                return MESSAGES["mixed_add_cert_1day_variant"][lang]
            elif days == 2:
                state.step = Step.MIXED_ADD_CERT_MULTI_DAY
                state.mixed_pending_cert_narrow_kind = "2day"
                self.set_quick_replies(state, "mixed_add_cert_2day_variant")
                return MESSAGES["mixed_add_cert_2day_variant"][lang]

        if dives == 2:
            state.mixed_pending_qty_plan = self._service_for_location("2_dives_1_day", state)
            return self._goto_mixed_cert_last_dive_or_qty(state)
        if dives in (3, 4, 5, 7, 9):
            multiday_choice = self._cert_dives_to_multiday_choice(dives, state)
            if multiday_choice is not None:
                service_map = self._mixed_cert_multi_day_service_map(state)
                state.mixed_pending_qty_plan = service_map[multiday_choice]
                note = self._mixed_cert_lodging_note(dives, lang)
                return note + "\n\n" + self._goto_mixed_cert_last_dive_or_qty(state)
            if dives == 4 and state.location == "island":
                state.step = Step.MIXED_ADD_CERT_MULTI_DAY
                state.mixed_pending_cert_narrow_kind = "4dive_island"
                self.set_quick_replies(state, "mixed_add_cert_4dive_variant")
                return MESSAGES["mixed_add_cert_4dive_variant"][lang]
        if fallback_multiday_menu:
            state.step = Step.MIXED_ADD_CERT_MULTI_DAY
            self.set_quick_replies(state, "mixed_add_cert_multi_day")
            return MESSAGES["mixed_add_cert_multi_day"][lang]
        # NO dive count given at all (e.g. "soy certificada, quiero unas
        # inmersiones"): only on the FREE-TEXT entry (recommend_default=True, set by
        # supervisor._route_detected_intent when a certified diver's first message
        # already says they want to dive) do we RECOMMEND the most popular plan
        # (2 dives / 1 day) directly and move on, instead of a "2 dives vs multi-day"
        # button menu (owner decision 2026-07-20 — a certified diver who already said
        # what they want shouldn't be sent back into a menu). The customer can still
        # switch to a multi-day package by text ("multi-día", "quiero 5 inmersiones"),
        # handled at the quantity step. The button-driven/guided paths (add-activity,
        # cert-count split, location, hotel menu) keep the plan menu so button cart
        # builders reach multi-day/4-dive variants and the split flow can still offer
        # the Open Water course to a beginner companion on a multi-day plan. That
        # same split flow (a beginner companion pending after the cert subgroup) is
        # ALWAYS routed to the menu, even on recommend_default paths, so the Open
        # Water offer survives — hence the `not mixed_pending_beginner_after_cert`.
        if (
            dives is None
            and days is None
            and recommend_default
            and not state.mixed_pending_beginner_after_cert
        ):
            state.mixed_pending_qty_plan = self._service_for_location("2_dives_1_day", state)
            intro = (
                "Te recomiendo nuestro plan más popular: *2 inmersiones en 1 día* "
                "en las Islas del Rosario. "
                "(Si prefieres un *paquete multi-día* de 3 o más inmersiones, dímelo.)\n\n"
                if lang == "es" else
                "I recommend our most popular plan: *2 dives in 1 day* in the Rosario "
                "Islands. (If you'd rather a *multi-day package* of 3+ dives, just tell me.)\n\n"
            )
            return intro + self._goto_mixed_cert_last_dive_or_qty(state)
        state.step = Step.MIXED_ADD_CERT_PLAN
        self.set_quick_replies(state, "mixed_add_cert_plan")
        return MESSAGES["mixed_add_cert_plan"][lang]



    def _goto_mixed_add_qty(self, state: ConversationState) -> str:
        # If we already know the quantity (pre-set by supervisor or from detected group size),
        # skip the question and auto-answer it.
        known_qty = state.mixed_pending_qty_value
        if not known_qty and state.detected_group_size and state.detected_group_size > 0:
            known_qty = state.detected_group_size
        if known_qty and known_qty > 0:
            return self._handle_mixed_add_qty(state, str(known_qty))
        lang = state.language
        state.step = Step.MIXED_ADD_QTY
        state.mixed_pending_exact = False
        self.set_quick_replies(state, "mixed_quantity")
        return MESSAGES["mixed_add_qty"][lang]

    def _reveals_non_certified_companion(self, message: str) -> bool:
        """True if the qty answer reveals a companion who is NOT a certified diver
        while the speaker is — e.g. 'yo buzo pero mi novia no lo es', 'ella no
        bucea', 'uno sí y otro no', 'my girlfriend isn't certified'.

        Deliberately requires the negation to attach to a certification/diving
        concept (not just any bare 'no') so it does not misfire on phrases like
        'no queremos separarnos' where the whole group is certified.
        """
        norm = "".join(
            c for c in unicodedata.normalize("NFD", message.lower())
            if unicodedata.category(c) != "Mn"
        )
        patterns = [
            r"\bno\s+(?:es|esta|estan|son)?\s*(?:certificad|buz[oa])",
            r"\bno\s+(?:sabe|saben)\s+bucear\b",
            r"\bno\s+bucea[n]?\b",
            r"\bno\s+tiene[n]?\s+(?:el\s+|la\s+)?(?:certificad|open\s*water|licencia|carne|carnet|titulo|titulacion)",
            r"\bno\s+lo\s+(?:es|tiene|son)\b",           # "mi novia no lo es" / "no lo tiene"
            r"\bsin\s+certifica(?:r|d)",                  # "otro sin certificar" / "sin certificado"
            r"\bsolo\s+yo\b[^.]{0,25}(?:buce|buzo|certificad)",
            r"\bun[oa]\s+(?:si\s+)?y\s+(?:el\s+|la\s+)?otr[oa]\s+no\b",
            # EN
            r"\bnot\s+(?:a\s+)?certified\b",
            r"\bisn'?t\s+certified\b",
            r"\b(?:doesn'?t|does not)\s+dive\b",
            r"\bonly\s+i\b[^.]{0,20}(?:dive|certif)",
            r"\bone\s+of\s+us\b[^.]{0,25}(?:isn'?t|is not|not\s+certif)",
        ]
        return any(re.search(p, norm) for p in patterns)

    def _detect_cert_qty_activity_split(self, message: str) -> tuple[int, int] | None:
        """At the certified-dive qty step, detect answers that give the dive
        count AND mention other people doing a NON-diving activity
        (snorkel / minicurso), so those people aren't silently dropped.

        Returns (dive_count, other_count), or None if no other activity is
        mentioned. Examples (dive, other):
          "2 y uno que quiere hacer snorkel"   -> (2, 1)
          "somos 2 y uno hace snorkel"         -> (1, 1)   ("somos N" = total)
          "somos 3 y 2 hacen snorkel"          -> (1, 2)
          "3 buceamos y 1 hace snorkel"        -> (3, 1)
          "yo buceo y mi novia snorkel"        -> (1, 1)
          "2 y mi hijo minicurso"              -> (2, 1)
        """
        norm = "".join(
            c for c in unicodedata.normalize("NFD", message.lower())
            if unicodedata.category(c) != "Mn"
        )
        norm = " ".join(norm.split())
        other_kw = r"snorkel|esnorkel|snorkeling|careteo|minicurso|mini curso|bautismo|bautizo"
        if not re.search(rf"\b(?:{other_kw})\b", norm):
            return None

        _wn = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
               "seis": 6, "siete": 7, "ocho": 8, "one": 1, "two": 2, "three": 3,
               "four": 4, "five": 5, "six": 6}
        num_re = r"\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho"

        def _to_int(tok: str) -> int | None:
            return int(tok) if tok.isdigit() else _wn.get(tok)

        def _first_num(text: str) -> int | None:
            m = re.search(num_re, text)
            return _to_int(m.group()) if m else None

        # Split into clauses on "y"/"e"/"and"/"," so a number stays bound to its
        # own activity ("3 buceamos y 1 snorkel" -> ["3 buceamos", "1 snorkel"]),
        # instead of the leading number greedily reaching the far keyword.
        clauses = re.split(r"\s+y\s+|\s+e\s+|\s+and\s+|,\s*", norm)
        other_clause = next((c for c in clauses if re.search(rf"\b(?:{other_kw})\b", c)), None)
        if other_clause is None:
            return None
        other_count = _first_num(other_clause) or 1  # "uno que quiere snorkel" / "mi hijo snorkel" -> 1

        # "somos/venimos/vamos N" (or English) states a TOTAL, not the dive count.
        m_total = re.search(rf"\b(?:somos|venimos|vamos|we are|there are)\s+({num_re})\b", norm)
        total = _to_int(m_total.group(1)) if m_total else None

        if total is not None:
            dive = total - other_count
        else:
            # Dive count = the number from the FIRST non-other clause; if none has
            # one ("yo buceo y mi novia snorkel"), default to 1.
            dive = None
            for c in clauses:
                if re.search(rf"\b(?:{other_kw})\b", c):
                    continue
                n = _first_num(c)
                if n:
                    dive = n
                    break
            if dive is None:
                dive = 1

        if not dive or dive < 1 or other_count < 1 or dive > 40 or other_count > 40:
            return None
        return (dive, other_count)










    def _cert_subgroup_is_multi_day(self, state: ConversationState) -> bool:
        """True if the certified subgroup's plan requires an island overnight
        stay — used to decide whether Open Water makes sense as an option for
        the non-certified people (they'd already be staying on the islands).
        Covers both real multi-day packages (MULTI_DAY_SERVICES) and
        "3_dives_1_day" — confusingly a single calendar day, but it still
        requires sleeping on the island that night because of the night dive
        (see _accommodation_requirement_note's special case for that id).
        """
        cert_item = next((it for it in state.mixed_cart if it.get("type") == "cert"), None)
        plan = (cert_item or {}).get("plan") or state.mixed_pending_qty_plan
        if not plan:
            return False
        service = SERVICES.get(plan) or {}
        return plan in MULTI_DAY_SERVICES or bool(service.get("includes_night_dive"))

    def _beginner_activity_quick_replies(self, lang: str, include_open_water: bool) -> list[dict]:
        # Companion ("just come along, no activity") is always the last option,
        # after Open Water when that is offered, so its value shifts 3->4.
        companion_value = "4" if include_open_water else "3"
        if lang == "es":
            options = [
                {"title": "🤿 Minicurso de buceo", "value": "1"},
                {"title": "🌊 Snorkel", "value": "2"},
            ]
            if include_open_water:
                options.append({"title": "🎓 Curso Open Water", "value": "3"})
            options.append({"title": "👤 Solo acompañante", "value": companion_value})
            options.append({"title": "🔙 Volver", "value": "back"})
        else:
            options = [
                {"title": "🤿 Dive mini-course", "value": "1"},
                {"title": "🌊 Snorkel", "value": "2"},
            ]
            if include_open_water:
                options.append({"title": "🎓 Open Water course", "value": "3"})
            options.append({"title": "👤 Just a companion", "value": companion_value})
            options.append({"title": "🔙 Back", "value": "back"})
        return options

    def _add_beginner_activity_for_person(self, state: ConversationState, option: str) -> None:
        """Add one non-certified person's chosen/forced activity to the cart."""
        if option == "companion":
            self._append_mixed_cart_item(state, "companion", None, 1)
        elif option == "snorkel":
            self._append_mixed_cart_item(state, "snorkel", self._service_for_location("snorkeling", state), 1)
        elif option == "bubble":
            # 8-9 yo dive intro priced/handled as Bubble Makers (8-10 range).
            state.kids_eight_to_ten_count = (state.kids_eight_to_ten_count or 0) + 1
            self._append_mixed_cart_item(state, "beginner", None, 1)
        else:  # minicourse (10+ adult mini-course)
            self._append_mixed_cart_item(state, "beginner", None, 1)

    def _build_beginner_queue(self, state: ConversationState, beginner_qty: int) -> list | None:
        """Per-person queue of non-cert ages when we know each one's age.

        Only fires when the count of known minor ages exactly matches the number
        of non-certified people (so we're confident each age maps to a person);
        otherwise returns None and the caller uses the single/grouped offer.
        """
        minor_ages = sorted(a for a in (state.detected_ages or []) if a < 18)
        if beginner_qty >= 2 and len(minor_ages) == beginner_qty:
            return minor_ages
        return None

    def _process_beginner_queue(self, state: ConversationState) -> str:
        """Auto-add forced activities (e.g. <6 -> companion) and stop to ask a
        choice for the next person who has more than one option."""
        queue = state.mixed_pending_beginner_queue or []
        while queue:
            age = queue[0]
            options = eligibility.beginner_options_for_age(age)
            if len(options) == 1:                 # forced (companion for <6)
                self._add_beginner_activity_for_person(state, options[0])
                queue.pop(0)
                continue
            # This person needs a choice — offer it, keep them at the head.
            state.mixed_pending_beginner_queue = queue
            return self._offer_queue_person(state, age)
        # Everyone placed.
        state.mixed_pending_beginner_queue = []
        state.mixed_pending_beginner_after_cert = 0
        return self._goto_mixed_cart_review(state)

    def _offer_queue_person(self, state: ConversationState, age: int) -> str:
        """Show the age-appropriate offer for ONE person from the queue."""
        lang = state.language
        state.step = Step.MIXED_ASK_BEGINNER_ACTIVITY
        if age < eligibility.MIN_DIVE:
            state.mixed_beginner_child_age = age
            state.quick_replies = self._child_beginner_quick_replies(lang, age)
            note = eligibility.age_eligibility_note(age, lang)
            head = (f"Para la persona de *{age} años*:\n" if lang == "es"
                    else f"For the *{age}-year-old*:\n")
            return head + note + ("\n\n¿Qué prefiere?" if lang == "es" else "\n\nWhat would they prefer?")
        # 10+ : general offer (minicurso / snorkel / companion) — fixed 3 options.
        state.mixed_beginner_child_age = None
        if lang == "es":
            state.quick_replies = [
                {"title": "🤿 Minicurso de buceo", "value": "1"},
                {"title": "🌊 Snorkel", "value": "2"},
                {"title": "👤 Solo acompañante", "value": "3"},
                {"title": "🔙 Volver", "value": "back"},
            ]
            return (f"Para la persona de *{age} años* (sin certificación), puede elegir:\n"
                    "• 🤿 Minicurso de buceo\n• 🌊 Snorkel\n• 👤 Solo acompañante\n\n¿Qué prefiere?")
        state.quick_replies = [
            {"title": "🤿 Dive mini-course", "value": "1"},
            {"title": "🌊 Snorkel", "value": "2"},
            {"title": "👤 Just a companion", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ]
        return (f"For the *{age}-year-old* (not certified), options:\n"
                "• 🤿 Dive mini-course\n• 🌊 Snorkel\n• 👤 Just a companion\n\nWhat would they prefer?")


    def _single_beginner_child_age(self, state: ConversationState) -> int | None:
        """Age of the non-certified person when it's a single known minor under
        the diving age (10). Returns None when there are several non-cert people
        or no under-10 age is known (then the general offer applies)."""
        if (state.mixed_pending_beginner_after_cert or 0) != 1:
            return None
        minors = [a for a in (state.detected_ages or []) if a < eligibility.MIN_DIVE]
        # Exactly one under-diving-age person known -> adapt to that age.
        return minors[0] if len(minors) == 1 else None

    def _child_beginner_options(self, age: int) -> list[str]:
        """Ordered action keys a non-certified minor of this age may pick."""
        if age < eligibility.MIN_SNORKEL:            # < 6: nothing in water
            return ["companion"]
        if age < eligibility.BUBBLE_MAKERS_MIN:      # 6-7: snorkel only
            return ["snorkel", "companion"]
        return ["bubble", "snorkel", "companion"]    # 8-9: Bubble Makers + snorkel

    def _child_beginner_quick_replies(self, lang: str, age: int) -> list[dict]:
        titles = {
            "bubble": "🤿 Buceo para niños (Bubble Makers)" if lang == "es" else "🤿 Kids diving (Bubble Makers)",
            "snorkel": "🌊 Snorkel" if lang == "es" else "🌊 Snorkel",
            "companion": "👤 Solo acompañante" if lang == "es" else "👤 Just a companion",
        }
        opts = [
            {"title": titles[a], "value": str(i + 1)}
            for i, a in enumerate(self._child_beginner_options(age))
        ]
        opts.append({"title": "🔙 Volver" if lang == "es" else "🔙 Back", "value": "back"})
        return opts



    def _offer_young_child_activity(self, state: ConversationState, age: int) -> str:
        lang = state.language
        state.mixed_beginner_child_age = age
        state.step = Step.MIXED_ASK_BEGINNER_ACTIVITY
        state.quick_replies = self._child_beginner_quick_replies(lang, age)
        note = eligibility.age_eligibility_note(age, lang)
        if lang == "es":
            intro = (
                "¡Listo! Los buceadores certificados ya están en el carrito. 🤿\n\n"
                f"{note}\n\n¿Qué prefiere para él/ella?"
            )
        else:
            intro = (
                "Done! The certified divers are in the cart. 🤿\n\n"
                f"{note}\n\nWhat would they prefer?"
            )
        return intro

    def _maybe_start_pending_beginner(self, state: ConversationState) -> str | None:
        """If a 'some certified, some not' group still has non-certified people
        waiting, ask what they'd like to do (we only know they're not
        certified — minicurso, snorkel, or, if the group is already staying
        overnight on the islands for the certified plan, Open Water). Returns
        the next message, or None if there's nothing pending.
        """
        beginner_qty = state.mixed_pending_beginner_after_cert or 0
        if beginner_qty <= 0:
            return None
        lang = state.language

        # Auto-build: several non-certified people whose ages we all know -> place
        # each one age-appropriately (auto-add the forced ones, ask the choices),
        # one person at a time.
        queue = self._build_beginner_queue(state, beginner_qty)
        if queue is not None:
            state.mixed_pending_beginner_queue = queue
            intro = ("¡Listo! Los buceadores certificados ya están en el carrito. 🤿\n\n"
                     "Ahora vemos el plan ideal para cada uno de los demás:\n\n"
                     if lang == "es" else
                     "Done! The certified divers are in the cart. 🤿\n\n"
                     "Now let's sort out the ideal plan for each of the others:\n\n")
            return intro + self._process_beginner_queue(state)

        # Age-aware offering: if the single non-certified person is a known minor
        # under the diving age (10), don't offer the adult mini-course — offer
        # only what their age allows (snorkel / Bubble Makers / companion).
        child_age = self._single_beginner_child_age(state)
        if child_age is not None:
            return self._offer_young_child_activity(state, child_age)

        include_open_water = self._cert_subgroup_is_multi_day(state)
        state.step = Step.MIXED_ASK_BEGINNER_ACTIVITY
        state.quick_replies = self._beginner_activity_quick_replies(lang, include_open_water)

        if lang == "es":
            who = "la persona no certificada" if beginner_qty == 1 else f"las {beginner_qty} personas no certificadas"
            quiere = "quiere" if beginner_qty == 1 else "quieren"
            intro = (
                f"¡Listo! Los buceadores certificados ya están en el carrito. 🤿\n\n"
                f"¡Y buenísimo que vengan juntos! Aunque {who} no tenga certificación, "
                f"igual {quiere} disfrutar del plan. Estas son las opciones:\n"
            )
            body = (
                "• 🤿 *Minicurso de buceo*: probar el buceo en una sesión introductoria con instructor, "
                "sin necesidad de certificación. ¡Es la forma perfecta de iniciarse!\n"
                "• 🌊 *Snorkel*: disfrutar del arrecife desde la superficie, sin bucear.\n"
            )
            if include_open_water:
                body += (
                    "• 🎓 *Curso Open Water*: ya que se alojarán en las islas con el grupo certificado, "
                    "puede aprovechar y certificarse como buzo.\n"
                )
            body += "• 👤 *Solo acompañante*: venir con el grupo y disfrutar del paseo, sin actividad en el agua.\n"
            outro = "\n¿Qué prefiere?" if beginner_qty == 1 else "\n¿Qué prefieren?"
        else:
            who = "the non-certified person" if beginner_qty == 1 else f"the {beginner_qty} non-certified people"
            intro = (
                f"Done! The certified divers are in the cart. 🤿\n\n"
                f"And it's great that you're coming together! Even though {who} isn't certified, "
                f"they can still enjoy the plan. Here are the options:\n"
            )
            body = (
                "• 🤿 *Dive mini-course*: try diving in an introductory session with an instructor, "
                "no certification needed. It's the perfect way to get started!\n"
                "• 🌊 *Snorkel*: enjoy the reef from the surface, no diving needed.\n"
            )
            if include_open_water:
                body += (
                    "• 🎓 *Open Water course*: since they'll already be staying on the islands with the "
                    "certified group, they could get certified too.\n"
                )
            body += "• 👤 *Just a companion*: come along with the group and enjoy the trip, no in-water activity.\n"
            outro = "\nWhat would they prefer?"
        return intro + body + outro


    # Emojis numéricos para listas dinámicas (botones de modificar/quitar item)
    _NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


    def _kids_sub_bullet(self, state: ConversationState, lang: str) -> str | None:
        """Sub-bullet line(s) shown under the beginner cart row when kids info is known.

        Returns None if no kids are flagged. For single-range answers shows one bullet.
        For mixed answers (both u8 and 8-10 > 0) returns two concatenated bullets.
        """
        u8 = state.kids_under_8_count or 0
        e10 = state.kids_eight_to_ten_count or 0
        bullets: list[str] = []
        if u8 > 0:
            if lang == "es":
                noun = "menor" if u8 == 1 else "menores"
                bullets.append(f"       _↳ {u8} {noun} de 8 — no pueden bucear, snorkel desde 6 años_")
            else:
                noun = "child" if u8 == 1 else "children"
                bullets.append(f"       _↳ {u8} {noun} under 8 — cannot dive, snorkel from age 6_")
        if e10 > 0:
            if lang == "es":
                noun = "niño" if e10 == 1 else "niños"
                bullets.append(f"       _↳ {e10} {noun} de 8 a 10 (Bubble Makers — supervisor especializado)_")
            else:
                noun = "kid" if e10 == 1 else "kids"
                bullets.append(f"       _↳ {e10} {noun} aged 8-10 (Bubble Makers — specialized supervisor)_")
        if not bullets:
            return None
        return "\n".join(bullets)

    def _format_cart_lines(self, state: ConversationState, lang: str) -> str:
        if not state.mixed_cart:
            return MESSAGES["mixed_cart_empty"][lang]
        title = "🛒 *Tu carrito:*" if lang == "es" else "🛒 *Your cart:*"
        lines = [title]
        # Build per-plan refresh map so each sub-bullet appears under the right cert
        # item, not always the first cert in the cart.
        # plan=None entries are legacy (pre-fix carts): fall back to the first cert.
        refresh_by_plan: dict[str | None, int] = {}
        for it in state.mixed_cart:
            if it.get("type") == "refresh":
                plan = it.get("plan")
                refresh_by_plan[plan] = refresh_by_plan.get(plan, 0) + it["qty"]
        kids_sub = self._kids_sub_bullet(state, lang)
        visible_idx = 0
        for item in state.mixed_cart:
            if item.get("type") == "refresh":
                continue
            visible_idx += 1
            lines.append(f"  *{visible_idx}.* {item['qty']} × {item['label']}")
            if item.get("type") == "cert":
                plan = item.get("plan")
                if plan in refresh_by_plan:
                    r_qty = refresh_by_plan.pop(plan)
                elif None in refresh_by_plan:
                    r_qty = refresh_by_plan.pop(None)
                else:
                    r_qty = 0
                if r_qty > 0:
                    people_word = "persona" if r_qty == 1 else "personas"
                    sub = (
                        f"       _↳ {r_qty} {people_word} con refresher (sin coste adicional)_"
                        if lang == "es"
                        else f"       _↳ {r_qty} {'person' if r_qty == 1 else 'people'} with refresher (no extra cost)_"
                    )
                    lines.append(sub)
            if item.get("type") == "beginner" and kids_sub:
                lines.append(kids_sub)
                kids_sub = None
        return "\n".join(lines)

    def _format_cart_info_links(self, state: ConversationState, lang: str) -> str:
        """Info links (web_url) for each distinct resolvable service in the
        cart — NOT booking links, those still depend on nationality (50/50
        payment vs. direct link) and are only sent after that question."""
        seen: set[str] = set()
        lines = []
        for item in state.mixed_cart:
            plan = item.get("plan")
            if not plan or plan in seen:
                continue
            service = SERVICES.get(plan)
            if not service:
                continue
            seen.add(plan)
            label = item.get("label") or service.get(f"name_{lang}") or plan
            lines.append(f"🔗 {label}: {service['web_url']}")
        if not lines:
            return ""
        header = "👉 Más información:" if lang == "es" else "👉 More information:"
        return header + "\n" + "\n".join(lines)

    def _goto_mixed_cart_review(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_CART_REVIEW
        self.set_quick_replies(state, "mixed_cart_actions")
        cart_lines = self._format_cart_lines(state, lang)
        links_block = self._format_cart_info_links(state, lang)
        prompt = MESSAGES["mixed_cart_actions"][lang]
        parts = [cart_lines]
        if links_block:
            parts.append(links_block)
        parts.append(prompt)
        return "\n\n".join(parts)

    def _goto_mixed_entry(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_ENTRY
        self.set_quick_replies(state, "mixed_entry")
        msg_key = "mixed_entry_cert_beg" if state.mixed_entry_path == "cert_beg" else "mixed_entry"
        return MESSAGES[msg_key][lang]




    # ─── Cambiar origen desde el carrito ───


    def _remap_plan_for_location(self, plan: str | None, state: ConversationState) -> str | None:
        """Swap a single service_id to the equivalent for state.location, if one
        exists in ISLAND_SERVICE_MAP. Returns the plan unchanged if there's no
        location-specific variant (or it's already unset)."""
        if not plan:
            return plan
        island_to_base = {island: base for base, island in ISLAND_SERVICE_MAP.items()}
        if state.location == "island" and plan in ISLAND_SERVICE_MAP:
            new_plan = ISLAND_SERVICE_MAP[plan]
            if new_plan in SERVICES:
                return new_plan
        elif state.location == "cartagena" and plan in island_to_base:
            new_plan = island_to_base[plan]
            if new_plan in SERVICES:
                return new_plan
        return plan

    def _remap_cart_for_location(self, state: ConversationState) -> None:
        """Refresh cart item labels and plans after a location change.

        Also remaps the PENDING plan (`state.mixed_pending_qty_plan`, set while
        resolving cert-plan/qty/last-dive/refresher but not yet confirmed into
        the cart) — fixed 2026-07-08. Previously, if the customer changed
        location mid-flow (e.g. resolved "5 inmersiones, desde cartagena" then
        said "en realidad estoy en las islas" before confirming add-to-cart),
        the item that eventually got added still carried the Cartagena
        service_id, since only `state.mixed_cart` (already-confirmed items)
        was rewritten.

        `cert` and `course` items carry a plan that may embed a location
        variant (e.g. `2_dives_1_day` ↔ `2_dives_1_day_already_on_island`,
        `open_water` ↔ `open_water_already_on_island`); we swap them to the
        equivalent for the new location when one exists in ISLAND_SERVICE_MAP.
        `beginner`/`snorkel`/`refresh` resolve their service via
        `_cart_service_id` dynamically and don't need plan rewriting; only
        their labels are refreshed.
        """
        for item in state.mixed_cart:
            item_type = item.get("type")
            plan = item.get("plan")
            if item_type in {"cert", "course"} and plan:
                item["plan"] = self._remap_plan_for_location(plan, state)
            # Refresh the label for the (possibly new) plan and language.
            item["label"] = self._cart_label_for(item_type, item.get("plan"), state.language)

        # Pending plan (not yet added to the cart) — same swap, so an
        # in-progress qty/last-dive/refresher resolution survives a mid-flow
        # location change instead of silently keeping the old-location plan.
        if state.mixed_pending_qty_plan:
            state.mixed_pending_qty_plan = self._remap_plan_for_location(
                state.mixed_pending_qty_plan, state
            )


    # ───────── Orchestrator (Fase 2) public helpers ─────────
    # These let the tool-calling orchestrator (src/agents/orchestrator.py) drive
    # the cart flow from free text, reusing the exact same handlers the buttons use.

    # Steps where the customer was asked something and hasn't answered it yet —
    # a message that resolves as an UNRELATED action (e.g. a location update)
    # must not silently jump past these without re-asking. Currently only
    # MIXED_ASK_CERTIFICATION is verified/tested; extend if a sibling case
    # shows up (MIXED_ASK_CERT_COUNT, MIXED_ASK_BEGINNER_ACTIVITY).
    _PENDING_QUESTION_STEPS = {Step.MIXED_ASK_CERTIFICATION}

    def orchestrator_set_location(self, state: ConversationState, origin: str) -> str | None:
        """Set the departure origin from free text, remap the cart, re-render.

        Returns the rendered response, or None if `origin` is invalid.
        """
        if origin not in ("cartagena", "island"):
            return None
        lang = state.language
        changed = state.location != origin
        state.location = origin
        # Switching to "island" without a known hotel: ask for it (needed for
        # pickup) before remapping prices and showing the cart again.
        if origin == "island" and not state.hotel:
            state.mixed_pending_location_change = True
            return self._goto_island_hotel_menu_or_unknown(state)
        # Remap whenever there's a confirmed cart OR an in-progress pending
        # plan (qty/last-dive/refresher resolution not yet added to cart) —
        # a cart-only check would silently skip the pending-plan case.
        if state.mixed_cart or state.mixed_pending_qty_plan:
            self._remap_cart_for_location(state)
        if lang == "es":
            loc_label = "Cartagena" if origin == "cartagena" else "Islas del Rosario"
            ack = (
                f"📍 Origen actualizado a *{loc_label}*. Precios y servicios ajustados."
                if changed
                else "📍 Ya estabas con ese origen, sin cambios."
            )
        else:
            loc_label = "Cartagena" if origin == "cartagena" else "Rosario Islands"
            ack = (
                f"📍 Origin updated to *{loc_label}*. Prices and services adjusted."
                if changed
                else "📍 Already set to that origin, no changes."
            )
        if state.mixed_cart:
            return ack + "\n\n" + self._goto_mixed_cart_review(state)
        # A message answering something ELSE (here: location) while a question
        # is still pending must not silently skip past it — found live 2026-07-21:
        # "somos 4... queremos bucear" -> asks "¿estáis certificados?", customer
        # replies "desde cartagena" (never answers certification), the orchestrator
        # reads it as a location update, and this used to jump straight to the
        # generic add-activity menu, losing the certification question for good.
        if state.step in self._PENDING_QUESTION_STEPS:
            return ack + "\n\n" + self._ask_certification_message(state)
        if state.step == Step.MIXED_ADD_ACTIVITY:
            return ack + "\n\n" + self._goto_mixed_add_activity(state)
        return ack + "\n\n" + self._goto_mixed_entry(state)

    def orchestrator_remove_activity(self, state: ConversationState, activity_type: str) -> str | None:
        """Remove every cart item of `activity_type` directly (no pick menu).

        Returns the rendered response, or None if nothing matched.
        """
        items = [it for it in state.mixed_cart if it.get("type") == activity_type]
        if not items:
            return None
        label = items[0].get("label") or activity_type
        qty = sum(it.get("qty", 0) for it in items)
        state.mixed_cart = [it for it in state.mixed_cart if it.get("type") != activity_type]
        # Refresher is meaningless without the certified line it sits under.
        if activity_type == "cert":
            state.mixed_cart = [it for it in state.mixed_cart if it.get("type") != "refresh"]
        # Removing a beginner line changes kids-context — re-ask next checkout.
        if activity_type == "beginner":
            self._invalidate_kids_answer(state)
        lang = state.language
        ack = (
            f"✅ Quitado del carrito: {qty} × {label}"
            if lang == "es"
            else f"✅ Removed from cart: {qty} × {label}"
        )
        # Same rule as orchestrator_set_location: a still-pending question
        # (e.g. certification) must not be silently dropped just because the
        # customer's message resolved to an unrelated cart action.
        if state.step in self._PENDING_QUESTION_STEPS:
            return ack + "\n\n" + self._ask_certification_message(state)
        return ack + "\n\n" + self._goto_mixed_cart_review(state)

    # Steps where the customer already answered the initial "which plan"
    # question for the activity and is now mid-way through its sub-questions
    # or at the final preview — i.e. NOT a fresh "add an activity" moment.
    _MIXED_ACTIVITY_MID_FLOW_STEPS = {
        Step.MIXED_ADD_QTY,
        Step.MIXED_CERT_LAST_DIVE,
        Step.MIXED_CERT_REFRESH_INTEREST,
        Step.MIXED_CERT_REFRESH_QTY,
        Step.MIXED_CERT_SPLIT_REVIEW,
        Step.MIXED_ADD_PREVIEW,
    }

    def orchestrator_start_activity(self, state: ConversationState, activity_type: str) -> str | None:
        """Enter the add sub-flow for an activity, reusing _handle_mixed_add_activity.

        Regression guard (found live 2026-07-09): a follow-up question asked
        mid-flow ("vale y como reservo?" right after the final preview) was
        misclassified by the LLM tool-router as "start a new cert booking",
        and this unconditionally reset the flow back to the very first "which
        plan?" question — discarding the already-resolved plan/qty/last-dive
        answers. If we're already mid-way through resolving THIS SAME
        activity (past its initial plan question), treat a repeat
        start_activity as a no-op instead of restarting it, so the caller
        falls through to RAG and actually answers the question.
        """
        if activity_type == state.mixed_pending_qty_type and state.step in self._MIXED_ACTIVITY_MID_FLOW_STEPS:
            return None
        # Same rule as orchestrator_set_location/orchestrator_remove_activity:
        # a still-pending question (certification hasn't been answered yet)
        # must not be silently skipped by resetting into a different activity's
        # add-flow — re-ask it instead.
        if state.step in self._PENDING_QUESTION_STEPS:
            return self._ask_certification_message(state)
        choice_map = {"cert": "1", "beginner": "2", "snorkel": "3", "course": "4", "companion": "5"}
        choice = choice_map.get(activity_type)
        if choice is None:
            return None
        self._goto_mixed_add_activity(state)
        return self._handle_mixed_add_activity(state, choice)

    def orchestrator_add_to_cart(self, state: ConversationState, activity_type: str, qty: int) -> str | None:
        """Add `qty` of a simple activity (beginner/snorkel/companion) to the cart.

        For cert/course the plan must be chosen first, so we just start the
        sub-flow and let the existing prompts collect the remaining detail.
        """
        resp = self.orchestrator_start_activity(state, activity_type)
        if resp is None:
            return None
        if state.step == Step.MIXED_ADD_QTY and isinstance(qty, int) and qty > 0:
            return self._handle_mixed_add_qty(state, str(qty))
        return resp

    # ─── Final-question handlers ───

    def _invalidate_kids_answer(self, state: ConversationState) -> None:
        """Forget the previous kids answer (range + counts) so the question is re-asked.

        Invoked whenever the cart mutates in a way that may change the kids-age
        context (add/modify/remove a beginner line). The next checkout will
        re-ask via _needs_kids_question if the trigger condition still applies.
        """
        state.kids_age_group = None
        state.kids_count = None
        state.kids_under_8_count = 0
        state.kids_eight_to_ten_count = 0
        state.mixed_final_has_kids_8_10 = None

    def _needs_kids_question(self, state: ConversationState) -> bool:
        """Decide if we should ask about kids ages at the end of the cart-mixto.

        Trigger only when there's a real signal of minors in the booking:
        (a) cart contains minicurso (beginner) — ages matter for Bubble Makers, or
        (b) the speaker explicitly mentioned kids/family in free text.
        Snorkel-only and cert-only adult carts are not bothered with the question;
        the speaker can still surface "voy con mis hijos" any time and the detector
        catches it.
        """
        if state.kids_age_group is not None:
            return False  # ya respondida
        if self._cart_includes(state, "beginner"):
            return True
        return bool(getattr(state, "kids_mention_detected", False))


    def _goto_mixed_final_colombian(self, state: ConversationState) -> str:
        lang = state.language
        # Si ya conocemos la respuesta del flujo lineal previo (state.is_colombian),
        # la heredamos y saltamos directo a la siguiente pregunta para no
        # repetir la pregunta al cliente.
        if state.is_colombian is not None and state.mixed_final_is_colombian is None:
            state.mixed_final_is_colombian = state.is_colombian
            state.mixed_display_currency = "COP" if state.is_colombian else "USD"
            # We no longer proactively ask about a private boat — it goes straight
            # to the summary. If the client wants a private boat they can ask, and
            # RAG answers from the KB.
            return self._goto_mixed_final_summary(state)
        state.step = Step.MIXED_FINAL_COLOMBIAN
        self.set_quick_replies(state, "mixed_yes_no")
        return MESSAGES["mixed_final_colombian"][lang]















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





























    def _format_summary(self, state: ConversationState, final_prompt: str | None = None) -> str:
        """Format final summary with booking link."""
        service = SERVICES.get(state.selected_service)
        if not service:
            return MESSAGES["escalate"][state.language]

        lang = state.language
        name = service[f"name_{lang}"]
        service_id = state.selected_service
        flight_rule = service[f"flight_rule_{lang}"]
        contact_only = service.get("contact_only", False)
        accommodation_note = _accommodation_requirement_note(service_id, service, lang)

        if lang == "es":
            # Datos base
            if state.location == "cartagena":
                departure = "Cartagena"
                meeting_note = "⏰ Punto de encuentro: 8:00 AM en el Muelle de la Bodeguita."
            elif state.location == "island":
                # Mapeo de island_id a nombre de isla
                island_names = {
                    "isla_grande": "Isla Grande",
                    "isla_marina": "Isla Marina",
                    "isla_del_pirata": "Isla del Pirata",
                    "isla_del_sol": "Isla del Sol",
                    "isleta": "Isleta",
                    "isla_arena": "Isla Arena",
                    "isla_pavitos": "Isla Pavitos",
                    "isla_lizamar": "Isla Lizamar",
                    "isla_gigi": "Isla Gigi",
                    "isla_rosa": "Isla Rosa",
                    "isla_pelicano": "Isla Pelícano",
                    "isla_rosario": "Isla Rosario",
                }
                # Si tenemos isla específica, mostrarla; si no, mostrar genérico
                departure = island_names.get(state.island, "Islas del Rosario") if state.island else "Islas del Rosario"
                meeting_note = "⏰ Recogida en hotel: alrededor de 9:30 AM (si hay acceso marítimo)."
            else:
                departure = "Islas del Rosario"
                meeting_note = ""

            includes_raw = service.get("includes_es") or ""
            includes_items = [
                item.strip()
                for item in includes_raw.split(",")
                if item.strip()
            ]

            # Precio: COP para colombianos, USD para el resto (cuando haya datos)
            price_text = ""
            price_usd = service.get("price_usd")
            price_usd_normal = service.get("price_usd_normal")
            price_cop = service.get("price_cop")
            price_cop_normal = service.get("price_cop_normal")
            price_note = service.get("price_note_es") or service.get("price_note")
            summary_intro = service.get("summary_intro_es") or []

            def _fmt_cop(value):
                try:
                    return f"{int(value):,}".replace(",", ".")
                except (TypeError, ValueError):
                    return str(value)

            def _fmt_usd_es(value):
                try:
                    return str(int(round(float(value))))
                except (TypeError, ValueError):
                    return str(value)

            # Cantidad ya conocida (grupo detectado en texto libre o respondida
            # en la pregunta de cantidad) -> mostramos el total del grupo, no
            # solo el precio por persona.
            qty_for_price = state.mixed_pending_qty_value if (state.mixed_pending_qty_value or 0) > 1 else None

            if state.is_colombian and price_cop:
                if price_cop_normal:
                    normal_unit = f"{_fmt_cop(price_cop_normal)} COP"
                    discount_unit = f"{_fmt_cop(price_cop)} COP"
                    if qty_for_price:
                        normal_total = f"{_fmt_cop(price_cop_normal * qty_for_price)} COP"
                        discount_total = f"{_fmt_cop(price_cop * qty_for_price)} COP"
                        normal_line = f"{normal_unit} × {qty_for_price} = **{normal_total}**"
                        discount_line = f"{discount_unit} × {qty_for_price} = **{discount_total}**"
                    else:
                        normal_line = f"**{normal_unit}**"
                        discount_line = f"**{discount_unit}**"
                    price_text = (
                        f"💰 Precio:\n"
                        f"  • Tarifa normal\n"
                        f"    {normal_line}\n"
                        f"  • Reservando online **(10% off)**\n"
                        f"    {discount_line}"
                    )
                else:
                    price_text = f"💰 Precio: {_fmt_cop(price_cop)} COP"
            elif price_usd:
                if price_usd_normal:
                    normal_unit = f"${_fmt_usd_es(price_usd_normal)}"
                    discount_unit = f"${_fmt_usd_es(price_usd)}"
                    if qty_for_price:
                        normal_total = f"${_fmt_usd_es(price_usd_normal * qty_for_price)}"
                        discount_total = f"${_fmt_usd_es(price_usd * qty_for_price)}"
                        normal_line = f"{normal_unit} × {qty_for_price} = **{normal_total}**"
                        discount_line = f"{discount_unit} × {qty_for_price} = **{discount_total}**"
                    else:
                        normal_line = f"**{normal_unit}**"
                        discount_line = f"**{discount_unit}**"
                    price_text = (
                        f"💰 Precio:\n"
                        f"  • Tarifa normal\n"
                        f"    {normal_line}\n"
                        f"  • Reservando online **(10% off)**\n"
                        f"    {discount_line}"
                    )
                else:
                    price_text = f"💰 Precio: ${_fmt_usd_es(price_usd)}"
            elif price_note:
                price_text = f"💰 Precio: {price_note}"

            # Construimos línea a línea para controlar los espacios
            lines: list[str] = []
            lines.append("Perfecto! Aqui tienes el resumen:")
            lines.append("")
            lines.append(f"🤿 **Servicio: {service['name_es']}**")
            lines.append("")

            if price_text:
                lines.append(price_text)
                lines.append("")

            lines.append(f"⏱ Duracion: {service['duration_es']}")
            lines.append("")

            min_age = service.get("min_age")
            if min_age is not None:
                lines.append(f"👶 Edad mínima: {min_age} años")
                lines.append("")

            if service_id in {"minicourse", "minicourse_already_on_island"}:
                lines.append("ℹ️ Experiencia ideal si es tu primera vez buceando. No necesitas experiencia previa.")
                lines.append("")

            if summary_intro:
                for item in summary_intro:
                    lines.append(item)
                lines.append("")

            # Bloque incluye: con guiones por ítem (solo si hay items)
            if includes_items:
                lines.append("✅ Incluye:")
                for item in includes_items:
                    lines.append(f"  • {item}")

            # Espacio antes de la salida
            lines.append("")
            lines.append(f"📍 Salida: {departure}")
            if meeting_note:
                lines.append(meeting_note)

            # Nota de nocturna si aplica (paquetes con includes_night_dive o 3 buceos en 1 día)
            if service.get("includes_night_dive") or service_id in {"3_dives_1_day_already_on_island"}:
                lines.append("")
                lines.append(
                    "🌙 Incluye buceo nocturno con bioluminiscencia "
                    "(microorganismos marinos que brillan en la oscuridad)"
                )
            elif service.get("category") == "package":
                lines.append("")
                lines.append("🌙 Este paquete no incluye buceo nocturno")

            if accommodation_note:
                lines.append("")
                lines.append(accommodation_note)

            # Refresher y regla de vuelo, cada uno separado por una línea en blanco
            if flight_rule or state.refresher_interested:
                lines.append("")

            if state.refresher_interested:
                lines.append(
                    "🧑‍🏫 Refresher: Sí (recomendado por inactividad) — sin coste adicional, "
                    "el guía adapta la inmersión a tu nivel"
                )

            if flight_rule:
                lines.append(f"✈️ Importante: {flight_rule}")

            if service_id in {"minicourse", "minicourse_already_on_island"}:
                lines.append(
                    "📘 Incluye teoría online: después de reservar recibirás un correo con instrucciones para completar la teoría. Es indispensable terminarla antes de comenzar la práctica."
                )

            # Notas extra (no se muestran para 2_dives_1_day en el resumen)
            extra_notes = service.get("extra_notes_es")
            # Para paquetes multi-dia, simplificamos la nota extra para enfatizar solo
            # que el alojamiento no esta incluido.
            if service_id in MULTI_DAY_SERVICES or service_id == "3_dives_1_day":
                not_included_es = service.get("not_included_es", [])
                if service_id == "3_dives_1_day" or any("Hotel/alojamiento" in item for item in not_included_es):
                    extra_notes = "El alojamiento no esta incluido."
            elif service_id in {"minicourse", "minicourse_already_on_island"}:
                extra_notes = ""
            elif state.location == "island" and service_id and service_id.endswith("_already_on_island"):
                extra_notes = "El alojamiento no esta incluido."
            if extra_notes and service_id != "2_dives_1_day" and not _is_padi_course_service(service_id):
                lines.append("")
                lines.append(f"ℹ️ {extra_notes}")

            lines.append("")

            # El link de RESERVA (con el 10% online) se sigue enviando solo al
            # confirmar, ya que depende de si el cliente es colombiano o no
            # (pago 50/50 vs. link directo). El link INFORMATIVO (web_url) sí
            # es seguro mostrarlo aquí siempre — mismo contenido para todos.
            if contact_only:
                lines.append("🔗 Más información del programa:")
                lines.append(service["web_url"])
                lines.append("")
                lines.append(_divemaster_itinerary_offer_prompt(lang))
            else:
                lines.append(
                    f"👉 Si quieres más información y reservar, puedes acceder directamente al link:\n{service['web_url']}"
                )
                lines.append("")
                lines.append(final_prompt or "¿Qué te gustaría hacer?")

            summary = "\n".join(lines)
        else:
            # English
            if state.location == "cartagena":
                departure = "Cartagena"
                meeting_note = "\n⏰ Meeting point: 8:00 AM at Muelle de la Bodeguita."
            elif state.location == "island":
                # Mapeo de island_id a nombre de isla en inglés
                island_names_en = {
                    "isla_grande": "Isla Grande",
                    "isla_marina": "Isla Marina",
                    "isla_del_pirata": "Isla del Pirata",
                    "isla_del_sol": "Isla del Sol",
                    "isleta": "Isleta",
                    "isla_arena": "Isla Arena",
                    "isla_pavitos": "Isla Pavitos",
                    "isla_lizamar": "Isla Lizamar",
                    "isla_gigi": "Isla Gigi",
                    "isla_rosa": "Isla Rosa",
                    "isla_pelicano": "Isla Pelícano",
                    "isla_rosario": "Isla Rosario",
                }
                # Si tenemos isla específica, mostrarla; si no, mostrar genérico
                departure = island_names_en.get(state.island, "Rosario Islands") if state.island else "Rosario Islands"
                meeting_note = "\n⏰ Hotel pickup: around 9:30 AM (if there is sea access)."
            else:
                departure = "Rosario Islands"
                meeting_note = ""

            includes_raw = service.get("includes_en") or ""
            includes_items = [
                item.strip()
                for item in includes_raw.split(",")
                if item.strip()
            ]
            includes_block = "\n".join(f"  • {item}" for item in includes_items)

            min_age = service.get("min_age")
            min_age_line = f"\n👶 *Minimum age*: {min_age} years" if min_age is not None else ""

            # Price line: show COP for Colombians, otherwise USD; fall back to price_note if present
            price_usd = service.get("price_usd")
            price_usd_normal = service.get("price_usd_normal")
            price_cop = service.get("price_cop")
            price_cop_normal = service.get("price_cop_normal")
            price_note = service.get("price_note_en") or service.get("price_note")
            summary_intro = service.get("summary_intro_en") or []

            def _fmt_cop_en(value):
                try:
                    return f"{int(value):,}"
                except (TypeError, ValueError):
                    return str(value)
            def _fmt_usd_en(value):
                try:
                    return str(int(round(float(value))))
                except (TypeError, ValueError):
                    return str(value)

            qty_for_price = state.mixed_pending_qty_value if (state.mixed_pending_qty_value or 0) > 1 else None

            price_line = ""
            if state.is_colombian and price_cop:
                if price_cop_normal:
                    normal_unit = f"{_fmt_cop_en(price_cop_normal)} COP"
                    discount_unit = f"{_fmt_cop_en(price_cop)} COP"
                    if qty_for_price:
                        normal_total = f"{_fmt_cop_en(price_cop_normal * qty_for_price)} COP"
                        discount_total = f"{_fmt_cop_en(price_cop * qty_for_price)} COP"
                        normal_line = f"{normal_unit} × {qty_for_price} = **{normal_total}**"
                        discount_line = f"{discount_unit} × {qty_for_price} = **{discount_total}**"
                    else:
                        normal_line = f"**{normal_unit}**"
                        discount_line = f"**{discount_unit}**"
                    price_line = (
                        f"\n💰 **Price**:\n"
                        f"  • Standard rate\n"
                        f"    {normal_line}\n"
                        f"  • Booking online **(10% off)**\n"
                        f"    {discount_line}"
                    )
                else:
                    price_line = f"\n💰 **Price**: {_fmt_cop_en(price_cop)} COP"
            elif price_usd:
                if price_usd_normal:
                    normal_unit = f"${_fmt_usd_en(price_usd_normal)}"
                    discount_unit = f"${_fmt_usd_en(price_usd)}"
                    if qty_for_price:
                        normal_total = f"${_fmt_usd_en(price_usd_normal * qty_for_price)}"
                        discount_total = f"${_fmt_usd_en(price_usd * qty_for_price)}"
                        normal_line = f"{normal_unit} × {qty_for_price} = **{normal_total}**"
                        discount_line = f"{discount_unit} × {qty_for_price} = **{discount_total}**"
                    else:
                        normal_line = f"**{normal_unit}**"
                        discount_line = f"**{discount_unit}**"
                    price_line = (
                        f"\n💰 **Price**:\n"
                        f"  • Standard rate\n"
                        f"    {normal_line}\n"
                        f"  • Booking online **(10% off)**\n"
                        f"    {discount_line}"
                    )
                else:
                    price_line = f"\n💰 **Price**: ${_fmt_usd_en(price_usd)}"
            elif price_note:
                price_line = f"\n💰 **Price**: {price_note}"

            summary_intro_block = ""
            if summary_intro:
                summary_intro_block = "\n" + "\n".join(summary_intro) + "\n"

            includes_block_full = f"✅ *Includes*:\n{includes_block}\n\n" if includes_items else ""
            summary = (
                "Perfect! Here's your summary:\n\n"
                f"🤿 *Service*: {name}\n"
                f"⏱ *Duration*: {service['duration_en']}"
                f"{price_line}"
                f"{min_age_line}\n"
                f"{summary_intro_block}"
                f"{includes_block_full}"
                f"📍 *Departure*: {departure}"
                f"{meeting_note}\n"
            )

            # Night-dive note if applicable
            if service.get("includes_night_dive") or service_id in {"3_dives_1_day_already_on_island"}:
                summary += (
                    "\n🌙 Includes a night dive with bioluminescence "
                    "(marine microorganisms that glow in the dark)\n"
                )
            elif service.get("category") == "package":
                summary += "\n🌙 This package does not include a night dive\n"

            if accommodation_note:
                summary += f"\n{accommodation_note}\n"

            if state.refresher_interested:
                summary += (
                    "\n🧑‍🏫 Refresher: Yes (recommended due to inactivity) — no extra cost, "
                    "the guide adapts the dive to your level\n"
                )

            if flight_rule:
                summary += f"\n✈️ *Important*: {flight_rule}\n"

            extra_notes = service.get("extra_notes_en")
            if service_id in MULTI_DAY_SERVICES or service_id == "3_dives_1_day":
                not_included_en = service.get("not_included_en", [])
                if service_id == "3_dives_1_day" or any("Hotel/accommodation" in item for item in not_included_en):
                    extra_notes = "Accommodation on the islands is not included."
            if extra_notes and not _is_padi_course_service(service_id):
                summary += f"\nℹ️ {extra_notes}\n"

            # The BOOKING link (10% online) is still only sent on confirm, since
            # it depends on whether the client is Colombian or not (50/50
            # payment vs. direct link). The INFO link (web_url) is safe to
            # always show here — same content for everyone.
            if contact_only:
                summary += f"\n🔗 *Program info*:\n{service['web_url']}\n"
                summary += "\n" + _divemaster_itinerary_offer_prompt(lang)
            else:
                summary += f"\n👉 For more information and to book, you can go directly to the link:\n{service['web_url']}\n"
                summary += "\n" + (final_prompt or "What would you like to do?")

        return summary

