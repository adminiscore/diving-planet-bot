# Handoff — refactor conversacional (slot-filling): estado exacto para continuar

> Escrito 2026-07-22 (Gadea → equipo). Ejecuta `docs/conversational-refactor-plan.md`.
> Este documento dice **exactamente** hasta dónde llegó el trabajo y qué queda, para
> que cualquiera (Gonzalo) pueda continuar sin releer todo. El registro narrativo por
> fase está en la sección "Registro de progreso" del propio plan; aquí va lo operativo.

## TL;DR del estado

| Fase | Estado | Dónde |
|---|---|---|
| **0 — Andamiaje** | ✅ COMPLETA, en PRE | `src/agents/conversational_core.py`, `settings.conversational_core` |
| **1 — Buceo certificado** | ✅ COMPLETA, **flag ON en PRE**, verificado en vivo | `docker-compose.vps.yml` (`CONVERSATIONAL_CORE: "true"`) |
| **2 — Snorkel/minicurso/acompañante** | ✅ COMPLETA (adelantada) | multi-actividad en el núcleo |
| **3 — Cursos PADI + checkout completo** | ✅ **COMPLETA (2026-07-22)** — las 2 causas raíz cerradas, los 3 ex-`xfail` en verde, verificado en vivo | `tests/test_conversational_core.py` (30 tests) |
| **4 — Retirada del árbol MIXED_*** | ⬜ Sin empezar (solo tras medir Fase 1-3 en PRE) | — |

Suite: **1826 passed, 0 xfail**. El árbol legacy sigue 100% intacto como fallback; el
núcleo solo se activa con el flag.

> **⚠️ Empieza por la sección final "Sesión 2026-07-22 (noche)"** — Fix A y Fix B ya
> están hechos y CONFIRMADOS contra tráfico real de PRE (no solo local). Queda un
> hallazgo de proceso sobre `only_fields` y el eval-set, y las Fases 4/5/7 por delante.

## Cómo está montado (mapa rápido)

- **Flag**: `settings.conversational_core` (`src/config.py`, default `False`). En PRE está
  `CONVERSATIONAL_CORE: "true"` en `docker-compose.vps.yml` → el proceso real usa el núcleo.
  Revertir = quitar esa línea + redeploy (sin rollback de código).
- **Hook**: `supervisor._route_message_inner` — tras el gating de seguridad existente
  (PII / sensibles / cancelación / DIVE TO HEAL / edad), si el flag está on llama a
  `conversational_core.maybe_handle_turn(state, message)`. Devuelve `None` para keywords
  de escalado / menú / volver → esos siguen en los handlers legacy de abajo.
- **El bucle** (`conversational_core.py`, `maybe_handle_turn`): por turno →
  1. si es PREGUNTA de info (`_looks_like_question`) → RAG (`supervisor.rag_answer`) +
     retoma el slot pendiente en el mismo mensaje.
  2. COMPRENDER: `_apply_short_answer` (carryover contra `state.core_pending_slot`) +
     `_understand` (regex `intent_detector` + gap-fill `llm_extractor.fill_gaps`, con la
     distinción **añadir-vs-cambiar** actividad).
  3. RESOLVER: `next_missing_slot(state)` (lógica pura, orden del plan).
  4. RESPONDER: `ask_slot(state, slot, reasking=...)` (determinista ES/EN, quick-replies
     mínimos) o, si no falta nada, `_finalize(state)` (resumen + links del catálogo,
     gating colombiano) + `supervisor._maybe_build_pending_note`.
- **Slots** y su orden **actual** (ojo: la cantidad se movió delante de la seguridad el
  2026-07-22 por decisión del owner — ver sección final): `SLOT_ACTIVITY →
  SLOT_CERTIFICATION → SLOT_LOCATION → SLOT_HOTEL → SLOT_QTY → SLOT_SAFETY →
  SLOT_REFRESHER → SLOT_AGES → SLOT_NATIONALITY → (resumen)`.
- **Momentos deterministas** (nunca los toca el LLM): precios, links, resumen, pregunta
  de seguridad, confirmación, gating colombiano — reusan la maquinaria del árbol
  (`_cart_booking_blocks`, `_format_activity_booking_messages`, `_goto_mixed_final_summary`,
  `_resolve_service_booking_url`). El LLM solo interpreta/rellena slots y frasea.

## Decisión ya tomada (no re-litigar): structured outputs strict → DESCARTADO

El plan pedía "confirmar json_schema strict". Se hizo, se **midió**, y se **revirtió** con
datos: strict INDUCE misfills (ej. "quiero hacer buceo" sin lugar → `location='cartagena'`
inventada desde la sede del negocio; reproducido con gpt-4o-mini Y gpt-4o). El eval-set
ahora caza misfills (convención `expected: null` = "debe abstenerse"; casos `neg-*` en
`docs/robustness/eval-set.json`; `compare_with_ground_truth` actualizado). No-strict +
prompt reforzado da **143/145 = 98.6% con CERO misfills**. Hay un comentario junto a
`_TOOL` en `llm_extractor.py` avisando de esto. Detalle en `docs/robustness/progress-log.md`
(bloque 2026-07-22). **Si alguien reintenta strict, correr primero los casos `neg-*`.**

## Fase 3 — CERRADA (2026-07-22, Gonzalo)

Las 2 causas raíz de abajo quedaron arregladas en `conversational_core.py` (los 3
`xfail` pasaron a tests normales, todos en verde):

- **(A) resuelta** — inferencia singular en contexto de CURSO, **scoped al núcleo**
  (la opción 2 del propio handoff, elegida por menos invasiva: no toca el detector
  compartido con el árbol legacy). `_COURSE_SOLO_RE` ("voy solo"/"just me"/"by
  myself"…) + `_NOT_ALONE_RE` (guarda conservadora: cualquier señal de compañía/
  plural/número gana y se sigue preguntando) en `_understand`: si la actividad es
  `padi_*`, no hay cantidad, y hay señal singular limpia → `group_size=1`.
- **(B) resuelta a nivel del bucle** (no solo para SLOT_AGES, como pedía el
  handoff): en `maybe_handle_turn` el carryover del slot pendiente corre ANTES del
  check de pregunta — si hay slot pendiente, el mensaje no lleva `"?"` explícito y
  `_apply_short_answer` lo resuelve, NO va a RAG ("tienen 7 y 9 años" responde las
  edades). Un `"?"` explícito sigue siendo SIEMPRE pregunta real → RAG + retoma del
  slot (`test_question_mid_flow_answers_and_reasks_pending_slot` intacto).

Verificado en vivo con LLM real (flag on, local): Open Water isla + "voy solo" →
cierre con `open_water_already_on_island`; Divemaster solo → cierre contact-only
vía asesor sin link directo; familia con niños "tienen 7 y 9 años" → split del
checkout u8=1 (snorkel) / e10=1 (Bubble Makers).

Lo que queda del refactor es solo la **Fase 4** (retirada del árbol) — no empezar
hasta medir Fases 1-3 en PRE con tráfico real (ver abajo).

### Registro histórico — lo que faltaba cuando se escribió este handoff

Lo que **ya funciona** de Fase 3 (tests en verde):
- `test_padi_course_flow_no_cert_no_safety_questions`: un curso PADI con cantidad explícita
  ("somos 2") va actividad → ubicación → nacionalidad → resumen con el link del curso, SIN
  preguntar certificación ni seguridad (no aplican a cursos). ✅
- `test_lead_note_built_at_close`: la nota de lead se materializa al cierre
  (`_maybe_build_pending_note` en `maybe_handle_turn`). ✅
- Código ya escrito y desplegado (safe/aditivo): `_cart_item` resuelve la **variante isla**
  del curso (`open_water` → `open_water_already_on_island` vía `_service_for_location`);
  `_derive_kids_counts` traduce edades a `kids_under_8_count`/`kids_eight_to_ten_count`
  para el split del checkout; Divemaster ya es contact-only vía `_cart_booking_blocks`
  (sin link). Estas piezas están listas — solo no se alcanzan por las 2 causas de abajo.

Lo que **falta** — 2 causas raíz, cada una con su `xfail` en `test_conversational_core.py`:

### (A) "voy solo" no fija `group_size` en contexto de CURSO
- **Síntoma**: `test_padi_course_island_variant_resolved` y
  `test_divemaster_contact_only_no_direct_link`. Con "quiero el curso X, voy solo", el
  regex `intent_detector` NO infiere `group_size=1` (la inferencia singular solo dispara
  para buceo/cert, no para cursos), así que `next_missing_slot` devuelve `SLOT_QTY` y el
  flujo se queda pidiendo cantidad en vez de llegar al checkout.
- **Verificado**: `IntentDetector().detect('quiero el curso de divemaster, voy solo, desde
  cartagena')` → `activity=padi_divemaster, service_id=divemaster, group_size=None`.
- **Dónde arreglarlo (elegir uno, medir)**:
  1. Extender la inferencia singular de `intent_detector._detect_group_info` para que "solo
     yo"/"voy solo"/"just me" también fije `group_size=1` cuando la actividad es un curso
     PADI (hoy está gateada a contexto de buceo). **Ojo**: es código compartido con el
     árbol legacy — correr toda la suite, no romper `test_intent_detector.py`.
  2. O, más acotado al núcleo: en `conversational_core`, si la actividad es un curso y el
     mensaje trae señal singular clara ("solo"/"just me") y no hay grupo, tratar
     `group_size=1`. Menos invasivo, no toca el detector compartido.
- Nota: una vez fijado el qty, las variantes isla/divemaster ya deberían pasar (el código
  de `_cart_item` y `_cart_booking_blocks` ya las cubre) — por eso ambas comparten causa.

### (B) una respuesta que "parece pregunta" cae a RAG antes de resolver el slot pendiente
- **Síntoma**: `test_kids_ages_split_cart_blocks`. Con `SLOT_AGES` pendiente, la respuesta
  "tienen 7 y 9 años" la clasifica `_looks_like_question` como pregunta (la palabra
  "tienen") → va a RAG en vez de resolver las edades por carryover.
- **Causa exacta**: en `maybe_handle_turn`, el check de PREGUNTA corre ANTES de
  `_apply_short_answer`. Cuando hay un slot pendiente que el mensaje SÍ resuelve, el
  carryover debe ganar.
- **Fix propuesto**: antes del check de pregunta, si `state.core_pending_slot` está puesto,
  intentar `_apply_short_answer` primero; si resuelve el slot (y el mensaje no es
  claramente una pregunta con "?"), NO ir a RAG. Alternativa: para `SLOT_AGES`, aceptar
  cualquier mensaje con dígitos de edad como respuesta aunque `_looks_like_question` diga
  que sí. Cuidado de no romper `test_question_mid_flow_answers_and_reasks_pending_slot`
  (una pregunta real mid-flujo SÍ debe ir a RAG y retomar el slot).
- **Impacto más amplio**: esto no es solo edades — cualquier slot cuya respuesta natural
  contenga una palabra-pregunta ("cuántos", "tienen"…) tiene el mismo riesgo. Vale la pena
  arreglarlo a nivel del bucle, no solo para `SLOT_AGES`.

## Fase 4 — retirada del árbol (NO empezar aún)

Solo cuando el núcleo cubra todos los verticales Y se haya medido en PRE con tráfico real
(coordinar con la Fase 6 de robustez — el harvest de logs). Retirar los ~24 pasos `MIXED_*`,
`set_quick_replies`/`_CART_MENU_KEYS`, `BACK_STEP`/`_go_back_one_step`, `classify_menu_intent`.
Es reversible con el flag hasta entonces.

## Cómo probar / verificar

- **Offline** (sin API key): `python -m pytest tests/test_conversational_core.py -q`. El
  gap-filler está mockeado (`_core_on` fixture) y RAG usa el stub del conftest.
- **En vivo con LLM real** (local): `ENV_FILE=.env.dev python -c "..."` poniendo
  `settings.conversational_core = True` antes de importar el supervisor; ver los guiones
  Sofía/Rocío del plan (§Verificación end-to-end).
- **En PRE** (flag ya on): SSH + `docker exec dp-pre-bot python3 /tmp/script.py` con el
  patrón de `scripts/live_battery_driver.py`. Guiones ya verdes en vivo: Sofía (3 turnos
  → link) y Rocío completa (6 turnos, snorkel post-cierre → carrito cert+snorkel).
- **Eval del extractor**: `ENV_FILE=.env.dev python -m scripts.run_extraction_eval`
  (73 casos, ~2-3 min, necesita API key). Umbral ≥98%.

## Reglas del proyecto (recordatorio)

TDD estricto (rojo→verde), suite completa + `ruff check src` antes de cada deploy, nada se
retira hasta que el núcleo lo cubre y se mide en PRE. Los `xfail` de Fase 3 deben pasar a
`@pytest.mark.asyncio` normal (quitar el `xfail`) cuando se cierren las 2 causas.

---

# Sesión 2026-07-22 (tarde) — validación en PRE, 3 ajustes, y 2 arreglos PENDIENTES

> **Gonzalo: esta es la parte viva del handoff.** Todo lo de arriba está hecho y
> desplegado. Aquí está lo que pasó después del merge de tu rama, y lo que queda.

## 1. Qué se hizo (todo commiteado y desplegado en PRE)

- **Merge de tu rama** (`4c69889`) a `feature/pre_gadea`, fast-forward limpio. Suite
  verde tras el merge (1820). Tus 3 commits entraron tal cual: el fix de historial
  (regresión que había introducido el refactor de fallbacks de Gadea), el cierre de
  la Fase 3, y la persona de Coral.
- **Incidente de despliegue**: el primer deploy falló con `429 insufficient_quota`
  (cuenta de OpenAI sin saldo) en el paso de reindexar la KB. **El código sí quedó
  desplegado** (el `docker compose up --build` corre antes del reindex); solo faltó el
  reindex, que era irrelevante porque ningún commit tocaba la KB. El owner recargó y
  se relanzó el job → verde. **Lección**: si vuelve a pasar, comprobar primero si el
  contenedor ya tiene el código nuevo antes de asumir que no se desplegó.
- **El owner validó los 5 casos en PRE por el widget** — todos correctos: curso PADI
  solo (deduce 1), curso en isla (variante `_already_on_island`, $596 vs $693),
  Divemaster (contact-only, sin link), familia con niños (7→snorkel, 9→Bubble Makers,
  4 personas sin perder a nadie) y mensaje vago (saludo de Coral + menú).
- **3 ajustes decididos por el owner** a partir de esa validación (`fbc13ed`,
  v0.20.46, ya en PRE):
  1. **"voy solo" deduce 1 persona en CUALQUIER actividad**, no solo `padi_*` — se
     quitó el gate de tu `_COURSE_SOLO_RE`. Sigue exigiendo señal explícita +
     `_NOT_ALONE_RE`: "tengo el open water" a secas NO basta (un jefe de grupo escribe
     igual) → ahí se pregunta.
  2. **La cantidad se pregunta ANTES que la seguridad** en `next_missing_slot`. Antes
     la pregunta de los 2 años adivinaba singular/plural sin saber el tamaño del grupo.
     **Ojo**: esto se desvía del orden escrito en `conversational-refactor-plan.md` —
     decisión explícita del owner, anotada también en el propio plan.
  3. **La nacionalidad se adapta a singular/plural** (salía siempre "¿sois
     colombianos?" a quien viajaba solo).

## 2. ✅ RESUELTO (2026-07-22, Gonzalo): Fix A y Fix B implementados — Fase 6 desbloqueada

Los dos fixes de abajo quedaron implementados con TDD (+7 tests: 4 en
`test_conversational_core.py`, 2 en `test_llm_extractor.py`, y el test de
integración que pasa las líneas de log del núcleo por el harvester real):

- **Fix A hecho**: `_understand` ahora loguea `[EXTRACT][CUTOVER] applied={patch}
  msg=...` (valores incluidos, mensaje completo vía `supervisor._log_safe_message`)
  en lugar del viejo `[CORE] gap-fill applied=[nombres]`. El harvester funciona sin
  tocarlo — el test de integración lo verifica parseando los logs reales del bucle.
- **Fix B hecho, a nivel de diseño**: `_relevant_gaps(state, intent, message)`
  calcula los huecos contra el ESTADO (no solo el intent del turno) y descarta
  campos fuera de contexto: island/hotel saliendo de Cartagena, ages sin menores
  mencionados, last_dive sin cert en la reserva, y group_allocation con la
  cantidad ya sabida y sin señal de persona añadida (`_ADDED_PERSON_RE`, que es
  cuando añadir-vs-cambiar lo consume). Sin huecos relevantes → NO se llama al
  LLM. Además `fill_gaps` ganó `only_fields` (kwarg opcional, backwards-compatible:
  el cutover legacy no cambia) para que el prompt solo pida esos campos.
  `duration`/`cert_dives`/`cert_days` quedan fuera del gap-fill del núcleo a
  propósito (afinadores espontáneos que el regex ya captura; no bloquean slots).
- **Verificado en vivo con LLM real** (local, flag on): conversación de 4 turnos
  con frases fuera del regex ("nos apetece explorar el fondo del mar", "barrio de
  bocagrande", "nos sumergimos el mes pasado", "venimos de madrid") → reserva
  cerrada (cert×2, $356) y el harvester sobre esos logs: **4 records, 4 candidatos
  con valores** (`bocagrande→location=cartagena`, `mes pasado→last_dive=False`,
  `madrid→is_colombian=False`…) y `--summary` clasificando por dominio. Antes: 0.

Queda el paso operativo de la Fase 6: correr el harvest contra los logs REALES de
`dp-pre-bot` tras acumular tráfico, curar candidatos (validando cada `expected`
contra el pipeline real) y alimentar el eval-set.

### Registro histórico — el hallazgo tal como se documentó

## 2. 🔴 HALLAZGO: la Fase 6 de robustez está BLOQUEADA por el núcleo

Se corrió el harvest sobre los logs reales de PRE (11 conversaciones del owner):
**0 candidatos**. No es falta de tráfico — hay 21 turnos con extracción real.

**Causa raíz**: `scripts/harvest_cutover_logs.py` parsea
`[EXTRACT][CUTOVER] applied={campo: valor} msg='...'`, que emite
`supervisor._maybe_apply_llm_extraction_cutover`. **Con el núcleo encendido ese código
nunca se ejecuta**: el núcleo intercepta antes y hace su propia extracción en
`conversational_core._understand`, que loguea otro formato:

```
[CORE] gap-fill applied=['activity', 'group_size']        <- solo nombres, sin valores ni mensaje
[LLM_EXTRACTOR] filled gaps=[...] msg='...'               <- nombres + mensaje, pero sin valores
```

Sin los **valores** no se puede construir un caso de eval-set, así que la Fase 6 (y con
ella la Fase 5 de limpieza, que depende de ella) sigue parada.

### Fix A — que el núcleo loguee en el formato que el harvest ya entiende

**Dónde**: `src/agents/conversational_core.py`, en `_understand`, la línea
`logger.info(f"[CORE] gap-fill applied={list(patch.keys())}")`.

**Qué**: emitir además (o en su lugar) el mismo tag y formato que el cutover:
`[EXTRACT][CUTOVER] applied={patch} msg={supervisor._log_safe_message(message)!r}`.
Es semánticamente correcto — el núcleo *está* aplicando valores del LLM al estado,
igual que el cutover. Reutilizando el tag, **el harvest funciona sin tocarlo** y el
contador por dominio (`--summary`) también.

**Cuidado**: `_log_safe_message` (en `supervisor.py`) corta a 500 chars con marca
explícita; usarlo, no `message[:60]` — ese truncado ya causó un bug documentado.

**Verificación**: tras desplegarlo, generar tráfico por el widget y correr
`ssh ... "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs --summary`.
Debe devolver registros > 0. Luego sin `--summary` para sacar candidatos, y **validar
cada `expected` contra el pipeline real antes de fijarlo** en el eval-set (regla del
plan: medir, no asumir).

### Fix B — no pedirle al LLM campos que ya sabemos (ahorra tokens y reduce misfills)

**Dónde**: `src/agents/conversational_core.py`, en `_understand`:
`gaps = missing_fields(intent)`.

**Problema**: `missing_fields()` se calcula contra el **intent del mensaje suelto** (lo
que el regex sacó de ESE mensaje), que casi siempre está casi vacío. Resultado: en cada
turno se le piden al LLM ~13 campos, incluidos los que **el estado ya tiene**. Ejemplo
real de los logs de PRE: el mensaje `"Cartagena"` disparó una llamada que rellenó
`activity`, `is_certified` y `group_size` — los tres ya conocidos.

**Impacto**: tokens desperdiciados en cada turno (relevante: la cuenta se quedó sin
cuota este mismo día) y superficie de misfill innecesaria.

**Qué hacer**: calcular los huecos contra el **estado** (lo que de verdad falta por
saber), no solo contra el intent del mensaje. Si no falta nada relevante, no llamar al
LLM. Cuidado de no romper el carryover ni la distinción añadir-vs-cambiar actividad.

**Nota**: se investigó y **descartó** una sospecha relacionada — parecía que el
extractor inventaba la respuesta de seguridad (`last_dive_over_2_years`) desde un
mensaje sobre acompañantes. Probado en controlado con la seguridad SIN responder en el
historial: **se abstiene correctamente**. Lo que se veía era re-derivación legítima
desde el historial, y los guards de `_apply_detected_intent` impiden sobrescribir. **No
es un bug** — pero es otro síntoma de que se está preguntando de más (Fix B).

## 3. Próximos pasos, en orden

1. ✅ **Fix A** — hecho (2026-07-22, Gonzalo; ver §2 arriba).
2. ✅ **Fix B** — hecho (2026-07-22, Gonzalo; ver §2 arriba).
3. **Correr el harvest de verdad** → curar candidatos → eval-set con casos reales →
   **cierra la Fase 6** y **desbloquea la Fase 5** de robustez (limpieza de regex muerto).
   El tooling está verificado end-to-end en local; falta tráfico real en PRE +
   `ssh ... "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs`.
4. **Fase 4 del refactor conversacional** — retirar los ~24 pasos `MIXED_*`,
   `set_quick_replies`/`_CART_MENU_KEYS`, `BACK_STEP`/`_go_back_one_step` y
   `classify_menu_intent`. **Precondición del plan**: medir antes en PRE con tráfico
   real (los puntos 1-3 son justo esa medición). Es el trabajo más grande y delicado;
   el flag lo mantiene reversible hasta que se retire el árbol.

## 4. Estado operativo

- `feature/pre_gadea` = `fbc13ed`, subido, **CI verde y desplegado en PRE**.
- `CONVERSATIONAL_CORE: "true"` en PRE (`docker-compose.vps.yml`). Revertir = quitar la
  línea + redeploy, sin rollback de código.
- Suite **1826 passed, 15 skipped, 0 xfail**. `ruff check src` y `compileall` limpios.
- Sin trabajo a medias en el árbol: todo lo de esta sesión está commiteado.

---

# Sesión 2026-07-22 (noche) — Fase 6 confirmada en PRE real + 1 hallazgo de proceso

> Continúa directamente de "Sesión 2026-07-22 (tarde)" arriba (Fix A/Fix B de Gonzalo,
> ya mergeados en `feature/pre_gadea`). Esta sección es la verificación contra
> **tráfico real** de PRE, no local.

## 1. Fix A confirmado en producción

Se tiró de `docker logs dp-pre-bot` (tráfico real del widget, tras el redeploy con los
Fix A/B) y se corrió el harvest: **2 records, 2 candidatos con valores** — antes de Fix
A esto daba 0 (ver sesión de la tarde). El fix funciona en producción, no solo en la
verificación local que hizo Gonzalo.

Nota: el container se reinició en el redeploy, así que el log solo tenía tráfico desde
entonces (160 líneas) — para una cosecha más grande hace falta esperar a que se
acumule más tráfico real y repetir el comando.

## 2. Un candidato añadido al eval-set, otro descartado — y por qué

- **`hv-aowd-acronym`** (83→84 casos): "hola soy rocio, quiero hacer buceo, tengo el
  AOWD" → el regex deja `is_certified=None` (AOWD = Advanced Open Water Diver, un
  acrónimo que no reconoce); `fill_gaps` sin historial da `is_certified=True` de forma
  estable. Validado y fijado.
- **Descartado**: "1 pero viene un amigo que quiere hacer buceo, no es certificado" →
  en PRE se logueó `group_allocation={certified_diving:1, minicourse:1}`, pero al
  reproducirlo con la llamada plana del eval-set (`fill_gaps(mensaje, intent)`, sin
  `only_fields`) el resultado fue DISTINTO: `group_size=2`. **No es un bug** — es que
  el candidato vino de una llamada con `only_fields` restringido por el Fix B de
  Gonzalo (que usa el ESTADO de la conversación para acotar qué campos pedir, no solo
  el mensaje suelto), y el eval-set/runner actual no simula ese contexto reducido.

### 🟡 Hallazgo de proceso — el eval-set no conoce `only_fields`

El Fix B (`_relevant_gaps` en `conversational_core.py`) hace que en producción el
patch logueado dependa del ESTADO de la conversación, no solo del mensaje. Un
candidato harvestado así **no siempre es reproducible** como caso de mensaje-suelto en
el eval-set actual. Antes de fijar más candidatos de este tipo, hay dos opciones (sin
decidir todavía):
  (a) extender el runner del eval-set para poder simular un `only_fields`/estado previo
      dado, o
  (b) tratar esos casos como tests de integración del núcleo completo (con estado
      previo), no como extracción de mensaje suelto.

Detalle completo en `docs/robustness/progress-log.md` (bloque 2026-07-22, harvest
confirmado + hallazgo `only_fields`).

## 3. Próximos pasos (sin cambios de fondo respecto a la sesión de la tarde)

1. Seguir acumulando tráfico real por el widget y repitiendo el harvest periódicamente
   — el tooling ya funciona de punta a punta contra PRE real.
2. Decidir (a) vs (b) del hallazgo de arriba antes de que se acumulen más candidatos
   `only_fields`-dependientes.
3. **Fase 7** (override selectivo por campo) — ya justificada con 3 bugs reales de
   regex (ver sesión de la tarde: `ages` capturando años como edad, curso mal
   clasificado para quien ya está certificado, "me plus 3 friends" → 3).
4. **Fase 5** (limpieza de regex muerto) — detrás de la 6 y la 7.
5. **Fase 4** del refactor conversacional (retirar el árbol `MIXED_*`) — el único punto
   pendiente del plan de Álvaro; su precondición (medir en PRE) ya se está cumpliendo.

## 4. Estado operativo

- `feature/pre_gadea` en `7211f7d` (merge de `feature/pruebaGon`) + este bloque de
  sesión, subido y desplegado en PRE.
- Suite y eval-set: ver el commit de esta sesión para el conteo exacto tras añadir
  `hv-aowd-acronym`.

---

# Sesión 2026-07-22 (tarde-noche) — Red de precisión LLM: recordar + acompañante añadido

> El owner reportó capturas reales de PRE con 3 fallos y dio una instrucción explícita:
> **no seguir ampliando el regex frase a frase** para "acompañante añadido" — resolverlo
> globalmente con el LLM, con precisión (nunca inventar un valor).

## Los 3 fallos originales (capturas reales de PRE)

1. "¿cuántas personas somos, me lo recuerdas?" → el bot decía "eso no lo tengo a la
   mano" y ofrecía un asesor, para un dato que YA tenía en el estado.
2. "mi acompañante quiere hacer buceo pero no es certificado" → repetía el resumen de
   buceo certificado con un "Refresher añadido" fuera de lugar, en vez de añadir un
   minicurso para el acompañante.
3. "hay un amigo que quiere hacer snorkel" / "viene un acompañante" → no añadían nada;
   caían al mismo mensaje genérico de asesor.

## Causa raíz

El mecanismo de "añadir acompañante" vivía en un regex (`_ADDED_PERSON_RE`) que solo
reconoce posesivo exacto ("mi amigo", "mi novia"...) y exige que la actividad detectada
sea DISTINTA de la principal. "hay un amigo" no tiene posesivo; "quiere hacer buceo
pero no es certificado" detecta la MISMA actividad (`certified_diving`) que la
principal, así que el patrón nunca disparaba. Un bug de fondo más serio: cuando SÍ
detectaba una actividad distinta (p. ej. "hay un amigo que quiere hacer snorkel"),
como no coincidía con `_ADDED_PERSON_RE`, `_apply_detected_intent` (latest-wins)
**sobreescribía la actividad principal completa** con la del acompañante.

## Solución (decidida con el owner vía AskUserQuestion, ambas opciones recomendadas)

- **Detección de acompañante**: nueva herramienta LLM dedicada
  (`detect_special_signals`, `llm_extractor.py`) — separada del gap-filler de slots
  persistentes porque esto es un EVENTO de turno, no un campo de `DetectedIntent`.
  Devuelve `companion_activity`/`companion_qty` cuando el mensaje introduce a alguien
  ADICIONAL (aplicando ya la regla de negocio: no certificado + quiere bucear →
  minicurso). Solo se invoca como red de última instancia cuando el turno no avanzó por
  los caminos normales (`next_missing_slot` no cambió) — nunca en cada turno.
- **Recordar un dato**: el mismo tool devuelve `recall_field` (qué campo se pide) SOLO
  cuando el mensaje es una pregunta explícita ("?"). El VALOR de la respuesta viene
  SIEMPRE del estado (`_recall_answer`), nunca del LLM — si el estado no tiene ese dato
  resuelto de verdad, se abstiene (`None`) y el turno cae a RAG normal, nunca inventa.
- **Bug de fondo corregido**: `_restore_main_diver_fields` — cuando se confirma que un
  turno hablaba de un acompañante (por regex o por la señal LLM), se restauran
  `activity`/`service_id`/`is_certified`/`last_dive_over_2_years`/`refresher_interested`
  del buceador PRINCIPAL a como estaban antes de este turno, luego se aplica SOLO el
  añadido. Aplicado en ambos caminos (el regex `_ADDED_PERSON_RE` ya existente y el
  nuevo camino LLM) para no dejar el mismo bug en uno de los dos.
- El "gate" de cuándo llamar a la señal es `next_missing_slot(state) != prev_pending`
  (no un snapshot crudo de campos) — precisamente porque un campo corrompido por error
  en este mismo turno no debe contar como "avance real".

## Verificado en vivo con LLM real (los 3 mensajes EXACTOS de las capturas)

- Recall: "cuantas personas somos me lo recuerda?" → "Me dijiste que sois *3* personas."
- Acompañante no certificado: `detected_group_allocation = {'certified_diving': 1,
  'minicourse': 1}`, `is_certified` del principal se mantiene `True` (no se corrompe).
- Amigo snorkel: carrito final `[('cert', 1), ('snorkel', 1)]`.

12 tests nuevos (6 `test_llm_extractor.py`, 6 `test_conversational_core.py`). Suite:
**1867 passed**, 15 skipped. Ruff limpio en los archivos tocados.

## Qué queda

Nada bloqueante de esta pieza. Si el equipo encuentra más "eventos de turno" similares
(no campos persistentes, sino cosas que pasan en un mensaje suelto), el patrón a seguir
es el mismo: extender `_SIGNALS_TOOL`/`detect_special_signals`, nunca añadir un regex
nuevo por frase. Sigue pendiente, sin cambios respecto a antes: Fase 5 (limpieza) y
Fase 4 (retirar el árbol `MIXED_*`).
