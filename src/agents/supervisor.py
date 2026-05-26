"""
LangGraph Supervisor Agent.

Routes incoming messages to the appropriate handler:
- Decision tree: for structured menu flows (user is navigating options)
- RAG agent: for free-text questions outside the menu flow
- Escalation: when user explicitly asks for a human

The routing logic is deterministic (no LLM call for routing),
keeping costs minimal.
"""

import logging
import re
import unicodedata

from src.agents.escalation import detect_sensitive_escalation
from src.agents.lead_summary import build_lead_summary
from src.flows.decision_tree import DecisionTree, ConversationState, Step
from src.agents.rag_agent import rag_answer
from src.privacy import detect_pii, privacy_block_message

logger = logging.getLogger("uvicorn.error")

decision_tree = DecisionTree()

# Steps where the user is actively navigating the decision tree menu
MENU_STEPS = {
    Step.WELCOME,
    Step.LANGUAGE,
    Step.MAIN_MENU,
    Step.RESERVA_MENU,
    Step.INFO_MENU,
    Step.TOURS_LOCATION,
    Step.GROUP_TYPE,
    Step.TOURS_EXPERIENCE,
    Step.TOURS_CERTIFIED,
    Step.CERTIFIED_LAST_DIVE,
    Step.CERTIFIED_EXPERIENCE,
    Step.REFRESHER_INTEREST,
    Step.TOURS_BEGINNER,
    Step.BEGINNER_AGE,
    Step.COURSES_MENU,
    Step.COURSES_OPEN_WATER_ORIGIN,
    Step.COURSES_OPEN_WATER_TIME,
    Step.COURSES_ADVANCED_MENU,
    Step.COURSES_SPECIALTIES_MENU,
    Step.PRICING_MENU,
    Step.BOOKING_MENU,
    Step.LOGISTICS_MENU,
    Step.ISLAND_MENU,
    Step.ISLAND_HOTEL_MENU,
    Step.SERVICE_DETAIL,
    Step.LOCATION,
    Step.COLOMBIAN,
}

# Keywords that send the user all the way back to the main menu.
MENU_KEYWORDS = {
    "menu", "menú", "inicio", "start", "opciones", "options",
}

# Keywords that take the user one step UP in the decision tree (see BACK_STEP).
BACK_KEYWORDS = {
    "volver", "back", "atras", "atrás", "regresar",
}

# For each step inside the Reservar branch, the (previous_step, quick_reply_key)
# to use when the user clicks "🔙 Volver" or types a back keyword. Steps that
# are not listed fall back to MAIN_MENU.
BACK_STEP: dict[Step, tuple[Step, str]] = {
    Step.RESERVA_MENU: (Step.MAIN_MENU, "main_menu"),
    Step.INFO_MENU: (Step.MAIN_MENU, "main_menu"),
    Step.TOURS_LOCATION: (Step.RESERVA_MENU, "reserva_menu"),
    Step.GROUP_TYPE: (Step.TOURS_LOCATION, "tours_location"),
    Step.TOURS_EXPERIENCE: (Step.GROUP_TYPE, "group_type"),
    Step.TOURS_CERTIFIED: (Step.TOURS_EXPERIENCE, "tours_experience"),
    Step.CERTIFIED_4_DIVES_VARIANT: (Step.TOURS_CERTIFIED, "tours_certified"),
    Step.TOURS_BEGINNER: (Step.TOURS_EXPERIENCE, "tours_experience"),
    Step.BEGINNER_AGE: (Step.TOURS_EXPERIENCE, "tours_experience"),
    Step.COURSES_MENU: (Step.RESERVA_MENU, "reserva_menu"),
    Step.COURSES_OPEN_WATER_ORIGIN: (Step.COURSES_MENU, "courses_menu"),
    Step.COURSES_OPEN_WATER_TIME: (Step.COURSES_OPEN_WATER_ORIGIN, "courses_open_water_origin"),
    Step.COURSES_ADVANCED_MENU: (Step.COURSES_MENU, "courses_menu"),
    Step.COURSES_SPECIALTIES_MENU: (Step.COURSES_MENU, "courses_menu"),
}

# Keywords that indicate escalation to a human
ESCALATION_KEYWORDS = {
    "humano", "human", "agente", "agent", "asesor", "advisor",
    "persona", "person", "hablar con", "speak with", "talk to",
}

LANGUAGE_SELECTION_KEYWORDS = {
    "1", "2", "es", "en", "español", "espanol", "spanish", "english",
}

GREETING_ONLY_KEYWORDS = {
    "hola", "hello", "hi", "buenas", "buenos dias", "buenos días",
    "buenas tardes", "buenas noches", "hey",
}

ENGLISH_HINTS = {
    "we", "are", "family", "certified", "divers", "snorkel", "snorkeling",
    "can", "together", "price", "book", "booking", "discount", "payment",
    "meeting", "point", "open water",
}

SPANISH_HINTS = {
    "somos", "familia", "buzos", "certificados", "bucear", "snorkel",
    "precio", "reservar", "reserva", "descuento", "pago", "juntos",
    "punto de encuentro",
}

# Words that should NOT count as button-title evidence on their own.
MENU_MATCH_STOP_WORDS = {
    "de", "la", "el", "y", "o", "para", "con", "en", "un", "una",
    "los", "las", "del", "al", "que", "es", "se", "lo", "mi", "mis",
    "and", "or", "the", "to", "in", "for", "with", "an", "is",
    "i", "me", "my", "you", "your", "we", "our", "do", "have",
    "quiero", "elijo", "selecciono", "want", "would", "like",
}

# If any of these appear, treat the message as a question (route to RAG, not the menu).
MENU_MATCH_QUESTION_WORDS = {
    "cuánto", "cuanto", "cómo", "como", "qué", "que",
    "dónde", "donde", "cuándo", "cuando", "cuál", "cual",
    "how", "what", "when", "where", "why", "which",
}


def _strip_accents(text: str) -> str:
    """Remove diacritics (á→a, ñ→n, ü→u, …) so text comparison is accent-insensitive."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_for_menu_match(text: str) -> str:
    """Lowercase, drop diacritics, strip punctuation/emoji, collapse whitespace.

    Accent stripping is critical: users frequently type "informacion" instead of
    "información", "espanol" instead of "español", etc., and the matcher must
    treat these as equivalent to the button titles.
    """
    cleaned = _strip_accents(text.strip().lower())
    cleaned = re.sub(r"[¿¡?!.,;:()\[\]\"'/\\]", " ", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def _detect_language_intent(message: str) -> str | None:
    """Detect an explicit language switch request.

    Matches words like "english/ingles", "spanish/espanol/castellano". Accent-insensitive.
    Returns "es", "en", or None when the message contains no language keyword.
    """
    normalized = _strip_accents(message.strip().lower())
    # Word-boundary match so "english" inside another word would not trigger;
    # at the same time tolerate adjacent punctuation.
    if re.search(r"\b(english|ingles)\b", normalized):
        return "en"
    if re.search(r"\b(spanish|espanol|castellano)\b", normalized):
        return "es"
    return None


def _match_quick_reply_text(state: ConversationState, message: str) -> str | None:
    """If user free text clearly maps to a current quick-reply button, return its value.

    Only matches against `state.quick_replies` (the buttons actually displayed now), so a
    text match cannot push the user off the current branch of the decision tree.
    """
    if not state.quick_replies:
        return None

    msg_clean = _normalize_for_menu_match(message)
    if not msg_clean:
        return None

    msg_words = msg_clean.split()
    msg_words_set = set(msg_words)

    # Question-word guard: questions belong to RAG even if they contain a button keyword.
    if msg_words_set & MENU_MATCH_QUESTION_WORDS:
        return None

    sig_msg = {w for w in msg_words_set if len(w) >= 3 and w not in MENU_MATCH_STOP_WORDS}
    if not sig_msg:
        return None

    best_value: str | None = None
    best_score = 0.0

    for reply in state.quick_replies:
        title = reply.get("title", "")
        title_clean = _normalize_for_menu_match(title)
        if not title_clean:
            continue

        if msg_clean == title_clean:
            return reply.get("value")

        title_words = set(title_clean.split())
        sig_title = {w for w in title_words if len(w) >= 3 and w not in MENU_MATCH_STOP_WORDS}
        if not sig_title:
            continue

        common = sig_msg & sig_title
        if not common:
            continue
        score = len(common) / max(len(sig_msg), 1)
        if score > best_score and score >= 0.5:
            best_score = score
            best_value = reply.get("value")

    return best_value


def _go_back_one_step(state: ConversationState) -> str:
    """Move state one step up in the decision tree and return the previous prompt.

    Falls back to MAIN_MENU when the current step has no mapping in BACK_STEP.
    """
    from src.flows.decision_tree import MESSAGES

    dynamic_target = decision_tree.resolve_back_target(state)
    if dynamic_target is not None:
        target_step, qr_key = dynamic_target
        state.summary_mode = None
    else:
        target_step, qr_key = BACK_STEP.get(state.step, (Step.MAIN_MENU, "main_menu"))
    state.step = target_step
    decision_tree.set_quick_replies(state, qr_key)
    return MESSAGES[qr_key][state.language]


def _matches_escalation_keyword(msg_lower: str) -> bool:
    """Word-boundary matching for escalation keywords to avoid false positives.

    Multi-word phrases ("hablar con") use substring matching; single words use
    word boundaries so "persona" does not match inside "personas".
    """
    for kw in ESCALATION_KEYWORDS:
        if " " in kw:
            if kw in msg_lower:
                return True
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", msg_lower):
                return True
    return False


def _is_substantive_free_text(message: str) -> bool:
    normalized = " ".join(message.strip().lower().split())
    normalized_clean = normalized.strip("?!.,;:")
    words = normalized_clean.split()
    if not normalized_clean:
        return False
    if normalized_clean in LANGUAGE_SELECTION_KEYWORDS:
        return False
    if normalized_clean in GREETING_ONLY_KEYWORDS:
        return False
    return len(normalized_clean.split()) >= 4 or "?" in normalized


def _infer_language(message: str, fallback: str = "es") -> str:
    normalized = f" {message.strip().lower()} "
    english_matches = sum(1 for hint in ENGLISH_HINTS if f" {hint} " in normalized)
    spanish_matches = sum(1 for hint in SPANISH_HINTS if f" {hint} " in normalized)
    if english_matches > spanish_matches:
        return "en"
    if spanish_matches > english_matches:
        return "es"
    return fallback


def _build_extra_context(state: ConversationState) -> str | None:
    """Build a compact natural-language summary of the current state to help RAG.

    Se usa como extra_context para que el agente de conocimiento tenga claro:
    - Actividad seleccionada
    - Si el cliente es buzo certificado
    - Si es colombiano
    - Desde donde sale (Cartagena / islas)
    - Isla / hotel reportado
    - Inactividad (>2 años) y si mostro interes en refresher
    """

    parts: list[str] = []

    # Idioma actual de la conversación
    if state.language == "es":
        parts.append("La conversación se esta llevando a cabo en español.")
    elif state.language == "en":
        parts.append("The conversation is currently happening in English.")

    # Ubicacion base
    if state.location == "cartagena":
        parts.append("El cliente indica que saldra desde Cartagena para su experiencia.")
    elif state.location == "island":
        parts.append("El cliente indica que ya esta en las Islas del Rosario.")

    # Isla / hotel
    if getattr(state, "island", None):
        parts.append(f"Se hospeda (o se hospedara) en la isla: {state.island}.")
    if getattr(state, "hotel", None):
        parts.append(f"Hotel/alojamiento reportado: {state.hotel}.")

    # Actividad seleccionada
    if getattr(state, "selected_service", None):
        try:
            from src.flows.decision_tree import SERVICES

            service = SERVICES.get(state.selected_service)
            if service:
                name_es = service.get("name_es", state.selected_service)
                parts.append(f"Actividad seleccionada en el arbol de opciones: {name_es} (id={state.selected_service}).")
        except Exception:
            parts.append(f"Actividad seleccionada en el arbol de opciones con id={state.selected_service}.")

    # Buzo certificado / principiante
    if getattr(state, "is_certified", None) is True:
        parts.append("El cliente marco que es buzo certificado (solo buzos certificados en el grupo).")
    elif getattr(state, "is_certified", None) is False:
        parts.append("El cliente marco que no es buzo certificado o que viene como principiante/snorkel.")

    # Colombiano o no
    if getattr(state, "is_colombian", None) is True:
        parts.append("El cliente indico que es colombiano/a (aplican tarifas locales y descuentos especiales).")
    elif getattr(state, "is_colombian", None) is False:
        parts.append("El cliente indico que no es colombiano/a.")

    # Inactividad y refresher
    if getattr(state, "last_dive_over_2_years", None) is True:
        parts.append("Segun el arbol, lleva mas de 2 años sin bucear.")
    elif getattr(state, "last_dive_over_2_years", None) is False:
        parts.append("Segun el arbol, su ultima inmersión fue hace menos de 2 años.")

    if getattr(state, "refresher_interested", None) is True:
        parts.append("En el flujo marco que SI le interesa incluir un refresher.")
    elif getattr(state, "refresher_interested", None) is False:
        parts.append("En el flujo marco que NO le interesa incluir un refresher.")

    if not parts:
        return None
    return " ".join(parts)


def _answer_state_introspection(state: ConversationState, message: str) -> str | None:
    """Answer simple meta-questions using the current conversation state.

    Esto evita respuestas genéricas de RAG cuando el usuario pregunta por
    cosas que ya sabemos del flujo guiado (actividad elegida, si es buzo
    certificado, si es colombiano, etc.).
    """

    normalized = " ".join(message.strip().lower().split())
    normalized_clean = normalized.strip("?!.,;:")
    words = normalized_clean.split()
    lang = state.language or "es"

    # Por ahora cubrimos solo las preguntas en español e inglés que ya se han visto
    if lang == "es":
        # Preguntas sobre la actividad elegida ("Que actividad hago?", "Que actividad he seleccionado?",
        # "Actividad seleccionada?", etc.). Usamos heuristicas amplias pero intentando no
        # interceptar preguntas generales sobre "actividades" en plural.
        ask_activity_es = False
        # Trabajamos con palabra exacta "actividad" para no confundir con "actividades"
        if "actividad" in words:
            text = normalized_clean

            # Casos directos tipo "actividad seleccionada?" (con o sin una "c")
            if "actividad seleccionad" in text or "actividad selecionad" in text:
                ask_activity_es = True

            # Casos tipo "que actividad ..." / "qué actividad ..." en singular. En este punto ya
            # sabemos que hay la palabra exacta "actividad", asi que asumimos que se refiere a
            # la actividad concreta de esta conversacion y no a una lista generica de actividades.
            if not ask_activity_es and ("que actividad" in text or "qué actividad" in text):
                ask_activity_es = True

            # Casos tipo "cual es la actividad?" / "cual es mi actividad?"
            if not ask_activity_es and ("cual es la actividad" in text or "cuál es la actividad" in text):
                ask_activity_es = True

        if ask_activity_es:
            if state.selected_service:
                try:
                    from src.flows.decision_tree import SERVICES

                    service = SERVICES.get(state.selected_service)
                    if service:
                        name = service.get(f"name_{lang}", state.selected_service)
                        return f"En esta conversación seleccionaste la actividad: {name}."
                except Exception:
                    # Si algo falla al leer SERVICES, caemos en el fallback genérico
                    pass
            return "Todavia no has elegido ninguna actividad concreta en esta conversación."

        # "Soy buzo certificado?"
        if "soy buzo" in normalized_clean and "certificado" in normalized_clean:
            if state.is_certified is True:
                return "En esta conversación marcaste que eres buzo certificado (solo buzos certificados en el grupo)."
            if state.is_certified is False:
                return "En esta conversación marcaste que no eres buzo certificado o que vienes como principiante/snorkel."
            return "Aun no me has dicho si eres buzo certificado o no en esta conversación."

        # "Soy colombiano?" / "Soy colombiana?"
        if "soy " in normalized_clean and "colombian" in normalized_clean:
            if state.is_colombian is True:
                return "En esta conversación me dijiste que eres colombiano/a."
            if state.is_colombian is False:
                return "En esta conversación me dijiste que no eres colombiano/a."
            return "Aun no me has dicho si eres colombiano/a en esta conversación."

        # "De donde soy?" / "De dónde soy?" -> origen aproximado del cliente
        if ("de donde" in normalized_clean or "de dónde" in normalized_clean) and "soy" in normalized_clean:
            idioma_actual = "español" if state.language == "es" else "inglés"
            if state.is_colombian is True:
                return (
                    "En esta conversación me dijiste que eres colombiano/a. "
                    "No tengo mas detalles sobre tu ciudad especifica."
                )
            if state.is_colombian is False:
                return (
                    "En esta conversación no me has dicho exactamente de que pais o ciudad eres. "
                    f"Solo se que marcaste que no eres colombiano/a y que estamos hablando en {idioma_actual}."
                )
            return (
                "Todavia no me has dicho de donde eres en esta conversación. "
                f"Solo se que estamos hablando en {idioma_actual}."
            )

        # "Cual es mi nacionalidad?" / "De que nacionalidad soy?"
        if "nacionalidad" in normalized_clean:
            idioma_actual = "español" if state.language == "es" else "inglés"
            if state.is_colombian is True:
                return (
                    "En esta conversación me dijiste que eres colombiano/a. "
                    "No tengo mas información sobre si tienes otra nacionalidad."
                )
            if state.is_colombian is False:
                return (
                    "En esta conversación marcaste que no eres colombiano/a, "
                    "pero no me has dicho exactamente cuál es tu nacionalidad."
                )
            return (
                "Todavia no me has dicho cuál es tu nacionalidad en esta conversación. "
                f"Solo se que estamos hablando en {idioma_actual}."
            )

        # "Llevo mas de X anos/años sin bucear?" o "Han pasado mas de X anos desde que bucee/hice buceo?"
        ask_last_dive = False
        if "llevo" in normalized_clean and "sin bucear" in normalized_clean:
            ask_last_dive = True
        elif "han pasado" in normalized_clean and (
            "buceo" in normalized_clean
            or "bucee" in normalized_clean
            or "bucear" in normalized_clean
            or "inmersion" in normalized_clean
            or "inmersión" in normalized_clean
        ):
            ask_last_dive = True

        if ask_last_dive:
            if state.last_dive_over_2_years is True:
                return "En esta conversación marcaste que si, que llevas mas de 2 años sin bucear."
            if state.last_dive_over_2_years is False:
                return "En esta conversación marcaste que no, que tu ultima inmersión fue hace menos de 2 años."
            return "Aun no hemos hablado de hace cuanto fue tu ultima inmersión en esta conversación."

        # "Necesito el curso de refresco?" / "Necesito refresher?"
        if ("refres" in normalized_clean or "refresher" in normalized_clean) and (
            "necesito" in normalized_clean
            or "necesitamos" in normalized_clean
            or "tengo que" in normalized_clean
            or "tenemos que" in normalized_clean
        ):
            if state.last_dive_over_2_years is True:
                # Ya marco que lleva mas de 2 anos sin bucear
                if getattr(state, "refresher_interested", None) is True:
                    return (
                        "En esta conversación marcaste que llevas mas de 2 años sin bucear y que SI te interesa "
                        "incluir el refresher. Por seguridad, es muy recomendable hacerlo antes de tus inmersiones."
                    )
                if getattr(state, "refresher_interested", None) is False:
                    return (
                        "En esta conversación marcaste que llevas mas de 2 años sin bucear. Por seguridad, te "
                        "recomendamos hacer un refresher aunque anteriormente dijiste que no te interesaba incluirlo."
                    )
                return (
                    "En esta conversación marcaste que llevas mas de 2 años sin bucear. En esos casos, por seguridad, "
                    "si recomendamos hacer un refresher antes de tus inmersiones."
                )

            if state.last_dive_over_2_years is False:
                if getattr(state, "refresher_interested", None) is True:
                    return (
                        "En esta conversación marcaste que tu ultima inmersión fue hace menos de 2 años, pero que SI "
                        "te interesa hacer un refresher. No es obligatorio en todos los casos, pero puede ser una buena "
                        "idea si sientes que necesitas repasar habilidades."
                    )
                return (
                    "En esta conversación marcaste que tu ultima inmersión fue hace menos de 2 años. En principio "
                    "no es obligatorio hacer un refresher, aunque en algunos casos puede ser recomendable si te sientes "
                    "inseguro o llevas tiempo sin bucear."
                )

            # Si aun no sabemos nada sobre la inactividad, respondemos que falta ese dato
            return (
                "Todavia no me has dicho hace cuanto fue tu ultima inmersión en esta conversación. Si ha pasado "
                "mas de 1–2 años, normalmente recomendamos hacer un refresher por seguridad."
            )

        # "Desde donde salgo?" / "Desde donde salimos?"
        if (
            ("desde donde" in normalized_clean or "desde dónde" in normalized_clean or "de donde" in normalized_clean)
            and ("salgo" in normalized_clean or "salimos" in normalized_clean)
        ):
            if state.location == "cartagena":
                return "En esta conversación marcaste que sales desde Cartagena."
            if state.location == "island":
                return "En esta conversación marcaste que ya estas en las Islas del Rosario."
            return "Aun no me has dicho desde donde sales (si desde Cartagena o si ya estas en las islas) en esta conversación."

    if lang == "en":
        # "What activity did I choose?" / "Which activity have I chosen?"
        if "activity" in normalized_clean and (
            "have i chosen" in normalized_clean
            or "did i choose" in normalized_clean
            or "did i pick" in normalized_clean
            or "am i going to do" in normalized_clean
            or "am i going to be doing" in normalized_clean
            or "am i doing" in normalized_clean
            or "will i do" in normalized_clean
            or "will i be doing" in normalized_clean
        ):
            if state.selected_service:
                try:
                    from src.flows.decision_tree import SERVICES

                    service = SERVICES.get(state.selected_service)
                    if service:
                        name = service.get(f"name_{lang}", state.selected_service)
                        return f"In this conversation you selected the activity: {name}."
                except Exception:
                    pass
            return "You have not selected a specific activity yet in this conversation."

        # "Am I a certified diver?"
        if "certified" in normalized_clean and (
            "am i" in normalized_clean
            or "i am" in normalized_clean
            or "i'm" in normalized_clean
        ) and ("diver" in normalized_clean or "dive" in normalized_clean):
            if state.is_certified is True:
                return "In this conversation you indicated that you are a certified diver (only certified divers in the group)."
            if state.is_certified is False:
                return "In this conversation you indicated that you are not a certified diver or that you are joining as a beginner/snorkeler."
            return "You haven't told me yet in this conversation whether you are a certified diver or not."

        # "Am I Colombian?"
        if "colombian" in normalized_clean and (
            "am i" in normalized_clean
            or "i am" in normalized_clean
            or "i'm" in normalized_clean
        ):
            if state.is_colombian is True:
                return "In this conversation you told me that you are Colombian."
            if state.is_colombian is False:
                return "In this conversation you told me that you are not Colombian."
            return "You haven't told me yet in this conversation whether you are Colombian or not."

        # "Has it been more than X years since my last dive?" / similar
        ask_last_dive_en = False
        if "last dive" in normalized_clean and "since" in normalized_clean:
            ask_last_dive_en = True
        elif "since my last" in normalized_clean and ("dive" in normalized_clean or "time i dived" in normalized_clean):
            ask_last_dive_en = True
        elif "since i last" in normalized_clean and ("dive" in normalized_clean or "dived" in normalized_clean or "went diving" in normalized_clean):
            ask_last_dive_en = True
        elif "since i dived" in normalized_clean or "since i went diving" in normalized_clean:
            ask_last_dive_en = True

        if ask_last_dive_en:
            if state.last_dive_over_2_years is True:
                return "In this conversation you indicated that yes, it has been more than 2 years since your last dive."
            if state.last_dive_over_2_years is False:
                return "In this conversation you indicated that no, your last dive was less than 2 years ago."
            return "We haven't talked yet in this conversation about when your last dive was."

    return None


async def route_message(state: ConversationState, message: str) -> str:
    """
    Supervisor: decides how to handle each incoming message.

    Routing rules (no LLM call):
    1. If user is in a menu step AND sends a number -> decision tree
    2. If user sends a menu/back keyword -> reset to main menu
    3. If user sends an escalation keyword -> escalate
    4. If user is in SUMMARY/ESCALATE/FREE_TEXT step -> RAG agent
    5. If user sends free text while in a menu step -> RAG agent
    """
    msg_lower = message.strip().lower()

    pii_hits = detect_pii(message)
    if pii_hits:
        state.step = Step.ESCALATE
        state.pending_escalation_reason = "datos sensibles detectados"
        logger.warning(f"[SUPERVISOR][PRIVACY] PII detected hits={pii_hits} step={state.step.value}")
        return privacy_block_message(state.language)

    # Check for escalation keywords
    if _matches_escalation_keyword(msg_lower):
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "solicitó asesor"
        state.pending_note = build_lead_summary(state, escalation_reason="solicitó asesor")
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Escalation triggered by keyword")
        return MESSAGES["escalate"][state.language]

    sensitive_escalation = detect_sensitive_escalation(message, state.language)
    if sensitive_escalation:
        reason, response = sensitive_escalation
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.info(f"[SUPERVISOR] Sensitive escalation triggered reason={reason}")
        return response

    # Check for menu reset keywords
    if msg_lower in MENU_KEYWORDS:
        state.step = Step.MAIN_MENU
        decision_tree.set_quick_replies(state, "main_menu")
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Menu reset triggered by keyword")
        return MESSAGES["main_menu"][state.language]

    # Step-back: "🔙 Volver" button (value="back") or back keyword
    if msg_lower == "back" or msg_lower in BACK_KEYWORDS:
        logger.info(f"[SUPERVISOR] Back navigation from step={state.step.value}")
        return _go_back_one_step(state)

    # Greeting at any step (except the very first WELCOME) → restart welcome / language selection.
    # We include LANGUAGE here so that a bare "hola" / "hi" at the language step re-shows the
    # welcome screen instead of auto-selecting Spanish (which felt unexpected to users).
    if msg_lower.strip("?!.,;:") in GREETING_ONLY_KEYWORDS and state.step != Step.WELCOME:
        state.step = Step.WELCOME
        state.quick_replies = []
        response = decision_tree.process_message(state, message)
        logger.info(f"[SUPERVISOR] Greeting restart -> step=WELCOME")
        return response

    # Explicit language-switch request ("in english", "spanish please",
    # "me lo puedes decir en español?", etc.) at any step.
    language_intent = _detect_language_intent(message)
    if language_intent is not None:
        from src.flows.decision_tree import MESSAGES
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            # Treat as language selection; advance to MAIN_MENU.
            state.language = language_intent
            state.step = Step.MAIN_MENU
            decision_tree.set_quick_replies(state, "main_menu")
            logger.info(f"[SUPERVISOR] Language intent at start -> lang={language_intent}")
            return MESSAGES["main_menu"][language_intent]
        if state.language != language_intent:
            # Mid-conversation switch: acknowledge in new language and re-show main menu.
            state.language = language_intent
            state.step = Step.MAIN_MENU
            decision_tree.set_quick_replies(state, "main_menu")
            ack = (
                "¡Listo! Sigamos en español. "
                if language_intent == "es"
                else "Got it! Continuing in English. "
            )
            logger.info(f"[SUPERVISOR] Language switch mid-conversation -> lang={language_intent}")
            return ack + MESSAGES["main_menu"][language_intent]

    # If user is in a menu step
    if state.step in MENU_STEPS:
        # If it looks like a menu choice (number), use decision tree
        if msg_lower.isdigit():
            response = decision_tree.process_message(state, message)
            if state.step == Step.ESCALATE and not state.pending_note:
                state.pending_escalation_reason = "derivado por el árbol de opciones"
                state.pending_note = build_lead_summary(state, escalation_reason="derivado por el árbol de opciones")
            logger.info(f"[SUPERVISOR] Decision tree -> step={state.step.value}")
            return response

        # Free text that clearly matches one of the current quick-reply buttons
        # is treated as if the user clicked that button.
        matched_value = _match_quick_reply_text(state, message)
        if matched_value == "back":
            logger.info(f"[SUPERVISOR] Back via quick-reply text from step={state.step.value}")
            return _go_back_one_step(state)
        if matched_value is not None:
            response = decision_tree.process_message(state, matched_value)
            if state.step == Step.ESCALATE and not state.pending_note:
                state.pending_escalation_reason = "derivado por el árbol de opciones"
                state.pending_note = build_lead_summary(state, escalation_reason="derivado por el árbol de opciones")
            logger.info(f"[SUPERVISOR] Quick-reply text match value={matched_value} -> step={state.step.value}")
            return response

        if state.step in (Step.WELCOME, Step.LANGUAGE) and _is_substantive_free_text(message):
            state.language = _infer_language(message, state.language)
            state.step = Step.FREE_TEXT
            state.quick_replies = []
            logger.info(f"[SUPERVISOR] RAG (early free text) lang={state.language}")
            state.history.append({"role": "user", "content": message})
            extra_context = _build_extra_context(state)
            answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
            state.history.append({"role": "assistant", "content": answer})
            return answer

        # If it's the welcome/language step and not a real question, use decision tree
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            response = decision_tree.process_message(state, message)
            logger.info(f"[SUPERVISOR] Decision tree (early step) -> step={state.step.value}")
            return response

        # Free text while in menu -> use RAG but keep menu state
        logger.info(f"[SUPERVISOR] RAG (free text in menu step={state.step.value})")
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Post-menu steps (SUMMARY, FREE_TEXT) -> summary may still have quick replies (itinerary offer)
    if state.step == Step.SUMMARY:
        matched_value = _match_quick_reply_text(state, message)
        if matched_value == "back":
            logger.info(f"[SUPERVISOR] Back via summary quick-reply from step={state.step.value}")
            return _go_back_one_step(state)
        if matched_value is not None:
            response = decision_tree.process_message(state, matched_value)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Decision tree (summary quick-reply={matched_value}) -> step={state.step.value}")
            return response

        summary_choices = {
            "1",
            "2",
            "si",
            "sí",
            "yes",
            "no",
            "gracias",
            "no gracias",
            "no, gracias",
            "thanks",
            "no thanks",
            "no, thanks",
            "itinerary",
            "skip",
            "ask",
            "done",
            "contact",
        }
        if msg_lower in summary_choices:
            response = decision_tree.process_message(state, message)
            if state.step == Step.ESCALATE and not state.pending_note:
                reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
                state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Decision tree (summary) -> step={state.step.value}")
            return response

        # Preguntas de estado simples ("que actividad he elegido?", "soy buzo certificado?", etc.)
        introspective = _answer_state_introspection(state, message)
        if introspective is not None:
            logger.info("[SUPERVISOR] State introspection answer (summary)")
            return introspective

        # Free text question after the summary -> use RAG
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        state.history.append({"role": "assistant", "content": answer})
        logger.info(f"[SUPERVISOR] RAG (post-summary)")
        return answer

    if state.step == Step.FREE_TEXT:
        # Check if user wants to restart
        if msg_lower in ("1", "si", "sí", "yes"):
            state.quick_replies = []
            if state.language == "es":
                return "Perfecto. ¿Qué te gustaría preguntarme?"
            return "Perfect. What would you like to ask me?"

        if msg_lower in ("2", "no", "gracias", "thanks", "no, gracias", "no, thanks"):
            state.quick_replies = []
            if state.language == "es":
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

        # Preguntas de estado simples ("que actividad he elegido?", "soy buzo certificado?", etc.)
        introspective = _answer_state_introspection(state, message)
        if introspective is not None:
            logger.info("[SUPERVISOR] State introspection answer (free_text)")
            return introspective

        # Free text question
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        state.history.append({"role": "assistant", "content": answer})
        logger.info(f"[SUPERVISOR] RAG (post-menu)")
        return answer

    # Escalate step -> let them ask freely via RAG
    if state.step == Step.ESCALATE:
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        state.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(state)
        answer = await rag_answer(message, lang=state.language, history=state.history, extra_context=extra_context)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Fallback: welcome
    response = decision_tree.process_message(state, message)
    if state.step == Step.ESCALATE and not state.pending_note:
        state.pending_escalation_reason = "derivado por el árbol de opciones"
        state.pending_note = build_lead_summary(state, escalation_reason="derivado por el árbol de opciones")
    return response
