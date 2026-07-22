# Robustez conversacional — extracción semántica por LLM

Índice de esta carpeta. Empieza aquí siempre, en cualquier sesión.

## Qué es esto

Plan de implementación de la **Opción 2** de `docs/robustness-strategy-options.md`
(decidida por el owner + Álvaro + Gonzalo el 2026-07-21): sustituir progresivamente la
extracción de información del mensaje (certificación, grupo, ubicación, cambios de
plan…) — hoy repartida en decenas de regex especializadas en `intent_detector.py`/
`supervisor.py`/`decision_tree.py` — por una capa de comprensión semántica vía LLM,
para dejar de perseguir bug a bug cada nueva forma de decir lo mismo.

**Objetivo del owner, textual**: "ser competitivos y sólidos, el cliente no puede
encontrar tantos bugs".

## Archivos

- **`plan.md`** — el plan completo: principios de diseño, arquitectura, fases,
  criterios de corte/rollback, formato del eval-set. Léelo entero antes de tocar código.
- **`progress-log.md`** — registro de progreso, **append-only**, un bloque nuevo por
  sesión. Antes de escribir código, léelo para saber exactamente dónde se quedó la
  sesión anterior. Al terminar tu sesión (o al quedarte sin tokens), añade tu bloque
  ANTES de parar — es lo único que le permite a la siguiente sesión continuar sin
  releer todo el trabajo previo.

## Cómo retomar este trabajo en una sesión nueva

1. Lee este README (ya lo estás haciendo).
2. Lee `progress-log.md` completo — especialmente el ÚLTIMO bloque, que dice
   exactamente qué se hizo, qué quedó a medias, y cuál es el siguiente paso concreto.
3. Lee en `plan.md` la sección de la fase en la que se quedó (el progress-log te dice
   cuál).
4. Sigue el flujo de trabajo ya establecido en todo el repo (ver
   `docs/project-history/session-handoff.md` y el propio historial de commits): TDD
   estricto (rojo → verde), suite completa antes de cada deploy, `/closework` antes de
   pushear, verificación en vivo contra PRE con `scripts/live_battery_driver.py` vía
   SSH para cualquier cambio de comportamiento observable.
5. Antes de quedarte sin tokens o de cerrar la sesión, **añade tu bloque a
   `progress-log.md`** (no lo edites, no lo resumas, solo añade) con: qué hiciste, qué
   decidiste y por qué, qué queda pendiente, y el siguiente paso concreto para quien
   continúe. Esto es lo más importante de todo — sin esto, el plan se vuelve inútil
   para la siguiente sesión.
6. Actualiza el checklist de fases en `plan.md` (marcar ✅/🔄/⬜) si el estado de una
   fase cambió.

## Estado actual

Ver el checklist en `plan.md` § "Fases" y el último bloque de `progress-log.md` para
el estado exacto. A fecha de creación de este documento (2026-07-21): **plan recién
escrito, Fase 0 no empezada.**
