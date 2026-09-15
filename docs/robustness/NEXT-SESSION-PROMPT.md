# Prompt para la siguiente sesión

Copia y pega lo de abajo.

---

## PROMPT

Retomamos el trabajo de robustez del bot en la rama `feature/pre_gadea`. Lee primero:
- la entrada `0.26.0` de `docs/HISTORY.md` (y la `0.25.0` si hace falta contexto);
- las entradas del 2026-09-15 de `docs/robustness/progress-log.md`: incluyen el inventario de las
  78 listas de vocabulario y cada medición de esta tanda, también las negativas;
- `docs/robustness/activity-domain-plan.md`.

### Cómo trabajar aquí (lo pidió el owner explícitamente)

- **Nada de parches regex.** Si la solución natural parece "añadir un patrón", busca el mecanismo
  común, la vía LLM o genera lo que haga falta desde el registro o el schema. Completar la
  conjugación de una lista única ("tengo" → "tiene") no es un parche; añadir una frase sí.
- **Cero código duplicado; ser óptimos.** Una fuente por concepto:
  - actividades: `data/knowledge_base/activities.json` + `src/domain/activities.py`;
  - paquetes: `dom.dive_packages()`;
  - certificación: `certification_status()` / `certification_claim()`;
  - lectura de inmersiones: `dive_counts_in()`;
  - dinero: `src/utils/money.py`; texto: `src/utils/text.py`.
- **Recurso escaso: peticiones/día (RPD)**, no tokens. No lances peticiones al LLM en paralelo con
  el eval-set (un 429 aborta la tanda). Si un cambio no altera la salida del regex en ningún mensaje
  del eval-set, no hace falta volver a correrlo: dilo explícitamente.
- **Medir por caso, no solo el agregado.** Un cambio que mejora uno y empeora otro no vale.
  - Cambios deterministas: foto antes/después sin LLM sobre los mensajes del eval-set, las tres
    baterías y sondas nuevas.
  - Si hace falta la línea base de HEAD: `git worktree add --detach <scratchpad>/wt_head HEAD`.
    Nunca `git stash`.
- **Juzgar el estado final**, no el intent. El eval-set NO pasa por el núcleo: para eso están las
  baterías (`scripts/battery_*`) y sondas sobre `_understand` / `_apply_short_answer`.
- **No dar por hecho lo que el cliente no eligió**: recomendar opciones según la situación y que
  elija; si algo es ambiguo, preguntar (owner 2026-09-14/15).
- Los resultados negativos se documentan, no se fuerzan.

### Cómo lanzar las mediciones

- Eval-set: `PYTHONPATH=. ENV_FILE=.env.dev python -m scripts.run_extraction_eval > <scratchpad>/x.raw`.
  **Sin `ENV_FILE=.env.dev` no hay clave y todas las llamadas degradan**; el script lo marca como
  tanda no comparable. La salida va en bloque al final: un fichero vacío no significa que esté
  colgado.
- Batería de booleanos: `ENV_FILE=.env.dev python -m scripts.battery_boolean_anchoring 3`.
- Foto de prompts: `scripts/snapshot_prompts.py -o base.json` en un worktree de HEAD y
  `--compare base.json` en el árbol de trabajo.
- Comparar por caso: `diff` de las líneas `[OK]/[GAP] id` entre dos `.raw`.

### Números de referencia (2026-09-15, último commit desplegado)

| medida | resultado |
|---|---|
| Eval-set (130 casos) | **221/230**. Fallan: 5 de los 7 casos `nat-mixto-*` (hueco conocido), 2 artefactos del arnés (casos con historial) y el ambiguo de ubicación "staying on the islands tomorrow". Los 123 casos anteriores: 220/223 |
| Batería de grupo, config PRE | repartos correctos **10/10**, total **13/13**, riesgo 12/13 (r13 vacío: pregunta sin asumir), 0 parciales / 0 inventados |
| Booleanos anclados | legítimos 18/24, alucinaciones evitadas 18/18 |
| Recomendación al acompañante | resolutor 11/11, estancia 6/6 |
| Pregunta "¿ya certificados o quieren certificarse?" | cuándo preguntar 10/10, resolutor 7/7 |
| Precio de paquetes (RAG, 21 preguntas sin LLM) | 11 cambios de 21 frente a antes, todos a bien |
| Suite | **2110 passed / 18 skipped** |

### Hecho el 2026-09-15 (no repetir)

- **Centralización:**
  - precios (`money.py`), quitatildes, edades y carrito desde el registro;
  - nombres de curso con una tabla;
  - una definición por campo en los prompts para `is_certified`, `location` e `is_colombian`;
  - código muerto de recomposición borrado.
- **Curso referido** detectado y cerrado con asesor. **Personas sin actividad elegida** →
  `undecided` y recomendación. **Pregunta aclaratoria** de nivel PADI.
- **Actividad y certificación:**
  - el veto de actividad no generaliza ("mindful diving specialty");
  - alcance de la negación en la certificación ("2 no tienen certificación");
  - "quiero hacer 2 inmersiones" → buceo certificado.
- **Reparto:** "N no están certificados" usa `certification_claim` ("somos 4 y dos no tienen
  licencia" ya reparte).
- **Certificación con una sola fuente** (detector y RAG), incluido el deseo de certificarse ("quiere
  sacarse la certificación" ya no sale certificado).
- **Tener un nivel en tercera persona** con la persona nombrada ("mi pareja tiene el advanced" ya no es
  el curso; "¿tienen el advanced?" sigue siendo pregunta al centro).
- **Ubicación pendiente:** un "no sé" sobre otra cosa ya no fija Cartagena.
- **Paquetes de buceo con una sola fuente** y precio correcto por días en el RAG ("paquete de 4 días" →
  el de 9 inmersiones).

### Cola de trabajo, por orden de valor

1. **Quién tiene la certificación dentro del grupo** (afecta a elegibilidad y precio).
   - **Sonda con LLM real (2026-09-15, en el progress-log):** en 9 de 9 mensajes con personas de
     estado distinto no sale reparto y el acompañante no se activa.
     - "mi amigo tiene licencia, yo no" y "somos 2, mi amigo es buzo y yo no" marcan al cliente como
       certificado.
     - "yo tengo el open water, mi esposa quiere probar" pierde a la esposa.
     - "mi esposo bucea, yo prefiero snorkel" pierde el buceo.
   - No es una puerta: `_relevant_gaps` pide total y reparto, y el LLM no los rellena. El detector
     fija `is_certified` con la afirmación de otra persona.
   - **Diseño propuesto:**
     - señal estructural "certificación atribuida a otra persona" (afirmación + sustantivo de
       persona de la lista compartida) para que el regex no fije `is_certified`;
     - definición única de `is_certified`/`group_allocation` por persona, con `certified_diving` +
       `undecided` y total contable.
   - Medir con el eval-set, la batería de grupo con escenarios nuevos de tercera persona y la
     batería de booleanos.
   - Mismo problema de fondo en `certification_status` (detector y RAG): "viene mi primo, él es
     certificado" y "4 certificados y 3 snorkel".
2. ~~"somos 5 y 2 nunca han buceado"~~ **hecho (2026-09-15)**: la regla final de `detect()` se
   generalizó ("la actividad principal no contradice el reparto"). Foto: 1 cambio de 244.
3. **Definición única por campo en los prompts, resto de campos**: `group_size`, `group_allocation`
   y `activity`.
   - Su texto en el tool lleva reglas medidas propias (plural vago, `undecided`) que hay que
     reconciliar.
   - Separar el significado neutro del tono de cada tarea: el tono de verificación en el prompt de
     relleno ya costó 5 casos.
   - Medir con el eval-set completo y la batería de grupo.
4. **Centralización de vocabulario, conceptos que quedan** (inventario en el progress-log). Cada paso
   con foto antes/después sin LLM.
   - `_BARE_PACKAGE_DIVE_RE` aún escribe `5|7|9` en el regex (el filtro ya sale del catálogo).
   - `_LOCATION_DEFER_RE` lee el "se" reflexivo como "sé": "que solo nos acompañe en la lancha, no se
     mete al agua".
   - Revisar el resto de listas del inventario.
5. **Comparación entre opciones** con las opciones del LLM del router (9/9 medido) en vez de
   `_mentioned_offerings`, midiendo también las otras 8 señales del router.
6. **Eval-set que pase por el núcleo** (`_understand`), para que su nota vea las guardas y deje de
   tener los 2 artefactos de casos con historial.
7. **Hallazgos antiguos por reproducir**: acompañante que llega a trozos, corrección tras el precio,
   "qué incluye el tour", cambio de reparto (f01).
8. **Observabilidad**: Langfuse frente a LangSmith (no pagar).
9. **CI**: `concurrency` en el job de deploy (dos pushes seguidos chocan; consultar con el equipo).

### Para reinvestigar (owner, 2026-09-15): medidos, sin solución todavía

Leer antes su entrada en el progress-log, porque cada uno tiene un intento descartado y medido.

A. **Grupo con nacionalidades mixtas → USD** (decisión del owner).
   - Hueco: "yo soy colombiano y mi novia extranjera" no lo reconoce `_MIXED_NATIONALITY_RE`, que
     es una lista de fraseos.
   - **Intento descartado:** meter "grupo mixto → false" en la definición de `is_colombian`. Rompía
     al residente ("no soy colombiano pero vivo en colombia") y solo arreglaba 1 de 6 casos mixtos.
     Revertido.
   - **Por qué no sirve:** un booleano no distingue "residente" de "grupo mixto".
   - Además, "somos colombianos pero mi amigo es aleman" no llega al LLM, porque el regex da True sin
     ambigüedad (no conoce gentilicios extranjeros).
   - **Pista:** un valor propio (campo o `mixed`) que dispare `_mixed_nationality_response`. Es un
     cambio de schema: diseñar y medir.
   - Ya hay 7 casos `nat-mixto-*` en el eval-set; hoy fallan 5 de 6.

B. **Respuesta doble tras F5a**: "desde cartagena, somos paisas" con la ubicación pendiente pierde la
   nacionalidad. La guarda (b) descarta el booleano que viaja con la respuesta a otra pregunta; coste
   conocido: una pregunta de más.
   - **Intento analizado:** separar la frase que contesta al slot del resto del mensaje. No hay
     arreglo determinista:
     - el regex no localiza "salimos de bocagrande";
     - tampoco ve "somos paisas" ni "ya tenemos el AOWD";
     - un resto de cortesía ("desde cartagena, gracias") dejaría pasar la alucinación que la guarda
       evita (18/18).
   - **Pista:** que el extractor diga en qué parte del mensaje apoya cada booleano, en la misma
     petición. Medir con la batería de booleanos más escenarios de cortesía.

C. **Unificar la ubicación entre detector y núcleo.**
   - **Discrepancias:** el resolutor corto (`_apply_short_answer`, con `_CARTAGENA_RE`/`_ISLAND_RE`)
     y `_detect_location` discrepan en 15 de 262 mensajes.
     - El núcleo no conoce "ctg", los apodos de la ciudad ni los hoteles.
     - El detector no conoce "barú" ni "isla"/"island" sueltos.
   - **Precedencias contrarias:**
     - el detector hace isla concreta > Cartagena > genérico, y el eval-set le da la razón en
       "estoy en cartagena pero el hotel es en isla grande";
     - copiarla al núcleo rompería "quiero ir a las islas del rosario desde cartagena", donde las
       islas son el destino.
   - **Otro fallo del detector:** "nos vemos en la marina" → Isla Marina, por el "marina" suelto.
   - **Pista:** distinguir salida o alojamiento de destino es semántico. Vía LLM, y después una sola
     fuente para las palabras de ubicación.
   - Foto base: script de comparación en el progress-log (224–262 mensajes).

### Decisiones pendientes del owner

- **Bubble Makers** sin servicio en `services.json` (D2).
- **Requisito previo del Rescue.**

### Aviso sobre PRE

- Es un solo entorno compartido. Un push a `feature/pre_gadea` despliega a PRE (CI: Lint + Tests +
  Deploy). El owner avisa al equipo.
- **No encadenar pushes**: espera a que termine la CI anterior (`gh run watch`), porque dos
  despliegues seguidos chocan con "container name already in use".
- No leer `/opt/diving-planet-bot/.env.pre`, no tocar `pre-launch-checklist.csv` y no pagar
  LangSmith.
