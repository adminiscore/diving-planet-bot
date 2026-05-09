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

from dataclasses import dataclass, field
from enum import Enum


class Step(str, Enum):
    WELCOME = "welcome"
    LANGUAGE = "language"
    MAIN_MENU = "main_menu"
    TOURS_EXPERIENCE = "tours_experience"
    TOURS_CERTIFIED = "tours_certified"
    TOURS_BEGINNER = "tours_beginner"
    COURSES_MENU = "courses_menu"
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
    is_colombian: bool | None = None
    history: list[dict] = None
    quick_replies: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.history is None:
            self.history = []


# --- Service catalog (extracted from divingplanet.org) ---

SERVICES = {
    "2_dives_1_day": {
        "name_es": "Salidas de Buceo - 2 inmersiones (1 dia)",
        "name_en": "Fun Dives - 2 dives (1 day)",
        "requires_cert": True,
        "price": "U$178 (online 10% off) / U$197 normal",
        "duration_es": "1 dia (8:00 AM - 4:15 PM)",
        "duration_en": "1 day (8:00 AM - 4:15 PM)",
        "includes_es": (
            "Entrada Parque Nacional, seguro de buceo, transporte en lancha "
            "Cartagena-Islas-Cartagena, 2 inmersiones guiadas, equipo completo, "
            "almuerzo, aporte eco-social DIVE TO HEAL"
        ),
        "includes_en": (
            "National Park entrance, dive insurance, boat transfer "
            "Cartagena-Islands-Cartagena, 2 guided dives, full equipment, "
            "lunch, eco-social contribution DIVE TO HEAL"
        ),
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es",
        "booking_url_island": "https://book.divingplanet.org/book/fun-dives-already-on-island/19?language=es",
    },
    "minicourse": {
        "name_es": "Minicurso de Buceo (principiantes)",
        "name_en": "Dive Mini Course (beginners)",
        "requires_cert": False,
        "price": "Consultar precios online (10% descuento)",
        "duration_es": "1 dia (8:00 AM - 4:15 PM)",
        "duration_en": "1 day (8:00 AM - 4:15 PM)",
        "includes_es": (
            "Entrada Parque Nacional, seguro de buceo, transporte en lancha, "
            "entrenamiento en piscina + 1 inmersion en mar con instructor PADI, "
            "equipo completo, almuerzo, aporte eco-social DIVE TO HEAL"
        ),
        "includes_en": (
            "National Park entrance, dive insurance, boat transfer, "
            "pool training + 1 ocean dive with PADI instructor, "
            "full equipment, lunch, eco-social contribution DIVE TO HEAL"
        ),
        "flight_rule_es": "Debes esperar al menos 12 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 12 hours before flying.",
        "booking_url": "https://book.divingplanet.org/book/minicurso-de-buceo/2?language=es",
        "booking_url_island": "https://book.divingplanet.org/book/dive-mini-course-already-on-island/20?language=es",
    },
    "snorkeling": {
        "name_es": "Tour de Snorkeling",
        "name_en": "Snorkeling Tour",
        "requires_cert": False,
        "price": "Consultar precios online (10% descuento)",
        "duration_es": "1 dia (8:00 AM - 4:15 PM)",
        "duration_en": "1 day (8:00 AM - 4:15 PM)",
        "includes_es": (
            "Entrada Parque Nacional, transporte en lancha Cartagena-Islas-Cartagena, "
            "2 salidas guiadas de snorkel, equipo completo, almuerzo, "
            "aporte eco-social DIVE TO HEAL"
        ),
        "includes_en": (
            "National Park entrance, boat transfer Cartagena-Islands-Cartagena, "
            "2 guided snorkel sessions, full equipment, lunch, "
            "eco-social contribution DIVE TO HEAL"
        ),
        "flight_rule_es": "",
        "flight_rule_en": "",
        "booking_url": "https://book.divingplanet.org/book/superficio/3?language=es",
        "booking_url_island": "https://book.divingplanet.org/book/snorkeling-already-on-the-island/25?language=es",
    },
    "5_dives_2_days": {
        "name_es": "5 Buceos - 2 dias (1 noche en isla)",
        "name_en": "5 Dives - 2 days (1 night on island)",
        "requires_cert": True,
        "price": "Consultar precios online (10% descuento)",
        "duration_es": "2 dias con 1 noche en Islas del Rosario",
        "duration_en": "2 days with 1 night on Rosario Islands",
        "includes_es": "4 buceos diurnos + 1 buceo nocturno con bioluminiscencia",
        "includes_en": "4 daytime dives + 1 night dive with bioluminescence",
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://divingplanet.org/tours-buceo-snorkel-cartagena/5-buceos-2-dias/",
        "booking_url_island": "",
    },
    "7_dives_3_days": {
        "name_es": "7 Buceos - 3 dias (2 noches en isla)",
        "name_en": "7 Dives - 3 days (2 nights on island)",
        "requires_cert": True,
        "price": "Consultar precios online",
        "duration_es": "3 dias con 2 noches en Islas del Rosario",
        "duration_en": "3 days with 2 nights on Rosario Islands",
        "includes_es": "6 buceos diurnos + 1 buceo nocturno",
        "includes_en": "6 daytime dives + 1 night dive",
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://divingplanet.org/tours-buceo-snorkel-cartagena/7-buceos-3-dias/",
        "booking_url_island": "",
    },
    "9_dives_4_days": {
        "name_es": "9 Buceos - 4 dias (3 noches en isla)",
        "name_en": "9 Dives - 4 days (3 nights on island)",
        "requires_cert": True,
        "price": "Consultar precios online",
        "duration_es": "4 dias con 3 noches en Islas del Rosario",
        "duration_en": "4 days with 3 nights on Rosario Islands",
        "includes_es": "8 buceos diurnos + 1 buceo nocturno",
        "includes_en": "8 daytime dives + 1 night dive",
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://divingplanet.org/tours-buceo-snorkel-cartagena/9-buceos-4-dias/",
        "booking_url_island": "",
    },
    "open_water": {
        "name_es": "Curso Basico PADI (Open Water Diver)",
        "name_en": "PADI Basic Course (Open Water Diver)",
        "requires_cert": False,
        "price": "Consultar precios online",
        "duration_es": "Multi-dia (teoria online + practica en islas)",
        "duration_en": "Multi-day (online theory + island practice)",
        "includes_es": "Teoria online + entrenamiento + inmersiones en Islas del Rosario. Obtienes certificacion Open Water.",
        "includes_en": "Online theory + training + dives in Rosario Islands. You get Open Water certification.",
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://divingplanet.org/curso-padi-cartagena/basico-open-water/",
        "booking_url_island": "",
    },
    "advanced": {
        "name_es": "Curso Avanzado PADI",
        "name_en": "PADI Advanced Course",
        "requires_cert": True,
        "price": "Consultar precios online",
        "duration_es": "Multi-dia",
        "duration_en": "Multi-day",
        "includes_es": "Explora nuevos entornos y perfecciona tus habilidades de buceo.",
        "includes_en": "Explore new environments and hone your diving skills.",
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://divingplanet.org/curso-padi-cartagena/avanzado/",
        "booking_url_island": "",
    },
    "rescue": {
        "name_es": "Curso de Rescate + EFR",
        "name_en": "Rescue Course + EFR",
        "requires_cert": True,
        "price": "Consultar precios online",
        "duration_es": "Multi-dia",
        "duration_en": "Multi-day",
        "includes_es": "Aprende a prevenir y gestionar emergencias de buceo.",
        "includes_en": "Learn to prevent and manage diving emergencies.",
        "flight_rule_es": "Debes esperar al menos 18 horas para tomar un avion.",
        "flight_rule_en": "You must wait at least 18 hours before flying.",
        "booking_url": "https://divingplanet.org/curso-padi-cartagena/rescate-primeros-auxilios/",
        "booking_url_island": "",
    },
    "divemaster": {
        "name_es": "Curso Dive Master PADI",
        "name_en": "PADI Dive Master Course",
        "requires_cert": True,
        "price": "Consultar precios (contactar directamente)",
        "duration_es": "Largo (varias semanas)",
        "duration_en": "Long (several weeks)",
        "includes_es": "Formacion profesional para trabajar como Dive Master.",
        "includes_en": "Professional training to work as a Dive Master.",
        "flight_rule_es": "",
        "flight_rule_en": "",
        "booking_url": "https://divingplanet.org/curso-padi-cartagena/dive-master/",
        "booking_url_island": "",
    },
    "private": {
        "name_es": "Servicio Privado (grupos)",
        "name_en": "Private Service (groups)",
        "requires_cert": False,
        "price": "Cotizacion personalizada",
        "duration_es": "Flexible",
        "duration_en": "Flexible",
        "includes_es": (
            "Lancha privada, instructores personalizados, equipo de buceo, "
            "horarios flexibles. Combina buceo + snorkel + acompanantes."
        ),
        "includes_en": (
            "Private boat, personalized instructors, diving equipment, "
            "flexible schedules. Mix diving + snorkel + companions."
        ),
        "flight_rule_es": "",
        "flight_rule_en": "",
        "booking_url": "https://divingplanet.org/contacto/",
        "booking_url_island": "",
    },
}


# --- Messages templates ---

MESSAGES = {
    "welcome": {
        "es": (
            "Hola! Bienvenido a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 anos de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "Selecciona tu idioma / Select your language:"
        ),
        "en": (
            "Hello! Welcome to *Diving Planet*, Colombia's first "
            "PADI 5 Star Dive Center, with 30 years of experience in "
            "the Rosario Islands, Cartagena.\n\n"
            "Select your language / Selecciona tu idioma:"
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
    "tours_beginner": {
        "es": (
            "Perfecto! No necesitas experiencia previa. Estas son tus opciones:"
        ),
        "en": (
            "Perfect! No prior experience needed. Here are your options:"
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
            "Eres colombiano/a? Tenemos descuentos especiales para locales."
        ),
        "en": (
            "Are you Colombian? We have special discounts for locals."
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
            {"title": "Español", "value": "1"},
            {"title": "English", "value": "2"},
        ],
        "en": [
            {"title": "Español", "value": "1"},
            {"title": "English", "value": "2"},
        ],
    },
    "main_menu": {
        "es": [
            {"title": "🤿 Tours de buceo y snorkel", "value": "1"},
            {"title": "📘 Cursos PADI", "value": "2"},
            {"title": "ℹ️ Informacion general", "value": "3"},
            {"title": "🧑‍💬 Hablar con un asesor", "value": "4"},
        ],
        "en": [
            {"title": "🤿 Diving and snorkel tours", "value": "1"},
            {"title": "📘 PADI courses", "value": "2"},
            {"title": "ℹ️ General information", "value": "3"},
            {"title": "🧑‍💬 Speak with an advisor", "value": "4"},
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
            {"title": "📘 Curso Basico Open Water", "value": "1"},
            {"title": "📘 Curso Avanzado", "value": "2"},
            {"title": "🛟 Rescate + EFR", "value": "3"},
            {"title": "🏅 Dive Master", "value": "4"},
            {"title": "✨ Especialidades PADI", "value": "5"},
        ],
        "en": [
            {"title": "📘 Basic Open Water", "value": "1"},
            {"title": "📘 Advanced Course", "value": "2"},
            {"title": "🛟 Rescue + EFR", "value": "3"},
            {"title": "🏅 Dive Master", "value": "4"},
            {"title": "✨ PADI Specialties", "value": "5"},
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
        state.quick_replies = get_button_options(key, state.language)

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
            Step.TOURS_EXPERIENCE: self._handle_tours_experience,
            Step.TOURS_CERTIFIED: self._handle_tours_certified,
            Step.TOURS_BEGINNER: self._handle_tours_beginner,
            Step.COURSES_MENU: self._handle_courses_menu,
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
        choice = self._parse_choice(message, 4)
        lang = state.language

        if state.history is None:
            state.history = []

        if choice == 1:
            state.step = Step.TOURS_EXPERIENCE
            self.set_quick_replies(state, "tours_experience")
            return MESSAGES["tours_experience"][lang]
        elif choice == 2:
            state.step = Step.COURSES_MENU
            self.set_quick_replies(state, "courses_menu")
            return MESSAGES["courses_menu"][lang]
        elif choice == 3:
            state.step = Step.MAIN_MENU
            self.set_quick_replies(state, "info_general")
            return MESSAGES["info_general"][lang]
        elif choice == 4:
            state.step = Step.ESCALATE
            return MESSAGES["escalate"][lang]
        else:
            self.set_quick_replies(state, "main_menu")
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
            state.step = Step.LOCATION
            self.set_quick_replies(state, "location")
            return self._format_service_detail(state) + "\n\n" + MESSAGES["location"][lang]
        else:
            self.set_quick_replies(state, "tours_certified")
            return MESSAGES["not_understood"][lang]

    def _handle_tours_beginner(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 3)
        lang = state.language
        service_map = {1: "minicourse", 2: "snorkeling", 3: "private"}

        if choice in service_map:
            state.selected_service = service_map[choice]
            if state.selected_service == "private":
                state.step = Step.ESCALATE
                state.quick_replies = []
                return self._format_service_detail(state) + "\n\n" + MESSAGES["escalate"][lang]
            state.step = Step.LOCATION
            self.set_quick_replies(state, "location")
            return self._format_service_detail(state) + "\n\n" + MESSAGES["location"][lang]
        else:
            self.set_quick_replies(state, "tours_beginner")
            return MESSAGES["not_understood"][lang]

    def _handle_courses_menu(self, state: ConversationState, message: str) -> str:
        choice = self._parse_choice(message, 5)
        lang = state.language
        course_map = {
            1: "open_water",
            2: "advanced",
            3: "rescue",
            4: "divemaster",
            5: None,  # Specialties -> escalate
        }

        if choice in course_map:
            if course_map[choice] is None:
                state.step = Step.ESCALATE
                state.quick_replies = []
                return MESSAGES["escalate"][lang]
            state.selected_service = course_map[choice]
            state.step = Step.COLOMBIAN
            self.set_quick_replies(state, "colombian")
            return self._format_service_detail(state) + "\n\n" + MESSAGES["colombian"][lang]
        else:
            self.set_quick_replies(state, "courses_menu")
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

        if lang == "es":
            return (
                f"*{name}*\n\n"
                f"💰 *Precio*: {price}\n"
                f"⏱ *Duracion*: {duration}\n"
                f"✅ *Incluye*: {includes}"
            )
        else:
            return (
                f"*{name}*\n\n"
                f"💰 *Price*: {price}\n"
                f"⏱ *Duration*: {duration}\n"
                f"✅ *Includes*: {includes}"
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
            summary = f"Perfecto! Aqui tienes el resumen:\n\n"
            summary += f"🤿 *Servicio*: {name}\n"
            summary += f"📍 *Salida*: {'Cartagena' if state.location == 'cartagena' else 'Islas del Rosario'}\n"

            if state.is_colombian:
                summary += (
                    "\n🇨🇴 *Descuento colombiano*: Contactanos por WhatsApp "
                    "al +57 320 2554961 para tu descuento especial.\n"
                )

            if flight_rule:
                summary += f"\n✈️ *Importante*: {flight_rule}\n"

            summary += f"\n👉 *Reserva aqui con 10% de descuento*:\n{booking_url}\n"
            summary += "\nTienes alguna otra pregunta?"
        else:
            summary = f"Perfect! Here's your summary:\n\n"
            summary += f"🤿 *Service*: {name}\n"
            summary += f"📍 *Departure*: {'Cartagena' if state.location == 'cartagena' else 'Rosario Islands'}\n"

            if state.is_colombian:
                summary += (
                    "\n🇨🇴 *Colombian discount*: Contact us via WhatsApp "
                    "at +57 320 2554961 for your special discount.\n"
                )

            if flight_rule:
                summary += f"\n✈️ *Important*: {flight_rule}\n"

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
