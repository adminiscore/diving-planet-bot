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
como el núcleo conversacional nuevo de `docs/conversational-refactor-plan.md`).

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
(`docs/conversational-refactor-handoff.md` §"Sesión 2026-07-22 (tarde)"):
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
