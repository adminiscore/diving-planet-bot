"""El RAG del núcleo y el escritor (lat-9 paso 4, 27-oct; antes en `conversational_core`): contestar una pregunta
en mitad de la reserva y volver al hueco, las entradas del escritor (hechos, pase, plan nombrado, pregunta final), el
RAG adelantado (rag-5) y la respuesta en paralelo (u3-4: «contesta y sigue»). Importa del núcleo las notas, el saludo
y si el turno trae pregunta; el núcleo lo importa al final y lo re-exporta."""

from __future__ import annotations

import asyncio
import logging
import re

from src.agents.conversational_core import (
    _greeting,
    _turn_has_question,
    await_pending_notes,
)
from src.agents.nucleo.huecos import (
    SLOT_ACTIVITY,
    next_missing_slot,
)
from src.agents.nucleo.origen import (
    _PREGUNTA_ORIGEN_RE,
    _answer_already_asks,
    _answer_asks_the_origin,
    _cierra_preguntando_el_origen,
    _es_pregunta_de_origen,
    _fijar_origen_antes_del_precio,
    _puerta_del_origen,
    _sin_la_pregunta_final,
)
from src.agents.nucleo.preguntas import ask_slot
from src.flows.state import (
    ConversationState,
    Step,
)

logger = logging.getLogger("uvicorn.error")


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
    escrita = getattr(state, "_pregunta_del_escritor", None)
    if escrita and pending is not None and not _is_rag_fallback(answer):
        # lat-9 paso 2: el escritor ya cerró con la pregunta fijada al empezar el turno; si la que toca es otra, se cambia.
        pregunta = ask_slot(state, pending, reasking=True)
        if pregunta == escrita and _answer_already_asks(answer):
            return answer
        if _cierra_preguntando_el_origen(state, answer):
            state.quick_replies = []  # la pregunta del turno es la del origen; la de la reserva queda pendiente
            return answer
        return f"{_sin_la_pregunta_final(answer).rstrip()}\n\n{pregunta}"
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
    sin_precio: bool = False, sin_busqueda: bool = False,
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
    if sin_busqueda:  # lat-9 paso 2: el escritor solo (`slotfill_close._sin_dato`)
        entradas["sin_busqueda"] = True
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
    if pregunta := getattr(state, "_pregunta_del_escritor", None):
        entradas["pregunta_final"] = pregunta  # lat-9 paso 2
    return entradas


def fijar_pregunta_del_escritor(state: ConversationState) -> None:
    """lat-9 paso 2 (26-oct): la pregunta de la reserva la escribe el escritor (RAG o redactor) al final de su texto, en
    vez de pegarla el código detrás. Se fija al empezar el turno, antes del RAG adelantado (rag-5), con la pregunta
    pendiente tal como se volvería a hacer, para que la adelantada y la del turno lleven la misma. Si el mensaje cambia
    la pregunta (contesta el dato, cierra la reserva), el cierre lo arregla (`slotfill_close._con_la_pregunta`). Sin
    pregunta pendiente (fuera de la reserva), nada: el escritor contesta como siempre."""
    import copy

    state._pregunta_del_escritor = None
    pendiente = state.core_pending_slot
    if not pendiente or state.step != Step.FREE_TEXT:  # solo con la reserva en marcha (ni el idioma ni el pase)
        return
    state._pregunta_del_escritor = ask_slot(copy.copy(state), pendiente, reasking=True)


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
_PARTES_HUELLA = ("mensaje", "idioma", "historial", "resumen", "origen", "hechos", "pregunta")  # orden de `_huella_rag`


def _huella_rag(message: str, entradas: dict) -> tuple:
    import json

    resumen = _HORA_DEL_RESUMEN.sub("", entradas.get("extra_context") or "")  # la hora cambia de un minuto a otro
    return (message, entradas.get("lang"), json.dumps(entradas.get("history") or [], ensure_ascii=False),
            resumen, entradas.get("origin"), entradas.get("hechos"), entradas.get("pregunta_final"))


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
    if (getattr(state, "_pregunta_del_escritor", None) and not _is_rag_fallback(answer)
            and not _es_pregunta_de_origen(answer)):
        answer = _sin_la_pregunta_final(answer)  # lat-9 paso 2: lo que sigue lo decide el flujo, que va detrás
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
