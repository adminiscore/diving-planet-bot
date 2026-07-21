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
inconsistencias reales en total (4 documentadas en `docs/live-test-inconsistencies-plan.md`,
2 más de typos documentadas en `docs/HISTORY.md` v0.20.31), se escribió
`docs/robustness-strategy-options.md` con 4 opciones estratégicas para el equipo. El
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
