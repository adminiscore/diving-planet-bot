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

# lat-9 paso 4 (27-oct): los huecos de la reserva, sus preguntas y la puerta del origen viven en `nucleo/` (ver su
# `__init__`); no dependen de este módulo y se re-exportan aquí, como lo de cada nodo al final.
from src.agents.nucleo.huecos import (  # noqa: F401
    _ACTIVITY_TO_CART_TYPE,
    _DAYS_TO_DIVES,
    _DIVES_TO_BASE_PLAN,
    _PREGUNTAS_DE_CERTIFICACION,
    _SLOTS_APLAZABLES,
    SLOT_ACTIVITY,
    SLOT_AGES,
    SLOT_CERT_OR_COURSE,
    SLOT_CERTIFICATION,
    SLOT_COMPANION_ACTIVITY,
    SLOT_COMPANION_QTY,
    SLOT_CONFIRM_CORRECTION,
    SLOT_COURSE_LEVEL,
    SLOT_HOTEL,
    SLOT_LOCATION,
    SLOT_NATIONALITY,
    SLOT_QTY,
    SLOT_REFRESHER,
    SLOT_SAFETY,
    _cart_will_include_cert,
    _certificacion_ya_preguntada,
    _companion_activity_options,
    _course_level_options,
    _effective_activity,
    _es_la_ultima_pregunta,
    _group_allocation_fully_resolved,
    _known_field_values,
    _resolve_cert_plan,
    _set_concrete_activity,
    next_missing_slot,
    refresh_en_el_grupo,
)
from src.agents.nucleo.origen import (  # noqa: F401
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
    _answer_already_asks,
    _answer_asks_the_origin,
    _cierra_preguntando_el_origen,
    _cotiza_alguno,
    _cotiza_los_dos_origenes,
    _dos_variantes,
    _el_extractor_calla_el_lugar,
    _enlaza_alguno,
    _es_pregunta_de_origen,
    _fijar_origen_antes_del_precio,
    _jev_dice_el_lugar,
    _jev_dice_que_no_lo_dice,
    _origen_antes_del_precio,
    _pide_precio,
    _puerta_del_origen,
    _sin_importes,
    _sin_la_pregunta_final,
)
from src.agents.nucleo.preguntas import (  # noqa: F401
    _SIN_OFERTA_CONCRETA,
    _describe_value,
    _dias_del_plan,
    _minicurso_ya_recomendado,
    _ofrecer_la_actividad_preguntada,
    _ow_dias,
    _ow_inmersiones,
    _ow_plan,
    _plan_en_duda,
    _plan_is_single_day,
    _plan_needs_overnight,
    _pregunta_origen,
    _recommended_plan_intro,
    _same_for_customer,
    ask_slot,
)
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState
from src.utils.number_words import number_alt
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")


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


def _words(message: str) -> list[str]:
    return [w for w in re.split(r"[^\wáéíóúñü]+", (message or "").lower()) if w]


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
    known = state.detected_group_size or 1  # DEUDA-EXT2: sin total, quien escribe es uno (como `setdefault(main, … or 1)`)
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


# lat-9 paso 4 (27-oct): el RAG del núcleo y el escritor (`nucleo/escritor.py`) importan de aquí las notas, el
# saludo y si el turno trae pregunta, y los nodos de abajo importan de aquí lo suyo: va antes que ellos.
from src.agents.nucleo.escritor import (  # noqa: E402, F401
    _AFFIRMS_SIGNAL_FIELDS,
    _HORA_DEL_RESUMEN,
    _PARTES_HUELLA,
    _PASE_HECHO_EN,
    _PASE_HECHO_ES,
    _PLAN_ID_RE,
    _adoptar_o_rehacer,
    _answer_question,
    _answer_replaces_the_booking_question,
    _con_hechos,
    _con_la_nacionalidad_del_mensaje,
    _entradas_rag,
    _has_pending_answer,
    _hechos_para_el_rag,
    _huella_rag,
    _is_rag_fallback,
    _lugar_desconocido,
    _maybe_launch_answer,
    _plan_nombrado,
    _prepend_parallel_answer,
    _rag_answer,
    _take_parallel_answer,
    attach_unused_answer,
    cancel_pending_answer,
    cancelar_rag_adelantado,
    fijar_pregunta_del_escritor,
    lanzar_rag_adelantado,
    rag_con_adelantado,
)

# isort: split

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
