# CALN-23 · Que el escritor redacte con la extracción ya hecha — estudio (4-nov, Gonzalo)

**Recomendación: no cambiar el orden del turno por ahora.** Esperar a la extracción no cuesta latencia, pero con este
prototipo las respuestas no mejoran: ninguno de los defectos desaparece y algunos salen más. Decide Gadea.

Hecho aparte, que sí parece aprovechable: la respuesta adelantada (rag-5) se tira y se rehace casi siempre. Ver «Qué
miraría después».

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

## Qué miraría después, si Gadea quiere

1. **Quitar la respuesta adelantada o afinarla.** Se rehace 34 de 47 veces. El dato de arriba dice que sin ella no se pierde
   latencia y se ahorra alguna llamada; pero se midió junto al resto del prototipo. Es lo más barato de probar por separado:
   sin rag-5, con la pregunta como hoy.
2. **B con la misma pregunta que A** (solo con pregunta pendiente): una pasada igual dice si el empeoramiento era del prototipo.
3. **Los duplicados, por su sitio:** que la tarjeta y el escritor sepan qué dice el otro. Es otra tarea.

Los puntos 1 y 2 se miden a la vez, con unos 20 minutos de PRE a solas, después de la 0.52b. Tocan `conversational_core.py`:
hay que coordinarlo con CALN-8 (5) de Álvaro.

## Medidas que no cuentan

Una primera pasada de este banco se lanzó por error a las 21:01 con un script que seguía vivo, y se descartó.

## Corrección a la tanda S04K

Los alemanes de S04K, medio: dije que no encontraba en la base el Nitrox para buzos certificados. Sí está (FAQ 102: bajo pedido,
10 USD por tanque). Lo dudoso era mi comprobación, no el bot; el único pero es que no dio el precio.
