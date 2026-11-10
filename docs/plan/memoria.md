# Memoria del equipo

Se lee al empezar cada sesión, también tras una compactación. Es la foto completa: de aquí se parte, no del relevo.
**Tope: 2 páginas.** Cada sección tiene dueño y tope; lo que no cabe va a su documento y aquí queda el enlace.
Hecha por el Claude de Álvaro el 9-nov a partir del Plan Gadea («Por qué nos cuesta tanto el bot: análisis por fases»); revisadas las
secciones 1 a 3 por el Claude de Gadea, con su OK, el 10-nov.

## 1. El plan y el bloque en curso · dueña: Gadea · tope 15 líneas

- **Diagnóstico.** Los graves no vienen de la búsqueda (0 de 67) y poco del escritor (6-8 de 67, aunque Luna no repite). Vienen de
  cuatro cosas: decisiones sin un dueño en el código (el plan, en ~12 sitios; el pase, en 17), código que estropea respuestas correctas,
  una lectura que cambia entre vueltas (Haiku y los umbrales de Jev) y una vara que no se parece a los clientes reales.
- **Lo que manda el orden:** de los 67 graves del panel 0.61, solo 26-31 son limpios (dos lecturas, 85 % de acuerdo); de ellos, 14-21
  son de plan, importe y moneda. El resto lo pone la vara: reglas posteriores, guiones que no contestan, fricción, el juez.
- **Bloques, en orden:** 0 la vara · 0,5 lo ya escrito · 2a plan e importe, lo determinista · 1 lo que recibe el escritor · 2b plan,
  importe y moneda que dependen de leer · 4 el momento de reservar y el pase · 3 horas y fechas · 5 reglas que faltan.
- **En curso (10-nov, noche):** el 0 tiene la vara montada (reloj fijo, juez con la hora y la huella, marcador, `panel-vara`,
  tanda de la vara) y medida su partida; el 0,5, el enlace con un dueño (Álvaro); el 2a, tres piezas en `bloque2a-gadea` (Claude de
  Gadea, Gonzalo no se ha conectado). Nada sube a PRE hasta cerrar el bloque.
- **Línea base (10-nov):** Luna sola saca lo mismo que el bot en graves (10,7 frente a 10,3 de 40), más corta y con 1 llamada
  por turno frente a 4: según la regla, deciden coste, latencia y control. Lo habla Gadea con el equipo; el plan sigue.
- **Por revisar con Gadea:** la meta de 5 y la parada se fijaron con el panel viejo (21-25); la vara nueva parte de 9-10 de 40. Y la
  propuesta de adelantar el 4 y el 3 (con clientes como los reales fallan la agencia, quien ya reservó y el vuelo) tras el 0,5.
- **Cierre del 0,5:** la tercera pregunta y el grupo a cero en su tanda y en el panel, y el saldo de código del bloque negativo.
- **Metas:** al acabar el plan, 5 o menos clientes con grave de 40, de media. La de 2 en 60 queda por debajo del ruido del juez.
- **Punto de parada:** tras el 0,5 y el 2a, el panel debería quedar en 8 a 11 por vuelta (antes del plan, 21 a 25). Si no baja de 16,
  se para y se revisa el rumbo.

## 2. Normas · dueña: Gadea · tope 15 líneas

1. **Mecanismo, no caso.** Nada de piezas por un grave suelto (señales de Jev, reglas del extractor, frases de prompt, regex).
2. **Ficha por cambio** (commit y Coral): bloque · mecanismo · familia · líneas que borra en src · banco sin IA · contador. Sin ficha, no entra.
3. **Lo que entra borra código:** el saldo de cada bloque en src, negativo.
4. **Un dueño por decisión, y leer, decidir y escribir por ese orden.** El código decide y pinta cifras, enlaces, horas y la pregunta.
5. **Una puerta que no edita:** si el escritor pone algo que el código no le dio, se rehace una vez o va la plantilla; nunca se recorta.
6. **Primero cubre, luego borra, y contando:** un corrector se borra cuando lleva un panel y una tanda sin actuar.
7. **La vara, quieta:** la referencia del juez congelada y con su huella; una regla nueva entra a la vez en el juez, el banco y el código.
8. **El panel, solo al cerrar un bloque:** 3 tiradas por lado, cada una juzgada dos veces; una bajada cuenta si es de 4 o más de media.
9. **Regla de parada:** si dos medidas seguidas no mueven el mecanismo, se para y se escribe «qué estamos haciendo mal».
10. **Breve y al grano:** la meta es la persona (119 caracteres, 1 de cada 4 con pregunta). Lo que pinta el código, en español e inglés.
11. **Los ciegos del panel no dan casos:** de ellos no sale nada para bancos ni arreglos; en los documentos solo se citan los `visto-*`.
12. **PRE:** una medida a la vez, avisando en Coral y con los dos saldos comprobados antes.

## 3. Decisiones vigentes · dueña: Gadea · tope 20 líneas

- **6-nov:** las tablas de CALN-43 (P1-P11), en `docs/robustness/caln/tablas-decisiones.md`. Una semana sin piezas nuevas por caso (#3664).
- **8-nov:** cuando el plan esté cerrado, se trabaja en conjunto y se reparte entre los tres.
- **9-nov, negocio:**
  - Un grupo mixto sin cédula paga todo en USD. El bot no da totales.
  - El cierre de las 4:30 es firme: se ofrece el primer día que se reserva.
  - «Next Friday» dicho un jueves es mañana.
  - A quien ya reservó le contesta la base; cambiar o cancelar va con un asesor.
  - Respuestas breves. Las agencias, como cualquier cliente.
  - La disponibilidad se contesta: siempre hay (21-oct).
  - De lo que la base no contesta, el clima del día y una recogida fuera de los puntos de siempre van con una persona; lo demás lo
    contesta la base.
- **9-nov, plan:** meta intermedia de 5 o menos de 40. Referencia del juez con las decisiones del 9-nov: c7c7268a, en
  `feature/caln34-gadea` desde el 10-nov. Ruido del juez: la misma vuelta juzgada dos veces da 20 y 23; cambian 5 de 40 clientes.
- **10-nov:** el 0,5 de Álvaro, aceptado. Su cierre: el enlace con un solo dueño, y solo con el origen conocido, con diseño antes (#3702).
- **10-nov, línea base:** sí. Luna sola con lo que lee el juez y la hora fija, sin nuestras piezas, sobre el panel de la vara (3 tiradas
  × 2 juicios); frente a la versión actual en el mismo panel, umbral de 4. Solo medida; la lleva el Claude de Gadea.
- **Pendientes de decidir:** pedir a Andrés más conversaciones reales; la norma de 5 de 5 en los clientes «a
  veces»; leer el vuelo con el lector de notas; quitar la segunda lectura de la nacionalidad (CALN-30, Gonzalo).

## 4. Quién lleva qué · cada uno su línea · tope 2 líneas por persona

- **Gadea:** el bloque 0 (la vara) y la referencia del juez, en `feature/caln34-gadea` (27ba702b, con el ruido del juez medido).
- **Álvaro:** el 0,5 (#3701). Integrado en `feature/bloque05-alvaro` (2e77937a, aceptado) y medido (38606c51: panel 24,5 → 16,7). Falta
  el cierre: el enlace y el pase con un solo dueño en la reserva, y solo con el origen conocido (diseño antes, #3702), y la tanda.
- **Gonzalo:** 0,5, el pase en una función (`feature/pase-gonzalo` 5ff32b8b).
- **Gonzalo:** el 2a (#3701 c); si no se conecta, queda libre para el primero que acabe, en orden.
- **Saldo (10-nov 00:30):** OpenAI recargado el 9-nov (22:57); OpenRouter, ~7,5 $ libres. Un panel ×3 por lado cuesta ~1,5 $ de OpenRouter.

## 5. Lecciones: lo que no funcionó · cualquiera añade · tope 12 líneas, una por lección

- Del 21-oct al 6-nov hubo 60 versiones: los bancos subían y los clientes nuevos no. Arreglar el caso visto no arregla la familia.
- Medir una pieza con el panel: el ruido (±3-4 clientes) tapa su efecto. Para la pieza, un banco sin IA.
- Probar una sola vez algo que sale a veces engaña: s04i-belgas pasaba 2 y 3 de 5.
- Arreglar un camino y no la decisión: el freno de la tercera pregunta tenía una excepción y no veía todas las preguntas.
- Quitar un corrector antes de cubrir su caso (el paso 4 de qué preguntar, 6-nov).
- El panel no se parece a los reales: infla el grupo y la tercera pregunta. Un tercio de los reales ya ha reservado.
- Atribuir a una persona lo que dijo su Claude. Hay que decir «el Claude de X».
- Medir sin mirar antes los dos saldos: el 9-nov, OpenRouter recargado pero OpenAI vacío. Antes de medir, una llamada a cada uno.
- Juzgar una sola vez: la misma vuelta, juzgada dos veces, cambia el veredicto de 5 de 40 clientes (9-nov).
- Dar por bueno un dato sin mirarlo en la charla: «visto-6929 rechaza lo que no se le ofreció» era falso; se le ofreció en el turno 1.

## 6. Marcador · la tabla entera, en `docs/plan/marcador.md` · aquí, la última línea

| Fecha | Versión | Bloque | Graves por vuelta | Líneas de src | Llamadas de IA por turno | Respuesta: caracteres · con pregunta |
|---|---|---|---|---|---|---|
| 10-nov | caln34 frente a 0,5+2a | 0,5 y 2a en `panel-vara` (una pasada) | 9,0 → 9,7 (no cuenta) | +38 en el 2a | 3,99 → 3,93 | 571 · 67 % → 575 · 67 % |



