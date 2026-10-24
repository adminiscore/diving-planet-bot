"""Nodo `routing` del subgrafo de la reserva: `_routing_phase` (respuestas cortas, recuerdo, deliberación y
comparación de opciones, paquete confirmado) y lo que solo usa él.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging
import re

from src.agents.conversational_core import (
    _AFFIRMS_SIGNAL_FIELDS,
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
    _answer_question,
    _apply_cert_or_course,
    _apply_group_total,
    _companion_activity_options,
    _course_level_options,
    _detector,
    _has_pending_answer,
    _is_greeting_only,
    _is_rag_fallback,
    _jev_says_no_recall,
    _maybe_launch_answer,
    _mentioned_courses,
    _mentioned_product_activities,
    _merge_companion_activity,
    _merge_pending_undecided,
    _recall_answer,
    _set_concrete_activity,
    _take_undecided_members,
    _words,
    ask_slot,
    cancel_pending_answer,
)
from src.agents.intent_detector import (
    _GENERIC_ISLAND_RE,
    AGE_WORDS,
    DetectedIntent,
)
from src.agents.llm_extractor import detect_special_signals
from src.config import settings
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState
from src.utils.fuzzy import is_affirmative, is_agree, is_negative
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")


# Cliente confirma un paquete multi-día deícticamente ("quiero este paquete",
# sin repetir el número) justo después de que el bot lo describió -- hallazgo
# en vivo (conversación real 831, 2026-09-02): el mensaje de confirmación casi
# siempre trae un "?" pegado ("...que podria hacer esos dos dias?"), así que
# nunca pasaba por `_understand()`/extracción (el gate de "?" manda directo a
# RAG, ver más abajo) y el carrito se quedaba con el paquete de 1 día ANTERIOR
# — el resumen final decía "ya en tu carrito" sobre el paquete VIEJO, no el
# que el cliente acababa de confirmar. Ver `_maybe_apply_confirmed_package`.
_CONFIRMS_DESCRIBED_PACKAGE_RE = re.compile(
    r"quiero\s+(?:este|ese|el)\s+paquete|quiero\s+ir\s+con\s+(?:este|ese|el)\s+plan|"
    r"i\s+want\s+(?:this|that|the)\s+package|(?:l['e]|voy\s+con)\s+(?:este|ese)\s+paquete",
    re.IGNORECASE,
)


def _maybe_apply_confirmed_package(state: ConversationState, message: str) -> None:
    """Si el cliente confirma deícticamente el paquete multi-día que el bot
    ACABA de describir ("quiero este paquete"), fija `detected_cert_dives` al
    número real (leído del último mensaje del propio bot, no adivinado) y
    limpia `mixed_cart` para que se reconstruya con el paquete correcto la
    próxima vez que se cierre/resuma la reserva -- en vez de quedarse
    pegado al paquete de 1 día que se había armado antes de esta conversación
    sobre alternativas. Determinista: solo actúa si el bot mismo nombró un
    número de inmersiones concreto en su último mensaje."""
    if not _CONFIRMS_DESCRIBED_PACKAGE_RE.search(message):
        return
    # Solo si el bot describio UN paquete multi-dia: si comparo varios, "este paquete"
    # no dice cual (2026-09-15, lectura compartida con el detector y el RAG).
    _elegir_el_paquete_propuesto(state)


def _elegir_el_paquete_propuesto(state: ConversationState) -> bool:
    """El cliente elige el paquete que el bot acaba de proponer (`plan_que_propone_el_bot`): su nº de inmersiones y el
    carrito vacío para rehacerlo con él. False si el bot no propuso uno solo o ya era el elegido."""
    from src.agents.extractor_turno import plan_que_propone_el_bot  # lazy

    dives = plan_que_propone_el_bot(state.history)
    if dives is None or dives == state.detected_cert_dives:
        return False
    state.detected_cert_dives = dives
    state.mixed_cart = []
    return True


async def _paquete_confirmado(state: ConversationState, message: str) -> None:
    """ex-9b paso 6 (`plan_elegido_por_extractor`): si el bot acaba de proponer UN paquete y el extractor lee que el
    mensaje lo ACEPTA (`acepta_propuesta`, con su cita: "perfecto, ese me sirve"), queda elegido y sigue la reserva
    (decisión de Gadea, 19-oct). Preguntar su precio no es aceptarlo. Solo espera al extractor cuando hay propuesta (es
    la única vez que lleva ese campo); si el extractor falla, la frase de siempre (`_CONFIRMS_DESCRIBED_PACKAGE_RE`).
    Sin el flag, la frase de siempre."""
    if not settings.plan_elegido_por_extractor:
        _maybe_apply_confirmed_package(state, message)
        return
    from src.agents.extractor_turno import plan_que_propone_el_bot  # lazy
    from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

    dives = plan_que_propone_el_bot(state.history)
    if dives is None or dives == state.detected_cert_dives:
        return
    datos = await lectura_del_extractor(state, message)
    if datos is None:
        logger.info("[CORE][EX9B-6] el extractor falló: el paquete confirmado lo decide la frase de siempre")
        _maybe_apply_confirmed_package(state, message)
        return
    if datos.get("acepta_propuesta") is True and _elegir_el_paquete_propuesto(state):
        logger.info(f"[CORE][EX9B-6] el cliente acepta el paquete propuesto: {dives} inmersiones")


def _departure_place(message: str) -> str | None:
    """Lugar de salida en la RESPUESTA a "¿desde donde saldrias?" (hallazgo C, 2026-09-15).
    Las palabras de lugar son las del detector (apodos de la ciudad, hoteles, islas; "rezar
    el rosario" no es isla), y una isla sin nombre ("isla", "Barú") vale como respuesta.
    Con Cartagena y una isla, decide el papel de cada lugar en el detector (`place_by_role`,
    hallazgo C.2): "quiero ir a las islas del rosario desde cartagena" sale de Cartagena."""
    text = (message or "").lower()
    intent = DetectedIntent()
    _detector._detect_location(text, intent)
    if intent.location:
        return intent.location
    isla = _GENERIC_ISLAND_RE.search(text)
    if isla and strip_accents(isla.group(0).lower()) == "baru":
        # G3-06: Barú no es una isla del Rosario (ver `lugar_sin_baru`); gen-6: quien se aloja allí sale desde Cartagena.
        return "cartagena"
    return "island" if isla else None


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


# ex-9b paso 4: las respuestas cortas que lee la IA en vez del regex.
_RESPUESTA_LEIDA_POR_LA_IA = frozenset({SLOT_LOCATION, SLOT_HOTEL, SLOT_QTY})


def _es_formato(state: ConversationState, slot: str, message: str) -> bool:
    """¿La respuesta es FORMATO y no hay que entenderla? Un botón (su título tecleado o su valor), "1"/"2" a la pregunta
    del origen o una cifra sola a "¿cuántos sois?" ("4", "dos"). Eso se sigue leyendo sin IA."""
    msg = message.strip().lower()
    if _button_value(state, message) is not None:
        return True
    if msg in {str(o.get("value", "")).lower() for o in state.quick_replies or []}:
        return True
    if slot == SLOT_LOCATION:
        return msg in ("1", "2")
    if slot == SLOT_QTY:
        return len(_words(message)) == 1 and cart_render.parse_quantity(message) is not None
    if slot == SLOT_COMPANION_ACTIVITY:
        return msg.isdigit()  # el número de una opción
    if slot == SLOT_AGES:
        # Solo cifras ("6 y 9", "8, 10"): la lectura de siempre basta. Con palabras, la lee la IA ("tiene 6 y el otro 9").
        palabras = _words(message)
        return any(p.isdigit() for p in palabras) and all(p.isdigit() or p in ("y", "e", "and") for p in palabras)
    return False


def _respuesta_del_paso6(state: ConversationState, slot: str) -> bool:
    """ex-9b paso 6: ¿la respuesta corta a esta pregunta la lee el extractor? Las edades; y el "¿un día o varios?" del
    acompañante (primer paso, aún sin duración)."""
    if slot == SLOT_AGES:
        return True
    return slot == SLOT_COMPANION_ACTIVITY and state.detected_duration is None


async def _lectura_de_la_ia(state: ConversationState, message: str, routing_signals: dict, slot: str) -> dict | None:
    """ex-9b paso 4: lo que la IA lee de la respuesta corta a la pregunta pendiente:
    {"jev": la respuesta de Jev a ESA pregunta (`pending_answer`, aunque dude), "extractor": lo que leyó el extractor}.
    None = el regex de siempre: otra pregunta, formato, o la IA calla (Jev no contestó a la pregunta y el extractor
    falló), la misma regla que `supervisor.regex_decide`. Con la respuesta de Jev al origen no
    hace falta esperar al extractor aquí: lo aplica `_understand` como siempre.
    ex-9b paso 6: también la respuesta a "¿qué edades tienen?" (`edades_por_extractor`) y a "¿un día o varios?" de la
    recomendación para el acompañante (`duracion_por_extractor`), con el extractor; los botones y las cifras solas son
    formato y se leen como siempre."""
    if _respuesta_del_paso6(state, slot):
        if _es_formato(state, slot, message):
            return None
        from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

        datos = await lectura_del_extractor(state, message)
        if datos is None:
            logger.info(f"[CORE][EX9B-6] la IA calla en la respuesta a {slot!r}: decide el regex de siempre")
            return None
        return {"jev": None, "extractor": datos}
    if slot not in _RESPUESTA_LEIDA_POR_LA_IA:
        return None
    if _es_formato(state, slot, message):
        return None
    pa = routing_signals.get("pending_answer")
    jev = pa if isinstance(pa, dict) and pa.get("slot") == slot else None
    datos = None
    if jev is None:
        from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

        datos = await lectura_del_extractor(state, message)
        if datos is None:
            logger.info(f"[CORE][EX9B-4] la IA calla en la respuesta a {slot!r}: decide el regex de siempre")
            return None
    return {"jev": jev, "extractor": datos}


def _lugar_del_catalogo(texto: str) -> tuple[str | None, str | None]:
    """(hotel, isla) de la lista cerrada del catálogo que nombra el texto (la del detector, clase d: se queda)."""
    intent = DetectedIntent()
    _detector._detect_location((texto or "").lower(), intent)
    return intent.hotel, intent.island


def _origen_por_la_ia(state: ConversationState, message: str, ia: dict) -> bool:
    """El origen en la respuesta corta, según Jev (`pending_answer`, seguro). Si Jev duda, dice que no contesta o no
    contestó, no se resuelve aquí: lo leen el extractor en `_understand` y la red anti-bucle del mismo turno (Jev si está
    seguro; si no, el resolutor LLM), con sus guardas, como cualquier respuesta que el regex no entendía. La delegación
    ("da igual", "tú decides" = Cartagena, la salida recomendada) Jev la contesta dudando (0,27-0,62 en el banco del
    paso 4) y la acaba resolviendo el resolutor (5/5)."""
    from src.agents.jev_router import PENDING_ANSWER_MIN  # lazy

    jev = ia.get("jev") or {}
    valor = jev.get("value")
    if valor in ("cartagena", "island") and jev.get("confidence", 0.0) >= PENDING_ANSWER_MIN:
        state.location = state.detected_location = valor
        logger.info(f"[CORE][EX9B-4] origen por Jev: {valor!r} ({jev['confidence']:.2f})")
        return True
    return False


def _hotel_por_la_ia(state: ConversationState, message: str, ia: dict) -> bool:
    """El hotel en la respuesta corta ("¿en qué hotel o isla te hospedas?"), según el extractor: el nombre tal como lo
    escribe, con su cita; si es del catálogo de las islas (la lista cerrada que guarda `_conservar_hotel`), su id y su
    isla. Si el extractor no trae hotel, el del catálogo que nombre el mensaje ("en el Ubuntu"; "en isla grande" da la
    isla). Sin hotel, "por confirmar" como hoy (lo coordina el asesor y no se pregunta en bucle). Nunca se guarda el
    mensaje entero como hotel."""
    hotel = ((ia.get("extractor") or {}).get("hotel") or "").strip()
    del_catalogo, isla = _lugar_del_catalogo(hotel or message)
    nombre = del_catalogo or hotel
    if isla and not state.detected_island:
        state.island = state.detected_island = isla
    if not nombre:
        marker = "por confirmar" if state.language == "es" else "to be confirmed"
        state.hotel = state.detected_hotel = marker
        if not state.island:
            state.island = marker
        logger.info(f"[CORE][EX9B-4] la respuesta no trae hotel (extractor: {hotel!r}, isla {isla!r}): por confirmar")
        return True
    state.hotel = state.detected_hotel = nombre
    if not state.island:
        state.island = nombre
    logger.info(f"[CORE][EX9B-4] hotel por el extractor: {nombre!r} (isla {isla!r})")
    return True


def _cantidad_por_la_ia(state: ConversationState, message: str, ia: dict) -> bool:
    """El total del grupo en la respuesta corta, según el extractor (`group_size`: "solo yo" = 1, "somos 4" = 4). Si no lo
    lee, no se resuelve aquí: la red anti-bucle pregunta al resolutor LLM con su guarda de magnitudes."""
    n = (ia.get("extractor") or {}).get("group_size")
    if isinstance(n, int) and not isinstance(n, bool) and n > 0:
        logger.info(f"[CORE][EX9B-4] total del grupo por el extractor: {n}")
        return _apply_group_total(state, n)
    return False


def _word_ages(message: str) -> list[int]:
    """Edades escritas en palabra, en orden de aparición ("cinco y siete" ->
    [5, 7]). Vacío si no hay ninguna. Reusa el mapa canónico `AGE_WORDS` de
    intent_detector (mismo vocabulario que el gate de elegibilidad)."""
    return [AGE_WORDS[t] for t in re.findall(r"[a-záéíóúñ]+", message.lower())
            if t in AGE_WORDS]


# ─── COMPRENDER ───

def _apply_short_answer(state: ConversationState, message: str, ia: dict | None = None) -> bool:
    """Contextual slot carryover: interpreta el mensaje como respuesta al slot
    pendiente. Devuelve True si lo resolvió. `ia` (ex-9b paso 4, `_lectura_de_la_ia`): con ella, el origen, el hotel y
    el total los lee la IA; sin ella (formato o la IA calla), el regex de siempre."""
    slot = state.core_pending_slot
    if not slot:
        return False
    if ia is not None and slot in _RESPUESTA_LEIDA_POR_LA_IA:
        lector = {SLOT_LOCATION: _origen_por_la_ia, SLOT_HOTEL: _hotel_por_la_ia, SLOT_QTY: _cantidad_por_la_ia}[slot]
        return lector(state, message, ia)
    # Escribir el titulo de un boton de la pregunta es pulsarlo (hallazgo G, 2026-09-15):
    # "seguimos siendo 2" tecleado no es un numero suelto ni un total que lea el detector.
    button = _button_value(state, message)
    if button is not None:
        message = button
    msg = message.strip().lower()

    if slot == SLOT_ACTIVITY and state.suggested_activity:
        # u3-5: "si" / "vale" a la recomendacion del minicurso la confirma. Nombrar otra actividad
        # sigue el camino normal (extraccion).
        first = next(iter(_words(message)), "")
        if is_affirmative(first) or is_agree(first):
            from src.agents import supervisor  # lazy

            confirmed = DetectedIntent()
            confirmed.activity = state.suggested_activity
            confirmed.detected_fields = ["activity"]
            state.suggested_activity = None
            supervisor._apply_detected_intent(confirmed, state, message)
            return True

    if slot == SLOT_CERTIFICATION:
        if is_affirmative(msg) or msg == "1":
            state.is_certified = state.detected_is_certified = True
            return True
        if is_negative(msg) or msg == "2":
            state.is_certified = state.detected_is_certified = False
            return True
        return False
    if slot == SLOT_LOCATION:
        # Auditoría 2026-08-26 (batería sintética contra PRE, portado de
        # pre_gadea v0.21.2): `_ISLAND_RE`/`_CARTAGENA_RE` tenían "2"/"1"
        # como alternativas del regex — matchean CUALQUIER mensaje que
        # contenga ese dígito en cualquier parte ("somos 2" respondiendo a
        # la pregunta de CANTIDAD, no de ubicación, resolvía la ubicación a
        # "island" sin que nadie lo dijera). El atajo "1"/"2" (mismo patrón
        # que is_certified/nationality/safety) solo tiene sentido si es la
        # respuesta COMPLETA, no una cifra suelta dentro de otra frase.
        place = {"1": "cartagena", "2": "island"}.get(msg) or _departure_place(msg)
        if place:
            state.location = state.detected_location = place
            return True
        # Deferral ("no sé/da igual/recomiéndame") → Cartagena (salida más
        # común). Sin esto, el regex fallaba y se re-preguntaba en bucle.
        # Solo si el mensaje no dice nada más (2026-09-15): "no sé si hacer el
        # minicurso o el snorkel" o "me interesa el curso PADI, no se bucear" con
        # la ubicación pendiente fijaban Cartagena sin que nadie la eligiera, y
        # además saltaban la comparación de opciones. Mismo principio que la
        # verificación del resolutor LLM ("si este turno habla de otra cosa, no
        # contestaba la ubicación"), con los campos del detector.
        other_fields = [f for f in _detector.detect(message, state).detected_fields if f != "language"]
        # Y la duda tiene que ser la respuesta entera (2026-09-15): quitadas sus frases,
        # como mucho quedan 4 palabras ("lo que tu me recomiendes" deja "lo que tu me").
        # "que solo nos acompañe en la lancha, no se mete al agua" casaba el "no se"
        # reflexivo y fijaba Cartagena; le quedan 9 palabras de contenido propio.
        leftover = re.findall(r"[a-záéíóúñü]+", _LOCATION_DEFER_RE.sub(" ", msg))
        if _LOCATION_DEFER_RE.search(msg) and not other_fields and len(leftover) <= 4:
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
    if slot == SLOT_CONFIRM_CORRECTION:
        # Se lee la primera palabra: "sí, cámbialo", "no, lo de antes".
        first = next(iter(_words(message)), "")
        if is_affirmative(first) or is_agree(first):
            return _accept_pending_correction(state, message)
        if is_negative(first):
            state.pending_correction = None
            return True
        return False
    if slot == SLOT_QTY:
        n = _quantity_answer(state, message)
        if n is not None and n > 0:
            return _apply_group_total(state, n)
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
        n = _quantity_answer(state, message)
        if n is not None and n > 0 and act:
            if state.pending_split_total:
                _assign_split_share(state, act, n)
            else:
                _merge_companion_activity(state, act, n)
            state.pending_companion_activity = None
            return True
        return False
    if slot == SLOT_COMPANION_ACTIVITY:
        # Respuesta a la recomendación para el acompañante: el valor de un botón,
        # el número de la opción o su nombre exacto. Por palabra clave se sigue
        # aceptando snorkel/minicurso ("quiere bucear" = minicurso, regla de
        # negocio). Si no elige UNA sola opción, no se adivina.
        options = _companion_activity_options(state)
        chosen = msg if msg in options else None
        if chosen is None and state.detected_duration is not None and msg.isdigit() and 1 <= int(msg) <= len(options):
            chosen = options[int(msg) - 1]
        if chosen is None:
            chosen = next(
                (o for o in options if msg in {dom.label(o, "es").lower(), dom.label(o, "en").lower()}),
                None,
            )
        if chosen is None:
            mentioned = set(_mentioned_product_activities(message))
            candidates = set()
            if "snorkel" in mentioned:
                candidates.add("snorkel")
            if "minicourse" in mentioned or "certified_diving" in mentioned:
                candidates.add("minicourse")
            if len(candidates) == 1:
                chosen = next(iter(candidates))
        if chosen is not None:
            state.pending_companion_activity = chosen
            state.needs_companion_activity = False
            return True
        # Primer paso (aún sin duración): "un día"/"varios días", botón o 1/2. Con el
        # dato se vuelve a preguntar, ahora con las recomendaciones.
        if state.detected_duration is None:
            duration = {"1": "single_day", "2": "multi_day"}.get(msg, msg)
            if duration not in ("single_day", "multi_day") and ia is not None:
                # ex-9b paso 6 (`duracion_por_extractor`): la respuesta libre la lee el extractor (días de buceo o, si
                # no, la estancia); el regex de siempre solo si la IA calla.
                from src.agents.nucleo.extractor import duracion_del_extractor  # lazy

                duration, de_buceo = duracion_del_extractor(ia.get("extractor"), state)
                if duration is not None and de_buceo:
                    state.duracion_de_buceo = True
            elif duration not in ("single_day", "multi_day"):
                duration = _detector.detect(message, state).duration
            if duration in ("single_day", "multi_day"):
                state.detected_duration = duration
                state.needs_companion_activity = True
                return True
        return False
    if slot == SLOT_CERT_OR_COURSE:
        chosen = {"1": "already_certified", "2": "wants_course"}.get(msg, msg)
        return _apply_cert_or_course(state, chosen)
    if slot == SLOT_COURSE_LEVEL:
        # Respuesta exacta: el valor de un boton (id del registro), el numero de la
        # opcion como mensaje completo, o el nombre exacto de la opcion. Cualquier
        # otra forma de decirlo la interpreta el resolutor LLM (red anti-bucle).
        options = _course_level_options(state)
        chosen = msg if msg in options else None
        if chosen is None and msg.isdigit() and 1 <= int(msg) <= len(options):
            chosen = options[int(msg) - 1]
        if chosen is None:
            chosen = next(
                (o for o in options if msg in {dom.label(o, "es").lower(), dom.label(o, "en").lower()}),
                None,
            )
        if chosen is not None:
            _set_concrete_activity(state, chosen)
            return True
        return False
    if slot == SLOT_AGES:
        if ia is not None:
            # ex-9b paso 6 (`edades_por_extractor`): las edades las lee el extractor (cifra validada en su cita); sin
            # edades no se resuelve aquí (las verá `_understand`).
            ages = list((ia.get("extractor") or {}).get("edades") or [])
            if ages:
                state.detected_ages = sorted(set((state.detected_ages or []) + ages))
                return True
            return False
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


def _looks_like_deliberation(message: str) -> bool:
    return bool(_DELIBERATION_RE.search(message))


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
    names = (
        [dom.text(o, "name_in_sentence", lang, default=o) for o in offerings]
        or [dom.text("snorkel", "name_in_sentence", lang)]
    )
    joined = (" y ".join(names) if lang == "es" else " and ".join(names))
    return (f"¿Qué diferencia hay entre {joined}? ¿Cuál me recomiendas?"
            if lang == "es" else
            f"What's the difference between {joined}? Which one do you recommend?")


# Composer determinista de comparación (2026-07-24): cuando RAG no tiene en el
# KB un chunk que compare ESE par (medido en vivo: "buceo vs snorkel" cae al
# fallback de asesor 4/4, consistente — no flaky), se arma la comparación desde
# el catálogo SERVICES. Los HECHOS (precio, certificación, nombre) salen del
# catálogo — nunca se inventan; solo el descriptor de tono es copy curado, igual
# que el menú de actividades. Nunca cae al asesor. El servicio, el nombre y la
# descripcion de cada oferta salen del registro de actividades (F3b); una
# generica (padi_course) se compara como su nivel por defecto (Open Water).


def _compose_comparison(offerings: list[str], lang: str) -> str:
    """Comparación lado-a-lado desde el catálogo, sin depender de RAG. Precio y
    requisito de certificación salen de SERVICES (nunca inventados)."""
    from src.flows.catalog import SERVICES
    rows = []
    for o in offerings:
        svc = SERVICES.get(dom.base_service_id(dom.resolved_activity_id(o)) or "", {})
        name = (
            (svc.get("name_es") if lang == "es" else svc.get("name_en"))
            or dom.text(o, "name_in_sentence", lang, default=o)
        )
        if lang == "es":
            cert_line = "Requiere certificación previa" if svc.get("requires_cert") else "Sin certificación previa"
        else:
            cert_line = "Requires prior certification" if svc.get("requires_cert") else "No certification needed"
        row = f"🤿 *{name}*\n• {cert_line}\n• {dom.text(o, 'pitch', lang, default='')}"
        price = svc.get("price_usd")
        if price:
            row += (f"\n• Desde {int(round(price))} USD por persona"
                    if lang == "es" else f"\n• From {int(round(price))} USD per person")
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
    # ex-9b paso 5: si la IA ha contestado este turno, manda `comparing_options`; la frase de duda solo si la IA calla.
    # Antes la señal pasaba por unos vetos hechos para el router LLM de antes (una cifra, cada oferta con su sujeto, una
    # oferta negada, "quiero"): Jev ya separa el reparto de la duda. Banco con la config de PRE: con los vetos 14/16,
    # solo Jev 15/16 ("somos 3 y no tenemos claro si hacer snorkel o el minicurso": el veto de la cifra). Con la IA
    # callada no hay `comparing_options` que vetar: los vetos se quitaron en la limpieza ex9b.
    if routing_signals:
        obj = routing_signals.get("comparing_options")
        return bool(obj.get("comparing")) if isinstance(obj, dict) else False
    return _looks_like_deliberation(message)


def _accept_pending_correction(state: ConversationState, message: str) -> bool:
    """El cliente confirma: los valores pasan por el MISMO camino que un turno normal
    (invariante del reparto, personas sin decidir y escritura), marcados como
    sobrescribibles. No hay un segundo escritor del estado."""
    from src.agents import supervisor  # lazy

    pending = state.pending_correction or {}
    state.pending_correction = None
    intent = DetectedIntent()
    for field, value in pending.items():
        setattr(intent, field, dict(value) if isinstance(value, dict) else value)
        intent.detected_fields.append(field)
        intent.overwrite.append(field)
    supervisor.enforce_group_allocation_consistency(intent, state, message)
    _take_undecided_members(intent, state)
    supervisor._apply_detected_intent(intent, state, message)
    return True


def _button_value(state: ConversationState, message: str) -> str | None:
    """Valor del boton de la pregunta pendiente cuyo titulo es exactamente lo que se
    escribio (sin emojis, signos ni tildes): "✅ Ya la tenemos", "Seguimos siendo 2"."""
    typed = strip_accents(" ".join(_words(message)))
    for option in state.quick_replies or []:
        if typed and typed == strip_accents(" ".join(_words(str(option.get("title", ""))))):
            return str(option.get("value"))
    return None


def _quantity_answer(state: ConversationState, message: str) -> int | None:
    """Respuesta determinista a "¿cuantas personas?" / "¿cuantos serian para X?"
    (hallazgo G, 2026-09-15).

    El parser de cantidad cogia el primer numero de cualquier mensaje: con la pregunta
    pendiente, "hace 3 años que no buceo", "mi hijo tiene 9 años", "llegamos el 12" o "a
    las 8" fijaban 3, 9, 12 u 8 personas (y en "¿cuantos para snorkel?" se sumaban). Sin
    lista de unidades: solo cuenta como respuesta lo que ES la cantidad (un unico
    elemento: "4", "dos", "6+") o lo que el detector ya lee como total del grupo ("somos
    4", "4 personas", "we are 4"), la misma fuente que la extraccion. Lo demas no se
    resuelve aqui: la pregunta del total la interpreta el resolutor LLM con su contexto y
    su guarda de anclaje; la de "¿cuantos para X?" se vuelve a hacer."""
    if len(_words(message)) == 1:
        n = cart_render.parse_quantity(message)
    else:
        n = _detector.detect(message, state).group_size
    return n if isinstance(n, int) and n > 0 else None


def _with_main_rest(allocation: dict, main_activity, total, taken: int = 0) -> dict:
    """El resto del grupo hace la actividad principal: con el total ya sabido, su cifra
    es aritmetica y no necesita respaldo en el texto. `taken` son personas del total que
    no estan en el reparto (las `undecided`). Punto unico (2026-09-15): lo usan las
    personas sin decidir, la guarda de cifras y las respuestas a "¿cuantos para X?"."""
    others = sum(v for k, v in allocation.items() if k != main_activity)
    rest = (total or 0) - others - taken
    result = {k: v for k, v in allocation.items() if k != main_activity}
    if main_activity and rest > 0:
        result[main_activity] = rest
    return result


def _assign_split_share(state: ConversationState, activity: str, qty: int) -> None:
    """Respuesta a "¿cuantos serian para X?" cuando X es un tramo del grupo YA contado
    (hallazgo H, 2026-09-15). Antes se sumaba encima: con 3 sabidos, "uno" dejaba 4 y el
    siguiente tramo 5. Ahora se reparte dentro del total; al contestar el ultimo tramo, la
    actividad principal se queda con el resto. Si las respuestas superan el total, se
    pregunta si se suma alguien (la pregunta de 7a)."""
    total = state.pending_split_total
    allocation = dict(state.detected_group_allocation or {})
    allocation[activity] = allocation.get(activity, 0) + qty
    main = state.detected_activity
    if sum(v for k, v in allocation.items() if k != main) > total:
        state.pending_split_total = None
        state.pending_companion_queue = []
        state.pending_companion_in_group = {"activity": activity, "qty": qty}
        return
    if not state.pending_companion_queue:
        state.pending_split_total = None
        allocation = _with_main_rest(allocation, main, total)
    state.detected_group_allocation = allocation
    state.detected_group_size = total
    logger.info(f"[CORE] tramo {activity} x{qty} dentro del total {total} -> alloc={allocation}")


def sembrar_senales_del_turno(state: ConversationState, routing_signals: dict) -> None:
    """Lo que Jev contestó en ESTE turno (misma llamada del router), guardado en el estado para las puertas
    de la extracción. Función aparte (ex-0, 12-oct) para que el banco de extracción
    (`scripts.run_extraction_eval --banco ex0`) siembre el turno EXACTAMENTE igual que producción."""
    # u3-4/u3-5: lo que Jev contestó en ESTE turno sobre si el cliente AFIRMA cada dato o solo lo
    # nombra. Se guarda en CADA turno (y se vacía si no hay señal), así nunca se usa la de un turno
    # anterior. Lo usan la puerta del turno con pregunta (`_question_turn_fields`), el relleno con
    # puerta y el filtro de contradicciones (`_route_contradictions`). Un campo AUSENTE (Jev apagado o
    # Jev falló) significa "no lo sé" -> la conducta de hoy; `False`, "no lo afirma".
    state._answer_affirms = {f: routing_signals[sig] for f, sig in _AFFIRMS_SIGNAL_FIELDS if sig in routing_signals}
    # u3-5 paso 2: ¿el mensaje corrige un dato ya dado? (Jev, misma llamada). Se renueva cada turno.
    state._jev_corrects = routing_signals.get("corrects")
    # Paso 5: ¿pide que le recordemos algo que él dijo? (Jev, misma llamada). Se renueva cada turno.
    state._jev_asks_recall = routing_signals.get("asks_recall")
    # u3-6: probabilidad de Jev de que el mensaje meta a otra persona en la reserva (filtro previo del
    # LLM de señales). Ausente = no lo sabemos -> se llama al LLM como hoy.
    state._jev_companion = routing_signals.get("companion_joins")
    # s4-26: probabilidad de Jev de que el mensaje SUME a una persona nueva (no a alguien ya contado). Ausente = no lo
    # sabemos.
    state._jev_adds_person = routing_signals.get("adds_person")
    # s4-28: dónde está / desde dónde sale el cliente según Jev ({choice, confidence}); ausente = no lo sabemos.
    state._jev_lugar = routing_signals.get("customer_place")


async def _routing_phase(
    state: ConversationState, message: str, routing_signals: dict, greeting: str,
) -> str | dict:
    """Fase 3.3d — routing interno del turno de booking (carryover → pregunta/
    recall → deliberación), extraído de `_body_phase`. Toma los snapshots
    `prev_*` (ANTES de que `_apply_short_answer` mute el estado) + `resolved_
    short`, y ejecuta los gates de early-return. Si un gate resuelve el turno
    devuelve la RESPUESTA (str); si no, devuelve el `carry` (dict con los
    `prev_*`/`resolved_short`) para `_extract_close_phase`. Lo llama la cascada
    (vía `maybe_handle_turn`) y el nodo `routing` del subgrafo — misma fuente de
    verdad, equivalencia por construcción."""

    # Confirmación deíctica de un paquete multi-día ("quiero este paquete")
    # ANTES de tomar snapshots/decidir la ruta del turno -- corre pase lo que
    # pase con el "?" (ver `_maybe_apply_confirmed_package`), para que un
    # mensaje como "...que podria hacer esos dos dias?" no deje el carrito
    # pegado al paquete de 1 día que se armó antes de esta conversación.
    await _paquete_confirmado(state, message)

    sembrar_senales_del_turno(state, routing_signals)

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
    # Snapshots de los OTROS campos que un slot puede resolver — los consume
    # `_turn_answered_a_different_slot` (red anti-bucle de Fase C, ver alli).
    prev_is_colombian = state.is_colombian
    prev_location = state.location or state.detected_location
    has_qmark = "?" in message

    resolved_short = False
    # ex-9b paso 4: la respuesta corta que resolvió la IA no se salta `_understand` aunque
    # tenga 12 caracteres o menos (el extractor ya la leyó entera: "el hilton" al origen trae también el hotel).
    respuesta_por_la_ia = False
    if prev_pending and not has_qmark:
        ia = await _lectura_de_la_ia(state, message, routing_signals, prev_pending)
        resolved_short = _apply_short_answer(state, message, ia=ia)
        respuesta_por_la_ia = resolved_short and ia is not None
    if prev_pending == SLOT_CONFIRM_CORRECTION and not resolved_short:
        # u3-5 paso 1b: la confirmación se pregunta UNA vez. Un "sí" al principio vale aunque el
        # mensaje siga con una pregunta ("sí, ¿y cuánto es?"); cualquier otra cosa = no confirmado:
        # se queda lo guardado y el turno sigue normal (el mensaje puede traer otra cosa).
        first = next(iter(_words(message)), "")
        if state.pending_correction and (is_affirmative(first) or is_agree(first)):
            resolved_short = _accept_pending_correction(state, message)
        elif state.pending_correction:
            logger.info(f"[CORE] correccion no confirmada, se queda lo guardado: {sorted(state.pending_correction)}")
            state.pending_correction = None

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
    if (
        resolved_short and prev_pending == SLOT_COMPANION_ACTIVITY and state.pending_companion_activity
        and not _merge_pending_undecided(state)
    ):
        response = greeting + ask_slot(state, SLOT_COMPANION_QTY)
        state.history.append({"role": "assistant", "content": response})
        return response

    # "?" explícito → SIEMPRE una pregunta real. Antes de RAG, comprobar si es
    # un pedido de RECORDAR un dato ya dado ("¿cuántas personas somos, me lo
    # recuerdas?") — se responde con el valor REAL del estado, determinista,
    # nunca con lo que el LLM "cree" que se dijo (hallazgo en vivo
    # 2026-07-22: el bot no sabía recuperar sus propios datos y ofrecía
    # escalar a un asesor para algo que ya tenía).
    if not resolved_short and has_qmark and not _is_greeting_only(message):
        # u3-4: la respuesta se lanza ANTES de mirar si es un "¿me recuerdas...?", para que
        # corra a la vez que esa comprobación y que la extracción.
        _maybe_launch_answer(state, message, routing_signals)
        # u3-6: aqui solo se usa `recall_field`; si Jev ya dice que no pide recordar, la llamada sobra.
        if _jev_says_no_recall(state):
            logger.info("[CORE][U3-6] recordar sin LLM (Jev: no pide recordar)")
            signals = {}
        else:
            signals = await detect_special_signals(message, history=state.history, lang=state.language)
        recalled = None
        if signals.get("recall_field") and not _jev_says_no_recall(state):
            recalled = _recall_answer(state, signals["recall_field"])
        if recalled:
            cancel_pending_answer(state)
            response = recalled
            if prev_pending:
                response += "\n\n" + ask_slot(state, prev_pending, reasking=True)
            response = greeting + response
            state.history.append({"role": "assistant", "content": response})
            return response
        if not _has_pending_answer(state):
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
    if (
        not resolved_short and not _has_pending_answer(state)
        and _is_deliberation_between_options(message, routing_signals)
    ):
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
        if _is_rag_fallback(rag):
            rag = _compose_comparison(offerings, state.language)
            state.core_pending_slot = SLOT_ACTIVITY
            state.quick_replies = []
            logger.info(f"[CORE] deliberation RAG fallback -> catalog compare offerings={offerings}")
        answer = greeting + rag
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # u3-4: una pregunta sin "?" (regex o Jev) también se contesta en paralelo.
    _maybe_launch_answer(state, message, routing_signals)

    # Ningún gate de routing resolvió el turno → pasar a extracción con el carry
    # (los snapshots `prev_*` tomados ANTES de `_apply_short_answer` + `resolved_
    # short`, que la extracción usa para detectar qué cambió este turno).
    return {
        "resolved_short": resolved_short,
        "respuesta_por_la_ia": respuesta_por_la_ia,
        "prev_pending": prev_pending,
        "prev_cart_types": prev_cart_types,
        "prev_main_activity": prev_main_activity,
        "prev_main_service_id": prev_main_service_id,
        "prev_main_is_certified": prev_main_is_certified,
        "prev_main_last_dive": prev_main_last_dive,
        "prev_main_refresher": prev_main_refresher,
        "prev_group_size": prev_group_size,
        "prev_group_allocation": prev_group_allocation,
        "prev_is_colombian": prev_is_colombian,
        "prev_location": prev_location,
    }
