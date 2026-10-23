"""Nodo `setup` del subgrafo de la reserva: `_setup_phase` (idioma, saludo, nombre del cliente) y lo que solo usa él.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import asyncio
import logging
import re

from src.agents.conversational_core import (
    _NAME_STOPWORDS,
    _greeting,
    _jev_sin_nada_que_apuntar,
    _maybe_capture_notes,
    _notes_snapshot,
    _otro_idioma_en_ingles,
)
from src.agents.nucleo.slotfill_close import _maybe_launch_ack
from src.flows.state import ConversationState, Step

logger = logging.getLogger("uvicorn.error")


# Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 4, portado de
# pre_gadea v0.21.4): una petición EXPLÍCITA de cambiar de idioma a mitad de
# conversación ("actually can we continue in english") se ignoraba por
# completo — no había ningún mecanismo que la detectara (la reclasificación
# por-mensaje del intent_detector solo corre en el PRIMER turno, antes de
# que `detected_language` quede fijado; después, nada vuelve a mirar el
# idioma). Lista deliberadamente pequeña y determinista (no LLM) — son
# peticiones explícitas, no ambiguas, no hace falta red de precisión.
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


def _idioma_pedido(state: ConversationState, message: str, routing_signals: dict) -> str | None:
    """El idioma al que el cliente pide pasar la conversación ("en"/"es"), o None si no lo pide o ya es ese. ex-9b paso
    5: si Jev contesta (`cambia_idioma`), manda Jev; los regex de siempre solo si Jev calla. Los regex pasaban al
    inglés con "¿el curso es en inglés?" y al español con "I don't speak spanish"."""
    from src.agents.jev_router import CAMBIA_IDIOMA

    if CAMBIA_IDIOMA in routing_signals:
        pedido = {"english": "en", "spanish": "es"}.get(routing_signals[CAMBIA_IDIOMA])
        return pedido if pedido and pedido != state.language else None
    if _SWITCH_TO_EN_RE.search(message) and state.language != "en":
        return "en"
    if _SWITCH_TO_ES_RE.search(message) and state.language != "es":
        return "es"
    return None


# ─── Persona: saludo del primer turno (Coral, cálida, sin "asistente"/"bot") ───

# Captura del nombre del cliente DEL PROPIO MENSAJE ("me llamo Ana"). Camino rápido determinista; el extractor lo
# rellena también. El nombre de WhatsApp (sender['name']) queda diferido hasta que el canal exista. Se captura en
# minúscula (móvil) y se Title-Casea. Primera captura gana (el nombre no cambia a mitad de conversación).
# 13-oct (`nombre_por_extractor`, promocionado): la regex solo captura las formas SIN ambigüedad ("me llamo",
# "mi nombre es", "my name is"); "soy X" lo decide el extractor con su cita (`_nombre_del_extractor`): "yo soy gringo"
# saludaba "¡Hola, Gringo!" y el nombre se arrastraba a los acuses y al resumen para el asesor.
_NAME_TRIGGER_SIN_SOY_RE = re.compile(
    r"\b(?:me\s+llamo|mi\s+nombre\s+es|my\s+name\s+is)\s+([a-záéíóúñ]{2,20})\b",
    re.IGNORECASE,
)


def _capture_client_name(state: ConversationState, message: str) -> None:
    if state.client_name:
        return
    m = _NAME_TRIGGER_SIN_SOY_RE.search(message)
    if not m:
        return
    word = m.group(1)
    if word.lower() in _NAME_STOPWORDS:
        return
    state.client_name = word[:1].upper() + word[1:].lower()
    logger.info(f"[CORE] captured client name -> {state.client_name}")


async def _nombre_del_mensaje(state: ConversationState, message: str) -> None:
    """El nombre con que se presenta el cliente. ex-9b paso 4 (con `nombre_por_extractor`): la regex de "me llamo X"
    iba antes que el extractor y ganaba; ahora, si la ve, manda el `nombre` del extractor (aquí mismo, para que el
    saludo del primer turno lo lleve; la lectura no se gasta) y la regex solo si el extractor falla. Sin la regex, el
    nombre lo pone el extractor más adelante en el turno, como hoy."""
    if state.client_name:
        return
    if _NAME_TRIGGER_SIN_SOY_RE.search(message):
        from src.agents.nucleo.extractor import _nombre_del_extractor, lectura_del_extractor  # lazy

        datos = await lectura_del_extractor(state, message)
        if datos is not None:
            _nombre_del_extractor(state, datos, message)
            if not state.client_name:
                logger.info("[CORE][EX9B-4] la regex veía un nombre y el extractor no: sin nombre")
            return
        logger.info("[CORE][EX9B-4] el extractor falló: el nombre lo lee la regex de siempre")
    _capture_client_name(state, message)


async def _idioma_del_extractor(state: ConversationState, message: str) -> str | None:
    """CAL-E4 (flag `idioma_del_extractor`): el idioma del PRIMER turno según el extractor, que ya va lanzado con el
    enrutador. "es" o "en" tal cual; cualquier otro idioma, inglés (regla G-10 de Gadea). None si el flag está apagado,
    el mensaje es muy corto (una o dos palabras no dicen el idioma) o la extracción no está: entonces, la cadena de
    siempre."""
    if len((message or "").split()) < 3:
        return None
    tarea = getattr(state, "_extraccion_adelantada", None)
    if tarea is None:
        return None
    try:
        datos = await tarea
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 — sin dato, la cadena de siempre
        return None
    idioma = (datos or {}).get("idioma")
    if not idioma:
        return None
    elegido = idioma if idioma in ("es", "en") else "en"
    logger.info(f"[CORE][IDIOMA] el extractor dice {idioma!r}: la conversación va en {elegido!r}")
    return elegido


async def idioma_de_apertura(state: ConversationState, message: str) -> None:
    """El idioma del PRIMER mensaje: lo fija en `state.language` y `state.detected_language` y aplica G-10 (otro
    idioma → inglés). La reserva lo llama desde `_setup_phase`; con `idioma_unico_de_apertura` (gen-5), el router del
    grafo, una vez por conversación y antes de cualquier ruta, para que lo sensible, el contacto, la edad o el buceo
    adaptado contesten en el mismo idioma que la reserva."""
    from src.agents import supervisor  # lazy
    from src.agents.language_detector import detect_language_llm
    from src.flows.catalog import _detect_language_from_text
    # Cadena: heurística de stopwords → fallback LLM (solo si la heurística no
    # detecta nada; evita preguntar "Español/English" ante un mensaje que
    # revela el idioma con palabras fuera de la lista curada) → heurística de
    # hints. El `or` corta: el LLM solo se llama si la primera devuelve None.
    # CAL-E4 (16-oct, flag `idioma_del_extractor`): la heurística de palabras vacías decide PRIMERO y corta la
    # cadena, así que un mensaje en portugués con muchas palabras iguales al español ("Busco el seguinte: Vamos en
    # família a Cartagena") se contestaba en español (cal-12). El idioma lo dice el EXTRACTOR, que ya va lanzado en
    # paralelo con el enrutador (campo `idioma`, G-10): no cuesta una llamada más y no es una lista de palabras.
    state.language = (
        await _idioma_del_extractor(state, message)
        or _detect_language_from_text(message)
        or await detect_language_llm(message)
        or supervisor._infer_language(message, state.language)
    )
    # Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 4,
    # portado de pre_gadea v0.21.4): esta detección de apertura
    # (heurística → LLM → hints, la más fiable) solo fijaba
    # `state.language`, nunca `state.detected_language` —
    # `_apply_detected_intent` (que corre en CADA turno vía
    # `_understand()`) sobreescribe `state.language` con su propia
    # clasificación más simple, por-mensaje, mientras
    # `state.detected_language` siga vacío. Resultado: en el PRIMER
    # turno, el saludo se renderizaba ya en el idioma correcto pero
    # segundos después, dentro del mismo turno, la pregunta de slot
    # salía en otro idioma — la clasificación por-mensaje del
    # intent_detector decidía distinto para un mensaje con palabras
    # mezcladas. Fijar `detected_language` aquí también evita ese
    # pisado sobre la detección ya resuelta y más fiable.
    state.detected_language = state.language
    await _otro_idioma_en_ingles(state, message=message)


async def _setup_phase(
    state: ConversationState, message: str, routing_signals: dict,
) -> tuple[str, bool] | None:
    """Fase 3.3b — setup del turno de booking, extraído de `maybe_handle_turn`.

    Hace lo que TODO el resto del turno da por hecho, y por eso va primero: (1)
    descarta el escalado por keyword/`wants_human` (→ None, lo resuelve la
    cascada); (2) en el primer turno infiere el idioma y arma el saludo; (3)
    captura el nombre; (4) **añade el mensaje del usuario al historial** (las
    notas y el RAG lo leen ya con el mensaje dentro); (5) captura notas.
    Devuelve `(greeting, first_turn)`, o `None` para escalado-keyword. Es el
    primer nodo del subgrafo del booking (§3.3) y también lo llama la cascada
    vía `maybe_handle_turn` — misma fuente de verdad, equivalencia por
    construcción."""
    from src.agents import supervisor  # lazy

    msg_lower = message.strip().lower()
    if (supervisor.regex_decide(routing_signals) and supervisor._matches_escalation_keyword(msg_lower)) or (
            routing_signals.get("wants_human")):
        return None
    # (Fase 4, decisión owner 2026-07-28) "menú"/"volver"/"back" = MENSAJE NORMAL:
    # el núcleo los trata como texto conversacional (re-orienta a la reserva) en
    # vez de resetear a un menú de botones que ya no existe.

    # Primer mensaje: inferir idioma como hace la entrada legacy, y marcar que
    # toca presentarse (Coral + Diving Planet, tono cercano — regla de persona).
    first_turn = state.step in (Step.WELCOME, Step.LANGUAGE)
    if first_turn:
        # gen-5: el router ya lo decidió en este mismo turno (mismo mensaje y misma cadena); no se vuelve a decidir.
        if not state.detected_language:
            await idioma_de_apertura(state, message)
        state.step = Step.FREE_TEXT
        state.quick_replies = []
    elif pedido := _idioma_pedido(state, message, routing_signals):
        # Petición EXPLÍCITA de cambiar de idioma a mitad de conversación
        # (auditoría 2026-08-26) — fuera del primer turno nada más vuelve a
        # mirar el idioma (a propósito, para no reclasificar cada mensaje),
        # así que sin este chequeo dedicado la petición se ignoraba del
        # todo. `elif` porque en el primer turno la detección de arriba ya
        # decide bien.
        state.language = state.detected_language = pedido
    await _nombre_del_mensaje(state, message)
    greeting = _greeting(state) if first_turn else ""

    state.history.append({"role": "user", "content": message})

    # (Fase C) Capturar hechos abiertos que un asesor querría recordar
    # (lesión/médico, accesibilidad, ocasión especial, restricciones) →
    # remembered_facts["notes"]. Corre en cualquier mensaje sustantivo, sin
    # afectar el enrutado del turno (solo escribe estado); un mensaje puede
    # traer una nota junto a una pregunta, una respuesta de slot o una reserva.
    #
    # l1-4: justo por eso —solo escribe estado— puede salir del turno. Con
    # `defer_background_tasks` la llama el canal tras ENVIAR la respuesta
    # (ver `supervisor.run_deferred_turn_tasks`), y el cliente no la espera.
    # rag-5: si Jev está seguro de que no hay nada que apuntar, no se llama al extractor.
    if not _jev_sin_nada_que_apuntar(routing_signals):
        # l1-4: se lanza y NO se espera aquí. La espera va justo antes de quien las
        # usa (`_build_extra_context`, contexto del RAG) y, como red de seguridad,
        # al cerrar el turno en `supervisor.route_message` — antes del `save_state`.
        # La tarea se cuelga del `state` como atributo NO declarado: viaja por
        # referencia entre los nodos del grafo (nada de ContextVars, que es donde
        # se perdió el contexto de traza en m0-1) y `asdict()` la ignora al
        # serializar, así que nunca llega a Redis.
        # La foto se toma AQUÍ, no dentro de la tarea: la tarea puede no arrancar
        # hasta que el bot ya ha metido su respuesta en el historial (A/B 23-sep).
        state._pending_notes_task = asyncio.create_task(
            _maybe_capture_notes(state, message, snapshot=_notes_snapshot(state))
        )
    if not first_turn:
        _maybe_launch_ack(state, message)
    return greeting, first_turn
