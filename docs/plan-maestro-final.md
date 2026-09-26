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
>   10/10 · 6/9, grupo (config PRE) 17/17 · 13/13 · 17/17 con 0 alucinaciones. **RAG corregido el
>   23-sep** (la primera tanda salió de un `.env` con umbral 0,50 / top-k 5 / gpt-4o, no el de PRE):
>   respuestas **39/39 con 1 fallback** y recuperación **20/20 ES / 19/20 EN**. Foto **por caso** en
>   `docs/robustness/baselines/2026-09-17-m0-7/` (ficheros `*_pre.*` = config de PRE); detalle y la
>   corrección, en `docs/robustness/progress-log.md` (entrada 2026-09-17).
> - 🟡 m0-4 datos del golden-set: sintéticos hechos; falta tráfico real (harvest).
> - ✅ m0-2 cubierta por `run_synthetic_pre --sample rapida` + `langfuse_snapshot` (2026-09-18, sin script nuevo).
> - ✅ m0-1 una traza por turno con resumen (tipo, ruta, RAG, link, escalado; sesión = conversación) (2026-09-18).
> - ✅ m0-5 métricas de negocio por conversación (2026-09-21). Línea base golden-set: actividad 22 %, carrito 22 %, link 19,5 %, escalado 14,6 %, fallback 1,6 % de turnos.
> - **M0 cerrada salvo m0-4** (tráfico real: necesita SSH y que PRE tenga clientes). Siguiente: **L1** y **U3**. Latencia: comparar antes/después el MISMO día (la API de OpenAI varía ~25 % entre días).
> - 10 fallos del bot del golden-set como tareas S4-6..S4-16 (varios encajan en U3).

> **📏 Cómo se mide desde el 24-sep-2026 (decisiones de Gadea, para todo el equipo):** la latencia y las llamadas se sacan de nuestros logs (`[TURN_METRICS]` + `scripts/turn_metrics.py`) hasta que vuelva Langfuse (plan gratuito superado, reinicio 16-oct); y las pruebas A/B van por escalones (local → 1+1 juzgando solo lo que cambia → 2+2 si hay dudas; ronda completa solo al cerrar fase). Detalle: **`docs/robustness/protocolo-medicion.md`**.

> **▶️ Estado a 26-sep-2026 (tarde):** L1 cerrada; U3 a medias: u3-1 hecha, **u3-4 PROMOCIONADA** (ronda
> B3, `ANSWER_AND_CONTINUE=true` en PRE), u3-5 en curso. CI arreglado (roto desde el 24-sep) y modelos fijados.
> **Desde hoy el plan se ejecuta en SECUENCIA (decisión del owner): lo pendiente se cierra antes de avanzar
> y no hay trabajo en paralelo.** El orden vigente, con su criterio de "hecho", es la **PARTE 8** (al final).

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
- **RAG (turno más lento):** `condense_query` (`gpt-4o-mini`) → embedding → answer (`gpt-4.1-mini`) →
  juez `is_grounded` (`gpt-4o-mini`). *(Corregido 25-sep: decía `gpt-4o` en todo, que era el valor por
  defecto del CÓDIGO; PRE fijaba otros desde su `.env.pre`. Desde el 25-sep el código trae los de PRE
  y el compose los fija. Mapa único: `README.md`, "LLM models".)* El juez **re-juzga la MISMA respuesta** antes de regenerar
  (`_verify_grounding_with_retry`, `rag_agent.py:1337-1344`) → gasto inútil. En el peor caso 6–8 llamadas.
- **Turno de reserva:** hasta ~5 llamadas en serie (`detect_routing_signals` + `detect_special_signals`/
  `fill_gaps` + `resolve_slot_answer` + `extract_notes` + `compose_acknowledgement`). Las 3 primeras leen
  el mismo mensaje para sacar cosas distintas = duplicación de entendimiento convertida en latencia.
- **Modelos (en PRE):** todo `gpt-4o-mini` salvo la respuesta del RAG (`gpt-4.1-mini`); las señales del
  router, con Jev. *(Corregido 25-sep: decía RAG/condense/grounding = `gpt-4o`.)* **Paralelismo:** solo
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

## PARTE 4 — Roadmap (orden: medir primero → examen robusto → wins baratos → fusión → corte)

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

### Fase G — Golden-set robusto con casos reales · **G1+G2 bloquean L1** · *añadida 2026-09-21*
Por qué: el golden-set v6 (43 diálogos) es sintético y apenas cubre lo que más pregunta el cliente real
(islas/ubicación, formularios, fotos). Sin un examen que se parezca a la realidad, las mejoras de L1 en
adelante no se pueden dar por buenas. **m0-4 sigue en paralelo**: m0-4 *mide* (línea base con tráfico real
por el widget), G *construye el examen*; lo que cosecha m0-4 entra en G4.

Punto de partida, `data/knowledge_base/conversations.json` (revisado 21-sep): 107 ejemplos = 40 chats
reales de WhatsApp troceados + 10 resumidos a mano; 65 ES / 42 EN; temas reales: certificación 70,
islas/ubicación 52, disponibilidad 26, precios 24, descuento colombiano 19, equipo, pago, punto de
encuentro, formularios, fotos. Problemas: 34 importados vacíos ("Hola buenas tardes"/bienvenida), 26 con
texto del centro mezclado en el lado cliente, anonimización floja (quedan nombres, dominios, enlaces),
respuestas desfasadas (descuento colombiano quitado en v0.18.0) y **contaminación**: el RAG ya los usa como
few-shot (`_select_fewshot_examples`), así que tal cual inflarían la nota.

1. **G1 — Minar los chats reales:** script que limpia, separa cliente/centro, trocea en turnos, anonimiza
   (nombres, enlaces, correos) y descarta vacíos → ~25-30 diálogos nuevos. Criterios propuestos por LLM a
   partir de la respuesta del equipo **+ KB actual** (la KB manda si discrepan), revisados por humanos.
   **Split examen/entrenamiento por chat de origen:** los chats que pasan al golden salen del few-shot.
2. **G2 — Mapa de cobertura:** cada caso etiquetado intención × actividad × idioma × perfil (solo, grupo
   mixto, familia) × dificultad; golden proporcional a la distribución real + cola de casos críticos
   (seguridad, inyección, quejas). Huecos visibles en la página. Golden partido en **core** (rápido) y **full**.
3. **G3 — Simulador de usuario con LLM** (modo nuevo de `run_synthetic_pre`): personas sacadas de los chats
   reales, con objetivo y datos ocultos que el bot tiene que preguntar; habla con PRE por el inbox
   sintético; juez actual + criterios genéricos (logra el objetivo, no inventa, no repregunta lo dicho).
   Los fallos son *candidatos* al golden, con revisión humana. En serie (RPD).
4. **G4 — Bucle producción → regresión:** conversación cosechada (m0-4 ahora, PRO después) que falla →
   caso `source=prod` en el golden. Regla: ningún fallo arreglado sin su caso de regresión.
   - **G4b · Modo entrenamiento** *(decisión del owner, 21-sep; tarea `g-4b` en la página)*. Capa **encima
     de Chatwoot** con **flag on/off**, sin tocar el núcleo: con el modo activo el bot **sugiere** en vez
     de enviar — su respuesta va a una cola de revisión (nota privada / etiqueta / inbox aparte) y un
     humano la **acepta o corrige** antes de que salga al cliente. **Cada corrección se convierte en un
     caso de regresión** del golden (`source=training`). Es la fuente de datos etiquetados más barata que
     tenemos (el equipo ya atiende por Chatwoot). Depende de G1+G2; no bloquea L1.
5. **G5 — Carga aparte** (Locust/k6): p95 con N concurrentes y 429; mide volumen, no calidad → en R6.
6. **G6 — Testers reales (20-50)** justo antes de PRO, con tareas libres; sus conversaciones entran por G4.
- **Orden:** G1+G2 → (L1 puede empezar) → G3; G4 continuo; G5 con R6; G6 antes de entregar (Q5).
- **DoD G1+G2:** golden v7 con casos reales anonimizados y revisados, split sin fugas al few-shot, mapa de
  cobertura publicado, nueva ronda del juez como línea base de calidad.
- **Estado (22-sep):** G2 hecha; G1 casi (falta comparar con el minado de Álvaro y retirar conversations.json, g-7).
  Golden v7 = 116 diálogos (73 reales), **core** de 32 (día a día) y **examen oculto** de 21 (solo al cerrar fase;
  no se mira al arreglar). **Línea base v7 revisada: 83,8 % de criterios, 38/116 sin fallos (reales 78,8 %, 9/73).**
  Los fallos, agrupados por causa, ya son tareas: u3-4/u3-5 (entender el mensaje: la causa mayor), l1-6/l1-7 (RAG),
  g-7, g-8, s4-20..22. Regla: soluciones globales por causa, nunca caso a caso del golden.

### Fase L1 — Wins de latencia baratos y seguros · *preservan conducta*
> **✅ L1 CERRADA el 2026-09-24 (l1-8).** Hechas l1-1 (juez de grounding único), l1-2, l1-4 (notas en paralelo) y el paso 4 de g-7 (sin chats antiguos). l1-3 y l1-5 se midieron y pasan a U3; l1-6 y l1-7 van detrás de U3. Ronda completa del golden frente a v7 (juez sin revisar): 80,5 → 81,5 %, **examen oculto 73,1 → 78,3 %**, **turno p50 4,62 → 3,34 s (−28 %)**, p95 9,00 → 7,33 s. Detalle en HISTORY 0.29.15. **U3 ya empezó:** Jev (u3-1) encendido en PRE con cascada por confianza.
> **Condición de cierre de L1 (acordado con Gadea el 22-sep):** justo **antes** de la ronda completa del golden
> que cierra L1, hacer el **paso 4 de g-7** (borrar `conversations.json` y su código; ver
> `docs/robustness/g7-retirar-conversations-plan.md`). Tope: **6-oct-2026** aunque L1 no haya terminado.
> Durante L1 los interruptores `RAG_EXCLUDE_SOURCES` / `RAG_FEWSHOT_ENABLED` siguen activos en PRE, así que
> todo L1 se mide ya sin los chats antiguos.
1. **RAG sin doble juez:** `_verify_grounding_with_retry` juzga UNA vez; si falla, **regenera** y juzga.
   - **✅ HECHA y ENCENDIDA en PRE (2026-09-23, A/B de Gadea con 2+2 rondas del core).** El segundo juez
     solo rescataba 1 de 24 rechazos (4 %). Con el juez único: −35 % de llamadas al juez de grounding,
     −10 % de coste por turno, peor turno del RAG de 9-10 llamadas a 7, calidad igual (85,0/87,1 % →
     87,5/87,2 %). Falta solo quitar del código la rama del reintento al cerrar L1.
   - **Implementado detrás de flag (2026-09-23, Gonzalo): `rag_single_grounding_judge`, por defecto
     OFF.** Línea preparada y **comentada** en `docker-compose.vps.yml`. Falta el A/B del core para
     decidir si se enciende. 6 tests (`tests/test_l1_single_grounding_judge.py`) que fijan el
     **número de llamadas al juez** en cada modo, no solo el veredicto.
   - **⚠️ Matiz que el enunciado no contemplaba: quitar el reintento NO es gratis en todos los
     caminos.** El bucle de `_answer_with_llm` ya regenera la respuesta, así que el reintento no es
     una segunda oportunidad real... **salvo que rescate**. Y cuando rescata, esa llamada al juez
     está **evitando una regeneración**, que es más cara: sin él, ese camino sale más LENTO. El
     ahorro solo es real si el rescate es raro.
   - **El dato que lo decide no existía:** el rescate devolvía `True` en silencio (en los logs solo
     quedaba rastro cuando FALLABA, por el `|retry:` del motivo). Añadido el log
     `[RAG][GROUNDING][RESCUE]`. **Antes de encender el flag, contar cuántos hay en PRE.**
2. **Checks deterministas primero:** `currency_amounts_grounded`/`urls_grounded`/`capacity_claims_grounded`
   antes; el juez LLM solo si pasan.
   - **YA SE CUMPLÍA (verificado 2026-09-23, Gonzalo): no hay nada que implementar.** En
     `_answer_with_llm` los siete guards deterministas van en una cadena `if/elif` y la llamada al
     juez está en el `else` final; `is_grounded` solo se invoca desde
     `_verify_grounding_with_retry`. Un rechazo determinista nunca gasta la petición.
   - Pero se cumplía **por la disposición del código**, sin nada que lo fijara: mover el juez arriba
     o añadir un guard detrás lo rompería sin que fallara un solo test. Clavado ahora en
     `tests/test_l1_deterministic_guards_first.py`.
   - **Hallazgo al escribirlo:** `rag_answer` tiene además una cadena de **atajos canónicos**
     (comida, overview de buceo, coste del refresher, precios, ubicación ambigua) que responden
     **sin una sola llamada al LLM** — un ahorro de L1 que no estaba anotado en ningún sitio. Queda
     fijado con test: si alguien los desmonta, el coste por turno sube sin que falle nada más.
     *(Salió porque el primer test se escribió con una pregunta de precio y pasaba en falso: el
     atajo respondía antes de llegar al juez. Lo cazó el test de control.)*
3. **Saltar `condense_query`** si no hay historial o el mensaje ya es autónomo.
   - **La mitad ya está hecha (verificado 2026-09-23, Gonzalo).** `_should_condense` corta si no hay
     historial (`if not query or not history: return False`) y trata como autónoma toda pregunta de
     **8+ palabras**. Lo que falta es la pregunta **corta pero autosuficiente** ("¿cuánto cuesta el
     minicurso?", 5 palabras, con historial), que hoy sigue gastando una llamada a `gpt-4o-mini`.
   - **Vía propuesta, sin listas de frases** (regla del owner): una pregunta es autosuficiente si
     **nombra su propio producto** del registro (`src/domain/activities.py`) — "¿cuánto cuesta el
     minicurso?" se nombra a sí misma; "¿y para dos?" no. Mecanismo común, no parche.
   - Cambia qué query llega a la recuperación ⇒ **flag + foto determinista sobre el corpus + A/B**.

> **🔭 Aviso sobre el margen real de L1 (2026-09-23).** Van **tres tareas seguidas** más hechas de lo
> que dice este plan: **l1-2 entera**, **l1-3 a medias**, y una cadena de **atajos canónicos** en
> `rag_answer` (comida, overview, coste del refresher, precios, ubicación ambigua) que responden
> **sin ninguna llamada al LLM** y que no estaba contabilizada en ningún sitio. **El ahorro
> disponible en L1 es menor que el que promete el enunciado**: conviene medir cuánto queda de verdad
> antes de comprometer una cifra de latencia con el owner.
4. **Sacar del turno** (`asyncio.create_task` tras enviar): `extract_notes`, `maybe_update_summary`, trazas.
5. **Paralelizar** llamadas independientes donde sea seguro (medido).
- Cada punto: foto calidad (0 regresiones) + delta de latencia en Langfuse. *(Álvaro RAG/turno · Gonzalo medición)*

> **l1-6 / l1-7 (26-sep): pendientes, van en el PASO 6 de la PARTE 8** (detrás de U3, como se acordó el
> 24-sep). Caso nuevo y sistemático para l1-7: a "¿me podéis devolver a Cartagena otro día?" el RAG contesta
> "we can definitely provide the transfer back" en casi todas las rondas desde el 22-sep, con el flag de
> u3-4 encendido o apagado, cuando la política `return_different_day` dice que NO está incluido y lo
> coordina un asesor. El juez SÍ lo marca, en su criterio específico `regreso-otro-dia-escalar` (no cumple
> en 28 de 29 rondas; la única que cumple, el bot lo dijo bien). *(Corregido 26-sep: se había escrito que el
> juez lo tapaba, mirando solo el criterio general `sin-invenciones`, que por "un fallo, un criterio" no
> debe contarlo dos veces.)*

### Fase L2 — Right-sizing de modelos + caching · *latencia + coste, con eval*
> **Estado (26-sep):** l2-4 (Jev) **hecha**: se evaluó y se usa en el router y en u3-4/u3-5. **l2-1 queda
> obsoleta**: el juez de grounding y `condense_query` ya van en `gpt-4o-mini` (mapa en `README.md`, "LLM
> models"). Quedan l2-2 (caché) y l2-3 ("escribiendo…"), en el PASO 7 de la PARTE 8.
> **Corrección (21-sep, medido en Langfuse; confirmado por la 0.29.9 del 23-sep):** en PRE **no se usa
> `gpt-4o`**. Los modelos reales son **`gpt-4o-mini`** (la mayoría de llamadas) y **`gpt-4.1-mini`**
> (la respuesta del RAG, `RAG_ANSWER_MODEL`, leído en el contenedor de PRE el 25-sep). El
> "bajar de tier" que asumía el plan **ya está hecho en gran parte**, así que L2 se re-encuadra: el lever
> real es **caché** (prompt + semántica) y, como mucho, revisar el modelo de la **respuesta RAG**.
- Evaluar por llamada **sobre los modelos reales**, siempre con A/B contra `eval_rag_answers`/
  `eval_retrieval`. Sin dar por hecho el tier: mirar primero la foto de Langfuse de esa llamada.
- **Prompt caching** de OpenAI (system-prompts/tool-schemas) + **caché semántica** de FAQ repetidas.
- **Streaming / latencia percibida:** investigar envío por partes / "escribiendo" en Chatwoot; si no, trocear.
- **`l2-4` · Evaluar Jev (TypeSafe, "System One model", 15-sep-2026) como clasificador.** Devuelve
  decisiones **tipadas** (Boolean con probabilidad calibrada, Choice ≤255 opciones, Score) **sin generar
  texto**: ~0,4 s y **coste de salida 0**. Encaja en **tres carriles**: (a) `detect_routing_signals` — 9
  señales booleanas, hoy a **p50 ~1,1 s en CADA turno**; (b) clasificación de actividad (Choice); (c)
  `is_grounded` en **cascada** (Jev decide cuando su probabilidad es alta; el juez LLM solo en la banda
  dudosa). **NO sirve** para: respuesta RAG, acuses, extracción de slots (`fill_gaps` saca valores, no
  elige de una lista → U3 sigue necesitando tool-calling) ni el **juez del golden-set** (necesita dar
  **evidencia** por criterio y Jev no explica). **Riesgo principal: el español** — no hay evaluación
  multilingüe publicada y el 65 % de nuestro tráfico es ES. Protocolo: después de G1+G2, detrás de flag,
  A/B **por caso** con `battery_router_signals.py 8 base,jev s,a,n`. **Pendiente de investigar.**
  *(Gonzalo)*

### Fase U3 — Unificación del entendimiento · **CONSERVADOR, detrás de flag** · *el cambio grande*
> **Estado real (26-sep) — el diseño de abajo es el ORIGINAL y cambió al medir.** La "UNA llamada
> estructurada" se descartó: la extracción ya era casi siempre una sola llamada (`extract_and_verify`), y lo
> que ralentizaba era la cadena extracción → acuse (`docs/robustness/u3-1-paso3-diseno.md`). U3 pasó a ser
> "decisiones de opciones fijas con Jev + contesta y sigue":
>
> | Tarea | Qué | Estado |
> |---|---|---|
> | u3-1 | Jev en las señales del router (paso 1) y acuse en paralelo (paso 3); el paso 2 ("¿se entiende sola?") se midió y se descartó | ✅ encendido |
> | u3-4 | Contesta y sigue (+ puerta de Jev, relleno con puerta) | ✅ promocionado 26-sep (ronda B3) |
> | u3-5 | Extracción sin inventar (preguntas de Jev de certificado, grupo, nacionalidad) | 🟡 en curso: quedan 2 errores conocidos |
> | u3-6 | `detect_special_signals` con Jev y el "recordar" mal disparado | ⏳ |
> | u3-7 | `resolve_slot_answer` con Jev (sí/no y listas) | ⏳ |
> | u3-3 | `intent_detector` como vía rápida determinista + respaldo (Jev/LLM) | ⏳ |
> | u3-2 | **Redefinida**: el "eval-set + baterías" no pasa por la fase donde actúa u3-4 (el eval-set `--core` no ejecuta `_routing_phase`), así que el cierre de U3 es la **ronda completa del golden con el examen oculto** del protocolo | ⏳ cierre |
>
> Orden y criterios: PASOS 3-5 de la PARTE 8.
> **🟦 Regla de Jev (Gadea, 24-sep-2026):** toda DECISIÓN de opciones fijas del bot (sí/no o elegir de una lista) se prueba primero con **Jev** (TypeSafe vía OpenRouter), siempre con cascada por confianza (si duda, el LLM de hoy) y con el protocolo de medición. Casos: router (u3-1, encendido), u3-4 (¿trae una pregunta?), u3-6 (`detect_special_signals`), u3-7 (`resolve_slot_answer` en sí/no y listas), u3-3 (respaldo del `intent_detector`) y el juez de grounding (l1-6/l1-7). **No** para extraer valores (fechas, cifras, nombres) ni para escribir texto. Adaptador de referencia: `src/agents/jev_router.py`.
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
- **r6-3 (nueva, 26-sep) — comprobar cada deploy.** Un CI rojo se salta el deploy SIN avisar: del 24-sep 23:04
  al 25-sep 21:30 PRE sirvió código viejo y nadie lo vio. Script que, tras un push a `pre_*`, confirme en la
  API pública de GitHub que el run pasó y por SSH el SHA y los flags que sirve PRE (PASO 1 de la PARTE 8).
- **r6-4 (nueva, 26-sep) — dependencias acotadas.** CI y Docker instalan con `pip install -e .` y casi todas las
  dependencias van con `>=` sin techo: así entró SQLAlchemy 2.1 y rompió CI. Poner techo de versión mayor (o
  instalar desde `requirements-lock.txt`) para que un major nuevo no entre sin probarlo (PASO 1).

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
| Hallazgo 25-sep | CI rojo se salta el deploy sin avisar | R6 (r6-3), paso 1 |
| Hallazgo 25-sep | Dependencias sin techo (SQLAlchemy 2.1 rompió CI) | R6 (r6-4), paso 1 |
| Hallazgo 26-sep | El RAG contradice `return_different_day` en casi todas las rondas | L1 (l1-7), paso 6 |
| Hallazgo 26-sep (corregido) | ~~El juez tapa contradicciones de política~~: NO, las marca en el criterio específico | — |
| Hallazgo 26-sep | El filtro de contradicciones de Jev podría tragarse una corrección real | U3 (u3-5), paso 1c |
| Owner 26-sep | Ejecución secuencial; lo pendiente antes de avanzar | PARTE 8 |

---

## PARTE 6 — Qué NO rehacer (ya está bien / hecho)
State único (`ConversationState`, Fase 4), grounding unificado (`grounding_check`+`rag_answer`, Fase 4.3),
prompts por nodo (`src/prompts/`, Fase 3.2), subgrafo booking en 5 fases (Fase 3.3), fuentes deterministas
de verdad (`money.py`/`activities.py`/`catalog.py`/`eligibility.py`), Langfuse con máscara PII.

---

## PARTE 7 — Cómo empezar (para Gadea) · *HISTÓRICO (16-sep): el vigente es la PARTE 8*
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

---

## PARTE 8 — Plan de ejecución SECUENCIAL (desde el 26-sep-2026) · *el vigente*

**Regla (owner, 26-sep):** un paso detrás de otro. Lo que está pendiente se cierra antes de avanzar y no hay
trabajo en paralelo. Cada paso se trabaja en la rama de quien tiene el turno (hoy `feature/pre_alvaro`;
integrad antes lo que otro haya subido: todas las `pre_*` despliegan el MISMO PRE), detrás de flag si cambia
conducta, con el protocolo por escalones (`docs/robustness/protocolo-medicion.md`), y se cierra con HISTORY,
handoff y la cola de Plan Coral. **Un paso no está hecho hasta que cumple su criterio.**

**Punto de partida (26-sep):** M0 hecha salvo m0-4 (necesita tráfico real); G1 y G2 hechas; L1 cerrada; U3 a
medias (u3-1 ✅, u3-4 ✅ promocionada, u3-5 🟡); PRE con u3-4 encendido. Suite 2677 passed.

| Paso | Qué | Tareas | Hecho cuando |
|---|---|---|---|
| **0** | Aterrizar: plan, handoff, HISTORY y página al día con lo nuevo | — | ✅ 26-sep (esta PARTE) · falta aplicar la cola de Plan Coral y re-exportar la copia `plan-coral.json` (del 23-sep) |
| **1** | Cabos sueltos técnicos (riesgos vivos, antes de tocar conducta) | r6-4 · r6-3 · control de correcciones · re-triaje s4-6…s4-22 | ✅ **cerrado 26-sep** (1a-1d abajo) |
| **2** | Afinar el instrumento: el juez | g-8 | criterios de los casos reales revisados y juez recalibrado con ellos: menos falsos suspensos, medido contra los veredictos humanos |
| **3** | Línea base nueva con u3-4 encendido | ronda A core, juzgada con el juez del paso 2 | ronda A de referencia para todos los A/B de U3 |
| **4** | Terminar U3, en orden | 4a u3-5 (+ s4-8, s4-9, s4-11, s4-22 personas) · 4b u3-6 (+ s4-6, s4-18, s4-19, s4-20) · 4c u3-7 · 4d u3-3 | cada una: escalón 0 → ronda B frente a la A del paso 3 → 0 regresiones propias, leídas por caso |
| **5** | Cierre de U3 | u3-2 (redefinida) | ronda COMPLETA del golden (116 diálogos + examen oculto): examen oculto ≥ 78,3 % (cierre de L1) y sin regresiones propias |
| **6** | Calidad del RAG | l1-6, l1-7 (+ s4-7 texto, s4-11 horas, s4-12, s4-17, s4-22 contenido) | los casos conocidos sin invención (el primero, "regreso otro día"); "no lo tengo" solo cuando el dato no está; `eval_rag_answers` y ronda core sin regresiones |
| **7** | L2 que queda | l2-2, l2-3 (l2-1 cerrada el 26-sep: obsoleta) | caché y "escribiendo…" medidos: latencia percibida ↓ y calidad igual |
| **8** | S4: un solo cerebro y código ordenado | s4-1, s4-2, s4-3, s4-4 (si u3-3 no lo cubre), retirar flags promocionados, s4-14, s4-15, s4-16, s4-21 | sin cascada legacy; módulos partidos por nodo; flags promocionados convertidos en código; suite verde |
| **9** | R6: robustez de producción | r6-1 (fallback y backoff ante 429), r6-2 (guardrails), g-5 (carga) | el bot nunca deja sin respuesta; inyección medida; p95 con N clientes a la vez |
| **10** | Q5: calidad continua y entrega | q5-1, g-3, g-4, g-4b, g-6, m0-4, q5-2 | gate en CI; simulador; bucle producción → golden; testers reales; SOAK; entrega |

**Detalle de cada paso:**

- **1a · r6-4 dependencias acotadas. ✅ HECHO 26-sep (HISTORY 0.29.35).** Techo de versión mayor en `pyproject.toml` para las que van sin él
  (fastapi, pydantic, pydantic-settings, asyncpg, alembic, pgvector, redis, httpx…), comprobando cada techo
  contra `requirements-lock.txt`. Hecho cuando un entorno limpio (como CI) instala y pasa lint, migraciones
  y tests, igual que se verificó el arreglo de SQLAlchemy (HISTORY 0.29.27).
- **1b · r6-3 comprobar cada deploy. ✅ HECHO 26-sep (HISTORY 0.29.36).** `scripts/check_deploy.py`: sondea el run de GitHub (API pública,
  `conclusion`) y, si pasa, el SHA, la rama y los flags que sirve PRE por SSH; sale con error si no cuadra.
  Se añade al ritual de cierre (`/close-work`) y al handoff.
- **1c · control de correcciones en el banco. ✅ HECHO 26-sep (HISTORY 0.29.37): 20/20 en los campos filtrados.** El filtro de contradicciones de Jev actúa en TODOS los turnos
  (u3-5) y va antes que la señal "ah no / perdón": una corrección real con p < 0,7 se ignoraría. Medido el
  26-sep: 21/21 correcciones explícitas pasan, pero "mejor snorkel" va justo (0,41 con la regla de actividad).
  Se añade como bloque fijo de `scripts/sonda_afirma_vs_pregunta.py` para que cualquier cambio de redacción
  lo vigile.
- **1d · re-triaje de s4-6…s4-22. ✅ HECHO 26-sep (HISTORY 0.29.38; detalle y evidencia caso a caso en
  `docs/robustness/s4-retriaje-2026-09-26.md`).** Con la ronda B3 (core) y el replay v9 (el resto, u3-4
  encendido): **resueltas s4-10 y s4-13** (el bucle que ignoraba preguntas lo arregló u3-4), s4-7 resuelta
  en el flujo (queda el texto del RAG), 4 parciales y 10 siguen. Reparto por mecanismo: 4a s4-8, s4-9,
  s4-11, s4-22 (personas) · 4b s4-6, s4-18, s4-19, s4-20 · 6 s4-7 (texto), s4-11 (horas), s4-12, s4-17,
  s4-22 (contenido) · 8 s4-14, s4-15, s4-16, s4-21. s4-19 y s4-20 cambian de paso (del 6 y el 8 al 4b):
  la causa es la intención mal detectada, no el texto.
- **2 · g-8. 🟡 EN CURSO (26-sep, HISTORY 0.29.39): 2a y 2b hechos; el 2c baja los falsos suspensos (75,0 → 83,2 %) pero sube lo que se escapa (7 → 16): hay que leer esas 16 y ajustar antes de cerrar.** En la ronda v7 el juez acertó el 72,7 % de sus "no cumple" (91,5 % en la calibración
  sintética): 51 falsos suspensos de 187, por criterios demasiado estrictos, contar dos veces un fallo o
  datos que no ve en su referencia. Va ANTES de las rondas que quedan porque todas se juzgan con él.
  *(Corregido 26-sep: NO deja pasar el "regreso otro día"; lo marca en su criterio específico.)*
- **4a · u3-5:** "cursos de buceo… primera vez" → minicurso supuesto (regla del owner: recomendar, no
  asumir) y "Vamos en família a Cartagena" → no colombiano (portugués); más s4-8/9/10/11 si el re-triaje los
  deja aquí. Y del 1c: la regla de actividad da 0,36-0,46 a "mejor snorkel", así que en un turno con
  pregunta ("mejor snorkel, ¿cuánto cuesta?") la puerta de u3-4 perdería el cambio de opinión. Del 1d: el
  "¿lo cambio? X → X" (se propone un cambio al mismo valor, acompanante-goteo), los niños a los que se da
  buceo certificado sin mirar la edad (s4-9), "solo" = 1 persona (s4-11) y el "¿para cuántas personas?" en
  bucle a quien habla en singular (s4-22). **4b · u3-6:** `detect_special_signals` con Jev; el "recordar"
  mal disparado ("how do we book" → resumen, sin contestar ni extraer; s4-18); y del 1d, las intenciones mal
  detectadas: cambio de fecha (s4-6), buceo adaptado con "mi madre es mayor" (s4-19), post-venta (s4-20:
  agencia, logs de PADI, "¿todo ok con mis reservas?") y el aviso médico que salta con "completed the
  medical form". **4c · u3-7:** `resolve_slot_answer` con Jev en sí/no y listas.
  **4d · u3-3:** el regex de `intent_detector` como vía rápida con respaldo, sin parches.
- **5 · cierre de U3** con la ronda completa (~2 $). Si sale bien, U3 queda cerrada y esa ronda es la línea
  base de los pasos 6-10.
- **Checkpoint de fecha:** Langfuse vuelve a tener cuota el **16-oct**. Decidir entonces si se reactiva o se
  sigue con `[TURN_METRICS]`.

## ANEXO — Visión de producto (FUTURO, fuera del camino técnico actual)
> Decisión del owner (21-sep). **No es trabajo de este plan**: son las piezas que convierten a Coral en
> producto vendible una vez esté pulido. Se abordan **después** de Q5 (entrega). Ninguna toca el núcleo.

1. **Multicanal.** Hoy entra WhatsApp por Chatwoot. Añadir **Instagram** y **correo** es conectar sus
   webhooks/API en Chatwoot: el bot itera igual porque el canal ya está abstraído (`src/channels/`).
   Coste bajo, valor comercial alto.
2. **White-label.** Que el cliente **no vea Chatwoot**: (a) cambiar logos/colores/dominio desde el propio
   panel, o (b) un frontend propio que hable con Chatwoot **por API**.
3. **All-in tipo CRM + web del cliente.** El paso grande: además del bot, llevarle la web con reservas y
   clientes en un panel. Es donde está el margen; requiere decidir alcance y precio antes de tocar nada.

**Criterio:** no empezar ninguna hasta cerrar Q5. La 1 y la 2 son semanas; la 3 es un producto aparte.
