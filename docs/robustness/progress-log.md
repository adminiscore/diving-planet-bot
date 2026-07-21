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
