# Prompt para la siguiente sesión

Copia y pega lo de abajo.

---

## PROMPT

Retomamos el trabajo de robustez del bot en la rama `feature/pre_gadea`. Lee primero las entradas
`0.26.0` y `0.25.0` de `docs/HISTORY.md`, las entradas del 2026-09-15 de
`docs/robustness/progress-log.md` (incluye el inventario de las 78 listas de vocabulario) y
`docs/robustness/activity-domain-plan.md`.

### Cómo trabajar aquí (lo pidió el owner explícitamente)

- **Nada de parches regex.** Si la solución natural parece "añadir un patrón", busca el mecanismo
  común, la vía LLM o genera lo que haga falta desde el registro/schema.
- **Cero código duplicado; ser óptimos.** Una fuente por concepto: registro de actividades
  (`data/knowledge_base/activities.json`), `src/utils/money.py`, `src/utils/text.py`.
- **Recurso escaso: peticiones/día (RPD)**, no tokens. No lances peticiones al LLM en paralelo con
  el eval-set (un 429 aborta la tanda).
- **Medir por caso, no solo el agregado.** Un cambio que mejora uno y empeora otro no vale. Para
  cambios deterministas: foto antes/después sin LLM sobre los mensajes del eval-set y las baterías.
- **Juzgar el estado final**, no el intent. El eval-set NO pasa por el núcleo: para eso están las
  baterías (`scripts/battery_*`) y sondas sobre `_understand`.
- **No dar por hecho lo que el cliente no eligió**: recomendar opciones según la situación y que
  elija; si algo es ambiguo, preguntar (owner 2026-09-14/15).
- Los resultados negativos se documentan, no se fuerzan.

### Números de referencia (2026-09-15, código desplegado)

| medida | resultado |
|---|---|
| Eval-set (123 casos, `run_extraction_eval.py`) | **213/219** en la última tanda completa (antes de añadir 4 casos de ubicación). Fallos: 2 artefactos del arnés, "mindful diving specialty", "no soy colombiano pero vivo en colombia", la actividad de "two have open water and one does not" |
| Batería de grupo, config PRE | repartos correctos **10/10**, total **13/13**, riesgo 12/13 (r13 vacío: pregunta sin asumir), 0 parciales / 0 inventados |
| Booleanos anclados | legítimos 18/24, alucinaciones evitadas 18/18 |
| Recomendación al acompañante | resolutor 11/11, estancia 6/6 |
| Pregunta "¿ya certificados o quieren certificarse?" | cuándo preguntar 10/10, resolutor 7/7 |
| Suite | 2025 passed / 18 skipped |

### Hecho el 2026-09-15 (no repetir)

- Centralización sin cambios de prompt: precios (`money.py`, COP en un solo formato), quitatildes,
  edades desde el registro, carrito derivado del registro, etiqueta del acompañante, nombres de
  curso con una sola tabla ("advanced open water" ya es Advanced).
- Curso referido detectado (v2) y cerrado con asesor (`contact_only`, `offer: false`).
- Decisión 3: personas del grupo sin actividad elegida → `undecided` y recomendación (antes el LLM
  suponía snorkel y el regex minicurso).
- Decisión 2: pregunta aclaratoria de nivel PADI con señal estructural del detector.
- `location` medido con casos de ciudad + islas: la verificación no gana nada; sin cambios.

### Cola de trabajo, por orden de valor

1. **Centralización de vocabulario por concepto** (inventario en el progress-log), siguiente paso
   del orden: **mención de otra persona/acompañante** (unas 13 listas en núcleo, RAG y supervisor
   que ya comparten `_PERSON_NOUN_*`), luego certificación en RAG/núcleo (la del RAG y
   `certification_claim` discrepan en 34 de 202 mensajes en los dos sentidos: diseñar antes de
   fusionar), ubicación y paquete. Cada paso con foto antes/después sin LLM.
2. **Definición única por campo en los prompts**: descripción del tool + guía de verificación ES/EN
   repiten la definición (para `is_colombian` hubo que editar tres). Separar el significado neutro
   del tono de cada tarea (el tono de verificación en el prompt de relleno ya costó 5 casos) y medir
   con el eval-set completo.
3. **Nacionalidad**: "no soy colombiano pero vivo en colombia" sigue dando `False`; grupos mixtos
   que `_MIXED_NATIONALITY_RE` no reconoce ("yo soy colombiano y mi novia extranjera") → USD.
4. **"somos 4 y dos no tienen licencia"**: sin reparto ni recomendación (el LLM no siempre marca
   `undecided`; el regex no cubre "no tienen licencia").
5. **Comparación entre opciones** con las opciones del LLM del router (9/9 medido) en vez de
   `_mentioned_offerings`, midiendo también las otras 8 señales del router.
6. **"mindful diving specialty"** y la actividad de "two have open water and one does not".
7. **Respuesta doble tras F5a** ("desde cartagena, somos paisas" pierde la nacionalidad).
8. **Eval-set que pase por el núcleo** (`_understand`), para que su nota vea las guardas.
9. **Hallazgos antiguos por reproducir**: acompañante que llega a trozos, corrección tras el precio,
   "qué incluye el tour", cambio de reparto (f01).
10. **Observabilidad**: Langfuse frente a LangSmith (no pagar).
11. **CI**: `concurrency` en el job de deploy (dos pushes seguidos chocan; consultar con el equipo).

### Decisiones pendientes del owner

- **Bubble Makers** sin servicio en `services.json` (D2).
- **Requisito previo del Rescue.**

### Aviso sobre PRE

Es un solo entorno compartido. Un push a `feature/pre_gadea` despliega a PRE (CI: Lint + Tests +
Deploy). El owner avisa al equipo. **No encadenar pushes**: espera a que termine la CI anterior
(dos despliegues seguidos chocan con "container name already in use").
