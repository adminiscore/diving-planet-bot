# Prompt para la siguiente sesión

Copia y pega lo de abajo.

---

## PROMPT

Retomamos el trabajo de robustez del bot en la rama `feature/pre_gadea`. Lee primero:
- las entradas `0.27.0` y `0.26.0` de `docs/HISTORY.md`;
- la entrada del 2026-09-16 de `docs/robustness/progress-log.md` y las del 2026-09-15: incluyen el inventario de las
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

### Números de referencia (2026-09-16, tras cerrar los huecos 1–3)

| medida | resultado |
|---|---|
| Eval-set (130 casos) | **221/230**. Fallan: 5 de los 7 casos `nat-mixto-*` (hueco conocido), 2 artefactos del arnés (casos con historial) y el ambiguo de ubicación "staying on the islands tomorrow". `split-one-not-certified-es` espera `is_certified: null` desde el 2026-09-15 (la frase habla de un miembro del grupo) |
| Eval-set por el núcleo (`run_extraction_eval --core`) | **230/230**, 0 a peor (227 antes de los huecos 1–3) |
| Batería de grupo, config PRE (52 escenarios) | repartos **17/17**, total **13/13**, riesgo **17/17**, **0 alucinaciones, 0 parciales, 0 totales mal**; segunda petición de grupo +8,1 % peticiones |
| Booleanos anclados (21 escenarios, con cortesías) | legítimos **33/33**, alucinaciones evitadas **30/30** (tras B y J) |
| Recomendación al acompañante | resolutor 11/11, estancia 6/6 |
| Pregunta "¿ya certificados o quieren certificarse?" | cuándo preguntar 10/10, resolutor 7/7 |
| Precio de paquetes (RAG, 21 preguntas sin LLM) | 11 cambios de 21 frente a antes, todos a bien |
| Batería del router (8 rep. en seguridad, 3 en el resto) | seguridad **18/21**, resto **12/16**. Fallos estables: `s02` y `a03`/`a02` marcan las dos señales o la equivocada (oscilan entre tandas con la petición idéntica), `n07`, `r07`–`r09` |
| Suite | **2517 passed / 18 skipped** |

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

1. ~~Quién tiene la certificación dentro del grupo~~ **cerrado (2026-09-15)**. Detalle y mediciones
   en el progress-log.
   - **Batería de grupo, config PRE:** repartos 17/17, total 13/13, riesgo 17/17, 0 alucinaciones, 0
     parciales, 0 totales mal. Segunda petición de grupo +8,1 % peticiones.
   - **Hecho también:** la regla contradictoria de `group_allocation` (parche mínimo, empata en
     todo) y el sujeto pospuesto ("no es certificado mi acompañante" ya no es de quien escribe).
2. ~~"somos 5 y 2 nunca han buceado"~~ **hecho (2026-09-15)**: la regla final de `detect()` se
   generalizó ("la actividad principal no contradice el reparto"). Foto: 1 cambio de 244.
3. ~~Definición única por campo en los prompts, resto de campos~~ **hecho (2026-09-15)**.
   - `activity`, `group_size` y `group_allocation` salen de `_FIELD_MEANING_*` (el texto ya medido del
     tool) más `_FIELD_VERIFY_RULES_*` (solo en las guías de verificación).
   - **Negativo medido:** poner las reglas de verificación en el tool baja el eval-set a 217/230 y
     vuelve a repartir b05.
   - **Medido y revertido:** unificar la regla "un plural vago no es una cantidad" (cinco sitios) en
     una pieza compartida. En el prompt de señales empeora "ocho personas hacen snorkel y yo buceo"
     (hablante como acompañante fantasma 2/3) y "mi amigo bucea y mis amigos hacen snorkel". Se deja
     cada texto como está.
4. **Centralización de vocabulario, conceptos que quedan** (inventario en el progress-log).
   - **Hecho (2026-09-15):** paquete sin unidad desde el catálogo y el "no se" reflexivo en la duda de
     ubicación (la duda delega solo si es la respuesta entera).
   - **Hecho (2026-09-15):** palabras numéricas con una sola fuente, `src/utils/number_words.py`
     (eran 20 copias). Foto sin LLM: 0 cambios de 1215. `_PURE_COMPANION_RE` era código muerto
     (borrado). La familia de acompañante del RAG no era duplicado: pregunta otra cosa.
   - **Hecho:** alineados los rangos ES/EN del RAG, nacionalidad mixta hasta 10 y días de paquete
     desde el catálogo. Foto: 7 cambios de 1215, todos buscados.
   - **Punto 4 cerrado** salvo lo que está en "Para reinvestigar" (ubicación, nacionalidad mixta).
5. ~~Comparación entre opciones con las opciones del LLM del router~~ **medida y no aplicada
   (2026-09-15)**. El enum del registro vuelve más ruidosas "soy epiléptica" (9/9 → 17/21) y "quiero
   buceo y snorkel para los dos" (9/9 → 9/12) a cambio de un único fraseo. Queda la batería real de
   las 9 señales: `scripts/battery_router_signals.py`.
   - **Hecho por la vía general:** los nombres de especialidad salen de las etiquetas del registro
     (antes estaban escritos tres veces y la tabla de cursos solo conocía nitrox). "dudo entre la
     especialidad de nitrox y la de flotabilidad" ya compara sin tocar el router. Foto sin LLM: 5
     cambios de 238 en el corpus, todos a mejor.
   - Dos hallazgos nuevos que salieron de esta medida pasan a "Para reinvestigar" (D y E).
6. ~~Eval-set que pase por el núcleo~~ **hecho (2026-09-15)**: `run_extraction_eval --core`. Da
   216/230 frente a 221/230 del modo script: los 2 artefactos de historial pasan a bien y hay 7 a
   peor, explicados uno a uno en el progress-log. Usar `--core` para medir cambios del núcleo; el
   modo script sigue sirviendo para medir el extractor suelto.
   - Los 4 costes de guarda que salieron de esta medida pasan a "Para reinvestigar" (F).
7. ~~Hallazgos antiguos por reproducir~~ **reproducidos (2026-09-15)**, con causa y pista en el
   progress-log ("Tarea 7"). Reproducción en local: `ENV_FILE=.env.dev python -m
   scripts.repro_old_findings [repeticiones] [drip,correccion,correccion_antes,f01,tour]`
   (conversación con `route_message`, RAG mockeado sin BD local, respuestas a slots según
   `core_pending_slot`). **Por arreglar, en este
   orden** (los dos primeros cobran mal sin avisar):
   - ~~**7a. Acompañante que llega a trozos (3/3).**~~ **arreglado (2026-09-15)**: el LLM decide
     quién es otra persona, se pregunta el total si podía estar ya contada y se mueve o se añade
     según la respuesta. LLM real 3/3; foto de baterías 0 cambios. Antes: "él quiere hacer snorkel" cambia la actividad
     principal, el reparto sigue en 2 buceadores y el resumen cobra 2 inmersiones.
     - **Causa:** el núcleo no ve el pronombre como otra persona, y el "latest wins" de actividad
       pisa la principal; la red de precisión no se llama.
     - **Pista:** reutilizar `_OTHER_PERSON_SUBJECT_RE` del detector antes del "latest wins".
   - ~~**7b. Correcciones.**~~ **arreglado (2026-09-15)**: con cue se aplica, sin cue se confirma; el regex propone y la verificación LLM de campos sabidos arbitra; el cierre se reconstruye. Antes: "espera, en realidad no somos colombianos" tras el precio re-emite COP
     (2/2), y antes del precio tampoco se aplica en `is_certified` ni en `location`.
     - **Causa:** `_apply_detected_intent` solo escribe esos campos la primera vez.
     - **Pista:** una única regla de corrección para todos los campos (la del total, con cue
       explícito) y re-emitir el resumen tras el cierre.
   - ~~**7c. Cambio de reparto (f01, 3/3).**~~ **arreglado (2026-09-15)** con el mismo mecanismo que 7b. Antes: "al final mi suegra también bucea" no cambia el
     reparto. Es la misma familia que 7b.
   - ~~**7d. "primero dime qué incluye el tour"**~~ **arreglado (2026-09-15)**, por estructura; antes recibía un acuse genérico:
     `_looks_like_info_question` va anclado al inicio del mensaje. Medir los falsos positivos de
     carrito antes de desanclar.
   - **Medir con:** el script de reproducción (3 repeticiones), `--core`, la batería de grupo y la
     de booleanos.
8. **Observabilidad: PENDIENTE — migrar a Langfuse.** Analizada (2026-09-16): recomendación Langfuse Cloud Hobby
   (50k unidades/mes, 30 días, 2 usuarios; ~830–1.040 conversaciones/mes frente a ~420–830 con LangSmith
   Developer, que ya agotó su cuota). Antes de migrar, el owner decide: trazas en un tercero (con `redact_pii`
   como máscara), tráfico esperado en PRO y quién crea la cuenta. Plan de migración en 6 pasos en el
   progress-log ("Tarea 8") y en la página publicada https://claude.ai/artifact/4dwaZZmDm7566oPg9sBJ19.
9. **CI: PENDIENTE.** `concurrency` en el job de deploy (dos pushes seguidos chocan con "container name already in use"; consultar con el equipo).

### Para reinvestigar (owner, 2026-09-15): medidos, sin solución todavía

Leer antes su entrada en el progress-log, porque cada uno tiene un intento descartado y medido.

A. ~~**Grupo con nacionalidades mixtas → USD**~~ **arreglado (2026-09-15, owner: que lo lea el LLM)**: valor
   `mixed_nationality` en la petición del turno, solo con los dos lados del grupo en el mensaje
   (`mentions_writer_and_others`); la lista de fraseos, fuera. `eval --core` 226/230. Antes:
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

B. ~~**Respuesta doble tras F5a**~~ **arreglado (2026-09-15)**: cita de cada booleano en la misma petición
   (`evidence`, solo con ubicación o total pendientes); booleanos 33/33 y 30/30. Antes: "desde cartagena, somos paisas" con la ubicación pendiente pierde la
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

C. ~~**Unificar la ubicación entre detector y núcleo**~~ **arreglado (2026-09-15/16)**:
   - **C:** una sola fuente de palabras de lugar; el resolutor corto usa el lector del detector.
   - **C.2:** con Cartagena y una isla, la preposición de cada lugar (estancia > origen > sin preposición >
     destino; lo negado no cuenta) en `place_by_role`. Dejarlo al LLM se midió peor y se revirtió.
   - **C.3:** la forma corta de "Isla X" ("grande", "marina"...) solo cuenta si el mensaje nombra una isla.
   - Sonda con el LLM real: apertura 22/22 y respuesta 20/20 en los casos de referencia; `eval --core` 227/230.
   - Quedan: ver "Huecos conocidos para la próxima sesión".

D. ~~**Pronóstico del tiempo sin escalar**~~ **arreglado y medido (2026-09-15, router `s04` 0/3 → 3/3)**: un
   único lector `llm_client.tool_arguments` reencaja desde el esquema la clave aplanada
   (`weather_conditions: true` → `sensitive_topic`). Antes: (hallazgo 2026-09-15, ya en producción; es de seguridad).
   - "¿va a llover mañana en cartagena?": ninguna palabra clave de `detect_sensitive_escalation` lo
     caza, y el LLM del router devuelve una clave `weather_conditions: true` que no existe en el
     esquema (3/3 con el enum actual) en vez de `sensitive_topic: "weather_conditions"`. Nadie la
     lee y el mensaje sigue el flujo normal, donde se podría inventar el pronóstico.
   - Medido con `scripts/battery_router_signals.py` (caso `s04-llover-manana`).
   - **Pista:** es un fallo de forma del tool, no de vocabulario. Mirar por qué el modelo saca el
     valor del enum a clave propia (la descripción de `sensitive_topic` es muy larga y mezcla cuatro
     temas) antes de pensar en añadir palabras clave. Medir las 9 señales, no solo esta.

E. ~~**Reparto leído como comparación**~~ **arreglado (2026-09-15)**: cada oferta con su propio sujeto
   (`clause_subject`) es un reparto y anula la señal `comparing_options` del LLM. LLM real 3/3.
   - "tengo un amigo que quiere bucear y yo hago snorkel": el router dice `comparing=true` 3/3 y
     `_is_deliberation_between_options` lo acepta, porque el texto nombra 2 ofertas y no hay número
     ni "quiero". Va a RAG a explicar la diferencia en vez de a la reserva.
   - Medido con `scripts/battery_router_signals.py` (caso `n07-amigo-snorkel`).
   - **Pista:** cada oferta tiene su propio sujeto (el amigo, yo), igual que un reparto. Buscar la
     señal estructural (sujetos distintos por actividad) en vez de ampliar `_COMMITMENT_RE`, y medir
     con los casos de deliberación del núcleo y la batería del router.

F. **Costes de las guardas del núcleo** (hallazgo 2026-09-15 con `run_extraction_eval --core`).
   El LLM acierta y una guarda descarta el valor. Cada uno cuesta una pregunta de más, nunca un
   valor malo. Detalle, sondas y réplicas deterministas en el progress-log ("Tarea 6").
   1. ~~**"ya llevo el rescue, quiero seguir buceando"**~~ **arreglado (2026-09-15)**: la pieza de tener un nivel
      conoce los verbos de posesión y de haberlo hecho en primera y tercera persona. Antes: el LLM da `is_certified=True` 3/3 y
      `_flag_cert_or_course` lo borra, porque "llevo" no está en las piezas de tener un nivel
      (`_HOLDS_WRITER`). El bot pregunta "¿ya la tienes o quieres sacarla?".
      - **Pista:** hueco de conjugación en la pieza compartida, no una frase nueva.
   2. ~~**"vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel"**~~ **arreglado con H (partición de
      las personas nombradas)**. Antes: el LLM da
      `{certified_diving: 2, snorkel: 1}` y la guarda de cifras lo tira, porque el 2 no está en el
      texto.
      - **Pista:** la composición "X y yo" respalda un 2, igual que `_named_people` respalda cifras 1.
   3. ~~**"my daughter is 9 and my son is 12, my wife and i dive"**~~ **arreglado con H (la misma
      partición conserva el total 4)**. Antes: el LLM da total 4 y
      `{certified_diving: 2, undecided: 2}` 3/3. La misma guarda tira el reparto y, con él, el total.
      - **Pista:** no tirar un total que cuadra con las personas nombradas (esa regla ya existe
        sin reparto).
   4. ~~**"im from the states, wanna dive"**~~ **cerrado sin cambio (2026-09-15, owner: preguntar)**: la
      abstención cumple la definición (extranjero Y no vive en Colombia) y protege al residente, que paga
      en COP. Se corrige la expectativa del eval-set a `null`. Antes: el LLM se abstiene de `is_colombian` 3/3 cuando solo se
      piden los huecos. Es la sensibilidad a la forma del prompt ya vista en F2b.
      - **Pista:** es de prompt; medir con el eval-set en los dos modos.
   - **Medir con:** `--core`, la batería de grupo (config PRE) y la de booleanos. Sin empeorar
     los casos de riesgo, que son justo los que estas guardas protegen.

J. ~~**"vale perfecto" con la ubicación pendiente rellena `is_certified=False`**~~ **arreglado (2026-09-15)**: la
   petición cambió en 7b (prompt combinado); los campos sabidos viajan ahora como relleno y se comparan con lo
   guardado. Booleanos 18/18, sonda 36/39 frente a 25/39. Antes (hallazgo 2026-09-15, ya en HEAD):
   - Batería de booleanos (`charla-vale-perfecto`): la alucinación se evitaba 3/3 en la referencia de 7b;
     hoy 2 de 4 en HEAD y en el árbol, con la petición idéntica byte a byte (`bool_scn_reps`).
   - No lo causa A (el mensaje no abre su puerta). Algún cambio entre 7b y F.4 lo dejó expuesto, o
     la referencia tuvo suerte: bisecar con la misma sonda antes de tocar nada.

K. ~~**"al final mi suegra también bucea, no hace snorkel" tras el cierre va a RAG**~~ **arreglado (2026-09-15)**:
   las ofertas de una frase negada no cuentan como opciones (`_weighed_offerings`); conversación 3/3. Antes:
   - La corrección del reparto se pierde: el router marca `comparing_options` y la puerta de deliberación
     del núcleo lo acepta (2 ofertas, sin cifra ni "quiero"). Visto 2/2 en la tanda de J y ya en la de H;
     en la de 7b pedía confirmación 2/2 (intermitente).
   - No pasa por la petición de extracción (la puerta va antes), así que no lo causa J.
   - **Pista:** una oferta negada ("no hace snorkel") no es una opción que se sopesa; señal estructural,
     igual que la de E (sujeto propio). Medir con `repro_old_findings f01_conversacion` y la batería del router.

I. ~~**El LLM se abstiene del grupo entero con muchos campos pedidos**~~ **arreglado (2026-09-15)** para la
   familia "persona con estado distinto": la frase elíptica del contraste se lee por su polaridad y el
   detector reparte sin depender del LLM. Antes: (medido 2026-09-15, ya en PRE).
   - "soy certificado y mi hijo no", "my wife is certified and I am not" y "mi pareja tiene el
     advanced y yo no tengo nada" (familia p de la batería de grupo), con estado vacío: con los
     mismos prompts y peticiones, el LLM devuelve a veces `{}` completo. p02 1/2, p05 1/2, p07 0/2
     en HEAD. La base de las 12:51 y la tanda de las 16:45 dieron 17/17; es inestabilidad del
     modelo, no de un cambio.
   - **Consecuencia segura:** sin reparto ni total, el bot pregunta. No cobra mal.
   - **Causa conocida:** los campos del grupo se pierden cuando viajan con muchos otros (efecto de
     recencia, ver `combined_extraction_system_prompt`). La segunda petición de grupo no se lanza
     si la primera volvió vacía del todo; fue una decisión de coste (+13 % → +27 % peticiones en el
     peor caso).
   - **Pista:** una señal estructural barata de "hay grupo que repartir" (2+ personas nombradas y
     un contraste de estado, como "y yo no") que dispare la segunda petición también cuando la
     primera vuelve vacía. Medir coste y aciertos con la batería de grupo en 3+ repeticiones: con
     2 no se distingue el ruido.

H. ~~**"¿Cuántos serían para X?" suma encima del total ya sabido**~~ **arreglado (2026-09-15)**: con el
   total sabido la actividad principal se queda con el resto (`_with_main_rest`), la principal no se
   pregunta y las respuestas se reparten dentro del total. Detalle en el progress-log. Antes (hallazgo 2026-09-15 al medir 7c;
   ya estaba antes de 7a, reproducido en 4a9c327). **Grave: cobra personas que no existen.**
   - "hola, vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel": la guarda de cifras tira el
     reparto (F.2), encola las dos actividades y pregunta "¿cuántos serían para buceo
     certificado?". Contestar "uno" deja 4 buceadores y el snorkel lo lleva a 5, con un total de 3
     ya conocido.
   - **Causa:** la respuesta de `SLOT_COMPANION_QTY` fusiona con `_merge_companion_activity`, que
     suma sin mirar el total. Además pregunta por la actividad principal, que el mensaje de
     apertura no permite distinguir de un acompañante.
   - **Pista:** la misma regla de 7a (`_add_or_ask_companion`, quien ya estaba contado no se suma)
     aplicada a esa respuesta, y arreglar F.2 ("X y yo" respalda un 2), que es lo que la dispara.

G. ~~**Una respuesta que no contesta la pregunta pendiente se toma como su respuesta**~~ **arreglado (2026-09-15)**:
   solo es respuesta a "¿cuántos?" lo que ES la cantidad o lo que el detector lee como total; el resto va al resolutor LLM,
   que descarta números de otra magnitud. Antes: (hallazgo
   2026-09-15, al medir 7c con una conversación que ignoraba lo que preguntaba el bot).
   - Con "¿cuántos serían para snorkel?" pendiente, "no, buceamos hace 6 meses" llevó el grupo de
     3 a 9 buceadores. La respuesta corta determinista lo rechaza (`_apply_short_answer` →
     False); el 6 lo pone el resolutor LLM del slot al leer "6 meses".
   - La verificación de campos sabidos de 7b lo detectó al turno siguiente y propuso volver a 3 (2
     buceo + 1 snorkel) con confirmación, pero el valor malo se había escrito antes.
   - **Pista:** es la misma familia que la guarda (b) de F5a (el turno contestó otra pregunta).
     `_turn_answered_a_different_slot` no lo cubre porque el dato de seguridad ya estaba. Medir con
     conversaciones que respondan otra cosa a cada slot pendiente.

### Huecos conocidos para la próxima sesión (2026-09-16)

Revisados contra el último `eval --core` (230/230) y lo anotado. Hechos el 2026-09-16: fallos 1–3 y la medida de las optimizaciones 1–2. Orden propuesto ahora: fallos 4–5, optimización 1 (vía extracción), optimización 3 y el resto.

**Fallos que nota el cliente**
1. ~~Querer un curso que no se reconoce como querer~~ **arreglado (2026-09-16)**: clase de querer con interés y
   "ser"; nombre de producto de cursos y especialidades desde el registro.
2. ~~Duración que no se lee~~ **arreglado (2026-09-16)**: cantidad × unidad.
3. ~~Certificación en inglés elíptico~~ **arreglado (2026-09-16)**: `_NEVER_DIVED`, una sola fuente.
4. **Reparto intermitente del LLM.** "4 con título y 2 snorkel" (b03 de la batería de grupo) sale bien 1–2 de cada 3
   veces con la petición idéntica; se podría leer sin depender del LLM.
5. **Reparto sin "yo" explícito.** "mi amigo quiere bucear y hago snorkel" sigue dependiendo del LLM: la señal de E
   (`clause_subject`) exige un sujeto explícito.
6. **Ubicación, restos de C:**
   - "no sé si cartagena o las islas" fija Cartagena (sin preposición decide la precedencia; la duda debería preguntarse);
   - "estamos en las islas pero salimos desde cartagena" sale isla (la estancia gana al origen), discutible;
   - alias de hotel que son palabras corrientes: "luxury", "flores", "secreto".

**Optimizaciones**
1. **Peticiones por turno: medidas, una fusión descartada (2026-09-16).** Por turno: router (siempre), extracción,
   respuesta y notas (3+ palabras). Llevar las notas al router tiraba "¿va a llover mañana?" (hasta 2/8) o "perdí una
   pierna" (2/8): revertido, detalle en el progress-log. Siguiente candidata: las notas dentro de la petición de
   extracción con `extra_fields` (mismo mecanismo que `mixed_nationality`/`evidence`), midiendo con `--core`, la batería
   de grupo y la de booleanos; no tocar el prompt del router.
2. ~~Las pruebas gastan la cuota de trazas~~ **ya estaba hecho** desde el 2026-09-14 (`scripts/__init__.py`).
3. **Tamaños de paquete escritos a mano.** `_BARE_PACKAGE_DIVE_RE` fija todavía `5|7|9`; un paquete nuevo sin unidad no
   se leería.
4. **Segunda petición de grupo.** Cuesta +8 % peticiones en la batería de grupo; revisar si sigue haciendo falta tras I.

**Infraestructura**
1. **`docs/robustness/eval-set.json` no está en la imagen de Docker**: el eval no se puede lanzar dentro del contenedor
   de PRE sin inyectarlo.
2. **Tarea 8** (pendiente: migrar a Langfuse) y **tarea 9** (pendiente: `concurrency` en el deploy), arriba en la cola.
3. **Veto LLM de `location` apagado** por defecto (`llm_location_veto_*`); no se ha comprobado PRE sin leer `.env.pre`.

**Consecuencias aceptadas (no tocar sin decisión)**
- "somos de nacionalidad mixta" sin nombrar a nadie no dispara la explicación de USD (A).
- "llevo el open water a medias" se lee como tener el nivel (F.1).
- "mi hermano es buzo, yo no quiero bucear" deja a quien escribe sin decidir (I).
- "nos vemos en la marina" como respuesta a la ubicación ya no es isla (C.3), pero "vamos al pirata" tampoco.


### Decisiones pendientes del owner

- **Bubble Makers** sin servicio en `services.json` (D2).
- **Requisito previo del Rescue.**

- **Tarea 8, antes de migrar a Langfuse:** trazas en un tercero (con `redact_pii`), tráfico esperado en PRO y quién crea la cuenta.
- **Tarea 9:** `concurrency` en el deploy de la CI (con el equipo).

### Aviso sobre PRE

- Es un solo entorno compartido. Un push a `feature/pre_gadea` despliega a PRE (CI: Lint + Tests +
  Deploy). El owner avisa al equipo.
- **No encadenar pushes**: espera a que termine la CI anterior (`gh run watch`), porque dos
  despliegues seguidos chocan con "container name already in use".
- No leer `/opt/diving-planet-bot/.env.pre`, no tocar `pre-launch-checklist.csv` y no pagar
  LangSmith.
