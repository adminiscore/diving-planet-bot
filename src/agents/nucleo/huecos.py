"""Los huecos de la reserva (lat-9 paso 4, 27-oct; antes en `conversational_core`): sus nombres, cuál falta
(`next_missing_slot`, el ÚNICO obligatorio que falta, en el orden del plan) y lo que el estado ya sabe de cada uno.
No depende del núcleo: lo usan las preguntas, el origen y cada nodo."""

from __future__ import annotations

from src.domain import activities as dom
from src.flows import (
    cart_render,
    eligibility,
)
from src.flows.state import ConversationState
from src.utils.text import strip_accents

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
    if act == "certified_diving" and state.is_certified is None and not _certificacion_ya_preguntada(state) and not (
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


# LAT-0b: un trozo de cada forma de la pregunta de la certificación (`ask_slot`), en minúsculas y sin tildes.
_PREGUNTAS_DE_CERTIFICACION = {
    "es": ("me confirmas que tienes tu certificacion", "me confirmas que tienen su certificacion",
           "eres buzo certificado?", "son buzos certificados?"),
    "en": ("can you confirm you have your certification", "can you confirm you all have your certification",
           "are you a certified diver?", "are you certified divers?"),
}


def _certificacion_ya_preguntada(state: ConversationState) -> bool:
    """LAT-0b (26-oct, decisión de Gadea #2040): la certificación se pregunta UNA vez; si el cliente contesta otra cosa,
    no se insiste (mod-2: elegir el buceo certificado no la confirma). Cuenta la que el cliente VIO: un mensaje del bot
    que la trae, en el idioma de ahora (si pidió otro, no la entendió). Marcarla al prepararla no valía: hay turnos en
    que se prepara y sale otra pregunta (el origen), y entonces no se hacía nunca."""
    trozos = _PREGUNTAS_DE_CERTIFICACION.get(state.language, ())
    return any(trozo in strip_accents((t.get("content") or "").lower()) for t in (state.history or [])
               if t.get("role") == "assistant" for trozo in trozos)


def _resolve_cert_plan(state: ConversationState) -> str | None:
    """Plan de buceo certificado desde los conteos detectados (sin consumirlos),
    o el recomendado por defecto. Determinista, del catálogo."""
    dives = state.detected_cert_dives
    if dives is None and state.detected_cert_days in _DAYS_TO_DIVES:
        dives = _DAYS_TO_DIVES[state.detected_cert_days]
    base = _DIVES_TO_BASE_PLAN.get(dives or 2, "2_dives_1_day")
    return cart_render.service_for_location(base, state)


# Actividades de un dia que el nucleo cierra con carrito -> tipo de item. Sale del
# registro de actividades (F3a de docs/robustness/activity-domain-plan.md).
_ACTIVITY_TO_CART_TYPE = {
    activity_id: dom.by_id(activity_id).cart_type for activity_id in dom.day_activity_ids()
}


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
