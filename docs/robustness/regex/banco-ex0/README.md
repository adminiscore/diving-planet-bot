# Banco ex-0 (fase EX): extracción con vocabulario real

Hecho el 12-oct-2026 (Gadea con Claude). Es la vara de medir de toda la fase EX (`../plan-ex-entender-con-ia.md`).

## Qué hay

- `candidatos.json`: los 368 turnos de cliente de la ronda visible con Luna (`2026-10-08-luna-visible`, 95 diálogos,
  **nunca el examen oculto**), cada uno con los 4 mensajes anteriores (`history`) y su grupo: **diseño** o **ciego**
  (`sha1(diálogo) % 2`, fijado antes de medir; un diálogo entero va a un solo grupo).
- `etiquetas.json`: por turno, la pregunta que el bot acababa de hacer (`slot`) y **solo lo que el cliente AFIRMA en
  ese mensaje** (`expected`), interpretado con esa pregunta. 26 `DUDOSO` (posventa sobre reservas ya hechas, el
  acompañante que no es actividad, la "extranjería") no cuentan. Quedan **342** (diseño 200, ciego 142): 136 con
  algún dato y **206 sin ninguno** (sirven para medir inventos).
- `etiquetar.py`: cómo se guardaron las etiquetas por tandas.
- `resultado-<modo>-<grupo>.json`: cada medida, con el detalle por caso.

Criterios de etiqueta: "quiero bucear" a secas no es una actividad (recomendar, no suponer); lo dicho de OTRA persona
no cambia los datos de quien escribe; una hipótesis ("in case I decided to…") no es un dato; viajar "a Cartagena" no
dice desde dónde sale; "sacarme la certificación" = Open Water. Campos: `activity`, `is_certified`, `group_size`,
`group_allocation`, `location`, `is_colombian`, `last_dive_over_2_years`.

## Cómo se mide

    python -m scripts.run_extraction_eval --banco ex0 --modo regex  --grupo todos    # sin LLM (ENV_FILE=.env.ci)
    python -m scripts.run_extraction_eval --banco ex0 --modo actual --grupo todos    # turno de producción (ENV_FILE=.env.dev)

- Cada caso arranca con lo que el cliente ya había dicho antes en su diálogo (`sabido`, de las etiquetas anteriores).
- **acierto / equivocado / perdido** para lo que el cliente dijo; **inventado** = un valor que el cliente no dijo (ni
  se sabía antes). No cuenta como invento lo coherente: la actividad "principal" de un grupo mixto, el reparto de una
  sola actividad, "no certificado" con minicurso u Open Water.
- `actual` reproduce la parte del turno que ENTIENDE: señales del router (Jev en cascada,
  `conversational_core.sembrar_senales_del_turno`, la misma función que producción), lector de respuestas cortas y
  `_understand` (regex + redes LLM).

## Línea base (12-oct, todos los casos)

| | Regex solo | Producción (regex + Jev + redes LLM) |
|---|---|---|
| Datos acertados | 154/204 (75,5 %) | **166/204 (81,4 %)** |
| Equivocados / perdidos | 17 / 33 | 15 / 23 |
| Casos con algún invento | 54/342 (15,8 %) | **78/342 (22,8 %)** |

- Las redes LLM recuperan datos (+6 puntos) pero **se inventan más**: 31 casos con inventos que el regex solo no
  tenía, sacados del HISTORIAL y no del mensaje ("gracias" → buceo certificado; "Muchas gracias!" → colombiano;
  "Para el sábado, 30/05" → sale de Cartagena; "Just completed the waivers" → 2 personas en las islas).
- El regex se inventa sobre todo actividad y ubicación por palabras sueltas ("el contacto del hotel Cocoliso" → en las
  islas; "where is the meeting point in cartagena?" → sale de Cartagena).

**Meta de ex-4 (extractor "LLM primero", en el grupo CIEGO):** acierto ≥ 81,4 % y casos con invento claramente por
debajo del 15,8 % (lo mejor de los dos de hoy), con la extracción en p50 ≤ 0,9 s.
