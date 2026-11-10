# Bloque 4R: el momento de reservar (diseño, 10-nov; v2 tras la revisión)

**Ficha:**
- **Rama:** 4R, en `feature/bloque4r-alvaro`, sobre `bloque31-gadea` 69aa7228. Es el cierre del 0,5 (#3702) y el 4R de #3721.
- **Mecanismo:** en la reserva, lo que se le da al cliente lo decide **una sola función** del código antes de escribir, y lo **pinta un
  solo pintor**. Las opciones son el enlace, el asesor, el hotel primero o el origen primero. El escritor no recibe enlaces de reserva
  ni la orden de ofrecer el pase.
- **Familias:**
  - el enlace con el origen sin saber;
  - el grupo, una parte sin enlace o un colombiano que reciben el enlace;
  - el pase que ofrece el escritor, también repetido;
  - la recogida fuera de los puntos de siempre;
  - el código que rompe sus propios enlaces;
  - el equipo propio y el horario (4R-2).
- **Banco:** sin IA, `tests/test_bloque4r.py`. **Contador:** `[CORE][4R]`.

**v2 (10-nov):** un agente revisó la v1 contra el código, sin mi conclusión. Comprobé los puntos que cambiaban algo (D1, D2 y D4, en el
código). Lo que cambia:
- **D1.** `catalog_booking_links` y la línea «Reserva:» de las fichas **no se tocan**: el juez las lee (`judge_golden_set.py:182-195`) y
  cambiaría la huella. Los urls se quitan solo de lo que recibe el escritor.
- **D2.** Con el origen sin saber, el pintor pide la pieza de los dos precios (`_con_la_pieza` solo actúa con un importe o con
  `pieza_pedida`, `origen_precio.py:344`).
- **D3.** `acepta_la_oferta_del_asesor` se queda como está (`tests/test_acepta_el_pase.py`, #3570). Si no, un «sí» a una oferta del
  escritor se perdería. En su lugar, un contador.
- **D4.** El pintor no va en `componer`, que corre después del pase (`supervisor.py:204-262`), sino donde el núcleo cierra la respuesta.
  La puerta va en el bucle del escritor.
- **D5.** El código rompe también sus propios enlaces (la nota del refresher y `con_la_pieza`): entra en el 4R.
- **D6.** Nueva pregunta a Gadea, P5: el orden entre el origen primero y el asesor.
- **D7 y D8.** Se quedan las constantes de `como_reserva` y la forma de `hechos["enlace"]`; se añade una clave nueva.
- **D9.** La recogida: la función es mía, y la llamada desde `decidir_pase` (`rutas/safety.py:153`) la pone el Claude de Gadea en su
  fichero.
- **El saldo, honesto:** dos pasos. 4R-1 cubre y cuenta; 4R-1b borra los correctores que el contador deje a cero.

No se tocan plan, importe ni moneda (2a y 2b); se usan sus piezas como están. Lo breve es del Claude de Gadea (#3732): no se toca
`brand_tone.json` ni `_build_tone_section`. De los ficheros del 4P no se toca ninguno.

## Lo que hay que cumplir (decisiones de Gadea)

| Situación | Qué hace el bot | Decisión |
|---|---|---|
| Quiere reservar y se sabe el origen | El enlace de su salida | `pago-y-reserva` |
| Quiere reservar y no se sabe el origen | Ningún enlace; los precios de cada salida con su rótulo y la pregunta del origen | #3701 b, #3738 (1), con `origen-y-precio` |
| …y sigue sin decirlo | Una vez más, con el motivo («para darte el enlace necesito saber desde dónde sales»); si no, asesor | #3742 (P1b) |
| Colombiano o residente | Sin enlace de la web: un asesor para el pago. Un grupo mixto, sí recibe el enlace | `pago-y-reserva` |
| Nacionalidad sin saber tras 2 preguntas | El enlace y «si eres colombiano o tienes cédula de extranjería, dímelo y te paso con un asesor» | #3741 (P2) |
| Grupo de 5 o más, o una parte sin enlace | Con un asesor antes del enlace | `grupo-por-el-asesor` (P9/P10) |
| Un plan que va con asesor y aún no pidió reservar | El código lo dice una vez, sin pregunta, y pasa cuando quiera reservar | #3741 (P3) |
| Islas sin hotel | Ni enlace ni asesor: que reserve el hotel y vuelva | `hotel-antes-de-reservar` |
| Casa, Airbnb u hotel fuera de la lista | Un asesor confirma la recogida antes de reservar | `hotel-antes-de-reservar`, `fuera-de-la-base` |
| Equipo propio completo, u otro horario | Con un asesor (pase directo para el horario) | `equipo-propio-por-el-asesor`, #3741 (P4); 4R-2 |

## Cómo está hoy (comprobado en el código; la revisión, entre paréntesis)

**M1. El escritor tiene todos los enlaces, en cada llamada.**
- `rag_agent.py:781-783` suma `catalog_booking_links` al prompt de sistema, con los dos orígenes (confirmado).
- Además le llegan urls por:
  - las fichas con «Reserva: url» (`catalog.py:318-321`);
  - los hechos (`hechos.py:322-345`; con el origen sin saber, el de Cartagena);
  - el historial (`rag_agent.py:913-915`);
  - el contexto de la guarda (`rag_agent.py:503-517`);
  - el resumen de la charla (`contexto_rag.py:244-252`).
- Los prompts empujan a compartir el link: RAG_BODY 174/218 y 185/230, la instrucción de `por-otros` y `contexto_rag.py` 348-350 y 364-366.
- Contraórdenes sueltas: el colombiano (`contexto_rag.py:574-577`), `RAG_SIN_PRECIO` (`info.py:476-489`) y RAG_BODY:185, que dice
  «NUNCA digas que un asesor enviará el enlace de pago» y choca con el colombiano.
- **El juez lee la misma lista y las mismas fichas** (`judge_golden_set.py:182-195`, comprobado), igual que las sondas
  `sonda_juez_grounding` y `sonda_juez_asesor`.

**M2. La decisión tiene un centro (`como_reserva`, `como_reserva.py:69-83`) que no mira el origen, y caminos que lo esquivan.**
- Hacen su propia versión:
  - `hechos.py:338-342`;
  - las ramas del colombiano en `_finalize` (`slotfill_close.py:278, 300`);
  - `_refresher_note` (162-180);
  - `_tras_la_tarjeta_ya_vista` (93-97): ofrecería el asesor también con HOTEL_PRIMERO.
- No la llaman:
  - la tarjeta rehecha (`extraction.py:759-765`), que también da enlaces web a un colombiano;
  - el redactor con el origen pendiente (`redactor_hechos.py:230-237` y 358-362; vuelve sin la puerta, `conversational_core.py:897-899`);
  - `_dos_variantes` (`origen_precio.py:277-280`), desde `_origen_antes_del_precio` y `compositor._las_dos_salidas` (158-171): tras dos
    preguntas del origen, los dos enlaces. Lo fijan `tests/test_053b_sin_tercera_vez.py`.

**M3. Recortes después de escribir (todos confirmados):**
- `origen_precio._con_la_pieza` 387-395;
- `_origen_antes_del_precio` 102/104/112/134;
- `escalation_agent._contestar_lo_demas` 147-172, que esquiva la puerta;
- compositor 66-105;
- los textos que dan por dados los enlaces (`ORIGEN_TRAS_LOS_ENLACES_*`, `SIN_ENLACE_DE_LAS_ISLAS_*`, `origen_precio.py:221-233`).

**M4. El pase lo ofrece el escritor, porque se lo pedimos.**
- `RAG_PASE_OFRECIDO` (`info.py:437-448`) va en `reglas_del_escritor`, en todas las llamadas.
- RAG_BODY 193-198/238-243 dice «intención concreta de reservar/pagar… lo cierra el equipo».
- `acepta_la_oferta_del_asesor` (`supervisor.py:569-582`, regex 75-80) acepta cualquier oferta, también la del escritor. Es a propósito
  (#3570, `tests/test_acepta_el_pase.py`, `setup.py:203-206`).
- En `panel-vara` (bloque 1, 3 tiradas) el escritor ofrece el pase a 8-11 clientes por tirada: visto-6898, 6901, 6929, 6930, 6934 y 6940
  (este, tres turnos seguidos). Lo cuenta `C:/t/medidas/4r/mecanismo4r.py`; la revisión no lo repitió.

**M5. Decisiones sin código.**
- Sin lectura del mensaje: el equipo propio (`discounts.json`, `info.py:167`) y el horario (`hechos.py:600`).
- La recogida (`slotfill_close.py:353-370`): solo islas y solo en el cierre; con la reserva hecha no corre (`availability.py:33`).

**M6. La nacionalidad y el número se saltan tras 2 preguntas** (`que_preguntar.py:30`, `slotfill_close.py:585`, cantidad 1 en 151).

**M7. El código rompe enlaces, también los suyos** (ejecutado por mí y por la revisión).
- `compositor._una_oferta_del_asesor` (313-337) deja `https://book.divingplanet.language=es`.
- Le pasa también a la nota del refresher dentro de la tarjeta del grupo (`slotfill_close.py:169, 296-298`). El grupo, además, no debía
  recibir ese enlace.
- `redactor_hechos.con_la_pieza` (248-252) parte un url con «?».
- `if not oferta:` (323) se salta una oferta en la posición 0.

## El cambio

**4R-1: cubrir y contar.**

**C1. Una decisión: `entrega(state, pedidas)` en `como_reserva.py`.**
- Pura. Se quedan las constantes de hoy (HOTEL_PRIMERO, ASESOR para el colombiano, RECOGIDA_POR_CONFIRMAR, GRUPO, PARTE_SIN_ENLACE,
  ENLACE) y se añade **ORIGEN_PRIMERO**.
- Devuelve la forma, el motivo y los urls que tocan, solo del origen sabido; el de las islas, solo con hotel.
- Con la nacionalidad sin saber tras 2 preguntas, ENLACE con la marca de P2.
- Pasan por ella:
  - `hechos.py:322-345`;
  - `_finalize`, `_refresher_note` y `_tras_la_tarjeta_ya_vista`;
  - la tarjeta rehecha;
  - el redactor;
  - `_dos_variantes` y `_las_dos_salidas`, que ya no dan enlaces sin origen: P1b.
- `como_reserva()` se queda como la parte sin el origen, para quien la lee hoy (`hechos.py:472`, compositor, core y 13 tests).
- **La recogida (#3723):** `recogida_por_confirmar(state)` en `como_reserva.py`, sacada de `slotfill_close.py:353-370`. El Claude de
  Gadea la llama desde `decidir_pase`.

**C2. El escritor no recibe urls de reserva, en ningún turno (opción A).**
- Se quitan donde se monta lo que lee el escritor:
  - la lista del prompt (deja de sumarse en `rag_agent.py:783`; queda una línea sin urls con los planes que reserva un asesor);
  - las fichas recuperadas;
  - los hechos: se quita el url y se añade `entrega: <forma>`; `enlace: {"asesor": True}` sigue igual;
  - el historial;
  - el contexto de la guarda;
  - el resumen.
- `catalog_booking_links` y `service_fact_sheet`, sin tocar (D1).
- Los que leen los hechos se ajustan: `hechos.faltan` (763-765), `_cubierta` (132-133) y el redactor (359-360).
- Fuera las frases que empujan a compartir el link y la de RAG_BODY:185.
- **Por qué A y no B:** `_turno_de_la_reserva` es falso en el primer turno («quiero el link del snorkel»), tras la tarjeta y tras un pase
  (`conversational_core.py:982`, `slotfill_close.py:270`). B deja el enlace con dos dueños justo donde se repiten el grupo y el
  colombiano.
- A llega también a turnos del 4P (posventa): **hace falta el sí del Claude de Gadea.**

**C3. Un solo pintor: `pintar_la_entrega`, donde el núcleo cierra la respuesta del turno, antes del pase del supervisor.**
- Lo llaman `_finalize`, para la tarjeta y su pase, y los dos sitios por donde sale la respuesta del escritor en el núcleo:
  - la puerta del origen (`_con_la_puerta`, 924-938, y `_take_parallel_answer`, 1110-1113);
  - el redactor (897-899).
- Pinta si las intenciones del turno (`state._intenciones`, `graph.py:201`) piden enlace, pago o disponibilidad, o en el cierre:
  - **ENLACE:** el url con su llamada, más la línea de P2 si toca;
  - **ORIGEN_PRIMERO:** la pieza de los dos precios (`_con_la_pieza(..., pieza_pedida=True)`) y la pregunta del origen. Si quiere
    reservar y ya se preguntó dos veces, la de P1b; si no la contesta, pase.
  - **ASESOR, GRUPO, PARTE_SIN_ENLACE o RECOGIDA:**
    - si pide reservar o pagar, `pasar_a_persona` con el motivo y el porqué;
    - si no, una vez «este plan se reserva con un asesor, por…» (P3). Lleva su clave en `preguntas_hechas`, para que no se repita.
  - **HOTEL_PRIMERO:** `hotel_before_booking`.
- Los textos del colombiano y la recogida (`por_que_el_asesor` hoy devuelve None) se escriben en español e inglés.
- **La puerta (norma 5), en el bucle del escritor** (`rag_agent.py:956-1050`, donde `urls_grounded` ya rehace): cualquier url de
  `book.divingplanet.org` en la respuesta se rechaza y se rehace una vez. Si vuelve, la plantilla: lo que pinta la entrega, sin el texto
  del escritor. Contador.

**C4. El pase, sin la orden al escritor; el «sí» se sigue aceptando.**
- Con un plan en curso (actividad o carrito, y no posventa), el escritor no recibe `RAG_PASE_OFRECIDO` ni RAG_BODY 193-198/238-243. Es
  una condición en `reglas_del_escritor`, no un borrado (#3740).
- `acepta_la_oferta_del_asesor`, sin tocar.
- Contador `escritor_ofrece_el_pase` en la reserva. Si no baja a cero, en 4R-1b la puerta lo vigila también.

**C5. Los enlaces que rompe el código (M7):**
- se enmascaran los urls antes de buscar preguntas en `_una_oferta_del_asesor` y en `con_la_pieza`;
- `_refresher_note`, por `entrega`;
- arreglado el `if not oferta:`.

**C6. La regla, en el juez (norma 7):**
- propongo los textos de `origen-y-precio` (el enlace), `sin-tercera-pregunta` (la excepción de P1b) y `por-otros` («su enlace»);
- los mete el Claude de Gadea en su próximo cambio de referencia, para que A y B se juzguen con la misma.

**4R-1b: borrar** lo que el contador de 4R-1 deje a cero en el mecanismo ×5 y en el panel y la tanda del cierre del 4 (norma 6):
- los cortes de enlaces de `origen_precio` (387-395, la rama de enlace de `_origen_antes_del_precio` y los urls de `_dos_variantes`);
- los textos que los daban por dados;
- en el compositor: `_sin_enlaces_repetidos`, `_sin_enlaces_de_reserva`, `_sin_estos_enlaces`, `_una_oferta_del_asesor` y la parte de
  enlaces de `_las_dos_salidas`;
- `_con_los_enlaces_que_faltan`;
- la contraorden del colombiano.

**4R-2 (diseño aparte):** el equipo propio y el horario, con una lectura del mensaje (Jev o el extractor).

## Lo que decide Gadea (negocio)

- P1, P1b, P2, P3 y P4: decididas (#3738, #3741 y #3742).
- **P5 (nueva):** con el origen sin saber, un colombiano o un grupo de 5 o más que quieren reservar, ¿primero el origen (puede estar
  en las islas sin hotel, y `hotel-antes-de-reservar` prohíbe pasarlo) o directamente el asesor?
- **Al Claude de Gadea:** el sí a la opción A en los turnos de posventa.

## Cómo se prueba y se mide

- **Banco sin IA (`tests/test_bloque4r.py`):**
  - `entrega` en todas las combinaciones: origen sabido o no, colombiano, nacionalidad sin saber, grupo mixto, número, partes con y sin
    enlace, islas con hotel de la lista, fuera de ella o sin hotel, y plan sin enlace;
  - ningún url de reserva en lo que lee el escritor (prompt, fichas, hechos, historial, guarda y resumen), en turnos de reserva, de
    pregunta, del primer mensaje y tras la tarjeta;
  - lo que pinta el pintor, por forma, en español e inglés, en singular y en plural;
  - la puerta rechaza un url y rehace;
  - un url pasa intacto por el compositor y por `con_la_pieza`, también los que pinta el código;
  - la recogida en los dos caminos;
  - la tarjeta rehecha.
- **Tests que cambian porque cambia una decisión:** `test_053b_sin_tercera_vez` (los dos enlaces tras dos preguntas),
  `test_caln35_como_reserva`, `test_arq1u_enlace` y `test_caln18_una_oferta_del_asesor`. `test_acepta_el_pase` no cambia.
- **Mecanismo ×5 con `reproducir_juez_pre --codigo-local`, sin juez:**
  - `panel-vara` visto-6898, 6901, 6929, 6930, 6934 y 6940;
  - la tanda b0a-10 y b0b-10;
  - caln35, caln39 y graves ×1.
  - Antes de cada medida, los dos saldos y Coral: OpenAI se comparte con PRE.
- **Meta:**
  - 0 enlaces con el origen sin saber;
  - 0 grupos y 0 colombianos con el enlace;
  - 0 enlaces rotos;
  - las ofertas del escritor en la reserva a cero, o contadas;
  - caln35 22/22.
- El juez puede marcar la pregunta de P1b como tercera vez hasta que cambie la referencia.
- **El panel, al cerrar el 4** (con el 4P), en `panel-vara`: una bajada cuenta si es de 3.

**Saldo (realista):**
- **4R-1:** entre +20 y +40.
  - Suma: la entrega, el pintor, la puerta, los textos (5-7 motivos × 2 idiomas) y quitar los urls en 6 sitios.
  - Resta: la copia de `hechos`, las ramas del colombiano, la lista del prompt y las frases de prompt.
- **4R-1b:** entre −120 y −150. El bloque queda negativo al cerrar.
- Si el contador no deja borrar los correctores, el bloque no cierra con saldo negativo, y se dice.

**Riesgos:**
- El escritor sin url escribe «aquí tienes el enlace:» y nada: el pintor tiene que pintar siempre que los hechos digan una forma.
- Si Jev no marca la intención, no se pinta: se mide en el mecanismo.
- `_reserva_nueva_en_curso` (`availability.py:21-30`) usa «un enlace en el historial» como señal. Los enlaces que pinta el código
  siguen ahí.
- `escalation_rules.json` complex_logistics («coordinación con agencias») choca con `por-otros`: es del juez y lo ve el Claude de Gadea.
