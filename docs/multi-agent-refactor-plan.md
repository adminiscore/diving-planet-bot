# Plan de refactorización — a un sistema multiagente sobre LangGraph

> **Fuente de verdad del refactor.** Los 3 desarrolladores (Álvaro, Gadea, Gonzalo)
> trabajamos contra este documento. Cada paso tiene checkbox; al cerrarlo se marca `[x]`
> y se añade una línea al **Registro de ejecución** (final). Si una sesión se corta o
> alguien retoma tras un merge, **el estado de los checkboxes aquí es la única verdad**.
> Acompaña (no sustituye) a `docs/project-history/session-handoff.md`.

**Estado global:** `Fase 0 completa · Fase 1 completa · Fase 2 COMPLETA (5/5 nodos reales)`.
Grafo LangGraph detrás de `agent_arch`; **los 5 nodos son REALES** (deflection/escalation/
changes/info/booking, cortes strangler 2.1–2.5) y el grafo (flag on) despacha cada ruta a su
nodo sin delegar en la cascada. Equivalencia probada: suite verde en los 3 modos (default/
grafo/shadow), 1490 passed. La cascada (flag off) sigue viva. **Siguiente: Fase 3** (consolidar
las redes LLM + prompts por nodo + partir el subgrafo del booking) — pendiente de decidir el
reparto entre los 3. Creado 2026-07-29; actualizado 2026-07-30.
**Base de código:** rama `feature/pre_alvaro` (Fase 4 completa + Bloque 2 + reorg §1/§2).
**Motor de orquestación elegido:** **LangGraph** (con LangChain de forma selectiva) — ver §2.

---

## 0. Contexto — por qué hacemos esto

El bot creció de forma orgánica: 3 devs iterando, arreglando bugs ad hoc, refactorizando
sobre la marcha. **Funciona y es sólido en los hechos** (nunca inventa precio, link, cupo ni
confirma una reserva falsa — blindado por la capa determinista), pero la **complejidad
acumulada es el riesgo nº 1**: cada bug se arregla añadiendo *otro interceptor/guard/red*, y
cada capa nueva es más superficie donde dos redes chocan. Lo sufrimos en vivo esta semana
(`comparing_options` leyó un reparto de grupo como "duda"; `booking_change_topic` pisó el
interceptor multi-día).

**Objetivo:** migrar a la arquitectura del bot profesional de IBM/Naturgy detallada en
`arquitectura-diving-planet-bot.html`:

> **Router de intención → Orquestador → Agentes especializados con prompt enfocado por caso
> de uso**, sobre un **estado compartido** y una **capa determinista transversal** (precios,
> links, grounding) que garantiza que los hechos nunca se inventan.

Ese patrón (router + sub-agentes jerárquicos) es **literalmente lo que LangGraph modela de
forma nativa** — por eso este plan lo construye sobre LangGraph, no a mano.

### Criterios de éxito — qué es "terminado" (la vara de medir del owner)
El refactor está hecho cuando el bot es, de forma **verificable**:
- **Entendible** — un dev nuevo entiende el flujo leyendo el grafo (`graph.py`) y la lista de
  nodos, sin arqueología. Cada caso de uso vive en un sitio.
- **Controlable** — se sabe exactamente qué nodo/prompt maneja cada mensaje; se puede tocar un
  agente sin miedo a romper otro (fronteras + contratos).
- **Sin fugas** — ningún mensaje se pierde, ningún estado se dropea en silencio, ningún nodo
  falla sin fallback. Errores y timeouts de LLM degradan de forma segura y trazada, nunca a un
  valor inventado ni a una respuesta muerta.
- **Mantenible** — arreglar un bug = tocar un nodo, no añadir otro interceptor global. Sin
  redes que se pisan.
- **Reproducible** — deps fijadas (lockfile), entorno dev reproducible (Docker), LLM a
  `temperature=0` donde toca; cualquiera del equipo levanta el mismo bot y la misma suite.
- **Potente** — igual o mejor cobertura conversacional que hoy (la suite lo garantiza), con
  observabilidad (LangSmith) para seguir mejorando con datos reales.

Cada fase indica cómo acerca a estos criterios; la Fase 5 los cierra.

### Punto de partida (importante)
Este plan asume la base **post-Fase-4 con el trabajo de Gonzalo ya integrado** (rama
`fase4-p2` mergeada: árbol legacy `MIXED_*` fuera, flag `conversational_core` retirado, reorg
§1/§2, notes re-cableadas) + el fix de deliberación (`04e40ca`). Ese merge está **hecho en
local sobre `feature/pre_alvaro`, pendiente de push/decisión** — el refactor arranca desde ahí.
Cabo suelto menor a decidir en Fase 0: **Bloque 2.6** (respuestas estructuradas generalizadas)
— o se cierra antes de arrancar, o se absorbe en los prompts por-nodo de la Fase 3.

---

## 1. Valoración honesta: ¿LangGraph + LangChain? ¿factible? ¿mejora el bot?

**Hecho decisivo:** `langgraph`, `langchain`, `langchain-openai`, `langchain-community` y
`langsmith` **ya están en `pyproject.toml`** pero con **0 imports en `src/`** — el proyecto se
montó para usarlos y nunca se hizo. Además **LangSmith ya está configurado** en `config.py`
(`langsmith_api_key`, `langchain_tracing_v2=True`, `langsmith_project`). Python 3.14.

### ¿Qué supondría?
- **Adoptar LangGraph como el motor de orquestación**: un `StateGraph` donde los **nodos** son
  los agentes, los **edges condicionales** son el router/handoffs, un **State compartido** es
  el contexto, el **checkpointer** es la persistencia (hoy Redis a mano en `state_store.py`),
  y trae streaming + human-in-the-loop (para el escalado) de serie.
- **LangSmith para observabilidad**: al correr sobre LangGraph, el tracing por turno (qué
  nodo corrió, latencia, tokens, coste) sale **gratis** — es justo el dato que íbamos a
  instrumentar a mano. Ya está configurado, solo hay que encenderlo.
- **LangChain (el grande) con MODERACIÓN**, no wholesale: **NO** reescribir nuestra RAG afinada
  (pgvector + BM25 + grounding propio) ni el catálogo determinista en abstracciones de
  LangChain — eso sería un downgrade. Dentro de cada nodo seguimos llamando a OpenAI como hoy
  (`AsyncOpenAI` crudo) o, como mucho, vía `langchain-openai` para structured output. La
  regla: **LangGraph para el grafo; LangChain solo donde aporte; capa determinista intacta.**

### ¿Es factible?
Sí, y más de lo que estimé antes: las deps **ya están declaradas**, Python 3.14 va, LangSmith
ya configurado, y la costura de estado (`state_store` Redis → JSON) mapea limpio a un State
schema de LangGraph. El target (router→agentes) es exactamente el caso de uso central de
LangGraph.

### ¿Mejoraría el bot? — sí, para esta arquitectura objetivo
- **Enrutado condicional + handoffs entre agentes = nativo** (`add_conditional_edges`,
  `Command(goto=...)`), no a mano ni con interceptores que se pisan.
- **Persistencia, streaming, human-in-the-loop** incluidos (checkpointer + `interrupt`).
- **Observabilidad real (LangSmith)**: latencia/coste/traza por nodo — el punto que Gadea
  marcó como no medido.
- **Vocabulario estándar** que los 3 devs aprenden de la doc oficial (menos "magia" propia
  que mantener).
- **Evals con LangSmith datasets** para el bucle de datos reales (Fase 5) — mejor que
  inventar edge-cases a mano.

### El matiz honesto (corrijo mi recomendación anterior)
Antes dije "sin framework por ahora" para evitar sobre-ingeniería. Con los datos delante
(deps ya puestas, LangSmith ya configurado, target = caso nativo de LangGraph) **cambio la
recomendación: LangGraph es la elección correcta.** Un orquestador a mano reinventaría el
enrutado, la persistencia y el tracing que LangGraph ya da probados. Los **riesgos reales** y
cómo se mitigan:
- *LangChain el grande tiene churn y abstracciones que ocultan control* → se usa **selectivo**;
  la RAG/grounding/catálogo se quedan en Python plano dentro de nodos.
- *Curva de aprendizaje para 3 devs* → LangGraph es acotado; PoC en Fase 0 para rodarlo.
- *Migración de tests (hoy mockean funciones por monkeypatch)* → se testea cada **nodo aislado**
  + el **grafo compilado**; trabajo manejable, se planifica en Fase 5.

---

## 2. Principios rectores (inquebrantables durante todo el refactor)

1. **Comportamiento preservado.** La suite (~1.400 tests) es el **invariante**: verde con el
   flag `AGENT_ARCH` on **y** off tras cada paso. Ningún paso cambia conducta salvo decisión
   explícita y documentada.
2. **Strangler-fig detrás de flag.** El grafo LangGraph **coexiste** con la cascada actual
   detrás de `settings.agent_arch`. Se migra **ruta por ruta**; el camino viejo solo se borra
   cuando el grafo está probado en PRE. Nunca un "big bang".
3. **Determinista primero, LLM como red, backstop determinista** donde el LLM sobre-dispara.
   Se mantiene dentro de los nodos.
4. **Los hechos nunca por LLM.** Catálogo/precios/links/grounding/elegibilidad son
   deterministas y se llaman como Python plano **dentro** de los nodos. **Esta capa no entra
   en LangChain ni se toca.**
5. **LangGraph para orquestar, LangChain con moderación.** El grafo, el State, el router, los
   handoffs y la persistencia son LangGraph. Las llamadas LLM siguen siendo nuestras (OpenAI
   crudo o `langchain-openai` mínimo). Nada de meter la RAG afinada en retrievers de LangChain.
6. **Contratos tipados.** El State schema es la interfaz; cada nodo declara qué lee y qué
   parte del State actualiza. Nada de mutación global opaca.
7. **Un merge = una unidad coherente y verde.** Cada PR entre ramas deja el bot funcionando.
8. **Medir con LangSmith.** Latencia/coste/nº de llamadas por turno se leen de LangSmith
   (Fase 0 baseline → Fase 3 comparación). No optimizar de oído.
9. **Descartar sin miedo, sin desperdiciar.** Se borra el código muerto y lo que el grafo hace
   redundante (cascada ad-hoc, redes solapadas, estado legacy), reubicando la **información
   útil** (prompts afinados, backstops medidos en vivo, eval-sets) en el nodo que corresponda.
10. **Sin fugas — resiliencia por nodo.** Cada nodo tiene fallback: un error/timeout de LLM
    degrada de forma segura (respuesta determinista o "te paso con un asesor"), nunca a un
    valor inventado ni a una respuesta muerta. El grafo nunca deja un turno sin responder. Los
    fallos se trazan (LangSmith) y se loguean a nivel ERROR (patrón que ya usamos en
    `detect_special_signals`).
11. **Reproducibilidad.** Deps **fijadas** (lockfile committeado); versiones de
    LangGraph/LangChain pineadas (no auto-update); LLM a `temperature=0` en extracción/routing
    (ya lo hacemos); el bot dev se levanta igual para los 3 (Docker: Postgres+Redis).

---

## 3. Modelo de coordinación (los 3 devs)

- **Rama de integración:** `feature/agent-arch` (nueva, desde `pre_alvaro`). Sub-ramas cortas
  por paso (`agent-arch/graph-skeleton`, `agent-arch/node-deflection`, …) → merge a
  `feature/agent-arch` con la suite verde. Se sincroniza con `pre_alvaro` a menudo.
- **Este MD es la fuente de verdad.** Leer los criterios de aceptación aquí antes de empezar
  un paso; marcar `[x]` + línea en el Registro al cerrarlo.
- **Reglas de merge (vigentes de los handoffs previos):** sincronizar antes de empezar; suite
  verde antes de push; **NO `ruff --fix`** para imports (rompió 144); **proteger** la base
  compartida (`catalog`/`state`/`messages`, `cart_render`, `grounding_check`, `eligibility`);
  borrar por reachability (AST), suite tras cada borrado.
- **Paralelización:** tras cerrar el State schema y el grafo esqueleto (Fase 1), los
  **nodos-agente son aislables** → se reparten entre los 3. El State, el router y el esqueleto
  del grafo son la parte secuencial que va primero.

### Protocolo de trabajo — pasos pequeños con paradas (cómo lo llevamos)
Este refactor se hace en **pasos pequeños con parada y reporte** entre cada uno, no en tandas
grandes silenciosas. Es lo que mantiene el control y evita romper nada:
1. **Un paso a la vez.** Cada checkbox de una fase es una unidad. No se encadenan varios pasos
   grandes sin verificar.
2. **Suite verde tras cada paso** (los flags que apliquen). Si toca borrar código, la suite
   corre tras **cada** borrado, no al final del lote.
3. **Parada + reporte al cerrar un paso**: qué se hizo, resultado de la suite, commit, y qué
   viene. Antes de un paso **grande o arriesgado** (p. ej. borrar ~1.000 líneas, cortar el
   legacy), se para y se confirma con el owner/equipo — no se ejecuta a ciegas.
4. **Registro de ejecución** (§8) actualizado en cada cierre: fecha · dev · qué · commit. Es
   la memoria del refactor entre sesiones y devs.
5. **Commits pequeños y limpios**, un propósito por commit, con la suite verde. Nada de
   `ruff --fix` en imports. Si un fichero se voltea a CRLF, normalizar a LF y `--amend` (el
   repo no tiene `.gitattributes`; ver `session-handoff.md`).

### Estrategia de tests (transversal — no es solo la Fase 5)
La suite es la red de seguridad de TODO el refactor, así que su evolución se planifica desde
el principio, no al final:
- **Hoy:** ~1.400 tests mockean funciones concretas por monkeypatch (`fill_gaps`,
  `rag_answer`, `detect_routing_signals`…) + fixtures autouse en `conftest`/`test_*`.
- **Durante el strangler (Fases 1-2):** los tests existentes corren con `agent_arch` **off**
  (comportamiento actual) — no se tocan. Se añaden tests **nuevos** que ejercitan el grafo con
  `agent_arch` **on**. La suite pasa en **ambos flags** = prueba de equivalencia.
- **Al reubicar redes (Fase 3):** cuando una red LLM se mueve a su nodo, sus tests se mueven
  con ella y se re-apuntan los mocks (del módulo global al nodo). Un paso, un re-apunte, suite
  verde.
- **Fase 5:** cada nodo con su **test unitario de contrato** (State in → update out, LLM
  mockeado) + tests de **grafo compilado** (integración e2e). Al cortar el legacy se borran los
  tests del camino viejo (reachability).
- **Regla:** ningún merge sin la suite verde en los flags que aplican a ese paso.

### Rollout en PRE (cómo se corta al final, sin susto)
El flag `agent_arch` se enciende **primero en PRE** (no en dev-only) cuando el grafo está
completo (Fase 3-4): se mide en LangSmith con tráfico real, se comparan trazas/latencia/coste
contra la baseline, y solo cuando el comportamiento es igual o mejor durante un periodo
acordado se hace el **corte** (Fase 5.2: quitar flag + borrar legacy). Reversible en cualquier
momento apagando el flag hasta el corte.

---

## 4. La arquitectura objetivo sobre LangGraph

```
Chatwoot ──► load_state (Redis / checkpointer LangGraph, thread_id = conversation_id)
                │
                ▼
        ┌───────────────────────  StateGraph (compilado)  ───────────────────────┐
        │  START                                                                  │
        │    │                                                                    │
        │    ▼                                                                    │
        │  [safety]  ──(riesgo)──► [escalation] ──► END                           │
        │    │ (ok)                                                               │
        │    ▼                                                                    │
        │  [router]  ── add_conditional_edges(intent) ──►                         │
        │        ├─► [booking]   (subgrafo: slot-fill + multi-ítem)               │
        │        ├─► [info]      (RAG + grounding)                                │
        │        ├─► [changes]   (cancelar · reprogramar · disponibilidad)        │
        │        └─► [deflection](contacto · identidad · off-topic)               │
        │   (cada nodo puede Command(goto=...) → handoff a otro nodo)             │
        │                                                                         │
        │  Todos llaman a la CAPA DETERMINISTA (catalog/cart_render/grounding)    │
        │  como Python plano dentro del nodo — NO entra en el grafo/LangChain.    │
        └─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
        save_state ──► respuesta a Chatwoot     (traza completa en LangSmith)
```

**El State (contrato compartido)** — `src/orchestration/state.py` (nuevo):
```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class BotState(TypedDict):
    conversation_id: str
    language: str
    messages: Annotated[list, add_messages]   # historial con reducer nativo
    route: str | None                          # lo fija el nodo router
    booking: BookingState                      # sub-estado de reserva (detected_* vivos)
    memory: dict                               # remembered_facts + summary + notes
    signals: dict                              # señales del router (1 vez/turno)
    reply: str | None                          # salida; los hechos vienen del catálogo
    quick_replies: list
    escalate: bool
    # … campos vivos saneados en Fase 0 (NO los ~30 mixed_* muertos)
```
Se construye **saneando** el `ConversationState` actual (que arrastra ~30 campos `mixed_*`
muertos y ~35 valores `Step.*` legacy). Persistencia: se evalúa usar un **checkpointer de
LangGraph** (Redis/Postgres) o mantener `state_store.py` mapeando `BotState`⇄JSON (Fase 4).

**Un nodo** = una función `async def node(state: BotState) -> dict` que devuelve el trozo de
State que actualiza. El router es un nodo que fija `state["route"]`; los edges condicionales
despachan. Los handoffs (un agente que detecta que en realidad es otro caso) son
`Command(goto="otro_nodo")`.

**Los prompts, como en IBM, son el corazón del control.** Cada nodo tiene **su** prompt corto,
enfocado a UN caso de uso, en `src/prompts/` — legible, revisable, versionado. Nada de un
prompt gigante que lo abarca todo (eso es lo que "se liaba" en el sistema de IBM). Los prompts
afinados que ya tenemos (persona Coral, grounding, deflexiones, extracción) se **conservan**,
recortados a su dominio y movidos al prompt del nodo correspondiente.

**Estructura de carpetas objetivo:**
```
src/
  orchestration/          ← NUEVO — el grafo LangGraph
    state.py                BotState (TypedDict) + reducers
    graph.py                StateGraph: nodos + edges + compile(checkpointer)
    router.py               nodo router (determinista-primero + LLM de respaldo)
  agents/                 ← nodos especializados (lógica + guards)
    booking_agent.py        subgrafo slot-fill + multi-ítem (era conversational_core)
    info_agent.py           RAG + grounding (era rag_agent, envuelto)
    changes_agent.py        cancelar/reprogramar/disponibilidad (hoy en supervisor)
    deflection_agent.py     contacto/identidad/off-topic (hoy en supervisor)
    escalation_agent.py     PII/médico/quejas/DIVE TO HEAL/humano (era escalation)
    _nets/                  redes LLM reubicadas por agente (era llm_extractor global)
  prompts/                ← PROMPTS como artefacto de primera clase (patrón IBM)
    router.py               prompt de clasificación de intención
    booking.py · info.py …  1 prompt corto y enfocado por caso de uso, versionado y legible
  flows/                  ← capa determinista — Python plano, NO se toca
    catalog.py · state.py · messages.py · cart_render.py · eligibility.py
  channels/ · knowledge/ · state_store.py …  (infra)
```

---

## 4.bis. Taxonomía de rutas — *nada se queda suelto*

El router debe cubrir **todos** los casos que hoy maneja la cascada de 14 gates + el núcleo.
Este mapeo es el contrato de "no perder ninguna casuística" en la migración. Cada gate actual
tiene su destino:

| Caso actual (gate/handler) | Ruta / nodo objetivo | Nota |
|---|---|---|
| PII (`detect_pii`) | `escalation` | Bloqueo de privacidad |
| Tema sensible médico/clima/queja (`SENSITIVE_RULES` + señal LLM) | `escalation` | Reglas + señal |
| Link roto (keyword + `broken_link_complaint`) | `escalation` | Con backstop `_has_link_tech_context` |
| DIVE TO HEAL / discapacidad (`_ADAPTIVE_DIVING_PATTERN` + señal) | `escalation` (contexto adaptado) | Persiste `adaptive_diving_context`; sigue a `info` para preguntas de precio/logística |
| Quiere humano (`ESCALATION_KEYWORDS` + `wants_human`) | `escalation` | Handoff (LangGraph `interrupt`) |
| Cancelar (`_detect_cancellation_request` + `booking_change_topic`) | `changes` | Gated `_in_active_cart_building` |
| Reprogramar (`_detect_reschedule_request` + señal) | `changes` | |
| Disponibilidad (`_AVAILABILITY_PATTERN` + `availability_question`) | `changes` | Respuesta canónica anti-alucinación |
| Deflexión de contacto (`_asks_for_contact_number`) | `deflection` | Límite + redirige |
| Identidad IA (`_asks_about_ai_identity`) | `deflection` | En persona, sin revelar |
| Off-topic / dominio blindado / anti-inyección | `deflection` | System prompt OWASP |
| Preguntas de info sobre productos/KB (RAG) | `info` | + grounding |
| Deliberación entre opciones (`comparing_options`) | `info` (comparación) | Backstop reparto-vs-deliberación |
| Reserva: actividad/cert/lugar/cantidad/… (slot-fill) | `booking` | Subgrafo |
| Multi-ítem / acompañantes | `booking` (sub-orquestador) | Cola de acompañantes |
| Nacionalidad mixta (`_detect_mixed_nationality_request`) | `booking` | Sub-caso de reserva |
| Recall ("¿qué te había pedido?") | `booking` (o memoria) | `_full_booking_recap` |
| Saludo / primer contacto / idioma | `booking` (entrada) o nodo `greeting` | Decidir en Fase 1.2 |
| Menú / reiniciar (`MENU_KEYWORDS` + `wants_menu_or_restart`) | *(decisión Fase 4)* — hoy "menú = mensaje normal" | Reevaluar si hace falta ruta propia |
| Restart de escenario nuevo (`_is_new_scenario_restart`) | pre-router (limpia memoria) | Se ejecuta antes del router |

**Auditoría obligatoria (Fase 1.5):** el modo shadow debe confirmar que **cada** una de estas
filas se enruta igual que hoy. Cualquier caso que la cascada maneja y que no aparezca aquí es
un bug del plan — se añade antes de cortar el legacy.

---

## 5. Las fases

Cada fase deja el bot **funcionando y verde**. Orden estricto (salvo los nodos de Fase 2, que
se paralelizan entre sí).

### Fase 0 — Cimientos, limpieza y observabilidad · *no cambia comportamiento* · **bloqueante**
- [x] **0.1 · Congelar el baseline.** ✅ **Baseline: `1412 passed · 18 skipped · 0 failed`**
      (rama `feature/agent-arch`, suite completa con LLM real, ~7 min). El único fallo previo
      (`test_gap_fill_logs_in_harvester_format`) era un test **infra-aislado**: mockeaba
      `fill_gaps` pero no `detect_routing_signals`, así que dependía de que el routing LLM real
      no disparara `availability_question` con el "mañana" del mensaje. Arreglado mockeando el
      routing en el test (test fix, no cambia producto). Verde inequívoco confirmado (3/3).
- [x] **0.2 · LIMPIEZA del estado (`ConversationState` + `Step`) — HECHO, partido en 0.2a+0.2b.**
      Borrar por reachability los campos `mixed_*` y valores `Step.*` muertos tras Fase 4.
      **Análisis de reachability hecho (2026-07-29):**
      - **`mixed_*`: 13 campos MUERTOS** (0 refs en src y tests) → borrado directo seguro:
        `mixed_pending_course_question`, `_cert_total_qty`, `_cert_remaining_qty`,
        `_refresh_added_qty`, `_beginner_after_cert`, `_companion_upsell`, `_modify_idx`,
        `_modify_refresh`, `_cert_narrow_kind`, `_exact`, `_location_change`,
        `mixed_beginner_child_age`, `mixed_pending_beginner_queue`. (El resto siguen vivos;
        algunos son write-only candidatos a revisar al construir el nodo booking.)
      - **`Step.*`: ~33 valores sin refs `Step.X`** PERO **acoplados a `messages.py`**: se
        referencian por su **valor string** (p. ej. `'info_menu'`, `'pricing_menu'`,
        `'courses_menu'`) como claves del dict `MESSAGES` / botones del menú legacy que la
        reorg §1 reubicó a `messages.py` **sin podar** (~1.000 líneas de datos de menú muertos).
        → La limpieza del enum es en realidad **podar el menú legacy entero de `messages.py`**
        (MESSAGES + BUTTON_OPTIONS + métodos de menú de `DecisionTree`) + los 5 steps
        referenciados en `_INTENT_TRIGGER_STEPS` (supervisor). Sub-tarea acoplada más grande
        de lo previsto — hacerla en un paso cuidado propio (0.2b), no mezclada con los campos.
      - Suite verde tras cada borrado (AST no líneas).
- [x] **0.2a · Campos `mixed_*` muertos — HECHO** (`5d7c890`). 13 campos borrados de
      `ConversationState` (75→62 campos). Suite completa idéntica al baseline (1412 passed).
- [x] **0.2b · Poda del menú legacy — HECHO** (0.2b-i `b8f8d43`, 0.2b-ii `fbeff5c`).
      - **0.2b-i · Enum `Step` (state.py) — HECHO.** 43→5 valores (quedan WELCOME/LANGUAGE/
        MAIN_MENU/ESCALATE/FREE_TEXT). Quitados RESERVA_MENU/INFO_MENU/BOOKING_MENU de
        `supervisor._INTENT_TRIGGER_STEPS`. Tests: `test_state_store` actualizado
        (PRICING_MENU→MAIN_MENU), borrados 3 helpers muertos de `test_conversations`
        (`reach_pricing_menu`/`reach_booking_menu`/`reach_logistics_menu`, 0 llamadas).
      - **0.2b-ii · Datos de `messages.py` — HECHO.** 1517→80 líneas. `MESSAGES` 60→2 claves
        (escalate/main_menu), `BUTTON_OPTIONS` 40→1 clave (main_menu). Borrados los 3 métodos
        de isla de `DecisionTree` (`_info_island_certified_options`/`_island_certified_options`/
        `_mixed_island_certified_multiday_options`, 0 refs) + las 3 ramas de `set_quick_replies`
        que solo ellos alimentaban (sus condiciones nunca ocurrían — el único caller real
        siempre pasa `key="main_menu"`); `set_quick_replies` queda en un solo camino.
      - Suite tras cada sub-paso: **1421 passed / 9 skipped / 0 failed** (mismo total 1430 que
        el baseline 1412/18 — la diferencia de skips es de entorno, sin `OPENAI_API_KEY` local,
        no del cambio). ruff + compileall limpios en ambos.
- [x] **0.3 · LIMPIEZA de dependencias y muertos — HECHO** (`24c7c77`, `10175ca`). Shim
      `decision_tree` cerrado: los ~34 importadores (7 en `src/`, resto tests/scripts)
      reapuntados a `catalog`/`state`/`messages` (incluidos 2 monkeypatch targets en
      `test_conversational_core.py`), `src/flows/decision_tree.py` borrado, y el vestigio
      `DecisionTree` (solo `set_quick_replies` + `_CART_MENU_KEYS`, sin estado propio)
      convertido en función de módulo. Auditoría de imports huérfanos hecha por diff
      (`git stash` antes/después): ruff da los mismos 170 errores en los mismos archivos
      — deuda preexistente ajena, cero regresiones; no se usó `ruff --fix`.
- [x] **0.4 · Encender LangSmith + baseline de métricas — HECHO** (`2071643`).
      **Activación:** `_activate_langsmith_tracing` en `config.py` propaga
      `langsmith_api_key`/`langsmith_project`/`langchain_tracing_v2` a las env vars
      `LANGSMITH_*` que el SDK realmente lee (pydantic-settings solo las carga al objeto
      `Settings`, nunca toca `os.environ` — por eso estaban "configuradas" pero 0 imports
      de langsmith/langchain en `src/` seguían sin activarse). No-op sin API key: **este
      entorno dev no tiene `LANGSMITH_API_KEY`**, así que sigue inerte hasta que se añada
      una — listo para cuando exista, sin más cambios de código.
      **Baseline (sin LangSmith, medido en local — `scripts/measure_llm_baseline.py`):**
      parchea `AsyncCompletions.create`/`AsyncEmbeddings.create` a nivel de clase (cubre
      las ~10 instanciaciones de `AsyncOpenAI` en `src/` sin tocar ningún archivo de
      producción) y corre un guion representativo de 5 turnos (reserva de buceo
      certificado con acompañante) contra el bot real (`ENV_FILE=.env.dev`, LLM/Postgres/
      Redis reales, sin mocks):

      | Turno | Mensaje | Llamadas LLM |
      |---|---|---|
      | 1 | "hola" | 2 |
      | 2 | "quiero bucear, ya soy certificada open water, somos 2 personas" | 4 |
      | 3 | "salimos desde cartagena" | 4 |
      | 4 | "cuanto cuesta" | 2 |
      | 5 | "perfecto, reservamos" | 3 |

      | Métrica | Total | Por turno |
      |---|---|---|
      | Llamadas LLM | 15 | 3.00 |
      | Latencia | 23.71 s | 4.74 s |
      | Latencia media/llamada | — | 1.58 s |
      | Tokens prompt | 23 554 | 4 711 |
      | Tokens completion | 455 | 91 |
      | Coste estimado | $0.0038 | $0.0008 |

      Las 15 llamadas fueron todas `gpt-4o-mini` (routing/extracción/RAG del núcleo;
      ninguna tocó `gpt-4o` en este guion). Es el **número que dirige la Fase 3**
      ("reducir llamadas LLM/turno" §5 Fase 3.4) — el objetivo ahí es bajar de 3.00
      llamadas/turno una vez las redes se consoliden por nodo. Repetir esta medición
      con LangSmith real en cuanto haya API key, y comparar contra esta baseline local.
- [x] **0.5 · Instalar de verdad LangGraph + PoC de-risk — HECHO** (`559450d`). Las deps ya
      estaban instaladas en el entorno (resueltas a 1.x: `langgraph 1.2.9`, `langchain 1.3.14`,
      `langchain-openai 1.4.1`, `langchain-community 0.4.2`, `langsmith 0.10.10` — un salto
      mayor de versión respecto a los `>=0.3/0.4` declarados). Pineadas a exacto en
      `pyproject.toml` (`pip check` sin conflictos) + `requirements-lock.txt` (snapshot
      completo vía `pip freeze`; el proyecto usa pip, no uv/poetry — informativo, Docker/CI
      siguen instalando por `pyproject.toml`). **PoC**: `src/orchestration/poc_graph.py`,
      grafo trivial de 2 nodos (uppercase → reply), sin checkpointer, cableado en
      `supervisor.route_message` detrás de `settings.agent_arch` (default `False`) como
      side-channel puro (nunca cambia la respuesta). **Validado en vivo** (LLM/Postgres/Redis
      reales, `ENV_FILE=.env.dev`): con el flag on, el log `[AGENT_ARCH POC]` sale ANTES del
      cascade real y la respuesta es idéntica a flag off para el mismo mensaje; con el flag
      off (default), `src.orchestration` ni se importa. 4 tests nuevos (flag off por defecto,
      no invoca el grafo con el flag off, no cambia la respuesta con el flag on, un fallo del
      grafo no rompe el turno — principio #10). Suite 1425 passed / 9 skipped / 0 failed, ruff
      + compileall limpios.
- [x] **0.6 · Spike de diseño LangGraph — ESCRITO, pendiente de revisión de los 3.**
      `docs/agent-arch-design.md`: patrón de State + reducers, router con
      `add_conditional_edges`, handoffs con `Command(goto=)`, subgrafo del booking,
      checkpointer candidato (+ nota de seguridad real encontrada — SQLi→RCE en
      checkpointers de LangGraph, ver doc), y cómo mockear un nodo en tests. **No
      redactado de memoria**: cada ejemplo de código se verificó ejecutando contra el
      `langgraph==1.2.9` real instalado (no la versión 0.x que el plan asumía
      originalmente — investigado el salto y confirmado **sin breaking changes** para
      lo que usamos aquí). Marcado `[x]` porque el documento está completo y lo que
      queda es la revisión humana del equipo, no trabajo pendiente de esta sesión —
      **Álvaro/Gonzalo: revisarlo antes de arrancar Fase 1.**
- **DoD:** estado limpio + shim fuera + LangSmith midiendo baseline + LangGraph instalado y
  PoC verde + flag + spike de diseño acordado. **Nadie cambió comportamiento.**

### Fase 1 — El grafo esqueleto + el Router · *misma conducta, estructura de grafo* · **HECHA**
- [x] **1.1 · `BotState` — HECHO** (`db69308`). `src/orchestration/state.py`: TypedDict
      (`total=False`) que durante el strangler **transporta** el `ConversationState` vivo
      (`conv_state`) + los campos de grafo (`message`/`route`/`signals`/`reply`). Los nodos
      delegan en los handlers actuales (que mutan `conv_state`), así que no se reescriben
      firmas — el `BotState` "rico" del §4 (booking/memory + `messages` con reducer) llega en
      Fase 4.1. Persistencia intacta: `BotState` es por-turno, nunca se serializa; solo
      `conv_state` se persiste (`state_store` ⇄ Redis sin cambios). Constantes `ROUTE_*` = las
      5 rutas §4.bis. 3 tests.
- [x] **1.2 · Router — HECHO** (`2c6d042`). `src/orchestration/router.py`: `classify_route(
      conv_state, message, signals)` read-only, reúsa los detectores reales del supervisor +
      señales LLM (pasadas, sin recomputar) + backstops. **Enrutado intencional** (taxonomía
      §4.bis), no réplica exacta de la cascada — la frontera BOOKING/INFO vive dentro del
      núcleo (todo lo que cae ahí → BOOKING; se separa en Fase 3.3). Import perezoso de
      supervisor (rompe el ciclo futuro). 22 tests (cada rama + prioridad safety-first).
- [x] **1.3+1.4 · Grafo esqueleto + cableado tras el flag — HECHO** (`e6d8de2`).
      `src/orchestration/graph.py`: `StateGraph(BotState)` con `START → router →
      add_conditional_edges → {5 nodos de ruta} → END`. Los 5 nodos son wrappers finos que
      delegan en `_route_message_inner` (reutilizando las señales del router — una sola llamada
      LLM/turno; `_route_message_inner` acepta `routing_signals` opcional). Compilado
      lazy-singleton. Cableado en `route_message` tras `settings.agent_arch` (off = cascada
      intacta; on = grafo). El `conv_state` viaja por referencia; las mutaciones in-place se
      propagan al objeto del caller (verificado contra LangGraph). Retirado el PoC de 0.5.
      (Sin `safety` como pre-nodo ni `checkpointer` todavía: safety es una ruta que el router
      elige — coincide con la taxonomía §4.bis que manda PII/sensible/link/humano a
      `escalation`; el checkpointer es decisión de Fase 4.2. Ambos anotados como refinamientos,
      no bloquean el DoD.) 6 tests de equivalencia.
- [x] **1.5 · Shadow + equivalencia — HECHO** (`c2ed174`). **Equivalencia**: la suite COMPLETA
      pasa idéntica en las 3 configuraciones — default, `AGENT_ARCH=true` (grafo) y
      `AGENT_ARCH_SHADOW=true` (shadow): **1459 passed / 9 skipped / 0 failed**. **Shadow**:
      nuevo flag `agent_arch_shadow` (default off) — con la cascada viva corre además el router
      y loguea `[ROUTE_SHADOW] match|MISMATCH` comparando su ruta con la que la cascada marcó
      (ContextVar `_cascade_route_taken` + `_mark_route` en cada gate; sin doble llamada LLM;
      inerte en operación normal; se retira con la cascada en 5.2). Verificado en vivo: 6/6
      match en mensajes de las 5 rutas. 7 tests.
- [x] **1.5.audit · Auditoría §4.bis vía la suite — HECHA** (2026-07-29). PRE no tiene tráfico
      real (solo el equipo probando), así que la auditoría del shadow se hizo sobre la suite
      COMPLETA (el conjunto más diverso y adversario disponible) en vez de esperar tráfico
      orgánico. **Resultado: 223 match / 14 MISMATCH = 94.1% de coincidencia** sobre casos
      deliberadamente difíciles (typos, jerga, edge cases). Los 14 caen en 2 patrones limpios:
      - **A · Elegibilidad por edad (11/14): router `booking`, cascada `info`.** "mi hijo de 9
        puede bucear?", "una persona de 14 años puede?", "bebé de 2 años"… La cascada las
        resuelve con el gate determinista `_maybe_answer_age_eligibility` (→ INFO); el router
        no lo predice porque es un gate "decide-haciendo" (ejecuta detección de intención +
        muta estado), no un predicado puro. **Hueco real y arreglable del router** — le falta
        una rama edad→INFO (cue `_AGE_ELIGIBILITY_CUE` + presencia de edad). A cerrar antes de
        Fase 2.4 (nodo info) o al construirlo.
      - **B · Disponibilidad (3/14): router `changes`, cascada `booking`.** "¿tienen
        disponibilidad el sábado?", "no tenéis algo para más días"… Divergencia ESTRUCTURAL
        conocida: la cascada comprueba disponibilidad DESPUÉS del núcleo (que las agarra
        primero → booking), el router la pone antes del default. Aquí el router es
        discutiblemente MÁS correcto — candidato a "bug de orden de la cascada" a decidir en
        el cutover (Fase 5.2): ¿es correcto que el núcleo intercepte una pregunta de
        disponibilidad fresca? Documentado, sin cambio por ahora.
- **DoD cumplido:** un turno real atraviesa el grafo con flag on y responde igual que la
  cascada (suite verde en los 3 modos); el shadow mide la coincidencia de rutas (94.1% sobre
  la suite adversaria; los 14 mismatches auditados y clasificados). **La cascada sigue viva.**

### Fase 2 — Los nodos-agente con contrato · *paralelizable entre los 3* · **COMPLETA**
- [ ] **2.0 · Contrato de nodo + orquestador.** Fijar la firma de nodo (State→update),
      `Command`/handoffs, y el manejo del resultado (reply/quick_replies/escalate). Secuencial,
      va primero.
- [x] **2.1 · Nodo `deflection` — HECHO** (`src/agents/deflection_agent.py`). Primer corte
      strangler real: la ruta `ROUTE_DEFLECT` deja de delegar en toda la cascada y ejecuta solo
      la lógica de deflexión (contacto vía `_asks_for_contact_number`/señal → límite 🔒 +
      redirige; identidad IA vía `_asks_about_ai_identity` → en persona, sin revelar), en el
      mismo orden que la cascada. Fallback a la cascada si se alcanza sin match (resiliencia
      #10). Cableado en `graph.py` (`_REAL_NODES`); detectores/copys importados de `supervisor`
      (migrarán a módulo propio en Fase 3). **8 tests nuevos** (aislado + equivalencia flag
      on/off en 4 mensajes) + 43 verdes en orquestación/grafo/router/shadow. Ruff limpio.
      *(dev: Álvaro)* NOTA: cubre lo que el router manda hoy a DEFLECT (contacto + identidad).
      El off-topic/dominio-blindado genérico sigue vía el system prompt endurecido de RAG; si se
      quiere una ruta DEFLECT para off-topic explícito, es un refinamiento del router aparte.
- [x] **2.2 · Nodo `escalation` — HECHO** (`src/agents/escalation_agent.py`). Segundo corte
      strangler: la ruta `ROUTE_SAFETY` ejecuta directamente los 6 gates SAFETY **pre-núcleo**
      (PII → bloqueo privacidad; link roto por keyword y por señal LLM+contexto; sensible por
      keyword y por señal; DIVE TO HEAL precio/reserva → asesor), en el mismo orden que la
      cascada, con idéntico efecto de estado (step/pending_escalation_reason/pending_note/
      adaptive_diving_context). Los gates SAFETY **post-núcleo** (wants_human / keyword de
      escalado / afirmación que acepta la oferta de asesor) NO se reproducen: están tras
      `maybe_handle_turn` en la cascada, así que reproducirlos sin correr el núcleo cambiaría el
      orden → se **delega en la cascada** (equivalencia garantizada, no-op de comportamiento).
      Respaldado por el audit del shadow (§1.5): **0 mismatches en SAFETY**. **11 tests nuevos**
      (5 aislados por gate + delegación + equivalencia flag on/off en 5 mensajes) + 116 verdes
      en la regresión ancha. Ruff limpio. *(dev: Álvaro)*
- [x] **2.3 · Nodo `changes` — HECHO** (`src/agents/changes_agent.py`). Tercer corte strangler:
      la ruta `ROUTE_CHANGE` ejecuta directamente los 2 gates **pre-núcleo** (cancelación y
      reprogramación, por keyword o por señal LLM `booking_change_topic` fuera de carrito) →
      política de la KB + botones asesor/menú. Copy/estado vía `supervisor._booking_change_
      response`, **helper extraído** (refactor mecánico, preservador de comportamiento) para que
      cascada y nodo compartan una sola fuente de strings (equivalencia por construcción, sin
      duplicar). La **disponibilidad** (gate post-núcleo, ⚠️ **patrón B** del audit §1.5:
      router→changes, cascada→booking, 3/14) NO se reproduce: reproducirla sin correr el núcleo
      cambiaría la conducta → se **delega en la cascada** (equivalencia garantizada). **Decisión
      diferida al cutover (Fase 5.2):** si la disponibilidad fresca debe ganar al núcleo. **7
      tests nuevos** (3 gates aislados + delegación + equivalencia flag on/off en 3 mensajes) +
      123 verdes en la regresión ancha + 13 de cancel/reschedule/disponibilidad en conversations
      (cascada tocada por la extracción). Ruff limpio. *(dev: Álvaro)*
- [x] **2.4 · Nodo `info` — HECHO** (`src/agents/info_agent.py`). Cuarto corte strangler: la
      ruta `ROUTE_INFO` ejecuta directamente los 2 gates **pre-núcleo** — (1) elegibilidad por
      edad determinista (`_maybe_answer_age_eligibility`, respuesta desde `eligibility.py`, sin
      RAG) y (2) DIVE TO HEAL no-precio → `rag_answer` (RAG con grounding, en Python plano
      dentro del nodo). Fallback a la cascada si ningún gate dispara (resiliencia #10).
      **⚠️ Patrón A del audit §1.5 CERRADO:** añadida la rama edad→INFO a `classify_route` vía
      el predicado PURO `_looks_like_age_eligibility_question` (cue `_AGE_ELIGIBILITY_CUE` +
      número de edad presente, o edad recordada + referencia a persona), ubicado entre mixta y
      DIVE TO HEAL igual que en la cascada. Sobre-disparar es seguro (el nodo delega si el gate
      real devuelve None); quedarse corto solo mantiene el comportamiento actual sin regresión.
      **8 tests nuevos** (router edad→INFO + no-overfire + nodo aislado + equivalencia edad y
      DIVE TO HEAL) + 198 verdes en la regresión ancha (incl. router/shadow/eligibility). Ruff
      limpio. *(dev: Álvaro)* La cascada (flag off) queda intacta — el predicado nuevo solo lo
      usa el router.
- [x] **2.5 · Nodo `booking` — HECHO** (`a617151`, `src/agents/booking_agent.py`). Quinto y
      último corte strangler: la ruta `ROUTE_BOOKING` ejecuta su nodo real, que **envuelve el
      núcleo** (el "gate" de booking ES `maybe_handle_turn`). PRE-núcleo: llama a
      `maybe_handle_turn(conv, message, routing_signals=signals)` reutilizando las señales del
      router (sin doble llamada LLM), muta `conv` por referencia. POST-núcleo (resiliencia #10):
      si el núcleo devuelve `None`, delega en `_route_message_inner` — verificado que ese `None`
      solo ocurre para escalado-keyword/`wants_human` (que el router manda a SAFETY, no a
      BOOKING) y es pre-mutación, así que aquí no se dispara y sería seguro si lo hiciera.
      **Partir el núcleo en subgrafo es Fase 3.3, NO 2.5** (el nodo envolvente basta).
      **Fix pre-router** (destapado por el corte): la cascada, en la cabecera de
      `_route_message_inner` antes de cualquier gate, ejecuta 2 side-effects — restart de
      escenario nuevo (§4.bis "antes del router") + detección sticky de niños. Como los nodos
      reales ya no delegan toda la cascada, se perdían con el flag on (bug:
      `kids_mention_detected` no se activaba) → reproducidos en el nodo `router` para las 5
      rutas. **6 tests nuevos.** *(dev: Gadea)*
- [x] **2.6 · El grafo despacha a nodos reales — HECHO** (con 2.5). Los 5 nodos de `_REAL_NODES`
      son reales (deflection/escalation/changes/info/booking); el grafo (flag on) ya no delega
      en la cascada por defecto (`_make_legacy_delegate_node` queda solo como red de resiliencia
      por si se añade una ruta sin nodo). **Suite COMPLETA verde en los 3 modos** (default /
      `AGENT_ARCH=true` / `AGENT_ARCH_SHADOW=true`): **1490 passed / 18 skipped / 0 failed**.
      Verificado en vivo (LLM real): respuesta idéntica flag on vs off.
- **DoD cumplido:** con `agent_arch` on, cada ruta va a **su** nodo; conducta idéntica (suite
  verde on/off + smoke en vivo); off = cascada legacy intacta. **Fase 2 completa.**

#### 🤝 HANDOFF (2026-07-30, Álvaro → Gadea) — patrón de nodo Fase 2 y siguiente paso (2.5)

**Estado:** 4 de 5 nodos reales hechos y pusheados a `origin/feature/agent-arch` (commits
`6a70d7f` deflection, `7e9ff05` escalation, `36b7da2` changes, `20c4a69` info). Base verde,
reproducible. **Siguiente: 2.5 (nodo `booking`), luego 2.6.** Sigue este patrón exacto:

**El patrón "corte strangler" (replicado idéntico en 2.1–2.4):**
1. **Un fichero por nodo** en `src/agents/<ruta>_agent.py`, función `async def <ruta>_node(state:
   BotState) -> dict`. Devuelve `{"reply": ...}`. Muta `conv_state` **por referencia** (igual
   que la cascada: `step`, `history`, `quick_replies`, flags). Imports de `supervisor`
   **perezosos** dentro de la función (rompe el ciclo; migran a módulo propio en Fase 3).
2. **Clasifica cada gate de la ruta por su posición respecto al núcleo** (`maybe_handle_turn`):
   - **PRE-núcleo** (predicado puro, antes de `maybe_handle_turn` en la cascada) → **reprodúcelo
     directamente** en el nodo, en el MISMO orden y con el MISMO efecto de estado que la cascada.
     Reusa los helpers existentes de `supervisor` para el copy; si el copy está inline y lo
     necesitan los dos, **extráelo a un helper compartido** (refactor mecánico preservador — ver
     `_booking_change_response` en 2.3). Nunca dupliques strings.
   - **POST-núcleo** (el gate está DESPUÉS de `maybe_handle_turn`) → **NO lo reproduzcas**:
     `return {"reply": await _route_message_inner(conv, message, routing_signals=signals)}`.
     Correrlo sin el núcleo cambiaría el orden. Delegar preserva la equivalencia exacta.
3. **Fallback de resiliencia (#10):** el caso por defecto SIEMPRE delega en la cascada, nunca
   dropea el turno.
4. **Wire** en `src/orchestration/graph.py`: añade `ROUTE_X: <ruta>_node` a `_REAL_NODES`.
5. **Tests** en `tests/test_<ruta>_agent.py`: (a) nodo aislado por gate, (b) equivalencia
   `agent_arch` off==on parametrizada, con `detect_routing_signals` mockeado a `{}` para hacer
   los detectores deterministas. Para respuestas no-deterministas (RAG/LLM), mockea el binding
   compartido (`supervisor.rag_answer`) a un valor fijo — así la igualdad prueba el enrutado, no
   la (no-)determinación del LLM (ver `test_info_agent.py`).
6. **Cierre:** compileall + `ruff check` + regresión ancha (orquestación/router/shadow/agentes +
   los tests de conversations del área tocada) + **normaliza CRLF→LF** de los ficheros nuevos
   (`git diff -w` para ver el cambio real; ver memoria "Repo line endings"). Commit con
   `git commit -F -` + heredoc (NO `@'...'@`: la Bash tool es Git Bash, no PowerShell) +
   `Co-Authored-By`. Push a `feature/agent-arch`. Marca el checkbox `[x]` + entrada en el
   Registro de ejecución. **Para y avisa al owner** tras cada nodo (protocolo de pasos pequeños).

**Nota 2.5 (`booking`, el núcleo) — es el salto grande:**
- El "gate" de booking en la cascada ES `maybe_handle_turn` (líneas ~2165-2172, marca
  `ROUTE_BOOKING`) + los handlers post-núcleo que hoy delegan (idioma, bare-affirmation, y todo
  lo que cae al default). El nodo booking es el que envuelve el núcleo de verdad.
- **Recomendación pragmática:** el primer corte de 2.5 puede ser un nodo que llame directamente
  a `conversational_core.maybe_handle_turn(conv, message, routing_signals=signals)` y, si
  devuelve `None` (clases que la cascada resuelve DESPUÉS: idioma/escalado-keyword/etc.),
  **delegue en `_route_message_inner`** — mismo patrón PRE/POST. Eso da la equivalencia y "mueve"
  la ruta a su nodo sin partir aún el monolito.
- **Partir el núcleo en el subgrafo LangGraph** (routing interno → extracción → slot-fill →
  cierre determinista) es **Fase 3.3**, no 2.5. No lo adelantes: 2.5 solo necesita el nodo
  envolvente equivalente. Así 2.6 (despacho a nodos reales, flag on, suite verde on/off) queda
  listo con los 5 nodos.
- **Ojo divergencias documentadas (audit §1.5) que se resuelven en el cutover (Fase 5.2), NO en
  2.5:** disponibilidad fresca (patrón B, hoy la intercepta el núcleo→booking) y la afirmación
  que acepta oferta de asesor. En 2.5 se preservan delegando; no cambies su conducta todavía.

### Fase 3 — Consolidar las redes LLM y los prompts por nodo · *la sustancia (patrón IBM)*
- [ ] **3.1 · Reubicar las redes.** Cada red LLM global → su nodo: `fill_gaps`/
      `detect_special_signals`/`resolve_slot_answer` → booking; `comparing_options` →
      router/info; `booking_change_topic` → changes/router; `extract_notes` → memoria.
      **Eliminar solapamientos** (una red ya no ve "todo el mensaje" fuera de su caso).
- [ ] **3.2 · Prompts específicos por caso de uso.** Cada nodo con 1 (o pocos) prompt(s)
      cortos y enfocados — no un prompt que lo abarca todo. Conservar los afinados actuales,
      reubicados y recortados a su dominio.
- [ ] **3.3 · Partir el subgrafo `booking`** en nodos de responsabilidad única: routing interno
      (deliberación/recall/pregunta-vs-reserva) → extracción → slot-fill (`next_missing_slot`)
      → cierre determinista (`cart_render`). Elimina el monolito de 2.249 líneas.
      - **3.3a · Andamiaje del subgrafo — HECHO** (`47c72cf`, Gadea). La ruta BOOKING invoca un
        subgrafo LangGraph (`booking_agent._build_booking_subgraph`) con UN nodo `core` que
        envuelve `maybe_handle_turn` — el contenedor del strangler, equivalente por construcción.
        Suite verde ambos flags (1491). Firma de `booking_node` preservada.
      - **⚠️ Hallazgo del mapeo (para el reparto del corte):** las fases de `maybe_handle_turn`
        NO son cleanly separables por el orden de efectos secundarios. El **setup** (detección de
        idioma en primer turno + `greeting` + captura de nombre + **append del mensaje del
        usuario al historial** + captura de notas) DEBE ir primero: la disponibilidad, el
        carryover, la deliberación y la extracción dependen todas de él (leen `greeting`, y las
        notas/RAG leen el historial YA con el mensaje). ⇒ **El primer nodo interno real es
        `setup`**; el `body` se extrae detrás, pasando `greeting`/`first_turn` por el estado del
        subgrafo.
      - **3.3b · Partir el núcleo en `setup` + `body` — HECHO** (`4c53d5c`, Gadea). El subgrafo
        pasa a `START → setup → (delega?END : body) → END`. `maybe_handle_turn` descompuesto en
        `_setup_phase` (→ `(greeting, first_turn)` o `None`) + `_body_phase` (disponibilidad →
        carryover → pregunta/recall → deliberación → extracción → slot-fill → cierre), llamados
        TANTO por la cascada (flag off) COMO por los nodos del subgrafo (flag on) — misma fuente
        de verdad. El `body` quedó byte-idéntico (diff `-w` solo toca firmas/docstrings/
        orquestador). **Equivalencia verificada por 3 vías**: suite verde en los 3 modos (1491),
        smoke en vivo (las diferencias flag on/off son solo no-determinismo del LLM — flag-off
        vs flag-off da el mismo patrón), y el diff no toca la lógica del body.
      - **3.3c · Peelar la disponibilidad a su nodo — HECHO** (`c6765d4`, Gadea). El subgrafo
        pasa a 3 nodos: `START → setup → availability → body → END`. `_availability_phase`
        (gate anti-alucinación de calendario) extraído de `_body_phase` como función compartida
        (la llaman cascada y subgrafo). Corte limpio de bajo riesgo: la disponibilidad es
        autocontenida (solo `greeting`, ya en el estado), sin los locales `prev_*`/
        `resolved_short` del resto. Aislarla facilita reubicar el patrón B del audit §1.5
        (disponibilidad → `changes`) en el cutover, sin tocar conducta ahora. Suite verde 3
        modos (1492), +2 tests.
      - **Siguiente (3.3d+):** partir el `body` restante en `extracción` → `slot-fill` →
        `cierre`. Estas SÍ comparten `resolved_short` + snapshots `prev_*` → hay que pasarlos
        por el estado del subgrafo (mismo patrón que `greeting`/`first_turn`). Es el resto del
        corte grande, en pasos con equivalencia por cada uno.
- [ ] **3.4 · Reducir llamadas LLM/turno.** Medir en **LangSmith** vs baseline de Fase 0.
      Documentar antes/después.
- **DoD:** llamadas LLM/turno ↓ vs baseline; cero colisiones; prompts por nodo testeados.

### Fase 4 — Estado, memoria y persistencia unificados
- [ ] **4.1 · `BotState` único.** Todos los nodos leen/escriben el mismo State; se elimina el
      estado disperso restante.
- [ ] **4.2 · Persistencia.** Decidir: **checkpointer de LangGraph** (Redis/Postgres, thread_id
      = conversation_id, trae time-travel/replay) **vs** mantener `state_store.py`. Registrar
      la decisión + migración.
- [ ] **4.3 · Grounding único + memoria/notes.** Unificar `grounding_check` + reglas
      anti-alucinación en una capa que todos los nodos atraviesan; cablear la Fase C de memoria
      (hechos abiertos) en el State; archivar `memory-context-improvement-plan.md`.
- **DoD:** estado consolidado, persistencia decidida, una capa de grounding, memoria coherente.

### Fase 5 — Test por nodo, corte del legacy y bucle de datos reales
- [ ] **5.1 · Test-harness por nodo.** Cada nodo probado en aislamiento (State in → update
      out, LLM mockeado) + el grafo compilado (integración). Reorganizar la suite por nodo.
- [ ] **5.2 · CORTE del legacy.** Con el flag probado en PRE: **quitar `agent_arch`** y borrar
      la cascada vieja del supervisor, las redes globales muertas y lo que quede de
      `ConversationState`/`Step` legacy (reachability, suite tras cada borrado). `supervisor.py`
      queda mínimo o desaparece a favor de `orchestration/`.
- [ ] **5.3 · Bucle de datos reales (Fase 6 robustez) con LangSmith.** Harvest de trazas de PRE
      → **datasets/evals de LangSmith** → dirigir refuerzos con datos reales, no edge-cases
      inventados.
- **DoD:** legacy fuera, grafo limpio, suite por nodo + e2e verde, evals de PRE fluyendo.
  **Refactor completo.**

---

## 6. Qué se descarta / se mantiene / se adapta

| | Elemento | Destino |
|---|---|---|
| 🟢 **Se mantiene** | `catalog` · `cart_render` · `eligibility` (precios/links/elegibilidad) | Intacto — Python plano dentro de nodos. La joya determinista |
| 🟢 | RAG propia (`vector_store` pgvector+BM25) + `grounding_check` | Se mantiene; **NO** se mete en retrievers de LangChain |
| 🟢 | `intent_detector` (regex de primer paso) | Capa determinista de extracción dentro del router/booking |
| 🟢 | Backstops medidos en vivo (`_in_active_cart_building`, `_has_link_tech_context`, reparto-vs-deliberación, `_EXPLICIT_NUMBER_RE`…) | Se reubican al nodo/router correspondiente |
| 🟢 | Suite de tests + eval-sets · LangSmith (ya configurado) | Red de seguridad + observabilidad/evals |
| 🟡 **Se adapta** | `escalation.py` · `rag_agent.py` · `conversational_core.py` | Se envuelven como nodos; booking se parte en subgrafo (Fase 3) |
| 🟡 | `ConversationState` → `BotState` | Se sanea (Fase 0) y se convierte en TypedDict de LangGraph |
| 🟡 | `state_store.py` (Redis) | Se mantiene o se sustituye por checkpointer LangGraph (Fase 4.2) |
| 🔴 **Se descarta** | La cascada de 14 `if` del supervisor | → grafo LangGraph + router |
| 🔴 | Redes LLM globales solapadas | → llamadas por-nodo enfocadas |
| 🔴 | Campos `mixed_*` y `Step.*` legacy muertos | Borrados (Fase 0.2) |
| 🔴 | Shim `decision_tree` + vestigio `DecisionTree` | Reapuntar importadores y borrar (Fase 0.3) |

---

## 7. Riesgos y mitigaciones

- **Refactor grande con 3 devs** → strangler tras flag + este MD como verdad + un merge = una
  unidad verde. Nadie mergea rojo.
- **Romper conducta probada** → la suite es el invariante (verde on/off) + shadow de
  equivalencia del router antes de cortar el legacy.
- **Sobre-ingeniería con LangChain** → **LangGraph sí; LangChain con moderación**; la
  RAG/grounding/catálogo se quedan en Python plano dentro de nodos, nunca en abstracciones de
  LangChain.
- **Curva de aprendizaje LangGraph (3 devs)** → PoC en Fase 0 + vocabulario estándar con doc
  oficial.
- **Migración de tests (monkeypatch → nodos)** → se planifica en Fase 5; nodos = funciones
  testeables en aislamiento.
- **Latencia/coste** → medidos en LangSmith (Fase 0 baseline → Fase 3), no de oído.
- **Churn de versiones de LangGraph/LangChain** → fijar versiones en `pyproject`; actualizar
  deliberadamente, no en automático.

---

## 8. Registro de ejecución
*(Una línea por paso cerrado: fecha · dev · qué · commit. El más reciente arriba.)*

- **2026-07-30 · Gadea · Fase 3.3a/b/c — corte del núcleo (subgrafo booking, en curso).**
  Arrancado el corte del monolito del núcleo (~2.249 líneas) en un subgrafo LangGraph, con
  strangler y equivalencia por construcción (cascada y subgrafo llaman a las MISMAS funciones
  extraídas). **3.3a** (`47c72cf`): andamiaje — la ruta BOOKING invoca un subgrafo que envuelve
  el núcleo (1 nodo `core`). **3.3b** (`4c53d5c`): `maybe_handle_turn` descompuesto en
  `_setup_phase` + `_body_phase` → subgrafo de 2 nodos (`setup`/`body`); equivalencia verificada
  por 3 vías (suite 3 modos, smoke en vivo donde las diferencias flag on/off son solo
  no-determinismo del LLM confirmado por off-vs-off, y el diff no toca la lógica del body).
  **3.3c** (`c6765d4`): disponibilidad peelada a `_availability_phase` → subgrafo de 3 nodos
  (`setup → availability → body`); corte de bajo riesgo (autocontenido, solo `greeting`).
  Suite verde en los 3 modos tras cada paso (1491→1492). **NOTA patrón B (audit §1.5):** la
  disponibilidad se AISLÓ en su nodo pero SIGUE en booking con la misma conducta — no se movió
  a `changes`; eso es decisión del cutover (Fase 5.2). **Siguiente: 3.3d** (partir el `body`
  restante en extracción/slot-fill/cierre; comparten `prev_*`/`resolved_short`).
- **2026-07-30 · Gadea · Fase 2.5+2.6 — FASE 2 COMPLETA** (`a617151`). Nodo `booking` real
  (quinto y último corte strangler): la ruta BOOKING ejecuta su nodo, que **envuelve el núcleo**
  (`maybe_handle_turn`, reutilizando las señales del router; delega en la cascada si el núcleo
  devuelve None — resiliencia #10, caso que no ocurre para tráfico BOOKING). `src/agents/
  booking_agent.py` + wire en `graph.py` (`_REAL_NODES`, ahora 5/5 nodos reales → 2.6). **Fix
  pre-router**: los side-effects de la cabecera de la cascada (restart de escenario nuevo +
  detección sticky de niños) se perdían con el flag on al dejar de delegar toda la cascada
  (bug: `kids_mention_detected`); reproducidos en el nodo `router` para las 5 rutas. Partir el
  núcleo en subgrafo es Fase 3.3, no aquí. 6 tests nuevos. **Equivalencia**: suite verde en los
  3 modos (default/grafo/shadow) — **1490 passed / 18 skipped / 0 failed**; smoke en vivo (LLM
  real) idéntico flag on vs off. ruff + compileall limpios. **Siguiente: Fase 3.**
- **2026-07-30 · Álvaro · Fase 2.4** — Nodo `info` real (cuarto corte strangler): la ruta INFO
  ejecuta edad determinista (`_maybe_answer_age_eligibility`) + DIVE TO HEAL no-precio (RAG en
  Python plano). **Cerrado el patrón A del audit §1.5**: rama edad→INFO en `classify_route` vía
  el predicado puro `_looks_like_age_eligibility_question`. `src/agents/info_agent.py` +
  predicado en `supervisor.py` + rama en `router.py` + wire en `graph.py`. 8 tests nuevos; 198
  verdes en la regresión ancha (incl. router/shadow/eligibility); ruff limpio. Cascada intacta.
- **2026-07-30 · Álvaro · Fase 2.3** — Nodo `changes` real (tercer corte strangler): la ruta
  CHANGE ejecuta directamente cancelación + reprogramación (pre-núcleo) vía el helper compartido
  `_booking_change_response` (extraído de la cascada, refactor preservador); la disponibilidad
  (post-núcleo, patrón B) delega en la cascada. `src/agents/changes_agent.py` + helper en
  `supervisor.py` + wire en `graph.py`. 7 tests nuevos; 123 verdes en la regresión ancha + 13 de
  conversations; ruff limpio. Decisión de disponibilidad vs núcleo diferida al cutover (5.2).
- **2026-07-30 · Álvaro · Fase 2.2** — Nodo `escalation` real (segundo corte strangler): la ruta
  SAFETY ejecuta directamente los 6 gates pre-núcleo (PII, link roto kw+señal, sensible
  kw+señal, DIVE TO HEAL precio→asesor); los gates post-núcleo (wants_human/keyword) delegan en
  la cascada para preservar el orden respecto al núcleo. `src/agents/escalation_agent.py` +
  wire en `graph.py`. 11 tests nuevos; 116 verdes en la regresión ancha; ruff limpio. Audit del
  shadow: 0 mismatches en SAFETY.
- **2026-07-30 · Álvaro · Fase 2.1** — Nodo `deflection` real (primer corte strangler): la ruta
  DEFLECT ejecuta solo la lógica de deflexión (contacto + identidad IA), no toda la cascada.
  `src/agents/deflection_agent.py` + wire en `graph.py` (`_REAL_NODES`). 8 tests nuevos
  (aislado + equivalencia flag on/off); 43 verdes en orquestación/grafo/router/shadow; ruff
  limpio. Equivalencia probada (grafo == cascada para mensajes de deflexión).

- **2026-07-30 · Álvaro · Revisión de asentamiento (sign-off Fase 0+1)** — Merge del trabajo
  de Gadea (fast-forward a `f04ffde`). Revisión de cabos sueltos: **ninguno**. Ruff limpio;
  deps pineadas + `requirements-lock.txt` presente; LangGraph 1.x verificado sin breaking
  changes (spike); docs (plan/registro/handoff) consistentes; orquestación limpia (340 líneas,
  estructura strangler correcta). Ítems abiertos = diferidos y documentados (edad→INFO en 2.4,
  disponibilidad en 5.2, checkpointer/safety-prenodo en 4.x). Suite completa en mi máquina:
  **1449 passed / 18 skipped / 1 flaky** → el flaky (`test_route_shadow::test_shadow_does_not_
  change_reply`) era otro test infra-aislado (comparaba dos respuestas a "hola" que dependen
  del LLM del núcleo sin mockear); arreglado mockeando los LLM del núcleo → determinista 5/5.
  (Los 18 skips vs 9 de Gadea son env-dependientes, no fallos.) **Fase 1 revisada y aprobada —
  despejado el arranque de Fase 2.** Contrato de nodo 2.0 = **ya fijado por el spike** (`async def
  node(state: BotState) -> dict | Command`; handoffs `Command(goto=)`; reply en `state["reply"]`;
  conv_state por referencia) — no requiere código nuevo, solo seguirlo.

- **2026-07-29 · Gadea · Fase 1 COMPLETA** (`db69308` 1.1 · `2c6d042` 1.2 · `e6d8de2` 1.3+1.4
  · `c2ed174` 1.5). Grafo LangGraph esqueleto: `BotState` (transporta el `ConversationState`
  vivo durante el strangler), router `classify_route` (enrutado intencional §4.bis, reúsa los
  detectores reales), `graph.py` (`StateGraph`: router → conditional edges → 5 nodos-wrapper
  que delegan en `_route_message_inner`), cableado en `route_message` tras `settings.agent_arch`
  (off=cascada, on=grafo), y shadow del router (`agent_arch_shadow`, ContextVar `_mark_route`
  en cada gate → `[ROUTE_SHADOW] match|MISMATCH`). Refactor: `_route_message_inner` acepta
  `routing_signals` opcional (una sola llamada LLM/turno). Retirado el PoC de 0.5. **Prueba de
  equivalencia**: suite COMPLETA verde en las 3 configuraciones (default / `AGENT_ARCH=true` /
  `AGENT_ARCH_SHADOW=true`) — **1459 passed / 9 skipped / 0 failed**. 38 tests nuevos. Verificado
  en vivo (LLM real): respuesta idéntica on/off, shadow 6/6 match. **Pendientes anotados**: (a)
  medir el shadow sobre tráfico real de PRE (encender `agent_arch_shadow` allí); (b) refinamientos
  diferidos que NO bloquean el DoD — `safety` como pre-nodo explícito y el `checkpointer` (Fase
  4.2). **Siguiente: Fase 2** (nodos-agente reales), pendiente de revisión del equipo.
- **2026-07-29 · Gadea · Fase 0.6** (`a747bb4`) — spike de diseño escrito:
  `docs/agent-arch-design.md`. Cubre los 6 puntos del plan (State+reducers, router
  con `add_conditional_edges`, handoffs `Command(goto=)`, subgrafo booking,
  checkpointer candidato, mock de nodos en tests). **Nada de memoria**: cada patrón
  de código (router+conditional-edges, Command handoff) se verificó ejecutando
  scripts ad-hoc contra el `langgraph==1.2.9` real instalado; `StateGraph.add_node`/
  `add_conditional_edges`/`compile` inspeccionados por firma. Confirmado por
  búsqueda web (fuentes citadas en el doc): **LangGraph 1.0 no tiene breaking
  changes** relevantes para este plan (solo deprecia el *prebuilt* `create_react_
  agent`, que no usamos). **Hallazgo de seguridad real** para anotar de cara a la
  Fase 4.2: vulnerabilidad SQLi→RCE en checkpointers de LangGraph
  (`langgraph-checkpoint-sqlite<3.0.1`/`langgraph<1.0.10`/`langgraph-checkpoint-
  redis<1.0.2`, dispara solo si se expone `get_state_history` con filtro sin
  sanitizar sobre SQLite/Redis) — ya estamos a salvo (`langgraph 1.2.9`), documentado
  para cuando se decida el checkpointer. Recomendación del spike: mantener
  `state_store.py` (mapeando `BotState`) en vez de adoptar un checkpointer nuevo,
  salvo que el equipo quiera time-travel/replay. **Fase 0 completa** — pendiente la
  revisión humana del documento por Álvaro/Gonzalo antes de arrancar Fase 1.
- **2026-07-29 · Gadea · Fase 0.5** (`559450d`) — LangGraph instalado de verdad: las deps
  ya estaban en el entorno, resueltas a **1.x** (`langgraph 1.2.9`, `langchain 1.3.14`,
  `langchain-openai 1.4.1`, `langchain-community 0.4.2`, `langsmith 0.10.10` — salto mayor
  vs. los `>=0.3/0.4` declarados). Pineadas a exacto en `pyproject.toml` (sin conflictos,
  `pip check` limpio) + `requirements-lock.txt` (snapshot completo, `pip freeze` — el
  proyecto usa pip, no uv/poetry). **PoC**: `src/orchestration/poc_graph.py`, grafo de 2
  nodos (uppercase → reply), sin checkpointer, cableado en `supervisor.route_message`
  detrás de `settings.agent_arch` (default `False`) como side-channel puro. Validado en
  vivo (LLM/Postgres/Redis reales): con el flag on la respuesta es idéntica a con el flag
  off para el mismo mensaje; el log del PoC sale antes del cascade real. 4 tests nuevos
  (default off, no-invoca-si-off, no-cambia-respuesta-si-on, resiliente a fallo del grafo).
  Suite 1425 passed / 9 skipped / 0 failed, ruff + compileall limpios. **Nota para el
  equipo**: el salto 0.x→1.x de LangGraph/LangChain es grande — revisar release notes antes
  de construir el grafo real en Fase 1 (algunas APIs de 0.x-gen pueden haber cambiado).
  Siguiente: **0.6** (spike de diseño `docs/agent-arch-design.md`).
- **2026-07-29 · Gadea · Fase 0.4** (`2071643`) — LangSmith activado (env vars
  `LANGSMITH_*` propagadas desde `Settings`, no-op sin API key — no hay una en este
  entorno dev) + baseline local de métricas LLM/turno vía
  `scripts/measure_llm_baseline.py` (parchea `AsyncCompletions.create`/
  `AsyncEmbeddings.create` a nivel de clase, sin tocar producción). Guion de 5 turnos
  contra el bot real: **15 llamadas LLM / 3.00 por turno · 23.71s / 4.74s por turno ·
  23 554 tokens prompt + 455 completion · $0.0038 estimado**, todas `gpt-4o-mini`.
  Tabla completa en §5 Fase 0.4. Es el número que dirige la Fase 3 (bajar
  llamadas/turno al consolidar redes por nodo). Suite 1421 passed / 9 skipped /
  0 failed, ruff limpio. **Pendiente real**: repetir con LangSmith cuando haya
  `LANGSMITH_API_KEY`, para comparar trazas reales contra esta baseline local.
  Siguiente: **0.5** (instalar LangGraph + PoC de 2 nodos + flag `agent_arch`).
- **2026-07-29 · Gadea · Fase 0.3** — shim `decision_tree` cerrado. **0.3a** (`24c7c77`):
  ~34 importadores (7 en `src/`, resto tests/scripts) reapuntados a `catalog`/`state`/
  `messages` (incluidos 2 imports inline afectados por monkeypatch en
  `conversational_core.py` + sus 2 targets en `test_conversational_core.py`,
  redirigidos a `src.flows.catalog`); `src/flows/decision_tree.py` borrado (0
  importadores restantes). **0.3b** (`10175ca`): vestigio `DecisionTree` (sin estado
  propio, solo `set_quick_replies` + `_CART_MENU_KEYS`) convertido en función de
  módulo `set_quick_replies(state, key)` en `messages.py`; `supervisor.py` pierde el
  singleton `decision_tree = DecisionTree()`. Auditoría de imports huérfanos por diff
  (`git stash` antes/después de 0.3a): ruff da los mismos 170 errores en los mismos
  archivos — deuda preexistente ajena (E402/F841/I001 en scripts/tests no tocados),
  cero regresiones; no se usó `ruff --fix`. Suite 1421 passed / 9 skipped / 0 failed
  en cada sub-paso. También actualizado `docs/future/decision-tree-reorg.md` (el
  pendiente opcional de §1 queda cerrado). **Fase 0.3 CERRADA.** Siguiente: **0.4**
  (encender LangSmith + baseline de métricas).
- **2026-07-29 · Gadea · Fase 0.2b-ii** — `messages.py` podado 1517→80 líneas.
  `MESSAGES` 60→2 claves (escalate/main_menu), `BUTTON_OPTIONS` 40→1 clave (main_menu),
  borrados los 3 métodos de isla muertos de `DecisionTree` + las 3 ramas de
  `set_quick_replies` que solo ellos alimentaban (condiciones nunca alcanzables — el único
  caller real, `supervisor.py:2214/2221`, siempre pasa `key="main_menu"`); también la rama
  `mixed_add_activity`/`mixed_entry_path` (su key ya no existe en `BUTTON_OPTIONS`, quedaba
  en no-op). `set_quick_replies` queda en un solo camino. Suite 1421 passed / 9 skipped /
  0 failed (idéntica a 0.2b-i). ruff + compileall limpios. Commit `fbeff5c`. **Fase 0.2b
  CERRADA.** Siguiente: **0.3** (cerrar shim `decision_tree` + imports huérfanos).
- **2026-07-29 · Gadea · Fase 0.2b-i** — enum `Step` podado 43→5 valores
  (quedan WELCOME/LANGUAGE/MAIN_MENU/ESCALATE/FREE_TEXT); quitados RESERVA_MENU/
  INFO_MENU/BOOKING_MENU de `supervisor._INTENT_TRIGGER_STEPS`; actualizado
  `test_state_store` (PRICING_MENU→MAIN_MENU) y borrados 3 helpers muertos de
  `test_conversations` (`reach_pricing_menu`/`reach_booking_menu`/
  `reach_logistics_menu`, 0 llamadas). Suite 1421 passed / 9 skipped / 0 failed
  (mismo total 1430 que baseline; diferencia de skips es de entorno, no del
  cambio). ruff limpio. Commit `b8f8d43`. **Siguiente: 0.2b-ii** (poda de
  `messages.py`, ~1500→~150 líneas) — paso grande, pendiente de confirmar
  antes de ejecutar (protocolo §3).
- **2026-07-29 · Álvaro · Fase 0.2a** — 13 campos `mixed_*` muertos borrados de
  `ConversationState` (75→62), suite idéntica al baseline (1412). Reachability completa de
  0.2b hecha y scopeada (Step enum + poda de `messages.py`, listas exactas en §5 Fase 0.2b).
  Commit `5d7c890`.
- **2026-07-29 · Álvaro · Fase 0.1** — Baseline congelado en `feature/agent-arch`:
  **1412 passed / 18 skipped / 0 failed**. Arreglado el único fallo (`test_gap_fill_logs_in_
  harvester_format`, test infra-aislado — mockeado `detect_routing_signals`). Rama creada +
  plan maestro committeado (`a56fa60`).

---

## 9. Anexos

- **Arquitectura visual:** `arquitectura-diving-planet-bot.html` (raíz del repo).
- **Runtime actual (referencia):** `_route_message_inner` (cascada de 14 gates, `supervisor.py`)
  → `conversational_core.maybe_handle_turn` (slot-loop) → `cart_render` / `rag_agent` / escalado.
- **Redes LLM hoy (Fase 0.4 las medirá en LangSmith):** `detect_routing_signals` (9 señales) ·
  `fill_gaps` · `detect_special_signals` · `resolve_slot_answer` · `compose_acknowledgement` ·
  `extract_notes` · `condense_query` · RAG + `is_grounded` · `detect_language_llm` ·
  `maybe_update_summary`.
- **Deps ya declaradas (pyproject, sin usar hoy):** `langgraph>=0.4` · `langchain>=0.3` ·
  `langchain-openai>=0.3` · `langchain-community>=0.3` · `langsmith>=0.3`.
- **Docs relacionados:** `session-handoff.md` (historia) · `future/decision-tree-reorg.md`
  (reorg/limpieza) · `robustness/plan.md` (bucle de datos = Fase 5.3) ·
  `archive/memory-context-improvement-plan.md` (notes = Fase 4.3).
