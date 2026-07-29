"""Fase 1.1 (docs/multi-agent-refactor-plan.md) — BotState del grafo LangGraph.

BotState es un TypedDict (contrato, sin lógica), así que estos tests fijan lo
que sí puede regresionar: que transporta el ConversationState vivo sin copiarlo
ni serializarlo, y que las 5 rutas de la taxonomía §4.bis están declaradas.
"""

from src.flows.state import ConversationState
from src.orchestration.state import (
    ALL_ROUTES,
    ROUTE_BOOKING,
    ROUTE_CHANGE,
    ROUTE_DEFLECT,
    ROUTE_INFO,
    ROUTE_SAFETY,
    BotState,
)


def test_all_routes_are_the_five_taxonomy_routes():
    assert set(ALL_ROUTES) == {
        ROUTE_SAFETY,
        ROUTE_BOOKING,
        ROUTE_INFO,
        ROUTE_CHANGE,
        ROUTE_DEFLECT,
    }
    # Sin duplicados (cada mensaje va a exactamente una ruta).
    assert len(ALL_ROUTES) == len(set(ALL_ROUTES))


def test_botstate_carries_the_live_conversation_state_object():
    conv = ConversationState(conversation_id="orch-test")
    state: BotState = {"conv_state": conv, "message": "hola"}
    # Es el MISMO objeto (transportado, no copiado) — los wrappers lo mutan
    # in-place como hace la cascada hoy.
    assert state["conv_state"] is conv
    assert state["message"] == "hola"


def test_botstate_is_partial_fields_filled_along_the_graph():
    # total=False: a la entrada solo conv_state/message; route/signals/reply
    # los añaden los nodos. Un BotState sin ellos es válido.
    conv = ConversationState(conversation_id="orch-test")
    state: BotState = {"conv_state": conv, "message": "hola"}
    assert "route" not in state
    state["route"] = ROUTE_BOOKING
    state["reply"] = "respuesta"
    assert state["route"] in ALL_ROUTES
