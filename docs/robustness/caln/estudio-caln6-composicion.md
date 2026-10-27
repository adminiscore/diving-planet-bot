# CALN-6 · Un solo sitio que compone la respuesta — estudio (27-oct)

Para Gadea y el equipo, antes de tocar código. Fase CALN: calidad en conversaciones nuevas y difíciles, sin perder la
arquitectura delgada y sin parches. Gadea (27-oct): «a estudiar».

## 1. Qué pasa hoy

La respuesta de un turno no se compone en un sitio: **se escribe en unos 26 sitios de 7 ficheros** (las salidas
tempranas que devuelven ya la respuesta: extracción 7, supervisor 5, enrutado 5, cierre 4, disponibilidad 2, cambios y
reserva 1 cada uno) y **se le pegan trozos en unos 27 puntos** (la pregunta de la reserva, el acuse, los avisos, la nota
de seguridad, la moneda, las listas que se le escapan al escritor, la tarjeta, el grupo mixto, el pase a un asesor).
Cada sitio no sabe qué ha dicho el otro: el escritor ya explicó X y el código pega X otra vez, o pega su pregunta fija
detrás de la del escritor.

**Lo que se ve en la ronda caln1-B** (465 turnos; comprobación por código, sin juez):

| Qué | caln1-B | integra6b | integra5 |
|---|---|---|---|
| Dice lo mismo dos veces (la misma pregunta pegada dos veces: el menú de actividades, «¿Ha pasado más de 2 años…?», la petición de nacionalidad; o la misma nota con otras palabras) | 16 | 23 | 24 |
| Dos o más preguntas en una respuesta | 17 | 20 | 18 |
| El menú genérico de 4 actividades | 84 (18 %) | 82 | 77 |

**Lo que se ve en el sparring** (hallazgos CALN1-04 y CALN2-01..05): el bloque entero de descuentos pegado después de
explicar el de grupo; el descuento de grupo dos veces seguidas; la regla del grupo mixto dos veces y «¿…o prefieres
volver al menú principal?»; un camino viejo de edades que se come el turno (solo los niños, sin saludo, con un relleno
robótico); el menú genérico pegado detrás de un plan persona a persona; la frase del escritor cortada por el tope de
tokens (esto ya está arreglado: 71b23b1).

Las 5 repreguntas de CALN-0 en la ronda son también de aquí: el menú «¿Con cuál te animas?» pegado tras una pregunta de
información, en una posventa o cuando el cliente pide para otro. Arreglarlas una a una serían parches.

## 2. Propuesta y otras formas de hacerlo

| Opción | A favor | En contra |
|---|---|---|
| **A. Un compositor al final del turno.** Cada sitio deja PIEZAS en el turno (lo que dice el escritor, la pregunta de la reserva, los avisos, las notas, la tarjeta, el pase) y una sola función las junta en un orden fijo, sin repetir lo que ya va y con UNA pregunta como mucho | Un sitio decide qué se dice; fuera las repeticiones y las dobles preguntas por construcción; las salidas tempranas dejan de escribir respuestas; comprobable por código | Toca todos los caminos del turno: hay que hacerlo por pasos medidos; choca con partir los módulos (Álvaro, aparcado) |
| B. Dejar los sitios y quitar lo repetido al final (un «deduplicador») | Pequeño | No quita la causa: un parche más grande; no sabe cuál de las dos versiones es la buena |
| C. Que el escritor componga todo (el código le pasa las piezas como hechos y solo añade la tarjeta y los enlaces) | Menos código | Más dependencia del modelo (inventos, latencia); va contra «el código decide» |
| D. Arreglar caso a caso | Cada arreglo es pequeño | Es lo que hemos hecho: 26 sitios y sigue pasando |

**Propuesta: A, por pasos**, cada uno con su comprobación por código y la suite:

| Paso | Qué | Cómo se mide |
|---|---|---|
| 0 | Comprobación por código de la composición (dice lo mismo dos veces, 2+ preguntas, menú genérico tras un plan o en posventa, frase cortada) en `caln0_comprobaciones` y un banco de ~20 turnos sacados del sparring | — |
| 1 | La pregunta de la reserva la pone SOLO el compositor (hoy, en varios sitios y a veces dos veces) | Comprobación + banco ×2 |
| 2 | Avisos, notas y listas del código, como piezas: el compositor no pega lo que el escritor ya dijo | Comprobación + banco ×2 |
| 3 | Las salidas tempranas devuelven piezas, no respuestas | Suite + comprobación; ronda completa al integrar |

## 3. Riesgos

- Es transversal: toca extracción, enrutado, cierre, supervisor e info. Por eso va por pasos y con la comprobación por
  código antes y después de cada uno.
- La partición de los módulos grandes (Álvaro, aparcada) se hace mejor después: este cambio reordena justo ese código.

## 4. Decisión de Gadea (27-oct)

**APROBADA la opción A** (un compositor al final del turno), por pasos medidos por código. Gadea preguntó cuál
de las cuatro era mejor y eligió A: la única que quita la causa y deja menos código. Se empieza por el paso 0.
