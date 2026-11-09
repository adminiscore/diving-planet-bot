# Memoria del equipo

Se lee al empezar cada sesión, también tras una compactación. Es la foto completa: de aquí se parte, no del relevo.
**Tope: 2 páginas.** Cada sección tiene dueño y tope; lo que no cabe va a su documento y aquí queda el enlace.
Borrador del Claude de Álvaro, 9-nov-2026, a partir del Plan Gadea («Por qué nos cuesta tanto el bot: análisis por fases»).
**Pendiente de revisión de Gadea.**

## 1. El plan y el bloque en curso · dueña: Gadea · tope 15 líneas

- **Diagnóstico.** Los graves no vienen de la búsqueda (0 de 67) ni del modelo (el escritor, 6-8 de 67). Vienen de cuatro cosas:
  decisiones sin un dueño en el código (el plan, en ~12 sitios; el pase, en 17), código que estropea respuestas correctas, una
  lectura que cambia entre vueltas (Haiku), y una vara que no se parece a los clientes reales.
- **Bloques, en orden:** 0 la vara · 0,5 lo ya escrito · 2a plan e importe, lo determinista · 1 lo que recibe el escritor · 2b plan,
  importe y moneda que dependen de leer · 4 el momento de reservar y el pase · 3 horas y fechas · 5 reglas que faltan.
- **En curso:** el 0 y el 0,5 a la vez; el 2a avanza con bancos sin saldo. Nada sube a PRE hasta cerrar el bloque.
- **Cierre del 0,5:** la tercera pregunta y el grupo a cero en su tanda y en el panel, y el saldo de código del bloque negativo.
- **Metas:** al acabar el plan, 5 o menos clientes con grave de 40, de media. La de 2 en 60 queda por debajo del ruido del juez.
- **Punto de parada:** tras el 0,5 y el 2a, el panel debería quedar en 8 a 11 por vuelta (hoy, 21 a 25). Si no baja de 16, se para y
  se revisa el rumbo.

## 2. Normas · dueña: Gadea · tope 15 líneas

1. **Mecanismo, no caso.** Nada de piezas por un grave suelto: ni señales de Jev, ni reglas del extractor, ni frases de prompt, ni
   regex. Un grave nuevo se apunta en su familia y espera a su bloque.
2. **Ficha por cambio**, en el commit y en el resultado de Coral: bloque · mecanismo · familia · líneas que borra en src · banco sin
   IA · contador. Si un cambio no puede rellenarla, es un parche y no entra.
3. **Lo que entra borra código:** el saldo de cada bloque en src, negativo.
4. **Un dueño por decisión.** Plan, importe, moneda, enlace, pregunta, pase, horas y fechas los decide el código antes de escribir. El
   código pinta cifras, enlaces y la pregunta; el escritor redacta alrededor.
5. **Leer, decidir y escribir**, por ese orden: el escritor trabaja con lo leído en este turno.
6. **Primero cubre, luego borra, y contando:** un corrector se borra cuando lleva un panel y una tanda sin actuar.
7. **La vara no se mueve durante una comparación:** referencia del juez congelada y con su huella; una regla nueva entra a la vez en el
   juez y en el código.
8. **El panel, solo al cerrar un bloque:** 3 tiradas por lado, cada una juzgada dos veces. Una bajada cuenta si es de 4 o más clientes de
   media. Las piezas se prueban con bancos sin IA.
9. **Regla de parada:** si dos medidas seguidas no mueven el mecanismo, se para y se escribe «qué estamos haciendo mal» antes de tocar
   nada más.
10. **Respuestas breves** (unos 120 caracteres, pocas preguntas), en español e inglés, en singular y para grupos.
11. **PRE:** una medida a la vez, avisando en Coral.

## 3. Decisiones vigentes · dueña: Gadea · tope 20 líneas

- **6-nov:** las tablas de CALN-43 (P1-P11), en `docs/robustness/caln/tablas-decisiones.md`. Una semana sin piezas nuevas por caso (#3664).
- **8-nov:** cuando el plan esté cerrado, se trabaja en conjunto y se reparte entre los tres.
- **9-nov, negocio:**
  - Un grupo mixto sin cédula paga todo en USD.
  - El bot no da totales.
  - El cierre de las 4:30 es firme: se ofrece el primer día que se reserva.
  - «Next Friday» dicho un jueves es mañana.
  - A quien ya reservó le contesta la base; cambiar o cancelar va con un asesor.
  - Respuestas breves.
  - Las agencias, como cualquier cliente.
  - De lo que la base no contesta, el clima del día y una recogida fuera de los puntos de siempre van con una persona; lo demás lo
    contesta la base.
- **9-nov, plan:** meta intermedia de 5 o menos de 40. La referencia del juez con las decisiones del 9-nov está en c7c7268a (local de
  Gadea).
- **Pendientes de decidir:** la línea base (2 vueltas); pedir a Andrés más conversaciones reales; la norma de 5 de 5 en los clientes «a
  veces»; leer el vuelo con el lector de notas; quitar la segunda lectura de la nacionalidad (CALN-30, Gonzalo).

## 4. Quién lleva qué · cada uno su línea · tope 2 líneas por persona

- **Gadea:** el plan y la vara (bloque 0); la referencia del juez. *(Por confirmar.)*
- **Álvaro:** el bloque 0,5, integrado en `feature/bloque05-alvaro` 2e77937a (el pase de Gonzalo, qué preguntar sin el paso 4, con el tono
  sin «cerrar con una pregunta» y el contador `escritor_pregunta`, y P9/P10 con `pasar_a_persona`). Suite 3597; src −13 netas frente a
  5ee94c7b. Falta medirlo con saldo. La memoria, hecha: falta que `feature/memoria-equipo-alvaro` entre en `feature/caln34-gadea`.
- **Gonzalo:** 0,5, el pase en una función (`feature/pase-gonzalo` 5ff32b8b).
- **Bloqueo:** OpenRouter, sin saldo desde el 6-nov a las 10:48. Sin él no corren las tandas ni el panel; los bancos de código, sí.

## 5. Lecciones: lo que no funcionó · cualquiera añade · tope 12 líneas, una por lección

- Del 21-oct al 6-nov hubo 60 versiones: los bancos subían y los clientes nuevos no. Arreglar el caso visto no arregla la familia.
- Medir una pieza con el panel: el ruido (±3-4 clientes) tapa su efecto. Para la pieza, un banco sin IA.
- Probar una sola vez algo que sale a veces engaña: s04i-belgas pasaba 2 y 3 de 5.
- Arreglar un camino y no la decisión: el freno de la tercera pregunta tenía una excepción y no veía todas las preguntas.
- Quitar un corrector antes de cubrir su caso (el paso 4 de qué preguntar, 6-nov).
- El panel no se parece a los reales: infla el grupo y la tercera pregunta. Un tercio de los reales ya ha reservado.
- Atribuir a una persona lo que dijo su Claude. Hay que decir «el Claude de X».

## 6. Marcador · la tabla entera, en `docs/plan/marcador.md` · aquí, la última línea

| Fecha | Versión | Bloque | Graves por vuelta | Líneas de src | Llamadas de IA por turno | Respuesta: caracteres · con pregunta |
|---|---|---|---|---|---|---|
| 6-nov | PRE 0.61 | antes del plan | 21, 25 y 21 (referencia del 6-nov) | 27.145 | ~4,1 | 703 · 77 % |


