# Plan: extracción semántica por LLM (Opción 2 de robustness-strategy-options.md)

Estado global: **no empezada**. Ver `progress-log.md` para el estado exacto y
sesión-a-sesión.

Decidido por: owner + Álvaro + Gonzalo, 2026-07-21, tras leer
`docs/archive/robustness-strategy-options.md`. Objetivo textual del owner: "ser competitivos y
sólidos, el cliente no puede encontrar tantos bugs".

Este documento es la guía persistente del proyecto. Está pensado para sobrevivir a
múltiples sesiones/agentes distintos trabajando en momentos distintos — cada uno debe
poder llegar aquí sin contexto previo, entender exactamente qué hacer, y dejarlo listo
para el siguiente. Lee `README.md` primero si no lo has hecho.

---

## 1. Por qué esto y no otra cosa

Contexto completo en `docs/archive/robustness-strategy-options.md`. Resumen de la causa raíz:
`intent_detector.py`/`supervisor.py`/`decision_tree.py` extraen información del mensaje
(¿está certificado? ¿cuántos son? ¿desde dónde? ¿cambió de plan?) mediante **regex
especializadas, una familia por caso**. Cada bug real encontrado en vivo (y llevamos
docenas en el historial de versiones — ver `docs/HISTORY.md`) es la misma forma:
*alguien dijo algo de una manera que el regex no anticipó*. Los 2 bugs de la sesión de
hoy (`v0.20.31`) son el ejemplo perfecto: "not certfied" (typo) y "vucea" (typo b/v de
"bucea") — cada uno arreglado con una línea de regex nueva, cada uno encontrado
manualmente, cada uno con el mismo patrón de fondo: el enfoque regex-por-caso tiene un
techo estructural.

Ojo con la ambición: esto **no** es "tirar todo el regex y meter un LLM que lo haga
todo". Álvaro ya lo planteó así en `docs/project-history/estado-pendientes.md` (punto
#10): la extracción LLM debe ser **una red de seguridad que rellena huecos que el
regex deja vacíos**, no un reemplazo de golpe. Razones:

- El regex actual funciona MUY bien para el caso común (miles de tests lo confirman).
- El LLM orquestador que ya existe (`src/agents/orchestrator.py`) es conocidamente
  **no-determinista** — mismo mensaje, clasificación distinta entre ejecuciones. Si
  reemplazamos el regex determinista por LLM sin red de seguridad, cambiamos "bugs
  reproducibles y fáciles de testear" por "bugs intermitentes", que son peores para un
  negocio real (impredecibles, difíciles de reproducir en test, difíciles de explicar
  al owner).
- Un reemplazo de golpe arriesga una regresión masiva en un flujo que ya está bien
  probado (suite de ~1700 tests).

## 2. Principios de diseño (no negociables)

1. **Strangler fig, no big-bang.** Migrar dominio por dominio (certificación, grupo,
   ubicación, cambios de plan…), nunca "reescribir intent_detector.py entero".
2. **Regex sigue siendo el camino rápido y primario.** El LLM solo entra cuando el
   regex deja un campo relevante sin resolver (`None`) — o, durante la fase de
   evaluación, en modo *shadow* (corre en paralelo, no decide nada, solo se compara).
3. **Nunca sin red de seguridad.** Cada integración de LLM tiene un fallback
   determinista si la llamada falla, tarda demasiado, o devuelve algo fuera de schema.
4. **Salida estructurada, temperatura 0.** Nunca texto libre parseado a mano — usar
   structured output / function calling con un JSON schema explícito (mismo patrón que
   ya usa `orchestrator.py` para sus tools).
5. **Eval set explícito antes de cualquier cutover.** Ningún campo pasa a usar LLM como
   fuente de verdad sin que su exactitud esté medida contra un dataset etiquetado (ver
   §5) — mismo rigor que se usó para calibrar `RAG_MIN_SCORE` en
   `docs/archive/rag-threshold-calibration.md`.
6. **TDD + verificación en vivo sigue siendo obligatorio**, sin excepciones, para cada
   cambio de comportamiento — es la disciplina que ya usa todo el repo (ver
   `docs/project-history/session-handoff.md`).
7. **Kill switch por fase.** Cada dominio migrado debe poder revertirse a "solo regex"
   con un flag, sin deploy de emergencia con cambio de código.
8. **Este documento se mantiene vivo.** Cualquier sesión que trabaje aquí actualiza
   `progress-log.md` antes de terminar — ver README.md.

## 3. Arquitectura objetivo

### 3.1 Dónde vive la extracción hoy

`src/agents/intent_detector.py` → clase `IntentDetector`, método `detect(message,
state) -> DetectedIntent`. `DetectedIntent` es un dataclass con campos sueltos:
`activity`, `is_certified`, `group_size`, `group_allocation`, `ages`, `location`,
`island`, `hotel`, `is_colombian`, `cert_dives`, `cert_days`, `language`,
`detected_fields` (lista de qué campos se resolvieron), `confidence`. Es la única
entrada — `supervisor.py` la llama y actúa sobre el resultado
(`_route_detected_intent`, `_should_ask_certification`, `_should_enter_mixed_flow`,
etc.).

Esto es una ventaja arquitectónica clave para la migración: **ya existe un contrato de
salida único y bien tipado** (`DetectedIntent`). No hace falta inventar un schema nuevo
desde cero — el LLM debe rellenar el MISMO dataclass, así que todo lo que consume
`DetectedIntent` aguas abajo no se entera del cambio.

### 3.2 Diseño de la capa LLM (gap-filler, no reemplazo)

```
mensaje del cliente
        │
        ▼
IntentDetector.detect()  (regex, determinista, igual que hoy)
        │
        ▼
DetectedIntent parcial (algunos campos en None)
        │
        ├── ¿hay campos relevantes en None Y el mensaje tiene señal
        │   suficiente (heurística barata, ver 3.3)?
        │                       │
        │                  sí   │   no
        │                       │
        ▼                       ▼
LLMExtractor.fill_gaps()   devolver tal cual
(solo rellena los None,
 NUNCA sobreescribe un
 campo que el regex ya
 resolvió)
        │
        ▼
DetectedIntent completo (regex + LLM donde hiciera falta)
```

Puntos clave:

- **El LLM nunca pisa un campo que el regex ya resolvió.** Si en el futuro un dominio
  demuestra (vía eval set, con datos) que el LLM es más fiable que el regex incluso
  cuando el regex "cree" haber resuelto algo, eso es una decisión de cutover explícita
  y documentada por campo (§4, Fase 2+), no un comportamiento por defecto.
- **`fill_gaps()` es una función pura de (mensaje, historial reciente, campos ya
  resueltos) → parche de campos nuevos**, igual de testeable que cualquier otra pieza
  del pipeline (se puede mockear la llamada LLM en tests, igual que ya se hace con
  `rag_answer`/`classify_menu_intent`/`orchestrator.orchestrate` en `test_conversations.py`).
- Reutiliza la infraestructura de tool-calling que ya existe en `orchestrator.py` (schema
  JSON, cliente OpenAI, patrón de parseo de respuesta) — no hace falta un cliente nuevo.

### 3.3 Cuándo se invoca (control de coste/latencia)

Llamar al LLM en cada mensaje sería caro y añadiría latencia siempre, incluso cuando el
regex ya lo resolvió todo bien (el caso común, la mayoría de los mensajes). Regla de
activación:

- **Fase de evaluación (shadow mode, ver §4 Fase 0)**: se llama SIEMPRE, en paralelo,
  pero el resultado nunca decide nada — solo se loguea para medir acuerdo/desacuerdo
  contra el regex y construir el eval set inicial con casos reales.
- **Fase de producción (tras cutover de un dominio)**: se llama solo si, tras el regex,
  queda al menos un campo relevante para el paso actual del árbol sin resolver Y el
  mensaje tiene señal suficiente para no ser una pregunta genérica ya destinada a RAG
  (reusar `_message_looks_like_question`/`_looks_like_info_question` ya existentes en
  `supervisor.py` como guardas — si ya se sabe que es una pregunta de info, no tiene
  sentido gastar una llamada extra en extracción).

### 3.4 Fallback y manejo de errores

- Timeout o error de la llamada LLM → devolver `DetectedIntent` tal cual (solo regex),
  loguear el fallo. El bot sigue funcionando exactamente como hoy, nunca peor.
- Respuesta fuera de schema / campo con tipo inesperado → descartar ese campo
  específico (no todo el resultado), loguear.
- Nunca bloquear la respuesta al cliente esperando reintentos de la extracción — un
  fallo aquí degrada a "como hoy", no debe convertirse en un nuevo punto de fallo.

## 4. Fases

Checklist de estado — actualizar aquí Y en el bloque correspondiente de
`progress-log.md` cuando cambie:

- [✅] **Fase 0 — Fundaciones** (sin cambio de comportamiento) — completa, 100.0% de acuerdo con LLM real (tras corregir un caso mal etiquetado), ver `progress-log.md`
- [✅] **Fase 1 — Dominio certificación** (primer vertical slice) — cutover implementado detrás de `settings.llm_extraction_cutover_certification` (default `False`), verificado en vivo con LLM real, ver `progress-log.md`
- [✅] **Fase 2 — Dominio grupo/cantidad/edades** (`group_size`/`group_allocation`/`ages`) — cutover implementado detrás de `settings.llm_extraction_cutover_group` (default `False`), eval-set ampliado a 58 casos con **99.2% de acuerdo con LLM real** (100% en el dominio de grupo excluyendo 1 bug de regex documentado), verificado en vivo, ver `progress-log.md`
- [✅] **Fase 3 — Dominio ubicación** (`location`/`island`/`hotel`) — cutover implementado detrás de `settings.llm_extraction_cutover_location` (default `False`), eval-set ampliado a 64 casos con **99.2% de acuerdo** y **`location` 13/13 = 100%**, verificado en vivo. Los interceptores de cambio de plan/acompañante quedan fuera (no son campos de `DetectedIntent`, ver nota en la sección). Ver `progress-log.md`
- [✅] **Fase 4 — Integración con acciones de carrito (orchestrator)** — evaluado con datos: **decisión de MANTENER separados** extractor y orquestador (fusionar acoplaría concerns, sometería la extracción validada al no-determinismo "auto" del orquestador, y la 2ª llamada solo ocurre en turnos con hueco). Mejora concreta entregada: el extractor pasa a un modelo más barato/rápido (`settings.extraction_model=gpt-4o-mini`), medido a 98.4% en el eval-set con modo de fallo seguro (abstención, no misfill). Ver `progress-log.md`
- [ ] **Fase 5 — Limpieza y consolidación** (bloqueada por Fase 6: sin datos reales no se sabe qué regex está muerto)
- [~] **Fase 6 — Bucle de datos reales** (NUEVA, prioridad alta) — **tooling construido**: `scripts/harvest_cutover_logs.py` parsea los logs `[EXTRACT][CUTOVER]`/`[EXTRACT][SHADOW]` de PRE → candidatos deduplicados para el eval-set (modo default) + contador por campo/dominio (`--summary`, H8), con 5 tests. **Pendiente**: correrlo contra los logs reales de `dp-pre-bot` y curar los candidatos (validar `expected` contra el pipeline real antes de fijarlo). Ver `review-2026-07-21.md` H1/H8.
- [✅] **Fase 7 — Bugs de regex donde el regex resuelve MAL** (NUEVA) — 3 bugs reales hallados por las baterías (`me plus N friends`→N (falta el hablante), `hace/in X años`→edad fantasma, `already have my X card`→curso en vez de certificado). **Decisión con datos**: eran patrones concretos y deterministas → se arregló el REGEX (no un override LLM no-determinista, que habría cambiado bugs reproducibles por intermitentes — contra el principio del plan). +11 tests en `test_intent_robustness.py`; el `me plus 3 friends` del eval-set pasa a acierto (group_size 100%, 0 disagree); corregido un `expected` mal etiquetado del eval-set (`lastdive-en` tenía un age fantasma del mismo bug). Ver `progress-log.md`.
- [✅] **Fase 8 — Dominio nacionalidad/logística** (`is_colombian`/`duration`/`last_dive_over_2_years`) — cutover detrás de `settings.llm_extraction_cutover_logistics` (default `False`), eval-set ampliado a 71 casos, **dominio al 100%** (is_colombian 4/4, duration 5/5, last_dive 5/5) con LLM real, verificado en vivo. **Parte 2 (cablear entry-points, H4) DEFERIDA con razón**: `_apply_group_recomposition`/`_maybe_answer_age_eligibility` son short-circuits pre-dispatch; cablear el cutover ahí duplicaría la llamada LLM en fall-through. El fix correcto (un cutover único temprano en `_route_message_inner`) es un refactor de dispatch, documentado en código y como trabajo futuro. Ver `review-2026-07-21.md` H4/H5.

> **Revisión 2026-07-21** (`review-2026-07-21.md`): tras completar Fases 0-4, revisión
> exhaustiva con 8 hallazgos priorizados. Los más importantes: no hay bucle de datos reales
> (H1 → Fase 6) y la suite es lenta/flaky porque RAG no está mockeado (H2 → tarea transversal
> T1). Las Fases 6-8 salen de esa revisión.

### Fase 0 — Fundaciones

Objetivo: tener la infraestructura de shadow-mode + eval-set funcionando, **sin tocar
el comportamiento del bot en producción**. Es la fase de "medir antes de cortar".

Pasos:

1. ✅ **Definir el schema de extracción** — se reutiliza `DetectedIntent` tal cual
   (`src/agents/intent_detector.py`) como contrato de salida; `EXTRACTABLE_FIELDS` en
   `src/agents/llm_extractor.py` es el subconjunto de campos que el LLM puede rellenar
   (excluye `language`, `service_id`, `confidence`, `detected_fields` — derivados/meta,
   no extraídos directamente del mensaje).
2. ✅ **Eval-set inicial construido**: `docs/robustness/eval-set.json`, 50 casos —
   42 semillas derivadas de `tests/test_intent_detector.py` (regex como ground truth,
   incluidos los 2 bugs reales de v0.20.31 marcados con su fuente) + 8 adversariales
   nuevos (negación con contracción EN, doble negación ES, edad+actividad de un
   tercero, certificación implícita por nombre de curso PADI, mensaje elíptico sin
   verbo de bucear, code-switching ES/EN, typo de letra duplicada, abreviatura de chat
   "ppl"). Formato exacto en §5.
3. ✅ **`LLMExtractor.fill_gaps()` construido** en `src/agents/llm_extractor.py` —
   función aislada, mockeable (mismo patrón de fake-client que
   `tests/test_orchestrator.py`), con su propio test file
   (`tests/test_llm_extractor.py`, 14 tests) validando: relleno correcto de huecos,
   que NUNCA sobreescribe un campo que el regex ya resolvió (ni siquiera si el LLM
   "opina" distinto), manejo de `is_certified=False`/`last_dive_over_2_years=False`/
   `is_colombian=False` como valores resueltos (no "missing" solo por ser falsy — bug
   real cazado por el propio test antes de escribir la implementación correcta), y
   fallback a `{}` en cualquier error/timeout/JSON malformado. Aún NO integrada en
   `supervisor.py`/`intent_detector.py` como fuente de verdad — solo shadow (paso 4).
4. ✅ **Shadow-mode harness construido**: `settings.llm_extraction_shadow_mode`
   (`src/config.py`, default `False`) + `_maybe_log_llm_extraction_shadow()` en
   `supervisor.py`, enganchado justo después de `intent_detector.detect()` dentro de
   `_dispatch_conversation_agent` (el entry-point principal de comprensión de texto
   libre). Con el flag apagado (default en todos los entornos), NUNCA llama al LLM —
   verificado con test dedicado (`tests/test_llm_extraction_shadow_mode.py`, 4 tests)
   que usa un mock que lanza `AssertionError` si se le llama, para probar la propiedad
   de seguridad de forma dura, no solo observacional. Loguea con el tag grepable
   `[EXTRACT][SHADOW] msg=... gaps_before=[...] llm_patch={...}`. Cualquier excepción
   en la sonda se traga (no puede romper un turno real).
5. ✅ **Corrido con LLM real** (`ENV_FILE=.env.dev python -m scripts.run_extraction_eval`,
   2026-07-21): primera pasada dio 99/100 (99.0%), con 1 desacuerdo en un caso
   adversarial. Al investigarlo (ver `progress-log.md`) resultó ser un **error de
   autoría del eval-set** (un "expected" escrito a mano sin correr antes el detector
   real), no un fallo del LLM ni una ambigüedad real de schema. Corregido el caso →
   **100/100 (100.0%) de acuerdo, 0 desacuerdos, 0 huecos** en la segunda pasada.
   Resultado muy por encima del baseline solo-regex (94%) y del umbral propuesto para
   el cutover de Fase 1 (≥98%). Con esto, el criterio de salida de Fase 0 queda
   cumplido para el dominio de certificación — la Fase 1 puede empezar.

Criterio de salida de la Fase 0: eval-set con al menos ~40-60 casos reales (✅ 50,
cumplido), harness de shadow-mode desplegado y logueando (✅ construido y testeado),
primer análisis de acuerdo/desacuerdo por campo con el LLM real documentado (✅ 100.0%,
ver arriba). **Fase 0 completa.**

### Fase 1 — Dominio certificación (primer vertical slice)

Por qué este dominio primero: es el más pequeño (un campo booleano, `is_certified`,
más el campo derivado `activity`), y es el que más bugs reales ha producido esta
sesión y en el historial (v0.20.9, v0.20.12, v0.20.17-21, v0.20.30-31 tocan todos este
área en algún punto). Buen banco de pruebas de bajo riesgo para validar el patrón
completo (shadow → eval → cutover → kill switch) antes de escalarlo a dominios más
grandes.

Pasos:

1. ✅ **Umbral de corte cumplido**: 100.0% de acuerdo en el eval-set con LLM real
   (Fase 0, `progress-log.md`) — por encima del ≥98% propuesto.
2. ✅ **Cutover implementado**: `_maybe_apply_llm_extraction_cutover()` en
   `supervisor.py`, gated por `settings.llm_extraction_cutover_certification`
   (default `False`). Rellena SOLO `is_certified`/`activity` cuando el regex los deja
   sin resolver — cualquier otro campo del patch LLM se descarta (queda para su
   propia Fase N). Corre ANTES de `_apply_detected_intent(intent, state)` para que lo
   rellenado se propague a `state` por el camino normal.
3. ✅ **TDD**: `tests/test_llm_extraction_cutover.py` (7 tests) — flag apagado no
   llama al LLM (verificado con `AssertionError` forzado, no solo observacional);
   flag encendido rellena SOLO los 2 campos del dominio aunque el patch LLM traiga
   más; nunca sobreescribe un campo ya resuelto por regex; no llama al LLM si lo
   único que falta es de OTRO dominio; fallo del LLM degrada silenciosamente a
   regex-only; el resultado se propaga correctamente a `state` vía
   `_apply_detected_intent`.
4. ✅ Suite completa (**1738 passed**, mismos 8 fallos preexistentes) + `ruff`/
   `compileall` en verde.
5. ✅ **Verificado en vivo con LLM real** (localmente, `ENV_FILE=.env.dev`, flag
   activado manualmente): mensaje `"never been underwater before, wanna give it a
   try, solo"` — el regex NO resuelve nada (`activity=None`, `is_certified=None`).
   **Con el cutover apagado** (comportamiento de hoy): cae a una respuesta genérica
   de RAG, se queda en `main_menu`, sin `detected_activity`. **Con el cutover
   encendido**: entra directo al flujo guiado de minicurso
   (`step=mixed_location`, `detected_activity=minicourse`,
   `detected_is_certified=False`) — mejora real y medible, no solo teórica.
6. ⬜ Pendiente (decisión de despliegue, no de código): activar
   `llm_extraction_cutover_certification=True` en un entorno real (dev/PRE) cuando
   el equipo decida — el código ya está listo y probado; el flag sigue en `False`
   por defecto en todos los entornos hasta esa decisión explícita.

**Fase 1 completa** (código + tests + verificación en vivo). Falta solo la decisión
del equipo de cuándo encender el flag en un entorno real — eso es una decisión de
producto/timing, no un bloqueador técnico.

### Fase 2 — Dominio grupo/cantidad/edades

`group_size`, `group_allocation`, `ages`. Más complejo que certificación (hay lógica de
split cert/no-cert, edades mínimas, etc. — ver `_split_out_uncertifiable_kids`). Mismo
patrón de pasos que la Fase 1, adaptado.

Pasos:

1. ✅ **Eval-set ampliado**: `docs/robustness/eval-set.json` pasa de 50 a 58 casos — 8
   adversariales nuevos del dominio de grupo, cada uno **validado contra el
   `IntentDetector` real antes de fijar su `expected`** (la lección de proceso de la
   Fase 0): "un par"/"the two of us" (group_size implícito), reparto mixto por rol
   ("four certified divers and two snorkelers", "mi pareja y yo buceamos y mi suegra
   snorkel"), conteo desde enumeración de personas, edad escrita en palabra ("ocho"),
   y un **bug de regex real hallado en esta fase** (`me plus 3 friends` → el regex
   resuelve `group_size=3`, debería ser 4).
2. ✅ **Cutover implementado**: `settings.llm_extraction_cutover_group` (`src/config.py`,
   default `False`). El cutover de `supervisor.py` se **generalizó a multi-dominio**:
   `_active_cutover_fields()` une los campos de los dominios cuyo flag está encendido, y
   `_maybe_apply_llm_extraction_cutover()` hace **una sola llamada LLM** que cubre todos
   los dominios activos (control de coste/latencia, §3.3), aplicando solo los campos de
   un dominio encendido. Retrocompatible con la Fase 1 (con el flag de grupo apagado, se
   comporta exactamente igual que antes — los tests de certificación pasan sin cambios).
   Campos del dominio: `_GROUP_CUTOVER_FIELDS = {"group_size", "group_allocation", "ages"}`.
3. ✅ **TDD**: `tests/test_llm_extraction_cutover.py` (+7 tests, 14 en total) — flag de
   grupo apagado no llama al LLM; encendido rellena SOLO los 3 campos de grupo aunque el
   patch traiga campos de certificación; nunca sobreescribe lo ya resuelto por regex; no
   llama al LLM si lo único que falta es de otro dominio; fallo degrada a regex-only;
   propaga a `state`; y el caso de la generalización: **ambos flags encendidos → una sola
   llamada** cubre certificación + grupo.
4. ✅ **Mejora de schema**: la descripción de `group_size` en el `_TOOL` de
   `llm_extractor.py` se afinó para contar enumeraciones de personas ("my wife and I" = 2,
   "me plus 3 friends" = 4, "four adults and a kid" = 5). Subió el acuerdo de group_size
   de 94% a 97% (el caso de enumeración implícita, antes `missed`, ahora acierta).
5. ✅ **Eval con LLM real** (`python -m scripts.run_extraction_eval`, 2026-07-21, gpt-4o):
   **121/122 = 99.2% de acuerdo, 1 desacuerdo, 0 huecos**. Por campo del dominio:
   `group_allocation` 8/8 (100%), `ages` 5/5 (100%), `group_size` 31/32 (97%). El único
   desacuerdo es el bug de regex `me plus 3 friends` — el regex resuelve `group_size=3`
   (mal) y, **por diseño, el gap-filler nunca pisa un campo que el regex ya resolvió**,
   así que este caso queda para un fix de regex o una fase de *override* futura, no lo
   arregla el cutover de gap-fill. Excluyéndolo, el gap-filler está al **100%** en el
   dominio de grupo, por encima del umbral ≥98%.
6. ✅ **Verificado en vivo con LLM real** (local, `.env`, flag activado a mano):
   - `"just the two of us wanna dive"` — regex no saca tamaño. Flag OFF →
     `group_size=None`; flag ON → `group_size=2`.
   - `"were a group of six, four certified divers and two snorkelers"` — regex saca
     `group_size=6` pero no el reparto. Flag OFF → `group_allocation=None`; flag ON →
     `group_allocation={certified_diving:4, snorkel:2}` (entra al flujo de grupo mixto).
   - `"mi hijo de ocho quiere probar y yo buceo"` — flag OFF → `group_size=None, ages=[]`;
     flag ON → `group_size=2, ages=[8]`.
7. ⬜ Pendiente (decisión de despliegue, no de código): activar
   `llm_extraction_cutover_group=True` en un entorno real cuando el equipo decida — mismo
   patrón que la Fase 1 (el flag de cada dominio se activa por separado). El código ya
   está listo, probado con TDD y verificado en vivo; el default sigue en `False`.

**Fase 2 completa** (código + tests + eval + verificación en vivo). El bug de regex
`me plus 3 friends` queda registrado en el eval-set como regresión permanente, pendiente
de fix por regex u override (fuera del alcance del gap-filler por el principio de no
sobreescribir lo que el regex ya resolvió).

### Fase 3 — Dominio ubicación/actividad/cambios de plan

`location`, `island`, `hotel`, y los interceptores de cambio de plan/acompañante que
generalizamos en el Fix 3 de `docs/archive/live-test-inconsistencies-plan.md` (los que causaron
la regresión que el Fix 4 tuvo que cazar). Este es el dominio con más regex dispersa
y más frágil — el más beneficiado por esta migración, pero también el que requiere más
cuidado (más superficie de regresión).

**Alcance real cortado en esta fase**: `location`/`island`/`hotel` (los campos de
`DetectedIntent` de este dominio). Los **interceptores de cambio de plan/acompañante NO
se cortan aquí**: no son campos de extracción de `DetectedIntent`, sino lógica de estado
mid-flow en `supervisor.py` (`_apply_group_recomposition` y similares) que reacciona a un
cambio durante el flujo. El patrón gap-filler (rellenar campos `None` de `DetectedIntent`)
no les aplica directamente; generalizarlos vía LLM es una sub-tarea aparte (candidata a
una Fase 3b o a la Fase 4 de integración con el orquestador), documentada aquí para que
no se pierda.

Pasos:

1. ✅ **Cutover implementado**: `settings.llm_extraction_cutover_location` (`src/config.py`,
   default `False`), registrado en `_active_cutover_fields()` con
   `_LOCATION_CUTOVER_FIELDS = {"location", "island", "hotel"}`. `location` (enum
   cartagena|island) es el campo de alto valor: dirige el enrutamiento logístico/precios y
   el LLM lo infiere de barrios/lugares que el regex no enumera (Bocagrande/Getsemaní/
   Manga/Castillogrande/Old Town → cartagena; Rosario/Barú → island). `island`/`hotel` se
   consumen solo para display/contexto (`island_names.get(slug, raw)`, degradan con
   gracia), así que rellenarlos con texto libre del LLM es inofensivo — no tocan el routing
   por service, que va por `state.location`.
2. ✅ **Mejora de schema**: la descripción de `location` en el `_TOOL` de
   `llm_extractor.py` se enriqueció con los barrios de Cartagena y las zonas insulares
   para guiar la inferencia; `island`/`hotel` con ejemplos.
3. ✅ **Fix defensivo del cutover** (hallado por TDD de esta fase): el cutover aplicaba
   cualquier campo del patch que estuviera en un dominio activo; ahora aplica SOLO los
   campos que eran un hueco real (`k in relevant_gaps`), no solo "en un dominio activo".
   `fill_gaps()` ya lo garantizaba, pero ahora el cutover refuerza él mismo la propiedad
   "nunca sobreescribir lo que el regex resolvió" (defensa en profundidad). Este fix
   beneficia a las 3 fases.
4. ✅ **Eval-set ampliado** de 58 a 64 casos: 6 adversariales de ubicación, cada uno
   validado contra el `IntentDetector` real (barrios de Cartagena en ES/EN + un hotel
   insular en Barú). El eval de `island`/`hotel` exactos se omite deliberadamente (son
   texto libre del LLM vs slugs canónicos del regex; el valor y el rigor está en
   `location`, el enum que dirige el routing).
5. ✅ **TDD**: `tests/test_llm_extraction_cutover.py` +5 tests (19 total) — flag apagado
   no llama al LLM; encendido rellena solo location/island/hotel aunque el patch traiga
   otros dominios; nunca sobreescribe `location` ya resuelto; degrada ante fallo; propaga
   a `state`.
6. ✅ **Eval con LLM real** (`python -m scripts.run_extraction_eval`, gpt-4o):
   **127/128 = 99.2% de acuerdo, 0 huecos**. `location` **13/13 = 100%**. El único
   desacuerdo global sigue siendo el bug de regex `me plus 3 friends` (Fase 2, group_size),
   ajeno a este dominio.
7. ✅ **Verificado en vivo con LLM real** (local, `.env`, flag a mano):
   - `"salimos desde bocagrande"` — flag OFF → `location=None`; ON → `location=cartagena`.
   - `"staying in the old town this week"` — OFF → `None`; ON → `location=cartagena`.
   - `"estamos hospedados en el hotel Las Islas en Baru"` — OFF → `None`; ON →
     `location=island, island=Barú, hotel=Las Islas` (entra a la logística insular).
8. ⬜ Pendiente (decisión de despliegue, no de código): activar
   `llm_extraction_cutover_location=True` en un entorno real cuando el equipo decida —
   mismo patrón que Fases 1-2. Default en `False`.

**Fase 3 completa** para el dominio de campos (location/island/hotel). Los interceptores
de cambio de plan/acompañante quedan explícitamente fuera (ver "Alcance real" arriba) —
son estado mid-flow, no extracción de campos, y se abordan en una fase posterior.

### Fase 4 — Integración con acciones de carrito (orchestrator)

Evaluar si, una vez los campos de `DetectedIntent` son fiables vía LLM, tiene sentido
fusionar esta extracción con el orquestador de acciones ya existente
(`src/agents/orchestrator.py`) en una sola llamada (ahorro de latencia/coste) o
mantenerlos separados (más simple de razonar, cada uno con su propio contrato).

**Decisión (tomada con datos de las fases 1-3): MANTENER SEPARADOS.** Razones:

1. **Concerns distintos.** El extractor (`fill_gaps`) es una extracción estructurada con
   `tool_choice` forzado a `extract_fields`, temperatura 0, prompt estrecho — determinista
   y validada contra el eval-set. El orquestador (`orchestrate`) elige una *acción* con
   `tool_choice="auto"` (puede declinar → `answer_question`), con otro prompt, otro set de
   tools y no-determinismo conocido. Fusionarlos metería la extracción (cuidada, medida)
   dentro del no-determinismo "auto" del orquestador — justo lo que este plan evita.
2. **El valor ya fluye.** El orquestador YA recibe el estado enriquecido por la extracción
   (cutover → `_apply_detected_intent` → `_build_extra_context` → snapshot). Fusionar no
   añadiría capacidad, solo ahorraría una llamada.
3. **El ahorro es pequeño en la práctica.** La 2ª llamada (extracción) solo ocurre cuando
   un flag de cutover está encendido Y el regex dejó un hueco relevante — la minoría de
   turnos. En el caso común (regex resuelve todo) no hay llamada extra.
4. **Testabilidad y kill switch.** Separados, cada uno es una función pura mockeable con su
   propio contrato y su propio flag; fusionados, se acopla la superficie de regresión de
   ambos.

**Mejora concreta entregada** (el objetivo de coste/latencia de esta fase, sin la
fusión arriesgada): el extractor pasa a un modelo dedicado más barato y rápido,
`settings.extraction_model` (default `gpt-4o-mini`), separado de `settings.openai_model`
(gpt-4o, que sigue en el orquestador para su tarea más difícil de decidir acción).

- Medido en `docs/robustness/eval-set.json` (64 casos): **gpt-4o-mini = 98.4%** vs
  **gpt-4o = 99.2%**. La única diferencia es **1 `missed` de más** (se abstiene en un caso
  de conteo implícito difícil en vez de rellenar mal) — 0 `disagree` de más. Modo de fallo
  **seguro**: degrada a "regex-only / preguntar", nunca a un valor equivocado.
- Sigue por encima del umbral ≥98% de los cutover, y es ~15-30x más barato por llamada.
- Revertible con una línea (`extraction_model="gpt-4o"`).

**Interceptores de cambio de plan/acompañante** (los que quedaron fuera de la Fase 3): se
confirman como trabajo separado del patrón gap-filler — son estado mid-flow, no extracción
de campos. Candidatos a una fase propia si el tráfico real (logs `[EXTRACT][CUTOVER]` en
PRE) muestra que siguen siendo una fuente de fragilidad. No se abordan aquí.

### Fase 8 — Dominio nacionalidad/logística + cobertura de entry-points (NUEVA, review H4/H5)

Los campos extraíbles que ningún dominio aplicaba: `is_colombian` (dirige moneda + el
descuento colombiano), `duration` (single/multi día) y `last_dive_over_2_years` (señal de
refresher). El LLM los infiere de frases que el regex no enumera.

Pasos (Parte 1 — dominio):

1. ✅ `settings.llm_extraction_cutover_logistics` (`src/config.py`, default `False`),
   registrado en `_active_cutover_fields()` con `_LOGISTICS_CUTOVER_FIELDS =
   {"is_colombian", "duration", "last_dive_over_2_years"}`.
2. ✅ Eval-set 64 → 71 casos: 7 adversariales validados contra el regex real
   ("soy paisa"→colombiano por slang, "vivo en España"→extranjero, "toda la semana"→
   multi_day, "hace como 4 años que no buceo"→>2y). También sube la cobertura fina que la
   review marcó como débil (H3) para estos 3 campos.
3. ✅ TDD: `tests/test_llm_extraction_cutover.py` +4 tests (23 total) — incl. el guard de
   "false es resuelto, no hueco" (`is_colombian=False`/`last_dive=False` no disparan LLM).
4. ✅ Eval con LLM real (gpt-4o-mini): **dominio al 100%** — `is_colombian` 4/4, `duration`
   5/5, `last_dive_over_2_years` 5/5. (Overall del eval-set: 133/136 = 97.8%; los 3
   no-acuerdos son ajenos a este dominio: el bug de regex `me plus 3 friends` + 2
   abstenciones seguras de gpt-4o-mini en casos límite de group_size/ages — `missed`, no
   misfill. Ver nota de varianza en `progress-log.md`.)
5. ✅ Verificado en vivo: `"soy paisa"` OFF→`is_colombian=None` / ON→`True`;
   `"toda la semana en las islas"` ON→`duration=multi_day`; `"hace como 4 años que no
   buceo"` ON→`last_dive_over_2_years=True`.
6. ⬜ Pendiente (despliegue): activar `llm_extraction_cutover_logistics=True` en PRE cuando
   se decida. Default `False`.

Parte 2 — cobertura de entry-points (H4): **DEFERIDA con razón documentada**. El cutover
solo está cableado en `_dispatch_conversation_agent`. Los otros 2 sitios que llaman
`intent_detector.detect` — `_apply_group_recomposition` (cambios de grupo mid-flow) y
`_maybe_answer_age_eligibility` (preguntas de edad) — son **short-circuits pre-dispatch**:
cuando devuelven `None`, el turno cae a `_dispatch_conversation_agent`, que YA corre el
cutover. Cablearlo también ahí significaría **dos llamadas LLM por mensaje** en el caso de
fall-through (el común). El fix correcto no es cablearlo en cada sitio, sino **un único
cutover temprano en `_route_message_inner`** compartido por todos los paths — un refactor
del dispatch que merece su propio cuidado (y su propia medición de que no rompe el orden de
short-circuits). Documentado con `NOTE` en ambas funciones. Trabajo futuro.

### Fase 6 — Bucle de datos reales (NUEVA, prioridad alta — review H1/H8)

**Objetivo:** cerrar el bucle de datos. Hoy el eval-set se alimenta de casos sintéticos/
manuales; el hallazgo H1 de la revisión es que **no hay bucle de datos reales**, así que
no sabemos con qué frecuencia dispara cada dominio ni qué casos reales fallan. Esta fase
convierte el tráfico real de PRE en casos de eval-set curados, y añade observabilidad de
disparos por dominio (H8). **Bloquea la Fase 5** (sin datos reales no se sabe qué regex
está muerto y se puede retirar).

**Estado:** `[~]` en curso. **Tooling ya construido** (2026-07-21):
- `scripts/harvest_cutover_logs.py` — parsea los logs `[EXTRACT][CUTOVER]` / `[EXTRACT]
  [SHADOW]` de PRE → candidatos deduplicados para el eval-set (modo default) + contador
  por campo/dominio (`--summary`, cubre H8). 5 tests en `tests/test_harvest_cutover_logs.py`.
- `docs/robustness/live-test-battery-fase6.md` — batería de 32 casos para generar tráfico.
- Fix (v0.20.38): los logs truncaban el mensaje a 60 chars (`message[:60]`), justo lo que
  la cosecha NO puede permitirse; nuevo `_log_safe_message()` (límite 500, marca
  `…[truncated]`). Tests `test_*_log_line_does_not_truncate_the_message`.

**Pendiente (los pasos que faltan por ejecutar):**

1. **Asegurar que se generan logs `[EXTRACT]` en PRE con tráfico real.** Los cutover por
   dominio ya se activaron en PRE "para pruebas reales" (Fases 1/2/3/8), así que las
   líneas `[EXTRACT][CUTOVER]` deberían salir. Confirmar que el shadow/cutover está
   emitiendo (H1 señalaba que el shadow-mode estaba apagado en todos los entornos).
2. **Generar tráfico registrable.** Correr la batería de 32 casos
   (`docs/robustness/live-test-battery-fase6.md`) contra PRE y/o dejar entrar tráfico real
   de clientes. **Aviso apuntado en `progress-log.md`**: los mensajes de prueba a veces no
   llegan a `docker logs` — verificar que el tráfico de prueba SÍ queda registrado antes de
   cosechar (si no, la cosecha sale vacía).
3. **Cosechar.** Por SSH a la VPS, correr `harvest_cutover_logs.py` sobre los logs de
   `dp-pre-bot` → candidatos deduplicados; `--summary` para el contador por dominio (H8).
4. **Curar.** Validar el `expected` de cada candidato contra el pipeline real ANTES de
   fijarlo en `docs/robustness/eval-set.json` (no meter etiquetas sin verificar).
5. **Re-medir.** Recalcular el % de acuerdo con el eval-set ampliado; si algún dominio cae
   por debajo del umbral (≥98%), ajustar el extractor/prompt antes de más cutover.

**Criterio de salida:** eval-set alimentado con casos reales curados + contador de
disparos por dominio operativo. Con esto se desbloquea la Fase 5.

### Fase 7 — Override selectivo por campo (NUEVA — review H6)

**Objetivo:** hoy el LLM solo rellena huecos que el regex dejó vacíos (gap-filler). Hay
casos donde el regex "resuelve" pero se equivoca. Esta fase introduce un **override
medido por campo**: donde los datos (Fase 6) muestren que el LLM es más fiable que el
regex para un campo concreto, dejar que el LLM lo pise aunque el regex haya resuelto.
**Requiere los datos de la Fase 6** para decidir por campo con evidencia, no a ojo. Ver
`review-2026-07-21.md` H6.

**Actualización 2026-07-22**: los 3 bugs que motivaban esta fase (`me plus 3 friends` →
`group_size`; `hace como N años` → `ages` fantasma; "i already have my open water" →
clasificado como querer tomar el curso) se **arreglaron directamente en el regex**
(v0.20.51) — eran bugs de adyacencia/enumeración puntuales, no casos donde el LLM sea
sistemáticamente más fiable. **La Fase 7 queda sin justificación pendiente por ahora.**
Retomar solo si aparece un caso nuevo donde el regex se equivoque de forma no
arreglable en el propio patrón (con evidencia de la Fase 6, no a ojo).

### Fase 5 — Limpieza y consolidación

Una vez todos los dominios migrados y estables en producción durante un periodo
razonable (a decidir con el equipo, ej. 2-4 semanas sin incidentes): eliminar el código
regex ya muerto, actualizar toda la documentación, y cerrar este plan como completado
(mover a `docs/project-history/` como referencia histórica, igual que se hizo con
`docs/archive/memory-context-improvement-plan.md`).

## 5. Formato del eval-set

Seguir el mismo patrón ya usado en `docs/rag-eval-set.json` (usado para calibrar
`RAG_MIN_SCORE`, ver `docs/archive/rag-threshold-calibration.md`) — un JSON versionable en el
repo, no una hoja de cálculo externa (`docs/project-history/estado-pendientes.md` ya
señala que el Google Sheet es solo para el checklist de lanzamiento, no para esto).

Propuesta de estructura (`docs/robustness/eval-set.json`, a crear en la Fase 0):

```json
{
  "cases": [
    {
      "id": "cert-typo-not-certfied-en",
      "message": "hi i wanna dive, im not certfied tho, just me",
      "lang": "en",
      "expected": {
        "is_certified": false,
        "activity": "certified_diving",
        "group_size": 1
      },
      "source": "live-PRE-2026-07-21",
      "notes": "Typo 'certfied' — bug real arreglado en v0.20.31"
    },
    {
      "id": "cert-typo-vucea-es",
      "message": "vamos 2, mi novia y yo, ella no vucea solo yo",
      "lang": "es",
      "expected": {
        "activity": "certified_diving",
        "group_size": 2
      },
      "source": "live-PRE-2026-07-21",
      "notes": "Typo b/v 'vucea'/'bucea' — bug real arreglado en v0.20.31"
    }
  ]
}
```

Cada caso nuevo encontrado (en vivo, o reportado por el owner) se añade aquí primero
—convirtiéndolo en regresión permanente— y luego se arregla, sea cual sea el mecanismo
(regex o LLM). Este archivo crece indefinidamente y es compartido por la Fase 0 (medir
acuerdo) y por cualquier fase de cutover posterior (medir regresiones).

## 6. Riesgos conocidos y cómo se mitigan

| Riesgo | Mitigación |
|---|---|
| No-determinismo del LLM (mismo mensaje, resultado distinto) | Temperatura 0, structured output, eval-set con umbral de acuerdo antes de cualquier cutover, kill switch por fase |
| Coste/latencia (llamada extra por mensaje) | Activación condicional (§3.3): solo cuando el regex deja huecos, no siempre |
| Regresión en un flujo ya validado | Nunca sobreescribe lo que el regex ya resolvió (fase inicial); suite completa + verificación en vivo obligatoria antes de cada cutover |
| El plan se abandona a medio camino entre sesiones | `progress-log.md` obligatorio, checklist de fases en este documento, README con instrucciones explícitas de "cómo retomar" |
| Se repite el error del Fix 3 de hoy (ampliar una regla sin darse cuenta de que incluye un caso donde el contexto asumido no es cierto) | Cada fase tiene su propio eval-set y su propia ronda de TDD — no se generaliza "por analogía", se mide con datos antes de cada cutover |

## 7. Referencias

- `docs/archive/robustness-strategy-options.md` — las 4 opciones evaluadas, esta es la Opción 2.
- `docs/project-history/estado-pendientes.md` (punto #10) — la propuesta original de Álvaro.
- `docs/archive/live-test-inconsistencies-plan.md` — los 4 fixes de la sesión que motivó esta decisión.
- `docs/HISTORY.md` v0.20.30-31 — los bugs concretos que ilustran el problema.
- `docs/archive/rag-threshold-calibration.md` — precedente de metodología (eval-set + umbral medido con datos) ya usado en este repo para otra decisión de calibración.
