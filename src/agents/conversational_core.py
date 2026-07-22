"""Núcleo conversacional de slot-filling (docs/conversational-refactor-plan.md).

Un único bucle por turno — COMPRENDER → RESOLVER → RESPONDER — sustituye a la
máquina de pasos MIXED_* cuando `settings.conversational_core` está encendido:

1. COMPRENDER: resolver primero la respuesta corta contra el slot pendiente
   (contextual slot carryover: "sí"/"no"/"2"/"cartagena" responden a lo que se
   preguntó), y extraer todo lo demás del mensaje (regex fast-path de
   `intent_detector` + gap-fill LLM de `llm_extractor` — el motor de slots ya
   construido y medido en docs/robustness/). Una PREGUNTA de info va a RAG y
   se vuelve al slot pendiente sin perderlo.
2. RESOLVER: `next_missing_slot(state)` — el ÚNICO dato obligatorio que falta,
   en el orden del plan: actividad → certificación → ubicación (+hotel si
   isla) → [plan auto-recomendado] → seguridad (2 años) → refresher →
   cantidad → edades (si menores) → nacionalidad → resumen.
3. RESPONDER: preguntar solo eso, en lenguaje natural (quick-replies mínimos:
   ubicación, sí/no de seguridad). Completo → resumen determinista + LINKS
   (reusa `_goto_mixed_final_summary`: precios y URLs salen del catálogo,
   nunca del LLM), con gating colombiano (sin link directo → asesor).

El `mixed_cart` sigue siendo el modelo de datos; este módulo solo cambia cómo
se conduce. Todo lo estructurado (precios, links, seguridad, escalado) es
determinista; el LLM interpreta, nunca fija precio/link ni salta el gating.
"""

from __future__ import annotations

import logging
import re

from src.agents.intent_detector import IntentDetector
from src.agents.llm_extractor import fill_gaps, missing_fields
from src.flows.decision_tree import ConversationState, DecisionTree, Step
from src.utils.fuzzy import is_affirmative, is_negative

logger = logging.getLogger("uvicorn.error")

_detector = IntentDetector()
_tree = DecisionTree()

# ─── Slots (orden del plan) ───
SLOT_ACTIVITY = "activity"
SLOT_CERTIFICATION = "certification"
SLOT_LOCATION = "location"
SLOT_HOTEL = "hotel"
SLOT_SAFETY = "safety"            # última inmersión >2 años (solo cert)
SLOT_REFRESHER = "refresher"      # solo si safety == True
SLOT_QTY = "qty"
SLOT_AGES = "ages"                # solo si hay menores mencionados sin edades
SLOT_NATIONALITY = "nationality"  # cerca del checkout (moneda + gating de links)

# Actividades "de producto" que el vertical actual del núcleo sabe cerrar.
# course:* llega en Fase 3; mientras, un curso PADI detectado se atiende pero
# el cierre lo hace el resumen genérico (plan del servicio detectado).
_PRODUCT_ACTIVITIES = {"certified_diving", "minicourse", "snorkel"}

_DIVES_TO_BASE_PLAN = {2: "2_dives_1_day", 3: "3_dives_1_day", 4: "4_dives_2_days",
                       5: "5_dives_2_days", 7: "7_dives_3_days", 9: "9_dives_4_days"}
_DAYS_TO_DIVES = {2: 5, 3: 7, 4: 9}

_CARTAGENA_RE = re.compile(r"\b(cartagena|cartagen\w*|1)\b", re.IGNORECASE)
_ISLAND_RE = re.compile(r"\b(isla\w*|island\w*|bar[uú]|rosario\w*|2)\b", re.IGNORECASE)

# (Fase 3 causa A) Señal singular clara para reservas de CURSO — la inferencia
# singular del detector compartido solo dispara en contexto de buceo/cert y no
# conoce "voy solo". Scoped al núcleo a propósito (opción 2 del handoff): no
# toca intent_detector, que comparte el árbol legacy.
_COURSE_SOLO_RE = re.compile(
    r"\b(?:voy|ir[eé]|vengo|viajo|estoy)\s+sol[oa]\b|\bs[oó]lo\s+yo\b|\byo\s+sol[oa]\b"
    r"|\bpara\s+m[ií]\b|\bjust\s+me\b|\bonly\s+me\b|\bby\s+myself\b|\bon\s+my\s+own\b"
    r"|\b(?:i'?m|i\s+am)\s+alone\b|\bgoing\s+alone\b",
    re.IGNORECASE,
)
# Conservador: cualquier señal de compañía/plural/número gana y se sigue
# preguntando la cantidad (mismo criterio que la inferencia del detector).
_NOT_ALONE_RE = re.compile(
    r"\b(?:somos|estamos|venimos|vamos|seremos|nosotr[oa]s|we\s+are|we're|we\s+want"
    r"|con\s+mi\b|y\s+mi\b|and\s+my\b"
    r"|mi\s+(?:novi[oa]|espos[oa]|pareja|hij[oa]s?|amig[oa]s?|herman[oa]s?|familia)"
    r"|my\s+(?:girlfriend|boyfriend|wife|husband|partner|kids?|son|daughter|friend|family)"
    r"|[2-9]|dos|tres|cuatro|cinco|seis|siete|ocho|nueve"
    r"|two|three|four|five|six|seven|eight|nine)\b",
    re.IGNORECASE,
)


def _effective_activity(state: ConversationState) -> str | None:
    """Producto real a reservar según los slots: un no-certificado que quiere
    bucear va al minicurso (misma convención que el árbol actual)."""
    act = state.detected_activity
    if act is None:
        return None
    if act == "certified_diving" and state.is_certified is False:
        return "minicourse"
    return act


def _cart_will_include_cert(state: ConversationState) -> bool:
    """True si la reserva final llevará buceo certificado — sea la actividad
    principal o un subgrupo del reparto ("3 certificados y 2 snorkel")."""
    alloc = state.detected_group_allocation or {}
    if alloc.get("certified_diving"):
        return True
    return _effective_activity(state) == "certified_diving"


def next_missing_slot(state: ConversationState) -> str | None:
    """El ÚNICO slot obligatorio que falta, o None si la reserva está lista
    para el resumen + links. Lógica pura: no muta el estado."""
    act = state.detected_activity
    if act is None:
        return SLOT_ACTIVITY
    if act == "certified_diving" and state.is_certified is None and not (
        state.detected_group_allocation or {}
    ).get("certified_diving"):
        # Un reparto explícito ("3 certificados y 2 snorkel") ya dice quién está
        # certificado — la pregunta genérica sobraría.
        return SLOT_CERTIFICATION
    if not state.location:
        return SLOT_LOCATION
    if state.location == "island" and not state.hotel:
        return SLOT_HOTEL
    # Plan: no se pregunta — se recomienda el más popular (decisión owner
    # v0.20.27) y el cliente puede cambiarlo por texto en cualquier momento.
    #
    # CANTIDAD antes que SEGURIDAD (decisión owner 2026-07-22, se desvía del
    # orden escrito en conversational-refactor-plan.md): preguntando primero
    # cuántos son, la pregunta de los 2 años ya sabe si dirigirse en singular o
    # en plural en vez de adivinar — en vivo se veía "¿tu última inmersión?" a
    # un grupo cuyo tamaño aún no se había preguntado.
    if not state.detected_group_size and not state.detected_group_allocation:
        return SLOT_QTY
    if _cart_will_include_cert(state):
        if state.last_dive_over_2_years is None:
            return SLOT_SAFETY
        if state.last_dive_over_2_years and state.refresher_interested is None:
            return SLOT_REFRESHER
    if state.kids_mention_detected and not state.detected_ages:
        return SLOT_AGES
    if state.is_colombian is None:
        return SLOT_NATIONALITY
    return None


# ─── Persona: saludo del primer turno (Coral, cálida, sin "asistente"/"bot") ───

def _greeting(state: ConversationState) -> str:
    """Presentación de Coral en el PRIMER turno de la conversación — cálida,
    con el nombre de la empresa y tono cercano colombiano. Nunca se describe
    como asistente/bot/IA (regla de persona, misma que rag_agent). Se antepone
    a la primera respuesta del núcleo (pregunta de slot, RAG o cierre) y no se
    repite en turnos posteriores."""
    if state.language == "es":
        return (
            "¡Hola! 🪸 Soy *Coral*, de *Diving Planet* — buceamos todos los días en "
            "las Islas del Rosario, saliendo desde Cartagena o desde las propias islas. "
            "¡Qué alegría tenerte por acá! Con muchísimo gusto te ayudo a armar tu plan. 🌊\n\n"
        )
    return (
        "Hi! 🪸 I'm *Coral* from *Diving Planet* — we dive every day in the Rosario "
        "Islands, departing from Cartagena or right from the islands. So happy to have "
        "you here! I'd love to help you put your plan together. 🌊\n\n"
    )


# ─── RESPONDER: redactor de slot (determinista, ES/EN, cierre a conversión) ───

def ask_slot(state: ConversationState, slot: str, *, reasking: bool = False) -> str:
    """Pregunta natural por el slot que falta. Un solo mensaje, UNA pregunta,
    quick-replies solo donde el plan lo permite (ubicación / sí-no).

    `reasking=True` cuando el mismo slot se vuelve a preguntar porque el turno
    anterior no lo resolvió (aportó otro dato, o fue una pregunta de info): se
    omiten los preámbulos (p. ej. la recomendación del plan) para no repetir el
    mismo bloque entero — hallazgo del guion Rocío en vivo (2026-07-22)."""
    lang = state.language
    state.core_pending_slot = slot
    state.quick_replies = []

    if slot == SLOT_ACTIVITY:
        return (
            "Cuéntame, ¿qué te gustaría vivir con nosotros? 🤿\n"
            "• *Buceo* en las Islas del Rosario, si ya eres buzo certificado\n"
            "• *Minicurso* para probar el buceo por primera vez (¡no necesitas experiencia!)\n"
            "• *Snorkel* para disfrutar el arrecife desde la superficie, ideal en familia\n"
            "• *Cursos PADI* completos, del Open Water en adelante\n"
            "Dime qué te llama la atención y lo armamos juntos. 🌊"
            if lang == "es" else
            "Tell me, what would you like to experience with us? 🤿\n"
            "• *Diving* in the Rosario Islands, if you're already certified\n"
            "• A beginner *mini-course* to try diving for the first time (no experience needed!)\n"
            "• *Snorkeling* to enjoy the reef from the surface, great for families\n"
            "• Full *PADI courses*, from Open Water up\n"
            "Tell me what catches your eye and we'll put it together. 🌊"
        )
    if slot == SLOT_CERTIFICATION:
        plural = (state.detected_group_size or 1) > 1
        if lang == "es":
            q = "¿Sois buzos certificados?" if plural else "¿Eres buzo certificado?"
            return (f"¡Genial! Para recomendarte el plan perfecto: {q} "
                    "(Y si no, ¡tranquilo! El minicurso es ideal para empezar. 🤿)")
        q = "Are you certified divers?" if plural else "Are you a certified diver?"
        return (f"Great! So I can recommend the perfect plan: {q} "
                "(And if not, no worries — the mini-course is the ideal way to start. 🤿)")
    if slot == SLOT_LOCATION:
        state.quick_replies = (
            [{"title": "🚤 Desde Cartagena", "value": "cartagena"},
             {"title": "🏝️ Ya en las islas", "value": "isla"}]
            if lang == "es" else
            [{"title": "🚤 From Cartagena", "value": "cartagena"},
             {"title": "🏝️ Already on the islands", "value": "island"}]
        )
        return (
            "¿Desde dónde saldrías? Podemos recogerte saliendo *desde Cartagena* "
            "(ida y vuelta el mismo día) o, si ya estás *en las islas*, coordinamos "
            "la recogida en tu hotel."
            if lang == "es" else
            "Where would you be departing from? We can pick you up *from Cartagena* "
            "(round trip, same day) or, if you're already *on the islands*, we arrange "
            "pickup at your hotel."
        )
    if slot == SLOT_HOTEL:
        return (
            "¿En qué hotel o isla te hospedas? Así coordinamos la recogida."
            if lang == "es" else
            "Which hotel or island are you staying at? That way we can arrange pickup."
        )
    if slot == SLOT_SAFETY:
        state.quick_replies = (
            [{"title": "✅ Sí", "value": "si"}, {"title": "❌ No", "value": "no"}]
            if lang == "es" else
            [{"title": "✅ Yes", "value": "yes"}, {"title": "❌ No", "value": "no"}]
        )
        plural = (state.detected_group_size or 1) > 1
        plan_intro = "" if reasking else _recommended_plan_intro(state)
        if lang == "es":
            q = ("¿Ha pasado *más de 2 años* desde la última inmersión de alguno del grupo?"
                 if plural else "¿Han pasado *más de 2 años* desde tu última inmersión?")
        else:
            q = ("Has it been *more than 2 years* since any diver in the group last dived?"
                 if plural else "Has it been *more than 2 years* since your last dive?")
        return f"{plan_intro}{q}"
    if slot == SLOT_REFRESHER:
        state.quick_replies = (
            [{"title": "✅ Sí", "value": "si"}, {"title": "❌ No", "value": "no"}]
            if lang == "es" else
            [{"title": "✅ Yes", "value": "yes"}, {"title": "❌ No", "value": "no"}]
        )
        return (
            "El *refresher* es una sesión corta de repaso en el agua antes de la "
            "inmersión, sin coste adicional. ¿Os interesa?"
            if lang == "es" else
            "The *refresher* is a short in-water review session before the dive, at "
            "no extra cost. Are you interested?"
        )
    if slot == SLOT_QTY:
        return (
            "¿Y para cuántas personas armamos el plan? Así te paso el precio exacto. 😊"
            if lang == "es" else
            "And how many people should I plan for? That way I can give you the exact price. 😊"
        )
    if slot == SLOT_AGES:
        return (
            "Me comentaste que van menores — ¿qué edades tienen? Así les preparo "
            "la actividad adecuada (snorkel, Bubble Makers o minicurso según la edad)."
            if lang == "es" else
            "You mentioned minors are coming — what are their ages? That way I can "
            "set up the right activity (snorkel, Bubble Makers or mini-course by age)."
        )
    if slot == SLOT_NATIONALITY:
        state.quick_replies = (
            [{"title": "🇨🇴 Sí", "value": "si"}, {"title": "🌎 No", "value": "no"}]
            if lang == "es" else
            [{"title": "🇨🇴 Yes", "value": "yes"}, {"title": "🌎 No", "value": "no"}]
        )
        # Singular/plural como en certificación y seguridad — en vivo salía
        # siempre en plural ("¿sois colombianos?") a quien viajaba solo.
        plural = (state.detected_group_size or 1) > 1
        if lang == "es":
            pregunta = (
                "¿sois colombianos o residentes en Colombia?" if plural
                else "¿eres colombiano o residente en Colombia?"
            )
            return (
                f"Última cosa para darte el precio y el link correctos: {pregunta} "
                "(El precio es el mismo — solo cambia la moneda y la forma de pago.)"
            )
        pregunta_en = (
            "are you Colombian or residents of Colombia?" if plural
            else "are you Colombian or a resident of Colombia?"
        )
        return (
            f"One last thing so I can give you the right price and link: {pregunta_en} "
            "(The price is the same — only the currency and payment method change.)"
        )
    raise ValueError(f"unknown slot {slot!r}")


def _recommended_plan_intro(state: ConversationState) -> str:
    """Recomendación del plan (determinista, del catálogo) antepuesta a la
    pregunta de seguridad — mismo criterio que v0.20.27: al certificado que ya
    dijo que quiere bucear no se le manda a un menú, se le recomienda el plan
    más popular y puede cambiarlo por texto."""
    lang = state.language
    plan_id = _resolve_cert_plan(state)
    if plan_id and plan_id != _tree._service_for_location("2_dives_1_day", state):
        return ""  # eligió un plan explícito: no hay que "recomendar" nada
    if lang == "es":
        return ("Te recomiendo nuestro plan más popular: *2 inmersiones en 1 día* en las "
                "Islas del Rosario. (Si prefieres un *paquete multi-día* de 3 o más "
                "inmersiones, dímelo.)\n\n")
    return ("I recommend our most popular plan: *2 dives in 1 day* in the Rosario "
            "Islands. (If you'd rather a *multi-day package* of 3+ dives, just tell "
            "me.)\n\n")


def _resolve_cert_plan(state: ConversationState) -> str | None:
    """Plan de buceo certificado desde los conteos detectados (sin consumirlos),
    o el recomendado por defecto. Determinista, del catálogo."""
    dives = state.detected_cert_dives
    if dives is None and state.detected_cert_days in _DAYS_TO_DIVES:
        dives = _DAYS_TO_DIVES[state.detected_cert_days]
    base = _DIVES_TO_BASE_PLAN.get(dives or 2, "2_dives_1_day")
    return _tree._service_for_location(base, state)


# ─── COMPRENDER ───

def _apply_short_answer(state: ConversationState, message: str) -> bool:
    """Contextual slot carryover: interpreta el mensaje como respuesta al slot
    pendiente. Devuelve True si lo resolvió."""
    slot = state.core_pending_slot
    if not slot:
        return False
    msg = message.strip().lower()

    if slot == SLOT_CERTIFICATION:
        if is_affirmative(msg) or msg == "1":
            state.is_certified = state.detected_is_certified = True
            return True
        if is_negative(msg) or msg == "2":
            state.is_certified = state.detected_is_certified = False
            return True
        return False
    if slot == SLOT_LOCATION:
        # "isla"/"island" primero: "islas del rosario" también matchea números no.
        if _ISLAND_RE.search(msg) and not _CARTAGENA_RE.search(msg.replace("1", "")):
            state.location = state.detected_location = "island"
            return True
        if _CARTAGENA_RE.search(msg):
            state.location = state.detected_location = "cartagena"
            return True
        return False
    if slot == SLOT_HOTEL:
        if len(msg) >= 3 and "?" not in message:
            state.hotel = state.detected_hotel = message.strip()
            if not state.island:
                state.island = message.strip()
            return True
        return False
    if slot == SLOT_SAFETY:
        if is_affirmative(msg) or msg == "1":
            state.last_dive_over_2_years = state.detected_last_dive_over_2_years = True
            return True
        if is_negative(msg) or msg == "2":
            state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
            return True
        return False
    if slot == SLOT_REFRESHER:
        if is_affirmative(msg) or msg == "1":
            state.refresher_interested = True
            return True
        if is_negative(msg) or msg == "2":
            state.refresher_interested = False
            return True
        return False
    if slot == SLOT_QTY:
        n = _tree._parse_mixed_quantity(message)
        if n is not None and n > 0:
            state.detected_group_size = n
            return True
        return False
    if slot == SLOT_AGES:
        ages = [int(a) for a in re.findall(r"\b(\d{1,2})\b", message) if 0 < int(a) < 100]
        if ages:
            state.detected_ages = sorted(set((state.detected_ages or []) + ages))
            return True
        return False
    if slot == SLOT_NATIONALITY:
        if is_affirmative(msg) or msg == "1":
            state.is_colombian = True
            return True
        if is_negative(msg) or msg == "2":
            state.is_colombian = False
            return True
        return False
    return False


_ADDED_PERSON_RE = re.compile(
    r"\b(tambi[eé]n|adem[aá]s|viene|acompa[ñn]a|se\s+(?:suma|apunta)|uno?\s+que|otra?\s+que"
    r"|mi\s+(?:novi[oa]|espos[oa]|marido|mujer|pareja|amig[oa]|herman[oa]|hij[oa]|padre|madre|pap[aá]|mam[aá])"
    r"|my\s+(?:partner|wife|husband|boyfriend|girlfriend|friend|brother|sister|son|daughter|mom|mother|dad|father)"
    r"|also|joining|is\s+coming|comes?\s+along)\b",
    re.IGNORECASE,
)

_ACTIVITY_TO_CART_TYPE = {"certified_diving": "cert", "minicourse": "beginner", "snorkel": "snorkel"}


# Campos que CONDUCEN la reserva en el núcleo (alimentan next_missing_slot o el
# gating de links/moneda). duration/cert_dives/cert_days quedan fuera del
# gap-fill del núcleo a propósito: son afinadores espontáneos que el regex ya
# captura cuando el cliente los dice claro (detect_cert_dive_count etc.) y no
# bloquean ningún slot — pedirlos al LLM en cada turno era parte del gasto que
# el Fix B elimina. (El cutover legacy del supervisor no cambia.)
_DRIVING_FIELDS = {
    "activity", "is_certified", "group_size", "group_allocation",
    "location", "island", "hotel", "ages", "last_dive_over_2_years",
    "is_colombian",
}


def _state_known_fields(state: ConversationState) -> set[str]:
    """Campos extraíbles que la CONVERSACIÓN ya conoce (estado), con la misma
    convención que missing_fields: False es un valor resuelto, None/[] no."""
    candidates = {
        "activity": state.detected_activity,
        "is_certified": state.is_certified if state.is_certified is not None
        else state.detected_is_certified,
        "group_size": state.detected_group_size,
        "group_allocation": state.detected_group_allocation,
        "location": state.location or state.detected_location,
        "island": state.island or state.detected_island,
        "hotel": state.hotel or state.detected_hotel,
        "ages": state.detected_ages,
        "last_dive_over_2_years": state.last_dive_over_2_years
        if state.last_dive_over_2_years is not None
        else state.detected_last_dive_over_2_years,
        "is_colombian": state.is_colombian,
    }
    return {f for f, v in candidates.items() if v not in (None, [], {})}


def _relevant_gaps(state: ConversationState, intent, message: str) -> list[str]:
    """(Fix B del handoff) Huecos que de verdad vale la pena pedirle al LLM:
    los calcula contra el ESTADO (no solo contra el intent del mensaje suelto,
    que casi siempre está vacío) y descarta los campos que no aplican al
    contexto (island/hotel saliendo de Cartagena, edades sin menores
    mencionados, seguridad sin buceo certificado en la reserva, reparto con la
    cantidad ya sabida y sin señal de persona añadida)."""
    known = _state_known_fields(state)
    gaps = [f for f in missing_fields(intent) if f in _DRIVING_FIELDS and f not in known]
    if (state.location or state.detected_location) == "cartagena":
        gaps = [f for f in gaps if f not in ("island", "hotel")]
    if not state.kids_mention_detected:
        gaps = [f for f in gaps if f != "ages"]
    if state.detected_activity and not _cart_will_include_cert(state):
        gaps = [f for f in gaps if f != "last_dive_over_2_years"]
    # El reparto por actividades solo importa si aún no sabemos cuántos son, o
    # si este mensaje añade gente ("viene también uno que...") — que es cuando
    # añadir-vs-cambiar lo consume. Con la cantidad sabida y sin esa señal,
    # pedirlo cada turno era gasto puro (el regex ya saca los repartos claros).
    if state.detected_group_size and not _ADDED_PERSON_RE.search(message):
        gaps = [f for f in gaps if f != "group_allocation"]
    return gaps


async def _understand(state: ConversationState, message: str):
    """Regex fast-path + gap-fill LLM sobre los campos que la CONVERSACIÓN aún
    no conoce (Fix B: nunca se piden campos que el estado ya tiene), y volcado
    al estado por el camino ya probado (_apply_detected_intent). Cualquier
    fallo del LLM degrada a regex-only (fill_gaps devuelve {}).
    Devuelve el intent del TURNO (lo que dijo este mensaje concreto), que el
    caller usa para distinguir "añade actividad" de "cambia de actividad"."""
    from src.agents import supervisor  # lazy: evita import circular

    prev_activity = state.detected_activity
    prev_service_id = state.detected_service_id

    intent = _detector.detect(message, state)
    gaps = _relevant_gaps(state, intent, message)
    if gaps and not _looks_like_question(message):
        patch = await fill_gaps(
            message, intent, history=state.history, lang=state.language, only_fields=gaps
        )
        for field_name, value in patch.items():
            setattr(intent, field_name, value)
            if field_name not in intent.detected_fields:
                intent.detected_fields.append(field_name)
        if patch:
            # (Fix A del handoff) Mismo tag y formato que el cutover legacy —
            # es lo que scripts/harvest_cutover_logs.py parsea para el bucle de
            # datos reales (Fase 6): valores incluidos y mensaje completo vía
            # _log_safe_message (nunca message[:60], bug documentado).
            logger.info(
                f"[EXTRACT][CUTOVER] applied={patch} "
                f"msg={supervisor._log_safe_message(message)!r}"
            )
    supervisor._apply_detected_intent(intent, state)

    # "voy solo" → 1 persona. Nació para cursos PADI (Fase 3 causa A) y el owner
    # decidió extenderlo a CUALQUIER actividad (2026-07-22): la señal explícita
    # de ir solo significa lo mismo en buceo, snorkel o minicurso, y sería raro
    # que el bot lo entendiera en un curso pero no en un buceo. Sigue exigiendo
    # señal singular EXPLÍCITA ("voy solo"/"just me") y ninguna señal de
    # compañía — una auto-presentación en singular sin más ("tengo el open
    # water") NO basta, porque un jefe de grupo escribe igual: ahí se pregunta.
    if (
        not state.detected_group_size
        and not state.detected_group_allocation
        and state.detected_activity
        and _COURSE_SOLO_RE.search(message)
        and not _NOT_ALONE_RE.search(message)
    ):
        state.detected_group_size = 1
        logger.info("[CORE] singular course booking -> group_size=1")

    # AÑADIR vs CAMBIAR: si ya había actividad principal y este turno menciona
    # OTRA junto a una persona añadida ("viene también uno que hace snorkel",
    # "mi novia hace el minicurso"), es un AÑADIDO — la actividad principal no
    # se pisa (se restaura del "latest wins" de _apply_detected_intent) y el
    # subgrupo nuevo se acumula en el reparto. Un cambio de opinión sin persona
    # añadida ("mejor snorkel") sigue siendo cambio (latest wins).
    turn_act = intent.activity
    if (
        prev_activity
        and turn_act
        and turn_act != prev_activity
        and turn_act in _ACTIVITY_TO_CART_TYPE
        and prev_activity in _ACTIVITY_TO_CART_TYPE
        and _ADDED_PERSON_RE.search(message)
    ):
        state.detected_activity = prev_activity
        state.detected_service_id = prev_service_id
        added_qty = (intent.group_allocation or {}).get(turn_act) or 1
        alloc = dict(state.detected_group_allocation or {})
        alloc.setdefault(prev_activity, state.detected_group_size or 1)
        alloc[turn_act] = alloc.get(turn_act, 0) + added_qty
        state.detected_group_allocation = alloc
        state.detected_group_size = sum(alloc.values())
        logger.info(f"[CORE] added activity {turn_act} x{added_qty} -> alloc={alloc}")
    return intent


def _looks_like_question(message: str) -> bool:
    from src.agents import supervisor  # lazy
    return supervisor._looks_like_info_question(message) or "?" in message


# ─── Cierre: carrito desde slots + resumen determinista con links ───

def _cart_item(state: ConversationState, activity: str, qty: int) -> dict:
    """Ítem del carrito para una actividad de producto (plan del catálogo)."""
    if activity == "certified_diving":
        plan = _resolve_cert_plan(state)
        return {"type": "cert", "qty": qty, "plan": plan,
                "label": _tree._cart_label_for("cert", plan, state.language)}
    if activity == "minicourse":
        return {"type": "beginner", "qty": qty, "plan": None,
                "label": _tree._cart_label_for("beginner", None, state.language)}
    if activity == "snorkel":
        return {"type": "snorkel", "qty": qty, "plan": None,
                "label": _tree._cart_label_for("snorkel", None, state.language)}
    # Curso PADI: resolver la variante por ubicación (open_water →
    # open_water_already_on_island si está en las islas). Divemaster es
    # contact-only y _cart_booking_blocks ya lo cierra vía asesor (sin link).
    plan = state.detected_service_id
    if plan:
        plan = _tree._service_for_location(plan, state)
    return {"type": "course", "qty": qty, "plan": plan,
            "label": _tree._cart_label_for("course", plan, state.language)}


def _derive_kids_counts(state: ConversationState) -> None:
    """Traducir edades explícitas a los contadores que el split por edad del
    checkout ya entiende (<8 → snorkel desde los 6; 8-10 → Bubble Makers;
    10+ cuenta normal) — misma regla de negocio que el árbol (eligibility)."""
    ages = state.detected_ages or []
    minors = [a for a in ages if a < 18]
    if not minors:
        return
    state.kids_under_8_count = len([a for a in minors if a < 8])
    state.kids_eight_to_ten_count = len([a for a in minors if 8 <= a <= 10])
    state.detected_ages = ages


def _build_cart_from_slots(state: ConversationState) -> None:
    _derive_kids_counts(state)
    alloc = state.detected_group_allocation or {}
    product_alloc = {k: v for k, v in alloc.items() if k in _ACTIVITY_TO_CART_TYPE and v}
    if product_alloc:
        # Grupo mixto: un ítem por subgrupo ("3 certificados y 2 snorkel").
        # Las claves ya vienen resueltas por el detector (los no certificados
        # ya son minicourse), así que NO se re-aplica _effective_activity.
        state.mixed_cart = [
            _cart_item(state, activity, qty) for activity, qty in product_alloc.items()
        ]
    else:
        qty = state.detected_group_size or 1
        state.mixed_cart = [_cart_item(state, _effective_activity(state), qty)]
    if state.is_colombian:
        state.mixed_display_currency = "COP"
        state.mixed_final_is_colombian = True


def _finalize(state: ConversationState) -> str:
    """Todos los slots listos → resumen por actividad + links (determinista,
    del catálogo), con gating colombiano: colombiano → asesor coordina el pago
    en COP (100% online o 50/50), sin link directo."""
    from src.agents.lead_summary import build_lead_summary

    lang = state.language
    state.core_pending_slot = None
    if not state.mixed_cart:
        _build_cart_from_slots(state)

    refresher_note = ""
    if state.refresher_interested:
        refresher_note = (
            "✅ *Refresher añadido* — el guía hace el repaso en el agua antes de la "
            "inmersión, sin coste adicional.\n\n"
            if lang == "es" else
            "✅ *Refresher added* — the guide runs the in-water review before the "
            "dive, at no extra cost.\n\n"
        )

    if state.is_colombian:
        # Gating colombiano: SIN link de reserva directa — el asesor coordina el
        # pago en COP (100% online o 50/50). Resumen determinista del catálogo.
        state.step = Step.ESCALATE
        state.quick_replies = []
        reason = "núcleo conversacional - cliente colombiano, pago en COP con asesor"
        state.pending_escalation_reason = reason
        summary = _colombian_summary_lines(state)
        state.mixed_last_summary = summary
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        if lang == "es":
            return (
                f"{refresher_note}{summary}\n\n"
                "Como sois colombianos/residentes, el pago es en pesos (COP): puedes "
                "pagar *100% online* o *50% online + 50% en persona*. Te paso con un "
                "asesor para confirmar disponibilidad y coordinar el pago — enseguida "
                "se pone en contacto contigo. 🌊"
            )
        return (
            f"{refresher_note}{summary}\n\n"
            "As Colombian residents you pay in COP: *100% online* or *50% online + "
            "50% in person*. I'll connect you with an advisor to confirm availability "
            "and arrange payment — they'll be in touch shortly. 🌊"
        )

    response = _tree._goto_mixed_final_summary(state)
    return refresher_note + response


def _colombian_summary_lines(state: ConversationState) -> str:
    """Resumen por actividad para clientes colombianos: label + cantidad +
    precio en COP del catálogo, sin URLs de reserva directa."""
    lang = state.language
    lines: list[str] = []
    for b in _tree._cart_booking_blocks(state):
        qty = b["qty"]
        lines.append(f"🤿 *{b['label']}*")
        cop = b.get("cop")
        if cop:
            per = f"{int(round(cop)):,}".replace(",", ".")
            if qty > 1:
                total = f"{int(round(cop)) * qty:,}".replace(",", ".")
                lines.append(f"💰 {qty} × COP {per} p.p. = *COP {total}*")
            else:
                lines.append(f"💰 *COP {per}*" + (" por persona" if lang == "es" else " per person"))
        if b.get("note"):
            lines.append(b["note"])
        lines.append("")
    return "\n".join(lines).strip()


# ─── El bucle por turno ───

async def maybe_handle_turn(state: ConversationState, message: str) -> str | None:
    """Punto de entrada desde el supervisor (tras el gating de seguridad).
    Devuelve None solo para las clases de mensaje que deben seguir cayendo a
    los handlers deterministas legacy (escalado por keyword, menú/volver)."""
    from src.agents import supervisor  # lazy

    msg_lower = message.strip().lower()
    if supervisor._matches_escalation_keyword(msg_lower):
        return None
    if msg_lower in supervisor.MENU_KEYWORDS or msg_lower in supervisor.BACK_KEYWORDS or msg_lower == "back":
        return None

    # Primer mensaje: inferir idioma como hace la entrada legacy, y marcar que
    # toca presentarse (Coral + Diving Planet, tono cercano — regla de persona).
    first_turn = state.step in (Step.WELCOME, Step.LANGUAGE)
    if first_turn:
        from src.flows.decision_tree import _detect_language_from_text
        state.language = (
            _detect_language_from_text(message)
            or supervisor._infer_language(message, state.language)
        )
        state.step = Step.FREE_TEXT
        state.quick_replies = []
    greeting = _greeting(state) if first_turn else ""

    state.history.append({"role": "user", "content": message})

    # COMPRENDER (carryover PRIMERO): si hay un slot pendiente y este mensaje
    # lo RESUELVE, el carryover gana aunque el mensaje "parezca pregunta" por
    # sus palabras — "tienen 7 y 9 años" responde SLOT_AGES aunque "tienen"
    # dispare _looks_like_info_question (Fase 3 causa B; clase general: la
    # respuesta natural de varios slots contiene palabras-pregunta). Un "?"
    # explícito SÍ es siempre una pregunta real y va a RAG (así
    # test_question_mid_flow_answers_and_reasks_pending_slot sigue intacto).
    prev_pending = state.core_pending_slot
    resolved_short = False
    if prev_pending and "?" not in message:
        resolved_short = _apply_short_answer(state, message)

    # PREGUNTA de info → RAG, y se retoma el slot pendiente sin perderlo.
    if not resolved_short and _looks_like_question(message):
        answer = greeting + await _answer_question(state, message)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # COMPRENDER: extracción del resto del mensaje.
    prev_cart_types = {it.get("type") for it in state.mixed_cart}
    if not (resolved_short and len(message.strip()) <= 12):
        await _understand(state, message)

    # Añadido POST-cierre ("viene también uno que hace snorkel" cuando el
    # resumen ya se emitió): añadir el subgrupo nuevo al carrito existente y
    # re-emitir el resumen completo — el buceo original nunca se pierde.
    if prev_cart_types:
        alloc = state.detected_group_allocation or {}
        new_items = [
            _cart_item(state, activity, qty)
            for activity, qty in alloc.items()
            if activity in _ACTIVITY_TO_CART_TYPE and qty
            and _ACTIVITY_TO_CART_TYPE[activity] not in prev_cart_types
        ]
        if new_items:
            state.mixed_cart.extend(new_items)
            logger.info(f"[CORE] post-close additions: {[i['type'] for i in new_items]}")
            response = _tree._goto_mixed_final_summary(state)
            state.core_pending_slot = None
            supervisor._maybe_build_pending_note(state)
            state.history.append({"role": "assistant", "content": response})
            return response

    # RESOLVER + RESPONDER.
    nxt = next_missing_slot(state)
    if nxt is None:
        response = _finalize(state)
        # Materializar la nota de lead (el cierre no-colombiano deja solo
        # pending_lead_note_reason; en el camino legacy la construye
        # _finalize_tree_response — aquí el equivalente).
        supervisor._maybe_build_pending_note(state)
    else:
        response = ask_slot(state, nxt, reasking=(nxt == prev_pending))
        state.step = Step.FREE_TEXT
    response = greeting + response
    state.history.append({"role": "assistant", "content": response})
    return response


async def _answer_question(state: ConversationState, message: str) -> str:
    # Vía supervisor.rag_answer (no rag_agent directamente): es la referencia
    # que mockean los tests y cualquier interceptor futuro — mismo camino que
    # el resto de respuestas de info del bot.
    from src.agents import supervisor  # lazy

    extra_context = supervisor._build_extra_context(state)
    answer = await supervisor.rag_answer(
        message, lang=state.language, history=state.history, extra_context=extra_context
    )
    pending = state.core_pending_slot or next_missing_slot(state)
    if pending is not None:
        follow_up = ask_slot(state, pending)
        return f"{answer}\n\n{follow_up}"
    return answer
