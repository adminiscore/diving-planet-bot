# Análisis de situación (6-nov): por qué los graves no bajan

Lo pidió Álvaro (Coral #3658): «damos vueltas en círculo poniendo parches». Gadea lo aceptó (#3659): se para lo que sigue el método de
siempre y se escribe este análisis antes de seguir. **Borrador de Álvaro, sin tocar código. Gadea lo corrige con datos. Gadea y Álvaro
deciden.** Cada número dice de dónde sale.

## En una frase

El bot falla en 1 de cada 3 clientes nuevos desde hace semanas. Cada arreglo baja los fallos de los casos que ya conocemos y no cambia
los de los clientes nuevos. Las decisiones de negocio están repartidas entre muchas piezas y muchas lecturas de IA, y los errores se
suman. Así no se llega a la meta (2 de 60) arreglando piezas una a una.

## 1. Dónde estamos

| Qué | Valor | Fuente |
|---|---|---|
| Meta de CALN-22 | como mucho 2 clientes con grave de 60 (un 3 %) | CALN-22 |
| Tandas de sparring, las 4 últimas (0.58-0.61) | 5, 2, 2 y 5 de 10: **14 de 40, un 35 %** | `g3/hallazgos.md`, s06b |
| Panel fijo, ciegos (20 clientes de dos autores) | 0.58: 13-15; 0.59: 12, 11, 14; 0.60: 12, 12, 10, 12; 0.61: 13, 11, 13 | HISTORY 0.59-0.61 |
| Versiones del 21-oct al 6-nov | 60 (al menos 31 subieron a PRE); de la 0.48 a la 0.61, 14 en tres días | HISTORY |
| Líneas de `src` | 23.506 (6-oct) → 27.372 (20-oct) → 26.444 (0.53) → 27.145 (0.61) → 27.223 (candidata 0.62) | git; Gadea #3659 |

La tasa no baja. El panel empata versión tras versión: la 0.60 y la 0.61 subieron «por lo decidido, no por una mejora medida» (HISTORY 0.60).

## 2. (a) Qué decide cada pieza, y cuántas deciden lo mismo

Detalle en `inventario-decisiones.md` (PRE 0.59).

| Decisión | Cuántos sitios la deciden | ¿Un solo dueño? |
|---|---|---|
| Qué plan le toca | unos 12 sitios en 9 ficheros, más el escritor. CALN-24 arbitra cuando no coinciden. `plan_de_buceo` (6-nov) está encima: no quita ninguno (Gadea #3659) | no |
| Cómo reserva (enlace, asesor, hotel primero) | `como_reserva`: una función, 30 tests | **sí** |
| Qué preguntar | `next_missing_slot` (una tabla), pero `core_pending_slot` se escribe en 7 sitios. El escritor cierra con sus propias preguntas, y el compositor las borra después (mi P11 de hoy es otro filtro de ese tipo) | no |
| Pase al asesor | `pending_escalation_reason` se escribe en 14 sitios de 9 ficheros | no |
| Moneda | `is_colombian` se escribe en 6 sitios de 4 ficheros | a medias |
| Descuento | 6 ficheros | no |

**Lectura del cliente:** cada mensaje pasa por Jev, que contesta **51 preguntas de lectura y 13 de ruta** (`_U34_QUESTIONS`, `_QUESTIONS`),
y por el extractor, que lee hasta 20 campos (`extractor_turno`: 10 de base, el nombre, el hotel, el refresher y 7 del paso 6). Muchas de esas señales existen para tapar un caso concreto: el nocturno, las salidas
sueltas, el pase aceptado, «son días de buceo», la cédula, el grupo mixto, el que viaja solo…

## 3. (b) Cuántas decisiones de IA hay en una conversación, y cómo se suman sus errores

Panel 059c (PRE 0.59, 40 conversaciones, 157 turnos, `metricas` de cada turno):

| Pieza | Llamadas | En qué turnos |
|---|---|---|
| Jev | 157 | 100 % (51 + 13 preguntas por llamada) |
| Extractor | 218 | 100 % (a veces dos por turno) |
| Escritor (RAG) | 150 | 90 % |
| Lector de grupo | 75 | 45 % |
| Notas | 40 | 25 % |
| **Por conversación** | **17 de mediana (entre 6 y 26)** | |

**Estimación, no medida** (supone errores independientes): si cada llamada acierta el 97 %, una conversación de 17 llamadas sale sin
ningún error el 0,97¹⁷ ≈ 60 % de las veces. El 40 % restante está en el rango que medimos (35 % en tandas, más en el panel). Para la
meta (97 % de conversaciones limpias), cada llamada tendría que acertar el 99,8 %. Ninguna pieza de IA llega a eso. **Mejorando piezas
no se llega. Hay que quitar decisiones de la IA, o hacer que un error de lectura no se convierta en un grave.**

## 4. (c) Cómo comprobamos hoy si algo funciona, y cómo debería ser

**Lo que medimos y lo que dice:**
- **Los bancos (casos ya conocidos) siempre suben.** Ejemplos: 0.53, banco-053b 20/32 → 44/48, con la mini 20 → 19; 0.54, se-despide 15/30 →
  30/30, con la mini 20 → 20; 0.51, origen en hipótesis 60/66 → 66/66, con la mini 22 → 22; 0.55, hora de volar 22/30 → 29/30, con la mini
  21 → 21 (HISTORY).
- **Los clientes nuevos (la mini, el panel, las tandas) no se mueven** fuera del ruido.
- **El ruido es del bot, no del juez.** Mismo código, distintos resultados: la 0.45 dio 20 fallos a las 22:00 y 28 a las 23:45; la 0.59, 15, 19 y
  21 clientes con grave en el panel (HISTORY). El bot responde distinto cada vez, así que una pieza pequeña no se distingue con el panel.
- **El juez:** en los fallos en general, 1 de cada 3 es falso (HISTORY 0.55.1, al pasar a Opus). En los **graves leídos a mano** acierta
  casi siempre: los 16 de hoy (panel 059c y 6952) son reales; s05f, 2 de 2; s06a, 2 de 2; s06b, 5 sin leer. El juez anterior contaba de
  menos: s05a y s05c, 5 de 21 al rejuzgar, frente a los 2 de 20 que contamos (HISTORY 0.57). **Pendiente (Gadea, #3659):** contar en todos
  los bancos y tandas cuántos graves eran reales leyendo el texto.

**Cómo debería ser:**
- **Las decisiones (plan, enlace, qué preguntar, pase, moneda) se prueban con tablas de casos, sin IA.** No tienen ruido, cuestan cero y
  tardan segundos. Un cambio que rompe un caso se ve en el acto.
- **La lectura del cliente se prueba con un banco de frases:** frase → campos esperados, N grande, por campo. Ya existe `banco-lectura.json`.
- **El panel y las tandas, solo para confirmar al final de un bloque**, no para decidir cada pieza. Cuesta OpenAI y horas, y no distingue
  cambios pequeños.

## 5. (d) Qué hemos añadido y qué hemos quitado, y qué bajó de verdad

**Patrón de las últimas semanas:** sale un grave en una tanda, se añade una señal de Jev, una regla del extractor o una frase del prompt
para ese caso, su banco pasa, la mini empata, la versión sube, y la tanda siguiente encuentra otro grave de la misma familia con otra
cara. Gadea lo dijo así: «cada autor nuevo encuentra clases que no teníamos»; y la 0.61, «sin tablas, los graves salen con otra cara» (#3649).

**Lo poco que bajó algo en clientes nuevos, y qué tenía en común:**

| Cambio | Efecto | Qué era |
|---|---|---|
| 0.52, el freno de la 3.ª pregunta | la misma pregunta 3+ veces, 21 → 6 diálogos de 43 | una regla de código en un sitio |
| 0.56, `como_reserva` | fallos firmes de la mini 29 → 20 | **un solo dueño**, tabla de casos |
| 0.55, la hora de volar en la base | banco 22/30 → 29/30; aun así, vuelve con otra cara (visto-6942 en el panel 059c; 2 casos del banco en la 0.60c) | un dato en la base, no una señal |
| 0.59, lo decidido como datos en la base | 4 clientes mejoran estables en el panel, 1 empeora | datos, no código |

**Lo que no bajó nada medible** (empates): las señales nuevas de Jev para casos sueltos, las reglas por caso en el extractor y los filtros
del compositor que borran lo que escribió el escritor. Hoy hemos añadido tres más de esos: `plan_de_buceo` encima de los 12 sitios, mi
P11 (un filtro al final) y mi P9/P10 (otra salida en `como_reserva`, este sí con un solo dueño).

**Pendiente (Gadea):** la lista completa de la 0.40 a la 0.61, con qué añadió cada versión, qué quitó, y su efecto en el panel o la mini
frente al ruido.

## 6. (e) Borrador del plan: piezas que se quitan

Para discutir. No es una solución cerrada.

1. **Una semana sin piezas nuevas por caso.** Ni señales de Jev, ni reglas del extractor, ni frases de prompt para un grave suelto. Un grave
   nuevo se apunta en su familia y espera a la tabla de esa familia.
2. **El plan, con un solo dueño de verdad.** `plan_de_buceo` decide y los otros sitios se borran: la regla de texto de `rutas/booking`
   (6929 leyó «el de 5 no es lo que pedí» como 5), el plan que «acaba de describir el bot», el arbitraje de CALN-24 y lo que nombra el
   escritor. El escritor recibe el plan decidido y no puede dar otro. Se mide en líneas quitadas y en casos de la tabla.
3. **Qué preguntar, antes de escribir y no después.** La tabla decide la pregunta del turno, con memoria de lo ya preguntado, y el escritor no
   cierra con preguntas de la reserva. Así sobran los filtros del compositor que las borran (y mi P11).
4. **El pase, en una función.** Los 14 sitios que escriben `pending_escalation_reason` pasan por ella.
5. **Jev, con menos preguntas.** Cada señal que solo servía a una decisión que ya tiene tabla se quita. Gadea dice cuáles.
6. **Cómo se mide cada paso:** las tablas, con cientos de casos sin IA; las lecturas, con el banco de frases; el panel, una vez al final del
   bloque. **Señal de que va bien: el código encoge y los tests sin IA crecen.** Si una semana el código crece, volvemos a parchear.

## 7. Lo que tienen que decidir Gadea y Álvaro

1. ¿Este diagnóstico es correcto? Si no, ¿qué dato lo contradice?
2. ¿Se para una semana la entrada de piezas por caso (punto 6.1)?
3. ¿Por qué familia se empieza a quitar? Propongo el plan: 7 de los 16 graves de hoy son de plan o enlace, y ya tiene tabla.
4. ¿Qué hacemos con lo de hoy, que no se ha medido? `plan_de_buceo` (Gadea), P11 y P9/P10 (Álvaro): ¿se integran dentro del plan de
   quitar o se descartan?
