# Simplificar, V2: la puerta del código sobre V1 (diseño, 10-nov; v1, antes de la revisión)

**Ficha:**
- **Rama:** `feature/puerta-v2-alvaro`, sobre `simple-gadea` 0209842a. Prototipo fuera de src: `scripts/simple_v2.py` envuelve
  `scripts/simple_v1.py` sin cambiarlo, para que V1 se pueda repetir tal como se midió (#3763).
- **Mecanismo:** Luna escribe en una llamada (V1). El código **comprueba y decide** sobre lo que Luna dice que entendió:
  - el pase;
  - los importes;
  - el enlace;
  - si toca una pregunta.
  Lo que no cumple se rehace una vez con el motivo. Si vuelve a fallar, el código pone lo suyo (norma 5: nunca se recorta).
- **Lo que arregla de V1** (#3761):
  - pasa de más (71 de 120 charlas frente a 45);
  - importes fuera del catálogo (13 de 272: cuentas suyas, descuentos aplicados, totales);
  - pregunta en el 76 % de las primeras respuestas a reales (criterio: ≤ 50 %).
- **Reutiliza, sin tocarlos:**
  - `como_reserva.entrega` (4R-1);
  - `grounding_check.currency_amounts_grounded`;
  - `que_preguntar.trae_pregunta` y `tapar_enlaces`;
  - los enlaces del catálogo (`cart_render._resolve_service_booking_url`).
- **Contador:** cada turno guarda `puerta`: lo que rechazó, si rehízo y lo que puso el código.

## 1. Lo entendido, en estado

Para que la puerta use `entrega`, V2 cambia en su envoltorio el esquema de «entendido»:
- `nacionalidad` admite **«mixta»**: el grupo mixto paga en USD con el enlace (`pago-y-reserva`).
- `actividad` deja de ser texto libre. Pasa a ser `reparto`: `{id del tipo: personas}`, con los tipos de la tarjeta
  (`certified_diving`, `minicourse`, `snorkel`, `companion`, `padi_course`…). `GRUPO` (5 o más con descuento) y `PARTE_SIN_ENLACE`
  necesitan saber quién hace qué.
- `plan` sigue siendo el id del catálogo. Si el plan no tiene enlace (`contact_only` o sin `booking_url`), lo reserva un asesor.

Se pasa a un `ConversationState` de prueba:

| Entendido | Estado |
|---|---|
| `origen` cartagena / islas | `location` cartagena / island |
| `hotel` | `hotel` |
| `nacionalidad` colombiana o residente | `is_colombian=True` |
| `nacionalidad` mixta | `is_colombian=True` y `mixed_nationality_notice=True` |
| `nacionalidad` extranjera | `is_colombian=False` |
| `personas` | `detected_group_size` |
| `reparto` | `detected_group_allocation` |
| `ya_reservo` | `ya_reservado` |

## 2. Las cuatro comprobaciones, en este orden

**C1. El pase lo decide el código.** `pasar` lleva un motivo de una lista cerrada (va en el esquema):

| Motivo | Se acepta si | Decisión |
|---|---|---|
| `reservar_con_asesor` | `entrega` da ASESOR, GRUPO, PARTE_SIN_ENLACE o RECOGIDA, o el plan no tiene enlace, **y** `quiere_reservar` | P3 (#3741), P9/P10 |
| `ya_reservo` | `ya_reservo` (cambiar, cancelar, el número, o lo que la base no tiene) | `ya-reservado` |
| `salud` | siempre (lo médico de verdad) | `salud` |
| `clima_del_dia` | siempre | `fuera-de-la-base` |
| `recogida_fuera` | sale desde las islas y `recogida_por_confirmar` (4R-1) | `fuera-de-la-base` |
| `pide_persona` | siempre | — |
| `horario` | siempre: pide otro horario | P4 (#3741) |
| `origen_sin_saber` | quiere reservar y el origen sigue sin saberse tras pedirlo una vez con su motivo | P1b (#3742) |
| `otro` | **P-a, la decide Gadea** | `fuera-de-la-base` |

- Si Luna marca un pase que no se acepta, se rehace con el motivo. Ejemplos: «no lo pases: el grupo aún no quiere reservar; dile una
  vez que lo reserva un asesor»; «no lo pases: los hoteles los contesta la base».
- Si el código decide un pase y Luna no lo marcó (grupo que quiere reservar), el código lo marca. Si su texto no lo dice, añade
  la línea del pase (la de `nucleo/entrega.py`).
- En el panel de V1, la mayoría de los pases sobrantes son de este tipo. Pasa al grupo, al equipo propio, al colombiano, al Airbnb
  y al paquete sin enlace en su primer mensaje, sin que pidan reservar: visto-6898, 6901, 6929, 6930 y 6940. También el precio de un
  hotel y el alojamiento barato, que contesta la base: visto-6942.

**C2. Los importes.**
- Cada cifra con moneda del texto tiene que estar en el catálogo: online o normal, USD o COP, del plan. La comprobación es
  `currency_amounts_grounded` contra el catálogo.
- Fuera: las cuentas, los descuentos aplicados («160,20 USD») y los totales («356 USD en total», `sin-totales`).
- Si no cumple, se rehace con el motivo: «solo el precio por persona del catálogo, sin aplicar descuentos ni sumar».

**C3. El enlace** (`entrega` sobre el estado de C1):
- **ENLACE:** el texto solo puede llevar el enlace de su plan y de su origen. Si quiere reservar y no lo lleva, lo añade el
  código.
- **ORIGEN_PRIMERO, ASESOR, GRUPO, PARTE_SIN_ENLACE, RECOGIDA o HOTEL_PRIMERO:** ningún enlace de reserva. Si lleva uno, se
  rehace.
- Un enlace de otro plan o del otro origen, también se rehace.

**C4. La pregunta.** Se permite una, y solo si la reserva la necesita:
- quiere reservar y falta un dato (origen, fecha, personas, certificado);
- o se habla de precio sin saber el origen (`origen-y-precio`).

Si no toca y el texto pregunta (`trae_pregunta`), o pregunta dos veces, se rehace con el motivo: «contesta sin preguntar».

**Rehacer:** una sola vez por turno, con todos los motivos juntos. Si la segunda tampoco cumple:
- **C1:** manda la decisión del código, y el texto que no la cumple va con la línea fija.
- **C2 y C3:** la plantilla. Es lo que pinta el código (la pieza de precios del plan por origen y moneda, y la línea de la entrega),
  sin el texto de Luna.
- **C4:** se deja pasar y se cuenta.

## 3. Lo que decide Gadea

- **P-a.** Lo que la base no tiene y no es de la lista (guardar maletas, quién vigila a una niña mientras bucean): ¿pasa con una
  persona, o lo dice y sigue sin pasar? `fuera-de-la-base` solo nombra el clima del día y la recogida.
- **P-b.** ¿El reloj y la línea del cierre de las 4:30 (3.1) se comprueban también, o basta con que V1 los reciba?

## 4. Cómo se mide

- Los criterios de `diseno-simple.md`, fijados antes de medir, frente a B (7,5) y V1:
  - panel-vara ×3 juzgado dos veces;
  - los 75 reales ×3;
  - pases ≤ B;
  - importes fuera del catálogo ≤ B;
  - estilo ≤ 300 caracteres y ≤ 50 % con pregunta;
  - p90 ≤ 7,5 s.
- **Además:**
  - el porcentaje de turnos rehechos;
  - el de turnos con plantilla;
  - el p90 con el rehacer: la segunda llamada cuesta ~3 s.
- **Banco sin IA** (`tests/test_simple_v2.py`):
  - las cuatro comprobaciones con salidas de Luna grabadas, de V1;
  - el paso de entendido a estado;
  - que V1 no cambia: mismo texto de esquema y mismas salidas sin la puerta.

## 5. Riesgos

- Rehacer suma una llamada: si pasa en más de 1 de cada 4 turnos, el p90 sube. Se mide.
- Luna puede marcar mal lo entendido (el origen o la nacionalidad). La puerta decide sobre lo que Luna dice, así que no arregla
  lecturas malas. Se mide comparando con lo que el cliente dijo en los bancos de origen y nacionalidad.
- La lista de motivos del pase puede quedarse corta. `otro` existe para eso, y su regla la decide Gadea (P-a).
