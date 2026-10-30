"""El grafo esqueleto (Fase 1.3) — StateGraph(BotState).

Ver `docs/agent-arch-design.md` §2 y `docs/multi-agent-refactor-plan.md` §1.3.

Estructura:

    START → router → [conditional edges por route] → {5 nodos de ruta} → END

En la Fase 1 los 5 nodos de ruta son **wrappers finos idénticos**: todos
delegan en `supervisor._shared_turn_handler` (la cascada actual). El grafo NO
cambia comportamiento — solo añade el enrutado por encima y valida la fontanería
(que LangGraph corre en la app, que el router clasifica, que un turno real
produce la misma respuesta que la cascada). En Fases 2-3 el cuerpo de cada nodo
se sustituye por su lógica real, una ruta a la vez (strangler-fig).

El `conv_state` viaja por referencia dentro del BotState; las mutaciones
in-place de la cascada (`state.step`, `state.history`, ...) se propagan al
objeto que tiene el caller — verificado empíricamente antes de escribir esto.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph

from src.agents.booking_agent import booking_node
from src.agents.changes_agent import changes_node
from src.agents.deflection_agent import deflection_node
from src.agents.escalation_agent import escalation_node
from src.agents.info_agent import info_node
from src.agents.jev_router import (
    NUEVO_CASO,
    PIDE_CAMBIOS,
    PIDE_CLIMA,
    PIDE_DESCUENTO,
    PIDE_DISPONIBILIDAD,
    PIDE_EDAD,
    PIDE_ENLACE,
    PIDE_FOTOS,
    PIDE_HORARIO,
    PIDE_HOTELES,
    PIDE_OTRA_COSA,
    PIDE_PAGO,
    PIDE_PRECIO,
    PIDE_QUE_INCLUYE,
    PIDE_REGRESO,
    PIDE_REQUISITOS,
    PIDE_SI_ALCANZA,
    PIDE_UN_DESCUENTO,
)
from src.flows.state import ConversationState, Step
from src.orchestration.router import classify_route
from src.orchestration.state import (
    ALL_ROUTES,
    ROUTE_BOOKING,
    ROUTE_CHANGE,
    ROUTE_DEFLECT,
    ROUTE_INFO,
    ROUTE_SAFETY,
    BotState,
)

logger = logging.getLogger("uvicorn.error")

# ARQ-1b: la señal de Jev de cada intención (src/flows/hechos.INTENCIONES).
_INTENCION_DE_SENAL = {
    "precio": PIDE_PRECIO, "incluye": PIDE_QUE_INCLUYE, "requisitos": PIDE_REQUISITOS, "horario": PIDE_HORARIO,
    "disponibilidad": PIDE_DISPONIBILIDAD, "edad": PIDE_EDAD, "enlace": PIDE_ENLACE,
    "descuento": PIDE_DESCUENTO,  # arq-4b
    "tiempo": PIDE_SI_ALCANZA,  # arq-1v
    "clima": PIDE_CLIMA, "pago": PIDE_PAGO,  # arq-1i
    "hoteles": PIDE_HOTELES, "regreso": PIDE_REGRESO, "fotos": PIDE_FOTOS, "cambios": PIDE_CAMBIOS,  # lat-8
}


# Nodos-agente REALES (Fase 2). Con 2.5 los 5 nodos son reales — ya no queda
# ningún wrapper delegando en la cascada por defecto (`_make_legacy_delegate_node`
# permanece solo como red de resiliencia si se añadiera una ruta nueva sin nodo).
_REAL_NODES = {
    ROUTE_DEFLECT: deflection_node,
    ROUTE_SAFETY: escalation_node,
    ROUTE_CHANGE: changes_node,
    ROUTE_INFO: info_node,
    ROUTE_BOOKING: booking_node,
}


async def _router_node(state: BotState) -> dict:
    """Calcula las señales de routing (1 vez/turno, con el mismo skip de clics
    numéricos que la cascada) y clasifica la ruta. Es el único sitio donde se
    llama a `detect_routing_signals` — el nodo de ruta reutiliza el resultado
    vía `state["signals"]` (evita la doble llamada LLM).

    Se importa `detect_routing_signals` DESDE `supervisor` (no desde
    `escalation`) a propósito: es el binding que los tests parchean
    (`src.agents.supervisor.detect_routing_signals`); hasta s4-1 un solo mock
    cubría así los dos caminos (grafo y cascada).

    **Side-effects pre-router** (§4.bis: el restart de escenario nuevo se
    ejecuta "antes del router"): la cascada, en la cabecera de
    `_shared_turn_handler` y ANTES de cualquier gate, (1) reinicia la memoria si
    el mensaje es un escenario nuevo y (2) marca la detección sticky de niños.
    Como los nodos-agente reales (Fase 2) llaman a sus handlers/al núcleo
    directamente (ya no delegan toda la cascada), estos side-effects se
    reproducen aquí para que los reciban las 5 rutas — si no, se perderían
    (bug real: `kids_mention_detected` no se activaba con el flag on)."""
    from src.agents.supervisor import (
        _detect_kids_mention,
        _is_new_scenario_restart,
        _reset_to_fresh_scenario,
        detect_routing_signals,
    )

    conv = state["conv_state"]
    message = state["message"]

    msg_lower = message.strip().lower()

    async def _senales() -> dict:
        return {} if msg_lower.isdigit() else await detect_routing_signals(
            message, lang=conv.language, pending_slot=conv.core_pending_slot, history=conv.history,
        )

    # Pre-router: restart de escenario nuevo (limpia memoria) → se clasifica
    # sobre el estado fresco, equivalente al reset+recursión de la cascada.
    # ex-9b paso 5: el regex (saludo + presentación + memoria) solo PROPONE. En esos turnos (pocos) se esperan las
    # señales ANTES de borrar y manda Jev (`nuevo_caso`, que ve el historial): "Hola, soy Ana, ya hablamos ayer, al
    # final somos 3" ya no borra la reserva. Si Jev calla, decide el regex.
    signals: dict | None = None
    if _is_new_scenario_restart(message, conv):
        signals = await _senales()
        if signals.get(NUEVO_CASO) is False:
            logger.info("[GRAPH] parece un escenario nuevo, pero Jev dice que sigue con lo de antes -> no se borra")
        else:
            logger.info("[GRAPH] restart de escenario nuevo -> limpio memoria")
            _reset_to_fresh_scenario(conv)
    # Pre-router: detección sticky de niños (persiste el resto de la conversación).
    if not getattr(conv, "kids_mention_detected", False) and _detect_kids_mention(message):
        conv.kids_mention_detected = True

    # rag-5: el RAG arranca ya, a la vez que el enrutador; la reserva lo aprovecha si el contexto no cambió.
    from src.agents.conversational_core import (
        fijar_pregunta_del_escritor,
        lanzar_extraccion_adelantada,
        lanzar_rag_adelantado,
    )

    fijar_pregunta_del_escritor(conv)  # lat-9 paso 2: antes del adelantado, que la lleva en su huella
    lanzar_rag_adelantado(conv, message)
    lanzar_extraccion_adelantada(conv, message)  # ex-5: el extractor "LLM primero", también a la vez

    # gen-5 (flag `idioma_unico_de_apertura`): el idioma de la apertura se decide aquí, una vez y a la vez que las
    # señales, para que todas las rutas contesten en el mismo (antes lo sensible, el contacto, la edad o el buceo
    # adaptado decidían cada uno a su manera y sin G-10).

    abre = not conv.detected_language and not msg_lower.isdigit() and conv.step in (Step.WELCOME, Step.LANGUAGE)
    if abre:
        from src.agents.nucleo.setup import idioma_de_apertura

        if signals is None:
            signals, _ = await asyncio.gather(_senales(), idioma_de_apertura(conv, message))
        else:
            await idioma_de_apertura(conv, message)
        logger.info(f"[GRAPH][IDIOMA] apertura en {conv.language!r}")
    if signals is None:
        signals = await _senales()
    # ex-9b paso 5 (PIDE_PRECIO): lo que Jev dice de ESTE turno (None si calla), para la puerta del origen antes
    # del precio, que corre en la reserva y en info. Se pone en cada turno: nunca queda el de un turno anterior.
    conv._jev_pide_precio = signals.get(PIDE_PRECIO)
    # ARQ-1b: las intenciones del mensaje según Jev (vacío si calla), para los hechos por código (src/flows/hechos.py).
    conv._intenciones = intenciones_del_turno(conv, signals)
    conv._otra_cosa = signals.get(PIDE_OTRA_COSA)  # ARQ-1d: None (Jev calla) cuenta como que sí trae algo más
    conv._un_descuento = signals.get(PIDE_UN_DESCUENTO) is True  # CALN3-Q05: pregunta por un descuento concreto
    # CALN-8 (lo delgado): el lector del grupo sale ahora, con lo que dice Jev, y solo si puede hacer falta.
    from src.agents.nucleo.extractor import lanzar_lector_si_hace_falta

    lanzar_lector_si_hace_falta(conv, message, signals)
    if conv._intenciones and conv._otra_cosa is False:
        # lat-1 (24-oct, fase LAT; Gadea #1731): el mensaje solo pide cosas de la tabla y lo contesta el redactor de
        # hechos, así que la respuesta adelantada del RAG se tira: se cancela ya, antes de que escriba y se revise
        # (latb2-B: en 48 turnos del redactor se gastaban escritor, revisor y embeddings para nada). Si al final contesta
        # el RAG (el redactor dice FALTA o no sabe la actividad), se lanza entonces, como sin adelantar.
        from src.agents.conversational_core import cancelar_rag_adelantado

        cancelar_rag_adelantado(conv)
    conv._redactor_dijo_falta = False  # ARQ-1g: lo pone el redactor si los hechos no contestan algo del mensaje
    conv._senales_router = signals  # gen-13: el cierre del turno sabe si el mensaje traía una pregunta
    route = classify_route(conv, message, signals)
    logger.info(f"[GRAPH] conv={conv.conversation_id} route={route}")
    if route == ROUTE_BOOKING and _no_usara_el_rag_adelantado(conv, message, signals):
        # lat-1 (24-oct; Gadea #1741): en la reserva, la respuesta adelantada solo se usa si el mensaje trae una pregunta
        # (o el lugar desconocido de CAL-C4). Sin eso se tiraba después de escribirla y revisarla («desde Cartagena»,
        # «somos 2»: latb3-B, 142 escritores y 67 revisores en turnos «descartado»). Se cancela ya; si al final hace
        # falta el RAG, se lanza entonces.
        from src.agents.conversational_core import cancelar_rag_adelantado

        cancelar_rag_adelantado(conv)
    from src.observability import note_turn

    note_turn(route=route)  # resumen del turno en Langfuse (m0-1)
    return {"signals": signals, "route": route}


def _make_legacy_delegate_node(route_name: str):
    """Fábrica de nodo-wrapper de Fase 1: delega en la cascada actual,
    reutilizando las señales ya calculadas por el router. Cada ruta registra
    su propio nodo (mismo cuerpo hoy) para que en Fase 2 se sustituyan uno a
    uno de forma independiente."""

    async def _node(state: BotState) -> dict:
        from src.agents.supervisor import _shared_turn_handler

        reply = await _shared_turn_handler(
            state["conv_state"], state["message"], routing_signals=state.get("signals")
        )
        return {"reply": reply}

    _node.__name__ = f"node_{route_name}"
    return _node


def _route_decision(state: BotState) -> str:
    return state["route"]


def _build_graph():
    builder = StateGraph(BotState)
    builder.add_node("router", _router_node)
    for route in ALL_ROUTES:
        node = _REAL_NODES.get(route) or _make_legacy_delegate_node(route)
        builder.add_node(route, node)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router", _route_decision, {route: route for route in ALL_ROUTES}
    )
    for route in ALL_ROUTES:
        builder.add_edge(route, END)
    return builder.compile()


_COMPILED_GRAPH = None


def get_compiled_graph():
    """Grafo compilado (lazy singleton — se compila una vez al primer uso, no
    a import)."""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = _build_graph()
    return _COMPILED_GRAPH


def _no_usara_el_rag_adelantado(conv: ConversationState, message: str, signals: dict) -> bool:
    """lat-1: ¿la reserva va a tirar la respuesta adelantada? Con el mismo criterio que la lanza
    (`conversational_core._maybe_launch_answer`): sin pregunta en el mensaje ni lugar desconocido, y fuera de DIVE TO
    HEAL (que la usa aunque no haya pregunta)."""
    from src.agents.conversational_core import _lugar_desconocido, _turn_has_question

    if getattr(conv, "_rag_adelantado", None) is None or conv.adaptive_diving_context:
        return False
    if _lugar_desconocido(signals):
        return False
    return not _turn_has_question(message, signals)


def intenciones_del_turno(conv: ConversationState, signals: dict) -> list[str]:
    """ARQ-1b: las intenciones del mensaje según Jev (vacío si calla), para los hechos por código."""
    intenciones = [nombre for nombre, señal in _INTENCION_DE_SENAL.items() if signals.get(señal)]
    if intenciones and conv.pregunta_precio_pendiente and "precio" not in intenciones:
        # arq-8f (G10 nº 6): el precio que esperaba el origen se perdía si el mensaje que da el origen pregunta otra cosa
        # («soy de Cartagena, ¿incluye el almuerzo?»): solo se contestaba la pregunta nueva. Va con ella.
        intenciones.append("precio")
    return intenciones


async def run_turn_via_graph(conv_state, message: str) -> str:
    """Punto de entrada del grafo para `supervisor.route_message` (Fase 1.4).
    Devuelve la respuesta; el `conv_state` queda mutado in-place por el nodo
    de ruta (que delega en la cascada), igual que si se hubiera llamado a
    `_shared_turn_handler` directamente.

    Observabilidad (Fase 5.3): si el tracing de Langfuse está activo, se pasa su
    `CallbackHandler` para trazar la corrida del grafo (nodos + latencia). Off →
    `config=None`, sin coste (ver `src/observability.py`)."""
    from src.config import settings
    from src.observability import current_turn_facts, langfuse_callback_handler, node_timer

    handler = langfuse_callback_handler(settings)
    callbacks = [handler] if handler is not None else []
    # Medición propia (TURN_METRICS): tiempo de cada nodo, con o sin Langfuse.
    facts = current_turn_facts()
    if facts is not None:
        callbacks.append(node_timer(facts))
    config = {"callbacks": callbacks} if callbacks else None
    result = await get_compiled_graph().ainvoke(
        {"conv_state": conv_state, "message": message}, config=config
    )
    return result["reply"]
