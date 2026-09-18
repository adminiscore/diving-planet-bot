# Plan maestro final — Coral (Diving Planet bot)

> **Handoff (2026-09-16, Álvaro → Gadea).** Este documento reúne TODO el contexto para arrancar el
> siguiente ciclo de trabajo como si lo hubiera dejado yo: qué tenemos hoy, qué se descubrió, el plan
> completo por fases con medición, y por dónde empezar. Fuentes cruzadas: las 2 capturas de análisis de
> latencia/estructura, el reporte HTML de arquitectura, y los dos planes vivos
> (`docs/multi-agent-refactor-plan.md`, `docs/robustness/plan.md`).

> **Estado M0 a 2026-09-17 (Gadea → equipo; tareas de cualquiera).** Seguimiento vivo en la página
> "Plan Coral" (https://claude.ai/artifact/XiGd3kguTNwwqTnH7mQwgi) y detalle en
> `docs/project-history/session-handoff.md` (banner 2026-09-17).
> - ✅ m0-3 golden-set + LLM-juez calibrado (gpt-5-mini medium + revisión humana); ronda 1: 95,1 %.
> - ✅ m0-6 fotos de Langfuse + página; ✅ m0-8 saludo verificado en vivo.
> - ✅ **m0-7 línea base de calidad CONGELADA (2026-09-17, Gonzalo)**: eval-set 220/230 (modo script)
>   y **230/230 por el núcleo**, booleanos 33/33 y 30/30, router 33/37 (`base`), actividad 10/10 ·
>   10/10 · 6/9, grupo (config PRE) 17/17 · 13/13 · 17/17 con 0 alucinaciones, RAG 38/39 y
>   recuperación 16/20 ES / 13/20 EN. Foto **por caso** en
>   `docs/robustness/baselines/2026-09-17-m0-7/`; detalle y hallazgos en
>   `docs/robustness/progress-log.md` (entrada 2026-09-17).
> - 🟡 m0-4 datos del golden-set: sintéticos hechos; falta tráfico real (harvest).
> - ✅ m0-2 cubierta por `run_synthetic_pre --sample rapida` + `langfuse_snapshot` (2026-09-18, sin script nuevo).
> - ⏳ m0-1 / m0-5 Langfuse (resumen por turno, negocio, traza que junta turnos).
> - 10 fallos del bot del golden-set como tareas S4-6..S4-16 (varios encajan en U3).

---

## PARTE 0 — Estado actual: qué tenemos / qué falta (leer primero)

### Lo que YA tenemos y está vivo en PRE
El bot **ya usa un orquestador que reparte a agentes distintos** (arquitectura multi-agente LangGraph,
`AGENT_ARCH=true` en `dp-pre-bot`). Cada mensaje hace:

```
Cliente (Chatwoot)
  → cargar memoria de la conversación (Redis, ConversationState)
  → ORQUESTADOR (router): clasifica el mensaje y decide a qué agente va
  → uno de 5 agentes:
       • booking (reserva)  → arma plan, precios, carrito (el más usado; tiene su propio subgrafo de 5 fases)
       • info               → responde preguntas por RAG (base de conocimiento)
       • escalation         → pasa a humano (sensible, PII)
       • changes            → cancelar / reprogramar
       • deflection         → contacto, "¿eres un bot?"
  → el agente responde → guardar memoria → enviar por Chatwoot   (traza a Langfuse en paralelo)
```

Esto está **construido, probado y en PRE**. NO es idea pendiente.

### La única fuente de confusión: conviven DOS "cerebros"
- **Nuevo** (grafo: orquestador → 5 agentes) → ENCENDIDO en PRE.
- **Viejo** (la "cascada": una función gigante que revisa reglas en orden, `supervisor._shared_turn_handler`)
  → apagado como camino principal, pero **sigue en el código** de red de seguridad y como camino cuando el
  flag está off. Se hizo así a propósito (poder volver atrás). "Cortar el legacy" = borrar el viejo para
  dejar UN solo cerebro.

### Lo que falta, en 3 frases
1. **Ir más rápido** (medir en Langfuse y quitar trabajo repetido/en serie).
2. **Borrar el cerebro viejo** y ordenar los 2 ficheros gigantes.
3. **Seguir afinando cuánto entiende** (calidad de extracción).

### Estado de esta sesión (lo recién cerrado — contexto para no repetir)
- **Deploy a PRE ARREGLADO (causa raíz).** El job `deploy-pre` usaba `ssh host 'script largo…'`; una
  comilla simple dentro del script rompía el entrecomillado y **truncaba** el script remoto (moría tras
  `git checkout`, nunca llegaba a `docker compose up --build`) → deploy "verde en 9s" pero **sin
  reconstruir el bot** → PRE servía código viejo días. Encima el `ci.yml` estaba en CRLF. **Fix
  (commit `0656eb0`):** el script viaja por STDIN con `bash -s <<'REMOTE'` (inmune a comillas) + fichero
  en **LF** + `.gitattributes` que fuerza LF en `*.yml/*.sh/Dockerfile`. Ahora el deploy imprime
  `git log --oneline -1` (SHA desplegado) y `GREETING_FIX_LIVE=` (verifica el fix dentro del contenedor),
  y hace `--force-recreate`. **Heurística:** un `deploy-pre` que acaba en segundos NO reconstruyó (un build
  real + `load_embeddings` son minutos).
- **Fix del saludo doble** (`"hola que tal?"` daba saludo + saludo RAG): corregido en código
  (`_is_greeting_only` + guards en las fases de `conversational_core`); verificado con 879 tests + repro
  de punta a punta por el grafo. Debía quedar live tras el deploy `0656eb0`.
- **Observabilidad:** migrada de LangSmith (cuota agotada) a **Langfuse**. Import lazy, gated por claves
  (langfuse casca al import en Py3.14; PRE/CI son 3.11). Confirmado trazando en PRE.
- **Chatwoot:** el widget se cayó por disco lleno (Rails 500). El deploy ahora reinicia `dp-chatwoot`
  condicionalmente si no responde.
- **Ramas:** trabajo en `feature/agent-arch` (dev de Álvaro) y `feature/pre_alvaro` (deploy). **`pre_gadea`
  intacta en `eda6929`** por decisión del owner. PRO no existe.

---

## PARTE 1 — Hallazgos verificados (las capturas son CIERTAS)
Comprobado contra el código en esta sesión:
- `intent_detector.py` = **2367 líneas** (exacto); `conversational_core.py` = **4174**; `supervisor.py` = **3273**.
- El entendimiento del mensaje está **repartido en 4 sitios**: `detect_routing_signals` (router, mini) +
  `intent_detector` (regex) + `fill_gaps`/`detect_special_signals`/`resolve_slot_answer` (núcleo, mini).
  `fill_gaps` se llama en `conversational_core.py:2057` **y** `:2089`; `extract_notes` en `:1906`;
  `compose_acknowledgement` en `:4068`.
- **RAG (turno más lento, todo `gpt-4o`):** `condense_query`(4o) → embedding → answer(4o) → juez
  `is_grounded`(4o). El juez **re-juzga la MISMA respuesta** antes de regenerar
  (`_verify_grounding_with_retry`, `rag_agent.py:1337-1344`) → gasto inútil. En el peor caso 6–8 llamadas.
- **Turno de reserva:** hasta ~5 llamadas en serie (`detect_routing_signals` + `detect_special_signals`/
  `fill_gaps` + `resolve_slot_answer` + `extract_notes` + `compose_acknowledgement`). Las 3 primeras leen
  el mismo mensaje para sacar cosas distintas = duplicación de entendimiento convertida en latencia.
- **Modelos:** extracción = `gpt-4o-mini`; RAG/condense/grounding = `gpt-4o`. **Paralelismo:** solo
  vector + BM25.
- Lo que la captura marca ✅ es correcto: **State único** (`ConversationState`, ~68 campos) y **grounding
  unificado** ya están hechos (refactor Fase 4). Datos duros deterministas desde Python/JSON, respuestas
  verificadas contra el contexto = por delante de un bot típico.

**La estructura de referencia de la captura 1 es correcta** (coincide con bots de reserva profesionales).
Ver PARTE 2 para las mejoras que añadimos por encima, hasta nivel de las grandes compañías.

---

## PARTE 2 — Estructura objetivo (la ideal, mapeada a Coral)
```
Canal → Ingesta (agrupar/idempotencia) → Cargar estado
     → ENTENDER (1 llamada estructurada: intención + datos + señales)
     → Gestor de diálogo (FSM/slot-fill determinista)
     → Acciones (catálogo, precios, carrito, disponibilidad)
     → RAG (solo si hace falta) → Redactar → Verificar → Enviar
     → En 2º plano / paralelo: notas, resumen, trazas
```
Coral ya tiene casi todas las capas. Las tres brechas a cerrar: **entender-una-vez**, **una sola
arquitectura**, **tareas secundarias fuera del turno**.

**Mejoras que añadimos más allá de la captura, para nivel "grandes compañías":**
(a) caché semántica de RAG + prompt-caching de OpenAI; (b) right-sizing de modelos por llamada;
(c) gates de calidad **y** latencia en CI; (d) "entender una sola vez" como pieza central (conecta con el
regex de 2367 líneas y la directiva del owner de extracción por LLM); (e) **resiliencia** (timeouts,
fallback si el LLM cae/va lento, backoff 429); (f) **guardrails** (inyección de prompts / jailbreak);
(g) **métricas de negocio** (embudo de conversión, escalado, % fallback); (h) **eval end-to-end** con
LLM-juez sobre diálogos dorados; (i) **datos sintéticos** para crecer el golden-set; (j) **streaming /
latencia percibida**.

---

## PARTE 3 — Principio de medición (transversal, requisito del owner)
Cada fase se abre y se cierra con la **misma foto**, comparando *lo que teníamos* vs *lo nuevo*:
- **Calidad (sin sorpresa de RPD):** `scripts/run_extraction_eval` (230 aserciones, y `--core`),
  `scripts/battery_{group_allocation_gate,boolean_anchoring,router_signals,activity_choice}`,
  `scripts/eval_rag_answers`, `scripts/eval_retrieval`. **Foto por caso** (`diff` de líneas `[OK]/[GAP] id`),
  no solo el agregado. Baseline de HEAD con `git worktree add --detach <scratchpad>/wt_head HEAD` (nunca
  `git stash`).
- **Latencia + coste (Langfuse):** p50/p95 por **nodo** y por **llamada LLM**, nº de llamadas/turno, por
  tipo de turno (saludo / extracción / RAG / cierre). Nueva `scripts/battery_latency.py`.
- **Reglas del owner:** nada de parches regex (buscar el mecanismo común / la vía LLM); una fuente por
  concepto; **RPD es el recurso escaso** (no lanzar LLM en paralelo en las tandas de eval, un 429 aborta
  la tanda); un cambio que mejora el agregado pero empeora un caso NO vale; latencia que degrada calidad
  NO vale. **Todo cambio de conducta va detrás de flag** hasta que la foto A/B lo aprueba. PRO no existe:
  el criterio de corte es **PRE validado a fondo (~90%)**.

---

## PARTE 4 — Roadmap (orden: medir primero → wins baratos → fusión → corte)

### Fase M0 — Instrumentación y línea base · **BLOQUEANTE, antes de tocar nada**
- Enriquecer la traza de Langfuse: spans por nodo del grafo (ya hay `CallbackHandler`) + latencia por
  llamada (`langfuse.openai` ya la captura) + resumen por turno (nº llamadas, ms por nodo).
  Ficheros: `src/observability.py`, `src/orchestration/graph.py`.
- `scripts/battery_latency.py` (nueva): reproduce los 5 turnos canónicos y vuelca p50/p95 por nodo.
- **Golden-set de diálogos + LLM-juez end-to-end:** conversaciones completas con respuesta esperada,
  juzgadas por un LLM (calidad de la RESPUESTA final, no solo extracción). Se **crece con datos
  sintéticos** (diálogos límite: grupos mixtos, cortesías, off-topic, intentos de inyección) + tráfico
  real curado por `harvest_cutover_logs`.
- **Métricas de negocio en Langfuse:** embudo saludo→actividad→carrito→reserva, tasa de escalado, %
  fallback/"no lo tengo".
- Congelar baseline de calidad (eval-set + baterías + RAG + golden-set) y de latencia/negocio.
- **DoD:** Langfuse muestra, por tipo de turno, nº de llamadas, p50/p95 por nodo y el embudo; baseline
  guardada; sin cambios de conducta. *(Álvaro instrumentación · Gadea golden-set/juez · Gonzalo battery_latency)*

### Fase L1 — Wins de latencia baratos y seguros · *preservan conducta*
1. **RAG sin doble juez:** `_verify_grounding_with_retry` juzga UNA vez; si falla, **regenera** y juzga.
2. **Checks deterministas primero:** `currency_amounts_grounded`/`urls_grounded`/`capacity_claims_grounded`
   antes; el juez LLM solo si pasan.
3. **Saltar `condense_query`** si no hay historial o el mensaje ya es autónomo.
4. **Sacar del turno** (`asyncio.create_task` tras enviar): `extract_notes`, `maybe_update_summary`, trazas.
5. **Paralelizar** llamadas independientes donde sea seguro (medido).
- Cada punto: foto calidad (0 regresiones) + delta de latencia en Langfuse. *(Álvaro RAG/turno · Gonzalo medición)*

### Fase L2 — Right-sizing de modelos + caching · *latencia + coste, con eval*
- Evaluar por llamada: juez de grounding y `condense_query` en `gpt-4o-mini` (A/B contra `eval_rag_answers`/
  `eval_retrieval`); mantener `gpt-4o` en la respuesta RAG salvo que un modelo menor iguale el eval.
- **Prompt caching** de OpenAI (system-prompts/tool-schemas) + **caché semántica** de FAQ repetidas.
- **Streaming / latencia percibida:** investigar envío por partes / "escribiendo" en Chatwoot; si no, trocear.
  *(Gonzalo)*

### Fase U3 — Unificación del entendimiento · **CONSERVADOR, detrás de flag** · *el cambio grande*
- **UNA llamada estructurada** (function-calling/JSON) que devuelve intención + slots + señales, dueña en
  router/setup, consumida por los nodos → reduce el reparto en 4 y encoge el regex de `intent_detector`
  a un **fast-path determinista** + backstop LLM. Alinea con la directiva del owner (extracción por LLM) y
  con el candidato ya diferido en refactor Fase 3.4.
- Flag `unified_understanding`. **A/B obligatorio:** eval-set (230) + TODAS las baterías + latencia,
  unificado vs actual, **por caso**. Solo se promociona si calidad ≥ actual **y** latencia ↓. El regex se
  queda como fast-path (no se borra a ciegas). *(Gadea — es su dominio)*

### Fase S4 — Corte del legacy + consolidación estructural
- Refactor Fase 5.2 Paso 3: **quitar el flag `agent_arch`** (grafo incondicional) + borrar gates
  pre-núcleo muertos de la cascada (reachability + suite tras cada borrado). Gated en PRE ~90%.
- **Partir los 2 módulos gigantes** `conversational_core.py` (4174) y `supervisor.py` (3273) por nodo
  (cerrar el 3.1 físico diferido: `src/agents/_nets/` o ficheros por nodo).
- Robustez **Fase 6** (bucle de datos, `harvest_cutover_logs.py`) → **Fase 5** (regex muerto). Huecos de
  detector (nat-mixto, señales router s02/n07/r07-r09) por el mecanismo general / U3, **no** por parches.
- **Limpieza:** retirar la dep muerta `langsmith` de `pyproject.toml`. *(Álvaro corte+split · Gadea datos+detector)*

### Fase R6 — Robustez de producción (resiliencia + guardrails) · *en paralelo; antes de entregar*
- **Resiliencia:** timeout por llamada LLM + **fallback** cuando OpenAI cae/va lento (enlatado / ofrecer
  humano) + **backoff** ante 429. El bot nunca deja al cliente sin respuesta.
- **Guardrails:** defensa ante **inyección de prompts / jailbreak** en texto libre y en lo que entra al RAG
  (grounding + máscara PII cubren parte; falta el vector de inyección). Medido con casos sintéticos del
  golden-set. *(Gonzalo resiliencia · Gadea guardrails)*

### Fase Q5 — Calidad continua + entrega
- Gate en CI: **golden-set** de regresión (incl. LLM-juez e2e) + **presupuesto de latencia** en Langfuse
  (alerta si p95 empeora) + **métricas de negocio** vigiladas. SOAK en PRE. Entrega directa al cliente
  (sin PRO intermedio).

---

## PARTE 5 — Cobertura: nada queda fuera
| Origen | Punto | Fase |
|---|---|---|
| Captura 2 | 1 llamada para entender | U3 |
| Captura 2 | Sacar del turno notas/resumen/trazas | L1.4 |
| Captura 2 | Abaratar RAG (saltar condense, mini, juez 1 vez, checks deterministas antes) | L1.1-3, L2 |
| Captura 2 | Terminar el corte del legacy | S4 |
| Captura 2 | Medir antes de tocar nada | M0 |
| Captura 1 | Estructura de referencia | Objetivo + M0→S4 |
| 3 frases | Ir más rápido / borrar viejo+ordenar / afinar entendimiento | M0+L1+L2 / S4 / U3+S4 |
| Plan refactor | Fase 5.2 Paso 3 + 3.1 físico (split módulos) | S4 |
| Plan robustez | Fase 6 → Fase 5 + huecos detector | S4 |
| Observabilidad | Retirar `langsmith` | S4 |
| Grandes cías | Right-sizing + caching + streaming | L2 |
| Grandes cías | Resiliencia (timeouts/fallback/429) | R6 |
| Grandes cías | Guardrails (inyección/jailbreak) | R6 |
| Grandes cías | Métricas de negocio | M0 + Q5 |
| Grandes cías | Eval e2e (LLM-juez) + datos sintéticos | M0 |
| Owner | Medición por caso, calidad+latencia, antes/después, Langfuse | Principio de medición + todas |
| Owner | Nada de parches regex; una fuente por concepto | U3 + S4 |

---

## PARTE 6 — Qué NO rehacer (ya está bien / hecho)
State único (`ConversationState`, Fase 4), grounding unificado (`grounding_check`+`rag_answer`, Fase 4.3),
prompts por nodo (`src/prompts/`, Fase 3.2), subgrafo booking en 5 fases (Fase 3.3), fuentes deterministas
de verdad (`money.py`/`activities.py`/`catalog.py`/`eligibility.py`), Langfuse con máscara PII.

---

## PARTE 7 — Cómo empezar (para Gadea)
1. **Empieza por M0** (bloqueante): sin línea base no se puede medir ninguna mejora. Instrumentar Langfuse
   (per-nodo/per-llamada), crear `scripts/battery_latency.py`, montar el golden-set + LLM-juez, y congelar
   la baseline de calidad y latencia. **No cambies conducta en M0.**
2. **Trabaja en `feature/pre_alvaro`** (o tu rama e integra), NO en `pre_gadea` sin querer disparar deploy.
   El deploy a PRE se dispara con push a una rama `pre_*` y ya funciona bien (heredoc/LF); mira el log del
   job `deploy-pre` para `git log` (SHA) y `GREETING_FIX_LIVE=`.
3. **Mediciones:** eval-set con `PYTHONPATH=. ENV_FILE=.env.dev python -m scripts.run_extraction_eval`
   (sin `ENV_FILE=.env.dev` no hay clave y degrada); baterías `ENV_FILE=.env.dev python -m
   scripts.battery_*`; foto de prompts `scripts/snapshot_prompts.py`. Recuerda: **RPD escaso**, no
   paralelices LLM en las tandas.
4. **Ficheros fuente de verdad:** `src/agents/{conversational_core,supervisor,intent_detector,rag_agent,
   llm_extractor,grounding_check,query_rewriter}.py`, `src/orchestration/{graph,router,state}.py`,
   `src/observability.py`, `src/config.py`, `src/prompts/*`. Planes:
   `docs/multi-agent-refactor-plan.md` (§3.4, §5), `docs/robustness/{plan.md,NEXT-SESSION-PROMPT.md,
   progress-log.md}`. Runbook de deploy: `docs/deploy-pre-redeploy.md`. Handoff operativo:
   `docs/project-history/session-handoff.md` (banner 2026-09-16).

**Regla de oro del ciclo:** cada fase abre con baseline (calidad + latencia), cambia detrás de flag,
cierra con foto A/B por caso, y se ve la mejora en Langfuse. No empezamos de cero — lo grande
(orquestador → agentes) ya está; esto es acelerar, limpiar y pulir hasta nivel producción.
