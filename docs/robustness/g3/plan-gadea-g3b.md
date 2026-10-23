# G3b · Charlas en directo de Gadea (con Claude): familias, grupos mixtos, pagos y descuentos

Decisión de Gadea (23-oct). Se lanzan contra el bot desplegado, por Chatwoot (`scripts/charla_pre.py`), después de la
promoción del G10 nº 6. Frases nuestras; el cliente se adapta a lo que contesta el bot, como uno de verdad. Lo que
salga va a `hallazgos.md` y se arregla por causa, con su banco ×3.

En todas se mira:

- que los datos sean correctos (precio, moneda, qué incluye, edades, recogida);
- que no repregunte lo ya dicho ni invente nada;
- que conteste antes de preguntar;
- la latencia de cada turno.

| # | Perfil | Cómo empieza | Qué miro en especial |
|---|---|---|---|
| 1 | Familia con niños de 7 y 11, en Cartagena | «Hola, vamos en familia con nuestros hijos de 7 y 11 años, ¿qué podemos hacer con ustedes?» | Edades mínimas (snorkel desde 6, Bubble Makers de 8 a 10, minicurso desde 10): que recomiende y deje elegir; precio por persona; el punto de encuentro |
| 2 | Grupo de 6 con actividades distintas | «Somos 6: tres somos buzos, dos nunca han buceado y una persona no se mete al agua» | El reparto sin repreguntar; cada plan con su precio; el acompañante; el 10 % de grupo, que se suma al online, se pide antes de pagar y no vale para cursos |
| 3 | Grupo mixto de nacionalidades | «Somos dos colombianos y dos franceses, queremos hacer snorkel» | Que todo el grupo paga en USD; nada de dos monedas a la vez; el enlace |
| 4 | Precio sin decir la nacionalidad, y luego «soy colombiana» | «¿Cuánto cuesta el minicurso?» … «ah, soy colombiana» | Las dos monedas al principio; después, COP sin repetir; que el cierre lo lleve un asesor |
| 5 | Cómo se paga, extranjero y colombiano | «¿Cómo pago? ¿Puedo pagar la mitad allá?» | Extranjero: el enlace online y que la reserva se confirma al conciliar el pago. Colombiano: el 50 % online y el 50 % en persona lo coordina un asesor |
| 6 | Descuentos | «¿Me hacen descuento si llevo mi equipo? ¿Tienen algún código?» | El 5 % solo con el equipo completo y en buceo recreativo o cursos (no en el minicurso ni en el snorkel); que no hay códigos |
| 7 | Reserva completa hasta el enlace, con todo en un mensaje | «Somos 2 adultos, no colombianos, snorkel desde Cartagena el sábado, ¿me pasas el link?» | Que no pregunte nada de lo que ya dijo; la tarjeta con el precio y el enlace a la primera |
| 8 | Posventa: se suma una persona | «Ya reservé para el sábado, pero ahora somos uno más. ¿Cuánto paga el nuevo?» | El precio del nuevo sin vender de nuevo lo ya reservado; el cambio de la reserva va a un asesor |
