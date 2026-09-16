# Registro de progreso — extracción semántica por LLM

**Append-only.** No edites bloques anteriores — añade uno nuevo al final con fecha y
autor/sesión. Antes de escribir código en cualquier sesión nueva, lee TODO este
archivo (especialmente el último bloque) antes de tocar nada.

Plantilla para cada bloque nuevo:

```
## AAAA-MM-DD — <quién/qué sesión>

**Fase(s) tocada(s)**:
**Qué se hizo**:
**Decisiones tomadas y por qué**:
**Qué quedó a medias / bloqueadores**:
**Siguiente paso concreto para quien continúe**:
```

---

## 2026-07-21 — sesión inicial (creación del plan)

**Fase(s) tocada(s)**: ninguna (planificación, previa a la Fase 0).

**Qué se hizo**: tras una sesión de live-testing contra PRE que encontró 6
inconsistencias reales en total (4 documentadas en `docs/archive/live-test-inconsistencies-plan.md`,
2 más de typos documentadas en `docs/HISTORY.md` v0.20.31), se escribió
`docs/archive/robustness-strategy-options.md` con 4 opciones estratégicas para el equipo. El
owner + Álvaro + Gonzalo decidieron empezar por la Opción 2 (extracción semántica vía
LLM). Se creó esta carpeta (`docs/robustness/`) con el plan completo (`plan.md`), este
registro de progreso, y el índice (`README.md`).

**Decisiones tomadas y por qué**:
- El diseño es **gap-filler, no reemplazo**: el LLM solo rellena campos que el regex
  deja en `None`, nunca sobreescribe lo que el regex ya resolvió — mismo enfoque que
  Álvaro ya había propuesto en `docs/project-history/estado-pendientes.md` punto #10.
  Razón: el orquestador LLM ya existente es conocidamente no-determinista; reemplazar
  el regex determinista de golpe cambiaría "bugs reproducibles" por "bugs
  intermitentes", peor para un negocio real.
- Migración por dominio (strangler fig), empezando por certificación (Fase 1) — es el
  dominio más pequeño y el que más bugs reales ha producido (v0.20.9/12/17-21/30-31).
- Eval-set explícito en JSON versionado (`docs/robustness/eval-set.json`, a crear en
  Fase 0) siguiendo el mismo patrón que `docs/rag-eval-set.json` — no un Google Sheet
  (ese ya está reservado para el checklist de lanzamiento, ver
  `docs/project-history/estado-pendientes.md`).
- Ningún cutover sin: eval-set con umbral de acuerdo medido, TDD, suite completa,
  verificación en vivo contra PRE (mismo rigor que se ha seguido toda la sesión de
  hoy para los fixes de v0.20.30/31).

**Qué quedó a medias / bloqueadores**: nada implementado todavía — es puramente el
plan. La Fase 0 no ha empezado.

**Siguiente paso concreto para quien continúe**: empezar la Fase 0 (`plan.md` §4):
(1) crear `docs/robustness/eval-set.json` con las semillas descritas en §5 del plan
(casos de `tests/test_intent_detector.py` + los 2 bugs de v0.20.31 + adversariales
nuevos); (2) escribir `LLMExtractor.fill_gaps()` como función aislada con su propio
test file, mockeable, SIN integrarla aún en `supervisor.py`; (3) construir el harness
de shadow-mode detrás de un flag. No cambiar comportamiento de producción en esta
fase — el criterio de salida está en `plan.md` §4 Fase 0.

---

## 2026-07-21 — Fase 0 pasos 1-4 completados (mismo día, sesión de continuación)

**Fase(s) tocada(s)**: Fase 0 (pasos 1-4 de 5).

**Qué se hizo**:
- `docs/robustness/eval-set.json`: 50 casos — 42 semillas derivadas de
  `tests/test_intent_detector.py` (regex como ground truth) + 8 adversariales nuevos
  (negación con contracción EN, doble negación ES, edad+actividad de un tercero,
  certificación implícita por curso PADI, mensaje elíptico sin verbo "bucear",
  code-switching ES/EN, typo de letra duplicada, abreviatura "ppl"). Los 2 bugs reales
  de v0.20.31 ("not certfied", "vucea") están marcados con su fuente real.
- `src/agents/llm_extractor.py`: `EXTRACTABLE_FIELDS` (subconjunto de `DetectedIntent`
  que el LLM puede rellenar — excluye `language`/`service_id`/`confidence`/
  `detected_fields`), `missing_fields()`, `fill_gaps()` (gap-filler puro, nunca
  sobreescribe lo que el regex ya resolvió, fallback a `{}` en cualquier error),
  `compare_with_ground_truth()` (helper para el eval-runner). 14 tests en
  `tests/test_llm_extractor.py` (mismo patrón de fake-client que
  `tests/test_orchestrator.py`).
- `settings.llm_extraction_shadow_mode` (`src/config.py`, default `False`) +
  `_maybe_log_llm_extraction_shadow()` en `supervisor.py`, enganchado en
  `_dispatch_conversation_agent` justo después de `intent_detector.detect()`. 4 tests
  en `tests/test_llm_extraction_shadow_mode.py`, incluido uno que fuerza un
  `AssertionError` si `fill_gaps` se llama con el flag apagado — prueba dura de la
  propiedad de seguridad, no solo observacional.
- `scripts/run_extraction_eval.py`: corre el pipeline realista (regex →
  `fill_gaps()` sobre los huecos) contra el eval-set y reporta acuerdo/desacuerdo por
  campo. Validado mecánicamente con `fill_gaps` mockeado (sin LLM real todavía).
- Suite completa: **1731 passed** (1713 + 18 tests nuevos), mismos 8 fallos
  preexistentes sin relación. `ruff check` limpio en todos los archivos tocados/creados.
  `compileall` limpio.

**Decisiones tomadas y por qué**:
- `missing_fields()` usa `getattr(...) in (None, [])`, NO `not getattr(...)` — un bug
  real que el propio test (`test_missing_fields_treats_false_as_resolved`) cazó ANTES
  de que llegara a ningún lado: con truthiness simple, `is_certified=False` (una
  respuesta real y resuelta) se habría tratado como "falta por rellenar", exactamente
  el mismo tipo de bug de fondo que motivó todo este plan (confundir "falso" con
  "desconocido").
- El eval-set inicial excluye `language` de los campos `expected` — ya tiene su propio
  detector robusto (`_detect_language`) y está fuera del alcance deliberado de
  `EXTRACTABLE_FIELDS`; incluirlo en el eval-set solo generaba "missed" artificiales
  sin señal real.
- El hook de shadow-mode se puso solo en `_dispatch_conversation_agent` (el
  entry-point principal de comprensión de texto libre), no en los 2 sitios más
  puntuales (`_apply_group_recomposition`, `_maybe_answer_age_eligibility`) — es el de
  mayor tráfico y variedad de typos, suficiente para la medición inicial de Fase 0. Si
  el análisis de acuerdo por campo sugiere que hace falta más cobertura, añadir el
  hook a esos otros 2 sitios es trivial (misma función, mismo patrón).

**Qué quedó a medias / bloqueadores**: el paso 5 de la Fase 0 (correr el eval-set con
un LLM real y medir tasa de acuerdo) NO se hizo — esta sesión no tiene
`OPENAI_API_KEY` real disponible localmente. El baseline SOLO-REGEX (sin LLM, mockeado
a `{}`) ya se validó: **94/100 (94.0%) de acuerdo, 1 desacuerdo, 5 huecos** — los
huecos caen exactamente en los 8 casos adversariales nuevos, que es la señal esperada
(ahí es donde el LLM debe demostrar que aporta valor). Nada de esto se ha commiteado
todavía en este bloque de trabajo — pendiente de decisión del usuario sobre push.

**Siguiente paso concreto para quien continúe**:
1. Correr `ENV_FILE=.env.dev python -m scripts.run_extraction_eval` (o vía SSH contra
   PRE, mismo patrón que `scripts/live_battery_driver.py`) con un `OPENAI_API_KEY`
   real, y pegar el resultado aquí (tasa de acuerdo real por campo, no el baseline
   mockeado).
2. Si el acuerdo es alto para el campo `is_certified`/`activity` (los del dominio de
   certificación, ver Fase 1), decidir el umbral de corte concreto y empezar la Fase 1
   (`plan.md` §4).
3. Considerar activar `llm_extraction_shadow_mode=True` en un entorno real (dev o PRE)
   durante unos días/sesiones para acumular datos de tráfico real, no solo del
   eval-set sintético — el eval-set es semillas iniciales, no sustituto de tráfico real.
4. Si se añaden más casos al eval-set (recomendado: cualquier bug nuevo encontrado en
   vivo debe añadirse aquí ANTES de arreglarse, como regla general del plan), re-correr
   el script y actualizar el baseline documentado en `plan.md` §4 Fase 0 paso 5.

---

## 2026-07-21 — Fase 0 paso 5: eval-set corrido con LLM real, Fase 0 completa

**Fase(s) tocada(s)**: Fase 0 (paso 5, el que quedaba pendiente).

**Qué se hizo**: el usuario dio permiso explícito para usar una API key real. Se
encontró una key real ya presente en `.env.dev` (local, no committeada) y se corrió:

```
ENV_FILE=.env.dev python -m scripts.run_extraction_eval
```

**Resultado real (LLM real, no mockeado), primera pasada**: **99/100 (99.0%) de
acuerdo, 1 desacuerdo, 0 huecos** — sobre el baseline solo-regex de 94% (mockeado,
sesión anterior). Los 8 casos adversariales que antes quedaban como "hueco" (regex
solo) los resolvió el LLM correctamente, salvo uno.

**El desacuerdo, investigado a fondo (el usuario cuestionó correctamente mi primer
análisis, y tenía razón)**:
- Caso `adv-en-negation-contraction`: `"hey we arent certified, first time diving,
  just the two of us"`. Esperado (mal escrito por mí): `activity="certified_diving"`.
  LLM devolvió: `activity="minicourse"`.
- **Mi primer análisis fue incorrecto**: escribí que era "una ambigüedad real de
  schema" (que `"certified_diving"` es la categoría genérica de "quiere bucear" en el
  código, y el LLM habría sobre-interpretado). El usuario preguntó, con razón, por qué
  eso estaría mal si el cliente literalmente dice que NO está certificado — debería
  ofrecerle el minicurso. Al verificar contra el código real (no contra mi memoria del
  código), confirmé que el usuario tenía razón y yo no:
  - El regex actual, corrido en vivo contra ese mensaje exacto, YA da
    `activity="minicourse"` — hay un patrón dedicado en `minicourse_patterns`
    (`intent_detector.py`) que reconoce la frase "first time diving" explícitamente.
    No es una laguna del regex, ya está cubierto.
  - Además, comprobé el routing real: con `is_certified=False`, si `activity` fuera
    `"certified_diving"` (lo que yo había puesto como "esperado"), **ni
    `_should_ask_certification` (exige `is_certified is None`) ni
    `_should_skip_to_certified_flow` (exige `is_certified is True`) se disparan** — el
    mensaje NO entraría a ningún flujo guiado, caería a RAG. Con `"minicourse"` sí
    entra directo al flujo de principiantes — el comportamiento correcto.
  - Conclusión: mi "expected" en el eval-set estaba mal escrito a mano (lo razoné sin
    correr antes el detector real). El LLM y el regex actual **coincidían y ambos
    acertaban** — el eval-set era el que estaba equivocado, no el LLM.
- **Corregido**: `docs/robustness/eval-set.json`, caso `adv-en-negation-contraction`,
  `expected.activity` → `"minicourse"`, con nota explicando la corrección. Re-corrida
  la evaluación: **100/100 (100.0%) de acuerdo, 0 desacuerdos, 0 huecos**.

**Lección de proceso (importante para cualquier sesión futura que edite el
eval-set)**: un caso adversarial escrito a mano SIEMPRE debe validarse corriendo el
pipeline real (`IntentDetector().detect(mensaje, state)` + los predicados de routing
en `supervisor.py` si aplica) ANTES de fijar su "expected" — razonar "a ojo" qué
debería pasar, sin verificarlo contra el código, reproduce exactamente el mismo tipo
de error que este plan entero intenta evitar (asumir en vez de medir).

**Decisiones tomadas y por qué**: con 100.0% de acuerdo (por encima del umbral ≥98%
propuesto en el plan para el cutover), **la Fase 0 se da por completa**. La Fase 1
(dominio certificación) puede empezar — sus criterios de entrada están cumplidos, sin
ningún ajuste de prompt pendiente (el prompt actual ya funciona bien para este caso).

**Qué quedó a medias / bloqueadores**: nada. La Fase 0 está completa sin deuda
pendiente.

**Siguiente paso concreto para quien continúe**: empezar la Fase 1 (`plan.md` §4,
sección "Fase 1 — Dominio certificación"):
1. Cambiar la regla de activación de "solo shadow" a "el LLM rellena
   `is_certified`/`activity` cuando el regex los deja en `None`, y el resultado SÍ se
   aplica a `state`" (primer cutover real, aún con el regex como camino primario y
   el LLM solo en huecos — ver plan.md §3.2).
2. TDD + suite completa + verificación en vivo contra PRE (mismo patrón usado toda la
   sesión) antes de dar la Fase 1 por cerrada.
3. Seguir ampliando el eval-set con cualquier caso nuevo que aparezca — validando
   SIEMPRE contra el pipeline real antes de fijar el "expected" (ver lección de
   proceso arriba).

---

## 2026-07-21 — Fase 1 implementada: cutover real del dominio certificación

**Fase(s) tocada(s)**: Fase 1 (dominio certificación) — completa.

**Qué se hizo**:
- `settings.llm_extraction_cutover_certification` (`src/config.py`, default `False`).
- `_maybe_apply_llm_extraction_cutover()` en `supervisor.py`: cuando el flag está
  encendido y el regex dejó `is_certified`/`activity` sin resolver, llama a
  `fill_gaps()` y aplica SOLO esos 2 campos al `intent` (cualquier otro campo del
  patch se descarta — queda para su propia fase futura). Se engancha en
  `_dispatch_conversation_agent` ANTES de `_apply_detected_intent(intent, state)`,
  para que lo rellenado se propague a `state` por el camino ya existente, sin tocar
  esa función.
- 7 tests nuevos en `tests/test_llm_extraction_cutover.py`: flag apagado no llama al
  LLM (con `AssertionError` forzado como prueba dura); flag encendido rellena solo
  los 2 campos en scope aunque el patch traiga más; nunca sobreescribe lo que el
  regex ya resolvió; no llama al LLM si lo único que falta es de otro dominio
  (ej. `group_size`); fallo del LLM degrada a regex-only sin romper nada; el
  resultado se propaga correctamente a `state` vía `_apply_detected_intent`.
- Suite completa: **1738 passed** (1731 + 7 nuevos), mismos 8 fallos preexistentes.
  `ruff`/`compileall` limpios.
- **Verificación en vivo con LLM real** (local, `ENV_FILE=.env.dev`, flag activado a
  mano para la prueba): mensaje `"never been underwater before, wanna give it a try,
  solo"` — el regex no resuelve nada (`activity=None`, `is_certified=None`).
  - **Flag apagado** (comportamiento de hoy en todos los entornos): cae a RAG
    genérico, se queda en `main_menu`, sin `detected_activity`.
  - **Flag encendido**: entra directo al flujo guiado de minicurso
    (`step=mixed_location`, `detected_activity="minicourse"`,
    `detected_is_certified=False`).
  - Contraste real y medible, no solo teórico — la mejora que la Fase 1 debía demostrar.

**Decisiones tomadas y por qué**:
- El cutover se restringe explícitamente a `_CERTIFICATION_CUTOVER_FIELDS =
  {"is_certified", "activity"}` — aunque `fill_gaps()` puede devolver más campos
  (group_size, location...) si el regex también los dejó sin resolver, esos NO se
  aplican todavía. Cada dominio se corta por separado, con su propio flag, siguiendo
  el diseño de fases del plan — evita que activar la Fase 1 traiga de regalo un
  cutover no probado de otro dominio.
- El hook corre ANTES de `_apply_detected_intent`, no después — así el enriquecimiento
  se integra por el camino normal (esa función ya sabe cómo escribir `intent.activity`/
  `intent.is_certified` en `state`), sin necesidad de duplicar esa lógica ni tocar
  `_apply_detected_intent` en absoluto.
- Verificación en vivo hecha LOCALMENTE con `.env.dev` (no contra PRE) porque el flag
  por defecto sigue en `False` en todos los entornos — no hay necesidad de tocar PRE
  para esto; activar el flag ahí es una decisión de despliegue explícita y separada
  (ver siguiente paso).

**Qué quedó a medias / bloqueadores**: nada técnico. Lo único pendiente es una
decisión de producto/timing: cuándo (si acaso) activar
`llm_extraction_cutover_certification=True` en un entorno real. El código está listo,
probado con TDD, y verificado en vivo con el LLM real.

**Siguiente paso concreto para quien continúe**: dos caminos posibles, a decidir con
el equipo (no es una decisión técnica):
1. **Activar el flag en PRE** (o dev) y dejarlo corriendo un tiempo con tráfico real
   antes de plantear producción — mismo patrón cauteloso ya usado para otras
   features (`settings.history_window_size`, etc.).
2. **Seguir con la Fase 2** (dominio grupo/cantidad/edades — `group_size`,
   `group_allocation`, `ages`) sin esperar a activar la Fase 1 en producción, ya que
   son dominios independientes y el flag de cada uno se activa por separado.
Cualquiera de las dos es válida; ninguna bloquea a la otra.

---

## 2026-07-21 — Flag de Fase 1 activado en PRE (para ir probando)

**Fase(s) tocada(s)**: Fase 1 (despliegue/activación, no código nuevo).

**Qué se hizo**: el usuario pidió explícitamente activar el flag en PRE para
empezar a probarlo con tráfico real. Se fijó `LLM_EXTRACTION_CUTOVER_CERTIFICATION:
"true"` en `docker-compose.vps.yml` (sección `dp-pre-bot`, `environment:`) — mismo
patrón ya usado para `RAG_MIN_SCORE` (pinned en el compose, no en `.env.pre` a mano
en el VPS, así queda versionado en el repo). El deploy-pre de CI hace
`docker compose up -d --build dp-pre-bot` en cada push a `feature/pre_gadea`, así que
un push normal ya aplica el cambio — no hace falta tocar el VPS a mano.

**Decisiones tomadas y por qué**: el flag queda encendido SOLO en PRE (`dp-pre-bot`),
no en PRO (que ni siquiera está desplegado hoy — ver memoria de sesión) ni en ningún
otro entorno. `src/config.py` sigue con el default `False`, así que cualquier otro
entorno que se levante de cero sigue sin este comportamiento salvo que se pin explícito
igual que aquí.

**Qué quedó a medias / bloqueadores**: pendiente confirmar tras el deploy que PRE
sigue sano (`/health`) y, con el tiempo, revisar los logs `[EXTRACT][CUTOVER]
applied=...` en PRE para ver cuántas veces se dispara con tráfico real y si acierta.

**Siguiente paso concreto para quien continúe**: revisar periódicamente los logs de
`dp-pre-bot` buscando `[EXTRACT][CUTOVER]` para ver el patrón real de uso antes de
decidir si se mantiene, se generaliza a otros dominios, o se apaga. Si algo va mal,
revertir es solo quitar esta línea de `docker-compose.vps.yml` + push (sin rollback
de código).

---

## 2026-07-21 — Fase 2 implementada: cutover del dominio grupo/cantidad/edades

**Fase(s) tocada(s)**: Fase 2 (dominio grupo/cantidad/edades) — completa.

**Qué se hizo**:
- `settings.llm_extraction_cutover_group` (`src/config.py`, default `False`) — kill
  switch independiente del de certificación (plan.md principio #7).
- **Generalización del cutover a multi-dominio** (`supervisor.py`): antes
  `_maybe_apply_llm_extraction_cutover` tenía cableado el set de certificación; ahora hay
  `_CERTIFICATION_CUTOVER_FIELDS` + `_GROUP_CUTOVER_FIELDS = {"group_size",
  "group_allocation", "ages"}` y un helper `_active_cutover_fields()` que une los campos
  de los dominios cuyo flag está encendido. La función hace **una sola llamada a
  `fill_gaps()`** que cubre todos los dominios activos (§3.3, coste/latencia) y aplica
  solo los campos en scope. Retrocompatible: con el flag de grupo apagado (default), su
  comportamiento es idéntico al de la Fase 1 — los 7 tests de certificación pasan sin
  tocarlos.
- **Mejora de schema**: la descripción de `group_size` en `llm_extractor.py` se afinó
  para contar enumeraciones de personas ("my wife and I" = 2, "me plus 3 friends" = 4,
  "four adults and a kid" = 5). Subió el acuerdo de `group_size` de 94% a 97%.
- **Eval-set ampliado** de 50 a 58 casos (`docs/robustness/eval-set.json`): 8
  adversariales del dominio de grupo, cada uno validado contra el `IntentDetector` real
  antes de fijar `expected` (lección de proceso de la Fase 0). Incluye un **bug de regex
  real** hallado en esta fase: `me plus 3 friends` → regex resuelve `group_size=3`
  (debería ser 4).
- **TDD**: `tests/test_llm_extraction_cutover.py` +7 tests (14 total) — flag apagado no
  llama al LLM; encendido rellena solo los 3 campos de grupo aunque el patch traiga
  campos de certificación; nunca sobreescribe lo resuelto por regex; no llama al LLM si
  solo falta otro dominio; degrada a regex-only ante fallo; propaga a `state`; y el caso
  clave de la generalización: **ambos flags on → una sola llamada** cubre ambos dominios.
- Suite completa: **1753 passed, 15 skipped** (1746 + 7 nuevos). `ruff`/`compileall`
  limpios.

**Resultado del eval con LLM real** (`python -m scripts.run_extraction_eval`, gpt-4o,
`.env` local): **121/122 = 99.2% de acuerdo, 1 desacuerdo, 0 huecos**. Por campo del
dominio: `group_allocation` 8/8 (100%), `ages` 5/5 (100%), `group_size` 31/32 (97%). El
único desacuerdo es el bug de regex `me plus 3 friends` — el regex ya resolvió el campo
(mal) y el gap-filler no lo pisa por diseño. **Excluyendo ese bug documentado, el
gap-filler está al 100% en el dominio de grupo**, por encima del umbral ≥98%.

**Verificación en vivo con LLM real** (local, `.env`, flag activado a mano):
- `"just the two of us wanna dive"`: flag OFF → `group_size=None`; ON → `group_size=2`.
- `"were a group of six, four certified divers and two snorkelers"`: OFF →
  `group_allocation=None`; ON → `group_allocation={certified_diving:4, snorkel:2}`.
- `"mi hijo de ocho quiere probar y yo buceo"`: OFF → `group_size=None, ages=[]`; ON →
  `group_size=2, ages=[8]`.

**Decisiones tomadas y por qué**:
- Generalizar el cutover a multi-dominio (en vez de duplicar una función por dominio)
  evita una segunda llamada LLM cuando dos dominios están encendidos a la vez, y mantiene
  el kill switch por dominio (cada flag decide qué campos del único patch se aplican). Se
  eligió mantener el nombre y la firma de `_maybe_apply_llm_extraction_cutover` para no
  romper los tests de Fase 1 ni el call-site en `_dispatch_conversation_agent`.
- El bug de regex `me plus 3 friends` NO se arregló en esta fase: el gap-filler no puede
  (el regex ya resuelve el campo, mal, y el diseño prohíbe sobreescribir regex). Se dejó
  en el eval-set como regresión permanente, con nota, para una futura fase de override o
  un fix puntual de regex — arreglarlo ahora sería salirse del alcance de la Fase 2.
- La mejora de la descripción de `group_size` se validó re-corriendo el eval completo
  (no solo el caso afectado) para confirmar que no regresó ningún otro campo (subió
  group_size, el resto quedó igual en 100%).

**Qué quedó a medias / bloqueadores**: nada técnico. Como en la Fase 1, lo único
pendiente es la decisión de producto/timing de cuándo activar
`llm_extraction_cutover_group=True` en un entorno real (dev/PRE). El código está listo,
probado y verificado en vivo; el default sigue en `False`.

**Siguiente paso concreto para quien continúe**: dos caminos, ninguno bloquea al otro:
1. **Activar el flag de grupo en PRE** (`docker-compose.vps.yml`, sección `dp-pre-bot`,
   `LLM_EXTRACTION_CUTOVER_GROUP: "true"`) igual que se hizo con el de certificación, para
   acumular datos de tráfico real antes de plantear producción.
2. **Seguir con la Fase 3** (dominio ubicación/actividad/cambios de plan — `location`,
   `island`, `hotel` y los interceptores de cambio de plan/acompañante). Es el dominio con
   más regex dispersa y frágil, el más beneficiado pero también el de más superficie de
   regresión — mismo patrón de pasos, con especial cuidado en el eval-set.
3. Considerar, en una fase de override futura, atacar el bug `me plus 3 friends` y otros
   casos donde el regex resuelve MAL (no solo deja hueco) — requiere cambiar el diseño de
   "nunca sobreescribir regex" a "sobreescribir cuando el eval-set demuestre, por campo,
   que el LLM es más fiable", que es una decisión explícita documentada (plan.md §3.2).

---

## 2026-07-21 — Flag de Fase 2 activado en PRE + Fase 3 implementada (dominio ubicación)

**Fase(s) tocada(s)**: Fase 2 (activación en PRE) + Fase 3 (dominio ubicación) — completa.

**Qué se hizo**:
- **Fase 2 activada en PRE**: `LLM_EXTRACTION_CUTOVER_GROUP: "true"` en `dp-pre-bot`
  (`docker-compose.vps.yml`), mismo patrón que el flag de certificación. Solo en PRE;
  default sigue `False` en el resto. Desplegado vía `scripts/deploy_pre_gon.sh`
  (`feature/pruebaGon` → mirror `feature/pre_pruebaGon` → CI deploy-pre).
- **Fase 3 — cutover del dominio ubicación** (`location`/`island`/`hotel`):
  - `settings.llm_extraction_cutover_location` (`src/config.py`, default `False`),
    registrado en `_active_cutover_fields()` con `_LOCATION_CUTOVER_FIELDS = {"location",
    "island", "hotel"}`.
  - **Alcance**: solo los 3 campos de `DetectedIntent` de este dominio. Los interceptores
    de cambio de plan/acompañante (`_apply_group_recomposition` y afines) NO se cortan —
    son estado mid-flow, no extracción de campos; no encajan en el patrón gap-filler.
    Documentado en `plan.md` §4 Fase 3 ("Alcance real") como sub-tarea futura.
  - `location` (enum cartagena|island) es el campo de valor: dirige el routing logístico;
    el LLM lo infiere de barrios/lugares que el regex no enumera. `island`/`hotel` solo
    display/contexto (degradan con gracia), inofensivos como texto libre.
  - Mejora de schema: descripción de `location` enriquecida con barrios de Cartagena y
    zonas insulares.
  - **Fix defensivo del cutover** (hallado por el TDD de esta fase): ahora aplica SOLO
    campos que eran hueco real (`k in relevant_gaps`), no "cualquier campo de un dominio
    activo". Refuerza "nunca sobreescribir regex" en la propia capa de cutover (antes solo
    lo garantizaba `fill_gaps`). Beneficia a las 3 fases.
  - Eval-set 58 → 64 casos (6 adversariales de ubicación, validados contra el regex real:
    Bocagrande/Getsemaní/Manga/Castillogrande/Old Town → cartagena, hotel en Barú →
    island). `island`/`hotel` exactos no se evalúan (texto libre vs slugs; el rigor está
    en `location`).
  - TDD: +5 tests (19 total en `test_llm_extraction_cutover.py`).

**Resultado del eval con LLM real** (gpt-4o, `.env`): **127/128 = 99.2%, 0 huecos**.
`location` **13/13 = 100%**. El único desacuerdo sigue siendo el bug de regex
`me plus 3 friends` (Fase 2, group_size), ajeno a este dominio.

**Verificación en vivo con LLM real** (local, `.env`, flag a mano):
- `"salimos desde bocagrande"`: OFF → `location=None`; ON → `location=cartagena`.
- `"staying in the old town this week"`: OFF → `None`; ON → `location=cartagena`.
- `"estamos hospedados en el hotel Las Islas en Baru"`: OFF → `None`; ON →
  `location=island, island=Barú, hotel=Las Islas`.

**Suite completa**: **1757 passed, 15 skipped, 1 flaky**. El único fallo,
`test_go_pro_itinerary_back_returns_to_go_pro_menu`, **pasa en aislado** (usa LLM real,
~21s) — es no-determinismo del orquestador, no relacionado con este cambio (el cutover
está `False` por defecto en toda la suite). `ruff`/`compileall` limpios.

**Decisiones tomadas y por qué**:
- Se dejó `island`/`hotel` como texto libre (no enum) porque su consumo aguas abajo es
  display/contexto con fallback `.get(slug, raw)` — el routing por service va por
  `state.location`, no por el slug de isla. Cortar `location` (enum) da todo el valor de
  routing; forzar un enum de islas/hoteles sería más frágil por poco beneficio.
- Los interceptores de cambio de plan se dejaron fuera a propósito (ver Alcance) en vez de
  forzarlos al patrón gap-filler, que no les aplica — hacerlo mal reintroduciría el tipo
  de fragilidad que este plan evita.

**Qué quedó a medias / bloqueadores**: nada técnico. Pendiente solo la decisión de
timing de activar `llm_extraction_cutover_location=True` en un entorno real.

**Siguiente paso concreto para quien continúe**:
1. (Opcional) Activar el flag de ubicación en PRE (`LLM_EXTRACTION_CUTOVER_LOCATION:
   "true"` en `docker-compose.vps.yml`) igual que los de Fase 1/2.
2. **Fase 4** — evaluar fusionar la extracción con el orquestador de acciones
   (`orchestrator.py`) en una sola llamada, ahora que 3 dominios de `DetectedIntent` son
   fiables vía LLM. Aquí también encajan los interceptores de cambio de plan que quedaron
   fuera de la Fase 3.
3. Fase de override futura para casos donde el regex resuelve MAL (`me plus 3 friends`),
   cambiando el diseño de "nunca sobreescribir regex" a "override por campo medido con
   datos" (plan.md §3.2).

---

## 2026-07-21 — Fase 3 activada en PRE + Fase 4 (decisión arquitectónica + modelo del extractor)

**Fase(s) tocada(s)**: Fase 3 (activación en PRE) + Fase 4 (decisión + mejora) — completa.

**Qué se hizo**:
- **Fase 3 activada en PRE**: `LLM_EXTRACTION_CUTOVER_LOCATION: "true"` en `dp-pre-bot`
  (`docker-compose.vps.yml`), desplegado. Los 3 flags (certificación, grupo, ubicación)
  quedan encendidos en PRE; default `False` en el resto.
- **Fase 4 — evaluación fusionar-vs-separar, con datos**:
  - **Decisión: mantener SEPARADOS** extractor (`fill_gaps`) y orquestador (`orchestrate`).
    Razones (detalle en `plan.md` §4 Fase 4): son concerns distintos (extracción forzada y
    determinista vs elección de acción con `tool_choice="auto"` no-determinista); el valor
    de la extracción YA llega al orquestador vía el snapshot de estado; la 2ª llamada solo
    ocurre en turnos con hueco (minoría), así que el ahorro de fusionar es pequeño; y
    separados cada uno es mockeable, con su contrato y su kill switch. Fusionar acoplaría
    ambas superficies de regresión y metería la extracción validada en el no-determinismo
    del orquestador — justo lo que este plan evita.
  - **Mejora concreta entregada** (el objetivo de coste/latencia de la fase, sin la fusión
    arriesgada): `settings.extraction_model` (default `gpt-4o-mini`), separado de
    `settings.openai_model` (gpt-4o, que sigue en el orquestador). El extractor es una
    tarea estrecha de tool-call forzado donde un modelo más pequeño basta.
  - **Medición** (eval-set, 64 casos, LLM real): **gpt-4o-mini = 98.4%** vs
    **gpt-4o = 99.2%**. La única diferencia es **1 `missed` de más** (se abstiene en el
    caso de conteo implícito `my daughter is 9 and my son is 12...` en vez de rellenar
    mal), **0 `disagree` de más**. Modo de fallo **seguro**: degrada a "regex-only /
    preguntar", nunca a un valor equivocado. Sigue ≥98% (umbral de cutover).
  - **Latencia** (micro-benchmark local, 4 llamadas/modelo, mensaje con hueco):
    gpt-4o avg **6254ms** (min 3484 / max 13864), gpt-4o-mini avg **4598ms**
    (min 3954 / max 6192) — ~26% más rápido de media y ~55% menos latencia de cola, más
    consistente. (Latencias absolutas altas por red local→OpenAI; el ratio se mantiene en
    PRE.) Coste: ~15-30x más barato por llamada.
  - TDD: `test_fill_gaps_uses_extraction_model_not_orchestrator_model` en
    `tests/test_llm_extractor.py` (cliente que captura el kwarg `model` y verifica que es
    `settings.extraction_model`).
- **Interceptores de cambio de plan/acompañante**: confirmados como trabajo separado del
  patrón gap-filler (estado mid-flow, no extracción de campos). No se abordan en Fase 4;
  candidatos a fase propia si el tráfico real de PRE muestra que siguen dando fragilidad.

**Decisiones tomadas y por qué**:
- Se eligió `gpt-4o-mini` como default del extractor (no solo configurable) porque el dato
  lo respalda: mismo conjunto de desacuerdos que gpt-4o (solo el bug de regex), y su única
  regresión es una abstención segura. El coste/latencia bajan de forma notable. Revertible
  con una línea si el tráfico real desmiente el eval.
- No se implementó ningún prototipo de fusión: habría sido código de usar y tirar que
  contradice la decisión tomada con datos. La Fase 4 del plan pedía *evaluar*, y la
  evaluación concluyó en "separar" + una mejora medible.

**Qué quedó a medias / bloqueadores**: nada. Fases 0-4 completas.

**Siguiente paso concreto para quien continúe**:
1. (Opcional) Activar los flags en PRE ya está hecho para los 3 dominios; falta solo la
   decisión de producción (PRO no está desplegado hoy).
2. **Fase 5 (limpieza/consolidación)**: cuando los 3 dominios lleven un periodo estable en
   PRE con tráfico real (revisar logs `[EXTRACT][CUTOVER]`), eliminar el código regex ya
   muerto que el LLM haya reemplazado de facto, y cerrar el plan.
3. Fase de override futura (`me plus 3 friends` y casos donde el regex resuelve MAL) +
   los interceptores de cambio de plan mid-flow, si el tráfico real lo justifica.

---

## 2026-07-21 — Revisión exhaustiva post-Fases 0-4

**Fase(s) tocada(s)**: ninguna (revisión, sin cambio de comportamiento). Se paró en
Fase 4 (los 4 flags en PRE recogiendo datos) por decisión del owner, y se pidió una
revisión de todo para ver qué mejorar.

**Qué se hizo**: revisión crítica del pipeline completo → `docs/robustness/review-2026-07-21.md`
con 8 hallazgos priorizados (evidencia archivo/línea + acción propuesta). Se añadieron
3 fases nuevas al checklist de `plan.md` (Fases 6-8) y 2 tareas transversales. Resumen:
- **H1 (alto)**: no hay bucle de datos reales — shadow-mode apagado en todos los entornos,
  los logs `[EXTRACT][CUTOVER]` de PRE no se revisan ni realimentan el eval-set. El
  eval-set son 64 casos sintéticos. → Fase 6 (nueva, prioridad alta).
- **H2 (alto)**: la suite es lenta (~5-7 min) y flaky porque `conftest.py` mockea
  `orchestrate` pero NO `rag_answer` — los tests que van a `answer_question` llaman al RAG
  real (no determinista). → Tarea transversal T1 (mockear RAG + marcador `live`).
- **H3-H5 (medio)**: cobertura desigual del eval-set (hotel 1, is_colombian 1, island 2…);
  cutover cableado en un solo entry-point (3 sitios llaman `detect`, solo 1 tiene cutover);
  campos extraíbles sin dominio (`is_colombian`/`duration`/`last_dive`…). → Fase 8 + T2.
- **H6-H8 (bajo/conocido)**: bug regex `me plus 3 friends` (→ Fase 7 override); interceptores
  plan-change mid-flow; observabilidad solo log-line (→ contador en Fase 6).

**Decisiones tomadas y por qué**: no se implementó ninguna de las mejoras en esta sesión —
el owner pidió revisar y documentar, no ejecutar. Se dejaron como fases/tareas priorizadas
para decidir. La Fase 5 (limpieza) se marca **bloqueada por la Fase 6**: sin datos reales no
se sabe qué regex está de verdad muerto.

**Qué quedó a medias / bloqueadores**: nada en curso. Los 4 flags siguen en PRE recogiendo
datos (aunque sin bucle de revisión aún — ese es justo el H1).

**Siguiente paso concreto para quien continúe**: leer `review-2026-07-21.md` y decidir
prioridad. La recomendación es empezar por la **Fase 6** (bucle de datos) porque desbloquea
la limpieza (Fase 5) y da fundamento real a las Fases 7-8; y la tarea **T1** (mockear RAG)
porque hace la suite rápida y determinista, que beneficia a todo el desarrollo futuro.

---

## 2026-07-21 — T1 (mock RAG), Fase 6 tooling, y Fase 8 (dominio logística)

**Fase(s) tocada(s)**: T1 (transversal), Fase 6 (tooling), Fase 8 (dominio) — de la
revisión `review-2026-07-21.md`.

**Qué se hizo**:
- **T1 (H2) — mock RAG por defecto**: `conftest.py` mockea `supervisor.rag_answer`
  (autouse `_rag_answers_offline`), con exclusión `_RAG_LIVE_MODULES` (`test_rag_safety`,
  que llama a `rag_agent` directo) y opt-out `@pytest.mark.live` (registrado en
  `pyproject.toml`). **Medido: suite 319s → 153s (~2.1x), 0 fallos**, el flaky
  `test_go_pro_itinerary_back` ahora es determinista. Cobertura del RAG real intacta.
- **Fase 6 (H1/H8) — tooling del bucle de datos**: `scripts/harvest_cutover_logs.py` parsea
  las líneas `[EXTRACT][CUTOVER]`/`[EXTRACT][SHADOW]` de PRE → candidatos deduplicados para
  el eval-set (con el patch del LLM como `expected` de partida, marcado SIN VALIDAR) +
  `--summary` (contador por campo/dominio, H8). Maneja dicts anidados y líneas truncadas.
  5 tests. **Pendiente**: correrlo contra `docker logs dp-pre-bot` (necesita acceso a PRE)
  y curar candidatos. Fase 6 marcada `[~]`.
- **Fase 8 (H5) — dominio nacionalidad/logística**: `settings.llm_extraction_cutover_logistics`
  (default `False`) + `_LOGISTICS_CUTOVER_FIELDS = {is_colombian, duration,
  last_dive_over_2_years}` en `_active_cutover_fields()`. Eval-set 64→71 (7 adversariales).
  TDD +4 (23 cutover tests). **Eval con LLM real: dominio al 100%** (is_colombian 4/4,
  duration 5/5, last_dive 5/5). Verificado en vivo (soy paisa→colombiano, toda la
  semana→multi_day, hace 4 años→>2y).
  - **Parte 2 (H4, cablear entry-points) DEFERIDA**: `_apply_group_recomposition` y
    `_maybe_answer_age_eligibility` son short-circuits pre-dispatch; cablear el cutover ahí
    duplicaría la llamada LLM en fall-through. El fix correcto es un cutover único temprano
    en `_route_message_inner` (refactor de dispatch), documentado con `NOTE` en ambas
    funciones y como trabajo futuro.

**Decisiones tomadas y por qué**:
- **Varianza de gpt-4o-mini observada**: el overall del eval bajó a 97.8% (vs 99.2% con
  gpt-4o / 98.4% mini en Fase 4). Los 3 no-acuerdos: el bug de regex `me plus 3 friends`
  (1 disagree) + 2 `missed` de mini en casos límite de group_size/ages. Notable: `ages`
  dio 4/5 aquí vs 5/5 en la corrida mini de Fase 4 sobre el MISMO caso → es **varianza
  run-to-run de gpt-4o-mini** (temp 0 no es 100% determinista en casos límite). Es
  consistente con la decisión de Fase 4: el modo de fallo de mini es **seguro** (abstención
  → el bot pregunta, nunca rellena mal), y el ahorro coste/latencia lo justifica. Si el
  equipo quiere máxima consistencia en casos límite, `extraction_model="gpt-4o"` es una
  línea. El dominio nuevo (logística) no se ve afectado: 100%.
- No se forzó la Parte 2 (cablear entry-points) para no introducir una regresión de doble
  llamada — se documentó el porqué y el fix correcto.

**Qué quedó a medias / bloqueadores**: Fase 6 necesita una corrida real contra los logs de
PRE (acceso al VPS). Nada más pendiente.

**Siguiente paso concreto para quien continúe**:
1. Correr `scripts/harvest_cutover_logs.py` contra `docker logs dp-pre-bot` y curar
   candidatos → primer crecimiento real del eval-set (cierra el H1).
2. (Opcional) activar `llm_extraction_cutover_logistics=True` en PRE.
3. Fase 7 (override) o el refactor de cutover-único-temprano (Parte 2 de Fase 8) cuando el
   tráfico real lo priorice.

---

## 2026-07-21 — Merge de Gonzalo + batería de 10 conversaciones para validar el H1/Fase 6 + 3 bugs reales encontrados y corregidos

**Fase(s) tocada(s)**: merge de Fases 2-4/6/8 + T1 (trabajo de Gonzalo, `feature/pruebaGon`), más 3 fixes nuevos encontrados validando el bucle de datos.

**Qué se hizo**:
- **Merge**: `git merge --ff-only origin/feature/pruebaGon` — fast-forward limpio (nuestra rama era ancestro exacto de la suya, cero divergencia). Trae Fases 2-4, 6, 8, la revisión `review-2026-07-21.md`, y T1 (mock RAG). Suite tras el merge: **1768 passed, 0 fallos** (el mock de RAG eliminó los 8 fallos crónicos).
- **Batería de 10 conversaciones reales (5 ES + 5 EN)** contra PRE vía SSH (con permiso explícito del usuario para usar la API key), buscando fallos y probando reservas normales, para intentar disparar el H1 (bucle de datos reales) y validar `scripts/harvest_cutover_logs.py` con tráfico generado.
- **Hallazgo operativo importante**: las conversaciones corridas como `docker exec python3 script.py` (patrón de `live_battery_driver.py` usado toda la sesión) **NO llegan a `docker logs dp-pre-bot`** — ese log solo captura el proceso real del servidor (uvicorn), no procesos `exec` separados. Tuve que forzar `logging.basicConfig` en el script de prueba para generar líneas `[EXTRACT][CUTOVER]` reales y validar el parseo del harvest. Para que el harvest funcione con tráfico real de verdad, hace falta tráfico que pase por el servidor real (Chatwoot/webhook), no scripts sueltos.
- **Bug real de negocio #1** (el más importante): "somos 5 amigos, 3 certificados y 2 sin certificar, queremos un paquete de varios días" caía a RAG, que inventó que los no certificados "deben hacer primero el curso Open Water" — falso. El usuario confirmó la regla correcta: minicurso SIEMPRE disponible; Open Water TAMBIÉN si el plan es de varios días (regla que YA estaba bien implementada en `decision_tree._maybe_start_pending_beginner`/`_cert_subgroup_is_multi_day`, solo que este mensaje nunca llegaba ahí). Causa raíz: `_should_enter_mixed_flow` no tenía el fallback determinista que sí tienen `_should_skip_to_certified_flow`/`_should_ask_certification` para cuando el orquestador clasifica el mensaje como `answer_question` — con `is_certified` agregado en `False` (grupo mixto: no todos certificados), ninguno de esos 2 fallbacks aplica (exigen `True` o `None`), así que el mixed flow nunca se alcanzaba. TDD: reproducido en rojo (`test_mixed_group_split_statement_enters_guided_flow_not_rag`), arreglado añadiendo el fallback que faltaba en `_dispatch_conversation_agent` (mismo patrón, mismo sitio, verificado primero por prioridad como ya hace `_route_detected_intent` internamente). 2 tests más (`test_non_cert_companion_single_day_offers_minicourse_not_open_water`/`..._multi_day_offers_minicourse_and_open_water`) fijan la regla de negocio directamente contra `_maybe_start_pending_beginner` (no tenía cobertura de test propia pese a ya estar bien implementada).
- **Bug #2 (harvest)**: `DOMAIN_FIELDS` en `scripts/harvest_cutover_logs.py` no incluía el dominio `logistics` (Fase 8: `is_colombian`/`duration`/`last_dive_over_2_years`) — esos campos caían en el cajón `"other"` del `--summary`. TDD: `test_summary_counts_logistics_domain_not_other`, arreglado añadiendo la entrada que faltaba.
- **Bug #3 (harvest)**: los logs `[EXTRACT][CUTOVER]`/`[EXTRACT][SHADOW]` truncaban el mensaje a 60 caracteres (`message[:60]!r}`) — los candidatos cosechados por el harvest perdían el final de mensajes reales, justo lo opuesto de lo que la Fase 6 necesita. Nuevo helper `_log_safe_message()` (límite 500, marca `…[truncated]` si aún se corta). TDD: `test_cutover_log_line_does_not_truncate_the_message`/`test_shadow_log_line_does_not_truncate_the_message` (con `caplog`).
- Suite completa tras los 3 fixes: **1774 passed**, 15 skipped. `ruff`/`compileall` limpios en todos los archivos tocados.

**Decisiones tomadas y por qué**:
- El fallback de `_should_enter_mixed_flow` se colocó ANTES del de `_should_skip_to_certified_flow` en `_dispatch_conversation_agent`, reflejando el mismo orden de prioridad que `_route_detected_intent` ya usa internamente ("PRIMERO: verificar si es grupo mixto").
- No se tocó `_maybe_start_pending_beginner`/`_cert_subgroup_is_multi_day` — la lógica de negocio ya era correcta, el problema era puramente de enrutamiento (el mensaje nunca llegaba a ese código).
- El límite de truncado se subió a 500 (no se eliminó del todo) para seguir teniendo una cota ante mensajes patológicamente largos, con marcador explícito de truncado en vez de cortar en silencio.

**Qué quedó a medias / bloqueadores**: el H1 (bucle de datos reales) sigue sin cerrarse del todo — el harvest ya está validado y sin bugs conocidos, pero todavía no se ha corrido contra tráfico 100% real de PRE (solo contra tráfico sintético generado a mano con logging forzado). Falta tráfico real vía Chatwoot para la validación definitiva.

**Siguiente paso concreto para quien continúe**:
1. Cuando haya tráfico real de clientes/pruebas por Chatwoot en PRE, correr
   `ssh vps "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs --summary`
   y luego sin `--summary` para generar candidatos reales — ahora sin los 2 bugs de arriba.
2. Considerar si el hallazgo de "mensajes de prueba no llegan a docker logs" cambia cómo el equipo genera tráfico de prueba para la Fase 6 (quizás documentar en `docs/robustness/plan.md` o en el propio harvest script).
3. Desplegar estos 3 fixes a PRE y verificar en vivo el escenario del grupo mixto (mismo mensaje que disparó el bug).

---

## 2026-07-22 — Strict schema evaluado y descartado con datos + el eval-set aprende a cazar misfills

**Fase(s) tocada(s)**: extractor (transversal — lo usa tanto el cutover de robustez
como el núcleo conversacional nuevo de `docs/archive/conversational-refactor-plan.md`).

**Qué se hizo**:
- Ejecutando la Fase 0 del plan conversacional (que pedía "confirmar json_schema
  strict"), se migró `_TOOL` a strict function-calling y, probando el guion de Rocío
  en vivo con el núcleo nuevo, salió un **misfill real**: "hola soy rocio, tengo el
  open water y quiero hacer buceo" (sin NINGUNA señal de lugar) recibió
  `location='cartagena'` y `duration='single_day'` inventados — la sede del negocio
  en el prompt contaminaba, y el modo strict (cada clave obligatoria, decidir
  valor-vs-null) empujaba a rellenar. Reproducido con gpt-4o-mini Y gpt-4o.
- **El eval no podía ver misfills**: `compare_with_ground_truth` solo comparaba los
  campos presentes en `expected`. Convención nueva: `expected` con valor `null` =
  "el extractor DEBE abstenerse" (ausencia = acuerdo; relleno = desacuerdo). 2 casos
  negativos nuevos en el eval-set (73 total): el mensaje real de Rocío (ES) y un
  espejo EN.
- Medición A/B con los negativos: **strict = misfill en ambos casos y ambos
  modelos; no-strict (omitir clave = abstenerse) = abstención limpia en ambos**. Se
  revirtió a no-strict conservando el prompt reforzado ("que el negocio opere en
  Cartagena NO es señal de la ubicación del cliente; abstenerse siempre es mejor
  que rellenar mal").
- **Eval final: 143/145 = 98.6%, CERO misfills** (los 2 no-acuerdos: el bug regex
  documentado `me plus 3 friends` + 1 missed seguro de `is_colombian`). Umbral ≥98%
  se mantiene.

**Decisiones tomadas y por qué**: el modo de fallo peligroso del extractor es el
misfill, no el JSON malformado (ese ya degrada seguro a `{}` → regex-only). Strict
compra forma-siempre-válida al precio de inducir el fallo peligroso — mala compra,
medida con datos, misma metodología que la decisión de Fase 4 (separar vs fusionar).
Documentado también en un comentario junto a `_TOOL` para que nadie lo "re-mejore" a
strict sin leer esto.

**Qué quedó a medias / bloqueadores**: nada de esta pieza. (El H1/Fase 6 sigue igual
que el bloque anterior: falta tráfico real vía Chatwoot.)

**Siguiente paso concreto para quien continúe**: si algún día se reintenta strict
(p. ej. por un modelo nuevo), correr PRIMERO el eval-set con los casos `neg-*` — si
hay un solo misfill, no hay debate. Y al añadir casos negativos nuevos, validar
antes que el regex real deja esos campos en None (misma lección de proceso de
siempre: medir, no asumir).

---

## 2026-07-22 — Fase 6 desbloqueada: el núcleo vuelve a alimentar el harvest (Fix A+B del handoff conversacional)

**Fase(s) tocada(s)**: Fase 6 (bucle de datos reales) — tooling desbloqueado.

**Qué se hizo**: los 2 fixes que dejó especificados el handoff conversacional
(`docs/archive/conversational-refactor-handoff.md` §"Sesión 2026-07-22 (tarde)"):
- **Fix A**: `conversational_core._understand` ahora loguea `[EXTRACT][CUTOVER]
  applied={patch} msg=...` (con valores y mensaje completo vía
  `supervisor._log_safe_message`) en vez del viejo `[CORE] gap-fill
  applied=[nombres]`. Con el núcleo encendido en PRE, el harvest volvía 0
  candidatos porque el formato no coincidía; ahora `scripts/harvest_cutover_logs.py`
  funciona sin tocarlo (test de integración que parsea los logs reales del bucle).
- **Fix B**: `_relevant_gaps(state, intent, message)` calcula los huecos contra el
  ESTADO de la conversación (no el intent del turno, casi siempre vacío) y filtra
  campos fuera de contexto; `fill_gaps` ganó `only_fields` (opcional,
  backwards-compatible — el cutover legacy no cambia). Sin huecos relevantes no se
  llama al LLM. Menos tokens por turno y menos superficie de misfill.

**Verificación en vivo** (LLM real, flag on, local): conversación de 4 turnos con
frases fuera del regex → reserva cerrada correctamente, y el harvester sobre esos
logs: **4 records, 4 candidatos con valores** (`bocagrande→location=cartagena`,
`nos sumergimos el mes pasado→last_dive_over_2_years=False`,
`venimos de madrid→is_colombian=False`) + `--summary` clasificando por dominio
(certification/logistics/location). Antes de los fixes: 0 candidatos con los
mismos mensajes.

**Qué quedó a medias / bloqueadores**: el paso operativo de la Fase 6 — acumular
tráfico real en PRE y correr
`ssh ... "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs`,
curar candidatos (validando cada `expected` contra el pipeline real) y alimentar
el eval-set. La Fase 5 (limpieza) sigue detrás de eso.

**Siguiente paso concreto para quien continúe**: desplegar a PRE (hecho en esta
sesión), generar/esperar tráfico real, y correr el harvest. Con los primeros
candidatos curados en el eval-set, la Fase 6 se cierra.

---

## 2026-07-22 — Fase 6: primer ciclo completo del bucle de datos (batería → harvest → curación → eval)

**Fase(s) tocada(s)**: Fase 6 — primer ciclo del bucle ejecutado de punta a punta.

**Qué se hizo**: sin acceso SSH al VPS desde esta sesión (denegado por política del
entorno local), se ejecutó la batería de la Fase 6
(`docs/robustness/live-test-battery-fase6.md`, categorías A-D+F = 30 casos de entrada)
**localmente contra el pipeline real** (núcleo conversacional ON, LLM real, mismo código
que PRE tras `2c8e195`), capturando los logs igual que `docker logs` y pasándolos por
`scripts/harvest_cutover_logs.py`:

- Batería: **30/30 sin excepciones**. Harvest: **18 records / 18 candidatos** con
  valores completos; `--summary`: group 7, certification 6, location 6, logistics 3.
- **Curación** (regla del plan: validar contra el pipeline real, no a ojo): **10 casos
  añadidos** al eval-set (ids `hv-*`; 73 → **83 casos**), 4 descartados por duplicado o
  casi-duplicado del eval-set, resto sin señal nueva. En 2 casos el `expected` se dejó
  deliberadamente conservador (sin `group_size` en "…con nosotros": fijarlo consagraría
  una adivinanza; sin `activity` en el mixto con alloc completo: discutible y el carrito
  se construye del alloc).
- **Eval con LLM real sobre los 83**: **167/169 = 98.8%**, con los 10 `hv-*` en verde.
  Los 2 no-acuerdos: el bug de regex documentado (`me plus 3 friends`, disagree) y 1
  abstención segura en un caso de `is_colombian` (missed — variabilidad run-to-run del
  mini ya documentada en Fase 8; nunca misfill).
- **2 bugs de regex NUEVOS encontrados por la batería** (anotados en el Registro de
  hallazgos de `live-test-battery-fase6.md`; candidatos a la Fase 7):
  1. "hace como 3 años que no buceo" / "haven't dived in like 4 years" → el regex de
     edades captura `ages=[3]`/`[4]` (los años del "hace X años" como edad de un niño
     fantasma; contaminaría el split infantil si hubiera minicurso en el carrito).
  2. "i already have my open water card, want to do more dives" →
     `activity=padi_open_water` (lo clasifica como CURSO cuando ya lo tiene y quiere
     bucear). Como `me plus 3 friends`: el regex resuelve MAL, el gap-filler no puede
     corregirlo por diseño.
  3. B3 confirmado otra vez ("me plus 3 friends want to snorkel" → qty 3, debería 4).

**Decisiones tomadas y por qué**: correr la batería en local NO sustituye el tráfico
por el widget de Chatwoot (rate-limits/webhooks del canal quedan sin cubrir), pero sí
cumple el objetivo de datos de la Fase 6 (mismos mensajes → misma extracción → mismos
candidatos) y valida el bucle entero tras el Fix A. Las categorías E y G no se corrieron:
multi-turno "fácil" que el regex resuelve (no generan gap-fills).

**Qué quedó a medias / bloqueadores**: la corrida por el widget de PRE (canal real) y el
harvest vía SSH (`ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker logs dp-pre-bot
2>&1" | python -m scripts.harvest_cutover_logs`) siguen pendientes para quien tenga la
clave — el tooling ya está probado de punta a punta. La Fase 6 queda **operativa**
(bucle demostrado); se puede dar por cerrada cuando el primer lote del canal real pase
por el mismo ciclo.

**Siguiente paso concreto para quien continúe**:
1. Lanzar la batería por el widget de PRE (o esperar tráfico real del owner) y correr el
   harvest por SSH; curar con el mismo criterio (los `hv-*` sirven de plantilla).
2. **Fase 7**: ya hay 3 bugs de regex reales esperándola (me-plus-N, hace-X-años→ages,
   already-have-card→curso). Es el siguiente trabajo técnico con más valor.
3. Fase 5 (limpieza) cuando la 6 lleve un par de lotes reales; Fase 4 del refactor
   conversacional cuando el owner dé por medida la operación en PRE.

---

## 2026-07-22 — Fase 6 confirmada en producción + hallazgo sobre `only_fields` en el harvest

**Fase(s) tocada(s)**: Fase 6 (paso operativo: harvest contra tráfico REAL de PRE).

**Qué se hizo**:
- Tras el merge de los Fix A/B de Gonzalo (`2c8e195`) y el redeploy a PRE, se tiró de
  `docker logs dp-pre-bot` (tráfico real por el widget, no sintético) y se corrió
  `scripts/harvest_cutover_logs.py` contra esos logs. **Resultado: 2 records, 2
  candidatos con valores** — el Fix A queda confirmado funcionando en PRODUCCIÓN, no
  solo en la verificación local de Gonzalo. Antes del fix esto daba 0 (documentado en
  el bloque anterior de este log).
- Candidato 1 validado contra el pipeline real (regex solo → `is_certified=None`;
  `fill_gaps` sin historial → `is_certified=True`, estable): "tengo el AOWD" (Advanced
  Open Water Diver) es un acrónimo de certificación que el regex no reconoce. Añadido
  al eval-set como `hv-aowd-acronym` (83→84).
- Candidato 2 ("1 pero viene un amigo que quiere hacer buceo, no es certificado" →
  `group_allocation={certified_diving:1, minicourse:1}`) se descartó de fijar en el
  eval-set — ver hallazgo de proceso abajo.

**Hallazgo de proceso — el harvest y el eval-set NO conocen `only_fields`**:
El Fix B de Gonzalo (`_relevant_gaps` en `conversational_core.py`) llama a
`fill_gaps(..., only_fields=[...])`, restringiendo qué campos se le piden al LLM según
lo que el ESTADO de la conversación ya sabe (no solo el mensaje suelto). Esto es
correcto y deseado (menos tokens, menos superficie de misfill) — pero significa que
**el patch logueado en producción depende del contexto de la conversación, no solo del
mensaje**. Al intentar reproducir el candidato 2 con la llamada "pelada" del eval-set
(`fill_gaps(mensaje, intent)`, sin `only_fields` ni el estado real), el resultado fue
DISTINTO: `group_size=2` en vez de `group_allocation={...}`. No es un misfill ni un bug
— es que el eval-set actual no simula el contexto reducido que ve el núcleo en
producción, así que un candidato harvestado con `only_fields` activo no siempre se
puede fijar como caso de mensaje-suelto sin más.

**Decisiones tomadas y por qué**: mejor un candidato descartado que un `expected`
fijado que no se sostiene contra el pipeline real — misma regla del plan de siempre
(medir, no asumir) aplicada también a los candidatos que sí llegan del harvest.

**Qué quedó a medias / bloqueadores**: el candidato 2 queda documentado aquí pero SIN
fijar en el eval-set. Si se quiere aprovechar, hace falta o (a) extender el eval-set
runner para que sepa simular `only_fields` a partir de un estado dado, o (b) reformular
el caso como un test de integración del núcleo completo (con estado previo), no como un
caso de extracción de mensaje suelto.

**Siguiente paso concreto para quien continúe**:
1. Seguir acumulando tráfico real por el widget de PRE y repitiendo este harvest
   periódicamente — ahora funciona de punta a punta.
2. Decidir si vale la pena extender el eval-set/runner para casos con `only_fields`
   (ver hallazgo de arriba) antes de que se acumulen más candidatos de ese tipo.
3. La Fase 7 se atacó justo después (bloque siguiente): los 3 bugs de regex reales.
4. Fase 5 (limpieza de regex muerto) sigue detrás de la 6 y la 7.
5. Fase 4 del refactor conversacional (retirar el árbol `MIXED_*`) es el único punto
   pendiente del plan de Álvaro — su precondición (medir en PRE) ya se está cumpliendo.

---

> Nota de merge: los dos bloques siguientes (Gadea y Gonzalo) documentan un trabajo
> paralelo e independiente sobre LOS MISMOS 3 bugs de regex — cada uno los encontró y
> arregló sin saber del otro. El código final que quedó en el repo es la versión de
> Gonzalo (más completa: cubre más frases, "we" además de "i", y corrige de paso un
> `expected` mal etiquetado del eval-set que el bloque de Gadea no detectó). Se dejan
> ambos bloques por transparencia del proceso, no como doble trabajo pendiente.

## 2026-07-22 (noche) — Decisión sobre el hallazgo `only_fields` + 3 bugs de regex arreglados (Gadea, superseded por el bloque de Gonzalo abajo)

**Fase(s) tocada(s)**: Fase 6 (decisión de proceso pendiente) + Fase 7 (candidatos cerrados).

**Decisión sobre `only_fields` y el eval-set**: se opta por la **opción (b)** del
hallazgo del bloque anterior — los candidatos harvestados que dependen de `only_fields`
(es decir, cuyo patch real en producción depende del ESTADO de la conversación, no solo
del mensaje suelto) **no se fuerzan** al formato mensaje-suelto del eval-set. Se tratan
en su lugar como tests de integración del núcleo completo con estado previo — patrón ya
establecido en `tests/test_conversational_core.py` (los tests multi-turno de Sofía/
Rocío ya construyen un `ConversationState` con historia real). Razón: extender el
runner del eval-set para simular `only_fields`/estado parcial añadiría complejidad a
una herramienta pensada para extracción de mensaje-suelto; el patrón de integración ya
existe y es más honesto con lo que realmente se está probando.

**3 bugs de regex arreglados** (los mismos 3 que motivaban la Fase 7, ver
`live-test-battery-fase6.md` y `plan.md` §Fase 7): se investigó primero si eran
arreglables en el propio patrón antes de complicar con un override por LLM, y los 3
lo eran — bugs de adyacencia/enumeración puntuales, no casos de fiabilidad sistemática
del LLM sobre el regex:
- `"me plus 3 friends"` → `group_size=3` (perdía al hablante) → ahora `4`.
- `"hace como 3 años que no buceo"` → `ages=[3]` (niño fantasma) + `last_dive_over_2_years`
  sin resolver → guarda de 8 caracteres cambiada a lookback por palabras (2 palabras).
- `"i already have my open water card"` → clasificado como querer tomar el curso →
  `_HOLDS_CERT_RE` ahora admite "i already have".

6 tests de regresión en `tests/test_intent_detector.py`. Suite: 1838 passed. Verificado
en vivo con LLM real (flag off, árbol legacy) contra los 3 mensajes originales de la
batería.

**Decisiones tomadas y por qué**: la Fase 7 (override por LLM) es más cara y más
arriesgada (introduce no-determinismo donde antes había un bug determinista) que
arreglar el regex cuando el bug es puntual — misma disciplina de "medir antes de
complicar" del resto del plan.

**Qué quedó a medias / bloqueadores**: ninguno de esta pieza. La Fase 7 queda sin
justificación pendiente (ver `plan.md`); se retoma solo si aparece un caso nuevo no
arreglable en el regex.

**Siguiente paso concreto para quien continúe**:
1. Si se harvestan más candidatos `only_fields`-dependientes, escribirlos como tests de
   `test_conversational_core.py` (estado previo real), no como entradas del eval-set.
2. Fase 5 (limpieza de regex muerto) sigue detrás de la 6 — no hay más bloqueadores
   conocidos para empezarla cuando el equipo decida el periodo de estabilidad.
3. Fase 4 del refactor conversacional (retirar el árbol `MIXED_*`) es el único punto
   pendiente del plan de Álvaro.

---

## 2026-07-22 — Fase 7: arreglados 3 bugs de regex hallados por las baterías (Gonzalo — versión que quedó en el código)

**Fase(s) tocada(s)**: Fase 7 (los casos donde el regex resuelve MAL, no solo deja hueco).

**Qué se hizo**: las baterías de Fase 6 dejaron 3 bugs reales del regex documentados en
`live-test-battery-fase6.md`. La Fase 7 estaba planteada como "override selectivo por
campo vía LLM", pero los 3 eran **patrones concretos y deterministas** → se decidió, con
ese dato, **arreglar el REGEX** en vez de meter un override LLM (que habría cambiado
"bugs reproducibles" por "intermitentes", justo lo que el plan evita, §1). TDD estricto,
+11 tests en `tests/test_intent_robustness.py`:

1. **`me plus N friends` / `N amigos y yo` / `voy con N amigos`** → el hablante es
   ADICIONAL al conteo de acompañantes: `group_size = N+1`. Nuevo patrón `me/yo +N
   companion-noun` (y variantes) que corre ANTES del genérico "N friends" (que matcheaba
   primero y daba N). Con guardas: un total explícito ("somos 4") no se incrementa.
2. **`hace X años` / `in like X years` / `X years ago` / `llevo X años sin bucear`** ya
   NO se capturan como edad. La ventana de 8 chars antes del número cortaba el "hace" de
   "hace como 3 años"; ampliada a 20 chars + más palabras-guarda (desde/llevo/in/for/
   like/since) + guarda por lo que sigue (ago/sin bucear). Los años de la última
   inmersión se colaban como edad de un niño fantasma que habría contaminado el split
   infantil del checkout.
3. **`i already have my open water card`** → certificado, no curso. El adverbio entre
   "i/we" y "have" rompía `_HOLDS_CERT_RE`, así que se clasificaba como QUERER el curso
   Open Water en vez de TENERLO. Nueva alternativa que admite already/now/both + have/got.

También se **corrigió un `expected` mal etiquetado del eval-set**: `lastdive-en`
("my last dive was 1 year ago") tenía `ages:[1]` — el mismo age fantasma del bug #2,
heredado del "regex ground truth" viejo. Quitado (la lección de proceso al revés: el
eval-set también hay que corregirlo cuando enshrina un bug).

**Resultado**: suite completa **1849 passed, 15 skipped, 0 fallos** (código compartido con
el árbol legacy — sin regresiones). Eval-set (83 casos): **group_size 100%, 0 disagree**
(el `me plus 3 friends` que era el único disagree histórico ahora acierta). Los missed que
quedan son abstenciones seguras del mini (is_colombian de "im from the states", y la edad
en palabra "ocho" que resuelve el LLM), nunca misfills.

**Decisiones tomadas y por qué**: regex-fix en vez de LLM-override para estos 3 porque son
deterministas y el regex es el camino primario del plan; un override LLM se reserva para un
caso futuro donde el LLM demuestre (con eval) ser más fiable que un regex que NO se puede
arreglar limpio. El bug #2 se arregló ensanchando la guarda existente, no añadiendo una
regla nueva frágil.

**Qué quedó a medias / bloqueadores**: nada de la Fase 7. Quedan Fase 5 (limpieza, tras un
par de lotes reales de la Fase 6) y Fase 4 del refactor conversacional (retirada del árbol,
cuando el owner dé por medida la operación en PRE).

**Siguiente paso concreto para quien continúe**: Fase 5 o Fase 4 según prioridad del
equipo; ambas requieren primero acumular tráfico real en PRE (Fase 6 por el canal Chatwoot).

## 2026-09-03 — Fase 9: veto LLM de `activity` para mensajes ambiguos (Gadea, agent-arch)

**Origen**: conversación real ("purple-sun-590") pidió explícitamente "sacarme el open
water" pero en el mismo mensaje añadió "nunca he buceado" — `_detect_activity`
(`intent_detector.py`) resuelve por cadena `if/elif` (primera categoría que matchea
gana) y `minicourse_patterns` se comprueba ANTES que `padi_course_patterns`, así que ganó
minicurso. Resultado real: el curso Open Water — con precio ($693/2.450.000 COP) y link de
reserva directa ya en el catálogo — nunca mostró precio ni link en toda la conversación.

**Por qué el cutover por dominio existente no lo salvó — corrección a una explicación previa
que le di al usuario en el chat**: dije que el cutover de certificación (activo en PRE,
`activity` en su dominio) "corrió pero no aplicó por su regla de nunca sobreescribir".
Investigando para implementar el fix, se confirmó algo más grave: `_maybe_apply_llm_
extraction_cutover`/`_maybe_log_llm_extraction_shadow` (`supervisor.py`) son **código
muerto** — solo los llaman sus propios tests, NUNCA el flujo real de turno
(`conversational_core._understand`, el único call site vivo de `IntentDetector.detect()`
+ `fill_gaps` para el flujo de reserva). Los 4 flags `LLM_EXTRACTION_CUTOVER_*` en `true`
en `docker-compose.vps.yml` son inertes en producción — no es que el mecanismo corriera y
se abstuviera, es que nunca se ejecuta en absoluto (ya documentado antes como hallazgo
separado — "Cutover de extracción muerto" — pero no lo até a este caso hasta ahora).

**Fix implementado** (Opción B, decidida con el usuario tras descartar explícitamente un
parche puntual de reordenar regex): nueva función pura `matched_activity_categories()`
(`intent_detector.py`, reusa las 5 listas de patrones de actividad elevadas a constantes
de módulo, sin cambiar contenido/orden) detecta cuándo un mensaje dispara 2+ categorías a
la vez (ambigüedad real, barata de calcular). Nueva `verify_activity()`
(`llm_extractor.py`, reusa `EXTRACTION_TOOL`/`settings.extraction_model`) pregunta al LLM
de forma independiente SOLO en esos casos, y devuelve su respuesta solo si discrepa. Nueva
`supervisor._maybe_veto_activity_via_llm()` — a diferencia del cutover muerto de arriba,
esta SÍ puede corregir un `activity` ya resuelto por el regex, gateada por 2 flags nuevos
(`llm_activity_veto_shadow_mode`/`llm_activity_veto_cutover`, ambos off por defecto), y
está cableada en el ÚNICO call site real y vivo (`conversational_core._understand`, antes
de `_apply_detected_intent`) — no en el bloque muerto.

**Medición real, antes/después, mismo arnés existente** (`scripts/run_extraction_eval.py`
+ `docs/robustness/eval-set.json`, 9 casos nuevos etiquetados `ambiguous_compound`,
incluido el mensaje real del bug + 2 casos de control que ya funcionaban):
- **Antes**: `activity` 55/62 agree (89%), 7/9 casos ambiguos nuevos fallan. Overall
  192/202 (95.0%).
- **Después**: `activity` 59/62 agree (95%), 8/9 casos ambiguos nuevos correctos. Overall
  196/202 (97.0%). El único caso ambiguo que sigue en desacuerdo
  (`ambig-curso-padi-generico-no-se-bucear`, "Me interesa el curso PADI, no se bucear"):
  el LLM eligió `padi_open_water` en vez del genérico `padi_course` que esperaba el
  eval-set — una respuesta razonable (Open Water es el curso PADI de entrada por
  defecto), no un misfill peligroso, documentado con honestidad en vez de forzar el
  `expected` para que "cuadre".
- Ningún caso previamente correcto (fuera de `ambiguous_compound`) cambió — 0 regresiones.

Suite completa (3 modos) + compileall + ruff en verde tras el fix (incluido un ajuste a
`scripts/snapshot_prompts.py`, que exige registrar cada prompt nuevo).

**Nota para el registro**: si en producción (medible vía el log `[EXTRACT][ACTIVITY_VETO]`)
el ratio de discrepancia/error en mensajes ambiguos sigue siendo significativo tras esto,
la siguiente escalación (anotada, no implementada) es sustituir las 13 cadenas `if/elif`
de `intent_detector.py` por detección multi-señal con prioridad explícita y documentada
(Opción C, descartada por ahora por ser un refactor mayor).

**Decisión (2026-09-10, ver Fase 11 abajo)**: `llm_activity_veto_cutover` está activo en
`.env.pre` del VPS (confirmado en vivo, `docker exec dp-pre-bot printenv`) — verificado que
corrige correctamente tanto el repro original (curso Open Water + "nunca he buceado") como el
caso nuevo de la conversación 913 ("primer nivel de buceo"). El usuario decidió dejarlo activo
tras la verificación en vivo de Fase 11 en vez de revertir a shadow-mode.

## 2026-09-10 — Fase 11: veto LLM generalizado por-campo, "A bien montado" (Gadea, agent-arch)

**Origen**: conversación real (913) detectada y auditada por el usuario — "Pues me gustaría
sacarme el primer nivel de buceo" resolvía a `certified_diving` en vez de `padi_open_water`.
A diferencia de Fase 9, esto NO era vocabulario duplicado sin sincronizar: era vocabulario
que ningún regex conocía todavía (`matched_activity_categories` solo matcheaba 1 categoría,
la incorrecta), así que el trigger de Fase 9 ("mensaje ambiguo, 2+ categorías") ni se
disparaba. El usuario resumió el riesgo de fondo: cualquier lista de regex, por bien
mantenida que esté, siempre falla ante una frase nueva que nadie escribió ("caemos como el
Titanic"), y pidió explícitamente una solución estructural en vez de otro parche puntual —
además de extender el mismo patrón a `is_certified`/`is_colombian`/`location` ("punto 6 por
bandera"), sin repetir la función casi-idéntica por cada campo.

**Diseño (2 cambios independientes)**:
1. **Trigger ampliado**: de "el regex se autodiagnostica ambiguo" a "el campo se resolvió
   ESTE turno" — `field in regex_intent.detected_fields`. Confirmado fiable leyendo
   `conversational_core._understand()`: `intent = _detector.detect(message, state)` crea un
   `DetectedIntent` NUEVO cada turno, así que ese chequeo distingue de forma correcta "recién
   resuelto" de "ya venía resuelto de un turno anterior" sin depender de que el propio regex
   sepa que se equivocó. Cierra exactamente el gap de la conversación 913.
2. **Generalización a un mecanismo único por-campo** (para no repetir, al nivel del propio
   fix, el mismo anti-patrón de "lógica duplicada que se desincroniza" que motivó la
   auditoría regex de Fase 10): `llm_extractor.verify_activity` → `verify_field(field,
   message, regex_value, ...)`; `prompts/booking.activity_verification_system_prompt` →
   `field_verification_system_prompt(field, lang)` (dispatch por campo, mismo texto de
   `activity` sin cambios + bloques nuevos para `is_certified`/`is_colombian`/`location`,
   basados en las descripciones ya existentes de `EXTRACTION_TOOL`, cada uno con una línea
   explícita pidiendo tener en cuenta variación dialectal/regional); `supervisor.
   _maybe_veto_activity_via_llm` → `_VETO_FIELD_SPECS` (tabla campo→par de flags→side-effect
   opcional) + `_maybe_veto_resolved_field_via_llm(field, ...)` genérico. El único
   side-effect específico de `activity` (fijar `service_id` vía `_ACTIVITY_TO_SERVICE_ID`) se
   extrajo a `_apply_activity_veto`, pasado como `apply` en su spec — el resto de campos no
   tiene side-effect, asignación directa.

**Flags**: los de `activity` (`llm_activity_veto_shadow_mode`/`_cutover`) NO se renombraron —
mismo nombre, solo cambia su condición de disparo internamente, para no requerir migración de
variables de entorno en el VPS. 6 flags nuevos, uno por par y por campo
(`llm_certification_veto_*`, `llm_nationality_veto_*`, `llm_location_veto_*`), todos `False`
por defecto — a diferencia de `activity` (evidencia real, conv. 913), estos 3 son paridad
PREVENTIVA sin bug en vivo que los motive todavía.

**Eval-set**: 4 casos nuevos en `docs/robustness/eval-set.json` — el mensaje real de la
conversación 913 (`conv913-first-level-activity`, `activity`→`padi_open_water`) y 3
sintéticos con fraseo dialectal para medir el mecanismo en los campos nuevos
(`certification-dialect-rescue-colloquial`: "ya llevo el rescue" → `is_certified=true`;
`nationality-dialect-paisa`: "soy paisa" → `is_colombian=true`;
`location-dialect-island-hotel-name`: nombre de hotel de isla sin la palabra "isla"/"rosario"
explícita → `location=island`). `scripts/run_extraction_eval.py` generalizado para medir los
4 campos (antes solo `activity`), con el mismo trigger "resuelto este turno".

Suite completa (3 modos, 1739 passed/18 skipped) + compileall + ruff en verde.

**Verificado en vivo contra PRE (2026-09-10)**: activado temporalmente
`LLM_ACTIVITY_VETO_CUTOVER=true` en `docker-compose.vps.yml` (con backup, revertido después),
redeploy, y reproducido el mensaje real de la conversación 913 vía
`scripts/live_battery_driver.py` dentro del contenedor desplegado. Log real:
`[EXTRACT][ACTIVITY_VETO] regex='certified_diving' llm='padi_open_water' applied=True
msg='Pues me gustaria sacarme el primer nivel de buceo'` seguido de `[INTENT] Activity
updated to: padi_open_water (service: open_water)` — el trigger ampliado ("resuelto este
turno") captura correctamente un caso que el trigger de ambigüedad de Fase 9 nunca hubiera
disparado. Al revertir el override temporal se descubrió que `.env.pre` en el VPS YA tenía
`LLM_ACTIVITY_VETO_CUTOVER=true` de forma independiente y preexistente (no activado en esta
sesión) — la decisión de Fase 9 que quedaba pendiente. El usuario decidió, con la verificación
en vivo de hoy en mano, dejarlo activo tal cual en vez de revertir a shadow-mode.

### Corrección urgente (mismo día, 2026-09-10): el trigger ampliado regresionaba `activity` en vivo

Al correr `run_extraction_eval.py` contra PRE con API key real (paso pendiente de arriba), el
trigger ampliado ("resuelto este turno", sin exigir ambigüedad) mostró una regresión severa:
`activity` cayó de ~95% a **73%** de agreement. Causa: el trigger ahora llamaba al LLM en TODO
turno donde `activity` se resuelve — incluidos los casos claros, sin ambigüedad real — y el
sesgo propio del LLM hacia `minicourse` en mensajes escuetos ("Hola quiero bucear", sin más
información) sobreescribía el default correcto del regex. Como `LLM_ACTIVITY_VETO_CUTOVER`
resultó estar YA activo en `.env.pre` de forma preexistente (ver arriba), **esto degradaba
respuestas reales en PRE en el momento del hallazgo** — desactivado de inmediato
(`LLM_ACTIVITY_VETO_CUTOVER=false`) tras confirmarlo con el usuario.

**Fix real, en dos partes**:
1. `activity` recupera su trigger original de Fase 9 (ambigüedad real, `matched_activity_
   categories(message) >= 2`) a través de un nuevo `should_verify` por-campo en
   `supervisor._VetoSpec`/`_VETO_FIELD_SPECS` — la generalización a otros campos se mantiene,
   pero cada campo puede tener su propio criterio de disparo, no solo "resuelto este turno".
2. El gap real de la conversación 913 se cierra por otra vía, más segura: nuevo patrón en
   `_PADI_COURSE_PATTERNS` (`intent_detector.py`) para "primer nivel"/"primer curso" (de
   buceo) — con este patrón, el mensaje real SÍ dispara 2+ categorías genuinamente
   (`{padi_course, certified_diving}`), así que el trigger de ambigüedad restaurado lo captura
   sin necesidad de ampliar nada.

**Segundo hallazgo, al re-correr el eval-set tras el fix**: `scripts/run_extraction_eval.py`
tenía su PROPIA copia de la condición de disparo (sin el `should_verify` nuevo) — exactamente
el anti-patrón de lógica duplicada que todo este trabajo intentaba evitar, y ocultaba que el
fix real ya funcionaba. Corregido reusando `supervisor._VETO_FIELD_SPECS` directamente en el
script en vez de reimplementar la condición.

**Tercer hallazgo**: `tool_choice` forzado no obliga al modelo a respetar el `enum` declarado en
`EXTRACTION_TOOL` — se observó un caso real donde `activity` volvió `'certificarse'` (ni
siquiera un valor del enum) en vez de un valor real. `verify_field` ahora descarta cualquier
valor fuera del enum declarado del campo (degrada a `None`, nunca deja pasar un valor
inventado).

**Resultado final, verificado en vivo contra PRE tras los 3 fixes**: `activity` 60/63 (95%,
igual que la Fase 9 original), overall 198/206 (96.1%) — mejor que el 95.0%/97.0% de la Fase 9
original y muy por encima del 73%/89% del trigger roto. Suite completa (3 modos, 1740
passed/18 skipped) + compileall + ruff en verde en cada paso.

**Qué quedó a medias / bloqueadores**: `is_colombian` mide 67% de agreement en este eval-set
(6 agree/2 disagree/1 missed) — dato real, pero el flag sigue en `False` por defecto en todas
partes (sin urgencia, no hay bug en vivo que lo motive). Antes de considerar activar shadow-mode
para `is_certified`/`is_colombian`/`location`, revisar esos casos concretos y, si aplica, el
mismo patrón de "el LLM llamado sin discriminar introduce su propio sesgo" que causó la
regresión de `activity` — cada campo puede necesitar su propio `should_verify` más estricto que
"resuelto este turno" antes de activarse en cutover, no asumir que el trigger genérico es
automáticamente seguro solo porque `activity` lo demostró inseguro.

### Extensión a `group_size` (mismo día, 2026-09-10) — 3 rondas de batería sintética + un caso real

Tras cerrar la regresión de `activity`, se activó `llm_activity_veto_cutover` de verdad en PRE
(ya corrige el bug real en producción) y se dejaron `is_certified`/`location` en shadow-mode.
Se corrieron 3 rondas de batería sintética (16, 17 y 16 mensajes respectivamente, vía
`scripts/live_battery_driver.py` dentro del contenedor desplegado) para cazar más gaps antes de
que un cliente real los sufriera. Hallazgos:

- **Corregidos y desplegados**: "nunca me he certificado" resolvía `is_certified=True` (mismo
  patrón que "nunca...buce\*" pero para "certificado", nunca cubierto); "tengo el título de
  buceo"/"estoy titulada" no daban ninguna señal (`título`/`titulad[oa]` no reconocidos como
  sinónimo de certificación).
- **Investigado y descartado (no era bug)**: "estuve certificado pero se me venció" resuelve
  `is_certified=True` por regex; el LLM en shadow-mode discrepó con `False` — pero el regex
  tenía razón (el negocio ya modela "certificado pero necesita refresher" via
  `last_dive_over_2_years`, no como "no certificado"). Buena señal de que el shadow-mode está
  haciendo su trabajo: mostrar discrepancias para juzgar, no para aplicar ciegamente.
- **Bug real de `group_size`, con impacto de precio directo**: "vengo con mi pareja y nuestros
  dos hijos" resuelve `group_size=2` (el patrón `pareja`→2 gana y nunca suma a los hijos) — el
  regex CONTESTA CON CONFIANZA y se equivoca (a diferencia de un hueco `None`, que ya cubriría
  `fill_gaps`; su regla es nunca tocar un campo ya resuelto). Un intento de arreglarlo por regex
  (excluir "mi/tu/su pareja" vía lookbehind negativa) **rompió un caso real validado por el
  owner** (`test_owner_conversations_fase1.py::test_scenario3a_couple_group_size_two`, donde
  "con mi pareja" SÍ debe valer 2 sola, sin más gente mencionada) — revertido de inmediato al
  fallar la suite completa.
- **Duración/nacionalidad**: "toda la semana"/gentilicios regionales ("rolo", "catracho") no se
  resuelven por regex — huecos ya conocidos (el primero documentado en el eval-set desde antes;
  cubierto por `fill_gaps`, que sí lo resuelve bien de forma aislada, solo que en el turno de
  prueba concreto la conversación aún no había llegado a ese punto del flujo). No son bugs
  nuevos.

**Decisión con el usuario**: en vez de seguir parcheando regex uno a uno para el caso de
`group_size` (lista interminable, filosofía explícitamente rechazada), extender el mecanismo de
veto por-campo ya construido a `group_size` — mismo patrón exacto que `is_certified`/
`is_colombian`/`location` (trigger genérico "resuelto este turno", sin `should_verify` propio,
2 flags nuevos `llm_group_size_veto_shadow_mode`/`_cutover`, ambos `False` por defecto). Prompt
de verificación nuevo en `field_verification_system_prompt` (ES+EN) explicando específicamente
el patrón de fallo real (acompañante mencionado + más gente después). Caso real añadido al
eval-set (`group-size-companion-plus-more-people`). Tests dedicados
(`tests/test_group_size_veto.py`) que reproducen el bug real y verifican shadow-mode/cutover/
degradación ante fallo. Suite completa (3 modos, 1756 passed/18 skipped) + compileall + ruff en
verde.

**Rollout completo, verificado en vivo contra PRE, MISMO DÍA** (a diferencia de `activity`, esta
vez con el proceso completo ANTES de decidir cutover — lección aplicada):
1. Desplegado con ambos flags en `False` (sin cambio de comportamiento) — verificado.
2. `llm_group_size_veto_shadow_mode=true` activado y redeployado. Batería de control (7 casos:
   3 ya-correctos + 4 con el bug real) contra el bot desplegado real:
   **0 falsos positivos** en los 3 casos control (ningún log de discrepancia — el LLM coincidió),
   **4/4 casos con bug real detectados** (`[EXTRACT][GROUP_SIZE_VETO] regex=2 llm=4
   applied=False`, etc.) sin aplicar nada.
3. `run_extraction_eval.py` contra el eval-set completo (107 casos, API key real):
   `group_size` 43/44 agree (**98%**), sin ninguna regresión en los casos ya existentes.
4. Con esos datos (no solo la corazonada), `llm_group_size_veto_cutover=true` activado y
   redeployado. Misma batería de 7 casos: los 3 controles siguen intactos, los 4 casos con bug
   real ahora corrigen de verdad (`applied=True`, valores 4/3/3/4) — verificado también end-to-end
   con `route_message` completo: "vengo con mi pareja y nuestros dos hijos" → el bot ahora
   responde "cuatro personas en total" (antes decía "tú y tu pareja", perdiendo a los hijos).

**Estado final en PRE**: `activity` en cutover real (Fase 9+11), `group_size` en cutover real
(Fase 11, hoy), `is_certified`/`location` en shadow-mode (midiendo), `is_colombian` apagado
(riesgo documentado, sin should_verify propio todavía).

### Coste real del mecanismo: medido y optimizado (2026-09-10)

Tras activar 4 campos (2 en cutover, 2 en shadow) nadie había medido cuánto cuesta esto por
turno. Medido en vivo contra PRE (mediana de 3 repeticiones, con calentamiento previo y orden
alternado — la primera medición sin esas precauciones salía sesgada por el arranque en frío,
3.29s vs 1.34s para la misma llamada única):

| escenario | sin vetos | con vetos | delta |
|---|---|---|---|
| actividad simple (0 vetos disparan) | 3.43s / 4 llam | 3.60s / 4 llam | +0.17s / +0 |
| multi-campo (2 vetos) | 3.58s / 4 llam | 5.36s / 6 llam | **+1.78s / +2** |
| conv913 (1 veto) | 3.57s / 4 llam | 4.25s / 5 llam | +0.68s / +1 |
| group_size (1 veto) | 3.53s / 4 llam | 4.28s / 5 llam | +0.75s / +1 |

Dos conclusiones: (1) cuando no dispara ningún veto el coste es **cero** — el diseño de "solo
verifica lo que se resolvió ESTE turno" cumple; (2) cada veto que sí dispara costaba ~0.7-0.9s
y **se sumaban en serie** (`for field in _VETO_FIELD_SPECS: await ...`), así que el peor caso
crecía linealmente con cada campo nuevo de la tabla — con los 5 actuales, +4s teóricos sobre un
turno base de 3.5s, y `group_allocation` era el siguiente candidato.

**Fix**: `asyncio.gather` en el punto de llamada (`conversational_core._understand`). Seguro
porque las llamadas son independientes: cada spec escribe SU campo y el único side-effect extra
(`service_id` de `activity`) también es exclusivo suyo. **Verificado en vivo tras desplegar**:
el caso de 2 vetos baja de +1.78s a +1.21s, y el peor caso real (todos los flags ON, 3 vetos
disparando en el mismo turno) cuesta **+0.53s en total** (4.83s vs 4.30s) en vez de los ~+2.5s
que costaría en serie. El coste ya no escala con el número de campos verificados.

Sobre coste económico: cada veto es una llamada a `gpt-4o-mini` con ~600 tokens de entrada y
`max_tokens=100` — del orden de $0.0001 por llamada. No es el factor limitante; la latencia sí
lo era.

**Corrección al párrafo anterior (descubierto en vivo el mismo día)**: el factor limitante real
no es el dinero ni la latencia, es el **número de peticiones por día**. Durante las pruebas de
hoy la cuenta agotó el límite diario de OpenAI: `Rate limit reached for gpt-4o-mini ... requests
per day (RPD): Limit 10000, Used 10000`. Cuentas: un turno consume ~4 peticiones de base y ~5-7
con los vetos activos, todas contra la MISMA cuota de `gpt-4o-mini` (extracción, notas, señales,
acuse, resolutor de slots y ahora los vetos compiten entre sí). Eso son ~1.400-2.500 turnos/día,
o del orden de 200-400 conversaciones diarias, como techo duro. Para PRE sobra; para producción
real es un número que conviene tener presente antes de añadir más llamadas por turno.

Lo que sí funcionó perfecto: la degradación. Los vetos que se toparon con el 429 cayeron a
"regex-only" en silencio (`[LLM_EXTRACTOR][*_VETO] error: Error code: 429`), el bot siguió
respondiendo con normalidad y el contenedor siguió sano — exactamente el contrato defensivo que
tiene todo el mecanismo desde el principio.

### Bug real de reparto: un grupo de 5 se convertía en uno de 2 (2026-09-10)

Buscando evidencia ANTES de extender el veto a `group_allocation` (en vez de asumir que hacía
falta), una batería local de repartos mixtos encontró un bug peor que el de `group_size`:

| mensaje | group_size | reparto | suma |
|---|---|---|---|
| "vamos 4: **2 certificados**, 1 minicurso y 1 snorkel" | **2** ❌ | `{minicourse:1, snorkel:1}` | 2 |
| "somos 5: **3 certificados**, 1 minicurso y 1 snorkel" | **2** ❌ | `{minicourse:1, snorkel:1}` | 2 |
| "somos 6: 2 **bucean** certificados, 2 minicurso, 2 snorkel" | 6 ✅ | completo | 6 |

Causa raíz: `"N certificados"` no matchea `activity_kw` (le falta el verbo, a diferencia de
`"N bucean certificados"`), así que el Patrón E de 3+ actividades no se activa, cae al Patrón A,
captura solo las 2 cláusulas que sí ve, y la suma (2) **sobreescribía el total explícito del
cliente**. Una reserva de 5 personas se convertía en una de 2 — mismo patrón de fallo que la
§6.bis, con impacto directo en el precio.

**Fix estructural, no una lista de fraseos** (`_set_group_size_from_allocation`): el total solo
se fija desde el reparto si no había uno o si la suma es MAYOR. Un reparto puede ampliar el
total (caso real: "2 de buceo y 3 de snorkel", donde el patrón genérico fijaba 2 y el total real
es 5) pero nunca reducirlo por debajo de lo que el cliente contó. El reparto puede quedar
incompleto, pero eso es ahora una inconsistencia visible (total 5, reparto suma 2) en vez de una
pérdida silenciosa de personas. Verificado en vivo contra PRE: los dos casos de arriba resuelven
ya `group_size` 5 y 4. Suite completa (3 modos, 1760 passed/18 skipped) + compileall + ruff.

**Nota sobre el eval-set y `group_allocation`**: su 91% NO justifica por sí solo un veto — el
único caso que falla (`hist-followup-must-not-rederive-resolved-group-allocation`) es una
alucinación de `fill_gaps` leyendo el historial, no un error del regex, y el veto ni siquiera se
dispararía ahí (solo actúa sobre campos que el REGEX resolvió ese turno). La justificación real
para el veto de `group_allocation` es otra: los repartos incompletos que quedan tras este fix
(total correcto, reparto que no suma el total).

### Rediseño: todas las verificaciones en UNA sola petición (2026-09-10)

El límite diario obligó a mirar el mecanismo con otros ojos. Headers reales de OpenAI en el
momento del 429:

```
x-ratelimit-limit-requests:     10000
x-ratelimit-remaining-requests: 0
x-ratelimit-limit-tokens:       200000
x-ratelimit-remaining-tokens:   199997   ← intactos
x-ratelimit-reset-requests:     24h6m34s (ventana deslizante, no corte a medianoche)
```

Es decir: el recurso escaso de la cuenta son las **peticiones**, no los tokens (que se reponen
cada minuto y estaban prácticamente sin tocar). El diseño de "una petición por campo" gastaba
justo el recurso limitado y desaprovechaba el abundante — y cada campo nuevo empeoraba la
proporción. La paralelización de antes arreglaba la latencia pero no el número de peticiones.

**Rediseño** (no un parche): una sola llamada verifica todos los campos elegibles del turno.
- `booking.py`: el prompt pasa a ser cabecera compartida + reglas POR CAMPO + cierre compartido,
  componibles. Agrupar 3 campos son 2.235 chars frente a 3.623 de los 3 prompts sueltos.
- `llm_extractor.verify_fields(fields, message, regex_values, ...)` devuelve solo las
  discrepancias; `verify_field` queda como atajo de un campo. La validación de enum y el saneado
  de dicts (nulls de `group_allocation`, igual que en `fill_gaps`) se extraen a
  `_clean_verified_value` y se aplican por campo.
- `supervisor._maybe_veto_resolved_fields_via_llm` recolecta los elegibles y hace UNA llamada.
  **Matiz crítico**: la llamada se hace si algún campo tiene alguna bandera encendida, pero la
  APLICACIÓN es por campo según SU PROPIA bandera de cutover — un campo en shadow-mode nunca se
  aplica aunque otro del mismo lote esté en cutover (test dedicado:
  `tests/test_batched_field_veto.py::test_shadow_and_cutover_fields_in_the_same_call_keep_their_own_semantics`).

Coste por turno, resumido en las tres etapas del día: **en serie** +1.78s y +2 peticiones (2
campos) → **en paralelo** +0.53s y +3 peticiones (3 campos) → **agrupado** una ida y vuelta y
**+1 petición** sea cual sea el número de campos. Verificado en vivo que el cableado nuevo
funciona: un turno con 4 campos elegibles produce UNA sola entrada de log
(`[LLM_EXTRACTOR][FIELDS_VETO]`) donde antes habría producido 4. Suite completa (3 modos, 1765
passed/18 skipped).

**Verificación dirigida con LLM real** (mismo día, en cuanto la ventana deslizante repuso ~110
peticiones; 54 gastadas, con tope duro en el script para no dejar al usuario sin margen):

- **Caso multi-campo, el que valida el rediseño** ("somos 4 certificados, estamos en bocagrande
  y queremos el open water aunque nunca hemos buceado" → 4 campos elegibles en UNA llamada):
  ```
  [ACTIVITY_VETO]     regex='minicourse' llm='padi_open_water' applied=True   ← cutover: aplicado
  [IS_CERTIFIED_VETO] regex=False        llm=True              applied=False  ← shadow: NO aplicado
  estado final: activity='padi_open_water' is_certified=False location='cartagena' group_size=4
  ```
  La semántica mixta shadow/cutover dentro de una misma petición, confirmada con modelo real y
  no solo con mocks. `location` y `group_size` no generaron discrepancia (el LLM coincidió con
  el regex): cero falsos positivos.
- Los dos bugs reales del día siguen corregidos tras el rediseño: conv913
  (`certified_diving`→`padi_open_water`) y group_size (`2`→`4`).
- Controles limpios: "quiero hacer snorkel" no disparó ninguna discrepancia; "somos pareja" se
  quedó en 2.
- Un 429 puntual a mitad de la tanda degradó en silencio, como debe.

Nota sobre la reposición de cuota: NO es suave sino a ráfagas — durante la propia tanda se pasó
de 110 disponibles a 0 (el 429 de arriba) y de vuelta a 97, porque el contador es una ventana
deslizante de 24h y la capacidad vuelve según van cumpliendo 24h las peticiones del día
anterior, que se hicieron en picos.

**Pendiente para cuando haya cuota holgada** (~250 peticiones): volver a correr el eval-set
completo para confirmar que agrupar no degrada el acuerdo por campo (el prompt ahora pide varios
campos a la vez y eso podría cambiar cómo responde el modelo — hay que medirlo, no asumirlo), y
re-medir la latencia real del camino agrupado. Solo después, retomar `group_allocation`.

## 2026-09-11 — INCIDENTE: el bot llevaba ≥12h re-respondiendo conversaciones antiguas en bucle

Al intentar correr el eval-set con la cuota ya repuesta (9.998 disponibles), la tanda murió con
429 diciendo "Used 10000". 10.000 peticiones en ~20 minutos no cuadraban con un eval de ~214, así
que se investigó el origen en vez de asumir.

**Lo que estaba pasando** (medido, no deducido):

```
procesados por hora, últimas 12h:
22h:109  23h:116  00h:102  01h:107  02h:111  03h:110
04h:110  05h:115  06h:109  07h:104  08h:107  09h:107
```

~110 mensajes/hora, constante, **las 24 horas incluida la madrugada** — nadie escribe a las 3am.
El contenido eran mensajes **antiguos** de conversaciones de días atrás (conv 492 "no somos
colombianos" msg 9315, conv 510 "hola quiero bucear certificado" msg 9369...), y se **enviaba
respuesta a Chatwoot en proporción 1:1** (16 procesados = 16 enviados en 10 min). 545 procesados
en 5h con 375 ids únicos: reproceso real, no tráfico nuevo.

**Causa raíz**: `_PROCESSED_TTL = 3600` con el comentario *"1 hour: dedup only needs to survive
the webhook/poll race window"*. La suposición es falsa: `poll_active_conversations_once`
(`channels/chatwoot.py`) recorre **cada** conversación del set activo **cada segundo** y relee
todos sus mensajes desde Chatwoot, durante toda la vida del estado (**30 días**). Pasada 1 hora
el marcador de "ya respondí" caducaba, el mensaje volvía a parecer nuevo, y se respondía otra
vez — indefinidamente. La guarda de antigüedad (`created_at < poll_started_at`) no protege de
esto: solo descarta mensajes anteriores a cuando se empezó a vigilar la conversación, no los ya
respondidos.

**Impacto**: ~2.600 mensajes/día ≈ **14.000 peticiones a OpenAI**, que por sí solas superan el
límite de 10.000 RPD de la cuenta. Esto explica los agotamientos de cuota del 10 y 11 de
septiembre que se habían atribuido a las pruebas propias — las pruebas contribuyeron, pero el
consumidor dominante era este bucle. Y en producción habría supuesto **reenviar respuestas a
clientes reales cada hora**: bloqueante de lanzamiento, no una molestia.

**Mitigación aplicada primero** (parar la sangría): adelantar `poll_started_at` a "ahora" en las
708 conversaciones, lo que activa la guarda de antigüedad del propio sistema para todo lo
existente sin borrar nada y sin afectar a mensajes nuevos. Verificado: de ~7 mensajes cada 4 min
a **0**. (Un primer intento de podar el set activo NO funcionó: `save_state` re-añade la
conversación al set cada vez que la procesa, así que se repoblaba sola.)

**Fix de raíz**: `_PROCESSED_TTL = _STATE_TTL` — el marcador de "ya procesado" vive tanto como la
ventana en la que ese mensaje puede volver a leerse. El test nuevo
(`test_dedup_outlives_the_window_in_which_a_message_can_be_reread`) fija el **invariante**
(`_PROCESSED_TTL >= _STATE_TTL`), no el número concreto. Suite completa (3 modos, 1766 passed/18
skipped). Desplegado y verificado en PRE: 0 procesados y 0 enviados en los 4 min posteriores.

**Consecuencia para la cuota**: con el bucle cortado, el consumo de base de PRE pasa de ~14.000
peticiones/día a prácticamente cero salvo pruebas reales. La cuota del 11 quedó igualmente
agotada (18 restantes, reset 23h57m) por las horas que el bucle estuvo activo, así que la
validación del rediseño agrupado se pospone otra vez — pero a partir de mañana debería haber
margen de verdad.

## 2026-09-12 — El rediseño agrupado, validado con datos limpios

Con el bucle parado 23h, la cuota amaneció entera (9.999) — confirmación indirecta del
diagnóstico: era el bucle, no un tope diario quemado.

### Eval-set: misma precisión con 1 petición en vez de N

Tanda limpia (107/107 evaluados, 0 llamadas degradadas, el propio arnés lo certifica):

| campo | suelto (referencia) | agrupado |
|---|---|---|
| activity | 95% (60/63) | 94% (59/63) |
| group_size | 98% (43/44) | **100% (44/44)** |
| is_certified | 97% | 97% |
| location | 100% | 100% |
| is_colombian | 67% | 67% |
| group_allocation | 91% | 91% |
| **overall** | **95.7% (198/207)** | **95.7% (198/207)** |

**Overall idéntico.** Un caso se desplaza de `activity` a `group_size` — dentro del ruido
esperable de un modelo no determinista. No hay degradación por agrupar.

Ojo al camino hasta este número, porque la primera medición decía otra cosa: una tanda con 3
errores 429 dio `activity` 92% y estuvo a punto de hacer descartar el rediseño. Los 3 casos
"nuevos" que fallaban devolvían exactamente el valor del regex, que es justo lo que produce un
429 al degradar. De ahí el endurecimiento del arnés (abortar en rate-limit, excluir degradados,
declarar si la tanda es comparable).

### Latencia: el coste ya no escala con el número de campos

| enfoque | multi-campo (4 campos elegibles) |
|---|---|
| en serie | +1.78s / +2 peticiones |
| en paralelo | +1.21s / +2 peticiones |
| **agrupado** | **+0.79s / +1 petición** |

Cuando no dispara ningún veto el coste sigue siendo cero (−0.08s, ruido). Y lo importante es
estructural: **+1 petición sea cual sea el número de campos verificados**, así que añadir campos
nuevos al mecanismo ya no encarece el turno.

### Fallo del modelo que queda abierto (no del código)

`conv913-first-level-activity` sigue fallando, pero por un motivo concreto y reproducible: para
"primer nivel de buceo" el modelo devuelve `'certificarse'`, que **no existe en el enum de
`activity`**. La validación lo descarta (correctamente: nunca aplicar un valor inventado) y el
campo se queda con el valor del regex. No es un fallo de infraestructura ni del mecanismo: es el
modelo respondiendo mal, y ahora el arnés lo cuenta como tal en vez de excluirlo — que era
justamente lo que ocultaba la primera versión de la guarda.

Hipótesis a probar (barata): el prompt describe las reglas de negocio pero no enumera los
valores válidos del enum, confiando en que el schema baste. Añadir la lista explícita al texto
probablemente lo arregle.

## 2026-09-12 (tarde) — `conv913` cerrado: el enum habia que enumerarlo en el TEXTO

Tarea 1 del `NEXT-SESSION-PROMPT.md`. **La hipotesis era correcta**, y la validacion
salio mas barata y mas concluyente de lo previsto.

### El fallo no era no-determinista: era 10/10

Probe suelto contra el modelo real desde PRE (20 peticiones en total, no el eval-set
entero), mensaje `"Pues me gustaria sacarme el primer nivel de buceo"`:

| variante del prompt | resultado |
|---|---|
| A — actual | **10/10 `'certificarse'`** (fuera del enum) |
| B — con el enum enumerado en el texto | **10/10 `padi_open_water`** |

Ojo al matiz, porque cambia como se lee el hallazgo: el progress-log anterior lo daba
por "no determinista" y sugeria repetir el mensaje "unas cuantas veces" por eso. Con
`temperature=0.0` es **perfectamente reproducible**. Y `'certificarse'` no sale de la
nada: es una palabra **del propio texto de la regla** (`pide 'certificarse'`), que el
modelo copia literalmente. Declarar el `enum` en el schema de la tool NO basta ni con
un `tool_choice` forzado.

### El primer intento SI regresiono algo (y por eso se midio antes de dar por bueno)

La primera version de la lista gloso `certified_diving` como *"inmersion para quien YA
esta certificado"*. A/B controlado sobre los 63 casos con `activity` esperado
(reutilizando un unico `fill_gaps` por caso, de modo que lo unico que cambia entre A y
B es el texto de la regla):

- **1 mejora** (`conv913`) y **1 regresion**: `mixed-uno-buceo-otro-snorkel`
  ("uno quiere buceo y el otro snorkel") pasaba de `certified_diving` a `minicourse`.
- Neto **59/63 → 59/63**: cero ganancia. Si solo se hubiera mirado el agregado del
  eval-set (que dio exactamente el mismo 94% y el mismo overall 95.7% que la
  referencia) se habria concluido "no cambia nada", cuando por dentro se habian
  movido dos casos en sentidos opuestos.

La causa: esa glosa **contradecia la regla que ya estaba escrita justo encima**
("solo usa `minicourse` cuando... solo habla de probar el buceo sin certificarse").
Reescrita como *"inmersion de buceo estandar; es el valor por DEFECTO cuando se pide
'buceo' sin mas, tenga o no certificacion"*:

| | A (prompt actual) | B (enum enumerado) |
|---|---|---|
| casos con `activity` esperado | 59/63 | **62/63** |
| regresiones | — | **0** |

Tres mejoras (`conv913`, `mixed-yo-buceo-amigo-snorkel`, `neg-es-vague-plural-companion-count`),
ninguna regresion.

### Eval-set completo, tanda limpia (107/107, 0 degradadas, el arnes la declara comparable)

| campo | referencia 2026-09-12 | con el fix |
|---|---|---|
| activity | 59/63 (94%) | **62/63 (98%)** |
| group_size | 44/44 (100%) | 43/44 (98%) |
| is_certified | 31/32 (97%) | 31/32 (97%) |
| location | 23/23 (100%) | 23/23 (100%) |
| group_allocation | 10/11 (91%) | 10/11 (91%) |
| is_colombian | 6/9 (67%) | 6/9 (67%) |
| **overall** | **198/207 (95.7%)** | **200/207 (96.6%)** |

El unico retroceso, `group_size` 44→43, es un **`missed` de `fill_gaps`**
(`adv-es-double-negation`, "no es que no estemos certificados, si lo estamos, los 2"):
el regex no resolvio `group_size` ese turno, asi que el veto ni se dispara sobre el y
el prompt de `activity` no puede ser la causa. Ruido no determinista de `fill_gaps`,
no una regresion del cambio.

### Lo que queda abierto (y no se ha forzado)

`ambig-curso-padi-generico-no-se-bucear` ("Me interesa el curso PADI, no se bucear")
sigue en desacuerdo: el eval-set espera `'padi_course'`, un valor **generico que no
existe en el enum de `EXTRACTION_TOOL`**. Es estructuralmente inalcanzable para el
veto — `_clean_verified_value` descartaria `'padi_course'` por la misma regla que
descartaba `'certificarse'`. El modelo responde `padi_open_water`, que es razonable
(Open Water es el curso PADI de entrada). Ya estaba documentado asi desde 2026-09-03 y
se deja igual: **no se toca el `expected` para que cuadre**. Si algun dia se quiere
cerrar, la decision es de producto (¿anadir `padi_course` al enum, o cambiar el
`expected`?), no de prompt.

### Codigo

- `src/prompts/booking.py`: la lista de valores validos, en ES y EN, dentro de
  `_FIELD_VERIFICATION_RULES_*['activity']`.
- `tests/test_activity_veto.py`: 4 tests nuevos (2 parametrizados x2 idiomas) que son
  la barrera — uno exige que el prompt enumere **todos** los valores del enum, otro
  que `certified_diving` se siga describiendo como el valor por defecto y no como
  "solo para ya certificados". Verificado que **fallan** sin el fix.
- Suite completa en verde (1766 passed, 18 skipped); ruff sobre el fichero tocado
  limpio (el repo arrastra 175 avisos preexistentes, identicos antes y despues).

## 2026-09-12 (tarde) — `group_allocation` entra al veto: codigo + medida, flags apagados

Tarea 2 del `NEXT-SESSION-PROMPT.md`. Hecho hasta el punto donde el proceso
obligatorio exige desplegar: **codigo + tests + bateria dirigida + eval-set**, con
`llm_group_allocation_veto_shadow_mode` y `_cutover` **en `False`**. Falta desplegar a
PRE y correr shadow-mode en vivo.

### La justificacion, y lo que NO es

Confirmado el caso real que motiva el campo, reproducido sin LLM de por medio:

    "somos 5: 3 certificados, 1 minicurso y 1 snorkel"
    -> group_size=5 (correcto), allocation={minicourse:1, snorkel:1}   (suma 2)

"N certificados" sin verbo no matchea `activity_kw`. Total bien, reparto que no suma el
total: el regex **contesta con confianza y se equivoca**, que es lo que este mecanismo
caza y lo que `fill_gaps` no puede tocar (su regla es no pisar un campo ya resuelto).

Y se confirma tambien lo contrario, que era el aviso del prompt: **el 91% del eval-set
no justifica nada**. Con el veto de `group_allocation` activo, el eval-set da
`group_allocation` **10/11 (91%), identico**. El unico caso que falla alli
(`hist-followup-must-not-rederive-resolved-group-allocation`) es una alucinacion de
`fill_gaps` leyendo el historial, y el veto **ni se dispara** sobre el: solo actua sobre
campos que el REGEX resolvio ESTE turno. La evidencia real es la bateria, no el
agregado.

### Trigger propio desde el minuto uno

`_group_allocation_should_verify`: dispara **solo si el reparto no suma el `group_size`
conocido**. Es aritmetica, comprobable sin preguntarle a nadie.

No es una optimizacion de coste sino de precision: el trigger generico ("resuelto este
turno") ya se midio en `activity` (89%->73%, revertido) porque llamar al LLM tambien en
los casos claros mete su sesgo por encima de un regex que acertaba. Aqui, ademas, un
reparto que ya cuadra no tiene nada que corregir. Sin `group_size` con que comparar, se
abstiene.

### Bateria dirigida contra el modelo real (shadow: mide, no aplica)

10 mensajes de la familia + 5 controles:

| resultado | casos |
|---|---|
| corregidos al reparto correcto etiquetado a mano | **9/9** |
| abstencion correcta (sin inventar) | **1/1** |
| fallos | **0** |
| controles que disparan (coste) | **0/5** |

Incluye variantes de la forma que se pierde ("3 certificados", "5 buzos certificados",
"3 con titulo", "2 open water" -> `padi_open_water`) y tamanos de grupo de 5 a 10.

El caso que mas importaba es el ultimo: **"somos 4: 2 minicurso y 1 snorkel"**, donde el
4o integrante no declara actividad. El reparto es incompleto de verdad (el mensaje no
dice que hace esa persona), asi que la respuesta correcta es **no inventar**. El modelo
se abstuvo. Es el riesgo real de este campo y no se materializo.

Los 5 controles (repartos que ya cuadran, y un plural vago) **no disparan**: coste cero.

### Eval-set completo, tanda limpia y declarada comparable

| campo | referencia 2026-09-12 | con ambos cambios de hoy |
|---|---|---|
| activity | 59/63 (94%) | **62/63 (98%)** |
| group_size | 44/44 (100%) | 44/44 (100%) |
| is_certified | 31/32 (97%) | 31/32 (97%) |
| location | 23/23 (100%) | 23/23 (100%) |
| group_allocation | 10/11 (91%) | 10/11 (91%) |
| is_colombian | 6/9 (67%) | 6/9 (67%) |
| **overall** | **198/207 (95.7%)** | **201/207 (97.1%)** |

Cero regresiones. La ganancia entera viene de `activity` (tarea 1); `group_allocation`
no mueve el eval-set, tal y como estaba previsto. De paso queda descartado el
`group_size` 43/44 de la tanda anterior: vuelve a 44/44, era ruido de `fill_gaps`.

### Hallazgos nuevos de la bateria (NO arreglados, a la cola)

1. **El veto de `group_allocation` es, hoy, solo de ES.** Ningun mensaje en ingles
   produce reparto: "we are 6: 3 certified, 2 minicourse and 1 snorkel" da
   `allocation=None`. En EN esto es territorio de `fill_gaps` (hueco), no del veto.
2. **`"en total 7: 4 certificados, 2 minicurso y 1 snorkel"` resuelve `group_size=4`**,
   no 7 — se queda con el "4" del primer tramo en vez del total declarado. Bug de
   `group_size`, independiente de este trabajo. El veto de `group_allocation` corrigio
   igualmente el reparto, pero lo compara contra un total equivocado. Candidato claro
   para el veto de `group_size` (que sigue apagado).
3. **La superficie del veto es mas estrecha de lo que parece**: hacen falta >=2 tramos
   que SI matcheen mas >=1 perdido. Con un solo tramo reconocible
   ("somos 8: 6 certificados, 2 minicurso") el regex devuelve `allocation=None` entero,
   que es un hueco de `fill_gaps`, no un reparto incompleto. Util para no sobrestimar
   lo que este veto puede arreglar.

### Codigo

- `src/config.py`: los 2 flags nuevos, `False`, con la justificacion (y el aviso de que
  no es el 91%).
- `src/agents/supervisor.py`: `_group_allocation_should_verify` + entrada en
  `_VETO_FIELD_SPECS`.
- `src/prompts/booking.py`: regla de `group_allocation` en ES y EN — **obligatoria**:
  `fields_verification_system_prompt` hace `rules[f]` y reventaria con `KeyError` en
  cuanto el campo entrase en un lote.
- `tests/test_group_allocation_veto.py`: 16 tests. Cubren el trigger (dispara/calla/se
  abstiene), shadow-no-aplica vs cutover-aplica, degradado a regex ante fallo del LLM, y
  sobre todo **que es un dict y no un escalar** (limpieza de nulls del schema estricto y
  comparacion `!=` sobre dicts), que es lo que el prompt de la sesion pedia fijar.

Suite completa en verde: **1786 passed, 18 skipped** (1766 antes; +4 de `activity`, +16
de `group_allocation`). Ruff limpio en los ficheros tocados.

### Lo que falta del proceso obligatorio

Desplegar a PRE con los flags en `False`, encender **shadow-mode** (`_shadow_mode=true`,
que solo loguea `[EXTRACT][GROUP_ALLOCATION_VETO]` sin aplicar), dejar correr trafico
real, y **solo entonces** decidir el cutover con esos datos. No se ha desplegado nada en
esta sesion.

## 2026-09-12 (tarde) — A y B: centralizar el enum y fusionar las 2 peticiones del turno

Petición del owner, en sus palabras: **"centralizar, no individualizar"** y **"nada de
más regex: arregla el caso de hoy y pincha con la jerga del siguiente"**. Dos trabajos
salieron de ahí.

### A — el enum, generado desde el schema (el fix de `activity` era un parche)

El arreglo de la mañana escribía la lista de valores válidos **a mano, en un campo, en
dos idiomas**. Pero hay **5 campos con enum** (`activity`, `duration`, `location`,
`recall_field`, `companion_activity`) y **2 prompts** que los consumen
(`extraction_system_prompt` para `fill_gaps` y `fields_verification_system_prompt` para
el veto). Cubrir 1 de 5 en 1 de 2 dejaba la misma bomba puesta en el resto: **`fill_gaps`
no enumeraba ningún enum**.

Ahora la lista la genera `_enum_values_sentence` **desde el propio schema** y se inyecta
sola en los dos prompts. Las **glosas** (lo único que no se deriva del schema, porque son
reglas de negocio) viven en un mapa único por idioma.

Eval-set, tanda limpia: **201/207 (97.1%) → 202/207 (97.6%)**, 0 regresiones. La subida
es un caso de `is_colombian`, que **no tiene enum** y por tanto no tiene vía causal con el
cambio: ruido, no mérito. El valor de A es estructural.

Tests: `tests/test_prompt_enum_enumeration.py`, parametrizado **sobre el schema**. No
comprueba `activity`: comprueba que *todo* campo con enum quede cubierto en *ambos*
prompts, también al agrupar, más una barrera contra glosas huérfanas. Un campo nuevo lo
hereda gratis.

### B — una petición por turno en vez de dos

`fill_gaps` y `verify_fields` usaban **el mismo modelo y la misma tool** en 2 peticiones
distintas del mismo turno. En el eval-set, **el 61% de los turnos disparan las dos**.

Se pueden fusionar porque **el conjunto de huecos NO depende del resultado del veto**: el
veto solo cambia el VALOR de campos que el regex YA había resuelto, y `missing_fields`
mira justo los que siguen en `None`/`[]`. Comprobado antes de tocar nada.

**El orden dentro del prompt resultó ser lo decisivo, y costó tres intentos medidos.**
6 repeticiones por variante, todas deterministas (0/6 o 6/6, nunca a medias):

| intento | resultado |
|---|---|
| 1. Reencuadrar en "(1) RELLENAR… (2) VERIFICAR…" | `grp-es-mixed-suegra` deja de rellenar `group_allocation` **0/6**; `adv-es-double-negation` deja de rellenar `group_size` **0/6** |
| 2. Prompt de huecos **intacto** + verificación **detrás** | igual de mal: **0/6** los dos. No era el reencuadre |
| 3. Verificación **primero**, huecos **al final** | la suegra vuelve a **6/6** |

Es un **efecto de recencia**: la última instrucción es la que el modelo atiende mejor, y
el relleno de huecos es la tarea frágil (para él, abstenerse siempre es una salida
válida). Si alguien reordena ese prompt "por legibilidad", reintroduce el fallo — por eso
está escrito en el docstring de la función, no solo aquí.

Ojo al primer número, porque casi engaña: la variante 1 dio **97.1% overall**, apenas
−0.5 puntos, y parecía un coste asumible por el 38% de ahorro. Pero por dentro había
**dos regresiones deterministas** compensadas por una mejora. El agregado del eval-set
volvió a esconder movimientos en sentidos opuestos, igual que esta mañana con `activity`.
Sin el A/B por caso se habría desplegado una regresión real creyendo que era ruido.

**Resultado final (tanda limpia, 107/107, declarada comparable):**

| | sin fusionar | fusionado (orden bueno) |
|---|---|---|
| overall | 202/207 (97.6%) | **204/207 (98.6%)** |
| peticiones | 172 | **107 (−38%)** |
| latencia/turno | 1.32s | **0.63s (−0.69s, −52%)** |
| `is_certified` | 31/32 | 32/32 |
| `is_colombian` | 7/9 | 9/9 |
| `group_allocation` | 10/11 | 10/11 |

La latencia está **medida** (18 muestras por variante), no extrapolada.

Sobre el `is_colombian` 7/9 → 9/9: son los dos casos de "ninguno colombiano" con
historial, y es el campo más ruidoso del set. Que la fusión los arregle es plausible (la
regla de `is_colombian` va ahora al principio del prompt), pero con 2 casos **no lo doy
por demostrado**.

**Caso conocido que la fusión NO recupera**: `adv-es-double-negation` ("no es que no
estemos certificados, si lo estamos, los 2") sigue sin rellenar `group_size`, 0/6
determinista, frente a 6/6 sin fusionar. Doble negación + cantidad implícita. Es el
precio real y medido de B, y se deja documentado en vez de esconderlo en el agregado.

### Código

- `src/prompts/booking.py`: `_enum_values_sentence`/`_enum_values_block` + glosas (A);
  `combined_extraction_system_prompt` (B), que **reutiliza `extraction_system_prompt`
  intacto y lo pone al final**.
- `src/agents/llm_extractor.py`: `extract_and_verify` (1 petición, devuelve
  `(patch, disagreements)`), más `_build_messages`/`_strip_schema_nulls` compartidos por
  las tres funciones para que no se desincronicen.
- `src/agents/supervisor.py`: `apply_veto_disagreements` separado de la llamada — ahora
  hay dos sitios que **obtienen** discrepancias y uno solo que **decide qué hacer** con
  ellas (flag de cutover por campo + `spec.apply`).
- `scripts/snapshot_prompts.py`: el prompt combinado y `group_allocation` registrados.
- `tests/test_activity_veto.py`: los e2e mockean ahora **las dos vías**; mockear solo una
  dejaba el test mudo y colándose a la API real.

Suite completa: **1801 passed, 18 skipped**. Ruff limpio en lo tocado.

## 2026-09-12 (tarde) — C: los tres hallazgos del parser de grupo son UNO

Encargo: mirar el parser de grupo **como una sola cosa**, en vez de abrir tres tickets.
Resultado: no son tres bugs. Son **un único fallo** con tres caras, y de paso se cae uno
de los tres hallazgos tal y como lo reporté.

### La causa

Todo el reparto de grupo se apoya en una **lista cerrada de palabras**
(`intent_detector.py`):

```
activity_kw = (buce\w*|buse\w*|snorkel|snorkeling|esnorkel|careteo|caretear|
               minicurso|mini\s?curso|bautismo|bautizo|diving|scuba|submarinismo)
```

…más una cadena de patrones (A/B/C/E) que reconocen **formas fijas de cláusula**
("N ACTIVIDAD y N ACTIVIDAD"), cada uno guardado por `if not intent.group_allocation`.

**Cada uno de los tres hallazgos es "el mensaje usó una palabra o una forma que no está
en la lista".** Nada más:

| hallazgo | lo que falta en la lista |
|---|---|
| reparto incompleto ("3 certificados") | `certificados` **como sustantivo que nombra la actividad**. En la lista solo existe como sufijo adjetivo detrás de una actividad de verdad (`bucean certificados`) |
| `group_size` equivocado | la frase de total. `somos 7`/`vamos 7` ✓, pero **`en total 7` ✗ y `seremos 7` ✗** → coge el "4" de la primera cláusula |
| "hace falta ≥2 tramos" | consecuencia del primero: si "6 certificados" no se reconoce, queda **una** cláusula, y ningún patrón cubre la aridad 1 |

Medido, regex puro:

```
somos 7: 4 certificados, 2 minicurso y 1 snorkel   -> group_size=7   ✓
vamos 7: ...                                       -> group_size=7   ✓
en total 7: ...                                    -> group_size=4   ✗
seremos 7: ...                                     -> group_size=4   ✗
somos 8: 6 certificados, 2 minicurso               -> allocation=None ✗
somos 8: 6 bucean y 2 minicurso                    -> allocation={certified_diving:6, minicourse:2} ✓
```

`seremos 7` no estaba en el hallazgo original: apareció al mirar la familia en vez del
caso.

### Corrección de un hallazgo anterior mío

En la entrada de `group_allocation` escribí que **"en EN el regex nunca produce
reparto"**. **Es falso.** El inglés funciona:

```
we are 6: 4 diving and 2 snorkel  -> group_size=6, allocation={certified_diving:4, snorkel:2} ✓
4 diving and 2 snorkel            -> allocation={certified_diving:4, snorkel:2}               ✓
```

Lo que fallaba en mis ejemplos era `3 certified` — o sea **la misma palabra que falta en
español**, no el idioma. Un hallazgo "de inglés" que en realidad era el hallazgo nº1 otra
vez: justo el error de individualizar que este trabajo venía a corregir.

### Por qué NO se arregla añadiendo palabras

Añadir `certificados`, `en total`, `seremos` cierra estos cuatro mensajes y deja el
mecanismo igual de frágil para el siguiente cliente que escriba `somos 7 en total`,
`entre todos 7`, `4 con título`, `4 brevetados`, `4 open water`… Es exactamente el modo
de fallo que el owner señaló: *"un regex evita el problema puntual, pero luego llega otra
persona con otra jerga y pinchamos"*. Y ya hay precedente en este repo: un intento previo
de arreglar `group_size` por regex rompió un caso real validado por el owner y hubo que
revertirlo.

### La vía que sí es estructural (recomendada, NO implementada)

El reparto de responsabilidades ya elegido en este proyecto es *"el LLM decide QUÉ pasó,
el CÓDIGO decide la respuesta con el valor real"*. Para el grupo eso ya existe en dos
sitios: `fill_gaps` (cuando el regex no resolvió) y el veto de `group_allocation`
(cuando resolvió a medias, añadido hoy). El problema es que **hay una puerta que los
apaga**, en `conversational_core._relevant_gaps`:

```python
if state.detected_group_size and not _ADDED_PERSON_RE.search(message):
    gaps = [f for f in gaps if f != "group_allocation"]
```

Con la cantidad ya sabida y sin señal de "se añade alguien", `group_allocation` **se cae
de los huecos**. Así que en "somos 8: 6 certificados, 2 minicurso" el regex se abstiene,
el veto no se dispara (no hay reparto que contradecir) y `fill_gaps` tiene prohibido
mirarlo: **el reparto se pierde en silencio**, que es el hallazgo nº3 visto desde el otro
lado.

Esa puerta se puso por **coste**: *"pedirlo cada turno era gasto puro"*. **Ese argumento
ya no aplica**: desde la fusión de hoy, pedir un campo más va en la MISMA petición que ya
se está haciendo — cuesta tokens (recurso abundante), no peticiones (el escaso). Quitar
la puerta es una línea, y devuelve el reparto al camino LLM sin tocar un solo regex.

**El contra, honesto**: la puerta también reducía superficie de misfill, y el riesgo está
documentado y **sigue vivo** — `hist-followup-must-not-rederive-resolved-group-allocation`
("desde cartagena" con historial) es hoy el único fallo de `group_allocation` en el
eval-set, y es precisamente `fill_gaps` alucinando un reparto desde el historial. Abrir
la puerta puede empeorar esa familia.

Por eso **no se ha tocado**: el eval-set no puede medirlo (el arnés no pasa por
`_relevant_gaps`, pide siempre todos los huecos), así que hace falta una batería a nivel
de CONVERSACIÓN, con estado e historial — `scripts/live_battery_driver.py`. Medir primero,
decidir después, como con todo lo demás de hoy.

### Estado

Diagnóstico cerrado; los tres hallazgos se unifican en uno solo y se corrige el de inglés.
Ningún cambio de código en C.

## 2026-09-12 (noche) — Batería de conversación: las dos palancas de `group_allocation`

Hacía falta porque **ni el eval-set ni PRE pueden responder esto**: el arnés del eval-set
pide siempre todos los huecos, así que nunca pasa por `_relevant_gaps`; y PRE no tiene
tráfico real (solo los 3 desarrolladores), así que esperar a producción no recoge nada.
Hay que provocarlo.

`scripts/battery_group_allocation_gate.py` — 23 escenarios (10 beneficio, 10 riesgo, 3
frontera) × 4 variantes × 2 repeticiones, atacando `_understand` (que es donde viven las
dos palancas y no toca BD ni RAG).

Las dos palancas:
- **puerta**: `_relevant_gaps` quita `group_allocation` de los huecos si ya se sabe la
  cantidad y el mensaje no añade gente. Se puso **por coste**, y ese argumento decayó al
  fusionar las peticiones del turno.
- **veto**: `llm_group_allocation_veto_cutover`, que corrige un reparto que el regex
  resolvió pero que no suma el total.

### Resultado del 2×2

| variante | repartos correctos | PARCIALES (peligrosos) | vacíos | alucinaciones |
|---|---|---|---|---|
| **hoy** (puerta sí, veto no) | 3/10 | 1 | 5 | **0/10** |
| sin puerta | 5/10 | 1 | 1 | **0/10** |
| solo veto | 4/10 | 0 | 5 | **0/10** |
| **puerta fuera + veto** | **6/10** | **0** | **1** | **0/10** |

**Las dos palancas son complementarias y solo juntas dominan**: duplican los repartos
correctos (3→6), eliminan los parciales peligrosos (1→0) y vacían la cola de abstenciones
(5→1), **sin introducir ni una sola alucinación**.

### Lo que NO esperaba, y es lo más útil

**Quitar la puerta sola puede EMPEORAR un caso.** En `b03` ("4 con titulo y 2 snorkel") y
`b04` ("3 brevetados y 2 snorkel") hoy hay abstención limpia (`null`); sin la puerta,
`fill_gaps` devuelve **`{snorkel: 2}`** — un reparto presente que se deja fuera a 4 de 6
personas. Un reparto incompleto pero visible es **peor** que no tener reparto: es
exactamente el fallo que el veto existe para cazar. Por eso la puerta sola no basta.

**El riesgo que temíamos no apareció: 0 alucinaciones en 10 escenarios × 4 variantes × 2
repeticiones.** La protección real no era la puerta, era `_state_known_fields`: un reparto
ya conocido por la conversación nunca vuelve a pedirse (`r01`, el caso del eval-set,
sale limpio en las cuatro variantes). El eval-set **sobreestimaba** ese riesgo porque su
arnés no pasa por ese filtro.

### Tres hallazgos accionables (no implementados)

1. **El trigger del veto se pierde el caso multi-turno.**
   `_group_allocation_should_verify` compara el reparto contra
   `regex_intent.group_size` — el total de ESTE turno. Pero en una conversación el total
   suele venir de un turno anterior y vive en `state.detected_group_size`. En `b03`/`b04`
   el veto **no llega a dispararse** por eso, y son justo los casos que quedan mal.
   Debería mirar el total que conoce la CONVERSACIÓN, no solo el turno. Es la misma
   lección de centralizar: el trigger razona con media foto.

2. **Las reglas de negocio por campo solo las tiene el prompt del veto.**
   La regla que escribí para `group_allocation` ("devuelve el reparto COMPLETO… o OMITE el
   campo entero") vive en `_FIELD_VERIFICATION_RULES_*`, que solo consume el veto.
   `fill_gaps` se apaña con la descripción del schema, que no dice eso — y por eso
   devuelve `{snorkel: 2}` en vez de omitir. **Es el mismo patrón que ya corregimos con
   los enums (A), sin corregir para las reglas**: centralizar `_FIELD_VERIFICATION_RULES_*`
   para que las consuman los dos prompts cerraría `b03`/`b04`/`b05` sin tocar un regex.

3. **`b05` ("2 open water y 3 snorkel") falla en las cuatro variantes.** El LLM omite el
   tramo de `padi_open_water` pese a estar en el enum. Cae en el mismo saco que (2).

### Casos que NO arregla ninguna variante

`b10` ("4 con brevet, 2 minicurso y 1 snorkel") y `b07` con el veto apagado: el regex ya
produjo `{minicourse:2, snorkel:1}`, así que no es hueco y la puerta no pinta nada — solo
el veto entra ahí. Con el veto puesto, `b07` pasa a **OK**.

### Recomendación

La combinación **quitar la puerta + veto de `group_allocation` en cutover** es la que
domina en los datos, y el riesgo medido es cero. Pero antes conviene resolver el hallazgo
(1) — el trigger multi-turno — porque es lo que impide que el veto rescate `b03`/`b04`,
y el (2), que es la centralización que de verdad cierra la familia.

Ningún cambio de código en esta entrada: la batería queda commiteada como herramienta
reutilizable para volver a medir cuando esos dos se toquen.

## 2026-09-12 (noche) — (2) centralizar reglas: RESULTADO NEGATIVO. (1) trigger multi-turno: hecho

Los dos arreglos que la batería había señalado. Uno salió mal y se revierte; el otro se
queda.

### (2) Meter las reglas por campo en `fill_gaps` — medido y revertido

La idea parecía la misma centralización que funcionó con los enums: `_FIELD_RULES_*` solo
las consumía el prompt del veto, y `fill_gaps` se apañaba con la descripción del schema —
que no dice "reparto completo o ninguno". De ahí los repartos a medias.

Se implementó (partiendo las reglas en semántica compartida + pistas de "así falla el
detector", que solo tienen sentido al verificar) y se midió. **Mal:**

| eval-set (mismo arnés serial) | overall |
|---|---|
| antes | 202/207 (97.6%) |
| con las reglas en `fill_gaps` | **197/207 (95.2%)** |

Los **5 casos nuevos que fallaban eran todos abstenciones de `fill_gaps`**: "just the two
of us wanna dive" dejó de dar `group_size`, "im from the states" dejó de dar
`is_colombian`, "vengo sin compañía" dejó de dar `group_size`… Y encima **no arregló lo
que lo motivaba**: en la batería, `b03`/`b04`/`b05` seguían dando repartos parciales.

La causa es la misma que ya medimos al fusionar las peticiones: **estas reglas están
escritas para VERIFICAR** y van cargadas de "no inventes" / "solo responde cuando" /
"abstenerse es mejor". En un prompt cuya tarea es RELLENAR, ese tono hace que no rellene.
La tarea de relleno es la frágil — es la tercera vez hoy que este proyecto se topa con lo
mismo.

**Se revierte el USO, no la estructura.** `_FIELD_RULES_*` y `_FIELD_DETECTOR_HINTS_*`
siguen separados (una sola fuente, sin texto duplicado) y `_field_guidance` sigue ahí;
simplemente `fill_gaps` vuelve a llevar solo los enums. Tras revertir, el eval-set vuelve
a **202/207**, confirmando que el coste era exactamente ese.

El resultado negativo queda escrito en el código y clavado con un test
(`test_fill_gaps_prompt_does_not_carry_the_verification_rules`), para que el siguiente que
tenga la idea no gaste una tanda entera en redescubrirla. Si alguien quiere reintentarlo,
el camino no es enchufar estas reglas tal cual sino escribir una versión **neutra** (qué
significa el campo y qué cuenta como contable, sin la carga de abstención) y volver a
medir.

### (1) El trigger del veto mira el total de la CONVERSACIÓN — hecho

`_group_allocation_should_verify` comparaba contra `regex_intent.group_size`, el total de
ESTE turno. En conversación real el total casi siempre se dijo antes y vive en
`state.detected_group_size`, así que el veto se quedaba mudo justo en los casos
multi-turno. Ahora `should_verify` recibe `state` (opcional, para no romper las llamadas
de 2 argumentos) y cae al total de la conversación cuando el turno no lo trae.

Neutro en el eval-set **por construcción**, no por suerte: su arnés crea un
`ConversationState` limpio por caso, así que nunca hay total previo. Confirmado: 202/207
antes y después. 5 tests nuevos lo fijan, incluido que el total del turno manda sobre el
de la conversación cuando existe.

### La batería, otra vez, con el estado final del código

| variante | correctos | parciales peligrosos | vacíos | alucinaciones |
|---|---|---|---|---|
| hoy | 3/10 | 1 | 5 | 0/10 |
| sin puerta | 5/10 | 1 | 1 | 0/10 |
| solo veto | 4/10 | 0 | 5 | 0/10 |
| **puerta fuera + veto** | **6/10** | **0** | **1** | **0/10** |

Igual que la primera medición. Ni (1) ni (2) movieron esta tabla, y merece la pena decir
por qué, porque es el hallazgo que queda vivo:

### Por qué el veto no rescata `b03`/`b04`: un agujero estructural

Con la puerta abierta, "4 con titulo y 2 snorkel" (grupo de 6) hace que `fill_gaps`
devuelva **`{snorkel: 2}`** — un reparto que deja fuera a 4 de 6 personas. El veto NO lo
corrige, y no es cuestión del trigger: **el veto solo mira campos que resolvió el REGEX**
(`field in regex_intent.detected_fields`, y la lista se calcula ANTES de la llamada al
LLM). Un reparto producido por `fill_gaps` está, por construcción, fuera de su alcance en
ese turno.

O sea que hoy la invariante "el reparto debe sumar el total" solo se comprueba para una de
las dos fuentes posibles del reparto. Eso es lo que convierte "abrir la puerta" en un
cambio con contrapartida: gana 3 repartos correctos pero introduce 2 repartos parciales
equivocados, que son peores que abstenerse porque mal-tarifican la reserva en silencio.

**La pieza que falta y que haría la decisión trivial**: aplicar esa invariante al reparto
FINAL, venga de donde venga — si no suma el total conocido, o se manda al veto o se
descarta (y el bot pregunta), pero nunca se guarda un reparto parcial. Es código puro,
determinista, cero peticiones extra y cero regex. Con eso, `puerta fuera + veto` pasaría a
ser estrictamente mejor que hoy: 6 correctos, 0 parciales, 0 alucinaciones.

No se implementa aquí: toca decidirlo con el owner.

## 2026-09-12 (noche) — La invariante del reparto, la puerta fuera y el veto en cutover

Cierre de la línea de `group_allocation`. Tres cambios que van juntos y que **solo juntos**
tienen sentido.

### La invariante: el reparto debe sumar el total, venga de donde venga

`supervisor.enforce_group_allocation_consistency`, aplicada en `_understand` justo antes de
escribir el estado — el **único punto** donde el intent del turno ya está completo (regex +
veto + relleno).

Nace de un agujero estructural: la comprobación "el reparto suma el total" solo la hacía el
veto, y **el veto solo mira campos que resolvió el regex** (la lista se calcula antes de la
llamada al LLM). Un reparto producido por `fill_gaps` quedaba sin revisar: "4 con titulo y 2
snorkel" en un grupo de 6 se guardaba como `{snorkel: 2}` — 4 personas fuera y la reserva
mal tarificada **en silencio**.

Se comprueba una vez sobre el resultado final en lugar de en cada productor, así que
cualquier fuente futura queda cubierta sin tocar nada.

**Dos desenlaces, no uno** — y el segundo salió de la medición, no del diseño:

- reparto suma **menos** que el total → le falta gente → se descarta (el bot pregunta,
  que sale gratis, en vez de tarificar de menos sin avisar).
- reparto suma **más** → se cree al reparto y se **sube** el total, mismo criterio que el
  regex ya aplicaba en `_set_group_size_from_allocation`.

La primera versión descartaba en los dos casos, y la batería la pilló: "3 certified and 3
snorkel" con el total mal leído como 3 **descartaba un reparto correcto de 6**. El total
también puede venir equivocado — es justo el hallazgo nº2 del parser de grupo.

### La puerta, fuera (con un matiz que salió de un test)

Retirado el filtro que quitaba `group_allocation` de los huecos cuando ya se sabía la
cantidad. Se puso por coste, y ese argumento decayó al fusionar las peticiones del turno.

Pero el argumento exacto es *"viaja gratis en una petición que ya se iba a hacer"*, y eso
**solo vale si la petición existe**. Un test existente
(`test_understand_skips_llm_when_state_knows_driving_fields`) lo cazó: con la puerta fuera
del todo, una reserva ya completa haría una llamada LLM **en cada turno de charla**
("genial, nos vemos") solo por el reparto. Así que se aplica el argumento literalmente:

```python
if gaps == ["group_allocation"]:
    gaps = []
```

Puede viajar de acompañante; nunca originar la petición. Coste real del cambio: **cero
peticiones nuevas**. En la batería no cuesta ni un caso.

### El veto, en cutover

`llm_group_allocation_veto_cutover` nace en `True`, a diferencia del resto de campos del
mecanismo. No es capricho: es el único que se activa **con datos medidos de antemano** en
vez de "a ver qué tal". Conviene anotar la inconsistencia — `activity` y `group_size` viven
en `.env.pre` del VPS y aquí la decisión está en el código.

### Resultado

Batería de conversación (23 escenarios × 4 variantes × 2 repeticiones):

| variante | correctos | parciales peligrosos | vacíos | alucinaciones |
|---|---|---|---|---|
| hoy (antes de todo esto) | 3/10 | 1 | 5 | 0/10 |
| solo veto | 4/10 | 0 | 5 | 0/10 |
| solo puerta fuera | 5/10 | 0 | 4 | 0/10 |
| **lo que se queda** | **6/10** | **0** | **3** | **0/10** |

**El doble de repartos correctos, cero repartos parciales y cero alucinaciones.** Los 10
escenarios de riesgo salen limpios en las cuatro variantes.

Eval-set, tanda limpia y declarada comparable, **con la invariante aplicada**:

| campo | antes | ahora |
|---|---|---|
| activity | 62/63 (98%) | 62/63 (98%) |
| group_size | 44/44 (100%) | 44/44 (100%) |
| group_allocation | 10/11 (91%) | 10/11 (91%) |
| is_colombian | 7/9 (78%) | 7/9 (78%) |
| **overall** | **202/207 (97.6%)** | **202/207 (97.6%)** |

La invariante **no cuesta nada** en el eval-set. Era el riesgo que había que descartar:
podría haber tirado repartos correctos si los totales discrepaban.

(Aviso metodológico: la fila de `group_allocation` salió **en blanco** en el stdout de esa
tanda — un `grep -v` del ruido de LangSmith se llevó la línea, exactamente el fallo contra
el que avisa la entrada del 2026-09-12. Los números salen de `eval-last-run.json`, que es
para lo que existe.)

### Lo que NO arregla, y por qué se deja

`b03` ("4 con titulo"), `b04` ("3 brevetados"), `b05` ("2 open water"), `b10` ("4 con
brevet") siguen sin dar reparto. El LLM no reconoce esas formas como tramo contable, y la
invariante ahora hace que, en vez de guardar un reparto a medias, **el bot pregunte** — que
es el desenlace seguro. Arreglarlos pasa por el prompt de `fill_gaps`, y ya está medido que
meterle ahí las reglas de verificación **cuesta 5 casos del eval-set**: haría falta una
versión neutra de esas reglas, escrita para rellenar y no para desconfiar. Queda anotado,
no forzado.

## 2026-09-14 — El total que cuenta es el que se GUARDA, triggers propios y los cutover al código

Sesión siguiendo `NEXT-SESSION-PROMPT.md` del 2026-09-12. Tres cambios de código, una
batería reescrita y tres hallazgos de infraestructura.

### Arranque

- La rama local `feature/pre_gadea` iba 178 commits por detrás de `origin` (y con 18
  propios). Los 18 están íntegros en `origin/backup-pre_gadea-2026-09-01` (su punta es
  exactamente el mismo commit) y ya se portaron en 0.22.1, así que se movió la rama a
  `origin` sin perder nada.
- Cuota OpenAI: 9999 peticiones restantes. PRE corría `b42ba26`.
- Logs de PRE, 72h: **ni una sola etiqueta `[EXTRACT]`**. Confirmado otra vez: sin tráfico,
  hay que provocarlo.

### Tarea 1 (total mal leído): la hipótesis del prompt era falsa

El prompt suponía que el trigger genérico del veto de `group_size` no disparaba porque el
regex "acierta con confianza". **Sí dispara**: con "en total 7: 4 certificados…" el regex da
`group_size=4` (el patrón `(\d+)\s+certificad[oa]s` de `intent_detector` toma la cifra de un
TRAMO por el total) y `_eligible_veto_fields` devuelve `group_size` y `group_allocation`.

Sonda con LLM real dentro del contenedor de PRE, pasando por `_understand` (14 escenarios × 2
repeticiones, deterministas):

| veto de `group_size` | total correcto | repartos parciales guardados |
|---|---|---|
| apagado (el default del código) | 20/28 | 6 |
| encendido (lo que tiene `.env.pre`) | **28/28** | **0** |

Controles intactos, incluido el caso del owner "con mi pareja, tenemos un presupuesto…" = 2.
Conclusión: **en PRE ya estaba resuelto, pero solo por un flag que vive fuera del repo** — lo
que convierte la tarea 1 en la tarea 4.

### El agujero que sí había: la invariante comparaba con el total del TURNO

La misma sonda destapó `m02`: con 7 personas ya sabidas, "4 certificados" → total de turno 4,
`fill_gaps` devuelve `{certified_diving: 4}`, el reparto **cuadra con ese 4** y se guarda. Pero
el estado sigue en 7 (el total se escribe una sola vez salvo corrección explícita): **reparto
de 4 para un grupo de 7**. `enforce_group_allocation_consistency` y
`_group_allocation_should_verify` razonaban con el total del turno, que es justo el que el
regex lee mal.

Y la batería lo encontró **fallando en PRE con los dos vetos encendidos** (`b10`): "4 con
brevet, 2 minicurso y 1 snorkel" con 7 sabidos. El regex deduce el total de turno (3) **del
propio reparto** `{minicourse: 2, snorkel: 1}`, así que el reparto cuadra consigo mismo, el
veto no dispara y la invariante lo acepta. 4 personas fuera, en silencio.

**Arreglo del mecanismo, no del fraseo**: `supervisor._group_size_that_will_persist(intent,
state, message)` es ahora la única fuente de "qué total queda guardado" (la regla de escritura
única + `_GROUP_SIZE_CORRECTION_CUE_RE` que ya aplicaba `_apply_detected_intent`), y la usan
los tres sitios que razonan sobre el total: el guardado del estado, la invariante y el trigger
del veto de reparto. Además, la rama "el reparto amplía el total" ahora sube también el total
del **estado** (antes solo el del intent, y la escritura única lo dejaba en el valor viejo —
mismo criterio que `_merge_companion_activity`).

Cambia un test existente a propósito: `test_trigger_prefers_this_turns_total_over_the_
conversations` fijaba que el total del turno manda siempre; ahora solo manda cuando es una
corrección explícita.

### La batería, reescrita (`scripts/battery_group_allocation_gate.py`)

- Juzga el **estado final** del turno, no el intent: `m02` solo se ve en el estado.
- Variantes = los dos vetos (`sin_vetos`/`solo_reparto`/`solo_total`/`ambos`). La "puerta" que
  medía la versión anterior ya no existe.
- Familia nueva **total** (13 escenarios: frases de total no listadas, multi-turno, corrección
  explícita, controles) y total esperado por escenario → veredicto nuevo `TOTAL_MAL`.
- Una sola repetición mala ya cuenta como fallo (antes mandaba la mayoría).

A/B en PRE, mismo LLM y escenarios, código desplegado vs local (2 repeticiones):

| variante | beneficio OK | total OK | TOTAL_MAL | PARCIAL | alucinaciones |
|---|---|---|---|---|---|
| `ambos` (config PRE), desplegado | 6/10 | 12/13 | 0 | **1** | 0/10 |
| `ambos` (config PRE), **local** | **7/10** | 12/13 | 0 | **0** | 0/10 |
| `sin_vetos`, desplegado → local | 5 → 5 | 8 → 9 | 5 → 5 | **2 → 0** | 0 → 0 |

Por caso solo se mueven dos escenarios y los dos a mejor: `b10` PARCIAL → **OK** (el veto ya
dispara y el LLM completa `{certified_diving: 4, minicourse: 2, snorkel: 1}`) y `m02`
PARCIAL → OK. Riesgo y controles, idénticos. `b03`/`b04`/`b05` y `t05` siguen en VACIO (seguro:
el bot pregunta) — es la tarea 2.

### Tarea 4: los cutover medidos viven en el código

`llm_activity_veto_cutover` y `llm_group_size_veto_cutover` pasan a `True` por defecto, como ya
estaba `group_allocation`. Criterio único escrito en `config.py`: **un flag de cutover medido,
que decide respuestas, vive en el código**; los de shadow (solo loguean) siguen en el entorno.
Motivo: `.env.pre` no está en el repo, y cualquier entorno nuevo (PRO no existe todavía)
arrancaría con `TOTAL_MAL` en 5 de 33 escenarios. En PRE el efecto es nulo (ya estaban en
`True`).

Destapó 5 tests que dependían de que estuvieran apagados: los 2 de shadow-mode (ahora apagan el
cutover explícitamente) y 3 de `test_conversational_core.py` que solo simulaban `fill_gaps` —
con los vetos activos el turno va por la petición fusionada, así que ahora simulan también
`extract_and_verify`, igual que `test_invariant_runs_in_the_real_turn_path`.

### Tarea 3: `is_colombian` con trigger propio

`intent_detector.nationality_is_ambiguous(message)`: verdadero solo con **polaridad
contradictoria** — una negación reconocida y, fuera de su tramo, una afirmación ("dos somos
colombianos pero uno es extranjero"), o una afirmación con una negación suelta fuera de ella
("mi pareja es colombiana, yo no"). Reutiliza los mismos patrones que `_detect_nationality`
(elevados a `_NOT_COLOMBIAN_RE`/`_COLOMBIAN_RE`, sin cambio de comportamiento), sin fraseos
nuevos. "ninguno colombiano" — la negación compacta que el LLM confunde — **ya no dispara**.
`test_field_veto_generic_trigger_risk.py` se actualizó como pedía su propio docstring: ahora
fija que el LLM no se consulta en ese caso. **El flag sigue apagado.**

**Medido con el eval-set** (A/B por caso, tanda limpia y comparable las dos, código desplegado
vs local inyectado):

| | desplegado | local |
|---|---|---|
| `is_colombian` | 7/9 (78%) | **9/9 (100%)** |
| overall | 202/207 (97.6%) | **204/207 (98.6%)** |

Por caso solo cambian `hist-nationality-answer-must-not-fill-pending-safety` y
`...-pending-certification`, los dos "ninguno colombiano" donde el LLM pisaba al regex. Ningún
caso a peor. (El arnés aplica siempre el `should_verify` de cada campo, esté o no el flag, así
que el 78% del 2026-09-12 medía el veto con el trigger genérico — en PRE, con el flag apagado,
nunca llegó a un cliente.)

**Lo que este número NO dice**: ninguno de los 9 casos de nacionalidad del eval-set es ambiguo,
así que con el trigger nuevo el veto no se ejercita en ninguno y el 9/9 es el regex. Queda
probado que el trigger ya no estropea los casos claros; no que el veto acierte en los ambiguos.
Antes de plantear encender `llm_nationality_veto_cutover` hay que añadir al eval-set casos de
polaridad contradictoria (los de `tests/test_nationality_veto_trigger.py` son un buen punto de
partida) y medirlos.

### Cómo se midió sin desplegar

Un lanzador en el scratchpad antepone el código local en base64 y lo ejecuta con `exec` sobre
el `__dict__` del módulo ya importado dentro del contenedor (`intent_detector` antes que
`supervisor`), y luego corre la batería o el arnés sin cambios. No toca ficheros de código del
contenedor, y la misma batería sin inyección da el lado "desplegado" del A/B.

### Hallazgos de infraestructura

1. **LangSmith agotó su cuota mensual** ("Monthly unique traces usage limit exceeded", 274
   errores 429 en una sola pasada). PRE no está guardando trazas. No afecta a las respuestas
   ni a las mediciones (0 llamadas OpenAI degradadas), pero sin trazas no hay observabilidad.
2. **`docs/robustness/eval-set.json` no está dentro de la imagen** (no se copia `docs/`), así
   que `docker exec -i dp-pre-bot python3 -m scripts.run_extraction_eval` falla con
   `FileNotFoundError`. Se inyectó desde el lanzador.
3. **El fallback de la petición fusionada no existe en la práctica**: `_understand` dice "si la
   fusión degradó, se pide `fill_gaps` como siempre" comprobando `_combined_patch is None`,
   pero `extract_and_verify` captura sus errores y devuelve `({}, {})`, así que ante un fallo
   el turno se queda sin huecos rellenados. No se cambió: contra la misma API caída, una
   segunda petición fallaría igual y gastaría RPD. Queda anotado para decidirlo.

### Estado

Suite **1873 passed / 18 skipped**. ruff limpio en todo lo tocado (`test_conversational_core.py`
arrastra 7 avisos que ya estaban en `HEAD`, no se tocaron). Pendiente: desplegar y repetir
batería + eval-set desde la imagen; tarea 2 (reglas neutras para `fill_gaps`); tarea 5
(`padi_course`, decisión de producto); decidir sobre el flag de `is_colombian`.

## 2026-09-14 (tarde) — F2b medida, booleanos anclados por estructura, la tilde y recomendar al acompañante

### F2b: abrir el vocabulario de actividad en los prompts — medida, no aplicada

- **Extractor** (enum de `activity`, 8 → 15 valores): eval-set 212/216 frente a 211/216, pero
  por caso **no pasa**. Arregla `ambig-curso-padi-generico-no-se-bucear` y
  `f2b-specialty-mindful-en`, pero rompe dos casos deterministas en **otros campos** del mismo
  prompt de relleno: `prof-en-from-states` (`is_colombian=False` 3/3 → abstención 3/3) y
  `b08-ninos` de la batería de grupo (reparto vacío en las cuatro variantes). Mandar solo las
  propiedades pedidas arregla `is_colombian`, pero rompe `is_certified` en "no es que no
  estemos certificados, sí lo estamos, los 2".
- **Router** (`comparing_options`): opciones 6/9 → 9/9 con vocabulario más contexto, pero la
  base ya marcaba `comparing=true` en los tres casos nuevos y el núcleo solo lee ese booleano.
  No cambiaría ninguna respuesta, y alarga en cada turno un tool con otras 8 señales sin medir.
- Queda como infraestructura: `dom.bookable_activity_ids()`, 9 casos `f2b-*` y las variantes
  `vocab`/`vocab+ctx` de `battery_activity_choice.py`.

### F5a: los booleanos del LLM, anclados por la estructura del turno

El eval-set no pasa por las guardas del núcleo, así que su nota no ve lo que descartan. Medido
aparte con turnos reales de `_understand` sobre los 10 casos donde la guarda de tema no
respaldaba el valor correcto: **3/10 con guardas, 8/10 sin ellas**. Todo lo perdido eran
booleanos de apertura ("soy paisa", "ya soy sertificado", "tengo el AOWD").

La guarda sí protegía de algo real: con la ubicación pendiente, "Desde Cartagena" hace que el
LLM añada `is_colombian=True` 3/3. La cita literal no lo arreglaría ("Cartagena" está en el
mensaje). Lo que separa ese caso de "soy paisa" es que **contesta otra pregunta pendiente**.
`scripts/battery_boolean_anchoring.py` (14 × 3; los filtros se compararon sobre la misma
salida del LLM y después se midió la implementación):

| filtro | legítimos | alucinaciones evitadas |
|---|---|---|
| vocabulario (retirado) | 0/24 | 18/18 |
| sin guarda | 24/24 | 15/18 |
| hay otro slot pendiente | 15/24 | 18/18 |
| **el turno contestó otro slot pendiente (aplicado)** | **18/24** | **18/18** |

### "no está certificado" con tilde

`certification_claim("mi amigo no está certificado")` daba `True`: la negación escribía "esta"
sin tilde, así que caía en el catch-all `\bcertificado\b` y el detector ponía
`is_certified=True`. Texto y patrones se comparan ahora sin tildes; sobre 177 mensajes solo
cambia ese caso.

### F5b: guarda de actividad del acompañante

`detect_special_signals` con LLM real (16 frases × 3): **13/16 solo LLM, 7/16 con la guarda**.
La guarda tira 9 aciertos ("tiene el AOWD", "máscara y tubo", "bajar con tanque"…); los 3
fallos del LLM son frases sin actividad ("mi amigo no está certificado" → `minicourse`).
Variantes del prompt de señales (26 × 3): base 22, `undecided` 24, cita literal 15,
dos redacciones más 23 y 23, "elegida o inferida" 15 y 10. Ninguna evita suponer el minicurso.

**Decisión del owner:** no dar por hecho. Se recomienda según la situación y el cliente elige.
La guarda se queda y cambia **cómo se pregunta** (F6, abajo).

### F6: recomendar al acompañante en vez de preguntar "¿A o B?"

Cuando un acompañante no dijo qué quiere hacer, el bot ya no pregunta "¿minicurso o
snorkel?". Mismo slot pendiente, dos pasos:

1. Si no se sabe la estancia, pregunta "¿un solo día o varios días?" con botones. Si ya se dijo
   en la conversación, la usa.
2. Recomienda con descripción y botones: minicurso, snorkel y venir de acompañante (de
   `eligibility.beginner_options_for_age`), más el curso Open Water solo si se quedan varios
   días. El cliente elige por botón, número, nombre o texto libre.

"Acompañante" entra al registro (precio en `pricing.json`, sin servicios; fuera de los prompts
y de los productos de un día). El carrito cobra todo lo que sabe cobrar
(`dom.cart_activity_ids()`). Antes, un acompañante con Open Water o sin actividad se habría
perdido del carrito, y un curso de acompañante heredaba el servicio del principal.

Resolutores con LLM real (3 repeticiones), antiguo frente a nuevo:

- `companion_activity_choice`: **8/11 → 11/11**, sin empeorar los 6 casos de la batería. El
  antiguo **suponía snorkel 3/3** para "que solo nos acompañe en la lancha, no se mete al agua"
  y minicurso para "quiere sacarse la certificación". "lo que tú me recomiendes" sigue sin
  elegir por el cliente.
- `stay_duration` (nuevo): **6/6** ("el finde", "solo mañana", "3 noches", "aún no lo sé",
  EN).

Solo cambian esos resolutores en el snapshot de prompts (3 cambiados y 3 nuevos, frente a F4).
Suite **1961 passed / 18 skipped**.

### Tarea 7: repartos "no contables" — era la guarda de vocabulario

Los VACIO de `b03` "4 con titulo y 2 snorkel", `b04` "3 brevetados…" y `t05` "7 in total: 4
certified, 2 minicourse and 1 snorkel" **no eran del LLM**. Devolvía el reparto bien, pero
`_activity_has_textual_backing` no respaldaba "con titulo", "brevetados" ni "minicourse" en
inglés. Tiraba ese tramo, el reparto dejaba de sumar el total y
`enforce_group_allocation_consistency` lo descartaba entero.

Batería de grupo completa, configuración de PRE (dos vetos), 2 repeticiones, con y sin la guarda:

| | con guarda | sin guarda |
|---|---|---|
| beneficio | 7/10 | **9/10** |
| total | 12/13 | **13/13** |
| riesgo | 10/10 | 10/10 |
| PARCIAL / TOTAL_MAL / ALUCINA | 0 / 0 / 0 | 0 / 0 / 0 |

Riesgo nuevo, el caso que la justificaba (`r11`–`r13`: "mi amigo no esta certificado", "somos 2,
mi amigo no está certificado", "vamos 4 pero dos no tienen licencia"): 0 repartos inventados con
y sin guarda (3/3). Lo cubren la comprobación de cifras del texto y la invariante.

**Único cambio a peor, ambiguo:** `b05` "2 open water y 3 snorkel" pasa de VACIO a
`{certified_diving: 2, snorkel: 3}`. "2 open water" también se dice de dos buzos con esa
certificación. Pendiente de decisión del owner.

### Tarea 8: nacionalidad — la definición del campo y el regex en los ambiguos

El eval-set no tenía ningún caso ambiguo. Se añaden 3 con respuesta clara según la política
(colombianos **y residentes** pagan en COP): dos residentes extranjeros y "colombiano no, soy
venezolano". Los grupos mixtos no entran: los responde el supervisor con un mensaje propio.

Hallazgos con LLM real (3 repeticiones):

- **El prompt definía `is_colombian` como nacionalidad**, pero lo que decide es la moneda
  (política y pregunta del bot: "¿eres colombiano o residente?"). Regex y veto daban `False` a
  los dos residentes.
- **El regex elige mal justo en los ambiguos**: residentes → `False`, "colombiano no, soy
  venezolano" → `True`. El veto solo corregía el venezolano, y el flag está apagado.

Cambios: definición "colombiano **o residente**" en la verificación ES/EN y en
`EXTRACTION_TOOL`, y abstención del regex con polaridad contradictoria. El hueco lo rellena el
LLM en la misma petición.

- Los 3 ambiguos por la ruta real (regex abstenido + `fill_gaps`): **2/3** (antes 0/3). Sigue
  fallando "no soy colombiano pero vivo en colombia" (`False` 3/3).
- Eval-set con la definición nueva (119 casos, ejecución limpia): **214/219 (97,7 %)**, sin ningún
  caso a peor en el resto de campos. Esa ejecución es anterior a la abstención; solo esos 3
  casos son ambiguos y se midieron aparte.
- Grupos mixtos ("yo soy colombiano y mi novia extranjera"): `_MIXED_NATIONALITY_RE` no
  reconoce todos y el LLM elige un valor. Queda pendiente, con decisión de negocio.

### Tarea 9: `is_certified` con disparador propio (la regla común no siempre implica abstenerse)

La regla "polaridad contradictoria" de la nacionalidad pasa a una función común,
`polarity_is_ambiguous(message, negative, positive)`, que usa los patrones del propio detector.
`nationality_is_ambiguous` y la nueva `certification_is_ambiguous` son dos llamadas a ella.

Sin LLM, sobre el eval-set: 4 mensajes con polaridad de certificación contradictoria ("somos 3,
2 con open water y 1 no", "no es que no estemos certificados, si lo estamos, los 2", "hey we
arent certified, first time diving…", "Quiero el open water aunque no soy buzo certificado").
**El regex acierta en todos**, al revés que en la nacionalidad. Con LLM real (3 repeticiones)
sobre esos más dos extra, el veto coincide con el regex **6/6**.

Decisión: el detector **no** se abstiene en certificación. El veto de `is_certified` pasa del
disparador genérico (todo turno que resuelve el campo, el riesgo que documentaba
`test_field_veto_generic_trigger_risk.py`) al propio. Flag apagado: hoy no ganaría nada.
`location` sigue con el genérico, en shadow.

### Tarea 13: el fallback de la petición fusionada — decidido no tenerlo

`extract_and_verify` captura sus errores y devuelve `({}, {})`, así que `_understand` nunca
volvía a `fill_gaps` como decía su comentario: ante un fallo, el turno sigue solo con el regex y
el bot pregunta lo que falte. Se mantiene así: una segunda petición contra la misma API que
acaba de fallar fallaría igual y gastaría RPD, el recurso escaso. Solo se corrige el comentario
para que describa el comportamiento real. `fill_gaps` se sigue pidiendo si no hubo fusión o si
la fusión lanza una excepción inesperada.

### `location`: sin disparador propio por falta de casos

En los 176 mensajes del eval-set y las baterías **ninguno** nombra a la vez la ciudad y las islas,
así que no hay con qué medir una regla de ambigüedad. En 4 mensajes de prueba el regex acierta los
claros ("llegamos a cartagena y luego nos vamos a baru" → cartagena; Barú se cotiza como salida
desde Cartagena) y solo duda en "we're in cartagena now, staying on the islands tomorrow". Queda
pendiente: añadir antes casos así al eval-set. Sigue en shadow con el disparador genérico.

### Tarea 10: la carta de referido es un fallo de precio, no solo de vocabulario

"ya hice la teoria y la piscina en mi centro PADI y traigo la carta de referido para terminar el
open water" se resuelve como `padi_open_water`. En `services.json` el referido cuesta **474 USD**
(432 ya en las islas) frente a **693 USD** del Open Water (595,8 en las islas): el bot cotizaría
**219 USD de más**.

No se arregla hoy con los mecanismos existentes:
- el veto de `activity` solo dispara con 2+ categorías (`_activity_should_verify`) y este mensaje
  tiene una sola (curso);
- aunque disparara, `EXTRACTION_TOOL` no tiene `padi_open_water_referral` en el enum, y abrirlo
  rompía otros campos del mismo prompt (F2b).

Pendiente de diseño medido. Idea a evaluar: cuando la actividad resuelta tiene **hermanas en el
registro** (misma familia y nivel, como Open Water y su referido), elegir entre ellas con un
resolutor acotado al estilo de `course_level` (F4), no con el extractor general.

Segundo hueco del referido: en `activities.json`, `padi_open_water_referral` tiene
`cart_type: null`, así que aunque se detectara bien **el carrito no sabría cobrarlo**
(`dom.cart_activity_ids()` lo excluye), igual que pasaba con el acompañante antes de F6. Las
"hermanas" sí se pueden derivar del registro sin listas: misma `family` (`course`) y mismo
`course_level` (1) que `padi_open_water`. Decisión de producto previa: ¿el bot pregunta si
trae carta de referido cuando alguien pide el Open Water, o solo lo detecta si lo dice?

### Decisiones del owner (2026-09-14, tarde) y lo aplicado

1. **Carta de referido: solo si el cliente lo dice, y entonces con el asesor.** Ver la sección
   del referido más abajo.
2. **"2 open water" / "advanced" dentro de un reparto**: el bot debe hacer una pregunta
   aclaratoria (¿ya certificados o quieren certificarse?). **Pendiente de implementar.**
3. **"somos 3, uno no está certificado"**: se recomiendan opciones, no se asume minicurso.
   **Pendiente**: el eval-set aún espera `{certified_diving: 2, minicourse: 1}` y el flujo de
   recomendación (F6) solo se dispara para acompañantes detectados por la señal.
4. **Grupo de nacionalidad mixta: USD para todo el grupo.** Aplicado en
   `_mixed_nationality_response` (texto y `is_colombian=False`). Sigue dependiendo de que
   `_MIXED_NATIONALITY_RE` reconozca el grupo ("yo soy colombiano y mi novia extranjera" no lo
   reconoce).

### Curso referido: preparado sin tocar prompts; la detección, medida y revertida

Aplicado (sin cambios de prompt, snapshot idéntico):
- `cart_render._is_contact_only_service` lee `contact_only` de `services.json` (antes
  `== "divemaster"` a mano). `referral` y `referral_already_on_island` pasan a `contact_only`:
  si el cliente acaba en el referido, se cierra con el asesor, sin link.
- En el registro, el referido tiene `cart_type: "course"` y `offer: false`: el carrito lo cobra,
  pero nunca se ofrece ni aparece en `course_level` (opciones del núcleo ni enum del resolutor).
- `dom.sibling_ids()`: hermanas = misma familia y `course_level`. Hoy solo Open Water ↔ referido.

Probado con LLM real y **revertido**:
1. **Abstención del regex** en actividades con hermanas: rompía 11 tests. Con el LLM
   simulado sin respuesta, "quiero el open water" se quedaba sin actividad; si el LLM falla
   se perdería el Open Water. Descartado sin gastar eval-set.
2. **Veto de actividad disparado por hermanas**, con `padi_open_water_referral` en el enum del
   extractor y glosa "solo si dice que trae carta de referido…". Eval-set **213/219** frente a
   214:
   - arregla `f2b-referral-es`;
   - rompe `adv-en-negation-contraction` ("hey we arent certified, first time diving…":
     minicourse → padi_open_water), probablemente por la glosa que nombra `padi_open_water`;
   - rompe `split-open-water-one-not` ("somos 3, 2 con open water y 1 no": → certified_diving,
     el caso ambiguo que el owner quiere aclarar con una pregunta).

Siguiente intento: glosa del referido que no nombre `padi_open_water` y medir solo el veto de
hermanas. O un resolutor acotado Open Water/referido que solo se dispare si el mensaje habla de
haber empezado el curso en otro centro, decidido por el LLM, no por palabras.

## 2026-09-15 — Centralización: sin código duplicado (owner: "hay que ser óptimos")

### Hecho y desplegado

- **Precios** (`src/utils/money.py`): una sola fuente para `usd`, `cop` y `usd_cop`, en lugar
  de cinco formateadores (RAG, catálogo, carrito, refresher, resumen colombiano). El COP ya no
  sale en dos formatos ("COP 1.260.000" y "630.000 COP"): ahora siempre "630.000 COP".
- **Quitatildes**: todo usa `src/utils/text.strip_accents`; borradas las copias del supervisor,
  rag_agent y cart_render.
- **Edades mínimas**: `eligibility` y el detector leen `min_age`/`max_age` del registro.
- **Carrito derivado del registro**: `_cart_item`, `_cart_label_for` y `_cart_service_id` ya
  no tienen una rama por actividad (tipo = `cart_type`, servicio = `services`, etiqueta =
  `texts.price_label`). Servicios idénticos a los de antes en las 12 combinaciones tipo ×
  ubicación. Etiquetas que pasan a las del registro: "Minicurso de buceo" y "Acompañante (no
  bucea ni hace snorkel)".
- Sin cambios de prompt (snapshot idéntico). Suite 1997 passed.

### Inventario de listas de vocabulario (78 regex de módulo en `src`)

Por fichero: supervisor 27, núcleo 22, detector 15, rag_agent 11, grounding_check 2,
lead_summary 1. Agrupadas por concepto:

| concepto | listas | ¿duplicado real? |
|---|---|---|
| mención de otra persona / acompañante | núcleo `_ADDED_PERSON_RE`, `_MENTIONS_PERSON_RE`, `_SINGULAR_COMPANION_RE`, `_PLURAL_COMPANION_RE`, `_BARE_HEADCOUNT_RE`, `_NOT_ALONE_RE`, `_COURSE_SOLO_RE`; rag `_MENTIONS_COMPANION_RE`, `_NON_DIVER_*` (4), `_COMPANION_PLURAL_QUANTIFIER_RE`; supervisor `_PURE_COMPANION_RE`, `_GROUP_RECOMPOSE_RE` | **sí**: ya comparten `_PERSON_NOUN_*` del detector, pero hay tres familias de patrones para la misma pregunta |
| certificación | detector `_CERTIFIED_PATTERNS`, `_NOT_CERTIFIED_PATTERNS`; núcleo `_STRONG_CERTIFIED_DIVING_RE`; rag `_ALREADY_CERTIFIED_RE`, `_WANTS_CERT_EXCLUDE_RE`; supervisor `_CERTIFIED_MENTION_RE`, `_INACTIVE_MENTION_RE`, `_UNCERTIFIED_COMPANION_NOTE_RE` | **parcial**: las del supervisor operan sobre notas parafraseadas por el LLM (dominio distinto, documentado); las de rag y núcleo sí repiten a `certification_claim` |
| mención de actividad o producto | detector `_CERTIFIED_DIVING_PATTERNS`, `_MINICOURSE_PATTERNS`, `_SNORKEL_PATTERNS`, `_PADI_COURSE_PATTERNS`, `_SPECIALTY_PATTERNS`; núcleo `_EXPLICIT_MINICOURSE_NAME_RE`, `_COURSE_MENTION_RE`; rag `_OVERVIEW_BARE_WORD_RE` | **sí**: los nombres de producto deberían salir del registro (labels + vocabulario por actividad) |
| ubicación | núcleo `_CARTAGENA_RE`, `_ISLAND_RE`, `_HOTEL_UNKNOWN_RE`, `_LOCATION_DEFER_RE`; detector `_detect_location` en línea | **sí** para Cartagena/isla |
| nº de inmersiones / paquete | detector `_CERT_DIVE_COUNT_RE`, `_BARE_PACKAGE_DIVE_RE`, `_CERT_DAY_COUNT_RE`; núcleo `_CONFIRMS_DESCRIBED_PACKAGE_RE`, `_PACKAGE_DIVE_COUNT_IN_TEXT_RE` | revisar |
| nacionalidad | detector `_NOT_COLOMBIAN_RE`, `_COLOMBIAN_RE`; supervisor `_MIXED_NATIONALITY_RE`, `_SAME_PRICE_DIFFERENT_NATIONALITY_RE` | parcial (el grupo mixto podría derivarse de `polarity_is_ambiguous` + persona) |
| disponibilidad | supervisor `_AVAILABILITY_PATTERN`, `_AVAILABILITY_RE` | **no**: van al mismo handler con condiciones distintas medidas (la ampliada no se aplica mientras se construye la reserva; "¿algo para más días?" es plan, no cupo) |
| nombre / presentación | núcleo `_NAME_TRIGGER_RE` (+ stoplist); supervisor `_NAME_INTRO_RE`, `_INTRO_PHRASE_RE` | **no del todo**: uno captura el nombre, el otro decide un reinicio de conversación y es sensible a mayúsculas a propósito ("soy Sofía" frente a "soy certificado") |
| actos de diálogo | núcleo `_DELIBERATION_RE`, `_COMMITMENT_RE`, `_SWITCH_TO_*`; supervisor `_INFO_QUESTION_STARTER_PATTERN`, `_GENERAL_INTEREST_PATTERN`, `_BOOKING_PROCESS_QUESTION_RE`, `_BARE_AFFIRMATION_RE`, `_ADVISOR_OFFER_RE`, `_OFFER_VERB_RE`, `_GREETING_START_RE` | candidatos a la señal LLM del router (ya existe `comparing_options`) |
| seguridad / sensibles | supervisor `_ADAPTIVE_DIVING_PATTERN`, `_DIVE_TO_HEAL_OVERRIDE_RE`, `_ALCOHOL_BEFORE_DIVING_RE`, `_ALLERGY_WORD_RE`, `_FOOD_ALLERGEN_RE`, `_PRIVATE_GROUP_EVENT_RE`, `_AI_IDENTITY_RE`, `_CLOSED_DATE_RE` | no: cada uno es una política distinta |

Orden propuesto (de más a menos riesgo de fallo por vocabulario): actividad/producto desde el
registro → mención de persona → certificación en rag/núcleo sobre `certification_claim` →
ubicación → paquete. Cada paso: comparación antes/después sobre los mensajes del eval-set y
de las baterías, sin LLM, más la suite completa.

**Certificación en el RAG: no se fusiona a ciegas.** `rag_agent._mentions_already_certified`
(`_ALREADY_CERTIFIED_RE` y no `_WANTS_CERT_EXCLUDE_RE`) frente a `certification_claim`, sobre
202 mensajes (eval-set, rag-eval-set, baterías y variantes): **34 discrepancias en los dos
sentidos**.
- La del RAG da "ya certificado" a "no soy buzo", "no soy certificado, es mi primera vez" y
  "Quiero el open water aunque no soy buzo certificado".
- `certification_claim` no reconoce "tengo el open water", "ya tengo el rescue diver" ni "i
  have my open water", y da `True` a "quiere sacarse la certificación de buceo".

Sustituir una por otra movería respuestas en ambos sentidos, y tapar los huecos sería añadir
vocabulario. Además `rag_answer` solo recibe la pregunta y `extra_context` (texto), no el
estado, así que usar lo ya extraído obliga a cambiar la firma en sus tres llamadas (núcleo,
info_agent, supervisor), y aun así la primera pregunta de una conversación no tiene estado.
Pendiente de diseño: una sola fuente de "¿afirma/niega certificación?" que resuelva los dos
tipos de error sin crecer por vocabulario.

### Curso referido v2: detectado sin empeorar el eval-set

Glosa del referido reescrita para describirlo sin nombrar `padi_open_water` ("trae la carta de
referido firmada, o ya hizo la teoría y la piscina en otro centro PADI y viene a terminar las
inmersiones"), referido de nuevo en el enum y veto de actividad disparado por hermanas.

Eval-set, ejecución limpia: **214/219 (97,7 %)**. Por caso, frente a la ejecución anterior:
- arregla `f2b-referral-es` (referido) y `nat-venezolano-niega-y-afirma-otra` (por la
  abstención del regex de la tarea 8);
- `adv-en-negation-contraction` ("first time diving") vuelve a acertar: el v1 lo rompía y la
  causa era la glosa que nombraba al Open Water;
- `split-open-water-one-not` ("somos 3, 2 CON open water y 1 no") pasa a `certified_diving`.
  La expectativa esperaba `padi_open_water` pero pedía `{certified_diving: 2, minicourse: 1}`
  como reparto: era incoherente. "2 con open water" es tener la certificación; se corrige;
- sigue fallando `nat-residente-no-colombiano-vive-en-colombia` (el LLM da `False`; conocido
  desde la tarea 8).

Snapshot: cambian exactamente los 13 prompts de actividad (enum + glosa).

### Decisión 2 del owner: "¿ya certificados o quieren certificarse?" — análisis previo

Owner: cuando se nombra un nivel que también es una certificación ("2 open water y 3 snorkel",
"3 advanced"), el bot pregunta si ya lo tienen o quieren sacárselo, en lugar de suponer.

Sin LLM (detector actual):

| mensaje | categorías | `certification_claim` | lectura |
|---|---|---|---|
| "2 open water y 3 snorkel" | curso + snorkel | — | **ambiguo** (el LLM reparte `certified_diving: 2`, batería b05) |
| "hola somos 4 open water" | curso | — | **ambiguo** (el regex resuelve el curso Open Water) |
| "2 advanced and 2 snorkel" | curso + snorkel | — | **ambiguo** |
| "somos 3, 2 con open water y 1 no" | curso | `True` | claro: certificados |
| "tengo el open water" | curso | — (el detector pone `is_certified=True`) | claro: certificado |
| "we are 2 open water divers" / "somos 2 buzos open water" | curso (+ buceo) | `True` | claro: certificados |
| "quiero el open water" / "quiero hacer el advanced" | curso | — | claro: curso |

Los ambiguos y "quiero el open water" dan las mismas señales deterministas: distinguirlos exige
entender el verbo, así que tiene que decidirlo el LLM, no una lista.

Diseño propuesto, a medir antes de aplicar:
1. Medir primero si el LLM rellena `is_certified` en esos mensajes ("quiero el open water" →
   `False`; "somos 4 open water" → `True` o abstención).
2. Slot nuevo "¿ya tienen el <nivel> o quieren sacárselo?" solo cuando, **después** de la
   extracción, hay un nivel de curso certificable nombrado y `is_certified` sigue sin resolver.
   Es la misma regla de "si no lo sabemos, se pregunta".
3. En repartos, un tramo nombrado solo por el nivel ("2 open water") no se asume
   `certified_diving`: se marca para aclarar, igual que `undecided`.

Medición: eval-set completo + batería de grupo (b05) + sonda de los mensajes de la tabla.

### Decisión 3 del owner: personas del grupo sin actividad elegida → recomendar opciones

Punto de partida, medido con LLM real:
- `fill_gaps` repartía "somos 3, uno no está certificado" como `{certified_diving: 2, snorkel: 1}`
  (**snorkel supuesto**, 3/3).
- El regex asignaba **minicurso** al tramo en "2 con open water y 1 no", "uno no está
  certificado" y "5 certificados y 2 principiantes".

Diseño (sin vocabulario nuevo):
1. **LLM**: la descripción de `group_allocation` en `EXTRACTION_TOOL` pide la clave `undecided`
   para quien solo se describe sin actividad (p. ej. "no está certificado"). Solo cambia ese tool
   (snapshot: 1 prompt).
2. **Regex**: el tramo no certificado es `minicourse` solo si su propio texto lo nombra
   (`matched_activity_categories` devuelve `minicourse` para "dos minicurso" o "2 bautismo", y
   nada para "1 no", "2 principiantes" o "sin certificar"); si no, `undecided`.
3. **Núcleo**: en el bloque del reparto del LLM se valida la cifra de `undecided` contra el texto
   y se completa el grupo principal por aritmética (total − sin decidir − otros tramos). Un punto
   único, `_take_undecided_members`, después de la invariante de la suma, saca `undecided` del
   intent final (regex o LLM), guarda `pending_undecided_qty` y marca la recomendación de F6. Al
   elegir, `_merge_pending_undecided` fusiona con esa cantidad sin preguntar "¿cuántos?".

Medición (tanda limpia):
- Primera versión (solo LLM): eval-set 210/219, porque el regex seguía asignando minicurso.
  Batería: r13 salía "parcial" porque la batería no sabía de pendientes (se le enseñó).
- **Versión final**:
  - eval-set **213/219**; reparto de nuevo al 91 %; el único caso nuevo que falla es la
    actividad de "two have open water and one does not", cuya expectativa se cambió a mano;
  - batería de grupo, config PRE: **beneficio 10/10** (antes 9/10), total 13/13, riesgo 12/13,
    0 parciales, 0 inventados (r13 queda vacío: el bot pregunta, igual que antes, sin asumir);
  - sonda en `_understand`: 4 de 5 frases acaban `{certified_diving: 2}` + 1 pendiente de
    recomendación; "somos 4 y dos no tienen licencia" sigue sin reparto.

Pendiente: frases con el tramo en plural sin cifra delante del atributo ("dos no tienen licencia"
tras "somos 4") y el texto de la recomendación de F6, que sigue diciendo "acompañante".

### Decisión 2 del owner: pregunta aclaratoria "¿ya tienen esa certificación o quieren sacarla?"

Aplicada con una señal estructural en lugar de depender de lo que rellene el LLM:
`course_level_is_ambiguous(message)`. Da ambiguo cuando se nombra un nivel PADI (`_CERT_LEVEL`) y
no se cumple nada de esto:
- se quiere (`_WANTS_CERT_RE`);
- se tiene (`_HOLDS_CERT_RE`);
- se nombra el producto con el sustantivo del catálogo ("curso"/"course", **derivado** de las
  etiquetas de los cursos con nivel del registro);
- afirma o niega certificación (`certification_claim`).

Con esa señal, `_flag_cert_or_course` descarta la certificación supuesta del turno y marca
`needs_cert_or_course`; `next_missing_slot` pregunta antes de cotizar. La respuesta, por botón,
número o texto libre (resolutor `cert_or_course`), deja buceo certificado o el curso nombrado.

Sonda con LLM real (2 repeticiones por caso):
- **cuándo pregunta 10/10**: sí en "hola somos 4 open water", "2 open water y 3 snorkel" y "2
  advanced and 2 snorkel"; no en "quiero el open water", "quiero hacer el advanced", "I'd like to
  take the advanced course", "tengo el open water", "we are 2 open water divers", "somos 3, 2 con
  open water y 1 no" ni "quiero bucear, somos 2". La primera versión (sin el sustantivo del
  catálogo) daba 9/10: preguntaba de más en "I'd like to take the advanced course".
- **resolutor 7/7**: "sí, ya somos buzos", "ya lo tenemos desde hace años", "queremos hacer el
  curso", "no, queremos sacárnoslo aquí", EN, y abstención ante "no sé, lo que me recomiendes".

Snapshot: solo aparecen los 3 prompts nuevos del resolutor. No se repitió el eval-set ni la batería
de grupo: el arnés no pasa por el núcleo y la regla no cambia repartos.

### Ajustes tras la decisión 3

- **Texto de la recomendación** (`ask_slot` de `companion_activity_choice`): con
  `pending_undecided_qty` habla a "quien no está certificado" o "quienes no están certificados",
  en singular o plural según la cantidad, en lugar de a "tu acompañante"; lo mismo en el paso de
  "¿un día o varios?".
- **Regla "N no están certificados" sin tildes**: `m_not_cert_only` se comparaba con "esta[nb]"
  sin tilde. Ahora busca sobre `strip_accents(message)`. Foto antes/después del detector sobre 192
  mensajes (eval-set, baterías y 5 variantes): **solo cambian las 4 variantes con tilde**, las
  cuatro al reparto esperado (p. ej. "somos 5, dos no están certificados" →
  `{certified_diving: 3, undecided: 2}`).

### `location`: medido con casos de ciudad + islas — sin cambios

Se añadieron al eval-set 4 casos que nombran la ciudad y las islas (123 casos en total). Sin LLM,
el regex acierta 3/4. Con la verificación de `location` (hoy en shadow), 3 repeticiones:

| mensaje | esperado | regex | con verificación |
|---|---|---|---|
| "llegamos a cartagena y luego nos vamos a baru" | cartagena | cartagena | 3/3 |
| "estoy en cartagena pero el hotel es en isla grande" | island | island | 3/3 |
| "salimos desde cartagena, no estamos en las islas" | cartagena | cartagena | 3/3 |
| "we're in cartagena now, staying on the islands tomorrow" | island | cartagena | **0/3** |

La verificación no estropea los claros, pero tampoco arregla el ambiguo, así que un disparador
propio no ganaría nada. Preguntar siempre que aparezcan ciudad e islas añadiría preguntas en los
dos claros que hoy salen bien. **Sin cambios**: `location` sigue en shadow. El caso ambiguo queda en
el eval-set como hueco conocido.

### Centralización: nombres de curso con una sola fuente

Primer paso del orden propuesto en el inventario ("actividad/producto desde una fuente").
Había dos vocabularios de curso → id que no coincidían:
- **Detector**: subcadenas en cadena if/elif ("open water" antes que "advanced": "quiero hacer
  el advanced open water" salía **Open Water**).
- **Núcleo** (`_COURSE_MENTION_RE`): variantes que el detector no conocía ("owd", "aowd",
  "avanzado", "rescate", "enriched air").

Ahora hay una tabla única en el detector, `_COURSE_NAME_PATTERNS` / `courses_mentioned`, en el
orden del registro, que usan los dos. Las especialidades por palabra suelta ("peces", "fish") no
entran: solo cuentan con el contexto de "especialidad".

`_distinct_course_levels` descarta un nombre que solo aparece dentro de otro curso nombrado. El
nombre compuesto sale de la etiqueta del registro sin el sustantivo del catálogo ("Advanced Open
Water course" → "advanced open water"). Si quedan varios, se conserva el orden del registro.

Foto del detector y del núcleo antes/después sobre 202 mensajes (eval-set, baterías y
variantes de curso):
- Primer intento, "el nivel más alto nombrado": 5 cambios. Arreglaba "advanced open water",
  pero también cambiaba 4 dudas entre dos cursos ("open water o advanced" → Advanced): otra
  suposición.
- **Versión final: 1 cambio**, "advanced open water" → `padi_advanced`. Cursos mencionados y
  ofertas del núcleo, idénticos.

### Centralización: listas de "mención de otra persona"

Paso 2 del orden del inventario. Qué contesta cada lista:
- **Núcleo**: son preguntas distintas, no duplicados. `_ADDED_PERSON_RE` (alguien se suma),
  `_MENTIONS_PERSON_RE` (se menciona a otra persona), `_SINGULAR_COMPANION_RE` /
  `_PLURAL_COMPANION_RE` (uno o varios) y `_BARE_HEADCOUNT_RE` (conteo "para 2 personas"). Ya
  comparten los sustantivos de `_PERSON_NOUN_*`.
- **RAG**: `_NON_DIVER_*` detecta acompañantes que no bucean, un concepto propio del resumen del
  RAG. Sí había un duplicado: `_mentions_plural_companions` repetía en línea el patrón de
  `_MENTIONS_COMPANION_RE`.
- **Supervisor**: `_GROUP_RECOMPOSE_RE` / `_apply_group_recomposition` era **código muerto**:
  solo lo llamaban sus tests, como ya decía el inventario del 2026-09-03.

Aplicado:
- Borrado el código muerto (103 líneas: `_PERSON_NOUN`, `_GROUP_RECOMPOSE_RE`,
  `_apply_group_recomposition`, `_GROUP_COUNT_WORDS`), `tests/test_group_recomposition.py` y
  dos imports que solo usaba ese código.
- `_mentions_plural_companions` reutiliza `_MENTIONS_COMPANION_RE`.

Medido y **no** aplicado: la jerga plural ("parceros", "cuates", "panas", "carnales", "compas"…)
vive solo en `_PLURAL_COMPANION_RE`. Llevarla a `_PERSON_NOUN_PLURAL_ES` (lista compartida)
cambió 1 de 200 mensajes en la foto: "somos 4, dos panas y yo buceamos" pasó de total 4 a **3**
(el conteo del detector sumó "dos panas y yo" y pisó el "somos 4"). Revertido: ahí la jerga solo
decide singular o plural. Foto final antes/después: **0 cambios** en 200 mensajes. Suite 2009
passed (18 tests menos: los del código borrado).

### Centralización: una definición por campo en los prompts

`is_certified`, `location` e `is_colombian` tenían su definición en tres sitios: descripción del
tool (EN), `_FIELD_RULES_EN` y `_FIELD_RULES_ES`. Ya divergían:
- la guía ES tenía ejemplos que el tool y la EN no ("llevo el rescue", "tengo el título de
  buceo", "soy paisa", "soy rolo");
- `location` decía "only set it when the message gives a real place signal" en el tool y "the
  business operating in Cartagena is NOT a signal" en la guía.

Ahora hay `_FIELD_MEANING_EN` / `_FIELD_MEANING_ES` con la unión del contenido. La descripción del
tool es el significado EN y las guías se construyen con `_meaning_rule(field, lang)`. Se borraron
los literales viejos. Snapshot: 7 prompts cambiados (tool y verificaciones de esos campos; las
guías ES de `is_certified`/`is_colombian` no cambian porque ya eran las más completas).

Medido (tanda limpia):
- eval-set **217/223** (con los 4 casos de ubicación). Por caso, frente a la tanda anterior:
  **arregla `nat-residente-no-colombiano-vive-en-colombia`** (nacionalidad 12/12); falla el caso
  ambiguo de ubicación ya documentado; ninguno a peor;
- batería de booleanos anclados idéntica: legítimos 18/24, alucinaciones evitadas 18/18.

Siguen aparte, a propósito, `group_size`, `group_allocation` y `activity`: su descripción en el
tool lleva reglas medidas una a una (plural vago, `undecided`) que las guías no tienen. Unificarlos
exige reconciliar ese contenido y medirlo aparte.

### Reparto y actividad coherentes en "2 con open water y 1 no"

Los dos casos del eval-set que seguían fallando en actividad (`split-open-water-one-not`,
`split-en-have-open-water`) venían de una contradicción dentro del propio detector:
- la regla de reparto leía "2 con / two have open water" como certificación que **tienen**
  (`{certified_diving: 2, undecided: 1}`);
- la rama de cursos, que va antes, había dejado `activity = padi_open_water`.

Regla nueva al final de `detect()`: si la actividad es un curso con nivel, el reparto trae
`certified_diving` y el mensaje no casa `_WANTS_CERT_RE`, la actividad es `certified_diving`. Sin
vocabulario nuevo.

Foto del detector antes/después sobre 197 mensajes: **3 cambios, los esperados**: los dos del
eval-set y "somos 4, dos con advanced y dos no". Controles sin cambio: "quiero el open water, somos
3 y 2 no estan certificados" (quiere el curso) y "hola somos 4 open water" (ambiguo, se pregunta).

### Un producto nombrado gana a la palabra genérica de buceo

Sonda sin LLM: en 7 de 10 mensajes que combinan "buceo/diving" con un curso o especialidad
nombrados, el detector daba `certified_diving`. `_detect_activity` probaba
`_CERTIFIED_DIVING_PATTERNS` ("buce*", "diving") antes que `_PADI_COURSE_PATTERNS` y
`_SPECIALTY_PATTERNS`. El veto de actividad (2+ categorías) solo lo podía arreglar en cursos:
el enum del extractor no tiene especialidades concretas.

Cambio: curso y especialidad se prueban antes que el buceo genérico. El minicurso sigue primero y
se conserva la excepción `_holds_padi_cert` ("ya tengo el open water").

Foto del detector sobre 208 mensajes: **12 cambios**.
- 9 mejoras claras: especialidades concretas y cursos con "buceo" ("el curso open water de buceo",
  "Quiero sacarme el open water, no he buceado nunca", "soy buzo certificado y quiero hacer el
  advanced"…).
- "Pues me gustaría sacarme el primer nivel de buceo": de `certified_diving` (mal) a `padi_course`
  (el núcleo aclara el nivel o aplica Open Water a quien no está certificado).
- "2 open water y 3 snorkel": de snorkel a curso (caso ambiguo, que ahora se pregunta).
- "ya llevo el rescue, quiero seguir buceando": el regex pasa a `padi_rescue`, pero tiene 2
  categorías y el veto lo corrige a `certified_diving`.

Eval-set, con este cambio y el de reparto/actividad: **219/223 (98,2 %)**, actividad 71/72, sin
ningún caso a peor. Queda `f2b-specialty-mindful-en`: el regex ya da `specialty_mindful_diving`,
pero el veto, cuyo enum solo tiene `padi_specialty`, lo generaliza.

### El veto de actividad no generaliza lo que el cliente nombró

`f2b-specialty-mindful-en` ("I'd like to do the mindful diving specialty"): el regex ya daba
`specialty_mindful_diving`; el mensaje toca 2 categorías, el veto dispara y el LLM, cuyo enum solo
tiene `padi_specialty`, lo cambiaba por la genérica. Regla desde el registro
(`_veto_would_generalize`): si la corrección propuesta es la genérica de la **misma familia** de
una actividad concreta, no es corrección. Las correcciones reales siguen aplicando ("ya llevo el
rescue, quiero seguir buceando" → buceo certificado).

Hallazgo de medición: el eval-set aplicaba las discrepancias por su cuenta
(`combined.update(disagreements)`), así que la primera tanda con la regla dio lo mismo (219/223):
el script no pasaba por el punto de decisión del producto. Ahora los dos usan
`supervisor.valid_veto_corrections`.

### Alcance de la negación en `certification_claim` y "N inmersiones"

Sonda sin LLM: "2 no tienen certificación", "two aren't certified", "no tenemos certificación",
"we aren't certified divers" y "no tengo licencia de buceo" salían **certificado**: el patrón
positivo casaba dentro de la negación. Añadir cada frase negativa era el parche que no queremos.
Regla general: una afirmación precedida de cerca (hasta dos palabras) por no/not/n't/nunca/never/
sin/without no cuenta, y la cadena de negaciones se cuenta por paridad ("no es que no estemos
certificados" sigue siendo sí; la primera versión sin paridad lo rompía y se vio en la foto). La
puntuación corta el alcance ("no, ya soy certificado" sigue siendo sí).

"quiero hacer 2 inmersiones" / "want to do 3 dives" daban actividad `None` aunque
`_detect_cert_dive_count` leía la cantidad: la regla que ya ponía buceo certificado cuando hay
certificación sin actividad usa también la cantidad de inmersiones.

Foto del detector sobre 207 mensajes (eval-set, las tres baterías y sondas): **7 cambios, todos
los buscados**; ningún mensaje del eval-set ni de las baterías cambia. Sin resolver:
"somos 4 y dos no tienen licencia" sigue sin reparto (el patrón de reparto no conoce "licencia").

Eval-set con las dos reglas de arriba (el veto que no generaliza, ya con el filtro compartido, y
el alcance de la negación): **220/223 (98,7 %)**, tanda limpia. Diferencia por caso con la tanda
anterior: **solo `f2b-specialty-mindful-en` pasa a OK**, sin ningún caso a peor. Quedan
`loc-en-cartagena-now-islands-tomorrow` (ambiguo) y dos casos con historial que el script no pasa
por el núcleo. Nota operativa: sin `ENV_FILE=.env.dev` el script corre sin clave y **todas** las
llamadas degradan; el propio script lo marca como tanda no comparable.

### "N no están certificados" con la misma fuente de certificación

El reparto `{certified_diving: resto, undecided: N}` tenía su propio patrón, que solo conocía
"cert*". "somos 4 y dos no tienen licencia", "dos no son buzos" o "2 sin certificar" quedaban sin
reparto, y "we are 4 and two are not certified" repartía 3/1. Ahora la frase que sigue a cada
cantidad, hasta puntuación o conjunción, se juzga con `certification_claim`: la misma fuente que
`is_certified`, con su alcance de negación. Dos huecos de conjugación en las listas únicas, no
frases nuevas: "tener licencia" solo existía como "tengo"/"tenemos" (ahora también "tiene(n)"), y
`_WANTS_CERT_RE` conjugaba `certificar(me|nos)` pero no `te|se`, como ya hacía la lista negativa.
Quien "quiere certificarse" ya eligió y no se marca como pendiente.

Foto del detector sobre 219 mensajes: **10 cambios**. Del corpus solo cambia "vamos 4 pero dos no
tienen licencia", que pasa a lo que la batería de grupo ya esperaba (2 certificados y 2 sin
decidir); el resto son sondas nuevas y todas mejoran. No se volvió a correr la batería: el regex da
ya exactamente el reparto esperado. Visto y pendiente: "somos 5 y 2 nunca han buceado" reparte 3/2,
pero la actividad sigue siendo minicurso, que es una suposición anterior del detector ("nunca he
buceado" → minicurso).

### Respuesta doble tras F5a: analizado, sin arreglo determinista

"desde cartagena, somos paisas" con la ubicación pendiente pierde `is_colombian`, porque la guarda
(b) descarta el booleano que viaja con la respuesta a otra pregunta. Idea estudiada: separar la
frase que contesta al slot del resto del mensaje y aceptar el booleano solo si queda resto. No
sirve sin LLM:
- el regex localiza "desde cartagena", pero no "salimos de bocagrande";
- tampoco ve el booleano en "somos paisas" ni en "ya tenemos el AOWD", que llegan del LLM;
- un resto de cortesía ("desde cartagena, gracias") dejaría pasar justo la alucinación que la
  guarda evita (18/18).

La salida general sería que el propio extractor diga en qué parte del mensaje apoya cada booleano,
en la misma petición. Es un cambio de prompt y hay que medirlo con la batería de booleanos
(escenarios nuevos: "desde cartagena, gracias", "desde cartagena, vale"). Queda en cola; mientras
tanto sigue el coste conocido: una pregunta de más, nunca una reserva equivocada.

### Grupo con nacionalidades mixtas en la definición del campo: medido y revertido

Idea: la decisión del owner (grupo mixto → USD) equivale a `is_colombian=false`, así que se añadió a
la definición única del campo ("un grupo que mezcla colombianos o residentes con extranjeros paga
todo en USD: false"). Foto de prompts: cambiaban solo los 5 que llevan esa definición. Eval-set con
7 casos nuevos (6 mixtos y 1 control), 130 casos: **221/230**.
- **Rompe** "no soy colombiano pero vivo en colombia" (OK → False): el LLM lo lee como grupo mixto.
- De los 6 mixtos solo acierta "dos somos colombianos pero uno es extranjero", que el regex ya
  reconocía. Con "yo soy colombiano y mi novia extranjera" y "mi esposa es colombiana y yo no", el
  LLM sigue diciendo True.
- "somos colombianos pero mi amigo es aleman" y "i'm colombian but my girlfriend is from spain": el
  regex da True sin ambigüedad (no conoce gentilicios extranjeros) y el LLM ni se consulta.

Revertido. Los 7 casos se quedan en el eval-set como medida del hueco. La batería de booleanos se
paró a medias para no gastar peticiones en un prompt descartado. Conclusión: un booleano no
distingue "residente" de "grupo mixto". Hace falta un valor propio (p. ej. un campo o un valor
`mixed` que dispare `_mixed_nationality_response`), y eso es un cambio de schema que hay que diseñar
y medir.

### Certificación con una sola fuente: el deseo de certificarse y el "ya certificado" del RAG

Sonda sin LLM sobre 225 mensajes. El deseo de certificarse vivía en tres listas que no
coincidían:
- `IntentDetector._WANTS_CERT_RE`: solo con un nivel como objeto.
- un patrón de `_NOT_CERTIFIED_PATTERNS`: solo con "quiero …".
- `rag_agent._WANTS_CERT_EXCLUDE_RE`: cualquier "quiero hacer …", incluido "quiero hacer buceo".

Además, el RAG tenía su propia lista de "ya certificado". Frente a `is_certified` del detector
discrepaba en 3 + 26 mensajes. Fallos reales:
- "quiere sacarse la certificación", "me quiero certificar", "quisiera obtener la certificación" y
  "we want to get our certification" salían **certificados**: ninguna lista de deseo los cubría y
  caían en el comodín `cert\w*`.
- el RAG leía "no soy certificado, es mi primera vez", "aunque no soy buzo certificado" y "no tengo
  licencia" como certificado, y descartaba "tengo el open water y quiero hacer buceo" por el
  "quiero hacer".

Cambio:
- Piezas únicas en el detector (`_DESIRE_VERB`, `_WANT_VERB`, `_WANT_OBJECT_PREFIX`, `_CERT_NOUN`).
  Con ellas se construyen `_WANTS_CERT_RE` y `_WANTS_CERTIFICATION`, que sustituye a los tres
  patrones de deseo de la lista negativa.
- `certification_status()` es la única decisión de "ya certificado". La usan `_detect_certification`
  y `rag_agent._mentions_already_certified`, y se borran las dos listas del RAG.

Solo un verbo de **deseo** implica "aún no certificado": con "hacer" a secas, la primera versión
convertía "no sé si hacer el open water o el advanced" en no certificado, y se vio en la foto.
Querer Advanced o Rescue tampoco lo implica, porque exigen Open Water. Y quien quiere certificarse
pide un curso: la regla "sin actividad + certificación conocida → buceo certificado" ya no se aplica
en ese caso (lo detectó un test que falló: "quisiera sacarme la licencia de buzo").

Foto sobre 234 mensajes: **9 cambios en el detector**, todos los buscados. Uno de ellos:
"somos 3 y 1 quiere certificarse" deja de suponer buceo certificado. En el RAG hay **34 cambios**:
sus 3 falsos positivos corregidos y 31 mensajes que ahora reconoce como certificados, porque
coinciden con lo que el detector ya guardaba.
- Límite heredado y visible: la fuente única lee en tercera persona ("viene mi primo, él es
  certificado") y en grupos parciales ("4 certificados y 3 snorkel") igual que `is_certified`. En el
  RAG solo cambia la frase de bienvenida del resumen de buceo, y únicamente si además es una
  pregunta de resumen.
- Arreglar el sujeto es trabajo del detector, no del RAG.

Eval-set con la fuente única de certificación (130 casos): **221/230**, tanda limpia. Frente a la
tanda anterior solo cambian los dos casos de nacionalidad, y los cambia la reversión del prompt de
grupo mixto: el residente vuelve a OK y "dos somos colombianos pero uno es extranjero" vuelve a
fallar. Ningún caso de actividad ni de certificación cambia. Referencia para las siguientes tandas:
**221/230**.

### Tener un nivel PADI en tercera persona, con la persona nombrada

"mi pareja tiene el advanced y quiere bucear" salía **curso Advanced**: `_HOLDS_CERT_RE` solo
conocía "tengo/tenemos". Completar la conjugación a secas ("tiene/tienen") fue la primera versión
y se descartó al medir. "¿tienen el advanced?" o "tiene el open water?" preguntan si el centro lo
ofrece, y habrían pasado a buceo certificado. Ahora la tercera persona solo cuenta con un
sustantivo de persona justo antes, sacado de la lista compartida (`_PERSON_NOUN_*`, ES y EN).

Medido sin LLM:
- Preguntas al centro frente a HEAD (en un worktree): **las 5 iguales**.
- Foto sobre 244 mensajes: **4 cambios, ninguno del corpus**. "mi pareja tiene el advanced", "mis
  amigos tienen el advanced" y "mi novia tiene el open water y quiere bucear conmigo" pasan a buceo
  certificado.
- "mi hermano tiene el rescue y yo quiero probar" estaba mal antes (curso Rescue) y lo sigue
  estando (buceo certificado para todos). Es reparto del grupo, trabajo del LLM, no de esta lista.
- "el tiene su open water" sigue sin reconocerse: "él" no es un sustantivo de persona.

Como el regex da lo mismo en todos los mensajes del eval-set, no se volvió a correr.

### Ubicación: la unificación detector/núcleo se para, y aparece un fallo real de la duda

Comparación sin LLM sobre 262 mensajes entre el resolutor corto del núcleo (`_apply_short_answer`,
ubicación pendiente) y `_detect_location` del detector: discrepan en 15. Cada uno sabe lo que el
otro no:
- el núcleo no conoce "ctg", los apodos de la ciudad ni los hoteles;
- el detector no conoce "barú" ni "island"/"isla" sueltos, que como respuesta a "¿desde dónde
  salen?" bastan.

La precedencia es contraria. El detector da isla concreta > Cartagena > genérico, y el eval-set le
da la razón en "estoy en cartagena pero el hotel es en isla grande". Pero no se puede copiar al
núcleo tal cual:
- "quiero ir a las islas del rosario desde cartagena" sale isla en el detector, cuando las islas son
  el destino de la excursión (el núcleo acierta con Cartagena);
- "nos vemos en la marina" sale Isla Marina por el "marina" suelto.

Distinguir dónde se aloja de adónde va es semántico: queda para la vía LLM, sin parches.

**Fallo real encontrado en la línea base.** Con la ubicación pendiente, `_LOCATION_DEFER_RE` ("no
sé", "recomiéndame"…) fijaba **Cartagena** en "Me interesa el curso PADI, no se bucear", "no sé si
hacer el minicurso o el snorkel" o "no sé si hacer el open water o el advanced". Nadie la eligió, y
la ubicación decide el servicio y el precio. Además, al darse la respuesta por resuelta, el turno
se saltaba la comparación de opciones. La verificación del resolutor LLM ya descartaba la ubicación
cuando el turno cambiaba la actividad, pero la vía determinista no tenía esa guarda. Arreglo, mismo
principio: la duda solo delega si el detector no encuentra ningún otro campo en el mensaje.
- Los 14 "no sé / da igual / tú decides / up to you" a secas siguen dando Cartagena.
- Foto: **4 cambios de 224**, los 4 buscados, sin cambios en el detector.
- Sigue abierto: "que solo nos acompañe en la lancha, no se mete al agua" casa "no se" (es el "se"
  reflexivo) y no trae otros campos.

### Paquetes de buceo con una sola fuente, y dos fallos de precio en el RAG

**Duplicado.** Los tamaños de paquete estaban copiados en cinco sitios:
- el detector (`(2,3,4,5,7,9)`, `(5,7,9)`, `(1,2,3,4)`);
- el núcleo (`_DIVES_TO_BASE_PLAN`, `_DAYS_TO_DIVES` y `_PACKAGE_DIVE_COUNT_IN_TEXT_RE`, que solo leía
  4/5/7/9 en cifra);
- el RAG (`_PRICE_PACKAGE_PATTERNS`, un regex por paquete).

**Fallos reales en la línea base** (21 preguntas de precio, sin LLM):
- "¿cuánto cuesta el paquete de 4 días?" y "cuánto cuesta bucear 4 días?" respondían el precio del
  paquete de **4 inmersiones** (2 días); el de 4 días es el de 9 inmersiones.
- "plan de 5 días" y "paquete de 7 días" respondían los paquetes de 5 y 7 inmersiones, que no son de
  esos días.
- Sin respuesta: "cinco inmersiones", "five dives", "pack de 9", "3-day"/"4-day dive package" y
  "9 buceos en 4 días".
- En el núcleo, confirmar "quiero este paquete" cogía el primer número del mensaje del bot, aunque el
  bot hubiera comparado dos paquetes.

**Cambio:**
- `dom.dive_packages()` deriva `{inmersiones: (días, servicio)}` de los ids `N_dives_D_days` de
  `services.json`.
- `dive_counts_in(texto)` (detector) es la única lectura de "N inmersiones":
  - devuelve todos los tamaños reales que nombra el texto, incluidas coordinaciones ("4 o 5
    inmersiones");
  - un "paquete de N" sin unidad solo cuenta si N no puede ser un número de días.
- `detect_cert_dive_count` devuelve un número solo si hay exactamente uno (antes, el primero).
- El núcleo deriva sus tablas (mismos valores; con solo los días sigue eligiendo el paquete más grande)
  y confirma el paquete solo si el bot describió uno multi-día.
- El RAG responde precio solo si la pregunta apunta a exactamente un paquete multi-día, por
  inmersiones o por días. "2 días" son dos paquetes (4 o 5 inmersiones): no supone.

**Medido:**
- Detector: **0 cambios** en 244 mensajes.
- Confirmación de paquete frente a HEAD (worktree): **2 cambios**, los dos correctos (dos paquetes
  comparados → no elige; "cinco inmersiones" → 5).
- Precios: **11 cambios de 21, todos a bien** (4 precios equivocados que desaparecen, 7 respuestas
  nuevas correctas). Los tests de precio existentes siguen pasando.
- Suite: 2109 passed.

Queda: `_BARE_PACKAGE_DIVE_RE` escribe todavía `5|7|9` en el regex. El filtro ya sale del catálogo,
pero un paquete nuevo de otro tamaño sin unidad no se leería.

### La actividad principal no contradice el reparto (regla general)

"somos 5 y 2 nunca han buceado" repartía `{certified_diving: 3, undecided: 2}`, pero la rama del
minicurso ("nunca he buceado") dejaba la actividad principal en minicurso. Ya existía una regla al
final de `detect()` para lo mismo con cursos con nivel ("2 con open water y 1 no"). Se generaliza
en vez de añadir otra: si el reparto trae buceo certificado y no contiene la actividad principal,
la actividad es buceo certificado, salvo que el mensaje diga que lo quieren sacar.

Foto sobre 244 mensajes: **1 cambio**, el buscado. Suite verde.

### Quién tiene la certificación dentro del grupo: sonda con LLM real (punto 1 de la cola)

9 mensajes con personas de estado distinto, a través de `_understand`, con los dos vetos del grupo
encendidos (config PRE) y 2 repeticiones idénticas. Resultado: **ningún reparto y el acompañante no
se activa nunca**.
- **Cliente marcado certificado sin serlo:** "mi amigo tiene licencia, yo no", "mi hermano tiene el
  rescue y yo quiero probar", "mi pareja tiene el advanced y yo no tengo nada" y "somos 2, mi amigo
  es buzo y yo no" (en este último, `is_certified=True` lo rellena el propio LLM).
- **La segunda persona se pierde:** "yo tengo el open water, mi esposa quiere probar" y "soy
  certificado y mi hijo no" dejan bien al cliente, pero la esposa o el hijo no aparecen en ningún
  campo.
- **"mi esposo bucea, yo prefiero snorkel"** deja solo snorkel.

**Por qué:**
- No es una puerta del código: `_relevant_gaps` sí pide `group_size` y `group_allocation`, y el LLM
  no los rellena.
- El detector fija `is_certified` con la afirmación de otra persona. La señal de polaridad
  (`certification_is_ambiguous`) solo marca 3 de los 9.

**Diseño propuesto (sin aplicar):**
- Señal estructural "la certificación se atribuye a otra persona": afirmación de certificación junto
  a un sustantivo de persona de la lista compartida.
- Con ella, el regex no fija `is_certified`.
- La definición única de `is_certified` y la de `group_allocation` dicen que se refieren a cada
  persona: con estados distintos, reparto con `certified_diving` para quien lo es y `undecided`
  para el resto, y total contable.

Es cambio de prompt: medir con el eval-set, la batería de grupo (escenarios nuevos de tercera
persona) y la batería de booleanos. Script de la sonda: `mixed_cert_probe.py` (scratchpad de la
sesión, se reproduce con `scripts/battery_group_allocation_gate._run`).

### Quién tiene la certificación dentro del grupo: la causa estaba en el núcleo, no en el LLM

**Diagnóstico.** Llamando a `fill_gaps` directamente, el LLM ya devolvía lo correcto:
- "mi amigo tiene licencia, yo no" → total 2 y `{certified_diving: 1, undecided: 1}`;
- "yo tengo el open water, mi esposa quiere probar" → lo mismo.

Lo borraba la comprobación de cifras de `_understand` (`_message_numbers` + `_consume_number`), que
exige que cada cantidad del reparto aparezca escrita como número. Aquí las personas se nombran una a
una ("mi amigo", "yo"), así que se tiraba el reparto entero y, con él, el total. El propio prompt ya
cuenta así ("mi pareja y yo" = 2).

**Arreglo (núcleo):**
- **Respaldo por persona nombrada.** `_named_people` cuenta personas nombradas en singular y la
  primera persona. Cada una respalda una cifra 1, y solo **todo o nada**: si con ellas quedan
  respaldadas todas las cifras. "soy certificado y mi hijo no" nombra a una sola persona (la primera
  va en el verbo); con respaldo parcial guardaba un reparto a medias con total 1 en vez de preguntar,
  y se vio en la sonda.
- **Total con las personas pendientes.** `_take_undecided_members` deja un total que incluye a las
  personas sin actividad elegida. Sin total escrito, el total se sincronizaba con la suma del reparto
  ya sin ellas y quedaba en 1: reproducido con el LLM simulado, y visto con el LLM real.
- **Sin duplicado.** "Determinante + persona en singular" ya existía en `_SINGULAR_COMPANION_RE`
  (`un|una|mi|a`). Ahora hay una pieza única, `_SINGULAR_PERSON`, en el detector, usada por los dos.
  - Efecto medido sin LLM: `_SINGULAR_COMPANION_RE` cambia en **8 de 209 mensajes**, todos "my …" en
    inglés más "viene su hermano", que no reconocía.
  - Como ya pasaba en español con "mi hija … mi hijo", también se lee como acompañante singular un
    mensaje con varias personas ("my daughter is 9 and my son is 12, my wife and i dive").
  - Exigir exactamente una persona cambiaría 2 de 198 mensajes (los dos de varias personas):
    pendiente.

**Negativo, revertido: reconciliar la regla del prompt.** La descripción de `group_allocation` y sus
guías ES/EN tienen una regla antigua ("a quien solo se describe por un atributo, déjalo fuera") que
contradice `undecided`.
- La reconciliación sola no cambiaba la sonda.
- Con ella, la batería de grupo bajó **b03** ("4 con titulo y 2 snorkel") de OK a VACIO: el LLM pasó
  a devolver `{certified_diving: 2, snorkel: 2}` 2/2 (con el parche antiguo simulado el núcleo lo
  guarda bien).
- Revertida. La contradicción del prompt sigue ahí: arreglarla necesita otra redacción y medirla
  contra b03. Copia de la versión probada en el scratchpad de la sesión (`booking_reconciled.diff`).

**Sonda con LLM real, solo el arreglo del núcleo** (prompt de HEAD, 9 mensajes, 2 repeticiones
idénticas). **4 de 9 pasan a correctos**, con total 2, 1 certificado + 1 pendiente y recomendación de
opciones: "mi amigo tiene licencia, yo no", "mi hermano tiene el rescue y yo quiero probar", "yo tengo
el open water, mi esposa quiere probar" y "mi pareja tiene el advanced y yo no tengo nada".
- "soy certificado y mi hijo no" sigue sin reparto (el bot pregunta), como antes.
- Sin cambio: "viene mi primo…", "mi novia es buza certificada y yo nunca he buceado", "somos 2, mi
  amigo es buzo y yo no" y "mi esposo bucea, yo prefiero snorkel".
- Queda: en tres de los arreglados el cliente sigue marcado `is_certified=True`; el reparto ya dice
  quién es quién.

### Quién tiene la certificación dentro del grupo: las tres causas que quedaban

Se añadió a la batería de grupo una familia de **personas con estado distinto**, cada una nombrada
una a una y sin cifras:
- beneficio p01–p07;
- riesgo q01–q04 ("mi amigo no sabe si viene", "le preguntaré a mi hermano si quiere bucear", "mis
  amigos tienen licencia, yo no", "mi hijo tiene 8 años");
- frontera g01–g02.

Una tanda enfocada con el parche en bruto del LLM separó tres causas.

**1. La petición fusionada pierde los campos del grupo** (b08, p03, p04, p06).
- Experimento con los mismos huecos: `fill_gaps` a solas da el reparto correcto **2/2** en los cuatro,
  y `extract_and_verify` lo devuelve vacío **2/2**.
- Es el efecto de recencia ya documentado en `combined_extraction_system_prompt`.
- La petición a b08 ("2 adultos bucean y 2 ninos hacen snorkel") es **idéntica** hoy y en b722d23
  (mismo camino, huecos y hash del prompt). Su paso de OK a VACIO frente a ayer es variación del LLM,
  no un cambio de código.
- Arreglo: si los campos del grupo no vuelven y el mensaje trae señal de grupo que el regex no
  resolvió, se piden solos. En la fusionada, con 2+ personas o 2+ cifras. Con `fill_gaps` a solas,
  solo si el LLM contestó otros campos pero no el grupo, con 2+ personas.
- Coste sin LLM sobre 208 turnos de una sola frase:
  - +13,5 % si la fusionada vuelve vacía;
  - tope teórico +26,5 %.
  - La primera versión (repetir siempre en `fill_gaps` con cifras) subía el peor caso a +28,5 %.

**2. Quien escribe no cuenta cuando va en el verbo** (p02, "soy certificado y mi hijo no").
- El LLM acierta y la guarda de cifras lo rechazaba.
- Ahora `_named_people` suma a quien escribe siempre que nombra a otra persona.
- Sin nadie más nombrado no cuenta: la regla anterior (un "yo"/"I" suelto) dejaba pasar un reparto de
  una sola entrada y fijaba el total en 1.

**3. El cliente se marcaba como certificado por lo que se decía de otra persona.**
- Lo introdujeron dos cambios propios de ayer: "tiene/tienen licencia" y "mi pareja tiene el
  advanced".
- Ahora `certification_claim(..., about_writer=False)` y `holds_padi_cert(..., about_writer=False)`
  cuentan la tercera persona solo para repartir, para la actividad de un acompañante o para decidir
  que no se pide el curso, nunca para el estado de quien escribe.
- La regla final de `detect()` pasa a cubrir también "sin actividad + reparto con buceo certificado".
- Foto del detector sobre 252 mensajes: 12 cambios, todos de mensajes con otra persona. "vamos 4 pero
  dos no tienen licencia" conserva reparto y actividad, pero ya no marca al cliente como no
  certificado.

**Más:** en el reparto, un curso con nivel que alguien del grupo YA tiene es buceo certificado
(`holds_padi_cert`). "mi pareja tiene el advanced y yo no tengo nada" volvió 1/2 como
`{padi_advanced: 1}`; quien quiere sacarlo conserva el curso.

**Pendiente del owner:** r11 ("mi amigo no esta certificado", grupo de 2) y r12 ("somos 2, mi amigo
no está certificado") esperan "sin reparto", una expectativa anterior a la decisión del 2026-09-15
("uno no está certificado" → `undecided` y recomendación). Con los cambios, r12 reparte `{certified:
1}` + 1 sin decidir y la batería lo cuenta como ALUCINA. Se deja la expectativa sin tocar hasta que
decida.

**Medición con el código final** (tanda enfocada, config PRE, 3 repeticiones):
- **Personas con estado distinto:** p01–p07 **7/7, las 3 veces**. Antes del punto 1 fallaban los 7:
  sin reparto, cliente marcado certificado o persona perdida.
- **r12:** 3/3 con la expectativa del owner.
- **Riesgo** (r03, r04, q01–q04): todo OK, **0 alucinaciones**.
- **r11** ("mi amigo no esta certificado"): sigue sin reparto 3/3, porque el LLM devuelve un parche
  vacío. La conversación sí es correcta: el núcleo ve a otra persona sin actividad respaldada y
  pregunta por el acompañante con las tres opciones
  (`test_companion_attribute_without_activity_asks_instead_of_guessing`).

**b05, regresión encontrada y cerrada.** La batería completa intermedia marcó b05 ("2 open water y 3
snorkel", grupo de 5) como ALUCINA. La segunda petición guardaba `{padi_open_water: 2, snorkel: 3}`
antes de la pregunta "¿ya certificados o quieren sacarlo?", que el owner decidió hacer primero. Ahora
la segunda petición no se hace cuando `course_level_is_ambiguous`. Confirmado con el LLM real: b05 2/2
sin reparto y el control b06 bien.

**Total respaldado por personas.** p06 volvió una vez con `group_size: 2` y sin reparto, y la rama
"persona añadida sin cifra" tiraba el total. Ahora se conserva cuando cuadra exactamente con las
personas nombradas y la conversación aún no tenía total. Un "tambien viene un amigo" a mitad nunca
pisa el total conocido (test).

**Coste real de la segunda petición** (batería completa intermedia, mensajes de grupo):
**47 sobre 408 peticiones de extracción (+11,5 %)**. En tráfico normal, con menos mensajes de grupo,
será menor.

**Pendiente, visto en la sonda:** en p03 ("somos 2, mi amigo es buzo y yo no") la petición fusionada
devuelve `is_certified: true` para el cliente (atribución del LLM, no del regex). El reparto sale
bien, pero el booleano del cliente queda mal. La guarda (b) no lo cubre porque no hay pregunta
pendiente.
Guarda estudiada y no aplicada para ese pendiente: descartar un `is_certified=True` del LLM cuando la
única certificación afirmada del mensaje es de otra persona. Sobre 210 mensajes solo toca 3 ("mi amigo
tiene licencia, yo no", "mi pareja tiene el advanced y yo no tengo nada", "mis amigos tienen licencia,
yo no"), y **no llega a p03**: "mi amigo es buzo" pasa por los patrones genéricos (`buzo`,
`cert\w*`), que no dicen de quién hablan. Arreglar el sujeto de esos patrones es el paso previo.

**Batería de grupo completa con el código final** (52 escenarios × 4 variantes × 2 repeticiones):
- **Config PRE:** repartos **16/17**, total **13/13**, riesgo **16/17**, **0 ALUCINA, 0 PARCIAL**,
  1 TOTAL_MAL, 1 VACIO.
  - El TOTAL_MAL es p06: 1 de 2 sin total ni reparto. Pasó 3/3 en la tanda enfocada y 2/2 en la
    batería intermedia, así que va bien en 6 de los últimos 7 intentos (variación de la segunda
    petición del LLM).
  - El VACIO es r11: el LLM no devuelve reparto, pero la conversación pregunta al acompañante.
- **Frente a la tanda solo-núcleo** (antes de la familia nueva): b05 queda igual (OK), b08 pasa a OK,
  r12 a OK con la expectativa del owner, y la familia nueva p01–p07 aparece bien salvo esa repetición
  de p06.
- **Coste real:** 44 segundas peticiones sobre 408 (**+10,8 %**).
- **Batería de booleanos** (3 repeticiones): legítimos **18/24**, alucinaciones evitadas **18/18**,
  idéntica a la referencia.
- El eval-set no se volvió a correr: el prompt es el de HEAD, su arnés no pasa por el núcleo y el
  regex no cambia en ninguno de sus mensajes (foto de 252 mensajes).

### Punto 1, segunda vuelta: los cuatro pendientes (deterministas)

**Acompañante singular = exactamente una persona nombrada** (`_singular_companion`). Antes bastaba
con una ("vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel" asumía cantidad 1). Frente a la
regla anterior cambian **2 de 210 mensajes**, los dos de varias personas.

**De quién habla una frase de certificación** (p03). Nueva pieza `_OTHER_PERSON_SUBJECT`: una persona
nombrada, un plural con posesivo, un pronombre o una cantidad ("uno", "dos", "two", "el otro"),
**siempre seguida de su verbo en tercera persona**. La primera versión sin verbo leía como sujeto el
complemento de "i am a certified diver with a companion" y lo detectó un test del RAG.
- `certification_claim(..., about_writer=True)` ignora afirmaciones y negaciones de esa frase, mirada
  entera (en "uno no esta certificado" el verbo cae dentro de la coincidencia).
- `other_person_certification()` da la polaridad de lo dicho del otro. En `_understand`, un
  `is_certified` del LLM igual a esa polaridad se descarta si quien escribe no dice nada propio:
  "somos 2, mi amigo es buzo y yo no" ya no marca al cliente, y el False de "my wife is certified and
  I am not" se conserva.
- Foto del detector: **17 cambios de 252**, todos frases sobre otra persona que dejan de fijar el
  estado del cliente ("somos 3, uno no esta certificado", "two aren't certified", "my wife is
  certified and I am not"…).
- Límite: "no es certificado mi acompañante" (sujeto detrás del verbo) sigue atribuyéndose a quien
  escribe.

**r11 determinista.** En el reparto "N no están certificados" una persona nombrada cuenta como 1 y el
total puede venir de la conversación: "mi amigo no esta certificado" con 2 ya sabidos →
`{certified_diving: 1, undecided: 1}`.

**p06 determinista (regla por personas).** Exactamente una persona nombrada con su certificación
dicha y quien escribe con la contraria → 1 certificado + 1 sin decidir, total 2. Solo sin total o con
total 2 conocido: con 4 serían 2 de 4 y no se reparte. Cubre también "soy buzo certificado y mi novia
no esta certificada" e "i'm not certified yet but my wife is certified".

**Fotos sin LLM:**
- Estado vacío: **3 cambios de 252**, los buscados (r12, p06 y el inglés).
- Con total conocido (2 y 4): pasan a repartir "mi amigo no está/esta certificado" y "my friend wants
  to try diving for the first time". p06 solo con 2.
- Suite: 2151 passed.

**Ronda A con LLM real** (código de la segunda vuelta, prompt de HEAD):
- **Batería de grupo, config PRE:** repartos **17/17**, total **13/13**, riesgo **17/17**.
  - **0 ALUCINA, 0 PARCIAL, 0 TOTAL_MAL, 0 VACIO**.
  - p06 y r11 pasan a OK frente a la tanda final anterior.
  - Segunda petición: 33 sobre 408 (**+8,1 %**, antes +10,8 %), porque p06 y r11 ya se resuelven sin
    ella.
- **Tanda enfocada:** todos los escenarios OK las 3 veces.
- **Batería de booleanos:** 18/24 y 18/18, idéntica.
- **Sonda del estado de quien escribe:** "somos 2, mi amigo es buzo y yo no" deja
  `is_certified=None` 2/2 (antes el LLM ponía True). "my wife is certified and I am not", "mi novia es
  buza certificada y yo nunca he buceado" y "soy buzo certificado y mi novia no esta certificada"
  quedan con el estado correcto 2/2. En "mi amigo tiene licencia, yo no" el cliente sale False 2/2: la
  expectativa de la sonda (None) estaba mal, porque "yo no" sí lo dice.

### Regla contradictoria de `group_allocation`: parche mínimo, medido y aplicado (ronda B)

La descripción del tool y las guías ES/EN tenían una frase antigua: "a quien solo se describe por un
atributo, déjalo fuera / OMITE el campo". Contradecía la regla `undecided` de la decisión del owner.
- La reescritura completa de la mañana hizo variar b03 y se revirtió.
- Esta vez se **quitaron solo esas tres frases**, sin reescribir el resto.
- Foto de prompts: cambian exactamente los 5 que llevan la regla.

**Medido con LLM real, frente a la ronda A (código idéntico sin el parche):**
- **Batería de grupo, config PRE:** 17/17, 13/13, 17/17, **mismo veredicto en todos los escenarios**.
  Segunda petición +7,6 %.
- **Tanda enfocada:** todo OK las 3 veces.
- **Booleanos:** 18/24 y 18/18, idéntica.
- **Eval-set:** 220/230 frente a la referencia de la mañana (221/230). La única diferencia es
  `split-one-not-certified-es` ("somos 3, uno no esta certificado"): pierde `is_certified=False`.
  - **La causa no es el parche**: es la atribución de sujeto del detector ya subida en 327379e. El
    eval-set no se había vuelto a correr tras la ronda A.
  - El reparto, el total y la actividad siguen bien.
  - La expectativa venía del "regex ground truth" antiguo y codificaba la mala atribución: "uno no está
    certificado" habla de un miembro del grupo, no de quien escribe. Se cambia a `is_certified: null`,
    mismo criterio que r11/r12.
  - Con la salida medida (regex y LLM sin valor) el caso vuelve a OK y el eval-set queda en
    **221/230**, recalculado sobre la tanda ya hecha, no re-corrido.

**Veredicto:** el parche empata en todas las mediciones y elimina una instrucción que contradice
`undecided`. Se sube aparte.

### Sujeto pospuesto: "no es certificado mi acompañante" ya no se atribuye a quien escribe

Era el límite que quedaba del punto 1: la atribución de sujeto solo reconocía a la otra persona
**delante** del verbo.
- **Nueva pieza `_POSTVERBAL_OTHER_SUBJECT_RE`:** verbo en tercera persona y, detrás en la misma frase
  (hasta 4 palabras), una persona nombrada.
- **Complementos:** no cuentan si hay una preposición de compañía o destino por medio ("quiero bucear
  con mi pareja", "es para mi novia"). "de" sí cuenta: "la primera vez de mi hijo" habla del hijo.
- **Sin duplicar:** la persona nombrada sale de una pieza compartida por los dos órdenes
  (`_NAMED_OTHER_PERSON`).
- **`other_person_certification`:** reconoce también el orden invertido, así que la guarda del
  booleano del LLM lo cubre.

**Medido sin LLM:**
- Foto del detector: **0 cambios de 252**.
- Sondas:
  - "no es certificado mi acompañante", "está certificada mi novia", "no es buzo mi hermano", "is
    certified my wife" y "es la primera vez de mi hijo" dejan de fijar el estado de quien escribe, y
    se sigue sabiendo el del acompañante.
  - Controles sin cambio: "soy buzo certificado y viene conmigo mi novia", "i am a certified diver with
    a companion…", "es mi primera vez, vengo con mi pareja".
- Un test antiguo esperaba la atribución al cliente de "no es certificado mi acompañante"; se movió a
  un test propio.

No se volvió a correr la batería con LLM: el cambio es determinista y el detector da lo mismo en todos
los mensajes del corpus (eval-set y las tres baterías).

### Punto 2: definición única de `activity`, `group_size` y `group_allocation`

**Inventario.** Cada campo estaba escrito dos o tres veces (descripción del tool, guías de
verificación ES y EN), con divergencias reales:
- el tool de `activity` solo decía "The diving-related activity the customer wants"; la regla del
  curso PADI nombrado vivía solo en las guías;
- al tool de `group_allocation` le faltaban "tramos con sustantivo" y "debe sumar el total";
- a las guías de verificación les faltaba la regla `undecided` que decidió el owner.

**Ronda C, negativo medido y revertido: la unión completa también en el tool.** El prompt de relleno
no cambió, pero la descripción del tool (lo único que ve `fill_gaps`) ganó la regla del curso PADI y
los tramos con sustantivo. Con el LLM real, frente a la ronda B:
- **Eval-set 217/230 (−4 frente a 221).** Pierden `is_certified`/`group_size` "never been underwater
  before, wanna give it a try, solo", "hola quiero probar el buceo, nunca lo he hecho, voy solo" y "my
  daughter is 9 and my son is 12, my wife and i dive".
- **Batería de grupo:** b05 ("2 open water y 3 snorkel") vuelve a ALUCINA. El LLM reparte
  `{certified_diving: 2, snorkel: 3}` en la primera petición, sin la pregunta aclaratoria.
- **Booleanos:** "apertura-nunca" pasa de 3/3 a 0/3 (15/24 frente a 18/24).

Causa: es la lección de 2026-09-12 otra vez. Una regla escrita para VERIFICAR hace que el camino de
RELLENO se abstenga, y justo en los mensajes que nombra ("nunca he buceado", "first time").

**Diseño final, dos capas desde una sola fuente:**
- `_FIELD_MEANING_EN/ES` = el texto ya medido del tool. El tool queda idéntico byte a byte.
- `_FIELD_VERIFY_RULES_EN/ES` = lo que solo sabía el veto (curso PADI nombrado; reparto completo, tramos
  con sustantivo y suma al total; "cambia el precio").
- `_meaning_rule` compone definición + regla de verificación para las guías.
- Así las guías ganan `undecided` y dejan de divergir entre sí, sin tocar el relleno.
- Foto de prompts: el tool no cambia; cambian las 10 guías y prompts fusionados.

**Ronda D, diseño en dos capas, con el LLM real y frente a la ronda B:**
- **Eval-set 221/230.** La única diferencia es `split-one-not-certified-es`, que pasa a OK por el
  cambio de expectativa ya hecho. No reaparece ninguna de las pérdidas de la ronda C.
- **Batería de grupo, config PRE:** 17/17, 13/13, 17/17, 0 alucinaciones, mismo veredicto escenario a
  escenario (b05 OK). Segunda petición +8,6 %.
- **Booleanos:** 18/24 y 18/18, idéntica ("apertura-nunca" vuelve a 3/3).
- **Tanda enfocada:** todo OK las 3 veces.

**Siguiente, del mismo punto:** la regla "un plural vago no es una cantidad" está escrita en cinco
sitios (`group_size`, `group_allocation` y tres campos del prompt de señales). Borrador de pieza
compartida preparado; se mide aparte con `battery_activity_choice`, la de grupo, la de booleanos y el
eval-set.

### "Un plural vago no es una cantidad" en una sola pieza: medido y revertido

**Idea.** La regla está escrita en cinco sitios: `group_size`, `group_allocation` y tres campos del
prompt de señales (`companion_is_singular`, `companion_qty`, `other_companions`). Se hicieron piezas
compartidas con las palabras ya medidas de `group_size` (lista de ejemplos + "un plural vago no es un
total concreto"), y cada campo conservaba su propia acción.
- Foto de prompts: el tool de extracción y las guías de `group_size` quedaban idénticos byte a byte;
  solo cambiaba el tool de señales.

**Medido con LLM real** (sonda de `detect_special_signals`, 8 casos × 3, prompt viejo en un worktree
de HEAD frente al nuevo):
- **Iguales:** "también vienen mis amigos a hacer snorkel", "viene mi familia a hacer snorkel" y los 4
  controles (singular, jerga, contado, mixto contado).
- **Peor, "ocho personas hacen snorkel y yo buceo":** vuelve el fallo medido nº 2. El hablante aparece
  como acompañante fantasma `{certified_diving: 1}` en 2 de 3; con el prompt viejo, 0 de 3.
- **Peor, "mi amigo bucea y mis amigos hacen snorkel":** `companion_is_singular` pasa de true 3/3 a
  false 3/3.
- La cantidad inventada para "mis amigos" (2 o 3) ya estaba en los dos.

**Revertido entero.** Reescribir esas descripciones cambia cómo el modelo pondera las advertencias
medidas que las rodean. Dejar las piezas solo para `group_size` no quitaba ninguna duplicación
(las señales seguían con su texto), así que tampoco se conservan.

**Referencia útil** (batería `battery_activity_choice` con el prompt actual, variante `base` de
producción): signals 10/10, slot 10/10, router 6/9.

**Lección:** en los prompts del LLM, "una sola fuente" solo es seguro donde el texto ya era idéntico.
Unificar redacciones distintas es un cambio de prompt y hay que medirlo como tal.

### Punto 4: vocabulario que quedaba (paquete sin unidad y "no se" reflexivo)

**Paquete sin unidad.** `_BARE_PACKAGE_DIVE_RE` todavía escribía `5|7|9|cinco|siete|nueve` y
`five|seven|nine` a mano. Ahora casa cualquier cifra (`_DIVE_NUMBER`) y `dive_counts_in` se queda
con los paquetes del catálogo que no pueden ser un número de días; un tamaño nuevo del catálogo se
lee sin tocar el regex.
- Foto del detector: **0 cambios de 252**.
- Sonda: "el pack de 5", "paquete de siete", "plan de 9" y "package of nine" se leen; "pack de 6" y
  "paquete de 8" no (no existen en el catálogo); "paquete de 3" y "paquete de 4 dias" siguen
  excluidos.

**"no se" reflexivo en la duda de ubicación.** Sin tildes, "no se mete al agua" y "no sé" se escriben
igual, y `_LOCATION_DEFER_RE` fijaba Cartagena en "que solo nos acompañe en la lancha, no se mete al
agua". Lo que las separa es estructural, no vocabulario: una duda que delega es la respuesta
entera. Quitadas sus frases quedan como mucho 4 palabras ("lo que tú me recomiendes" deja "lo que
tú me"); a la otra le quedan 9 de contenido propio.
- Foto del resolutor de ubicación: **1 cambio de 236**, el buscado.
- Las dudas cortas siguen recomendando Cartagena ("no sé", "da igual", "tú decides", "lo que tú me
  recomiendes", "no sé, lo que sea mejor", "up to you", "whatever", "no sé la verdad, tú decides").
- Cambio de conducta fuera del corpus: "no se todavía donde nos vamos a quedar" deja de suponer
  Cartagena y el bot vuelve a preguntar (no dar por hecho lo que el cliente no eligió).

**Estado del inventario de las 78 listas:**
- **Cerrados:** certificación (`certification_status`), cursos (`courses_mentioned`), paquete
  (`dive_counts_in` + catálogo) y la pieza de persona (`_SINGULAR_PERSON`, `_NAMED_OTHER_PERSON`).
- **Para reinvestigar:** ubicación y grupo con nacionalidades mixtas.
- **No son duplicado real:** disponibilidad, nombre, actos de diálogo y seguridad.
- **Queda como duplicado real:** la familia de acompañante/no buzo del RAG y el supervisor
  (`_NON_DIVER_*`, `_COMPANION_PLURAL_QUANTIFIER_RE`, `_PURE_COMPANION_RE`).

### Punto 4: acompañante/no buzo y palabras numéricas

**Corrección del inventario.** Revisada de cerca, la familia de acompañante del RAG no duplica
nada: pregunta otra cosa ("¿hay alguien que no bucea, uno o varios?") y solo la usa el resumen
de buceo del RAG, cubierto por `test_rag_safety.py`. `_PURE_COMPANION_RE` del supervisor era
**código muerto** (sin referencias en src, tests ni scripts): borrado.

**El duplicado real eran las palabras numéricas.** Estaba la lista "dos|tres|cuatro…" copiada 20
veces en detector, núcleo, supervisor, RAG, carrito y fuzzy, cada una con su rango (1-4, 1-6, 2-9,
1-10, 2-19). Ahora hay una sola fuente, `src/utils/number_words.py`:
- `number_words(lo, hi, lang)` devuelve el mapa palabra → valor, ordenado por valor y con ES antes que
  EN en cada valor (el carrito y fuzzy eligen por orden).
- `number_alt(lo, hi, lang)` devuelve la alternancia regex con la palabra más larga primero, para que
  "seventeen" no se quede en "seven".
- Cada consumidor conserva su rango y sus extras ("un", "otros", "varios", "couple").
- Foto sin LLM de todos los consumidores (intent completo, `dive_counts_in`, sujeto de otra
  persona, `_message_numbers`, `_NOT_ALONE_RE`, nacionalidad mixta, normalización y niños del
  supervisor, acompañante del RAG, cantidad del carrito, fuzzy) sobre el corpus más una rejilla de
  palabras 1-19 ES/EN en 43 plantillas: **0 cambios de 1215**.
- `AGE_WORDS` y `_WORD_TO_NUM` son idénticos, orden incluido.

**Asimetrías de rango que la fuente única dejó a la vista: alineadas en un paso aparte**, porque
cambian conducta:
- **RAG, elíptico:** EN pasa de 1-5 a 1-6, como ES. Lo mismo en la lista de plurales.
- **RAG, cuantificador de acompañantes:** EN pasa de 2-5 a 2-10, como ES.
- **Supervisor, nacionalidad mixta:** ES pasa de 2-5 a 2-10, el rango de los otros patrones de grupo.
- **Días de paquete:** el rango sale del catálogo (`_MAX_PACKAGE_DAYS`, hoy 4), no de un 4 escrito a
  mano.
- Foto contra el commit anterior: **7 cambios de 1215, todos buscados.** "seis"…"diez de nosotros
  somos colombianos pero uno es extranjero" pasan a grupo mixto (5), y "three dive and six don't"
  pasa a no buzos en plural en el RAG (2 lecturas del mismo mensaje).
- El cuantificador EN no cambia nada visible: "companions" en plural ya marcaba plural.

**Lint:** el primer push falló en CI por ruff UP033 (`lru_cache(maxsize=None)` → `functools.cache`);
el deploy no llegó a correr.

### Tarea 1: opciones del router para la comparación — medida y no aplicada

**Idea.** Hay dos piezas:
- **Router.** El enum de `comparing_options.options` pasa de 4 valores escritos a mano a
  `dom.bookable_activity_ids()`.
- **Núcleo.** Las ofertas que se comparan pasan a ser las del texto más las del LLM, solo con la
  duda escrita en el texto y quitando la genérica si hay una concreta de su familia.

Caso que arreglaba: "dudo entre la especialidad de nitrox y la de flotabilidad", sin "?". El regex
solo ve nitrox, así que se reservaba nitrox en vez de explicar la diferencia.

**Batería nueva de las 9 señales del router** (`scripts/battery_router_signals.py`). Los tests del
router van con mock y no había medida real. Tiene 28 casos de las otras 8 señales, sacados de
hallazgos en vivo de HISTORY y de los negativos que piden las descripciones del tool, más los 9 de
`comparing_options`. Un caso acierta si salen exactamente las señales esperadas.

**Resultado, enum viejo frente a nuevo** (todas las tandas sumadas):

| caso | enum viejo | enum del registro |
|---|---|---|
| "soy epiléptica" (solo médico) | 9/9 | 17/21 (marca también discapacidad) |
| "quiero buceo y snorkel para los dos" (no compara) | 9/9 | 9/12 (dice que compara) |
| las otras 26 de las 8 señales | igual | igual |
| r08 opciones "nitrox o flotabilidad" | no | sí |

- Ninguna de las dos pérdidas cambia hoy lo que ve el cliente:
  - La señal médica del LLM sigue escalando antes que DIVE TO HEAL, en la cascada y en el grafo.
  - "quiero" bloquea la comparación.
- Aun así son dos señales más ruidosas a cambio de un único fraseo: **no se aplica** (regla del owner).
- Con el enum viejo, la unión del núcleo no aporta nada que el regex no vea, así que también se
  revierte. Se queda la batería.

**Ruido medido:** con el mismo prompt a temperatura 0 salen cambios sueltos de 1 repetición
en 6. Un cambio de una sola repetición no es una regresión.

**Error de método, anotado:** la segunda tanda comparó el mismo prompt dos veces, porque `base`
toma el tool de producción y ese ya estaba editado. La comparación válida se repitió con un
worktree de HEAD.

**Hallazgos nuevos (igual con los dos enums, ya en producción):**
- **Pronóstico del tiempo sin escalar.** "¿va a llover mañana en cartagena?" no lo caza ninguna
  palabra clave, y el LLM devuelve una clave `weather_conditions` que no existe en el esquema en vez
  de `sensitive_topic` (3/3 y 2/3). Nadie la lee, así que va al flujo normal.
- **Reparto leído como comparación.** "tengo un amigo que quiere bucear y yo hago snorkel": el LLM
  dice `comparing=true` 3/3 y el núcleo lo acepta, porque hay 2 ofertas en el texto, ni número ni
  "quiero". Va a RAG en vez de a la reserva.
- **"me cobraron dos veces y nadie me responde"** sale `real_time_issues`, no queja. Escala
  igual; la etiqueta de la batería acepta los dos.

**Vía general para r08, sin tocar el router:** `courses_mentioned` solo conoce nitrox entre las
especialidades. "especialidad de flotabilidad", "buoyancy specialty" (la propia etiqueta del
registro), "naturalista" o "mindful diving" dan `[]`, y el vocabulario de especialidades está
escrito tres veces en el detector.

### Tarea 1, vía general: nombres de especialidad desde el registro (aplicada)

**Cambio.** El nombre de cada especialidad es su etiqueta del registro sin el sustantivo común
de la familia ("Especialidad Flotabilidad" → "flotabilidad", "Fish Identification specialty" →
"fish identification"), con y sin tildes. El sustantivo sale igual que el de los cursos, y
`_label_nouns` es la pieza que comparten los dos. Con eso:
- `_SPECIALTY_PATTERNS` se genera a partir de esos nombres.
- La especialidad concreta del detector sale de esos mismos patrones. Se borra
  `_SPECIALTY_KEYWORD_TO_ACTIVITY`, que buscaba subcadenas sueltas como "fish" o "peces".
- `_COURSE_NAME_PATTERNS` junta las variantes que ninguna etiqueta contiene ("owd",
  "rescate", "enriched air") con los nombres del registro.

**Foto sin LLM** sobre 737 mensajes (corpus más una rejilla de 20 nombres × 11 plantillas):
- **Corpus real: 5 cambios de 238, todos a mejor.**
  - "dudo entre la especialidad de nitrox y la de flotabilidad" pasa a comparación (r08).
  - Cuatro especialidades pasan a ser oferta: flotabilidad, naturalista, identificación de peces y
    mindful diving. "I'd like to do the mindful diving specialty" ya no cuenta como buceo
    certificado.
- **Actividad: 22 cambios, todos en la rejilla y buscados.**
  - "naturalist" (EN) e "identificacion de peces" sin tilde ya se reconocen.
  - "fish/peces o mindful diving" sale mindful: la palabra suelta no es un nombre.
- Ninguna plantilla sin duda cambia su veredicto de comparación, ni con la señal del LLM ni sin ella.
- **Siguen sin comparar**, a propósito: los sinónimos de la misma especialidad (buoyancy y
  flotabilidad son una oferta) y las palabras sueltas ("fish", "peces", "mindful"), que no se
  añaden a mano.

### Tarea 6: el eval-set pasa por el núcleo (`--core`)

**Por qué.** El eval-set medía regex + `fill_gaps` + veto, sin las guardas del núcleo. Los
casos con historial fallaban por un artefacto: el LLM veía la pregunta del bot, pero no el estado
que esa conversación tendría.

**Cambio.** `scripts/run_extraction_eval.py --core` pasa cada caso por
`conversational_core._understand` con la config de producción, sobre un estado sembrado con
`history` y un `state` opcional por caso.
- Se puntúa lo que el turno cambió en el estado: un campo que ya estaba y no se toca cuenta como
  abstención.
- Las personas sin decidir (`pending_undecided_qty`) se leen como `undecided` dentro del reparto.
- Los 3 casos `hist-*` llevan ya su slot pendiente, y el del reparto también el reparto sabido.
- El modo por defecto no cambia y cada modo escribe su propio resumen JSON.

**Resultado** (tanda limpia, 0 degradadas): **núcleo 216/230** frente a script 221/230 (base
eval_d). Por caso:
- **2 a mejor:** los dos artefactos de historial (`hist-...-pending-certification`,
  `hist-followup-...-group-allocation`).
- **7 a peor.** Se explicaron uno a uno con sondas del LLM real (3 repeticiones) y réplicas
  deterministas con los valores devueltos:

| caso | qué pasa | ¿pérdida en producción? |
|---|---|---|
| `prof-es-toda-la-semana`, `prof-en-just-the-day` | el núcleo no pide `duration` a propósito (Fix B, no conduce slots) | no |
| `adv-en-elliptical-no-dive-verb` | el LLM da minicurso sin `is_certified`; con minicurso el siguiente slot es ubicación | no |
| `certification-dialect-rescue-colloquial` | el LLM da `is_certified=True` 3/3, pero `_flag_cert_or_course` lo borra: "ya **llevo** el rescue" no cuenta como tenerlo | sí, segura: pregunta "¿ya la tienes o quieres sacarla?" |
| `grp-es-mixed-suegra` | el LLM da `{certified_diving: 2, snorkel: 1}`; la guarda de cifras lo tira ("mi pareja y yo" = 2 no es una cifra ni una persona suelta) | sí, segura: encola y pregunta |
| `grp-en-implicit-count-ages` | el LLM da total 4 y `{certified_diving: 2, undecided: 2}` 3/3; la misma guarda tira el reparto y, con él, el total | sí, segura: pregunta |
| `prof-en-from-states` | el LLM se abstiene de `is_colombian` 3/3 cuando se piden solo los huecos (la sensibilidad ya medida en F2b) | sí, segura: pregunta la nacionalidad |

**Lectura:** ninguna guarda deja pasar un valor malo en estos casos; el coste es una pregunta de
más en 4 mensajes. Las tres pistas quedan en la cola, sin tocar (orden del owner):
- **"llevo" como tener un nivel.** Es un hueco en las piezas de `_HOLDS_WRITER`, no una frase nueva.
- **Guarda de cifras.** La composición "X y yo" o "mi mujer y yo" respalda un 2, igual que
  `_named_people` respalda cifras 1.
- **Total con reparto.** No tirar un total que cuadra con las personas nombradas cuando se tira el
  reparto. Ya existe esa regla para el caso sin reparto.

**Nota de método:** la sonda espiaba el dict que devuelve el LLM por referencia, y el núcleo lo
muta después (`pop`). Un `{}` en el espía parecía una abstención; se corrigió con `deepcopy`
antes de sacar conclusiones.

### Tarea 7: hallazgos antiguos, reproducidos

Los cuatro venían de la batería sintética contra PRE (lote 5, 2026-08-26) y de la de grupo. Se
reproducen en local con `route_message`. Sin BD local, RAG va mockeado, lo que no afecta a
ninguno de ellos. Nada arreglado todavía (orden del owner: primero reproducir).

**"primero dime qué incluye el tour" → acuse genérico, sin la información.** Reproducido de forma
determinista, con el LLM mockeado.
- Con un slot pendiente, el mensaje va a extracción y el cliente recibe el acuse más la pregunta
  del slot; RAG no se llama.
- Con "?" ("…el tour?") o empezando por "que incluye" sí va a RAG.
- **Causa:** `supervisor._looks_like_info_question` ancla la palabra de pregunta al principio
  (`^(qué|dime|cuéntame|…)`), y "primero" delante lo rompe.
- Es el mismo hueco que ya se cerró en `_BOOKING_PROCESS_QUESTION_RE` ("vale y como reservo"),
  que por eso no va anclado.
- **Pista general:** no anclar al principio del mensaje, sino al principio de la cláusula (tras
  relleno o puntuación). Antes hay que medir los falsos positivos que el anclaje evita, que son
  acciones de carrito ("puedo añadir…").

**Una corrección no se aplica, y no solo tras el precio.** Reproducido de forma determinista.
- **Tras el resumen en COP**, "espera, en realidad no somos colombianos" y "perdón, no somos
  colombianos, somos españoles" dejan `is_colombian=True` y re-emiten el mismo resumen en COP.
- **Antes del precio** pasa lo mismo, con un slot pendiente:
  - "perdón, en realidad no estamos certificados" deja `is_certified=True`;
  - "mejor desde las islas, estamos en isla grande" deja `location=cartagena`.
- **Causa:** el detector lee bien el valor nuevo (`is_colombian=False`), pero
  `supervisor._apply_detected_intent` solo escribe estos campos si el estado aún no los tenía.
  Además, `_relevant_gaps` no los pide al LLM porque ya se conocen.
- Solo dos campos se corrigen:
  - la actividad, porque "latest wins";
  - el total, que se sustituye si el mensaje trae el cue `_GROUP_SIZE_CORRECTION_CUE_RE`.
- Ningún test fija "la primera nacionalidad gana" como decisión. El único test de "latest wins"
  protege al buceador principal de lo que se dice del acompañante.
- **Pista general:** llevar la regla del total (el valor nuevo solo gana con un cue explícito de
  corrección) a una sola función para todos los campos que escribe `_apply_detected_intent`.
  Tras el cierre, esa función re-emitiría el resumen, que hoy solo se re-emite si se añade un tipo
  de actividad nuevo.
  - El cue actual ya reconoce "espera, en realidad…" y "perdón…".
  - No reconoce "mejor desde las islas" ni "al final mi suegra también bucea".
  - Hay que medir que "mejor" o "al final" no conviertan en corrección un mensaje normal.
- **Con el LLM real (2/2) es peor que en la réplica:** el acuse dice "Entendido, ninguno es
  colombiano" y justo debajo re-emite el mismo precio en COP.

**Acompañante que llega a trozos: ahora cobra mal, de forma consistente (3/3 con LLM real).**
- **Conversación:**
  1. "hola, quiero bucear con mi amigo, yo soy certificado";
  2. "desde cartagena";
  3. "no, buceamos hace 6 meses";
  4. con la nacionalidad pendiente, "él quiere hacer snorkel";
  5. "somos colombianos".
- **Resultado:** la actividad principal pasa a snorkel, el reparto sigue en
  `{certified_diving: 2}` y el resumen cobra **2 × inmersiones en COP**. El amigo que quiere
  snorkel se cobra como buceador, aunque el acuse dice "Entiendo que él está interesado en hacer
  snorkel".
- Ya no es el doble conteo del informe de agosto (reparto de 3 para 2 personas): el código cambió
  desde entonces, y el síntoma de hoy es este.
- **Causa**, reproducida sin LLM:
  - El núcleo no ve a otra persona en "él quiere hacer snorkel". `_ADDED_PERSON_RE`,
    `_singular_companion` y `_MENTIONS_PERSON_RE` no conocen el pronombre.
  - El detector lee `activity=snorkel`, y `_apply_detected_intent` aplica "la última actividad
    gana" sobre la actividad **principal**.
  - Como el turno "avanzó" (cambió la actividad), la red de precisión (`detect_special_signals`)
    no se llama: 0 llamadas en la réplica, aunque se mockeó para devolver el acompañante.
- **Pista general, sin vocabulario nuevo:** la pieza del detector `_OTHER_PERSON_SUBJECT_RE` (sujeto
  de otra persona + su verbo) ya reconoce "él quiere hacer snorkel", "mi amigo quiere…" y "she wants
  to snorkel", y no "quiero hacer snorkel" ni "mejor snorkel".
  - Usarla antes del "latest wins" de la actividad: una actividad dicha de otra persona va al
    reparto como la del acompañante, no a la principal.
  - Falta "ella prefiere": el verbo no está en la pieza, y hay que medirlo aparte.

**Cambio de reparto (f01, 3/3 con LLM real): "al final mi suegra también bucea, no hace snorkel"**
deja `{certified_diving: 2, snorkel: 1}`.
- **Causa:**
  - el reparto ya se conoce, así que no se pide al LLM (`_state_known_fields`);
  - el detector no lee reparto nuevo;
  - no hay cue de corrección ("al final" no está en `_GROUP_SIZE_CORRECTION_CUE_RE`);
  - `_ADDED_PERSON_RE` casa con "mi suegra" sin número, así que se quita cualquier reparto del patch.
- Es la misma familia que las correcciones de arriba: un dato guardado solo se reescribe por el
  total y por la actividad.

**Corrección de la causa de 7a** (revisada al ir a arreglarlo): la red de precisión no se salta
porque el turno "avanzara". La nacionalidad seguía pendiente antes y después, así que `advanced`
era False. La salta el circuit-breaker `_group_allocation_fully_resolved`: `{certified_diving: 2}`
suma el total 2 y el grupo se da por explicado, aunque la actividad principal ya no esté en el
reparto. Si corriera, la guarda "misma actividad que el grupo" compara con
`state.detected_activity`, que este turno ya pisó, y tiraría la señal. Y
`_merge_companion_activity` suma sin restar, así que contaría dos veces al amigo que ya estaba en
el 2 (el doble conteo de agosto).

**Lectura conjunta.** Tres de los cuatro son un mismo mecanismo: el estado no tiene una regla única
de **corrección**. Hay campos que no se reescriben nunca, uno con cue (el total) y uno siempre (la
actividad), y en ese último sin distinguir si la actividad es de otra persona. Dos cobran mal sin
avisar (acompañante y nacionalidad). El cuarto (qué incluye el tour) es independiente.

### Tarea 7d, arreglada: la pregunta de información se reconoce por su estructura

`supervisor._looks_like_info_question` iba anclada al inicio del mensaje. Ahora reconoce además,
con clases gramaticales cerradas y sin frases nuevas:
- **Imperativo de pedir información en cualquier posición:** dime, cuéntame, explícame, infórmame,
  quiero/quisiera/necesito/me gustaría saber, tell me, let me know, i'd like to know.
- **Palabra interrogativa al inicio de una cláusula:**
  - tras puntuación, con o sin conjunción ("vale, cuánto cuesta", "perfecto, y cómo pago");
  - o tras una conjunción sola ("ok y dónde nos recogen").
  - Tras puntuación no valen "hay/tiene/incluye" ("somos 3, hay un niño" es un dato), y
    "como/cuando/donde" solo con tilde ("somos 3, como te dije").
  - Tras una conjunción sola, "que" solo con tilde ("quiero bucear y que mi hijo haga snorkel"), y
    en inglés solo what/how/which ("and when we arrive").

**Foto sin LLM** sobre 440 mensajes (eval-set, baterías, eval de RAG, mensajes de los tests y
sondas):
- Cambia la conducta en **7, todos sondas buscadas**: "primero dime qué incluye el tour", "antes de
  nada, dime qué horario tienen", "bueno, cuéntame del minicurso", "perfecto, y cómo pago", "ok y
  dónde nos recogen", "oye y cuánto cuesta el snorkel" y "vale pero qué incluye el almuerzo".
- **Ningún mensaje del eval-set ni de las baterías cambia.** Otros 11 cambian solo la marca interna,
  porque ya llevaban "?" y el núcleo ya los trataba como pregunta.
- Las sondas de falso positivo siguen fuera: "genial, lo que tú digas", "creo que somos 3", "es que
  mi novia no bucea", "vale, cuando lleguemos te escribo".

**Límite conocido:** una pregunta solo por entonación, sin "?" ni interrogativo ni imperativo ("parce
y eso trae almuerzo"), sigue recibiendo el acuse. No hay estructura que leer sin LLM.

### Tarea 7a, arreglada: la actividad de otra persona ya no pisa la principal ni se cuenta dos veces

**Cambio**, sin vocabulario nuevo:
- **Quién es otra persona lo decide el LLM de señales.** Sonda real, 15/15 estable: "él quiere…",
  "mi parce se anima al snorkel" y "ella prefiere snorkel" salen como acompañante; "mejor snorkel"
  no devuelve nada.
- **Circuit-breaker** (`_group_allocation_fully_resolved`): un reparto que no contiene la actividad
  principal no explica al grupo. Así la red de precisión vuelve a correr cuando el turno pisa la
  principal.
- **Guarda de "misma actividad que el grupo":** compara con la actividad de ANTES del turno
  (`prev_main_activity`), no con la que el propio turno acaba de escribir.
- **Un solo punto de decisión, `_add_or_ask_companion`** (fast-path y red). Ni el texto ni el LLM
  dicen si esa persona ya estaba contada: "él quiere hacer snorkel" y "también viene mi hermana
  que quiere hacer snorkel" dan la misma señal.
  - **Pregunta el total** si sumar supera el total conocido, el mensaje no trae señal de adición
  (`_ADDITION_CUE_RE`, separada de "mi amigo" en `_ADDED_PERSON_RE`) y `qty <= total - 1`. La
  pregunta es "¿seguís siendo N o se suma alguien?", con botones, y `pending_companion_in_group`
  guarda a la persona pendiente.
  - Esa última condición existe porque quien escribe siempre es uno de los contados, así que con un
    total de 1 la otra persona es nueva.
- **La respuesta se aplica en un único sitio** (`_apply_group_total`, respuesta corta y resolutor
  LLM): si el total no crece, esa persona se MUEVE de la actividad principal; si crece, se AÑADE.

**Medido:**
- **LLM real, 3/3** (`scripts/repro_old_findings drip`): "él quiere hacer snorkel" → pregunta el
  total → "somos 2" → `{certified_diving: 1, snorkel: 1}`. El resumen cobra 1 inmersión y 1 snorkel
  (antes, 2 inmersiones).
- **Réplica determinista:**
  - "somos 3" añade;
  - "también viene mi hermana…" añade sin preguntar;
  - "mi acompañante…" con total 1 añade sin preguntar.
- **Foto determinista** de los 66 escenarios de las baterías de grupo y booleanos por `_understand`,
  HEAD frente a árbol: **0 cambios**.
- Suite 2240.

**Hallazgo al medir (pasa a 7b):** "mejor snorkel", un cambio de opinión del propio grupo, cambia
la actividad principal pero deja el reparto en `{certified_diving: 2}`, y el cierre cobra 2
inmersiones. Es la misma familia que 7b/7c: el reparto guardado no se reescribe.

### Tareas 7b y 7c, arregladas: una contradicción no se ignora ni se aplica a ciegas

**Problema.** Los campos se escribían una sola vez (salvo la actividad, que siempre gana, y el
total, que se sustituía con cue):
- "espera, en realidad no somos colombianos" tras el precio re-emitía COP;
- "al final mi suegra también bucea" no cambiaba el reparto;
- "mejor snorkel" cambiaba la actividad pero cobraba el reparto anterior.

Sonda del regex sobre 21 fraseos de corrección: lee el valor nuevo en 11 y trae cue solo en 6. Una
lista de cues no es una solución global.

**Decisiones del owner (2026-09-15):**
- Con cue explícito se aplica; sin cue se confirma con botones ("¿lo cambio?").
- Los campos ya sabidos se leen con el LLM en la petición que el turno ya hace, y tras el cierre en
  una propia (salvo "vale"/"ok" a secas).

**Diseño**, con un solo escritor del estado:
- **Detectar.** Un valor de ESTE mensaje distinto del guardado es una contradicción; no la decide
  ni la jerga ni el cue.
  - **El regex propone, no decide** (`_regex_contradictions`). También deduce (minicurso → no
    certificado) y lee frases de otra persona ("mi novia no es buzo", "mi parce no está
    certificado"): tres tests existentes lo destaparon al pedir confirmación donde no tocaba.
  - **Se acepta sin más** solo lo que quien escribe dice de sí mismo con cue: sin otra persona de
    sujeto (`mentions_other_person_subject`) y, para la certificación, con `certification_claim`.
  - **Lo demás lo arbitra el LLM:** la verificación existente (`verify_fields` /
    `extract_and_verify`) con los campos sabidos y su valor guardado, que el LLM no ve. Sonda real:
    discrepa solo cuando el mensaje dice otra cosa ("somos gringos", "somos de fuera", "estamos en
    barú", "ninguno tiene licencia", f01) y se abstiene en "perfecto, gracias", en el mismo valor y
    si habla de otra persona, **24/24**. Pide una petición propia solo si el regex vio una
    contradicción o tras el cierre.
- **Aceptar** (`_route_contradictions`). Con cue marca `intent.overwrite`; sin cue deja
  `pending_correction` y `next_missing_slot` pregunta `SLOT_CONFIRM_CORRECTION` con botones. La
  respuesta se lee por la primera palabra ("sí, cámbialo", "no, lo de antes").
- **Escribir.** `_apply_detected_intent` y `_group_size_that_will_persist` respetan
  `intent.overwrite`. El cue de corrección vive en un único sitio, renombrado
  `_CORRECTION_CUE_RE`. Al confirmar, los valores pasan por el mismo camino que un turno normal
  (invariante del reparto, `_take_undecided_members`, escritura).
- **Cerrar.** `_finalize` reconstruye siempre el carrito y la moneda desde el estado.
- **"mejor snorkel".** Al empezar la fase de cierre, un reparto que solo tenía la actividad anterior
  sigue al cambio. Va ahí y no al escribir la actividad: si el turno era de otra persona, la red de
  7a ya restauró la principal.

**Medido:**
- Suite en verde con 9 tests nuevos. Se actualizaron 4 tests que fijaban el contrato viejo (el cue
  leído dentro de la función del total, y `fill_gaps` como única petición con campos sabidos).
- **Foto determinista** de los 66 escenarios de las baterías de grupo y booleanos, HEAD frente a
  árbol, con `pending_correction` incluido: **0 cambios**.
- **LLM real:**
  - "espera, en realidad no somos colombianos" tras el precio re-emite el resumen en **USD (356 USD)**, 2/2;
  - "perdón, en realidad no estamos certificados" se aplica;
  - "mejor desde las islas, estamos en isla grande" pregunta "¿lo cambio? salida desde Cartagena →
    en las islas", 2/2;
  - acompañante a trozos (7a) sigue 2/2.
- **Baterías:**
  - booleanos idéntica por caso (18/24, 18/18);
  - `eval --core` idéntico por caso (216/230);
  - grupo, config PRE: 16/17, 13/13, 17/17, con un solo cambio frente a la base de las 12:51:
    `b05-open-water-nombrado` pasa a ALUCINA. b05 ya alucinaba en la tanda de las 12:35 con el
    código anterior, y lo único que cambia en su petición es `group_size` en la lista a verificar.

**b05, regresión de 7b: medida, explicada y cerrada con una guarda estructural.**
- **Síntoma.** Con la verificación de campos sabidos, "2 open water y 3 snorkel" (total 5 conocido)
  guardaba `{padi_open_water: 2, snorkel: 3}`: **6/6 frente a 0/6 en HEAD**, la misma petición salvo
  `group_size` en la lista a verificar.
- **Causa de fondo.** Réplica con el LLM mockeado a ese reparto: **HEAD lo guardaba igual**. La
  decisión del owner (nivel PADI ambiguo → se pregunta, no se asume curso ni buceo) solo la sostenía
  que el LLM se abstuviera.
- **Arreglo.** En `_flag_cert_or_course`, el único punto que marca esa pregunta, un reparto con una
  clave de nivel de curso no se guarda hasta tener la respuesta, diga lo que diga el LLM.

**Hallazgo al medir 7c (pasa a "Para reinvestigar", G).** Con "¿cuántos serían para snorkel?"
pendiente, "no, buceamos hace 6 meses" llevó el grupo de 3 a 9 buceadores.
- La respuesta corta determinista lo rechaza. El 6 lo pone el resolutor LLM del slot.
- La verificación de 7b lo detectó al turno siguiente y propuso volver a 3 con confirmación.

**Guarda (b) sobre la verificación de campos sabidos.** f01 medido como conversación completa con
el LLM real destapó un riesgo de 7b. En turnos que contestan otra pregunta pendiente ("desde
cartagena" con la ubicación pendiente, "no, buceamos hace 6 meses" con la seguridad), la
verificación re-derivaba del historial el total y el reparto y pedía confirmar cambios que nadie
había dicho. En la sonda de un solo mensaje se abstenía 24/24; en conversación larga, el historial
tira de él.
- **Arreglo:** el mismo principio que `_boolean_patch_is_anchored`: lo que viaja pegado a la
  respuesta de otra pregunta no se acepta. `_recheck_proposals` descarta las propuestas cuando el
  turno contestó el slot pendiente, sea por respuesta corta (`answered_pending`, que `_understand`
  recibe como `resolved_short`) o porque el intent trae el campo de ese slot.
- **Sigue leyéndose** "ah no, somos gringos" con la ubicación pendiente, que no la contesta, y
  cualquier corrección tras el cierre, donde no hay nada pendiente.
- Tests: se descarta en "desde cartagena" y se conserva en "ah no, somos gringos".
- **Batería de grupo, config PRE, con la guarda de b05:** **17/17, 13/13, 17/17, 0 alucinaciones, 0
  cambios frente a la base de las 12:51**.

**Reproducción final con el LLM real** (`scripts/repro_old_findings`, 2 repeticiones por caso, con
todas las guardas): **todos los casos correctos 2/2**.
- **f01 como conversación (7c).** Apertura con cifras, para no caer en H. "al final mi suegra
  también bucea, no hace snorkel" pide confirmar; con "sí" pasa a `{certified_diving: 3}` y cobra 3
  inmersiones.
- **Corrección tras el precio (7b).** Pasa a USD.
- **Correcciones antes del precio.** Con cue se aplican; "mejor desde las islas" sin cue pregunta.
- **Acompañante a trozos (7a).** Cobra 1 inmersión + 1 snorkel.
- **Ninguna confirmación de más** en "desde cartagena" ni en "no, buceamos hace 6 meses".

**Tarea 7 cerrada.** Queda en "Para reinvestigar" lo que salió al medirla y es de otra familia: D, E,
F, G y H.

### Hallazgo H y F.2/F.3, arreglados: tramos de un total ya sabido y personas nombradas

**H (grave, anterior a la tarea 7).** "hola, vamos 3, mi pareja y yo buceamos y mi suegra hace
snorkel": la guarda de cifras tiraba el reparto `{2, 1}` del LLM, encolaba las dos actividades y
preguntaba "¿cuántos serían para buceo certificado?". La respuesta se fusionaba con
`_merge_companion_activity`, que suma sin mirar el total: "uno" dejaba 4 personas y el siguiente
tramo 5, con un total de 3 conocido. Reproducido igual en 4a9c327, antes de 7a.

**Regla única**, que el núcleo ya aplicaba a las personas sin decidir: **con el total sabido, la
actividad principal se queda con el resto.** Vive en un único helper, `_with_main_rest`, que ahora
usan los tres sitios.
- **F.2, partición de las personas nombradas.** Si las cifras del reparto suman exactamente las
  personas nombradas una a una, incluido quien escribe (`_named_people`), es un reparto de esas
  personas y se acepta.
  - "mi pareja y yo buceamos y mi suegra hace snorkel" nombra a 3 y `{2, 1}` las cubre.
  - Los plurales ("mis amigos") siguen sin contar.
- **Arreglo de H en la guarda.** Si solo la actividad principal se queda sin respaldo y hay un total
  que dijo el mensaje o la conversación (nunca el del LLM), su cifra es el resto.
- **Cola dentro del total.** Si aun así hay tramos sin respaldo ("vamos 5, mis amigos bucean y mis
  primos hacen snorkel"):
  - no se pregunta la principal;
  - se guarda `pending_split_total`;
  - la respuesta a "¿cuántos para X?" se reparte dentro del total (`_assign_split_share`) y, al
    contestar el último tramo, la principal se queda con el resto.
  - Si las respuestas superan el total, se hace la pregunta de 7a ("¿seguís siendo N o se suma
    alguien?").
  - El marcador se limpia donde se limpia la cola.
- **F.3 queda cubierto por la misma partición:** "my daughter is 9 and my son is 12, my wife and i
  dive" (4 personas, `{certified_diving: 2, undecided: 2}`) conserva el total 4.

**Medido sin LLM:**
- Suite 2258, con 6 tests nuevos.
- Foto determinista de los 66 escenarios de las baterías de grupo y booleanos, HEAD frente a
  árbol: **0 cambios**.

**Medido con el LLM real:**
- **Reproducción de H, 3/3.** "vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel" guarda
  `{certified_diving: 2, snorkel: 1}` y cobra 3 personas (antes 5). "vamos 5, mis amigos bucean y
  mis primos hacen snorkel" solo pregunta el snorkel; "uno" deja `{snorkel: 1, certified_diving: 4}`,
  total 5.
- **Acompañante a trozos (7a):** sigue correcto.
- **Batería de grupo, config PRE: 13/17, 13/13, 17/17, con 4 cambios frente a la base.** Son p02,
  p03, p05 y p07: el reparto vacío o el total sin fijar. **No los causa H**, comprobado por cuatro
  vías:
  - la foto de prompts es idéntica, 86/86 byte a byte;
  - las peticiones son idénticas en HEAD y en el árbol (función, huecos y campos a verificar);
  - con la misma respuesta del LLM, HEAD y el árbol dejan el mismo estado;
  - sonda real en HEAD (c45cd8b, ya en PRE, sin H): p02 1/2, p05 1/2, p07 0/2, el mismo fallo.
  
  Con los mismos prompts, el LLM devuelve a veces `{}` completo para esos mensajes. El 17/17 de las
  16:45 fue una tirada favorable. Pasa a "Para reinvestigar" (I).

**Pendiente de medir: `eval --core` completo.** La tanda abortó en el primer caso por rate-limit (429,
cuota diaria agotada tras las mediciones del día). El script para en seco para no publicar números
degradados. Los dos casos del eval-set que F.2 cambia (`grp-es-mixed-suegra`,
`grp-en-implicit-count-ages`) están cubiertos por tests con la respuesta exacta que dio el LLM real en
la sonda de la tarea 6. Repetir la tanda con cuota y compararla por caso con la de 7b (216/230).

### Hallazgo D, arreglado (pendiente de medir con el LLM): la pregunta de pronóstico se escala

**Síntoma** (batería del router, caso `s04-llover-manana`). Con "¿va a llover mañana en cartagena?"
el LLM devolvía `{"weather_conditions": true}` (3/3 con el enum de hoy): un valor del enum de
`sensitive_topic` sacado a clave propia, en vez de `{"sensitive_topic": "weather_conditions"}`.
Ninguna palabra clave lo caza, nadie leía esa clave y el mensaje seguía el flujo normal, donde se
podía inventar el pronóstico. La respuesta de escalado ya existía (`SENSITIVE_RULES` /
`sensitive_response_for`); solo fallaba la forma.

**Arreglo, sin vocabulario y desde el esquema.** Un único lector, `llm_client.tool_arguments(tool_call,
tool)`, para los 7 sitios que leían la respuesta de un tool: router, extracción ×3, señales,
resolutor de slot y notas.
- **Se reencaja** una clave que el tool no declara, con valor `true`, que sea valor del enum de un
  solo campo vacío.
- **No se toca** si el valor es de texto (sería otra cosa, no un flag aplanado), si pertenece a
  varios enums o si el campo ya viene relleno.
- Arregla la misma forma de fallo en cualquier enum de cualquier tool, sin coste en peticiones.

**Medido sin LLM:**
- 8 tests: el reencaje, las formas que no se tocan y `detect_routing_signals` con un cliente falso que
  devuelve exactamente la respuesta de la sonda real, que ahora da `sensitive_topic` y su respuesta de
  escalado.
- Suite 2266. Sin cambios de prompts.

**Pendiente con cuota:** `scripts/battery_router_signals.py` (37 casos), para ver `s04` en verde y
que ninguna otra señal cambie.

**D con el LLM real: el primer arreglo no bastaba, medido y corregido.**
- **Primera tanda de la batería del router tras el deploy:** `s04` seguía **0/3**.
- **Por qué:** la sonda de los argumentos crudos mostró que el LLM rellena **todos** los campos del
  tool, también los de enum de texto con `false`, y además repite claves:
  `{"sensitive_topic":false, ..., "comparing_options":false, "booking_change_topic":false,
  "weather_conditions":true}`. La guarda solo trataba como vacío `None`/`""`/`[]`/`{}`, así que
  `sensitive_topic: false` contaba como "ya relleno" y no se reencajaba. El test con cliente falso
  lo construí sin esos `false` y no lo vio.
- **Corrección, desde el esquema y más estricta:** un campo está vacío para el reencaje cuando **no
  trae un valor válido de su enum**. Un valor real (`"medical_questions"`) nunca se pisa. El test
  usa ahora la cadena exacta que devolvió el LLM real. Suite 2267.
- **Lectura de las otras diferencias de esa primera tanda frente a la base:**
  - `r07`-`r09` (3/3 → 0/3) no son regresión: la base de esos tres venía de la tanda en la que
    `router.py` llevaba el enum del registro, revertido después. Con el enum de hoy no caben esas
    comparaciones (router 6/9, ya documentado).
  - `s05` (0/3 → 3/3) es el cambio de etiqueta, que acepta queja o problema en tiempo real.

**D medido con el LLM real tras la corrección** (`battery_router_signals 3 base`): **`s04` 0/3 → 3/3**,
con `{"sensitive_topic": "weather_conditions"}`. Frente a la tanda de justo antes de la corrección,
**es el único caso que cambia**; ninguna otra de las 37 señales se mueve. Resumen 33/37: los 4 que no
pasan son `r07`-`r09` (comparaciones de cursos y especialidades que el enum de hoy no expresa, ya
documentado) y el negativo `n07` (hallazgo E).

**`eval --core` con cuota, tras H y D** (tanda limpia, 0 degradadas): **218/230** frente a 216/230 de 7b.
Por caso, **2 a mejor y 0 a peor**; son exactamente los dos que F.2 debía arreglar:
- `grp-es-mixed-suegra`: el reparto `{2, 1}` de las personas nombradas ya no se tira;
- `grp-en-implicit-count-ages`: se conserva el total 4.

### Hallazgo G, arreglado: un número de otra magnitud no es la respuesta a "¿cuántos?"

**Síntoma, determinista (sin LLM).** El parser de cantidad cogía el primer número de cualquier
mensaje.
- Con "¿para cuántas personas?" pendiente, se leía como total: "hace 3 años que no buceo" → 3, "mi
  hijo tiene 9 años" → 9, "llegamos el 12" → 12, "a las 8" → 8, "2 inmersiones" → 2.
- Con "¿cuántos serían para snorkel?" pendiente, esos números se **sumaban** al total. Solo se
  libraban los mensajes que nombraban otra actividad.
- El caso de la conversación de 7c ("no, buceamos hace 6 meses" → 6) era uno de ellos.

**Arreglo, sin lista de unidades:**
- **Respuesta determinista (`_quantity_answer`):** solo cuenta lo que ES la cantidad (un único
  elemento: "4", "dos", "6+") o lo que el detector ya lee como total del grupo ("somos 4", "4
  personas", "we are 4", "yo y mi pareja"), la misma fuente que la extracción. Lo demás no se
  resuelve ahí:
  - la pregunta del total va al resolutor LLM que ya existía, con su contexto y su guarda de
    anclaje;
  - la de "¿cuántos para X?" se vuelve a hacer.
- **Escribir el título de un botón es pulsarlo** (`_button_value`, para cualquier pregunta con
  botones): "seguimos siendo 2", "si cambialo" o "ya la tenemos" tecleados. Lo destapó un test de
  7a, en el que la regla nueva dejaba sin resolver el título tecleado.
- **Guarda del resolutor LLM del total (`_number_of_something_else`).** Una cantidad que el detector
  ya lee como otra magnitud (inmersiones, días, edades) se descarta.

**Medido:**
- **Sonda del resolutor LLM, 2 repeticiones:**
  - se abstiene en "a las 8", "llegamos el 12", "mi hijo tiene 9 años" y "hace 3 años que no buceo";
  - resuelve bien "unos 3" (3), "seremos 5" (5), "2 adultos y un niño" (3), "un par" (2) y "somos yo
    y mis 3 amigos" (4);
  - leía "2 inmersiones" como 2 personas 2/2, que es lo que cierra la guarda de arriba.
- 34 tests nuevos. Suite 2302.

**G en conversación con el LLM real: una segunda entrada, cerrada con la misma regla.**
- **Repro** (`scripts/repro_old_findings g_numeros`): apertura en plural sin cantidad, para que el bot
  pregunte el total. La primera versión del caso abría con "soy certificado", que se lee como una
  sola persona, y nunca llegaba a preguntarlo.
- **Resultado:** "mi hijo tiene 9 años" y "llegamos el 12" ya no fijan el total (2/2). "2 inmersiones"
  seguía fijando 2 personas (2/2), pero no por el resolutor, que ya tenía la guarda: entraba por el
  **relleno LLM de la extracción**, porque el total es un hueco que se le pide.
- **Arreglo:** la misma guarda (`_number_of_something_else`) en el único punto donde el relleno entra
  al turno: un `group_size` del LLM que el detector lee como inmersiones, días o edades se descarta.
  Test con el relleno mockeado. Suite 2303.

**G destapó una alucinación que ocultaba el orden de las guardas: medido y corregido.**
- **Síntoma.** En la conversación de la repro, el turno "2 inmersiones" dejaba `is_colombian=False`
  sin que nadie lo dijera (2/2).
- **Causa**, localizada con traza del escritor y el patch copiado. La petición del turno, con el
  historial completo (hijo de 9 años y acuses del bot), devolvía `{"group_size": 2, "is_colombian":
  false}`; con un historial corto no pasaba (0/15).
  - Antes de G, ese `group_size` contaba como respuesta a la pregunta pendiente y la guarda (b)
    tiraba el booleano que viajaba con él.
  - La guarda de G quitaba el `group_size` **antes** de la (b), así que la (b) ya no veía el intento
    de respuesta y dejaba pasar la nacionalidad.
- **Arreglo, sin regla nueva:** la guarda de G va **después** de la (b). Aunque el total no valga, el
  LLM trató el mensaje como respuesta a la pregunta pendiente, y lo que viaja con ese intento no es de
  fiar. Test con el patch exacto del LLM real. Suite 2304.

**G medido tras el reorden, con el LLM real y en conversación completa (2/2):** con "¿para cuántas
personas?" pendiente, "mi hijo tiene 9 años", "llegamos el 12" y "2 inmersiones" no fijan el total
ni la nacionalidad; "somos 3" fija 3. **Hallazgo G cerrado.**

### Hallazgo I: el reparto de "persona con estado distinto" ya no depende de que el LLM conteste

**Síntoma**, medido con el LLM real. En la familia p de la batería de grupo, con estado vacío, el LLM
devolvía a veces `{}` entero y el reparto dependía de esa tirada: p02 1/2, p05 1/2 y p07 0/2 en HEAD,
con prompts y peticiones idénticos. Casos: "soy certificado y mi hijo no", "my wife is certified and
I am not" y "mi pareja tiene el advanced y yo no tengo nada". Disparar más peticiones no bastaba: en
p07 la segunda petición de grupo también volvía vacía, y además cuesta RPD.

**Causa estructural: la elipsis del contraste.** El detector ya tiene una regla por persona (otra
persona nombrada y quien escribe, de estado contrario → `{certified_diving: 1, undecided: 1}`),
pero necesita las dos certificaciones. La frase coordinada no repite el predicado ("..., yo no",
"y mi hijo no", "and I am not", "y yo no tengo nada") y `certification_claim` devolvía None para ese
lado.

**Arreglo, sin vocabulario de dominio: `elided_certification`.** La frase coordinada sin afirmación
propia, cuyo sujeto es la contraparte ("yo"/"I" si lo afirmado es de otra persona, o la persona
nombrada si es de quien escribe), se lee **por su propia polaridad**:
- **Negación → no certificado**, aunque la frase siga ("yo no tengo nada").
- **Afirmación → certificado**, solo si quitado el sujeto quedan partículas o auxiliares ("pero yo
  sí", "but I am"). "yo sí quiero bucear" no cuenta.
- **Solo hay reparto si las dos polaridades son distintas.** "mi amigo no tiene licencia y yo
  tampoco" no reparte.
- Reutiliza `_CLAUSE_BOUNDARY_RE`, `_SINGULAR_PERSON`, `certification_claim` y `holds_padi_cert`. La
  regla por persona solo rellena el lado que falta.

**Medido sin LLM:**
- **Foto del detector** sobre 265 entradas (eval-set, las tres baterías y sondas de contraste):
  **18 cambios, todos buscados**.
  - p01, p02, p03, p05 y p07 reparten de forma determinista, con total 2.
  - Las sondas de contraste también, incluidas las afirmativas.
  - Ningún mensaje del eval-set cambia.
- **Consecuencia aceptada:** "mi hermano es buzo, yo no quiero bucear" deja a quien escribe sin
  decidir y el bot le recomienda opciones.
- **Quedan fuera:** plurales vagos, "tampoco", mensajes sin estado dicho y dos personas nombradas
  sin quien escribe.
- **Tests:** 22 nuevos.
  - Se actualizan dos que fijaban la limitación anterior.
  - "mi amigo tiene licencia, yo no" pasa de "no reparte" a reparto.
  - El test de la segunda petición de grupo usa ahora un mensaje que el detector no puede repartir.
- Suite 2326.

**I medido con el LLM real** (batería de grupo, config PRE, 3 repeticiones): **17/17 repartos, 13/13
total, 17/17 riesgo, 0 alucinaciones, 0 parciales, 0 totales mal, 0 cambios frente a la base de las
12:51**. p02, p03, p05 y p07 salen `gs=2 {certified_diving: 1}` en las 3 repeticiones; antes daban
1/2, 1/2 y 0/2 según contestara el LLM.

**`eval --core` tras I:** **218/230, idéntico por caso** (0 a mejor, 0 a peor; tanda limpia). **Hallazgo I cerrado.**

### Hallazgo E: reparto por personas leído como comparación (arreglado)

**Síntoma.** "tengo un amigo que quiere bucear y yo hago snorkel": el router marca
`comparing_options` 3/3 y `_is_deliberation_between_options` lo acepta (2 ofertas, sin cifra ni
"quiero"). El turno va a RAG a explicar la diferencia en vez de a la reserva.

**Referencia con el LLM real** (`repro_old_findings 3 reparto_personas`, conversación completa):

| Frase | Base |
|---|---|
| "tengo un amigo que quiere bucear y yo hago snorkel" | 3/3 a comparar |
| "mi novia hace el minicurso y yo buceo" | 1/3 a comparar |
| "my wife wants to snorkel and I'll dive" | 0/3 a comparar |
| control: "mi amigo no sabe si bucear o hacer snorkel" | 3/3 a comparar (correcto) |

**Causa estructural.** La puerta ya descartaba al LLM cuando el mensaje reparte con cifras ("2
bucean, mis amigos hacen snorkel"). El mismo reparto sin cifras no tenía señal: cada oferta va con
su propio sujeto.

**Arreglo, sin verbos ni frases nuevas.**
- `clause_subject(clause)` en el detector: "writer" si la frase solo nombra a quien escribe, "other"
  si solo nombra a otra persona, None si a las dos o a nadie. El contraste elíptico de la I usaba
  esa misma lectura en línea y ahora la llama (con `_SINGULAR_PERSON`).
- `_offerings_with_own_subject` en el núcleo: frase a frase (`_CLAUSE_BOUNDARY_RE`), ofertas de quien
  escribe y de otra persona, distintas → reparto. Va junto a la regla de las cifras, después de la
  duda escrita, así que "mi novia bucea y yo no sé si snorkel o minicurso" sigue comparando.
- Conservador: una frase sin sujeto explícito ("hago snorkel" sin "yo") no cuenta, y el turno sigue
  dependiendo del LLM como antes.

**Medido sin LLM.** Foto de la puerta (con y sin `comparing`) y de `elided_certification` sobre
2308 frases (eval-set, baterías y literales de los tests), HEAD frente al árbol: **10 cambios, todos
con el LLM diciendo comparing y todos repartos con sujeto propio** ("mi esposo bucea, yo prefiero
snorkel", "yo haría el minicurso y mi novia snorkel"...). Sin la señal del LLM, 0 cambios. El
contraste elíptico, 0 cambios.

**Medido con el LLM real** tras el cambio: la frase de E 3/3 reservando (`{snorkel: 1,
certified_diving: 1}`, total 2, pregunta la ubicación), el minicurso 3/3, el inglés 3/3 y el control
3/3 comparando. El router no cambia (ni prompt ni tool), así que no se repite su batería; el
eval-set y la batería de grupo no pasan por esta puerta y la foto ya los cubre.

- Tests: 16 nuevos (`tests/test_offerings_by_subject.py`). Suite 2342.

### Hallazgo F.1: "ya llevo el rescue" no contaba como tener el nivel (arreglado)

**Síntoma.** "ya llevo el rescue, quiero seguir buceando": el LLM da `is_certified=True` 3/3, pero
`course_level_is_ambiguous` ve un nivel sin decir si lo tienen y `_flag_cert_or_course` borra el
valor para preguntar "¿ya la tienes o quieres sacarla?". Una pregunta de más, nunca un valor malo.

**Causa.** La pieza de tener un nivel (`_HOLDS_WRITER`, `_HOLDS_OTHER_PERSON`) solo conocía
"tengo/tenemos/tiene(n)" y "have/got".

**Opciones valoradas.** Barrido del corpus: 36 frases salen ambiguas hoy.
- Con verbo de posesión o de haberlo hecho: "ya llevo el rescue", "hola soy Sofia de chile, hice mi
  open water y quiero bucear" (conversación real).
- Deseos que no caza `_WANTS_CERT_RE` ("quiero ser divemaster", "me interesa el rescue").
- Preguntas al centro ("¿tienen el advanced?", "que es el open water").
- **Vía B descartada:** dejar al LLM cuando hay cualquier verbo delante del nivel. Metería en la
  vía del LLM las preguntas al centro y los "me interesa", demasiado amplio para un coste de una
  pregunta.
- **Vía A aplicada:** completar la clase cerrada de verbos de la pieza compartida.

**Arreglo.** Tres piezas en el detector: `_HOLD_VERB_WRITER_ES` (tengo, llevo, hice, saqué, terminé,
completé y plurales), `_HOLD_VERB_OTHER_ES` (tercera persona) y `_HOLD_VERB_EN` (have, has, got,
did, completed, finished, took, con "have done"). Las usan quien escribe y la persona nombrada.
`_WANTS_CERT_RE` sigue ganando ("hice el open water y quiero hacer el advanced").

**Medido sin LLM.** Foto del detector (actividad, certificación, total, reparto, ambigüedad y las dos
posesiones) sobre 2333 frases (eval-set, baterías, escenarios de grupo con estado y literales de los
tests), HEAD frente al árbol: **3 cambios, los tres buscados**. "ya llevo el rescue" (dos) y el mensaje
de Sofía pasan de curso ambiguo a `certified_diving`, certificado.

**Medido con el LLM real.** `eval --core`: **219/230** (218 con la I), 0 a peor, 1 a mejor
(`certification-dialect-rescue-colloquial`), tanda limpia.

- **Consecuencia aceptada:** "llevo el open water a medias" (curso en marcha) se lee como tenerlo.
  No hay ninguna frase así en el corpus.
- **Tests:** 21 nuevos (`tests/test_holds_level_conjugations.py`). Suite 2363.

### Hallazgo F.4: "im from the states" sin nacionalidad (cerrado sin cambio de código)

**Síntoma anotado.** "im from the states, wanna dive": el LLM se abstiene de `is_colombian` y el
eval-set (`prof-en-from-states`) esperaba `false`. Se había atribuido a la sensibilidad del relleno a
la forma del prompt.

**Lo que se vio al investigarlo.** No es un fallo de forma:
- **La definición del campo** (`_FIELD_MEANING_EN/ES`, una sola fuente para el tool y las guías) da
  `false` solo a quien es extranjero **y** no vive en Colombia. "from the states" no dice dónde vive:
  abstenerse es aplicarla bien.
- **El detector hace lo mismo.** "soy de mexico", "i'm from spain", "soy gringo", "we're american",
  "i'm canadian" y "somos alemanes" dan `None`. Solo "soy extranjero" da `false`.
- **Con la abstención, el bot pregunta** cerca del checkout: "are you Colombian or a resident of
  Colombia?". Una pregunta, sin valor malo.
- **El intento anterior** de ampliar la definición (grupo mixto) rompía al residente.

**Decisión del owner: preguntar.** Se corrige la expectativa a `null` ("el extractor debe
abstenerse", la convención de `neg-en-no-location-signal`). "vivo en españa pero estoy de visita"
sigue esperando `false`: ahí sí dice que no vive en Colombia.

- **Sin cambio de código ni de prompt.** 0 peticiones.
- **Eval:** no se repite la tanda. En la última (`eval --core` tras F.1) el caso se abstuvo de
  `is_colombian` y acertó la actividad, así que con la expectativa corregida cuenta como acierto.

### Hallazgo A: grupo con nacionalidades mixtas (arreglado, decisión del owner: que lo lea el LLM)

**Síntoma.** Decisión del owner (2026-09-14): un grupo mixto paga todo en USD. La detección era
`_MIXED_NATIONALITY_RE`, una lista de fraseos en la cascada, el nodo `booking` y el router. No conocía
gentilicios ("somos colombianos pero mi amigo es aleman" cobraba en COP) y marcaba mixto "mi amigo es
colombiano y yo tambien". `eval --core`: 6/6 casos `nat-mixto-*` fallaban.

**Opciones presentadas al owner.**
- Lectura por frases con el vocabulario conocido: 3 de 6 casos.
- Preguntar al grupo.
- **Un valor propio en el LLM (elegida).**

**Sonda antes de tocar src** (22 frases y luego 28, 2 repeticiones, tool actual frente a variante):
- **v1 de la descripción:** 8/8 mixtos, residentes y controles bien, el resto de campos igual salvo en
  2 mixtos (`is_colombian` a `false`, en la dirección buscada). Falsos positivos 2/2: "ninguno
  colombiano" y "mi novio es aleman y quiere hacer snorkel". El LLM supone la otra mitad.
- **v2 (insistiendo en no suponer la nacionalidad de nadie): peor.** Marca mixtos a los residentes
  ("somos extranjeros pero vivimos en colombia" 2/2) y cambia `is_colombian` de "no soy colombiano pero
  vivo en colombia" 1/2. Descartada.
- **Los fallos de v1 son todos de un solo lado del grupo:** eso lo corta la estructura, no el prompt.

**Arreglo.**
- `extraction_tool(extra_fields)`: `EXTRACTION_TOOL` intacto, o una copia con `mixed_nationality`
  (definición en `_FIELD_MEANING_EN`, texto v1). `fill_gaps` y `extract_and_verify` aceptan
  `extra_fields`, que nunca abren una petición solos.
- `mentions_writer_and_others` (detector): quien escribe o su grupo (`yo/I/me`, "nosotros/we/us" o la
  desinencia "-mos") Y otra persona (`_NAMED_OTHER_PERSON`) o parte del grupo
  (`_OTHER_PERSON_SUBJECT_RE`: "uno es", "the others are"). Es la puerta para pedir el valor.
- Núcleo: si vuelve `true` y se pidió, `is_colombian=False` (con `overwrite`, porque el regex pudo leer
  "colombianos") y el turno responde con `_mixed_nationality_response`, la copy ya decidida. Una sola
  fuente: la lista sale de la cascada, del nodo del grafo y del router; `_mixed_nationality_response`
  ya no escribe el historial.

**Medido sin LLM.**
- `snapshot_prompts`: los 86 prompts idénticos byte a byte; 1 nuevo, la variante del tool.
- Suite 2379 (16 tests nuevos en `tests/test_mixed_nationality_llm.py`; se quitan los 3 que fijaban la
  lista y el e2e pasa a mockear el extractor).

**Medido con el LLM real.**
- `eval --core`: **226/230** (219 con F.1), **0 a peor, 7 a mejor**: los 6 `nat-mixto-*` y
  `prof-en-from-states`, este último por la expectativa corregida en F.4. Tanda limpia.
- Conversación completa (`repro_old_findings 3 grupo_mixto`): "somos colombianos pero mi amigo es
  aleman" y "yo vivo en bogota y mi amigo es gringo" 3/3 con la explicación de USD; el residente
  extranjero y "mi novio es aleman y quiere hacer snorkel" 3/3 siguen la reserva sin marcar mixto.
- **Batería de grupo** (config PRE, 3 repeticiones): 16/17, 13/13, 17/17. Único cambio, `b03-con-titulo`
  ("4 con titulo y 2 snorkel"), que no abre la puerta. Repetido con el hash de cada petición: **la misma
  petición en HEAD y en el árbol** (`b8637c7eb17e`), con resultado variable en los dos (2/3 y 1/3).
  Variabilidad del LLM.
- **Batería de booleanos:** 18/24 legítimos, 15/18 alucinaciones evitadas. Único cambio,
  `charla-vale-perfecto` ("vale perfecto"), que no abre la puerta. HEAD en la misma tanda: 17/18, y
  repetido con hashes: **la misma petición** (`739e80bb2ecb`), 2 de 4 alucinan en los dos. No es A; queda
  como hallazgo J (la referencia de 7b lo evitaba 3/3).

- **Consecuencia aceptada:** "somos de nacionalidad mixta", sin nombrar a nadie, no abre la puerta y ya
  no dispara la explicación.

### Hallazgo J: "vale perfecto" rellena is_certified=False (arreglado)

**Síntoma** (visto al medir A). Batería de booleanos, `charla-vale-perfecto` (ubicación pendiente,
buceo certificado y total 2 sabidos): la alucinación se evitaba 3/3 en la referencia de 7b y hoy 2 de 4,
con la petición idéntica byte a byte en HEAD y en el árbol.

**Búsqueda del origen, sin gastar peticiones.** `bool_scn_hash.py` corta la llamada al LLM antes de
enviarla y guarda el hash de la petición. Recorrido por los commits desde 7b:
- **4c7e2df (antes de 7b):** `d418eabc0b7b`.
- **c45cd8b (7b) y todos los posteriores hasta e3fa566:** `739e80bb2ecb`.

La petición cambió solo en 7b. La medición de 7b ya se hizo con esa petición: su 3/3 fue suerte.
Tasa con 8 repeticiones: **antes de 7b 0/8, HEAD 5/8**.

**Causa.** 7b añadió la verificación de campos sabidos a la petición del turno: con huecos, el turno
pasaba del prompt de rellenar (`extraction_system_prompt`) al combinado (verificar primero, rellenar al
final). Con ese prompt, un mensaje sin contenido rellena booleanos desde el historial.

**Descartado:**
- **Ampliar `_is_short_ack`:** no conoce "perfecto", "gracias" ni "listo", y la siguiente jerga ("de una",
  "chévere") volvería a caer.
- **"El detector no vio nada":** "ah y somos paisas" tampoco lo ve el detector y hay que rellenarlo.

**Sonda antes de tocar src** (`j_probe.py`, 13 casos × 3). Mismos estados, huecos y campos sabidos que el
núcleo. Compara V (HEAD, combinado) con F (los campos sabidos como campos a rellenar y la contradicción por
comparación). **V 25/39, F 36/39.**
- "vale perfecto": V 1/3, F 3/3.
- "ah no, somos gringos": V 1/3, F 3/3 (V proponía además total 4 y un reparto con `undecided` 2/3).
- "al final mi suegra también bucea…": V 1/3, F 3/3.
- "perfecto, gracias": V inventaba `group_size` 4 2/3, F 3/3 limpio.
- "ah y somos paisas": los dos rellenan la nacionalidad, pero V añadía `is_certified=False` 3/3.
- **Único fallo de F:** "al final somos 4", igual en V (propone total 4 con la persona nueva `undecided`,
  razonable; la expectativa de la sonda era estricta).

**Arreglo.**
- Misma petición única (decisión del owner en 7b): `extract_and_verify(gaps + recheck, veto_fields, ...)`.
  Sin campos del regex que vetar, es el prompt de rellenar de siempre.
- Lo devuelto para los campos sabidos se compara con lo guardado con `disagreements_with`, que es también
  la comparación de `verify_fields` y `extract_and_verify` (dos bucles iguales menos). Esos valores salen
  del patch antes de aplicarse.
- El LLM sigue sin ver el valor guardado. La verificación propia (sin huecos, tras el cierre) y el veto
  de lo que resolvió el regex en el turno no cambian.

**Medido.**
- `snapshot_prompts`: 87 idénticos byte a byte. Suite 2379 (2 tests actualizados al nuevo contrato).
- Batería de booleanos: **18/24 legítimos, 18/18 alucinaciones evitadas** (15/18 con A). Único cambio,
  `charla-vale-perfecto` 0/3 → 3/3.
- `eval --core`: **226/230, idéntico por caso**, tanda limpia.
- Batería de grupo (config PRE): **17/17, 13/13, 17/17**. Único cambio, b03, que vuelve a OK (ya
  probado variable con la petición idéntica).
- Conversaciones de 7b (`repro_old_findings 2`): corrección tras el precio a USD 2/2, correcciones antes
  del precio iguales y actividad del acompañante que llega tarde 2/2.
- `f01_conversacion`: "al final mi suegra también bucea, no hace snorkel" tras el cierre fue a RAG 2/2.
  Con la reserva cerrada ese turno no tiene huecos (no pasa por este cambio) y la puerta de deliberación
  corre antes de la extracción; ya pasó en la tanda de H. **Hallazgo K**, anotado en pendientes.

### Hallazgo K: una oferta negada contaba como opción que se compara (arreglado)

**Síntoma** (visto al medir J). `repro_old_findings f01_conversacion`: tras el cierre, "al final mi suegra
tambien bucea, no hace snorkel" fue a RAG 2/2 (también en la tanda de H; en la de 7b pedía confirmación
2/2, intermitente). El router marca `comparing_options` y `_is_deliberation_between_options` lo acepta:
dos ofertas, sin cifra, sin "quiero" y sin sujetos distintos (E). La puerta va antes de la extracción,
así que J no lo causa.

**Causa estructural.** La puerta cuenta las ofertas nombradas, pero el snorkel está negado: se descarta,
no se sopesa.

**Arreglo, sin palabras nuevas.**
- `_weighed_offerings`: frase a frase (`_CLAUSE_BOUNDARY_RE`), las ofertas de una frase cuya primera oferta
  va negada no cuentan. La negación es `_is_negated` del detector (con paridad: "no es que no quiera
  bucear" sigue afirmando), mirada sobre las palabras anteriores a la primera que ya nombra una oferta.
- **Primer intento, corregido antes de medir:** rompía el control de E. En "mi amigo no sabe si bucear o
  hacer snorkel", la ventana de la negación llega a "bucear". Una pregunta subordinada corta su alcance:
  `_EMBEDDED_QUESTION_WORDS` ("si", "if", "whether", "entre", "between"), una clase cerrada.
- Solo en el camino que depende del LLM, después de la duda escrita, las cifras y el sujeto propio (E).
  "no sé si buceo o snorkel" sigue comparando.

**Medido sin LLM.** Foto de la puerta (con y sin `comparing`) y del contraste elíptico sobre 2325 frases,
HEAD frente al árbol: **14 cambios, todos con el LLM diciendo comparación y todos correctos**. Sin la señal
del LLM, 0 cambios; el contraste elíptico, 0.
- **El caso de K** y "just snorkel, no diving": una elección, no una comparación.
- **"nunca he buceado", "no sé bucear", "nunca hemos hecho buceo", "primo nunca ha buceado":** la misma
  frase contaba como dos ofertas (buceo certificado por "buce*" y minicurso por el cualificador de
  experiencia).
- **"mi novia es buza certificada y yo nunca he buceado"** (grupo) y **"Me interesa el curso PADI, no se
  bucear"** (ya eligió el curso).
- **Con "?":** otra puerta anterior las atiende, sin cambio de flujo.

**Medido con el LLM real.** `repro_old_findings 3 f01_conversacion`: **3/3 pide confirmar el cambio** y,
tras "sí", cobra 3 inmersiones. El router no cambia y el eval-set no pasa por esta puerta, así que no se
repiten su batería ni el eval.

- Tests: 13 nuevos (`tests/test_negated_offering.py`). Suite 2392.

### Hallazgo B: respuesta doble con otra pregunta pendiente (arreglado)

**Síntoma.** Con la ubicación pendiente, "desde cartagena, somos paisas" perdía `is_colombian`. La guarda
(b) descarta todo booleano que viaja con la respuesta a otra pregunta: "Desde Cartagena" rellenaba
`is_colombian=True` 3/3. Batería de booleanos: `doble-cartagena-paisas` y `doble-bocagrande-aowd` 0/3.
Separar la frase del slot con regex no servía: no localiza "salimos de bocagrande" ni "somos paisas", y
una cortesía de resto dejaría pasar la alucinación.

**Pista aplicada:** que el extractor diga en qué parte del mensaje apoya cada booleano, en la misma
petición.

**Sonda antes de tocar src** (`b_probe.py`: los 14 escenarios de la batería + 7 nuevos, cortesías y
dobles; misma petición que el núcleo, tool actual frente a variante con `evidence`):
- **v1, con cita también de `location` y `group_size`:** legítimos 16/22 → 22/22 y alucinaciones 20/20,
  pero en los dos mensajes con Bocagrande el LLM citaba "Bocagrande" y **dejaba de rellenar `location`**
  2/2. Descartada.
- **v2, cita solo de los booleanos:** legítimos **24/33 → 33/33**, alucinaciones **30/30** igual; el patch
  solo difiere en `is_certified` de "somos 3, todos colombianos", sacado del historial en las dos
  variantes y descartado igual por la guarda.
- **Citas del historial** ("si los dos", "somos 2"): aparecen pese a la instrucción. Las filtra la regla
  de que la cita esté en el mensaje.

**Arreglo.**
- `extraction_tool(["evidence"])`: objeto con una cadena por booleano. `EVIDENCE_FIELDS` en los prompts,
  con un test que la ata a `_BOOL_PATCH_FIELDS` del núcleo.
- Se pide solo si la guarda (b) puede actuar: la pregunta pendiente la contesta un campo extraíble que no
  es booleano (ubicación, total; `_asks_for_evidence`). Viaja con `extra_fields`, sin peticiones de más.
- `_quote_backs_boolean`: la cita respalda el booleano si está literalmente en el mensaje (sin tildes ni
  puntuación), no es el mensaje entero y el detector no lee en ella la respuesta pendiente.
- `_pending_answer_field`: una sola lectura del campo que contesta la pregunta pendiente para la guarda
  (b), la de campos sabidos y la cita.

**Medido.**
- `snapshot_prompts`: 87 idénticos, 2 nuevos (la variante y la lista). Suite 2405 (13 tests nuevos en
  `tests/test_double_answer_evidence.py`).
- Batería de booleanos (21 escenarios, 3 repeticiones): **legítimos 33/33, alucinaciones evitadas
  30/30**. De los 14 anteriores solo cambian las dos dobles, 0/3 → 3/3.
- Conversación completa (`repro_old_findings 2 respuesta_doble`): "desde cartagena, somos paisas" guarda
  ubicación y nacionalidad y pasa a seguridad 2/2; "desde cartagena, gracias" no cuela la nacionalidad 2/2.
- `eval --core`: **226/230, idéntico por caso**, tanda limpia.
- Batería de grupo (config PRE): 17/17, 13/13, 17/17, **0 cambios de veredicto**.

### Hallazgo C: ubicación entre detector y núcleo (hecho en parte, con un resultado negativo)

**Punto de partida.** Dos lectores de la ubicación:
- el resolutor corto del núcleo (`_apply_short_answer`, solo con la ubicación pendiente), con su propio
  `_CARTAGENA_RE`/`_ISLAND_RE`;
- `_detect_location` del detector (cada turno), con apodos, hoteles e islas concretas.

Discrepaban en 29 de 155 mensajes con palabra de lugar:
- el núcleo no conocía apodos ni hoteles y leía isla en "rezar el rosario";
- el detector no usa "isla" suelta;
- con Cartagena y una isla en el mismo mensaje, las precedencias son contrarias (detector: isla
  concreta primero; núcleo: Cartagena primero).

El veto LLM de `location` está apagado por defecto (no se ha podido comprobar PRE sin leer `.env.pre`).

**Referencia con el LLM real** (`c_probe.py`, 2 repeticiones; apertura con `_understand`, respuesta con
`route_message` y la ubicación pendiente): **apertura 16/22, pendiente 14/20**.
- **Fallan:** "quiero ir a las islas del rosario desde cartagena" (apertura → isla), "we're in cartagena
  now, staying on the islands tomorrow" (los dos contextos → Cartagena), "estoy en cartagena pero el
  hotel es en isla grande" (respuesta → Cartagena), "nos vemos en la marina" (→ isla) y "rezar el
  rosario" como respuesta (→ isla).

**Primer diseño, medido y revertido: con los dos lugares, ningún lector determinista decide y el LLM
rellena el hueco.** Sonda con el LLM real:
- **"llegamos a cartagena y luego nos vamos a baru":** apertura 2/2 → **0/2** (isla).
- **"vamos de cartagena a baru":** Cartagena en HEAD → **isla 2/2**.
- **"quiero ir a las islas del rosario desde cartagena" como respuesta:** 2/2 → **0/2**.
- **Mejora:** solo "we're in cartagena now…" en apertura (0/2 → 1/2).
- **En los mismos casos de la referencia:** apertura 16 → 15 de 22, pendiente 14 → 14 de 20.

El prompt de relleno y el resolutor de slot también leen el destino de la excursión como la ubicación:
mejora uno y empeoran otros, no se acepta. Sigue abierto (C.2). La pista sería la definición del campo,
que no dice que el destino no cuenta, medida con esta misma sonda.

**Lo que queda: una sola fuente de palabras de lugar.**
- `_CARTAGENA_NAME_RE` (nombre y apodos, antes una cadena de `if`) y `_GENERIC_ISLAND_RE` ("isla",
  "island", "Barú", "los rosarios") en el detector.
- `_departure_place` del núcleo: Cartagena nombrada gana (la precedencia de siempre en la respuesta);
  si no, el lector del detector (islas concretas, hoteles, la guarda de "rezar el rosario"); si no, una
  isla sin nombre vale como respuesta. Fuera `_CARTAGENA_RE`/`_ISLAND_RE`.

**Medido sin LLM** (`c_snapshot.py`, 3379 frases, HEAD frente al árbol):
- **detector, 0 cambios**;
- **resolutor corto, 55 cambios**, todos en la dirección buscada salvo uno:
  - hoteles y apodos que antes iban al resolutor LLM ("Hotel Pao Pao", "La Heroica" ya salían bien 2/2 por
    esa vía en la referencia: mismo valor, sin petición);
  - "rezar el rosario" deja de ser isla (2/2 sin ubicación con el LLM real);
  - unos cuantos son literales de tests con forma de identificador;
  - **el que no:** "nos vemos en la marina" como respuesta pasa a isla, por el alias "marina" que el
    detector ya tenía (C.3).
- El eval-set no pasa por el resolutor corto (`_understand` y el detector no cambian), así que no se
  repite.

- Tests: 19 nuevos (`tests/test_location_single_source.py`). Suite 2424.

### Tarea 8: observabilidad, LangSmith frente a Langfuse (analizada, pendiente del owner)

**Hoy.** PRE traza con LangSmith: `trace_openai` envuelve cada cliente OpenAI y el SDK traza el grafo
(`AGENT_ARCH=true` en el compose de PRE). El plan Developer agotó su cuota (274 respuestas 429 en una
pasada de batería dentro del contenedor): PRE se queda sin trazas y las pruebas gastan la misma cuota
que el tráfico real.

**Medido** (`obs_volume.py`, reserva completa con `route_message`, grafo activo, RAG simulado, sin enviar
nada fuera): 4 turnos, **12 llamadas al LLM (3 por turno)** y 2 ejecuciones raíz de LangGraph por
turno. El colector local no ve los nodos anidados. Los turnos de RAG (embeddings, respuesta, juez) no
están en la cifra.

**Planes** (consultados el 2026-09-16):
- **LangSmith Developer:** 5.000 trazas base/mes, 14 días, 1 usuario; rechaza al pasarse. Plus: 39 $ por
  asiento al mes.
- **Langfuse Cloud Hobby:** 50.000 unidades/mes (traza + spans + llamadas LLM + evaluaciones), 30 días,
  2 usuarios; sin excedente en el plan gratis. Core: 29 $ al mes.
- **Langfuse self-hosted:** gratis (código abierto), pero pide Postgres, ClickHouse, Redis, S3, web y
  worker, ≥ 4 vCPU y 16 GiB; Docker Compose solo lo recomiendan para pruebas. No cabe en el VPS
  actual, que ya lleva PRE, PRO, Chatwoot, tres Postgres y tres Redis.

**Estimación** con 6 turnos por conversación:
- **LangSmith:** 1–2 trazas por turno → **~420–830 conversaciones/mes**. Si las llamadas al LLM no se
  anidaran dentro del turno, 4–5 trazas → ~170.
- **Langfuse Hobby:** 8–10 unidades por turno → **~830–1.040 conversaciones/mes**.

**Recomendación: Langfuse Cloud Hobby.** Da más margen, 2 usuarios y 30 días, y deja la salida de
alojarlo nosotros sin reescribir la integración.

**Decide el owner:**
- enviar trazas a un tercero, con `src/privacy.py` como máscara;
- tráfico esperado en PRO (por encima de ~800 conversaciones/mes, ningún plan gratis traza todo: muestrear
  o pagar);
- quién crea la cuenta y las claves (un proyecto para PRE y otro para PRO).

**Migración, si se aprueba:**
1. Claves por entorno; sin claves, trazado apagado.
2. `redact_pii` como función `mask`.
3. `trace_openai` pasa al cliente OpenAI de Langfuse, callback en `run_turn_via_graph`, fuera
   `_activate_langsmith_tracing`.
4. Baterías y eval sin trazas por defecto.
5. Una semana midiendo unidades reales en PRE.
6. Retirar LangSmith.

### Hallazgos C.2 y C.3: salida, estancia y destino; formas cortas de isla (arreglados)

**C.2. Punto de partida.** Con Cartagena y una isla en el mismo mensaje, los dos lectores decidían por precedencia
(detector: isla concreta primero; resolutor: Cartagena primero). Dejarlo al LLM se había medido peor (el LLM
también toma el destino por la ubicación).

**Arreglo, estructural: la preposición de cada lugar** (`place_by_role` en el detector, clase cerrada):
- papel de cada mención por la última palabra antes del nombre, dentro de su frase y sin artículos:
  - estancia: "en", "in", "on", "at";
  - origen: "desde", "de", "del", "from";
  - destino: "a", "al", "hacia", "hasta", "para", "to", "into";
- una pregunta subordinada corta el alcance (`_EMBEDDED_QUESTION_WORDS`, ahora con una sola fuente para K y C.2);
- una mención negada no cuenta (`_is_negated`: "no estamos en las islas");
- un hotel de isla es alojamiento (estancia al final del mensaje);
- **decide:** la última estancia > el primer origen > la primera sin preposición > la primera; sin ninguna
  preposición, la precedencia de siempre;
- `_departure_place` del núcleo lee directamente el detector (fuera la regla "Cartagena primero").

**C.3.** Barrido del corpus: los 15 mensajes que el detector fija sin la palabra isla, hotel o resort son nombres
propios correctos (Cocoliso, Pao Pao, Majagua, Bora Bora). El riesgo real son las formas cortas de las islas "Isla X"
("grande", "marina", "arena", "pirata", "pelícano", "pavitos"), que son palabras corrientes. Solo cuentan si el
mensaje nombra una isla (patrón sin "isl" y sin isla nombrada, fuera). Los hoteles no cambian.

**Medido sin LLM** (`c_snapshot.py`, 3395 frases, HEAD frente al árbol): **12 cambios, los buscados**:
- **C.2:**
  - "quiero ir a las islas del rosario desde cartagena" → Cartagena;
  - "we're in cartagena now, staying on the islands tomorrow" → isla;
  - "estoy en cartagena pero el hotel es en isla grande" como respuesta → isla;
  - "estoy en cartagena y me hospedo en el hotel pao pao" → isla;
  - "nos quedamos en baru, vamos a cartagena de paseo" → isla;
  - "salimos de la isla y queremos ir a cartagena" → isla;
- **C.3:** "somos un grupo grande", "nos vemos en la marina", "la arena es blanca", "vamos al pirata" → sin isla;
- **discutible:** "estamos en las islas pero salimos desde cartagena" → isla (la estancia gana al origen).

**Medido con el LLM real** (`c_probe.py`, 2 repeticiones):
- **Apertura 26/28:** en los 11 casos de la referencia, 16/22 → **22/22**.
- **Respuesta a "¿desde dónde saldrías?" 26/26:** en los 10 de la referencia, 14/20 → **20/20**.
- **Único fallo:** "no sé si cartagena o las islas" fija Cartagena, igual que HEAD.
- `eval --core`: **227/230**, 0 a peor, 1 a mejor (`loc-en-cartagena-now-islands-tomorrow`), tanda limpia.

- Tests: `tests/test_location_single_source.py` ampliado (C.2 y C.3). Suite 2446.

## 2026-09-16 — Huecos 1–3 cerrados; peticiones por turno medidas (fusión descartada)

### Hueco 1: querer un nivel con cualquier verbo de querer (arreglado)

**Causa.** `_WANTS_CERT_RE` solo conocía el deseo con objeto directo ("quiero el rescue"). "quiero ser divemaster",
"me interesa el rescue" o "i'm interested in the advanced" dejaban el nivel "sin decir si lo tienen o lo quieren" y
`course_level_is_ambiguous` preguntaba. "quiero la especialidad de nitrox" además no contaba como nombre de producto:
el sustantivo salía solo de las etiquetas de los cursos.

**Arreglo, clase cerrada como la de tener (F.1):**
- `_INTEREST_VERB_WRITER` / `_INTEREST_VERB_OTHER` dentro de `_DESIRE_VERB` ("me/nos interesa", "estoy interesado en",
  "i'm interested in"; "le/les interesa", "is/are interested in");
- el camino al objeto admite llegar a serlo ("ser", "llegar a ser", "be", "become");
- el verbo en tercera persona lleva el sujeto dentro: `_about_other_person` lo lee, así que "le interesa el open water a
  mi hijo" no marca a quien escribe (sí cuenta para repartir el grupo);
- `_product_family_nouns`: curso y especialidad, del registro.

**Medido sin LLM** (`cert_snapshot.py`, 3420 frases, HEAD frente al árbol): 13 cambios de este hueco, todos buscados.
El único del eval-set (`f2b-specialty-nitrox-en`) pasa por el núcleo 3/3 bien.

### Hueco 2: la duración se compone (arreglado)

**Causa.** Dos listas de fraseos. **Arreglo:** cantidad × unidad (`_DURATION_RES`):
- cantidad: cifra, `number_words`, "un par", "varios", "a few"; o la unidad entera ("toda la semana", "the whole
  weekend") o tras preposición de duración ("por el día", "for the day");
- unidad: día 1, fin de semana 2, semana 7, mes 30; total 1 → `single_day`, más → `multi_day`;
- fuera: tiempo transcurrido (`hace` delante, `ago/atrás` detrás), noches, un artículo suelto ("el día 5 de octubre",
  "venimos el fin de semana": dice cuándo, no cuánto);
- residuo no compositivo: paquete (multi-día por definición) y "solo hoy".

**Medido sin LLM** (`dur_snapshot.py`, 3430 frases): 22 cambios, todos buscados; incluye "hace 3 días que llegamos" y
"3 days ago", que antes daban multi-día.

### Hueco 3: "nunca se ha sumergido" con una sola fuente (arreglado)

**Causa.** La regla estaba en `_MINICOURSE_PATTERNS` y en `_NOT_CERTIFIED_PATTERNS` con formas distintas; en inglés
la de certificación solo tenía "never dived". **Arreglo:** `_NEVER_DIVED` (nunca + auxiliares/participios/clíticos +
sumergirse; el inglés elide el objeto: "never tried, …", "never done it before") y `_NEVER_CERTIFIED` con el mismo
esqueleto.
- **Medido y corregido en la foto:** con "tres palabras cualesquiera" en inglés, "i will never stop diving" salía
  principiante; con el participio regular sin "hecho", "nunca hemos hecho buceo" se perdía. Versión final: 10 cambios,
  todos buscados; "never tried nitrox but i am advanced" pasa de minicurso/no certificado a nitrox/certificado.

**Eval-set por el núcleo: 230/230** (antes 227/230), tanda limpia; cambian exactamente `adv-en-elliptical-no-dive-verb`,
`prof-es-toda-la-semana` y `prof-en-just-the-day`, 0 a peor. Suite 2517.

### Optimización 1: peticiones por turno (medida, fusión revertida)

**Qué peticiones hace un turno** (`obs_calls.py`, reserva de 4 turnos con `route_message`, RAG simulado): 12 llamadas.
- `detect_routing_signals` en los 4 turnos (salvo clics numéricos);
- `extract_fields` (petición fusionada de extracción y verificación) en 3;
- la respuesta redactada ("Coral") en 3;
- `capture_notes` en 2 (mensajes de 3+ palabras). El resumen rodante solo cada `history_window_size` mensajes.

**Intento: llevar las notas a la petición del router** (la única de todos los turnos; mismo mensaje crudo). Por turno
real guardaba las mismas notas con 0 peticiones propias (HEAD: 2 en 4 turnos) y la sonda de notas daba 9–10/10 frente
a 10/10. Pero el prompt de las 9 señales no lo aguanta (batería del router, 8 repeticiones en seguridad):
- instrucción "(10) anota en `notes`…" en el prompt: "¿va a llover mañana?" **8/8 → 3/8**; aislado, es la frase del
  prompt y no el campo del esquema;
- solo "ya tienes anotado…": 7/8;
- campo solo en el esquema, detrás de las señales: **2/8** (dos tandas);
- campo delante: el tiempo 8/8, pero a veces el modelo escribe solo las notas y cierra: "perdí una pierna" pierde
  `adaptive_diving_topic` **2/8**.
- Control de ruido: "soy epiléptica" (2 palabras, petición idéntica en las dos columnas) oscila 0–3/8, y "soy
  sordomuda" 4/8–8/8 entre tandas. Aun así, el tiempo cae de forma repetida con notas.

**Decisión:** revertido (una señal de seguridad no se cambia por una petición). Queda una lección para la siguiente
fusión: el prompt del router es el más frágil del bot; la vía restante es la petición de extracción (ya fusionada), con
el eval-set completo, la batería de grupo y la de booleanos.

**De la medida sale un arreglo general:** el LLM repite claves en el mismo objeto (`"sensitive_topic":
"weather_conditions", …, "sensitive_topic": false`) y `json.loads` se queda con la última. `tool_arguments` ya no deja que
el "nada" de un campo (null, false fuera de booleanos, vacío) borre un valor real. La cadena real de la sonda del
hallazgo D ya repetía `sensitive_topic`. Tests en `test_tool_arguments_schema.py`.

### Optimización 2: scripts sin trazas (ya estaba)

`scripts/__init__.py` apaga LangSmith para todo `python -m scripts.X` desde el 2026-09-14 (comprobado:
`langchain_tracing_v2=False`, `trace_openai` no envuelve). La nota de la cola estaba desactualizada.
