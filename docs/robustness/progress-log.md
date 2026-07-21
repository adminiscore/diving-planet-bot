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

**Resultado real (LLM real, no mockeado)**: **99/100 (99.0%) de acuerdo, 1
desacuerdo, 0 huecos** — sobre el baseline solo-regex de 94% (mockeado, sesión
anterior). Los 8 casos adversariales que antes quedaban como "hueco" (regex solo)
ahora los resuelve el LLM correctamente, salvo uno.

**El único desacuerdo encontrado**:
- Caso `adv-en-negation-contraction`: `"hey we arent certified, first time diving,
  just the two of us"`.
- Esperado: `activity="certified_diving"`. LLM devolvió: `activity="minicourse"`.
- **Análisis**: no es necesariamente un error del LLM — es una ambigüedad real del
  schema/convención existente. En el código actual (`intent_detector.py`, ver el
  comentario junto a la línea `if intent.activity is None and intent.is_certified is
  not None: intent.activity = "certified_diving"`), el valor `"certified_diving"` se
  usa como la categoría GENÉRICA "quiere bucear" independientemente de si está
  certificado o no — el campo `is_certified` es el que decide la sub-rama después. El
  LLM, en cambio, interpretó semánticamente "primera vez, sin certificar, quiere
  probar" como el producto específico "minicurso" — una lectura razonable en
  lenguaje natural, pero que no coincide con la convención interna del código.
- **Implicación para la Fase 1**: antes del cutover del campo `activity`, hay que
  aclarar en el prompt/schema de `llm_extractor.py` que `"certified_diving"` es la
  categoría genérica de intención de bucear (no implica certificación), y que
  `"minicourse"` solo debe usarse cuando el cliente pide explícitamente el
  minicurso/bautismo como PRODUCTO, no como inferencia de "es principiante". Esto es
  exactamente el tipo de ajuste esperable en esta fase — encontrado con datos, no a
  ciegas.
- Este caso YA está en el eval-set (no hace falta añadirlo de nuevo) — sirve como
  regresión permanente para confirmar el ajuste cuando se haga.

**Decisiones tomadas y por qué**: con 99.0% de acuerdo (por encima del umbral ≥98%
propuesto en el plan para el cutover), **la Fase 0 se da por completa**. La Fase 1
(dominio certificación) puede empezar — sus criterios de entrada están cumplidos.

**Qué quedó a medias / bloqueadores**: nada bloqueado. La corrección del prompt de
`activity` (ver "implicación para la Fase 1" arriba) es el primer ítem a resolver
DENTRO de la Fase 1, no un bloqueador de Fase 0.

**Siguiente paso concreto para quien continúe**: empezar la Fase 1 (`plan.md` §4,
sección "Fase 1 — Dominio certificación"):
1. Primero, afinar el prompt/descripción del campo `activity` en
   `src/agents/llm_extractor.py` para resolver la ambigüedad encontrada arriba
   (`"certified_diving"` = intención genérica de bucear, no certificación), con TDD
   (test dirigido a `adv-en-negation-contraction` u otro caso equivalente) antes de
   tocar nada más.
2. Re-correr `scripts/run_extraction_eval.py` para confirmar 100% (o al menos
   mantenerse ≥98%) tras el ajuste.
3. Cambiar la regla de activación de "solo shadow" a "el LLM rellena
   `is_certified`/`activity` cuando el regex los deja en `None`, y el resultado SÍ se
   aplica a `state`" (primer cutover real, aún con el regex como camino primario y
   el LLM solo en huecos — ver plan.md §3.2).
4. TDD + suite completa + verificación en vivo contra PRE (mismo patrón usado toda la
   sesión) antes de dar la Fase 1 por cerrada.
