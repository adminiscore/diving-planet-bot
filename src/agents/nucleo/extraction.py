"""Nodo `extraction` del subgrafo de la reserva: `_extraction_phase` y su cuerpo, `_understand` (regex + `fill_gaps`),
acompañantes, multi-ítem, redes de precisión, contradicciones y el turno con pregunta.

La capa de abajo, lo que el núcleo hace con el extractor del turno (ex-5), está en `extractor.py`.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging
import re

from src.agents.conversational_core import (
    _ACTIVITY_TO_CART_TYPE,
    _EXPLICIT_NUMBER_RE,
    SLOT_CERT_OR_COURSE,
    SLOT_CERTIFICATION,
    SLOT_COMPANION_ACTIVITY,
    SLOT_COMPANION_QTY,
    SLOT_COURSE_LEVEL,
    SLOT_LOCATION,
    SLOT_NATIONALITY,
    SLOT_QTY,
    SLOT_REFRESHER,
    SLOT_SAFETY,
    _answer_question,
    _apply_cert_or_course,
    _apply_group_total,
    _cart_item,
    _companion_activity_options,
    _course_level_options,
    _elige_quien_falta,
    _group_allocation_fully_resolved,
    _has_pending_answer,
    _is_greeting_only,
    _jev_says_no_recall,
    _known_field_values,
    _looks_like_question,
    _mentioned_product_activities,
    _merge_companion_activity,
    _prepend_parallel_answer,
    _recall_answer,
    _set_concrete_activity,
    _take_undecided_members,
    ask_slot,
    next_missing_slot,
)
from src.agents.intent_detector import (
    _PERSON_NOUN_MENTION_EN,
    _PERSON_NOUN_MENTION_ES,
    _PERSON_NOUN_SINGULAR_EN,
    _PERSON_NOUN_SINGULAR_ES,
    _SINGULAR_PERSON,
    course_level_is_ambiguous,
    lectura_del_turno,
)
from src.agents.llm_extractor import (
    detect_special_signals,
    resolve_slot_answer,
)
from src.agents.nucleo.extractor import (
    _CAMPOS_LISTA_CERRADA,
    _aplicar_extractor,
)
from src.domain import activities as dom
from src.flows import cart_render, grupo
from src.flows.state import ConversationState
from src.utils.number_words import number_alt, number_words

logger = logging.getLogger("uvicorn.error")


# Slots booleanos/escalares que el resolutor LLM anti-bucle (Fase C) sabe
# resolver cuando el parser canónico (is_affirmative/is_negative/número) falla
# ante una respuesta válida pero no-canónica. Los nombres coinciden con las
# claves de `_SLOT_RESOLVER_SPEC` en llm_extractor.py.
_LLM_RESOLVABLE_SLOTS = frozenset({
    SLOT_CERTIFICATION, SLOT_SAFETY, SLOT_REFRESHER, SLOT_QTY, SLOT_NATIONALITY,
    SLOT_LOCATION, SLOT_COURSE_LEVEL, SLOT_CERT_OR_COURSE,
})


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
# Inventario regex 2026-09-03: sustantivo tras "mi"/"my" ahora viene de la
# fuente compartida (`_PERSON_NOUN_MENTION_ES/EN`, ya con plural opcional
# incorporado -- el original ya toleraba "mi hijos"/"mi amigos" sueltos, así
# que la forma "mención" es la compatible; no la "singular" estricta).
# Cierra el mismo gap real de "compañero"/"acompañante"/"boyfriend"/"kids"
# que las demás.
_NOT_ALONE_RE = re.compile(
    r"\b(?:somos|estamos|venimos|vamos|seremos|nosotr[oa]s|we\s+are|we're|we\s+want"
    r"|con\s+mi\b|y\s+mi\b|and\s+my\b"
    r"|mi\s+(?:" + _PERSON_NOUN_MENTION_ES + r")"
    r"|my\s+(?:" + _PERSON_NOUN_MENTION_EN + r")"
    r"|[2-9]|" + number_alt(2, 9) + r")\b",
    re.IGNORECASE,
)


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
        return _apply_group_total(state, value)
    if slot == SLOT_LOCATION and value in ("cartagena", "island"):
        state.location = state.detected_location = value
        return True
    if slot == SLOT_CERT_OR_COURSE:
        return _apply_cert_or_course(state, value)
    if slot == SLOT_COURSE_LEVEL and value in _course_level_options(state):
        _set_concrete_activity(state, value)
        return True
    if slot == SLOT_COMPANION_ACTIVITY and value in _companion_activity_options(state):
        _elige_quien_falta(state, value)
        return True
    return False


# Inventario regex 2026-09-03: el sustantivo singular tras "mi"/"my" ahora
# viene de `_PERSON_NOUN_SINGULAR_ES/EN` (fuente compartida, intent_detector.py)
# -- cierra un gap real: esta lista no tenía "compañero"/"acompañante"/
# "primo" (ES) ni "companion"/"cousin"/"kid"/"child" (EN) pese a que otras
# listas del mismo concepto sí los tenían.
# Solo la señal de que se SUMA alguien ("también", "viene", "se apunta"), sin el
# "mi amigo" de abajo: nombrar a una persona no dice si ya estaba contada en el total
# (tarea 7a, 2026-09-15). La usa `_add_or_ask_companion`.
_ADDITION_CUE = (
    r"tambi[eé]n|adem[aá]s|viene|acompa[ñn]a|se\s+(?:suma|apunta)|otra?\s+que"
    r"|also|joining|is\s+coming|comes?\s+along"
)
_ADDITION_CUE_RE = re.compile(r"\b(?:" + _ADDITION_CUE + r")\b", re.IGNORECASE)
_ADDED_PERSON_RE = re.compile(
    r"\b(" + _ADDITION_CUE + r"|uno?\s+que"
    r"|mi\s+(?:" + _PERSON_NOUN_SINGULAR_ES + r")"
    r"|my\s+(?:" + _PERSON_NOUN_SINGULAR_EN + r"))\b",
    re.IGNORECASE,
)

# Señal LÉXICA amplia de que el mensaje menciona OTRA PERSONA (no el hablante).
# Es el discriminador entre AÑADIR un acompañante y un CAMBIO de opinión: el LLM
# decide la ACTIVIDAD, pero solo se trata como añadido si el mensaje nombra a una
# persona. Robusto ante el flip-flop del LLM con historial: "mejor snorkel" (sin
# persona) NUNCA añade; "hay un amigo que quiere snorkel" / "2 y uno hace snorkel"
# (con persona) sí. Más amplio que `_ADDED_PERSON_RE` (que exigía "mi amigo"/"un
# que" y perdía "hay un amigo que…").
#
# Inventario regex 2026-09-03: el sustantivo de parentesco ahora viene de
# `_PERSON_NOUN_MENTION_ES/EN` (intent_detector.py, fuente compartida con
# _ADDED_PERSON_RE/_SINGULAR_COMPANION_RE/_PLURAL_COMPANION_RE/_NOT_ALONE_RE
# más abajo) en vez de una copia local -- cierra el gap real que motivó este
# fix (ver comentario histórico abajo): "boyfriend"/"girlfriend" faltaban en
# ESTA lista pese a estar en otras 2 del mismo archivo. Las palabras que NO
# son sustantivos de parentesco ("vienen", "se suma", "otra persona",
# "others/folks/people/someone/is coming/joins") se quedan aparte, tal cual
# — son cues verbales propias de ESTE patrón, no vocabulario compartido.
_MENTIONS_PERSON_RE = re.compile(
    r"\b(" + _PERSON_NOUN_MENTION_ES + r"|"
    r"vien[ea]n?|se\s+(?:suma|apunta|une)n?|otra?\s+persona|"
    # Auditoría 2026-07-23 (matriz EN de multi-ítem): la lista en inglés no
    # tenía plurales ("friend" sin "s?") mientras que TODA la lista en
    # español sí ("amig[oa]s?") — "my friends do snorkel" no disparaba
    # NINGÚN mecanismo de acompañante (ni el nuevo chequeo de mención
    # perdida, ni el `companion_ambiguous` original, ni el fast-path), un
    # hueco real de idioma, no solo del fix de hoy.
    + _PERSON_NOUN_MENTION_EN + r"|"
    r"others?|folks?|people|someone|is\s+coming|are\s+coming|joins?)\b"
    r"|\b(?:y|,|adem[aá]s|tambi[ée]n|más|mas|and)\s+(?:un[oa]?|otr[oa]|another|one)\b",
    re.IGNORECASE,
)

# Compañero SINGULAR e inequívoco (un/una/mi/a + sustantivo en singular, o "a
# friend"/"someone"): el número de personas es 1 sin ambigüedad, se puede
# asumir con seguridad sin preguntar. Deliberadamente NO matchea plurales
# ("mis amigos", "unos amigos", "friends") ni un número explícito (ese lo
# extrae el LLM en `companion_qty`) — para esos dos casos hay que preguntar
# cuántos son en vez de adivinar (hallazgo en vivo 2026-07-22: "mis amigos"
# se inventaba un total sin preguntar). Ver SLOT_COMPANION_QTY.
_SINGULAR_COMPANION_RE = re.compile(
    # Inventario regex 2026-09-03: sustantivo singular ahora viene de la
    # fuente compartida (`_PERSON_NOUN_SINGULAR_ES/EN`, intent_detector.py) —
    # esta lista ya tenía "compañero"/"acompañante"/"companion" (era la más
    # completa de las 3 con determinante singular), sin cambio de cobertura.
    _SINGULAR_PERSON + r"|\bsomeone\b"
    # "uno/una que..." / "one who/that..." — pronombre numeral, no un
    # sustantivo de relación: "viene también uno que hace snorkel" es
    # exactamente 1 persona, mismo patrón que ya usa _ADDED_PERSON_RE.
    r"|\bun[oa]?\s+que\b|\bone\s+(?:who|that)\b",
    re.IGNORECASE,
)

_WORD_TO_NUM = number_words(1, 10)


# Personas nombradas una a una: la misma pieza `_SINGULAR_PERSON` que usa
# `_SINGULAR_COMPANION_RE`. Los plurales ("mis amigos") no cuentan: siguen sin respaldar cifra.
_NAMED_PERSON_RE = re.compile(_SINGULAR_PERSON, re.IGNORECASE)


def _rehacer_la_tarjeta_si_no_cuadra(state: ConversationState) -> bool:
    """CALN-2 (27-oct, sparring b2): tras el cierre, si el reparto ya no cuadra con lo que cobra la tarjeta (personas por
    tipo de ítem), la tarjeta se rehace ENTERA desde el reparto (`_build_cart_from_slots`, la del cierre). Antes solo se
    añadían los tipos nuevos: «no, él es buzo; solo yo hago el minicurso» dejaba «minicurso × 2» y sumaba el buceo (tres
    plazas para dos). Cubre también el añadido de siempre («viene también uno que hace snorkel»). True si la rehízo."""
    from src.agents.nucleo.slotfill_close import _build_cart_from_slots  # lazy

    cobrables = set(dom.cart_activity_ids())
    reparto: dict = {}
    for actividad, n in (state.detected_group_allocation or {}).items():
        if actividad in cobrables and n:
            tipo = _cart_item(state, actividad, n)["type"]
            reparto[tipo] = reparto.get(tipo, 0) + n
    tarjeta: dict = {}
    for item in state.mixed_cart or []:
        tarjeta[item.get("type")] = tarjeta.get(item.get("type"), 0) + (item.get("qty") or 0)
    if not reparto or reparto == tarjeta:
        return False
    _build_cart_from_slots(state)
    logger.info(f"[CORE][CALN2] el reparto cambió tras el cierre: tarjeta {tarjeta} -> "
                f"{[(i['type'], i['qty']) for i in state.mixed_cart]}")
    return True


def _singular_companion(message: str) -> bool:
    """¿El mensaje habla de UN solo acompañante? Exactamente una persona nombrada o, si no
    nombra a nadie, "someone"/"uno que" (2026-09-15). Antes bastaba con que apareciera una:
    "vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel" o "my daughter is 9 and my
    son is 12" contaban como un acompañante y se asumia cantidad 1 sin preguntar."""
    named = len(_NAMED_PERSON_RE.findall(message))
    return named == 1 or (named == 0 and bool(_SINGULAR_COMPANION_RE.search(message)))


# Slots de SÍ/NO y el campo que resuelve cada uno. Hallazgo en vivo
# (2026-09-01, cierre del problema abierto §6.bis del plan multi-agente,
# conversación 769 de PRE + repro determinista en local con LLM real): con
# `core_pending_slot == SLOT_SAFETY` (el bot acababa de preguntar "¿ha pasado
# más de 2 años desde la última inmersión?"), el mensaje "ninguno colombiano"
# —que solo responde NACIONALIDAD y no menciona el buceo en absoluto— hacía
# que `fill_gaps` devolviera `{"last_dive_over_2_years": false}`. El LLM ve el
# historial como turnos de diálogo reales, ve la pregunta del bot sin
# responder, y la contesta ÉL. Como el campo estaba en None, el valor
# inventado se aplicaba, `next_missing_slot` daba el slot de seguridad por
# resuelto y la reserva se cerraba SIN haber preguntado nunca al cliente algo
# que es de seguridad, no de logística.
#
# La regla estructural (no un parche por síntoma, misma familia que el corte
# de `_group_allocation_fully_resolved`): un
# extractor LLM de formato libre NO puede responder por el cliente. Estos
# campos ya tienen DOS resolutores anclados al mensaje del turno —
# `_apply_short_answer` (determinista, corre ANTES de `_understand`) y el
# resolutor LLM anti-bucle de Fase C (`_apply_resolved_slot_value`, para
# fraseos no canónicos)— así que `fill_gaps` es un tercer camino redundante y
# el único que mira el historial. Si ninguno de los dos resolutores buenos
# entiende la respuesta, el slot sigue pendiente y se RE-PREGUNTA, que es el
# fallo seguro.
#
# Solo booleanos a propósito: para location/hotel/activity la respuesta ES
# texto libre y `fill_gaps` sí es el extractor correcto ("salimos desde
# bocagrande"). SLOT_REFRESHER no entra porque `refresher_interested` no es un
# campo extraíble de `DetectedIntent` — nunca llega por esta vía.
_BOOL_SLOT_FIELD = {
    SLOT_SAFETY: "last_dive_over_2_years",
    SLOT_CERTIFICATION: "is_certified",
    SLOT_NATIONALITY: "is_colombian",
}


# Campo de estado que resuelve cada slot que la red anti-bucle de Fase C sabe
# interpretar (`_LLM_RESOLVABLE_SLOTS`) — usado por
# `_turn_answered_a_different_slot`.
_SLOT_STATE_FIELD = {
    SLOT_CERTIFICATION: "is_certified",
    SLOT_SAFETY: "last_dive_over_2_years",
    SLOT_NATIONALITY: "is_colombian",
    SLOT_REFRESHER: "refresher_interested",
    SLOT_QTY: "detected_group_size",
    SLOT_LOCATION: "location",
}


def _turn_answered_a_different_slot(state: ConversationState, pending: str, carry: dict) -> bool:
    """¿Este turno resolvió el campo de OTRO slot, distinto del pendiente?

    Segunda mitad de la GUARDA (b) — el mismo hallazgo del 2026-09-01, por la
    otra vía. Con la guarda de `fill_gaps` puesta, el repro de §6.bis seguía
    fallando de forma intermitente por la red anti-BUCLE de slot (Fase C, más
    abajo): con `SLOT_SAFETY` pendiente, `resolve_slot_answer("safety",
    "ninguno colombiano")` devolvía `{"value": False}` — otra vez un extractor
    LLM contestando por el cliente una pregunta que el mensaje no responde.

    Aquí NO sirve un gate de tema por vocabulario: esta red
    existe precisamente para las respuestas válidas pero no-canónicas, y la
    legítima de este mismo slot ("uf, hace muchísimo") tampoco menciona el
    buceo. Lo que distingue "uf, hace muchísimo" de "ninguno colombiano" no es
    el vocabulario: es que el segundo YA respondió a OTRO slot en este mismo
    turno. Un mensaje que acaba de contestar la nacionalidad no está
    contestando además, en silencio, la de seguridad.

    Misma forma que la verificación determinista que este bloque ya aplica a
    SLOT_LOCATION ("si este turno cambió la actividad, el mensaje no hablaba de
    ubicación"), generalizada a todos los slots en vez de a un par concreto.
    """
    for slot, field in _SLOT_STATE_FIELD.items():
        if slot == pending:
            continue
        prev = carry.get(_SLOT_PREV_KEY[slot])
        if prev is None and getattr(state, field, None) is not None:
            return True
    return False


# Clave del carry con el snapshot pre-turno de cada campo de `_SLOT_STATE_FIELD`.
_SLOT_PREV_KEY = {
    SLOT_CERTIFICATION: "prev_main_is_certified",
    SLOT_SAFETY: "prev_main_last_dive",
    SLOT_NATIONALITY: "prev_is_colombian",
    SLOT_REFRESHER: "prev_main_refresher",
    SLOT_QTY: "prev_group_size",
    SLOT_LOCATION: "prev_location",
}


def _state_known_fields(state: ConversationState) -> set[str]:
    """Campos extraíbles que la CONVERSACIÓN ya conoce (estado), con la misma
    convención que missing_fields: False es un valor resuelto, None/[] no."""
    return {f for f, v in _known_field_values(state).items() if v not in (None, [], {})}


def _recommend_inferred_minicourse(intent, state: ConversationState, message: str) -> None:
    """u3-5 (decision de Gadea, 27-sep: "debe recomendar el minicurso pero lo confirma el cliente"). Si el cliente
    ELIGE el minicurso (el extractor, `_actividad_elegida`) y aun no habia actividad, la recomendacion pendiente se
    borra. ex-9b paso 3: ya no hay minicurso DEDUCIDO del regex ("es la primera vez que vamos a hacer buceo"), que aqui
    se convertia en recomendacion; la recomendacion la hace CAL-C1 (`actividad_por_lo_sabido`) con lo que dice el
    extractor (`quiere_bucear`, `is_certified`)."""
    if intent.activity == "minicourse" and not state.detected_activity:
        state.suggested_activity = None


def _pista_del_regex(intent) -> dict:
    """Lo que leyó el regex en los campos que decide el extractor (una copia; el intent no se toca hasta el final): solo
    la isla y el hotel del catálogo (`_CAMPOS_LISTA_CERRADA`, ex-9b paso 3)."""
    return {c: getattr(intent, c) for c in _CAMPOS_LISTA_CERRADA if getattr(intent, c, None) not in (None, "", [], {})}


async def _understand(state: ConversationState, message: str, *, answered_pending: bool = False) -> tuple:
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
    acompañante)."""
    from src.agents import supervisor  # lazy: evita import circular

    prev_activity = state.detected_activity
    prev_service_id = state.detected_service_id
    prev_is_certified = state.is_certified
    prev_last_dive = state.last_dive_over_2_years
    prev_refresher = state.refresher_interested

    # lat-11 T6a: del regex, solo lo que el turno sigue usando (`lectura_del_turno`); el resto lo decide el extractor.
    intent = lectura_del_turno(message)
    # ex-5 (fase EX): los dominios que entiende el extractor "LLM primero" no los
    # decide el regex. Lo que leyó se queda en el intent como PROVISIONAL (las guardas que miran si el mensaje
    # CONTESTA la pregunta pendiente lo siguen viendo, como hoy), pero ni dispara contradicciones, ni va al veto, al
    # relleno o a la re-comprobación. Al final se sustituye por lo del extractor (`_ubicacion_del_extractor`).
    # ex-9b paso 3: la pista solo guarda la isla y el hotel del catálogo; lo demás lo decide el extractor y, si falla,
    # se pregunta.
    pista_lugar = _pista_del_regex(intent)
    # u3-4: turno con pregunta (la respuesta del RAG ya está lanzada en paralelo).
    if _has_pending_answer(state):
        _question_turn_fields(intent, state)
    state.mixed_nationality_notice = False
    # lat-11 (26-oct): fuera el relleno LLM de siempre (`fill_gaps`). Solo decidía las edades de los menores y solo si el
    # extractor fallaba (0 llamadas en la integra-B del 26-oct, 465 turnos); sin extractor, las edades se preguntan.
    # Invariante del reparto, en el UNICO punto donde el intent del turno ya
    # esta completo (regex + veto + relleno) y aun no se ha escrito al estado.
    # Ponerla aqui la hace valida para cualquier fuente del reparto, presente o
    # futura, en vez de repetir la comprobacion en cada una.
    await _aplicar_extractor(intent, state, message, pista_lugar)
    supervisor.enforce_group_allocation_consistency(intent, state, message)
    _take_undecided_members(intent, state)
    _flag_cert_or_course(intent, state, message)
    _recommend_inferred_minicourse(intent, state, message)
    supervisor._apply_detected_intent(intent, state, message)

    # Circuit-breaker (portado 2026-09-01, hallazgo en vivo, batería de
    # grupos mixtos contra PRE, lote 8): si el reparto del grupo YA cubre a
    # todo el mundo (p. ej. "2 certificados, 2 minicurso, 2 snorkel" para un
    # grupo de 6, ya aplicado arriba vía `_apply_detected_intent`), no puede
    # quedar ningún acompañante sin actividad — se auto-limpia cualquier
    # bandera de "pregunta de acompañante pendiente" que hubiera quedado
    # marcada por la razón que sea, en vez de dejar que dispare más
    # adelante en el turno pese a no tener ya ningún sentido.
    if _group_allocation_fully_resolved(state):
        state.personas = grupo.solo_el_reparto(state.personas)

    # "voy solo" → 1 persona. Nació para cursos PADI (Fase 3 causa A) y el owner
    # decidió extenderlo a CUALQUIER actividad (2026-07-22): la señal explícita
    # de ir solo significa lo mismo en buceo, snorkel o minicurso, y sería raro
    # que el bot lo entendiera en un curso pero no en un buceo. Sigue exigiendo
    # señal singular EXPLÍCITA ("voy solo"/"just me") y ninguna señal de
    # compañía — una auto-presentación en singular sin más ("tengo el open
    # water") NO basta, porque un jefe de grupo escribe igual: ahí se pregunta.
    # ex-9b paso 4: si el extractor leyó el mensaje, "voy solo" es su `group_size` 1 (ya aplicado arriba); estos regex
    # solo si el extractor falla.
    if (
        not getattr(intent, "_leido_por_extractor", False)
        and not state.detected_group_size
        and not state.detected_group_allocation
        and state.detected_activity
        and _COURSE_SOLO_RE.search(message)
        and not _NOT_ALONE_RE.search(message)
    ):
        state.detected_group_size = 1
        state.solo_traveler_confirmed = True
        logger.info("[CORE] singular course booking -> group_size=1")

    # AÑADIR vs CAMBIAR (fast-path regex): si ya había actividad principal y
    # este turno menciona OTRA junto a una persona añadida ("viene también uno
    # que hace snorkel", "mi novia hace el minicurso"), es un AÑADIDO — la
    # actividad principal no se pisa (se restaura del "latest wins" de
    # _apply_detected_intent) y el subgrupo nuevo se acumula en el reparto. Un
    # cambio de opinión sin persona añadida ("mejor snorkel") sigue siendo
    # cambio (latest wins). Cubre solo las frases de _ADDED_PERSON_RE — frases
    # fuera de esa lista (o donde turn_act == prev_activity, p. ej. "mi
    # acompañante quiere hacer buceo pero no es certificado") las lee el
    # reparto del extractor o el lector del grupo (CALN-8, 28-oct: antes, la
    # red de señales), nunca ampliando este regex frase a frase (decisión
    # owner 2026-07-22).
    turn_act = intent.activity
    companion_merged_fastpath = False
    if (
        prev_activity
        and turn_act
        and turn_act != prev_activity
        and turn_act in _ACTIVITY_TO_CART_TYPE
        and prev_activity in _ACTIVITY_TO_CART_TYPE
        and _ADDED_PERSON_RE.search(message)
        # ex-7: si el extractor ya puso a esa persona en el reparto, el atajo no la vuelve a sumar ("él quiere hacer
        # snorkel" sobre buceo de 1 acababa en {snorkel: 2}).
        and turn_act not in (getattr(intent, "_reparto_del_extractor", None) or ())
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
        # una cifra inventada — dejar el estado sin tocar: cuántos son lo da
        # el reparto del extractor o del lector del grupo (CALN-8, 28-oct).
        if explicit_qty is not None and not _EXPLICIT_NUMBER_RE.search(message):
            explicit_qty = None
        if (
            explicit_qty is None
            and not _singular_companion(message)
        ):
            pass
        else:
            _restore_main_diver_fields(state, prev_activity, prev_service_id, prev_is_certified, prev_last_dive, prev_refresher)
            _add_or_ask_companion(state, message, turn_act, explicit_qty or 1)
            companion_merged_fastpath = True

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
    no del hablante (fast-path regex arriba). Bug real: "no es certificado"/"sin bucear hace X años"
    referido al acompañante se aplicaba por 'latest wins' al buceador
    principal ya resuelto (p. ej. is_certified=True → False de golpe).

    `activity`/`service_id` solo se restauran si HABÍA algo que proteger
    (`activity` no es None): si el mensaje de APERTURA establece la
    actividad principal en primera persona ("quiero bucear") en el MISMO
    turno que menciona a un acompañante ("...voy con mi amigo pero el no
    esta certificado"), no hay ninguna actividad previa que restaurar —
    pisarla con None borraba la actividad recién y correctamente detectada
    del hablante, dejando la reserva sin actividad principal (hallazgo D,
    batería sintética 2026-08-26). Igual el resto (CALN-2, 27-oct): «Quiero
    bucear, soy buzo certificado. Vienen también unos amigos…» perdía la
    certificación recién dicha y se le volvía a preguntar (banco g26)."""
    if activity is not None:
        state.detected_activity = activity
        state.detected_service_id = service_id
    if is_certified is not None:
        state.is_certified = is_certified
    if last_dive is not None:
        state.last_dive_over_2_years = last_dive
    if refresher is not None:
        state.refresher_interested = refresher


def _flag_cert_or_course(intent, state: ConversationState, message: str) -> None:
    """Nivel PADI nombrado sin decir si lo tienen o lo quieren: no se da por buena la
    lectura del regex ni la del LLM (curso o buceo certificado) y se pregunta."""
    if state.needs_cert_or_course or state.is_certified is not None:
        return
    if getattr(intent, "_certificacion_del_extractor", False):
        # ex-6: el extractor ya leyó con cita si lo tiene o lo quiere sacar; solo se pregunta si no lo dice.
        return
    if not course_level_is_ambiguous(message):
        return
    if intent.activity == "padi_open_water_referral":
        # gen-16 (21-oct): el extractor ya leyó que quiere TERMINAR aquí un Open Water empezado (el Referido): nombrar
        # «Open Water» no es ambiguo y «¿ya tienen el Curso referido o quieren sacarla?» era una repregunta
        # (banco dialogos-gen16-repreguntas, 2/2).
        return
    preguntada = getattr(intent, "_actividad_preguntada", None)
    if preguntada and getattr(dom.by_id(preguntada), "course_level", None):
        # flu-1 (G10 nº 2): «do you have open water available tomorrow?» pregunta por el CURSO (el extractor lo lee como
        # la actividad de la que pregunta); quien ya tiene el nivel no pregunta por su disponibilidad ni su precio. Con
        # el nivel a secas («somos 4 open water») el extractor no lee ninguna actividad preguntada y se sigue preguntando.
        return
    registered = dom.by_id(intent.activity) if intent.activity else None
    if registered is not None and registered.course_level is not None:
        state.cert_or_course_level = intent.activity
    intent.is_certified = None
    # Un reparto con el nivel ("2 open water y 3 snorkel" -> {padi_open_water: 2, ...})
    # depende justo de la respuesta que se va a pedir: no se guarda hasta tenerla. Antes
    # solo lo evitaba que el LLM se abstuviera, y cualquier cambio en la peticion lo
    # rompia (b05, 6/6 con la verificacion de campos sabidos, 2026-09-15).
    allocation = intent.group_allocation or {}
    if any(getattr(dom.by_id(key), "course_level", None) for key in allocation):
        intent.group_allocation = None
    intent.detected_fields = [
        f for f in intent.detected_fields
        if f != "is_certified" and (f != "group_allocation" or intent.group_allocation)
    ]
    state.needs_cert_or_course = True
    from src.observability import marca_regex  # lazy

    marca_regex("R6")  # CALN-8 (6): nivel PADI ambiguo según el detector; se pregunta cert o curso


def _number_of_something_else(state: ConversationState, message: str, value) -> bool:
    """¿El detector ya lee ese numero como otra magnitud (inmersiones, dias, edades)? Lo
    usa el resolutor LLM de la pregunta del total (G): con "¿cuantas personas?"
    pendiente, "2 inmersiones" volvia como 2 personas 2/2."""
    intent = lectura_del_turno(message)
    return value in {intent.cert_dives, intent.cert_days, *(intent.ages or [])}


_JEV_SE_SUMA_SEGURO = 0.7  # ex-9b: por encima, Jev está seguro de que el mensaje suma a una persona NUEVA


def _add_or_ask_companion(state: ConversationState, message: str, activity: str, qty: int) -> None:
    """Punto unico para la actividad de otra persona (tarea 7a, 2026-09-15).

    Quien es otra persona lo decide el turno (el fast-path regex o el extractor). Lo que ni el texto ni el LLM dicen es si esa persona
    YA estaba contada: "él quiere hacer snorkel" y "también viene mi hermana que quiere
    hacer snorkel" dan la misma señal. Si sumarla supera el total conocido y el mensaje
    no dice que se suma alguien, no se adivina: se pregunta el total
    (`pending_companion_in_group` -> SLOT_QTY) y la respuesta decide mover o añadir.
    Quien escribe siempre es uno de los contados, asi que con un total de 1 cualquier
    otra persona es nueva (`qty <= total - 1`)."""
    total = state.detected_group_size
    counted = sum((state.detected_group_allocation or {}).values()) or (total or 0)
    se_suma = bool(_ADDITION_CUE_RE.search(message))
    jev = getattr(state, "_jev_adds_person", None)
    if jev is not None:
        # ex-9b (19-oct): "¿se suma alguien?" lo decide Jev cuando contesta (`adds_person`); la lista de palabras solo si
        # calla. Con la lista, "mi amigo, el que ya te dije que viene, quiere snorkel" casaba "viene" y se contaba dos
        # veces (Jev 0,30: duda -> se pregunta el total). Banco s4-26: las personas nuevas dan >= 0,45 y casi todas
        # las ya contadas < 0,2; por encima de 0,7 se añade sin preguntar.
        se_suma = jev >= _JEV_SE_SUMA_SEGURO
    if (
        total and qty <= total - 1 and counted + qty > total
        and not se_suma
    ):
        state.pending_companion_in_group = {"activity": activity, "qty": qty}
        if _jev_dice_ya_contada(state):
            # s4-26: "él quiere hacer snorkel" habla de alguien del grupo; es lo mismo que contestar "seguimos
            # siendo {total}" a la pregunta, sin hacerla (acompanante-goteo: "¿seguís siendo 2?" tras "con mi amigo").
            logger.info(f"[CORE][S4-26] companion {activity} x{qty}: Jev, ya contado en {total} -> se mueve")
            _apply_group_total(state, total)
            return
        logger.info(f"[CORE] companion {activity} x{qty}: ¿ya contado en {total}? -> se pregunta el total")
        return
    pendientes = state.pending_undecided_qty or 0
    if pendientes and total and counted + qty <= total and not se_suma:
        # CALN-2: cabe en el total sin los que aún no habían elegido, y nadie dice que se sume: es de ellos, que ya
        # elige («el niño el Open Water» con el niño pendiente). Sumarlo lo contaba dos veces (banco g21: total 5 de 4).
        quedan = pendientes - min(qty, pendientes)
        state.pending_undecided_qty = quedan or None
        state.needs_companion_activity = bool(quedan)
    _merge_companion_activity(state, activity, qty)


def _jev_dice_ya_contada(state: ConversationState) -> bool:
    """s4-26 (flag `jev_persona_ya_contada`): ¿Jev esta SEGURO de que el mensaje no suma a una persona nueva
    (adds_person < ADDS_PERSON_NOT_MAX), sino que habla de alguien que ya estaba en el grupo? Ausente = no lo
    sabemos -> se pregunta el total, como hoy. Banco ciego (frases propias, no del golden): 0/10 personas nuevas
    por debajo del umbral (la mas baja 0,45), 9/10 ya contadas por debajo."""
    from src.agents.jev_router import ADDS_PERSON_NOT_MAX  # lazy

    p = getattr(state, "_jev_adds_person", None)
    return p is not None and p < ADDS_PERSON_NOT_MAX


def _jev_pending_answer(slot: str | None, routing_signals: dict) -> dict | None:
    """u3-7: lo que Jev leyo como respuesta a la pregunta pendiente, si esta
    seguro (confianza >= PENDING_ANSWER_MIN). {"value": ...} si contesta, {} si Jev esta seguro de que
    NO contesta a esa pregunta, None si hay que preguntar al LLM (flag apagado, Jev no la contesto, era
    de otro slot o duda). Las verificaciones de despues (otro slot, cambio de actividad) valen igual."""
    from src.agents.jev_router import PENDING_ANSWER_MIN  # lazy

    pa = routing_signals.get("pending_answer")
    if not pa or pa.get("slot") != slot or pa.get("confidence", 0.0) < PENDING_ANSWER_MIN:
        return None
    logger.info(f"[CORE][U3-7] respuesta a {slot} por Jev: {pa.get('value')!r} ({pa['confidence']:.2f})")
    return {} if pa.get("value") is None else {"value": pa["value"]}


def _apply_question_turn_answers(intent, fields: list[str], answers: dict, message: str) -> None:
    """u3-4 arreglo 2: en un turno con pregunta se guarda lo que el LLM AFIRMA.

    Tres casos por campo, y el tercero es el que arregla la regresión del escalón 1:

    - el LLM devuelve el MISMO valor que el regex -> confirmado, se queda;
    - devuelve OTRO valor -> corrige (el regex leyó mal la frase);
    - **no lo devuelve** -> nadie lo afirma, se cae. Aquí es donde mueren
      "¿me recomiendas un hotel en Rosario?" (el regex leía isla) e "in case I
      decided to do the Open Water course?" (el relleno lo daba por dato).

    Nació aparte de los `llm_*_veto_cutover` (el veto del turno NORMAL, "¿el regex
    leyó mal?", borrado con sus flags en MEJ-1): aquí la pregunta es otra — "¿el
    cliente afirma esto o es hipótesis?" — y solo corre en turnos con pregunta.
    """
    for f in fields:
        llm_value = answers.get(f)
        regex_value = getattr(intent, f, None)
        if llm_value == regex_value:
            continue
        afirmado = f in answers and llm_value not in (None, [], "", {})
        logger.info(
            f"[EXTRACT][U3-4] campo={f} regex={regex_value!r} llm={llm_value!r} "
            f"{'corregido' if afirmado else 'descartado (nadie lo afirma)'} "
            f"msg={message[:60]!r}"
        )
        setattr(intent, f, llm_value if afirmado else ([] if f == "ages" else None))
        if not afirmado and f in intent.detected_fields:
            intent.detected_fields.remove(f)
        if f == "activity":
            intent.service_id = None


def _question_turn_fields(intent, state: ConversationState) -> list[str]:
    """u3-4: en un turno con pregunta, lo que leyó el regex no se guarda si no se puede confirmar que el cliente lo
    afirma ("do you have any hotel in Rosario you recommend?" no es alojarse en la isla). Así nació (24-27 sep): el
    regex lee palabras sueltas y en una pregunta suelen ser hipotéticas; los campos que Jev sabe verificar
    (`affirms_*`) los decidía Jev y los demás se borraban.

    ex-9b paso 3: los campos del extractor ya no traen nada del regex (la isla y el hotel de la pista se copian después,
    en `_aplicar_extractor`). Solo quedan las EDADES, que siguen siendo del regex hasta el paso 6 y que Jev no
    verifica: en un turno con pregunta no se guardan. Devuelve los campos a verificar: ninguno (la lista vacía marca el
    turno con pregunta)."""
    if "ages" in intent.detected_fields:
        logger.info(f"[EXTRACT][U3-4] campo=ages regex={intent.ages!r} descartado (turno con pregunta)")
        intent.ages = []
        intent.detected_fields.remove("ages")
    return []


async def _extraction_phase(
    state: ConversationState, message: str, routing_signals: dict,
    greeting: str, carry: dict,
) -> str | None:
    """`_extraction_phase_body` + u3-4: si una de sus salidas anticipadas resuelve el
    turno (acompañante, carrito post-cierre...), la respuesta a la pregunta va delante."""
    response = await _extraction_phase_body(state, message, routing_signals, greeting, carry)
    if response is None:
        return None
    return await _prepend_parallel_answer(state, response, greeting)


async def _extraction_phase_body(
    state: ConversationState, message: str, routing_signals: dict,
    greeting: str, carry: dict,
) -> str | None:
    """Fase 3.3e — extracción del mensaje (understand + multi-ítem + redes de
    precisión LLM + anti-bucle de slot), extraído de `_extract_close_phase`.
    Muta el estado con lo extraído; si un gate resuelve el turno devuelve la
    respuesta (str), si no devuelve None para pasar a `_slotfill_close_phase`.
    Recibe el `carry` de `_routing_phase`. Lo llama la cascada (vía
    `maybe_handle_turn`) y el nodo `extraction` del subgrafo."""
    from src.agents import supervisor  # lazy

    resolved_short = carry["resolved_short"]
    prev_pending = carry["prev_pending"]
    prev_cart_types = carry["prev_cart_types"]
    prev_main_activity = carry["prev_main_activity"]
    prev_group_size = carry["prev_group_size"]
    prev_group_allocation = carry["prev_group_allocation"]

    # COMPRENDER: extracción del resto del mensaje.
    companion_merged_fastpath = False
    # ex-9b paso 4: una respuesta corta resuelta por la IA no se salta la lectura del resto (ver `_routing_phase`).
    if not (resolved_short and len(message.strip()) <= 12) or carry.get("respuesta_por_la_ia"):
        _, companion_merged_fastpath = await _understand(state, message, answered_pending=resolved_short)
    if state.mixed_nationality_notice:
        # Grupo con nacionalidades mixtas (hallazgo A, 2026-09-15; decisión del owner del 14-sep: todo en USD). CALN-6
        # paso 2 (27-oct): ya no corta el turno con un texto fijo, que repetía lo que el escritor dice con sus hechos (la
        # regla del grupo mixto) y cerraba con «¿…o prefieres volver al menú principal?», un menú que ya no existe
        # (sparring s07). Queda el efecto y el turno sigue; la regla la dicen el escritor y, si hace falta, el aviso
        # «grupo-mixto-todo-usd».
        state.is_colombian = False

    # Circuit-breaker (portado 2026-09-01, hallazgo en vivo, batería de
    # grupos mixtos contra PRE, lote 8): corre SIEMPRE, incluso en el turno
    # de arriba donde `_understand()` se salta por ser respuesta corta ya
    # resuelta (`resolved_short and len(message) <= 12`, p. ej.
    # "no"/"cartagena"). Si el reparto del grupo YA cubre a todo el mundo, no
    # puede quedar ningún acompañante sin actividad.
    if _group_allocation_fully_resolved(state):
        state.personas = grupo.solo_el_reparto(state.personas)

    # ¿La extracción de `_understand()` ya cambió el tamaño/reparto del grupo
    # este turno? Cuenta como avance (ver `advanced`, abajo).
    group_composition_resolved_by_base_extraction = (
        state.detected_group_size != prev_group_size
        or (state.detected_group_allocation or {}) != prev_group_allocation
    )

    # Añadido POST-cierre ("viene también uno que hace snorkel" cuando el
    # resumen ya se emitió): añadir el subgrupo nuevo al carrito existente y
    # re-emitir el resumen completo — el buceo original nunca se pierde.
    if prev_cart_types:
        if _rehacer_la_tarjeta_si_no_cuadra(state):
            response = cart_render.goto_final_summary(state)
            state.core_pending_slot = None
            supervisor._maybe_build_pending_note(state)
            state.history.append({"role": "assistant", "content": response})
            return response

    # ¿Avanzó el turno? Si no, lo de abajo (el «¿me recuerdas…?», la red
    # anti-bucle, la pregunta suelta) mira si el mensaje era otra cosa. Se mide
    # por next_missing_slot, no por un snapshot crudo de campos; sumar un
    # acompañante (`companion_merged_fastpath`) o cambiar el tamaño/reparto del
    # grupo cuenta como avance aunque siga faltando el mismo dato (p. ej. la
    # nacionalidad). Hasta CALN-8 (28-oct) esto decidía también si corría la
    # red de señales de acompañantes (historia en git).
    advanced = (
        resolved_short
        or companion_merged_fastpath
        or group_composition_resolved_by_base_extraction
        or next_missing_slot(state) != prev_pending
    )

    # CALN-8 (1), lector del grupo paso 3 (28-oct, decisión de Gadea #2311): fuera la red de señales de acompañantes
    # (`detect_special_signals`: companion_activity, mentions_other_person, other_companions, companion_qty). Iba en
    # serie (p50 1,4 s) y releía el historial entero: sus guardas eran parches contra los acompañantes fantasma que eso
    # creaba (historia en git). Quién viene y qué hace lo leen el extractor (el reparto persona a persona) y el lector
    # del grupo; el refresher, el extractor (CAL-F). De esa llamada queda el «¿me recuerdas…?», solo si Jev no descarta
    # que se pida recordar.
    if not advanced and not _jev_says_no_recall(state):
        signals = await detect_special_signals(message, history=state.history, lang=state.language)
        recalled = _recall_answer(state, signals["recall_field"]) if signals.get("recall_field") else None
        if recalled:
            response = recalled
            if prev_pending:
                response += "\n\n" + ask_slot(state, prev_pending, reasking=True)
            response = greeting + response
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
        if state.detected_duration is None:
            # Primer paso de la recomendación: la respuesta libre es la duración
            # ("nos quedamos el finde"). Con ella, el re-pregunta de abajo ya
            # muestra las opciones.
            resolved = await resolve_slot_answer("stay_duration", message, lang=state.language)
            if resolved.get("value") in ("single_day", "multi_day"):
                state.detected_duration = resolved["value"]
        else:
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
        resolved = _jev_pending_answer(prev_pending, routing_signals)
        if resolved is None:
            resolved = await resolve_slot_answer(prev_pending, message, lang=state.language)
        resolved_value = resolved.get("value")
        # Verificación determinista para SLOT_LOCATION (hallazgo en vivo,
        # batería sintética contra PRE, 2026-08-26, portado de pre_gadea —
        # el hallazgo más grave de la batería): un mensaje que cambia de
        # ACTIVIDAD a mitad de flujo ("mejor pensándolo bien quiero el
        # minicurso", sin mencionar ubicación en absoluto) no avanza
        # `next_missing_slot` (sigue faltando location), así que esta red
        # anti-bucle se disparaba y le preguntaba al LLM "¿qué respondió
        # para location?" — sin ningún respaldo real, el LLM alucinaba
        # "cartagena" con confianza (medido en vivo, reproducible). El
        # resultado: la reserva avanzaba con una ubicación que el cliente
        # nunca dio, saltándose la pregunta real y arriesgando un precio/
        # link incorrecto. Se descarta el valor SOLO cuando ESTE MISMO
        # turno cambió la actividad principal (`prev_main_activity` vs
        # `state.detected_activity`, ya calculados arriba) — la señal
        # concreta del hallazgo: un mensaje que habla de actividad no dice
        # nada de ubicación. No se exige respaldo textual literal
        # ("cartagena"/"isla") porque hay respuestas legítimas e
        # indirectas ("ya estamos alojados por la zona de playa blanca")
        # que el LLM sí interpreta bien sin nombrar la ubicación tal cual.
        if (
            prev_pending == SLOT_LOCATION
            and resolved_value in ("cartagena", "island")
            and prev_main_activity != state.detected_activity
        ):
            resolved_value = None
        # Misma verificación, generalizada a cualquier slot (hallazgo en vivo
        # 2026-09-01, cierre de §6.bis): si este turno resolvió el campo de
        # OTRO slot, el mensaje hablaba de ESE, no del pendiente — y lo que
        # este resolutor devuelva para el pendiente viene del historial, no
        # del cliente. Ver `_turn_answered_a_different_slot` para por qué aquí
        # no vale un gate de tema por vocabulario.
        if resolved_value is not None and _turn_answered_a_different_slot(
            state, prev_pending, carry
        ):
            logger.info(
                f"[CORE] slot resolver descartado para {prev_pending!r} "
                f"(el turno respondio a otro slot) msg={supervisor._log_safe_message(message)!r}"
            )
            resolved_value = None
        if (
            resolved_value is not None and prev_pending == SLOT_QTY
            and _number_of_something_else(state, message, resolved_value)
        ):
            from src.observability import marca_regex  # lazy

            marca_regex("R5")  # CALN-8 (6): el número es otra magnitud según el detector
            logger.info(
                f"[CORE] slot resolver descartado para 'qty' (el numero es de otra magnitud) "
                f"msg={supervisor._log_safe_message(message)!r}"
            )
            resolved_value = None
        if resolved_value is not None and _apply_resolved_slot_value(state, prev_pending, resolved_value):
            advanced = True

    # Última red antes del genérico: heurística blanda de pregunta de info
    # (sin exigir "?", ya descartado arriba) — mismo camino RAG de siempre.
    if (
        not advanced and _looks_like_question(message) and not _is_greeting_only(message)
        and not _has_pending_answer(state)  # u3-4: ya se está contestando en paralelo
    ):
        answer = greeting + await _answer_question(state, message)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Ningún gate de extracción resolvió el turno → pasar a slot-fill + cierre.
    return None
