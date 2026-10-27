# Batería fija de sparring (CALN-1)

Decisión de Gadea (27-oct, #2164): el sparring (Claude hace de cliente contra el bot) es barato y encuentra lo que el
examen oculto no ve. Esta es la **batería fija**: se pasa en cada integración, como prueba de regresión, con
`scripts/charla_rama.py` contra la rama, sin desplegarla. Aparte van las **tandas por tema** (precios y origen,
grupos que cambian, familias con niños, posventa, inglés y quejas).

**Cómo se pasa.** Una charla por persona: `python -m scripts.charla_rama nueva --nombre bN-<persona>`, y luego un
`di` por turno. El cliente sigue el guion, pero contesta a lo que diga el bot, como haría una persona. Las frases son
nuestras: no salen del golden, de G9/G10 ni de las charlas reales. Al acabar:

1. Cada fallo va a `hallazgos.md`, con su causa y su tarea.
2. Cada caso va a un banco fijo (`docs/robustness/caln/banco-*.json`).
3. Se rellena la columna «hoy» de esta tabla.

**Qué mirar siempre.** Además de lo propio de cada persona:

- saludo en el turno 1, y solo en ese;
- ningún dato que el cliente ya dio se vuelve a preguntar;
- una sola pregunta, al final;
- nada dicho dos veces;
- precios por persona, con los dos orígenes y las dos monedas mientras no se sepan (A1: sin total del grupo en el
  texto);
- nada inventado (edades, días, lo que incluye cada plan);
- idioma del cliente;
- turnos de menos de 8 s.

| # | Persona | Qué quiere | Qué hay que comprobar | Se rompía (hallazgo) | 1.ª tanda (b0f3a97, 27-oct; CALN3-01..14) | 2.ª tanda (c1be0e4, 27-oct; CALN4-01..12) |
|---|---------|------------|-----------------------|----------------------|-----|-----|
| 1 | Familia Advanced: él y ella Advanced, hijo de 11 que no bucea, suegra que no se mete al agua; «vamos a estar en Cartagena» | Qué recomiendan y cuánto; luego 2 días, el niño el Open Water | «Advanced» = certificados (no se pregunta); «estar en Cartagena» = origen; lo que elige cada uno se guarda; sin bucle | t2 repregunta la certificación; t3 «¿desde dónde?»; t5-6 bucle con el niño (CALN1-01) | t1 grupo 2 (cuenta solo a los buzos), doble saludo; t2 «¿desde dónde?» y sin precios de 2 días; t3 todo dicho dos veces (16,9 s), tarjeta bien | t1 doble saludo, grupo 2 (solo los buzos); t2 «¿desde dónde saldrías?» y reparto {acompañante 1, buceo 1} en un grupo de 2; t3 tarjeta bien (2 × paquete de 5, Open Water, acompañante) y sin repetir; 12-13 s cada turno |
| 2 | Pareja en inglés: él PADI, ella nunca ha buceado; Canadá; luego en Isla Grande | «How much for both of us?»; él con repaso | Cada uno su actividad en la primera cotización; «for us» = 2; el precio del repaso desde las islas | dos minicursos en t1; «¿cuántos sois?»; «I don't have its island price» (CALN1-02, CALN2-01/03) | t1 sin precios y un título suelto; t2 minicurso ×2 para él (buzo); t3 tarjeta sin rehacer (3 plazas para 2), repaso sin precio | t1 sin precios y el título suelto; t2 minicurso ×2 (él es buzo) y dos preguntas; t3 tarjeta rehecha bien (1 + 1), repaso sin precio, enlaces y moneda dos veces |
| 3 | Amigos de Medellín, snorkel «en las islas» este puente; luego «salimos desde Cartagena», 5 (2 snorkel, 3 buceo) | El precio, y re-cotizar al corregir el origen | Nombrar las islas como sitio no es el origen; al corregirlo, se re-cotiza y se dice; nada repetido | cotiza solo islas; no re-cotiza; frase del snorkel dos veces (CALN1-03) | bien: dos orígenes y re-cotiza al corregir; t3 dos «¡Perfecto…!» y enlaces de la web a colombianos | t1 doble saludo y el precio de las islas (150.000) como «saliendo desde Cartagena»; t2 grupo bien pero no re-cotiza; t3 tarjeta bien (448.000) sin aclarar el de t1, enlaces de la web a colombianos |
| 4 | Familia de 5: marido Advanced, ella nunca ha buceado, hijas de 14 y 9, suegro acompañante; del 3 al 7 de noviembre | Recomendación y precio de todos | Plan persona a persona por edad (Bubble Makers para la de 9); el grupo entero guardado; el precio de cada uno; sin menú genérico | frase cortada y menú genérico; «no tengo aquí los precios» (CALN1-04) | t1 sin precios y la línea del suegro rota; t2 grupo y precios bien, pero los 6 planes de buceo y avisos repetidos | t1 doble saludo, «Precios por persona» sin precios, «¿saldrías?» en singular; t2 grupo y precios bien, pero los 6 planes, el bloque de alojamiento de cursos que nadie pidió y «Te recomiendo 2 inmersiones» |
| 5 | Familia con niños pequeños: ella Open Water, él no bucea, niños de 7 y 4; alojados en Cartagena | Qué pueden hacer todos; luego los enlaces | El camino viejo de edades no se come el turno; grupo de 4; «alojados en Cartagena» = origen; enlaces sin «¿desde dónde?» | solo los niños y relleno (CALN2-04, arreglado 395f1db); origen no guardado (CALN2-05) | camino de edades arreglado; t2 tarjeta de 2 buzos por la regla de DEUDA-EXT2 (arreglado); «no tengo… en el contexto» | t1 «con 7 y 4 ninguno alcanza la edad» (el snorkel es desde 6) y quien escribe queda «acompañante», grupo 3; t2 corrige la edad, pero «¿Saldrías desde…?», dos preguntas y «Reserva con el de tu punto de salida» |
| 6 | Amigos de Bogotá: 4 certificados y 2 que dudan entre minicurso y snorkel; luego son 8 | Precio del grupo y descuento | Sin menú genérico cuando el grupo acota; el grupo que crece se guarda; el descuento de grupo una vez | menú de 4; descuentos repetidos (CALN2-06/07) | t1 bien (descuento una vez) pero sin reparto; t2 «¿Con cuál te animas?» (repregunta) | t1 bien (precios, descuento una vez) pero doble saludo y sin reparto; t2 reparto descartado por incompleto y «¿me confirmas que tienen su certificación?» |
| 7 | Grupo con nacionalidades mezcladas: dos colombianos y dos de España | Precio para todos | Moneda del grupo mixto (USD) y su regla una sola vez; sin «¿volver al menú principal?» | regla del mixto dos veces y el menú (CALN2-07) | t1 regla del mixto dos veces y «¿…volver al menú principal?» | t1 regla del mixto una vez y sin el menú (mejor); doble saludo y lo que incluye dicho dos veces |
| 8 | Turista en inglés, escribe con faltas y abreviaturas; ya está en un hotel de Isla Grande; certificado, pero hace 4 años que no bucea; quiere ir mañana por la tarde | Si se puede mañana, el precio y si necesita repaso | El repaso (más de 2 años) se ofrece con su precio desde las islas; el corte de reservas dicho tal cual (sin «cerró ayer»); horario real (las salidas son por la mañana) | nueva | t1 muy bien (repaso, corte tal cual, «no hay salida por la tarde»); t2 recogida dos veces, «how many people?» tras «book me» | t1 muy bien (repaso con precio, corte tal cual, sin tarde); t2 recogida tres veces y «how many people?» tras «book me» |
| 9 | Grupo de 8 colombianos: 5 certificados y 3 que nunca han buceado; uno toma pastillas para la tensión; regatean y quieren pagar en efectivo | Precio, descuento y pago | La medicación sale como aviso o pase a un asesor (seguridad); el descuento de grupo (5+) sin inventar otros; el pago de colombianos (anticipo con asesor); sin total del grupo | nueva | t1 sin saludo (pase), bloque de descuentos y requisitos sin pedir, sin reparto | t1 pase por la medicación y descuentos bien (efectivo sin descuento); lo médico dos veces, 4 planes y qué llevar sin pedirlo, sin reparto |
| 10 | Pareja que cambia de idea: snorkel → minicurso → cambia la fecha → pide el enlace | Reservar sin perderse | Cada cambio corrige lo guardado (actividad, fecha) sin preguntar «¿lo cambio?» cuando lo dice claro; el enlace es el del minicurso | nueva | t1 perfecto (4 s); t2 no cambia la actividad y el cambio de fecha sin reserva va al asesor | t1 perfecto (3 s); t2 no cambia la actividad y el cambio de fecha sin reserva va al asesor |
| 11 | Buzo Open Water que quiere el Advanced y la especialidad Nitrox; sale de Cartagena; fecha concreta | Días, alojamiento, precio de los dos | Los días del curso y la noche en las islas (alojamiento no incluido); el precio de cada uno; el Nitrox como especialidad aparte | nueva | t1 contenido bien; dos preguntas (enlaces + «¿Te animas?»), sin guardar los dos cursos | t1 contenido bien y sin «¿Te animas?» (mejor); la pregunta en medio y un párrafo suelto del punto de encuentro; sin guardar los dos cursos |

Las personas 1 a 7 salen de `hallazgos.md` (CALN1-01..04 y CALN2-01..07). Las 8 a 11 son nuevas: cubren temas que la
batería no tenía (inglés con faltas en las islas, seguridad y regateo en grupo grande, cambios de idea, cursos).

**Primera tanda (27-oct, feature/caln-gadea b0f3a97):** hallazgos CALN3-01..14 en `hallazgos.md`, charlas
`docs/robustness/g3/charlas-rama/b*.jsonl` y los casos en `docs/robustness/caln/banco-sparring.json` (10 diálogos,
puntuados por código con `scripts/puntua_banco_edades.py`).

**Segunda tanda (27-oct, feature/caln-gadea c1be0e4, con CALN-2 lectura, CALN-6 2d y el plan):** las mismas once
personas, con el mismo primer mensaje (charlas `docs/robustness/g3/charlas-rama/b*-t2.jsonl`, 22 turnos). Hallazgos
CALN4-01..12 en `hallazgos.md`; casos nuevos s11..s14 en `banco-sparring.json`.
