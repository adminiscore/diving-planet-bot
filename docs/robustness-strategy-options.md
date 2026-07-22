# Opciones para mejorar la robustez conversacional del bot

Estado: **decidida (2026-07-21)** — owner + Álvaro + Gonzalo acordaron empezar por la
**Opción 2**. Plan de implementación completo en `docs/robustness/` (empezar por
`docs/robustness/README.md`).

## Contexto

Sesión del 2026-07-21: se simularon 2 conversaciones reales contra PRE (LLM real, con
typos, ES/EN) y salieron 4 inconsistencias reales que perdían al cliente a mitad de
reserva (detalle completo en `docs/live-test-inconsistencies-plan.md`). Los 4 fixes se
implementaron con TDD y se re-confirmaron en vivo.

Durante ese mismo trabajo pasó algo revelador: al generalizar un interceptor (Fix 3,
de "aplica en 2-3 pasos concretos" a "aplica en cualquier paso donde estemos en una
reserva de buceo certificado"), esa misma generalización **introdujo una regresión
nueva** — el interceptor ampliado empezó a dispararse también en el paso donde
justamente preguntamos si el cliente está certificado, y silenciosamente asumía que sí.
Se cazó porque escribimos un test para el fix siguiente (Fix 4), no porque lo
buscáramos a propósito.

Este patrón no es nuevo — es el mismo que aparece en `docs/project-history/estado-pendientes.md`
(punto #10, ya anotado por Álvaro) y en el historial de versiones desde hace semanas:
mucha lógica vive en reglas deterministas dispersas (regex + listas de "en qué paso
aplica esto") por `supervisor.py`/`decision_tree.py`, y cada vez que ampliamos una regla
para tapar un bug, hay riesgo real de que esa ampliación choque con otra regla o con un
paso que significa algo distinto de lo que asumimos.

Comparado con bots de otras empresas que no muestran estos fallos, la sospecha es que
ellos dependen menos de reglas deterministas dispersas y más de una capa de comprensión
más centralizada (LLM con buen grounding, o un motor de estado más explícito).

## Las 4 opciones

### 1. Seguir parcheando incrementalmente (statu quo)

Lo que hacemos hoy: encontrar un bug real (en vivo o reportado), reproducirlo con TDD,
arreglarlo, desplegar, confirmar. Es el patrón de todo el historial de versiones hasta
ahora.

**Pros**
- Cero coste de arranque — ya es el flujo de trabajo establecido.
- Cada fix es pequeño, revisable y de bajo riesgo individual (TDD, suite completa antes de cada deploy).
- Funciona bien para bugs aislados y bien acotados.

**Contras**
- Rendimientos decrecientes: cuantas más reglas dispersas se acumulan, más superficie hay para que una interactúe mal con otra (pasó literalmente hoy).
- No ataca la causa raíz — solo el síntoma más reciente encontrado.
- Depende de que alguien encuentre el bug primero (manualmente, probando en vivo) — no hay red de seguridad sistemática.

### 2. Extracción semántica vía LLM (la "aspiración de fondo" de Álvaro, punto #10)

Sustituir buena parte de la extracción de información del mensaje (certificación,
cantidad, ubicación, cambios de plan, etc.) — hoy repartida en decenas de regex y
detectores especializados — por una capa de comprensión más general vía LLM, que
extraiga la información estructurada relevante de cada mensaje una sola vez, en vez de
tener un detector especializado por cada tipo de dato.

**Pros**
- Ataca la causa raíz: entiende variaciones de lenguaje natural (typos, frases nuevas, sinónimos) sin necesitar un patrón nuevo por cada forma de decir lo mismo.
- Reduce drásticamente el número de reglas dispersas a mantener.
- Es la clase de solución que probablemente usan los bots de la competencia que no muestran estos fallos.

**Contras**
- El LLM ya usado para el orquestador de acciones es conocidamente no-determinista (mismo mensaje, clasificación distinta en pasadas distintas) — habría que invertir en una batería de evals seria antes de confiar en él más que en el regex actual, para no cambiar "bugs deterministas reproducibles" por "bugs intermitentes difíciles de reproducir".
- Coste de desarrollo más alto: requiere diseño cuidadoso (qué extrae, cómo se combina con el árbol de decisión existente), no es un fix de una tarde.
- Migración gradual necesaria — no se puede reemplazar todo de golpe sin arriesgar una regresión masiva.

### 3. Hacer explícito el estado de "pregunta pendiente" (refactor acotado)

Hoy, "¿hay una pregunta sin responder?" se infiere implícitamente combinando
`state.step` con varios sets dispersos (`_PENDING_QUESTION_STEPS`,
`_CERT_FLOW_IN_PROGRESS_STEPS`, `_CERT_COMPANION_SPLIT_STEPS`, etc.), cada uno definido
en un sitio distinto y mantenido a mano. La opción es centralizar esto: un único
concepto explícito en `ConversationState` (p.ej. `pending_question: PendingQuestion | None`)
que cada handler consulta de la misma manera, en vez de que cada interceptor nuevo
tenga que acordarse de comprobar su propio set de pasos.

**Pros**
- Ataca exactamente la clase de bug que causó la regresión de hoy — un set ampliado que incluye sin querer un paso donde el contexto asumido todavía no es cierto.
- Alcance acotado (no es una reescritura completa) — se puede hacer de forma incremental, empezando por consolidar los sets ya existentes.
- Compatible con seguir usando regex/detectores deterministas donde ya funcionan bien — no es excluyente con la opción 2.

**Contras**
- Sigue siendo trabajo manual de reglas — no resuelve el problema de fondo de "un patrón nuevo de lenguaje natural no tiene regex que lo cubra".
- Requiere tocar código central (`decision_tree.py`/`supervisor.py`) con cuidado para no romper el comportamiento ya validado — necesita su propia ronda de TDD + regresión completa.

### 4. Batería de conversaciones reales automatizada (red de seguridad, no fix)

En vez de sesiones manuales puntuales como la de hoy, mantener un conjunto creciente de
conversaciones realistas (con typos, en ES/EN, cubriendo los flujos críticos) que se
ejecute automáticamente contra un entorno con LLM real después de cada deploy — parecido
a `scripts/live_battery_driver.py` pero como parte del pipeline, no ad-hoc.

**Pros**
- Barato de empezar — el driver y el patrón de conversaciones ya existen, solo falta automatizarlo y hacerlo crecer con cada bug real encontrado.
- Detecta regresiones ANTES de que las vea el owner o un cliente real, en vez de después.
- Compatible con cualquiera de las otras 3 opciones — es la red de seguridad, no la solución.

**Contras**
- No arregla nada por sí sola — solo avisa. Sigue haciendo falta alguien que interprete los resultados y decida qué arreglar.
- Con LLM real tiene un coste (tokens) y cierta variabilidad (el propio orquestador no es 100% determinista) — hay que diseñarla para tolerar eso sin generar ruido de falsos positivos.
- Requiere mantenimiento propio (la batería necesita crecer con cada bug nuevo encontrado, o se vuelve obsoleta).

## Recomendación

Empezar por **3 y 4** primero: coste bajo, atacan directamente cómo se coló el bug de
hoy, y son compatibles con seguir avanzando en **2** más adelante si el equipo decide
que vale la pena la inversión mayor. La sesión de hoy (documentada en
`docs/live-test-inconsistencies-plan.md`) puede servir de caso de prueba concreto para
esa decisión.
