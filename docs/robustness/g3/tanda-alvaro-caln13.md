# CALN-13 · La tanda de Álvaro: otros clientes, hasta reservar (diseño, 3-nov)

Encargo de Gadea (#2712): una tanda con otros clientes y otro criterio de gravedad, y cada charla hasta reservar
(tarjeta, enlace o asesor, y pago). Cuenta para la meta de cierre de CALN: dos tandas seguidas sin graves. Las frases
las escribe Claude haciendo de cliente, turno a turno (`charla_rama`), sin copiar el golden, G9, G10, las tandas
anteriores ni conversaciones reales.

## 1. Los 8 clientes (ninguno se ha probado en s29-s30e)

| # | Cliente | Lo que pone a prueba | Hasta dónde |
|---|---|---|---|
| 1 | Pasajera de crucero: llega a Cartagena a las 7:00 y el barco sale a las 17:00 | horario fijo, vuelta a las 3:00 p. m. (llegada ~4:15), reservar para mañana, no el mismo día | el enlace de la salida de 2 inmersiones o el no claro |
| 2 | Buzo SSI con 40 inmersiones que quiere nitrox | certificación de otra agencia, la especialidad de nitrox, la tarjeta | el enlace del plan o de la especialidad |
| 3 | Usuario en silla de ruedas que quiere probar el buceo | DIVE TO HEAL (buceo adaptado), sin prometer lo que coordina el equipo | el pase al asesor, bien explicado |
| 4 | Cuatro estudiantes con poco dinero que pagan cada uno lo suyo | lo más barato de verdad, el descuento de grupo de 5 (no llegan), pagos por separado | los enlaces y cómo paga cada uno |
| 5 | Madre con dos hijos de 15 y 17, alojados en Bocagrande, que quieren el Open Water | el curso de 2 días, la noche en las islas, las edades, el origen por el barrio (CALN, barrios) | el enlace del curso o el asesor |
| 6 | Cliente que ya reservó por la web y quiere cambiar la fecha y añadir una persona | la posventa (ya reservado), los cambios de fecha según los términos, no volver a vender | el pase al asesor con los datos |
| 7 | Pareja brasileña que escribe en portugués y se marea | los idiomas (se contesta en español o inglés, decisión de Gadea), el consejo del mareo, el snorkel | el enlace del snorkel o del minicurso |
| 8 | Colombiano con pasaporte colombiano que vive en Madrid | la moneda (el colombiano paga en pesos, aunque viva fuera), el pago | el asesor (colombiano) con el anticipo |

## 2. El criterio de gravedad (otro que el de las tandas de Gadea)

Se mira con los ojos del cliente que quiere reservar:
- **Grave:** el cliente reserva mal o no puede reservar. Por ejemplo:
  - un importe, una moneda o un enlace equivocados, o el plan del otro origen;
  - una fecha, un horario o una disponibilidad falsos (el mismo día, volver a tiempo al barco);
  - un consejo inseguro (salud, alcohol, volar);
  - lo contrario de una política;
  - un callejón sin salida: ni enlace ni asesor ni siguiente paso;
  - la misma pregunta por tercera vez después de contestada.
- **Medio:** reserva, pero con fricción. Por ejemplo:
  - una pregunta que sobra;
  - un dato pedido dos veces;
  - un texto largo pegado (la lista de descuentos);
  - un dato que sí está en la base y no se da (la búsqueda o la redacción).
- **Menor:** estilo, tono, emojis, el orden de las frases.

Cada grave se repite ×3 frente a PRE para separar lo nuevo de lo que ya pasaba, como en s30a y s30e. Cada hallazgo
dice de qué zona es: grupo y origen para Álvaro; precios y descuentos para Gonzalo; hechos, moneda, extractor y base
para Gadea.

## 3. Cuándo y cómo

- Contra la candidata que toque (la 0.42 cuando esté en PRE), con `charla_rama` y `--codigo-local` si es una rama. Va
  en serie, con `mi_estado`, y sin juez.
- 8 charlas de ~5-7 turnos (≈ 50 turnos, unos céntimos de Luna), más las repeticiones de los graves.
- Resultado en `docs/robustness/g3/hallazgos.md` como CALN-S03A-…, con las charlas en
  `docs/robustness/g3/charlas-rama/s03a-*`.
