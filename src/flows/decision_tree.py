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
    TOURS_LOCATION = "tours_location"
    GROUP_TYPE = "group_type"
    TOURS_EXPERIENCE = "tours_experience"
    TOURS_CERTIFIED = "tours_certified"
    CERTIFIED_4_DIVES_VARIANT = "certified_4_dives_variant"
    CERTIFIED_LAST_DIVE = "certified_last_dive"
    CERTIFIED_EXPERIENCE = "certified_experience"
    REFRESHER_INTEREST = "refresher_interest"
    TOURS_BEGINNER = "tours_beginner"
    BEGINNER_AGE = "beginner_age"
    COURSES_MENU = "courses_menu"
    COURSES_OPEN_WATER_ORIGIN = "courses_open_water_origin"
    COURSES_OPEN_WATER_TIME = "courses_open_water_time"
    COURSES_ADVANCED_MENU = "courses_advanced_menu"
    COURSES_SPECIALTIES_MENU = "courses_specialties_menu"
    # Cart-style mixed-group flow
    MIXED_ENTRY = "mixed_entry"
    MIXED_LOCATION = "mixed_location"
    MIXED_ADD_ACTIVITY = "mixed_add_activity"
    MIXED_ADD_CERT_PLAN = "mixed_add_cert_plan"
    MIXED_ADD_QTY = "mixed_add_qty"
    MIXED_CERT_LAST_DIVE = "mixed_cert_last_dive"
    MIXED_CERT_REFRESH_INTEREST = "mixed_cert_refresh_interest"
    MIXED_CERT_REFRESH_QTY = "mixed_cert_refresh_qty"
    MIXED_CERT_SPLIT_REVIEW = "mixed_cert_split_review"
    MIXED_ADD_PREVIEW = "mixed_add_preview"
    MIXED_CART_REVIEW = "mixed_cart_review"
    MIXED_CART_MODIFY_PICK = "mixed_cart_modify_pick"
    MIXED_CART_REMOVE_PICK = "mixed_cart_remove_pick"
    MIXED_FINAL_COLOMBIAN = "mixed_final_colombian"
    MIXED_FINAL_KIDS = "mixed_final_kids"
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
    mixed_pending_modify_idx: int | None = None  # cart index when editing an item
    mixed_pending_exact: bool = False            # waiting for exact count after "6+"
    mixed_display_currency: str = "USD"          # "USD" | "COP"
    mixed_final_is_colombian: bool | None = None
    mixed_final_has_kids_8_10: bool | None = None
    mixed_final_wants_private: bool | None = None
    mixed_last_summary: str | None = None        # final summary text (for lead note)
    # Ruta de entrada al flujo carrito: "booking" (entrada principal),
    # "diving_snorkel" (grupo mixto legacy) o "cert_beg" (certificados + principiantes).
    # Si es "cert_beg" no ofrecemos snorkel.
    mixed_entry_path: str | None = None
    # Lista de (label, booking_url) para enviar al cliente cuando pulse "Reservar"
    # en el resumen final del flujo mixto.
    mixed_booking_links: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self):
        if self.history is None:
            self.history = []


def _detect_language_from_text(message: str) -> str | None:
    normalized = " ".join(message.strip().lower().split())
    words = {word.strip(".,!?¡¿:;()[]{}\"'") for word in normalized.split()}

    if normalized in {"en", "english"} or words.intersection({"english", "hello", "hi"}):
        return "en"
    if normalized in {"es", "espanol", "español", "spanish"} or words.intersection({"espanol", "español", "spanish", "hola"}):
        return "es"
    return None


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
    service = SERVICES.get(state.selected_service)

    booking_url: str | None = None
    if service:
        if state.location == "island" and service.get("booking_url_island"):
            booking_url = service["booking_url_island"]
        else:
            booking_url = service.get("booking_url")

        # Para clientes colombianos seguimos sin mostrar el link real de pago
        if state.is_colombian:
            booking_url = None

    if lang == "es":
        base = (
            "Genial que ya hayas empezado tu curso. Para completar un referral/reactivate en Diving Planet "
            "necesitamos revisar tu eLearning y formularios PADI, y ver cuantas inmersiones te faltan.\n\n"
            "Te paso con un asesor para que te indique exactamente que documentos traer y como funciona el precio en tu caso.\n\n"
            + MESSAGES["escalate"][lang]
        )
        if booking_url:
            base += (
                "\n\nCuando mi jefe te confirme los detalles, podras completar el pago aqui:\n"
                f"{booking_url}"
            )
        return base

    base = (
        "Great that you already started your course. To finish a referral/reactivate with Diving Planet we "
        "need to review your eLearning and PADI forms, and see how many dives you still need.\n\n"
        "I will transfer you to an advisor so they can tell you exactly which documents to bring and how pricing works in your case.\n\n"
        + MESSAGES["escalate"][lang]
    )
    if booking_url:
        base += (
            "\n\nOnce our manager confirms the details with you, you can complete the payment here:\n"
            f"{booking_url}"
        )
    return base


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
            "Que te gustaria hacer?"
        ),
        "en": (
            "What would you like to do?"
        ),
    },
    "reserva_menu": {
        "es": (
            "¡Perfecto! ¿Qué te gustaría reservar?"
        ),
        "en": (
            "Great! What would you like to book?"
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
            "Genial, cuentame que tipo de plan buscas:\n"
            "Elige la opcion que mejor se ajuste."
        ),
        "en": (
            "Great! Tell me what kind of plan you're looking for:\n"
            "Choose the option that fits best."
        ),
    },
    "info_packages_menu": {
        "es": (
            "Perfecto. Dentro de buceo, ¿como esta compuesto tu grupo?"
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
    "tours_location": {
        "es": (
            "¿Desde dónde harás el tour?"
        ),
        "en": (
            "Where will you depart from?"
        ),
    },
    "tours_experience": {
        "es": (
            "Perfecto. Dentro de buceo, ¿como esta compuesto tu grupo?"
        ),
        "en": (
            "Perfect. Within diving, how is your group made up?"
        ),
    },
    "tours_certified": {
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
    "certified_4_dives_variant": {
        "es": (
            "Perfecto. Para *4 inmersiones (2 días)* desde las islas, ¿qué opción prefieres?"
        ),
        "en": (
            "Perfect. For *4 dives (2 days)* from the islands, which option would you prefer?"
        ),
    },
    "certified_last_dive": {
        "es": (
            "¿Han pasado *más de 2 años* desde tu última inmersión?\n\n"
            "Si es así, te recomendamos hacer un *refresher* antes de la salida."
        ),
        "en": (
            "Has it been *more than 2 years* since your last dive?\n\n"
            "If so, we recommend doing a *refresher* before the trip."
        ),
    },
    "certified_experience": {
        "es": (
            "¿Tienes *más de 500 inmersiones* o eres *Dive Master* (o nivel similar)?\n\n"
            "Esto nos ayuda a recomendarte la mejor opción de forma segura."
        ),
        "en": (
            "Do you have *500+ logged dives* or are you a *Dive Master* (or similar level)?\n\n"
            "This helps us recommend the best option safely."
        ),
    },
    "refresher_info": {
        "es": (
            "Te recomendamos hacer un *refresher* antes de salir al mar — un repaso rápido para volver al agua con confianza:\n\n"
            "✅ Repaso de teoría (señales, equipo y procedimientos)\n"
            "🏊 Práctica en piscina\n"
            "🤿 1 buceo en el mar con instructor\n\n"
            "⚠️ No es el minicurso de principiantes — está pensado para *buzos ya certificados* que quieren actualizarse.\n\n"
            "¿Te interesa incluirlo?"
        ),
        "en": (
            "We recommend doing a *refresher* before going out to sea — a quick review to get back in the water with confidence:\n\n"
            "✅ Theory review (signals, equipment and procedures)\n"
            "🏊 Pool / confined water practice\n"
            "🤿 1 open water dive with an instructor\n\n"
            "⚠️ This is not the beginner course — it's designed for *already-certified divers* who want to brush up.\n\n"
            "Would you like to include it?"
        ),
    },
    "tours_beginner": {
        "es": (
            "Perfecto! No necesitas experiencia previa.\n\n"
            "- *Minicurso de Buceo*: si quieres *probar buceo* por primera vez (vas debajo del agua con tanque e instructor, 1 inmersión guiada)."
        ),
        "en": (
            "Perfect! No previous experience is needed.\n\n"
            "- *Dive Mini Course*: if you want to *try diving* for the first time (you go underwater with tank and instructor, 1 guided dive)."
        ),
    },
    "beginner_age": {
        "es": (
            "El *Minicurso de Buceo* es ideal para vivir la experiencia de bucear por primera vez 🤿\n\n"
            "Selecciona la opción que mejor describa al grupo:"
        ),
        "en": (
            "The *Dive Mini Course* is perfect for first-time divers 🤿\n\n"
            "Pick the option that best describes the group:"
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
    "group_type": {
        "es": (
            "Genial, cuentame que tipo de plan buscas:\n"
            "Elige la opcion que mejor se ajuste."
        ),
        "en": (
            "Great! Tell me what kind of plan you're looking for:\n"
            "Choose the option that fits best."
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
    "mixed_add_activity": {
        "es": "¿Qué actividad quieres *añadir* al carrito?",
        "en": "Which activity would you like to *add* to the cart?",
    },
    "mixed_add_cert_plan": {
        "es": (
            "Para *buceo certificado*, ¿qué plan?\n\n"
            "🤿 *2 inmersiones / 1 día*: salida de día completo a las Islas del Rosario "
            "con 2 inmersiones guiadas.\n"
            "📅 *Paquete multi-día (5/7/9 inmersiones)*: varios días seguidos para profundizar "
            "tu experiencia. Requiere coordinación con el asesor."
        ),
        "en": (
            "For *certified diving*, which plan?\n\n"
            "🤿 *2 dives / 1 day*: full-day trip to the Rosario Islands with 2 guided dives.\n"
            "📅 *Multi-day package (5/7/9 dives)*: several consecutive days to deepen your "
            "experience. Requires coordination with the advisor."
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
    "mixed_final_colombian": {
        "es": "Para terminar, ¿eres *colombiano/a o residente en Colombia*? (aplica descuento)",
        "en": "Last few questions: are you *Colombian / resident in Colombia*? (discount applies)",
    },
    "mixed_final_kids": {
        "es": (
            "¿Hay *niños entre 8 y 10 años* en el grupo?\n\n"
            "• Menores de 8 años: solo pueden hacer snorkel (mín. 6 años).\n"
            "• De 8 a 10 años: programa *Bubble Makers* (piscina y aguas poco profundas, máximo 2 metros de profundidad).\n"
            "• A partir de 10 años: pueden hacer el minicurso normal."
        ),
        "en": (
            "Are there any *children aged 8 to 10* in the group?\n\n"
            "• Under 8: snorkeling only (min. 6 years).\n"
            "• Ages 8-10: *Bubble Makers* program (pool + max 2 m depth).\n"
            "• 10 and over: regular mini-course."
        ),
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
    "info_general": {
        "es": (
            "Aqui tienes informacion general sobre Diving Planet:\n\n"
            "📍 *Ubicacion*: Plaza de San Diego, Cl. 39 #8-24 Piso 2, "
            "Ciudad Amurallada, Cartagena\n"
            "🤿 *Zona de buceo*: Islas del Rosario (Parque Nacional Natural)\n"
            "⏰ *Hora de salida*: 8:00 AM desde el Muelle de la Bodeguita\n"
            "🏆 *Certificacion*: PADI 5 Estrellas (primero de Colombia)\n"
            "🌱 *Programa social*: DIVE TO HEAL (buceo adaptado + restauracion coralina)\n\n"
            "Quieres saber algo mas?"
        ),
        "en": (
            "Here's general information about Diving Planet:\n\n"
            "📍 *Location*: Plaza de San Diego, Cl. 39 #8-24 Floor 2, "
            "Walled City, Cartagena\n"
            "🤿 *Dive zone*: Rosario Islands (National Natural Park)\n"
            "⏰ *Departure*: 8:00 AM from Muelle de la Bodeguita\n"
            "🏆 *Certification*: PADI 5 Star (first in Colombia)\n"
            "🌱 *Social program*: DIVE TO HEAL (adaptive diving + coral restoration)\n\n"
            "Want to know more?"
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
            {"title": "🤿 Tours de buceo / snorkel", "value": "1"},
            {"title": "📘 Cursos PADI y certificaciones", "value": "2"},
            {"title": "🔙 Volver al menú principal", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Diving / snorkel tours", "value": "1"},
            {"title": "📘 PADI courses and certifications", "value": "2"},
            {"title": "🔙 Back to main menu", "value": "back"},
        ],
    },
    "info_menu": {
        "es": [
            {"title": "🧭 Actividades y cursos", "value": "1"},
            {"title": "💰 Precios y descuentos", "value": "2"},
            {"title": "💳 Reservas y pago", "value": "3"},
            {"title": "📍 Logística", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🧭 Activities and courses", "value": "1"},
            {"title": "💰 Prices and discounts", "value": "2"},
            {"title": "💳 Bookings and payment", "value": "3"},
            {"title": "📍 Logistics", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
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
            {"title": "👥 Grupo mixto (buceo + snorkel)", "value": "3"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Diving", "value": "1"},
            {"title": "🐠 Snorkeling", "value": "2"},
            {"title": "👥 Mixed group (diving + snorkel)", "value": "3"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_packages_menu": {
        "es": [
            {"title": "🤿 Solo buzos certificados", "value": "1"},
            {"title": "🆕 Solo principiantes", "value": "2"},
            {"title": "👥 Grupo mixto (certificados + principiantes)", "value": "3"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Only certified divers", "value": "1"},
            {"title": "🆕 Only beginners", "value": "2"},
            {"title": "👥 Mixed group (certified + beginners)", "value": "3"},
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
    "mixed_add_activity": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "🐠 Snorkel", "value": "3"},
            {"title": "🤿 Curso PADI", "value": "4"},
            {"title": "👤 Acompañante (sin actividad)", "value": "5"},
            {"title": "🔙 Cancelar", "value": "back"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "🐠 Snorkeling", "value": "3"},
            {"title": "🤿 PADI course", "value": "4"},
            {"title": "👤 Companion (no activity)", "value": "5"},
            {"title": "🔙 Cancel", "value": "back"},
        ],
    },
    "mixed_add_cert_plan": {
        "es": [
            {"title": "🤿 2 Inmersiones / 1 día", "value": "1"},
            {"title": "📅 Paquete multi-día (5/7/9 inmersiones)", "value": "2"},
            {"title": "🔙 Cancelar", "value": "back"},
        ],
        "en": [
            {"title": "🤿 2 Dives / 1 day", "value": "1"},
            {"title": "📅 Multi-day package (5/7/9 dives)", "value": "2"},
            {"title": "🔙 Cancel", "value": "back"},
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
            {"title": "🔙 Cancelar", "value": "back"},
        ],
        "en": [
            {"title": "1", "value": "1"},
            {"title": "2", "value": "2"},
            {"title": "3", "value": "3"},
            {"title": "4", "value": "4"},
            {"title": "5", "value": "5"},
            {"title": "6 or more", "value": "6+"},
            {"title": "🔙 Cancel", "value": "back"},
        ],
    },
    "mixed_preview_actions": {
        "es": [
            {"title": "🛒 Añadir al carrito", "value": "1"},
            {"title": "🗺️ Ver itinerario completo", "value": "itinerary"},
            {"title": "🔙 Cancelar", "value": "back"},
        ],
        "en": [
            {"title": "🛒 Add to cart", "value": "1"},
            {"title": "🗺️ View full itinerary", "value": "itinerary"},
            {"title": "🔙 Cancel", "value": "back"},
        ],
    },
    "mixed_cert_split_review": {
        "es": [
            {"title": "🎓 Continuar con el buceo", "value": "1"},
            {"title": "❌ Quitar Minicurso / Refresher", "value": "2"},
            {"title": "🔄 Empezar de nuevo", "value": "3"},
        ],
        "en": [
            {"title": "🎓 Continue with diving", "value": "1"},
            {"title": "❌ Remove Mini-course / Refresher", "value": "2"},
            {"title": "🔄 Start over", "value": "3"},
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
            {"title": "➕ Añadir otra actividad", "value": "1"},
            {"title": "🔧 Modificar item", "value": "2"},
            {"title": "❌ Quitar item", "value": "3"},
            {"title": "✅ Confirmar carrito", "value": "4"},
            {"title": "🔄 Empezar de nuevo", "value": "5"},
        ],
        "en": [
            {"title": "➕ Add another activity", "value": "1"},
            {"title": "🔧 Modify item", "value": "2"},
            {"title": "❌ Remove item", "value": "3"},
            {"title": "✅ Confirm cart", "value": "4"},
            {"title": "🔄 Start over", "value": "5"},
        ],
    },
    "mixed_final_summary_actions": {
        "es": [
            {"title": "🧑‍💼 Reservar / contactar asesor", "value": "1"},
            {"title": "🔄 Empezar de nuevo", "value": "2"},
        ],
        "en": [
            {"title": "🧑‍💼 Book / contact advisor", "value": "1"},
            {"title": "🔄 Start over", "value": "2"},
        ],
    },
    "tours_certified": {
        "es": [
            {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
            {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
            {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
            {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
            {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
            {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
            {"title": "🧑‍💬 Servicio Privado", "value": "7"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 2 Dives (1 day)", "value": "1"},
            {"title": "🤿 3 Dives (1 day)*", "value": "2"},
            {"title": "🤿 4 Dives (2 days)", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🧑‍💬 Private Service", "value": "7"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "certified_4_dives_variant": {
        "es": [
            {"title": "🤿 4 inmersiones (2 días) · 4 diurnas", "value": "1"},
            {"title": "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 4 Dives (2 days) · 4 daytime dives", "value": "1"},
            {"title": "🤿 4 Dives (2 days) · 3 daytime + 1 night dive", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "certified_last_dive": {
        "es": [
            {"title": "Sí", "value": "1"},
            {"title": "No", "value": "2"},
        ],
        "en": [
            {"title": "Yes", "value": "1"},
            {"title": "No", "value": "2"},
        ],
    },
    "certified_experience": {
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
            {"title": "Sí", "value": "1"},
            {"title": "No", "value": "2"},
        ],
        "en": [
            {"title": "Yes", "value": "1"},
            {"title": "No", "value": "2"},
        ],
    },
    "tours_beginner": {
        "es": [
            {"title": "🤿 Minicurso de Buceo", "value": "1"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Dive Mini Course", "value": "1"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "beginner_age": {
        "es": [
            {"title": "👶 Hay menores de 8 años", "value": "1"},
            {"title": "👦 Hay niños de 8 a 10 (Bubble Makers)", "value": "2"},
            {"title": "🧑 Todos tienen 10+ años", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "👶 Under 8 years old", "value": "1"},
            {"title": "👦 Kids 8-10 (Bubble Makers)", "value": "2"},
            {"title": "🧑 Everyone 10+ years old", "value": "3"},
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
            {"title": "🔙 Volver al menú", "value": "back"},
        ],
        "en": [
            {"title": "❓ Yes, I have more questions", "value": "ask"},
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
            {"title": "🗺️ Ver itinerario completo + link de reserva", "value": "itinerary"},
            {"title": "🔙 Volver al menú", "value": "back"},
        ],
        "en": [
            {"title": "🗺️ View full itinerary + booking link", "value": "itinerary"},
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
    "info_general": {
        "es": [
            {"title": "🤿 Ver tours y actividades", "value": "1"},
            {"title": "📘 Ver cursos PADI", "value": "2"},
            {"title": "🧑‍💬 Hablar con un asesor", "value": "4"},
        ],
        "en": [
            {"title": "🤿 View tours and activities", "value": "1"},
            {"title": "📘 View PADI courses", "value": "2"},
            {"title": "🧑‍💬 Speak with an advisor", "value": "4"},
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
            Step.CERTIFIED_LAST_DIVE,
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
            Step.TOURS_LOCATION: self._handle_tours_location,
            Step.GROUP_TYPE: self._handle_group_type,
            Step.TOURS_EXPERIENCE: self._handle_tours_experience,
            Step.TOURS_CERTIFIED: self._handle_tours_certified,
            Step.CERTIFIED_4_DIVES_VARIANT: self._handle_certified_4_dives_variant,
            Step.CERTIFIED_LAST_DIVE: self._handle_certified_last_dive,
            Step.CERTIFIED_EXPERIENCE: self._handle_certified_experience,
            Step.REFRESHER_INTEREST: self._handle_refresher_interest,
            Step.TOURS_BEGINNER: self._handle_tours_beginner,
            Step.BEGINNER_AGE: self._handle_beginner_age,
            Step.COURSES_MENU: self._handle_courses_menu,
            Step.COURSES_OPEN_WATER_ORIGIN: self._handle_courses_open_water_origin,
            Step.COURSES_OPEN_WATER_TIME: self._handle_courses_open_water_time,
            Step.COURSES_ADVANCED_MENU: self._handle_courses_advanced_menu,
            Step.COURSES_SPECIALTIES_MENU: self._handle_courses_specialties_menu,
            Step.PRICING_COLOMBIAN: self._handle_pricing_colombian,
            Step.MIXED_ENTRY: self._handle_mixed_entry,
            Step.MIXED_LOCATION: self._handle_mixed_location,
            Step.MIXED_ADD_ACTIVITY: self._handle_mixed_add_activity,
            Step.MIXED_ADD_CERT_PLAN: self._handle_mixed_add_cert_plan,
            Step.MIXED_ADD_QTY: self._handle_mixed_add_qty,
            Step.MIXED_CERT_LAST_DIVE: self._handle_mixed_cert_last_dive,
            Step.MIXED_CERT_REFRESH_INTEREST: self._handle_mixed_cert_refresh_interest,
            Step.MIXED_CERT_REFRESH_QTY: self._handle_mixed_cert_refresh_qty,
            Step.MIXED_CERT_SPLIT_REVIEW: self._handle_mixed_cert_split_review,
            Step.MIXED_ADD_PREVIEW: self._handle_mixed_add_preview,
            Step.MIXED_CART_REVIEW: self._handle_mixed_cart_review,
            Step.MIXED_CART_MODIFY_PICK: self._handle_mixed_cart_modify_pick,
            Step.MIXED_CART_REMOVE_PICK: self._handle_mixed_cart_remove_pick,
            Step.MIXED_FINAL_COLOMBIAN: self._handle_mixed_final_colombian,
            Step.MIXED_FINAL_KIDS: self._handle_mixed_final_kids,
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
        return self._enter_booking_cart(state)

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
        choice = self._parse_choice(message, 3)
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
        if choice == 3:
            state.step = Step.INFO_MIXED_ACTIVITY_MENU
            self.set_quick_replies(state, "info_mixed_activity_menu")
            return MESSAGES["info_mixed_activity_menu"][lang]

        self.set_quick_replies(state, "info_tours_menu")
        return MESSAGES["not_understood"][lang]

    def _handle_info_packages_menu(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 3)
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
        if choice == 3:
            state.step = Step.INFO_MIXED_CERT_BEG_MENU
            self.set_quick_replies(state, "info_mixed_cert_beg_menu")
            return MESSAGES["info_mixed_cert_beg_menu"][lang]

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

        booking_url = service.get("booking_url")
        web_url = service.get("web_url")
        url = booking_url or web_url or "https://divingplanet.org/contacto/"

        state.step = Step.MAIN_MENU
        self.set_quick_replies(state, "main_menu")
        if lang == "es":
            return (
                "🔗 Aquí tienes el link para reservar (verás el precio actualizado según fecha y disponibilidad):\n"
                + url
                + "\n\n"
                + MESSAGES["main_menu"][lang]
            )
        return (
            "🔗 Here is the booking link (you will see the up-to-date price depending on date and availability):\n"
            + url
            + "\n\n"
            + MESSAGES["main_menu"][lang]
        )

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

    def _handle_tours_location(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.location = "cartagena"
        elif choice == 2:
            state.location = "island"
        else:
            self.set_quick_replies(state, "tours_location")
            return MESSAGES["not_understood"][lang]

        state.step = Step.GROUP_TYPE
        self.set_quick_replies(state, "group_type")
        return MESSAGES["group_type"][lang]

    def _handle_group_type(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language

        if choice == 1:
            state.step = Step.TOURS_EXPERIENCE
            self.set_quick_replies(state, "tours_experience")
            return MESSAGES["tours_experience"][lang]
        if choice == 2:
            self._set_back_target(state, Step.GROUP_TYPE, "group_type")
            state.selected_service = self._service_for_location("snorkeling", state)
            intro = (
                "El *Tour de Snorkeling* es ideal para explorar las Islas del Rosario "
                "en la superficie 🐠\n\n"
                "*Edad mínima: 6 años.*\n\n"
                if lang == "es"
                else "The *Snorkeling Tour* is perfect for exploring the Rosario Islands "
                "from the surface 🐠\n\n"
                "*Minimum age: 6 years.*\n\n"
            )
            return intro + self._goto_location_with_costs(state)
        if choice == 3:
            # Enter cart-style mixed flow
            self._reset_mixed_state(state)
            state.mixed_entry_path = "diving_snorkel"
            self._set_back_target(state, Step.GROUP_TYPE, "group_type")
            state.step = Step.MIXED_ENTRY
            self.set_quick_replies(state, "mixed_entry")
            intro_es = (
                "¡Perfecto! Para grupos mixtos *buceo + snorkel* combinamos actividades en un mismo tour: "
                "todos viajan juntos a las islas y comparten almuerzo.\n\n"
            )
            intro_en = (
                "Great! For *diving + snorkeling* mixed groups we combine activities in a single tour: "
                "everyone travels together to the islands and shares lunch.\n\n"
            )
            return (intro_es if lang == "es" else intro_en) + MESSAGES["mixed_entry"][lang]

        self.set_quick_replies(state, "group_type")
        return MESSAGES["not_understood"][lang]

    def _handle_tours_experience(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language

        if choice == 1:
            state.is_certified = True
            state.step = Step.TOURS_CERTIFIED
            self.set_quick_replies(state, "tours_certified")
            return MESSAGES["tours_certified"][lang]
        if choice == 2:
            state.is_certified = False
            self._set_back_target(state, Step.TOURS_EXPERIENCE, "tours_experience")
            state.selected_service = self._service_for_location("minicourse", state)
            state.step = Step.BEGINNER_AGE
            self.set_quick_replies(state, "beginner_age")
            return MESSAGES["beginner_age"][lang]
        if choice == 3:
            # Enter cart-style mixed flow (cert + ppt → NO snorkel)
            self._reset_mixed_state(state)
            state.mixed_entry_path = "cert_beg"
            self._set_back_target(state, Step.TOURS_EXPERIENCE, "tours_experience")
            state.step = Step.MIXED_ENTRY
            self.set_quick_replies(state, "mixed_entry")
            intro_es = (
                "¡Perfecto! Para grupos mixtos *certificados + principiantes* combinamos actividades en un mismo tour: "
                "todos viajan juntos a las islas y comparten almuerzo.\n\n"
            )
            intro_en = (
                "Great! For *certified + beginners* mixed groups we combine activities in a single tour: "
                "everyone travels together to the islands and shares lunch.\n\n"
            )
            return (intro_es if lang == "es" else intro_en) + MESSAGES["mixed_entry_cert_beg"][lang]

        self.set_quick_replies(state, "tours_experience")
        return MESSAGES["not_understood"][lang]

    # ───────────────────── Cart-style mixed group flow ─────────────────────

    @staticmethod
    def _is_in_mixed_flow(state: ConversationState) -> bool:
        return bool(state.mixed_cart) or state.step in {
            Step.MIXED_ENTRY,
            Step.MIXED_LOCATION,
            Step.MIXED_ADD_ACTIVITY,
            Step.MIXED_ADD_CERT_PLAN,
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
        state.mixed_pending_modify_idx = None
        state.mixed_pending_exact = False
        state.mixed_display_currency = "USD"
        state.mixed_final_is_colombian = None
        state.mixed_final_has_kids_8_10 = None
        state.mixed_final_wants_private = None
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
            if lang == "es":
                return "Buceo certificado (2 inmersiones)" if plan == "2_dives_1_day" else "Buceo certificado"
            return "Certified diving (2 dives)" if plan == "2_dives_1_day" else "Certified diving"
        if item_type == "beginner":
            return "Buceo principiantes (Minicurso)" if lang == "es" else "Beginner diving (Mini-course)"
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
        if item_type == "cert" and plan == "2_dives_1_day":
            return self._service_for_location("2_dives_1_day", state)
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
        msg = " ".join(message.strip().lower().split())
        if msg in {"6+", "6 o mas", "6 o más", "6 or more", "more"}:
            return 6
        try:
            n = int(msg)
            if 1 <= n <= 99:
                return n
        except ValueError:
            return None
        return None

    def _mixed_preview_state(self, state: ConversationState, service_id: str) -> ConversationState:
        preview_state = ConversationState(conversation_id=state.conversation_id)
        preview_state.language = state.language
        preview_state.location = state.location
        preview_state.selected_service = service_id
        preview_state.is_colombian = False
        preview_state.is_certified = service_id.startswith("2_dives") or service_id.startswith("3_dives")
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
        remaining_qty = state.mixed_pending_cert_remaining_qty or 0
        cart_lines = self._format_cart_lines(state, lang)
        if lang == "es":
            person_phrase = "1 persona" if remaining_qty == 1 else f"{remaining_qty} personas"
            pending_line = (
                f"Aún queda {person_phrase} pendiente de continuar con la reserva de *Buceo certificado (2 inmersiones)*."
            )
            prompt = "¿Cómo quieres continuar?"
        else:
            person_phrase = "1 person" if remaining_qty == 1 else f"{remaining_qty} people"
            pending_line = (
                f"There is still {person_phrase} pending to continue with the *Certified diving (2 dives)* booking."
            )
            prompt = "How would you like to continue?"
        return f"{cart_lines}\n\n{pending_line}\n\n{prompt}"

    # ─── Step handlers ───

    def _handle_mixed_entry(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
            target_step = state.back_step_override or Step.MAIN_MENU
            quick_replies_key = state.back_quick_replies_key or "main_menu"
            state.step = target_step
            self.set_quick_replies(state, quick_replies_key)
            return MESSAGES[quick_replies_key][lang]
        choice = self._parse_choice(message, 1)
        if choice == 1 or msg in ("start", "empezar", "ok", "vale", "si", "sí", "yes"):
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
        if msg in ("back", "cancel", "cancelar"):
            return self._goto_mixed_entry(state)
        if choice == 1:
            state.location = "cartagena"
            return self._goto_mixed_add_activity(state)
        if choice == 2:
            state.location = "island"
            return self._goto_mixed_add_activity(state)
        self.set_quick_replies(state, "tours_location")
        return MESSAGES["not_understood"][lang]

    def _goto_mixed_add_activity(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_ADD_ACTIVITY
        self.set_quick_replies(state, "mixed_add_activity")
        return MESSAGES["mixed_add_activity"][lang]

    def _handle_mixed_add_activity(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
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

    def _handle_mixed_add_cert_plan(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
            return self._goto_mixed_add_activity(state)
        choice = self._parse_choice(message, 2)
        if choice == 1:
            state.mixed_pending_qty_plan = "2_dives_1_day"
            return self._goto_mixed_add_qty(state)
        if choice == 2:
            # Multi-day mixed packages → still requires advisor (price/logistics unknown)
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = (
                "grupo mixto con paquete multi-dia (5/7/9 buceos) - requiere cotizacion personalizada"
            )
            self._reset_mixed_state(state)
            if lang == "es":
                return (
                    "Los paquetes multi-dia (5/7/9 buceos) en grupos mixtos requieren cotizar fechas, "
                    "alojamiento en las islas y compatibilidad entre subgrupos. Te paso con un asesor para "
                    "armar la propuesta completa.\n\n"
                    + MESSAGES["escalate"][lang]
                )
            return (
                "Multi-day packages (5/7/9 dives) in mixed groups require quoting dates, island accommodation, "
                "and compatibility between subgroups. Let me connect you with an advisor to build the "
                "complete proposal.\n\n"
                + MESSAGES["escalate"][lang]
            )
        self.set_quick_replies(state, "mixed_add_cert_plan")
        return MESSAGES["not_understood"][lang]

    def _goto_mixed_add_qty(self, state: ConversationState) -> str:
        lang = state.language
        state.step = Step.MIXED_ADD_QTY
        state.mixed_pending_exact = False
        self.set_quick_replies(state, "mixed_quantity")
        return MESSAGES["mixed_add_qty"][lang]

    def _handle_mixed_add_qty(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
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
            state.mixed_cart[state.mixed_pending_modify_idx]["qty"] = n
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
            self.set_quick_replies(state, "certified_last_dive")
            return MESSAGES["certified_last_dive"][lang]

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
            return self._prepare_mixed_add_preview(state, self._service_for_location("minicourse", state))
        if item_type == "snorkel":
            return self._prepare_mixed_add_preview(state, self._service_for_location("snorkeling", state))

        self._clear_mixed_pending_add(state)
        return self._goto_mixed_cart_review(state)

    def _handle_mixed_cert_last_dive(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
            state.step = Step.MIXED_ADD_QTY
            self.set_quick_replies(state, "mixed_quantity")
            return MESSAGES["mixed_add_qty"][lang]
        if choice == 1:
            state.step = Step.MIXED_CERT_REFRESH_INTEREST
            self.set_quick_replies(state, "refresher_interest")
            return MESSAGES["refresher_info"][lang]
        if choice == 2:
            return self._prepare_mixed_add_preview(state, self._service_for_location("2_dives_1_day", state))
        self.set_quick_replies(state, "certified_last_dive")
        return MESSAGES["not_understood"][lang]

    def _handle_mixed_cert_refresh_interest(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
            state.step = Step.MIXED_CERT_LAST_DIVE
            self.set_quick_replies(state, "certified_last_dive")
            return MESSAGES["certified_last_dive"][lang]
        if choice == 1:
            state.step = Step.MIXED_CERT_REFRESH_QTY
            self.set_quick_replies(state, "mixed_quantity")
            return MESSAGES["mixed_cert_refresh_qty"][lang]
        if choice == 2:
            return self._prepare_mixed_add_preview(state, self._service_for_location("2_dives_1_day", state))
        self.set_quick_replies(state, "refresher_interest")
        return MESSAGES["not_understood"][lang]

    def _handle_mixed_cert_refresh_qty(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        total_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
        if msg in ("back", "cancel", "cancelar"):
            state.step = Step.MIXED_CERT_REFRESH_INTEREST
            self.set_quick_replies(state, "refresher_interest")
            return MESSAGES["refresher_info"][lang]

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
            self.set_quick_replies(state, "mixed_quantity")
            return MESSAGES["not_understood"][lang]

        state.mixed_pending_exact = False
        self._append_mixed_cart_item(state, "refresh", None, n)
        state.mixed_pending_refresh_added_qty = n
        remaining_qty = total_qty - n
        state.mixed_pending_cert_remaining_qty = remaining_qty
        if remaining_qty <= 0:
            self._clear_mixed_pending_add(state)
            return self._goto_mixed_cart_review(state)

        state.mixed_pending_qty_type = "cert"
        state.mixed_pending_qty_plan = "2_dives_1_day"
        state.mixed_pending_qty_value = remaining_qty
        state.step = Step.MIXED_CERT_SPLIT_REVIEW
        self.set_quick_replies(state, "mixed_cert_split_review")
        return self._build_mixed_cert_split_review_message(state)

    def _handle_mixed_cert_split_review(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
            refresh_qty = state.mixed_pending_refresh_added_qty or 0
            self._remove_mixed_cart_item_qty(state, "refresh", None, refresh_qty)
            state.mixed_pending_refresh_added_qty = None
            state.mixed_pending_cert_remaining_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
            state.step = Step.MIXED_CERT_REFRESH_QTY
            self.set_quick_replies(state, "mixed_quantity")
            return MESSAGES["mixed_cert_refresh_qty"][lang]
        if choice == 1:
            return self._prepare_mixed_add_preview(state, self._service_for_location("2_dives_1_day", state))
        if choice == 2:
            refresh_qty = state.mixed_pending_refresh_added_qty or 0
            self._remove_mixed_cart_item_qty(state, "refresh", None, refresh_qty)
            total_qty = state.mixed_pending_cert_total_qty or state.mixed_pending_qty_value or 0
            state.mixed_pending_refresh_added_qty = None
            state.mixed_pending_cert_remaining_qty = total_qty
            state.mixed_pending_qty_type = "cert"
            state.mixed_pending_qty_plan = "2_dives_1_day"
            state.mixed_pending_qty_value = total_qty
            return self._prepare_mixed_add_preview(state, self._service_for_location("2_dives_1_day", state))
        if choice == 3:
            self._reset_mixed_state(state)
            return self._goto_mixed_entry(state)
        self.set_quick_replies(state, "mixed_cert_split_review")
        return self._build_mixed_cert_split_review_message(state)

    def _handle_mixed_add_preview(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = " ".join(message.strip().lower().split())
        service_id = state.mixed_pending_preview_service_id
        if msg in ("back", "cancel", "cancelar"):
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
            return self._goto_mixed_cart_review(state)

        self.set_quick_replies(state, "mixed_preview_actions")
        return MESSAGES["not_understood"][lang]

    # Emojis numéricos para listas dinámicas (botones de modificar/quitar item)
    _NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    def _cart_pick_buttons(self, state: ConversationState) -> list[dict]:
        """Genera botones dinámicos para elegir un item del carrito (modify/remove)."""
        options: list[dict] = []
        for idx, item in enumerate(state.mixed_cart, start=1):
            emoji = self._NUMBER_EMOJIS[idx - 1] if idx <= len(self._NUMBER_EMOJIS) else f"{idx}."
            # Truncamos el label para que el botón no quede gigante (límite suave de Chatwoot)
            label = item["label"]
            title = f"{emoji} {item['qty']} × {label}"
            if len(title) > 60:
                title = title[:57] + "..."
            options.append({"title": title, "value": str(idx)})
        cancel = (
            {"title": "🔙 Cancelar", "value": "back"}
            if state.language == "es"
            else {"title": "🔙 Cancel", "value": "back"}
        )
        options.append(cancel)
        return options

    def _format_cart_lines(self, state: ConversationState, lang: str) -> str:
        if not state.mixed_cart:
            return MESSAGES["mixed_cart_empty"][lang]
        title = "🛒 *Tu carrito:*" if lang == "es" else "🛒 *Your cart:*"
        lines = [title]
        for idx, item in enumerate(state.mixed_cart, start=1):
            lines.append(f"  *{idx}.* {item['qty']} × {item['label']}")
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
        choice = self._parse_choice(message, 5)
        if choice == 1:
            return self._goto_mixed_add_activity(state)
        if choice == 2:
            if not state.mixed_cart:
                return self._goto_mixed_add_activity(state)
            state.step = Step.MIXED_CART_MODIFY_PICK
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_modify_pick"][lang]
        if choice == 3:
            if not state.mixed_cart:
                return self._goto_mixed_add_activity(state)
            state.step = Step.MIXED_CART_REMOVE_PICK
            state.quick_replies = self._cart_pick_buttons(state)
            return self._format_cart_lines(state, lang) + "\n\n" + MESSAGES["mixed_cart_remove_pick"][lang]
        if choice == 4:
            if not state.mixed_cart:
                self.set_quick_replies(state, "mixed_cart_actions")
                return MESSAGES["mixed_cart_empty"][lang]
            return self._goto_mixed_final_colombian(state)
        if choice == 5:
            self._reset_mixed_state(state)
            return self._goto_mixed_entry(state)
        self.set_quick_replies(state, "mixed_cart_actions")
        return MESSAGES["not_understood"][lang]

    def _handle_mixed_cart_modify_pick(self, state: ConversationState, message: str) -> str:
        lang = state.language
        msg = message.strip().lower()
        if msg in ("back", "cancel", "cancelar"):
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
        if msg in ("back", "cancel", "cancelar"):
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
        ack = (f"✅ Quitado del carrito: {removed['qty']} × {removed['label']}"
               if lang == "es" else
               f"✅ Removed from cart: {removed['qty']} × {removed['label']}")
        return ack + "\n\n" + self._goto_mixed_cart_review(state)

    # ─── Final-question handlers ───

    def _goto_mixed_final_colombian(self, state: ConversationState) -> str:
        lang = state.language
        # Si ya conocemos la respuesta del flujo lineal previo (state.is_colombian),
        # la heredamos y saltamos directo a la siguiente pregunta para no
        # repetir la pregunta al cliente.
        if state.is_colombian is not None and state.mixed_final_is_colombian is None:
            state.mixed_final_is_colombian = state.is_colombian
            state.mixed_display_currency = "COP" if state.is_colombian else "USD"
            if self._cart_includes(state, "beginner"):
                state.step = Step.MIXED_FINAL_KIDS
                self.set_quick_replies(state, "mixed_yes_no")
                return MESSAGES["mixed_final_kids"][lang]
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
        # If beginner in cart → ask kids; else skip to private
        if self._cart_includes(state, "beginner"):
            state.step = Step.MIXED_FINAL_KIDS
            self.set_quick_replies(state, "mixed_yes_no")
            return MESSAGES["mixed_final_kids"][lang]
        if not self._cart_has_boat_activities(state):
            return self._goto_mixed_final_summary(state)
        return self._goto_mixed_final_private(state)

    def _handle_mixed_final_kids(self, state: ConversationState, message: str) -> str:
        lang = state.language
        choice = self._parse_choice(message, 2)
        if choice == 1:
            state.mixed_final_has_kids_8_10 = True
        elif choice == 2:
            state.mixed_final_has_kids_8_10 = False
        else:
            self.set_quick_replies(state, "mixed_yes_no")
            return MESSAGES["not_understood"][lang]
        if not self._cart_has_boat_activities(state):
            return self._goto_mixed_final_summary(state)
        return self._goto_mixed_final_private(state)

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
        choice = self._parse_choice(message, 2)
        if choice == 1:
            # Reservar → escalate + enviar links de reserva
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "grupo mixto - cliente confirma carrito y quiere reservar"

            # Construir bloque de links si los tenemos guardados
            links_block = ""
            if state.mixed_booking_links and not state.mixed_final_is_colombian:
                if lang == "es":
                    lines = ["\n🔗 *Links de reserva* (10% off online):"]
                    for name, url in state.mixed_booking_links:
                        lines.append(f"  • Reserva aquí ({name}): {url}")
                else:
                    lines = ["\n🔗 *Booking links* (10% off online):"]
                    for name, url in state.mixed_booking_links:
                        lines.append(f"  • Book here ({name}): {url}")
                links_block = "\n".join(lines) + "\n"

            if lang == "es":
                return (
                    "¡Perfecto! Te paso con un asesor para confirmar disponibilidad, "
                    "número exacto de personas y precio final. Enseguida se pone en contacto contigo."
                    + links_block
                )
            return (
                "Great! I'll connect you with an advisor to confirm availability, exact "
                "number of people, and the final price. They will be in touch shortly."
                + links_block
            )
        if choice == 2:
            self._reset_mixed_state(state)
            return self._goto_mixed_entry(state)
        self.set_quick_replies(state, "mixed_final_summary_actions")
        return MESSAGES["not_understood"][lang]

    def _handle_tours_certified(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 7)
        lang = state.language
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
            state.step = Step.CERTIFIED_4_DIVES_VARIANT
            self.set_quick_replies(state, "certified_4_dives_variant")
            return MESSAGES["certified_4_dives_variant"][lang]

        if choice in service_map:
            state.selected_service = service_map[choice]
            if state.selected_service == "private":
                state.step = Step.ESCALATE
                state.quick_replies = []
                return self._format_service_detail(state) + "\n\n" + MESSAGES["escalate"][lang]

            self._set_back_target(state, Step.TOURS_CERTIFIED, "tours_certified")
            state.step = Step.CERTIFIED_LAST_DIVE
            self.set_quick_replies(state, "certified_last_dive")
            # Servicios en los que primero preguntamos por la ultima inmersión y nacionalidad,
            # y solo mostramos el resumen completo al final (estructura comun de 2, 5, 7 y 9 buceos).
            core_split_services = {
                "2_dives_1_day",
                "3_dives_1_day",
                "2_dives_1_day_already_on_island",
                "4_dives_2_days",
                "5_dives_2_days",
                "4_dives_2_days_already_on_island",
                "4_dives_2_days_mixed_already_on_island",
                "5_dives_2_days_already_on_island",
                "7_dives_3_days",
                "7_dives_3_days_already_on_island",
                "9_dives_4_days",
                "9_dives_4_days_already_on_island",
                "3_dives_1_day_already_on_island",
            }
            if state.selected_service in core_split_services:
                return MESSAGES["certified_last_dive"][lang]
            return self._format_service_detail(state) + "\n\n" + MESSAGES["certified_last_dive"][lang]
        else:
            self.set_quick_replies(state, "tours_certified")
            return MESSAGES["not_understood"][lang]

    def _handle_certified_4_dives_variant(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.selected_service = "4_dives_2_days_already_on_island"
        elif choice == 2:
            state.selected_service = "4_dives_2_days_mixed_already_on_island"
        else:
            self.set_quick_replies(state, "certified_4_dives_variant")
            return MESSAGES["not_understood"][lang]

        self._set_back_target(state, Step.CERTIFIED_4_DIVES_VARIANT, "certified_4_dives_variant")
        state.step = Step.CERTIFIED_LAST_DIVE
        self.set_quick_replies(state, "certified_last_dive")
        return MESSAGES["certified_last_dive"][lang]

    def _handle_certified_last_dive(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.last_dive_over_2_years = True
            state.step = Step.CERTIFIED_EXPERIENCE
            self.set_quick_replies(state, "certified_experience")
            return MESSAGES["certified_experience"][lang]
        if choice == 2:
            state.last_dive_over_2_years = False
            return self._goto_location_with_costs(state)

        self.set_quick_replies(state, "certified_last_dive")
        return MESSAGES["not_understood"][lang]

    def _handle_certified_experience(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice == 1:
            state.has_500_dives_or_dive_master = True
            state.step = Step.ESCALATE
            state.quick_replies = []
            return MESSAGES["escalate"][lang]
        if choice == 2:
            state.has_500_dives_or_dive_master = False
            state.step = Step.REFRESHER_INTEREST
            self.set_quick_replies(state, "refresher_interest")
            return MESSAGES["refresher_info"][lang]

        self.set_quick_replies(state, "certified_experience")
        return MESSAGES["not_understood"][lang]

    def _handle_refresher_interest(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language
        multi_day_services = MULTI_DAY_SERVICES
        refresher_preserve_services = REFRESHER_PRESERVE_SERVICES

        if choice == 1:
            state.refresher_interested = True
            if state.original_service is None and state.selected_service is not None:
                state.original_service = state.selected_service
            if state.selected_service not in refresher_preserve_services:
                state.selected_service = self._service_for_location("minicourse", state)
        elif choice == 2:
            state.refresher_interested = False
        else:
            self.set_quick_replies(state, "refresher_interest")
            return MESSAGES["not_understood"][lang]

        if state.selected_service in multi_day_services and state.refresher_interested:
            intro = (
                "Perfecto. Mantengo el paquete multi-dia seleccionado y dejo anotado que necesitas "
                "revisar/reforzar habilidades antes de las inmersiones.\n\n"
                "Como es un paquete de varios dias, un asesor confirmara la mejor forma de integrarlo "
                "sin cambiar tu plan principal.\n\n"
                if lang == "es"
                else "Perfect. I'll keep the selected multi-day package and note that you need to review/refresh "
                "skills before the dives.\n\n"
                "Because this is a multi-day package, an advisor will confirm the best way to include it "
                "without changing your main plan.\n\n"
            )
            return intro + self._goto_location_with_costs(state)

        # Para planes de 1 día, el refresher se gestiona como el minicurso de iniciación
        # (mismo formato: piscina + mar), pero el asesor confirma si se factura aparte.
        if state.refresher_interested and state.original_service:
            intro = (
                "Perfecto. Como han pasado más de 2 años, te incluimos el *refresher* — "
                "el asesor lo coordina al confirmar la reserva (sin coste adicional).\n\n"
                if lang == "es"
                else "Perfect. Since it's been more than 2 years, we'll include the *refresher* — "
                "the advisor coordinates it when confirming the booking (no extra cost).\n\n"
            )
            return intro + self._goto_location_with_costs(state)

        return self._goto_location_with_costs(state)

    def _handle_tours_beginner(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 1)
        lang = state.language

        if choice == 1:
            self._set_back_target(state, Step.TOURS_BEGINNER, "tours_beginner")
            state.selected_service = self._service_for_location("minicourse", state)
            state.step = Step.BEGINNER_AGE
            self.set_quick_replies(state, "beginner_age")
            return MESSAGES["beginner_age"][lang]

        self.set_quick_replies(state, "tours_beginner")
        return MESSAGES["not_understood"][lang]

    def _handle_beginner_age(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language

        if choice == 1:
            # Menores de 8: solo pueden hacer snorkel
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "menores de 8 - solo snorkel disponible"
            if lang == "es":
                return (
                    "Los *menores de 8 años* todavía no pueden bucear, pero sí pueden hacer "
                    "*snorkel* (mínimo 6 años) en familia 🐠\n\n"
                    "Te paso con un asesor del equipo de Diving Planet para coordinar la salida según las edades del grupo.\n"
                    "Enseguida se pone en contacto contigo. ¡Gracias! :)"
                )
            return (
                "Children *under 8* cannot dive yet, but they can do *snorkeling* "
                "(minimum age 6) with the family 🐠\n\n"
                "I'll connect you with an advisor to arrange the trip based on the group's ages.\n\n"
                + MESSAGES["escalate"][lang]
            )

        if choice == 2:
            # Niños 8-10: programa Bubble Makers (escala al asesor)
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "ninos 8-10 - programa Bubble Makers"
            if lang == "es":
                return (
                    "Para niños de *8 a 10 años* tenemos el programa *Bubble Makers*: una "
                    "experiencia de buceo en piscina y aguas poco profundas (máximo 2 metros de profundidad), "
                    "diseñada especialmente para niños.\n\n"
                    "Te paso con un asesor del equipo de Diving Planet para coordinar fechas y detalles.\n"
                    "Enseguida se pone en contacto contigo. ¡Gracias! :)"
                )
            return (
                "For children aged *8 to 10* we offer the *Bubble Makers* program: a diving "
                "experience in a pool and shallow water (max. 2 meters deep), specially designed for kids.\n\n"
                "I'll connect you with an advisor to arrange dates and details.\n\n"
                + MESSAGES["escalate"][lang]
            )

        if choice == 3:
            # Todos tienen 10+ años: continuar con LOCATION → COLOMBIAN → SUMMARY
            return self._goto_location_with_costs(state)

        self.set_quick_replies(state, "beginner_age")
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
                    "👥 Descuentos para grupos\n"
                    "📆 Plan PARCEROS (según fechas)\n\n"
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
                    "👥 Group discounts\n"
                    "📆 PARCEROS plan (selected dates)\n\n"
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

        island_hotels = hotels_by_island.get(state.island, [])
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
            if lang == "es":
                return (
                    "🚀 Estos son nuestros cursos PADI avanzados y profesionales.\n"
                    "Elige el que mas te interese."
                )
            return (
                "🚀 These are our advanced and professional PADI courses.\n"
                "Choose the one you are most interested in."
            )
        if choice == 3:
            state.step = Step.COURSES_SPECIALTIES_MENU
            self.set_quick_replies(state, "courses_specialties_menu")
            if lang == "es":
                return (
                    "✨ Estas son nuestras especialidades PADI disponibles.\n"
                    "Elige una para ver la informacion del servicio."
                )
            return (
                "✨ These are our available PADI specialties.\n"
                "Choose one to see the service information."
            )
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

        return self._prepare_mixed_add_preview(
            state,
            state.mixed_pending_qty_plan or self._service_for_location("open_water", state),
        )

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

        if msg in ("itinerary", "skip", "ask", "done", "contact", "reservar", "book"):
            action = "reservar" if msg == "book" else msg

        if choice is None:
            if msg in ("si", "sí", "yes"):
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
                svc = SERVICES.get(service_id) or {}
                if state.location == "island" and svc.get("booking_url_island"):
                    booking_url = svc.get("booking_url_island")
                else:
                    booking_url = svc.get("booking_url")
                state.summary_mode = None
                state.step = Step.ESCALATE
                state.quick_replies = []
                state.pending_escalation_reason = "cliente quiere reservar - confirma asesor"

                if lang == "es":
                    link_block = ""
                    if booking_url and not state.is_colombian:
                        link_block = (
                            f"\n\n🔗 *Link de reserva* (10% off online):\n{booking_url}\n"
                        )
                    return (
                        "¡Perfecto! Te paso con un asesor para confirmar disponibilidad "
                        "y precio final. Enseguida se pone en contacto contigo."
                        + link_block
                    )
                link_block = ""
                if booking_url and not state.is_colombian:
                    link_block = (
                        f"\n\n🔗 *Booking link* (10% off online):\n{booking_url}\n"
                    )
                return (
                    "Great! I'll connect you with an advisor to confirm availability "
                    "and the final price. They will be in touch shortly."
                    + link_block
                )

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
            svc = SERVICES.get(service_id) or {}
            if state.location == "island" and svc.get("booking_url_island"):
                booking_url = svc.get("booking_url_island")
            else:
                booking_url = svc.get("booking_url")
            state.summary_mode = None
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = "cliente quiere reservar - confirma asesor"
            link_block = ""
            if booking_url and not state.is_colombian:
                if lang == "es":
                    link_block = f"\n\n🔗 *Link de reserva* (10% off online):\n{booking_url}\n"
                else:
                    link_block = f"\n\n🔗 *Booking link* (10% off online):\n{booking_url}\n"
            if lang == "es":
                return (
                    "¡Perfecto! Te paso con un asesor para confirmar disponibilidad "
                    "y precio final. Enseguida se pone en contacto contigo."
                    + link_block
                )
            return (
                "Great! I'll connect you with an advisor to confirm availability "
                "and the final price. They will be in touch shortly."
                + link_block
            )

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
        if state.location == "island" and service.get("booking_url_island"):
            booking_url = service["booking_url_island"]
        else:
            booking_url = service.get("booking_url")

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

        # Bloque final con link de pago si hay booking_url (excepto para referral)
        if booking_url and not contact_only and service_id not in {"referral", "referral_already_on_island"}:
            block = [payment_title, booking_url]
            blocks.append(block)

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
        if state.mixed_final_has_kids_8_10:
            avisos_lines.append(
                "  • Niños 8-10 (Bubble Makers): supervisor especializado — el asesor confirmará el precio final al reservar"
                if lang == "es"
                else "  • Kids 8-10 (Bubble Makers): specialized supervisor — advisor confirms the final price at booking"
            )
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
            lbl = "Minicurso" if lang == "es" else "Mini-course"
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
        if self._cart_includes(state, "snorkel"):
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
            departure = "Cartagena" if state.location == "cartagena" else "Islas del Rosario"
            meeting_note = ""
            if state.location == "cartagena":
                meeting_note = "⏰ Punto de encuentro: 8:00 AM en el Muelle de la Bodeguita."
            elif state.location == "island":
                meeting_note = "⏰ Recogida en hotel: alrededor de 9:30 AM (si hay acceso marítimo)."

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

            if state.is_colombian and price_cop:
                if price_cop_normal:
                    price_text = (
                        f"💰 Precio:\n"
                        f"  • {_fmt_cop(price_cop)} COP reservando online (10% off)\n"
                        f"  • {_fmt_cop(price_cop_normal)} COP tarifa normal"
                    )
                else:
                    price_text = f"💰 Precio: {_fmt_cop(price_cop)} COP"
            elif price_usd:
                if price_usd_normal:
                    price_text = (
                        f"💰 Precio:\n"
                        f"  • {_fmt_usd_es(price_usd)} USD reservando online (10% off)\n"
                        f"  • {_fmt_usd_es(price_usd_normal)} USD tarifa normal"
                    )
                else:
                    price_text = f"💰 Precio: {_fmt_usd_es(price_usd)} USD"
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
            departure = "Cartagena" if state.location == "cartagena" else "Rosario Islands"
            meeting_note = ""
            if state.location == "cartagena":
                meeting_note = "\n⏰ Meeting point: 8:00 AM at Muelle de la Bodeguita."
            elif state.location == "island":
                meeting_note = "\n⏰ Hotel pickup: around 9:30 AM (if there is sea access)."

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

            price_line = ""
            if state.is_colombian and price_cop:
                if price_cop_normal:
                    price_line = (
                        f"\n💰 *Price*:\n"
                        f"  • {_fmt_cop_en(price_cop)} COP booking online (10% off)\n"
                        f"  • {_fmt_cop_en(price_cop_normal)} COP standard rate"
                    )
                else:
                    price_line = f"\n💰 *Price*: {_fmt_cop_en(price_cop)} COP"
            elif price_usd:
                if price_usd_normal:
                    price_line = (
                        f"\n💰 *Price*:\n"
                        f"  • {_fmt_usd_en(price_usd)} USD booking online (10% off)\n"
                        f"  • {_fmt_usd_en(price_usd_normal)} USD standard rate"
                    )
                else:
                    price_line = f"\n💰 *Price*: {_fmt_usd_en(price_usd)} USD"
            elif price_note:
                price_line = f"\n💰 *Price*: {price_note}"

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
