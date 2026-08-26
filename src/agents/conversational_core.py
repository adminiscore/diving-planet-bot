"""Núcleo conversacional de slot-filling (docs/archive/conversational-refactor-plan.md).

Un único bucle por turno — COMPRENDER → RESOLVER → RESPONDER — es el único camino
de enrutado de texto libre desde Fase 4 (sustituyó a la máquina de pasos MIXED_*,
ya retirada):

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
from collections import Counter

from src.agents.intent_detector import AGE_WORDS, IntentDetector
from src.agents.llm_extractor import (
    compose_acknowledgement,
    detect_special_signals,
    fill_gaps,
    missing_fields,
    resolve_slot_answer,
)
from src.flows import cart_render
from src.flows.decision_tree import ConversationState, Step
from src.utils.fuzzy import is_affirmative, is_negative

logger = logging.getLogger("uvicorn.error")

_detector = IntentDetector()

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
SLOT_COMPANION_QTY = "companion_qty"  # cuántos acompañantes cuando el plural es vago
# Auditoría 2026-07-23: un acompañante mencionado solo por un atributo (p. ej.
# "no está certificado") sin actividad ni intención declarada no permite
# adivinar snorkel/minicurso — se pregunta primero QUÉ quiere hacer, antes de
# poder preguntar la cantidad (SLOT_COMPANION_QTY).
SLOT_COMPANION_ACTIVITY = "companion_activity_choice"

# Slots booleanos/escalares que el resolutor LLM anti-bucle (Fase C) sabe
# resolver cuando el parser canónico (is_affirmative/is_negative/número) falla
# ante una respuesta válida pero no-canónica. Los nombres coinciden con las
# claves de `_SLOT_RESOLVER_SPEC` en llm_extractor.py.
_LLM_RESOLVABLE_SLOTS = frozenset({
    SLOT_CERTIFICATION, SLOT_SAFETY, SLOT_REFRESHER, SLOT_QTY, SLOT_NATIONALITY,
    SLOT_LOCATION,
})
# SLOT_COMPANION_QTY y SLOT_COMPANION_ACTIVITY NO van aquí: `next_missing_slot`
# no los rastrea, así que con la reserva principal ya resuelta `advanced` es
# espuriamente True y el bloque genérico Fase C (gate `not advanced`) los
# saltaría. Tienen bloques dedicados en maybe_handle_turn (gate `not
# resolved_short`).

# Actividades "de producto" que el vertical actual del núcleo sabe cerrar.
# course:* llega en Fase 3; mientras, un curso PADI detectado se atiende pero
# el cierre lo hace el resumen genérico (plan del servicio detectado).
_PRODUCT_ACTIVITIES = {"certified_diving", "minicourse", "snorkel"}

_DIVES_TO_BASE_PLAN = {2: "2_dives_1_day", 3: "3_dives_1_day", 4: "4_dives_2_days",
                       5: "5_dives_2_days", 7: "7_dives_3_days", 9: "9_dives_4_days"}
_DAYS_TO_DIVES = {2: 5, 3: 7, 4: 9}

_CARTAGENA_RE = re.compile(r"\b(cartagena|cartagen\w*)\b", re.IGNORECASE)
_ISLAND_RE = re.compile(r"\b(isla\w*|island\w*|bar[uú]|rosario\w*)\b", re.IGNORECASE)

# Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 4): una petición
# EXPLÍCITA de cambiar de idioma a mitad de conversación ("actually can we
# continue in english") se ignoraba por completo — no había ningún mecanismo
# que la detectara (la reclasificación por-mensaje del intent_detector solo
# corre en el PRIMER turno, antes de que `detected_language` quede fijado;
# después, nada vuelve a mirar el idioma). Lista deliberadamente pequeña y
# determinista (no LLM) — son peticiones explícitas, no ambiguas, no hace
# falta red de precisión para esto.
_SWITCH_TO_EN_RE = re.compile(
    r"\b(?:can\s+we|could\s+we|let'?s|switch\s+to|in\s+)?\s*"
    r"(?:continue|talk|speak|chat)?\s*in\s+english\b|"
    r"\bswitch\s+to\s+english\b|\bspeak\s+english\b|\ben\s+ingl[ée]s\b|"
    r"\bhabl(?:ar|amos|emos)\s+en\s+ingl[ée]s\b",
    re.IGNORECASE,
)
_SWITCH_TO_ES_RE = re.compile(
    r"\b(?:podemos|puedes|seguimos|continuamos)?\s*"
    r"(?:hablar|seguir|continuar)?\s*en\s+español\b|"
    r"\bcambia(?:r|mos)?\s+a\s+español\b|\bhabl(?:ar|amos|emos)\s+en\s+español\b|"
    r"\bswitch\s+to\s+spanish\b|\bin\s+spanish\b|\bspeak\s+spanish\b",
    re.IGNORECASE,
)
# Respuesta de DUDA al preguntar el hotel (no un nombre real de hotel). Fase C.
_HOTEL_UNKNOWN_RE = re.compile(
    r"\b(no\s+s[eé]|ni\s+idea|no\s+lo\s+s[eé]|a[uú]n\s+no|todav[ií]a\s+no|"
    r"sin\s+definir|no\s+estoy\s+segur\w*|no\s+tengo|"
    r"not\s+sure|no\s+idea|dunno|don'?t\s+know|not\s+yet|undecided|tbd)\b",
    re.IGNORECASE,
)
# Deferral en el paso de UBICACIÓN: "no sé / da igual / recomiéndame / tú
# decides" — el cliente delega la elección. En vez de re-preguntar en bucle
# (regex de ubicación fallaba), se recomienda Cartagena (la salida más común,
# como el árbol legacy). "No estoy seguro" se deja FUERA a propósito: eso lo
# interpreta el resolutor LLM (puede ser Cartagena o abstenerse).
_LOCATION_DEFER_RE = re.compile(
    r"\bno\s+s[eé]\b|\bda\s+igual\b|\bme\s+da\s+igual\b|\bcualquiera\b|\bt[uú]\s+decides?\b"
    r"|\bel\s+que\s+(?:sea|quieras|recomiendes|prefieras|digas)\b"
    r"|\blo\s+que\s+(?:sea|recomiendes|prefieras|digas|quieras)\b"
    r"|\brecomi[eé]nd\w*\b|\bqu[eé]\s+(?:me\s+)?recomiendas\b"
    r"|\bwhatever\b|\byou\s+(?:decide|recommend|choose)\b|\bup\s+to\s+you\b|\beither\b"
    r"|\bi\s+don'?t\s+know\b|\bno\s+idea\b",
    re.IGNORECASE,
)

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

# Captura del nombre del cliente DEL PROPIO MENSAJE ("hola soy Rocío", "me llamo
# Ana"). Camino rápido determinista; el LLM de comprensión (Parte 1 del plan)
# puede rellenarlo también. Conservador a propósito: tras "soy" siguen muchos
# atributos que NO son nombres ("soy certificado", "soy colombiano", "soy buzo"),
# así que se filtran con una stoplist. El nombre de WhatsApp (sender['name']) queda
# diferido hasta que el canal exista. Se captura en minúscula (móvil) y se
# Title-Casea. Primera captura gana (el nombre no cambia a mitad de conversación).
_NAME_TRIGGER_RE = re.compile(
    r"\b(?:me\s+llamo|mi\s+nombre\s+es|my\s+name\s+is|soy)\s+([a-záéíóúñ]{2,20})\b",
    re.IGNORECASE,
)
_NAME_STOPWORDS = frozenset({
    "certificado", "certificada", "certificados", "certificadas", "buzo", "buza",
    "buzos", "buceador", "buceadora", "colombiano", "colombiana", "colombianos",
    "extranjero", "extranjera", "principiante", "instructor", "instructora",
    "turista", "estudiante", "nuevo", "nueva", "mayor", "menor", "de", "un", "una",
    "open", "advanced", "rescue", "divemaster", "nitrox", "padi", "el", "la",
    "certified", "diver", "tourist", "beginner", "colombian", "resident", "solo",
    "sola", "el", "la", "yo",
    # Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 8): "soy del
    # equipo de pruebas..." capturaba "del" (contracción de "de"+"el", no
    # cubierta por el "de" ya excluido) como si fuera un nombre propio ->
    # saludo "¡Hola, Del!". Añadidas otras palabras funcionales cortas del
    # mismo riesgo que podrían seguir a "soy" sin ser un nombre.
    "del", "al", "los", "las", "muy", "así", "asi", "bien", "aquí", "aqui", "ya", "que",
})


def _capture_client_name(state: ConversationState, message: str) -> None:
    if state.client_name:
        return
    m = _NAME_TRIGGER_RE.search(message)
    if not m:
        return
    word = m.group(1)
    if word.lower() in _NAME_STOPWORDS:
        return
    state.client_name = word[:1].upper() + word[1:].lower()
    logger.info(f"[CORE] captured client name -> {state.client_name}")


def _greeting(state: ConversationState) -> str:
    """Presentación de Coral en el PRIMER turno de la conversación — cálida,
    con el nombre de la empresa y tono cercano colombiano. Nunca se describe
    como asistente/bot/IA (regla de persona, misma que rag_agent). Se antepone
    a la primera respuesta del núcleo (pregunta de slot, RAG o cierre) y no se
    repite en turnos posteriores."""
    name = state.client_name
    if state.language == "es":
        saludo = f"¡Hola, {name}! 🪸" if name else "¡Hola! 🪸"
        return (
            f"{saludo} Soy *Coral*, de *Diving Planet* — buceamos todos los días en "
            "las Islas del Rosario, saliendo desde Cartagena o desde las propias islas. "
            "¡Qué alegría tenerte por acá! Con muchísimo gusto te ayudo a armar tu plan. 🌊\n\n"
        )
    saludo = f"Hi, {name}! 🪸" if name else "Hi! 🪸"
    return (
        f"{saludo} I'm *Coral* from *Diving Planet* — we dive every day in the Rosario "
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
        # `reasking=True`: se re-ancla la actividad tras una respuesta de info
        # (RAG). Repetir el bloque entero de 4 bullets que ya se mostró al
        # abrir es ruido — una línea que reofrece las opciones basta (fallo en
        # vivo 2026-07-24: el menú completo se pegaba tras cada recomendación).
        if reasking:
            return (
                "¿Con cuál te animas — *buceo*, *minicurso*, *snorkel* o un *curso PADI*? 🌊"
                if lang == "es" else
                "Which one are you leaning toward — *diving*, a *mini-course*, "
                "*snorkeling* or a *PADI course*? 🌊"
            )
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
    if slot == SLOT_COMPANION_QTY:
        act = state.pending_companion_activity
        label = (_RECALL_LABELS_ES if lang == "es" else _RECALL_LABELS_EN).get(act, act or "")
        return (
            f"¿Cuántos serían para {label}? Así les cuento el plan exacto. 😊"
            if lang == "es" else
            f"How many people would that be for {label}? That way I can give you the exact plan. 😊"
        )
    if slot == SLOT_COMPANION_ACTIVITY:
        return (
            "¿Qué le gustaría hacer a tu acompañante — probar el buceo con el "
            "*minicurso*, o prefiere *snorkel*?"
            if lang == "es" else
            "What would your companion like to do — try diving with the "
            "*mini-course*, or would they rather go *snorkeling*?"
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
            return f"Última cosa para darte el precio y el link correctos: {pregunta}"
        pregunta_en = (
            "are you Colombian or residents of Colombia?" if plural
            else "are you Colombian or a resident of Colombia?"
        )
        return f"One last thing so I can give you the right price and link: {pregunta_en}"
    raise ValueError(f"unknown slot {slot!r}")


def _recommended_plan_intro(state: ConversationState) -> str:
    """Recomendación del plan (determinista, del catálogo) antepuesta a la
    pregunta de seguridad — mismo criterio que v0.20.27: al certificado que ya
    dijo que quiere bucear no se le manda a un menú, se le recomienda el plan
    más popular y puede cambiarlo por texto."""
    lang = state.language
    plan_id = _resolve_cert_plan(state)
    if plan_id and plan_id != cart_render.service_for_location("2_dives_1_day", state):
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
    return cart_render.service_for_location(base, state)


def _word_ages(message: str) -> list[int]:
    """Edades escritas en palabra, en orden de aparición ("cinco y siete" ->
    [5, 7]). Vacío si no hay ninguna. Reusa el mapa canónico `AGE_WORDS` de
    intent_detector (mismo vocabulario que el gate de elegibilidad)."""
    return [AGE_WORDS[t] for t in re.findall(r"[a-záéíóúñ]+", message.lower())
            if t in AGE_WORDS]


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
        # Auditoría 2026-08-26 (batería sintética contra PRE): `_ISLAND_RE`/
        # `_CARTAGENA_RE` tenían "2"/"1" como alternativas del regex —
        # matchean CUALQUIER mensaje que contenga ese dígito en cualquier
        # parte ("somos 2" respondiendo a la pregunta de CANTIDAD, no de
        # ubicación, resolvía la ubicación a "island" sin que nadie lo
        # dijera, y "cartagena" dicho DESPUÉS se malinterpretaba como
        # nombre de hotel). Bug reproducido 4/4 veces en la batería. El
        # atajo "1"/"2" (mismo patrón que is_certified/nationality/safety)
        # solo tiene sentido si es la respuesta COMPLETA, no una cifra
        # suelta dentro de otra frase — de ahí la igualdad exacta en vez de
        # una alternativa dentro del regex de substring.
        if msg == "2" or (_ISLAND_RE.search(msg) and not _CARTAGENA_RE.search(msg)):
            state.location = state.detected_location = "island"
            return True
        if msg == "1" or _CARTAGENA_RE.search(msg):
            state.location = state.detected_location = "cartagena"
            return True
        # Deferral ("no sé/da igual/recomiéndame") → Cartagena (salida más
        # común). Sin esto, el regex fallaba y se re-preguntaba en bucle.
        if _LOCATION_DEFER_RE.search(msg):
            state.location = state.detected_location = "cartagena"
            return True
        return False
    if slot == SLOT_HOTEL:
        # Guarda de mis-parse (Fase C, 2026-07-23): el hotel acepta texto libre
        # (cualquier nombre ≥3 chars), pero una DUDA/negativa ("no sé todavía",
        # "aún no lo sé", "not sure yet") se guardaba TAL CUAL como nombre del
        # hotel. En vez de eso, se guarda un marcador claro y se avanza (el
        # hotel/recogida lo coordina el asesor); así el lead refleja "sin
        # definir" en vez de una frase de duda como si fuera un hotel real, y
        # el flujo no se queda pidiendo hotel para siempre.
        if _HOTEL_UNKNOWN_RE.search(msg):
            marker = "por confirmar" if state.language == "es" else "to be confirmed"
            state.hotel = state.detected_hotel = marker
            if not state.island:
                state.island = marker
            return True
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
        n = cart_render.parse_quantity(message)
        if n is not None and n > 0:
            state.detected_group_size = n
            return True
        return False
    if slot == SLOT_COMPANION_QTY:
        act = state.pending_companion_activity
        # Auditoría 2026-07-23 (matriz EN de multi-ítem): si la respuesta a
        # "¿cuántos para snorkel?" menciona OTRA actividad producto distinta
        # a la preguntada ("we are 3 for diving" respondiendo a la pregunta
        # de snorkel), el número no es una respuesta válida para ESTA
        # pregunta — aplicarlo a ciegas mezclaría el "3" de buceo con
        # snorkel (bug en vivo: acabó facturando snorkel:3 cuando el cliente
        # decía 3 para BUCEO). Si el mensaje menciona un producto que NO es
        # el preguntado (y no menciona el preguntado), no se resuelve aquí —
        # se abstiene para que el mensaje se re-entienda desde cero.
        mentioned = _mentioned_product_activities(message)
        if mentioned and act not in mentioned:
            return False
        n = cart_render.parse_quantity(message)
        if n is not None and n > 0 and act:
            _merge_companion_activity(state, act, n)
            state.pending_companion_activity = None
            return True
        return False
    if slot == SLOT_COMPANION_ACTIVITY:
        # Respuesta a "¿qué le gustaría hacer a tu acompañante?" — solo
        # snorkel/minicurso son opciones válidas aquí (ya se sabe que no
        # está certificado; certified_diving no tendría sentido en sí
        # mismo). "quiere bucear"/"wants to dive" se traduce a minicurso
        # (regla de negocio, mismo criterio que `_activity_has_textual_
        # backing`). Si la respuesta no deja claro UNA sola opción, se
        # abstiene (nunca se adivina cuál).
        mentioned = set(_mentioned_product_activities(message))
        candidates = set()
        if "snorkel" in mentioned:
            candidates.add("snorkel")
        if "minicourse" in mentioned or "certified_diving" in mentioned:
            candidates.add("minicourse")
        if len(candidates) == 1:
            state.pending_companion_activity = next(iter(candidates))
            state.needs_companion_activity = False
            return True
        return False
    if slot == SLOT_AGES:
        ages = [int(a) for a in re.findall(r"\b(\d{1,2})\b", message) if 0 < int(a) < 100]
        if not ages:  # sin dígitos, probar edades en palabra ("cinco y siete")
            ages = _word_ages(message)
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


def _apply_resolved_slot_value(state: ConversationState, slot: str, value) -> bool:
    """Aplica al estado el valor que el resolutor LLM anti-bucle (Fase C)
    interpretó para un slot booleano/escalar cuyo parser canónico falló.
    Devuelve True si se aplicó algo utilizable. Mismos campos que
    `_apply_short_answer`, sin duplicar su lógica de parseo (aquí el valor ya
    viene tipado del LLM)."""
    if slot == SLOT_CERTIFICATION and isinstance(value, bool):
        state.is_certified = state.detected_is_certified = value
        return True
    if slot == SLOT_SAFETY and isinstance(value, bool):
        state.last_dive_over_2_years = state.detected_last_dive_over_2_years = value
        return True
    if slot == SLOT_REFRESHER and isinstance(value, bool):
        state.refresher_interested = value
        return True
    if slot == SLOT_NATIONALITY and isinstance(value, bool):
        state.is_colombian = value
        return True
    if slot == SLOT_QTY and isinstance(value, int) and value > 0:
        state.detected_group_size = value
        return True
    if slot == SLOT_LOCATION and value in ("cartagena", "island"):
        state.location = state.detected_location = value
        return True
    if slot == SLOT_COMPANION_ACTIVITY and value in ("snorkel", "minicourse"):
        state.pending_companion_activity = value
        state.needs_companion_activity = False
        return True
    return False


_ADDED_PERSON_RE = re.compile(
    r"\b(tambi[eé]n|adem[aá]s|viene|acompa[ñn]a|se\s+(?:suma|apunta)|uno?\s+que|otra?\s+que"
    r"|mi\s+(?:novi[oa]|espos[oa]|marido|mujer|pareja|amig[oa]|herman[oa]|hij[oa]|padre|madre|pap[aá]|mam[aá])"
    r"|my\s+(?:partner|wife|husband|boyfriend|girlfriend|friend|brother|sister|son|daughter|mom|mother|dad|father)"
    r"|also|joining|is\s+coming|comes?\s+along)\b",
    re.IGNORECASE,
)

# Señal LÉXICA amplia de que el mensaje menciona OTRA PERSONA (no el hablante).
# Es el discriminador entre AÑADIR un acompañante y un CAMBIO de opinión: el LLM
# decide la ACTIVIDAD, pero solo se trata como añadido si el mensaje nombra a una
# persona. Robusto ante el flip-flop del LLM con historial: "mejor snorkel" (sin
# persona) NUNCA añade; "hay un amigo que quiere snorkel" / "2 y uno hace snorkel"
# (con persona) sí. Más amplio que `_ADDED_PERSON_RE` (que exigía "mi amigo"/"un
# que" y perdía "hay un amigo que…").
_MENTIONS_PERSON_RE = re.compile(
    r"\b(amig[oa]s?|prim[oa]s?|parej\w*|novi[oa]s?|espos[oa]s?|marido|mujer|"
    r"herman[oa]s?|hij[oa]s?|padre|madre|pap[aá]s?|mam[aá]s?|suegr[oa]s?|cu[ñn]ad[oa]s?|"
    r"sobrin[oa]s?|niet[oa]s?|abuel[oa]s?|familia\w*|acompa[ñn]antes?|"
    r"vien[ea]n?|se\s+(?:suma|apunta|une)n?|otra?\s+persona|"
    # Auditoría 2026-07-23 (matriz EN de multi-ítem): la lista en inglés no
    # tenía plurales ("friend" sin "s?") mientras que TODA la lista en
    # español sí ("amig[oa]s?") — "my friends do snorkel" no disparaba
    # NINGÚN mecanismo de acompañante (ni el nuevo chequeo de mención
    # perdida, ni el `companion_ambiguous` original, ni el fast-path), un
    # hueco real de idioma, no solo del fix de hoy. Añadido "s?"/"es?" a cada
    # sustantivo en inglés, más "others"/"folks"/"people" (equivalentes de
    # "otra?\s+persona").
    r"friends?|partners?|wife|wives|husbands?|brothers?|sisters?|sons?|"
    r"daughters?|moms?|dads?|mothers?|fathers?|others?|folks?|people|"
    r"someone|is\s+coming|are\s+coming|joins?)\b"
    r"|\b(?:y|,|adem[aá]s|tambi[ée]n|más|mas|and)\s+(?:un[oa]?|otr[oa]|another|one)\b",
    re.IGNORECASE,
)


def _mentions_person(message: str) -> bool:
    return bool(_MENTIONS_PERSON_RE.search(message))


# Compañero SINGULAR e inequívoco (un/una/mi/a + sustantivo en singular, o "a
# friend"/"someone"): el número de personas es 1 sin ambigüedad, se puede
# asumir con seguridad sin preguntar. Deliberadamente NO matchea plurales
# ("mis amigos", "unos amigos", "friends") ni un número explícito (ese lo
# extrae el LLM en `companion_qty`) — para esos dos casos hay que preguntar
# cuántos son en vez de adivinar (hallazgo en vivo 2026-07-22: "mis amigos"
# se inventaba un total sin preguntar). Ver SLOT_COMPANION_QTY.
_SINGULAR_COMPANION_RE = re.compile(
    r"\b(?:un|una|mi|a)\s+(?:amig[oa]|novi[oa]|espos[oa]|marido|mujer|pareja|"
    r"compa[ñn]er[oa]|acompa[ñn]ante|herman[oa]|hij[oa]|padre|madre|pap[aá]|mam[aá]|"
    r"prim[oa]|friend|partner|wife|husband|boyfriend|girlfriend|brother|sister|"
    r"son|daughter|companion)\b|\bsomeone\b"
    # "uno/una que..." / "one who/that..." — pronombre numeral, no un
    # sustantivo de relación: "viene también uno que hace snorkel" es
    # exactamente 1 persona, mismo patrón que ya usa _ADDED_PERSON_RE.
    r"|\bun[oa]?\s+que\b|\bone\s+(?:who|that)\b",
    re.IGNORECASE,
)

# Respaldo determinista para la asimetría señalada en la auditoría de Fase B
# (2026-07-23): `companion_qty` se descarta si el mensaje no trae un número
# real (`_EXPLICIT_NUMBER_RE`), pero `companion_is_singular` no tenía ninguna
# segunda verificación — si el LLM dice singular=True para un plural con
# jerga rarísima, nada lo contradice. Sustantivo de compañero en PLURAL
# inequívoco (termina en "s": "amigos", "parceros", "friends"...) — si
# aparece, no se confía en `companion_is_singular=True` del LLM aunque lo
# devuelva, y se pasa a preguntar cuántos son en vez de asumir 1.
_PLURAL_COMPANION_RE = re.compile(
    r"\b(?:amig[oa]s|novi[oa]s|espos[oa]s|parejas|compa[ñn]er[oa]s|acompa[ñn]antes|"
    r"herman[oa]s|hij[oa]s|prim[oa]s|padres|mam[aá]s|pap[aá]s|"
    r"parceros?|parceras?|cuates|panas|carnales|compas|patas|causas|"
    r"friends|buddies|companions|partners)\b",
    re.IGNORECASE,
)

# Respaldo determinista: verificado en vivo (2026-07-22) que el LLM NO siempre
# obedece la instrucción de abstenerse en `companion_qty` para un plural vago
# — "también vienen mis amigos a hacer snorkel" devolvió companion_qty=1 pese
# al prompt reforzado. No basta confiar en que el modelo se abstenga: si el
# mensaje no contiene NINGÚN número explícito (dígito o palabra-número), se
# descarta cualquier companion_qty que el LLM haya devuelto igualmente, antes
# de decidir si preguntar o asumir 1 por singular inequívoco.
_EXPLICIT_NUMBER_RE = re.compile(
    r"\d+|\b(?:uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
    r"one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)

_WORD_TO_NUM = {
    "uno": 1, "una": 1, "one": 1, "dos": 2, "two": 2, "tres": 3, "three": 3,
    "cuatro": 4, "four": 4, "cinco": 5, "five": 5, "seis": 6, "six": 6,
    "siete": 7, "seven": 7, "ocho": 8, "eight": 8, "nueve": 9, "nine": 9,
    "diez": 10, "ten": 10,
}


def _message_numbers(message: str) -> Counter:
    """MULTIconjunto (Counter, no set) de números que aparecen de verdad en el
    mensaje. Auditoría 2026-07-23 (multi-ítem, `other_companions`): probado en
    vivo con matriz de 9 casos x 4 repeticiones que el LLM NO se abstiene de
    forma fiable ante un plural vago ni con el prompt reforzado — sigue
    inventando una cantidad para "mis amigos". Verificación determinista pura:
    si la cantidad que dice el LLM para un sub-grupo no tiene un número real
    detrás en el texto, no es de fiar. Debe ser Counter (con consumo, una
    ocurrencia por sub-grupo validado) y no un set de presencia: con un set,
    "2 bucean, mis amigos hacen snorkel" validaba por error un snorkel=2
    inventado solo porque el "2" de "2 bucean" YA aparecía en el texto —
    aunque ese "2" ya estaba gastado por el sub-grupo principal."""
    counts = Counter()
    for m in _EXPLICIT_NUMBER_RE.finditer(message):
        tok = m.group(0).lower()
        counts[int(tok) if tok.isdigit() else _WORD_TO_NUM[tok]] += 1
    return counts


def _consume_number(counts: Counter, n) -> bool:
    """True y descuenta una ocurrencia si `n` sigue disponible en `counts`."""
    if n is not None and counts.get(n, 0) > 0:
        counts[n] -= 1
        return True
    return False


_ACTIVITY_TO_CART_TYPE = {"certified_diving": "cert", "minicourse": "beginner", "snorkel": "snorkel"}

# Auditoría multi-ítem 2026-07-23 (segundo hallazgo, más profundo que el
# primero): cuando el LLM se ABSTIENE correctamente ante un plural vago (no
# incluye la actividad en group_allocation/other_companions en absoluto, tal
# y como se le pide), esa actividad puede desaparecer SIN QUE NADA LO NOTE —
# "tres bucean, mis amigos hacen snorkel, y dos hacen el minicurso" hizo que
# el propio fill_gaps omitiera "snorkel" del todo (comportamiento correcto
# del modelo), y sin este chequeo la mención se perdía en silencio, sin
# preguntar. Deliberadamente laxo (palabra clave, no clasificación fina): un
# falso positivo aquí cuesta una pregunta de más, nunca una reserva
# equivocada — mismo principio de "mejor preguntar" de todo este bloque.
# Sinónimos de negocio alineados con `intent_detector` (2026-07-24): el
# minicurso se vende como "bautizo"/"bautismo"/"discover scuba"/"try dive", y el
# snorkel como "careteo"/"caretear" (regional caribeño). Sin ellos, la
# deliberación y las redes multi-ítem del núcleo no reconocían estas palabras
# (el intent_detector sí las conocía — era un hueco solo del núcleo).
_PRODUCT_MENTION_RE = {
    "certified_diving": re.compile(r"\bbuce\w*|\bvuce\w*|\bbuse[ao]\w*|\bdive\b|\bdiving\b|\bscuba\b", re.IGNORECASE),
    "minicourse": re.compile(
        r"\bmini[\s-]?curso\b|\bmini[\s-]?course\b|\bbauti[sz]\w*\b"
        r"|\bdiscover\s*scuba\b|\btry\s+(?:dive|diving|scuba)\b",
        re.IGNORECASE),
    "snorkel": re.compile(r"\be?snork\w*|\be?snorqu\w*|\bcarete[ao]\w*\b", re.IGNORECASE),
}


def _mentioned_product_activities(message: str) -> list:
    """Lista (no set) para que el orden en que se pregunta por cada
    sub-grupo sea determinista (el orden de un `set` de strings depende del
    hash aleatorizado por proceso, no es reproducible entre corridas)."""
    return [act for act, pat in _PRODUCT_MENTION_RE.items() if pat.search(message)]


# Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 3): "mi amigo...
# él es certificado también" respalda `certified_diving` igual que "quiere
# bucear" — declarar la certificación del acompañante ES la intención (nadie
# dice "ya soy certificado" para pedir un minicurso). Sin este respaldo, el
# guard determinista descartaba una señal del LLM que SÍ era correcta
# (medido 3/3, `detect_special_signals` devolvía `certified_diving` bien),
# preguntando "¿minicurso o snorkel?" a un acompañante YA certificado —
# ninguna de las dos opciones tiene sentido en ese caso. Negado explícito
# ("no está certificado") NO cuenta como respaldo — ese es el caso genuino
# de `SLOT_COMPANION_ACTIVITY` que el hallazgo original (Grupo 3 §D) sí
# necesita preguntar.
_CERTIFICATION_CLAIM_RE = re.compile(r"certificad[oa]s?|certified", re.IGNORECASE)
_CERTIFICATION_NEGATED_RE = re.compile(
    r"no\s+(?:es[ts]\w*\s+)?certificad[oa]s?|not\s+certified|isn['’]?t\s+certified|"
    r"no\s+certified",
    re.IGNORECASE,
)


def _activity_has_textual_backing(activity: str, message: str) -> bool:
    """¿Tiene `activity` algún respaldo real en el texto? No basta con
    buscar la palabra exacta: la regla de negocio traduce "no certificado +
    quiere bucear" -> minicurso, así que un mensaje que dice "buceo" sin
    decir "minicurso" SÍ respalda `minicourse` (auditoría 2026-07-23). Lo
    que NO respalda nada es un mensaje que solo da un ATRIBUTO del
    acompañante ("mi amigo no está certificado") sin mencionar ninguna
    actividad ni intención — ahí `_mentioned_product_activities` devuelve
    vacío y esta función correctamente dice False para cualquier `activity`."""
    mentioned = set(_mentioned_product_activities(message))
    if activity in mentioned:
        return True
    if activity == "minicourse" and "certified_diving" in mentioned:
        return True
    if (
        activity == "certified_diving"
        and _CERTIFICATION_CLAIM_RE.search(message)
        and not _CERTIFICATION_NEGATED_RE.search(message)
    ):
        return True
    return False


# B2 (2026-07-24): deliberación entre actividades. El cliente que SOPESA dos
# opciones sin decidirse ("mi pareja duda entre buceo y minicurso", "no sé si
# snorkel o el minicurso") no está reservando ambas — quiere que le expliquen.
# Antes solo se salvaba si el mensaje traía "?"; sin él, la extracción tomaba
# las dos actividades como selección. Backstop determinista de frases de duda,
# que se combina con la señal LLM `comparing_options` (respaldo bidireccional:
# el patrón cubre lo obvio aunque el LLM falle; el LLM cubre el fraseo que el
# patrón no enumera).
_DELIBERATION_RE = re.compile(
    r"\bno\s+s[eé]\s+(?:si|cu[aá]l|qu[eé]|entre)\b"
    r"|\bno\s+estoy\s+segur\w+\s+(?:de\s+)?si\b"
    r"|\bno\s+me\s+decido\b"
    r"|\bdud\w+\s+(?:entre|si)\b"
    r"|\b(?:saber|decid\w+)\s+(?:si|cu[aá]l|qu[eé]|entre)\b"
    r"|\bmejor\s+\w.+\bo\b"
    r"|\bqu[eé]\s+diferencia\b|\bdiferencia\s+entre\b"
    r"|\bcu[aá]l\s+(?:me\s+)?(?:conviene|recomiend\w+|elijo|escojo|es\s+mejor)\b"
    r"|\bqu[eé]\s+me\s+recomiendas\s+entre\b"
    r"|\bnot\s+sure\s+(?:if|whether)\b|\btorn\s+between\b|\bdecid\w+\s+between\b"
    r"|\bwhat'?s\s+the\s+difference\b|\bdifference\s+between\b"
    r"|\bshould\s+i\s+.+\bor\b"
    r"|\bwhich\s+(?:one\s+)?(?:is\s+better|do\s+you\s+recommend|should\s+i)\b",
    re.IGNORECASE,
)
# Selección/compromiso claro con la(s) actividad(es): anula el camino que
# depende SOLO de la señal LLM (por si sobre-dispara comparing en un "quiero A
# y B"). NO anula el patrón de duda determinista. "quiero SABER/CONOCER" es una
# PREGUNTA, no un compromiso — se excluye con lookahead para que "quiero saber
# si buceo o snorkel" cuente como duda y vaya a RAG.
_COMMITMENT_RE = re.compile(
    r"\b(?:quiero|queremos|quisiera)(?!\s+(?:saber|conocer))\b"
    r"|\b(?:reserv\w+|me\s+quedo\s+con|nos\s+quedamos\s+con|elijo|elegimos"
    r"|book|i'?ll\s+take|we'?ll\s+take)\b",
    re.IGNORECASE,
)


def _looks_like_deliberation(message: str) -> bool:
    return bool(_DELIBERATION_RE.search(message))


# Cursos PADI por NOMBRE como opciones distintas de deliberación (gap
# 2026-07-24): `_mentioned_product_activities` no distingue cursos (todos serían
# "padi_course"), así que "no sé si open water o advanced" (sin "?") no
# disparaba el ancla de 2+ opciones. Cada nombre de curso cuenta como una opción
# propia. Conservador: solo nombres inequívocos de curso, no la palabra "curso"
# suelta (evita casar dentro de "minicurso").
_COURSE_MENTION_RE = {
    "open_water": re.compile(r"\bopen\s*water\b|\bowd\b", re.IGNORECASE),
    "advanced": re.compile(r"\badvanced\b|\baowd\b|\bavanzad\w*\b", re.IGNORECASE),
    "rescue": re.compile(r"\brescue\b|\brescate\b", re.IGNORECASE),
    "divemaster": re.compile(r"\bdive\s*master\b|\bdivemaster\b", re.IGNORECASE),
    "nitrox": re.compile(r"\bnitrox\b|\benriched\s+air\b", re.IGNORECASE),
}

_DELIB_LABELS_ES = {"certified_diving": "buceo certificado", "minicourse": "minicurso de buceo",
                    "snorkel": "snorkel", "padi_course": "curso PADI",
                    "open_water": "curso Open Water", "advanced": "curso Advanced Open Water",
                    "rescue": "curso Rescue Diver", "divemaster": "curso Divemaster",
                    "nitrox": "especialidad Nitrox"}
_DELIB_LABELS_EN = {"certified_diving": "certified diving", "minicourse": "beginner mini-course",
                    "snorkel": "snorkeling", "padi_course": "PADI course",
                    "open_water": "Open Water course", "advanced": "Advanced Open Water course",
                    "rescue": "Rescue Diver course", "divemaster": "Divemaster course",
                    "nitrox": "Nitrox specialty"}


def _mentioned_courses(message: str) -> list:
    return [c for c, pat in _COURSE_MENTION_RE.items() if pat.search(message)]


def _mentioned_offerings(message: str) -> list:
    """Ofertas distintas mencionadas: actividades de producto + cursos PADI por
    nombre. Base del ancla de deliberación (2+ ofertas distintas). Dedup
    conservando el orden (determinista)."""
    seen: list[str] = []
    for o in _mentioned_product_activities(message) + _mentioned_courses(message):
        if o not in seen:
            seen.append(o)
    return seen


def _comparison_query(offerings: list[str], lang: str) -> str:
    """Query EXPLÍCITA de comparación para RAG a partir de las ofertas que se
    sopesan (actividades o cursos). El mensaje crudo de deliberación ("mi pareja
    duda entre buceo y minicurso") es una query pobre — recupera mal y el juez
    de grounding la rechaza (hallazgo en vivo 2026-07-24); una pregunta clara de
    diferencia recupera igual de bien que cuando el cliente la formula con "?"."""
    labels = _DELIB_LABELS_ES if lang == "es" else _DELIB_LABELS_EN
    names = [labels.get(o, o) for o in offerings] or ([labels["snorkel"]])
    joined = (" y ".join(names) if lang == "es" else " and ".join(names))
    return (f"¿Qué diferencia hay entre {joined}? ¿Cuál me recomiendas?"
            if lang == "es" else
            f"What's the difference between {joined}? Which one do you recommend?")


# Composer determinista de comparación (2026-07-24): cuando RAG no tiene en el
# KB un chunk que compare ESE par (medido en vivo: "buceo vs snorkel" cae al
# fallback de asesor 4/4, consistente — no flaky), se arma la comparación desde
# el catálogo SERVICES. Los HECHOS (precio, certificación, nombre) salen del
# catálogo — nunca se inventan; solo el descriptor de tono es copy curado, igual
# que el menú de actividades. Nunca cae al asesor.
_OFFERING_TO_SERVICE = {
    "certified_diving": "2_dives_1_day", "minicourse": "minicourse",
    "snorkel": "snorkeling", "padi_course": "open_water",
    "open_water": "open_water", "advanced": "advanced", "rescue": "rescue",
    "divemaster": "divemaster", "nitrox": "nitrox_specialty",
}
_OFFERING_BLURB_ES = {
    "certified_diving": "Inmersiones guiadas para buzos ya certificados; explorás el arrecife a profundidad.",
    "minicourse": "Tu primera vez bajo el agua con instructor: entrenamiento en piscina y una inmersión real. Sin experiencia previa.",
    "snorkel": "Disfrutas el arrecife desde la superficie, con máscara y aletas. Ideal en familia.",
    "padi_course": "Curso de certificación inicial: te habilita a bucear de forma autónoma hasta 18 m.",
    "open_water": "Curso de certificación inicial: te habilita a bucear de forma autónoma hasta 18 m.",
    "advanced": "Para buzos ya certificados que quieren profundizar y sumar especialidades.",
    "rescue": "Curso enfocado en seguridad y rescate; el paso previo a Divemaster.",
    "divemaster": "El primer nivel profesional PADI.",
    "nitrox": "Especialidad de aire enriquecido para inmersiones más largas.",
}
_OFFERING_BLURB_EN = {
    "certified_diving": "Guided dives for already-certified divers; explore the reef at depth.",
    "minicourse": "Your first time underwater with an instructor: pool training and a real dive. No experience needed.",
    "snorkel": "Enjoy the reef from the surface, with mask and fins. Great for families.",
    "padi_course": "Entry certification course: qualifies you to dive independently down to 18 m.",
    "open_water": "Entry certification course: qualifies you to dive independently down to 18 m.",
    "advanced": "For already-certified divers who want to go deeper and add specialties.",
    "rescue": "Safety- and rescue-focused course; the step before Divemaster.",
    "divemaster": "The first professional PADI level.",
    "nitrox": "Enriched-air specialty for longer dives.",
}


def _compose_comparison(offerings: list[str], lang: str) -> str:
    """Comparación lado-a-lado desde el catálogo, sin depender de RAG. Precio y
    requisito de certificación salen de SERVICES (nunca inventados)."""
    from src.flows.decision_tree import SERVICES
    blurbs = _OFFERING_BLURB_ES if lang == "es" else _OFFERING_BLURB_EN
    labels = _DELIB_LABELS_ES if lang == "es" else _DELIB_LABELS_EN
    rows = []
    for o in offerings:
        svc = SERVICES.get(_OFFERING_TO_SERVICE.get(o, ""), {})
        name = (svc.get("name_es") if lang == "es" else svc.get("name_en")) or labels.get(o, o)
        if lang == "es":
            cert_line = "Requiere certificación previa" if svc.get("requires_cert") else "Sin certificación previa"
        else:
            cert_line = "Requires prior certification" if svc.get("requires_cert") else "No certification needed"
        row = f"🤿 *{name}*\n• {cert_line}\n• {blurbs.get(o, '')}"
        price = svc.get("price_usd")
        if price:
            row += (f"\n• Desde U${int(round(price))} por persona"
                    if lang == "es" else f"\n• From U${int(round(price))} per person")
        rows.append(row)
    if lang == "es":
        return ("¡Con gusto te explico la diferencia! 🌊\n\n" + "\n\n".join(rows)
                + "\n\n¿Con cuál te animas? Y lo armamos juntos. 🐠")
    return ("Happy to explain the difference! 🌊\n\n" + "\n\n".join(rows)
            + "\n\nWhich one are you leaning toward? Let's put it together. 🐠")


def _is_deliberation_between_options(message: str, routing_signals: dict) -> bool:
    """True si el mensaje sopesa 2+ ofertas (actividades o cursos) sin decidirse
    — va a RAG en vez de a extracción. Ancla determinista fuerte: exige 2+
    OFERTAS distintas nombradas en el texto (una sola nunca es deliberación, es
    selección/pregunta), y entonces confía en el patrón de duda o en la señal
    LLM `comparing_options`. El respaldo por texto (2+ ofertas) hace que un
    falso positivo del LLM no pueda suprimir una selección real de una sola
    actividad."""
    if len(_mentioned_offerings(message)) < 2:
        return False
    if _looks_like_deliberation(message):
        return True
    obj = routing_signals.get("comparing_options")
    llm_comparing = bool(obj.get("comparing")) if isinstance(obj, dict) else False
    return llm_comparing and not _COMMITMENT_RE.search(message)


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


async def _understand(state: ConversationState, message: str) -> tuple:
    """Regex fast-path + gap-fill LLM sobre los campos que la CONVERSACIÓN aún
    no conoce (Fix B: nunca se piden campos que el estado ya tiene), y volcado
    al estado por el camino ya probado (_apply_detected_intent). Cualquier
    fallo del LLM degrada a regex-only (fill_gaps devuelve {}).
    Devuelve (intent, companion_merged_fastpath): el intent del TURNO (lo que
    dijo este mensaje concreto, que el caller usa para distinguir "añade
    actividad" de "cambia de actividad"), y un booleano que indica si el
    fast-path regex de acompañante (más abajo) ya fusionó un acompañante en
    este turno. Sin ese booleano, `advanced` (en maybe_handle_turn) no se
    entera de que este fast-path avanzó la reserva cuando el siguiente slot
    pendiente no cambia (p. ej. seguía faltando "nacionalidad" con o sin el
    acompañante) — y la red de precisión LLM vuelve a ejecutarse para el
    MISMO mensaje y duplica la cantidad (hallazgo en vivo 2026-07-22: "viene
    también uno que hace snorkel" con LLM real daba snorkel:2, no snorkel:1)."""
    from src.agents import supervisor  # lazy: evita import circular

    prev_activity = state.detected_activity
    prev_service_id = state.detected_service_id
    prev_is_certified = state.is_certified
    prev_last_dive = state.last_dive_over_2_years
    prev_refresher = state.refresher_interested

    intent = _detector.detect(message, state)
    gaps = _relevant_gaps(state, intent, message)
    if gaps and not _looks_like_question(message):
        patch = await fill_gaps(
            message, intent, history=state.history, lang=state.language, only_fields=gaps
        )
        # Verificado en vivo (2026-07-23): con el historial REAL de la
        # conversación por delante, fill_gaps puede alucinar un
        # group_allocation/group_size completo para un mensaje de "se añade
        # un acompañante" sin ningún número real ("también vienen mis parces
        # a hacer snorkel" con 5 turnos previos devolvió {cert:1, snorkel:3}
        # o {cert:1, snorkel:6} según la corrida — nada respaldado por el
        # texto). `_apply_detected_intent` (más abajo) aplica estos campos
        # SIN verificación alguna, antes de que el fast-path o la red de
        # precisión LLM (que sí tienen el respaldo `_EXPLICIT_NUMBER_RE`)
        # puedan intervenir.
        #
        # Ampliado (auditoría multi-ítem 2026-07-23): la guarda original solo
        # se activaba si `_ADDED_PERSON_RE` (lista cerrada: "mi amigo", nunca
        # "mis amigos" plural) coincidía con el mensaje ENTERO, y entonces
        # tiraba TODO group_allocation. "2 bucean, mis amigos hacen snorkel, y
        # uno hace el minicurso" no matchea esa lista (posesivo plural), así
        # que el guard viejo no se disparaba y snorkel colaba una cantidad
        # inventada sin más. Ahora se valida CADA actividad del reparto por
        # separado contra `_message_numbers` (¿su cantidad tiene un número
        # real en el texto?) — se descarta solo la entrada sin respaldo, no
        # el reparto entero, para no perder las que sí son correctas.
        alloc_patch = patch.get("group_allocation")
        if isinstance(alloc_patch, dict) and alloc_patch:
            # Auditoría 2026-07-23 (segunda pasada, más allá de la cantidad):
            # una actividad sin NINGÚN respaldo textual (ni siquiera la
            # palabra del producto aparece en el mensaje) es un problema de
            # ACTIVIDAD, no de cantidad — "mi amigo no está certificado" (sin
            # decir bucear/snorkel/minicurso) hacía que fill_gaps adivinara
            # snorkel o minicurso indistintamente para la MISMA frase
            # ambigua (otro extractor, detect_special_signals, adivinaba lo
            # contrario). Reforzar el prompt para que se abstenga NO
            # funcionó (medido 3/3 sigue adivinando) — verificación
            # determinista igual que el resto de este bloque. No aplica a la
            # actividad PRINCIPAL ya conocida (`prev_activity`), que puede
            # restatearse sin repetir la palabra en este turno.
            activity_unbacked = [
                act for act in alloc_patch
                if act != prev_activity and not _activity_has_textual_backing(act, message)
            ]
            if activity_unbacked:
                for act in activity_unbacked:
                    alloc_patch.pop(act, None)
                if _mentions_person(message):
                    state.needs_companion_activity = True
            # Counter con consumo, no un set de presencia (auditoría
            # 2026-07-23): un mismo número no puede "avalar" dos actividades
            # distintas solo porque aparece una vez en el texto para otra.
            msg_nums = _message_numbers(message)
            cleaned = {
                act: qty for act, qty in alloc_patch.items()
                if _consume_number(msg_nums, qty)
            }
            dropped = [act for act in alloc_patch if act not in cleaned]
            if dropped:
                # No se descarta en silencio — se pregunta (mismo principio
                # que el resto del núcleo): cada actividad sin respaldo
                # numérico real se encola para preguntarla, en vez de
                # perderse o de facturar una cantidad inventada.
                #
                # Excepción (bug en vivo 2026-07-23): en un turno MID-FLOW de
                # "añadir acompañante" (ya había `prev_activity` establecido
                # antes de este mensaje), fill_gaps puede RESTATEAR la
                # actividad principal dentro del mismo group_allocation
                # alucinado ("viene también un amigo que quiere hacer
                # snorkel" → {certified_diving:1, snorkel:1}, sin ningún
                # número real en el texto para ninguna de las dos). Si esa
                # restatement se descarta por falta de respaldo, encolarla iba
                # a preguntar por la actividad PRINCIPAL ya confirmada
                # ("¿Cuántos serían para buceo certificado?") en vez de por el
                # acompañante real — sin sentido, y pisa la pregunta correcta
                # que el fast-path regex de más abajo (`_ADDED_PERSON_RE` +
                # `_SINGULAR_COMPANION_RE`) ya sabe resolver sin preguntar. No
                # aplica al mensaje de apertura (`prev_activity` es None ahí),
                # donde la actividad principal SÍ puede ser un sub-grupo
                # legítimo por confirmar.
                for act in dropped:
                    if act == prev_activity:
                        continue
                    if act not in state.pending_companion_queue:
                        state.pending_companion_queue.append(act)
                if cleaned:
                    patch["group_allocation"] = cleaned
                else:
                    patch.pop("group_allocation", None)
                # El total (group_size) ya no es de fiar si el reparto que lo
                # sustenta tenía una entrada inventada.
                patch.pop("group_size", None)
        elif _ADDED_PERSON_RE.search(message) and not _EXPLICIT_NUMBER_RE.search(message):
            patch.pop("group_allocation", None)
            patch.pop("group_size", None)
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
    supervisor._apply_detected_intent(intent, state, message)

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

    # AÑADIR vs CAMBIAR (fast-path regex): si ya había actividad principal y
    # este turno menciona OTRA junto a una persona añadida ("viene también uno
    # que hace snorkel", "mi novia hace el minicurso"), es un AÑADIDO — la
    # actividad principal no se pisa (se restaura del "latest wins" de
    # _apply_detected_intent) y el subgrupo nuevo se acumula en el reparto. Un
    # cambio de opinión sin persona añadida ("mejor snorkel") sigue siendo
    # cambio (latest wins). Cubre solo las frases de _ADDED_PERSON_RE — frases
    # fuera de esa lista (o donde turn_act == prev_activity, p. ej. "mi
    # acompañante quiere hacer buceo pero no es certificado") las resuelve la
    # red de precisión LLM en maybe_handle_turn (detect_special_signals),
    # nunca ampliando este regex frase a frase (decisión owner 2026-07-22).
    turn_act = intent.activity
    companion_merged_fastpath = False
    if (
        prev_activity
        and turn_act
        and turn_act != prev_activity
        and turn_act in _ACTIVITY_TO_CART_TYPE
        and prev_activity in _ACTIVITY_TO_CART_TYPE
        and _ADDED_PERSON_RE.search(message)
    ):
        explicit_qty = (intent.group_allocation or {}).get(turn_act)
        # `intent.group_allocation` puede venir del gap-fill LLM (`fill_gaps`,
        # llamado más arriba en este mismo `_understand()` vía `_relevant_gaps`),
        # no solo del regex — y verificado en vivo (2026-07-23) que ese LLM
        # puede alucinar un reparto completo con el historial real de la
        # conversación por delante ("también vienen mis parces a hacer
        # snorkel" con 5 turnos previos de contexto devolvió
        # group_allocation={cert:1, snorkel:3} sin ningún "3" en el mensaje).
        # Por eso el respaldo de número explícito se aplica SIEMPRE, tenga o
        # no ya un valor `explicit_qty` — no solo cuando es None — antes de
        # confiarlo. Si no hay número real en el mensaje ni es un compañero
        # singular inequívoco ("mi novia"/"mi acompañante"), NO fusionar con
        # una cifra inventada — dejar el estado sin tocar para que el bloque
        # de la red de precisión más abajo (`detect_special_signals`)
        # pregunte cuántos son.
        if explicit_qty is not None and not _EXPLICIT_NUMBER_RE.search(message):
            explicit_qty = None
        if (
            explicit_qty is None
            and not _SINGULAR_COMPANION_RE.search(message)
        ):
            pass
        else:
            _restore_main_diver_fields(state, prev_activity, prev_service_id, prev_is_certified, prev_last_dive, prev_refresher)
            _merge_companion_activity(state, turn_act, explicit_qty or 1)
            companion_merged_fastpath = True
            # `turn_act` puede haber quedado encolado arriba (guard del
            # alloc_patch alucinado, sin respaldo numérico) antes de que este
            # fast-path lo resolviera de verdad por otra vía (compañero
            # singular inequívoco) — sin este descarte, se preguntaba una
            # cantidad que ya se acababa de fijar sin ambigüedad.
            if turn_act in state.pending_companion_queue:
                state.pending_companion_queue.remove(turn_act)

    # Normalizar group_size con el reparto: si el reparto suma MÁS personas que el
    # group_size conocido, el total manda. Bug en vivo (2026-07-22): "1 pero viene
    # un amigo que quiere bucear, no es certificado" dejaba alloc={cert:1,
    # minicurso:1} pero group_size=1 (el "1" lo fijó `_apply_short_answer` y la
    # extracción del acompañante llegó por otra vía que no lo re-sumaba) → el
    # precio/qty saldría para 1 persona en vez de 2.
    alloc = state.detected_group_allocation or {}
    if alloc:
        total = sum(v for v in alloc.values() if isinstance(v, int) and v > 0)
        if total > (state.detected_group_size or 0):
            state.detected_group_size = total
            logger.info(f"[CORE] group_size synced from allocation -> {total}")
    return intent, companion_merged_fastpath


def _restore_main_diver_fields(
    state: ConversationState, activity, service_id, is_certified, last_dive, refresher,
) -> None:
    """Restaura el perfil del buceador PRINCIPAL a como estaba antes de este
    turno — usado cuando ya se sabe que el mensaje hablaba de un ACOMPAÑANTE,
    no del hablante (fast-path regex arriba y red de precisión LLM en
    maybe_handle_turn). Bug real: "no es certificado"/"sin bucear hace X años"
    referido al acompañante se aplicaba por 'latest wins' al buceador
    principal ya resuelto (p. ej. is_certified=True → False de golpe).

    `activity`/`service_id` solo se restauran si HABÍA algo que proteger
    (`activity` no es None): si el mensaje de APERTURA establece la
    actividad principal en primera persona ("quiero bucear") en el MISMO
    turno que menciona a un acompañante ("...voy con mi amigo pero el no
    esta certificado"), no hay ninguna actividad previa que restaurar —
    pisarla con None borraba la actividad recién y correctamente detectada
    del hablante, dejando la reserva sin actividad principal (hallazgo D,
    batería sintética 2026-08-26)."""
    if activity is not None:
        state.detected_activity = activity
        state.detected_service_id = service_id
    state.is_certified = is_certified
    state.last_dive_over_2_years = last_dive
    state.refresher_interested = refresher


def _merge_companion_activity(state: ConversationState, activity: str, qty: int) -> None:
    """Añade `qty` personas a `activity` como subgrupo del reparto sin pisar
    la actividad principal — helper compartido por el fast-path regex
    (_ADDED_PERSON_RE, arriba) y por la red de precisión LLM
    (detect_special_signals, maybe_handle_turn) para que ambos caminos dejen
    el estado exactamente igual de consistente."""
    alloc = dict(state.detected_group_allocation or {})
    main_act = state.detected_activity
    if main_act and main_act not in alloc:
        alloc.setdefault(main_act, state.detected_group_size or 1)
    alloc[activity] = alloc.get(activity, 0) + qty
    state.detected_group_allocation = alloc
    state.detected_group_size = sum(alloc.values())
    logger.info(f"[CORE] merged companion activity {activity} x{qty} -> alloc={alloc}")


_RECALL_LABELS_ES = {
    "certified_diving": "buceo certificado", "minicourse": "minicurso",
    "snorkel": "snorkel", "padi_open_water": "el curso Open Water",
    "padi_advanced": "el curso Advanced", "padi_rescue": "el curso Rescue",
    "padi_divemaster": "el curso Divemaster", "padi_specialty": "un curso PADI",
}
_RECALL_LABELS_EN = {
    "certified_diving": "certified diving", "minicourse": "the mini-course",
    "snorkel": "snorkel", "padi_open_water": "the Open Water course",
    "padi_advanced": "the Advanced course", "padi_rescue": "the Rescue course",
    "padi_divemaster": "the Divemaster course", "padi_specialty": "a PADI specialty",
}


def _full_booking_recap(state: ConversationState) -> str | None:
    """Recap COMPLETO y cálido de la reserva (todas las actividades/personas +
    ubicación), del ESTADO (nunca inventado). Para la pregunta general "¿qué te
    había pedido?" — reemplaza el recall de campo-suelto que salía seco y a veces
    equivocado ("Me habías dicho: snorkel"). Estilo Monegros: recap estructurado.
    Devuelve None si no hay nada resuelto (el caller cae a RAG)."""
    es = state.language == "es"
    labels = _RECALL_LABELS_ES if es else _RECALL_LABELS_EN
    lines: list[str] = []
    alloc = state.detected_group_allocation or {}
    product_alloc = {k: v for k, v in alloc.items() if k in labels and v}
    if product_alloc:
        for act, qty in product_alloc.items():
            lines.append(f"• *{qty}* para *{labels[act]}*" if es else f"• *{qty}* for *{labels[act]}*")
    else:
        act = _effective_activity(state)
        if act:
            n = state.detected_group_size or 1
            lines.append(f"• *{n}* para *{labels.get(act, act)}*" if es else f"• *{n}* for *{labels.get(act, act)}*")
    if not lines:
        return None
    loc = state.location or state.detected_location
    if loc == "cartagena":
        lines.append("📍 Salida *desde Cartagena*" if es else "📍 Departing *from Cartagena*")
    elif loc == "island":
        hotel = state.hotel or state.detected_hotel
        suffix = f" (hotel {hotel})" if hotel else ""
        lines.append((f"📍 Ya *en las islas*{suffix}") if es else (f"📍 Already *on the islands*{suffix}"))
    name = f", {state.client_name}" if state.client_name else ""
    header = (f"Claro{name}, esto es lo que llevamos hasta ahora: 🤿\n"
              if es else f"Sure{name}, here's what we have so far: 🤿\n")
    return header + "\n".join(lines)


def _recall_answer(state: ConversationState, field: str) -> str | None:
    """Responde un pedido de "recuérdame qué dije" con el VALOR REAL del
    estado (nunca lo que el LLM "cree" que dijiste — el LLM solo identificó
    QUÉ campo se pide, ver detect_special_signals). Devuelve None si el
    estado no tiene de verdad ese dato resuelto, para que el caller caiga a
    RAG en vez de inventar algo — abstenerse es siempre mejor que un dato
    falso (mismo principio que el resto del extractor)."""
    lang = state.language
    es = lang == "es"
    if field == "booking_recap":
        return _full_booking_recap(state)
    if field == "group_size":
        n = state.detected_group_size
        if not n:
            return None
        if n == 1:
            return "Me dijiste que vas *solo/a*." if es else "You told me it's just *you*."
        return f"Me dijiste que sois *{n}* personas." if es else f"You told me you're a group of *{n}*."
    if field == "activity":
        act = _effective_activity(state)
        if not act:
            return None
        label = (_RECALL_LABELS_ES if es else _RECALL_LABELS_EN).get(act, act)
        return f"Me habías dicho: *{label}*." if es else f"You told me: *{label}*."
    if field == "location":
        loc = state.location
        if not loc:
            return None
        if loc == "island":
            return "Me dijiste que ya estás *en las islas*." if es else "You told me you're already *on the islands*."
        return "Me dijiste que salís *desde Cartagena*." if es else "You told me you're departing *from Cartagena*."
    if field == "is_certified":
        if state.is_certified is None:
            return None
        if state.is_certified:
            return "Me dijiste que *sí* estás certificado/a." if es else "You told me you *are* certified."
        return "Me dijiste que *no* estás certificado/a." if es else "You told me you're *not* certified."
    if field == "is_colombian":
        if state.is_colombian is None:
            return None
        if state.is_colombian:
            return "Me dijiste que *sí* eres colombiano/a o residente." if es else "You told me you *are* Colombian or a resident."
        return "Me dijiste que *no* eres colombiano/a." if es else "You told me you're *not* Colombian."
    if field == "ages":
        ages = state.detected_ages or []
        if not ages:
            return None
        ages_str = ", ".join(str(a) for a in ages)
        return f"Me dijiste que las edades eran: *{ages_str}*." if es else f"You told me the ages were: *{ages_str}*."
    if field == "hotel":
        if not state.hotel:
            return None
        return f"Me dijiste que estás en el *{state.hotel}*." if es else f"You told me you're staying at *{state.hotel}*."
    if field == "last_dive_over_2_years":
        if state.last_dive_over_2_years is None:
            return None
        if state.last_dive_over_2_years:
            return "Me dijiste que *sí*, hace más de 2 años." if es else "You told me it *has* been more than 2 years."
        return "Me dijiste que *no*, hace menos de 2 años." if es else "You told me it has *not* been more than 2 years."
    if field == "refresher_interested":
        if state.refresher_interested is None:
            return None
        if state.refresher_interested:
            return "Me dijiste que *sí* querías el refresher." if es else "You told me you *did* want the refresher."
        return "Me dijiste que *no* querías el refresher." if es else "You told me you did *not* want the refresher."
    return None


def _looks_like_question(message: str) -> bool:
    from src.agents import supervisor  # lazy
    return supervisor._looks_like_info_question(message) or "?" in message


# ─── Cierre: carrito desde slots + resumen determinista con links ───

def _cart_item(state: ConversationState, activity: str, qty: int) -> dict:
    """Ítem del carrito para una actividad de producto (plan del catálogo)."""
    if activity == "certified_diving":
        plan = _resolve_cert_plan(state)
        return {"type": "cert", "qty": qty, "plan": plan,
                "label": cart_render.cart_label_for("cert", plan, state.language)}
    if activity == "minicourse":
        return {"type": "beginner", "qty": qty, "plan": None,
                "label": cart_render.cart_label_for("beginner", None, state.language)}
    if activity == "snorkel":
        return {"type": "snorkel", "qty": qty, "plan": None,
                "label": cart_render.cart_label_for("snorkel", None, state.language)}
    # Curso PADI: resolver la variante por ubicación (open_water →
    # open_water_already_on_island si está en las islas). Divemaster es
    # contact-only y _cart_booking_blocks ya lo cierra vía asesor (sin link).
    plan = state.detected_service_id
    if plan:
        plan = cart_render.service_for_location(plan, state)
    return {"type": "course", "qty": qty, "plan": plan,
            "label": cart_render.cart_label_for("course", plan, state.language)}


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

    response = cart_render.goto_final_summary(state)
    return refresher_note + response


def _colombian_summary_lines(state: ConversationState) -> str:
    """Resumen por actividad para clientes colombianos: label + cantidad +
    precio en COP del catálogo, sin URLs de reserva directa."""
    lang = state.language
    lines: list[str] = []
    for b in cart_render.cart_booking_blocks(state):
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

def _booking_context_summary(state: ConversationState) -> str:
    """Resumen corto del estado de la reserva para dar contexto al redactor del
    acuse (para que reconozca cosas concretas: "anoto a tu amigo para el
    minicurso"). Nunca incluye precios ni links — solo estructura."""
    parts: list[str] = []
    if state.detected_activity:
        parts.append(f"actividad principal: {state.detected_activity}")
    alloc = state.detected_group_allocation or {}
    if alloc:
        parts.append("reparto: " + ", ".join(f"{k} x{v}" for k, v in alloc.items()))
    elif state.detected_group_size:
        parts.append(f"personas: {state.detected_group_size}")
    loc = state.location or state.detected_location
    if loc:
        parts.append(f"ubicación: {loc}")
    return "; ".join(parts)


async def maybe_handle_turn(
    state: ConversationState, message: str, *, routing_signals: dict | None = None,
) -> str | None:
    """Punto de entrada desde el supervisor (tras el gating de seguridad).
    Devuelve None solo para las clases de mensaje que deben seguir cayendo a
    los handlers deterministas legacy (escalado por keyword, menú/volver).

    `routing_signals` (auditoría 2026-07-22): ya calculado UNA vez por
    `supervisor._route_message_inner` (red de precisión LLM para escalado/
    menú cuando las listas de palabras clave no reconocen la frase — nunca
    se vuelve a llamar aquí, mismo resultado para todo el turno)."""
    from src.agents import supervisor  # lazy

    routing_signals = routing_signals or {}
    msg_lower = message.strip().lower()
    if supervisor._matches_escalation_keyword(msg_lower) or routing_signals.get("wants_human"):
        return None
    # (Fase 4, decisión owner 2026-07-28) "menú"/"volver"/"back" = MENSAJE NORMAL:
    # el núcleo los trata como texto conversacional (re-orienta a la reserva) en
    # vez de resetear a un menú de botones que ya no existe. Con esto muere el
    # último caller vivo del árbol legacy (los handlers menú-reset/back del
    # supervisor). Antes esto devolvía None → caía a esos handlers.

    # Primer mensaje: inferir idioma como hace la entrada legacy, y marcar que
    # toca presentarse (Coral + Diving Planet, tono cercano — regla de persona).
    first_turn = state.step in (Step.WELCOME, Step.LANGUAGE)
    if first_turn:
        from src.agents.language_detector import detect_language_llm
        from src.flows.decision_tree import _detect_language_from_text
        # Cadena: heurística de stopwords → fallback LLM (solo si la heurística no
        # detecta nada; evita preguntar "Español/English" ante un mensaje que
        # revela el idioma con palabras fuera de la lista curada) → heurística de
        # hints. El `or` corta: el LLM solo se llama si la primera devuelve None.
        state.language = (
            _detect_language_from_text(message)
            or await detect_language_llm(message)
            or supervisor._infer_language(message, state.language)
        )
        # Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 4): esta
        # detección de apertura (heurística → LLM → hints, la más fiable)
        # solo fijaba `state.language`, nunca `state.detected_language` — y
        # `_apply_detected_intent` (que corre en CADA turno vía
        # `_understand()`) sobreescribe `state.language` con su propia
        # clasificación más simple, por-mensaje, mientras
        # `state.detected_language` siga vacío. Resultado: en el PRIMER
        # turno, el saludo se renderizaba ya en el idioma correcto (inglés
        # para "hi quiero snorkel...") pero segundos después, dentro del
        # mismo turno, la pregunta de slot salía en español — la
        # clasificación por-mensaje del intent_detector (más simple, sin
        # LLM) decidía distinto para un mensaje con palabras mezcladas.
        # Fijar `detected_language` aquí también evita ese pisado sobre la
        # detección ya resuelta y más fiable.
        state.detected_language = state.language
        state.step = Step.FREE_TEXT
        state.quick_replies = []
    elif _SWITCH_TO_EN_RE.search(message) and state.language != "en":
        # Petición EXPLÍCITA de cambiar de idioma a mitad de conversación
        # (auditoría 2026-08-26) — fuera del primer turno nada más vuelve a
        # mirar el idioma (a propósito, para no reclasificar cada mensaje),
        # así que sin este chequeo dedicado la petición se ignoraba del
        # todo. `elif` porque en el primer turno la detección de arriba ya
        # decide bien ("hi, can we talk in english" ya sale en inglés).
        state.language = state.detected_language = "en"
    elif _SWITCH_TO_ES_RE.search(message) and state.language != "es":
        state.language = state.detected_language = "es"
    _capture_client_name(state, message)
    greeting = _greeting(state) if first_turn else ""

    state.history.append({"role": "user", "content": message})

    # Disponibilidad: NO alucinar el calendario (Bloque 2.5, portado al núcleo
    # 2026-07-24). Bug vivo en PRE: el gate del supervisor está DESPUÉS del hook
    # del núcleo, así que con core-on "¿tienen disponibilidad el sábado?" caía a
    # RAG y respondía "Claro que sí, tenemos disponibilidad para el sábado" —
    # confirmando un cupo que no puede conocer. `_AVAILABILITY_PATTERN` (narrow,
    # seguro) aplica siempre; la señal amplia (`_asks_about_availability` /
    # `availability_question`) solo si NO hay una reserva en curso (con actividad
    # elegida, "¿algo para más días?" es una pregunta de PLAN, no de cupo — mismo
    # criterio que el guard `_in_active_cart_building` del supervisor legacy).
    # Hallazgo (batería sintética contra PRE, 2026-08-26, conv 395): "¿abren
    # el 25 de diciembre?" NO matchea `_AVAILABILITY_PATTERN` ni
    # `_asks_about_availability` (ninguno de los dos reconoce "abren"/"open
    # on"), así que sin la señal LLM `availability_question` (que no
    # siempre se calcula, p.ej. si el keyword-gate de arriba ya encontró
    # otra cosa) el mensaje caía derecho a RAG. `_CLOSED_DATE_RE` sola basta
    # para entrar aquí — no depende de que el mensaje además "suene" a
    # pregunta de disponibilidad genérica.
    if (
        supervisor._AVAILABILITY_PATTERN.search(msg_lower)
        or (
            (supervisor._asks_about_availability(msg_lower)
             or routing_signals.get("availability_question"))
            and state.detected_activity is None
        )
        or supervisor._CLOSED_DATE_RE.search(msg_lower)
    ):
        # Hallazgo (batería sintética contra PRE, 2026-08-26, conv 395):
        # "¿abren el 25 de diciembre?" caía en el canned genérico de abajo
        # ("siempre hay disponibilidad") — FALSO para esos dos días
        # concretos (`policies.json["closed_days"]`: solo cerrado 25 dic y
        # 1 ene). Este bloque del núcleo es el que realmente responde la
        # mayoría de mensajes de apertura (se ejecuta ANTES que la copia
        # del supervisor); el mismo guard se aplicó ahí también.
        if supervisor._CLOSED_DATE_RE.search(msg_lower):
            from src.knowledge.loader import load_policies
            policy_text = (load_policies().get("policies", {}).get("closed_days") or {}).get(
                state.language, ""
            )
            response = greeting + policy_text
            state.history.append({"role": "assistant", "content": response})
            return response
        avail = (
            "¡Buena noticia! 📅 Las salidas son diarias y siempre hay disponibilidad. "
            "Vas a poder elegir el día exacto y el número de personas directamente en el "
            "calendario del link de reserva. 😊"
            if state.language == "es" else
            "Good news! 📅 Departures run daily and there's always availability. "
            "You'll be able to pick the exact date and number of people right in the "
            "booking link's calendar. 😊"
        )
        response = greeting + avail
        state.history.append({"role": "assistant", "content": response})
        return response

    # COMPRENDER (carryover PRIMERO): si hay un slot pendiente y este mensaje
    # lo RESUELVE, el carryover gana aunque el mensaje "parezca pregunta" por
    # sus palabras — "tienen 7 y 9 años" responde SLOT_AGES aunque "tienen"
    # dispare _looks_like_info_question (Fase 3 causa B; clase general: la
    # respuesta natural de varios slots contiene palabras-pregunta). Un "?"
    # explícito SÍ es siempre una pregunta real y va a RAG (así
    # test_question_mid_flow_answers_and_reasks_pending_slot sigue intacto).
    prev_pending = state.core_pending_slot
    prev_cart_types = {it.get("type") for it in state.mixed_cart}
    prev_main_activity = state.detected_activity
    prev_main_service_id = state.detected_service_id
    prev_main_is_certified = state.is_certified
    prev_main_last_dive = state.last_dive_over_2_years
    prev_main_refresher = state.refresher_interested
    prev_group_size = state.detected_group_size
    prev_group_allocation = dict(state.detected_group_allocation or {})
    has_qmark = "?" in message

    resolved_short = False
    if prev_pending and not has_qmark:
        resolved_short = _apply_short_answer(state, message)

    # Encadenar la cola de sub-grupos adicionales (multi-ítem, auditoría
    # 2026-07-23): si se acaba de resolver la cantidad de UN sub-grupo
    # ambiguo y quedan más en `pending_companion_queue`, preguntar por el
    # siguiente ya mismo — el flujo normal (next_missing_slot) no conoce esta
    # cola, así que hay que interceptarlo aquí antes de que seguir de largo
    # pierda la pregunta pendiente.
    if resolved_short and prev_pending == SLOT_COMPANION_QTY and state.pending_companion_queue:
        state.pending_companion_activity = state.pending_companion_queue.pop(0)
        response = greeting + ask_slot(state, SLOT_COMPANION_QTY)
        state.history.append({"role": "assistant", "content": response})
        return response

    # Encadenar SLOT_COMPANION_ACTIVITY -> SLOT_COMPANION_QTY (auditoría
    # 2026-07-23): una vez se sabe QUÉ quiere hacer el acompañante ("mi
    # amigo no está certificado" -> se preguntó y respondió "snorkel"),
    # sigue faltando CUÁNTOS son — se encadena la pregunta de cantidad ya
    # mismo, mismo patrón que la cola de sub-grupos.
    if resolved_short and prev_pending == SLOT_COMPANION_ACTIVITY and state.pending_companion_activity:
        response = greeting + ask_slot(state, SLOT_COMPANION_QTY)
        state.history.append({"role": "assistant", "content": response})
        return response

    # "?" explícito → SIEMPRE una pregunta real. Antes de RAG, comprobar si es
    # un pedido de RECORDAR un dato ya dado ("¿cuántas personas somos, me lo
    # recuerdas?") — se responde con el valor REAL del estado, determinista,
    # nunca con lo que el LLM "cree" que se dijo (hallazgo en vivo
    # 2026-07-22: el bot no sabía recuperar sus propios datos y ofrecía
    # escalar a un asesor para algo que ya tenía).
    if not resolved_short and has_qmark:
        signals = await detect_special_signals(message, history=state.history, lang=state.language)
        recalled = None
        if signals.get("recall_field"):
            recalled = _recall_answer(state, signals["recall_field"])
        if recalled:
            response = recalled
            if prev_pending:
                response += "\n\n" + ask_slot(state, prev_pending, reasking=True)
            response = greeting + response
            state.history.append({"role": "assistant", "content": response})
            return response
        answer = greeting + await _answer_question(state, message)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # DELIBERACIÓN entre actividades (B2, 2026-07-24): un mensaje que sopesa
    # 2+ actividades sin decidirse ("mi pareja duda entre buceo y minicurso",
    # sin "?") NO es una selección de ambas — va a RAG (explicar la diferencia)
    # ANTES de que la extracción las tome como reserva. Va tras el carryover
    # (una respuesta de slot legítima ya ganó arriba) y tras el gate de "?"
    # (esas ya fueron a RAG). El ancla determinista de 2+ productos evita
    # secuestrar dudas de slot (ubicación/hotel) y selecciones de una sola
    # actividad. `who`/`options` de la señal solo se registran (v1): RAG ve el
    # mensaje entero y explica; la forma rica deja el camino de upgrade abierto.
    if not resolved_short and _is_deliberation_between_options(message, routing_signals):
        offerings = _mentioned_offerings(message)
        obj = routing_signals.get("comparing_options") or {}
        logger.info(
            f"[CORE] deliberation -> RAG offerings={offerings} "
            f"who={obj.get('who') if isinstance(obj, dict) else None}"
        )
        query = _comparison_query(offerings, state.language)
        rag = await _answer_question(state, message, rag_query=query)
        # Fallback determinista: si el KB no tiene ese par (RAG devuelve su
        # respuesta de "no lo tengo a la mano"), comparar desde el catálogo en
        # vez de ofrecer un asesor (hallazgo en vivo 2026-07-24, consistente).
        from src.agents.rag_agent import FALLBACK_EN, FALLBACK_ES
        if FALLBACK_ES in rag or FALLBACK_EN in rag:
            rag = _compose_comparison(offerings, state.language)
            state.core_pending_slot = SLOT_ACTIVITY
            state.quick_replies = []
            logger.info(f"[CORE] deliberation RAG fallback -> catalog compare offerings={offerings}")
        answer = greeting + rag
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # COMPRENDER: extracción del resto del mensaje.
    companion_merged_fastpath = False
    if not (resolved_short and len(message.strip()) <= 12):
        _, companion_merged_fastpath = await _understand(state, message)

    # Multi-ítem (auditoría 2026-07-23): si _understand() encoló alguna
    # actividad del reparto sin respaldo numérico real (fill_gaps inventando
    # una cantidad para un plural vago dentro de group_allocation — hallazgo
    # nuevo, mismo principio que la cola de other_companions más abajo),
    # preguntar por ella ya mismo en vez de seguir de largo. Nunca se pierde
    # en silencio ni se factura una cantidad inventada.
    if state.pending_companion_queue and not state.pending_companion_activity:
        state.pending_companion_activity = state.pending_companion_queue.pop(0)
        response = greeting + ask_slot(state, SLOT_COMPANION_QTY)
        state.history.append({"role": "assistant", "content": response})
        return response

    # Auditoría 2026-07-23: `_understand()` detectó un acompañante mencionado
    # solo por un ATRIBUTO ("mi amigo no está certificado"), sin actividad ni
    # intención declarada — no hay caso válido para adivinar snorkel o
    # minicurso, se pregunta qué le gustaría hacer.
    #
    # Auditoría 2026-08-26 (batería sintética contra PRE): interrumpir
    # SIEMPRE aquí, sin mirar si ya había una pregunta obligatoria pendiente
    # (seguridad, nacionalidad...), la enterraba sin preguntarla nunca —
    # "soy buzo certificado... ¿han pasado más de 2 años?" seguido de "somos
    # 2" saltaba directo a la pregunta del acompañante, sin que la de
    # seguridad se llegara a responder jamás. Mismo criterio que el bloque
    # `companion_activity_deferred` de más abajo: solo se interrumpe YA
    # MISMO si no había nada más pendiente; si lo había, se difiere (se dejar
    # caer sin `return`, para que el resto del turno siga su curso normal —
    # `next_missing_slot` volverá a preguntar por lo que de verdad tocaba) y
    # se marca para retomar el acompañante en cuanto ese hueco se cierre.
    if state.needs_companion_activity:
        state.needs_companion_activity = False
        if next_missing_slot(state) is None:
            response = greeting + ask_slot(state, SLOT_COMPANION_ACTIVITY)
            state.history.append({"role": "assistant", "content": response})
            return response
        state.companion_activity_deferred = True

    # ¿La extracción base (regex + gap-fill, dentro de `_understand()`) ya
    # cambió el tamaño/reparto del grupo este turno? Bug en vivo (2026-07-23,
    # Rocío): "tengo 3 amigos que quieren hacer alguna actividad" — el fix del
    # regex de intent_detector.py ya suma correctamente +1 (group_size 1→4).
    # Sin esta guarda, `companion_ambiguous` (más abajo) volvía a disparar la
    # red de precisión LLM para el MISMO mensaje, que fusionaba 3 acompañantes
    # OTRA VEZ encima del grupo ya correcto → 4+3=7. La extracción base y la
    # red de precisión leen la MISMA evidencia textual; si la base ya absorbió
    # el cambio de tamaño de grupo, no hay que re-contarlo.
    group_composition_resolved_by_base_extraction = (
        state.detected_group_size != prev_group_size
        or (state.detected_group_allocation or {}) != prev_group_allocation
    )

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
            response = cart_render.goto_final_summary(state)
            state.core_pending_slot = None
            supervisor._maybe_build_pending_note(state)
            state.history.append({"role": "assistant", "content": response})
            return response

    # Red de precisión: si el turno NO avanzó nada por los caminos normales
    # (regex + gap-fill), probar la detección de señales por LLM antes de caer
    # al escalado genérico — cubre "hay un amigo que quiere hacer snorkel" o
    # "mi acompañante quiere hacer buceo pero no es certificado", frases que
    # ningún regex reconocía (decisión owner 2026-07-22: nunca ampliar el
    # regex frase a frase para esto; el LLM decide QUÉ pasó, el estado decide
    # el VALOR real). Solo se gasta esta llamada cuando de verdad hace falta.
    # (Se mide por next_missing_slot, no por un snapshot crudo de campos: un
    # campo del buceador PRINCIPAL pisado por error por este mismo turno —el
    # bug que _restore_main_diver_fields corrige— no debe contar como
    # "avance", o la red de precisión nunca llegaría a correr.)
    # `companion_merged_fastpath` (hallazgo en vivo 2026-07-22): añadir un
    # acompañante no siempre cambia next_missing_slot (p. ej. seguía faltando
    # "nacionalidad" con o sin el acompañante) — sin este flag, la red de
    # precisión LLM de abajo se ejecutaba OTRA VEZ para el mismo mensaje y
    # duplicaba la cantidad (snorkel:1 fusionado por el fast-path + snorkel:1
    # fusionado de nuevo por el LLM = snorkel:2).
    # `group_composition_resolved_by_base_extraction` (hallazgo en vivo
    # 2026-07-23, Rocío): si la extracción base ya absorbió el tamaño/reparto
    # del grupo este turno pero SIN cambiar next_missing_slot (p. ej. seguía
    # faltando la ubicación), la red de precisión volvía a contar los mismos
    # acompañantes encima (4 de la base + 3 de la señal = 7). Que la base haya
    # resuelto la composición del grupo cuenta como avance por sí mismo.
    advanced = (
        resolved_short
        or companion_merged_fastpath
        or group_composition_resolved_by_base_extraction
        or next_missing_slot(state) != prev_pending
    )

    # Un acompañante / actividad DISTINTA a la principal que el fast-path por regex
    # NO cazó (`_ADDED_PERSON_RE` no matchea "hay un amigo que quiere snorkel",
    # "2 y uno hace snorkel"…) se clasifica SIEMPRE por el LLM — añadir vs. cambiar —
    # pase lo que pase con el resto de slots. Así estos añadidos no se pierden por
    # haber "avanzado" otro dato en el mismo mensaje (bug en vivo 2026-07-22). El
    # prompt de señales ya distingue el acompañante del cambio de opinión ("mejor
    # snorkel" → None), así que ampliar el disparo aquí no crea falsos añadidos.
    # Un mensaje que menciona a OTRA persona (por `_mentions_person`) en una reserva
    # ya iniciada se clasifica SIEMPRE por el LLM (añadir acompañante vs. nada),
    # aunque el acompañante quiera la MISMA actividad (p. ej. "1 pero tengo un amigo
    # que quiere hacer buceo") y aunque otro slot haya avanzado en el mismo mensaje.
    #
    # El guard usaba `not _ADDED_PERSON_RE.search(message)` para decidir si el
    # fast-path "ya cubrió" el mensaje — pero ese regex solo marca que el mensaje
    # TIENE un disparador léxico de persona ("además", "también"...), no que el
    # fast-path realmente fusionó algo: ese fast-path (en `_understand()`) exige
    # ADEMÁS una actividad explícita en el mismo turno (`turn_act`). Bug en vivo
    # (2026-07-23, Rocío): "tengo el AOWD, además tengo 3 amigos que quieren hacer
    # ALGUNA actividad" — "además" matchea `_ADDED_PERSON_RE`, pero sin actividad
    # explícita el fast-path no hace nada; con el guard viejo, la red de precisión
    # tampoco corría, y los 3 acompañantes se perdían en silencio. La señal correcta
    # de "¿ya lo fusionó el fast-path?" es `companion_merged_fastpath` (el flag que
    # `_understand()` ya devuelve para esto mismo), no una re-lectura del regex
    # disparador.
    # `prev_main_activity` (actividad ANTES de este turno) no basta cuando la
    # actividad principal y la mención del acompañante llegan en el MISMO
    # mensaje de apertura ("hola quiero bucear, voy con mi amigo pero el no
    # esta certificado"): ahí `prev_main_activity` sigue en None (nada se
    # había establecido todavía) aunque `_understand()` YA resolvió la
    # actividad principal este mismo turno, así que este bloque nunca se
    # disparaba y la mención del acompañante se perdía en silencio (hallazgo
    # D, batería sintética 2026-08-26 — `_activity_has_textual_backing`/el
    # fix de v0.20.62 solo se había verificado en vivo para el caso
    # MID-FLOW). Se comprueba también `state.detected_activity` (post-turno)
    # para cubrir ambos casos sin ampliar el disparo a mensajes que no
    # mencionan actividad alguna.
    companion_ambiguous = bool(
        (prev_main_activity in _ACTIVITY_TO_CART_TYPE or state.detected_activity in _ACTIVITY_TO_CART_TYPE)
        and _mentions_person(message)
        and not companion_merged_fastpath
        and not group_composition_resolved_by_base_extraction
    )
    if not advanced or companion_ambiguous:
        signals = await detect_special_signals(message, history=state.history, lang=state.language)
        activity = signals.get("companion_activity")
        # Verificación determinista (auditoría 2026-07-23): reforzar el
        # prompt para que no adivine una actividad sin respaldo textual NO
        # funcionó (medido 3/3 sigue adivinando "minicourse" para "mi amigo
        # no está certificado", sin ninguna actividad mencionada) — misma
        # lección que la cuantificación de plurales vagos: hace falta
        # verificación determinista, no más prompt. Si el mensaje no
        # menciona NINGÚN producto por palabra clave, la actividad que
        # devuelve el LLM no tiene respaldo textual — se descarta.
        if activity and not _activity_has_textual_backing(activity, message):
            activity = None
        # Guard contra el flip-flop del LLM con historial: solo se trata como
        # ACOMPAÑANTE si el mensaje nombra a otra persona. El LLM decide la
        # actividad; que nombre a una persona decide que es un añadido, no un
        # cambio de opinión ("mejor snorkel" nunca añade; "un amigo…" sí).
        # La confianza en "nombra a otra persona" viene del propio LLM
        # (`mentions_other_person`, hallazgo en vivo 2026-07-22: `_mentions_person`
        # es una lista fija de palabras — amigo/novia/hermano/primo... — que NO
        # reconoce jerga regional como "parce"/"cuate"/"pana"/"carnal"; con solo
        # el regex, un acompañante bien detectado por el LLM se descartaba en
        # silencio porque la palabra no estaba en la lista). El regex se
        # mantiene como respaldo barato para cuando el LLM no marque el campo.
        if activity and (signals.get("mentions_other_person") or _mentions_person(message)):
            # El turno hablaba de un ACOMPAÑANTE, no del hablante principal:
            # restaurar lo que este mismo turno pudo haber pisado por error en
            # el perfil del buceador principal antes de aplicar el añadido.
            _restore_main_diver_fields(
                state, prev_main_activity, prev_main_service_id,
                prev_main_is_certified, prev_main_last_dive, prev_main_refresher,
            )
            # Counter compartido con consumo (auditoría multi-ítem 2026-07-23):
            # el sub-grupo PRINCIPAL consume su número antes que
            # `other_companions` más abajo, para que un mismo número del texto
            # no pueda avalar dos sub-grupos distintos a la vez (bug medido en
            # vivo: "2 bucean, mis amigos hacen snorkel" validaba por error un
            # snorkel=2 inventado solo porque el "2" de "2 bucean" ya estaba en
            # el texto — aunque ya estaba gastado por el principal).
            msg_numbers = _message_numbers(message)
            qty = signals.get("companion_qty")
            if qty is not None and not _consume_number(msg_numbers, qty):
                # Verificado en vivo (2026-07-22): el LLM devolvió qty=1 para
                # "también vienen mis amigos a hacer snorkel" pese a que el
                # prompt le pide abstenerse ante un plural vago — no basta con
                # pedírselo, hay que comprobarlo. Si el número que dice no
                # tiene respaldo real (o ya lo consumió otro sub-grupo), se
                # descarta el qty del LLM sea cual sea.
                qty = None
            # "¿es exactamente 1?" también se confía primero al LLM
            # (`companion_is_singular`, mismo criterio que `mentions_other_person`):
            # el regex `_SINGULAR_COMPANION_RE` es una lista fija de palabras que
            # no reconoce jerga regional ("mi parce"/"mi cuate" preguntaban
            # cantidad en vez de asumir 1 sin necesidad). El LLM entiende
            # cualquier variante; el regex se queda como respaldo barato.
            #
            # Asimetría cerrada (auditoría Fase B, 2026-07-23): `companion_qty`
            # ya se descartaba si no había número real en el texto, pero
            # `companion_is_singular=True` del LLM no tenía ninguna segunda
            # verificación — un plural con jerga rarísima podía colarse como
            # "1 solo" sin que nada lo contradijera. `_PLURAL_COMPANION_RE`
            # (sustantivo de compañero en plural inequívoco: "amigos",
            # "parceros"...) invalida esa confianza igual que
            # `_EXPLICIT_NUMBER_RE` invalida `companion_qty`.
            singular_confirmed = _SINGULAR_COMPANION_RE.search(message) or (
                signals.get("companion_is_singular")
                and not _PLURAL_COMPANION_RE.search(message)
            )
            main_ambiguous = qty is None and not singular_confirmed
            if not main_ambiguous:
                qty = qty or 1  # singular inequívoco ("un amigo"/"a friend") -> 1

            # Multi-ítem (auditoría 2026-07-23): 3+ actividades en un mensaje
            # ("2 bucean, mis amigos hacen snorkel y uno hace el minicurso").
            # Medido con matriz de 9 casos x 4 repeticiones, con Y sin refuerzo
            # de prompt: el LLM NUNCA se abstiene de forma fiable ante un
            # plural vago en `other_companions` — sigue inventando una
            # cantidad. Se procesa ANTES de decidir qué preguntar (si el
            # principal TAMBIÉN es ambiguo) para no perder sub-grupos
            # adicionales por cortar el turno demasiado pronto. Reutiliza
            # `msg_numbers` YA CONSUMIDO por el principal (mismo Counter, no
            # uno nuevo) — así el mismo número del texto no puede avalar dos
            # sub-grupos distintos.
            for item in (signals.get("other_companions") or []):
                other_act = item.get("activity")
                other_qty = item.get("qty")
                if other_act not in _ACTIVITY_TO_CART_TYPE or other_act == activity:
                    continue
                if other_qty is not None and _consume_number(msg_numbers, other_qty):
                    _merge_companion_activity(state, other_act, other_qty)
                else:
                    # Cantidad no respaldada por ningún número real del
                    # mensaje — se pregunta en vez de asumir, en cuanto se
                    # resuelvan el principal y el resto de la cola.
                    if other_act not in state.pending_companion_queue:
                        state.pending_companion_queue.append(other_act)

            if main_ambiguous:
                # Plural vago ("mis amigos", "unos amigos", "friends" sin
                # número) en el sub-grupo PRINCIPAL — en vez de asumir 1, se
                # pregunta cuántos son (hallazgo en vivo: "mis amigos"
                # generaba group_allocation={snorkel:3} sin preguntar). Va
                # primero en la cola; lo adicional (ya encolado arriba) se
                # preguntará después, uno a la vez.
                if activity not in state.pending_companion_queue:
                    state.pending_companion_queue.insert(0, activity)
            else:
                _merge_companion_activity(state, activity, qty)

            if state.pending_companion_queue:
                state.pending_companion_activity = state.pending_companion_queue.pop(0)
                response = greeting + ask_slot(state, SLOT_COMPANION_QTY)
                state.history.append({"role": "assistant", "content": response})
                return response

            # Post-cierre: puede haber MÁS de una actividad nueva a la vez
            # (el sub-grupo principal Y uno o más de other_companions), así
            # que se añaden todas las que falten en el carrito, no solo la
            # principal (mismo patrón que el chequeo genérico de arriba).
            if prev_cart_types:
                alloc_now = state.detected_group_allocation or {}
                new_items = [
                    _cart_item(state, act2, qty2)
                    for act2, qty2 in alloc_now.items()
                    if act2 in _ACTIVITY_TO_CART_TYPE and qty2
                    and _ACTIVITY_TO_CART_TYPE[act2] not in prev_cart_types
                ]
                if new_items:
                    state.mixed_cart.extend(new_items)
                    response = cart_render.goto_final_summary(state)
                    state.core_pending_slot = None
                    supervisor._maybe_build_pending_note(state)
                    state.history.append({"role": "assistant", "content": response})
                    return response
            advanced = True
        elif (
            (signals.get("mentions_other_person") or _mentions_person(message))
            and prev_pending != SLOT_COMPANION_ACTIVITY
        ):
            # Auditoría 2026-07-23: hay un acompañante (persona mencionada)
            # pero ninguna actividad con respaldo textual real — "mi amigo
            # no está certificado" dice un ATRIBUTO, no una actividad ni
            # intención ("quiere bucear"/"quiere snorkel"). Dos extractores
            # distintos (fill_gaps y esta misma señal) adivinaban cosas
            # DISTINTAS para la misma frase ambigua (snorkel vs. minicurso).
            # En vez de adivinar cuál, se pregunta qué le gustaría hacer.
            #
            # Bug en vivo (auditoría 2026-08-26, batería sintética contra
            # PRE): sin `prev_pending != SLOT_COMPANION_ACTIVITY`, esto
            # entraba en BUCLE — detect_special_signals RE-DERIVA la señal
            # de "hay un acompañante" desde el HISTORIAL entero cada vez que
            # se le llama, así que una respuesta vacía de contenido como
            # "no" (que en realidad respondía a SEGURIDAD, una pregunta
            # pendiente ANTERIOR que quedó enterrada) seguía devolviendo
            # `mentions_other_person=True` turno tras turno, re-preguntando
            # la MISMA pregunta sin parar y sin dejar que se llegara a
            # preguntar seguridad/nacionalidad nunca. Si ya es la pregunta
            # pendiente y no se resolvió (si se hubiera resuelto,
            # `_apply_short_answer` ya habría devuelto antes de llegar
            # aquí), no se repregunta por esta vía — se deja que el flujo
            # normal decida el siguiente slot.
            #
            # Además (mismo hallazgo 2026-08-26): interrumpir aquí SIEMPRE,
            # sin mirar si ya había una pregunta obligatoria pendiente
            # (seguridad, nacionalidad...) de ANTES de que se detectara este
            # acompañante, la enterraba sin preguntarla nunca. Solo se
            # interrumpe ya mismo si no queda nada más por delante; si lo
            # hay, se difiere con `companion_activity_deferred` (se retoma
            # justo antes de cerrar) y se deja que el turno siga su curso
            # normal.
            _restore_main_diver_fields(
                state, prev_main_activity, prev_main_service_id,
                prev_main_is_certified, prev_main_last_dive, prev_main_refresher,
            )
            if next_missing_slot(state) is None:
                response = greeting + ask_slot(state, SLOT_COMPANION_ACTIVITY)
                state.history.append({"role": "assistant", "content": response})
                return response
            state.companion_activity_deferred = True
            advanced = True
        elif signals.get("refresher_interested") is not None:
            # Auditoría 2026-07-22: refresher_interested no tenía NINGÚN
            # respaldo LLM — una frase que is_affirmative/is_negative no
            # reconocieran ("sí, no estaría mal") dejaba al bot re-preguntando
            # lo mismo sin fin, único slot booleano de la reserva sin red.
            state.refresher_interested = signals["refresher_interested"]
            advanced = True
        elif signals.get("recall_field"):
            recalled = _recall_answer(state, signals["recall_field"])
            if recalled:
                response = recalled
                if prev_pending:
                    response += "\n\n" + ask_slot(state, prev_pending, reasking=True)
                response = greeting + response
                state.history.append({"role": "assistant", "content": response})
                return response

    # Multi-ítem, segundo hallazgo (más profundo que el primero, auditoría
    # 2026-07-23): cuando el LLM se ABSTIENE correctamente ante un plural
    # vago (no incluye la actividad en group_allocation/other_companions en
    # absoluto, tal y como se le pide), esa actividad puede desaparecer SIN
    # QUE NADA LO NOTE — el guard de arriba solo reacciona cuando el LLM SÍ
    # incluye un valor sin respaldo; si directamente omite la clave, no hay
    # nada que descartar. "tres bucean, mis amigos hacen snorkel, y dos hacen
    # el minicurso" hizo que fill_gaps omitiera "snorkel" del todo
    # (comportamiento correcto del modelo) y la mención se perdía en
    # silencio. Se compara qué actividades MENCIONA el texto (palabra clave,
    # independiente de lo que el LLM haya estructurado) contra lo que quedó
    # registrado en cualquier sitio (tras TODO el procesamiento de arriba,
    # regex + gap-fill + señales) — si algo se mencionó y no aparece en
    # ningún sitio, se pregunta. Va DESPUÉS del bloque de señales (no antes)
    # para dejar que el mecanismo preciso (companion_qty/other_companions,
    # que sabe distinguir "quién ya quedó confirmado") resuelva primero; esto
    # es solo la red de última instancia para lo que ni siquiera llegó a
    # entrar en la estructura del LLM. Acotado a mensajes que mencionan a
    # otra persona (`_mentions_person`) para no disparar en cada mención
    # suelta.
    mentioned = _mentioned_product_activities(message)
    if mentioned and _mentions_person(message) and not state.pending_companion_queue:
        accounted = set((state.detected_group_allocation or {}).keys())
        main_act = _effective_activity(state)
        if main_act:
            accounted.add(main_act)
        missing_mentions = [act for act in mentioned if act not in accounted]
        if missing_mentions:
            for act in missing_mentions:
                if act not in state.pending_companion_queue:
                    state.pending_companion_queue.append(act)
            state.pending_companion_activity = state.pending_companion_queue.pop(0)
            response = greeting + ask_slot(state, SLOT_COMPANION_QTY)
            state.history.append({"role": "assistant", "content": response})
            return response

    # Red anti-BUCLE para SLOT_COMPANION_QTY (2026-07-24): el bloque Fase C de
    # abajo se EXCLUYE a propósito cuando hay `pending_companion_activity`, así
    # que una cantidad de acompañante no-canónica ("un par", "los dos", "just
    # the two of them") no tenía red y re-preguntaba en bucle — asimetría con
    # SLOT_QTY, que sí la tiene. Mismo resolutor LLM, con el mismo guard que
    # `_apply_short_answer`/SLOT_COMPANION_QTY: si el mensaje menciona OTRO
    # producto distinto al preguntado, no se resuelve aquí (el número podría
    # ser de esa otra actividad, no del acompañante preguntado).
    # (Se gatea por `not resolved_short`, no por `not advanced`: la cantidad de
    # acompañante NO la rastrea `next_missing_slot`, así que con la reserva
    # principal ya completa `advanced` es espuriamente True — el guard correcto
    # es "el parser canónico no lo resolvió y el acompañante sigue pendiente".)
    if (
        not resolved_short
        and prev_pending == SLOT_COMPANION_QTY
        and state.pending_companion_activity
        and not _looks_like_question(message)
    ):
        act = state.pending_companion_activity
        mentioned = _mentioned_product_activities(message)
        if not (mentioned and act not in mentioned):
            resolved = await resolve_slot_answer("companion_qty", message, lang=state.language)
            val = resolved.get("value")
            if isinstance(val, int) and val > 0:
                _merge_companion_activity(state, act, val)
                state.pending_companion_activity = None
                advanced = True

    # Red anti-BUCLE para SLOT_COMPANION_ACTIVITY (2026-07-24): "¿minicurso o
    # snorkel para tu acompañante?" respondido de forma no-canónica ("que se
    # quede arriba viendo peces", "que se anime a bajar") lo resuelve el LLM
    # (enum snorkel/minicourse). Bloque dedicado por el mismo motivo que
    # companion_qty (next_missing_slot no lo rastrea → `advanced` no vale).
    if (
        not resolved_short
        and prev_pending == SLOT_COMPANION_ACTIVITY
        and not state.pending_companion_activity
        and not _looks_like_question(message)
    ):
        resolved = await resolve_slot_answer(SLOT_COMPANION_ACTIVITY, message, lang=state.language)
        if _apply_resolved_slot_value(state, SLOT_COMPANION_ACTIVITY, resolved.get("value")):
            advanced = True

    # Red anti-BUCLE de slot (Fase C, 2026-07-23): si el turno NO avanzó y el
    # slot pendiente es booleano/escalar, el cliente pudo haber respondido de
    # forma válida pero no-canónica que el parser de `_apply_short_answer` no
    # reconoció ("uf, hace muchísimo" para seguridad, "vivo en bogotá" para
    # nacionalidad, "un par" para cantidad). Sin esto, el núcleo re-pregunta el
    # MISMO slot para siempre. El LLM interpreta la respuesta EN EL CONTEXTO de
    # la pregunta concreta; si se abstiene, se cae al re-preguntar de siempre
    # (nunca peor que hoy). No se dispara si el mensaje parece una pregunta de
    # info (eso va a RAG, abajo) ni si ya hay un acompañante pendiente.
    if (
        not advanced
        and prev_pending in _LLM_RESOLVABLE_SLOTS
        and not _looks_like_question(message)
        and not state.pending_companion_activity
    ):
        resolved = await resolve_slot_answer(prev_pending, message, lang=state.language)
        if "value" in resolved and _apply_resolved_slot_value(state, prev_pending, resolved["value"]):
            advanced = True

    # Última red antes del genérico: heurística blanda de pregunta de info
    # (sin exigir "?", ya descartado arriba) — mismo camino RAG de siempre.
    if not advanced and _looks_like_question(message):
        answer = greeting + await _answer_question(state, message)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # RESOLVER + RESPONDER.
    #
    # Bug en vivo 2026-07-23 (matriz EN de multi-ítem): si este turno NO
    # resolvió la pregunta de cantidad de un acompañante pendiente (p. ej.
    # el mensaje mencionaba OTRA actividad distinta a la preguntada — guarda
    # nueva en `_apply_short_answer`/SLOT_COMPANION_QTY — y cayó de largo
    # hasta aquí), `next_missing_slot()` NO conoce en absoluto
    # `pending_companion_activity`/`pending_companion_queue`: sin este
    # chequeo, `core_pending_slot` se sobreescribía con el siguiente slot
    # "normal" (ubicación, seguridad...) dejando la pregunta de acompañante
    # huérfana — el estado seguía "pensando" que faltaba responderla pero
    # nada volvía a preguntarla nunca. Se prioriza sobre next_missing_slot
    # igual que el resto de comprobaciones de este bloque multi-ítem.
    if state.pending_companion_activity:
        response = ask_slot(state, SLOT_COMPANION_QTY, reasking=True)
        state.step = Step.FREE_TEXT
    elif state.pending_companion_queue:
        state.pending_companion_activity = state.pending_companion_queue.pop(0)
        response = ask_slot(state, SLOT_COMPANION_QTY)
        state.step = Step.FREE_TEXT
    elif prev_pending == SLOT_COMPANION_ACTIVITY and not resolved_short:
        # La actividad del acompañante seguía pendiente y este turno no la
        # resolvió (deferral "lo que sea mejor" que el LLM no fija): re-preguntar
        # en vez de caer al resumen y PERDER al acompañante (hallazgo en vivo
        # 2026-07-24). `next_missing_slot` no rastrea este slot, de ahí el guard
        # explícito antes de dejar que sobrescriba `core_pending_slot`.
        #
        # Auditoría 2026-08-26 (batería sintética contra PRE): re-preguntar
        # INCONDICIONALMENTE aquí entraba en BUCLE — seguía repitiendo la
        # MISMA pregunta para siempre, incluso cuando había otras preguntas
        # obligatorias (seguridad, nacionalidad) todavía sin responder por
        # detrás, enterradas sin posibilidad de llegar a plantearse nunca.
        # Ahora se distingue: si el resto de la reserva YA está completa,
        # repreguntar aquí mismo (si no, se pierde el acompañante al
        # cerrar); si todavía falta algo más, se deja avanzar a por ello
        # primero y se marca `companion_activity_deferred` (NO
        # `needs_companion_activity` — ese otro flag es para la detección
        # FRESCA del turno actual, se consume de inmediato justo tras
        # `_understand()`, y usarlo aquí también haría que ese chequeo
        # temprano interceptara el turno SIGUIENTE antes de procesar la
        # respuesta a la pregunta realmente pendiente) para retomar el
        # acompañante justo antes de cerrar (ver el chequeo equivalente en
        # el `if nxt is None` de abajo) — nunca se pierde, pero tampoco
        # bloquea el resto de la reserva.
        nxt_now = next_missing_slot(state)
        if nxt_now is None:
            response = ask_slot(state, SLOT_COMPANION_ACTIVITY, reasking=True)
            state.step = Step.FREE_TEXT
        else:
            state.companion_activity_deferred = True
            response = ask_slot(state, nxt_now, reasking=(nxt_now == prev_pending))
            state.step = Step.FREE_TEXT
    else:
        nxt = next_missing_slot(state)
        if nxt is None:
            if state.companion_activity_deferred:
                # Ya se cerró el hueco que interrumpió la pregunta del
                # acompañante (seguridad/nacionalidad/etc.) — se retoma
                # ahora, antes de cerrar, en vez de darla por perdida.
                state.companion_activity_deferred = False
                response = ask_slot(state, SLOT_COMPANION_ACTIVITY, reasking=True)
                state.step = Step.FREE_TEXT
            else:
                response = _finalize(state)
                # Materializar la nota de lead (el cierre no-colombiano deja solo
                # pending_lead_note_reason; en el camino legacy la construye
                # _finalize_tree_response — aquí el equivalente).
                supervisor._maybe_build_pending_note(state)
        else:
            response = ask_slot(state, nxt, reasking=(nxt == prev_pending))
            state.step = Step.FREE_TEXT

    # Envoltorio cálido (Parte 2 del plan): en los turnos posteriores al saludo,
    # reconocer con calidez lo que el cliente acaba de decir ANTES de encadenar la
    # pregunta/dato (el "responde-y-encadena" que se había perdido). Los datos DUROS
    # (precio/links/plan/seguridad/resumen) ya están en `response` y NO pasan por el
    # LLM; el acuse solo pone el envoltorio. Si falla o se salta las reglas -> "".
    ack = ""
    if not first_turn:
        ack = await compose_acknowledgement(
            message,
            state_summary=_booking_context_summary(state),
            client_name=state.client_name,
            lang=state.language,
        )
        if ack:
            ack = ack.rstrip() + "\n\n"
    response = greeting + ack + response
    state.history.append({"role": "assistant", "content": response})
    return response


async def _answer_question(
    state: ConversationState, message: str, *, rag_query: str | None = None,
) -> str:
    # Vía supervisor.rag_answer (no rag_agent directamente): es la referencia
    # que mockean los tests y cualquier interceptor futuro — mismo camino que
    # el resto de respuestas de info del bot. `rag_query` (opcional): consulta
    # reescrita para RAG cuando el mensaje crudo recupera mal (deliberación);
    # el historial sigue teniendo el mensaje real del cliente.
    from src.agents import supervisor  # lazy

    extra_context = supervisor._build_extra_context(state)
    answer = await supervisor.rag_answer(
        rag_query or message, lang=state.language, history=state.history,
        extra_context=extra_context,
    )
    pending = state.core_pending_slot or next_missing_slot(state)
    # No re-anclar el slot si la propia respuesta RAG ya cierra con una
    # pregunta (una recomendación/comparación termina invitando a elegir): el
    # re-prompt sería redundante — dos preguntas seguidas y, si el pendiente
    # es la actividad, el menú entero pegado a una respuesta que ya lo cubría
    # (fallo en vivo 2026-07-24). El re-ancla usa la variante corta.
    if pending is not None and not _answer_already_asks(answer):
        follow_up = ask_slot(state, pending, reasking=True)
        return f"{answer}\n\n{follow_up}"
    # Aun sin re-preguntar, dejar fijado el slot pendiente para el próximo turno
    # (el carryover lo retoma) y limpiar los quick-replies del turno anterior:
    # la respuesta ya cierra con su propia pregunta, botones stale confundirían.
    state.core_pending_slot = pending
    state.quick_replies = []
    return answer


def _answer_already_asks(answer: str) -> bool:
    """¿La respuesta ya termina invitando a responder (cierra con una
    pregunta)? Mira la última línea no vacía — así una recomendación que
    acaba en "¿te inclinas por alguna?" no recibe encima el re-prompt del
    slot. Barato y seguro: un falso negativo solo re-adjunta la variante
    corta, nunca vuelve al bloque entero."""
    for line in reversed(answer.strip().splitlines()):
        if line.strip():
            return "?" in line or "¿" in line
    return False
