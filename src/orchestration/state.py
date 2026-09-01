"""BotState — el contrato de estado del grafo LangGraph (Fase 1.1).

Ver `docs/agent-arch-design.md` §1 (patrón de State) y
`docs/multi-agent-refactor-plan.md` §4 (arquitectura objetivo).

## Por qué BotState transporta el `ConversationState` vivo (strangler-fig)

El objetivo final (§4 del plan) es un `BotState` "rico" con el estado
desglosado en campos tipados (`booking`/`memory`/`signals`/...) y un
`messages` con reducer `add_messages`. Pero llegar ahí de golpe rompería el
principio #2 (strangler-fig): en las Fases 1-2 los nodos del grafo son
**wrappers finos que delegan en los handlers ACTUALES**
(`_shared_turn_handler` y compañía), y esos handlers reciben y mutan un
`ConversationState`. Reescribir su firma a un `BotState` plano de golpe sería
un big-bang, justo lo que el plan prohíbe.

Así que durante el strangler `BotState` **transporta** el `ConversationState`
vivo (`conv_state`) + los campos de orquestación del grafo (`message`,
`route`, `signals`, `reply`). Los nodos-wrapper leen/mutan `conv_state`
llamando a la lógica de hoy; el grafo solo añade el enrutado por encima.

**Decisión de Fase 4.1 (2026-07-31, reencuadre aprobado por el owner):** el
"BotState rico con campos tipados + reducer `messages`" del §4 **NO se
materializa** — `ConversationState` (dataclass de ~60 campos tipados en
`src/flows/state.py`) YA es el State único y canónico: todos los nodos lo
comparten por referencia vía `conv_state`, y el audit de Fase 4 no encontró
estado de conversación disperso (los únicos globals son cachés inmutables de
config/KB y un ContextVar de diagnóstico por turno, no estado). Re-tipar ese
dataclass a un `BotState` plano sería un big-bang contra el principio strangler
(#2), y el reducer `add_messages` no aporta en una topología **lineal** (grafo
router→nodo→END y subgrafo booking lineal, sin fan-out). Así que `conv_state`
**se queda** como el portador del State canónico; `BotState` sigue siendo el
transporte por turno (message/route/signals/reply + conv_state).

**Persistencia — decisión de Fase 4.2 (2026-07-31): mantener `state_store.py`
sin cambios.** `BotState` es un envoltorio **por turno**, en vuelo — NUNCA se
serializa. Solo `conv_state` (el `ConversationState` canónico) se persiste
(`src/state_store.py` ⇄ Redis, JSON por `conversation_id` + TTL). Como no se
migra a `BotState` tipado, la serialización sigue siendo `ConversationState ⇄
JSON` **sin ninguna migración**. Se descarta el checkpointer de LangGraph por
ahora (no usamos time-travel/replay; añadiría migración + la superficie SQLi→RCE
de los checkpointers — ver `docs/agent-arch-design.md` §5); revisable si en el
futuro se necesita replay explícito.

## Reducers

El `messages: Annotated[list, add_messages]` del §4 todavía NO está aquí: en
la Fase 1 el grafo es lineal (router → un nodo de ruta → END), sin fan-out,
así que ningún campo necesita todavía una regla de fusión — el historial vive
en `conv_state.history` como hoy. El reducer entra cuando los nodos reales
escriban a un campo acumulado compartido (Fase 3+). Añadirlo ahora, sin nadie
que lo pueble, sería andamiaje muerto.
"""

from __future__ import annotations

from typing import TypedDict

from src.flows.state import ConversationState

# Las 5 rutas del router (§4.bis del plan). Cada mensaje se clasifica en
# exactamente una. Los valores son los que `route_decision` (el edge
# condicional del grafo) devuelve.
ROUTE_SAFETY = "safety"        # PII · médico/sensible · link roto · humano · DIVE TO HEAL
ROUTE_BOOKING = "booking"      # reserva: slot-fill, multi-ítem, acompañantes, recall
ROUTE_INFO = "info"            # preguntas de info/KB (RAG) + comparación de opciones
ROUTE_CHANGE = "changes"       # cancelar · reprogramar · disponibilidad
ROUTE_DEFLECT = "deflection"   # contacto · identidad IA · off-topic

ALL_ROUTES = (ROUTE_SAFETY, ROUTE_BOOKING, ROUTE_INFO, ROUTE_CHANGE, ROUTE_DEFLECT)


class BotState(TypedDict, total=False):
    """Estado en vuelo del grafo, por turno. `total=False`: los campos se van
    poblando a lo largo del grafo (el router fija `route`/`signals`, el nodo de
    ruta fija `reply`), no todos existen a la entrada."""

    # --- Entrada (las fija route_message al invocar el grafo) ---
    conv_state: ConversationState   # el estado vivo de la conversación (mutado por los wrappers)
    message: str                    # el mensaje entrante de este turno

    # --- Lo fija el nodo router (1.2) ---
    route: str                      # una de ALL_ROUTES
    signals: dict                   # detect_routing_signals(), calculado 1 vez/turno y compartido

    # --- Lo fija el nodo de ruta (wrapper que delega en la lógica actual) ---
    reply: str                      # la respuesta final al cliente
