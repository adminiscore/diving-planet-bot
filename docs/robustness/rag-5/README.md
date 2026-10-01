# rag-5 — por qué se tira la respuesta adelantada (30-sep, Gonzalo)

**Pregunta de partida** (paso 1 del "Siguiente" del handoff del 30-sep): en la ronda core `rag5-B` la respuesta
adelantada se **aprovechó en 12 turnos y se rehízo en otros 12**, y no se sabía por qué. Hipótesis de Gadea: las
notas de ESTE mensaje se calculan después de lanzar el adelantado y cambian el resumen.

**Respuesta corta:** la hipótesis es **correcta en la causa y le falta la mitad importante**. Son las notas, sí —
pero no por *cuándo* llegan, sino por *lo que dicen*. Y lo que dicen son, en buena parte, **preguntas e hipótesis
del cliente apuntadas como si fueran hechos**, y algún hecho directamente inventado. Eso ya no es un problema de
latencia: es un **fallo de calidad del extractor de notas**, de la misma familia que u3-4 y u3-5.

Instrumento: `scripts/rag5_por_que_se_rehace.py` — local, sin desplegar, casi gratis. Mismo montaje que
`replay_golden_local` (extracción y Jev de verdad; RAG y acuse con respuesta fija) sobre los 95 diálogos del golden
sin el examen oculto, con los interruptores de rag-5 como en PRE. Cada vez que se rehace, compara el resumen
**antes y después** y guarda qué cambió.

---

## 1. La réplica local reproduce PRE

Con notas reales, en local se rehace el **41 %** de los turnos que llegan a usar el adelantado. En PRE (`rag5-B`)
fue el **50 %**. Mismo orden de magnitud: la réplica es fiel y los experimentos de abajo valen.

## 2. Experimento de control: ¿el momento o el contenido?

Tres pasadas idénticas salvo las notas:

| notas | tardan | se aprovecha |
|---|---|---|
| vacías | nada | **99 %** |
| vacías | 1,2 s (≈ una llamada real) | **99 %** |
| **reales** | lo que tarden | **59-61 %** |

- Con las notas **vacías**, da igual que tarden: se aprovecha casi siempre. La espera **no** deja a la extracción
  cambiar el resumen entre las dos huellas (esa era mi hipótesis alternativa, y los datos la descartan).
- Con las notas **reales**, el aprovechamiento cae a ~60 %.

→ **La causa es el CONTENIDO de las notas, no su momento.** Gadea tenía razón en la causa.

## 3. Lo que dicen esas notas

De los 47 turnos rehechos (pasada final; la anterior dio 48 y 27, se repite), en **26 lo único que cambia del resumen
es el bloque de notas**, y en **los 26 entra una nota nueva** (ninguno es la misma nota reformulada o reordenada). Pero mira cuáles:

| el cliente escribe | el bot apunta como HECHO del cliente | qué es en realidad |
|---|---|---|
| "how much would that be" | **"customer is not Colombian"** | **inventado**: el mensaje no dice nada de nacionalidad |
| "y si somos un grupo grande, bajan el precio?" | "consideran grupo grande para descuentos" | una **hipótesis** (y es dato de reserva) |
| "Ustedes cotizan los hoteles san pedro y cocoliso?" | "Cotiza hoteles San Pedro y Cocoliso" | una **pregunta** |
| "entonces qué actividad me recomiendas para cada uno" | "hijo mayor puede hacer snorkel" | una **deducción del bot**, no algo que diga el cliente |
| "Uno de los buceos puede ser en wreck?" | "interés en buceo en wreck" | una pregunta (discutible) |
| "para residentes en colombia (3 años) no aplica…?" | "Residentes en Colombia por 3 años" | ✅ un hecho de verdad |

**El extractor incumple sus propias instrucciones.** Su prompt (`src/prompts/memory.py`) ya dice, literal:
*"never invent, never restate the booking slots, and never capture plain questions"*, que los datos de reserva
(*"activity, group size, location, dates, certification, nationality"*) NO son notas, y *"Call capture_notes with
ONLY what the message actually states"*. Y aun así apunta nacionalidad inventada, tamaño de grupo y actividad, a
partir de preguntas.

### Los 26 casos, leídos uno a uno (pasada completa, `por-que-se-rehace-notas-reales.json`)

Contra las reglas del propio extractor — apuntar solo "hechos abiertos" (salud, accesibilidad, ocasiones, límites de
agenda o presupuesto), nunca preguntas, nunca datos de reserva, nunca inventar:

| veredicto | casos | ejemplos literales |
|---|---|---|
| ✅ nota buena, la que debería apuntar | **7** | "acompañante no habla inglés ni español, será intérprete" · "presupuesto limitado" · "tiene cuenta local" · "no tiene claro si volverá este año" |
| ⚠️ hecho real, pero es **dato de reserva** (prohibido como nota) | **4** | "Clientes de Bogotá" · "pensando en ir en unos meses" · "quiere comprar sin ir a Cartagena" |
| ❌ **la pregunta misma** apuntada como nota, o inventada | **15** | "not Colombian" · "pregunta sobre el almuerzo incluido" · "Inquiring about discount code" · "customer inquired about a photographer" · "course duration is 2 full days" · "Cotizan hoteles San Pedro y Cocoliso" |

**Solo 7 de 26 (27 %) son el tipo de nota que el extractor debe apuntar. 19 de 26 (73 %) incumplen sus propias
instrucciones**, y 15 son basura sin discusión: el modelo registra *que el cliente preguntó algo* como si fuera un
hecho del cliente. Hay además un duplicado casi literal que el `if n not in existing` (comparación exacta de texto)
deja pasar: "He needs information about the dive center." y "Needs information about the dive center.".

### Los otros 21 rehechos: las notas cambian en TODOS

En los 21 casos donde cambia algo más que el bloque de notas, **las notas también cambian**. O sea, **las notas
cambian en los 47 de 47 rehechos**. Lo que cambia además es legítimo y hace que **rehacer sea lo correcto**:

| frase que aparece en el mismo turno | veces | ¿rehacer es correcto? |
|---|---|---|
| "El cliente marcó que es buzo certificado" | 5 | sí: la respuesta tiene que saberlo |
| el origen ("ya en las islas" / "sale desde Cartagena") | 3 | sí: con `RAG_BUSQUEDA_ORIGEN`, cambia la búsqueda |
| "Paso actual del flujo guiado: …" | 8 | dudoso: es un marcador del flujo, casi nunca cambia la respuesta |
| varios días, regla del refresher… | 4 | sí |

### Proyección, con base en esos números

Si el extractor dejara de apuntar las 19 notas que incumplen sus reglas, esos rehechos pasarían a aprovechados:
**de 69 a ~88 de 116, del 59 % a ~76 %**. Y los rehechos que quedarían serían **los correctos** — las 7 notas
buenas y los 21 turnos donde el cliente acaba de dar un dato que la respuesta necesita.

(Es una proyección sobre la réplica local, no una medida de PRE: en PRE el denominador incluye los primeros mensajes
y los turnos descartados, que este cambio no toca.)

### Por qué importa más allá de la latencia

1. **Calidad.** Esas notas entran en el contexto del RAG con la orden *"tenlos en cuenta, no los ignores"*. Un
   "customer is not Colombian" inventado puede hacer que el bot cotice en dólares a un colombiano.
2. **El asesor.** Las mismas notas van a la nota de lead que lee el equipo.
3. **Se pierden datos buenos.** La lista tiene tope de 8 (`supervisor._MAX_REMEMBERED_NOTES`): cada nota basura
   que entra empuja fuera la más antigua, que puede ser una alergia contada al principio.

## 4. Qué NO funcionaría, y por qué

**Ajustar el prompt del extractor.** Ya dice exactamente lo correcto y el modelo lo incumple. Y es la **cuarta**
vez que el proyecto se encuentra con esto: tres matices de prompt salieron negativos con medida (relleno 24-sep,
verificación 25-sep, RAG 29-sep — ver `docs/robustness/rag-3/README.md`).

**"Lanzar el adelantado cuando estén las notas"** (la propuesta del handoff). Se aprovecharía casi siempre, pero
empezaría ~0,8 s más tarde, y la ganancia entera de rag-5 era de 1,2 s. Y dejaría intacto el problema de calidad.

## 5. Propuesta: que Jev decida si hay algo que apuntar

El patrón que **sí funcionó** en este proyecto: una pregunta cerrada a Jev en la llamada del router que ya se hace,
a coste 0 de peticiones (u3-4, "¿el cliente AFIRMA esto o solo lo pregunta?"). El equipo ya la amplió en u3-5: hoy
Jev contesta en cada turno si el cliente **afirma** su nacionalidad, certificación, grupo, actividad y ubicación.
Para el mensaje "how much would that be", Jev da `affirms_nationality = 0,02`: habría cazado la nota inventada.

La idea: **solo capturar notas cuando el mensaje cuenta algo del cliente**, no cuando solo pregunta. Con una
pregunta más a Jev ("¿el mensaje cuenta un hecho nuevo sobre el cliente —salud, accesibilidad, ocasión, límites—,
o solo pregunta?"), o reutilizando las que ya hay.

Si funciona, es triple ganancia: **calidad** (menos hechos inventados en el contexto y en el lead), **latencia**
(los turnos de pregunta dejan de cambiar el resumen, y el adelantado se aprovecha más) y **coste** (se ahorra la
llamada de notas en los turnos que solo preguntan).

**Cómo validarlo antes de promocionar nada**, en este orden:
1. Calibrar la pregunta de Jev contra los casos reales de la tabla de arriba y de la pasada completa (banco estilo
   `scripts/sonda_afirma_vs_pregunta.py`, 10 s): tiene que dejar pasar el "residentes en Colombia por 3 años" y
   las lesiones/ocasiones de verdad, y parar las preguntas. **Lección de v4 (25-sep): calibrar ANTES de medir.**
2. Esta misma réplica local con la puerta puesta: el aprovechamiento tiene que subir y las notas buenas no pueden
   desaparecer.
3. Ronda core A/B en PRE, leída por caso.

---

## Errores de método que cometí, para que no se repitan

1. **Primera pasada con `NOTES_IN_PARALLEL=false`** (lo copié de la réplica de u3-4). Así las notas se calculan al
   principio del turno, ANTES de lanzar el adelantado, y el problema desaparece — no porque no exista, sino porque
   no se reproducía. Salió "99 % aprovechado" y era falso. En PRE está a `true`.
2. **Clasificar lo que cambió por palabras clave.** El bloque de notas es una sola "frase" para un separador de
   frases (lista con guiones, sin puntos), así que salía etiquetado como "grupo", "paso", "origen"… por las
   palabras que llevaban DENTRO las notas. Casi todo era el bloque de notas. Se corrigió leyendo el bloque entero.
3. **Una pasada se arrastró 4 horas** por errores de conexión con OpenAI desde mi máquina (en PRE, en el mismo
   rato, 0 errores): el script no tenía tope de tiempo. Ahora se lanza con `timeout 1800`.

---

## 6. La puerta de Jev para las notas, medida (1-oct, Gadea con Claude)

Flag `NOTAS_PUERTA_JEV` (`jev_router.SHARES_OPEN_FACT`): en la llamada a Jev que ya hace el enrutador (coste 0) va
"¿cuenta algo del cliente que haya que apuntar?", con la definición del propio extractor (salud, alergias,
accesibilidad, ocasiones, idioma, límites de presupuesto o agenda). Si Jev está SEGURO de que no (p < 0,2), no se
llama al extractor. El prompt del extractor no se toca.

**Calibrada antes de medir** (`scripts/sonda_notas.py`, N=2, conservador; sin el examen oculto): positivos perdidos
0/17 de diseño y **0/7 ciegos** (casos reales que no se usaron para redactarla); negativos parados 43/44. Decisión de
Gadea: "residentes en Colombia (3 años)" se queda parado (0,11): la residencia es un dato de reserva.

**Réplica local, mismas condiciones, las dos pasadas a la vez** (`NOTAS_REALES=1`, `SUFIJO=-sin-puerta` /
`-con-puerta`; 95 diálogos, 116 turnos que llegan a usar la respuesta adelantada en las dos):

| | sin puerta | con puerta |
|---|---|---|
| respuesta adelantada **aprovechada** | 70 (60 %) | **107 (92 %)** |
| rehecha | 46 | 9 (paso de la conversación, origen, grupo, certificación: los correctos) |
| llamadas al extractor de notas | 289 | **37** (−87 %) |
| mensajes con alguna nota | 127 | 32 |

**¿Se come notas buenas?** Leídas a mano las 96 que entraban sin puerta y ya no: ninguna de salud, ocasión ni
límite. Son datos de reserva ("no soy colombiano", "somos 4", "desde cartagena"), la pregunta apuntada como hecho
("incluye el almuerzo?" → "pregunta sobre el almuerzo incluido") o inventadas ("how much would that be" → "not
Colombian"). Único dudoso: "will have two large hiking backpacks" (equipaje). Las buenas siguen entrando: intérprete,
cuenta local, presupuesto, vuelo esa misma noche, "no tiene claro si volverá", edades de los niños.

**Lo que queda:** en respuestas cortas siguen entrando datos de reserva ciertos ("soy certificado, voy solo",
"residente", "todos extranjeros"): no son inventos y no hacen rehacer casi nunca, pero no deberían ser notas. No se
toca ahora (sería ajustar el umbral contra estos mismos casos).

Ficheros: `por-que-se-rehace-notas-reales-{sin,con}-puerta.json` y `…-notas-capturadas.json` (cada llamada al
extractor). ⚠️ Aviso de método: una pasada parada con `TaskStop` siguió viva y escribió su resumen en el mismo log;
los ficheros de resultados se comprobaron (116 turnos y número de llamadas de cada pasada buena).

Siguiente: ronda core B en PRE (calidad leída por caso y latencia), con los pasos 2 y 3 del bloque de Gadea si se
hacen antes.
