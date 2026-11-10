# Memoria del equipo

Se lee al empezar cada sesión, también tras una compactación. Es la foto completa: de aquí se parte, no del relevo.
**Tope: 2 páginas.** Cada sección tiene dueño y tope; lo que no cabe va a su documento y aquí queda el enlace.
Hecha por el Claude de Álvaro el 9-nov a partir del Plan Gadea («Por qué nos cuesta tanto el bot: análisis por fases»); revisadas las
secciones 1 a 3 por el Claude de Gadea, con su OK, el 10-nov.

## 1. El plan y el bloque en curso · dueña: Gadea · tope 15 líneas

- **Diagnóstico.** Los graves no vienen de la búsqueda (0 de 67) y poco del escritor (6-8 de 67, aunque Luna no repite). Vienen de
  cuatro cosas: decisiones sin un dueño en el código (el plan, en ~12 sitios; el pase, en 17), código que estropea respuestas correctas,
  una lectura que cambia entre vueltas (Haiku y los umbrales de Jev) y una vara que no se parece a los clientes reales.
- **Bloques, en orden (10-nov):** 0 la vara · 0,5 lo ya escrito · 2a plan e importe, lo determinista · 1 lo que recibe el escritor ·
  4P el pase y la posventa fuera de la reserva (Gadea) a la vez que 4R el momento de reservar (Álvaro, con su cierre del 0,5) · 3.1 el
  cierre de las 4:30, con el reloj y la base · 2b plan, importe y moneda que dependen de leer · 3.2 el vuelo (si Gadea lo decide) · 5.
- **Por qué ese orden:** con clientes como los reales pesa el 4 (~5 de 40 en `panel-vara`; el 71 % de los reales pide algo suyo) y falla
  siempre (la agencia, 18 de 18, por `needs_staff`); el 2b, 0,6-2,5 y siempre «a veces». Las decisiones del 9-nov, en el juez y no en el bot.
- **En curso (10-nov):** medidos el 0, el 2a y la 1.ª parte del 1; el Claude de Gadea empieza el 4P. Nada sube a PRE hasta cerrar el bloque.
- **Vara, meta y parada (10-nov):** `panel-vara`, reloj del jueves 5, huella 9326257c; partida 9,2. Meta: 5 o menos de 40, la mitad ciega
  en 1 o menos y ningún cliente con grave en los 6 juicios. Parada: tras el 4 entero y el 3.1, si no baja al menos 3 desde 8,2.
- **Lo que aún no sabemos y cuándo se mira:** (1) el reparto por bloque es una sola lectura: segunda a ciegas en la próxima medida; (2) la
  tanda es una tirada: se repite en cada cierre; (3) cómo falla el bot con los reales: antes del 2b, con más charlas de Andrés; (4) si los
  ciegos nuevos (escritos con el diagnóstico) inclinan la vara: al final, en el examen independiente.
- **Línea base (10-nov):** Luna sola, 10,7 frente a 10,3 del bot, con 1 llamada por turno frente a 4: deciden coste, latencia y control.

## 2. Normas · dueña: Gadea · tope 15 líneas

1. **Mecanismo, no caso.** Nada de piezas por un grave suelto (señales de Jev, reglas del extractor, frases de prompt, regex).
2. **Ficha por cambio** (commit y Coral): bloque · mecanismo · familia · líneas que borra en src · banco sin IA · contador. Sin ficha, no entra.
3. **Lo que entra borra código:** el saldo de cada bloque en src, negativo.
4. **Un dueño por decisión, y leer, decidir y escribir por ese orden.** El código decide y pinta cifras, enlaces, horas y la pregunta.
5. **Una puerta que no edita:** si el escritor pone algo que el código no le dio, se rehace una vez o va la plantilla; nunca se recorta.
6. **Primero cubre, luego borra, y contando:** un corrector se borra cuando lleva un panel y una tanda sin actuar.
7. **La vara, quieta:** la referencia del juez congelada y con su huella; una regla nueva entra a la vez en el juez, el banco y el código.
8. **El panel, solo al cerrar un bloque:** 3 tiradas por lado, cada una juzgada dos veces; una bajada cuenta si es de 3 o más de media en
   `panel-vara` (con su ruido, ~1 % de falsos positivos; se recalcula en cada cierre). Entre cierres, el mecanismo: sus clientes ×5.
9. **Regla de parada:** si dos medidas seguidas no mueven el mecanismo, se para y se escribe «qué estamos haciendo mal».
10. **Breve y al grano:** la meta es la persona (119 caracteres, 1 de cada 4 con pregunta). Lo que pinta el código, en español e inglés.
11. **Los ciegos del panel no dan casos:** de ellos no sale nada para bancos ni arreglos; en los documentos solo se citan los `visto-*`.
12. **PRE:** una medida a la vez, avisando en Coral y con los dos saldos comprobados antes.
13. **Despacio y con doble confirmación (Gadea, 10-nov):** cada decisión de rumbo, con dos lecturas independientes (agentes sin la
   conclusión) y comprobada en las charlas o en el código antes de proponerla.

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
  - De lo que la base no contesta, el clima del día y una recogida fuera de los puntos de siempre van con una persona; lo demás, la base.
- **9-nov, plan:** referencia del juez con las decisiones del 9-nov (c7c7268a; huella 9326257c). Ruido del juez: la misma vuelta juzgada
  dos veces da 20 y 23; cambian 5 de 40 clientes.
- **10-nov:** el 0,5 de Álvaro, aceptado. Su cierre: el enlace con un solo dueño, y solo con el origen conocido, con diseño antes (#3702).
- **10-nov, línea base:** sí; Luna sola con lo que lee el juez y la hora fija, frente al bot en `panel-vara`. Solo medida (hecha).
- **10-nov, rumbo (auditado con dos agentes independientes):** la vara, la meta, la parada y el orden de la sección 1, y el umbral de 3
  (norma 8). El 4R, propuesto a Álvaro (#3721); si no está, se da por bueno.
- **Pendientes de decidir:** pedir a Andrés más conversaciones reales; la norma de 5 de 5 en los clientes «a veces»; el vuelo con el
  lector de notas (3.2); quitar la segunda lectura de la nacionalidad (CALN-30).

## 4. Quién lleva qué · cada uno su línea · tope 2 líneas por persona

- **Gadea:** el 0, el 2a y la 1.ª parte del 1, hechos y medidos (`bloque0-gadea` 2761fbc1, `bloque2a-gadea`, `bloque1-gadea` b16e3612).
  Ahora, el 4P: el pase y la posventa fuera de la reserva.
- **Álvaro:** el 0,5 (#3701). Integrado en `feature/bloque05-alvaro` (2e77937a, aceptado) y medido (38606c51: panel 24,5 → 16,7). Falta
  el cierre: el enlace y el pase con un solo dueño en la reserva, y solo con el origen conocido (diseño antes, #3702), y la tanda.
- **Gonzalo:** 0,5, el pase en una función (`feature/pase-gonzalo` 5ff32b8b). El 2a lo hizo el Claude de Gadea, al no conectarse él.
- **Saldo (10-nov 05:54):** OpenAI con saldo; OpenRouter, 6,11 $. Un lado del panel ×3 cuesta ~1,5 $ de OpenRouter.

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
| 10-nov | 0,5+2a frente a bloque 1 | 1 en `panel-vara` (6 juicios por lado) | 8,7 → 8,2 (no cuenta); «a veces» 18 → 11 | 1: −1 | 3,93 → 3,70 | 575 · 67 % → 570 · 66 % |



