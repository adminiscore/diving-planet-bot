# Spike de diseño — LangGraph para el refactor multiagente

**Fase 0.6** de `docs/multi-agent-refactor-plan.md`. Fija el "cómo" técnico que
desbloquea las Fases 1-2 sin improvisar: patrón de State + reducers, router,
handoffs, subgrafo del booking, checkpointer candidato, y cómo se mockea un
nodo en tests. Todo lo de abajo está **verificado contra el LangGraph
realmente instalado en este repo** (no contra memoria/documentación
genérica) — ver método al final. Revisar entre los 3 antes de arrancar Fase 1.

---

## 0. Versión real instalada (importante)

Las deps del proyecto están pineadas (Fase 0.5) a lo que YA estaba resuelto
en el entorno — **no** a los `>=0.3/0.4` que originalmente declaraba
`pyproject.toml`:

| Paquete | Versión pineada |
|---|---|
| `langgraph` | `1.2.9` |
| `langchain` | `1.3.14` |
| `langchain-openai` | `1.4.1` |
| `langchain-community` | `0.4.2` |
| `langsmith` | `0.10.10` |

**Es un salto de versión mayor (0.x → 1.x)** frente a lo que el plan asumía
al principio. Investigado explícitamente para este spike: **LangGraph 1.0 no
trae breaking changes** para lo que usamos aquí — la única deprecación real
es `create_react_agent`/`AgentState`/`MessageGraph` (el *prebuilt* ReAct
agent y sus wrappers), reemplazados por `langchain.agents.create_agent`.
**No los usamos**: este plan construye un `StateGraph` a mano con nodos
propios, no el agente prebuilt — la deprecación no nos afecta. `StateGraph`,
`add_conditional_edges`, `Command(goto=)`, `add_messages`, y los
checkpointers mantienen la misma API. Único cambio real de entorno: Python
≥3.10 (ya estamos en 3.12/3.11, sin problema).

---

## 1. El patrón de State + reducers

`BotState` (el State schema real, §4 del plan) es un `TypedDict`. Cada campo
es un valor plano **salvo** los que necesitan una regla de fusión especial —
esos se anotan con `Annotated[tipo, reducer]`. El caso canónico es
`messages`, con el reducer que trae LangGraph de serie:

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class BotState(TypedDict):
    conversation_id: str
    language: str
    messages: Annotated[list, add_messages]   # reducer: agrega en vez de sobrescribir
    route: str | None
    booking: dict            # sub-estado de reserva (detected_* vivos)
    memory: dict              # remembered_facts + summary + notes
    signals: dict              # señales del router (1 vez/turno)
    reply: str | None
    quick_replies: list
    escalate: bool
```

**Por qué importa el reducer**: sin `Annotated[..., add_messages]`, cada
`return {"messages": [...]}` de un nodo **reemplazaría** la lista completa
(comportamiento por defecto: el último write gana). Con el reducer, cada
nodo puede devolver `{"messages": [nuevo_mensaje]}` y LangGraph hace el
`append`/merge por él — verificado (ver §6): un mensaje string devuelto por
un nodo se normaliza a `HumanMessage`/`AIMessage` y se **acumula**, no se
pisa. Para el resto de campos (`route`, `reply`, `escalate`...) el
comportamiento por defecto (el nodo que actualiza último gana) es lo que
queremos — no llevan reducer.

**Mapeo desde `ConversationState` actual** (`src/flows/state.py`, ya podado
a 5 valores de `Step` en Fase 0.2b): `BotState` no es un mapeo 1:1 — es una
reestructuración. Los ~29 campos vivos que quedan en `ConversationState`
(detected_*, mixed_cart, kids_*, remembered_facts, conversation_summary...)
se agrupan en `booking`/`memory` en vez de ir sueltos, siguiendo el objetivo
de "contratos tipados" (principio #6). Este mapeo campo-a-campo es trabajo
de la Fase 1.1, no de este spike — aquí solo se fija el *patrón*.

---

## 2. El router con `add_conditional_edges`

Un nodo normal que **lee** el mensaje/estado y **escribe** `state["route"]`;
un edge condicional aparte **lee** ese campo y decide a qué nodo saltar.
Son dos pasos separados a propósito: el nodo router puede ser
determinista-primero + LLM de respaldo (igual que hoy `detect_routing_
signals`), y el edge condicional es una función síncrona pura y barata.

```python
from typing import Literal

async def router_node(state: BotState) -> dict:
    # determinista-primero (reusa detectores actuales) + LLM de respaldo
    route = _detect_route_deterministic(state) or await _detect_route_llm(state)
    return {"route": route}

def route_decision(state: BotState) -> Literal["booking", "info", "changes", "deflection"]:
    return state["route"]

graph = StateGraph(BotState)
graph.add_node("router", router_node)
graph.add_node("booking", booking_node)
graph.add_node("info", info_node)
graph.add_node("changes", changes_node)
graph.add_node("deflection", deflection_node)
graph.add_edge(START, "safety")       # el gate de seguridad va ANTES del router (§4)
graph.add_edge("safety", "router")
graph.add_conditional_edges(
    "router", route_decision,
    {"booking": "booking", "info": "info", "changes": "changes", "deflection": "deflection"},
)
```

**Verificado en este repo** (script ad-hoc, ver §6): un router que escribe
`state["route"]` y un `route_decision` que lo lee despachan correctamente al
nodo correspondiente — sin sorpresas de la versión 1.x.

El `path_map` explícito (el tercer argumento, dict) es **opcional** pero
recomendado: sin él, LangGraph infiere los destinos del valor de retorno de
`route_decision`, lo cual funciona pero es menos legible/verificable
estáticamente. Úsalo siempre — es gratis y documenta el grafo.

**La taxonomía de rutas (§4.bis del plan) es el contrato de `route_decision`.**
Cada fila de esa tabla debe mapear a un valor de retorno válido del router.
La auditoría de la Fase 1.5 (shadow mode) es literalmente: por cada mensaje
de la suite, comparar `route_decision(state)` contra a qué gate lo mandaba
la cascada actual.

---

## 3. Handoffs con `Command(goto=)`

Un nodo que a mitad de su lógica descubre que en realidad el mensaje es de
**otro** caso (p. ej. `booking` procesando "¿cuánto cuesta?" y dándose
cuenta de que es una pregunta de `info`) no necesita que el router lo
prevea — puede redirigir él mismo devolviendo un `Command` en vez de un
dict:

```python
from typing import Literal
from langgraph.types import Command

async def booking_node(state: BotState) -> Command[Literal["info", "__end__"]]:
    if _looks_like_pure_info_question(state):
        return Command(goto="info", update={"route": "info"})
    reply = await _handle_booking_turn(state)
    return Command(goto=END, update={"reply": reply})
```

**Verificado en este repo** (§6): `Command(goto="node_b", update={...})`
redirige la ejecución al nodo indicado Y aplica el `update` al state antes
de entrar — confirmado con un trail que pasa por `node_a → node_b` solo
cuando la condición del handoff se cumple, y termina en `node_a → END` si
no. `Command(goto=END, ...)` termina el grafo igual que un edge normal a
`END`.

**Dónde se usan en el plan** (§4.bis): los backstops medidos en vivo que hoy
son "interceptores antes del gate" (`_in_active_cart_building`,
`_has_link_tech_context`, reparto-vs-deliberación) se convierten en
`Command(goto=...)` dentro del nodo que los detecta, en vez de listas de
condiciones en el supervisor. Un nodo puede tener **varios** posibles
`goto` (de ahí el `Literal["info", "__end__"]` en la firma — declara
explícitamente sus destinos posibles, útil para que `compile()` valide el
grafo).

---

## 4. El subgrafo del `booking`

El nodo `booking` (Fase 2.5, "el más grande, el último") no es una función
plana — es un **subgrafo compilado**, montado como un nodo del grafo padre.
LangGraph trata cualquier grafo compilado como un `Runnable` normal
(`ainvoke`/`astream`...), así que se puede pasar directo a `add_node`:

```python
# src/agents/booking_agent.py
def _build_booking_subgraph():
    sub = StateGraph(BookingState)   # sub-estado propio, no BotState completo
    sub.add_node("extract", extract_node)        # fill_gaps/detect_special_signals
    sub.add_node("slot_fill", slot_fill_node)     # next_missing_slot
    sub.add_node("close", close_node)             # cart_render determinista
    sub.add_edge(START, "extract")
    sub.add_conditional_edges("extract", ...)
    return sub.compile()

booking_subgraph = _build_booking_subgraph()

# en el grafo padre:
graph.add_node("booking", booking_subgraph)
```

Esto mapea directo a la Fase 3.3 del plan ("Partir el subgrafo booking en
nodos de responsabilidad única: routing interno → extracción → slot-fill →
cierre determinista"). El subgrafo tiene su **propio** state schema
(`BookingState`, un sub-conjunto/superset de `BotState` según convenga) —
LangGraph mapea claves compartidas automáticamente al invocar un subgrafo
como nodo; no hace falta un adaptador manual mientras las claves usadas
dentro del subgrafo existan también en el state del padre (o se declare
`input_schema`/`output_schema` explícito en `add_node`, disponible en la
API instalada — ver firma de `add_node` en §6).

**Por qué subgrafo y no una función gigante**: cada nodo interno
(`extract`/`slot_fill`/`close`) queda testeable en aislamiento (State in →
update out, LLM mockeado — exactamente la Fase 5.1 del plan), en vez del
monolito de 2.249 líneas que es hoy `conversational_core.py`.

---

## 5. El checkpointer candidato

**No es una decisión de este spike** (eso es la Fase 4.2, explícitamente:
"Decidir: checkpointer de LangGraph vs mantener `state_store.py`") — pero
sí hay que dejar el terreno investigado para no improvisar entonces.

**Lo que hay disponible, verificado con el LangGraph 1.2.9 instalado:**

| Backend | Paquete | Instalado hoy |
|---|---|---|
| En memoria (dev/tests) | `langgraph.checkpoint.memory.InMemorySaver` | ✅ (viene con `langgraph`) |
| Postgres | `langgraph-checkpoint-postgres` | ❌ paquete aparte, no instalado |
| Redis | `langgraph-checkpoint-redis` | ❌ paquete aparte, no instalado |
| SQLite | `langgraph-checkpoint-sqlite` | ❌ paquete aparte, no instalado |

El proyecto **ya tiene** persistencia de estado propia en Redis
(`src/state_store.py`, TTL configurado, `serialize_state`/`deserialize_state`
a mano). Las dos opciones reales para Fase 4.2 son:

1. **Adoptar `langgraph-checkpoint-redis`** (checkpointer oficial de Redis
   para LangGraph — mismo Redis que ya corre en dev/PRE) — da de serie
   time-travel/replay, pero cambia el formato de serialización y hay que
   migrar `state_store.py` entero.
2. **Mantener `state_store.py`** y solo mapear `BotState ⇄ JSON` en vez de
   `ConversationState ⇄ JSON` — cero migración de infra, se pierde
   time-travel/replay (no lo usamos hoy, así que no es una pérdida real
   inmediata).

**⚠️ Nota de seguridad para cuando se decida (investigado para este spike,
no aplica hoy — no usamos ningún checkpointer todavía):** hay una cadena de
vulnerabilidades real y reciente (Check Point Research, SQLi→RCE) en los
checkpointers de LangGraph:

- `langgraph-checkpoint-sqlite` **< 3.0.1**, `langgraph` **< 1.0.10**,
  `langgraph-checkpoint-redis` **< 1.0.2** son vulnerables.
- Cadena: claves de un `filter` dict controlado por el usuario se
  interpolan sin parametrizar en la query (`UNION SELECT` → SQLi) →
  el resultado inyectado se deserializa con
  `getattr(importlib.import_module(...), ...)(...)` → RCE.
- Dispara solo si la app **expone `get_state_history()`/`aget_state_history()`
  con un `filter` controlable por el usuario final** sin sanitizar, sobre
  backend **SQLite o Redis** (Postgres y el checkpointer en memoria no
  aparecen como afectados en la investigación).
- **Ya estamos a salvo en `langgraph` (1.2.9 ≥ 1.0.10)**. Si en Fase 4.2 se
  adopta `langgraph-checkpoint-redis`, fijar **`>=1.0.2`** desde el
  `pyproject.toml` (mismo principio #11 de versiones pineadas) y, sobre
  todo: **nunca exponer `get_state_history` a un filtro que venga del
  cliente sin sanitizar** — no es un caso de uso que el bot necesite hoy
  (no hay UI de "ver historial de estados" para el cliente final), así que
  el riesgo real es bajo, pero queda anotado para no reintroducirlo sin
  darse cuenta al construir herramientas de debug/admin sobre el
  checkpointer.

**Recomendación de este spike**: opción 2 (mantener `state_store.py`,
mapear `BotState`) para la Fase 4.2, salvo que el equipo quiera
time-travel/replay explícitamente — es menos migración y evita añadir la
superficie de la nota de seguridad de arriba sin necesidad real.

---

## 6. Cómo se mockea un nodo en tests

Un nodo de LangGraph **es solo una función** `async def node(state) -> dict
| Command`. No hace falta ningún util especial de testing de LangGraph — se
mockea exactamente como ya mockeamos todo lo demás en este repo
(`monkeypatch.setattr`/`unittest.mock.patch`, ver `tests/conftest.py` y el
patrón ya usado en `tests/test_agent_arch_poc.py` de la Fase 0.5):

**Nivel 1 — nodo en aislamiento** (Fase 5.1, "State in → update out, LLM
mockeado"): no se toca el grafo para nada, se llama a la función del nodo
directo:

```python
async def test_router_node_routes_booking():
    state = {"messages": [...], "route": None}
    with patch("src.orchestration.router._detect_route_llm", new=AsyncMock(return_value="booking")):
        result = await router_node(state)
    assert result["route"] == "booking"
```

**Nivel 2 — grafo compilado** (integración, Fase 5.1 también): se compila
el grafo real y se mockea la función interna que llama a un LLM (igual que
hoy con `conversational_core.fill_gaps`), luego se invoca el grafo entero:

```python
async def test_graph_handoff_booking_to_info():
    with patch("src.agents.booking_agent._looks_like_pure_info_question", return_value=True):
        result = await compiled_graph.ainvoke({"messages": ["cuanto cuesta"], "route": None})
    assert result["route"] == "info"
```

**Nivel 3 — equivalencia flag on/off** (patrón ya establecido en Fase 0.5,
`tests/test_agent_arch_poc.py`): correr el mismo mensaje con `agent_arch`
off (cascada actual) y on (grafo), comparar la respuesta. Es el patrón que
sostiene TODA la estrategia de tests del strangler (§3 del plan,
"Estrategia de tests"): mientras el flag existe, cada caso de la taxonomía
§4.bis debería tener un test de este tipo antes de cortar el legacy.

**Nada nuevo que aprender de LangGraph para esto** — la única diferencia
real con el resto de la suite es que ahora se mockea la función que un
*nodo* llama, en vez de la función que un *paso del árbol* llamaba. El
mismo `monkeypatch`/`unittest.mock.patch` de siempre.

---

## 7. Mapa de redes LLM → nodo (Fase 3.1)

`docs/multi-agent-refactor-plan.md` §5 Fase 3.1 pide "cada red LLM global → su
nodo" y "eliminar solapamientos (una red ya no ve 'todo el mensaje' fuera de su
caso)". **Hallazgo (2026-07-30):** el corte del núcleo (Fase 3.3) YA dejó cada
red llamándose desde su nodo dueño — el objetivo *funcional* de 3.1 está
conseguido como efecto del subgrafo. Mapa auditado de dónde vive cada red y
desde qué nodo se invoca:

| Red LLM | Módulo (definición) | Nodo que la invoca | Notas |
|---|---|---|---|
| `detect_routing_signals` | `escalation.py` | **router** (`orchestration/graph._router_node`) | 1 llamada/turno; sus 9 señales las consumen varios nodos (compartida por eficiencia, no duplicada) |
| `fill_gaps` · `missing_fields` | `llm_extractor.py` | **booking** (`_extraction_phase` vía `_understand`) | ⚠️ también en `supervisor._maybe_apply_llm_extraction_cutover` (subsistema legacy gated por `LLM_EXTRACTION_CUTOVER_*`, off por defecto — **NO tocar**, ver session-handoff) |
| `detect_special_signals` | `llm_extractor.py` | **booking** (`_routing_phase` recall + `_extraction_phase`) | scoped a booking |
| `resolve_slot_answer` | `llm_extractor.py` | **booking** (`_extraction_phase` anti-bucle de slot) | scoped a booking |
| `compose_acknowledgement` | `llm_extractor.py` | **booking** (`_slotfill_close_phase`) | scoped a booking |
| `extract_notes` | `notes_extractor.py` | **booking/memoria** (`_setup_phase` vía `_maybe_capture_notes`) | memoria; Fase 4.3 la unifica |
| `detect_language_llm` | `language_detector.py` | **booking** (`_setup_phase`, solo primer turno) | scoped a setup |
| `condense_query` | `query_rewriter.py` | **info** (RAG) | scoped a info |
| `is_grounded` / RAG | `rag_agent.py` | **info** | capa determinista de grounding (§4 del plan) |
| `maybe_update_summary` | `conversation_summarizer.py` | cross-cutting (`route_message`, post-turno) | memoria; Fase 4.3 |

**Solapamientos auditados:** ninguna red de un nodo se llama desde OTRO nodo
salvo (a) `detect_routing_signals`, compartida a propósito (1 llamada, señales
consumidas por nodo — no es un solapamiento problemático sino la fuente única de
señales del turno), y (b) `fill_gaps` en el cutover legacy (subsistema aparte,
flagged, off por defecto — no es el camino vivo). Los solapamientos que motivaron
el refactor (§0: `comparing_options` leído como reparto, `booking_change_topic`
pisando el multi-día) están **estructuralmente contenidos**: el router computa las
señales una vez y `classify_route` decide la ruta; la lógica de cada caso vive en
su nodo/fase.

**Pendiente de 3.1 (reubicación FÍSICA, diferida como churn de bajo valor):**
mover las definiciones a `src/agents/_nets/` (estructura objetivo del §4 del
plan) reapuntando los imports de `conversational_core`/`supervisor`/tests. Es
mecánico pero toca ~4 módulos + mocks de la suite; se hace deliberadamente (no
como cierre de sesión) y su valor es organizativo, no de comportamiento — la
propiedad red→nodo ya está lograda y documentada aquí.

---

## Anexos

- **Arquitectura objetivo completa**: §4 de `docs/multi-agent-refactor-plan.md`
  (diagrama, `BotState`, estructura de carpetas `src/orchestration/`).
- **Taxonomía de rutas**: §4.bis del mismo plan — el contrato que
  `route_decision` (§2 de este doc) debe cubrir entero.
- **PoC ya funcionando en la app real**: `src/orchestration/poc_graph.py`
  (Fase 0.5) — 2 nodos, sin router/handoffs/subgrafo todavía, pero prueba
  que LangGraph corre dentro del mismo event loop que Chatwoot sin
  conflictos.
- **Referencias externas usadas para este spike** (verificadas 2026-07-29):
  - [LangGraph v1 migration guide](https://docs.langchain.com/oss/python/migrate/langgraph-v1)
  - [LangChain/LangGraph reach v1.0](https://blog.langchain.com/langchain-langgraph-1dot0/)
  - [langgraph-checkpoint-redis (PyPI)](https://pypi.org/project/langgraph-checkpoint-redis/)
  - [Check Point Research — From SQLi to RCE, exploiting LangGraph's checkpointer](https://research.checkpoint.com/2026/from-sqli-to-rce-exploiting-langgraphs-checkpointer/)
- **Método de verificación de este spike**: cada afirmación de código de
  las §1-4 se probó con scripts ad-hoc contra el `langgraph==1.2.9`
  realmente instalado en este repo (no contra documentación genérica ni
  memoria de una versión distinta) — inspección de firmas
  (`inspect.signature`) de `StateGraph.add_node`/`add_conditional_edges`/
  `compile`, y ejecución real de grafos de prueba con `router` +
  `add_conditional_edges` y con `Command(goto=)`. Los datos de checkpointers
  y el aviso de seguridad (§5) vienen de búsqueda web verificada, con
  fuentes citadas arriba.
