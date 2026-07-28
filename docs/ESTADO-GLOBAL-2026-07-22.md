# Estado global del proyecto — 2026-07-22 (actualizado 2026-07-28)

> Mapa único de dónde está todo y qué queda, tras la sesión de Gonzalo del 22-07.
> Para el detalle por fase ver `docs/robustness/` (plan/progress-log/review) y
> `docs/conversational-refactor-*`. Este documento es el resumen ejecutable.

## ⛔ ACTUALIZACIÓN 2026-07-28 — Fase 4 EN EJECUCIÓN en `feature/fase4-p2` (NO mergear)

**Ahora mismo NO se mergea nada.** La rama **`feature/fase4-p2` es WIP** — el corte
grande (borrar el árbol legacy `MIXED_*` + los ~6.000 líneas de handlers muertos de
`decision_tree.py`) está **a medias**. Mergearla ahora dejaría PRE con el árbol muerto
pero el código de menú/back a medio quitar → **inconsistente**. (Nota de Gadea, foto del
28-07; transcrita aquí para que no se pierda.)

**Gonzalo trabaja EN `feature/fase4-p2`** (no crea rama nueva):
1. `git checkout feature/fase4-p2 && git pull`
2. **Sincroniza primero**: `git merge origin/feature/pre_gadea` (por si Gonzalo o Álvaro
   habéis pusheado fixes — así arrancó Gadea la sesión, sin conflictos).
3. Sigue la lista **"PENDIENTE (el corte MAYOR)"** de `docs/legacy-tree-retirement-plan.md`
   (esa lista vive en `feature/fase4-p2`).

**El merge de verdad** (`feature/fase4-p2` → `feature/pre_gadea`) se hace **solo cuando la
Fase 4 esté completa y verde**: suite flag-on + smoke del render (`test_cart_render`) +
prueba en vivo del guion completo en PRE. Y **revisado por los tres** (Gonzalo/Gadea/Álvaro).

**Avisos clave** (también en `legacy-tree-retirement-plan.md` §4 y en el handoff):
- **PROTEGER** en `decision_tree.py`: la base compartida (`SERVICES` / `ConversationState`
  / `Step` / `MESSAGES` / `MESSAGE_SPLIT`) **+ los 9 símbolos que usa `cart_render`**
  (`_service_for_location`, `_cart_label_for`, `_cart_service_id`, `_parse_mixed_quantity`,
  `_cart_booking_blocks`, `_format_activity_booking_messages`, `_goto_mixed_final_summary`,
  `_is_contact_only_service`, `_resolve_service_booking_url`) — son los que renderizan cada
  reserva de PRE. Su cierre transitivo NO toca ningún `_handle_mixed_*` (verificado por AST).
- **Red de seguridad**: correr la suite en core-on tras **cada** borrado + smoke del render.
- **NO usar `ruff --fix` para imports**: quita los que solo se parchean en tests
  (`detect_language_llm`) — rompió 144 tests. Limpiar los imports huérfanos **a mano**.

**Antes de tocar Fase 4, LEE**: `docs/project-history/session-handoff.md`,
`docs/conversational-refactor-handoff.md` y `docs/legacy-tree-retirement-plan.md`
(los tres están en `feature/fase4-p2`, con el estado de ejecución al día).

> Estado de `feature/fase4-p2` al 28-07 (del propio plan): P1 (seam `cart_render.py`) +
> P4 (core-only, flag a `True` por defecto, ~2.400 líneas de supervisor borradas) HECHO y
> verde (suite 1444, idéntica flag-off/on). Hallazgo: el árbol legacy ENTERO está muerto con
> el núcleo on (no solo `MIXED_*`), ~6.000 líneas de `decision_tree.py` deletables. Falta el
> corte mayor (P2/P3): borrar `process_message` + los 70 handlers `_handle_*` + quitar el flag.
> **Todo committeado en la rama, sincronizable — no mergear hasta completar y revisar entre los tres.**

## Dos líneas de trabajo en paralelo (encajan entre sí)

1. **Robustez — extracción semántica por LLM** (`docs/robustness/plan.md`): red de
   seguridad que rellena, con el LLM, los campos que el regex deja vacíos. Nunca
   sobreescribe el regex; kill switch por dominio; medida contra un eval-set.
2. **Refactor conversacional — slot-filling** (`docs/conversational-refactor-plan.md`):
   sustituir los menús de botones (`MIXED_*`) por un bucle conversacional
   (comprender→resolver→responder). Usa el extractor de la línea 1 como motor.

Encajan: el "punto único de comprensión" del refactor ES el extractor de robustez.

## Estado por fase

### Robustez
| Fase | Estado | Nota |
|---|---|---|
| 0 — Fundaciones | ✅ | eval-set + `fill_gaps` + shadow harness |
| 1 — Certificación | ✅ flag ON en PRE | `is_certified`/`activity` |
| 2 — Grupo/edades | ✅ flag ON en PRE | `group_size`/`group_allocation`/`ages` |
| 3 — Ubicación | ✅ flag ON en PRE | `location`/`island`/`hotel` |
| 4 — Arquitectura | ✅ | decisión: extractor y orquestador SEPARADOS; extractor en `gpt-4o-mini` (barato/rápido, fallo seguro) |
| 8 — Nacionalidad/logística | ✅ flag ON en PRE | `is_colombian`/`duration`/`last_dive_over_2_years` |
| 6 — Bucle de datos reales | ✅ operativa | harvest confirmado con tráfico REAL de PRE (Gadea); tooling `scripts/harvest_cutover_logs.py` |
| 7 — Bugs "regex resuelve mal" | ✅ | 3 arreglados (me+N, hace-X-años→edad, already-have-card→curso) |
| 5 — Limpieza (retirar regex muerto) | ⬜ | requiere varios lotes reales de la Fase 6 primero |

**Eval-set**: 84 casos, último eval **167/168 = 99.4%, 0 disagree** (el único miss es una
abstención segura del mini). Los 4 flags de cutover + el core están ON solo en PRE
(default `False` en el resto).

### Refactor conversacional (flag `CONVERSATIONAL_CORE`, ON solo en PRE)
| Fase | Estado |
|---|---|
| 0 — Andamiaje | ✅ |
| 1 — Buceo certificado | ✅ validado en vivo en PRE por el owner |
| 2 — Snorkel/minicurso/acompañante | ✅ |
| 3 — Cursos PADI + checkout | ✅ (2 causas raíz cerradas, ex-`xfail` en verde) |
| Persona de Coral | ✅ saludo cálido colombiano en el 1er turno, sin "asistente/bot" |
| Fix A/B del handoff | ✅ harvest desbloqueado + gap-fill contra el estado |
| 4 — Retirada del árbol `MIXED_*` | 🔨 **EN EJECUCIÓN en `feature/fase4-p2` (NO mergear, WIP)** — P1+P4 hechos y verdes; falta el corte mayor (P2/P3). Ver la sección "⛔ ACTUALIZACIÓN 2026-07-28" arriba + `docs/legacy-tree-retirement-plan.md` |

## Qué queda pendiente (ordenado por lo que desbloquea)

1. **Fase 6 — canal real, en continuo** (parcial): seguir generando tráfico por el
   **widget de Chatwoot en PRE** y correr el harvest periódicamente
   (`ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker logs dp-pre-bot 2>&1" | python -m
   scripts.harvest_cutover_logs`). El tooling está confirmado en producción; es curación
   continua, no una tarea puntual. **Necesita la clave SSH del VPS** (a Gonzalo/Gadea el
   entorno local de Claude le deniega ese SSH por política de servidor compartido).

2. **Hallazgo abierto — `only_fields` vs eval-set** (decisión de proceso): los candidatos
   harvestados con el Fix B activo dependen del contexto de conversación, y el eval-set
   los evalúa con la llamada "pelada". Antes de fijar más candidatos de ese tipo, decidir:
   (a) extender el runner para simular `only_fields` desde un estado, o (b) tratarlos como
   tests de integración del núcleo, no de extracción de mensaje suelto. Detalle en
   `docs/robustness/progress-log.md` (bloque "Fase 6 confirmada en producción").

3. **Fase 5 robustez — limpieza**: retirar el regex que el LLM haya reemplazado de facto,
   una vez la Fase 6 lleve un par de lotes reales sin sorpresas. Bloqueada por (1).

4. **Fase 4 refactor — retirar el árbol `MIXED_*`** → **YA EN EJECUCIÓN en
   `feature/fase4-p2`** (arrancada 24-07, en curso 28-07 por Gadea). P1 (seam
   `cart_render.py`) + P4 (core-only, flag a `True` por defecto, ~2.400 líneas de
   supervisor borradas) HECHO y verde. Falta el corte mayor (P2/P3): borrar
   `process_message` + los ~70 handlers `_handle_*` legacy (~6.000 líneas) + quitar el
   flag. **Reglas y avisos: ver la sección "⛔ ACTUALIZACIÓN 2026-07-28" al principio de
   este documento** y `docs/legacy-tree-retirement-plan.md` (en `feature/fase4-p2`). **NO
   mergear `feature/fase4-p2` hasta completar + verde + revisión de los tres.**

## Salud del repo (checks de esta sesión)
- Rama de trabajo: `feature/pruebaGon`, sincronizada con `origin`.
- Mergeado el trabajo de Gadea (Fase 6 en producción + `hv-aowd-acronym`); sin
  divergencia pendiente.
- `ruff check src` limpio, `compileall` limpio.
- Suite completa en verde (ver el último bloque del progress-log para el número exacto).
- Flags en `docker-compose.vps.yml` (solo PRE): 4 cutover de robustez + `CONVERSATIONAL_CORE`
  + `RAG_MIN_SCORE=0.40`. Todos revertibles quitando la línea + redeploy, sin rollback de código.

## Recordatorios operativos
- **PRE es compartida** (Gonzalo/Gadea/Álvaro): un deploy sobreescribe lo desplegado —
  avisar al equipo. Los mirrors `feature/pre_pruebaGon` y `feature/pre_gadea` disparan
  ambos el `deploy-pre`.
- **Nada se retira** (Fase 5 robustez / Fase 4 refactor) hasta medir en PRE — el árbol
  legacy y el regex siguen siendo el fallback mientras los flags puedan apagarse.
