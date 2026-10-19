"""Nodo `extraction` del subgrafo de la reserva: `_extraction_phase` y su cuerpo, `_understand` (regex + `fill_gaps`),
acompañantes, multi-ítem, redes de precisión, contradicciones y el turno con pregunta.

La capa de abajo, lo que el núcleo hace con el extractor del turno (ex-5), está en `extractor.py`.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

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
    _cart_will_include_cert,
    _companion_activity_options,
    _course_level_options,
    _detector,
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
    _PERSON_NOUN_PLURAL_EN,
    _PERSON_NOUN_PLURAL_ES,
    _PERSON_NOUN_SINGULAR_EN,
    _PERSON_NOUN_SINGULAR_ES,
    _SINGULAR_PERSON,
    certification_claim,
    course_level_is_ambiguous,
)
from src.agents.llm_extractor import (
    detect_special_signals,
    fill_gaps,
    missing_fields,
    resolve_slot_answer,
)
from src.agents.nucleo.extractor import (
    _CAMPOS_LISTA_CERRADA,
    _aplicar_extractor,
    campos_del_extractor,
)
from src.config import settings
from src.domain import activities as dom
from src.flows import cart_render
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
        state.pending_companion_activity = value
        state.needs_companion_activity = False
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

# Conteo total dentro de una pregunta de precio/info ("how much for 2
# people?", "cuanto cuesta para 2 personas?") -- hallazgo en vivo (lote 9,
# bateria sintetica contra PRE, 2026-09-02): "how much for 2 people,
# certified diving?" disparaba `_MENTIONS_PERSON_RE` solo por la palabra
# "people", y el propio `detect_special_signals` (LLM) tambien devolvia
# `mentions_other_person=true` -- ninguno de los dos tenia respaldo real de
# un ACOMPAÑANTE con actividad distinta, era el tamaño total del grupo
# preguntando precio. Resultado: se trataba "certified diving" como la
# actividad de un acompañante fantasma en vez de la del grupo completo, el
# estado de certificacion del hablante principal quedaba sin resolver, y el
# turno terminaba con la respuesta de precio + una re-pregunta redundante de
# "¿eres buzo certificado?" pese a que el propio mensaje ya lo decia.
_BARE_HEADCOUNT_RE = re.compile(
    r"\b(?:for|para)\s+\d+\s+(?:people|personas?|folks?|persons?)\b",
    re.IGNORECASE,
)


def _mentions_person(message: str) -> bool:
    # Se enmascara el conteo total ("for 2 people") antes de evaluar: si
    # "people"/"personas" no aparece en NINGUN otro sitio del mensaje, no es
    # una mencion real de otra persona (ver _BARE_HEADCOUNT_RE arriba).
    masked = _BARE_HEADCOUNT_RE.sub("", message)
    return bool(_MENTIONS_PERSON_RE.search(masked))


def _menciona_a_alguien(state: ConversationState, message: str) -> bool:
    """s4-26 (flag `jev_acompanante_manda`): ¿el mensaje menciona a otra persona? Si Jev esta seguro de que
    no (companion_joins < COMPANION_NONE_MAX, la puerta de u3-6), manda Jev; si no lo sabemos, la regex de
    siempre. Todas las decisiones del acompañante del turno pasan por aqui."""
    if settings.jev_acompanante_manda:
        from src.agents.jev_router import COMPANION_NONE_MAX  # lazy

        p = getattr(state, "_jev_companion", None)
        if p is not None and p < COMPANION_NONE_MAX:
            if _mentions_person(message):
                logger.info(f"[CORE][S4-26] la regex ve a otra persona y Jev no ({p:.2f}): manda Jev")
            return False
    return _mentions_person(message)


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

# Respaldo determinista para la asimetría señalada en la auditoría de Fase B
# (2026-07-23): `companion_qty` se descarta si el mensaje no trae un número
# real (`_EXPLICIT_NUMBER_RE`), pero `companion_is_singular` no tenía ninguna
# segunda verificación — si el LLM dice singular=True para un plural con
# jerga rarísima, nada lo contradice. Sustantivo de compañero en PLURAL
# inequívoco (termina en "s": "amigos", "parceros", "friends"...) — si
# aparece, no se confía en `companion_is_singular=True` del LLM aunque lo
# devuelva, y se pasa a preguntar cuántos son en vez de asumir 1.
# Inventario regex 2026-09-03: sustantivos plurales de parentesco ahora
# vienen de la fuente compartida (`_PERSON_NOUN_PLURAL_ES/EN`,
# intent_detector.py) -- cierra un gap real (suegros/cuñados/sobrinos/
# nietos/abuelos y brothers/sisters/sons/daughters/cousins/kids en plural
# faltaban aquí pese a estar en otras listas del mismo concepto). La jerga
# regional (parcero/pana/carnal/compa/pata/causa) NO es parte del
# vocabulario compartido a propósito -- se queda local a este patrón.
_PLURAL_COMPANION_RE = re.compile(
    r"\b(?:" + _PERSON_NOUN_PLURAL_ES + r"|"
    # La jerga plural se queda AQUI a proposito (medido 2026-09-15): llevarla a la
    # lista compartida hacia que el conteo de grupo del detector sumara "dos panas
    # y yo" = 3 y pisara un "somos 4" explicito. Aqui solo decide singular/plural.
    r"parceros?|parceras?|cuates|panas|carnales|compas|patas|causas|"
    + _PERSON_NOUN_PLURAL_EN + r")\b",
    re.IGNORECASE,
)


_WORD_TO_NUM = number_words(1, 10)


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


# Personas nombradas una a una: la misma pieza `_SINGULAR_PERSON` que usa
# `_SINGULAR_COMPANION_RE`. Los plurales ("mis amigos") no cuentan: siguen sin respaldar cifra.
_NAMED_PERSON_RE = re.compile(_SINGULAR_PERSON, re.IGNORECASE)


def _singular_companion(message: str) -> bool:
    """¿El mensaje habla de UN solo acompañante? Exactamente una persona nombrada o, si no
    nombra a nadie, "someone"/"uno que" (2026-09-15). Antes bastaba con que apareciera una:
    "vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel" o "my daughter is 9 and my
    son is 12" contaban como un acompañante y se asumia cantidad 1 sin preguntar."""
    named = len(_NAMED_PERSON_RE.findall(message))
    return named == 1 or (named == 0 and bool(_SINGULAR_COMPANION_RE.search(message)))


def _consume_number(counts: Counter, n) -> bool:
    """True y descuenta una ocurrencia si `n` sigue disponible en `counts`."""
    if n is not None and counts.get(n, 0) > 0:
        counts[n] -= 1
        return True
    return False


# Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 3, portado de
# pre_gadea v0.21.3): "mi amigo... él es certificado también" respalda
# `certified_diving` igual que "quiere bucear" — declarar la certificación
# del acompañante ES la intención (nadie dice "ya soy certificado" para
# pedir un minicurso). Sin este respaldo, el guard determinista descartaba
# una señal del LLM que SÍ era correcta (medido 3/3, `detect_special_
# signals` devolvía `certified_diving` bien), preguntando "¿minicurso o
# snorkel?" a un acompañante YA certificado — ninguna de las dos opciones
# tiene sentido en ese caso. Negado explícito ("no está certificado") NO
# cuenta como respaldo — ese es el caso genuino de `SLOT_COMPANION_ACTIVITY`
# que sí necesita preguntar.
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
    # El acompanante es OTRA persona: cuenta su certificacion ("mi amigo tiene licencia").
    if activity == "certified_diving" and certification_claim(message, about_writer=False) is True:
        return True
    return False


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
# La regla estructural (no un parche por síntoma, misma familia que el bloqueo
# de `detect_special_signals` de `_group_allocation_fully_resolved`): un
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


def _relevant_gaps(state: ConversationState, intent, message: str, *, keep_pending_bool: bool = False) -> list[str]:
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
    # PUERTA RETIRADA (2026-09-12). Aqui se quitaba `group_allocation` de los
    # huecos cuando ya se sabia la cantidad y el mensaje no anadia gente. El
    # motivo era el COSTE ("pedirlo cada turno era gasto puro"), y ese argumento
    # decayo al fusionar las peticiones del turno: un campo mas viaja en la
    # MISMA peticion, asi que cuesta tokens (abundante), no peticiones (lo
    # escaso).
    #
    # Medido antes de quitarla, con scripts/battery_group_allocation_gate.py
    # (23 escenarios de conversacion x 4 variantes x 2 repeticiones):
    #   hoy (puerta puesta)     3/10 repartos correctos
    #   puerta fuera + veto     6/10, 0 repartos parciales, 0 alucinaciones
    # Los 10 escenarios de riesgo (turnos donde inventarse un reparto seria un
    # misfill) salen limpios en las cuatro variantes: lo que protege de eso no
    # era esta puerta sino `_state_known_fields`, que impide rederivar un
    # reparto que la conversacion YA sabe.
    #
    # No va sola: depende de `supervisor.enforce_group_allocation_consistency`,
    # que impide guardar un reparto que no suma el total. Sin esa invariante,
    # quitar la puerta introducia repartos PARCIALES (medido), que son peores
    # que no tener reparto.
    #
    # PERO el argumento "viaja gratis" solo vale si la peticion YA se iba a
    # hacer. Si `group_allocation` fuese el UNICO hueco, seria el causante de
    # una llamada que si no no existiria -- y una reserva ya completa haria una
    # peticion en cada turno de charla ("genial, nos vemos"). Asi que se aplica
    # el argumento tal cual: puede viajar de acompanante, nunca originar la
    # peticion. Lo caza `test_understand_skips_llm_when_state_knows_driving_fields`.
    if gaps == ["group_allocation"]:
        gaps = []
    # GUARDA (a) — el slot booleano que el bot ACABA de preguntar no se le pide
    # nunca a `fill_gaps`. Ver `_BOOL_SLOT_FIELD`: esos campos ya tienen dos
    # resolutores anclados al mensaje del turno, y `fill_gaps` es el único de
    # los tres que puede "contestar" mirando el historial.
    #
    # Excepción (u3-4, 26-sep): el relleno CON PUERTA del turno con pregunta
    # (`keep_pending_bool`). Va sin historial y con el "sí" de Jev para ese campo, así que
    # el motivo de la guarda no aplica; y en un turno con pregunta los otros dos resolutores
    # se lo saltan (la respuesta corta exige que no haya "?" y `resolve_slot_answer`, que no
    # "parezca pregunta"), así que sin esto "completé el curso básico el 3 de abril, ¿tengo
    # que hacer algo especial?" se perdía siempre (regresión de la ronda B2).
    pending_field = _BOOL_SLOT_FIELD.get(state.core_pending_slot)
    if pending_field and not keep_pending_bool:
        gaps = [f for f in gaps if f != pending_field]
    return gaps


async def _edades_las_lee_el_extractor(state: ConversationState, message: str) -> bool:
    """ex-9b paso 6 (`edades_por_extractor`): ¿leyó el extractor este mensaje (con su campo `edades`)? Espera la lectura
    adelantada sin gastarla (`lectura_del_extractor`): ninguna llamada más."""
    if not settings.edades_por_extractor:
        return False
    from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

    return await lectura_del_extractor(state, message) is not None


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
    # ex-5 (fase EX): los dominios que entiende el extractor "LLM primero" no los
    # decide el regex. Lo que leyó se queda en el intent como PROVISIONAL (las guardas que miran si el mensaje
    # CONTESTA la pregunta pendiente lo siguen viendo, como hoy), pero ni dispara contradicciones, ni va al veto, al
    # relleno o a la re-comprobación. Al final se sustituye por lo del extractor (`_ubicacion_del_extractor`).
    # ex-9b paso 3: la pista solo guarda la isla y el hotel del catálogo; lo demás lo decide el extractor y, si falla,
    # se pregunta.
    pista_lugar = _pista_del_regex(intent)
    # u3-4: turno con pregunta (la respuesta del RAG ya está lanzada en paralelo).
    question_turn_fields = None
    if _has_pending_answer(state):
        question_turn_fields = _question_turn_fields(intent, state)
    state.mixed_nationality_notice = False
    # ex-9 (15-oct): con los cuatro dominios en el extractor "LLM primero" (ex-5…ex-8), lo único que el relleno LLM de
    # siempre (`fill_gaps`) aún decide son las EDADES de los menores. El veto, la re-comprobación de lo sabido, la
    # verificación del turno con pregunta, las contradicciones del regex y las guardas del parche (grupo, booleanos,
    # origen, grupo mixto) se quedaban sin campos y se quitaron (HISTORY 0.31.28).
    gaps = [f for f in _relevant_gaps(state, intent, message) if f not in campos_del_extractor()]
    # u3-4: un mensaje con pregunta ya no se salta el relleno (así nació el núcleo, 22-jul: pregunta -> RAG O dato ->
    # extracción); el dato que venga junto a la pregunta no se pierde.
    rellenar = gaps if question_turn_fields is None and not _is_greeting_only(message) else []
    rellenar_sin_historial = []
    if question_turn_fields is not None and not _is_greeting_only(message):
        # u3-4 paso 3: en el turno con pregunta, solo los huecos que Jev dice que el cliente afirma en ESTE mensaje, y
        # sin historial (Jev solo ve el mensaje).
        afirma = getattr(state, "_answer_affirms", None) or {}
        rellenar_sin_historial = [
            f for f in _relevant_gaps(state, intent, message, keep_pending_bool=True)
            if afirma.get(f) is True and f not in campos_del_extractor()
        ]
    if "ages" in rellenar + rellenar_sin_historial and await _edades_las_lee_el_extractor(state, message):
        # ex-9b paso 6 (`edades_por_extractor`): las edades las da el extractor con su cita (`_poner_edades`); el relleno
        # con el historial no las supone. Si el extractor falla, el relleno de siempre.
        rellenar = [f for f in rellenar if f != "ages"]
        rellenar_sin_historial = [f for f in rellenar_sin_historial if f != "ages"]
    if rellenar or rellenar_sin_historial:
        patch = await fill_gaps(
            message, intent, history=state.history if rellenar else None, lang=state.language,
            only_fields=rellenar or rellenar_sin_historial,
        )
        patch = {
            f: v for f, v in patch.items()
            if f not in campos_del_extractor() and f not in ("evidence", "mixed_nationality")
        }
        for field_name, value in patch.items():
            setattr(intent, field_name, value)
            if field_name not in intent.detected_fields:
                intent.detected_fields.append(field_name)
        if patch:
            # (Fix A del handoff) El tag que parsea scripts/harvest_cutover_logs.py.
            logger.info(f"[EXTRACT][CUTOVER] applied={patch} msg={supervisor._log_safe_message(message)!r}")
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
        state.needs_companion_activity = False
        state.companion_activity_deferred = False
        state.pending_companion_activity = None
        state.pending_companion_queue = []
        state.pending_split_total = None
        state.pending_undecided_qty = None

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
        # una cifra inventada — dejar el estado sin tocar para que el bloque
        # de la red de precisión más abajo (`detect_special_signals`)
        # pregunte cuántos son.
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


def _number_of_something_else(state: ConversationState, message: str, value) -> bool:
    """¿El detector ya lee ese numero como otra magnitud (inmersiones, dias, edades)? Lo
    usa el resolutor LLM de la pregunta del total (G): con "¿cuantas personas?"
    pendiente, "2 inmersiones" volvia como 2 personas 2/2."""
    intent = _detector.detect(message, state)
    return value in {intent.cert_dives, intent.cert_days, *(intent.ages or [])}


def _add_or_ask_companion(state: ConversationState, message: str, activity: str, qty: int) -> None:
    """Punto unico para la actividad de otra persona (tarea 7a, 2026-09-15).

    Quien es otra persona lo decide el turno (fast-path o red de precision LLM, que
    reconoce pronombres y jerga). Lo que ni el texto ni el LLM dicen es si esa persona
    YA estaba contada: "él quiere hacer snorkel" y "también viene mi hermana que quiere
    hacer snorkel" dan la misma señal. Si sumarla supera el total conocido y el mensaje
    no dice que se suma alguien, no se adivina: se pregunta el total
    (`pending_companion_in_group` -> SLOT_QTY) y la respuesta decide mover o añadir.
    Quien escribe siempre es uno de los contados, asi que con un total de 1 cualquier
    otra persona es nueva (`qty <= total - 1`)."""
    total = state.detected_group_size
    counted = sum((state.detected_group_allocation or {}).values()) or (total or 0)
    if (
        total and qty <= total - 1 and counted + qty > total
        and not _ADDITION_CUE_RE.search(message)
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
    _merge_companion_activity(state, activity, qty)


# ex-9b paso 6 (`reparto_al_sumarse_alguien`): por encima, Jev está SEGURO de que el mensaje mete a otra persona en la
# reserva (`companion_joins`). En los fallos de "se suma alguien a un grupo ya repartido" Jev daba 0,94-0,97.
_JEV_SE_SUMA_MIN = 0.8


def _jev_seguro_de_que_se_suma(state: ConversationState, companion_ambiguous: bool) -> bool:
    """ex-9b paso 6 (`reparto_al_sumarse_alguien`): el atajo de "el reparto ya cubre a todo el grupo" se saltaba la red de
    acompañantes aunque el mensaje sumara a alguien ("mi hermano también viene, él quiere hacer snorkel" sobre {buceo: 2}
    para 2): la persona se perdía. Se deja pasar el turno solo si el mensaje nombra a otra persona y Jev está seguro de
    que entra en la reserva; el atajo sigue para todo lo demás (se puso porque el router LLM de antes inventaba
    acompañantes). Si el extractor ya amplió el reparto en este turno, `companion_ambiguous` es False y no hace falta."""
    if not settings.reparto_al_sumarse_alguien or not companion_ambiguous:
        return False
    p = getattr(state, "_jev_companion", None)
    if p is None or p < _JEV_SE_SUMA_MIN:
        return False
    logger.info(f"[CORE][EX9B-6] reparto completo, pero Jev seguro de que se suma alguien ({p:.2f}): la red de "
                "acompañantes corre")
    return True


def _jev_dice_ya_contada(state: ConversationState) -> bool:
    """s4-26 (flag `jev_persona_ya_contada`): ¿Jev esta SEGURO de que el mensaje no suma a una persona nueva
    (adds_person < ADDS_PERSON_NOT_MAX), sino que habla de alguien que ya estaba en el grupo? Ausente = no lo
    sabemos -> se pregunta el total, como hoy. Banco ciego (frases propias, no del golden): 0/10 personas nuevas
    por debajo del umbral (la mas baja 0,45), 9/10 ya contadas por debajo."""
    if not settings.jev_persona_ya_contada:
        return False
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


def _jev_rules_out_special_signals(state: ConversationState) -> bool:
    """u3-6: ¿Jev descarta todo lo que busca `detect_special_signals`? Seguro de
    que el mensaje no mete a otra persona (p < COMPANION_NONE_MAX), que no pide recordar, y sin la
    pregunta del refresher pendiente (esa respuesta la lee el LLM). Banco
    `scripts/sonda_acompanante.py`: 0/14 acompanantes perdidos, 13/14 turnos normales sin la llamada."""
    from src.agents.jev_router import COMPANION_NONE_MAX  # lazy

    p = getattr(state, "_jev_companion", None)
    if p is None or p >= COMPANION_NONE_MAX or not _jev_says_no_recall(state):
        return False
    # Con el refresher en juego (mas de 2 anos sin bucear) la respuesta a esa pregunta puede llegar en
    # cualquier turno ("espera, en realidad si lo quiero" con otra pregunta ya pendiente, escalon 0):
    # esa la lee el LLM.
    if state.last_dive_over_2_years or (state.core_pending_slot or next_missing_slot(state)) == SLOT_REFRESHER:
        return False
    logger.info(f"[CORE][U3-6] señales sin LLM (Jev: acompañante {p:.2f}, no pide recordar)")
    return True


def _apply_question_turn_answers(intent, fields: list[str], answers: dict, message: str) -> None:
    """u3-4 arreglo 2: en un turno con pregunta se guarda lo que el LLM AFIRMA.

    Tres casos por campo, y el tercero es el que arregla la regresión del escalón 1:

    - el LLM devuelve el MISMO valor que el regex -> confirmado, se queda;
    - devuelve OTRO valor -> corrige (el regex leyó mal la frase);
    - **no lo devuelve** -> nadie lo afirma, se cae. Aquí es donde mueren
      "¿me recomiendas un hotel en Rosario?" (el regex leía isla) e "in case I
      decided to do the Open Water course?" (el relleno lo daba por dato).

    Se aplica sin mirar el flag `llm_*_veto_cutover` de cada campo, y es a
    propósito: esos flags gobiernan el veto del turno NORMAL, donde la pregunta es
    "¿el regex leyó mal?" y cada campo se midió por separado (`location`,
    `is_certified` e `is_colombian` están en `False`). Aquí la pregunta es otra —
    "¿el cliente afirma esto o es hipótesis?" — y solo corre en turnos con pregunta.
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
    prev_main_service_id = carry["prev_main_service_id"]
    prev_main_is_certified = carry["prev_main_is_certified"]
    prev_main_last_dive = carry["prev_main_last_dive"]
    prev_main_refresher = carry["prev_main_refresher"]
    prev_group_size = carry["prev_group_size"]
    prev_group_allocation = carry["prev_group_allocation"]

    # COMPRENDER: extracción del resto del mensaje.
    companion_merged_fastpath = False
    # ex-9b paso 4: una respuesta corta resuelta por la IA no se salta la lectura del resto (ver `_routing_phase`).
    if not (resolved_short and len(message.strip()) <= 12) or carry.get("respuesta_por_la_ia"):
        _, companion_merged_fastpath = await _understand(state, message, answered_pending=resolved_short)
    if state.mixed_nationality_notice:
        # Una sola fuente de copy y efecto para el grupo mixto (hallazgo A, 2026-09-15).
        state.mixed_nationality_notice = False
        response = greeting + supervisor._mixed_nationality_response(state, message)
        state.history.append({"role": "assistant", "content": response})
        return response

    # Circuit-breaker (portado 2026-09-01, hallazgo en vivo, batería de
    # grupos mixtos contra PRE, lote 8): este chequeo es el punto REAL que
    # consume `pending_companion_queue` para preguntar por un acompañante —
    # y corre SIEMPRE, incluso en el turno de arriba donde `_understand()`
    # se salta por ser respuesta corta ya resuelta (`resolved_short and
    # len(message) <= 12`, p. ej. "no"/"cartagena"). Si el reparto del grupo
    # YA cubre a todo el mundo, no puede quedar ningún acompañante sin
    # actividad — limpiar la cola aquí, justo antes de que se consuma.
    if _group_allocation_fully_resolved(state):
        state.needs_companion_activity = False
        state.companion_activity_deferred = False
        state.pending_companion_activity = None
        state.pending_companion_queue = []
        state.pending_split_total = None
        state.pending_undecided_qty = None

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
    # Auditoría 2026-08-26 (batería sintética contra PRE, portado de
    # pre_gadea v0.21.1): interrumpir SIEMPRE aquí, sin mirar si ya había
    # una pregunta obligatoria pendiente (seguridad, nacionalidad...), la
    # enterraba sin preguntarla nunca — "soy buzo certificado... ¿han
    # pasado más de 2 años?" seguido de "somos 2" saltaba directo a la
    # pregunta del acompañante, sin que la de seguridad se llegara a
    # responder jamás. Mismo criterio que el bloque
    # `companion_activity_deferred` de más abajo: solo se interrumpe YA
    # MISMO si no había nada más pendiente; si lo había, se difiere (se
    # deja caer sin `return`, para que el resto del turno siga su curso
    # normal — `next_missing_slot` volverá a preguntar por lo que de
    # verdad tocaba) y se marca para retomar el acompañante en cuanto ese
    # hueco se cierre.
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
    # D, batería sintética 2026-08-26, portado de pre_gadea). Se comprueba
    # también `state.detected_activity` (post-turno) para cubrir ambos casos
    # sin ampliar el disparo a mensajes que no mencionan actividad alguna.
    companion_ambiguous = bool(
        (prev_main_activity in _ACTIVITY_TO_CART_TYPE or state.detected_activity in _ACTIVITY_TO_CART_TYPE)
        and _menciona_a_alguien(state, message)
        and not companion_merged_fastpath
        and not group_composition_resolved_by_base_extraction
    )
    # Circuit-breaker (portado 2026-09-01, hallazgo en vivo, batería de
    # grupos mixtos contra PRE, lote 8, confirmado con trazas de LangSmith):
    # `detect_special_signals` RE-DERIVA `mentions_other_person`/
    # `companion_activity`/`other_companions` del HISTORIAL ENTERO en cada
    # llamada — con un reparto ya completo ("2 certificados, 2 minicurso, 2
    # snorkel" para un grupo de 6), un turno tan inocuo como "ninguno
    # colombiano" (respondiendo nacionalidad, sin mencionar a nadie) hizo que
    # el LLM redescubriera la conversación de grupo y devolviera
    # `mentions_other_person=true` + una re-descripción de todo el reparto
    # como "acompañantes" — pisando `detected_group_allocation`, ya
    # correcto, con una versión parcial. Si el grupo ya está completamente
    # explicado, no hay ninguna ambigüedad de acompañante que esta llamada
    # pueda resolver — se salta entera (ahorra una llamada LLM de paso).
    if (not advanced or companion_ambiguous) and not (
        _group_allocation_fully_resolved(state) and not _jev_seguro_de_que_se_suma(state, companion_ambiguous)
    ):
        signals = (
            {} if _jev_rules_out_special_signals(state)
            else await detect_special_signals(message, history=state.history, lang=state.language)
        )
        activity = signals.get("companion_activity")
        # Guardado ANTES del descarte por falta de respaldo textual de abajo
        # (hallazgo en vivo, lote 10, 2026-09-02): el guard de "misma
        # actividad que el grupo" más abajo necesita lo que el LLM DIJO, no
        # si ese valor tenía o no respaldo textual -- un mensaje como
        # "perfecto, hagamos la reserva" no respalda NINGUNA actividad
        # (`activity` se pone a None por el chequeo de abajo), pero eso no
        # significa que ya no exista la señal fantasma que hay que descartar
        # -- solo cambia por qué rama de código la deja pasar.
        raw_companion_activity = activity
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
        #
        # Excepcion (hallazgo en vivo, lote 9, 2026-09-02): cuando el UNICO
        # rastro de "otra persona" en el mensaje es un conteo total tipo "for
        # 2 people"/"para 2 personas" (ver _BARE_HEADCOUNT_RE), ni siquiera se
        # confia en que el propio LLM lo haya visto bien -- ya devolvio un
        # falso positivo igual que el regex en este caso real ("how much for
        # 2 people, certified diving?" -> companion fantasma con la MISMA
        # actividad que el grupo, dejando sin resolver la certificacion del
        # hablante principal y generando una re-pregunta redundante). Mismo
        # principio que 6.bis: verificacion determinista del TEXTO por encima
        # de la señal del LLM cuando hay evidencia real de que se equivoca.
        llm_mentions_other_person = bool(signals.get("mentions_other_person"))
        regex_mentions_other_person = _menciona_a_alguien(state, message)
        if (
            llm_mentions_other_person
            and not regex_mentions_other_person
            and _BARE_HEADCOUNT_RE.search(message)
        ):
            llm_mentions_other_person = False
        # Segunda variante del mismo fallo, generalizada (hallazgo en vivo,
        # lote 10, batería de conversaciones LARGAS hasta el cierre de
        # reserva, 2026-09-02): "no hace mas de 2 años que buceamos" (una
        # respuesta de SEGURIDAD sin mencionar a nadie) disparó
        # mentions_other_person=true + companion_activity=certified_diving
        # (la MISMA actividad que ya tenía el grupo), corrompiendo
        # group_allocation con un compañero fantasma y dejando la reserva en
        # un BUCLE INFINITO. Un primer fix acotó esto a los 3 temas
        # booleanos (una lista de vocabulario por tema, ya retirada) pero el MISMO fallo reapareció
        # en un mensaje que no toca ninguno de esos temas: "perfecto,
        # hagamos la reserva" (afirmación de cierre lisa y llana) volvió a
        # disparar el mismo companion_activity=certified_diving fantasma —
        # verificado en vivo tras desplegar el primer fix. Generalizado sin
        # el requisito de tema: si el LLM dice que hay un acompañante pero
        # el regex determinista NO ve a NADIE (`_mentions_person` false) Y la
        # actividad que le atribuye es la MISMA que ya tiene el grupo (no una
        # elección distinta — la señal real de un acompañante genuino), no
        # se confía en el LLM. Sigue sin tocar el caso de jerga regional que
        # motivó confiar en el LLM en primer lugar ("mi parce no está
        # certificado" -> companion_activity=minicourse, DISTINTA de
        # certified_diving), porque los disparadores léxicos reales
        # ("viene", "también", "y otro"...) ya hacen que `_mentions_person`
        # sea True para cualquier mención genuina de acompañante, aun en
        # jerga — lo único que queda sin respaldo textual y con la MISMA
        # actividad es, en la práctica, el LLM alucinando de la nada.
        #
        # Usa `raw_companion_activity` (lo que el LLM dijo) y NO `activity`
        # (ya puesta a None arriba si el mensaje no respalda textualmente
        # NINGUNA actividad -- exactamente el caso de "perfecto, hagamos la
        # reserva", que no menciona nada de buceo): con `activity` ya en
        # None, `None == state.detected_activity` siempre da False y este
        # guard nunca se disparaba para el caso que motivó el fix.
        # "La misma actividad que el grupo" es la de ANTES de este turno (tarea 7a,
        # 2026-09-15): "él quiere hacer snorkel" ya ha pisado la principal con snorkel, y
        # comparar con el estado de ahora tiraba justo el acompañante real.
        if (
            llm_mentions_other_person
            and not regex_mentions_other_person
            and raw_companion_activity == (prev_main_activity or state.detected_activity)
        ):
            llm_mentions_other_person = False
        if activity and (llm_mentions_other_person or regex_mentions_other_person):
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
            singular_confirmed = _singular_companion(message) or (
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
                _add_or_ask_companion(state, message, activity, qty)

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
            # Reusa las variables ya corregidas arriba (no `signals.get(
            # "mentions_other_person")` en crudo) -- mismo hallazgo en vivo
            # del lote 10, 2026-09-02: esta rama comparte el mismo fallo del
            # `if` de arriba (compañero fantasma sin respaldo textual, misma
            # actividad que el grupo) y con la lectura cruda seguía
            # disparando aunque `activity` fuera falsy más arriba.
            (llm_mentions_other_person or regex_mentions_other_person)
            and prev_pending != SLOT_COMPANION_ACTIVITY
            # Hallazgo en vivo (batería sintética contra PRE, 2026-08-26,
            # lote 5, portado de pre_gadea): "los niños tienen 7 y 10" (solo
            # edades, sin acompañante nuevo) hacía que `mentions_other_person`
            # (LLM, más liberal que el regex — SÍ reconoce "niños") disparara
            # esta rama, difiriendo una pregunta de acompañante que se
            # retomaba al final SIN NINGÚN motivo. Si ya estamos en contexto
            # de niños Y el regex determinista (que NO reconoce "niño") no ve
            # a nadie más, no se confía solo en la señal LLM más amplia.
            and not (state.kids_mention_detected and not _menciona_a_alguien(state, message))
            # Hallazgo en vivo (batería de grupos mixtos contra PRE,
            # 2026-09-01, lote 8): un cliente que dijo explícitamente "solo
            # yo" recibía, turnos después (incluso tras cerrar la reserva),
            # "¿qué le gustaría hacer a tu acompañante?" — `mentions_other_
            # person` (LLM) se re-deriva del HISTORIAL ENTERO en cada turno
            # (ver auditoría 2026-07-23 más abajo) y puede volver a disparar
            # sin que el turno actual mencione a nadie nuevo. `solo_traveler_
            # confirmed` se fija SOLO desde el match estricto y con guardas
            # de `_COURSE_SOLO_RE`/`intent_detector` (nunca desde un
            # `detected_group_size == 1` genérico, que también puede darse
            # legítimo mientras se negocia un acompañante aparte — ver
            # test_companion_attribute_without_activity_asks_instead_of_
            # guessing, que YA fija group_size=1 para el buzo principal
            # confirmado mientras el acompañante se resuelve por su cuenta).
            and not state.solo_traveler_confirmed
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
            # PRE, portado de pre_gadea v0.21.1): sin `prev_pending !=
            # SLOT_COMPANION_ACTIVITY`, esto entraba en BUCLE —
            # detect_special_signals RE-DERIVA la señal de "hay un
            # acompañante" desde el HISTORIAL entero cada vez que se le
            # llama, así que una respuesta vacía de contenido como "no"
            # (que en realidad respondía a SEGURIDAD, una pregunta
            # pendiente ANTERIOR que quedó enterrada) seguía devolviendo
            # `mentions_other_person=True` turno tras turno, re-preguntando
            # la MISMA pregunta sin parar. Además, interrumpir aquí SIEMPRE
            # sin mirar si ya había una pregunta obligatoria pendiente la
            # enterraba sin preguntarla nunca — se difiere con
            # `companion_activity_deferred` si hace falta.
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
        elif signals.get("recall_field") and not _jev_says_no_recall(state):
            recalled = _recall_answer(state, signals["recall_field"])
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
