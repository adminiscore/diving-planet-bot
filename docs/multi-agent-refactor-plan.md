# Plan de refactorización — a un sistema multiagente sobre LangGraph

> **Fuente de verdad del refactor.** Los 3 desarrolladores (Álvaro, Gadea, Gonzalo)
> trabajamos contra este documento. Cada paso tiene checkbox; al cerrarlo se marca `[x]`
> y se añade una línea al **Registro de ejecución** (final). Si una sesión se corta o
> alguien retoma tras un merge, **el estado de los checkboxes aquí es la única verdad**.
> Acompaña (no sustituye) a `docs/project-history/session-handoff.md`.

**Estado global:** `Fase 0 — en curso` (0.1/0.2a/0.2b/0.3 hechos; siguiente 0.4). Creado 2026-07-29.
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
- [ ] **0.2 · LIMPIEZA del estado (`ConversationState` + `Step`).** Borrar por reachability los
      campos `mixed_*` y valores `Step.*` muertos tras Fase 4. **Análisis de reachability hecho
      (2026-07-29):**
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
- [ ] **0.4 · Encender LangSmith + baseline de métricas.** Activar tracing (ya configurado) y
      medir sobre un guion representativo: **nº de llamadas LLM, latencia, tokens/coste por
      turno**. Tabla en el Registro — es el número que dirige la Fase 3.
- [ ] **0.5 · Instalar de verdad LangGraph + PoC de-risk.** `uv/pip install` de las deps ya
      declaradas; un **grafo trivial de 2 nodos** corriendo dentro de la app (un turno real lo
      atraviesa detrás del flag off) para validar versión/integración/Chatwoot. Flag
      `settings.agent_arch` (default `False`). Fijar versiones en `pyproject` + lockfile
      committeado (reproducibilidad).
- [ ] **0.6 · Spike de diseño LangGraph** ("investigar qué necesitamos y cómo", pedido del
      owner). Documento corto (`docs/agent-arch-design.md`) que fija, con la doc oficial: el
      patrón de State + reducers, cómo se hace el router con `add_conditional_edges`, los
      handoffs con `Command(goto=)`, el subgrafo del booking, el checkpointer candidato, y cómo
      se mockea un nodo en tests. Es el "cómo" técnico que desbloquea las Fases 1-2 sin
      improvisar. Revisado por los 3.
- **DoD:** estado limpio + shim fuera + LangSmith midiendo baseline + LangGraph instalado y
  PoC verde + flag + spike de diseño acordado. **Nadie cambió comportamiento.**

### Fase 1 — El grafo esqueleto + el Router · *misma conducta, estructura de grafo*
- [ ] **1.1 · `BotState`.** Definir el State schema (TypedDict + reducers) mapeando desde el
      `ConversationState` saneado. `serialize`/`deserialize` ⇄ Redis conservados.
- [ ] **1.2 · Nodo `router`.** Clasificador **determinista-primero** (reusa keyword lists +
      detectores actuales: `_detect_cancellation_request`, `_asks_for_contact_number`,
      `_AVAILABILITY_PATTERN`, `detect_sensitive_escalation`, `_ADAPTIVE_DIVING_PATTERN`…) +
      `detect_routing_signals` (LLM) de respaldo → fija `state["route"]` (SAFETY/BOOKING/INFO/
      CHANGE/DEFLECT). Hereda los backstops (`_in_active_cart_building`, `_has_link_tech_context`,
      reparto-vs-deliberación).
- [ ] **1.3 · `graph.py` esqueleto.** `StateGraph(BotState)` con: `START → safety → router →
      add_conditional_edges → (nodos, inicialmente wrappers finos que llaman a los handlers
      ACTUALES) → save → END`. `compile(checkpointer=…)`.
- [ ] **1.4 · Cablear detrás del flag (strangler).** `agent_arch` off → cascada actual intacta.
      On → `graph.ainvoke(state)`. Los nodos aún delegan en la lógica actual (no agentes
      todavía) — valida el **grafo y el router** sin tocar los agentes.
- [ ] **1.5 · Shadow + equivalencia.** Con flag off, correr también el router y **loggear
      discrepancias** de ruta vs la cascada, sobre la suite y tráfico PRE (≥99% coincidencia;
      las discrepancias reales = bugs de la cascada a documentar). Suite verde on **y** off.
- **DoD:** un turno real atraviesa el grafo con flag on y responde igual que la cascada;
  discrepancias auditadas. **La cascada sigue viva.**

### Fase 2 — Los nodos-agente con contrato · *paralelizable entre los 3*
- [ ] **2.0 · Contrato de nodo + orquestador.** Fijar la firma de nodo (State→update),
      `Command`/handoffs, y el manejo del resultado (reply/quick_replies/escalate). Secuencial,
      va primero.
- [ ] **2.1 · Nodo `deflection`** (contacto · identidad IA · off-topic/OWASP). El más aislado.
      *(dev: —)*
- [ ] **2.2 · Nodo `escalation`** (PII · médico · quejas · DIVE TO HEAL · humano vía
      `interrupt`). Envuelve `escalation.py` + `SENSITIVE_RULES`. *(dev: —)*
- [ ] **2.3 · Nodo `changes`** (cancelar · reprogramar · disponibilidad) — 3 gates → 1 nodo.
      *(dev: —)*
- [ ] **2.4 · Nodo `info`** (RAG + grounding) — envuelve `rag_agent`; la RAG queda en Python
      plano dentro del nodo. *(dev: —)*
- [ ] **2.5 · Nodo `booking`** (el núcleo) — como **subgrafo** LangGraph (el slot-fill loop +
      multi-ítem). El más grande, el último. *(dev: —)*
- [ ] **2.6 · El grafo despacha a nodos reales** (flag on). Suite verde tras cada uno, on/off.
- **DoD:** con `agent_arch` on, cada ruta va a **su** nodo; conducta idéntica; off = legacy.

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
