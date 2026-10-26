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

import asyncio
import logging
import re

from src.agents.intent_detector import (
    courses_mentioned,
    matched_activity_categories,
)
from src.agents.notes_extractor import extract_notes
from src.domain import activities as dom
from src.flows import cart_render, eligibility, moneda
from src.flows.state import ConversationState, Step
from src.utils.fuzzy import is_affirmative, is_agree
from src.utils.number_words import number_alt
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")

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
# Curso o especialidad sin nivel (padi_course / padi_specialty): el bot pregunta
# cual, con las opciones del registro de actividades (F4, decision del owner).
SLOT_COURSE_LEVEL = "course_level"
SLOT_CERT_OR_COURSE = "cert_or_course"
# "Antes me dijiste X, ¿lo cambio a Y?" (tarea 7b, owner 2026-09-15).
SLOT_CONFIRM_CORRECTION = "confirm_correction"


# SLOT_COMPANION_QTY y SLOT_COMPANION_ACTIVITY NO van aquí: `next_missing_slot`
# no los rastrea, así que con la reserva principal ya resuelta `advanced` es
# espuriamente True y el bloque genérico Fase C (gate `not advanced`) los
# saltaría. Tienen bloques dedicados en maybe_handle_turn (gate `not
# resolved_short`).


# Desde el catalogo (`dom.dive_packages`, 2026-09-15). Con solo los dias se elige el
# paquete mas grande de esa duracion (2 dias -> 5 inmersiones), como antes.
_DIVES_TO_BASE_PLAN = {dives: service for dives, (_, service) in dom.dive_packages().items()}
_DAYS_TO_DIVES = {
    days: max(dives for dives, (pkg_days, _) in dom.dive_packages().items() if pkg_days == days)
    for days, _ in dom.dive_packages().values() if days > 1
}


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


def _group_allocation_fully_resolved(state: ConversationState) -> bool:
    """True si `detected_group_allocation` ya explica a TODO el grupo (su suma
    cubre `detected_group_size`) — circuit-breaker (portado 2026-09-01,
    hallazgo en vivo, batería de grupos mixtos contra PRE, lote 8): con un
    reparto ya completo (p. ej. "2 certificados, 2 minicurso, 2 snorkel"
    para un grupo de 6), el mecanismo de acompañante-ambiguo seguía
    disparándose por alguna vía (no aislada con certeza total ni siquiera
    con trazas de LangSmith — la lógica determinista involucrada no deja
    rastro de LLM que inspeccionar), preguntando "¿qué le gustaría hacer a
    tu acompañante?" pese a que no queda NADIE sin actividad asignada. Si el
    reparto ya cubre a todo el grupo, no hay ningún acompañante posible que
    preguntar — sea cual sea la vía que intente disparar esa pregunta.

    NO ampliar esto a "la reserva ya está lista para cerrar" (intentado y
    revertido, lote 10, 2026-09-02): un grupo homogéneo sin reparto puede
    seguir recibiendo un acompañante NUEVO legítimo después de cerrar todos
    los slots core ("mi amigo también quiere venir") — `next_missing_slot`
    en `None` no implica que ya no pueda aparecer nadie más. Ver el fix real
    del hallazgo de cierre en `_understand()` (guard de "misma actividad").
    """
    alloc = state.detected_group_allocation
    if not alloc:
        return False
    size = state.detected_group_size
    if not size:
        return False
    # Un reparto que no contiene la actividad principal no la explica (tarea 7a,
    # 2026-09-15): "él quiere hacer snorkel" pisa la principal y {certified_diving: 2}
    # seguia "cubriendo" el grupo, asi que la red de precision no llegaba a correr.
    if state.detected_activity in _ACTIVITY_TO_CART_TYPE and state.detected_activity not in alloc:
        return False
    return sum(alloc.values()) >= size


def _course_level_options(state: ConversationState) -> list[str]:
    """Opciones concretas para un curso/especialidad sin nivel: las actividades del
    registro de la misma familia que la generica pendiente, reservables (con tipo
    de carrito), ordenadas por nivel de curso. Salen del registro, no de una lista."""
    current = dom.by_id(state.detected_activity) if state.detected_activity else None
    family = current.family if current else "course"
    options = [
        a for a in dom.registry().activities
        if a.family == family and not a.generic and a.cart_type and a.sold_as is None and a.offer
    ]
    return [a.id for a in sorted(options, key=lambda a: (a.course_level is None, a.course_level or 0))]


def _set_concrete_activity(state: ConversationState, activity_id: str) -> None:
    """Fija la actividad concreta elegida y su servicio desde el registro."""
    state.detected_activity = activity_id
    state.detected_service_id = dom.base_service_id(activity_id)


def _companion_activity_options(state: ConversationState) -> list[str]:
    """Lo que el bot RECOMIENDA a un acompañante que no dijo qué quiere hacer
    (owner 2026-09-14: "no podemos dar por hecho; recomendamos si entendemos la
    situación, pero el cliente elige").

    Base: las opciones de un principiante de `eligibility` (minicurso, snorkel e ir
    de acompañante). El curso Open Water se añade solo si se sabe que se quedan
    varios días: certificarse no cabe en un día."""
    options = [eligibility.option_activity_id(o) for o in eligibility.beginner_options_for_age(None)]
    if state.detected_duration == "multi_day" and "minicourse" in options:
        options.insert(options.index("minicourse") + 1, "padi_open_water")
    return [o for o in options if dom.by_id(o) is not None]


# EX-FLUJO-1 (decisión de Gadea, 14-oct): las preguntas que se pueden dejar para antes del resumen si el cliente no
# las contesta. No condicionan a otras; la actividad, la certificación y las confirmaciones sí, y no se aplazan.
_SLOTS_APLAZABLES = frozenset({
    SLOT_LOCATION, SLOT_HOTEL, SLOT_QTY, SLOT_SAFETY, SLOT_REFRESHER, SLOT_AGES, SLOT_NATIONALITY,
})


def refresh_en_el_grupo(state: ConversationState) -> bool | None:
    """¿Alguien del grupo lleva más de 2 años sin bucear? None si aún no se sabe.

    gen-7 (20-oct): la pregunta de seguridad es de GRUPO ("¿… de alguno del grupo?") y el
    refresher se cobra "por persona que lo necesite", pero solo contaba quien escribe (`last_dive_over_2_years`).
    "Sí, uno de nosotros no bucea desde hace 4 años" lo guardaba el extractor como de OTRA persona
    (`acompanante_certificado_inactivo`) y la pregunta se repetía sin llegar nunca al refresher."""
    if state.last_dive_over_2_years or state.acompanante_certificado_inactivo:
        return True
    return state.last_dive_over_2_years


def next_missing_slot(state: ConversationState, saltar: frozenset[str] | set[str] = frozenset()) -> str | None:
    """El ÚNICO slot obligatorio que falta, o None si la reserva está lista
    para el resumen + links. Lógica pura: no muta el estado. `saltar`: slots
    aplazados (EX-FLUJO-1) que no se preguntan mientras falte otro; solo los de
    `_SLOTS_APLAZABLES`."""
    saltar = frozenset(saltar) & _SLOTS_APLAZABLES
    act = state.detected_activity
    if act is None:
        return SLOT_ACTIVITY
    if state.pending_companion_in_group:
        # ¿Esa persona ya estaba contada o se suma? Antes de cotizar (tarea 7a).
        return SLOT_QTY
    if state.pending_correction:
        # Un dato que contradice lo guardado, sin cue: se confirma antes de cotizar (7b).
        return SLOT_CONFIRM_CORRECTION
    if state.needs_cert_or_course:
        # Nivel PADI nombrado sin decir si ya lo tienen o lo quieren (owner
        # 2026-09-15): se aclara antes de cotizar nada.
        return SLOT_CERT_OR_COURSE
    activity = dom.by_id(act)
    if activity is not None and activity.generic:
        # Curso/especialidad sin nivel: nunca se cierra sin decidir cual (antes
        # acababa en un curso sin precio ni link). F4 del plan de dominio.
        return SLOT_COURSE_LEVEL
    if act == "certified_diving" and state.is_certified is None and not (
        state.detected_group_allocation or {}
    ).get("certified_diving"):
        # Un reparto explícito ("3 certificados y 2 snorkel") ya dice quién está
        # certificado — la pregunta genérica sobraría.
        return SLOT_CERTIFICATION
    if not state.location and SLOT_LOCATION not in saltar:
        return SLOT_LOCATION
    if state.location == "island" and not state.hotel and SLOT_HOTEL not in saltar:
        return SLOT_HOTEL
    # Plan: no se pregunta — se recomienda el más popular (decisión owner
    # v0.20.27) y el cliente puede cambiarlo por texto en cualquier momento.
    #
    # CANTIDAD antes que SEGURIDAD (decisión owner 2026-07-22, se desvía del
    # orden escrito en conversational-refactor-plan.md): preguntando primero
    # cuántos son, la pregunta de los 2 años ya sabe si dirigirse en singular o
    # en plural en vez de adivinar — en vivo se veía "¿tu última inmersión?" a
    # un grupo cuyo tamaño aún no se había preguntado.
    if not state.detected_group_size and not state.detected_group_allocation and SLOT_QTY not in saltar:
        return SLOT_QTY
    if _cart_will_include_cert(state):
        refresh = refresh_en_el_grupo(state)
        if refresh is None and SLOT_SAFETY not in saltar:
            return SLOT_SAFETY
        if refresh and state.refresher_interested is None and SLOT_REFRESHER not in saltar:
            return SLOT_REFRESHER
    if state.kids_mention_detected and not state.detected_ages and SLOT_AGES not in saltar:
        return SLOT_AGES
    if state.is_colombian is None and SLOT_NATIONALITY not in saltar:
        return SLOT_NATIONALITY
    return None


def _es_la_ultima_pregunta(state: ConversationState) -> bool:
    """La nacionalidad es la última pregunta salvo que haya otra aplazada aún sin contestar (EX-FLUJO-1)."""
    if not state.preguntas_aplazadas:
        return True
    return next_missing_slot(state, saltar=frozenset({SLOT_NATIONALITY})) in (None, SLOT_NATIONALITY)


_NAME_STOPWORDS = frozenset({
    "certificado", "certificada", "certificados", "certificadas", "buzo", "buza",
    "buzos", "buceador", "buceadora", "colombiano", "colombiana", "colombianos",
    "extranjero", "extranjera", "principiante", "instructor", "instructora",
    "turista", "estudiante", "nuevo", "nueva", "mayor", "menor", "de", "un", "una",
    "open", "advanced", "rescue", "divemaster", "nitrox", "padi", "el", "la",
    "certified", "diver", "tourist", "beginner", "colombian", "resident", "solo",
    "sola", "el", "la", "yo",
    # Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 8, portado
    # de pre_gadea v0.21.6): "soy del equipo de pruebas..." capturaba "del"
    # (contracción de "de"+"el", no cubierta por el "de" ya excluido) como
    # si fuera un nombre propio -> saludo "¡Hola, Del!". Añadidas otras
    # palabras funcionales cortas del mismo riesgo que podrían seguir a
    # "soy" sin ser un nombre.
    "del", "al", "los", "las", "muy", "así", "asi", "bien", "aquí", "aqui", "ya", "que",
})


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
            f"{saludo} Soy *Coral*, de *Diving Planet* — buceamos todo el año en "
            "las Islas del Rosario, saliendo desde Cartagena o desde las propias islas. "
            "¡Qué alegría tenerte por acá! Con muchísimo gusto te ayudo a armar tu plan. 🌊\n\n"
        )
    saludo = f"Hi, {name}! 🪸" if name else "Hi! 🪸"
    return (
        f"{saludo} I'm *Coral* from *Diving Planet* — we dive year-round in the Rosario "
        "Islands, departing from Cartagena or right from the islands. So happy to have "
        "you here! I'd love to help you put your plan together. 🌊\n\n"
    )


# ─── RESPONDER: redactor de slot (determinista, ES/EN, cierre a conversión) ───

def _minicurso_ya_recomendado(state: ConversationState) -> bool:
    """CAL-C1: si algún mensaje del bot ya trae la recomendación entera del minicurso."""
    marcas = ("te recomiendo el *minicurso*", "I'd recommend the *mini-course*")
    return any(m in (t.get("content") or "") for t in (state.history or []) if t.get("role") == "assistant"
               for m in marcas)


# gen-8 (`actividad_de_la_pregunta`): productos genéricos ("un curso PADI", "una especialidad"): no hay uno que ofrecer.
_SIN_OFERTA_CONCRETA = ("padi_course", "padi_specialty")


def _ofrecer_la_actividad_preguntada(state: ConversationState) -> str | None:
    """gen-8: quien pregunta por UNA actividad sin elegirla recibe la oferta de esa, no el menú de 4 (textos-B). La
    elige el cliente: "sí" confirma la recomendación (`suggested_activity`, nucleo/routing)."""
    actividad = state.actividad_preguntada
    if not actividad or actividad in _SIN_OFERTA_CONCRETA:
        return None
    if not state.detected_activity and actividad in (state.detected_group_allocation or {}):
        # DEUDA-EXT (26-oct): es la actividad de los que se suman ("vienen dos amigos que quieren probar el minicurso"),
        # no una oferta para el grupo que aún no ha elegido la suya (banco-lat11 a4: se ofrecía el minicurso a 3 buzos).
        return None
    if state.suggested_activity and state.suggested_activity != actividad:
        return None
    lang = state.language
    state.suggested_activity = actividad
    nombre = dom.label(actividad, lang)
    state.quick_replies = [{"title": "✅ Sí, quiero reservar" if lang == "es" else "✅ Yes, let's book it",
                            "value": "sí" if lang == "es" else "yes"}]
    return (f"Si quieres, te ayudo a reservar: *{nombre}*. ¿Te animas? 🌊" if lang == "es" else
            f"If you'd like, I can help you book it: *{nombre}*. Shall we? 🌊")


def _ow_plan() -> tuple[dict, dict]:
    """La ficha y la fila de la tarifa del Open Water desde Cartagena (lat-deuda-u: sus días e inmersiones salen de ahí,
    no de un texto fijo)."""
    from src.flows.catalog import RAW_SERVICES, fila_de_la_tarifa  # lazy

    ficha = RAW_SERVICES[dom.service_ids("padi_open_water", "cartagena")[0]]
    return ficha, fila_de_la_tarifa(ficha["tarifa"])


def _ow_dias() -> int:
    return _ow_plan()[0]["duration_days"]


def _ow_inmersiones() -> int:
    return _ow_plan()[1]["num_dives"]


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

    if slot == SLOT_ACTIVITY and (oferta := _ofrecer_la_actividad_preguntada(state)):
        return oferta
    if (slot == SLOT_ACTIVITY and state.quiere_bucear
            and not state.suggested_activity and not state.detected_group_allocation):
        # CAL-C1 (16-oct; regla de Gadea 14/27-sep: recomendar según lo que se sabe). Quien ya dijo que quiere bucear
        # recibía el menú entero ("5 inmersiones", "Muchas gracias!", "no estamos certificados" → "¿Con cuál te
        # animas — buceo, minicurso, snorkel…?"; banco CAL, 10 casos). Sabiendo que quiere bucear, lo que falta es la
        # certificación: sin certificación se recomienda el minicurso (lo confirma el cliente); sin saberla, se pregunta.
        certificado = _known_field_values(state).get("is_certified")
        if certificado is False:
            state.suggested_activity = "minicourse"
        elif certificado is None:
            return ask_slot(state, SLOT_CERTIFICATION, reasking=reasking)
    if (slot == SLOT_ACTIVITY and state.suggested_activity == "minicourse"
            and reasking and not _minicurso_ya_recomendado(state)):
        # La recomendación entera la primera vez que se hace (la corta "¿minicurso u Open Water?" no recomendaba:
        # cal-60, también cuando la recomendación se había apuntado en un turno anterior sin llegar a decirse).
        reasking = False

    if slot == SLOT_ACTIVITY and state.suggested_activity == "padi_open_water":
        # Quien pide un curso desde cero: se recomienda el Open Water y el minicurso queda como opcion.
        state.quick_replies = (
            [{"title": "✅ Sí, el Open Water", "value": "curso open water"},
             {"title": "🤿 Mejor el minicurso", "value": "minicurso"}]
            if lang == "es" else
            [{"title": "✅ Yes, Open Water", "value": "open water course"},
             {"title": "🤿 The mini-course instead", "value": "mini course"}]
        )
        if reasking:
            return (
                "¿Te animas con el *curso Open Water* o prefieres probar antes con el *minicurso*? 🌊"
                if lang == "es" else
                "Shall we go for the *Open Water course*, or would you rather try the *mini-course* first? 🌊"
            )
        return (
            f"Para certificarte desde cero, el curso es el *PADI Open Water*: {_ow_dias()} días en las Islas del "
            f"Rosario con teoría online, piscina y {_ow_inmersiones()} inmersiones. Si antes prefieres probar, está el "
            "*minicurso*, sin "
            "necesidad de experiencia. ¿Te animas con el Open Water? 🤿"
            if lang == "es" else
            f"To get certified from scratch, the course is the *PADI Open Water*: {_ow_dias()} days in the Rosario "
            f"Islands with online theory, pool and {_ow_inmersiones()} dives. If you'd rather try first, there's the "
            "*mini-course*, no "
            "experience needed. Shall we go for the Open Water? 🤿"
        )
    if slot == SLOT_ACTIVITY and state.suggested_activity == "minicourse":
        # u3-5: recomendar el minicurso a quien empieza, y que lo confirme el cliente (Gadea, 27-sep).
        state.quick_replies = (
            [{"title": "✅ Sí, el minicurso", "value": "minicurso"},
             {"title": "🎓 El curso Open Water", "value": "curso open water"}]
            if lang == "es" else
            [{"title": "✅ Yes, the mini-course", "value": "mini course"},
             {"title": "🎓 The Open Water course", "value": "open water course"}]
        )
        if reasking:
            # CAL-C1: la corta también recomienda (cal-60: "¿minicurso u Open Water?" no se leía como recomendación).
            return (
                "Para empezar, lo ideal es el *minicurso*: no hace falta experiencia ni certificación. ¿Te animas? "
                "(Si prefieres certificarte, está el *curso Open Water*.) 🤿"
                if lang == "es" else
                "To start, the *mini-course* is the ideal choice: no experience or certification needed. Shall we go "
                "for it? (If you'd rather get certified, there's the *Open Water course*.) 🤿"
            )
        return (
            "Para una primera vez te recomiendo el *minicurso*: teoría, práctica en aguas tranquilas y una "
            "inmersión en el mar con instructor, sin necesidad de experiencia. Si lo que buscas es "
            "certificarte, está el *curso PADI Open Water*. ¿Te animas con el minicurso? 🤿"
            if lang == "es" else
            "For a first time I'd recommend the *mini-course*: theory, practice in calm water and a sea dive "
            "with an instructor, no experience needed. If you want to get certified, there's the *PADI Open "
            "Water course*. Shall we go for the mini-course? 🤿"
        )
    if slot == SLOT_ACTIVITY and state.is_certified is True:
        # 14-oct (ronda flujo1-B3): a quien ya dijo que es buzo certificado se le ofrecía el menú entero (minicurso,
        # snorkel…) y el juez lo marcaba como repregunta. Regla de Gadea (14/27-sep): recomendar según el contexto, y
        # que elija el cliente: para un certificado, la salida de 2 inmersiones, los paquetes o un curso avanzado.
        state.quick_replies = (
            [{"title": "🤿 Salida de 2 inmersiones", "value": "buceo certificado"},
             {"title": "📅 Paquete de varios días", "value": "paquete de buceos"},
             {"title": "🎓 Curso avanzado", "value": "curso advanced"}]
            if lang == "es" else
            [{"title": "🤿 2-dive trip", "value": "certified diving"},
             {"title": "📅 Multi-day package", "value": "dive package"},
             {"title": "🎓 Advanced course", "value": "advanced course"}]
        )
        if reasking:
            return (
                "¿Te animas con la *salida de 2 inmersiones*, un *paquete de varios días* o un *curso avanzado*? 🌊"
                if lang == "es" else
                "Shall we go for the *2-dive trip*, a *multi-day package* or an *advanced course*? 🌊"
            )
        return (
            "Como ya eres buzo certificado, te propongo la *salida de 2 inmersiones* en las Islas del Rosario; si "
            "quieres más días, hay *paquetes de varias inmersiones*, y si buscas subir de nivel, el *curso Advanced* "
            "o una especialidad. ¿Cuál te interesa? 🤿"
            if lang == "es" else
            "Since you're already a certified diver, I'd suggest the *2-dive trip* in the Rosario Islands; for more "
            "days there are *multi-dive packages*, and to level up, the *Advanced course* or a specialty. Which one "
            "interests you? 🤿"
        )
    if (slot == SLOT_ACTIVITY and state.is_certified is False
            and not state.suggested_activity):
        # 18-oct (ronda mod-F): el simétrico de `recomendar_a_certificados`. A quien sabemos que NO es certificado y no
        # ha elegido ("Sería buzo principiante y snorkeling": el extractor no elige actividad en un mensaje ambiguo) se
        # le repetía el menú entero, con "buceo" (solo para certificados) incluido. Regla de Gadea: recomendar según lo
        # que se sabe y que elija el cliente, sin adivinar la actividad.
        state.quick_replies = (
            [{"title": "🤿 Minicurso", "value": "minicurso"},
             {"title": "🐠 Snorkel", "value": "snorkel"},
             {"title": "🎓 Curso Open Water", "value": "curso open water"}]
            if lang == "es" else
            [{"title": "🤿 Mini-course", "value": "mini course"},
             {"title": "🐠 Snorkeling", "value": "snorkeling"},
             {"title": "🎓 Open Water course", "value": "open water course"}]
        )
        if reasking:
            return (
                "¿Te animas con el *minicurso*, el *snorkel* o el *curso Open Water*? 🌊"
                if lang == "es" else
                "Shall we go for the *mini-course*, *snorkeling* or the *Open Water course*? 🌊"
            )
        return (
            "Sin certificación, para bucear lo ideal es el *minicurso*: no hace falta experiencia y vas con un "
            "instructor. Si prefieres disfrutar el arrecife desde la superficie, está el *snorkel*, y si quieres "
            "certificarte, el *curso PADI Open Water*. ¿Cuál te interesa? 🤿"
            if lang == "es" else
            "Without a certification, the *mini-course* is the ideal way to dive: no experience needed and you go "
            "with an instructor. To enjoy the reef from the surface there's *snorkeling*, and to get certified, the "
            "*PADI Open Water course*. Which one interests you? 🤿"
        )
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
    if slot == SLOT_CERT_OR_COURSE:
        state.quick_replies = (
            [{"title": "✅ Ya la tenemos", "value": "already_certified"},
             {"title": "🎓 Queremos sacarla", "value": "wants_course"}]
            if lang == "es" else
            [{"title": "✅ We already have it", "value": "already_certified"},
             {"title": "🎓 We want to get it", "value": "wants_course"}]
        )
        level = state.cert_or_course_level
        name = dom.label(level, lang) if level else None
        if lang == "es":
            what = f"el *{name}*" if name else "esa certificación"
            return f"Para recomendarte bien: ¿ya tienen {what} o quieren sacarla con el curso? 🤿"
        what = f"the *{name}*" if name else "that certification"
        return f"So I can recommend the right plan: do you already hold {what}, or do you want to get it with the course? 🤿"
    if slot == SLOT_COURSE_LEVEL:
        options = _course_level_options(state)
        current = dom.by_id(state.detected_activity) if state.detected_activity else None
        is_specialty = bool(current and current.family == "specialty")
        state.quick_replies = [{"title": dom.label(o, lang), "value": o} for o in options]
        lines = []
        for option in options:
            pitch = dom.text(option, "pitch", lang)
            lines.append(f"• *{dom.label(option, lang)}*" + (f" — {pitch}" if pitch else ""))
        if lang == "es":
            head = "¿Qué especialidad te interesa? 🐠" if is_specialty else "¿Qué curso te interesa? 🎓"
        else:
            head = "Which specialty are you interested in? 🐠" if is_specialty else "Which course are you interested in? 🎓"
        return head + "\n" + "\n".join(lines)
    if slot == SLOT_CERTIFICATION:
        plural = (state.detected_group_size or 1) > 1
        if lang == "es":
            q = ("¿Son buzos certificados?" if plural
                 else "¿Eres buzo certificado?")
            return (f"¡Genial! Para recomendarte el plan perfecto: {q} "
                    + "(Y si no, ¡tranqui! El minicurso es ideal para empezar. 🤿)")
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
        if _plan_en_duda(state):
            # CAL-F (flag `origen_neutro_con_dos_planes`): duda entre dos planes; ninguno se afirma (ver `_plan_en_duda`).
            return _pregunta_origen(lang)
        if _plan_needs_overnight(state):
            # Politica `courses_overnight_requirement` / paquetes de varios dias: hay que dormir en
            # las islas; ofrecer "ida y vuelta el mismo dia" contradecia la referencia (ronda A).
            # CAL-D (17-oct, cal-74): los días EXACTOS de la ficha del plan ("dura 2 días"); "varios
            # días" solo cuando aún no se sabe qué plan es (un paquete sin concretar: de 2 a 4 días).
            dias = _dias_del_plan(state)
            return (
                f"¿Desde dónde saldrías? Este plan dura {(f'{dias} día' if dias == 1 else f'{dias} días') if dias else 'varios días'} y hay "
                "que *dormir en las islas* (el alojamiento no está incluido): puedes salir *desde Cartagena* "
                "el primer día o, si ya estás *en las islas*, coordinamos la recogida en tu hotel."
                if lang == "es" else
                f"Where would you be departing from? This plan takes {(f'{dias} day' if dias == 1 else f'{dias} days') if dias else 'several days'} "
                "and you need to *stay on the islands* (accommodation is not included): you can leave *from "
                "Cartagena* on the first day or, if you're already *on the islands*, we arrange pickup at your "
                "hotel."
            )
        if not _plan_is_single_day(state):
            # Paso 6 (ronda B): con la actividad sin concretar ("curso básico" -> curso PADI generico)
            # se ofrecia "ida y vuelta el mismo dia" a un Open Water. Solo se afirma si se sabe.
            return _pregunta_origen(lang)
        return _pregunta_origen(lang, mismo_dia=True)
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
        # Se cobra (owner 2026-09-14): precio por persona desde el catalogo.
        price = cart_render.refresher_price_text(state, una_moneda=True)  # G3-07a
        # gen-7 (20-oct): lo que dice la base del refresher (ficha `refresher:minicourse` y `medical_restrictions`): se
        # reserva como el Minicurso de Buceo y usa el formulario médico de curso, aunque sea buzo certificado.
        plural = (state.detected_group_size or 1) > 1
        return (
            "El *refresher* es un repaso con instructor antes de volver a bucear: se reserva como *Minicurso de "
            f"Buceo* y cuesta *{price}* por persona que lo necesite. Lleva el formulario médico de curso (aunque "
            "estén certificados, el enlace llega con la reserva). "
            + ("¿Les interesa?" if plural else "¿Te interesa?")
            if lang == "es" else
            "The *refresher* is an instructor-led review before diving again: it is booked as the *Dive Mini "
            f"Course* and costs *{price}* per person who needs it. It uses the course medical form (even for "
            "certified divers; the link comes with the booking). Are you interested?"
        )
    if slot == SLOT_CONFIRM_CORRECTION and state.pending_correction:
        known = _known_field_values(state)
        lines = "\n".join(
            f"• {_describe_value(field, known.get(field), lang)} → *{_describe_value(field, value, lang)}*"
            for field, value in state.pending_correction.items()
        )
        state.quick_replies = (
            [{"title": "✅ Sí, cámbialo", "value": "sí"}, {"title": "↩️ No, como estaba", "value": "no"}]
            if lang == "es" else
            [{"title": "✅ Yes, change it", "value": "yes"}, {"title": "↩️ No, keep it", "value": "no"}]
        )
        return (
            f"Solo para confirmar, ¿lo cambio?\n{lines}"
            if lang == "es" else
            f"Just to confirm, should I change it?\n{lines}"
        )
    if slot == SLOT_QTY and state.pending_companion_in_group:
        pending = state.pending_companion_in_group
        total = state.detected_group_size or 0
        more = total + pending["qty"]
        label = dom.text(pending["activity"], "recall", lang, default=pending["activity"])
        state.quick_replies = (
            [{"title": f"Seguimos siendo {total}", "value": str(total)},
             {"title": f"Somos {more}", "value": str(more)}]
            if lang == "es" else
            [{"title": f"Still {total}", "value": str(total)},
             {"title": f"We're {more}", "value": str(more)}]
        )
        return (
            f"¡Anotado, *{label}*! Para cuadrar el precio: ¿seguís siendo *{total}* en total "
            "o se suma alguien más? 😊"
            if lang == "es" else
            f"Got it, *{label}*! To get the price right: are you still *{total}* in total, "
            "or is someone else joining? 😊"
        )
    if slot == SLOT_QTY:
        return (
            "¿Y para cuántas personas armamos el plan? Así te paso el precio exacto. 😊"
            if lang == "es" else
            "And how many people should I plan for? That way I can give you the exact price. 😊"
        )
    if slot == SLOT_COMPANION_QTY:
        act = state.pending_companion_activity
        label = dom.text(act, "recall", "es" if lang == "es" else "en", default=act or "")
        return (
            f"¿Cuántos serían para {label}? Así les cuento el plan exacto. 😊"
            if lang == "es" else
            f"How many people would that be for {label}? That way I can give you the exact plan. 😊"
        )
    if slot == SLOT_COMPANION_ACTIVITY:
        # Dos pasos, mismo slot pendiente: sin saber si se quedan uno o varios días
        # no se puede recomendar bien (el Open Water necesita varios), así que se
        # pregunta primero, como la nacionalidad o la ubicación. Con ese dato, se
        # recomiendan las opciones y el cliente elige.
        if state.detected_duration is None:
            state.quick_replies = (
                [{"title": "☀️ Un día", "value": "single_day"},
                 {"title": "🏝️ Varios días", "value": "multi_day"}]
                if lang == "es" else
                [{"title": "☀️ One day", "value": "single_day"},
                 {"title": "🏝️ Several days", "value": "multi_day"}]
            )
            if state.pending_undecided_qty:
                return (
                    "Para recomendar lo que mejor les encaje a quienes no están certificados: "
                    "¿van a estar *un solo día* o *varios días*? 🌊"
                    if lang == "es" else
                    "So I can recommend what suits those who aren't certified: will you be "
                    "here for *one day* or *several days*? 🌊"
                )
            return (
                "¡Qué bien que venga alguien más! 🌊 Para recomendarle lo que mejor le "
                "encaje: ¿van a estar *un solo día* o *varios días*?"
                if lang == "es" else
                "Great that someone else is coming! 🌊 So I can recommend what suits "
                "them best: will you be here for *one day* or *several days*?"
            )
        options = _companion_activity_options(state)
        state.quick_replies = [{"title": dom.label(o, lang), "value": o} for o in options]
        lines = []
        for option in options:
            pitch = dom.text(option, "pitch", lang)
            lines.append(f"• *{dom.label(option, lang)}*" + (f" — {pitch}" if pitch else ""))
        if state.pending_undecided_qty:
            plural = state.pending_undecided_qty > 1
            head = (
                ("Para quienes no están certificados te recomiendo estas opciones. ¿Cuál les apetece más? 🐠"
                 if plural else
                 "Para quien no está certificado te recomiendo estas opciones. ¿Cuál le apetece más? 🐠")
                if lang == "es" else
                ("For those who aren't certified I'd recommend these options. Which one do they like best? 🐠"
                 if plural else
                 "For the one who isn't certified I'd recommend these options. Which one do they like best? 🐠")
            )
        else:
            head = (
                "Para tu acompañante te recomiendo estas opciones. ¿Cuál le apetece más? 🐠"
                if lang == "es" else
                "For your companion I'd recommend these options. Which one do they like best? 🐠"
            )
        return head + "\n" + "\n".join(lines)
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
        # gen-4: "residente" se contestaba "sí, vivo aquí"; lo que cuenta es la nacionalidad o la cédula de extranjería
        # (policies.json, colombian_pricing). Sin género supuesto (SIN_GENERO_SUPUESTO).
        pregunta = (
            ("¿son de nacionalidad colombiana o tienen cédula de extranjería?" if plural
             else "¿eres de nacionalidad colombiana o tienes cédula de extranjería?")
            if lang == "es" else
            # Sin "resident" (Gonzalo, #852): "resident" se contestaba "I live here", el fallo de gen-4.
            # Sin explicar, «cédula de extranjería» quedaba en español en una respuesta en inglés (ronda gen14-B,
            # reserva-ingles idioma); decisión de Gadea (#1078): una explicación corta y sin «residents».
            ("are you Colombian nationals, or do you have a Colombian *cédula de extranjería* (Colombia's ID card "
             "for foreigners)?" if plural else
             "are you a Colombian national, or do you have a Colombian *cédula de extranjería* (Colombia's ID card "
             "for foreigners)?")
        )
        if lang == "es":
            cabeza = ("Para darte el precio y el link correctos:" if not _es_la_ultima_pregunta(state)
                      else "Última cosa para darte el precio y el link correctos:")
        else:
            cabeza = ("So I can give you the right price and link:" if not _es_la_ultima_pregunta(state)
                      else "One last thing so I can give you the right price and link:")
        return f"{cabeza} {pregunta}"
    raise ValueError(f"unknown slot {slot!r}")


def _dias_del_plan(state: ConversationState) -> int | None:
    """Cuántos días dura el plan elegido, de la ficha (`duration_days` de services.json): el servicio ya
    resuelto, o la actividad si todos sus servicios duran lo mismo (Open Water y su referido: 2). None si
    no se sabe (sin plan, o un paquete sin concretar, que va de 2 a 4 días)."""
    from src.flows.catalog import RAW_SERVICES  # lazy

    def _dias(sid: str) -> int | None:
        return (RAW_SERVICES.get(sid) or {}).get("duration_days")

    if state.detected_service_id and _dias(state.detected_service_id):
        return _dias(state.detected_service_id)
    act = dom.by_id(state.detected_activity) if state.detected_activity else None
    dias = {_dias(sid) for sid in (act.all_services() if act else ())}
    return dias.pop() if len(dias) == 1 and None not in dias else None


def _pregunta_origen(lang: str, mismo_dia: bool = False) -> str:
    """La pregunta del origen (gen, 20-oct, textos en el español de Cartagena): desde Cartagena se sale del Muelle de la
    Bodeguita ("podemos recogerte saliendo desde Cartagena" sugería una recogida que no existe)."""
    if lang == "es":
        dia = ", ida y vuelta el mismo día" if mismo_dia else ""
        return (f"¿Desde dónde saldrías? Puedes salir *desde Cartagena* (desde el Muelle de la Bodeguita{dia}) o, si ya "
            "estás *en las islas*, coordinamos la recogida en tu hotel.")
    dia = ", round trip, same day" if mismo_dia else ""
    return (f"Where would you be departing from? You can leave *from Cartagena* (from Muelle de la Bodeguita{dia}) or, "
        "if you're already *on the islands*, we arrange pickup at your hotel.")


def _plan_en_duda(state: ConversationState) -> bool:
    """CAL-F (flag `origen_neutro_con_dos_planes`, 18-oct; precios-y-disponibilidad-con-negociacion, turno 3): "los
    valores de dos buceos o del pack de 5 buceos en 2 días" dejaba el servicio de un día (el de la actividad) y la
    duración de varios días (la del pack nombrado). La pregunta del origen mezclaba los dos: "Este plan dura 1 día y hay
    que dormir en las islas". Si el servicio es de un día y la duración dice varios, el plan no está elegido."""
    from src.flows.catalog import MULTI_DAY_SERVICES, OVERNIGHT_SERVICES  # lazy

    servicio = state.detected_service_id
    return bool(
        state.detected_activity == "certified_diving"
        and state.detected_duration == "multi_day" and servicio
        and servicio not in (MULTI_DAY_SERVICES | OVERNIGHT_SERVICES)
    )


def _plan_needs_overnight(state: ConversationState) -> bool:
    """¿El plan elegido obliga a dormir en las islas? Del catalogo (`OVERNIGHT_SERVICES`: varios dias
    o buceo nocturno, salvo los marcados "overnight": "optional", como el Curso Referido), no de una
    lista: el servicio ya resuelto, una actividad cuyos servicios obligan todos, o el paquete multi-dia
    que el cliente ya pidio."""
    from src.flows.catalog import OVERNIGHT_SERVICES  # lazy

    if state.detected_service_id and state.detected_service_id in OVERNIGHT_SERVICES:
        return True
    act = dom.by_id(state.detected_activity) if state.detected_activity else None
    services = act.all_services() if act else ()
    if services and all(sid in OVERNIGHT_SERVICES for sid in services):
        return True
    return state.detected_activity == "certified_diving" and state.detected_duration == "multi_day"


def _plan_is_single_day(state: ConversationState) -> bool:
    """¿Se SABE que el plan es de un dia (ida y vuelta desde Cartagena)? El servicio ya resuelto, o
    una actividad cuyos servicios son todos de un dia sin pernocta. Sin actividad, o con una que mezcla
    (curso PADI generico: Open Water de 2 dias y especialidades de 1), no se sabe."""
    from src.flows.catalog import MULTI_DAY_SERVICES, OVERNIGHT_SERVICES  # lazy

    not_single = MULTI_DAY_SERVICES | OVERNIGHT_SERVICES
    if state.detected_service_id:
        return state.detected_service_id not in not_single
    if state.detected_activity == "certified_diving":
        # EX-EST-2 (14-oct): "el plan de 5 buceos para el finde" sin duración detectada recibía "ida y vuelta el mismo
        # día". Solo se afirma un día si se SABE.
        return state.detected_duration == "single_day"
    act = dom.by_id(state.detected_activity) if state.detected_activity else None
    services = act.all_services() if act else ()
    return bool(services) and not any(sid in not_single for sid in services)


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
        return ("Te recomiendo el plan de *2 inmersiones en 1 día* en las "
                "Islas del Rosario. (Si prefieres un *paquete multi-día* de 3 o más "
                "inmersiones, dímelo.)\n\n")
    return ("I recommend the *2 dives in 1 day* plan in the Rosario "
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


# Respaldo determinista: verificado en vivo (2026-07-22) que el LLM NO siempre
# obedece la instrucción de abstenerse en `companion_qty` para un plural vago
# — "también vienen mis amigos a hacer snorkel" devolvió companion_qty=1 pese
# al prompt reforzado. No basta confiar en que el modelo se abstenga: si el
# mensaje no contiene NINGÚN número explícito (dígito o palabra-número), se
# descarta cualquier companion_qty que el LLM haya devuelto igualmente, antes
# de decidir si preguntar o asumir 1 por singular inequívoco.
_EXPLICIT_NUMBER_RE = re.compile(
    r"\d+|\b(?:" + number_alt(1, 10) + r")\b",
    re.IGNORECASE,
)


# Actividades de un dia que el nucleo cierra con carrito -> tipo de item. Sale del
# registro de actividades (F3a de docs/robustness/activity-domain-plan.md).
_ACTIVITY_TO_CART_TYPE = {
    activity_id: dom.by_id(activity_id).cart_type for activity_id in dom.day_activity_ids()
}

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
# Marca fuerte de buceo certificado -- a diferencia del patron generico
# "buce*"/"dive"/"scuba" (que tambien matchea dentro de un cualificador de
# experiencia como "nunca he buceado"), estas frases solo tienen sentido si
# el cliente de verdad pide/tiene buceo certificado.
_STRONG_CERTIFIED_DIVING_RE = re.compile(
    r"\bbuzo\s+certificado\b|\bbuzos\s+certificados\b|\bsoy\s+buz[oa]\b|"
    r"\bcertified\s+diver\b|\bdos\s+inmersiones\b|\btwo\s+dives\b|"
    r"\bpaquete\s+de\s+\d+\s+buceos?\b|\b\d+\s+dives?\b",
    re.IGNORECASE,
)
# Nombre real del minicurso -- a diferencia de un cualificador de
# experiencia ("nunca he buceado", "primera vez"), que tambien dispara la
# categoria "minicourse" de matched_activity_categories() pero no nombra el
# producto en si.
_EXPLICIT_MINICOURSE_NAME_RE = re.compile(
    r"\bmini[\s\-]?cursos?\b|\bmini[\s\-]?courses?\b|\bbauti[sz]\w{0,3}\b|"
    r"\bbubble\s?makers?\b|\bdiscover\s+scuba\b",
    re.IGNORECASE,
)


def _mentioned_product_activities(message: str) -> list:
    """Lista (no set, orden fijo) de actividades de producto mencionadas
    (certified_diving/minicourse/snorkel). Reusa `matched_activity_
    categories()` (intent_detector.py) como fuente unica -- antes esta
    funcion mantenia su PROPIO diccionario de regex (`_PRODUCT_MENTION_RE`),
    duplicado y sin las mismas protecciones que el detector de actividad
    principal, lo que permitio que "nunca he buceado" (un cualificador de
    experiencia, no una peticion de producto) contara como "mencion de
    buceo certificado" via el patron generico "buce*" (hallazgo en vivo,
    conversacion real "purple-sun-590", 2026-09-03).

    Cuando el mensaje YA nombra un curso PADI explicito (`_mentioned_courses`
    no vacio, la senal mas fuerte de lo que el cliente pidio), una mencion
    de certified_diving/minicourse que SOLO viene de un patron generico o de
    un cualificador de experiencia (sin su propio respaldo especifico) no
    cuenta como oferta aparte -- es contexto sobre el nivel del cliente, no
    un segundo producto en competencia. Sin curso nombrado, el
    comportamiento es igual que antes (todas las categorias detectadas
    cuentan)."""
    cats = matched_activity_categories(message)
    acts = [a for a in ("certified_diving", "minicourse", "snorkel") if a in cats]
    if _mentioned_courses(message):
        if "certified_diving" in acts and not _STRONG_CERTIFIED_DIVING_RE.search(message):
            acts.remove("certified_diving")
        if "minicourse" in acts and not _EXPLICIT_MINICOURSE_NAME_RE.search(message):
            acts.remove("minicourse")
    return acts


# Cursos PADI por NOMBRE como opciones distintas de deliberación (gap
# 2026-07-24): `_mentioned_product_activities` no distingue cursos (todos serían
# "padi_course"), así que "no sé si open water o advanced" (sin "?") no
# disparaba el ancla de 2+ opciones. Cada nombre de curso cuenta como una opción
# propia. Conservador: solo nombres inequívocos de curso, no la palabra "curso"
# suelta (evita casar dentro de "minicurso").
# Los nombres salen de la tabla UNICA del detector (`courses_mentioned`,
# centralizacion 2026-09-15): antes esta era una segunda lista con variantes que
# el detector de actividad no conocia.


def _mentioned_courses(message: str) -> list:
    return courses_mentioned(message)


async def _otro_idioma_en_ingles(state: ConversationState, datos: dict | None = None, message: str = "") -> None:
    """G-10 (decisión de Gadea, 14-oct): si el mensaje está escrito en un idioma que no es español ni inglés, el bot
    contesta en inglés. El idioma principal lo dice el extractor de la fase EX (misma llamada; unas palabras sueltas no
    cuentan). En el primer turno se mira la extracción ya lanzada con el enrutador, antes del saludo (sin consumirla:
    `_understand` la vuelve a esperar y ya está hecha).

    Solo en la apertura (lat-deuda, 26-oct): con la conversación ya en marcha, el idioma lo cambia solo una petición
    del cliente (`cambia_idioma` de Jev). «Y para transferência tiene descuento?», en el noveno turno de una conversación
    en español, pasaba al inglés (el extractor dijo «pt»): el criterio de idioma fallaba en las 6 rondas."""
    if any(m.get("role") == "assistant" for m in state.history or []):
        return
    if len((message or "").split()) < 3:
        # Ronda flujo1-B2: "Frances" (contesta la nacionalidad) pasó la conversación a inglés. Una o dos palabras no
        # dicen en qué idioma escribe el cliente.
        return
    if datos is None:
        tarea = getattr(state, "_extraccion_adelantada", None)
        if tarea is None:
            return
        try:
            datos = await tarea
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 — sin dato, el idioma de siempre
            return
    idioma = (datos or {}).get("idioma")
    if idioma and idioma not in ("es", "en") and state.language != "en":
        logger.info(f"[CORE][IDIOMA] el cliente escribe en {idioma!r}: se contesta en inglés")
        state.language = state.detected_language = "en"


def _jev_dice_el_lugar(state: ConversationState) -> bool:
    """gen-15: ¿Jev está seguro (≥ `CUSTOMER_PLACE_MIN`) de que el mensaje dice dónde está el cliente (Cartagena o las
    islas)? Lo contrario de `_jev_dice_que_no_lo_dice`."""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}
    return lugar.get("choice") in ("islands", "cartagena") and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN


def _jev_dice_que_no_lo_dice(state: ConversationState) -> bool:
    """CAL-C3c: ¿Jev está seguro (≥ `CUSTOMER_PLACE_MIN`) de que el mensaje no dice dónde está el cliente?"""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}
    return lugar.get("choice") == "none" and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN


def _same_for_customer(field: str, a, b, lang: str) -> bool:
    """¿Se leen igual para el cliente? En un reparto no cuentan el orden ni las cantidades a
    cero (u3-5 paso 1a)."""
    def canon(v):
        if isinstance(v, dict):
            return {k: q for k, q in sorted(v.items()) if q}
        return v
    return _describe_value(field, canon(a), lang) == _describe_value(field, canon(b), lang)


def _describe_value(field: str, value, lang: str) -> str:
    """Texto corto de un valor para la pregunta de confirmacion."""
    es = lang == "es"
    if field == "group_allocation":
        return ", ".join(
            f"{qty} {('sin decidir' if es else 'undecided') if act == 'undecided' else dom.text(act, 'recall', lang, default=act)}"
            for act, qty in (value or {}).items()
        )
    if field == "group_size":
        return f"{value} personas" if es else f"{value} people"
    if field == "location":
        return {
            "cartagena": "salida desde Cartagena" if es else "departing from Cartagena",
            "island": "en las islas" if es else "on the islands",
        }.get(value, str(value))
    yes_no = {
        "is_colombian": ("colombianos o residentes", "no colombianos", "Colombian or resident", "not Colombian"),
        "is_certified": ("con certificación de buceo", "sin certificación", "certified", "not certified"),
        "last_dive_over_2_years": ("más de 2 años sin bucear", "buceo en los últimos 2 años",
                                   "over 2 years since the last dive", "dived in the last 2 years"),
    }[field]
    return yes_no[(0 if value else 1) + (0 if es else 2)]


def _words(message: str) -> list[str]:
    return [w for w in re.split(r"[^\wáéíóúñü]+", (message or "").lower()) if w]


def _is_short_ack(message: str) -> bool:
    """"vale", "ok", "sí" a secas: tras el cierre no justifican una peticion."""
    words = _words(message)
    return 0 < len(words) <= 2 and all(is_agree(w) or is_affirmative(w) for w in words)


def _known_field_values(state: ConversationState) -> dict:
    """Valor de cada campo extraible que la conversacion ya conoce: el confirmado
    antes que el detectado. Una sola lectura para los huecos, las correcciones y el
    eval-set (`run_extraction_eval --core`)."""
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
    return candidates


async def await_pending_notes(state: ConversationState) -> None:
    """l1-4: espera a la captura de notas que `_setup_phase` lanzó en paralelo.

    Se llama en los dos sitios donde importa que ya estén: antes de
    `_build_extra_context` (el contexto del RAG las incluye) y al cerrar el turno
    en `supervisor.route_message`, antes de que el canal guarde el estado. Es
    idempotente: si no hay tarea, o ya se esperó, no hace nada.

    Si la captura falla, se traga el error a propósito: la nota es un extra para el
    asesor y no puede tumbar el turno del cliente (el código de siempre, cuando iba
    en serie, tampoco propagaba: `_maybe_capture_notes` ya registra y sigue).
    """
    task = getattr(state, "_pending_notes_task", None)
    if task is None:
        return
    state._pending_notes_task = None
    try:
        await task
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[NOTES][PARALELO] la captura de notas falló: {exc}")


def _notes_snapshot(state: ConversationState) -> dict:
    """l1-4: foto de lo que `extract_notes` debe leer, tomada al final de `setup`.

    En serie da lo mismo que leer el estado en el momento. En paralelo es lo que
    evita la carrera del A/B del 23-sep: una tarea de asyncio no arranca hasta que
    el turno espera algo, y en los turnos sin más llamadas al LLM eso es el final
    de `route_message`, cuando las fases ya han metido la respuesta del BOT en
    `state.history`. Las notas salían de esa respuesta y contaminaban los turnos
    siguientes. Copias: la lista del historial crece después, y sus mensajes no
    se modifican."""
    facts = state.remembered_facts or {}
    return {
        "history": list(state.history),
        "existing": list(facts.get("notes") or []),
        "lang": state.language,
    }


def _jev_sin_nada_que_apuntar(routing_signals: dict) -> bool:
    """rag-5 (flag `notas_puerta_jev`): ¿Jev está SEGURO de que el mensaje no cuenta nada del cliente que haya que
    apuntar? Entonces no se llama al extractor de notas, que en esos mensajes apuntaba la pregunta como si fuera un
    hecho ("how much would that be" -> "not Colombian"). Sin la respuesta de Jev (falló), lo de siempre."""
    from src.agents.jev_router import NOTES_SKIP_MAX, SHARES_OPEN_FACT
    from src.observability import note_turn

    p = routing_signals.get(SHARES_OPEN_FACT)
    if p is None:
        return False
    saltar = p < NOTES_SKIP_MAX
    note_turn(notas="saltadas" if saltar else "extraidas")
    if saltar:
        logger.info(f"[CORE][NOTAS] Jev: nada que apuntar ({p:.2f}): no se llama al extractor")
    return saltar


async def _maybe_capture_notes(
    state: ConversationState, message: str, *, snapshot: dict | None = None
) -> None:
    """(Fase C, re-cableado 2026-07-28 — decisión owner: con LLM) Captura hechos
    abiertos que un asesor querría recordar (lesión/médico, accesibilidad,
    ocasión especial, restricciones) y los persiste en
    `state.remembered_facts["notes"]` → alimenta `_build_extra_context` (contexto
    del LLM) y la nota de lead del asesor, que ya renderizan esa lista.

    Gate barato: se salta mensajes triviales (numéricos / <3 palabras) para no
    gastar una llamada en "sí"/"2"/"cartagena". Cualquier fallo se traga — nunca
    puede romper el turno (mismo principio que el resto del núcleo).

    `snapshot` (l1-4, en paralelo; sin flag desde s4-25): lo que hay que leer, tomado
    en `_setup_phase` antes de lanzar la tarea (ver `_notes_snapshot`). Sin él (una
    llamada directa) se toma ahora."""
    from src.agents import supervisor  # lazy

    stripped = message.strip()
    if stripped.isdigit() or len(stripped.split()) < 3:
        return
    try:
        snap = snapshot if snapshot is not None else _notes_snapshot(state)
        new_notes = await extract_notes(
            message, history=snap["history"], existing_notes=snap["existing"], lang=snap["lang"]
        )
        if not new_notes:
            return
        # Se fusiona con el estado de AHORA, no con el de la foto: en paralelo el
        # turno ha podido seguir escribiendo `remembered_facts` mientras tanto.
        facts = state.remembered_facts if state.remembered_facts is not None else {}
        existing = list(facts.get("notes") or [])
        notes = existing + [n for n in new_notes if n not in existing]
        facts["notes"] = notes[-supervisor._MAX_REMEMBERED_NOTES:]
        state.remembered_facts = facts
        logger.info(f"[CORE] notes captured -> {new_notes}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[CORE] notes capture failed (ignored): {exc}")


def _apply_cert_or_course(state: ConversationState, value) -> bool:
    """Respuesta a "¿ya la tienen o quieren sacarla?": si ya la tienen, son buzos
    certificados; si la quieren, es el curso de ese nivel."""
    if value == "already_certified":
        state.is_certified = state.detected_is_certified = True
        _set_concrete_activity(state, "certified_diving")
    elif value == "wants_course":
        state.is_certified = state.detected_is_certified = False
        _set_concrete_activity(state, state.cert_or_course_level or "padi_course")
    else:
        return False
    state.needs_cert_or_course = False
    state.cert_or_course_level = None
    return True


def _take_undecided_members(intent, state: ConversationState) -> None:
    """Punto UNICO para las personas del grupo sin actividad elegida, vengan del
    regex o del LLM: salen del reparto (que se guarda sin ellas), su cantidad queda
    pendiente y se marca la recomendacion de opciones (F6). Va DESPUES de la
    invariante de la suma, que las cuenta porque aun estan dentro del reparto."""
    allocation = getattr(intent, "group_allocation", None)
    if not isinstance(allocation, dict):
        return
    qty = allocation.pop("undecided", None)
    if not (isinstance(qty, int) and qty > 0):
        return
    # El total incluye a esas personas (2026-09-15): sin total escrito ("mi amigo tiene
    # licencia, yo no"), el total se sincronizaba despues con la suma del reparto ya sin
    # ellas y quedaba en 1.
    with_undecided = sum(v for v in allocation.values() if isinstance(v, int) and v > 0) + qty
    if (intent.group_size or state.detected_group_size or 0) < with_undecided:
        intent.group_size = with_undecided
        if "group_size" not in intent.detected_fields:
            intent.detected_fields.append("group_size")
    intent.group_allocation = allocation or None
    state.pending_undecided_qty = qty
    state.needs_companion_activity = True


def _merge_pending_undecided(state: ConversationState) -> bool:
    """Si ya se eligio actividad para las personas `undecided` del grupo, se
    fusionan con su cantidad conocida (sin preguntar "¿cuantos serian?")."""
    qty, activity = state.pending_undecided_qty, state.pending_companion_activity
    if not (qty and activity):
        return False
    _merge_companion_activity(state, activity, qty)
    state.pending_companion_activity = None
    state.pending_undecided_qty = None
    return True


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
    known = state.detected_group_size or 0
    alloc[activity] = alloc.get(activity, 0) + qty
    state.detected_group_allocation = alloc
    state.detected_group_size = sum(alloc.values())
    if not main_act and known + qty > state.detected_group_size:
        # DEUDA-EXT (26-oct): sin actividad principal, los que ya se contaban se perdían: "two certified divers" + "my
        # wife will join us but she'll just snorkel" dejaba {snorkel: 1} y total 1 (banco-lat11 a3). El total suma a la
        # persona nueva; los demás esperan a la principal, que el bot pregunta (`booking._resto_a_la_principal`).
        state.detected_group_size = known + qty
    logger.info(f"[CORE] merged companion activity {activity} x{qty} -> alloc={alloc}")


def _apply_group_total(state: ConversationState, total: int) -> bool:
    """Respuesta al total del grupo. Con una persona pendiente de ubicar
    (`pending_companion_in_group`): si el total no crece, esa persona ya estaba
    contada y se MUEVE de la actividad principal; si crece, se AÑADEN los que faltan."""
    pending = state.pending_companion_in_group
    if not pending:
        state.detected_group_size = total
        return True
    state.pending_companion_in_group = None
    known = state.detected_group_size or 0
    activity, qty = pending["activity"], pending["qty"]
    if total > known:
        _merge_companion_activity(state, activity, total - known)
        return True
    alloc = dict(state.detected_group_allocation or {})
    main = state.detected_activity
    if not main:
        # DEUDA-EXT (26-oct): sin actividad principal, el que ya estaba contado pasa a su actividad y el resto espera a
        # la principal (antes `alloc[None]`).
        moved = min(qty, known or qty)
        alloc[activity] = alloc.get(activity, 0) + moved
        state.detected_group_allocation = alloc
        logger.info(f"[CORE] companion {activity} x{moved} ya contado, sin principal -> alloc={alloc}")
        return True
    alloc.setdefault(main, known or qty)
    moved = min(qty, alloc[main])
    alloc[main] -= moved
    alloc[activity] = alloc.get(activity, 0) + moved
    state.detected_group_allocation = {k: v for k, v in alloc.items() if v}
    logger.info(f"[CORE] companion {activity} x{moved} ya contado -> alloc={state.detected_group_allocation}")
    return True


def _full_booking_recap(state: ConversationState) -> str | None:
    """Recap COMPLETO y cálido de la reserva (todas las actividades/personas +
    ubicación), del ESTADO (nunca inventado). Para la pregunta general "¿qué te
    había pedido?" — reemplaza el recall de campo-suelto que salía seco y a veces
    equivocado ("Me habías dicho: snorkel"). Estilo Monegros: recap estructurado.
    Devuelve None si no hay nada resuelto (el caller cae a RAG)."""
    es = state.language == "es"
    lang = "es" if es else "en"
    lines: list[str] = []
    alloc = state.detected_group_allocation or {}
    # Solo actividades con texto de recordatorio en el registro (F3b).
    product_alloc = {k: v for k, v in alloc.items() if v and dom.text(k, "recall", lang)}
    if product_alloc:
        for act, qty in product_alloc.items():
            label = dom.text(act, "recall", lang)
            lines.append(f"• *{qty}* para *{label}*" if es else f"• *{qty}* for *{label}*")
    else:
        act = _effective_activity(state)
        if act:
            n = state.detected_group_size or 1
            label = dom.text(act, "recall", lang, default=act)
            lines.append(f"• *{n}* para *{label}*" if es else f"• *{n}* for *{label}*")
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


def _jev_says_no_recall(state: ConversationState) -> bool:
    """Paso 5: Jev dice que el mensaje NO pide recordar nada. Ausente (Jev apagado o Jev fallo) = no lo
    sabemos -> la conducta de hoy. En la ronda A el "¿me recuerdas…?"
    contesto 15 preguntas que no lo eran y cancelo su respuesta; banco
    `scripts/sonda_pide_recordar.py`: 11/12 peticiones reales, 0/14 falsas."""
    return getattr(state, "_jev_asks_recall", None) is False


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
        return (f"Me dijiste que son *{n}* personas." if es
                else f"You told me you're a group of *{n}*.")
    if field == "activity":
        act = _effective_activity(state)
        if not act:
            return None
        label = dom.text(act, "recall", "es" if es else "en", default=act)
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


def _turn_has_question(message: str, routing_signals: dict) -> bool:
    """u3-4: ¿trae el mensaje algo que CONTESTAR? El regex/"?" de siempre, o Jev en la
    misma llamada del router (`asks_question`, >= 0,7): "perfecto, como pago" no lleva
    "?" ni lo ve el regex, y se quedaba sin contestar."""
    if _is_greeting_only(message):
        return False
    # ex-9b paso 5: si Jev ha contestado, manda Jev (y el "?"); el regex solo si Jev calla. El regex daba por pregunta
    # "hay un niño de 5 años" (lanzaba el RAG y se saltaba los resolutores).
    if "asks_question" in routing_signals:
        if "?" in message:
            return True
        return bool(routing_signals["asks_question"]) and not _solo_pide_reservar(routing_signals)
    return _looks_like_question(message)


def _solo_pide_reservar(routing_signals: dict) -> bool:
    """lat-7 (25-oct, fase LAT): Jev da `asks_question` también a quien PIDE algo de la reserva sin preguntar nada
    («quiero bucear certificado», «hi, i want to book a dive», «Hola, me gustaría reservar»). Si no hay ninguna intención
    de la tabla y Jev está seguro de que no trae otra cosa (`pide_otra_cosa` = False), es un paso de la reserva: lo
    contesta el flujo con su siguiente pregunta (~1,3 s) y no el RAG (3-9 s, y repetía el saludo; sonda lat-7, latb5-B:
    47 mensajes cortos así)."""
    from src.agents.jev_router import PIDE_OTRA_COSA  # lazy
    from src.orchestration.graph import _INTENCION_DE_SENAL  # lazy

    if routing_signals.get(PIDE_OTRA_COSA) is not False:
        return False
    return not any(routing_signals.get(senal) for senal in _INTENCION_DE_SENAL.values())


def _is_greeting_only(message: str) -> bool:
    """True si el mensaje es SOLO saludo y/o cortesía de small-talk ("hola",
    "buenas", "hola buenas que tal?", "hi how are you") — sin contenido de
    reserva ni pregunta de info real.

    Se compone del vocabulario de saludo + cortesía (`GREETING_ONLY_KEYWORDS` +
    `GREETING_SMALLTALK_KEYWORDS`, una sola fuente): se quitan esas frases del
    mensaje (sin tildes ni signos) y, si no queda nada sustantivo, es un saludo.
    Así cubre combinaciones ("hola buenas") y saludo+cortesía ("hola que tal")
    sin enumerarlas. "que tal el buceo nocturno?" NO lo es (queda "el buceo
    nocturno") y sí va a RAG.

    Fase 3.4: un saludo no tiene slots que extraer (skip `fill_gaps`). Fase
    robustez (2026-09-16, bug en vivo): tampoco es una pregunta → no va a RAG
    (antes "hola buenas que tal?" daba saludo + fallback de asesor)."""
    from src.agents import supervisor  # lazy
    norm = re.sub(r"[^a-z0-9\s]", " ", strip_accents(message).lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return False
    phrases = supervisor.GREETING_ONLY_KEYWORDS | supervisor.GREETING_SMALLTALK_KEYWORDS
    for phrase in sorted((strip_accents(p).lower() for p in phrases), key=len, reverse=True):
        norm = re.sub(rf"\b{re.escape(phrase)}\b", " ", norm)
    return norm.strip() == ""


# ─── Cierre: carrito desde slots + resumen determinista con links ───

def _cart_item(state: ConversationState, activity: str, qty: int) -> dict:
    """Ítem del carrito para una actividad: el tipo sale del registro (`cart_type`).
    Solo dos tipos llevan plan propio: el buceo certificado (plan de inmersiones del
    catálogo) y los cursos, con el servicio de ESTE ítem en su variante de ubicación
    (un acompañante que elige Open Water no hereda el servicio del principal;
    Divemaster y el referido se cierran con asesor por `contact_only`)."""
    registered = dom.by_id(activity)
    item_type = (registered.cart_type if registered else None) or "course"
    plan = None
    if item_type == "cert":
        plan = _resolve_cert_plan(state)
    elif item_type == "course":
        plan = state.detected_service_id if activity == state.detected_activity else dom.base_service_id(activity)
        if plan:
            plan = cart_render.service_for_location(plan, state)
    return {"type": item_type, "qty": qty, "plan": plan,
            "label": cart_render.cart_label_for(item_type, plan, state.language)}


# ─── El bucle por turno ───

async def maybe_handle_turn(
    state: ConversationState, message: str, *, routing_signals: dict | None = None,
) -> str | None:
    """Punto de entrada desde el supervisor (tras el gating de seguridad).
    Devuelve None solo para las clases de mensaje que deben seguir cayendo a
    los handlers deterministas legacy (escalado por keyword, menú/volver).

    `routing_signals` (auditoría 2026-07-22): ya calculado UNA vez por el nodo
    router del grafo, que lo pasa por `supervisor._shared_turn_handler` (nunca
    se recalcula aquí).

    (Fase 3.3b/c/d/e) Orquesta las fases extraídas: `_setup_phase` →
    `_availability_phase` → `_routing_phase` → `_extraction_phase` →
    `_slotfill_close_phase`. El subgrafo del booking llama a las MISMAS
    funciones como nodos, así que cascada y grafo comparten la fuente de verdad —
    equivalencia por construcción."""
    routing_signals = routing_signals or {}
    setup = await _setup_phase(state, message, routing_signals)
    if setup is None:
        return None
    greeting, first_turn = setup
    avail = await _availability_phase(state, message, routing_signals, greeting)
    if avail is not None:
        return avail
    routing = await _routing_phase(state, message, routing_signals, greeting)
    if isinstance(routing, str):
        return routing
    carry = routing
    extraction = await _extraction_phase(state, message, routing_signals, greeting, carry)
    if extraction is not None:
        return extraction
    return await _slotfill_close_phase(state, message, greeting, first_turn, carry)


async def _answer_question(
    state: ConversationState, message: str, *, rag_query: str | None = None,
) -> str:
    # Vía supervisor.rag_answer (no rag_agent directamente): es la referencia
    # que mockean los tests y cualquier interceptor futuro — mismo camino que
    # el resto de respuestas de info del bot. `rag_query` (opcional): consulta
    # reescrita para RAG cuando el mensaje crudo recupera mal (deliberación);
    # el historial sigue teniendo el mensaje real del cliente.
    answer = await _rag_answer(state, message, rag_query=rag_query)
    if _es_pregunta_de_origen(answer):
        _fijar_origen_antes_del_precio(state, message)
        return answer
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


async def _con_la_nacionalidad_del_mensaje(state: ConversationState, message: str) -> ConversationState:
    """gen-14 (21-oct, flag `rag_espera_la_nacionalidad`): el RAG de un turno con pregunta se escribe (o se adelanta)
    ANTES de que la extracción apunte lo que dice ESE mensaje, así que «Somos de Cali… ¿cuánto vale la salida?» se
    cotizaba en USD con la regla de «sin nacionalidad, USD» (banco dialogos-gen14-moneda: is_colombian True y la
    respuesta en USD 2/2; en la traza, «respuesta adelantada aprovechada» antes de «Detected nationality»). Con el
    flag, el RAG recibe una COPIA del estado con la nacionalidad que la extracción del turno ya leyó (no se gasta ni
    se lanza otra: es la tarea adelantada); el estado de verdad lo sigue escribiendo la extracción. Si la nacionalidad
    cambia, la huella de rag-5 cambia y la respuesta adelantada se rehace."""
    if state.is_colombian is not None:
        return state
    from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

    datos = await lectura_del_extractor(state, message)
    valor = (datos or {}).get("is_colombian")
    if valor is None or (datos or {}).get("mixed_nationality"):
        return state
    import copy

    copia = copy.copy(state)
    copia.is_colombian = valor
    logger.info(f"[CORE][GEN14] el RAG ya sabe la nacionalidad de este mensaje: is_colombian={valor}")
    return copia


async def _con_hechos(state: ConversationState, message: str, history: list) -> str | None:
    """ARQ-1d: si el mensaje solo pide intenciones que el código sabe contestar, la respuesta del redactor de hechos
    (src/agents/redactor_hechos.py); si no, None y contesta el RAG de siempre."""
    from src.agents import redactor_hechos  # lazy

    return await redactor_hechos.responder(state, message, history)


async def _hechos_para_el_rag(state: ConversationState, message: str, history: list, *, siempre: bool = False
                              ) -> str | None:
    """ARQ-1g: en un mensaje MEZCLADO (intenciones de la tabla y algo más: «¿cuánto cuesta y qué
    peces se ven?»), el RAG contesta, pero la parte cubierta la escribe con los hechos del código y no de memoria. None
    si no hay nada cubierto o si el mensaje es todo de la tabla (entonces contesta el redactor). También cuando Jev lo
    daba por todo de la tabla pero el redactor dijo FALTA: el mensaje traía algo más."""
    mezclado = getattr(state, "_otra_cosa", None) is not False or getattr(state, "_redactor_dijo_falta", False)
    # arq-5a: `siempre` (la respuesta antes del pase a un asesor) no mira si el mensaje es mezclado: ahí el redactor no
    # contesta nunca, así que lo de la tabla tiene que llegar al RAG.
    if not (mezclado or siempre):
        return None
    from src.agents import redactor_hechos  # lazy

    turno = await redactor_hechos.hechos_del_turno(state, message, history)
    if turno is None:
        return None
    bloques, cubiertas = turno
    logger.info(f"[HECHOS] mensaje mezclado: el RAG recibe los hechos de {cubiertas} ({bloques[0]['actividad']})")
    from src.observability import note_turn  # lazy

    note_turn(hechos_por_codigo="al_rag")
    state._hechos_del_rag = (bloques, cubiertas)  # arq-4b: el RAG comprueba que su respuesta los lleve
    return redactor_hechos.texto_de_los_hechos(bloques)


async def _rag_answer(
    state: ConversationState, message: str, *, rag_query: str | None = None, history: list | None = None,
    sin_precio: bool = False,
) -> str:
    from src.agents import supervisor  # lazy

    # l1-4: las notas de ESTE mensaje pueden estar calculándose en paralelo. Aquí
    # es donde se usan (van dentro del contexto del RAG), así que aquí se espera.
    await await_pending_notes(state)
    if not sin_precio and (con_hechos := await _con_hechos(state, message,
                                                            state.history if history is None else history)):
        return con_hechos
    entradas = _entradas_rag(await _con_la_nacionalidad_del_mensaje(state, message),
                             state.history if history is None else history, message)
    if hechos := await _hechos_para_el_rag(state, message, state.history if history is None else history):
        entradas["hechos"] = hechos  # arq-1g
        entradas["hechos_bloques"] = state._hechos_del_rag
    if sin_precio:  # G3-07a: solo se pasa cuando hace falta (la llamada de siempre no cambia)
        entradas["sin_precio"] = True
    answer = await supervisor.rag_answer(rag_query or message, **entradas)
    # 7-oct (opción C): si cotiza sin origen, se pregunta el origen; quien la recibe deja el estado preparado
    # (`_fijar_origen_antes_del_precio`).
    return _puerta_del_origen(state, message, answer)


# CAL-C3d (17-oct, flag `tras_pase_recuerda_el_pase`): tras pasar la conversación a un asesor, "¿me podrías ayudar con
# este tema?" (cal-59, la agencia con un correo sin respuesta) llegaba al RAG sin saber que ya había un pase, y contestaba
# "Cuéntame, ¿qué tema tienes en mente?". El RAG recibe el estado; ahora también este hecho.
_PASE_HECHO_ES = ("Esta conversación YA está pasada a un asesor del equipo, que la ve entera y escribirá por este chat. "
                  "Si el cliente pide ayuda con lo que ya contó, no le pidas que lo repita: dile que el asesor ya tiene "
                  "su caso y le escribe por aquí.")
_PASE_HECHO_EN = ("This conversation has ALREADY been passed to an advisor from the team, who sees all of it and will "
                  "write in this chat. If the customer asks for help with what they already told, do not ask them to "
                  "repeat it: tell them the advisor already has their case and will write here.")


def _entradas_rag(state: ConversationState, history: list, message: str = "") -> dict:
    """Lo que recibe el RAG además de la pregunta: idioma, historial, resumen del estado y (rag-3) el origen.
    Una sola fuente para la llamada normal y para la adelantada de rag-5, que compara sus huellas."""
    from src.agents import supervisor  # lazy

    extra = supervisor._build_extra_context(state)
    plan = _plan_nombrado(state, message)
    if plan:
        extra = f"{extra}\n\n{plan}" if extra else plan
    if state.step == Step.ESCALATE:
        pase = _PASE_HECHO_ES if state.language == "es" else _PASE_HECHO_EN
        extra = f"{extra}\n\n{pase}" if extra else pase
    entradas = {"lang": state.language, "history": history, "extra_context": extra}
    # rag-3: con el origen del cliente, la búsqueda baja las fichas del otro origen.
    if state.location:
        entradas["origin"] = state.location
    # CAL-D: lo que ya sabemos del cliente (los mismos hechos del estado que eligen los avisos) para que la consulta de
    # búsqueda nombre el asunto.
    from src.flows import avisos as avisos_mod  # lazy

    entradas["avisos_hechos"] = avisos_mod.hechos_del_estado(state)
    return entradas


# s4-27 (7-oct, Gonzalo; flag `rag_plan_nombrado`): "¿el precio de las 2 inmersiones? desde ese hotel" (cliente ya en
# las islas) -> el RAG ofrecía el paquete de 3 y decía que desde las islas no hay 2 inmersiones sueltas (existe: 124
# USD). El catálogo del prompt sí lo trae; la búsqueda trae las fichas de los paquetes de las islas (sus itinerarios
# repiten "2 inmersiones") y, con el historial real de la conversación, el modelo se iba al paquete (rag_piezas: 0-1/3
# con el historial real, 3/3 con uno limpio, 3/3 con el plan puesto en el estado; docs/robustness/s4-27/). Si el
# cliente NOMBRA cuántas inmersiones y su origen consta, el contexto dice qué plan del catálogo es: solo añade un dato,
# no decide nada. El número de inmersiones de cada plan sale de su id (`2_dives_1_day...`), no de una lista a mano.
# ex-9b paso 4 (sin flag: replay del golden igual): "N inmersiones" lo lee `intent_detector.dive_counts_in`, la única
# lectura de esa cifra (antes un regex propio, `_N_INMERSIONES_RE`), con los tamaños de los planes de su origen.
_PLAN_ID_RE = re.compile(r"(\d+)_dives?_")


def _plan_nombrado(state: ConversationState, message: str) -> str | None:
    """El plan del catálogo que nombra el cliente ("las 2 inmersiones") para su origen, como una línea del contexto;
    None si el origen no consta, no nombra un número de inmersiones o ningún plan lo tiene."""
    if state.location not in ("cartagena", "island") or not message:
        return None
    from src.agents.intent_detector import dive_counts_in  # lazy
    from src.flows.catalog import SERVICES, service_fact_parts  # lazy

    en_islas = state.location == "island"
    por_tamano: dict[int, list[str]] = {}
    for sid in SERVICES:
        m = _PLAN_ID_RE.match(sid)
        if m and sid.endswith("_already_on_island") == en_islas:
            por_tamano.setdefault(int(m.group(1)), []).append(sid)
    nombrados = dive_counts_in(message, tamanos=por_tamano)
    if not nombrados:
        return None
    n = nombrados[0]
    planes = por_tamano[n]
    if state.selected_service in planes:
        return None
    es = state.language == "es"
    nombre = "name_es" if es else "name_en"
    lineas = [f"- {SERVICES[sid].get(nombre, sid)}: {'; '.join(service_fact_parts(sid, state.language))}."
              for sid in planes]
    cabeza = (f"El cliente nombra {n} inmersion(es). En el catálogo, para su origen, eso es:" if es else
              f"The customer names {n} dive(s). In the catalog, for their origin, that is:")
    return "\n".join([cabeza, *lineas])


# rag-5 (30-sep): el RAG arranca A LA VEZ que el enrutador (Jev, ~0,7 s) en vez de después, y solo se usa si su
# contexto es EXACTAMENTE el que tendría la llamada de siempre (misma "huella": pregunta, idioma, historial,
# resumen del estado sin la hora y origen). Si algo cambió entre medias (notas nuevas de este mensaje, una
# corrección, un cambio de idioma...), se tira y se lanza la de siempre: nunca contesta con otro contexto y nunca
# tarda más que hoy. Si el turno no llega a pedir respuesta, se cancela al cerrarlo (ese es el coste extra).
_HORA_DEL_RESUMEN = re.compile(r"^(Fecha y hora actual|Current date and time): [^(]*\([^)]*\)\.\s*")
_PARTES_HUELLA = ("mensaje", "idioma", "historial", "resumen", "origen", "hechos")  # en el orden de `_huella_rag`


def _huella_rag(message: str, entradas: dict) -> tuple:
    import json

    resumen = _HORA_DEL_RESUMEN.sub("", entradas.get("extra_context") or "")  # la hora cambia de un minuto a otro
    return (message, entradas.get("lang"), json.dumps(entradas.get("history") or [], ensure_ascii=False),
            resumen, entradas.get("origin"), entradas.get("hechos"))


def lanzar_rag_adelantado(state: ConversationState, message: str) -> None:
    """Al empezar el turno, antes del enrutador: lanza el RAG con lo que ya se sabe (el historial con ESTE
    mensaje, como lo dejará `_setup_phase`).

    Primer mensaje (1-oct): el idioma aún no está decidido. Se usa la misma regla rápida con la que empieza
    `_setup_phase` (sin llamadas) y la foto queda como la dejará él (idioma y paso de conversación libre). Si la
    regla no sabe el idioma (`_setup_phase` preguntaría al LLM), no se adelanta. Si al final decide otra cosa, la
    huella no coincide y se rehace, como siempre."""
    texto = (message or "").strip()
    if not texto or texto.isdigit():
        return
    import copy

    from src.agents import supervisor  # lazy

    history = [*(state.history or []), {"role": "user", "content": message}]
    foto = copy.copy(state)
    foto.history = history
    if state.step in (Step.WELCOME, Step.LANGUAGE):
        from src.flows.catalog import _detect_language_from_text

        lang = _detect_language_from_text(message)
        if not lang:
            return
        foto.language = foto.detected_language = lang
        foto.step = Step.FREE_TEXT
        foto.quick_replies = []
    entradas = _entradas_rag(foto, history, message)

    async def _correr() -> str:
        from src.agents.rag_agent import RAG_ADELANTADO

        RAG_ADELANTADO.set(True)
        return await supervisor.rag_answer(message, **entradas)

    state._rag_adelantado = {"task": asyncio.create_task(_correr()), "huella": _huella_rag(message, entradas),
                             "mensaje": message}


async def _adoptar_o_rehacer(state: ConversationState, message: str, history: list, adelantado: dict) -> str:
    """rag-5: donde hoy se lanzaría el RAG. Espera a las notas (como la llamada de siempre), calcula las entradas
    de verdad y, si su huella es la de la respuesta adelantada, la aprovecha; si no, la tira y la rehace."""
    from src.agents import supervisor  # lazy
    from src.observability import note_turn

    await await_pending_notes(state)
    if con_hechos := await _con_hechos(state, message, history):
        adelantado["task"].cancel()
        note_turn(rag_adelantado="descartado")
        return con_hechos
    entradas = _entradas_rag(await _con_la_nacionalidad_del_mensaje(state, message), history, message)
    if hechos := await _hechos_para_el_rag(state, message, history):
        entradas["hechos"] = hechos  # arq-1g: la adelantada salió sin ellos, así que su huella no coincide y se rehace
        entradas["hechos_bloques"] = state._hechos_del_rag
    huella = _huella_rag(message, entradas)
    if huella == adelantado["huella"]:
        note_turn(rag_used=True, rag_adelantado="aprovechado")
        logger.info("[CORE][RAG5] respuesta adelantada aprovechada")
        answer = await adelantado["task"]
        return _puerta_del_origen(state, message, answer)  # 7-oct: opción C, ver `_rag_answer`
    adelantado["task"].cancel()
    # Diagnóstico (30-sep): la mitad de los intentos de la ronda rag5-B se rehicieron y no se sabía por qué.
    cambio = ",".join(n for n, a, b in zip(_PARTES_HUELLA, adelantado["huella"], huella, strict=True) if a != b)
    note_turn(rag_adelantado="rehecho", rag_rehecho_por=cambio)
    logger.info(f"[CORE][RAG5] el contexto cambió entre medias ({cambio}): se rehace la respuesta")
    answer = await supervisor.rag_answer(message, **entradas)
    return _puerta_del_origen(state, message, answer)


async def rag_con_adelantado(state: ConversationState, message: str, history: list) -> str:
    """rag-5 (1-oct): el RAG de los caminos que contestan fuera de la reserva (buceo adaptado: nodo `info` y la
    cascada). En la ronda rag5-B esos turnos tiraban su respuesta adelantada y hacían otra. Ahora la adoptan con la
    misma huella que la reserva; las entradas salen de `_entradas_rag`, así que la búsqueda también recibe el origen
    del cliente (rag-3), que este camino no pasaba."""
    adelantado = getattr(state, "_rag_adelantado", None)
    if adelantado is not None and adelantado["mensaje"] == message:
        state._rag_adelantado = None
        answer = await _adoptar_o_rehacer(state, message, history, adelantado)
    else:
        answer = await _rag_answer(state, message, history=history)
    if _es_pregunta_de_origen(answer):
        _fijar_origen_antes_del_precio(state, message)
    return answer


def cancelar_rag_adelantado(state: ConversationState) -> None:
    """Cierre del turno: una respuesta adelantada que el turno no usó se cancela."""
    from src.observability import note_turn

    adelantado = getattr(state, "_rag_adelantado", None)
    state._rag_adelantado = None
    if adelantado is not None:
        if not adelantado["task"].done():
            adelantado["task"].cancel()
        note_turn(rag_adelantado="descartado")


# u3-4 (24-sep): "contesta y sigue". Escalón 0, 165 turnos con pregunta de la ronda de
# cierre de L1: fallaban 79, y en 27 el bot se saltaba la pregunta y seguía con la reserva
# (la pregunta solo se contestaba si la reserva NO avanzaba ese turno); y al revés, con "?"
# contestaba pero no extraía los datos del mismo mensaje. Con el flag, la respuesta del RAG
# se lanza en paralelo en `_routing_phase`, la extracción sigue su camino normal y el
# cierre (o la salida anticipada de la extracción) pone la respuesta delante.
# Campo del estado -> pregunta de Jev que dice si el cliente lo AFIRMA en este mensaje (u3-4 lugar y
# actividad; u3-5 certificado, grupo y nacionalidad). El reparto por actividad cuelga de la del
# grupo: si el cliente no dice cuántos van, tampoco dice cómo se reparten.
_AFFIRMS_SIGNAL_FIELDS = (
    ("location", "affirms_location"),
    ("activity", "affirms_activity"),
    ("is_certified", "affirms_certification"),
    ("group_size", "affirms_group"),
    ("group_allocation", "affirms_group"),
    ("is_colombian", "affirms_nationality"),
)


def _has_pending_answer(state: ConversationState) -> bool:
    return getattr(state, "_pending_answer", None) is not None


def _lugar_desconocido(routing_signals: dict) -> bool:
    """CAL-C4 (`lugar_desconocido_al_rag`): ¿el cliente afirma un lugar que Jev, seguro, no reconoce como Cartagena ni
    las islas? ("En baru y Rosario", cal-55). Sin lista de nombres: lo que se sabe de ese lugar lo dice la base."""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = routing_signals.get("customer_place") or {}
    return (bool(routing_signals.get("affirms_location")) and lugar.get("choice") == "none"
            and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN)


def _maybe_launch_answer(state: ConversationState, message: str, routing_signals: dict) -> None:
    if _has_pending_answer(state):
        return
    if not _turn_has_question(message, routing_signals):
        if not _lugar_desconocido(routing_signals):
            return
        # CAL-C4 (17-oct): "En baru y Rosario" contestaba "Entiendo que te encuentras en Barú y Rosario" y nadie le
        # decía que en Barú no operamos (cal-55): el turno era una respuesta a la reserva y no llegaba a la base. Un
        # lugar afirmado que no es Cartagena ni las islas se le pregunta a la base, como una pregunta más.
        logger.info("[CORE][CAL-C4] lugar afirmado que no es Cartagena ni las islas: se consulta la base")
    # La foto del historial se toma AQUÍ (lección de la carrera de l1-4): la tarea puede no
    # arrancar hasta después de que el bot meta otra cosa en el historial.
    history = list(state.history)
    adelantado = getattr(state, "_rag_adelantado", None)
    if adelantado is not None and adelantado["mensaje"] == message:
        # rag-5: ya hay una respuesta en marcha desde antes del enrutador; se usa si su contexto es el mismo.
        state._rag_adelantado = None
        state._pending_answer = asyncio.create_task(_adoptar_o_rehacer(state, message, history, adelantado))
        return
    state._pending_answer = asyncio.create_task(_rag_answer(state, message, history=history))


async def _take_parallel_answer(state: ConversationState) -> str | None:
    task = getattr(state, "_pending_answer", None)
    state._pending_answer = None
    if task is None:
        return None
    try:
        return await task
    except Exception as exc:  # noqa: BLE001 — si el RAG falla, el turno sigue sin respuesta
        logger.warning(f"[CORE][U3-4] la respuesta en paralelo falló, sigue la reserva: {exc}")
        return None


async def attach_unused_answer(state: ConversationState, response):
    """Cierre del turno: una respuesta lanzada en paralelo que ninguna salida del turno recogio se
    pone delante en vez de cancelarse. Paso 5 (27-sep): salidas como el resumen ("Sure, here's
    what we have so far") o el recordatorio de un dato no la tomaban y la pregunta se quedaba sin
    contestar ("Hope you are operating on Easter Sunday? … How do we pay for the refresher?").
    La unica salida que la descarta a proposito (el "¿me recuerdas…?") ya la cancela antes."""
    if not isinstance(response, str) or not response or not _has_pending_answer(state):
        return response
    greeting = _greeting(state)
    return await _prepend_parallel_answer(state, response, greeting if response.startswith(greeting) else "")


def cancel_pending_answer(state: ConversationState) -> None:
    """Red de seguridad al cerrar el turno: una respuesta lanzada que nadie usó se cancela."""
    task = getattr(state, "_pending_answer", None)
    state._pending_answer = None
    if task is not None and not task.done():
        task.cancel()


def _is_rag_fallback(text: str | None) -> bool:
    """El "no lo tengo a la mano" del RAG, con la comprobación en un solo sitio
    (`rag_agent.is_fallback_answer`). Import perezoso, como el resto de usos de la
    RAG en este módulo."""
    from src.agents.rag_agent import is_fallback_answer

    return is_fallback_answer(text)


def _answer_replaces_the_booking_question(
    state: ConversationState, answer: str, *, finalized: bool = False
) -> bool:
    """u3-4: ¿la respuesta a la pregunta va SOLA, sin pegarle detrás la de la reserva?

    Dos casos, y los dos vienen de un fallo leído en vivo:

    1. **El RAG no sabe** (arreglo 1, escalón 1 del 24-sep). Si contesta "eso no lo
       tengo a la mano, ¿te paso con un asesor?" y detrás se pega "¿desde dónde
       saldrías?", el cliente recibe DOS preguntas y la segunda tapa la oferta de
       asesor. El camino antiguo (`_answer_question`) no encadenaba nada cuando la
       respuesta ya acababa preguntando; al mover esto a `_slotfill_close_phase` se
       relajó a "solo si el siguiente paso es el menú de actividades" y el caso se
       coló. `core_pending_slot` se queda como está: la reserva sigue en el turno
       siguiente, que es justo lo que hacía el camino antiguo.
    2. **La respuesta ya invita a elegir actividad** y lo siguiente sería el menú
       entero (fallo en vivo 2026-07-24), que era la condición original.
    """
    if _is_rag_fallback(answer):
        return True
    if not finalized and _answer_already_asks(answer):
        # CAL-C3b (17-oct): la regla vale para cualquier dato pendiente, como en el camino antiguo
        # (`_answer_question`). "¿En qué hotel de las islas se alojan? ¿En qué hotel o isla te hospedas?"
        # (cal-71/73): dos preguntas seguidas; la de la reserva queda pendiente para el turno siguiente.
        return True
    return not finalized and state.core_pending_slot == SLOT_ACTIVITY and _answer_already_asks(answer)


async def _prepend_parallel_answer(state: ConversationState, response: str, greeting: str) -> str:
    """Pone la respuesta en paralelo delante de una respuesta ya escrita (y ya metida en el
    historial). Sin respuesta pendiente, la deja igual.

    u3-4 arreglo 1: si el RAG no sabe, la respuesta va SOLA — no se le pega detrás la
    pregunta de la reserva (ver `_answer_replaces_the_booking_question`)."""
    answer = await _take_parallel_answer(state)
    if not answer:
        return response
    body = response[len(greeting):] if greeting and response.startswith(greeting) else response
    if _es_pregunta_de_origen(answer):
        ultimo = next((h.get("content") or "" for h in reversed(state.history or []) if h.get("role") == "user"), "")
        _fijar_origen_antes_del_precio(state, ultimo)
        merged = f"{greeting}{answer.rstrip()}"
    elif _is_rag_fallback(answer) or (_answer_asks_the_origin(state, answer) and _PREGUNTA_ORIGEN_RE.search(body)):
        merged = f"{greeting}{answer.rstrip()}"
    else:
        merged = f"{greeting}{answer.rstrip()}\n\n{body}"
    last = state.history[-1] if state.history else {}
    if last.get("role") == "assistant" and last.get("content") == response:
        last["content"] = merged
    return merged


# 6-oct (flag `rag_origen_pregunta`): con el origen desconocido el RAG pregunta ya "¿saldrías desde Cartagena o ya
# estás en las islas?"; si detrás se pegaba la pregunta del origen de la reserva, el cliente leía la misma pregunta dos
# veces seguidas.
# Solo se mira cuando la reserva iba a preguntar justo el origen (`SLOT_LOCATION`), así que basta con reconocer las
# formas de preguntarlo ("¿desde dónde prefieren salir?", "¿saldrían desde Cartagena o ya están en las islas?").
_PREGUNTA_ORIGEN_RE = re.compile(
    r"desde d[oó]nde|(sal|part)\w* desde cartagena o|(depart|leav)\w* from cartagena or|"
    r"where (would|will|do) you (be )?(depart|leav|start)|cartagena or (are you |you're )?already",
    re.IGNORECASE,
)


def _answer_asks_the_origin(state: ConversationState, answer: str) -> bool:
    """¿La reserva iba a preguntar el origen y la respuesta del RAG ya lo pregunta? Entonces va sola."""
    return state.core_pending_slot == SLOT_LOCATION and bool(_PREGUNTA_ORIGEN_RE.search(answer))


# 7-oct (Álvaro, opción C del punto 3; flag `rag_origen_pregunta`): si el cliente pide un PRECIO y no sabemos desde
# dónde sale, el bot pregunta el origen ANTES de cotizar (lo pide el golden) y lo hace el CÓDIGO, no el modelo: con
# instrucciones en el contexto del RAG (6-oct, V1 y V2) o repreguntaba lo que el cliente ya había dado a entender o
# volvía a cotizar Cartagena. La pregunta del precio se guarda y se contesta en cuanto el cliente dice el origen.
ORIGEN_ANTES_DEL_PRECIO_ES = (
    "Para darte el precio exacto necesito saber desde dónde sales: ¿saldrías *desde Cartagena* o ya estás *en las "
    "Islas del Rosario*? Los planes y los precios cambian según el punto de salida. 🌊"
)
ORIGEN_ANTES_DEL_PRECIO_EN = (
    "To give you the exact price I need to know where you're starting from: would you leave *from Cartagena* or are "
    "you already *on the Rosario Islands*? Plans and prices change depending on the departure point. 🌊"
)
_PIDE_PRECIO_RE = re.compile(
    r"cu[aá]nto (cuesta|cuestan|vale|valen|sale|salen|cobran|ser[ií]a|es\b)|\bprecios?\b|\bcostos?\b|\bcoste\b|"
    r"\btarifas?\b|\bvalor\b|how much|\bprices?\b|\bcosts?\b|\brates?\b|\bfees?\b",
    re.IGNORECASE,
)
# El precio de algo que no vendemos (el hotel, la noche) no depende de desde dónde sale el cliente.
_PRECIO_AJENO_RE = re.compile(
    r"hotel|alojamiento|hospedaje|por noche|la noche|habitaci|taxi|\bnights?\b|\brooms?\b|accommodation|lodging",
    re.IGNORECASE,
)
# Pistas del origen en lo que ha escrito el CLIENTE (el saludo del bot nombra los dos orígenes). Si el cliente ya
# nombró Cartagena o las islas, el origen se deja al RAG como siempre: preguntarlo sería repreguntar (lección de V1).
_PISTA_ORIGEN_RE = re.compile(r"cartagena|\bislas?\b|\bislands?\b|bar[uú]|tierra bomba", re.IGNORECASE)


# 7-oct (Gonzalo, ronda core origen-c-B): la puerta mira la RESPUESTA, no solo la pregunta. Mirando solo la pregunta
# fallaba por los dos lados: "Amigo el precio que está allí es en dólares o pesos?" (dice "precio", pero pregunta la
# MONEDA; antes se contestaba y con la puerta se quedaba sin respuesta) y "Gracias - y en pesos?" (pide un importe sin
# ninguna palabra de precio; el RAG cotizaba Cartagena). La regla de la opción C es "no cotizar sin origen": se
# comprueba justo eso, que la respuesta lleve un importe.
_IMPORTE_RE = re.compile(
    r"\d[\d.,]*\s*(?:cop|usd|us\$|d[oó]lares|dollars|pesos)\b|(?:usd|cop|us\$|\$)\s*\d",
    re.IGNORECASE,
)


def _origen_antes_del_precio(state: ConversationState, message: str, answer: str | None) -> str | None:
    """El texto fijo que pregunta el origen, si la respuesta del RAG (`answer`) cotiza sin saber desde dónde sale el
    cliente; si no, None (y la respuesta va tal cual).

    Cotiza = lleva un importe, y el cliente pide un precio o repregunta tras la pregunta del origen sin contestarla
    ("¿y en pesos?"). Un importe en la respuesta a otra cosa ("¿qué incluye?") se deja como hoy."""
    if state.location or state.detected_location:
        return None
    if _jev_dice_el_lugar(state):
        # gen-15: la puerta mira el origen antes de que la extracción del turno lo guarde, y sus pistas son palabras
        # («Cartagena», «islas», «Barú»): «We booked 3 nights at Mulata. How much is snorkeling?» se repreguntaba 2/2
        # con Jev seguro (islands 0,97). Si Jev está seguro de dónde está el cliente, el mensaje ya lo dice.
        return None
    texto = message or ""
    # ord-7: un enlace de reserva también depende del origen («mándame el enlace del Open Water» daba el de Cartagena).
    da_enlace = bool(answer) and "book.divingplanet.org" in answer
    if not answer or not (_IMPORTE_RE.search(answer) or da_enlace):
        return None
    jev = getattr(state, "_jev_pide_precio", None)
    if jev is not None:
        # ex-9b paso 5: Jev dice si pide el precio de NUESTRAS actividades (el hotel, la noche o un taxi no cuentan);
        # las palabras sueltas solo si Jev calla. "Me quedo en el hotel Caribe" ya no salta la puerta.
        pide = jev is True
    elif _PRECIO_AJENO_RE.search(texto):
        return None
    else:
        pide = bool(_PIDE_PRECIO_RE.search(texto))
    if not (pide or state.pregunta_precio_pendiente or da_enlace):
        return None
    del_cliente = [h.get("content") or "" for h in (state.history or []) if h.get("role") == "user"]
    este = [texto]
    if _jev_dice_que_no_lo_dice(state):
        # CAL-C3c: "bucear en islas del rosario" nombra las islas sin decir dónde está el cliente (cal-71/73); si Jev
        # está seguro de que ESTE mensaje no dice su origen, sus palabras no cuentan como pista y se pregunta antes de
        # cotizar. El mensaje ya está en el historial cuando contesta el RAG: se quita de ahí también.
        este = []
        if del_cliente and del_cliente[-1] == texto:
            del_cliente = del_cliente[:-1]
    if any(_PISTA_ORIGEN_RE.search(t) for t in [*del_cliente, *este]):
        return None
    pregunta = ORIGEN_ANTES_DEL_PRECIO_ES if state.language == "es" else ORIGEN_ANTES_DEL_PRECIO_EN
    variantes = _dos_variantes(state, answer, con_enlace=da_enlace)
    if variantes:
        tras = (ORIGEN_TRAS_LOS_ENLACES_ES, ORIGEN_TRAS_LOS_ENLACES_EN) if da_enlace else (
            ORIGEN_TRAS_LAS_VARIANTES_ES, ORIGEN_TRAS_LAS_VARIANTES_EN)
        pregunta = f"{variantes}\n\n{tras[0] if state.language == 'es' else tras[1]}"
    resto = _sin_importes(answer)
    return f"{resto}\n\n{pregunta}" if resto else pregunta


# s4-31 (8-oct, flag `origen_conserva_respuesta`): en la ronda del golden visible con Luna (`2026-10-08-luna-visible`),
# 6 de los 33 fallos del RAG eran de la puerta del origen: la pregunta fija SUSTITUÍA la respuesta entera y se perdía lo
# que no era el precio ("no hay precio especial para colombianos, solo cambia la moneda", "con 1,5 años no hace falta
# el refresher", "el refresher tiene el coste del minicurso"). Ahora se quitan solo las frases con un importe y la
# pregunta final de la respuesta (la sustituye la del origen); si no queda nada que decir, solo la pregunta.
_FRASE_RE = re.compile(r"(?<=[.!?])\s+")
# Escalón 0 en PRE (8-oct): además del importe dependen del origen el link de reserva (uno por origen: se dejaba el de
# Cartagena mientras se preguntaba el origen) y lo que incluye ("Incluye lancha ida y vuelta y almuerzo" es solo de
# Cartagena, y sin la frase del precio se quedaba sin sujeto).
_DEPENDE_DEL_ORIGEN_RE = re.compile(
    rf"{_IMPORTE_RE.pattern}|book\.divingplanet\.org|^\W*(?:esto |el plan |el curso |el paquete )?(?:incluye|includes|it includes)\b"
    r"|desde cartagena|from cartagena|cartagena-islas|islands-cartagena|almuerzo|\blunch\b",
    re.IGNORECASE,
)


def _sin_importes(answer: str) -> str:
    lineas = []
    for linea in (answer or "").splitlines():
        if not _DEPENDE_DEL_ORIGEN_RE.search(linea):
            lineas.append(linea)
            continue
        frases = [f for f in _FRASE_RE.split(linea) if f.strip() and not _DEPENDE_DEL_ORIGEN_RE.search(f)]
        if frases:
            lineas.append(" ".join(frases))
        else:
            # El título de una lista que se ha quitado entera ("los precios son:"). gen-6 (21-oct): "La salida de 2
            # inmersiones cuesta:", una línea en blanco y la lista de precios dejaba el título colgado ("…cuesta:" y
            # luego la pregunta del origen): el título se busca saltando las líneas en blanco.
            ultima = len(lineas) - 1
            while ultima >= 0 and not lineas[ultima].strip():
                ultima -= 1
            if ultima >= 0 and lineas[ultima].rstrip().endswith(":"):
                del lineas[ultima:]
    # La pregunta final (casi siempre "¿quieres el link / que te ayude a reservar?") la sustituye la del origen.
    while lineas and not lineas[-1].strip():
        lineas.pop()
    if lineas:
        frases = _FRASE_RE.split(lineas[-1].strip())
        while frases and "?" in frases[-1]:
            frases.pop()
        lineas[-1] = " ".join(frases)
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return texto if len(texto) >= 40 else ""


def _es_pregunta_de_origen(answer: str | None) -> bool:
    return bool(answer) and any(p in answer for p in (ORIGEN_ANTES_DEL_PRECIO_ES, ORIGEN_ANTES_DEL_PRECIO_EN,
                                                      ORIGEN_TRAS_LAS_VARIANTES_ES, ORIGEN_TRAS_LAS_VARIANTES_EN,
                                                      ORIGEN_TRAS_LOS_ENLACES_ES, ORIGEN_TRAS_LOS_ENLACES_EN))


# ord-7 (21-oct, flag `origen_dos_variantes`, decisión de Gadea con ord-0): sin saber el origen, la puerta quitaba el
# precio, lo que incluye, el almuerzo y el enlace, y el cliente se quedaba sin nada de lo que preguntó (g10-029: «¿hay
# comida?», g9-003: «¿qué incluye?»). Con las dos variantes del catálogo se contesta sin suponer el origen; la pregunta
# del origen va después, para el enlace y el plan exacto.
ORIGEN_TRAS_LAS_VARIANTES_ES = "¿Saldrías *desde Cartagena* o ya estás *en las Islas del Rosario*? Así te paso el plan y el enlace exactos. 🌊"
ORIGEN_TRAS_LAS_VARIANTES_EN = "Would you leave *from Cartagena* or are you already *on the Rosario Islands*? Then I'll send you the exact plan and booking link. 🌊"
ORIGEN_TRAS_LOS_ENLACES_ES = "Reserva con el de tu punto de salida. ¿Saldrías *desde Cartagena* o ya estás *en las Islas del Rosario*? 🌊"
ORIGEN_TRAS_LOS_ENLACES_EN = "Book with the one for your starting point. Would you leave *from Cartagena* or are you already *on the Rosario Islands*? 🌊"
_VARIANTE = {
    "es": {"cartagena": ("Desde Cartagena", "lancha ida y vuelta desde el Muelle de la Bodeguita"),
           "island": ("Ya en las islas", "recogida en tu hotel si tiene acceso marítimo"),
           "titulo": "{actividad}, según desde dónde salgas (precio online por persona):",
           "con_almuerzo": "almuerzo incluido", "sin_almuerzo": "sin almuerzo"},
    "en": {"cartagena": ("From Cartagena", "round-trip boat from Muelle de la Bodeguita"),
           "island": ("Already on the islands", "pickup at your hotel if it has sea access"),
           "titulo": "{actividad}, depending on where you start from (online price per person):",
           "con_almuerzo": "lunch included", "sin_almuerzo": "no lunch"},
}


def _dos_variantes(state: ConversationState, answer: str = "", con_enlace: bool = False) -> str | None:
    """Las dos salidas de la actividad de la que pregunta el cliente, del catálogo: precio online por persona en su
    moneda (`src/flows/moneda.py`), el transporte y si lleva almuerzo. None si
    no hay una actividad concreta con un solo plan por origen (los paquetes de buceo tienen varios) o si el importe que
    dio el RAG (`answer`) no es de ninguna de las dos: la actividad anotada no era la cotizada (banco ord-7: «tengo el
    Open Water, ¿cuánto cuesta el repaso?» anotaba el Open Water y salían los precios del curso). `con_enlace`: cada
    variante lleva su enlace de reserva (el RAG había dado uno sin saber el origen)."""
    from src.flows.catalog import SERVICES  # lazy

    actividad = state.actividad_preguntada or state.detected_activity or state.suggested_activity
    if not actividad:
        return None
    servicios = []
    for origen in ("cartagena", "island"):
        ids = dom.service_ids(actividad, origen)
        servicio = SERVICES.get(ids[0]) if len(ids) == 1 else None
        if not servicio:
            return None
        servicios.append((origen, servicio))
    if answer and not _cotiza_alguno(answer, [s for _, s in servicios]) and not _enlaza_alguno(answer, servicios, state):
        return None
    lang = "es" if state.language == "es" else "en"
    textos = _VARIANTE[lang]
    lineas = [textos["titulo"].format(actividad=f"*{dom.label(actividad, lang)}*")]
    for origen, servicio in servicios:
        precio = moneda.precio(state, servicio.get("price_usd"), servicio.get("price_cop"))
        if not precio:
            return None
        nombre, transporte = textos[origen]
        almuerzo = textos["con_almuerzo" if "almuerzo" in (servicio.get("includes_es") or "").lower() else "sin_almuerzo"]
        linea = f"• *{nombre}*: {precio}, {transporte}; {almuerzo}."
        url = cart_render._resolve_service_booking_url(servicio, state) if con_enlace else None
        lineas.append(f"{linea} {url}" if url else linea)
    return "\n".join(lineas)


def _enlaza_alguno(answer: str, servicios: list[tuple[str, dict]], state: ConversationState) -> bool:
    """¿La respuesta lleva el enlace de reserva de alguna de las dos variantes?"""
    urls = (cart_render._resolve_service_booking_url(s, state) or "" for _, s in servicios)
    return any(u and u.split("?")[0] in answer for u in urls)


def _puerta_del_origen(state: ConversationState, message: str, answer: str) -> str:
    """La respuesta del RAG tras la puerta del origen (opción C): la pregunta del origen (con las dos variantes, ord-7)
    si cotiza o enlaza sin saber el origen; si no, la respuesta tal cual. gen-19 (21-oct) añadía aquí el enlace cuando
    tocaba; se quitó por decisión de Gadea: en su banco no cambiaba nada (el enlace ya salía cuando lo piden). ord-9
    (la lista de qué incluye, de la ficha) se retiró en arq-2c (22-oct): la da el redactor de hechos."""
    return _origen_antes_del_precio(state, message, answer) or answer


def _cotiza_alguno(answer: str, servicios: list[dict]) -> bool:
    """¿Alguna cifra de la respuesta es un precio (online o normal, USD o COP) de estos servicios? Todas las cifras, no
    solo los `_IMPORTE_RE`: ese corta «$124 USD» en «$1»."""
    precios = {str(round(float(s[k]))) for s in servicios
               for k in ("price_usd", "price_usd_normal", "price_cop", "price_cop_normal") if s.get(k)}
    return any(re.sub(r"\D", "", cifra) in precios for cifra in re.findall(r"\d[\d.,]*", answer))


def _fijar_origen_antes_del_precio(state: ConversationState, pregunta: str) -> None:
    """La pregunta del origen ocupa el turno: queda pendiente el origen (con los botones de siempre) y se guarda la
    pregunta del precio para contestarla cuando el cliente lo diga."""
    ask_slot(state, SLOT_LOCATION)  # solo por lo que deja en el estado: el slot pendiente y sus botones
    anterior = state.pregunta_precio_pendiente
    if anterior and not _pide_precio(state, pregunta):
        # arq-8f (banco arq-8c de Gadea, #1667): con una pregunta de precio guardada, «soy de Medellín» (no dice el origen)
        # vuelve a pedirlo y pisaba la pregunta con ese mensaje; luego se contestaba «soy de Medellín». Se queda la de
        # antes, salvo que este mensaje pregunte otro precio.
        pregunta = anterior
    state.pregunta_precio_pendiente = pregunta
    logger.info("[CORE][ORIGEN] precio sin origen -> se pregunta el origen antes de cotizar")


def _pide_precio(state: ConversationState, mensaje: str) -> bool:
    """¿Este mensaje pide un precio? Lo dice Jev (ex-9b paso 5); si calla, las palabras de siempre."""
    jev = getattr(state, "_jev_pide_precio", None)
    if jev is not None:
        return jev is True
    return bool(_PIDE_PRECIO_RE.search(mensaje or "")) and not _PRECIO_AJENO_RE.search(mensaje or "")


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


# s4-2 (19-oct): el código de cada nodo del subgrafo `booking` vive en `src/agents/nucleo/<nodo>.py` (ver su
# `__init__`). Se re-exporta aquí para que `maybe_handle_turn`, el resto del código, los scripts y los tests lo sigan
# encontrando en este módulo. Va al final a propósito: esos módulos importan de aquí lo común, que tiene que estar ya
# definido.
from src.agents.nucleo.availability import (  # noqa: E402, F401
    _availability_phase,
    _modo_posventa,
    _reserva_nueva_en_curso,
    _tras_el_pase,
)
from src.agents.nucleo.extraction import (  # noqa: E402, F401
    _ADDED_PERSON_RE,
    _ADDITION_CUE,
    _ADDITION_CUE_RE,
    _BARE_HEADCOUNT_RE,
    _BOOL_SLOT_FIELD,
    _COURSE_SOLO_RE,
    _LLM_RESOLVABLE_SLOTS,
    _MENTIONS_PERSON_RE,
    _NAMED_PERSON_RE,
    _NOT_ALONE_RE,
    _PLURAL_COMPANION_RE,
    _SINGULAR_COMPANION_RE,
    _SLOT_PREV_KEY,
    _SLOT_STATE_FIELD,
    _WORD_TO_NUM,
    _activity_has_textual_backing,
    _add_or_ask_companion,
    _apply_question_turn_answers,
    _apply_resolved_slot_value,
    _consume_number,
    _extraction_phase,
    _extraction_phase_body,
    _flag_cert_or_course,
    _jev_dice_ya_contada,
    _jev_pending_answer,
    _jev_rules_out_special_signals,
    _menciona_a_alguien,
    _mentions_person,
    _message_numbers,
    _number_of_something_else,
    _pista_del_regex,
    _question_turn_fields,
    _recommend_inferred_minicourse,
    _restore_main_diver_fields,
    _singular_companion,
    _state_known_fields,
    _turn_answered_a_different_slot,
    _understand,
)
from src.agents.nucleo.extractor import (  # noqa: E402, F401
    _CAMPOS_ACTIVIDAD,
    _CAMPOS_CERTIFICACION,
    _CAMPOS_DEL_PASE,
    _CAMPOS_GRUPO,
    _CAMPOS_LUGAR,
    _CATEGORIA_DEL_REPARTO,
    _CORRECTABLE_FIELDS,
    _amplia,
    _aplicar_extractor,
    _conservar_hotel,
    _guardar_lo_dicho,
    _has_correction_cue,
    _hotel_del_catalogo,
    _jev_says_not_affirmed,
    _nombre_del_extractor,
    _pasa_la_puerta_de_hoy,
    _poner_actividad,
    _poner_certificacion,
    _poner_grupo,
    _poner_hotel,
    _poner_nacionalidad,
    _poner_refresher,
    _poner_ubicacion,
    _quitar_provisional,
    _reparto_guardado,
    _reparto_valido,
    _route_contradictions,
    _sabido_para_extractor,
    campos_del_extractor,
    cancelar_extraccion_adelantada,
    datos_del_extractor,
    guardar_lo_dicho_en_el_pase,
    guardar_lo_dicho_sin_nucleo,
    lanzar_extraccion_adelantada,
)
from src.agents.nucleo.routing import (  # noqa: E402, F401
    _CONFIRMS_DESCRIBED_PACKAGE_RE,
    _DELIBERATION_RE,
    _HOTEL_UNKNOWN_RE,
    _accept_pending_correction,
    _apply_short_answer,
    _assign_split_share,
    _button_value,
    _comparison_query,
    _compose_comparison,
    _departure_place,
    _is_deliberation_between_options,
    _looks_like_deliberation,
    _maybe_apply_confirmed_package,
    _mentioned_offerings,
    _quantity_answer,
    _routing_phase,
    _with_main_rest,
    _word_ages,
    sembrar_senales_del_turno,
)
from src.agents.nucleo.setup import (  # noqa: E402, F401
    _NAME_TRIGGER_SIN_SOY_RE,
    _SWITCH_TO_EN_RE,
    _SWITCH_TO_ES_RE,
    _capture_client_name,
    _idioma_del_extractor,
    _setup_phase,
)
from src.agents.nucleo.slotfill_close import (  # noqa: E402, F401
    _build_cart_from_slots,
    _colombian_summary_lines,
    _derive_kids_counts,
    _finalize,
    _nota_seguridad,
    _prune_applied_corrections,
    _refresher_note,
    _siguiente_pregunta,
    _slotfill_close_phase,
    _tarjeta_sin_seguridad,
)
