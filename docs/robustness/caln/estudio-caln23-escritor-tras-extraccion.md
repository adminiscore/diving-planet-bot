# CALN-23 · Que el escritor redacte con la extracción ya hecha — estudio (4-nov, Gonzalo)

**Resultado tras dos vueltas: el orden no cambia nada a favor, y recomiendo cerrar CALN-23 sin integrarlo.** Esperar a la extracción
no cuesta latencia y ahorra un 7-8 % de llamadas y coste, pero las respuestas no mejoran y tienden a empeorar un poco. Decide Gadea.

## Vuelta 2 (decisión de Gadea, #3292): la pregunta final como hoy

Mismo cambio, sin tocar la pregunta (`fijar_pregunta_del_escritor`, solo con una pendiente), sobre la 0.52.0 (6595abed, rama
`feature/caln23-v2-gonzalo` be931d72). Mismo banco, 8 pasadas intercaladas, 96 turnos por lado y 56 puntuables. A solas en PRE, salvo un minuto
de medida de Gadea al empezar.

| | A, hoy | B, tras la extracción |
|---|---:|---:|
| p50 | 4,85 s | 4,82 s |
| p90 | 6,91 s | 6,83 s |
| p95 | 7,25 s | 7,01 s |
| Máximo | 9,5 s | 8,4 s |
| Turnos de más de 7 s | 7 | 5 |
| Llamadas por turno | 4,96 | 4,56 |
| Coste por turno (milésimas de $) | 1,05 | 0,98 |
| Búsquedas (embeddings) | 351 | 193 |
| Llamadas al escritor | 114 | 103 |
| Recorta el compositor (de 96) | 36 | 34 |
| Adelantada rehecha / aprovechada | 39 / 10 | — |

**A ciegas, 28 pares:** A mejor en 8, B mejor en 5, empate en 15. Respaldos: A, 1 del lector y 3 de otras piezas; B, 2 del lector. Ninguno del extractor.

**Por código, los 56 turnos puntuables:**

| Defecto | A | B |
|---|---:|---:|
| Menú genérico | 13 | 15 |
| «¿Para cuántas personas?» | 1 | 4 |
| Pago explicado dos veces | 3 | 7 |
| Mismo enlace dos veces | 4 | 4 |
| Lista vacía | 0 | 0 |

Quitar la pregunta del prototipo arregla lo peor de la vuelta 1 (menú 24 → 15, compositor 80 → 34): aquello era del prototipo. Lo que queda:

- **Calidad, juntando las dos vueltas:** A mejor en 15 pares, B en 10, empate en 31. No es significativo, pero en ninguna vuelta gana B.
- **Dos defectos suben en las dos vueltas:** el pago dos veces (4 → 7 y 3 → 7) y «¿para cuántas personas?» (1 → 8 y 1 → 4). Lo del pago tiene sentido: con la
  nacionalidad ya guardada, el escritor explica el pago y la tarjeta también. Es una hipótesis, sin demostrar.
- **Ningún defecto de la lista original desaparece.**
- **Latencia:** iguales. Las diferencias son pequeñas y no las doy por reales.

**Para el pago con un solo dueño:** esperar a la extracción no lo arregla, sino que lo repite más. Hay que decírselo al escritor de otra forma.

**Lo que sí queda como dato:** la respuesta adelantada se rehace 39 de 49 veces (34 de 47 en la vuelta 1) y sin ella la latencia no sube. Pero aquí se quitó junto con
el resto: quitarla sola, dejando el escritor en paralelo a la extracción, no se ha medido y es otra prueba.

# Vuelta 1 (solo lo que sigue valiendo)

## Qué se comparó

- **A, hoy:** el escritor arranca a la vez que el enrutador, y al recoger la respuesta se comprueba si el contexto cambió
  (rag-5). La pregunta final se fija al empezar el turno.
- **B, prototipo:** sin respuesta adelantada. El escritor arranca al recoger la respuesta, con la extracción de este mensaje
  ya guardada, y su pregunta final es la que toca después de esa extracción (`next_missing_slot`).

Mismo código (`feature/caln23-gonzalo`, 163525a8, sobre la 0.51.1 44b1aa54), con el interruptor `CALN23_TRAS_EXTRACCION`
solo en B. Apagado, la suite pasa entera (3314). Encendido fallan 7 tests y 1 se queda esperando; los 8 comprueban la carrera
de hoy. El prototipo no es para integrar.

Banco `banco-caln23.json`: 14 casos de las tandas 11.ª y 12.ª (S04D, S04E) y los jubilados t2, con sus mensajes tal cual. El
plan habla de «11 de 21» sin enumerarlos: los 14 son mi lectura. 8 pasadas intercaladas (A B B A A B B A) contra PRE, 4 por
lado, 96 turnos por lado, 56 de ellos puntuables (último turno de cada caso).

## Latencia y coste

| | A, hoy | B, tras la extracción |
|---|---:|---:|
| p50 | 5,18 s | 4,99 s |
| p90 | 6,74 s | 6,29 s |
| p95 | 7,01 s | 6,83 s |
| Máximo | 7,3 s | 8,5 s |
| Turnos de más de 7 s | 5 | 4 |
| Llamadas por turno | 4,89 | 4,56 |
| Coste por turno (milésimas de $) | 0,97 | 0,95 |
| Llamadas al escritor | 117 | 101 |
| Respaldos del extractor | 2 | 0 |
| Respaldos del escritor | 1 | 3 |

B no es más lento porque A ya esperaba casi siempre: de las 47 respuestas adelantadas que llegaron a usarse o a tirarse, **34
se rehicieron** porque el contexto cambió y 13 se aprovecharon. La diferencia a favor de B es pequeña y con 96 turnos no la doy
por real: lo que este dato sostiene es que B no es más lento, no que sea más rápido.

Todos los turnos del banco contestan una pregunta con el RAG. Los turnos sin pregunta no pasan por aquí.

## Calidad

**A ciegas, 28 pares** (14 casos × las 2 primeras repeticiones), con el lado barajado y la valoración fijada antes de abrir la
clave: **A mejor en 7, B mejor en 5, empate en 16.** Ningún caso gana B en las dos repeticiones; A gana en las dos en Guadalajara
t1 y Múnich t1 (salen listas vacías en B: «your options are.», «can choose:» seguido de otra frase).

**Por código, los 56 turnos puntuables:**

| Defecto | A | B |
|---|---:|---:|
| Menú genérico («¿te animas?», «¿con cuál?») | 12 | 24 |
| «¿Para cuántas personas?» | 1 | 8 |
| Pago explicado dos veces | 4 | 7 |
| Mismo enlace dos veces | 4 | 4 |
| Lista vacía | 1 | 2 |

Por traza, en todo el banco: el compositor recorta en 33 turnos de A y en 80 de B, y `[LAT9]` cambia la pregunta en 16 y 32.
Era lo contrario de lo que se buscaba.

- **Defectos de la lista original:** ninguno desaparece en B. «¿Con cuál te animas?» a quien se despide (la tarde t2) sale en
  los dos lados, y también el enlace dos veces (Canadá t2) y el pago dos veces (niño de 7 t3).
- **La carrera de los jubilados t2 ya no sale en ninguno de los dos**, en las 2 repeticiones leídas: la arregló la puerta al recoger (s04c).

**Por qué B sale peor, sin demostrar:** le doy al escritor la pregunta de `next_missing_slot` en cualquier turno, y A solo si ya
había una pregunta pendiente (`fijar_pregunta_del_escritor`). Encaja con el menú y «¿para cuántas personas?» de más. Es decir,
parte del empeoramiento puede ser del prototipo y no de la idea. No lo he medido por separado.

**Lo que la idea no podía arreglar:** muchos defectos no vienen del orden, sino de que el escritor y las piezas del código
escriben lo mismo sin saberlo (el pago en el texto y en la tarjeta, el enlace en los dos). Eso ocurre aunque el escritor tenga
la extracción hecha.

## Límites

- Lo he valorado yo solo, con 2 de las 4 repeticiones por caso. Los recuentos por código usan las 4, pero son búsquedas de texto.
- Banco pequeño, elegido por sus defectos y sin los turnos sin pregunta: no sirve para estimar calidad general, solo para comparar.
- Sin juez, sin mini y sin bancos de grupos o graves.
- Una sonda de Jev de Álvaro coincidió con el primer minuto de la primera pasada (hasta las 21:43). Al intercalar, no sesga.

## Medidas que no cuentan

Una primera pasada de este banco se lanzó por error a las 21:01 con un script que seguía vivo, y se descartó.

## Corrección a la tanda S04K

Los alemanes de S04K, medio: dije que no encontraba en la base el Nitrox para buzos certificados. Sí está (FAQ 102: bajo pedido,
10 USD por tanque). Lo dudoso era mi comprobación, no el bot; el único pero es que no dio el precio.
