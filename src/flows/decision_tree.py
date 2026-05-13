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


class Step(str, Enum):
    WELCOME = "welcome"
    LANGUAGE = "language"
    MAIN_MENU = "main_menu"
    GROUP_TYPE = "group_type"
    TOURS_EXPERIENCE = "tours_experience"
    TOURS_CERTIFIED = "tours_certified"
    CERTIFIED_LAST_DIVE = "certified_last_dive"
    CERTIFIED_EXPERIENCE = "certified_experience"
    REFRESHER_INTEREST = "refresher_interest"
    TOURS_BEGINNER = "tours_beginner"
    COURSES_MENU = "courses_menu"
    COURSES_OPEN_WATER_ORIGIN = "courses_open_water_origin"
    COURSES_OPEN_WATER_TIME = "courses_open_water_time"
    COURSES_ADVANCED_MENU = "courses_advanced_menu"
    PRICING_MENU = "pricing_menu"
    BOOKING_MENU = "booking_menu"
    LOGISTICS_MENU = "logistics_menu"
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

    def __post_init__(self):
        if self.history is None:
            self.history = []


def _join_items(items: list[str] | str | None) -> str:
    if isinstance(items, list):
        return ", ".join(items)
    return items or ""


def _format_price(service: dict) -> str:
    price = service.get("price_usd")
    normal = service.get("price_usd_normal")
    note = service.get("price_note")
    if price and normal:
        return f"U${price} online / U${normal} normal"
    if price:
        return f"U${price}"
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


def _extra_notes(service: dict, lang: str) -> str:
    parts = []
    description = service.get(f"description_{lang}")
    preparation = service.get(f"preparation_{lang}")
    itinerary = service.get(f"itinerary_{lang}", [])
    not_included = service.get(f"not_included_{lang}", [])
    requirements = service.get(f"requirements_{lang}", [])
    if description:
        parts.append(description)
    if preparation:
        title = "Preparacion: " if lang == "es" else "Preparation: "
        parts.append(title + preparation)
    if itinerary:
        title = "Itinerario: " if lang == "es" else "Itinerary: "
        parts.append(title + "; ".join(itinerary))
    if requirements:
        title = "Requisitos: " if lang == "es" else "Requirements: "
        parts.append(title + "; ".join(requirements))
    if not_included:
        title = "No incluye: " if lang == "es" else "Not included: "
        parts.append(title + "; ".join(not_included))
    if lang == "es":
        if "Minicurso" in service.get("name_es", "") and "No necesitas experiencia previa" not in " ".join(parts):
            parts.append("No necesitas experiencia previa.")
        if "Snorkeling" in service.get("name_es", "") and "Actividad de superficie" not in " ".join(parts):
            parts.append("Actividad de superficie ideal para acompanantes o personas que no quieren bucear.")
        if service.get("includes_night_dive") and "quitar la nocturna" not in " ".join(parts):
            parts.append("Si quieres quitar la nocturna, cambiar noches o personalizar el paquete, lo revisamos con un asesor.")
        if any("Hotel/alojamiento" in item for item in not_included) and "alojamiento no esta incluido" not in " ".join(parts):
            parts.append("El alojamiento no esta incluido y se reserva aparte con el hotel.")
    return " ".join(parts)


def _load_services() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "services.json"
    raw_services = json.loads(path.read_text(encoding="utf-8")).get("services", {})
    services = {}
    for service_id, service in raw_services.items():
        services[service_id] = {
            "name_es": service.get("name_es", service_id),
            "name_en": service.get("name_en", service.get("name_es", service_id)),
            "requires_cert": service.get("requires_certification", False),
            "price": _format_price(service),
            "duration_es": _format_duration(service, "es"),
            "duration_en": _format_duration(service, "en"),
            "includes_es": _join_items(service.get("included_es")),
            "includes_en": _join_items(service.get("included_en")),
            "min_age": service.get("min_age")
            or (10 if "Minicurso" in service.get("name_es", "") else 6 if "Snorkeling" in service.get("name_es", "") else None),
            "extra_notes_es": _extra_notes(service, "es"),
            "extra_notes_en": _extra_notes(service, "en"),
            "flight_rule_es": _flight_rule(service, "es"),
            "flight_rule_en": _flight_rule(service, "en"),
            "booking_url": service.get("booking_url") or service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url_island": "",
            "category": service.get("category"),
        }
    return services


SERVICES = _load_services()

ISLAND_SERVICE_MAP = {
    "2_dives_1_day": "2_dives_1_day_already_on_island",
    "minicourse": "minicourse_already_on_island",
    "snorkeling": "snorkeling_already_on_island",
    "5_dives_2_days": "5_dives_2_days_already_on_island",
    "7_dives_3_days": "7_dives_3_days_already_on_island",
    "open_water": "open_water_already_on_island",
    "advanced": "advanced_already_on_island",
    "fish_identification_specialty": "fish_identification_specialty_already_on_island",
    "nitrox_specialty": "nitrox_specialty_already_on_island",
    "naturalist_specialty": "naturalist_specialty_already_on_island",
    "buoyancy_specialty": "buoyancy_specialty_already_on_island",
}

MULTI_DAY_SERVICES = {
    "5_dives_2_days",
    "7_dives_3_days",
    "9_dives_4_days",
    "3_dives_1_day_already_on_island",
    "5_dives_2_days_already_on_island",
    "7_dives_3_days_already_on_island",
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


# --- Messages templates ---

MESSAGES = {
    "welcome": {
        "es": (
            "Hola! Bienvenido a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 anos de experiencia en "
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
    "tours_experience": {
        "es": (
            "Tienes certificacion de buceo?"
        ),
        "en": (
            "Do you have a diving certification?"
        ),
    },
    "tours_certified": {
        "es": (
            "Excelente! Estas son nuestras opciones para buzos certificados:"
        ),
        "en": (
            "Excellent! Here are our options for certified divers:"
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
            "Te recomendamos hacer un *refresher* para volver al agua de forma segura:\n\n"
            "✅ Repaso de teoría (señales, equipo y procedimientos)\n"
            "🏊 Práctica en piscina\n"
            "🤿 Buceo en el mar con instructor\n\n"
            "Más información (itinerario completo):\n"
            "https://divingplanet.org/tours-buceo-snorkel-cartagena/minicurso-principiantes/\n\n"
            "¿Te interesa incluirlo?"
        ),
        "en": (
            "A *refresher* is a quick review with an instructor before diving.\n"
            "It typically covers signals, equipment setup, procedures, and a controlled skills practice "
            "(depending on your level and the day's conditions).\n\n"
            "Would you like to include it?"
        ),
    },
    "tours_beginner": {
        "es": (
            "Perfecto! No necesitas experiencia previa.\n\n"
            "- Si quieres *probar buceo*, elige *Minicurso de Buceo*.\n"
            "- Si prefieres ir en superficie o acompanar a alguien, elige *Tour de Snorkeling*.\n"
            "- Para grupos especiales o algo privado, elige *Servicio Privado*."
        ),
        "en": (
            "Perfect! No previous experience is needed.\n\n"
            "- If you want to *try diving*, choose *Dive Mini Course*.\n"
            "- If you prefer staying at the surface or accompanying someone, choose *Snorkeling Tour*.\n"
            "- For special groups or a private setup, choose *Private Service*."
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
    "group_type": {
        "es": (
            "Genial, cuentame como es tu grupo:\n"
            "Elige la opcion que mejor se ajuste."
        ),
        "en": (
            "Great! Tell me about your group:\n"
            "Choose the option that fits best."
        ),
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
            "Para esta situacion especifica, prefiero transferirte con mi jefe.\n"
            "Enseguida se pone en contacto con usted, muchas gracias :)"
        ),
        "en": (
            "For this specific situation, I'd prefer to transfer you to my manager.\n"
            "They will contact you shortly. Thank you :)"
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
            {"title": "🤿 Tours de buceo y snorkel (desde Cartagena)", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "📘 Cursos PADI y certificaciones", "value": "3"},
            {"title": "💰 Precios y descuentos", "value": "4"},
            {"title": "💳 Reserva y pagos", "value": "5"},
            {"title": "ℹ️ Logistica y otras preguntas", "value": "6"},
            {"title": "🧑‍💬 Hablar con un asesor", "value": "7"},
        ],
        "en": [
            {"title": "🤿 Diving and snorkel tours (from Cartagena)", "value": "1"},
            {"title": "🏝️ I'm already on the islands", "value": "2"},
            {"title": "📘 PADI courses and certifications", "value": "3"},
            {"title": "💰 Prices and discounts", "value": "4"},
            {"title": "💳 Booking and payments", "value": "5"},
            {"title": "ℹ️ Logistics and other questions", "value": "6"},
            {"title": "🧑‍💬 Speak with an advisor", "value": "7"},
        ],
    },
    "group_type": {
        "es": [
            {"title": "Solo buzos certificados", "value": "1"},
            {"title": "Solo principiantes", "value": "2"},
            {"title": "Grupo mixto (buceo + snorkel)", "value": "3"},
            {"title": "Solo snorkel / acompanantes", "value": "4"},
        ],
        "en": [
            {"title": "Only certified divers", "value": "1"},
            {"title": "Only beginners", "value": "2"},
            {"title": "Mixed group (diving + snorkel)", "value": "3"},
            {"title": "Only snorkel / companions", "value": "4"},
        ],
    },
    "tours_experience": {
        "es": [
            {"title": "✅ Si, soy buzo certificado", "value": "1"},
            {"title": "🆕 No, nunca he buceado", "value": "2"},
            {"title": "❓ No estoy seguro", "value": "3"},
        ],
        "en": [
            {"title": "✅ Yes, I'm certified", "value": "1"},
            {"title": "🆕 No, never dived", "value": "2"},
            {"title": "❓ I'm not sure", "value": "3"},
        ],
    },
    "tours_certified": {
        "es": [
            {"title": "🤿 2 Buceos - 1 dia", "value": "1"},
            {"title": "🤿 5 Buceos - 2 dias", "value": "2"},
            {"title": "🤿 7 Buceos - 3 dias", "value": "3"},
            {"title": "🤿 9 Buceos - 4 dias", "value": "4"},
            {"title": "🧑‍💬 Servicio Privado", "value": "5"},
        ],
        "en": [
            {"title": "🤿 2 Dives - 1 day", "value": "1"},
            {"title": "🤿 5 Dives - 2 days", "value": "2"},
            {"title": "🤿 7 Dives - 3 days", "value": "3"},
            {"title": "🤿 9 Dives - 4 days", "value": "4"},
            {"title": "🧑‍💬 Private Service", "value": "5"},
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
            {"title": "🐠 Tour de Snorkeling", "value": "2"},
            {"title": "🧑‍💬 Servicio Privado", "value": "3"},
        ],
        "en": [
            {"title": "🤿 Dive Mini Course", "value": "1"},
            {"title": "🐠 Snorkeling Tour", "value": "2"},
            {"title": "🧑‍💬 Private Service", "value": "3"},
        ],
    },
    "courses_menu": {
        "es": [
            {"title": "Quiero certificarme (curso Basico Open Water)", "value": "1"},
            {"title": "Quiero otro curso PADI (Avanzado / Rescate / Dive Master)", "value": "2"},
            {"title": "Especialidades PADI", "value": "3"},
            {"title": "Ya empece un curso en otro centro (referral / reactivate)", "value": "4"},
        ],
        "en": [
            {"title": "I want to get certified (Open Water)", "value": "1"},
            {"title": "I want another PADI course (Advanced / Rescue / Divemaster)", "value": "2"},
            {"title": "PADI specialties", "value": "3"},
            {"title": "I already started a course elsewhere (referral / reactivate)", "value": "4"},
        ],
    },
    "courses_open_water_origin": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
        ],
    },
    "courses_open_water_time": {
        "es": [
            {"title": "Si, tengo al menos 2 dias completos", "value": "1"},
            {"title": "No estoy seguro / tengo menos tiempo", "value": "2"},
        ],
        "en": [
            {"title": "Yes, I have at least 2 full days", "value": "1"},
            {"title": "Not sure / I have less time", "value": "2"},
        ],
    },
    "courses_advanced_menu": {
        "es": [
            {"title": "📘 Curso Avanzado", "value": "1"},
            {"title": "🛟 Rescate + EFR", "value": "2"},
            {"title": "🏅 Dive Master", "value": "3"},
            {"title": "✨ Mindful Diving", "value": "4"},
            {"title": "🐠 Identificacion de Peces", "value": "5"},
            {"title": "🌿 Naturalista", "value": "6"},
            {"title": "⚖️ Flotabilidad", "value": "7"},
            {"title": "🫧 Nitrox", "value": "8"},
        ],
        "en": [
            {"title": "📘 Advanced Course", "value": "1"},
            {"title": "🛟 Rescue + EFR", "value": "2"},
            {"title": "🏅 Divemaster", "value": "3"},
            {"title": "✨ Mindful Diving", "value": "4"},
            {"title": "🐠 Fish Identification", "value": "5"},
            {"title": "🌿 Naturalist", "value": "6"},
            {"title": "⚖️ Buoyancy", "value": "7"},
            {"title": "🫧 Nitrox", "value": "8"},
        ],
    },
    "pricing_menu": {
        "es": [
            {"title": "Precios saliendo desde Cartagena", "value": "1"},
            {"title": "Precios si ya estoy en las islas", "value": "2"},
            {"title": "Paquetes 5/7/9 buceos (multi-dia)", "value": "3"},
            {"title": "Descuentos para colombianos/residentes", "value": "4"},
        ],
        "en": [
            {"title": "Prices departing from Cartagena", "value": "1"},
            {"title": "Prices if I'm already on the islands", "value": "2"},
            {"title": "5/7/9-dive multi-day packages", "value": "3"},
            {"title": "Discounts for Colombians/residents", "value": "4"},
        ],
    },
    "booking_menu": {
        "es": [
            {"title": "Pagar todo online", "value": "1"},
            {"title": "Pagar 50% ahora y 50% despues", "value": "2"},
            {"title": "Formas de pago (tarjeta / transferencia)", "value": "3"},
            {"title": "Reservas de grupo o agencia", "value": "4"},
        ],
        "en": [
            {"title": "Pay everything online", "value": "1"},
            {"title": "Pay 50% now and 50% later", "value": "2"},
            {"title": "Payment methods (card / transfer)", "value": "3"},
            {"title": "Group or agency bookings", "value": "4"},
        ],
    },
    "logistics_menu": {
        "es": [
            {"title": "Punto de encuentro y horarios", "value": "1"},
            {"title": "Alojamiento en islas y recogida en hotel", "value": "2"},
            {"title": "Que incluye / que no incluye el plan", "value": "3"},
            {"title": "Que llevar y recomendaciones", "value": "4"},
        ],
        "en": [
            {"title": "Meeting point and schedule", "value": "1"},
            {"title": "Accommodation on the islands & hotel pickup", "value": "2"},
            {"title": "What's included / not included", "value": "3"},
            {"title": "What to bring & recommendations", "value": "4"},
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
            {"title": "❓ Si, tengo mas preguntas", "value": "1"},
            {"title": "🙏 No, gracias", "value": "2"},
        ],
        "en": [
            {"title": "❓ Yes, I have more questions", "value": "1"},
            {"title": "🙏 No, thanks", "value": "2"},
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
        state.quick_replies = get_button_options(key, state.language)

    def _service_for_location(self, service_id: str, state: ConversationState) -> str:
        if state.location == "island":
            return ISLAND_SERVICE_MAP.get(service_id, service_id)
        return service_id

    def _island_certified_options(self, lang: str) -> list[dict]:
        if lang == "es":
            return [
                {"title": "🤿 2 buceos - 1 dia", "value": "1"},
                {"title": "🌙 3 buceos - 1 dia (incluye nocturna)", "value": "2"},
                {"title": "🤿 5 buceos - 2 dias", "value": "3"},
                {"title": "🤿 7 buceos - 3 dias", "value": "4"},
                {"title": "🧑‍💬 Servicio Privado", "value": "5"},
            ]
        return [
            {"title": "🤿 2 dives - 1 day", "value": "1"},
            {"title": "🌙 3 dives - 1 day (includes night dive)", "value": "2"},
            {"title": "🤿 5 dives - 2 days", "value": "3"},
            {"title": "🤿 7 dives - 3 days", "value": "4"},
            {"title": "🧑‍💬 Private Service", "value": "5"},
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
            Step.GROUP_TYPE: self._handle_group_type,
            Step.TOURS_EXPERIENCE: self._handle_tours_experience,
            Step.TOURS_CERTIFIED: self._handle_tours_certified,
            Step.CERTIFIED_LAST_DIVE: self._handle_certified_last_dive,
            Step.CERTIFIED_EXPERIENCE: self._handle_certified_experience,
            Step.REFRESHER_INTEREST: self._handle_refresher_interest,
            Step.TOURS_BEGINNER: self._handle_tours_beginner,
            Step.COURSES_MENU: self._handle_courses_menu,
            Step.COURSES_OPEN_WATER_ORIGIN: self._handle_courses_open_water_origin,
            Step.COURSES_OPEN_WATER_TIME: self._handle_courses_open_water_time,
            Step.COURSES_ADVANCED_MENU: self._handle_courses_advanced_menu,
            Step.PRICING_MENU: self._handle_pricing_menu,
            Step.BOOKING_MENU: self._handle_booking_menu,
            Step.LOGISTICS_MENU: self._handle_logistics_menu,
            Step.ISLAND_MENU: self._handle_island_menu,
            Step.ISLAND_HOTEL_MENU: self._handle_island_hotel_menu,
            Step.SERVICE_DETAIL: self._handle_service_detail,
            Step.LOCATION: self._handle_location,
            Step.COLOMBIAN: self._handle_colombian,
        }

        handler = handlers.get(state.step, self._handle_welcome)
        return handler(state, message)

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
            # Try to detect language from text
            if any(w in message.lower() for w in ["english", "en", "hi", "hello"]):
                state.language = "en"
            elif any(w in message.lower() for w in ["espanol", "español", "es", "hola"]):
                state.language = "es"
            else:
                self.set_quick_replies(state, "welcome")
                return MESSAGES["not_understood"]["es"]

        state.step = Step.MAIN_MENU
        self.set_quick_replies(state, "main_menu")
        return MESSAGES["main_menu"][state.language]

    def _handle_main_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 7)
        lang = state.language

        if state.history is None:
            state.history = []

        if choice == 1:
            # Tours desde Cartagena: fijamos ubicacion y pedimos tipo de grupo
            state.location = "cartagena"
            state.step = Step.GROUP_TYPE
            self.set_quick_replies(state, "group_type")
            return MESSAGES["group_type"][lang]
        elif choice == 2:
            # Planes para quienes ya estan en las islas: fijamos ubicacion y pedimos tipo de grupo
            state.location = "island"
            state.step = Step.GROUP_TYPE
            self.set_quick_replies(state, "group_type")
            return MESSAGES["group_type"][lang]
        elif choice == 3:
            state.step = Step.COURSES_MENU
            self.set_quick_replies(state, "courses_menu")
            return MESSAGES["courses_menu"][lang]
        elif choice == 4:
            state.step = Step.PRICING_MENU
            self.set_quick_replies(state, "pricing_menu")
            return MESSAGES["pricing_menu"][lang]
        elif choice == 5:
            state.step = Step.BOOKING_MENU
            self.set_quick_replies(state, "booking_menu")
            return MESSAGES["booking_menu"][lang]
        elif choice == 6:
            state.step = Step.LOGISTICS_MENU
            self.set_quick_replies(state, "logistics_menu")
            return MESSAGES["logistics_menu"][lang]
        elif choice == 7:
            state.step = Step.ESCALATE
            return MESSAGES["escalate"][lang]
        else:
            self.set_quick_replies(state, "main_menu")
            return MESSAGES["not_understood"][lang]

    def _handle_group_type(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice == 1:
            # Solo buzos certificados
            state.is_certified = True
            state.step = Step.TOURS_CERTIFIED
            self.set_quick_replies(state, "tours_certified")
            return MESSAGES["tours_certified"][lang]
        elif choice == 2:
            # Solo principiantes
            state.is_certified = False
            state.step = Step.TOURS_BEGINNER
            self.set_quick_replies(state, "tours_beginner")
            return MESSAGES["tours_beginner"][lang]
        elif choice == 3:
            # Grupo mixto: explicamos como funciona y derivamos a humano
            state.step = Step.ESCALATE
            state.quick_replies = []
            if lang == "es":
                return (
                    "¡Perfecto! Para grupos mixtos (buzos certificados, principiantes y/o snorkel) "
                    "podemos combinar actividades en un mismo tour:\n\n"
                    "- Todos viajan juntos Cartagena ↔ Islas y comparten base y almuerzo.\n"
                    "- Durante las actividades, los snorkelers pueden ir en otra lancha por seguridad.\n"
                    "- Cada subgrupo elige su plan (2 buceos, paquete de varios dias, minicurso o snorkel).\n\n"
                    "Como se trata de una reserva mas personalizada, te paso con un asesor para afinar "
                    "fechas, cupos y precios segun tu grupo.\n\n"
                    + MESSAGES["escalate"][lang]
                )
            return (
                "Great! For mixed groups (certified divers, beginners and/or snorkelers) we can "
                "combine activities in a single tour:\n\n"
                "- Everyone travels together Cartagena ↔ Rosario Islands and shares the same base and lunch.\n"
                "- Snorkelers may use a different boat during the activity for safety.\n"
                "- Each subgroup chooses its plan (2 dives, multi-day packages, minicourse or snorkel).\n\n"
                "Because this is a more customized booking, I'll transfer you to a human advisor to "
                "confirm dates, availability and pricing for your group.\n\n"
                + MESSAGES["escalate"][lang]
            )
        elif choice == 4:
            # Solo snorkel / acompanantes: usamos el plan de snorkel directamente
            state.is_certified = False
            state.selected_service = self._service_for_location("snorkeling", state)
            state.step = Step.COLOMBIAN
            self.set_quick_replies(state, "colombian")
            return self._format_service_detail(state) + "\n\n" + MESSAGES["colombian"][lang]

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
        elif choice in (2, 3):
            state.is_certified = False
            state.step = Step.TOURS_BEGINNER
            self.set_quick_replies(state, "tours_beginner")
            return MESSAGES["tours_beginner"][lang]
        else:
            self.set_quick_replies(state, "tours_experience")
            return MESSAGES["not_understood"][lang]

    def _handle_tours_certified(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 5)
        lang = state.language
        if state.location == "island":
            service_map = {
                1: "2_dives_1_day_already_on_island",
                2: "3_dives_1_day_already_on_island",
                3: "5_dives_2_days_already_on_island",
                4: "7_dives_3_days_already_on_island",
                5: "private",
            }
        else:
            service_map = {
                1: "2_dives_1_day",
                2: "5_dives_2_days",
                3: "7_dives_3_days",
                4: "9_dives_4_days",
                5: "private",
            }

        if choice in service_map:
            state.selected_service = service_map[choice]
            if state.selected_service == "private":
                state.step = Step.ESCALATE
                state.quick_replies = []
                return self._format_service_detail(state) + "\n\n" + MESSAGES["escalate"][lang]

            state.step = Step.CERTIFIED_LAST_DIVE
            self.set_quick_replies(state, "certified_last_dive")
            if state.selected_service in ("2_dives_1_day", "2_dives_1_day_already_on_island"):
                return MESSAGES["certified_last_dive"][lang]
            return self._format_service_detail(state) + "\n\n" + MESSAGES["certified_last_dive"][lang]
        else:
            self.set_quick_replies(state, "tours_certified")
            return MESSAGES["not_understood"][lang]

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
            state.step = Step.COLOMBIAN
            self.set_quick_replies(state, "colombian")
            if state.selected_service in ("2_dives_1_day", "2_dives_1_day_already_on_island"):
                return self._format_service_detail(state) + "\n\n" + MESSAGES["colombian"][lang]
            return MESSAGES["colombian"][lang]

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

        if choice == 1:
            state.refresher_interested = True
            if state.original_service is None and state.selected_service is not None:
                state.original_service = state.selected_service
            if state.selected_service not in multi_day_services:
                state.selected_service = self._service_for_location("minicourse", state)
        elif choice == 2:
            state.refresher_interested = False
        else:
            self.set_quick_replies(state, "refresher_interest")
            return MESSAGES["not_understood"][lang]

        state.step = Step.COLOMBIAN
        self.set_quick_replies(state, "colombian")
        if state.selected_service in multi_day_services and state.refresher_interested:
            if lang == "es":
                return (
                    "Perfecto. Mantengo el paquete multi-dia seleccionado y dejo anotado que necesitas "
                    "revisar/reforzar habilidades antes de las inmersiones.\n\n"
                    "Como es un paquete de varios dias, un asesor confirmara la mejor forma de integrarlo "
                    "sin cambiar tu plan principal.\n\n"
                    + MESSAGES["colombian"][lang]
                )
            return (
                "Perfect. I'll keep the selected multi-day package and note that you need to review/refresh "
                "skills before the dives.\n\n"
                "Because this is a multi-day package, an advisor will confirm the best way to include it "
                "without changing your main plan.\n\n"
                + MESSAGES["colombian"][lang]
            )
        return MESSAGES["colombian"][lang]

    def _handle_tours_beginner(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language
        service_map = {
            1: self._service_for_location("minicourse", state),
            2: self._service_for_location("snorkeling", state),
            3: "private",
        }

        if choice in service_map:
            state.selected_service = service_map[choice]
            if state.selected_service == "private":
                state.step = Step.ESCALATE
                state.quick_replies = []
                if lang == "es":
                    return (
                        "Perfecto. Para un *servicio privado* necesitamos revisar fecha, numero de personas, "
                        "nivel de experiencia, si habra snorkelers/acompanantes y preferencias de horario.\n\n"
                        + MESSAGES["escalate"][lang]
                    )
                return (
                    "Perfect. For a *private service* we need to review the date, group size, experience level, "
                    "whether there will be snorkelers/companions, and schedule preferences.\n\n"
                    + MESSAGES["escalate"][lang]
                )
            # Si ya conocemos la ubicacion (Cartagena o islas), pasamos directo a pregunta de colombiano
            if state.location:
                state.step = Step.COLOMBIAN
                self.set_quick_replies(state, "colombian")
                return self._format_service_detail(state) + "\n\n" + MESSAGES["colombian"][lang]

            state.step = Step.LOCATION
            self.set_quick_replies(state, "location")
            return self._format_service_detail(state) + "\n\n" + MESSAGES["location"][lang]
        else:
            self.set_quick_replies(state, "tours_beginner")
            return MESSAGES["not_understood"][lang]

    def _handle_pricing_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "pricing_menu")
            return MESSAGES["not_understood"][lang]

        if lang == "es":
            if choice == 1:
                response = (
                    "Te cuento los precios de referencia *saliendo desde Cartagena*:\n\n"
                    f"- 2 buceos 1 dia: {SERVICES['2_dives_1_day']['price']}\n"
                    f"- Minicurso de buceo: {SERVICES['minicourse']['price']}\n"
                    f"- Tour de snorkel: {SERVICES['snorkeling']['price']}\n\n"
                    "Los montos exactos y promociones (como el 10% online) se actualizan siempre en la web. "
                    "Cuando elijas un plan te compartire el enlace de reserva con el precio vigente."
                )
            elif choice == 2:
                location_note = ""
                if state.location == "island":
                    location_note = "Como ya indicaste que estas en las islas, "
                response = (
                    f"{location_note}para quienes *ya estan en las Islas del Rosario* manejamos tarifas "
                    "especiales sin transporte Cartagena-Islas ni almuerzo incluido.\n\n"
                    f"- 2 buceos: {SERVICES['2_dives_1_day_already_on_island']['price']}\n"
                    f"- 3 buceos con nocturna: {SERVICES['3_dives_1_day_already_on_island']['price']}\n"
                    f"- Minicurso: {SERVICES['minicourse_already_on_island']['price']}\n"
                    f"- Snorkel: {SERVICES['snorkeling_already_on_island']['price']}\n\n"
                    "En cada enlace de reserva veras el valor actualizado segun actividad y fecha."
                )
            elif choice == 3:
                response = (
                    "Sobre los *paquetes multi-dia*:\n\n"
                    f"- 5 buceos 2 dias: {SERVICES['5_dives_2_days']['price']}\n"
                    f"- 7 buceos 3 dias: {SERVICES['7_dives_3_days']['price']}\n"
                    f"- 9 buceos 4 dias: {SERVICES['9_dives_4_days']['price']}\n\n"
                    "Si ya estas en las islas, tambien existen versiones especificas:\n"
                    f"- 5 buceos 2 dias (islas): {SERVICES['5_dives_2_days_already_on_island']['price']}\n"
                    f"- 7 buceos 3 dias (islas): {SERVICES['7_dives_3_days_already_on_island']['price']}\n\n"
                    "En todos los casos el alojamiento en las islas se reserva aparte directamente con el hotel. "
                    "En la web veras siempre el valor actualizado y posibles promociones antes de confirmar."
                )
            else:  # choice == 4
                response = (
                    "Para *colombianos y residentes* tenemos precios especiales en COP y distintos tipos de "
                    "descuentos (10% online, segundo dia, grupos, plan PARCEROS en algunas fechas).\n\n"
                    "Normalmente veras un valor en USD en la web y, al contactarnos por WhatsApp, podemos "
                    "aplicarte la tarifa local cuando corresponda y explicarte las condiciones."
                )
        else:
            if choice == 1:
                response = (
                    "Here are reference prices *departing from Cartagena*:\n\n"
                    f"- 2 dives 1 day: {SERVICES['2_dives_1_day']['price']}\n"
                    f"- Dive minicourse: {SERVICES['minicourse']['price']}\n"
                    f"- Snorkeling tour: {SERVICES['snorkeling']['price']}\n\n"
                    "Exact amounts and promotions (such as the 10% online discount) are always updated "
                    "on the website. Once you choose a plan I'll share the booking link with the current price."
                )
            elif choice == 2:
                location_note = ""
                if state.location == "island":
                    location_note = "Since you already indicated you are on the islands, "
                response = (
                    f"{location_note}for guests *already on the Rosario Islands* we usually work with "
                    "special rates that do not include transport from Cartagena or lunch.\n\n"
                    f"- 2 dives: {SERVICES['2_dives_1_day_already_on_island']['price']}\n"
                    f"- 3 dives with night dive: {SERVICES['3_dives_1_day_already_on_island']['price']}\n"
                    f"- Dive minicourse: {SERVICES['minicourse_already_on_island']['price']}\n"
                    f"- Snorkeling: {SERVICES['snorkeling_already_on_island']['price']}\n\n"
                    "Each booking link will show the up-to-date amount for your activity and date."
                )
            elif choice == 3:
                response = (
                    "For *multi-day packages*:\n\n"
                    f"- 5 dives 2 days: {SERVICES['5_dives_2_days']['price']}\n"
                    f"- 7 dives 3 days: {SERVICES['7_dives_3_days']['price']}\n"
                    f"- 9 dives 4 days: {SERVICES['9_dives_4_days']['price']}\n\n"
                    "If you are already on the islands, there are also dedicated versions:\n"
                    f"- 5 dives 2 days (islands): {SERVICES['5_dives_2_days_already_on_island']['price']}\n"
                    f"- 7 dives 3 days (islands): {SERVICES['7_dives_3_days_already_on_island']['price']}\n\n"
                    "Accommodation on the islands is not included and is booked directly with the hotel. "
                    "The website will always show the current amount and any promotions before you pay."
                )
            else:  # choice == 4
                response = (
                    "We offer special COP prices and discounts for *Colombian guests and residents* "
                    "(online discounts, second-day and group discounts, PARCEROS plan on selected dates).\n\n"
                    "You'll usually see a USD price on the website, and when contacting us on WhatsApp we "
                    "can apply the local rate when applicable and explain the conditions."
                )

        # Tras responder, volvemos al menu principal
        state.step = Step.MAIN_MENU
        self.set_quick_replies(state, "main_menu")
        return response

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
            quick_replies.append({"title": "Otro / No esta en la lista", "value": str(len(island_hotels) + 1)})

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
                quick_replies.append({"title": "Otro / No esta en la lista", "value": str(len(island_hotels) + 1)})
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
                    "acompanantes) o coordinar una reserva centralizada.\n\n"
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
        return response

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
                        "Para *salidas desde Cartagena*:\n\n"
                        "- Punto de encuentro: Muelle de la Bodeguita a las 8:00 a.m. (entrada 3, a pocos minutos de la Ciudad Amurallada).\n"
                        "- Regreso estimado de los tours de un dia: entre 4:00 y 4:30 p.m.\n\n"
                        "En los paquetes de varios dias, el horario se ajusta segun el numero de inmersiones y noches "
                        "en las islas, y veras el detalle en el enlace de cada plan."
                    )
                else:
                    response = (
                        "Normalmente las salidas operan asi:\n\n"
                        "- Punto de encuentro en Cartagena: Muelle de la Bodeguita a las 8:00 a.m.\n"
                        "- Regreso estimado de los tours de un dia: entre 4:00 y 4:30 p.m.\n\n"
                        "Si estas en las islas o haces un paquete multi-dia, coordinamos contigo horarios especificos "
                        "segun tu plan y alojamiento, y veras el detalle en el enlace de reserva."
                    )
            elif choice == 2:
                # Alojamiento en islas y recogida en hotel -> ir al selector de isla
                state.step = Step.ISLAND_MENU
                self.set_quick_replies(state, "island_menu")
                return MESSAGES["island_menu"][lang]
            elif choice == 3:
                # Que incluye / que no incluye el plan
                if state.location == "island":
                    location_line = (
                        "Como ya estas en las islas, las tarifas suelen cubrir principalmente el servicio de buceo/snorkel "
                        "sin transporte desde Cartagena ni almuerzo.\n\n"
                    )
                else:
                    location_line = ""
                response = (
                    f"{location_line}"
                    "En general, los tours incluyen: entrada al Parque Nacional, seguro de buceo, equipo completo, "
                    "transporte en lancha Cartagena-Islas-Cartagena y almuerzo, ademas del aporte eco-social a DIVE TO HEAL.\n\n"
                    "No esta incluido normalmente: transporte terrestre al muelle, fotos/videos submarinos, propinas, "
                    "comidas adicionales al almuerzo y regresos en fecha distinta."
                )
            else:  # choice == 4
                # Que llevar y recomendaciones
                response = (
                    "Te recomendamos llevar: toalla, bloqueador solar, ropa comoda, gorra o sombrero, "
                    "y si te mareas, tu propia medicacion para el mareo.\n\n"
                    "Las salidas dependen de las condiciones de clima y mar; si hay cambios o cancelaciones, "
                    "coordinamos contigo reprogramacion o reembolso segun la politica del plan."
                )
        else:
            if choice == 1:
                if state.location == "cartagena":
                    response = (
                        "For *departures from Cartagena*:\n\n"
                        "- Meeting point: Muelle de la Bodeguita at 8:00 a.m. (gate 3, a few minutes from the old city).\n"
                        "- Usual return time for one-day tours: around 4:00–4:30 p.m.\n\n"
                        "For multi-day packages, the schedule depends on the number of dives and nights on the islands, "
                        "and you'll see the details in each plan link."
                    )
                else:
                    response = (
                        "Trips typically operate as follows:\n\n"
                        "- Meeting point in Cartagena: Muelle de la Bodeguita at 8:00 a.m.\n"
                        "- Usual return time for one-day tours: around 4:00–4:30 p.m.\n\n"
                        "If you are already on the islands or on a multi-day package, we coordinate exact times "
                        "with you depending on your plan and accommodation, and you'll see them in the booking link."
                    )
            elif choice == 2:
                state.step = Step.ISLAND_MENU
                self.set_quick_replies(state, "island_menu")
                return MESSAGES["island_menu"][lang]
            elif choice == 3:
                if state.location == "island":
                    location_line = (
                        "Since you are already on the islands, rates usually cover mainly the diving/snorkel service "
                        "without transport from Cartagena or lunch.\n\n"
                    )
                else:
                    location_line = ""
                response = (
                    f"{location_line}"
                    "In general, tours include: National Park entrance, dive insurance, full equipment, "
                    "boat transfer Cartagena–Islands–Cartagena and lunch, plus the eco-social contribution to DIVE TO HEAL.\n\n"
                    "Not usually included: ground transportation to the dock, underwater photos/videos, tips, "
                    "additional food beyond lunch, and returns on a different date."
                )
            else:  # choice == 4
                response = (
                    "We recommend bringing: towel, sunscreen, comfortable clothes, a hat, and your own "
                    "seasickness medication if needed.\n\n"
                    "Trips depend on weather and sea conditions; if there are changes or cancellations we will "
                    "coordinate rescheduling or refunds according to the plan policy."
                )

        state.step = Step.MAIN_MENU
        self.set_quick_replies(state, "main_menu")
        return response

    def _handle_courses_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 4)
        lang = state.language

        if choice == 1:
            state.selected_service = self._service_for_location("open_water", state)
            state.step = Step.COURSES_OPEN_WATER_ORIGIN
            self.set_quick_replies(state, "courses_open_water_origin")
            if lang == "es":
                return (
                    "Perfecto, vamos a ver tu curso Open Water.\n\n"
                    "Primero, ¿desde donde harias la parte practica?"
                )
            return (
                "Great, let's check your Open Water course.\n\n"
                "First, where would you do the practical part?"
            )
        if choice == 2:
            state.step = Step.COURSES_ADVANCED_MENU
            self.set_quick_replies(state, "courses_advanced_menu")
            if lang == "es":
                return (
                    "Estos son nuestros cursos PADI avanzados y profesionales.\n"
                    "Elige el que mas te interese."
                )
            return (
                "These are our advanced and professional PADI courses.\n"
                "Choose the one you are most interested in."
            )
        if choice == 3:
            state.step = Step.COURSES_ADVANCED_MENU
            self.set_quick_replies(state, "courses_advanced_menu")
            if lang == "es":
                return (
                    "Estas son nuestras especialidades PADI disponibles.\n"
                    "Elige una para ver la informacion del servicio."
                )
            return (
                "These are our available PADI specialties.\n"
                "Choose one to see the service information."
            )
        if choice == 4:
            state.step = Step.ESCALATE
            state.quick_replies = []
            if lang == "es":
                return (
                    "Genial que ya hayas empezado tu curso. Para completar un referral/reactivate en Diving Planet "
                    "necesitamos revisar tu eLearning y formularios PADI, y ver cuantas inmersiones te faltan.\n\n"
                    "Te paso con un asesor para que te indique exactamente que documentos traer y como funciona el precio en tu caso.\n\n"
                    + MESSAGES["escalate"][lang]
                )
            return (
                "Great that you already started your course. To finish a referral/reactivate with Diving Planet we "
                "need to review your eLearning and PADI forms, and see how many dives you still need.\n\n"
                "I will transfer you to a human advisor so they can tell you exactly which documents to bring and how pricing works in your case.\n\n"
                + MESSAGES["escalate"][lang]
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

        state.selected_service = self._service_for_location("open_water", state)
        state.step = Step.COURSES_OPEN_WATER_TIME
        self.set_quick_replies(state, "courses_open_water_time")
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

    def _handle_courses_open_water_time(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 2)
        lang = state.language

        if choice is None:
            self.set_quick_replies(state, "courses_open_water_time")
            return MESSAGES["not_understood"][lang]

        response = self._format_service_detail(state)

        if lang == "es":
            if choice == 1:
                response += (
                    "\n\nGenial, con 2 dias completos podemos organizar bien la practica en islas "
                    "para que completes tu certificacion Open Water."
                )
            else:
                response += (
                    "\n\nSi tienes menos de 2 dias completos, podemos ver alternativas (por ejemplo combinar "
                    "minicurso o buceos guiados) o ajustar el planning."
                )
        else:
            if choice == 1:
                response += (
                    "\n\nGreat, with 2 full days we can comfortably organize the practice in the islands "
                    "so you can complete your Open Water certification."
                )
            else:
                response += (
                    "\n\nIf you have less than 2 full days, we can look at alternatives (for example combining "
                    "a mini course or guided dives) or adjust the plan."
                )

        state.step = Step.COLOMBIAN
        self.set_quick_replies(state, "colombian")
        return response + "\n\n" + MESSAGES["colombian"][lang]

    def _handle_courses_advanced_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 8)
        lang = state.language
        course_map = {
            1: self._service_for_location("advanced", state),
            2: "rescue",
            3: "divemaster",
            4: "mindful_diving",
            5: self._service_for_location("fish_identification_specialty", state),
            6: self._service_for_location("naturalist_specialty", state),
            7: self._service_for_location("buoyancy_specialty", state),
            8: self._service_for_location("nitrox_specialty", state),
        }

        if choice in course_map:
            if course_map[choice] in SPECIALTY_SERVICE_IDS and course_map[choice] not in SERVICES:
                state.step = Step.ESCALATE
                state.quick_replies = []
                return MESSAGES["escalate"][lang]
            state.selected_service = course_map[choice]
            state.step = Step.COLOMBIAN
            self.set_quick_replies(state, "colombian")
            return self._format_service_detail(state) + "\n\n" + MESSAGES["colombian"][lang]

        self.set_quick_replies(state, "courses_advanced_menu")
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
        state.quick_replies = []
        return self._format_summary(state)

    def _format_service_detail(self, state: ConversationState) -> str:
        """Format service details for the selected service."""
        service = SERVICES.get(state.selected_service)
        if not service:
            return ""

        lang = state.language
        name = service[f"name_{lang}"]
        price = service["price"]
        duration = service[f"duration_{lang}"]
        includes = service[f"includes_{lang}"]

        extra = ""
        min_age = service.get("min_age")
        if min_age is not None:
            if lang == "es":
                extra += f"\n👶 *Edad minima recomendada*: {min_age} anos."
            else:
                extra += f"\n👶 *Recommended minimum age*: {min_age} years."

        notes_key = "extra_notes_" + lang
        extra_notes = service.get(notes_key)
        if extra_notes:
            extra += "\nℹ️ " + extra_notes

        if lang == "es":
            return (
                f"*{name}*\n\n"
                f"💰 *Precio*: {price}\n"
                f"⏱ *Duracion*: {duration}\n"
                f"✅ *Incluye*: {includes}"
                f"{extra}"
            )
        else:
            return (
                f"*{name}*\n\n"
                f"💰 *Price*: {price}\n"
                f"⏱ *Duration*: {duration}\n"
                f"✅ *Includes*: {includes}"
                f"{extra}"
            )

    def _format_summary(self, state: ConversationState) -> str:
        """Format final summary with booking link."""
        service = SERVICES.get(state.selected_service)
        if not service:
            return MESSAGES["escalate"][state.language]

        lang = state.language
        name = service[f"name_{lang}"]
        flight_rule = service[f"flight_rule_{lang}"]

        # Choose booking URL based on location
        if state.location == "island" and service.get("booking_url_island"):
            booking_url = service["booking_url_island"]
        else:
            booking_url = service["booking_url"]

        if lang == "es":
            departure = "Cartagena" if state.location == "cartagena" else "Islas del Rosario"
            meeting_note = ""
            if state.location == "cartagena":
                meeting_note = "\n⏰ Punto de encuentro: 8:00 AM en el Muelle de la Bodeguita."
            elif state.location == "island":
                meeting_note = "\n⏰ Recogida en hotel: alrededor de 9:30 AM (si hay acceso marítimo)."

            includes_items = [
                item.strip()
                for item in service["includes_es"].split(",")
                if item.strip()
            ]
            includes_block = "\n".join(f"✅ {item}" for item in includes_items)

            summary = (
                "Perfecto! Aqui tienes el resumen:\n\n"
                f"🤿 Servicio: {service['name_es']}\n"
                f"⏱ Duracion: {service['duration_es']}\n"
                f"✅ Incluye:\n{includes_block}\n\n"
                f"📍 Salida: {departure}"
                f"{meeting_note}\n"
            )

            if state.refresher_interested:
                summary += "\n🧑‍🏫 Refresher: Si (recomendado por inactividad)\n"

            if state.is_colombian:
                summary += (
                    "\n🌎 *Descuento colombiano*: Contactanos por WhatsApp "
                    "al +57 320 2554961 para tu descuento especial.\n"
                )

            if flight_rule:
                summary += f"\n✈️ Importante: {flight_rule}\n"

            extra_notes = service.get("extra_notes_es")
            if extra_notes:
                summary += f"\nℹ️ {extra_notes}\n"

            summary += f"\n👉 Reserva aqui con 10% de descuento:\n{booking_url}\n"
            summary += "\nTienes alguna otra pregunta?"
        else:
            departure = "Cartagena" if state.location == "cartagena" else "Rosario Islands"
            meeting_note = ""
            if state.location == "cartagena":
                meeting_note = "\n⏰ Meeting point: 8:00 AM at Muelle de la Bodeguita."
            elif state.location == "island":
                meeting_note = "\n⏰ Hotel pickup: around 9:30 AM (if there is sea access)."

            includes_items = [
                item.strip()
                for item in service["includes_en"].split(",")
                if item.strip()
            ]
            includes_block = "\n".join(f"✅ {item}" for item in includes_items)

            summary = (
                "Perfect! Here's your summary:\n\n"
                f"🤿 *Service*: {name}\n"
                f"⏱ *Duration*: {service['duration_en']}\n"
                f"✅ *Includes*:\n{includes_block}\n\n"
                f"📍 *Departure*: {departure}"
                f"{meeting_note}\n"
            )

            if state.refresher_interested:
                summary += "\n🧑‍🏫 Refresher: Yes (recommended due to inactivity)\n"

            if state.is_colombian:
                summary += (
                    "\n🌎 *Colombian discount*: Contact us via WhatsApp "
                    "at +57 320 2554961 for your special discount.\n"
                )

            if flight_rule:
                summary += f"\n✈️ *Important*: {flight_rule}\n"

            extra_notes = service.get("extra_notes_en")
            if extra_notes:
                summary += f"\nℹ️ {extra_notes}\n"

            summary += f"\n👉 *Book here with 10% off*:\n{booking_url}\n"
            summary += "\nDo you have any other questions?"

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
