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
from src.domain import activities as dom
from src.flows import cart_render, eligibility
from src.flows.como_reserva import (
    HOTEL_PRIMERO,
    como_reserva,
    hotel_conocido,
)
from src.flows.state import ConversationState, Step
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


# SLOT_COMPANION_QTY NO lo rastrea `next_missing_slot`, así que con la reserva
# principal ya resuelta `advanced` es espuriamente True y el bloque genérico
# Fase C (gate `not advanced`) lo saltaría. SLOT_COMPANION_ACTIVITY sí sale de
# `next_missing_slot` (CALN-2 paso 3a). Los dos tienen su bloque de lectura
# dedicado en maybe_handle_turn (gate `not resolved_short`).




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
    # seguia "cubriendo" el grupo, asi que el grupo parecia completo.
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
    varios días: certificarse no cabe en un día.

    CALN-2 (27-oct): más lo que puede hacer cada edad sabida del grupo: con una niña de 9, Bubble Makers (sparring
    CALN1-04). Las de un adulto se quedan siempre: las edades no dicen quién falta por elegir.

    CALN-2 (27-oct, tanda de precios q1): quien falta por elegir puede ser un buzo certificado («uno es buzo certificado
    y los otros dos queremos snorkel»), y `personas` aún no guarda la certificación de cada uno. Si nadie del grupo ha
    dicho que no lo está (`acompanante_sin_certificar`), el buceo certificado también se recomienda (su texto dice que
    es para buzos ya certificados) y elige el cliente; primero si se sabe que es un buzo sin bucear hace tiempo.
    Con el lector del grupo (flag `lector_grupo`), lo que dice de quienes faltan por elegir manda sobre esa bandera de
    «otra persona»: todos certificados, el buceo primero; ninguno, sin él (`sin_decidir_certificados`)."""
    edades = [e for e in state.detected_ages or [] if isinstance(e, int)]
    por_edad = [eligibility.beginner_options_for_age(e) for e in [None, *edades]]
    options: list[str] = []
    for opcion in (eligibility.option_activity_id(o) for grupo_edad in por_edad for o in grupo_edad):
        if opcion not in options:
            options.append(opcion)
    options.sort(key=lambda o: o == "companion")  # ir de acompañante, siempre la última
    if state.detected_duration == "multi_day" and "minicourse" in options:
        options.insert(options.index("minicourse") + 1, "padi_open_water")
    certificados = state.sin_decidir_certificados
    # Que el lector diga «no certificado» no quita el buceo si el extractor dijo que otra persona lo está pero lleva tiempo
    # sin bucear (s03 del sparring: «he hasn't been diving in 3 years» leído como no certificado).
    sin_certificar = ((certificados is False and not state.acompanante_certificado_inactivo)
                      or (certificados is None and state.acompanante_sin_certificar))
    if not sin_certificar and "certified_diving" not in options:
        primero = certificados is True or state.acompanante_certificado_inactivo
        donde = 0 if primero else len(options) - ("companion" in options)
        options.insert(donde, "certified_diving")
    if certificados is True:
        # Sparring s29c (pareja de Barú, los dos Advanced): a quien ya está certificado no se le ofrecen el minicurso
        # ni el curso Open Water, que son para quien no bucea.
        options = [o for o in options if o not in ("minicourse", "padi_open_water")]
    return [o for o in options if dom.by_id(o) is not None]


OTRA_COSA = "otra_cosa"  # el «No» de «¿también va a bucear?»: se le recomiendan las opciones


def _pregunta_si_tambien_bucea(state: ConversationState) -> bool:
    """CALN-8 (pareja Advanced, golden precio-desde-islas-vs-cartagena; decisión de Gadea #2475): quien escribe va a
    bucear y quien falta por elegir está certificado (el lector del grupo). En vez de «¿un día o varios?» y las opciones,
    una pregunta de sí o no: «¿la otra persona también va a bucear?». Sí = el buceo certificado; no = las opciones
    (`sin_decidir_certificados` deja de ser True). Sin adivinar: «somos una pareja Advanced» y «mi esposa y yo somos
    buzos, los niños quieren probar» (g12) se leen igual, y en las dos se pregunta."""
    return (state.sin_decidir_certificados is True and state.detected_activity == "certified_diving"
            and bool(state.pending_undecided_qty))


# EX-FLUJO-1 (decisión de Gadea, 14-oct): las preguntas que se pueden dejar para antes del resumen si el cliente no
# las contesta. No condicionan a otras; la actividad, la certificación y las confirmaciones sí, y no se aplazan. Qué
# hará quien aún no ha elegido tampoco: si no contesta, se le vuelve a preguntar antes del resumen (CALN-2 paso 3a).
_SLOTS_APLAZABLES = frozenset({
    SLOT_COMPANION_ACTIVITY, SLOT_LOCATION, SLOT_HOTEL, SLOT_QTY, SLOT_SAFETY, SLOT_REFRESHER, SLOT_AGES,
    SLOT_NATIONALITY,
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
    if (state.needs_cert_or_course and state.is_certified is None
            and not (state.detected_group_allocation or {}).get("certified_diving")):
        # Nivel PADI nombrado sin decir si ya lo tienen o lo quieren (owner
        # 2026-09-15): se aclara antes de cotizar nada. Sparring s04i (embarazada, 3 veces): si ya se sabe o el reparto
        # ya lleva a un buzo («mi esposo es Advanced», ella snorkel), la pregunta sobra, como la de la certificación.
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
    if state.needs_companion_activity and SLOT_COMPANION_ACTIVITY not in saltar:
        # Quién hace qué, antes que el origen: el plan y el precio dependen de eso (CALN-2 paso 3a, orden aprobado por
        # Gadea el 27-oct). Antes se aplazaba, con dos esperas, hasta que no faltara nada más.
        return SLOT_COMPANION_ACTIVITY
    if not state.location and SLOT_LOCATION not in saltar:
        return SLOT_LOCATION
    if state.location == "island" and not state.hotel and SLOT_HOTEL not in saltar:
        return SLOT_HOTEL
    if como_reserva(state) == HOTEL_PRIMERO:
        return None  # CALN-35: sin hotel no se sigue con la reserva; lo dice `slotfill_close._hotel_primero`
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
    # Sparring s03g (3-nov): «I've lived in Miami since I was a baby» marca niños (la palabra «baby») y, con el grupo ya
    # en 1 persona, se preguntaba «You mentioned minors are coming, what are their ages?». Un grupo de uno no trae menores.
    solo_uno = state.detected_group_size == 1 and not state.detected_group_allocation
    if state.kids_mention_detected and not state.detected_ages and not solo_uno and SLOT_AGES not in saltar:
        return SLOT_AGES
    if state.is_colombian is None and SLOT_NATIONALITY not in saltar:
        return SLOT_NATIONALITY
    return None



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


# CALN-6 paso 2 (sparring CALN4: «¡Bienvenidos!», «¡Con mucho gusto te ayudo a armar el plan!» debajo del saludo en 4
# de 10 primeros turnos): la calidez del saludo. Si en el turno contesta el escritor, que ya da la bienvenida, el
# compositor la quita y el saludo se queda en la presentación (`compositor._sin_saludo_repetido`).
CALIDEZ_DEL_SALUDO = {"es": "¡Qué alegría tenerte por acá! Con muchísimo gusto te ayudo a armar tu plan. ",
                      "en": "So happy to have you here! I'd love to help you put your plan together. "}


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
            f"las Islas del Rosario, saliendo desde Cartagena o desde las propias islas. {CALIDEZ_DEL_SALUDO['es']}🌊\n\n"
        )
    saludo = f"Hi, {name}! 🪸" if name else "Hi! 🪸"
    return (
        f"{saludo} I'm *Coral* from *Diving Planet* — we dive year-round in the Rosario "
        f"Islands, departing from Cartagena or right from the islands. {CALIDEZ_DEL_SALUDO['en']}🌊\n\n"
    )


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


def _el_extractor_calla_el_lugar(state: ConversationState) -> bool:
    """DEUDA-ORIGEN (26-oct): ¿el extractor ya leyó el mensaje de este turno y no dice desde dónde sale el cliente? Si
    aún no ha acabado o falló, no se sabe (False)."""
    leida = getattr(state, "_lectura_del_turno", None)
    if leida is not None:
        return leida[1] is not None and not leida[1].get("location")
    tarea = getattr(state, "_extraccion_adelantada", None)
    if tarea is None or not tarea.done() or tarea.cancelled() or tarea.exception() is not None:
        return False
    datos = tarea.result()
    return datos is not None and not datos.get("location")


def _jev_dice_el_lugar(state: ConversationState) -> bool:
    """gen-15: ¿Jev está seguro (≥ `CUSTOMER_PLACE_MIN`) de que el mensaje dice dónde está el cliente (Cartagena o las
    islas)? Lo contrario de `_jev_dice_que_no_lo_dice`. DEUDA-ORIGEN (decisión de Gadea, 26-oct): con el extractor
    callado no vale ("Estaremos visitando Cartagena…": Jev dice cartagena, y el viaje no dice la salida)."""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    if _el_extractor_calla_el_lugar(state):
        return False
    lugar = getattr(state, "_jev_lugar", None) or {}
    return lugar.get("choice") in ("islands", "cartagena") and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN


def _jev_dice_que_no_lo_dice(state: ConversationState) -> bool:
    """CAL-C3c: ¿Jev está seguro (≥ `CUSTOMER_PLACE_MIN`) de que el mensaje no dice dónde está el cliente?"""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}
    return lugar.get("choice") == "none" and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN


def _jev_duda_del_lugar(state: ConversationState, datos: dict | None) -> bool:
    """CALN-9 (4-nov): el extractor lee un lugar en este mensaje; ¿Jev no está seguro de que el cliente lo afirme? «What if I
    decide to stay one day longer in rosario» o «¿y si nos quedamos una noche más en las islas?» son hipótesis: el extractor
    leía «ya en las islas» y salían el precio y la recogida del otro origen. Medido (banco-origen-hipotesis ×6 y 138 lecturas
    de otros bancos): quien lo afirma tiene a Jev en 0,98-1,00 y las hipótesis en 0,16-0,48; así, solo 2 lecturas buenas
    pasan a confirmarse. Quien contesta a la pregunta del origen («Desde Cartagena») también tiene a Jev seguro. Sin Jev,
    como hoy. No si nombra un hotel de las islas (ARQ-8b: «the Ubuntu hotel», con Jev a 0,52)."""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy
    from src.agents.nucleo.lectura import hotel_de_las_islas as _hotel_de_las_islas  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}
    if not lugar or (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN:
        return False
    hotel = (datos or {}).get("hotel")
    return not (isinstance(hotel, str) and _hotel_de_las_islas(hotel))


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
        "hotel": hotel_conocido(state),
        "ages": state.detected_ages,
        "last_dive_over_2_years": state.last_dive_over_2_years
        if state.last_dive_over_2_years is not None
        else state.detected_last_dive_over_2_years,
        "is_colombian": state.is_colombian,
    }
    return candidates


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
        hotel = hotel_conocido(state)
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
        if not hotel_conocido(state):
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
    extra: dict = {}
    if item_type == "cert":
        plan = _resolve_cert_plan(state)
        del_plan = plan_del_estado(state)  # CALN-43
        if del_plan.veces > 1:
            extra["veces"] = del_plan.veces
        if del_plan.asesor_cierra_el_precio:
            extra["asesor_cierra_el_precio"] = True
    elif item_type == "course":
        plan = state.detected_service_id if activity == state.detected_activity else dom.base_service_id(activity)
        if plan:
            plan = cart_render.service_for_location(plan, state)
    elif dom.cart_activity_for_type(item_type) not in (None, activity) and dom.base_service_id(activity):
        # Sparring s04b (4-nov, Majagua): Bubble Makers comparte el tipo «beginner» con el minicurso, y sin plan propio el
        # ítem salía con el servicio del minicurso y su enlace («Dive Mini Course» dos veces, una para el niño de 9).
        plan = cart_render.service_for_location(dom.base_service_id(activity), state)
    return {"type": item_type, "qty": qty, "plan": plan,
            "label": cart_render.cart_label_for(item_type, plan, state.language), **extra}


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
    sin_precio: bool = False, puerta_al_recoger: bool = False,
) -> str:
    from src.agents import supervisor  # lazy

    # l1-4: las notas de ESTE mensaje pueden estar calculándose en paralelo. Aquí
    # es donde se usan (van dentro del contexto del RAG), así que aquí se espera.
    await await_pending_notes(state)
    if not sin_precio and (con_hechos := await _con_hechos(state, message,
                                                            state.history if history is None else history)):
        return await _con_la_entrega(state, message, con_hechos, history)
    if state.is_colombian is None:
        # gen-14 (21-oct): «Somos de Cali… ¿cuánto vale la salida?» se cotizaba en USD porque el RAG se escribía antes de
        # que la extracción guardara la nacionalidad. Bloque 1: espera a lo guardado, en vez de una copia del estado.
        from src.agents.nucleo.extractor import con_lo_guardado  # lazy

        await con_lo_guardado(state, message)
    entradas = _entradas_rag(state, state.history if history is None else history, message)
    if hechos := await _hechos_para_el_rag(state, message, state.history if history is None else history):
        entradas["hechos"] = hechos  # arq-1g
        entradas["hechos_bloques"] = state._hechos_del_rag
    pieza_pedida = not sin_precio and _precios_por_codigo(state, entradas)
    if sin_precio:  # G3-07a: solo se pasa cuando hace falta (la llamada de siempre no cambia)
        entradas["sin_precio"] = True
    answer = await supervisor.rag_answer(rag_query or message, **entradas)
    contar_si_el_escritor_pregunta(entradas, answer)
    if sin_precio and answer:
        # CALN-3 paso 3 «A» (r01): con la tarjeta no va la pieza de precios, pero sí lo que dicen los hechos del
        # descuento de grupo (aplica, o no aplica a un curso PADI); el escritor ya no habla de él (RAG_SIN_PRECIO).
        from src.agents import redactor_hechos  # lazy

        if nota := await redactor_hechos.nota_de_grupo(state, message, state.history if history is None else history):
            answer = redactor_hechos.con_la_pieza(answer, nota)
    # 7-oct (opción C): si cotiza sin origen, se pregunta el origen; quien la recibe deja el estado preparado
    # (`_fijar_origen_antes_del_precio`).
    answer = _con_la_puerta(state, message, answer, al_recoger=puerta_al_recoger, sin_precio=sin_precio,
                            pieza_pedida=pieza_pedida)
    if puerta_al_recoger:
        return answer  # la entrega se pinta al recoger, con lo que la extracción de este mensaje ya guardó
    return await _con_la_entrega(state, message, answer, history)


async def _con_la_entrega(state: ConversationState, message: str, answer: str | None, history: list | None) -> str | None:
    """Bloque 4R (C3): lo del momento de reservar (el enlace, el origen, el asesor) lo pinta el código a la salida del escritor."""
    from src.agents.nucleo.entrega import pintar_la_entrega  # lazy

    return await pintar_la_entrega(state, message, answer, state.history if history is None else history)


def _con_la_puerta(state: ConversationState, message: str, answer: str, *, al_recoger: bool,
                   sin_precio: bool = False, pieza_pedida: bool = False) -> str:
    """La puerta del origen, ya o al recoger la respuesta. Sparring s04c (jubilados t2, «Desde Cartagena. Somos
    argentinos. ¿Y mi esposa qué puede hacer?»): la respuesta en paralelo (u3-4) corre a la vez que la extracción, y la
    puerta miraba el estado antes de que la extracción de ESTE mensaje guardara el origen: los precios de los dos
    orígenes y la pregunta del origen, y debajo otra vez la de la reserva. Con `al_recoger`, la puerta la pone
    `_take_parallel_answer`, cuando la extracción ya acabó (gen-15 lo arreglaba con Jev solo en una de sus ramas)."""
    if al_recoger:
        state._puerta_al_recoger = (message, sin_precio, pieza_pedida)
        return answer
    return _puerta_del_origen(state, message, answer, sin_precio=sin_precio, pieza_pedida=pieza_pedida)


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
    """
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
    if getattr(state, "_turno_de_la_reserva", False):
        entradas["sin_preguntas"] = True  # CALN-43: la pregunta la pone el código al final
    if _plan_en_curso(state):
        entradas["sin_ofrecer_el_pase"] = True  # bloque 4R (C4): el pase lo decide el código (`nucleo/entrega.py`)
    return entradas


def _plan_en_curso(state: ConversationState) -> bool:
    """Bloque 4R (C4): hay una reserva nueva en marcha (una actividad o un carrito), no una posventa ni un pase ya hecho. Más ancho que
    `_turno_de_la_reserva`, que es falso en el primer mensaje y tras la tarjeta (diseño 4R, v2)."""
    return (bool(state.detected_activity or state.detected_group_allocation or state.mixed_cart)
            and not state.ya_reservado and state.step != Step.ESCALATE)


def marcar_turno_de_la_reserva(state: ConversationState) -> None:
    """CALN-43, qué preguntar (decisión de Gadea, 6-nov; sustituye a lat-9 paso 2): en un turno de la reserva el escritor no pregunta.
    La pregunta la decide la tabla (`src/flows/que_preguntar.py`) después de leer el mensaje y la pone el código, una vez y al final. Sin
    la reserva en marcha (ni el idioma ni el pase), el escritor contesta como siempre."""
    state._turno_de_la_reserva = bool(state.core_pending_slot) and state.step == Step.FREE_TEXT


def contar_si_el_escritor_pregunta(entradas: dict, answer: str | None) -> None:
    """Bloque 0,5 del Plan Gadea («primero cubre, luego borra, y contando»): en un turno de la reserva el escritor no debe preguntar.
    Si su texto trae una pregunta, se apunta en la traza y en [TURN_METRICS] (`escritor_pregunta`). El borrado de sus copias en el
    compositor sigue activo hasta que esto marque cero en un panel y una tanda."""
    from src.flows.que_preguntar import trae_pregunta  # lazy
    from src.observability import note_turn  # lazy

    if entradas.get("sin_preguntas") and not _is_rag_fallback(answer) and trae_pregunta(answer):
        note_turn(escritor_pregunta=True)
        logger.info("[CORE][CALN43] el escritor preguntó en un turno de la reserva (el compositor quita las copias de las nuestras)")
    if entradas.get("sin_ofrecer_el_pase") and not _is_rag_fallback(answer) and ofrece_el_pase(answer):
        # Bloque 4R (C4): con un plan en curso ya no recibe la orden de ofrecerlo; si lo ofrece igual, se cuenta (norma 6).
        note_turn(escritor_ofrece_el_pase=True)
        logger.info("[CORE][4R] el escritor ofreció el pase con un plan en curso (sigue valiendo el «sí», #3570)")


def ofrece_el_pase(answer: str | None) -> bool:
    """¿El texto ofrece pasar con un asesor? Lo mismo que reconoce `supervisor.acepta_la_oferta_del_asesor` en el último mensaje."""
    from src.agents import supervisor  # lazy

    return bool(answer) and bool(supervisor._ADVISOR_OFFER_RE.search(answer) and supervisor._OFFER_VERB_RE.search(answer))


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


async def rag_fuera_de_la_reserva(state: ConversationState, message: str, history: list) -> str:
    """El RAG de los caminos que contestan fuera de la reserva (buceo adaptado: nodo `info` y la cascada). Las entradas
    salen de `_entradas_rag`, así que la búsqueda recibe el origen del cliente (rag-3)."""
    answer = await _rag_answer(state, message, history=history)
    if _es_pregunta_de_origen(answer):
        _fijar_origen_antes_del_precio(state, message)
    return answer


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
    state._pending_answer = asyncio.create_task(_rag_answer(state, message, history=history, puerta_al_recoger=True))


async def _take_parallel_answer(state: ConversationState) -> str | None:
    task = getattr(state, "_pending_answer", None)
    state._pending_answer = None
    if task is None:
        return None
    from src.agents.nucleo.extractor import marcar_guardado  # lazy

    marcar_guardado(state)  # bloque 1: quien recoge la respuesta ya no va a guardar antes; que no espere
    try:
        answer = await task
    except Exception as exc:  # noqa: BLE001 — si el RAG falla, el turno sigue sin respuesta
        logger.warning(f"[CORE][U3-4] la respuesta en paralelo falló, sigue la reserva: {exc}")
        return None
    if puerta := getattr(state, "_puerta_al_recoger", None):
        # La puerta del origen, con lo que la extracción de este mensaje ya guardó (`_con_la_puerta`).
        state._puerta_al_recoger = None
        answer = _puerta_del_origen(state, puerta[0], answer, sin_precio=puerta[1], pieza_pedida=puerta[2])
        answer = await _con_la_entrega(state, puerta[0], answer, None)  # bloque 4R (C3), ya con lo guardado
    return answer


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
    state._puerta_al_recoger = None
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


# s4-2 (19-oct): el código de cada nodo del subgrafo `booking` vive en `src/agents/nucleo/<nodo>.py` (ver su
# `__init__`). Se re-exporta aquí para que `maybe_handle_turn`, el resto del código, los scripts y los tests lo sigan
# encontrando en este módulo. Va al final a propósito: esos módulos importan de aquí lo común, que tiene que estar ya
# definido. CALN-8 (5): `origen_precio` (el origen antes del precio) no es un nodo, pero va igual; tiene que ir antes
# que `slotfill_close`, que importa de aquí algunos de sus nombres (el orden alfabético ya lo deja así).
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
    _BOOL_SLOT_FIELD,
    _COURSE_SOLO_RE,
    _LLM_RESOLVABLE_SLOTS,
    _NAMED_PERSON_RE,
    _NOT_ALONE_RE,
    _SINGULAR_COMPANION_RE,
    _SLOT_PREV_KEY,
    _SLOT_STATE_FIELD,
    _WORD_TO_NUM,
    _add_or_ask_companion,
    _apply_question_turn_answers,
    _apply_resolved_slot_value,
    _extraction_phase,
    _extraction_phase_body,
    _flag_cert_or_course,
    _jev_dice_ya_contada,
    _jev_pending_answer,
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
from src.agents.nucleo.huecos import (  # noqa: E402, F401
    _CONFIRMA_ORIGEN,
    _PREGUNTAS_DE_CERTIFICACION,
    _SIN_OFERTA_CONCRETA,
    _certificacion_ya_preguntada,
    _minicurso_ya_recomendado,
    _ofrecer_la_actividad_preguntada,
    _ow_dias,
    _ow_inmersiones,
    _ow_plan,
    _texto_de_la_pregunta,
    ask_slot,
)
from src.agents.nucleo.notas import (  # noqa: E402, F401
    _jev_sin_nada_que_apuntar,
    _maybe_capture_notes,
    _notes_snapshot,
    await_pending_notes,
)
from src.agents.nucleo.origen_precio import (  # noqa: E402, F401
    _DEPENDE_DEL_ORIGEN_RE,
    _FRASE_RE,
    _IMPORTE_RE,
    _PIDE_PRECIO_RE,
    _PISTA_ORIGEN_RE,
    _PRECIO_AJENO_RE,
    _PREGUNTA_ORIGEN_RE,
    _VARIANTE,
    ORIGEN_ANTES_DEL_PRECIO_EN,
    ORIGEN_ANTES_DEL_PRECIO_ES,
    ORIGEN_TRAS_LAS_VARIANTES_EN,
    ORIGEN_TRAS_LAS_VARIANTES_ES,
    ORIGEN_TRAS_LOS_ENLACES_EN,
    ORIGEN_TRAS_LOS_ENLACES_ES,
    SIN_ENLACE_DE_LAS_ISLAS_EN,
    SIN_ENLACE_DE_LAS_ISLAS_ES,
    _answer_already_asks,
    _answer_asks_the_origin,
    _cierra_preguntando_el_origen,
    _con_la_pieza,
    _cotiza_alguno,
    _cotiza_los_dos_origenes,
    _dos_variantes,
    _enlaza_alguno,
    _es_pregunta_de_origen,
    _fijar_origen_antes_del_precio,
    _origen_antes_del_precio,
    _pide_precio,
    _precios_por_codigo,
    _puerta_del_origen,
    _sin_importes,
    _sin_la_pregunta_final,
)
from src.agents.nucleo.plan import (  # noqa: E402, F401
    _dias_del_plan,
    _plan_en_duda,
    _plan_is_single_day,
    _plan_needs_overnight,
    _pregunta_origen,
    _recommended_plan_intro,
    _resolve_cert_plan,
    plan_del_estado,
)
from src.agents.nucleo.reparto import (  # noqa: E402, F401
    _apply_cert_or_course,
    _apply_group_total,
    _elige_quien_falta,
    _merge_companion_activity,
    _take_undecided_members,
)
from src.agents.nucleo.routing import (  # noqa: E402, F401
    _CONFIRMS_DESCRIBED_PACKAGE_RE,
    _DELIBERATION_RE,
    _HOTEL_UNKNOWN_RE,
    _accept_pending_correction,
    _apply_short_answer,
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
