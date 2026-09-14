# Prompt para la siguiente sesión

Copia y pega lo de abajo.

---

## PROMPT

Retomamos el trabajo de robustez del bot en la rama `feature/pre_gadea`. Lee primero la
entrada `0.25.0` de `docs/HISTORY.md`, las entradas del 2026-09-14 (tarde) de
`docs/robustness/progress-log.md` y `docs/robustness/activity-domain-plan.md`.

### Cómo trabajar aquí (lo pidió el owner explícitamente)

- **Nada de parches regex.** Si la solución natural parece "añadir un patrón", busca el
  mecanismo común, la vía LLM o genera lo que haga falta desde el registro o el schema.
- **Centralizar, no individualizar**: fuente única (`data/knowledge_base/activities.json`).
- **Recurso escaso: peticiones/día (RPD)**, no tokens.
- **Medir por caso, no solo el agregado.** Un cambio que mejora uno y empeora otro no vale.
- **Juzgar el estado final**, no el intent. El eval-set NO pasa por las guardas del núcleo:
  para ellas están las baterías (`scripts/battery_*`).
- **No dar por hecho lo que el cliente no eligió**: recomendar opciones según la situación
  y que elija el cliente (owner 2026-09-14).
- **Los prompts de extracción son sensibles a cada palabra**: un valor de enum o una glosa
  nueva mueven otros campos (F2b, referido). Mide siempre con el eval-set completo.
- Los resultados negativos se documentan, no se fuerzan.

### Números de referencia (2026-09-14, código desplegado)

| medida | resultado |
|---|---|
| Eval-set (119 casos, `run_extraction_eval.py`) | **214/219 (97,7 %)**. activity 70/72, is_certified 31/32, group_allocation 10/11, is_colombian 11/12, resto 100 % |
| Batería de grupo, config PRE (`battery_group_allocation_gate.py`) | repartos correctos **9/10**, total **13/13**, riesgo 10/10 (+ r11–r13 3/3 medidos aparte), 0 parciales, 0 inventados |
| Booleanos anclados (`battery_boolean_anchoring.py`) | legítimos 18/24, alucinaciones evitadas 18/18 |
| Resolutor de actividad del acompañante / de estancia | 11/11 / 6/6 |
| Señal del acompañante con guarda | 7/16 (en los otros 9 el bot pregunta con recomendaciones) |
| Router, opciones al comparar (`battery_activity_choice.py`) | 6/9 (9/9 posible, sin aplicar) |
| Suite | 1982 passed / 18 skipped |

Fallos que quedan en el eval-set:
- "mindful diving specialty";
- carta de referido;
- "no soy colombiano pero vivo en colombia";
- dos artefactos del arnés, que no pasa por el núcleo ("ninguno colombiano", "desde cartagena").

"colombiano no, soy venezolano" ya lo arregla la abstención del regex (medido aparte, 3/3).

### Cola de trabajo, por orden de valor

1. **Detectar la carta de referido (hoy se cotizan 219 USD de más).** Ya aplicado: cierre con
   asesor por `contact_only`, `offer: false`, `cart_type` y `dom.sibling_ids()`. Falta la
   **detección**, y solo si el cliente lo dice (owner). Probado y revertido: veto de actividad
   disparado por hermanas + referido en el enum → eval-set 214 → 213 ("hey we arent
   certified, first time diving" pasó a Open Water; la glosa nombraba `padi_open_water`).
   Siguiente intento: glosa que no nombre el Open Water, o un resolutor acotado Open
   Water/referido. Medir con el eval-set completo.
2. **Pregunta aclaratoria "¿ya certificados o quieren certificarse?"** (owner) cuando un tramo
   o mensaje nombra un nivel que también es certificación ("2 open water y 3 snorkel", "3
   advanced"). Hoy se lee como buzos certificados (batería de grupo `b05`).
3. **"somos 3, uno no está certificado" → recomendar opciones** (owner), no asumir minicurso.
   Cambiar lo que espera el eval-set (`split-one-not-certified-es`, `split-open-water-one-not`,
   `split-en-have-open-water`) y disparar la recomendación de F6 también para ese tramo.
4. **Nacionalidad, lo que queda:** "no soy colombiano pero vivo en colombia" sigue dando
   `False` con el LLM; `_MIXED_NATIONALITY_RE` no reconoce "yo soy colombiano y mi novia
   extranjera" (el grupo mixto debe ir a USD); y decidir el flag
   `llm_nationality_veto_cutover` (casi no dispara, porque el regex se abstiene en los
   ambiguos).
5. **`location` con disparador propio**: sin casos en el eval-set que nombren ciudad e islas.
   Añadirlos antes (p. ej. "we're in cartagena now, staying on the islands tomorrow").
6. **Comparación entre opciones**: el núcleo usa `_mentioned_offerings` (regex), aunque el
   router acierta las opciones 9/9 con el vocabulario del registro (F2b). Pasar la
   comparación a las opciones del LLM y medir también las otras 8 señales del router.
7. **"mindful diving specialty"**: el regex gana con "diving". Hoy el bot pregunta qué
   especialidad (F4), así que es seguro. Buscar una vía que no abra el enum del extractor.
8. **Respuesta doble tras F5a**: "desde cartagena, somos paisas" pierde la nacionalidad y el
   bot la pregunta después. Coste conocido; medir si molesta.
9. **El eval-set no pasa por el núcleo** (`_understand`). Valorar un modo que sí pase.
10. **Hallazgos antiguos por reproducir**: acompañante que llega a trozos, corrección tras el
    precio, "qué incluye el tour", cambio de reparto (f01 de la batería de grupo).
11. **Observabilidad**: Langfuse frente a LangSmith (no pagar; LangSmith agotado hasta el 1 de
    octubre). Envoltorio centralizado en `src/llm_client.py::trace_openai`.

Hecho y cerrado el 2026-09-14 (no repetir): fallback de la petición fusionada (decidido no
tenerlo), `is_certified` con disparador propio, repartos "no contables", edad de
Advanced/Rescue, textos del registro, precio "183 USD", recomendación al acompañante (F6).

### Decisiones pendientes del owner

- **Bubble Makers** sin servicio en `services.json` (D2): no se puede reservar.
- **Requisito previo del Rescue.**

### Aviso sobre PRE

Es un solo entorno compartido. Un push a `feature/pre_gadea` despliega a PRE (CI: Lint +
Tests + Deploy). El owner avisa al equipo.

**No encadenar pushes.** El 2026-09-14, dos pushes con menos de ~4 minutos de separación
hicieron chocar los despliegues ("container name already in use"): el job de Deploy salió en
rojo aunque los tests pasaban. Lo arregló el siguiente despliegue. Espera a que termine la CI
antes del siguiente push, o agrupa commits. Arreglo de fondo pendiente: un `concurrency` en
el job de deploy del workflow (config compartida: consultarlo con el equipo).
