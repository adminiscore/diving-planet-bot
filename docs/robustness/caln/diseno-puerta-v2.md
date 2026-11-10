# Simplificar, V2: la puerta del código sobre V1 (diseño, 10-nov; v2 tras la revisión; V2m tras revisar el código)

**V2m (10-nov, #3773 y #3774, con el OK del Claude de Gadea).** La revisión del código (paso 5) encontró 13 defectos en la primera
puerta. En vez de tapar los 13, se simplifica:
- **Solo lo exacto rehace:** C2, los importes, y C3, el enlace.
- **C1 (el pase) y C4 (la pregunta) solo se cuentan.** El comportamiento lo llevan las reglas del esquema: el esquema lleva 5, no 3.
  Si V2m pasa a más clientes que B, no cumple el criterio, y entonces sí haría falta que C1 decida.
- **Arreglado en lo que queda:**
  - C2 lee también los precios de `pricing.json` que no son de un servicio (el acompañante, la nocturna…);
  - C2 acepta los redondeos hacia arriba y hacia abajo, «mil», «dólares», separadores, decimales en pesos y el 20 %;
  - C3 acepta el enlace en los dos idiomas;
  - el pase y el enlace del código no se repiten entre turnos;
  - fuera el aviso del asesor añadido por el código;
  - la plantilla conserva un pase bueno y no adivina el precio del buceo sin plan;
  - si la plantilla no tiene nada seguro, se queda el texto de Luna;
  - una salida rara de Luna, o una segunda llamada que falla, no tumban la tirada.
- **Un brazo más para atribuir: V1R.** Es el mismo esquema con las mismas reglas, sin puerta (`--modo v1r`). Se mide sin juez, salvo
  que sobre ventana. V2m se juzga entera.
- **Banco:** 58 tests sin IA, también del bucle de un cliente con salidas simuladas, y la huella de V1 fijada.

**Ficha:**
- **Rama:** `feature/puerta-v2-alvaro`, sobre `simple-gadea` 0209842a. Prototipo fuera de src: `scripts/simple_v2.py` envuelve
  `scripts/simple_v1.py` sin cambiarlo, para que V1 se pueda repetir tal como se midió (#3763).
- **Mecanismo:** Luna escribe en una llamada (V1) y dice qué entendió. El código **comprueba y decide** cuatro cosas sobre eso:
  el pase, los importes, el enlace y la pregunta.
  - Lo que no cumple se rehace una vez con el motivo.
  - Si vuelve a fallar, manda la decisión del código (norma 5: nunca se recorta).
- **Lo que arregla de V1** (#3761):
  - pasa de más (71 de 120 charlas frente a 45);
  - importes fuera del catálogo (cuentas suyas, descuentos aplicados, totales);
  - pregunta en el 76 % de las primeras respuestas a reales (criterio: ≤ 50 %).
- **Contador:** cada turno guarda `puerta`: qué falló, si rehízo y qué puso el código.

**v2 (10-nov):** un agente revisó la v1 contra el código y las 384 respuestas de V1, sin mi conclusión. Lo que cambia:
- **La decisión es propia, pequeña y sobre lo entendido**, en el script. No se pasa a `ConversationState` ni se usa `entrega` del
  4R: esa está en otra rama, no en simple-gadea, y src está congelado. Además el paso a estado perdía el idioma, las edades y el
  plan.
- **Faltaban reglas:** el equipo propio y la reserva a nombre de otro van con un asesor (`equipo-propio-por-el-asesor`,
  `temas-3nov`).
- **El orden manda:** el hotel y el origen van antes que un plan sin enlace (`hotel-antes-de-reservar`, P5).
- **Los importes, con un extractor propio.** `currency_amounts_grounded` no ve «USD 999» (Luna lo escribe así 53 veces) y no sabe
  de plan, origen ni moneda.
- **La pregunta, por tema y contando.** La v1 prohibía preguntas que las decisiones piden (el hotel, la nacionalidad, las edades, el
  refresher, «4 diurnas o salidas sueltas»).
- **Si el pase se rechaza dos veces, se deja pasar y se cuenta.** Mandar «te paso» sin pase se contradecía.
- **Criterios de rehacer fijados antes de medir:** la revisión estima que se reharía el 31 % de los turnos.

## 1. Lo que Luna devuelve (cambio del esquema, solo en el envoltorio de V2)

A lo que ya da V1 se añade:
- `nacionalidad`: también «mixta» (el grupo mixto paga en USD con el enlace).
- `reparto`: `{id: personas}`, con los ids de la tarjeta (`certified_diving`, `minicourse`, `snorkel`, `companion`,
  `padi_open_water`…; la lista sale de `cart_activity_ids()`).
- `equipo_propio` y `a_nombre_de_otro`: `true` | `false`.
- `idioma`: `es` | `en`.
- `pasar`: `{"si", "motivo", "tema"}`, con `motivo` de la lista de C1.
- `pregunta`: `{"tema"}` de la pregunta que hace el texto, o null. Los temas son origen, fecha, personas, certificado, hotel,
  nacionalidad, edades, refresher, plan u otra.

Un `plan` que no es un id del catálogo cuenta como no dicho, no como plan sin enlace.

## 2. La decisión del momento de reservar, sobre lo entendido

En este orden (como `entrega` del 4R):
1. `ya_reservo` → la posventa (C1).
2. Sale desde las islas sin hotel → **HOTEL_PRIMERO**: ni enlace ni asesor.
3. Origen sin saber → **ORIGEN_PRIMERO**: ningún enlace (#3738), y primero el origen (P5).
4. Va con un asesor (**ASESOR**, con su motivo) si se da alguna de estas:
   - colombiana o residente;
   - casa, Airbnb u hotel fuera de la lista de recogida (`lugares.recogida_conocida`);
   - 5 o más en actividades con descuento de grupo;
   - una parte del plan sin enlace (Bubble Makers por las edades, el acompañante…);
   - el plan no tiene enlace;
   - equipo propio;
   - a nombre de otro.
5. Si no → **ENLACE**: el del plan y su origen. El origen va en el id del servicio (`*_already_on_island`).

## 3. Las cuatro comprobaciones

**C1. El pase.** Se acepta según el motivo:

| Motivo | Se acepta si |
|---|---|
| `reservar_con_asesor` | la decisión es ASESOR **y** `quiere_reservar` (P3) |
| `ya_reservo` | `ya_reservo` y quiere cambiar, cancelar o cambiar el número, o lo que pregunta no está en la base (`ya-reservado`) |
| `salud` | una condición médica para bucear; no el mareo ni lo que la base contesta (`salud`) |
| `clima_del_dia` | siempre (`fuera-de-la-base`) |
| `recogida_fuera` | sale desde las islas y su alojamiento no está en la lista (`fuera-de-la-base`) |
| `pide_persona` | el mensaje del cliente pide una persona; un «sí» a una oferta de Luna no cuenta (#3765) |
| `horario` | pide mover la hora de salida o de recogida; no el cierre de las 4:30 (`cierre-para-manana`) |
| `origen_sin_saber` | quiere reservar y el origen sigue sin decirse después de la pregunta con su motivo (P1b) |
| `la_base_no_lo_tiene` | el tema no es de los que contesta la base: hoteles, puntos de inmersión, qué llevar, comida, precio, horario, disponibilidad (P-a) |

- **Un pase que no se acepta** se rehace con el motivo («no lo pases: aún no quiere reservar; di una vez que lo reserva un asesor»).
  Si Luna insiste, se deja pasar y se cuenta: el cliente llega a una persona, que es lo menos malo.
- **Un pase que el código exige y Luna no marcó** (quiere reservar y la decisión es ASESOR; P1b sin origen): lo marca el código.
  Si el texto no lo dice, añade la línea del pase.
- **Luna no ofrece el pase:** una oferta («¿quieres que te pase…?») es una pregunta que no toca (C4).

**C2. Los importes** (extractor propio):
- Lee «N USD», «USD N», «N COP», «COP N», «$N» y «N mil pesos», y los porcentajes.
- Cada importe tiene que ser un precio del catálogo (online o normal, de `pricing.json`):
  - del plan o del reparto, si se saben;
  - en la moneda que toca (`moneda`): COP a colombianos y residentes, USD a extranjeros y grupos mixtos, las dos si no se sabe;
  - del origen sabido, o de los dos si no se sabe (`origen-y-precio`).
- Cada porcentaje tiene que estar en `discounts.json`.
- No caben cuentas, descuentos aplicados ni totales (`sin-totales`).

**C3. El enlace:**
- Solo puede ir el de ENLACE.
- Con otra decisión, ningún enlace de reserva.
- Si quiere reservar, la decisión es ENLACE y no lo lleva, lo añade el código. Si la nacionalidad no se sabe, con la línea de P2
  (#3741).

**C4. La pregunta.** Se permite una si se cumplen las tres:
- su tema (`pregunta.tema`) es un dato que la reserva necesita y falta;
- el cliente quiere reservar, o pregunta precio o plan;
- ese tema se ha preguntado menos de 2 veces (`sin-tercera-pregunta`), salvo el origen al reservar, una vez más con su motivo
  (P1b).

No caben las preguntas para seguir la charla («¿algo más?», «¿te interesa?»). El envoltorio guarda las veces de cada tema entre
turnos.

**Rehacer:**
- Una vez por turno, con todos los motivos juntos.
- Si la segunda tampoco cumple:
  - **C1:** se deja pasar y se cuenta.
  - **C2 y C3:** la plantilla. Es la pieza de precios del plan con su origen y su moneda y la línea de la entrega, sin el texto de
    Luna. Si no se sabe el plan, la línea de la entrega sola.
  - **C4:** se deja pasar y se cuenta.

## 4. Lo que decide Gadea

- P-a: decidida (#3766). Lo que la base no tiene y no está en la lista pasa con una persona.
- P-b: decidida (#3765). El cierre de las 4:30 no se comprueba. El vuelo, después, si V2 pasa.

## 5. Cómo se mide (fijado antes de medir)

- **Los criterios de `diseno-simple.md`, frente a B (7,5) y V1:**
  - panel-vara ×3 juzgado dos veces;
  - los 75 reales ×3;
  - pases ≤ B;
  - importes fuera del catálogo ≤ B;
  - estilo ≤ 300 caracteres y ≤ 50 % con pregunta;
  - p90 ≤ 7,5 s.
- **V1 se repite a la misma hora que V2.**
- **Los importes los cuenta un contador independiente**, no el extractor de C2. Si no, la medida sería circular.
- **Topes de la puerta:**
  - rehechos ≤ 25 % de los turnos;
  - plantilla ≤ 3 %;
  - p90 de los primeros mensajes ≤ 7,5 s.
  - Si se pasan, V2 no se adopta tal cual.
- **Banco sin IA** (`tests/test_simple_v2.py`):
  - la decisión del §2 en sus combinaciones;
  - C1-C4 con salidas grabadas de V1;
  - el extractor de importes con sus formatos;
  - que V1 no cambia: mismo esquema y mismas salidas sin la puerta.
- Con 3 tiradas, los graves solo dicen si V2 no es peor que B (no-inferioridad). Lo que la puerta cambia (pases, importes, preguntas)
  se ve en sus contadores, que en V1 son estables entre tiradas.

## 6. Riesgos

- **La puerta decide sobre lo que Luna dice que entendió.** Si Luna marca mal el origen, la nacionalidad o el motivo del pase, la
  puerta no lo arregla.
  - La revisión estima que, aun con la puerta, las charlas con pase bajarían de 71 a ~49 de 120, por encima de las 45 de B.
  - Se mide; si no baja, el pase pide algo más que la etiqueta de Luna.
- **Rehacer suma una llamada.** En los primeros mensajes, el p90 puede pasar de 7,5 s. Se mide contra el tope.
- **La plantilla pierde lo demás que contestaba Luna.** Se cuenta; se espera muy rara.
- **La puerta no debe crecer hasta parecerse a lo que queremos quitar.** Si para pasar los criterios hace falta mucho más que esto,
  se dice y se para.
