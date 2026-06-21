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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from src.utils.fuzzy import is_back, is_affirmative, is_negative, is_agree, is_none_selection, fuzzy_word_number


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
    mixed_pending_modify_idx: int | None = None  # cart index when editing an item
    mixed_pending_modify_refresh: bool = False   # cert qty just changed → re-ask refresher
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
    detected_activity: str | None = None
    detected_service_id: str | None = None
    detected_is_certified: bool | None = None
    detected_group_size: int | None = None
    detected_group_allocation: dict | None = None
    detected_last_dive_over_2_years: bool | None = None
    detected_duration: str | None = None
    detected_location: str | None = None
    detected_island: str | None = None
    detected_hotel: str | None = None
    # Low-confidence intent detection (0.2 < confidence < 0.30): awaiting a
    # yes/no confirmation from the user before applying it (Capa 3, typo plan).
    pending_intent_confirmation: object | None = None

    def __post_init__(self):
        if self.history is None:
            self.history = []


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


def _divemaster_follow_up_prompt(lang: str) -> str:
    if lang == "es":
        return "¿Quieres contactar con nuestro jefe para solicitar el curso de Dive Master?"
    return "Would you like to contact our manager to request the Dive Master course?"


def _referral_escalation_message(state: "ConversationState") -> str:
    lang = state.language

    if lang == "es":
        # El asesor envía el link de pago tras revisar el caso (patrón unificado).
        return (
            "Genial que ya hayas empezado tu curso. Para completar un referral/reactivate en Diving Planet "
            "necesitamos revisar tu eLearning y formularios PADI, y ver cuantas inmersiones te faltan.\n\n"
            "Te paso con un asesor para que te indique exactamente que documentos traer, como funciona el precio "
            "en tu caso y te envie el link para completar la reserva.\n\n"
            + MESSAGES["escalate"][lang]
        )

    return (
        "Great that you already started your course. To finish a referral/reactivate with Diving Planet we "
        "need to review your eLearning and PADI forms, and see how many dives you still need.\n\n"
        "I will transfer you to an advisor so they can tell you exactly which documents to bring, how pricing "
        "works in your case, and send you the link to complete the booking.\n\n"
        + MESSAGES["escalate"][lang]
    )


def _resolve_service_booking_url(service: dict, state: "ConversationState") -> str | None:
    """Pick the right booking link for the service's catalog entry given location."""
    if state.location == "island" and service.get("booking_url_island"):
        return service["booking_url_island"]
    return service.get("booking_url")


def _format_booking_links_block(links: list[tuple[str, str]], lang: str) -> str:
    return "\n".join(f"🔗 *{label}*: {url}" for label, url in links)


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


def _group_itinerary_by_day(itinerary: list[str], lang: str) -> list[str]:
    """Group raw itinerary lines by day so we show 'Dia 1:' / 'Day 1:' once
    and then the steps beneath it, instead of repeating the day prefix on
    every line.
    """
    grouped: list[str] = []
    current_day_label = None
    day_prefix = "dia " if lang == "es" else "day "

    for item in itinerary:
        stripped = item.strip()
        lowered = stripped.lower()
        if lowered.startswith(day_prefix):
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                day_label_raw, rest = parts
                day_label = day_label_raw.strip()
                if current_day_label != day_label:
                    grouped.append(f"{day_label}:")
                    current_day_label = day_label
                rest = rest.strip()
                if rest:
                    grouped.append(rest)
                continue
        grouped.append(item)

    return grouped


def _info_itinerary_line_prefix(item: str, lang: str) -> str | None:
    lowered = item.strip().lower()
    if lang == "es":
        if lowered.startswith("dia ") and lowered.endswith(":"):
            return "📅 "
        if "punto de encuentro" in lowered or "muelle" in lowered:
            return "📍 "
        if "traslado" in lowered or "lancha" in lowered:
            return "🚤 "
        if "equipo" in lowered or "base" in lowered or "bienvenida" in lowered:
            return "🤿 "
        if "inmersion" in lowered or "inmersiones" in lowered or "arrecif" in lowered:
            return "🐠 "
        if "almuerzo" in lowered or "comida" in lowered:
            return "🍽️ "
        if "regreso" in lowered or "retorno" in lowered:
            return "↩️ "
        return "- "

    if lowered.startswith("day ") and lowered.endswith(":"):
        return "📅 "
    if "meeting point" in lowered or "dock" in lowered or "pier" in lowered:
        return "📍 "
    if "transfer" in lowered or "speedboat" in lowered or "boat" in lowered:
        return "🚤 "
    if "equipment" in lowered or "base" in lowered or "welcome" in lowered:
        return "🤿 "
    if "dive" in lowered or "dives" in lowered or "reef" in lowered:
        return "🐠 "
    if "lunch" in lowered or "meal" in lowered:
        return "🍽️ "
    if "return" in lowered:
        return "↩️ "
    return "- "


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
            "Hola! Bienvenido a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 años de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "Selecciona tu idioma / Select your language:\n\n"
            "🌎 Español\n"
            "🌐 English"
        ),
        "en": (
            "Hello! Welcome to *Diving Planet*, Colombia's first "
            "PADI 5 Star Dive Center, with 30 years of experience in "
            "the Rosario Islands, Cartagena.\n\n"
            "Select your language / Selecciona tu idioma:\n\n"
            "🌎 Español\n"
            "🌐 English"
        ),
    },
    "main_menu": {
        "es": (
            "¿Qué te gustaría hacer?"
        ),
        "en": (
            "What would you like to do?"
        ),
    },
    "welcome_detected": {
        "es": (
            "Hola! Bienvenido a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 años de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "¿Qué te gustaría hacer?"
        ),
        "en": (
            "Hello! Welcome to *Diving Planet*, Colombia's first "
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
            "Antes de añadir actividades, dime desde dónde tomarán la salida."
        ),
        "en": (
            "Before adding activities, tell me where you will depart from."
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
    "mixed_add_qty": {
        "es": "¿Para *cuántas personas*?",
        "en": "For *how many people*?",
    },
    "mixed_add_preview": {
        "es": "¿Quieres *añadir esta actividad al carrito* o ver primero el itinerario completo?",
        "en": "Would you like to *add this activity to the cart* or view the full itinerary first?",
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
        "es": "Para terminar, ¿eres *colombiano/a o residente en Colombia*? (aplica descuento)",
        "en": "Last few questions: are you *Colombian / resident in Colombia*? (discount applies)",
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
            "Desde donde tomaras el tour?"
        ),
        "en": (
            "Where will you depart from?"
        ),
    },
    "colombian": {
        "es": (
            "🌎 ¿Eres colombiano/a? Tenemos descuentos especiales para locales."
        ),
        "en": (
            "🌎 Are you Colombian? We have special discounts for locals."
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
            "No entendi tu respuesta. Por favor, selecciona una de las opciones."
        ),
        "en": (
            "I didn't understand your response. Please select one of the options."
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
            {"title": "🛒 Añadir al carrito", "value": "1"},
            {"title": "🗺️ Ver itinerario completo", "value": "itinerary"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🛒 Add to cart", "value": "1"},
            {"title": "🗺️ View full itinerary", "value": "itinerary"},
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
            {"title": "🇨🇴 Descuentos para colombianos/residentes", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🚤 Prices departing from Cartagena", "value": "1"},
            {"title": "🏝️ Prices if I'm already on the islands", "value": "2"},
            {"title": "📦 5/7/9-dive multi-day packages", "value": "3"},
            {"title": "🇨🇴 Discounts for Colombians/residents", "value": "4"},
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

    def set_quick_replies(self, state: ConversationState, key: str):
        if key == "tours_certified" and state.location == "island":
            state.quick_replies = self._island_certified_options(state.language)
            return
        if key == "info_tours_certified_menu" and state.location == "island":
            state.quick_replies = self._info_island_certified_options(state.language)
            return
        if key == "mixed_add_cert_multi_day" and state.location == "island":
            state.quick_replies = self._mixed_island_certified_multiday_options(state.language)
            return
        if key == "mixed_add_activity" and state.mixed_entry_path == "cert_beg":
            # Filtramos snorkel cuando entran por la rama de certificados + principiantes.
            options = [
                opt for opt in get_button_options(key, state.language)
                if opt.get("value") != "3"
            ]
            state.quick_replies = options
            return
        state.quick_replies = get_button_options(key, state.language)

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

    def _set_back_target(self, state: ConversationState, step: Step, quick_replies_key: str):
        state.back_step_override = step
        state.back_quick_replies_key = quick_replies_key

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

    def _summary_quick_replies_key(self, state: ConversationState) -> str:
        service_id = state.selected_service
        if service_id in {"referral", "referral_already_on_island"}:
            return "summary_referral"
        if _is_contact_only_service(service_id):
            return "summary_contact"
        return "summary"

    def _itinerary_offer_quick_replies_key(self, state: ConversationState) -> str:
        if _is_contact_only_service(state.selected_service):
            return "itinerary_offer_contact"
        return "itinerary_offer"

    @staticmethod
    def _back_to_menu_hint(lang: str) -> str:
        """Closing line shown after an info-tree leaf so users see they can switch branches."""
        if lang == "es":
            return (
                "\n\n¿Quieres *reservar* ahora o seguir consultando *información*? "
                "También puedes escribir tu pregunta."
            )
        return (
            "\n\nWould you like to *book* now or keep checking *information*? "
            "You can also type your question."
        )

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

    def process_message(self, state: ConversationState, message: str) -> str:
        """Process a user message and return the bot's response."""
        message = message.strip()
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})

        response = self._route(state, message)

        state.history.append({"role": "assistant", "content": response})
        return response

    def _route(self, state: ConversationState, message: str) -> str:
        """Route to the appropriate handler based on current step."""
        handlers = {
            Step.WELCOME: self._handle_welcome,
            Step.LANGUAGE: self._handle_language,
            Step.MAIN_MENU: self._handle_main_menu,
            Step.RESERVA_MENU: self._handle_reserva_menu,
            Step.INFO_MENU: self._handle_info_menu,
            Step.INFO_ACTIVITY_LOCATION: self._handle_info_activity_location,
            Step.INFO_ACTIVITIES_MENU: self._handle_info_activities_menu,
            Step.INFO_TOURS_MENU: self._handle_info_tours_menu,
            Step.INFO_PACKAGES_MENU: self._handle_info_packages_menu,
            Step.INFO_COURSES_MENU: self._handle_info_courses_menu,
            Step.INFO_SPECIALTIES_MENU: self._handle_info_specialties_menu,
            Step.INFO_TOUR_DETAIL: self._handle_info_tour_detail,
            Step.INFO_PACKAGE_DETAIL: self._handle_info_package_detail,
            Step.INFO_COURSE_DETAIL: self._handle_info_course_detail,
            Step.INFO_SPECIALTY_DETAIL: self._handle_info_specialty_detail,
            Step.INFO_TOURS_CERTIFIED_MENU: self._handle_info_tours_certified_menu,
            Step.INFO_COURSES_ADVANCED_MENU: self._handle_info_courses_advanced_menu,
            Step.INFO_MIXED_ACTIVITY_MENU: self._handle_info_mixed_activity_menu,
            Step.INFO_MIXED_CERT_BEG_MENU: self._handle_info_mixed_cert_beg_menu,
            Step.INFO_CERTIFIED_4_DIVES_VARIANT: self._handle_info_certified_4_dives_variant,
            # Flujo antiguo eliminado - ahora todo va por el carrito (MIXED_*)
            Step.COURSES_MENU: self._handle_courses_menu,
            Step.COURSES_OPEN_WATER_ORIGIN: self._handle_courses_open_water_origin,
            Step.COURSES_OPEN_WATER_TIME: self._handle_courses_open_water_time,
            Step.COURSES_ADVANCED_MENU: self._handle_courses_advanced_menu,
            Step.COURSES_SPECIALTIES_MENU: self._handle_courses_specialties_menu,
            Step.PRICING_COLOMBIAN: self._handle_pricing_colombian,
            Step.MIXED_ENTRY: self._handle_mixed_entry,
            Step.MIXED_LOCATION: self._handle_mixed_location,
            Step.MIXED_ASK_CERTIFICATION: self._handle_mixed_ask_certification,
            Step.MIXED_ASK_CERT_COUNT: self._handle_mixed_ask_cert_count,
            Step.MIXED_ASK_BEGINNER_ACTIVITY: self._handle_mixed_ask_beginner_activity,
            Step.MIXED_ADD_ACTIVITY: self._handle_mixed_add_activity,
            Step.MIXED_ADD_CERT_PLAN: self._handle_mixed_add_cert_plan,
            Step.MIXED_ADD_CERT_MULTI_DAY: self._handle_mixed_add_cert_multi_day,
            Step.MIXED_ADD_QTY: self._handle_mixed_add_qty,
            Step.MIXED_CERT_LAST_DIVE: self._handle_mixed_cert_last_dive,
            Step.MIXED_CERT_REFRESH_INTEREST: self._handle_mixed_cert_refresh_interest,
            Step.MIXED_CERT_REFRESH_QTY: self._handle_mixed_cert_refresh_qty,
            Step.MIXED_CERT_SPLIT_REVIEW: self._handle_mixed_cert_split_review,
            Step.MIXED_ADD_PREVIEW: self._handle_mixed_add_preview,
            Step.MIXED_CART_REVIEW: self._handle_mixed_cart_review,
            Step.MIXED_CART_MODIFY_PICK: self._handle_mixed_cart_modify_pick,
            Step.MIXED_CART_REMOVE_PICK: self._handle_mixed_cart_remove_pick,
            Step.MIXED_CART_LOCATION: self._handle_mixed_cart_location,
            Step.MIXED_FINAL_COLOMBIAN: self._handle_mixed_final_colombian,
            Step.MIXED_FINAL_KIDS: self._handle_mixed_final_kids,
            Step.MIXED_FINAL_KIDS_QTY: self._handle_mixed_final_kids_qty,
            Step.MIXED_FINAL_KIDS_U8: self._handle_mixed_final_kids_u8,
            Step.MIXED_FINAL_KIDS_810: self._handle_mixed_final_kids_810,
            Step.MIXED_FINAL_PRIVATE: self._handle_mixed_final_private,
            Step.MIXED_FINAL_SUMMARY: self._handle_mixed_final_summary,
            Step.PRICING_MENU: self._handle_pricing_menu,
            Step.PRICING_CARTAGENA: self._handle_pricing_cartagena,
            Step.PRICING_ISLANDS: self._handle_pricing_islands,
            Step.PRICING_PACKAGES: self._handle_pricing_packages,
            Step.PRICING_DISCOUNTS: self._handle_pricing_discounts,
            Step.BOOKING_MENU: self._handle_booking_menu,
            Step.LOGISTICS_MENU: self._handle_logistics_menu,
            Step.LOGISTICS_MEETING: self._handle_logistics_meeting,
            Step.LOGISTICS_INCLUDES: self._handle_logistics_includes,
            Step.LOGISTICS_WHAT_TO_BRING: self._handle_logistics_what_to_bring,
            Step.ISLAND_MENU: self._handle_island_menu,
            Step.ISLAND_HOTEL_MENU: self._handle_island_hotel_menu,
            Step.SERVICE_DETAIL: self._handle_service_detail,
            Step.LOCATION: self._handle_location,
            Step.COLOMBIAN: self._handle_colombian,
            Step.SUMMARY: self._handle_summary,
        }

        handler = handlers.get(state.step, self._handle_welcome)
        return handler(state, message)

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

    def _handle_welcome(self, state: ConversationState, message: str) -> str:
        # If the very first message already signals a language ("hola" / "hello" /
        # "hi" / "español" / "english"...), skip the language question entirely
        # instead of asking something the user already answered implicitly.
        detected_language = _detect_language_from_text(message)
        if detected_language:
            state.language = detected_language
            state.step = Step.MAIN_MENU
            self.set_quick_replies(state, "main_menu")
            return MESSAGES["welcome_detected"][detected_language]

        state.step = Step.LANGUAGE
        self.set_quick_replies(state, "welcome")
        return MESSAGES["welcome"]["es"]

    def _handle_language(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        if choice == 1:
            state.language = "es"
        elif choice == 2:
            state.language = "en"
        else:
            detected_language = _detect_language_from_text(message)
            if not detected_language:
                self.set_quick_replies(state, "welcome")
                return MESSAGES["not_understood"]["es"]
            state.language = detected_language

        state.step = Step.MAIN_MENU
        self.set_quick_replies(state, "main_menu")
        return MESSAGES["main_menu"][state.language]

    def _enter_booking_cart(
        self,
        state: ConversationState,
        back_step: Step = Step.MAIN_MENU,
        back_quick_replies_key: str = "main_menu",
    ) -> str:
        self._reset_mixed_state(state)
        state.mixed_entry_path = "booking"
        self._set_back_target(state, back_step, back_quick_replies_key)
        state.step = Step.MIXED_ENTRY
        self.set_quick_replies(state, "mixed_entry")
        return MESSAGES["mixed_entry"][state.language]

    def _handle_main_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if state.history is None:
            state.history = []

        if choice == 1:
            return self._enter_booking_cart(state)
        if choice == 2:
            # Información: precios / reservas y pago / logística
            state.step = Step.INFO_MENU
            self.set_quick_replies(state, "info_menu")
            return MESSAGES["info_menu"][lang]

        self.set_quick_replies(state, "main_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_reserva_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 1)
        if choice == 1:
            return self._enter_booking_cart(state)
        self.set_quick_replies(state, "reserva_menu")
        return MESSAGES["not_understood"][state.language]

    def _handle_info_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice == 1:
            if state.location is None:
                state.step = Step.INFO_ACTIVITY_LOCATION
                self.set_quick_replies(state, "info_activity_location")
                return MESSAGES["info_activity_location"][lang]
            state.step = Step.INFO_ACTIVITIES_MENU
            self.set_quick_replies(state, "info_activities_menu")
            return MESSAGES["info_activities_menu"][lang]
        if choice == 2:
            if state.is_colombian is None:
                state.step = Step.PRICING_COLOMBIAN
                self.set_quick_replies(state, "colombian")
                return MESSAGES["colombian"][lang]
            state.step = Step.PRICING_MENU
            self.set_quick_replies(state, "pricing_menu")
            return MESSAGES["pricing_menu"][lang]
        if choice == 3:
            state.step = Step.BOOKING_MENU
            self.set_quick_replies(state, "booking_menu")
            return MESSAGES["booking_menu"][lang]
        if choice == 4:
            state.step = Step.LOGISTICS_MENU
            self.set_quick_replies(state, "logistics_menu")
            return MESSAGES["logistics_menu"][lang]

        self.set_quick_replies(state, "info_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_activity_location(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.location = "cartagena"
        elif choice == 2:
            state.location = "island"
        else:
            self.set_quick_replies(state, "info_activity_location")
            return MESSAGES["not_understood"][lang]

        state.step = Step.INFO_ACTIVITIES_MENU
        self.set_quick_replies(state, "info_activities_menu")
        return MESSAGES["info_activities_menu"][lang]

    def _handle_info_activities_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.step = Step.INFO_TOURS_MENU
            self.set_quick_replies(state, "info_tours_menu")
            return MESSAGES["info_tours_menu"][lang]
        if choice == 2:
            state.step = Step.INFO_COURSES_MENU
            self.set_quick_replies(state, "info_courses_menu")
            return MESSAGES["info_courses_menu"][lang]

        self.set_quick_replies(state, "info_activities_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_tours_menu(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 2)
        if choice is None:
            self.set_quick_replies(state, "info_tours_menu")
            return MESSAGES["not_understood"][lang]

        if choice == 1:
            state.step = Step.INFO_PACKAGES_MENU
            self.set_quick_replies(state, "info_packages_menu")
            return MESSAGES["info_packages_menu"][lang]
        if choice == 2:
            return self._show_info_service(
                state,
                self._service_for_location("snorkeling", state),
                Step.INFO_TOURS_MENU,
                "info_tours_menu",
            )

        self.set_quick_replies(state, "info_tours_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_packages_menu(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 2)
        if choice is None:
            self.set_quick_replies(state, "info_packages_menu")
            return MESSAGES["not_understood"][lang]

        if choice == 1:
            state.step = Step.INFO_TOURS_CERTIFIED_MENU
            self.set_quick_replies(state, "info_tours_certified_menu")
            return MESSAGES["info_tours_certified_menu"][lang]
        if choice == 2:
            return self._show_info_service(
                state,
                self._service_for_location("minicourse", state),
                Step.INFO_PACKAGES_MENU,
                "info_packages_menu",
            )

        self.set_quick_replies(state, "info_packages_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_tours_certified_menu(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 7)
        if choice is None:
            self.set_quick_replies(state, "info_tours_certified_menu")
            return MESSAGES["not_understood"][lang]

        if state.location == "island":
            service_map = {
                1: "2_dives_1_day_already_on_island",
                2: "3_dives_1_day_already_on_island",
                4: "5_dives_2_days_already_on_island",
                5: "7_dives_3_days_already_on_island",
                6: "9_dives_4_days_already_on_island",
                7: "private",
            }
        else:
            service_map = {
                1: "2_dives_1_day",
                2: "3_dives_1_day",
                3: "4_dives_2_days",
                4: "5_dives_2_days",
                5: "7_dives_3_days",
                6: "9_dives_4_days",
                7: "private",
            }

        if state.location == "island" and choice == 3:
            state.step = Step.INFO_CERTIFIED_4_DIVES_VARIANT
            self.set_quick_replies(state, "info_certified_4_dives_variant")
            return MESSAGES["info_certified_4_dives_variant"][lang]

        if choice not in service_map:
            self.set_quick_replies(state, "info_tours_certified_menu")
            return MESSAGES["not_understood"][lang]

        return self._show_info_service(
            state,
            service_map[choice],
            Step.INFO_TOURS_CERTIFIED_MENU,
            "info_tours_certified_menu",
        )

    def _handle_info_courses_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice == 1:
            return self._show_info_service(
                state,
                self._service_for_location("open_water", state),
                Step.INFO_COURSES_MENU,
                "info_courses_menu",
            )
        if choice == 2:
            state.step = Step.INFO_COURSES_ADVANCED_MENU
            self.set_quick_replies(state, "info_courses_advanced_menu")
            return MESSAGES["info_courses_advanced_menu"][lang]
        if choice == 3:
            state.step = Step.INFO_SPECIALTIES_MENU
            self.set_quick_replies(state, "info_specialties_menu")
            return MESSAGES["info_specialties_menu"][lang]
        if choice == 4:
            return self._show_info_service(
                state,
                self._service_for_location("referral", state),
                Step.INFO_COURSES_MENU,
                "info_courses_menu",
            )

        self.set_quick_replies(state, "info_courses_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_courses_advanced_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language

        service_map = {
            1: self._service_for_location("advanced", state),
            2: "rescue",
            3: "divemaster",
        }

        if choice not in service_map:
            self.set_quick_replies(state, "info_courses_advanced_menu")
            return MESSAGES["not_understood"][lang]

        return self._show_info_service(
            state,
            service_map[choice],
            Step.INFO_COURSES_ADVANCED_MENU,
            "info_courses_advanced_menu",
        )

    def _handle_info_specialties_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 5)
        lang = state.language

        service_map = {
            1: "mindful_diving",
            2: self._service_for_location("fish_identification_specialty", state),
            3: self._service_for_location("naturalist_specialty", state),
            4: self._service_for_location("buoyancy_specialty", state),
            5: self._service_for_location("nitrox_specialty", state),
        }

        if choice not in service_map:
            self.set_quick_replies(state, "info_specialties_menu")
            return MESSAGES["not_understood"][lang]

        return self._show_info_service(
            state,
            service_map[choice],
            Step.INFO_SPECIALTIES_MENU,
            "info_specialties_menu",
        )

    def _handle_info_mixed_activity_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language

        if choice == 1:
            state.step = Step.INFO_TOURS_CERTIFIED_MENU
            self.set_quick_replies(state, "info_tours_certified_menu")
            return MESSAGES["info_tours_certified_menu"][lang]
        if choice == 2:
            return self._show_info_service(
                state,
                self._service_for_location("minicourse", state),
                Step.INFO_MIXED_ACTIVITY_MENU,
                "info_mixed_activity_menu",
            )
        if choice == 3:
            return self._show_info_service(
                state,
                self._service_for_location("snorkeling", state),
                Step.INFO_MIXED_ACTIVITY_MENU,
                "info_mixed_activity_menu",
            )

        self.set_quick_replies(state, "info_mixed_activity_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_mixed_cert_beg_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.step = Step.INFO_TOURS_CERTIFIED_MENU
            self.set_quick_replies(state, "info_tours_certified_menu")
            return MESSAGES["info_tours_certified_menu"][lang]
        if choice == 2:
            return self._show_info_service(
                state,
                self._service_for_location("minicourse", state),
                Step.INFO_MIXED_CERT_BEG_MENU,
                "info_mixed_cert_beg_menu",
            )

        self.set_quick_replies(state, "info_mixed_cert_beg_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_certified_4_dives_variant(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            service_id = "4_dives_2_days_already_on_island"
        elif choice == 2:
            service_id = "4_dives_2_days_mixed_already_on_island"
        else:
            self.set_quick_replies(state, "info_certified_4_dives_variant")
            return MESSAGES["not_understood"][lang]

        return self._show_info_service(
            state,
            service_id,
            Step.INFO_CERTIFIED_4_DIVES_VARIANT,
            "info_certified_4_dives_variant",
        )

    def _show_info_service(self, state: ConversationState, service_id: str, back_step: Step, back_quick_replies_key: str) -> str:
        service = SERVICES.get(service_id)
        if not service:
            state.step = Step.INFO_MENU
            self.set_quick_replies(state, "info_menu")
            return MESSAGES["info_menu"][state.language]

        category = service.get("category")
        if category == "course":
            detail_step = Step.INFO_COURSE_DETAIL
        elif category == "specialty":
            detail_step = Step.INFO_SPECIALTY_DETAIL
        elif category == "package":
            detail_step = Step.INFO_PACKAGE_DETAIL
        else:
            detail_step = Step.INFO_TOUR_DETAIL

        state.selected_service = service_id
        self._set_back_target(state, back_step, back_quick_replies_key)
        state.step = detail_step
        self.set_quick_replies(state, "info_detail_actions")
        return self._format_info_card(state)

    def _info_detail_book_action(self, state: ConversationState) -> str:
        lang = state.language
        service_id = state.selected_service
        service = SERVICES.get(service_id)
        if not service:
            state.step = Step.INFO_MENU
            self.set_quick_replies(state, "info_menu")
            return MESSAGES["info_menu"][lang]

        contact_only = bool(service.get("contact_only", False))
        if contact_only or service_id in {"referral", "referral_already_on_island"}:
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "solicitó contacto desde información"
            if lang == "es":
                return "Perfecto. Para este caso, te paso con un asesor.\n\n" + MESSAGES["escalate"][lang]
            return "Perfect. For this case, I'll connect you with an advisor.\n\n" + MESSAGES["escalate"][lang]

        # Route into the booking cart, jumping to the deepest point we can reach
        # given what we already know from the info card the user just read.
        cart_type = SERVICE_TO_CART_TYPE.get(service_id)
        self._reset_mixed_state(state)
        state.mixed_entry_path = "booking"
        self._set_back_target(state, Step.MAIN_MENU, "main_menu")

        # If the service is an island variant, location is implicit.
        if service_id.endswith("_already_on_island") and not state.location:
            state.location = "island"

        if cart_type == "cert":
            # User already chose the exact plan on the info card — pre-select it so
            # the flow skips MIXED_ADD_CERT_PLAN / MIXED_ADD_CERT_MULTI_DAY entirely
            # and goes straight to "¿cuántos buzos?" → "¿última inmersión?".
            state.mixed_pending_qty_type = "cert"
            state.mixed_pending_qty_plan = service_id
            return self._goto_mixed_cert_last_dive_or_qty(state)

        if cart_type in ("beginner", "snorkel"):
            # No plan choice needed — skip straight to qty question.
            state.mixed_pending_qty_type = cart_type
            state.mixed_pending_qty_plan = None
            return self._goto_mixed_add_qty(state)

        if cart_type == "course":
            # Courses still need to pick the specific course type → use orchestrator helper.
            response = self.orchestrator_start_activity(state, "course")
            if response:
                return response

        # Fallback: generic MIXED_ENTRY if mapping fails or unknown cart type.
        state.step = Step.MIXED_ENTRY
        self.set_quick_replies(state, "mixed_entry")
        return MESSAGES["mixed_entry"][lang]

    def _handle_info_tour_detail(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 2)
        if msg == "itinerary" or choice == 2:
            self.set_quick_replies(state, "info_detail_actions")
            return self._format_info_itinerary(state)
        if choice == 1:
            return self._info_detail_book_action(state)
        self.set_quick_replies(state, "info_detail_actions")
        return MESSAGES["not_understood"][state.language]

    def _handle_info_package_detail(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 2)
        if msg == "itinerary" or choice == 2:
            self.set_quick_replies(state, "info_detail_actions")
            return self._format_info_itinerary(state)
        if choice == 1:
            return self._info_detail_book_action(state)
        self.set_quick_replies(state, "info_detail_actions")
        return MESSAGES["not_understood"][state.language]

    def _handle_info_course_detail(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 2)
        if msg == "itinerary" or choice == 2:
            self.set_quick_replies(state, "info_detail_actions")
            return self._format_info_itinerary(state)
        if choice == 1:
            return self._info_detail_book_action(state)
        self.set_quick_replies(state, "info_detail_actions")
        return MESSAGES["not_understood"][state.language]

    def _handle_info_specialty_detail(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 2)
        if msg == "itinerary" or choice == 2:
            self.set_quick_replies(state, "info_detail_actions")
            return self._format_info_itinerary(state)
        if choice == 1:
            return self._info_detail_book_action(state)
        self.set_quick_replies(state, "info_detail_actions")
        return MESSAGES["not_understood"][state.language]

    def _format_info_itinerary(self, state: ConversationState) -> str:
        service = SERVICES.get(state.selected_service)
        if not service:
            return MESSAGES["escalate"][state.language]

        lang = state.language
        itinerary = service.get("itinerary_es" if lang == "es" else "itinerary_en") or []

        if itinerary:
            itinerary = _group_itinerary_by_day(itinerary, lang)

        lines: list[str] = []
        if lang == "es":
            lines.append("🗺️ *Itinerario (resumen)*")
        else:
            lines.append("🗺️ *Itinerary (summary)*")
        lines.append("")

        if itinerary:
            for item in itinerary:
                stripped = item.strip()
                if not stripped:
                    continue
                prefix = _info_itinerary_line_prefix(stripped, lang) or "- "
                if prefix == "📅 ":
                    lines.append(prefix + stripped.rstrip(":"))
                else:
                    lines.append(prefix + stripped)
        else:
            if lang == "es":
                lines.append("No tengo un itinerario detallado para esta opción.")
            else:
                lines.append("I don't have a detailed itinerary for this option.")

        return "\n".join(lines)

    def _handle_pricing_colombian(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.is_colombian = True
        elif choice == 2:
            state.is_colombian = False
        else:
            self.set_quick_replies(state, "colombian")
            return MESSAGES["not_understood"][lang]

        state.step = Step.PRICING_MENU
        self.set_quick_replies(state, "pricing_menu")
        return MESSAGES["pricing_menu"][lang]

    # ───────────────────── Cart-style mixed group flow ─────────────────────

    @staticmethod
    def _is_in_mixed_flow(state: ConversationState) -> bool:
        return bool(state.mixed_cart) or state.step in {
            Step.MIXED_ENTRY,
            Step.MIXED_LOCATION,
            Step.MIXED_ADD_ACTIVITY,
            Step.MIXED_ADD_CERT_PLAN,
            Step.MIXED_ADD_CERT_MULTI_DAY,
            Step.MIXED_ADD_QTY,
            Step.MIXED_CERT_LAST_DIVE,
            Step.MIXED_CERT_REFRESH_INTEREST,
            Step.MIXED_CERT_REFRESH_QTY,
            Step.MIXED_CERT_SPLIT_REVIEW,
            Step.MIXED_ADD_PREVIEW,
            Step.MIXED_CART_REVIEW,
            Step.MIXED_CART_MODIFY_PICK,
            Step.MIXED_CART_REMOVE_PICK,
            Step.MIXED_FINAL_COLOMBIAN,
            Step.MIXED_FINAL_KIDS,
            Step.MIXED_FINAL_PRIVATE,
            Step.MIXED_FINAL_SUMMARY,
        }

    @staticmethod
    def _cart_includes(state: ConversationState, item_type: str) -> bool:
        return any(it.get("type") == item_type for it in state.mixed_cart)

    @staticmethod
    def _cart_total_qty(state: ConversationState, item_type: str | None = None) -> int:
        return sum(
            it.get("qty", 0)
            for it in state.mixed_cart
            if item_type is None or it.get("type") == item_type
        )

    @staticmethod
    def _cart_is_large_group(state: ConversationState) -> bool:
        return any(it.get("qty", 0) >= 6 for it in state.mixed_cart)

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
        state.mixed_pending_modify_idx = None
        state.mixed_pending_modify_refresh = False
        state.mixed_pending_exact = False
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

    @staticmethod
    def _cart_has_boat_activities(state: ConversationState) -> bool:
        return any(it.get("type") in {"cert", "beginner", "snorkel"} for it in state.mixed_cart)

    def _mixed_open_water_time_prompt(self, lang: str) -> str:
        if lang == "es":
            return (
                "Perfecto. Para la parte practica del curso Open Water en las Islas del Rosario, "
                "lo ideal es que tengas al menos *2 dias completos* disponibles.\n\n"
                "¿Cuentas con ese tiempo?"
            )
        return (
            "Perfect. For the practical part of your Open Water course in the Rosario Islands, "
            "it is ideal to have at least *2 full days* available.\n\n"
            "Do you have that time available?"
        )

    def _open_water_time_warning(self, state: ConversationState) -> str:
        if state.language == "es":
            if state.location == "island":
                return (
                    "⚠️ *Importante*: este curso sigue requiriendo *2 dias completos* en las Islas del Rosario. "
                    "Si vas justo de tiempo, revisa bien tus horarios antes de reservar."
                )
            return (
                "⚠️ *Importante*: este curso requiere *2 dias completos* y pasar al menos *1 noche en las Islas del Rosario*. "
                "Si no tienes ese tiempo confirmado todavia, revisalo antes de reservar."
            )
        if state.location == "island":
            return (
                "⚠️ *Important*: this course still requires *2 full days* on the Rosario Islands. "
                "If your timing is tight, please double-check your schedule before booking."
            )
        return (
            "⚠️ *Important*: this course requires *2 full days* and at least *1 overnight stay on the Rosario Islands*. "
            "If you do not have that time confirmed yet, please review it before booking."
        )

    def _start_mixed_course_add(
        self,
        state: ConversationState,
        service_id: str,
        follow_up_question: str | None = None,
    ) -> str:
        state.selected_service = service_id
        state.mixed_pending_qty_type = "course"
        state.mixed_pending_qty_plan = service_id
        state.mixed_pending_course_question = follow_up_question
        return self._goto_mixed_add_qty(state)

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

    def _remove_mixed_cart_item_qty(self, state: ConversationState, item_type: str, plan: str | None, qty: int) -> None:
        if qty <= 0:
            return
        existing = next(
            (it for it in state.mixed_cart if it["type"] == item_type and it.get("plan") == plan),
            None,
        )
        if existing is None:
            return
        existing["qty"] -= qty
        if existing["qty"] <= 0:
            state.mixed_cart.remove(existing)

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

    def _build_mixed_cert_split_review_message(self, state: ConversationState) -> str:
        lang = state.language
        total_qty = state.mixed_pending_cert_total_qty or 0
        refresh_qty = state.mixed_pending_refresh_added_qty or 0
        remaining_qty = state.mixed_pending_cert_remaining_qty or 0
        cert_label = self._cart_label_for("cert", state.mixed_pending_qty_plan, lang)
        if lang == "es":
            total_word = "persona" if total_qty == 1 else "personas"
            with_word = "persona" if refresh_qty == 1 else "personas"
            without_word = "persona" if remaining_qty == 1 else "personas"
            msg = (
                f"*Resumen del grupo ({total_qty} {total_word} · {cert_label}):*\n\n"
                f"✅ {refresh_qty} {with_word} harán el refresher antes de bucear\n"
                f"➡️ {remaining_qty} {without_word} bucearán directamente (sin refresher)\n\n"
                f"¿Cómo quieres continuar?"
            )
        else:
            total_word = "person" if total_qty == 1 else "people"
            with_word = "person" if refresh_qty == 1 else "people"
            without_word = "person" if remaining_qty == 1 else "people"
            msg = (
                f"*Group summary ({total_qty} {total_word} · {cert_label}):*\n\n"
                f"✅ {refresh_qty} {with_word} will do the refresher before diving\n"
                f"➡️ {remaining_qty} {without_word} will dive directly (no refresher)\n\n"
                f"How would you like to continue?"
            )
        return msg

    # ─── Step handlers ───

    def _handle_mixed_entry(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            target_step = state.back_step_override or Step.MAIN_MENU
            quick_replies_key = state.back_quick_replies_key or "main_menu"
            state.step = target_step
            self.set_quick_replies(state, quick_replies_key)
            return MESSAGES[quick_replies_key][lang]
        choice = self._parse_choice(message, 1)
        if choice == 1 or is_agree(msg):
            if state.location is None:
                state.step = Step.MIXED_LOCATION
                self.set_quick_replies(state, "tours_location")
                return MESSAGES["mixed_location"][lang]
            return self._goto_mixed_add_activity(state)
        # Default: also advance (the entry step is just an intro)
        if state.location is None:
            state.step = Step.MIXED_LOCATION
            self.set_quick_replies(state, "tours_location")
            return MESSAGES["mixed_location"][lang]
        return self._goto_mixed_add_activity(state)

    def _handle_mixed_location(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language
        msg = message.strip().lower()
        
        if is_back(msg):
            return self._goto_mixed_entry(state)
        
        def _after_location_set() -> str:
            """Lógica común tras fijar la ubicación: auto-añade snorkel/minicurso
            detectados y enruta según lo que queda pendiente."""
            allocation = getattr(state, "detected_group_allocation", None) or {}

            # Auto-añadir actividades no-cert ya conocidas (snorkel, minicurso).
            # OJO: si hay un "algunos certificados, otros no" en curso, el
            # minicurso de los no-certificados ya esta en cola via
            # mixed_pending_beginner_after_cert (se añade despues del subgrupo
            # certificado, no aqui) — añadirlo tambien aqui lo duplicaba.
            for act, qty in allocation.items():
                if act == "snorkel":
                    snorkel_svc = self._service_for_location("snorkeling", state)
                    self._append_mixed_cart_item(state, "snorkel", snorkel_svc, qty)
                elif act == "minicourse" and not state.mixed_pending_beginner_after_cert:
                    self._append_mixed_cart_item(state, "beginner", None, qty)

            # Si ya estamos en las islas pero no sabemos el hotel, preguntarlo
            # antes de seguir (necesario para coordinar la recogida) — aplica a
            # cualquier actividad pendiente (cert, beginner, snorkel, course...).
            if state.location == "island" and not state.hotel:
                return self._goto_island_hotel_menu_or_unknown(state)

            # Ahora decidir el siguiente step
            if state.mixed_pending_qty_type == "cert":
                state.step = Step.MIXED_ADD_CERT_PLAN
                self.set_quick_replies(state, "mixed_add_cert_plan")
                return MESSAGES["mixed_add_cert_plan"][lang]
            elif state.mixed_pending_qty_type in ("beginner", "snorkel", "course", "companion"):
                # Use _goto_mixed_add_qty so it auto-skips if qty is already known
                return self._goto_mixed_add_qty(state)
            elif state.mixed_cart:
                return self._goto_mixed_cart_review(state)
            return self._goto_mixed_add_activity(state)

        # Detectar texto libre: Cartagena
        if choice == 1 or "cartagena" in msg or "ctg" in msg:
            state.location = "cartagena"
            return _after_location_set()

        # Detectar texto libre: Islas del Rosario
        if choice == 2 or "isla" in msg or "rosario" in msg:
            state.location = "island"
            return _after_location_set()
        
        self.set_quick_replies(state, "tours_location")
        return MESSAGES["not_understood"][lang]

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

    def _handle_mixed_ask_certification(self, state: ConversationState, message: str) -> str:
        """Handler para pregunta de certificación cuando detectamos buceo sin certificación clara."""
        lang = state.language
        msg = message.strip().lower()
        group_qty = (state.mixed_pending_cert_total_qty or 0) + sum(
            it["qty"] for it in state.mixed_cart if it.get("type") == "cert"
        )
        is_group = group_qty > 1 or (state.detected_group_size or 0) > 1
        max_choice = 3 if is_group else 2
        choice = self._parse_choice(message, max_choice)

        if is_back(msg):
            return self._goto_mixed_entry(state)

        def _after_cert(cert_type: str) -> str:
            state.mixed_pending_qty_type = cert_type
            if state.location == "island" and not state.hotel:
                return self._goto_island_hotel_menu_or_unknown(state)
            if state.location:
                if cert_type == "cert":
                    state.step = Step.MIXED_ADD_CERT_PLAN
                    self.set_quick_replies(state, "mixed_add_cert_plan")
                    return MESSAGES["mixed_add_cert_plan"][lang]
                # Use _goto_mixed_add_qty so it auto-skips if qty is already known
                return self._goto_mixed_add_qty(state)
            state.step = Step.MIXED_LOCATION
            self.set_quick_replies(state, "tours_location")
            return MESSAGES["mixed_location"][lang]

        # Opción 1: Sí / Todos certificados
        if choice == 1:
            state.detected_is_certified = True
            return _after_cert("cert")

        # Opción 2: No / Ninguno
        if choice == 2:
            state.detected_is_certified = False
            return _after_cert("beginner")

        # Opción 3 (solo grupo): Algunos sí, otros no → preguntar cuántos certificados
        # para luego añadir un minicurso a los no certificados.
        if choice == 3 and is_group:
            state.detected_is_certified = None
            group_size = (state.detected_group_size or 0)
            if group_size > 1:
                state.step = Step.MIXED_ASK_CERT_COUNT
                state.quick_replies = self._cert_count_quick_replies(group_size)
                if lang == "es":
                    return (
                        f"Sois {group_size} en total. ¿Cuántos son *buzos certificados*? "
                        "Al resto les preparo el minicurso de buceo."
                    )
                return (
                    f"You are {group_size} in total. How many are *certified divers*? "
                    "I'll set up the dive mini-course for the rest."
                )
            # No conocemos el tamaño del grupo: caemos al flujo cert clásico.
            state.mixed_pending_qty_type = "cert"
            if state.location == "island" and not state.hotel:
                return self._goto_island_hotel_menu_or_unknown(state)
            if state.location:
                state.step = Step.MIXED_ADD_CERT_PLAN
                self.set_quick_replies(state, "mixed_add_cert_plan")
                if lang == "es":
                    return "Perfecto, empezamos con los buceadores certificados.\n\n" + MESSAGES["mixed_add_cert_plan"][lang]
                return "Great, let's start with the certified divers.\n\n" + MESSAGES["mixed_add_cert_plan"][lang]
            state.step = Step.MIXED_LOCATION
            self.set_quick_replies(state, "tours_location")
            return MESSAGES["mixed_location"][lang]

        qr_key = "mixed_ask_certification_group" if is_group else "mixed_ask_certification"
        self.set_quick_replies(state, qr_key)
        return MESSAGES["not_understood"][lang]

    def _cert_count_quick_replies(self, group_size: int) -> list[dict]:
        """Buttons 1..(group_size-1) to pick how many of the group are certified.

        We cap at group_size-1 because choosing all would not be a mixed group.
        """
        cap = max(1, min(group_size - 1, 8))
        options = [{"title": str(n), "value": str(n)} for n in range(1, cap + 1)]
        options.append({"title": "🔙 Volver", "value": "back"})
        return options

    def _handle_mixed_ask_cert_count(self, state: ConversationState, message: str) -> str:
        """How many of the group are certified (rest get a minicurso)."""
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            return self._ask_certification_message(state)

        group_size = state.detected_group_size or 0
        n = self._parse_mixed_quantity(message)
        if n is None or n < 1 or n >= group_size:
            state.quick_replies = self._cert_count_quick_replies(group_size)
            if lang == "es":
                return (
                    f"Dime un número entre 1 y {group_size - 1} (los certificados; "
                    "al resto les preparo el minicurso)."
                )
            return (
                f"Please pick a number between 1 and {group_size - 1} (the certified ones; "
                "the rest get the mini-course)."
            )

        cert_qty = n
        beginner_qty = group_size - n
        # Pre-cargar el subgrupo certificado y recordar los principiantes pendientes.
        state.mixed_pending_qty_type = "cert"
        state.mixed_pending_cert_total_qty = cert_qty
        state.mixed_pending_cert_remaining_qty = cert_qty
        state.mixed_pending_qty_value = cert_qty
        state.mixed_pending_beginner_after_cert = beginner_qty

        intro = (
            f"Perfecto: {cert_qty} certificado/s y {beginner_qty} para minicurso. "
            "Empezamos con los buceadores certificados.\n\n"
            if lang == "es"
            else f"Got it: {cert_qty} certified and {beginner_qty} for the mini-course. "
            "Let's start with the certified divers.\n\n"
        )
        if state.location == "island" and not state.hotel:
            return intro + self._goto_island_hotel_menu_or_unknown(state)
        if state.location:
            state.step = Step.MIXED_ADD_CERT_PLAN
            self.set_quick_replies(state, "mixed_add_cert_plan")
            return intro + MESSAGES["mixed_add_cert_plan"][lang]
        state.step = Step.MIXED_LOCATION
        self.set_quick_replies(state, "tours_location")
        return intro + MESSAGES["mixed_location"][lang]

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

    def _goto_mixed_add_activity(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_ADD_ACTIVITY
        self.set_quick_replies(state, "mixed_add_activity")
        return MESSAGES["mixed_add_activity"][lang]

    def _handle_mixed_add_activity(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            return self._goto_mixed_cart_review(state) if state.mixed_cart else self._goto_mixed_entry(state)
        choice = self._parse_choice(message, 5)
        if choice == 1:
            state.mixed_pending_qty_type = "cert"
            state.step = Step.MIXED_ADD_CERT_PLAN
            self.set_quick_replies(state, "mixed_add_cert_plan")
            return MESSAGES["mixed_add_cert_plan"][lang]
        if choice == 4:
            state.step = Step.COURSES_MENU
            self.set_quick_replies(state, "courses_menu")
            if lang == "es":
                return "Perfecto, vamos a añadir un curso PADI al carrito.\n\n" + MESSAGES["courses_menu"][lang]
            return "Perfect, let's add a PADI course to the cart.\n\n" + MESSAGES["courses_menu"][lang]
        if choice in (2, 3, 5):
            # Si entran via cert+ppt, snorkel (choice 3) no está disponible
            if choice == 3 and state.mixed_entry_path == "cert_beg":
                self.set_quick_replies(state, "mixed_add_activity")
                return MESSAGES["not_understood"][lang]
            state.mixed_pending_qty_type = {2: "beginner", 3: "snorkel", 5: "companion"}[choice]
            state.mixed_pending_qty_plan = None
            return self._goto_mixed_add_qty(state)
        self.set_quick_replies(state, "mixed_add_activity")
        return MESSAGES["not_understood"][lang]

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
            # Cantidad ya conocida → ir directamente a última inmersión
            state.mixed_pending_qty_value = pre_qty
            state.step = Step.MIXED_CERT_LAST_DIVE
            msg_key = "mixed_cert_last_dive_group" if pre_qty > 1 else "mixed_cert_last_dive"
            self.set_quick_replies(state, "mixed_cert_last_dive")
            return MESSAGES[msg_key][lang]
        return self._goto_mixed_add_qty(state)

    def _handle_mixed_add_cert_plan(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            return self._goto_mixed_add_activity(state)
        choice = self._parse_choice(message, 2)
        if choice == 1:
            state.mixed_pending_qty_plan = self._service_for_location("2_dives_1_day", state)
            return self._goto_mixed_cert_last_dive_or_qty(state)
        if choice == 2:
            state.step = Step.MIXED_ADD_CERT_MULTI_DAY
            self.set_quick_replies(state, "mixed_add_cert_multi_day")
            return MESSAGES["mixed_add_cert_multi_day"][lang]
        self.set_quick_replies(state, "mixed_add_cert_plan")
        return MESSAGES["not_understood"][lang]

    def _handle_mixed_add_cert_multi_day(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            state.step = Step.MIXED_ADD_CERT_PLAN
            self.set_quick_replies(state, "mixed_add_cert_plan")
            return MESSAGES["mixed_add_cert_plan"][lang]
        service_map = self._mixed_cert_multi_day_service_map(state)
        choice = self._parse_choice(message, len(service_map))
        if choice in service_map:
            state.mixed_pending_qty_plan = service_map[choice]
            return self._goto_mixed_cert_last_dive_or_qty(state)
        self.set_quick_replies(state, "mixed_add_cert_multi_day")
        return MESSAGES["not_understood"][lang]

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

    def _handle_mixed_add_qty(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            # If editing an item, cancel sends back to cart review (don't drop the existing item)
            state.mixed_pending_modify_idx = None
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_cart_review(state) if state.mixed_cart else self._goto_mixed_entry(state)

        if message.strip() == "6+" and not state.mixed_pending_exact:
            state.mixed_pending_exact = True
            state.quick_replies = []
            return ("Son 6 o más. ¿Cuántas personas exactamente? Escribe el número (ej: 7, 8, 10...)."
                    if lang == "es" else
                    "6 or more. How many exactly? Type the number (e.g. 7, 8, 10...).")

        n = self._parse_mixed_quantity(message)
        if n is None:
            if state.mixed_pending_exact:
                state.quick_replies = []
                return ("Escribe el número exacto, por favor."
                        if lang == "es" else "Please type the exact number.")
            self.set_quick_replies(state, "mixed_quantity")
            return MESSAGES["not_understood"][lang]

        state.mixed_pending_exact = False
        item_type = state.mixed_pending_qty_type or "cert"
        plan = state.mixed_pending_qty_plan
        if state.mixed_pending_modify_idx is not None and 0 <= state.mixed_pending_modify_idx < len(state.mixed_cart):
            modified_item = state.mixed_cart[state.mixed_pending_modify_idx]
            modified_item["qty"] = n
            had_refresh = any(it.get("type") == "refresh" for it in state.mixed_cart)
            # Changing the cert qty invalidates any refresher tied to it: drop refresh
            # items and re-ask the user (different qty → different subgroup).
            if modified_item.get("type") == "cert" and had_refresh:
                state.mixed_cart = [it for it in state.mixed_cart if it.get("type") != "refresh"]
                state.mixed_pending_modify_idx = None
                state.mixed_pending_modify_refresh = True
                state.mixed_pending_cert_total_qty = n
                state.mixed_pending_qty_value = n
                state.mixed_pending_qty_type = "cert"
                state.mixed_pending_qty_plan = "2_dives_1_day"
                state.step = Step.MIXED_CERT_REFRESH_INTEREST
                self.set_quick_replies(state, "refresher_interest")
                intro = (
                    f"✏️ Actualizado a {n} buceadores. Como cambió la cantidad, vuelvo a preguntar por el *refresher*:\n\n"
                    if lang == "es"
                    else f"✏️ Updated to {n} divers. Since the quantity changed, I'll re-ask about the *refresher*:\n\n"
                )
                return intro + self._refresher_info_msg(state)
            # Modifying a beginner line changes how many minors might be in the
            # group → wipe previous kids answer and re-ask ranges inline. The
            # modify_idx stays set; _continue_after_kids reads it to know it's
            # a modify-in-progress and returns to cart_review (no preview).
            if modified_item.get("type") == "beginner":
                self._invalidate_kids_answer(state)
                state.mixed_pending_qty_value = n
                return self._enter_mixed_final_kids(state)
            state.mixed_pending_modify_idx = None
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_cart_review(state)

        state.mixed_pending_qty_value = n
        if item_type == "companion":
            self._append_mixed_cart_item(state, item_type, plan, n)
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_cart_review(state)

        if item_type == "cert":
            state.mixed_pending_cert_total_qty = n
            state.mixed_pending_cert_remaining_qty = n
            state.step = Step.MIXED_CERT_LAST_DIVE
            self.set_quick_replies(state, "mixed_cert_last_dive")
            msg_key = "mixed_cert_last_dive_group" if n > 1 else "mixed_cert_last_dive"
            return MESSAGES[msg_key][lang]

        if item_type == "course":
            if state.mixed_pending_course_question == "open_water_time":
                state.step = Step.COURSES_OPEN_WATER_TIME
                self.set_quick_replies(state, "courses_open_water_time")
                return self._mixed_open_water_time_prompt(lang)
            return self._prepare_mixed_add_preview(
                state,
                plan or self._service_for_location("open_water", state),
            )

        if item_type == "beginner":
            # Inline kids question — invalidate any previous answer (e.g. from
            # a removed-and-re-added beginner) so the ranges are asked fresh.
            self._invalidate_kids_answer(state)
            return self._enter_mixed_final_kids(state)
        if item_type == "snorkel":
            return self._prepare_mixed_add_preview(state, self._service_for_location("snorkeling", state))

        self._clear_mixed_pending_add(state)
        return self._goto_mixed_cart_review(state)

    def _handle_mixed_cert_last_dive(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            state.step = Step.MIXED_ADD_QTY
            self.set_quick_replies(state, "mixed_quantity")
            return MESSAGES["mixed_add_qty"][lang]
        if choice == 1:
            state.step = Step.MIXED_CERT_REFRESH_INTEREST
            self.set_quick_replies(state, "refresher_interest")
            return self._refresher_info_msg(state)
        if choice == 2:
            return self._prepare_mixed_add_preview(state, self._current_mixed_cert_service_id(state))
        self.set_quick_replies(state, "mixed_cert_last_dive")
        return MESSAGES["not_understood"][lang]

    def _refresh_qty_quick_replies(self, state: ConversationState) -> list[dict]:
        """Buttons for MIXED_CERT_REFRESH_QTY clipped to the certified-divers total.

        Without this the bot offered 1..5 + 6+ even when only 3 certified divers
        were in the cart, letting users click an out-of-range value that the
        handler then had to reject. Clipping at total_qty keeps the UI honest.
        """
        lang = state.language
        total_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
        cancel_title = "🔙 Volver" if lang == "es" else "🔙 Back"
        if total_qty <= 0:
            return [{"title": cancel_title, "value": "back"}]
        max_button = min(total_qty, 5)
        buttons = [{"title": str(n), "value": str(n)} for n in range(1, max_button + 1)]
        if total_qty >= 6:
            six_plus_title = "6 o mas" if lang == "es" else "6 or more"
            buttons.append({"title": six_plus_title, "value": "6+"})
        buttons.append({"title": cancel_title, "value": "back"})
        return buttons

    def _handle_mixed_cert_refresh_interest(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            state.step = Step.MIXED_CERT_LAST_DIVE
            self.set_quick_replies(state, "mixed_cert_last_dive")
            return MESSAGES["mixed_cert_last_dive"][lang]
        if choice == 1:
            state.step = Step.MIXED_CERT_REFRESH_QTY
            state.quick_replies = self._refresh_qty_quick_replies(state)
            return MESSAGES["mixed_cert_refresh_qty"][lang]
        if choice == 2:
            # In modify mode, cert is already in the cart with the updated qty —
            # "No" just means no refresher; return straight to cart review.
            if state.mixed_pending_modify_refresh:
                state.mixed_pending_modify_refresh = False
                self._clear_mixed_pending_add(state)
                return self._goto_mixed_cart_review(state)
            return self._prepare_mixed_add_preview(state, self._current_mixed_cert_service_id(state))
        self.set_quick_replies(state, "refresher_interest")
        return MESSAGES["not_understood"][lang]

    def _handle_mixed_cert_refresh_qty(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        total_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
        current_plan = self._current_mixed_cert_service_id(state)
        if is_back(msg):
            state.step = Step.MIXED_CERT_REFRESH_INTEREST
            self.set_quick_replies(state, "refresher_interest")
            return self._refresher_info_msg(state)

        if message.strip() == "6+" and not state.mixed_pending_exact:
            state.mixed_pending_exact = True
            state.quick_replies = []
            return ("Son 6 o más. ¿Cuántas personas exactamente? Escribe el número (ej: 7, 8, 10...)."
                    if lang == "es" else
                    "6 or more. How many exactly? Type the number (e.g. 7, 8, 10...).")

        n = self._parse_mixed_quantity(message)
        if n is None or n > total_qty:
            if state.mixed_pending_exact:
                state.quick_replies = []
                return ("Escribe un número exacto válido para ese subgrupo, por favor."
                        if lang == "es" else "Please enter a valid exact number for that subgroup.")
            state.quick_replies = self._refresh_qty_quick_replies(state)
            if n is not None and n > total_qty:
                people_word = "persona" if total_qty == 1 else "personas"
                return (
                    f"Solo hay {total_qty} {people_word} en el subgrupo certificado. Elige un número entre 1 y {total_qty}."
                    if lang == "es"
                    else f"There are only {total_qty} certified people. Pick a number between 1 and {total_qty}."
                )
            return MESSAGES["not_understood"][lang]

        state.mixed_pending_exact = False
        # Modify mode: the cert is already in the cart with the updated qty.
        # Just attach the refresher count and return to cart review (no preview,
        # no split-review).
        if state.mixed_pending_modify_refresh:
            self._append_mixed_cart_item(state, "refresh", current_plan, n)
            state.mixed_pending_refresh_added_qty = n
            state.mixed_pending_modify_refresh = False
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_cart_review(state)

        # Normal add flow: cert is appended via the preview/split-review path,
        # not here. We only append the refresher and then route depending on
        # whether all certs got refresher (preview) or only some (split-review).
        self._append_mixed_cart_item(state, "refresh", current_plan, n)
        state.mixed_pending_refresh_added_qty = n
        remaining_qty = total_qty - n
        state.mixed_pending_cert_remaining_qty = remaining_qty
        if remaining_qty <= 0:
            state.mixed_pending_qty_type = "cert"
            state.mixed_pending_qty_plan = current_plan
            state.mixed_pending_qty_value = total_qty
            return self._prepare_mixed_add_preview(state, current_plan)

        state.mixed_pending_qty_type = "cert"
        state.mixed_pending_qty_plan = current_plan
        state.mixed_pending_qty_value = remaining_qty
        state.step = Step.MIXED_CERT_SPLIT_REVIEW
        self.set_quick_replies(state, "mixed_cert_split_review")
        return self._build_mixed_cert_split_review_message(state)

    def _handle_mixed_cert_split_review(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language
        msg = message.strip().lower()
        current_plan = self._current_mixed_cert_service_id(state)
        if is_back(msg):
            refresh_qty = state.mixed_pending_refresh_added_qty or 0
            self._remove_mixed_cart_item_qty(state, "refresh", current_plan, refresh_qty)
            state.mixed_pending_refresh_added_qty = None
            state.mixed_pending_cert_remaining_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
            state.step = Step.MIXED_CERT_REFRESH_QTY
            state.quick_replies = self._refresh_qty_quick_replies(state)
            return MESSAGES["mixed_cert_refresh_qty"][lang]
        if choice == 1:
            # Preview and add ALL people under one cert line; the refresh sub-item
            # already in the cart will show as a sub-bullet under that cert line.
            total_qty = state.mixed_pending_cert_total_qty or 0
            if total_qty:
                state.mixed_pending_qty_value = total_qty
            return self._prepare_mixed_add_preview(state, current_plan)
        if choice == 2:
            refresh_qty = state.mixed_pending_refresh_added_qty or 0
            self._remove_mixed_cart_item_qty(state, "refresh", current_plan, refresh_qty)
            total_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
            state.mixed_pending_refresh_added_qty = None
            state.mixed_pending_cert_remaining_qty = total_qty
            state.mixed_pending_qty_type = "cert"
            state.mixed_pending_qty_plan = current_plan
            state.mixed_pending_qty_value = total_qty
            return self._prepare_mixed_add_preview(state, current_plan)
        if choice == 3:
            self._reset_mixed_state(state)
            return self._goto_mixed_entry(state)
        self.set_quick_replies(state, "mixed_cert_split_review")
        return self._build_mixed_cert_split_review_message(state)

    def _handle_mixed_add_preview(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = " ".join(message.strip().lower().split())
        service_id = state.mixed_pending_preview_service_id
        if is_back(msg):
            if state.mixed_pending_refresh_added_qty and (state.mixed_pending_cert_remaining_qty or 0) > 0:
                state.step = Step.MIXED_CERT_SPLIT_REVIEW
                self.set_quick_replies(state, "mixed_cert_split_review")
                return self._build_mixed_cert_split_review_message(state)
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_add_activity(state)
        if msg == "itinerary":
            preview_state = self._mixed_preview_state(state, service_id or self._service_for_location("snorkeling", state))
            self.set_quick_replies(state, "mixed_preview_actions")
            return self._format_full_itinerary(preview_state) + MESSAGE_SPLIT + MESSAGES["mixed_add_preview"][lang]

        choice = self._parse_choice(message, 1)
        if choice == 1:
            item_type = state.mixed_pending_qty_type
            plan = state.mixed_pending_qty_plan
            qty = state.mixed_pending_qty_value or 0
            if item_type and qty > 0:
                self._append_mixed_cart_item(state, item_type, plan, qty)
            self._clear_mixed_pending_add(state)
            # "Some certified, some not": after the cert is in the cart, add the
            # minicurso for the remaining non-certified people automatically.
            pending_beginner = self._maybe_start_pending_beginner(state)
            if pending_beginner is not None:
                return pending_beginner
            return self._goto_mixed_cart_review(state)

        self.set_quick_replies(state, "mixed_preview_actions")
        return MESSAGES["not_understood"][lang]

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
        if lang == "es":
            options = [
                {"title": "🤿 Minicurso de buceo", "value": "1"},
                {"title": "🌊 Snorkel", "value": "2"},
            ]
            if include_open_water:
                options.append({"title": "🎓 Curso Open Water", "value": "3"})
            options.append({"title": "🔙 Volver", "value": "back"})
        else:
            options = [
                {"title": "🤿 Dive mini-course", "value": "1"},
                {"title": "🌊 Snorkel", "value": "2"},
            ]
            if include_open_water:
                options.append({"title": "🎓 Open Water course", "value": "3"})
            options.append({"title": "🔙 Volver", "value": "back"})
        return options

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
        include_open_water = self._cert_subgroup_is_multi_day(state)
        state.step = Step.MIXED_ASK_BEGINNER_ACTIVITY
        state.quick_replies = self._beginner_activity_quick_replies(lang, include_open_water)

        if lang == "es":
            who = "la persona no certificada" if beginner_qty == 1 else f"las {beginner_qty} personas no certificadas"
            intro = f"Listo, los buceadores certificados ya están en el carrito.\n\nPara {who}, hay varias opciones:\n"
            body = (
                "• 🤿 *Minicurso de buceo*: probar el buceo en una sesión introductoria con instructor, sin certificación.\n"
                "• 🌊 *Snorkel*: disfrutar del arrecife desde la superficie, sin necesidad de bucear.\n"
            )
            if include_open_water:
                body += (
                    "• 🎓 *Curso Open Water*: ya que se alojarán en las islas con el grupo certificado, "
                    "puede aprovechar y certificarse como buzo.\n"
                )
            outro = "\n¿Qué prefiere?" if beginner_qty == 1 else "\n¿Qué prefieren?"
        else:
            who = "the non-certified person" if beginner_qty == 1 else f"the {beginner_qty} non-certified people"
            intro = f"Done, the certified divers are in the cart.\n\nFor {who}, there are a few options:\n"
            body = (
                "• 🤿 *Dive mini-course*: try diving in an introductory session with an instructor, no certification.\n"
                "• 🌊 *Snorkel*: enjoy the reef from the surface, no diving needed.\n"
            )
            if include_open_water:
                body += (
                    "• 🎓 *Open Water course*: since they'll already be staying on the islands with the "
                    "certified group, they could get certified too.\n"
                )
            outro = "\nWhat would they prefer?"
        return intro + body + outro

    def _handle_mixed_ask_beginner_activity(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        include_open_water = self._cert_subgroup_is_multi_day(state)
        max_choice = 3 if include_open_water else 2
        if is_back(msg):
            return self._goto_mixed_cart_review(state)
        choice = self._parse_choice(message, max_choice)
        beginner_qty = state.mixed_pending_beginner_after_cert or 0
        if choice is None or beginner_qty <= 0:
            state.quick_replies = self._beginner_activity_quick_replies(lang, include_open_water)
            return MESSAGES["not_understood"][lang]

        state.mixed_pending_beginner_after_cert = 0
        state.mixed_pending_qty_value = beginner_qty
        if choice == 1:
            state.mixed_pending_qty_type = "beginner"
            state.mixed_pending_qty_plan = None
            return self._goto_mixed_add_qty(state)
        if choice == 2:
            state.mixed_pending_qty_type = "snorkel"
            state.mixed_pending_qty_plan = self._service_for_location("snorkeling", state)
            return self._goto_mixed_add_qty(state)
        # choice == 3: Open Water (only offered when include_open_water is True)
        return self._start_mixed_course_add(
            state,
            self._service_for_location("open_water", state),
            "open_water_time",
        )

    # Emojis numéricos para listas dinámicas (botones de modificar/quitar item)
    _NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    def _cart_pick_buttons(self, state: ConversationState) -> list[dict]:
        """Genera botones dinámicos para elegir un item del carrito (modify/remove).

        Refresher items don't get their own button — they are an attribute of
        the cert line, not an independent service. The button value uses the
        raw 1-based index into state.mixed_cart so existing handlers keep
        working as-is.
        """
        options: list[dict] = []
        visible_idx = 0
        for raw_idx, item in enumerate(state.mixed_cart):
            if item.get("type") == "refresh":
                continue
            visible_idx += 1
            emoji = self._NUMBER_EMOJIS[visible_idx - 1] if visible_idx <= len(self._NUMBER_EMOJIS) else f"{visible_idx}."
            # Truncamos el label para que el botón no quede gigante (límite suave de Chatwoot)
            label = item["label"]
            title = f"{emoji} {item['qty']} × {label}"
            if len(title) > 60:
                title = title[:57] + "..."
            options.append({"title": title, "value": str(raw_idx + 1)})
        cancel = (
            {"title": "🔙 Volver", "value": "back"}
            if state.language == "es"
            else {"title": "🔙 Back", "value": "back"}
        )
        options.append(cancel)
        return options

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

    def _goto_mixed_cart_review(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_CART_REVIEW
        self.set_quick_replies(state, "mixed_cart_actions")
        cart_lines = self._format_cart_lines(state, lang)
        prompt = MESSAGES["mixed_cart_actions"][lang]
        return f"{cart_lines}\n\n{prompt}"

    def _goto_mixed_entry(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_ENTRY
        self.set_quick_replies(state, "mixed_entry")
        msg_key = "mixed_entry_cert_beg" if state.mixed_entry_path == "cert_beg" else "mixed_entry"
        return MESSAGES[msg_key][lang]

    def _handle_mixed_cart_review(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 6)
        if choice == 1:
            return self._enter_mixed_cart_location(state)
        if choice == 2:
            return self._goto_mixed_add_activity(state)
        if choice == 3:
            if not state.mixed_cart:
                return self._goto_mixed_add_activity(state)
            state.step = Step.MIXED_CART_MODIFY_PICK
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_modify_pick"][lang]
        if choice == 4:
            if not state.mixed_cart:
                return self._goto_mixed_add_activity(state)
            state.step = Step.MIXED_CART_REMOVE_PICK
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_remove_pick"][lang]
        if choice == 5:
            self._reset_mixed_state(state)
            return self._goto_mixed_entry(state)
        if choice == 6:
            if not state.mixed_cart:
                self.set_quick_replies(state, "mixed_cart_actions")
                return MESSAGES["mixed_cart_empty"][lang]
            return self._goto_mixed_final_colombian(state)
        self.set_quick_replies(state, "mixed_cart_actions")
        return MESSAGES["not_understood"][lang]

    def _handle_mixed_cart_modify_pick(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            return self._goto_mixed_cart_review(state)
        try:
            idx = int(message.strip()) - 1
        except ValueError:
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_modify_pick"][lang]
        if not (0 <= idx < len(state.mixed_cart)):
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_modify_pick"][lang]
        item = state.mixed_cart[idx]
        state.mixed_pending_modify_idx = idx
        state.mixed_pending_qty_type = item["type"]
        state.mixed_pending_qty_plan = item.get("plan")
        return self._goto_mixed_add_qty(state)

    def _handle_mixed_cart_remove_pick(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            return self._goto_mixed_cart_review(state)
        try:
            idx = int(message.strip()) - 1
        except ValueError:
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_remove_pick"][lang]
        if not (0 <= idx < len(state.mixed_cart)):
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_remove_pick"][lang]
        removed = state.mixed_cart.pop(idx)
        # Refresher is meaningless without the certified-diving line it sits
        # under, so dropping the cert auto-removes any refresh items too.
        if removed.get("type") == "cert":
            state.mixed_cart = [it for it in state.mixed_cart if it.get("type") != "refresh"]
        # Removing a beginner line changes the kids-context — invalidate any
        # previous age-range answer so the next checkout re-asks if needed.
        if removed.get("type") == "beginner":
            self._invalidate_kids_answer(state)
        ack = (f"✅ Quitado del carrito: {removed['qty']} × {removed['label']}"
               if lang == "es" else
               f"✅ Removed from cart: {removed['qty']} × {removed['label']}")
        return ack + "\n\n" + self._goto_mixed_cart_review(state)

    # ─── Cambiar origen desde el carrito ───

    def _enter_mixed_cart_location(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_CART_LOCATION
        self.set_quick_replies(state, "tours_location")
        return MESSAGES["mixed_cart_location"][lang]

    def _remap_cart_for_location(self, state: ConversationState) -> None:
        """Refresh cart item labels and plans after a location change.

        `cert` and `course` items carry a plan that may embed a location
        variant (e.g. `2_dives_1_day` ↔ `2_dives_1_day_already_on_island`,
        `open_water` ↔ `open_water_already_on_island`); we swap them to the
        equivalent for the new location when one exists in ISLAND_SERVICE_MAP.
        `beginner`/`snorkel`/`refresh` resolve their service via
        `_cart_service_id` dynamically and don't need plan rewriting; only
        their labels are refreshed.
        """
        island_to_base = {island: base for base, island in ISLAND_SERVICE_MAP.items()}
        for item in state.mixed_cart:
            item_type = item.get("type")
            plan = item.get("plan")
            if item_type in {"cert", "course"} and plan:
                if state.location == "island" and plan in ISLAND_SERVICE_MAP:
                    new_plan = ISLAND_SERVICE_MAP[plan]
                    if new_plan in SERVICES:
                        item["plan"] = new_plan
                elif state.location == "cartagena" and plan in island_to_base:
                    new_plan = island_to_base[plan]
                    if new_plan in SERVICES:
                        item["plan"] = new_plan
            # Refresh the label for the (possibly new) plan and language.
            item["label"] = self._cart_label_for(item_type, item.get("plan"), state.language)

    def _handle_mixed_cart_location(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            return self._goto_mixed_cart_review(state)
        choice = self._parse_choice(message, 2)
        if choice == 1:
            new_loc = "cartagena"
        elif choice == 2:
            new_loc = "island"
        else:
            self.set_quick_replies(state, "tours_location")
            return MESSAGES["not_understood"][lang]
        if new_loc == state.location:
            ack = (
                "📍 Ya estabas con ese origen, sin cambios."
                if lang == "es"
                else "📍 Already set to that origin, no changes."
            )
            return ack + "\n\n" + self._goto_mixed_cart_review(state)
        state.location = new_loc
        # Switching to "island" without a known hotel: ask for it (needed for
        # pickup) before remapping prices and showing the cart again.
        if new_loc == "island" and not state.hotel:
            state.mixed_pending_location_change = True
            return self._goto_island_hotel_menu_or_unknown(state)
        self._remap_cart_for_location(state)
        loc_label = (
            ("Cartagena" if new_loc == "cartagena" else "Islas del Rosario")
            if lang == "es"
            else ("Cartagena" if new_loc == "cartagena" else "Rosario Islands")
        )
        ack = (
            f"📍 Origen actualizado a *{loc_label}*. Precios y servicios ajustados."
            if lang == "es"
            else f"📍 Origin updated to *{loc_label}*. Prices and services adjusted."
        )
        return ack + "\n\n" + self._goto_mixed_cart_review(state)

    # ───────── Orchestrator (Fase 2) public helpers ─────────
    # These let the tool-calling orchestrator (src/agents/orchestrator.py) drive
    # the cart flow from free text, reusing the exact same handlers the buttons use.

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
        if state.mixed_cart:
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
        return ack + "\n\n" + self._goto_mixed_cart_review(state)

    def orchestrator_start_activity(self, state: ConversationState, activity_type: str) -> str | None:
        """Enter the add sub-flow for an activity, reusing _handle_mixed_add_activity."""
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

    def _enter_mixed_final_kids(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_FINAL_KIDS
        self.set_quick_replies(state, "mixed_kids_age")
        return MESSAGES["mixed_final_kids"][lang]

    def _goto_mixed_final_colombian(self, state: ConversationState) -> str:
        lang = state.language
        # Si ya conocemos la respuesta del flujo lineal previo (state.is_colombian),
        # la heredamos y saltamos directo a la siguiente pregunta para no
        # repetir la pregunta al cliente.
        if state.is_colombian is not None and state.mixed_final_is_colombian is None:
            state.mixed_final_is_colombian = state.is_colombian
            state.mixed_display_currency = "COP" if state.is_colombian else "USD"
            if not self._cart_has_boat_activities(state):
                return self._goto_mixed_final_summary(state)
            return self._goto_mixed_final_private(state)
        state.step = Step.MIXED_FINAL_COLOMBIAN
        self.set_quick_replies(state, "mixed_yes_no")
        return MESSAGES["mixed_final_colombian"][lang]

    def _handle_mixed_final_colombian(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 2)
        if choice == 1:
            state.mixed_final_is_colombian = True
            state.mixed_display_currency = "COP"
        elif choice == 2:
            state.mixed_final_is_colombian = False
            state.mixed_display_currency = "USD"
        else:
            self.set_quick_replies(state, "mixed_yes_no")
            return MESSAGES["not_understood"][lang]
        if not self._cart_has_boat_activities(state):
            return self._goto_mixed_final_summary(state)
        return self._goto_mixed_final_private(state)

    def _pending_beginner_qty(self, state: ConversationState) -> int | None:
        """qty for the Minicurso item under consideration (in-cart or pending add).

        Returns None when no beginner context is known. The kids questions can
        run either inline at add (before the item is committed to the cart) or
        on modify (after qty is updated in-cart); both should cap correctly.
        """
        if state.mixed_pending_modify_idx is not None and 0 <= state.mixed_pending_modify_idx < len(state.mixed_cart):
            item = state.mixed_cart[state.mixed_pending_modify_idx]
            if item.get("type") == "beginner":
                return int(item.get("qty") or 0)
        if state.mixed_pending_qty_type == "beginner" and state.mixed_pending_qty_value:
            return int(state.mixed_pending_qty_value)
        beginner_item = next((it for it in state.mixed_cart if it.get("type") == "beginner"), None)
        if beginner_item:
            return int(beginner_item.get("qty") or 0)
        return None

    def _kids_qty_quick_replies(self, state: ConversationState) -> list[dict]:
        """Buttons for MIXED_FINAL_KIDS_QTY clipped to the beginner qty context.

        When the cap exceeds 9 (large group), shows 1..5 + "6+" so the user
        can type the exact number on the next turn (same UX as MIXED_ADD_QTY).
        """
        lang = state.language
        cancel_title = "🔙 Volver" if lang == "es" else "🔙 Back"
        pending = self._pending_beginner_qty(state)
        max_qty = max(pending or 6, 1)
        if max_qty <= 9:
            buttons = [{"title": str(n), "value": str(n)} for n in range(1, max_qty + 1)]
        else:
            plus_title = "6 o mas" if lang == "es" else "6 or more"
            buttons = [{"title": str(n), "value": str(n)} for n in range(1, 6)]
            buttons.append({"title": plus_title, "value": "6+"})
        buttons.append({"title": cancel_title, "value": "back"})
        return buttons

    def _enter_mixed_final_kids_qty(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_FINAL_KIDS_QTY
        state.quick_replies = self._kids_qty_quick_replies(state)
        return MESSAGES["mixed_final_kids_qty"][lang]

    def _kids_mixed_qty_quick_replies(self, state: ConversationState, cap: int) -> list[dict]:
        """Buttons for KIDS_U8 / KIDS_810 questions. Allows 'Ninguno' (0) and caps.

        When the cap exceeds 8 (large remaining group), shows 0..5 + "6+" so
        the user can type the exact number on the next turn.
        """
        lang = state.language
        none_title = "0 — Ninguno" if lang == "es" else "0 — None"
        cancel_title = "🔙 Volver" if lang == "es" else "🔙 Back"
        cap = max(0, cap)
        buttons = [{"title": none_title, "value": "0"}]
        if cap <= 8:
            for n in range(1, cap + 1):
                buttons.append({"title": str(n), "value": str(n)})
        else:
            for n in range(1, 6):
                buttons.append({"title": str(n), "value": str(n)})
            plus_title = "6 o mas" if lang == "es" else "6 or more"
            buttons.append({"title": plus_title, "value": "6+"})
        buttons.append({"title": cancel_title, "value": "back"})
        return buttons

    def _enter_mixed_final_kids_u8(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_FINAL_KIDS_U8
        cap = self._pending_beginner_qty(state) or 9
        state.quick_replies = self._kids_mixed_qty_quick_replies(state, cap)
        return MESSAGES["mixed_final_kids_u8"][lang]

    def _enter_mixed_final_kids_810(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_FINAL_KIDS_810
        total = self._pending_beginner_qty(state) or 9
        cap = max(0, total - (state.kids_under_8_count or 0))
        state.quick_replies = self._kids_mixed_qty_quick_replies(state, cap)
        return MESSAGES["mixed_final_kids_810"][lang]

    def _continue_after_kids(self, state: ConversationState) -> str:
        """Routes after kids info is captured.

        Three contexts:
          - MODIFY (modify_idx set): qty already updated → return to cart_review.
          - ADD (pending qty type is beginner): show preview before commit.
          - Fallback: legacy end-of-flow (private/summary).
        """
        # MODIFY in-progress: the beginner item was already updated; just clean
        # up pending state and go back to cart_review.
        if state.mixed_pending_modify_idx is not None:
            state.mixed_pending_modify_idx = None
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_cart_review(state)
        # ADD in-progress: show preview before committing.
        if state.mixed_pending_qty_type == "beginner":
            return self._prepare_mixed_add_preview(
                state,
                self._service_for_location("minicourse", state),
            )
        # Fallback (legacy paths that may still call this).
        if not self._cart_has_boat_activities(state):
            return self._goto_mixed_final_summary(state)
        return self._goto_mixed_final_private(state)

    def _handle_mixed_final_kids(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 4)
        if choice == 1:
            state.kids_age_group = "under_8"
            state.mixed_final_has_kids_8_10 = False
        elif choice == 2:
            state.kids_age_group = "eight_to_ten"
            state.mixed_final_has_kids_8_10 = True
        elif choice == 3:
            state.kids_age_group = "ten_plus"
            state.mixed_final_has_kids_8_10 = False
            state.kids_count = None  # 10+ no necesita desglose
            state.kids_under_8_count = 0
            state.kids_eight_to_ten_count = 0
            return self._continue_after_kids(state)
        elif choice == 4:
            # Mixed: ask u8 first, then 8-10
            state.kids_age_group = "mixed"
            state.kids_under_8_count = 0
            state.kids_eight_to_ten_count = 0
            return self._enter_mixed_final_kids_u8(state)
        else:
            self.set_quick_replies(state, "mixed_kids_age")
            return MESSAGES["not_understood"][lang]
        # under_8 / eight_to_ten → preguntar cuántos
        return self._enter_mixed_final_kids_qty(state)

    def _handle_mixed_final_kids_qty(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            state.mixed_pending_exact = False
            return self._enter_mixed_final_kids(state)
        if message.strip() == "6+" and not state.mixed_pending_exact:
            state.mixed_pending_exact = True
            state.quick_replies = []
            max_qty = self._pending_beginner_qty(state) or 9
            return (
                f"Son 6 o más. ¿Cuántos *niños* exactamente? Escribe el número (máx. {max_qty})."
                if lang == "es"
                else f"6 or more. How many *kids* exactly? Type the number (max {max_qty})."
            )
        n = self._parse_mixed_quantity(message)
        max_qty = self._pending_beginner_qty(state) or 9
        if n is None or n < 1 or n > max_qty:
            state.mixed_pending_exact = False
            state.quick_replies = self._kids_qty_quick_replies(state)
            if n is not None and n > max_qty:
                noun = "niño" if max_qty == 1 else "niños"
                return (
                    f"En el carrito hay {max_qty} {noun} como máximo en esa actividad. Elige un número entre 1 y {max_qty}."
                    if lang == "es"
                    else f"There are at most {max_qty} kids possible for that activity in the cart. Pick a number between 1 and {max_qty}."
                )
            return MESSAGES["not_understood"][lang]
        state.mixed_pending_exact = False
        state.kids_count = n
        if state.kids_age_group == "under_8":
            state.kids_under_8_count = n
            state.kids_eight_to_ten_count = 0
        elif state.kids_age_group == "eight_to_ten":
            state.kids_under_8_count = 0
            state.kids_eight_to_ten_count = n
        return self._continue_after_kids(state)

    def _handle_mixed_final_kids_u8(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            state.mixed_pending_exact = False
            return self._enter_mixed_final_kids(state)
        max_qty = self._pending_beginner_qty(state) or 9
        if message.strip() == "6+" and not state.mixed_pending_exact:
            state.mixed_pending_exact = True
            state.quick_replies = []
            return (
                f"Son 6 o más. ¿Cuántos *menores de 8* exactamente? Escribe el número (máx. {max_qty})."
                if lang == "es"
                else f"6 or more. How many *under 8* exactly? Type the number (max {max_qty})."
            )
        n = self._parse_mixed_quantity(message)
        if n is None:
            # Accept literal "0" or "ninguno"/"none"
            if is_none_selection(msg):
                n = 0
        if n is None or n < 0 or n > max_qty:
            state.mixed_pending_exact = False
            beginner_cap = max_qty
            state.quick_replies = self._kids_mixed_qty_quick_replies(state, beginner_cap)
            if n is not None and n > max_qty:
                return (
                    f"Solo hay {max_qty} en el minicurso. Elige un número entre 0 y {max_qty}."
                    if lang == "es"
                    else f"Only {max_qty} in the mini-course. Pick a number between 0 and {max_qty}."
                )
            return MESSAGES["not_understood"][lang]
        state.mixed_pending_exact = False
        state.kids_under_8_count = n
        return self._enter_mixed_final_kids_810(state)

    def _handle_mixed_final_kids_810(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if is_back(msg):
            state.mixed_pending_exact = False
            return self._enter_mixed_final_kids_u8(state)
        total = self._pending_beginner_qty(state) or 9
        cap = max(0, total - (state.kids_under_8_count or 0))
        if message.strip() == "6+" and not state.mixed_pending_exact:
            state.mixed_pending_exact = True
            state.quick_replies = []
            return (
                f"Son 6 o más. ¿Cuántos *entre 8 y 10* exactamente? Escribe el número (máx. {cap})."
                if lang == "es"
                else f"6 or more. How many *between 8 and 10* exactly? Type the number (max {cap})."
            )
        n = self._parse_mixed_quantity(message)
        if n is None:
            if is_none_selection(msg):
                n = 0
        if n is None or n < 0 or n > cap:
            state.mixed_pending_exact = False
            state.quick_replies = self._kids_mixed_qty_quick_replies(state, cap)
            if n is not None and n > cap:
                return (
                    f"Solo quedan {cap} en el minicurso después de los menores de 8. Elige un número entre 0 y {cap}."
                    if lang == "es"
                    else f"Only {cap} remain after the under-8 kids. Pick a number between 0 and {cap}."
                )
            return MESSAGES["not_understood"][lang]
        state.mixed_pending_exact = False
        state.kids_eight_to_ten_count = n
        u8 = state.kids_under_8_count or 0
        e10 = state.kids_eight_to_ten_count or 0
        if u8 == 0 and e10 == 0:
            state.kids_age_group = "ten_plus"
            state.kids_count = None
            state.mixed_final_has_kids_8_10 = False
        elif u8 > 0 and e10 == 0:
            state.kids_age_group = "under_8"
            state.kids_count = u8
            state.mixed_final_has_kids_8_10 = False
        elif u8 == 0 and e10 > 0:
            state.kids_age_group = "eight_to_ten"
            state.kids_count = e10
            state.mixed_final_has_kids_8_10 = True
        else:
            state.kids_age_group = "mixed"
            state.kids_count = u8 + e10
            state.mixed_final_has_kids_8_10 = True
        return self._continue_after_kids(state)

    def _goto_mixed_final_private(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_FINAL_PRIVATE
        self.set_quick_replies(state, "mixed_yes_no")
        return MESSAGES["mixed_final_private"][lang]

    def _handle_mixed_final_private(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 2)
        if choice == 1:
            state.mixed_final_wants_private = True
        elif choice == 2:
            state.mixed_final_wants_private = False
        else:
            self.set_quick_replies(state, "mixed_yes_no")
            return MESSAGES["not_understood"][lang]
        return self._goto_mixed_final_summary(state)

    def _goto_mixed_final_summary(self, state: ConversationState) -> str:
        state.step = Step.MIXED_FINAL_SUMMARY
        self.set_quick_replies(state, "mixed_final_summary_actions")
        return self._format_mixed_final_summary(state)

    def _handle_mixed_final_summary(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 3)
        if choice == 1:
            # No-Colombian clients pay 100% online, so we can send the booking
            # link(s) right away instead of waiting on an advisor. Colombian
            # clients (split payment + discount coordination) and carts where
            # no direct link is available (contact-only/referral items) still
            # escalate as before.
            if state.mixed_final_is_colombian is False and state.mixed_booking_links:
                links_block = _format_booking_links_block(state.mixed_booking_links, lang)
                state.step = Step.FREE_TEXT
                state.quick_replies = []
                state.pending_lead_note_reason = (
                    "grupo mixto - cliente confirmó carrito, link(es) de reserva enviados directamente"
                )
                plural = len(state.mixed_booking_links) > 1
                if lang == "es":
                    intro = "tus links de reserva" if plural else "tu link de reserva"
                    return (
                        f"¡Perfecto! 🎉 Aquí tienes {intro} (10% de descuento pagando online):\n\n{links_block}\n\n"
                        "Al completar el pago tu reserva queda registrada. Si tienes alguna duda, escríbeme.\n\n"
                        "Si necesitas algo más, escribe *menu* para volver al inicio."
                    )
                intro = "your booking links" if plural else "your booking link"
                return (
                    f"Great! 🎉 Here's {intro} (10% off paying online):\n\n{links_block}\n\n"
                    "Once payment is completed your booking is confirmed. If you have any questions, just ask.\n\n"
                    "If you need anything else, type *menu* to go back."
                )

            # Reservar → escalate. El asesor envía el link de reserva tras confirmar.
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "grupo mixto - cliente confirma carrito y quiere reservar"

            if lang == "es":
                return (
                    "¡Perfecto! Te paso con un asesor para confirmar disponibilidad, "
                    "número exacto de personas y precio final. Enseguida se pone en contacto contigo "
                    "y te envía el link de reserva."
                )
            return (
                "Great! I'll connect you with an advisor to confirm availability, exact "
                "number of people, and the final price. They will be in touch shortly "
                "with the booking link."
            )
        if choice == 2:
            self._reset_mixed_state(state)
            return self._goto_mixed_entry(state)
        if choice == 3:
            # Client wants to book but pay in person (no online payment at all) —
            # always escalate, regardless of nationality; the advisor coordinates
            # the in-person payment instead of sending a booking link.
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "grupo mixto - quiere pagar en persona, no online"
            if lang == "es":
                return (
                    "¡Perfecto! Te paso con un asesor para coordinar el pago presencial y confirmar "
                    "disponibilidad, número exacto de personas y precio final. Enseguida se pone en "
                    "contacto contigo."
                )
            return (
                "Great! I'll connect you with an advisor to arrange in-person payment and confirm "
                "availability, exact number of people, and the final price. They will be in touch "
                "shortly."
            )
        self.set_quick_replies(state, "mixed_final_summary_actions")
        return MESSAGES["not_understood"][lang]

    def _handle_pricing_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "pricing_menu")
            return MESSAGES["not_understood"][lang]

        def _fmt_cop(v: float | int | None) -> str:
            if v is None:
                return ""
            try:
                return f"{int(round(float(v))):,}".replace(",", ".")
            except (TypeError, ValueError):
                return str(v)

        def _price_for_client(service_id: str) -> str:
            svc = SERVICES.get(service_id, {})
            if state.is_colombian and svc.get("price_cop"):
                if svc.get("price_cop_normal"):
                    return f"{_fmt_cop(svc['price_cop'])} COP online / {_fmt_cop(svc['price_cop_normal'])} COP normal"
                return f"{_fmt_cop(svc['price_cop'])} COP"
            return svc.get("price", "")

        if lang == "es":
            if choice == 1:
                state.step = Step.PRICING_CARTAGENA
                response = (
                    "🚤 *Precios de referencia saliendo desde Cartagena*\n"
                    "(incluye lancha + almuerzo + entrada al parque):\n\n"
                    f"🤿 2 buceos (1 día): {_price_for_client('2_dives_1_day')}\n"
                    f"🆕 Minicurso de buceo: {_price_for_client('minicourse')}\n"
                    f"🐠 Tour de snorkel: {_price_for_client('snorkeling')}"
                )
            elif choice == 2:
                location_note = ""
                if state.location == "island":
                    location_note = "Como ya indicaste que estas en las islas, "
                state.step = Step.PRICING_ISLANDS
                response = (
                    f"{location_note}🏝️ *Precios para quienes ya están en las Islas del Rosario*\n"
                    "(sin transporte Cartagena-Islas ni almuerzo):\n\n"
                    f"🤿 2 buceos: {_price_for_client('2_dives_1_day_already_on_island')}\n"
                    f"🌙 3 buceos con nocturna: {_price_for_client('3_dives_1_day_already_on_island')}\n"
                    f"🆕 Minicurso: {_price_for_client('minicourse_already_on_island')}\n"
                    f"🐠 Snorkel: {_price_for_client('snorkeling_already_on_island')}"
                )
            elif choice == 3:
                state.step = Step.PRICING_PACKAGES
                response = (
                    "📦 *Paquetes multi-día*:\n\n"
                    f"🤿 5 buceos (2 días): {_price_for_client('5_dives_2_days')}\n"
                    f"🤿 7 buceos (3 días): {_price_for_client('7_dives_3_days')}\n"
                    f"🤿 9 buceos (4 días): {_price_for_client('9_dives_4_days')}\n\n"
                    "🏝️ *Versiones si ya estás en las islas*:\n\n"
                    f"🤿 5 buceos (2 días): {_price_for_client('5_dives_2_days_already_on_island')}\n"
                    f"🤿 7 buceos (3 días): {_price_for_client('7_dives_3_days_already_on_island')}\n"
                    f"🤿 9 buceos (4 días): {_price_for_client('9_dives_4_days_already_on_island')}\n\n"
                    "🏨 El alojamiento en las islas se reserva aparte directamente con el hotel."
                )
            else:  # choice == 4
                state.step = Step.PRICING_DISCOUNTS
                response = (
                    "🇨🇴 *Descuentos para colombianos y residentes*:\n\n"
                    "💸 10% online\n"
                    "👥 Descuentos para grupos\n\n"
                    "📲 Escríbenos por WhatsApp y te aplicamos la tarifa local cuando corresponda "
                    "(te pediremos cédula o documento de residencia)."
                )
        else:
            if choice == 1:
                state.step = Step.PRICING_CARTAGENA
                response = (
                    "🚤 *Reference prices departing from Cartagena*\n"
                    "(includes speedboat + lunch + park entrance):\n\n"
                    f"🤿 2 dives (1 day): {_price_for_client('2_dives_1_day')}\n"
                    f"🆕 Dive minicourse: {_price_for_client('minicourse')}\n"
                    f"🐠 Snorkeling tour: {_price_for_client('snorkeling')}"
                )
            elif choice == 2:
                location_note = ""
                if state.location == "island":
                    location_note = "Since you already indicated you are on the islands, "
                state.step = Step.PRICING_ISLANDS
                response = (
                    f"{location_note}🏝️ *Prices for guests already on the Rosario Islands*\n"
                    "(no transport from Cartagena and no lunch):\n\n"
                    f"🤿 2 dives: {_price_for_client('2_dives_1_day_already_on_island')}\n"
                    f"🌙 3 dives with night dive: {_price_for_client('3_dives_1_day_already_on_island')}\n"
                    f"🆕 Dive minicourse: {_price_for_client('minicourse_already_on_island')}\n"
                    f"🐠 Snorkeling: {_price_for_client('snorkeling_already_on_island')}"
                )
            elif choice == 3:
                state.step = Step.PRICING_PACKAGES
                response = (
                    "📦 *Multi-day packages*:\n\n"
                    f"🤿 5 dives (2 days): {_price_for_client('5_dives_2_days')}\n"
                    f"🤿 7 dives (3 days): {_price_for_client('7_dives_3_days')}\n"
                    f"🤿 9 dives (4 days): {_price_for_client('9_dives_4_days')}\n\n"
                    "🏝️ *Versions if you're already on the islands*:\n\n"
                    f"🤿 5 dives (2 days): {_price_for_client('5_dives_2_days_already_on_island')}\n"
                    f"🤿 7 dives (3 days): {_price_for_client('7_dives_3_days_already_on_island')}\n"
                    f"🤿 9 dives (4 days): {_price_for_client('9_dives_4_days_already_on_island')}\n\n"
                    "🏨 Accommodation on the islands is not included and is booked directly with the hotel."
                )
            else:  # choice == 4
                state.step = Step.PRICING_DISCOUNTS
                response = (
                    "🇨🇴 *Discounts for Colombian guests and residents*:\n\n"
                    "💸 Online discount\n"
                    "👥 Group discounts\n\n"
                    "📲 Contact us on WhatsApp and we can apply the local rate when applicable and explain the conditions."
                )

        self.set_quick_replies(state, "pricing_leaf")
        return response

    def _handle_pricing_cartagena(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 1)
        if msg == "reserve" or choice == 1:
            return self._enter_booking_cart(state)
        self.set_quick_replies(state, "pricing_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_pricing_islands(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 1)
        if msg == "reserve" or choice == 1:
            return self._enter_booking_cart(state)
        self.set_quick_replies(state, "pricing_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_pricing_packages(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 1)
        if msg == "reserve" or choice == 1:
            return self._enter_booking_cart(state)
        self.set_quick_replies(state, "pricing_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_pricing_discounts(self, state: ConversationState, message: str) -> str:
        msg = " ".join(message.strip().lower().split())
        choice = self._parse_choice(message, 1)
        if msg == "reserve" or choice == 1:
            return self._enter_booking_cart(state)
        self.set_quick_replies(state, "pricing_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_island_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 12)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "island_menu")
            return MESSAGES["not_understood"][lang]

        islands = {
            1: "Isla Grande",
            2: "Isla Marina",
            3: "Isla del Pirata",
            4: "Isla del Sol",
            5: "Isleta",
            6: "Isla Arena",
            7: "Isla Pavitos",
            8: "Isla Lizamar",
            9: "Isla Gigi",
            10: "Isla Rosa",
            11: "Isla Pelicano",
            12: "Isla Rosario",
        }

        island_name = islands.get(choice)
        if not island_name:
            self.set_quick_replies(state, "island_menu")
            return MESSAGES["not_understood"][lang]

        state.island = island_name

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
            if lang == "es":
                quick_replies.append({"title": "⬅️ Volver", "value": "back"})
                quick_replies.append({"title": "🏠 Inicio", "value": "inicio"})
            else:
                quick_replies.append({"title": "⬅️ Back", "value": "back"})
                quick_replies.append({"title": "🏠 Home", "value": "inicio"})

            state.step = Step.ISLAND_HOTEL_MENU
            state.quick_replies = quick_replies

            if lang == "es":
                return (
                    f"Perfecto, estas en *{island_name}*.\n\n"
                    "Ahora dime en que hotel te hospedas. Si no ves tu alojamiento, elige \"Otro / No esta en la lista\"."
                )
            return (
                f"Great, you are on *{island_name}*.\n\n"
                "Now tell me which hotel you are staying at. If you don't see it, choose \"Other / Not listed\"."
            )

        if lang == "es":
            response = (
                f"Perfecto, tomamos nota de que te hospedas en *{island_name}*.\n\n"
                "Con esto podemos coordinar mejor horarios de recogida y regreso segun el acceso en lancha.\n\n"
                "Si quieres, ahora puedes revisar otros puntos de logistica o volver al menu principal."
            )
        else:
            response = (
                f"Great, we have noted that you are staying on *{island_name}*.\n\n"
                "This helps us coordinate pickup and return times depending on boat access.\n\n"
                "You can now check other logistics topics or go back to the main menu."
            )

        state.step = Step.LOGISTICS_MENU
        self.set_quick_replies(state, "logistics_menu")
        return response

    def _handle_island_hotel_menu(self, state: ConversationState, message: str) -> str:
        lang = state.language
        if not state.island:
            state.step = Step.ISLAND_MENU
            self.set_quick_replies(state, "island_menu")
            return MESSAGES["island_menu"][lang]

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
        max_options = len(island_hotels) + 1 if island_hotels else 1
        choice = self._parse_choice(message, max_options)

        if choice is None:
            # reconstruir quick replies para este paso
            quick_replies: list[dict] = []
            for idx, hotel_name in enumerate(island_hotels, start=1):
                quick_replies.append({"title": hotel_name, "value": str(idx)})
            if island_hotels:
                other_title = "Otro / No esta en la lista" if lang == "es" else "Other / Not listed"
                quick_replies.append({"title": other_title, "value": str(len(island_hotels) + 1)})
            if lang == "es":
                quick_replies.append({"title": "⬅️ Volver", "value": "back"})
                quick_replies.append({"title": "🏠 Inicio", "value": "inicio"})
            else:
                quick_replies.append({"title": "⬅️ Back", "value": "back"})
                quick_replies.append({"title": "🏠 Home", "value": "inicio"})
            state.quick_replies = quick_replies
            return MESSAGES["not_understood"][lang]

        if not island_hotels:
            state.hotel = None
        elif choice <= len(island_hotels):
            state.hotel = island_hotels[choice - 1]
        else:
            state.hotel = "Otro / No esta en la lista"

        island_name = state.island
        hotel_name = state.hotel

        # Venimos de cambiar el origen del carrito a "island" (Cambiar origen
        # o "estoy en las islas" por texto libre) — remapear precios y volver
        # al resumen del carrito, no a un flujo de añadir que nunca empezo.
        if state.mixed_pending_location_change:
            state.mixed_pending_location_change = False
            self._remap_cart_for_location(state)
            if hotel_name and hotel_name != "Otro / No esta en la lista":
                intro = (
                    f"📍 Origen actualizado a *{island_name}* (*{hotel_name}*). Precios y servicios ajustados.\n\n"
                    if lang == "es"
                    else f"📍 Origin updated to *{island_name}* (*{hotel_name}*). Prices and services adjusted.\n\n"
                )
            else:
                intro = (
                    f"📍 Origen actualizado a *{island_name}*. Precios y servicios ajustados.\n\n"
                    if lang == "es"
                    else f"📍 Origin updated to *{island_name}*. Prices and services adjusted.\n\n"
                )
            return intro + self._goto_mixed_cart_review(state)

        # Si venimos del flujo de reserva (mixed flow), continuar con ese flujo
        if state.mixed_pending_qty_type:
            # Certificado → ir a elegir plan
            if state.mixed_pending_qty_type == "cert":
                state.step = Step.MIXED_ADD_CERT_PLAN
                self.set_quick_replies(state, "mixed_add_cert_plan")
                return MESSAGES["mixed_add_cert_plan"][lang]
            # Principiante, snorkel, etc. → ir a cantidad
            else:
                state.step = Step.MIXED_ADD_QTY
                self.set_quick_replies(state, "mixed_quantity")
                return MESSAGES["mixed_add_qty"][lang]

        # Estamos en el flujo de carrito pero aun sin actividad elegida (p.ej.
        # se pregunto el hotel justo despues de fijar la ubicacion, antes de
        # elegir que añadir) → volver al menu de actividades, no a logistica.
        if state.mixed_entry_path:
            intro = ""
            if hotel_name and hotel_name != "Otro / No esta en la lista":
                intro = (
                    f"Perfecto, tomamos nota de que te hospedas en *{hotel_name}* en *{island_name}*.\n\n"
                    if lang == "es"
                    else f"Great, we've noted you're staying at *{hotel_name}* on *{island_name}*.\n\n"
                )
            return intro + self._goto_mixed_add_activity(state)

        # Si NO venimos del flujo de reserva, es el flujo de logística normal
        if lang == "es":
            if hotel_name and hotel_name != "Otro / No esta en la lista":
                response = (
                    f"Perfecto, tomamos nota de que te hospedas en *{hotel_name}* en *{island_name}*.\n\n"
                    "Con esto podemos coordinar mejor horarios de recogida y regreso segun el acceso en lancha.\n\n"
                    "Ahora puedes revisar otros puntos de logistica o volver al menu principal."
                )
            else:
                response = (
                    f"Perfecto, tomamos nota de que te hospedas en otro alojamiento de *{island_name}*.\n\n"
                    "Aunque tu hotel no este en la lista, coordinaremos la logistica de recogida según el acceso disponible.\n\n"
                    "Ahora puedes revisar otros puntos de logistica o volver al menu principal."
                )
        else:
            if hotel_name and hotel_name != "Otro / No esta en la lista":
                response = (
                    f"Great, we have noted that you are staying at *{hotel_name}* on *{island_name}*.\n\n"
                    "This helps us coordinate pickup and return times depending on boat access.\n\n"
                    "You can now check other logistics topics or go back to the main menu."
                )
            else:
                response = (
                    f"Great, we have noted that you are staying at another place on *{island_name}*.\n\n"
                    "Even if your hotel is not listed, we will coordinate logistics according to the available access.\n\n"
                    "You can now check other logistics topics or go back to the main menu."
                )

        state.step = Step.LOGISTICS_MENU
        self.set_quick_replies(state, "logistics_menu")
        return response

    def _handle_booking_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "booking_menu")
            return MESSAGES["not_understood"][lang]

        if lang == "es":
            if choice == 1:
                response = (
                    "Puedes hacer la *reserva completa online* usando el enlace que te enviamos para cada plan.\n\n"
                    "Al completar el pago recibes la confirmacion por correo y WhatsApp con todos los detalles "
                    "de la salida."
                )
            elif choice == 2:
                response = (
                    "En muchos casos es posible pagar solo el *50% como anticipo* y el resto el dia de la salida.\n\n"
                    "El asesor te indicara si aplica en tu caso (tipo de plan, fecha, numero de personas) y te "
                    "enviara el enlace o instrucciones para el pago parcial."
                )
            elif choice == 3:
                response = (
                    "Manejamos diferentes *formas de pago*: tarjeta de credito extranjera, pasarela local y/o "
                    "transferencia bancaria en Colombia.\n\n"
                    "En el enlace de pago veras las opciones disponibles para tu moneda y pais."
                )
            else:  # choice == 4
                response = (
                    "Para *grupos y agencias* podemos generar enlaces de pago separados (buceo, minicurso, snorkel, "
                    "acompañantes) o coordinar una reserva centralizada.\n\n"
                    "Un asesor revisara fechas, numero de personas y necesidades especiales antes de confirmar."
                )
        else:
            if choice == 1:
                response = (
                    "You can *book and pay everything online* using the link we send for each plan.\n\n"
                    "Once payment is completed, you'll receive a confirmation by email and WhatsApp with all "
                    "the details of your trip."
                )
            elif choice == 2:
                response = (
                    "In many cases you can pay only *50% as a deposit* and the rest on the day of the trip.\n\n"
                    "The advisor will confirm if this applies to your case (plan type, dates, group size) and "
                    "send you the right payment link or instructions."
                )
            elif choice == 3:
                response = (
                    "We support several *payment methods*: international credit card, local payment gateway and/or "
                    "bank transfer within Colombia.\n\n"
                    "The payment link will show the options available for your country and currency."
                )
            else:  # choice == 4
                response = (
                    "For *groups and agencies* we can create separate payment links (diving, minicourse, snorkel, "
                    "companions) or coordinate a centralized booking.\n\n"
                    "An advisor will review dates, group size and any special needs before confirming."
                )

        state.step = Step.MAIN_MENU
        self.set_quick_replies(state, "main_menu")
        return response + self._back_to_menu_hint(lang)

    def _handle_logistics_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "logistics_menu")
            return MESSAGES["not_understood"][lang]

        if lang == "es":
            if choice == 1:
                # Punto de encuentro y horarios
                if state.location == "cartagena":
                    response = (
                        "📍 *Punto de encuentro y horarios (Cartagena)*\n\n"
                        "⏰ Encuentro: *Muelle de la Bodeguita* a las *8:00 a.m.* (entrada 3).\n"
                        "↩️ Regreso estimado (tours de 1 día): *4:00–4:30 p.m.*\n\n"
                        "📦 En paquetes multi-día, el horario se ajusta según tu plan y alojamiento."
                    )
                else:
                    response = (
                        "📍 *Punto de encuentro y horarios*\n\n"
                        "⏰ Encuentro (Cartagena): *Muelle de la Bodeguita* a las *8:00 a.m.*\n"
                        "↩️ Regreso estimado (tours de 1 día): *4:00–4:30 p.m.*\n\n"
                        "🏝️ Si ya estás en las islas o es un paquete multi-día, coordinamos horarios específicos según tu plan y alojamiento."
                    )
                state.step = Step.LOGISTICS_MEETING
                self.set_quick_replies(state, "logistics_leaf")
                return response
            elif choice == 2:
                # Alojamiento en islas y recogida en hotel -> ir al selector de isla
                state.step = Step.ISLAND_MENU
                self.set_quick_replies(state, "island_menu")
                return MESSAGES["island_menu"][lang]
            elif choice == 3:
                # Que incluye / que no incluye el plan
                if state.location == "island":
                    location_line = (
                        "🏝️ Como ya estás en las islas, normalmente la tarifa cubre el servicio de buceo/snorkel *sin* transporte desde Cartagena ni almuerzo.\n\n"
                    )
                else:
                    location_line = ""
                response = (
                    f"{location_line}"
                    "✅ *Incluye (en general)*:\n"
                    "- 🎟️ Entrada al Parque Nacional\n"
                    "- 🛟 Seguro de buceo\n"
                    "- 🤿 Equipo completo\n"
                    "- 🚤 Lancha Cartagena ↔ Islas (si aplica)\n"
                    "- 🍽️ Almuerzo (si aplica)\n"
                    "- 🌱 Aporte eco-social a DIVE TO HEAL\n\n"
                    "❌ *No incluye normalmente*:\n"
                    "- 🚕 Transporte terrestre al muelle\n"
                    "- 📸 Fotos / videos\n"
                    "- 💁 Propinas\n"
                    "- 🍴 Comidas extra\n"
                    "- 🗓️ Regreso en una fecha distinta"
                )
                state.step = Step.LOGISTICS_INCLUDES
                self.set_quick_replies(state, "logistics_leaf")
                return response
            else:  # choice == 4
                # Que llevar y recomendaciones
                response = (
                    "🎒 *Qué llevar (recomendado)*:\n"
                    "- 🧴 Bloqueador solar\n"
                    "- 🧢 Gorra / sombrero\n"
                    "- 👕 Ropa cómoda\n"
                    "- 🧻 Toalla\n"
                    "- 💊 Si te mareas: tu medicación para el mareo\n\n"
                    "🌦️ Las salidas dependen del clima y el mar. Si hay cambios o cancelaciones, coordinamos reprogramación o reembolso según la política del plan."
                )
                state.step = Step.LOGISTICS_WHAT_TO_BRING
                self.set_quick_replies(state, "logistics_leaf")
                return response
        else:
            if choice == 1:
                if state.location == "cartagena":
                    response = (
                        "📍 *Meeting point & schedule (Cartagena)*\n\n"
                        "⏰ Meeting point: *Muelle de la Bodeguita* at *8:00 a.m.* (gate 3).\n"
                        "↩️ Usual return time (1-day tours): *4:00–4:30 p.m.*\n\n"
                        "📦 For multi-day packages, the schedule depends on your plan and accommodation."
                    )
                else:
                    response = (
                        "📍 *Meeting point & schedule*\n\n"
                        "⏰ Meeting point (Cartagena): *Muelle de la Bodeguita* at *8:00 a.m.*\n"
                        "↩️ Usual return time (1-day tours): *4:00–4:30 p.m.*\n\n"
                        "🏝️ If you are already on the islands or on a multi-day package, we coordinate exact times depending on your plan and accommodation."
                    )
                state.step = Step.LOGISTICS_MEETING
                self.set_quick_replies(state, "logistics_leaf")
                return response
            elif choice == 2:
                state.step = Step.ISLAND_MENU
                self.set_quick_replies(state, "island_menu")
                return MESSAGES["island_menu"][lang]
            elif choice == 3:
                if state.location == "island":
                    location_line = (
                        "🏝️ Since you are already on the islands, rates usually cover mainly the diving/snorkel service *without* transport from Cartagena or lunch.\n\n"
                    )
                else:
                    location_line = ""
                response = (
                    f"{location_line}"
                    "✅ *Usually included*:\n"
                    "- 🎟️ National Park entrance\n"
                    "- 🛟 Dive insurance\n"
                    "- 🤿 Full equipment\n"
                    "- 🚤 Boat transfer Cartagena ↔ Islands (if applicable)\n"
                    "- 🍽️ Lunch (if applicable)\n"
                    "- 🌱 Eco-social contribution to DIVE TO HEAL\n\n"
                    "❌ *Usually not included*:\n"
                    "- 🚕 Ground transportation to the dock\n"
                    "- 📸 Photos / videos\n"
                    "- 💁 Tips\n"
                    "- 🍴 Extra food\n"
                    "- 🗓️ Return on a different date"
                )
                state.step = Step.LOGISTICS_INCLUDES
                self.set_quick_replies(state, "logistics_leaf")
                return response
            else:  # choice == 4
                response = (
                    "🎒 *What to bring (recommended)*:\n"
                    "- 🧴 Sunscreen\n"
                    "- 🧢 Hat\n"
                    "- 👕 Comfortable clothes\n"
                    "- 🧻 Towel\n"
                    "- 💊 Seasickness medication (if needed)\n\n"
                    "🌦️ Trips depend on weather and sea conditions. If there are changes or cancellations we coordinate rescheduling or refunds according to the plan policy."
                )
                state.step = Step.LOGISTICS_WHAT_TO_BRING
                self.set_quick_replies(state, "logistics_leaf")
                return response

    def _handle_logistics_meeting(self, state: ConversationState, message: str) -> str:
        self.set_quick_replies(state, "logistics_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_logistics_includes(self, state: ConversationState, message: str) -> str:
        self.set_quick_replies(state, "logistics_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_logistics_what_to_bring(self, state: ConversationState, message: str) -> str:
        self.set_quick_replies(state, "logistics_leaf")
        return MESSAGES["not_understood"][state.language]

    def _handle_courses_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice == 1:
            if state.location is None:
                state.step = Step.COURSES_OPEN_WATER_ORIGIN
                self.set_quick_replies(state, "courses_open_water_origin")
                return MESSAGES["courses_open_water_origin"][lang]
            return self._start_mixed_course_add(
                state,
                self._service_for_location("open_water", state),
                "open_water_time",
            )
        if choice == 2:
            state.step = Step.COURSES_ADVANCED_MENU
            self.set_quick_replies(state, "courses_advanced_menu")
            return MESSAGES["courses_advanced_menu"][lang]
        if choice == 3:
            state.step = Step.COURSES_SPECIALTIES_MENU
            self.set_quick_replies(state, "courses_specialties_menu")
            return MESSAGES["courses_specialties_menu"][lang]
        if choice == 4:
            return self._start_mixed_course_add(
                state,
                self._service_for_location("referral", state),
            )

        self.set_quick_replies(state, "courses_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_courses_open_water_origin(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.location = "cartagena"
        elif choice == 2:
            state.location = "island"
        else:
            self.set_quick_replies(state, "courses_open_water_origin")
            return MESSAGES["not_understood"][lang]

        return self._start_mixed_course_add(
            state,
            self._service_for_location("open_water", state),
            "open_water_time",
        )

    def _handle_courses_open_water_time(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "courses_open_water_time")
            return MESSAGES["not_understood"][lang]

        preview = self._prepare_mixed_add_preview(
            state,
            state.mixed_pending_qty_plan or self._service_for_location("open_water", state),
        )
        if choice == 2:
            return self._open_water_time_warning(state) + "\n\n" + preview
        return preview

    def _handle_courses_advanced_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language
        course_map = {
            1: self._service_for_location("advanced", state),
            2: "rescue",
            3: "divemaster",
        }

        if choice in course_map:
            if course_map[choice] in SPECIALTY_SERVICE_IDS and course_map[choice] not in SERVICES:
                state.step = Step.ESCALATE
                state.quick_replies = []
                return MESSAGES["escalate"][lang]
            return self._start_mixed_course_add(state, course_map[choice])

        self.set_quick_replies(state, "courses_advanced_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_courses_specialties_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 5)
        lang = state.language
        course_map = {
            1: "mindful_diving",
            2: self._service_for_location("fish_identification_specialty", state),
            3: self._service_for_location("naturalist_specialty", state),
            4: self._service_for_location("buoyancy_specialty", state),
            5: self._service_for_location("nitrox_specialty", state),
        }

        if choice in course_map:
            if course_map[choice] in SPECIALTY_SERVICE_IDS and course_map[choice] not in SERVICES:
                state.step = Step.ESCALATE
                state.quick_replies = []
                return MESSAGES["escalate"][lang]
            return self._start_mixed_course_add(state, course_map[choice])

        self.set_quick_replies(state, "courses_specialties_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_service_detail(self, state: ConversationState, message: str) -> str:
        # Fallback: show detail and go to location
        state.step = Step.LOCATION
        self.set_quick_replies(state, "location")
        return MESSAGES["location"][state.language]

    def _handle_location(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.location = "cartagena"
        elif choice == 2:
            state.location = "island"
        else:
            self.set_quick_replies(state, "location")
            return MESSAGES["not_understood"][lang]

        if state.selected_service:
            state.selected_service = self._service_for_location(state.selected_service, state)
        state.step = Step.COLOMBIAN
        self.set_quick_replies(state, "colombian")
        return MESSAGES["colombian"][lang]

    def _handle_colombian(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.is_colombian = True
        elif choice == 2:
            state.is_colombian = False
        else:
            self.set_quick_replies(state, "colombian")
            return MESSAGES["not_understood"][lang]

        if state.selected_service:
            state.selected_service = self._service_for_location(state.selected_service, state)
        state.step = Step.SUMMARY
        state.summary_mode = "itinerary_offer"
        self.set_quick_replies(state, self._itinerary_offer_quick_replies_key(state))
        return self._format_summary(state)

    def _single_service_reservar_response(self, state: ConversationState) -> str:
        """Resolve the 'Reservar' action for a single bookable service.

        Non-Colombian clients pay 100% online, so we send the booking link
        directly instead of escalating. Colombian clients (split payment +
        discount coordination) and services without a resolvable link still
        go through the advisor as before.
        """
        lang = state.language
        service = SERVICES.get(state.selected_service) or {}
        url = None if state.is_colombian else _resolve_service_booking_url(service, state)
        if url:
            label = service.get(f"name_{lang}") or state.selected_service
            state.step = Step.FREE_TEXT
            state.quick_replies = []
            state.pending_lead_note_reason = "cliente confirmó reserva, link enviado directamente"
            block = _format_booking_links_block([(label, url)], lang)
            if lang == "es":
                return (
                    f"¡Perfecto! 🎉 Aquí tienes tu link de reserva (10% de descuento pagando online):\n\n{block}\n\n"
                    "Al completar el pago tu reserva queda registrada. Si tienes alguna duda, escríbeme.\n\n"
                    "Si necesitas algo más, escribe *menu* para volver al inicio."
                )
            return (
                f"Great! 🎉 Here's your booking link (10% off paying online):\n\n{block}\n\n"
                "Once payment is completed your booking is confirmed. If you have any questions, just ask.\n\n"
                "If you need anything else, type *menu* to go back."
            )

        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "cliente quiere reservar - confirma asesor"
        if lang == "es":
            return (
                "¡Perfecto! Te paso con un asesor para confirmar disponibilidad "
                "y precio final. Enseguida se pone en contacto contigo y te envía el link de reserva."
            )
        return (
            "Great! I'll connect you with an advisor to confirm availability "
            "and the final price. They will be in touch shortly with the booking link."
        )

    def _single_service_cash_payment_response(self, state: ConversationState) -> str:
        """Client wants to book but pay in person (no online payment at all) —
        always escalate, regardless of nationality; the advisor coordinates
        the in-person payment instead of sending a booking link."""
        lang = state.language
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "cliente quiere pagar en persona, no online"
        if lang == "es":
            return (
                "¡Perfecto! Te paso con un asesor para coordinar el pago presencial y confirmar "
                "disponibilidad y precio final. Enseguida se pone en contacto contigo."
            )
        return (
            "Great! I'll connect you with an advisor to arrange in-person payment and confirm "
            "availability and the final price. They will be in touch shortly."
        )

    def _handle_summary(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = " ".join(message.strip().lower().split())
        service_id = state.selected_service
        summary_mode = state.summary_mode or "itinerary_offer"

        contact_only = _is_contact_only_service(service_id)
        max_options = 2
        if summary_mode == "itinerary_offer" and contact_only:
            max_options = 2
        elif summary_mode != "itinerary_offer" and contact_only:
            max_options = 3
        elif summary_mode != "itinerary_offer":
            max_options = 1
        choice = self._parse_choice(message, max_options)
        action = None

        if msg in ("itinerary", "skip", "ask", "done", "contact", "reservar", "book", "cash", "efectivo", "pago presencial"):
            if msg == "book":
                action = "reservar"
            elif msg in ("efectivo", "pago presencial"):
                action = "cash"
            else:
                action = msg

        if choice is None:
            if is_affirmative(msg):
                choice = 1
            elif msg in (
                "no",
                "gracias",
                "no gracias",
                "no, gracias",
                "thanks",
                "no thanks",
                "no, thanks",
            ):
                # En itinerary_offer ya no hay botón "No gracias" — la respuesta "no" se mapea a skip
                if contact_only and summary_mode == "itinerary_offer":
                    action = "skip"
                elif contact_only:
                    choice = 3
                else:
                    action = "skip"

        if summary_mode == "itinerary_offer":
            if service_id in {"referral", "referral_already_on_island"} and action == "reservar":
                state.summary_mode = None
                state.step = Step.ESCALATE
                state.quick_replies = []
                state.pending_escalation_reason = "solicitó contacto para curso referido"
                return _referral_escalation_message(state)

            if contact_only and action == "reservar":
                action = "contact"

            if action == "reservar" and not contact_only:
                state.summary_mode = None
                return self._single_service_reservar_response(state)

            if action == "cash" and not contact_only and service_id not in {"referral", "referral_already_on_island"}:
                state.summary_mode = None
                return self._single_service_cash_payment_response(state)

            if action == "itinerary" or choice == 1:
                state.summary_mode = "follow_up"
                self.set_quick_replies(state, self._summary_quick_replies_key(state))
                if contact_only:
                    return self._format_full_itinerary(state) + MESSAGE_SPLIT + _divemaster_follow_up_prompt(lang)
                if service_id in {"referral", "referral_already_on_island"}:
                    if lang == "es":
                        return (
                            self._format_full_itinerary(state)
                            + MESSAGE_SPLIT
                            + "Si quieres avanzar con tu curso referido o aclarar tu caso especifico, puedo ponerse en contacto con mi jefe para ayudarte a reservar."
                        )
                    return (
                        self._format_full_itinerary(state)
                        + MESSAGE_SPLIT
                        + "If you would like to move forward with your referral course or clarify your specific case, I can connect you with my manager to help you book."
                    )

                if lang == "es":
                    return self._format_full_itinerary(state) + MESSAGE_SPLIT + "¿Quieres preguntarme algo más?"
                return self._format_full_itinerary(state) + MESSAGE_SPLIT + "Would you like to ask anything else?"

            if contact_only and (action == "contact" or choice == 2):
                state.summary_mode = None
                state.step = Step.ESCALATE
                state.quick_replies = []
                state.pending_escalation_reason = "solicitó contacto para curso divemaster"
                if lang == "es":
                    return (
                        "Perfecto. Si ya estas 100% interesado/a en el curso Dive Master, te pongo en contacto con mi jefe "
                        "para revisar tu perfil, fechas y modalidad del programa."
                    )
                return (
                    "Perfect. If you are already 100% interested in the Dive Master course, I'll connect you with my manager "
                    "to review your profile, dates, and the best program format for you."
                )

            if action == "skip":
                state.summary_mode = "follow_up"
                self.set_quick_replies(state, self._summary_quick_replies_key(state))
                if contact_only:
                    return _divemaster_follow_up_prompt(lang)
                if service_id in {"referral", "referral_already_on_island"}:
                    if lang == "es":
                        return (
                            "Perfecto. Si quieres avanzar con tu curso referido o resolver dudas especificas de tu caso, "
                            "puedo ponerte en contacto con mi jefe para ayudarte a reservar."
                        )
                    return (
                        "Great. If you would like to move forward with your referral course or clarify your specific case, "
                        "I can connect you with my manager to help you book."
                    )
                if lang == "es" and service_id == "2_dives_1_day" and state.is_certified:
                    return (
                        "Perfecto. Si en algún momento quieres reservar este plan, el siguiente paso "
                        "es completar un formulario de exoneración para buzos certificados "
                        "(es obligatorio para el seguro y el zarpe):\n"
                        "https://form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol\n\n"
                        "¿Quieres preguntarme algo más?"
                    )
                if lang == "en" and service_id == "2_dives_1_day" and state.is_certified:
                    return (
                        "Great. If at any point you decide to book this plan, the next step is to complete "
                        "a liability waiver form for certified divers (it's mandatory for insurance and "
                        "boat clearance):\n"
                        "https://form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol\n\n"
                        "Would you like to ask anything else?"
                    )
                if lang == "es":
                    return "Perfecto. ¿Quieres preguntarme algo más?"
                return "Perfect. Would you like to ask anything else?"

            self.set_quick_replies(state, self._itinerary_offer_quick_replies_key(state))
            return MESSAGES["not_understood"][lang]

        if contact_only and (action == "contact" or choice == 1):
            state.summary_mode = None
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "solicitó contacto para curso divemaster"
            if lang == "es":
                return (
                    "Perfecto. Si ya estas 100% interesado/a en el curso Dive Master, te pongo en contacto con mi jefe "
                    "para revisar tu perfil, fechas y modalidad del programa."
                )
            return (
                "Perfect. If you are already 100% interested in the Dive Master course, I'll connect you with my manager "
                "to review your profile, dates, and the best program format for you."
            )

        if service_id in {"referral", "referral_already_on_island"} and (action == "contact" or action == "reservar" or choice == 1):
            state.summary_mode = None
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "solicitó contacto para curso referido"
            return _referral_escalation_message(state)

        if action == "reservar" and not contact_only and service_id not in {"referral", "referral_already_on_island"}:
            state.summary_mode = None
            return self._single_service_reservar_response(state)

        if action == "cash" and not contact_only and service_id not in {"referral", "referral_already_on_island"}:
            state.summary_mode = None
            return self._single_service_cash_payment_response(state)

        ask_choice = 2 if contact_only else (None if service_id in {"referral", "referral_already_on_island"} else 1)
        if action == "ask" or (ask_choice is not None and choice == ask_choice):
            state.summary_mode = None
            # Para el curso referido, en lugar de pasar a FREE_TEXT derivamos directamente a humano
            # con el mensaje explicativo de referral + el mensaje generico de escalada.
            if service_id in {"referral", "referral_already_on_island"}:
                state.step = Step.ESCALATE
                state.quick_replies = []
                state.pending_escalation_reason = "solicitó contacto para curso referido"
                return _referral_escalation_message(state)

            state.step = Step.FREE_TEXT
            state.quick_replies = []
            if lang == "es":
                return "Perfecto. ¿Qué te gustaría preguntarme?"
            return "Perfect. What would you like to ask me?"

        if action == "done" or choice == (3 if contact_only else 99):
            state.summary_mode = None
            state.step = Step.FREE_TEXT
            state.quick_replies = []
            if lang == "es":
                return (
                    "¡Gracias por contactar a Diving Planet! 🤿\n"
                    "Si necesitas algo más, escribe *menu* para volver al inicio.\n"
                    "¡Te esperamos en las Islas del Rosario!"
                )
            return (
                "Thank you for contacting Diving Planet! 🤿\n"
                "If you need anything else, type *menu* to go back.\n"
                "We look forward to seeing you at the Rosario Islands!"
            )

        self.set_quick_replies(state, self._summary_quick_replies_key(state))
        return MESSAGES["not_understood"][lang]

    def _format_full_itinerary(self, state: ConversationState) -> str:
        service = SERVICES.get(state.selected_service)
        if not service:
            return MESSAGES["escalate"][state.language]

        lang = state.language
        service_id = state.selected_service
        accommodation_note = _accommodation_requirement_note(service_id, service, lang)
        if lang == "es":
            description = service.get("description_es")
            preparation = service.get("preparation_es")
            overview = service.get("itinerary_overview_es") or []
            itinerary = service.get("itinerary_es") or []
            requirements = service.get("requirements_es") or []
            not_included = service.get("not_included_es") or []
            web_url = service.get("web_url")
            contact_only = service.get("contact_only", False)
            title_overview = "📘 **Resumen del programa:**"
            title_itinerary = "🗺️ **Itinerario:**"
            title_requirements = "✅ **Requisitos:**"
            title_not_included = "❌ **No incluye:**"
            title_link = "🔗 Link de la actividad en la web:"
            payment_title = "🔗 Link de reserva (10% off online):"
        else:
            description = service.get("description_en")
            preparation = service.get("preparation_en")
            overview = service.get("itinerary_overview_en") or []
            itinerary = service.get("itinerary_en") or []
            requirements = service.get("requirements_en") or []
            not_included = service.get("not_included_en") or []
            web_url = service.get("web_url")
            contact_only = service.get("contact_only", False)
            title_overview = "📘 **Program overview:**"
            title_itinerary = "🗺️ **Itinerary:**"
            title_requirements = "✅ **Requirements:**"
            title_not_included = "❌ **Not included:**"
            title_link = "🔗 Activity page link:"
            payment_title = "🔗 Booking link (10% off online):"

        # Elegimos el booking_url igual que en el resumen
        booking_url = _resolve_service_booking_url(service, state)

        # Mientras el flujo de pago para colombianos esté pendiente de confirmación,
        # no mostramos el link real de pasarela/reserva a clientes colombianos.
        if state.is_colombian:
            booking_url = "PENDIENTE"

        # Reagrupamos el itinerario por dia para no repetir "Dia 1:" / "Day 1:" en cada linea
        if itinerary:
            itinerary = _group_itinerary_by_day(itinerary, lang)

        # Filtramos reglas genericas de vuelo y propinas del detalle completo
        if requirements:
            if lang == "es":
                requirements = [
                    item
                    for item in requirements
                    if not ("esperar minimo 18 horas" in item.lower() and "vuelo" in item.lower())
                ]
            else:
                requirements = [
                    item
                    for item in requirements
                    if not ("18 hours" in item.lower() and ("fly" in item.lower() or "flying" in item.lower()))
                ]

        if not_included:
            if lang == "es":
                not_included = [
                    item for item in not_included if "propinas voluntarias" not in item.lower()
                ]
            else:
                not_included = [
                    item for item in not_included if "voluntary tips" not in item.lower()
                ]

        # Construimos bloques separados para controlar bien los espacios entre secciones
        blocks: list[list[str]] = []

        svc_title = service.get(f"name_{lang}") or service.get("name_es") or ""
        if svc_title:
            blocks.append([f"🤿 *{svc_title}*"])

        if description and not _is_padi_course_service(service_id):
            blocks.append([f"ℹ️ {description}"])

        if accommodation_note:
            blocks.append([accommodation_note])

        if overview or (preparation and contact_only):
            block = [title_overview]
            for item in overview:
                block.append(item)
            if preparation:
                block.append(preparation)
            blocks.append(block)

        if itinerary:
            block = [title_itinerary]
            for item in itinerary:
                # Sin guion al inicio para evitar formato de lista Markdown y el espacio extra
                block.append(item)
            blocks.append(block)

        if requirements:
            block = [title_requirements]
            for item in requirements:
                block.append(item)
            blocks.append(block)

        if not_included:
            block = [title_not_included]
            for item in not_included:
                block.append(item)
            blocks.append(block)

        if web_url:
            block = [title_link, web_url]
            blocks.append(block)

        # El link de reserva/pago ya no se muestra al cliente: lo envía el asesor
        # tras confirmar disponibilidad y precio final (patrón unificado).

        # Bloque con formulario de exoneración para buzos certificados
        # (implementado inicialmente solo para 2 buceos - 1 día en español)
        if service_id == "2_dives_1_day" and state.is_certified:
            if lang == "es":
                exo_block = [
                    "📝 Siguiente paso si quieres reservar este plan:",
                    "Antes de salir al mar necesitamos que completes un formulario de exoneración para buzos certificados (es obligatorio para el seguro y el zarpe):",
                    "https://form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol",
                ]
            else:
                exo_block = [
                    "📝 Next step if you would like to book this plan:",
                    "Before going out to sea we need you to complete a liability waiver form for certified divers (it's mandatory for insurance and boat clearance):",
                    "https://form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol",
                ]
            blocks.append(exo_block)

        # Una línea en blanco entre bloques, sin línea en blanco entre título y sus elementos
        return "\n\n".join("\n".join(block) for block in blocks)

    def _format_service_detail(self, state: ConversationState) -> str:
        """Format service details for the selected service."""
        service = SERVICES.get(state.selected_service)
        if not service:
            return ""

        lang = state.language
        service_id = state.selected_service
        name = service[f"name_{lang}"]
        price = service["price"]
        duration = service[f"duration_{lang}"]
        includes = service[f"includes_{lang}"]
        includes_items = [item.strip() for item in includes.split(",") if item.strip()]
        includes_block = "\n".join(f"- {item}" for item in includes_items)

        extra = ""
        min_age = service.get("min_age")
        if min_age is not None:
            if lang == "es":
                extra += f"\n\n*Edad mínima recomendada*: {min_age} años."
            else:
                extra += f"\n\n*Recommended minimum age*: {min_age} years."

        block_key = "extra_block_" + lang
        extra_block = service.get(block_key)
        if extra_block:
            extra += "\n\n" + extra_block

        accommodation_note = _accommodation_requirement_note(service_id, service, lang)
        if accommodation_note:
            extra += "\n\n" + accommodation_note

        if lang == "es":
            return (
                f"🤿 *{name}*\n\n"
                f"💰 *Precio*: {price}\n"
                f"⏱ *Duracion*: {duration}\n\n"
                f"✅ *Incluye*:\n{includes_block}"
                f"{extra}"
            )
        else:
            return (
                f"🤿 *{name}*\n\n"
                f"💰 *Price*: {price}\n"
                f"⏱ *Duration*: {duration}\n\n"
                f"✅ *Includes*:\n{includes_block}"
                f"{extra}"
            )

    def _format_mixed_final_summary(self, state: ConversationState) -> str:
        """Restaurant-bill style final summary for the cart-style mixed-group flow."""
        lang = state.language
        primary = state.mixed_display_currency  # "USD" or "COP"

        def fmt_usd(x: float | None) -> str:
            if x is None:
                return "consultar"
            try:
                return f"${int(round(float(x))):,}"
            except (TypeError, ValueError):
                return f"${x}"

        def fmt_cop(x: int | float | None) -> str:
            if x is None:
                return "consultar"
            try:
                return f"COP {int(x):,}".replace(",", ".")
            except (TypeError, ValueError):
                return f"COP {x}"

        # Compute subtotals. Cada fila guarda: (label, qty, per-person usd/cop, subtotal usd/cop, booking_url)
        items_rows: list[dict] = []
        booking_links: list[tuple[str, str]] = []
        total_usd = 0.0
        total_cop = 0
        any_consultable = False

        for item in state.mixed_cart:
            qty = item.get("qty", 0)
            item_type = item.get("type")
            # Refresh is free — never add to paid rows or totals.
            if item_type == "refresh":
                continue
            # Split beginner row when kids info requires different activities/pricing.
            # Supports mixed ranges: adult portion + under_8 (snorkel) + 8-10 (Bubble Makers).
            if item_type == "beginner":
                u8 = min(state.kids_under_8_count or 0, qty)
                e10 = min(state.kids_eight_to_ten_count or 0, max(0, qty - u8))
                if u8 > 0 or e10 > 0:
                    adult_qty = max(0, qty - u8 - e10)
                    svc_id_beg = self._cart_service_id("beginner", None, state)
                    svc_beg = SERVICES.get(svc_id_beg) or {}
                    usd_beg = svc_beg.get("price_usd")
                    cop_beg = svc_beg.get("price_cop")
                    beg_name = svc_beg.get(f"name_{lang}") or ("Minicurso de Buceo" if lang == "es" else "Dive Mini Course")
                    beg_url = svc_beg.get("booking_url")
                    if adult_qty > 0:
                        sub_usd_a = (float(usd_beg) * adult_qty) if usd_beg else None
                        sub_cop_a = (int(cop_beg) * adult_qty) if cop_beg else None
                        if sub_usd_a is not None:
                            total_usd += sub_usd_a
                        else:
                            any_consultable = True
                        if sub_cop_a is not None:
                            total_cop += sub_cop_a
                        items_rows.append({
                            "type": "beginner",
                            "label": beg_name,
                            "qty": adult_qty,
                            "usd_per_person": float(usd_beg) if usd_beg else None,
                            "cop_per_person": int(cop_beg) if cop_beg else None,
                            "sub_usd": sub_usd_a,
                            "sub_cop": sub_cop_a,
                        })
                        if beg_url:
                            booking_links.append((beg_name, beg_url))
                    if u8 > 0:
                        snk_id = self._service_for_location("snorkeling", state)
                        snk_svc = SERVICES.get(snk_id) or {}
                        usd_snk = snk_svc.get("price_usd")
                        cop_snk = snk_svc.get("price_cop")
                        snk_base = snk_svc.get(f"name_{lang}") or ("Tour de Snorkeling" if lang == "es" else "Snorkeling Tour")
                        snk_label = snk_base + (" [menores de 8]" if lang == "es" else " [under 8]")
                        sub_usd_k = (float(usd_snk) * u8) if usd_snk else None
                        sub_cop_k = (int(cop_snk) * u8) if cop_snk else None
                        if sub_usd_k is not None:
                            total_usd += sub_usd_k
                        else:
                            any_consultable = True
                        if sub_cop_k is not None:
                            total_cop += sub_cop_k
                        items_rows.append({
                            "type": "snorkel_kids",
                            "label": snk_label,
                            "qty": u8,
                            "usd_per_person": float(usd_snk) if usd_snk else None,
                            "cop_per_person": int(cop_snk) if cop_snk else None,
                            "sub_usd": sub_usd_k,
                            "sub_cop": sub_cop_k,
                        })
                        snk_url = snk_svc.get("booking_url")
                        if snk_url:
                            booking_links.append((snk_label, snk_url))
                    if e10 > 0:
                        bubble_label = beg_name + " [Bubble Makers]"
                        sub_usd_b = (float(usd_beg) * e10) if usd_beg else None
                        sub_cop_b = (int(cop_beg) * e10) if cop_beg else None
                        if sub_usd_b is not None:
                            total_usd += sub_usd_b
                        else:
                            any_consultable = True
                        if sub_cop_b is not None:
                            total_cop += sub_cop_b
                        items_rows.append({
                            "type": "beginner_bubble",
                            "label": bubble_label,
                            "qty": e10,
                            "usd_per_person": float(usd_beg) if usd_beg else None,
                            "cop_per_person": int(cop_beg) if cop_beg else None,
                            "sub_usd": sub_usd_b,
                            "sub_cop": sub_cop_b,
                        })
                        if beg_url:
                            booking_links.append((bubble_label, beg_url))
                    continue
            label = item.get("label") or self._cart_label_for(item_type, item.get("plan"), lang)
            if item_type == "companion":
                usd = COMPANION_PRICE.get("usd_online")
                cop = COMPANION_PRICE.get("cop_online")
                booking_url = None
            else:
                svc_id = self._cart_service_id(item_type, item.get("plan"), state)
                svc = SERVICES.get(svc_id) or {}
                usd = svc.get("price_usd")
                cop = svc.get("price_cop")
                if state.location == "island" and svc.get("booking_url_island"):
                    booking_url = svc.get("booking_url_island")
                else:
                    booking_url = svc.get("booking_url")
                svc_name = svc.get(f"name_{lang}")
                if svc_name and item_type != "refresh":
                    label = svc_name
                if _is_contact_only_service(svc_id) or svc_id in {"referral", "referral_already_on_island"}:
                    booking_url = None
                    any_consultable = True
            sub_usd = (float(usd) * qty) if usd else None
            sub_cop = (int(cop) * qty) if cop else None
            if sub_usd is not None:
                total_usd += sub_usd
            else:
                any_consultable = True
            if sub_cop is not None:
                total_cop += sub_cop
            items_rows.append({
                "type": item_type,
                "label": label,
                "qty": qty,
                "usd_per_person": float(usd) if usd else None,
                "cop_per_person": int(cop) if cop else None,
                "sub_usd": sub_usd,
                "sub_cop": sub_cop,
            })
            if booking_url:
                booking_links.append((label, booking_url))

        # Layout helpers
        def primary_str(usd_val, cop_val):
            return cop_val if primary == "COP" else usd_val

        def secondary_str(usd_val, cop_val):
            return usd_val if primary == "COP" else cop_val

        title = "🧾 *RESERVA DIVING PLANET*" if lang == "es" else "🧾 *DIVING PLANET BOOKING*"
        sep_bold = "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        sep_thin = "─────────────────────────"

        # ACTIVIDADES block — formato: "qty × label" en una línea, debajo "qty × $price p.p. = *$total*"
        section_title = "*ACTIVIDADES*" if lang == "es" else "*ACTIVITIES*"
        rows_text: list[str] = [section_title, ""]
        pp_label = "p.p." if lang == "es" else "p.p."
        _kids_rows_split = (
            (state.kids_under_8_count or 0) > 0
            or (state.kids_eight_to_ten_count or 0) > 0
        )
        kids_sub = None if _kids_rows_split else self._kids_sub_bullet(state, lang)
        for row in items_rows:
            qty = row["qty"]
            label = row["label"]
            if primary == "COP":
                per_person = row["cop_per_person"]
                sub_total = row["sub_cop"]
                fmt_p = fmt_cop
            else:
                per_person = row["usd_per_person"]
                sub_total = row["sub_usd"]
                fmt_p = fmt_usd
            rows_text.append(f"  *{qty} × {label}*")
            if per_person is not None and sub_total is not None:
                rows_text.append(
                    f"    {qty} × {fmt_p(per_person)} {pp_label} = *{fmt_p(sub_total)}*"
                )
            else:
                consult_word = "a consultar" if lang == "es" else "to confirm"
                rows_text.append(f"    _{consult_word}_")
            if row.get("type") == "beginner" and kids_sub:
                rows_text.append(kids_sub)
                kids_sub = None
            rows_text.append("")

        subtotal_label = "*SUBTOTAL*" if lang == "es" else "*SUBTOTAL*"
        if primary == "COP":
            subtotal_str = fmt_cop(int(total_cop)) if total_cop else "consultar"
        else:
            subtotal_str = fmt_usd(total_usd) if total_usd else "consultar"
        rows_text.append(f"{subtotal_label}: *{subtotal_str}*")

        # Includes line (Cartagena origin)
        includes = ""
        has_course_items = self._cart_includes(state, "course")
        has_boat_items = self._cart_has_boat_activities(state)
        if state.location == "cartagena" and has_boat_items:
            includes = ("\n✅ _Incluye: transporte Cartagena-Islas-Cartagena, almuerzo y equipo._"
                        if lang == "es"
                        else "\n✅ _Includes: Cartagena-Islands transport, lunch and gear._")

        # EXTRAS / DESCUENTOS block (only if any apply)
        extras_lines: list[str] = []
        refresh_qty = sum(item["qty"] for item in state.mixed_cart if item.get("type") == "refresh")
        if refresh_qty > 0:
            word = "persona" if refresh_qty == 1 else "personas"
            extras_lines.append(
                f"  🧑‍🏫 Refresher incluido: {refresh_qty} {word} — sin coste adicional"
                if lang == "es"
                else f"  🧑‍🏫 Refresher included: {refresh_qty} person{'s' if refresh_qty > 1 else ''} — no extra cost"
            )
        if state.mixed_final_is_colombian:
            extras_lines.append(
                "  💚 Descuento colombianos/residentes — el asesor confirmará el descuento al reservar"
                if lang == "es"
                else "  💚 Local-resident discount — advisor confirms the discount at booking"
            )
        if state.mixed_final_wants_private:
            extras_lines.append(
                "  🚤 Lancha privada solicitada — el asesor confirmará el precio final al reservar"
                if lang == "es"
                else "  🚤 Private boat requested — advisor confirms the final price at booking"
            )

        # TOTAL
        total_label = "*TOTAL ESTIMADO*" if lang == "es" else "*ESTIMATED TOTAL*"
        if primary == "COP":
            total_primary = fmt_cop(int(total_cop)) if total_cop else "consultar"
            total_secondary = f"≈ {fmt_usd(total_usd)}" if total_usd else ""
        else:
            total_primary = fmt_usd(total_usd) if total_usd else "consultar"
            total_secondary = f"≈ {fmt_cop(int(total_cop))}" if total_cop else ""

        # Avisos (only relevant ones)
        avisos_lines: list[str] = []
        if self._cart_is_large_group(state):
            avisos_lines.append(
                "  • Grupo grande (6+ personas): condiciones especiales — el asesor confirma"
                if lang == "es"
                else "  • Large group (6+ people): special conditions — advisor confirms"
            )
        _u8 = state.kids_under_8_count or 0
        _e10 = state.kids_eight_to_ten_count or 0
        if _u8 > 0:
            cart_has_dive = self._cart_includes(state, "beginner") or self._cart_includes(state, "cert")
            if cart_has_dive:
                avisos_lines.append(
                    "  • ⚠️ Hay menores de 8 — no pueden bucear. Snorkel desde 6 años; el asesor confirmará la planificación."
                    if lang == "es"
                    else "  • ⚠️ Under 8 in the group — cannot dive. Snorkel from age 6; advisor will confirm the plan."
                )
            else:
                avisos_lines.append(
                    "  • ⚠️ Hay menores de 8 — snorkel desde 6 años; confirmar edad exacta con el asesor."
                    if lang == "es"
                    else "  • ⚠️ Under 8 in the group — snorkel from age 6; confirm exact age with advisor."
                )
        if _e10 > 0 or (
            _u8 == 0 and (state.kids_age_group == "eight_to_ten" or state.mixed_final_has_kids_8_10)
        ):
            avisos_lines.append(
                "  • Niños 8-10 (Bubble Makers): supervisor especializado — el asesor confirmará el precio final al reservar"
                if lang == "es"
                else "  • Kids 8-10 (Bubble Makers): specialized supervisor — advisor confirms the final price at booking"
            )
        # kids_age_group == "ten_plus" (u8=0 y e10=0) → sin aviso (todo normal)
        if has_boat_items and has_course_items:
            avisos_lines.append(
                "  • Este carrito mezcla tours y cursos PADI — el asesor confirmará la coordinación final de fechas y logística"
                if lang == "es"
                else "  • This cart mixes tours and PADI courses — the advisor will confirm the final schedule and logistics"
            )
        if any(
            item.get("type") == "course"
            and self._cart_service_id(item.get("type"), item.get("plan"), state) in {"divemaster", "referral", "referral_already_on_island"}
            for item in state.mixed_cart
        ):
            avisos_lines.append(
                "  • Algunos cursos requieren validación manual con el asesor antes de confirmar"
                if lang == "es"
                else "  • Some courses require manual advisor validation before confirmation"
            )
        if any_consultable:
            avisos_lines.append(
                "  • Algunos precios deben confirmarse con el asesor"
                if lang == "es"
                else "  • Some prices need to be confirmed with the advisor"
            )

        # Los links de reserva NO se muestran en el resumen — se envían cuando el
        # cliente pulsa "Reservar" en el siguiente paso. Aquí solo guardamos la lista
        # para usarla más tarde.
        state.mixed_booking_links = booking_links

        # Waiver forms (only show those that apply)
        waiver_lines: list[str] = []
        if self._cart_includes(state, "cert"):
            lbl = "Buzos certificados" if lang == "es" else "Certified divers"
            waiver_lines.append(
                f"  • {lbl}: https://form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol"
            )
        if self._cart_includes(state, "beginner"):
            beg_item = next((it for it in state.mixed_cart if it.get("type") == "beginner"), None)
            total_beg = beg_item["qty"] if beg_item else 0
            _u8w = min(state.kids_under_8_count or 0, total_beg)
            _e10w = min(state.kids_eight_to_ten_count or 0, max(0, total_beg - _u8w))
            _adult_beg = max(0, total_beg - _u8w - _e10w)
            if _adult_beg > 0 or _e10w > 0:
                lbl = "Minicurso" if lang == "es" else "Mini-course"
                if _e10w > 0:
                    lbl = ("Minicurso / Bubble Makers" if lang == "es" else "Mini-course / Bubble Makers")
                waiver_lines.append(
                    f"  • {lbl}: https://form.jotform.com/divingplanetcartagena/exoneracion-curso-en-espanol"
                )
        if waiver_lines:
            waiver_lines.insert(
                0,
                "📝 *Formularios obligatorios antes de salir al mar*:"
                if lang == "es"
                else "📝 *Required forms before going out to sea*:"
            )
        _has_snorkel_activity = self._cart_includes(state, "snorkel") or (
            self._cart_includes(state, "beginner")
            and (state.kids_under_8_count or 0) > 0
        )
        if _has_snorkel_activity:
            waiver_lines.append(
                "_El formulario específico de snorkel lo envía el asesor por correo._"
                if lang == "es"
                else "_The snorkel-specific form is sent by the advisor via email._"
            )

        actions_prompt = (
            "¿Cómo quieres continuar?" if lang == "es" else "How would you like to continue?"
        )

        # Assemble
        parts: list[str] = [title, sep_bold, "\n".join(rows_text)]
        if includes:
            parts.append(includes.strip())
        if extras_lines:
            parts.append(sep_bold)
            parts.append("*EXTRAS / DESCUENTOS*" if lang == "es" else "*EXTRAS / DISCOUNTS*")
            parts.append("\n".join(extras_lines))
        parts.append(sep_bold)
        if total_secondary:
            parts.append(f"*{total_label}*: *{total_primary}* {total_secondary}")
        else:
            parts.append(f"*{total_label}*: *{total_primary}*")
        if avisos_lines:
            parts.append(sep_bold)
            parts.append("🚨 *Avisos*:" if lang == "es" else "🚨 *Notices*:")
            parts.append("\n".join(avisos_lines))
        if waiver_lines:
            parts.append("")
            parts.append("\n".join(waiver_lines))
        parts.append("═══════════════════════════")
        parts.append(actions_prompt)

        result = "\n".join(parts)
        state.mixed_last_summary = result
        return result

    def _goto_location_with_costs(self, state: ConversationState) -> str:
        """Manda al usuario al step LOCATION con un prompt que explica el coste
        de cada opción (Cartagena con transporte vs ya en islas con precio reducido).

        Si state.location ya está seteada (por ejemplo desde tests o conversación
        restaurada), saltamos LOCATION y vamos directo a COLOMBIAN.
        """
        lang = state.language
        if state.location is not None:
            if state.selected_service:
                state.selected_service = self._service_for_location(state.selected_service, state)
            state.step = Step.COLOMBIAN
            self.set_quick_replies(state, "colombian")
            return MESSAGES["colombian"][lang]

        state.step = Step.LOCATION
        self.set_quick_replies(state, "location")

        # Obtenemos la variante base (Cartagena) y la variante isla del servicio actual
        service_id = state.selected_service or ""
        if service_id.endswith("_already_on_island"):
            base_id = service_id[: -len("_already_on_island")]
        else:
            base_id = service_id
        island_id = ISLAND_SERVICE_MAP.get(base_id, base_id)

        base_svc = SERVICES.get(base_id) or {}
        island_svc = SERVICES.get(island_id) or {}
        base_price = base_svc.get("price_usd")
        island_price = island_svc.get("price_usd")

        def _fmt(p):
            try:
                return f"U${int(round(float(p)))}"
            except (TypeError, ValueError):
                return None

        base_p = _fmt(base_price)
        island_p = _fmt(island_price)

        if lang == "es":
            lines = ["📍 *¿Desde dónde harás el tour?*", ""]
            line_cartagena = (
                "🚤 *Desde Cartagena* — Incluye transporte ida y vuelta a las islas y almuerzo"
            )
            if base_p:
                line_cartagena += f" ({base_p})"
            line_island = (
                "🏝️ *Ya estoy en las islas* — Precio reducido, sin transporte desde Cartagena"
            )
            if island_p:
                line_island += f" ({island_p})"
            lines.append(line_cartagena)
            lines.append(line_island)
            return "\n".join(lines)

        lines = ["📍 *Where will you start the tour from?*", ""]
        line_cartagena = (
            "🚤 *From Cartagena* — Includes round-trip transport to the islands and lunch"
        )
        if base_p:
            line_cartagena += f" ({base_p})"
        line_island = (
            "🏝️ *Already on the islands* — Reduced price, no transport from Cartagena"
        )
        if island_p:
            line_island += f" ({island_p})"
        lines.append(line_cartagena)
        lines.append(line_island)
        return "\n".join(lines)

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

        # Choose booking URL based on location
        if state.location == "island" and service.get("booking_url_island"):
            booking_url = service["booking_url_island"]
        else:
            booking_url = service["booking_url"]

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

            # Refresher, descuento y regla de vuelo, cada uno separado por una línea en blanco
            if flight_rule or state.refresher_interested or state.is_colombian:
                lines.append("")

            if state.refresher_interested:
                lines.append(
                    "🧑‍🏫 Refresher: Sí (recomendado por inactividad) — sin coste adicional, "
                    "el guía adapta la inmersión a tu nivel"
                )

            if state.is_colombian:
                lines.append(
                    "🌎 *Descuento colombiano*: Contactanos por WhatsApp "
                    "al +57 320 231515 para tu descuento especial."
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

            # El link de reserva se envía cuando el cliente pulsa "Reservar"
            # (no se incluye aquí para no mostrarlo antes de tiempo).
            if contact_only:
                lines.append("🔗 Más información del programa:")
                lines.append(service["web_url"])
                lines.append("")
                lines.append(_divemaster_itinerary_offer_prompt(lang))
            else:
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

            if state.is_colombian:
                summary += (
                    "\n🌎 *Colombian discount*: Contact us via WhatsApp "
                    "at +57 320 231515 for your special discount.\n"
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

            # Booking link sent on "Reservar" click, not in summary
            if contact_only:
                summary += f"\n🔗 *Program info*:\n{service['web_url']}\n"
                summary += "\n" + _divemaster_itinerary_offer_prompt(lang)
            else:
                summary += "\n\n" + (final_prompt or "What would you like to do?")

        return summary

    @staticmethod
    def _parse_choice(message: str, max_options: int) -> int | None:
        """Parse a numeric choice from user message."""
        cleaned = message.strip().rstrip(".")
        try:
            choice = int(cleaned)
            if 1 <= choice <= max_options:
                return choice
        except ValueError:
            pass

        cleaned_lower = cleaned.lower()
        for replies_by_lang in BUTTON_OPTIONS.values():
            for replies in replies_by_lang.values():
                for reply in replies:
                    value = reply.get("value")
                    title = reply.get("title", "").strip().lower()
                    if title == cleaned_lower and value and value.isdigit():
                        choice = int(value)
                        if 1 <= choice <= max_options:
                            return choice
        return None
