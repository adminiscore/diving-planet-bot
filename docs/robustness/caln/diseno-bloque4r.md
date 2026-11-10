# Bloque 4R: el momento de reservar (diseño, 10-nov; v1, antes de la revisión)

**Ficha:**
- **Rama:** 4R, en `feature/bloque4r-alvaro`, sobre `bloque31-gadea` 69aa7228. Es el cierre del 0,5 (#3702) y el 4R de #3721.
- **Mecanismo:** en la reserva, lo que se le da al cliente (el enlace, los de cada salida con su rótulo, el asesor, el hotel primero o
  una pregunta) lo decide **una sola función** del código antes de escribir, y lo **pinta el código**. El escritor no recibe enlaces de
  reserva ni ofrece el pase.
- **Familias:**
  - el enlace con el origen sin saber;
  - el grupo, una parte sin enlace o un colombiano que reciben el enlace;
  - el pase que ofrece el escritor, también repetido;
  - la recogida fuera de los puntos de siempre;
  - el equipo propio y el horario que no es el de siempre.
- **Banco:** sin IA, `tests/test_bloque4r.py`. **Contador:** `[CORE][4R]`.

No se tocan los ficheros del 4P (`jev_router`, `safety`, `availability`, `changes`) ni plan, importe ni moneda (2a y 2b). Lo breve es
del Claude de Gadea (#3732): no se toca `brand_tone.json` ni `_build_tone_section`.

## Lo que hay que cumplir (decisiones de Gadea)

| Situación | Qué hace el bot | Decisión |
|---|---|---|
| Quiere reservar y se sabe el origen | El enlace de su salida (lo pinta el código) | `pago-y-reserva` |
| Quiere reservar y no se sabe el origen | Ningún enlace: los precios de cada salida con su rótulo y la pregunta del origen | #3701 b y #3738 (1), con `origen-y-precio` (**el enlace aún no está en `decisiones.json`**) |
| Colombiano o residente | Sin enlace de la web: pasa con un asesor para el pago. Un grupo mixto, sí recibe el enlace (USD) | `pago-y-reserva` |
| Grupo de 5 o más, o una parte sin enlace | Con un asesor antes del enlace | `grupo-por-el-asesor` (P9/P10) |
| Sale desde las islas sin hotel | Ni enlace ni asesor: que lo reserve y vuelva con el nombre | `hotel-antes-de-reservar` |
| Casa, Airbnb u hotel fuera de la lista | Un asesor confirma la recogida antes de reservar | `hotel-antes-de-reservar`, `fuera-de-la-base` |
| Trae su equipo completo (5 %) | Con un asesor antes de pagar | `equipo-propio-por-el-asesor` |
| Pide otro horario | Los horarios son fijos; un ajuste lo revisa un asesor | política `schedule_not_adjustable`; `escalation_rules.json` complex_logistics (#3738 (4), Gadea lo confirma) |
| La misma pregunta (también la oferta del pase) | Nunca una tercera vez | `sin-tercera-pregunta` |

## Cómo está hoy (comprobado en el código)

**M1. El escritor tiene todos los enlaces, en cada llamada.**
- `rag_agent.py:781-783` suma `catalog_booking_links` (`catalog.py:678-701`) al prompt de sistema: todos los servicios con enlace, de
  los dos orígenes. No mira el origen, el grupo ni la nacionalidad.
- Las fichas de la base llevan la línea «Reserva: url» (`catalog.py:318-321`, construidas por `scripts/kb_v2.py`).
  `fichas_del_origen` (`rag_agent.py:436-484`) deja solo la del origen cuando se sabe.
- Los hechos con la intención enlace, pago o disponibilidad llevan el url (`hechos.py:322-345`). Con el origen sin saber, el de
  Cartagena, y el de las islas solo con el hotel.
- El historial con tarjetas anteriores (`rag_agent.py:913-915`).
- Los prompts lo empujan:
  - «si el link está en el contexto, compártelo» (`info.py` RAG_BODY 174/218, 185/230);
  - la instrucción de `por-otros`: «dale … el enlace de su plan»;
  - `contexto_rag.py` 348-350, 364-366 y 614-616.
- La única contraorden es para el colombiano (`contexto_rag.py:574-577`, en español también en inglés) y la reescritura sin precio
  (`info.py:476-489`).
- La guarda de URLs (`grounding_check.py:271-284`) solo mira que el url esté en el contexto, y todos lo están.

**M2. La decisión está copiada y no mira el origen.**
- `como_reserva()` (`como_reserva.py:69-83`) devuelve HOTEL_PRIMERO, ASESOR, RECOGIDA_POR_CONFIRMAR, GRUPO, PARTE_SIN_ENLACE o
  ENLACE. Con el origen sin saber da ENLACE.
- Tiene copias o caminos que no pasan por ella:
  - `hechos.py:322-345`;
  - las ramas de `_finalize` (`slotfill_close.py:294-336`);
  - `_refresher_note` (`slotfill_close.py:162-180`): da el url salvo al colombiano, sin `como_reserva`;
  - la tarjeta rehecha tras el cierre (`extraction.py:759-765` → `goto_final_summary`): sin `como_reserva` ni el colombiano;
  - el redactor añade «• Desde Cartagena: url» con el origen pendiente (`redactor_hechos.py:230-237`, aplicado en 358-362), y
    esa respuesta vuelve sin la puerta del origen (`conversational_core.py:897-899`);
  - `_dos_variantes` (`origen_precio.py:277-280`).

**M3. Los recortes después de escribir: no ven todos los caminos y uno rompe enlaces.**
- `origen_precio._con_la_pieza` (330-402) corta frases con enlace solo si hay un precio y el origen no está en los bloques (387).
- `_origen_antes_del_precio` (96-157) sale sin tocar nada en 102, 104, 112 y 134: basta con que el cliente haya escrito «Cartagena» o
  «islas» en algún mensaje.
- `escalation_agent._contestar_lo_demas` (147-172) llama al RAG sin esa puerta.
- El compositor quita enlaces solo si `como_reserva` ≠ ENLACE (`_sin_enlaces_de_reserva`, 95-105), y nunca mira el origen.
- `compositor._una_oferta_del_asesor` (313-337) quita las preguntas de delante con `_PREGUNTA_RE` (31). Ese patrón casa con
  «org/book/<x>/<n>?» dentro del url. **Ejecutado:** deja `https://book.divingplanet.language=es`, que ya no reconoce
  `_ENLACE_DE_RESERVA_RE`.
- Con la norma 5 (una puerta que no edita), estos recortes son lo que hay que dejar de necesitar.

**M4. El pase lo ofrece el escritor, porque se lo pedimos.**
- `RAG_PASE_OFRECIDO` (`info.py:437-448`, en `reglas_del_escritor`, todos los turnos): «OFRÉCELO como pregunta ("¿Quieres que te pase
  con un asesor del equipo?"): si el cliente acepta, el sistema hace el pase».
- `acepta_la_oferta_del_asesor` (`supervisor.py:569-582`, regex 75-80 sobre el último mensaje del bot) convierte en pase el «sí» a
  cualquier oferta, también la del escritor.
- **En `panel-vara`** (bloque 1, 3 tiradas, `C:/t/medidas/4r/mecanismo4r.py`): el escritor pregunta si le pasa con un asesor a 8-11
  clientes por tirada (13-15 turnos), siempre en turnos `rag`. Ejemplos:
  - visto-6898 (grupo de 7) y visto-6929 (grupo de 6);
  - visto-6901 (equipo propio);
  - visto-6930 (Airbnb en Isla Grande);
  - visto-6940 (paquete de 4, sin enlace: tres turnos seguidos);
  - visto-6934 (la fecha).
  En casi todos, la decisión ya dice que pasa con un asesor, sin preguntar.
- El enlace con el origen sin saber: 1 cliente por tirada, y en la tanda de la vara b0a-10 y b0b-10 (#3715).

**M5. Decisiones sin código.**
- El equipo propio vive solo en `discounts.json` y en el prompt (`info.py:167`).
- El horario, en la política que se pega a `horario_general` (`hechos.py:600`).
- La recogida fuera de los puntos (`_recogida_por_confirmar`, `slotfill_close.py:353-370`) solo vale para las islas y solo en el cierre:
  con la reserva hecha va a posventa (`availability.py:33`) y no corre (#3723).
- Ninguna de las tres tiene una lectura (señal) del mensaje hoy.

**M6. La nacionalidad y el número se saltan tras 2 preguntas** (`que_preguntar.py:30`, `slotfill_close.py:585`): la tarjeta sale con
`is_colombian=None` y da ENLACE, o con 1 persona y no ve el grupo.

## El cambio

**C1. Una sola decisión: `entrega(state)` en `como_reserva.py`.**
- Pura: decide, no pinta ni pasa a nadie. Absorbe `como_reserva()`.
- Devuelve la forma y los enlaces que tocan:
  - `ENLACE`: un url, el del origen sabido;
  - `ORIGEN_PRIMERO`: origen sin saber, ningún enlace; la pregunta del origen la pone la tabla de qué preguntar (P11) y los precios de
    cada salida, `origen-y-precio` (2a, sin tocar);
  - `ASESOR`, con el motivo: colombiano, grupo, parte sin enlace o plan sin enlace, recogida por confirmar, equipo propio, horario;
  - `HOTEL_PRIMERO`.
- Llaman a esta función, en vez de a sus copias:
  - `hechos.py:322-345`;
  - `_finalize` y `_refresher_note`;
  - la tarjeta rehecha de `extraction.py:759-765`;
  - el redactor (358-362);
  - `_dos_variantes`.
- **La recogida (#3723):** `recogida_por_confirmar(state)` sale de `slotfill_close` a `como_reserva.py`. La llaman `entrega` y el
  `decidir_pase` del 4P.

**C2. El escritor no recibe enlaces de reserva.**
- Fuera `catalog_booking_links` del prompt. Queda una línea sin urls con los planes que reserva un asesor.
- Fuera los urls de reserva de lo que lee el escritor: las fichas recuperadas, los hechos y el historial. Se hace en el código al montar
  el contexto, así que no hace falta recargar `kb_v2` en el Postgres de PRE.
- En los hechos, `enlace` dice la forma y no el url: `{"lo_pone_el_codigo": "ENLACE" | "ORIGEN_PRIMERO" | "ASESOR" | "HOTEL_PRIMERO"}`.
- Fuera las frases que empujan a compartir el link. `por-otros` dice «su plan» y el enlace lo pone el código.
- **Opción A (propuesta):** en todos los turnos. Un enlace de reserva es, por definición, el momento de reservar, y así tiene un solo
  dueño.
- **Opción B:** solo en los turnos de reserva (`_turno_de_la_reserva`). Deja vivo el camino de «¿cómo reservo?» en un turno de pregunta,
  que es el de M2 y M4.

**C3. El código pinta la entrega, en un solo sitio: el final del turno (`compositor.componer`, donde ya pone la pregunta).**
- Cuándo: si el turno pide enlace, pago o disponibilidad (las `pedidas` de los hechos) o es el cierre. La tarjeta usa la misma
  `entrega`.
- Qué pinta, con textos fijos en español e inglés:
  - **ENLACE:** el enlace con su llamada.
  - **ORIGEN_PRIMERO:** nada de enlace; la pregunta del origen, si la tabla la deja (P1b tras dos sin respuesta).
  - **ASESOR:** si pide reservar o pagar, `pasar_a_persona` con el motivo y el porqué (`por_que_el_asesor`, `como_reserva.py:117-130`).
    Si no, según P3.
  - **HOTEL_PRIMERO:** la política `hotel_before_booking`.
- **La puerta (norma 5):** si la respuesta del escritor trae un url de reserva (no lo recibió), se rehace una vez; si vuelve, va la
  plantilla. Nunca se recorta. Lleva su contador.

**C4. El pase lo decide el código.**
- En la reserva, el escritor no recibe `RAG_PASE_OFRECIDO`. Ese texto también lo usa el 4P fuera de la reserva: se acuerda con el
  Claude de Gadea.
- `acepta_la_oferta_del_asesor` solo acepta nuestras ofertas (los textos fijos o una marca en el estado), no las del escritor.
- Nuestra oferta cuenta en la tabla de qué preguntar (`VECES_MAX`): nunca una tercera vez.

**C5. Los agujeros.**
- La tarjeta rehecha y la nota del refresher, por `entrega` (C1).
- La nacionalidad saltada, según P2.
- `compositor._una_oferta_del_asesor`, `_sin_enlaces_repetidos` y `_sin_enlaces_de_reserva` quedan con contador (norma 6). Se borran
  cuando lleven un panel y una tanda sin actuar. Con C2, el escritor ya no tiene urls que romper.

**C6. La regla nueva, a la vez en el juez, el banco y el código (norma 7).**
- «Nunca el enlace de un origen supuesto» entra en `decisiones.json`, en `origen-y-precio` o en una decisión propia, en el mismo
  cambio.
- Cambia la huella: lo coordino con el Claude de Gadea, dueño de la referencia, para el panel del cierre del 4.

**C7. El equipo propio y el horario (segundo paso, 4R-2, con su propio diseño).** Necesitan una lectura del mensaje que hoy no existe:
una pregunta de Jev, o un campo del extractor. Jev es fichero compartido y lo toca el 4P. No entra en el 4R-1.

## Lo que decide Gadea (negocio)

- **P1. El origen sin saber y quiere reservar:** decidido (#3738 (1)). Ningún enlace; los precios de las dos salidas y la pregunta del
  origen.
- **P1b. El origen sigue sin saberse tras dos preguntas** (`sin-tercera-pregunta`) **y quiere reservar:** ¿asesor, o sigue sin enlace
  hasta que lo diga? Sin preguntar a Gadea todavía.
- **P2. La nacionalidad sin contestar tras 2 preguntas:** hoy sale el enlace de la web, como a un extranjero. ¿Bien, o asesor? (se lo
  pregunta el Claude de Gadea, #3738)
- **P3. Un plan que va con asesor y aún no pidió reservar:** ¿el código lo dice una vez y pasa cuando quiera reservar, o pasa ya? (ídem)
- **P4. Pide otro horario al reservar:** pase con un asesor según la base del juez (`complex_logistics`); Gadea lo confirma (para el 4R-2).

## Cómo se prueba y se mide

- **Banco sin IA (`tests/test_bloque4r.py`):**
  - `entrega` en todas las combinaciones: origen (sabido o no), colombiano, grupo mixto, número, partes con y sin enlace, islas con hotel
    de la lista, fuera de la lista o sin hotel, y plan sin enlace;
  - ningún url de reserva en lo que recibe el escritor (prompt, contexto e historial), en turnos de reserva y de pregunta;
  - lo que pinta el código, por forma, en español e inglés;
  - solo nuestras ofertas se aceptan;
  - la recogida en los dos caminos, sin reserva y con la reserva hecha;
  - la tarjeta rehecha;
  - un url dentro de una respuesta pasa por el compositor sin romperse.
- **Mecanismo, ×5 con `reproducir_juez_pre --codigo-local` y sin juez:**
  - de `panel-vara`: visto-6898, 6901, 6929, 6930, 6934 y 6940;
  - de la tanda: b0a-10 y b0b-10;
  - los bancos caln35, caln39 y graves (×1).
- **Meta:**
  - 0 enlaces con el origen sin saber;
  - 0 ofertas del pase escritas por el escritor, y ninguna tercera;
  - 0 grupos de 5 o más y 0 colombianos con el enlace;
  - 0 enlaces rotos;
  - caln35 22/22.
- **El panel, al cerrar el 4 entero** (con el 4P), en `panel-vara`: una bajada cuenta si es de 3 o más.

**Saldo previsto (a comprobar al escribir):**
- Se borra:
  - `catalog_booking_links` y su llamada (~25);
  - la copia de `hechos` (~20);
  - las ramas de `_finalize` (~20);
  - los cortes de enlaces de `origen_precio` (~25);
  - `_con_los_enlaces_que_faltan` (~13);
  - las frases de prompt con enlaces y la contraorden del colombiano (~15);
  - `RAG_PASE_OFRECIDO` en la reserva (~12).
- Se añade: `entrega` (~45), lo que pinta (~35), la puerta (~20) y los textos (~20).
- Neto: entre −40 y −60 en el 4R-1, y unas −60 más cuando salgan los correctores del compositor (C5).

**Riesgos:**
- El escritor, sin el url, puede escribir «aquí tienes el enlace:» y nada más: la entrega tiene que pintarse siempre que los hechos
  digan una forma, y la puerta lo vigila.
- Quitar los urls de las fichas no debe quitar el resto de la ficha.
- `RAG_PASE_OFRECIDO` fuera de la reserva es del 4P: no se toca allí sin acuerdo.
