# Plan de refactorización — a un sistema multiagente sobre LangGraph

> **Fuente de verdad del refactor.** Los 3 desarrolladores (Álvaro, Gadea, Gonzalo)
> trabajamos contra este documento. Cada paso tiene checkbox; al cerrarlo se marca `[x]`
> y se añade una línea al **Registro de ejecución** (final). Si una sesión se corta o
> alguien retoma tras un merge, **el estado de los checkboxes aquí es la única verdad**.
> Acompaña (no sustituye) a `docs/project-history/session-handoff.md`.

**Estado global:** `Fase 0/1/2/3/4 completas · Fase 5 en curso (5.1 hecha · 5.2 paso 1 · 5.3
midiendo)`. ✅ **Grafo en PRE, validado en vivo, con LangSmith trazando** (`AGENT_ARCH=true`,
`feature/pre_alvaro`). El **periodo de medición del rollout está ABIERTO** (trazas reales →
`diving-planet-bot`). Retirado el subsistema shadow (5.2 paso 1) + LangSmith trazando grafo **y por-llamada**
(`trace_openai`). **⏳ AHORA EN SOAK** (Fase 5.3-bis, ver §5): reposo multi-día para acumular
tráfico real; el corte del flag (resto de 5.2) espera a que la medición dé "igual o mejor" vs
baseline de Fase 0.4. Rollback hasta el corte = apagar `agent_arch`. Nota: Fase 4 se cerró como **confirmar+documentar** (reencuadre aprobado) — el
estado ya estaba consolidado en `ConversationState`, el grounding centralizado en `rag_answer`, y
la memoria Fase C cableada en el State; sin big-bang. Grafo LangGraph detrás de `agent_arch`; **los 5 nodos son REALES**
(deflection/escalation/changes/info/booking, cortes strangler 2.1–2.5) y el grafo (flag on)
despacha cada ruta a su nodo sin delegar en la cascada. El nodo `booking` es ya un **subgrafo de
5 fases** (`setup → availability → routing → extraction → slotfill_close`, 3.3) y **los prompts
viven en `src/prompts/`, un módulo por nodo** (3.2). Equivalencia probada tras cada paso: suite
verde en los 3 modos (default/grafo/shadow) — **1492 passed / 18 skipped** medidos en el cierre
de 3.3; la pasada de 3.2 (con sus 27 tests nuevos) estaba en vuelo al commitear, ver §8. La
cascada (flag off) sigue viva. **Siguiente: 3.4** (medir llamadas LLM/turno vs baseline — hoy bloqueado por
entorno, ver el paso) y luego **Fase 4** (estado/memoria/persistencia unificados). Creado
2026-07-29; actualizado 2026-07-30.
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
  prompts/                ← PROMPTS como artefacto de primera clase (patrón IBM) — HECHO (3.2)
    __init__.py             índice: tabla prompt→nodo + reglas del paquete
    router.py               señales de enrutado (prompt + tool schema)
    booking.py              idioma · extracción · señales de turno · resolutor de slot · acuse
    info.py                 reescritura de query · persona/seguridad/reglas RAG · grounding
    memory.py               notes (hechos abiertos) · resumen rodante
                            (hoja del grafo de imports: NO importa nada de src/)
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
- [x] **2.0 · Contrato de nodo + orquestador — HECHO** (sin código propio: lo fijó el spike de
      0.6, ver la entrada de revisión de asentamiento en §8). Firma
      `async def node(state: BotState) -> dict | Command`; handoffs con `Command(goto=)`; la
      respuesta va en `state["reply"]`; el `conv_state` viaja por referencia. Los 5 nodos de
      2.1-2.5 lo siguen; el checkbox quedó sin marcar por despiste al cerrar la fase.
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
- [x] **3.1 · Reubicar las redes — HECHO (funcional; reubicación física diferida)** (docs,
      Gadea). **Hallazgo:** el corte del núcleo (3.3) YA dejó cada red llamándose desde su nodo
      dueño — el objetivo funcional de 3.1 está conseguido. Auditado y documentado el **mapa
      red→nodo** en `docs/agent-arch-design.md` §7: `fill_gaps`/`detect_special_signals`/
      `resolve_slot_answer`/`compose_acknowledgement` → booking (extraction/routing/slotfill);
      `detect_routing_signals` → router (1 llamada/turno, señales consumidas por nodo);
      `extract_notes`/`detect_language_llm` → setup de booking; `condense_query`/RAG → info;
      `maybe_update_summary` → cross-cutting. **Solapamientos auditados:** ninguno problemático
      — los que motivaron el refactor (§0) están estructuralmente contenidos (router computa
      señales una vez → `classify_route`; cada caso en su nodo). Únicos cross-node: `detect_
      routing_signals` (compartida a propósito) y `fill_gaps` en el cutover legacy (subsistema
      flagged off, NO tocar). **Diferido:** mover las definiciones a `src/agents/_nets/`
      (reapuntar imports de core/supervisor/tests) — churn mecánico de valor solo organizativo,
      a hacer deliberadamente, no como cierre de sesión.
- [x] **3.2 · Prompts específicos por caso de uso — HECHO** (Gonzalo). Nuevo paquete
      **`src/prompts/`** (§4 del plan): un módulo por nodo dueño — `router.py`, `booking.py`,
      `info.py`, `memory.py` — más un `__init__.py` que es el índice (tabla prompt→nodo +
      las reglas del paquete). Movidos **25 símbolos** desde 8 módulos de `src/agents/` = los
      **11 prompts** del bot (unos como constante por idioma, otros como builder que interpola
      argumentos) + los 4 tool-schemas estáticos + la factoría `slot_resolver_tool` + el
      `SLOT_RESOLVER_SPEC`.
      - **Hallazgo (por qué NO se "recortó" nada):** el enunciado original de 3.2 asumía un
        prompt gigante que lo abarcaba todo. **No lo hay**: cada red ya tenía SU prompt corto
        y enfocado a un caso de uso; lo que faltaba era que vivieran *enterrados* dentro de
        módulos de lógica de 900-1300 líneas, imposibles de revisar de un golpe. 3.2 es por
        tanto **reubicar y hacer revisable**, no reescribir. Recortar texto = cambio de
        conducta (principio #1) y no había nada multi-caso que recortar: el único prompt que
        cubre varios casos es el del router (9 señales) y es **compartido a propósito**
        (§7 de `agent-arch-design.md`, 1 llamada/turno).
      - **El tool schema cuenta como prompt** y se movió con él: las descripciones de campo son
        instrucción real para el modelo — varias se afinaron midiendo en vivo (p. ej. el caso
        negativo del plural vago en `group_size`, v0.20.55; la nota de por qué se descartó
        strict function-calling). Ahora prompt + schema se leen juntos, que es como se revisan.
      - **`src/prompts/` es una HOJA del grafo de imports** (no importa nada de `src/`): así un
        prompt se lee/diffea sin arrastrar el runtime y ningún módulo de `src/agents/` puede
        crear un ciclo al importar el suyo.
      - **Equivalencia probada byte a byte**: nuevo `scripts/snapshot_prompts.py` renderiza los
        **61 prompts** (todas las variantes de idioma y de argumentos: campos que faltan, los 8
        slots del resolutor, con/sin nombre de cliente, con/sin notas previas, + el prompt RAG
        ENSAMBLADO) con su SHA-256 → snapshot antes/después con **diff vacío**. Sirve además
        como visor de la superficie de prompt entera y como red para cualquier movimiento futuro.
      - **Tests nuevos** (`tests/test_prompts_surface.py`, 27): la propiedad de hoja (AST, sin
        imports de `src`), la **identidad** de cada red con el objeto de su módulo de prompts
        (si alguien vuelve a inlinear una copia, falla en vez de desincronizarse en silencio),
        y que el snapshot **renderiza todos** los símbolos públicos — cobertura *derivada* de lo
        que `_collect()` toca de verdad, no una lista paralela.
      - **Métricas**: `llm_extractor.py` 898→302, `escalation.py` 479→180, `notes_extractor.py`
        148→84, `rag_agent.py` 1336→1210, `query_rewriter.py` 92→67, `conversation_summarizer.py`
        104→81, `grounding_check.py` 229→218, `language_detector.py` 38→34 (−1148 líneas en
        total; +1282 en `src/prompts/`, con los docstrings de índice y las cabeceras por red).
      - Verificado al commitear: snapshot **byte a byte idéntico**, los 27 tests nuevos y los
        subconjuntos afectados en verde, ruff + compileall limpios, y la **baseline completa
        (1492 passed / 18 skipped) medida en esta máquina ANTES de tocar nada**. La pasada
        completa en los **3 modos** quedó lanzada y en vuelo al hacer el commit (en esta máquina
        son ~40 min por modo, no los ~7 del handoff de Gadea) — el resultado se registra en §8
        en cuanto termina; si algo saliera rojo, se arregla encima, no se reescribe este paso.
- [x] **3.3 · Partir el subgrafo `booking`** en nodos de responsabilidad única: routing interno
      (deliberación/recall/pregunta-vs-reserva) → extracción → slot-fill (`next_missing_slot`)
      → cierre determinista (`cart_render`). Elimina el monolito de 2.249 líneas.
      *(Marcado `[x]` al cerrar 3.2: los 5 sub-pasos 3.3a-e están hechos y el propio texto de
      abajo lo declara completo en la práctica — el checkbox se había quedado sin marcar, y aquí
      es la única fuente de verdad. Partir más es refinamiento opcional, no pendiente.)*
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
      - **3.3d · Partir el `body` en `routing` + `extract_close` — HECHO** (`5e7420b`, Gadea).
        El subgrafo pasa a 4 nodos: `START → setup → availability → routing → extract_close →
        END`. `_body_phase` partido en `_routing_phase` (snapshots `prev_*` + `resolved_short`
        + carryover/pregunta/deliberación; early-return o devuelve el `carry`) +
        `_extract_close_phase` (extracción → slot-fill → cierre; recibe el `carry`,
        byte-idéntico salvo el unpack). Los 10 valores compartidos (`prev_*`/`resolved_short`)
        van por `_BookingSubState.carry`. El corte más intrincado, pero seguro por la fuente de
        verdad compartida (un fallo rompería también la cascada). Suite verde 3 modos (1492) +
        smoke en vivo (flujo de reserva multi-turno por los 4 nodos).
      - **3.3e · Partir `extract_close` en `extraction` + `slotfill_close` — HECHO** (`41368dc`,
        Gadea). `_extract_close_phase` partido en `_extraction_phase` (understand + multi-ítem +
        redes de precisión + anti-bucle; early-return o None) + `_slotfill_close_phase` (RESOLVER
        + RESPONDER: elige/pregunta el slot que falta o cierra + acuse). Costura limpia
        (`slotfill_close` solo necesita `prev_pending`/`resolved_short` del carry + `greeting`/
        `first_turn`). **Subgrafo de 5 nodos:** `setup → availability → routing → extraction →
        slotfill_close`. `maybe_handle_turn` queda como orquestador plano de las 5 fases. Suite
        verde 3 modos (1492) + smoke en vivo de 5 turnos.
      - **✅ 3.3 en la práctica COMPLETA:** el monolito del núcleo (~2.249 líneas) queda partido
        en **5 fases de responsabilidad única** (setup/availability/routing/extraction/
        slotfill_close), todas compartidas por cascada y subgrafo (equivalencia por
        construcción). Partir más (p. ej. slot-fill vs. cierre) es refinamiento de valor
        marginal decreciente; queda a criterio del equipo.
- [x] **3.4 · Reducir llamadas LLM/turno — HECHO (1ª reducción medida; resto diferido por
      robustez, con criterio).** Medir vs baseline de Fase 0. **DoD cumplido: 3.00 → 2.80
      llamadas/turno**, cero colisiones, prompts por nodo testeados. **Suite completa verde con la
      reducción dentro: 1538 passed / 9 skipped / 0 failed** (2026-07-31, esta máquina). Análisis
      completo de los candidatos restantes → se dejan a propósito (no son reducciones seguras):
      el solapamiento `fill_gaps`/`detect_special_signals` son redes intencionalmente separadas
      (bugs de doble-conteo ya peleados), y `detect_routing_signals` es la red de seguridad del
      router. Detalle abajo.
      - **Estado (2026-07-30, Gonzalo): PENDIENTE, y hasta ahora no hay nada que medir.** Los
        tres pasos cerrados de Fase 3 (3.1 funcional, 3.2, 3.3) son **estructurales y
        preservadores de conducta**: mismos prompts (byte a byte, probado) y mismos puntos de
        llamada ⇒ las llamadas/turno siguen siendo las **3.00** de la baseline por construcción.
        Bajar de ahí requiere un cambio deliberado de comportamiento (fusionar redes, o no
        invocar una red cuando el nodo ya sabe que no aplica), que es trabajo propio de 3.4 y
        **necesita decisión** — no un efecto colateral de mover ficheros.
      - **Bloqueo de entorno para volver a medir**: `scripts/measure_llm_baseline.py` corre el
        bot real, así que necesita **Postgres arriba** (la RAG del turno "cuanto cuesta" hace
        retrieval); en la máquina de Gonzalo hoy Docker Desktop devuelve 500 y los puertos
        5432/6379 no responden, así que una corrida ahora daría un número **no comparable** con
        la baseline (camino RAG degradado) — mejor no publicarlo. Y sigue sin haber
        `LANGSMITH_API_KEY` en ningún entorno dev, que era la vía preferida del plan.
      - **Para retomarlo**: levantar Postgres+Redis dev, correr
        `python -m scripts.measure_llm_baseline` y comparar contra la tabla de §5 Fase 0.4. Lo
        primero a mirar con ese dato delante es **qué red concreta pone cada llamada en los
        turnos baratos** (el saludo ya cuesta 2 llamadas y el cierre 3, sin extracción de
        slots por medio): ahí es donde una llamada evitable se nota más, no en el turno de
        extracción, que es el que sí tiene que trabajar.
      - **✅ AVANCE (2026-07-31, Álvaro) — infra desbloqueada + paridad + 1ª reducción medida.**
        Con Postgres+Redis arriba: **el grafo (flag on) mide 3.00 llamadas/turno, IDÉNTICO a la
        baseline de la cascada** → confirmado que el refactor 2.x/3.x NO añadió ni quitó llamadas
        (preservador por construcción). **Atribución por turno** (guion de §5 Fase 0.4, trazando
        el caller de cada `chat.completions.create`):
        - T1 `hola` (saludo): `detect_routing_signals` + **`fill_gaps`**
        - T2/T3 (extracción/ubicación): `detect_routing_signals` + `extract_notes` + `fill_gaps`
          + `compose_acknowledgement`
        - T4 `cuanto cuesta`: `detect_routing_signals` + `detect_special_signals`
        - T5 `perfecto, reservamos` (cierre): `detect_routing_signals` + **`fill_gaps`** +
          `detect_special_signals`
        - **Reducción landed:** `fill_gaps` se salta en un **saludo puro** (`_is_greeting_only`
          contra `GREETING_ONLY_KEYWORDS`) — no hay slots que extraer, devolvía `{}` →
          preservador de conducta. Medido: **saludo 2→1 llamada, total 15→14, 3.00 → 2.80
          llamadas/turno**. 508 tests de regresión (core/intent/booking/grafo) verdes + test
          nuevo `test_llm_call_reduction.py` que fija el comportamiento.
        - **Siguientes candidatos (identificados, sin hacer):** (a) el **solapamiento
          `fill_gaps` + `detect_special_signals`** en el turno de cierre (T5) — dos redes de
          extracción sobre el mismo mensaje sin reparto nuevo (el 3.1-audit ya lo marcó); (b)
          `detect_routing_signals` corre en los 5 turnos: ver si un pre-check determinista puede
          evitarlo en turnos sin señal posible (más delicado, es la red de seguridad del router).
- **DoD:** llamadas LLM/turno ↓ vs baseline (**2.80 < 3.00 ✓, más headroom identificado**); cero
  colisiones; prompts por nodo testeados.

### Fase 4 — Estado, memoria y persistencia unificados
> **Reencuadre aprobado por el owner (2026-07-31).** El audit de Fase 4 mostró que **el estado
> ya está consolidado**: `ConversationState` (dataclass ~60 campos tipados) es el State único que
> todos los nodos comparten por referencia; no hay estado de conversación disperso (solo cachés
> inmutables de config/KB + un ContextVar de diagnóstico por turno). Por eso 4.1/4.2 se cierran
> como **confirmar+documentar** (no big-bang), y el trabajo sustantivo de la fase es 4.3.
- [x] **4.1 · State canónico único — HECHO (reencuadrado, sin big-bang).** Confirmado y
      documentado que `ConversationState` es el State único y canónico (todos los nodos lo mutan
      por referencia vía `conv_state` en `BotState`). **NO** se re-tipa a un `BotState` plano: sería
      un big-bang contra el strangler (#2) y el reducer `add_messages` no aporta en topología
      lineal (sin fan-out). Audit: cero estado disperso que eliminar. Docstring de
      `src/orchestration/state.py` actualizado con la decisión. *(dev: Álvaro)*
- [x] **4.2 · Persistencia — DECIDIDO: mantener `state_store.py` sin cambios.** Sigue
      persistiendo el `ConversationState` canónico (JSON ⇄ Redis, por `conversation_id` + TTL).
      Como no hay migración a `BotState` tipado, la serialización no cambia (cero migración). Se
      descarta el checkpointer de LangGraph por ahora: no usamos time-travel/replay y añadiría
      migración + la superficie SQLi→RCE de los checkpointers (spike §5); revisable si se
      necesita replay explícito, fijando `langgraph-checkpoint-redis>=1.0.2` y sin exponer
      `get_state_history` a filtros del cliente. *(dev: Álvaro)*
- [x] **4.3 · Grounding único + memoria/notes — HECHO (confirmado + documentado; ya satisfecho
      por la arquitectura).** Audit con evidencia:
      - **Grounding YA unificado:** un solo módulo (`src/agents/grounding_check.py`:
        `is_grounded`/`urls_grounded`/`currency_amounts_grounded`/`capacity_claims_grounded`) y un
        **único chokepoint de texto factual**: `supervisor.rag_answer`. TODOS los emisores de
        respuesta factual pasan por ahí — el nodo `info` (`info_agent`), el núcleo
        (`_answer_question` → `supervisor.rag_answer`) y el DIVE TO HEAL de la cascada. **No hay
        camino factual que salte el grounding.** Cubierto por ~50 aserciones en
        `test_rag_safety.py`. **Decisión:** NO se construye un "middleware" que atraviesen
        deflection/escalation/changes — usan copy determinista/enlatado (no alucinan); sería
        andamiaje inútil. `compose_acknowledgement` (ack de persona) queda fuera a propósito: no
        asevera hechos de la KB (precios/cupo/URLs), solo reconoce lo dicho + CTA.
      - **Memoria Fase C YA cableada en el State canónico:** `remembered_facts["notes"]` vive en
        `ConversationState`, se captura con `_maybe_capture_notes` (→ `extract_notes`) y alimenta
        `_build_extra_context` (contexto RAG). **Decisión:** se captura en la ruta booking (donde
        aparecen los hechos sustantivos de reserva), NO cross-route — hacerlo global añadiría una
        llamada `extract_notes` a cada turno de safety/deflection/changes/info, deshaciendo la
        reducción de 3.4 por poca ganancia. `docs/archive/memory-context-improvement-plan.md` **ya
        archivado**. *(dev: Álvaro)*
- **DoD cumplido:** estado consolidado (ConversationState canónico), persistencia decidida
  (`state_store.py`), una capa de grounding (centralizada en `rag_answer`+`grounding_check`),
  memoria coherente (Fase C en el State). **Fase 4 completa.**

### Fase 5 — Test por nodo, corte del legacy y bucle de datos reales

> **✅ RESUELTO (2026-08-11) — el bloqueo de infra se auto-arregló desde la Action.** El deploy a
> PRE fallaba porque `dp-pre-postgres` estaba *unhealthy* (`pg_isready`, persistente; Redis sano) —
> infra del VPS, no el refactor. **Sin acceso SSH manual**, se resolvió metiendo en el job
> `deploy-pre` un bloque que, solo si postgres no está healthy, **libera disco** (`docker builder
> prune -af` + `docker image prune -af` — la causa era caché de build de Docker) y **reinicia
> postgres** esperando a *healthy*. Corrida #309 (`b47401f`) verde en 4m 2s: PRE arranca con el
> grafo. **Aprendizaje:** la Action ES nuestra vía de acceso al VPS (secrets `PRE_VPS_SSH_KEY`/
> `HOST`), no hace falta SSH propio para operar/reparar PRE. Queda: **validación funcional del
> grafo** (5 mensajes, uno por ruta) antes de 5.2. Rollback = quitar `AGENT_ARCH` de `dp-pre-bot` +
> push a `pre_alvaro`. **5.2 (corte irreversible) solo tras validar PRE.**

- [x] **5.1 · Test-harness por nodo — HECHO.** Cada nodo real tiene su fichero de test en
      aislamiento (State in → update out, LLM/fases mockeadas): `test_deflection_agent` (5),
      `test_escalation_agent` (7), `test_changes_agent` (5), `test_info_agent` (8),
      `test_booking_agent` (6). El **grafo compilado** (integración) en `test_agent_arch_graph`
      (6) + router (20) + estado (3) + shadow (3). **Cerrado el hueco fino** con
      `test_booking_subgraph_nodes.py` (7): los 5 nodos internos del subgrafo booking
      (`setup/availability/routing/extraction/slotfill_close`) probados en aislamiento con las
      fases del núcleo mockeadas + las funciones de edge `_after_*`. La "reorganización por nodo"
      queda satisfecha por la convención `test_<nodo>_agent.py`. *(dev: Álvaro)*
- [~] **5.2 · CORTE del legacy — EN CURSO (incremental, suite verde tras cada paso).** Con el flag
      probado en PRE. **Hallazgo del prep:** la cascada NO se borra entera — `_shared_turn_handler`
      (renombrada, ver Paso 2) **se queda** como handler compartido al que los nodos delegan (núcleo + tail post-núcleo:
      wants_human, idioma, disponibilidad); reproducir esos gates en los nodos SIN el núcleo
      perdería efectos de estado. Lo que muere: el flag + shadow + gates pre-núcleo ya reproducidos.
      - [x] **Paso 1 — subsistema shadow retirado** (`2491be5`). El shadow (Fase 1.5) ya cumplió
        (grafo validado en suite + PRE en vivo). Borrado: 21 `_mark_route(...)` no-op, el ContextVar
        `_cascade_route_taken`, `_mark_route`, `_run_route_shadow`, la rama `elif agent_arch_shadow`
        de `route_message`, `import contextvars`, el import `ROUTE_*` sin uso (supervisor.py) y el
        campo `agent_arch_shadow` (config.py) + `test_route_shadow.py`. −183 líneas. Sin tocar el
        rollback (flag + cascada siguen). Comportamiento intacto (marks no-op): ruff limpio, 129
        verdes en orquestación/agentes/equivalencia; suite completa en verificación.
      - [x] **Paso 2 — renombrar `_route_message_inner` → `_shared_turn_handler`** (2026-08-27,
        Gadea, tras verificar el SOAK de cierre en LangSmith — 579 turnos/232 conversaciones,
        0 errores). Renombrado en `supervisor.py` + los 5 nodos-agente + `orchestration/{graph,
        router,state,__init__}.py` + tests (19 archivos), con la suite (por nodo + e2e, flag on/
        off/shadow) verde tras el cambio. Docstring reescrito documentando su rol dual post-corte
        (núcleo+tail compartido cuando el grafo está ON, único camino cuando está OFF) — ver la
        función en `supervisor.py` para el detalle. `docs/archive/*` y las entradas fechadas de
        este documento (§8, handoffs) se dejan con el nombre viejo a propósito: son registro
        histórico de lo que era cierto en su momento, no se reescribe el pasado.
      - [ ] **Paso 3 — quitar el flag `agent_arch`** de `route_message` (grafo incondicional).
        Borrar los gates pre-núcleo de la cascada que queden muertos (reachability + suite tras
        cada borrado). **"Punto de no retorno" (rollback hasta aquí = apagar el flag). No
        ejecutado; ver el prep de abajo para lo que SÍ se preparó sin tocar el flag.**
        - **⚠️ Criterio revisado (2026-08-27, Gadea + Álvaro, decisión conjunta — sustituye "3.
          Promover a PRO" de §5.3-bis abajo):** PRO no tiene fecha, no existe todavía como entorno.
          **No se espera a PRO** — el criterio de corte pasa a ser **PRE validado a fondo** (SOAK +
          batería sintética + tráfico real acumulado, sin gate intermedio de PRO) hasta llegar a
          confianza suficiente (orientativo: ~90%, a definir con más precisión según vaya
          avanzando la validación), y entonces se entrega directamente al cliente. El resto de la
          Fase 5.3-bis (criterio de reanudación, comparación contra baseline Fase 0.4) se mantiene
          igual — solo cambia que no hay un tercer entorno intermedio entre PRE y el cliente.
      - **🔎 PREP — mapa de reachability (2026-08-11, Álvaro, análisis sin borrar nada):** el corte
        NO es un borrado directo — **`_shared_turn_handler` sigue VIVA**: los 5 nodos reales
        delegan en ella. Se parte en dos:
        - **(A) Gates PRE-núcleo ya reproducidos en nodos** (PII/link/sensible/DIVE-TO-HEAL,
          cancel/reschedule/modify-headcount, contacto/identidad, edad, disponibilidad-narrow) →
          **mueren** al cortar (los nodos los ejecutan directamente). Borrables por reachability.
        - **(B) Gates POST-núcleo + fallbacks que los nodos AÚN delegan** → dependen del resultado
          de `maybe_handle_turn` (solo devuelve `None` para escalado-keyword/`wants_human` —
          idéntico en `pre_gadea`, no es propio del grafo).
        - **Decisión de diseño tomada (2026-08-27, Gadea, plan-mode, ver commit del mismo día):**
          **NO se redistribuye (B) físicamente en 5 archivos** — se mantiene `_shared_turn_handler`
          como "tail handler" compartido permanente (la alternativa que este mismo plan ya
          contemplaba), llamado directamente por los nodos (no vía el flag). Mismo patrón que las
          fases compartidas de `booking_agent.py` (`_setup_phase` etc.): funciones compartidas
          extraídas, no "propiedad" de un solo archivo. Menor riesgo de equivalencia que dispersar
          ~170 líneas interdependientes en 5 sitios distintos.
        - **Hallazgo al auditar el alcance real de (B) (2026-08-27, Gadea):** es más estrecho de
          lo que sugería el resumen por nodo. `maybe_handle_turn` (idéntico en ambas ramas) SOLO
          devuelve `None` por escalado-keyword/`wants_human` — así que de los 7 ítems de la cola
          (afirmación-breve-acepta-asesor, escalado-keyword/`wants_human`, link-roto duplicado,
          sensible duplicado, disponibilidad/días-cerrados duplicado, cambio de idioma explícito,
          fallback), **solo los 2 primeros se alcanzan en la práctica** (verificado con tests
          directos, sin mockear la delegación — `tests/test_escalation_agent.py`). La
          "afirmación-breve-acepta-asesor" en concreto solo dispara cuando la señal LLM
          `wants_human` (que ve el historial completo) clasifica un "sí" contextual como
          aceptación — no cualquier "sí" aislado. La disponibilidad/días-cerrados NO se alcanza
          por esta cola: la intercepta `conversational_core._availability_phase` (el núcleo mismo,
          portado el mismo día que el resto de hallazgos de la batería sintética) — confirmado con
          tests directos en `tests/test_changes_agent.py`. Los 4 ítems restantes (link-roto dup,
          sensible dup, cambio de idioma, fallback) están **confirmados como código muerto por
          análisis de flujo de control (2026-09-01, Gadea), no solo "sin evidencia de uso"**: el
          chequeo de escalado-keyword/`wants_human` (línea justo después de la rama
          afirmación-breve) usa EXACTAMENTE la misma condición (`_matches_escalation_keyword
          (msg_lower) or routing_signals.get("wants_human")`) que hizo que `_setup_phase`
          devolviera `None` para llegar hasta aquí — ni `msg_lower` ni `routing_signals` se
          reasignan entre ambos puntos. Así que **siempre que el núcleo declina, ese chequeo
          también matchea** (y escala ahí, o antes en la rama de afirmación-breve) — nunca se
          llega a link-roto/sensible/disponibilidad-dup/idioma/fallback. No se han borrado
          todavía (es trabajo del Paso 3 real), pero la pregunta "¿son alcanzables?" ya tiene
          respuesta definitiva: no.
        - **Checklist ejecutable para el Paso 3 real (gateado por PRE llegando a confianza
          suficiente — ver criterio revisado arriba — NO ejecutar sin esa confirmación):**
          1. Confirmar que las 6 pruebas `*_equivalent_graph_vs_cascade` (una por nodo) ya no son
             la única red sobre el comportamiento del grupo B — con los tests directos añadidos
             hoy, no lo son; se pueden simplificar/borrar sin perder cobertura real.
          2. Borrar la rama OFF-flag de `route_message` (`src/agents/supervisor.py`, 2 líneas).
          3. Reachability + suite completa (3 modos) para borrar los gates PRE-núcleo del grupo
             (A) que queden muertos por duplicación con los nodos.
          4. Borrar los 4 ítems del grupo (B) confirmados como código muerto (ver el hallazgo de
             flujo de control arriba — link-roto/sensible duplicados, cambio de idioma, fallback),
             con la suite completa (3 modos) como red.
          5. Quitar el campo `agent_arch` de `config.py` y sus referencias.
        - **Nota aparte, YA RESUELTA (2026-09-01, Gadea):** `booking_agent.py` no reproducía la
          explicación de nacionalidad mixta que sí da la cascada (gap pre-existente, ya
          documentado en `orchestration/router.py` como "candidato a discrepancia de shadow").
          Arreglado: `_mixed_nationality_response` extraída a `supervisor.py` y llamada desde
          `booking_node` antes del subgrafo (mismo patrón que `deflection_node`/`info_node`),
          verificado con test end-to-end y en vivo contra PRE (redeploy `feature/pre_alvaro`).
          Auditados también el resto de los checks pre-núcleo de la cascada (PII, link roto,
          sensible, DIVE TO HEAL, cancelación/reprogramación/modify-headcount, contacto/identidad,
          edad, alcohol/alergia, reinicio-de-escenario, mención-de-niños) — todos confirmados
          reproducidos en algún nodo del grafo, sin más huecos de este tipo encontrados.
- [~] **5.3 · Bucle de datos reales con LangSmith — EN CURSO (periodo de medición ABIERTO).**
      LangSmith trazando PRE en vivo (proyecto `diving-planet-bot`, commit `cd5a23a`). Cableado:
      key como GitHub secret → inyectada en `.env.pre` por el job `deploy-pre`; **fix de un bug
      real** en `config._activate_langsmith_tracing` (fijaba `LANGSMITH_TRACING_V2`, var
      inexistente → tracing nunca encendía; ahora `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2`).
      **Traza el grafo LangGraph** (nodos + latencia/turno) **+ cada llamada LLM** (tokens/coste;
      `trace_openai` en `src/llm_client.py`, `e34c981`). Pendientes del bucle: (b) harvest de
      trazas → datasets/evals para dirigir refuerzos con datos reales; (c) comparar trazas/
      latencia/coste vs baseline de Fase 0.4 durante el periodo acordado → gatea el corte (5.2).

> ### ⏳ Fase 5.3-bis · PERIODO DE MEDICIÓN (SOAK) — PARADO, esperando tráfico real (multi-día)
> **Estado (2026-08-11):** el grafo sirve en PRE con observabilidad completa en LangSmith
> (proyecto `diving-planet-bot`: trazas de grafo + por-llamada). **No hay código que hacer aquí**
> — es un reposo de varios días para acumular tráfico real del equipo/PRE.
> **Criterio de reanudación (cuándo pasar al corte) — REVISADO 2026-08-27 (Gadea + Álvaro,
> decisión conjunta):** PRO no tiene fecha, no existe todavía — **no se espera a un tercer
> entorno**. Sustituye el criterio original: cuando haya un volumen razonable de conversaciones
> (real y/o batería sintética dirigida) trazadas en PRE (orientativo: **≥ ~1 semana o ~50-100
> conversaciones** — ya superado hoy con 232+50, ver Fase 5.3) y la comparación en LangSmith vs
> la **baseline de Fase 0.4** (llamadas/turno ≤ 3.00, hoy 2.80; latencia; coste; sin
> errores/mismatches nuevos) sea **"igual o mejor"**, **Y** además la confianza general en PRE
> llegue a un nivel alto (orientativo ~90%, a precisar) antes de entregar al cliente — sin gate
> intermedio de PRO.
> **Qué hacer al reanudar (el corte, en orden — ver el 🔎 PREP de reachability arriba):**
> 1. ~~Migrar los gates POST-núcleo delegados (grupo B) a sus nodos~~ **HECHO 2026-08-27**:
>    decisión tomada de mantener `_shared_turn_handler` como tail handler compartido (no
>    redistribuir físicamente), con tests directos de cobertura — ver el 🔎 PREP arriba.
> 2. ~~Renombrar `_route_message_inner` (paso 2)~~ **HECHO 2026-08-27** → `_shared_turn_handler`.
> 3. ~~Promover a PRO (rollout escalonado shadow→live)~~ **YA NO APLICA** (criterio revisado
>    arriba — PRE es el entorno de validación final, sin PRO intermedio).
> 4. Quitar el flag `agent_arch` (paso 3, punto de no retorno) + borrar los gates pre-núcleo
>    muertos (grupo A) + confirmar alcanzabilidad de los 4 ítems no confirmados del grupo B antes
>    de tocarlos. **Rollback hasta el corte = apagar `agent_arch`.**

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

## 6.bis Reparto de grupos mixtos: extractores LLM que "contestan de más" (2026-09-01) — CERRADO

**Estado: CERRADO.** Las tres causas raíz están identificadas, arregladas, cubiertas por tests y
verificadas en vivo contra PRE. Este apartado se conserva completo porque el *método* (y las
trampas) sirven para la próxima investigación de esta familia.

### Síntoma original

Un grupo con reparto mixto de 3+ actividades explícito en el mensaje de apertura ("somos 6: 2
bucean certificados, 2 hacen minicurso y 2 snorkel") terminaba, unos turnos después (a veces tras
cerrar ya la reserva), preguntando "¿Qué le gustaría hacer a tu acompañante — probar el buceo con
el *minicurso*, o prefiere *snorkel*?" — una pregunta sin sentido, porque el reparto YA estaba
completo desde el turno 1. Encontrado en el lote 8 (batería de grupos mixtos contra PRE).

### Repro exacto

```
python pre_driver.py "repro-tag" "somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel" "cartagena" "ninguno colombiano" "no"
```
(`pre_driver.py` vive en el scratchpad de sesión; usa la Application API de Chatwoot contra el
inbox "Synthetic Test" — ver `docs/robustness/pre-synthetic-battery-findings.md` para el
token/inbox. **No se sube a `scripts/` porque lleva el token embebido.**)

**Repro en LOCAL con LLM real** (2026-09-01, sesión de cierre — mucho más rápido y barato que
tirar contra PRE, y permite instrumentar): un driver de ~30 líneas que importa
`supervisor.route_message`, carga `.env.dev` a `os.environ`, fuerza `AGENT_ARCH=true` y envuelve
`conversational_core.fill_gaps`/`detect_special_signals`/`resolve_slot_answer` con un wrapper que
imprime argumentos y valor devuelto. No hace falta ni Chatwoot ni base de datos. **Esta es la vía
recomendada** para el próximo bug de esta familia; LangSmith solo cuando no haya créditos locales.

### Investigación: trazas de LangSmith

Sin acceso a LLM en local (sin créditos en `.env.dev` durante parte de la sesión anterior), la
única forma de ver qué devolvían las llamadas LLM reales fue tirar de las trazas de LangSmith
(proyecto `diving-planet-bot-pre`), con **`scripts/inspect_langsmith_trace.py`**:

```bash
python scripts/inspect_langsmith_trace.py <conversation_id> [minutos_atras=15]
```

Tres lecciones ya incorporadas al docstring del script: (1) `detect_special_signals` se registra en
las trazas como `detect_signals`; (2) los snapshots de `conv_state` del nodo "LangGraph chain" más
externo NO son fiables (objeto mutable compartido por referencia, serialización tardía) — usar los
outputs de los nodos de fase; (3) **el driver de repro debe leer TODOS los salientes de cada turno**
(ver causa raíz #2 abajo).

### Causa raíz #1 — `detect_special_signals` re-derivando el reparto (arreglada)

`detect_special_signals` (tool `detect_signals`) **re-deriva sus señales del HISTORIAL ENTERO en
cada llamada**, no solo del mensaje del turno actual. En la traza real del turno "ninguno
colombiano" (que solo responde nacionalidad, sin mencionar a nadie), devolvió:
```json
{"companion_activity":"certified_diving","mentions_other_person":true,"companion_is_singular":false,
 "companion_qty":2,"other_companions":[{"activity":"minicourse","qty":2},{"activity":"snorkel","qty":2}]}
```
El LLM, mirando el historial completo, "redescubre" la conversación y re-describe TODO el reparto
como "buzo principal + acompañantes" — un encaje forzado, porque el esquema de esta tool no tiene
forma limpia de representar "reparto N-way sin buzo principal". Pisaba `detected_group_allocation`
(ya correcto desde el turno 1) con una versión parcial.

**Fix** (`_group_allocation_fully_resolved` en `src/agents/conversational_core.py` + 3 puntos de
uso — commits `8ff6e7a` y `92dd8cc`): con el reparto ya cubriendo a todo `detected_group_size`, la
llamada se salta ENTERA. Verificado con test y en vivo (conversaciones 766 y 767).

### Causa raíz #2 — FALSA ALARMA: "el resumen final pierde actividades"

La sesión anterior anotó como cabo suelto que el resumen de cierre mostraba solo buceo certificado
(2 pax, $356), sin rastro de minicurso ni snorkel. **No era un bug del bot: era el driver de
repro.** `pre_driver.wait_for_reply()` devolvía SOLO el primer mensaje saliente, y el núcleo parte
la respuesta multi-ítem en varios mensajes de Chatwoot (separador `<<<SPLIT>>>`).

El volcado completo de la conversación 769 (`get_messages`) muestra los tres bloques enviados
—ids 10877/10878/10879 y 10882/10883/10884: cert $356 + minicurso $366 + snorkel $252— y el repro
local confirma `mixed_cart=[('cert',2),('beginner',2),('snorkel',2)]`.
**`_build_cart_from_slots`/`_finalize` no tienen ningún bug.** El driver está arreglado y la trampa
documentada en el docstring de `scripts/inspect_langsmith_trace.py`.

### Causa raíz #3 — extractores LLM contestando por el cliente (arreglada)

El bug real que quedaba, y de la misma familia que la #1: **un extractor LLM de formato libre que
ve el historial como diálogo, encuentra una pregunta del bot sin responder, y la contesta él.**
Reproducido de forma determinista en local, por DOS vías distintas:

**Vía A — `fill_gaps`.** Con `core_pending_slot == SLOT_SAFETY` (el bot acababa de preguntar "¿ha
pasado más de 2 años desde la última inmersión?"), el mensaje "ninguno colombiano" —que solo
responde nacionalidad y no menciona el buceo en absoluto— producía:
```json
{"activity":"minicourse","is_certified":true,"group_size":6,
 "group_allocation":{"certified_diving":2,"minicourse":2,"snorkel":2},
 "last_dive_over_2_years":false,          // <-- ALUCINADO
 "location":"cartagena","is_colombian":false}
```
Como `state.last_dive_over_2_years` estaba en `None`, el valor inventado se aplicaba (patrón "solo
si el campo está vacío" de `_apply_detected_intent`), `next_missing_slot` daba `SLOT_SAFETY` por
resuelto y la reserva se cerraba **sin haber preguntado nunca algo que es de seguridad**.

**Vía B — el resolutor de slot anti-bucle (Fase C).** Al verificar el fix de la vía A en vivo, el
repro seguía fallando de forma intermitente: `resolve_slot_answer("safety", "ninguno colombiano")`
devolvía `{"value": False}` — 2 de 3 corridas con LLM real. Mismo fallo, otro extractor.

**Fix — dos guardas genéricas** (no un parche por síntoma), en `conversational_core.py`:

- **(a) El slot booleano pendiente nunca se le pide a `fill_gaps`** (`_BOOL_SLOT_FIELD`, aplicado
  en `_relevant_gaps`). `SLOT_SAFETY`/`SLOT_CERTIFICATION`/`SLOT_NATIONALITY` ya tienen dos
  resolutores anclados al mensaje del turno — `_apply_short_answer` (determinista, corre ANTES de
  `_understand`) y el resolutor anti-bucle para fraseos no canónicos. `fill_gaps` era un tercer
  camino redundante y el único que mira el historial. Solo booleanos: en location/hotel/activity
  la respuesta ES texto libre y `fill_gaps` sí es el extractor correcto.
- **(b) Respaldo textual determinista para los booleanos** (`_boolean_has_textual_backing`,
  aplicado al patch de `fill_gaps` en `_understand`, junto al saneamiento de `group_allocation`
  que ya existía). Si el mensaje no toca el TEMA del campo, el valor viene del historial, no del
  cliente. Los léxicos se reutilizan de los detectores regex (`LAST_DIVE_TOPIC_RE`,
  `CERTIFICATION_TOPIC_RE`, `NATIONALITY_TOPIC_RE`, ahora a nivel de módulo en
  `intent_detector.py`): un solo vocabulario por campo, no dos listas que se desincronizan.
- **(b-bis) Para la vía B el gate de tema NO vale**, y esto importa: esa red existe precisamente
  para las respuestas válidas pero no canónicas, y la legítima de este mismo slot ("uf, hace
  muchísimo") tampoco menciona el buceo. Lo que distingue "uf, hace muchísimo" de "ninguno
  colombiano" no es el vocabulario, sino que el segundo **ya respondió a OTRO slot en este mismo
  turno** → `_turn_answered_a_different_slot`, que generaliza la verificación determinista que ese
  bloque ya aplicaba solo a `SLOT_LOCATION`.

Reforzar el prompt está descartado por medición previa para toda esta familia (documentado en
`_message_numbers`; `extraction_system_prompt` ya pide explícitamente abstenerse). La verificación
determinista sobre el texto del turno es el patrón que sí funciona.

**Verificación**: suite completa verde en las 3 configuraciones (default / `AGENT_ARCH=true` /
`AGENT_ARCH_SHADOW=true`) — **1603 passed / 18 skipped / 0 failed**, 8 tests nuevos sobre un
baseline de 1595. En vivo contra PRE y en local con LLM real: el turno "ninguno colombiano"
**re-pregunta la de seguridad** en vez de cerrar, el reparto de 3 actividades sobrevive intacto, y
"uf, hace muchísimo" / "hace 3 años que no buceo" / "no" siguen resolviendo el slot como antes.

### Regla de diseño que sale de aquí

> Un extractor LLM de formato libre no puede responder por el cliente. Si el valor que devuelve
> para un campo no tiene respaldo en el TEXTO del turno —o el turno ya respondió a otro slot—, se
> descarta y se pregunta. Preguntar de más es el fallo seguro; dar un slot por respondido sin que
> el cliente lo respondiera, no.

Las tres causas raíz son la misma: el historial entra en el prompt como diálogo, y el modelo lo
completa. Antes de añadir un extractor LLM nuevo que toque campos de reparto/actividad/seguridad,
comprobar qué pasa cuando el bot acaba de preguntar algo que el mensaje no responde.

### Deuda anotada (no se toca aquí)

- **Cutover de extracción muerto**: `_maybe_apply_llm_extraction_cutover` y
  `_maybe_log_llm_extraction_shadow` (`src/agents/supervisor.py`) **no tienen ningún call-site en
  `src/`** — solo los llaman sus tests (`test_llm_extraction_cutover.py`,
  `test_llm_extraction_shadow_mode.py`). Los cuatro `LLM_EXTRACTION_CUTOVER_*: "true"` de
  `docker-compose.vps.yml` son inertes en PRE. Borrarlos va con el corte de Fase 5.2, que ya entra
  en esa zona — no se mezcla con un fix de bug. **Ojo si alguien los reconecta: llaman a
  `fill_gaps` SIN `only_fields`**, así que ampliarían la superficie de alucinación en vez de
  reducirla, y no llevan las guardas (a)/(b) de arriba.
- ~~**Acuse de recibo poco afortunado**~~ — **ARREGLADO 2026-09-02**: `acknowledgement_system_prompt`
  (`src/prompts/booking.py`) ahora instruye explícitamente a no reinterpretar un HECHO (nacionalidad,
  cantidad de personas, ubicación...) como una PREFERENCIA, con el ejemplo real como negativo.
  Test: `test_ack_prompt_warns_against_reinterpreting_fact_as_preference` en
  `tests/test_conversational_core.py`. Cosmético, cambio de prompt puro — no requiere redeploy de
  comportamiento de negocio, solo de texto.
- ~~**Eval-set sin historial**~~ — **ARREGLADO 2026-09-02**: `fill_gaps` ya aceptaba `history` como
  kwarg; `scripts/run_extraction_eval.py` ahora lo pasa (`case.get("history")`), y
  `docs/robustness/eval-set.json` gana un campo opcional `history` por caso. Se añadieron 3 casos
  representativos de la familia "contesta de más" (`hist-nationality-answer-must-not-fill-pending-safety`,
  `-pending-certification`, `hist-followup-must-not-rederive-resolved-group-allocation`), cada uno
  con `expected: null` en el campo que NO debe rellenarse — así una regresión futura de las guardas
  (a)/(b)/(b-bis) de causa raíz #3 se vuelve un número medible en el runner, no solo un test unitario.

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
- ~~**⚠️ Respuesta RAG corrupta, sin reproducir**~~ — **ARREGLADO 2026-09-02**: una conversación en
  contexto DIVE TO HEAL (`dive-to-heal-persist-across-many-turns`, turno 3, "cuantas inmersiones
  son", 2026-09-01 lote 7) había devuelto literalmente `{" "}` como respuesta — texto corrupto,
  no una respuesta real. Nunca se reprodujo en vivo, así que no se pudo verificar un fix contra
  el caso exacto; en su lugar se añadió una guarda determinista general (mismo patrón que
  `currency_amounts_grounded`/`urls_grounded`): `is_coherent_text` (`src/agents/grounding_check.py`)
  rechaza una respuesta vacía o con menos de 2 caracteres alfabéticos — cubre `{" "}` y cualquier
  salida igual de degenerada — como PRIMER guard en `_answer_with_llm` (`src/agents/rag_agent.py`),
  antes de precio/URL/etc., para que el mecanismo de regenerar-una-vez ya existente (muestra a
  temperatura 0.3) produzca una respuesta real en el reintento en vez de dejar pasar la corrupta.
  Deliberadamente laxa (umbral de 2 letras) para no rechazar respuestas cortas legítimas ("Sí",
  "No"). Tests: `TestCoherentTextGuard` + `test_rag_regenerates_when_answer_is_garbled` en
  `tests/test_rag_safety.py`.
- ~~**⚠️ Relevancia del RAG dentro de DIVE TO HEAL para preguntas genéricas**~~ — **ARREGLADO
  2026-09-02** (2026-09-01, Gadea, lote 7). Causa raíz real, distinta de lo que apuntaba la
  entrada original: `_build_extra_context` (`src/agents/supervisor.py`) **nunca mencionaba**
  `adaptive_diving_context` en el texto que arma para el LLM — el contexto DIVE TO HEAL no se
  perdía por perder una carrera contra un doc del KB (esa hipótesis original no se pudo
  reproducir así), sino porque `extra_context` no llevaba ninguna señal de que la conversación
  estuviera en ese programa. Reproducido en vivo contra PRE (turno 1 dispara DIVE TO HEAL,
  turno 2 "cuántas inmersiones son" caía al fallback genérico "no lo tengo a la mano" en vez de
  responder sobre el programa adaptado) y localmente con LLM real (A/B de `rag_answer` con y sin
  la nota: sin ella, la respuesta se rechazaba por el juez de grounding — `HALLUCINATED` — y caía
  al fallback; con ella, respuesta correcta y bien fundamentada).
  **Fix**: `_build_extra_context` ahora añade una nota explícita cuando
  `state.adaptive_diving_context` es `True`, indicando que preguntas de seguimiento genéricas
  (número de inmersiones, duración, itinerario, qué incluye...) deben interpretarse DENTRO de
  DIVE TO HEAL — esos detalles se coordinan caso a caso con el equipo, no son el dato fijo de un
  paquete estándar — salvo que el cliente pida explícitamente el programa normal. Deliberadamente
  NO se tocó la prioridad KB-vs-contexto-conversacional (el doc más confiable sigue ganando la
  recuperación): el fix mejora la instrucción que el LLM ya recibía junto al contexto recuperado,
  sin arriesgar romper los casos donde el KB debe ganar. Verificado en vivo contra PRE tras
  redeploy a `feature/pre_alvaro` (commit `179ac27`): antes del fix, fallback genérico; después,
  "en el programa DIVE TO HEAL, la cantidad de inmersiones se ajusta según las necesidades... se
  coordinan caso a caso con nuestro equipo". Tests:
  `test_extra_context_flags_dive_to_heal_for_generic_followups` y
  `test_extra_context_omits_dive_to_heal_note_when_not_in_that_context` en
  `tests/test_conversational_core.py`.

### Lote 9 (12 conversaciones, 2026-09-02) — áreas frescas: escalado, cambio de idioma,
### override DIVE TO HEAL, cambio de tamaño de grupo, reservas existentes, menores, alcohol+alergia
### — CERRADO (4/4 hallazgos corregidos)

Zonas no cubiertas por lotes 1-8: escalado a humano (keyword y explícito), cambio de idioma a
mitad de flujo, el override explícito "en realidad quiero el programa normal" de DIVE TO HEAL
(justo el fix de arriba), cambio de tamaño de grupo a mitad de negociación, cancelación/
reprogramación de una reserva ya existente, mención de un menor de edad, combo alcohol+alergia
en un mismo mensaje, 3+ nacionalidades mezcladas, precio en una moneda no soportada (euros).

- ✅ **Escalado humano (keyword y explícito) — sin problema.** Ambas variantes escalan
  correctamente ("Te paso con un asesor..." / "Voy a transferirte inmediatamente...").
- ✅ **Cambio de tamaño de grupo a mitad de negociación — sin problema.** "en realidad ahora
  somos 6, se sumaron 2 mas" se procesa bien, el conteo se actualiza y el flujo continúa.
- ✅ **Cancelación/reprogramación de reserva existente — sin problema** (dentro del alcance:
  no hay lookup de reserva real, así que ofrece asesor/menú, comportamiento esperado).
- **⚠️🔴 CORREGIDO — fuga de nota interna de autoría en `policies.json["food_policy"]`.**
  El shortcut determinista de `info_agent.py` (`_ALLERGY_WORD_RE` + `_FOOD_ALLERGEN_RE`, portado
  de `pre_gadea`) devuelve el texto de `food_policy` **verbatim, sin pasar por el LLM** — y ese
  texto llevaba pegada al final la frase "El bot no debe preguntar proactivamente por alergias."
  ("The bot should not proactively ask about allergies." en EN) — una nota para quien escribe el
  prompt, no información para el cliente. Repro real (conversación 788): "queremos bucear manana,
  anoche tomamos algo de alcohol y uno de nosotros es alergico a los mariscos" devolvió el párrafo
  de política de comida completo terminando literalmente en esa frase. **Fix**: nota eliminada de
  ambos idiomas en `data/knowledge_base/policies.json` (dato, no código — el comportamiento que
  describía ya está implementado: el shortcut solo dispara si el CLIENTE menciona una alergia,
  nunca pregunta proactivamente). `policies.json` también se indexa al vector store
  (`scripts/load_embeddings.py`), y el reindex ya es automático en cada deploy a PRE
  (`docker exec dp-pre-bot python -m scripts.load_embeddings --yes` en `ci.yml`), así que no hace
  falta paso manual. Guarda de regresión genérica añadida:
  `test_policy_texts_never_mention_the_bot_in_third_person` en `tests/test_rag_safety.py` —
  escanea TODOS los textos de `policies.json` por "el bot"/"the bot" en tercera persona, no solo
  el caso puntual.
- **⚠️🟡 CORREGIDO — alcohol se perdía cuando venía junto con alergia en el mismo mensaje.** En
  el mismo repro (conversación 788), la parte de alcohol del mensaje ("anoche tomamos algo de
  alcohol") no generaba ninguna respuesta: `_ALCOHOL_BEFORE_DIVING_RE` (`supervisor.py`) exigía
  que la palabra de alcohol estuviera a ≤25 caracteres de "bucear/buceo/buzos/dive/diving", y en
  este mensaje la distancia real es de 32 caracteres ("bucear" al principio, "alcohol" tras
  "manana, anoche tomamos algo de"). Además, los dos gates (`_ALCOHOL_BEFORE_DIVING_RE` primero,
  `_ALLERGY_WORD_RE`+`_FOOD_ALLERGEN_RE` después) eran `if` independientes con `return`
  inmediato — el primero que matcheaba se comía la respuesta entera, sin combinar ambos temas.
  **Fix**: ventana ampliada 25→60 (cubre cláusulas intermedias típicas en español sin volverse
  irrestricta) + nueva función `_alcohol_and_food_policy_answer` (`supervisor.py`) que comprueba
  los dos temas y CONCATENA las dos políticas si aplican ambos, en vez de que el primero pise al
  segundo — usada tanto por `info_agent.py` como por `_shared_turn_handler` (cascada) para que se
  comporten igual. Test: `test_alcohol_and_food_allergy_combined_in_one_message_both_answered`
  en `tests/test_routing_signals_integration.py`.
- **⚠️🟡 CORREGIDO — el override "programa normal, sin adaptar" de DIVE TO HEAL no respondía con
  la info genérica esperada.** Verificando el fix de arriba en vivo (conversación 782/792): tras
  confirmar que el contexto DIVE TO HEAL sí se preserva ("cuántas inmersiones son?" → respuesta
  correcta), la aclaración explícita del cliente ("en realidad quiero saber del programa normal,
  sin adaptar...") caía al fallback en vez de responder con la info genérica del paquete. Traza de
  LangSmith: la respuesta SÍ se generaba (con datos de paquete) pero el juez de grounding la
  rechazaba como `HALLUCINATED` las 2 veces — la nota DIVE TO HEAL seguía presente en
  `extra_context` y sesgaba la generación pese a la excepción escrita en el propio párrafo de
  instrucción ("salvo que el cliente aclare..."), confirmando que confiar en que el LLM se
  autocorrija DENTRO de un párrafo largo no es fiable. **Fix determinista** (mismo principio que
  las guardas de §6.bis): nuevo regex `_DIVE_TO_HEAL_OVERRIDE_RE` (`supervisor.py`) que detecta la
  aclaración explícita en el ÚLTIMO mensaje del cliente; si matchea, la nota DIVE TO HEAL NO se
  añade en absoluto para ese turno (el flag persistido `adaptive_diving_context` no se toca, por
  si el cliente vuelve a preguntar por DIVE TO HEAL después). Test:
  `test_extra_context_omits_dive_to_heal_note_on_explicit_override` en
  `tests/test_conversational_core.py`.
- **⚠️🟡 CORREGIDO (2 causas, no 1) — re-pregunta redundante tras responder una pregunta de info
  mezclada con la respuesta a un slot pendiente.** Visto en 2 conversaciones (781 cambio de
  idioma, 790 precio en euros): "how much for 2 people, certified diving?" contestaba el precio
  correctamente pero volvía a preguntar "Are you a certified diver?" pese a que el mismo mensaje
  ya lo decía.
  - **Causa #1 (real pero NO la causante de este bug — descubierto al verificar en vivo tras el
    primer fix, que no cambió el repro): `detect_special_signals` + `_mentions_person`
    interpretaban "2 people" como un ACOMPAÑANTE fantasma** con la misma actividad que el grupo
    (`mentions_other_person=true, companion_activity=certified_diving, companion_qty=2` en la
    traza de LangSmith) — "people" está en la lista de palabras de `_mentions_person` sin
    excepción para un conteo total. Es un bug real (podía crear ambigüedad de acompañante
    espuria en OTROS flujos sin "?"), pero **no es lo que causaba este síntoma concreto**: la
    rama de código donde vive esa detección (`_understand`, dentro de `_extraction_phase`) NI
    SIQUIERA SE EJECUTA para un mensaje con "?" (ver `_routing_phase`: el gate de "?" explícito
    responde con RAG y retorna ANTES de llegar a extracción). Fix igualmente aplicado (bug real,
    solo que en el flujo equivocado): `_BARE_HEADCOUNT_RE` enmascara "for/para N people/personas"
    antes de evaluar `_mentions_person`, y en el punto de uso, si el LLM dice
    `mentions_other_person=true` pero el regex (sin el conteo) no lo confirma Y el mensaje
    matchea el patrón de conteo puro, tampoco se confía en el LLM. Tests: casos nuevos en
    `test_mentions_person_discriminates_companion_from_change` +
    `test_bare_headcount_in_price_question_does_not_spawn_phantom_companion`.
  - **Causa #2 (la real, encontrada al reproducir en vivo DESPUÉS del primer fix y ver que el
    síntoma seguía idéntico): un mensaje con "?" nunca pasa por extracción ese turno**, así que
    `state.is_certified` seguía en `None` pese a que el mensaje nombra "certified diving", y
    `next_missing_slot` lo volvía a pedir. **Fix** en `_answer_question`
    (`conversational_core.py`): si el slot pendiente es certificación y el propio mensaje respalda
    textualmente `certified_diving` (misma función `_activity_has_textual_backing` que ya usa el
    resto del núcleo), se fija `is_certified=True` antes de decidir si re-preguntar — sin correr
    extracción completa fuera de su fase normal. Test:
    `test_price_question_naming_certified_diving_does_not_reask_certification`. **Verificado en
    vivo contra PRE** (conversación 796) repitiendo el repro exacto tras el redeploy: ya no
    re-pregunta la certificación — el flujo avanza correctamente a la siguiente pregunta
    (ubicación).
  - **Lección**: la traza de LangSmith mostró un candidato plausible (causa #1) que resultó real
    pero irrelevante para ESTE síntoma — sin la verificación en vivo tras desplegar el primer fix,
    se habría dado el hallazgo por cerrado incorrectamente. Confirmar siempre contra el repro
    exacto después de cada fix, no solo contra la hipótesis de la traza.

### Lote 10 (6 conversaciones LARGAS hasta el cierre de reserva, 8-12 turnos c/u, 2026-09-02)

A diferencia de los lotes anteriores (turnos sueltos por área), este lote valida el flujo
COMPLETO end-to-end: que el bot llegue a un resumen final + link de pago coherente pese a que
el cliente meta preguntas de duda típicas (clima, qué llevar, fotos, cancelación, precio en otra
unidad, hijos, certificación, refresher) a mitad del camino.

- ✅ **5 de 6 conversaciones cierran limpio** con resumen + link de pago, sin perder el hilo de
  lo ya resuelto ni repetir preguntas ya contestadas (solo/certificado, familia con niños,
  minicurso en isla, refresher, grupo mixto con cancelación).
- **⚠️🔴 CORREGIDO — bucle infinito que impedía cerrar la reserva (conversación 800, "paquete de
  5 inmersiones").** El flujo se quedaba re-preguntando "¿ha pasado más de 2 años desde la
  última inmersión?" turno tras turno sin avanzar nunca, incluso tras responderla y tras pedir
  explícitamente "hagamos la reserva". Traza de LangSmith: el turno "no hace mas de 2 años que
  buceamos" — una respuesta de SEGURIDAD que no menciona a NADIE más — disparó
  `mentions_other_person=true` + `companion_activity=certified_diving` (la MISMA actividad que
  ya tenía el grupo) en `detect_special_signals`, dejando `detected_group_allocation` corrupto
  con un compañero fantasma (`{'certified_diving': 1, 'padi_open_water': 2}` para un grupo de 2).
  Con ese reparto corrupto, la certificación/seguridad del grupo principal nunca terminaba de
  resolverse del todo — la reserva jamás llegaba al resumen final. Misma familia que el fix del
  lote 9 (`_BARE_HEADCOUNT_RE`), pero un patrón de misfire distinto: aquí no hay ningún conteo,
  el LLM simplemente inventó un acompañante de la nada. **Fix**: generalización del guard —
  cuando el mensaje responde claramente a OTRO tema de slot booleano (seguridad/certificación/
  nacionalidad, los regex de `_BOOL_FIELD_TOPIC_RE`) sin ningún respaldo textual de persona, Y la
  actividad que el LLM atribuye al "acompañante" es la MISMA que ya tiene el grupo (no una
  elección distinta — la señal real de un acompañante genuino), no se confía en el LLM tampoco.
  La condición de "misma actividad" es deliberada: preserva el caso de jerga regional que motivó
  confiar en el LLM en primer lugar ("mi parce no está certificado" → `companion_activity`
  DISTINTA de la del grupo, sigue confiando en el LLM). Tests:
  `test_safety_answer_without_person_mention_does_not_spawn_phantom_companion` +
  `test_slang_companion_with_different_activity_still_trusts_llm` en
  `tests/test_conversational_core.py`.
  - **Segunda iteración (mismo día, verificando en vivo tras el fix de arriba):** el primer fix
    acotaba la excepción a mensajes que tocan uno de los 3 temas booleanos
    (`_BOOL_FIELD_TOPIC_RE`). Repitiendo el repro exacto contra PRE tras desplegarlo, la reserva
    ya NO se quedaba en bucle — pero al confirmar el cierre ("perfecto, hagamos la reserva",
    turno posterior al resumen + link ya entregados) el MISMO patrón reapareció:
    `companion_activity=certified_diving` (otra vez la misma actividad del grupo) sin mencionar a
    nadie, y la reserva ya cerrada se REABRIÓ con "¿Qué le gustaría hacer a tu acompañante —
    minicurso o snorkel?" en vez de simplemente confirmar. Causa: "hagamos la reserva" no toca
    ninguno de los 3 temas booleanos, así que el primer fix no lo cubría. **Fix generalizado**:
    se quitó el requisito de tema — ahora basta con que el LLM diga que hay un acompañante sin
    ningún respaldo textual (`_mentions_person` false) Y que la actividad que le atribuye
    coincida con la del grupo, sea cual sea el tema del mensaje. Detalle técnico importante: el
    guard debía compararse contra lo que el LLM DIJO (`raw_companion_activity`, capturado antes
    del descarte por falta de respaldo textual), no contra la variable `activity` ya puesta a
    `None` por ese descarte — con `activity=None`, la comparación "misma actividad" nunca se
    cumplía y el guard no disparaba para mensajes (como este) que no respaldan textualmente
    ninguna actividad en absoluto. También se corrigió una segunda rama de código
    (`elif` de acompañante diferido) que leía la señal del LLM sin corregir, en crudo,
    bypaseando el guard incluso cuando `activity` ya estaba en `None`. **Verificado en vivo
    contra PRE** (conversación 804, repro completo de las 6 conversaciones): tras el resumen +
    link, "perfecto, hagamos la reserva" ahora re-confirma el mismo resumen en vez de reabrir con
    una pregunta de acompañante. Test:
    `test_closing_affirmation_without_person_mention_does_not_reopen_with_phantom_companion`.
- **📝 Anotado, sin arreglar — inconsistencia entre "¿qué pasa si llueve?" y "política de
  cancelación por mal clima".** Dos preguntas semánticamente equivalentes reciben trato distinto:
  "¿cuál es la política de cancelación si el clima está malo?" (conversación 802) obtiene una
  respuesta real y detallada (reprogramación o reembolso 100%); "¿qué pasa si llueve ese día?"
  (conversación 798) escala con el texto genérico "Las condiciones del tiempo pueden cambiar
  rápidamente. Te conecto con el equipo" — el mismo texto que se usa para una pregunta de
  pronóstico en tiempo real ("¿qué tiempo hace estos días, hay buena visibilidad?", conversación
  797, donde SÍ tiene sentido escalar porque el bot no puede saber el pronóstico real). Prioridad
  menor (no bloquea nada, solo da una respuesta más pobre de lo necesario en un caso); no
  arreglado — requiere revisar cómo se distingue "pregunta de política" de "pregunta de
  pronóstico en tiempo real" en el detector de señales, sin arriesgar romper el caso donde
  escalar SÍ es correcto.

---

## 8. Registro de ejecución
*(Una línea por paso cerrado: fecha · dev · qué · commit. El más reciente arriba.)*

- **2026-09-02 · Gadea (Claude) · companion fantasma — 2ª iteración, verificada en vivo.**
  Reproduciendo en vivo contra PRE el fix del bucle infinito (entrada siguiente), el mismo turno
  de confirmación de cierre ("perfecto, hagamos la reserva") volvió a disparar un compañero
  fantasma, esta vez reabriendo una reserva YA cerrada. El primer fix solo cubría mensajes que
  tocan uno de 3 temas booleanos; generalizado sin ese requisito + corregido un bug real de
  variable (comparar contra `raw_companion_activity`, no contra `activity` ya puesta a `None`) +
  una segunda rama de código que leía la señal del LLM sin corregir. Verificado en vivo contra
  PRE (conversación 804) repitiendo el repro completo: cierra bien y la confirmación ya no
  reabre. Suite verde en las 3 configuraciones: 1623 passed / 18 skipped.
- **2026-09-02 · Gadea (Claude) · Lote 10 (6 conversaciones LARGAS hasta el cierre de reserva) —
  bucle infinito corregido, 1 hallazgo menor anotado.** 5/6 conversaciones cerraban limpio; la
  6ª ("paquete de 5 inmersiones") se quedaba en un bucle infinito re-preguntando la pregunta de
  seguridad sin cerrar nunca la reserva — causa raíz: `detect_special_signals` inventaba un
  compañero fantasma con la MISMA actividad del grupo a partir de una respuesta de seguridad sin
  ninguna mención de persona ("no hace mas de 2 años que buceamos"), corrompiendo
  `detected_group_allocation`. Fix: guard generalizado (mismo patrón que el lote 9) que distrust
  la señal LLM cuando el mensaje responde a otro tema booleano sin respaldo textual de persona Y
  la actividad "del acompañante" coincide con la del grupo — preserva el caso de jerga regional
  ("mi parce no está certificado") donde la actividad SÍ difiere. Suite verde en las 3
  configuraciones: 1622 passed / 18 skipped. Anotado sin arreglar: inconsistencia entre "¿qué
  pasa si llueve?" (escala genérico) y "política de cancelación por clima" (respuesta real) para
  preguntas semánticamente equivalentes — prioridad menor.
- **2026-09-02 · Gadea (Claude) · re-pregunta redundante — causa raíz corregida (2ª iteración).**
  El fix del "companion fantasma" (entrada anterior) no cambió el repro al verificarlo en vivo: la
  causa real es que un mensaje con "?" nunca pasa por extracción ese turno (`_routing_phase`
  responde con RAG y retorna antes). Fix en `_answer_question`: si el mensaje respalda
  textualmente `certified_diving`, fija `is_certified=True` antes de decidir si re-preguntar.
  Verificado en vivo contra PRE (conversación 796): ya no re-pregunta. Suite verde en las 3
  configuraciones: 1620 passed / 18 skipped.
- **2026-09-02 · Gadea (Claude) · Lote 9 CERRADO — 4/4 hallazgos corregidos.** Tras el fix inicial
  de la fuga de `food_policy`, se corrigieron también los 3 hallazgos que habían quedado anotados
  sin arreglar: (1) alcohol perdido cuando llega junto con alergia en el mismo mensaje — ventana
  de proximidad ampliada 25→60 + nueva `_alcohol_and_food_policy_answer` que combina ambas
  políticas en vez de que la primera pise la segunda; (2) el override "programa normal, sin
  adaptar" de DIVE TO HEAL no usaba la info genérica esperada — traza de LangSmith confirmó que el
  LLM SÍ generaba la respuesta pero el juez de grounding la rechazaba (`HALLUCINATED`) porque la
  nota DIVE TO HEAL seguía presente en `extra_context`; fix determinista con
  `_DIVE_TO_HEAL_OVERRIDE_RE` que omite la nota en el turno donde el cliente aclara explícitamente;
  (3) re-pregunta redundante de certificación tras una pregunta de precio ("how much for 2 people,
  certified diving?") — traza de LangSmith mostró que tanto el LLM (`detect_special_signals`) como
  el regex de respaldo (`_mentions_person`) interpretaban "2 people" como un acompañante fantasma
  con la misma actividad del grupo; fix con `_BARE_HEADCOUNT_RE` que enmascara conteos totales
  ("for N people") antes de evaluar la mención de otra persona, y distrust del LLM cuando el
  regex (ya sin el conteo) no lo confirma. Los 3 siguen el mismo principio de diseño de §6.bis:
  verificación determinista del texto del turno por encima de una señal LLM de formato libre.
  Suite completa verde en las 3 configuraciones: 1619 passed / 18 skipped (+6 sobre el baseline).
  Ver §7, bloque "Lote 9" para el detalle completo de cada uno.
- **2026-09-02 · Gadea (Claude) · §7 CERRADO — DIVE TO HEAL pierde su contexto en seguimientos
  genéricos** (`179ac27`). Causa raíz real: `_build_extra_context` nunca mencionaba
  `adaptive_diving_context`, no una carrera perdida contra un doc del KB como suponía la entrada
  original (esa hipótesis no se pudo reproducir). Fix: nota explícita en `extra_context` cuando
  el flag está activo. Verificado con LLM real en local (A/B de `rag_answer`) y en vivo contra
  PRE tras redeploy a `feature/pre_alvaro`: antes, fallback genérico ante "cuántas inmersiones
  son"; después, respuesta correcta dentro del programa adaptado. Suite completa verde en las 3
  configuraciones (1612 passed / 18 skipped), 2 tests nuevos sobre baseline 1610.

- **2026-09-02 · Gadea · 3 pendientes de §6.bis/§7 cerrados**: guarda `is_coherent_text` para la
  respuesta RAG corrupta (`{" "}`, sin reproducir); campo `history` en `eval-set.json` +
  `run_extraction_eval.py` (3 casos nuevos que miden la familia "contesta de más"); prompt de
  `compose_acknowledgement` ya no reinterpreta un hecho como preferencia ("ninguno colombiano").
  Suite completa verde en las 3 configuraciones tras cada uno.
- **2026-09-01 · Gadea · §6.bis CERRADO — extractores LLM que "contestan de más"**.
  Cerradas las dos causas raíz que quedaban abiertas del bug de reparto de grupos mixtos. La
  "pérdida de actividades en el resumen final" resultó ser **falsa alarma del driver de repro**
  (`pre_driver.wait_for_reply` leía solo el primer saliente; el núcleo parte la respuesta
  multi-ítem en varios mensajes de Chatwoot) — `_build_cart_from_slots`/`_finalize` estaban bien;
  driver arreglado y trampa documentada en `scripts/inspect_langsmith_trace.py`. El bug real:
  `fill_gaps` **y** el resolutor de slot anti-bucle contestaban ellos mismos el slot de SEGURIDAD
  ("¿más de 2 años?") en un turno que solo respondía nacionalidad, cerrando la reserva sin
  preguntarlo nunca. Arreglado con dos guardas genéricas (`_BOOL_SLOT_FIELD` en `_relevant_gaps`,
  `_boolean_has_textual_backing` + `_turn_answered_a_different_slot`), reutilizando los léxicos de
  los detectores regex (`LAST_DIVE_TOPIC_RE`/`CERTIFICATION_TOPIC_RE`/`NATIONALITY_TOPIC_RE`, ahora
  a nivel de módulo). **1603 passed / 18 skipped / 0 failed** en las 3 configuraciones (default /
  `AGENT_ARCH=true` / `AGENT_ARCH_SHADOW=true`), 8 tests nuevos sobre baseline 1595; verificado en
  local con LLM real y en vivo contra PRE. Anotada como deuda de Fase 5.2 el cutover de extracción
  muerto (`_maybe_apply_llm_extraction_cutover`, sin call-site, con 4 flags inertes en PRE).

- **2026-08-11 · Álvaro · Fase 5.3 — `trace_openai` (detalle por-llamada) + SOAK abierto** (`e34c981`).
  `src/llm_client.py`: `trace_openai(client)` envuelve los 13 clientes OpenAI (9 módulos) con
  `wrap_openai` solo si el tracing está activo (no-op en dev/CI/tests → preserva los mocks de
  `AsyncOpenAI`). Ahora LangSmith tiene grafo + tokens/latencia/coste por llamada. Suite 1537
  passed (+1 flaky `test_intent_hotel_detection`, pasa al re-correr, ajeno al cambio). **Entrada
  en Fase 5.3-bis (SOAK, multi-día): parado esperando tráfico real; criterio de reanudación y
  orden del corte documentados en §5.**
- **2026-08-11 · Álvaro · Fase 5.3 — periodo de medición ABIERTO (LangSmith trazando PRE).**
  Key como GitHub secret + inyección en `.env.pre` (job `deploy-pre`). Fix de bug real:
  `config` fijaba `LANGSMITH_TRACING_V2` (var inexistente) → tracing nunca encendía; corregido a
  `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2` (`cd5a23a`). Trazas del grafo confirmadas en vivo
  (proyecto `diving-planet-bot`). También arreglado el gate del CI (`test_route_shadow.py`
  borrado seguía hardcodeado → bloqueaba el deploy; reforzado con los tests de nodos). **Periodo
  de medición en marcha; el corte del flag (5.2) espera a "igual o mejor" vs baseline.**
- **2026-08-11 · Álvaro · Fase 5.2 paso 1 — subsistema shadow retirado** (`2491be5`). Grafo
  validado (suite + PRE en vivo) → el shadow del router (Fase 1.5) ya no hace falta. Borrado
  completo (−183 líneas): 21 `_mark_route(...)` no-op + ContextVar + `_run_route_shadow` + la rama
  `elif` de `route_message` + config `agent_arch_shadow` + `test_route_shadow.py`. Sin tocar el
  rollback (flag `agent_arch` + cascada siguen). Ruff limpio, 129 verdes en orquestación/agentes/
  equivalencia. Pasos 2-3 de 5.2 documentados; el flag se quita cuando el grafo tenga confianza en PRO.
- **2026-08-11 · Álvaro · Deploy PRE — RESUELTO y validado en vivo.** El grafo sirve en PRE
  (`AGENT_ARCH=true`); el bloqueo de `dp-pre-postgres` (disco lleno de caché de build) se
  auto-resolvió desde la propia Action (prune de disco + restart de postgres, sin SSH manual).
  Validado con 5 mensajes en vivo (una ruta cada uno). Aprendizaje: la Action es la vía de acceso
  al VPS.
- **2026-07-31 · Álvaro · Deploy PRE (Stage A+B) — BLOQUEADO por infra, pendiente Gadea.**
  Añadido `AGENT_ARCH_SHADOW`→`AGENT_ARCH: "true"` a `dp-pre-bot` (PRE-only, PRO intacto) y
  llevado a `feature/pre_alvaro` (dispara la Action de auto-deploy). La Action falla en
  `deploy-pre`: **`dp-pre-postgres` unhealthy** (`pg_isready`, persistente; Redis sano) — infra del
  VPS, no el refactor (imagen OK, `AGENT_ARCH` solo env var). Anotado como paso pendiente para
  Gadea (gestiona la VPS) en §5 Fase 5. 5.2 no se ejecuta hasta validar el grafo en PRE.
- **2026-07-31 · Álvaro · Fase 4.3 — grounding único + memoria Fase C (confirmado, ya satisfecho).**
  Audit con evidencia: grounding centralizado en `grounding_check.py` + único chokepoint factual
  `supervisor.rag_answer` (info/núcleo/DIVE TO HEAL pasan por ahí; ~50 aserciones en
  `test_rag_safety.py`); memoria Fase C (`remembered_facts`/notes) ya en el State canónico y
  alimentando el contexto RAG; doc ya archivado. Decisiones deliberadas: no middleware de
  grounding para nodos de copy determinista; notes se captura en booking, no cross-route (evita
  añadir `extract_notes` a cada turno y deshacer 3.4). **Fase 4 COMPLETA.** Siguiente: Fase 5.
- **2026-07-31 · Álvaro · Fase 4.1+4.2 — reencuadre aprobado (estado ya consolidado).** Audit:
  `ConversationState` (dataclass ~60 campos) ya es el State único que todos los nodos comparten
  por referencia; cero estado de conversación disperso. **4.1**: confirmar+documentar como State
  canónico (NO re-tipar a BotState plano — big-bang contra strangler, reducer inútil en topología
  lineal). **4.2**: mantener `state_store.py` sin cambios (persiste el `ConversationState`
  canónico; checkpointer de LangGraph descartado por ahora — sin replay, evita migración + la
  superficie SQLi→RCE). Docstring de `state.py` + plan actualizados. Siguiente: **4.3** (grounding
  único + memoria/notes), la parte sustantiva de la fase.
- **2026-07-31 · Álvaro · Fase 3.4 — medición desbloqueada + 1ª reducción de llamadas/turno.**
  Con Postgres+Redis arriba: el grafo mide **3.00 llamadas/turno = baseline** (paridad tras el
  refactor, confirmada empíricamente). Atribuida cada llamada a su red (traza del caller). 1ª
  reducción segura: `fill_gaps` se salta en un saludo puro (`_is_greeting_only`) → **3.00 → 2.80
  llamadas/turno** (saludo 2→1), preservador de conducta. 508 tests de regresión verdes + test
  nuevo `test_llm_call_reduction.py`. Siguientes candidatos analizados y **diferidos con criterio**
  (no son seguros: redes intencionalmente separadas / red de seguridad del router). **Fase 3.4
  cerrada; suite COMPLETA verde con la reducción dentro: 1538 passed / 9 skipped / 0 failed
  (6:15). Fase 3 COMPLETA.**
- **2026-07-30 · Gonzalo · Fase 3.2 — prompts a `src/prompts/`, un módulo por nodo.** Sincronizada
  la rama (`feature/agent-arch` traída a `feature/fase4-p2`, fast-forward de 48 commits) y
  cerrado el siguiente paso del plan. Nuevo paquete `src/prompts/` (`router.py` · `booking.py` ·
  `info.py` · `memory.py` + índice en `__init__.py`) con **25 símbolos** movidos desde 8 módulos
  de `src/agents/`: los **11 prompts** del bot (constantes por idioma o builders), los 4
  tool-schemas estáticos, la factoría `slot_resolver_tool` y el `SLOT_RESOLVER_SPEC`. **Hallazgo:** no existía el "prompt gigante que lo abarca todo" que el
  enunciado de 3.2 asumía — cada red ya tenía su prompt enfocado; lo que faltaba era sacarlos de
  módulos de lógica de 900-1300 líneas para poder revisarlos. Así que 3.2 fue **reubicar sin
  tocar texto** (recortar sería cambio de conducta, principio #1), incluyendo los tool-schemas
  porque sus descripciones de campo son prompt de verdad (varias afinadas midiendo en vivo).
  `src/prompts/` es una **hoja** del grafo de imports: no importa nada de `src/`, así que ningún
  agente puede crear un ciclo al importar el suyo.
  **Equivalencia byte a byte probada, no asumida**: nuevo `scripts/snapshot_prompts.py` renderiza
  los **61 prompts** (todas las variantes de idioma/argumentos + el prompt RAG ensamblado) con
  SHA-256 → snapshot antes vs. después con **diff vacío**; el corte se hizo con un script mecánico
  por rangos de AST (no reescribiendo texto a mano). Verificado además: **baseline completa medida
  en esta máquina antes de tocar nada (1492 passed / 18 skipped)**, los 27 tests nuevos y los
  subconjuntos afectados en verde, ruff + compileall limpios; la pasada completa en los **3 modos**
  (default/`AGENT_ARCH`/`AGENT_ARCH_SHADOW`) quedó **en vuelo al commitear** — esperado 1519
  passed / 18 skipped (1492 + 27), **a confirmar aquí cuando termine**. **27 tests nuevos**
  (`tests/test_prompts_surface.py`): propiedad de hoja por AST, identidad red↔módulo de prompts
  (una copia inlineada falla en vez de desincronizarse en silencio), y cobertura del snapshot
  *derivada* de lo que renderiza de verdad. Métricas: −1148 líneas en los 8 módulos de agentes
  (`llm_extractor` 898→302, `escalation` 479→180, `notes_extractor` 148→84, `rag_agent`
  1336→1210, …), +1282 en `src/prompts/`. Marcado también **2.0** (el contrato de nodo lo había
  fijado el spike 0.6; el checkbox estaba sin marcar por despiste).
  **Siguiente: 3.4** — anotado en el paso: hasta ahora no hay nada que medir (3.1/3.2/3.3 son
  estructurales y preservan conducta ⇒ siguen siendo 3.00 llamadas/turno por construcción) y
  volver a medir está **bloqueado por entorno** (Docker Desktop en 500 → sin Postgres, y sigue
  sin haber `LANGSMITH_API_KEY`).
- **2026-07-30 · Gadea · Fase 3.1 — mapa red→nodo (reubicación funcional; física diferida).**
  Auditado que tras el corte del núcleo (3.3) cada red LLM ya se llama desde su nodo dueño
  (objetivo funcional de 3.1 conseguido). Documentado el mapa completo + auditoría de
  solapamientos en `docs/agent-arch-design.md` §7: ninguno problemático (los del §0 están
  estructuralmente contenidos por el router+classify_route). Únicos cross-node a propósito:
  `detect_routing_signals` (compartida, 1 llamada/turno) y `fill_gaps` en el cutover legacy
  flagged (NO tocar). La reubicación FÍSICA a `src/agents/_nets/` queda diferida como churn de
  valor solo organizativo (reapunta imports de core/supervisor/tests). Solo docs, cero cambio
  de código/comportamiento. Suite intacta (1492). Siguiente: **3.2** (prompts) / **3.4** (medir).
- **2026-07-30 · Gadea · Fase 3.3a/b/c/d/e — corte del núcleo (subgrafo booking) COMPLETO.**
  Corte del monolito del núcleo (~2.249 líneas) en un subgrafo LangGraph, con strangler y
  equivalencia por construcción (cascada y subgrafo llaman a las MISMAS funciones extraídas).
  **3.3a** (`47c72cf`): andamiaje — la ruta BOOKING invoca un subgrafo que envuelve el núcleo
  (1 nodo `core`). **3.3b** (`4c53d5c`): `maybe_handle_turn` descompuesto en `_setup_phase` +
  `_body_phase` → subgrafo de 2 nodos; equivalencia verificada por 3 vías (suite 3 modos, smoke
  en vivo donde las diferencias flag on/off son solo no-determinismo del LLM confirmado por
  off-vs-off, y el diff no toca la lógica del body). **3.3c** (`c6765d4`): disponibilidad
  peelada a `_availability_phase` → 3 nodos (bajo riesgo, autocontenido). **3.3d** (`5e7420b`):
  `_body_phase` partido en `_routing_phase` + `_extract_close_phase` (carry de 10 `prev_*`/
  `resolved_short`). **3.3e** (`41368dc`): `_extract_close_phase` partido en `_extraction_phase`
  (understand + multi-ítem + redes de precisión + anti-bucle) + `_slotfill_close_phase` (RESOLVER
  + RESPONDER). **✅ Núcleo partido en 5 fases de responsabilidad única:** subgrafo `setup →
  availability → routing → extraction → slotfill_close`, todas compartidas por cascada y subgrafo.
  Suite verde en los 3 modos tras cada paso (1491→1492) + smoke en vivo por los 5 nodos. **NOTA
  patrón B (audit §1.5):** la disponibilidad se AISLÓ en su nodo pero SIGUE en booking con la
  misma conducta — no se movió a `changes`; eso es decisión del cutover (Fase 5.2).
  **3.3 en la práctica completa.** Siguiente: **3.1** (reubicar redes a nodos) / **3.2** (prompts
  a `src/prompts/`) / **3.4** (medir llamadas LLM/turno vs baseline de Fase 0).
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
