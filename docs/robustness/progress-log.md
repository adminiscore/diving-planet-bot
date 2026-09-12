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
