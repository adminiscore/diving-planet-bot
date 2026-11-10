# Plan V1: llegar a «robusto» quitando piezas, sin el bucle de parches (borrador v4, 10-nov)

**Historia del borrador:**
- **v1 y v2:** del Claude de Álvaro (#3793-#3799).
- **v3:** del Claude de Gadea, a petición de Gadea, con su segunda revisión independiente (#3800).
- **v4:** recoge la revisión independiente de la v3 y las decisiones de Gadea del 10-nov entre las 21:50 y las 22:25. Lo que
  afirmaba la revisión sobre el código y la memoria del equipo está comprobado.

La revisa el Claude de Álvaro.

El diagnóstico del análisis (`docs/plan/analisis-por-fases.md`) se queda (§7). Los bloques se retiran como forma de trabajar.

## 1. Por qué un plan nuevo

- **Del 21-oct al 10-nov:** unas 60 versiones y 5 bloques. Los mecanismos caían, pero los graves no: 8,2 → 7,5 de 40.
- **El panel de 40 mide sobre todo azar** (#3786). En el panel-vara, con 6 juicios por sistema:
  - A (antes de los bloques) 8,2, B 7,5, V1 7,5 y V2m 8,5;
  - solo 1 cliente falla en los cuatro: visto-6914, el vuelo;
  - 14 no fallan nunca y 25 fallan a veces;
  - el juez se contradice con la misma respuesta en 5-11 de cada 120 juicios (4-9 %).
- **Con clientes que reaccionan, el reparto es otro:** 21 de 71 tuvieron grave (30 %), y pesan más las horas y las fechas (análisis,
  «Lo que falla en nuestra vara»).
- **Luna no repite:** con el prompt idéntico y temperatura 0 salen 4 o 5 textos distintos de 5 (análisis, Fase 2). Un fallo visto una
  vez puede ser azar.
- **La raíz del bot** (análisis, Fases 1-5): varias piezas piensan sobre lo mismo y ninguna es dueña.
  - Hay cuatro lectores del mismo mensaje.
  - El redactor también decide, y con información vieja.
  - El código le cambia el texto en el 68 % de los turnos.
  - El plan se decide en ~12 sitios y el pase en 17.
  - Los bloques no quitaron a nadie de pensar: añadieron funciones que deciden encima.
- **El bucle cambiaba de nombre y no de forma** (construir, medir, «es un detalle», arreglar, medir): pasó del código a las reglas del
  prompt y a la puerta. Álvaro lo paró dos veces el 10-nov.
- **Decidido por Gadea:**
  - V1 es la base y V2 y V2m quedan fuera;
  - solo se quitan piezas;
  - de momento solo Luna;
  - la calidad la comprueban los Claude (#3790, #3791, #3793).
- **Un límite que conocemos:** V1 lee la misma base que el juez (`scripts/simple_v1.py:53`, desde `load_reference`), lo que la
  favorece (análisis, Fase 5). B recibe 3 de las 22 decisiones. Por eso el examen se apoya en reales (F0) y en fichas cuya respuesta
  correcta calcula el código, no el juez.

## 2. La meta «robusto», fijada antes de empezar

| Medida | Meta | Sobre qué se cuenta |
|---|---|---|
| Clientes con grave | ≤ 10 % | El examen sin los 75 reales (F0), la media de sus tiradas, con la rúbrica cerrada en F0 |
| Importes | 0 mal | Contador **contra la ficha de cada cliente**: el precio por persona de su plan, con el descuento que le toca. Antes de la puerta |
| Enlace (plan, origen e idioma) e idioma de la respuesta | 100 % bien | Contador contra la ficha, antes de la puerta |
| p90 del turno | ≤ 7,5 s | Contador, en el examen |
| Largo mediano | ≤ 300 caracteres | Contador, en el examen |
| Primeras respuestas con pregunta | ≤ 50 % (fijada por Gadea, 10-nov) | Contador, en el examen |
| Pases | **Sin meta, pero se cuentan** (Gadea, 10-nov) | Contador contra la ficha: los pases indebidos y los que faltan |

- **La persona y las preguntas:** pregunta en el 16 % de sus primeras respuestas y en el 12 % de sus mensajes. El 23 % del análisis es
  sobre sus respuestas agrupadas en todos los turnos. Contado el 10-nov en `docs/robustness/golden-set/real-episodes.json`, con la
  primera respuesta del centro tras el primer mensaje del cliente y sin contar los enlaces.
- **Por qué contra la ficha y antes de la puerta:**
  - después de la puerta, el 0 y el 100 % salen solos;
  - contra el catálogo, un importe de otro plan pasaría, porque 16 cifras casan con más de un plan;
  - contra una lista de todos los precios con descuento, cualquier precio rebajado pasaría.
- **La confirmación:** cuando un examen cumple todas las metas, se repite una vez con la misma versión.
  - Si la confirmación también cumple, se presenta a Andrés.
  - Si falla, la versión no pasa y ese examen no se vuelve a repetir.
  - Con 200 clientes y 3 tiradas, la media baila unos ±1,4 puntos: una versión que de verdad está al 8 % pasa los dos exámenes ~85 %
    de las veces, y una al 10 %, ~25 %.
- **Si B ya cumple el 10 % en el examen,** se avisa a Gadea antes de seguir, porque la meta no distinguiría.
- **Si solo fallan las preguntas,** decide Gadea con las salidas cerradas de §5.2, nunca reescribiendo la regla.
- **Solo Gadea cambia una meta, y por escrito.**

## 3. La regla de diseño

```
el código calcula HECHOS ──▶ Luna lee, DECIDE y ESCRIBE (1 llamada) ──▶ la puerta COMPRUEBA hechos ──▶ cliente
```

- **Hecho antes:** un dato que el código sabe sin leer el mensaje de este turno. Aprobados por Gadea:
  - **el primer día que se puede reservar** (el cierre de las 4:30 y el de la noche): V1 ya lo recibe;
  - **la tabla de precios por persona con descuento:** para cada plan, su precio con cada descuento que le aplica según la base
    (`discounts.json`: el de grupo no vale en los cursos PADI ni se suma al de equipo propio; el de equipo propio no vale en el
    minicurso ni en el snorkel), calculada por código (Gadea, 10-nov).
    - **El código no elige cuál le toca al cliente:** eso lo decide Luna con sus filas y lo dice tal cual, sin hacer cuentas.
    - Los totales siguen prohibidos (`sin-totales`).
    - El descuento de grupo y el de equipo propio, además, pasan con un asesor antes de pagar (§4);
  - **la hora desde la que se puede volar tras cada plan** (`vuelo-hora`).
- **Regla:** una decisión de Gadea escrita como dato para Luna, una vez y desde la decisión (§4).
- **Comprobación después:** solo de hechos, sobre lo que Luna escribió:
  - **un importe** que no está en el catálogo ni en la tabla de precios con descuento;
  - **un enlace** que no es de un plan del catálogo o no lleva su idioma;
  - **el idioma** de la respuesta;
  - **el vuelo** (Gadea, 10-nov). Se compara la hora del vuelo que Luna apunta en «entendido» con la hora desde la que puede volar tras
    el plan, y con lo que dice su texto. No es un lector nuevo: usa lo que Luna entendió. Si Luna no apuntó vuelo, no se comprueba.

  **La puerta no comprueba conducta:** cuándo pasar, cuándo preguntar o las condiciones del enlace (colombianos, hotel, grupo). Eso son
  reglas para Luna. La puerta no lee «entendido» para decidir qué debería haber dicho Luna.
- **Si la puerta encuentra un fallo:** se rehace una vez, y **el motivo solo nombra el hecho** («X no está en el catálogo ni en los
  hechos»), sin instrucciones de conducta. Si vuelve a fallar, **sale el segundo texto y se cuenta como fallo** (Gadea, 10-nov).
  **La puerta nunca escribe, nunca decide, nunca recorta y no tiene plantilla.**
- **El idioma** lo fija Luna en «entendido» (`idioma`), con su fila (otro idioma → inglés). De ahí lo leen `_el_cierre`,
  `_respuesta_fallo_tecnico` y `lead_summary`. El detector de idioma (`language_detector.py`, una heurística más un LLM) es otro lector:
  se borra (propuesta, la confirma Gadea).
- **Si Luna no contesta** (error o sin saldo): el aviso técnico que ya existe (`_respuesta_fallo_tecnico`, `src/agents/supervisor.py`),
  que dice la verdad y pasa con una persona. No hay respaldo en otro modelo.
- **No entra nunca:**
  - otro lector o pensador;
  - un corrector que edite el texto de Luna;
  - una regla por un caso;
  - un regex sobre lo que dice el cliente;
  - una comprobación de conducta;
  - un segundo escritor.
- **Un hecho o una comprobación nuevos solo con una decisión escrita de Gadea**, nunca porque lo pida el sparring. `como_reserva` (de B)
  no se reutiliza, porque decide.

## 4. La tabla de decisiones, cerrada con Gadea antes de tocar el bot

**Una fila por decisión.** Entran:
- las 31 de `decisiones.json`;
- «breve y concisa» (9-nov), que no está;
- **las del 10-nov que aún no están en `decisiones.json`:**
  - las del 4R (#3736): la nacionalidad sin saber tras dos preguntas; un plan con asesor se dice una vez y pasa al reservar; el origen
    sin saber al reservar se pide una vez con su motivo (la excepción de `sin-tercera-pregunta`);
  - la P-a: lo que la base no tiene y no está en la lista de `fuera-de-la-base` pasa de verdad con una persona.

  Están en la memoria del equipo, rama `memoria`, `docs/plan/memoria.md:62-66`.

Cada fila dice:
- si es **regla** (con su texto para Luna; 19 no tienen `instruccion_es` y Luna leería el texto del juez);
- o si es **hecho antes** o **comprobación después**, y quién la escribe.

**Quién escribe una fila:** un agente que solo recibe la decisión de Gadea (su texto y su fecha), sin charlas, sin el panel y sin el
examen. La revisa otro agente contra la decisión.

**El prompt de V1 tampoco tiene reglas propias.** Antes de congelarlo, cada línea de conducta de `INSTRUCCIONES`
(`scripts/simple_v1.py`) se convierte en fila de la tabla o sale. Dos ya se sabe que no coinciden con una decisión:
- `:36`, «si algo no está o no se puede resolver aquí… pasas al cliente con una persona», se alinea con `fuera-de-la-base` y la P-a: según
  el tema, y lo que no está en la lista, con una persona;
- `:33`, «contestas en el idioma del cliente», se alinea con `idioma` (otro idioma → inglés).

«Una pregunta como mucho» y «unos 300 caracteres» son filas de «breve y concisa».

**Ya decidido por Gadea el 10-nov:**
- **El cambio de fecha:** sin una reserva hecha, se cambia la fecha sin asesor; con la reserva hecha, va al asesor. El texto de
  `cambio-de-fecha` (17-sep), que dice «antes de pagar, a un asesor», se reescribe.
- **El horario que no es el de siempre** (visto-6899): regla. La política `schedule_not_adjustable` («los horarios son fijos; un ajuste
  lo revisa un asesor») pasa con una persona. No es la P4: la P4 es «2 días desde las islas sin nocturna».
- **El cierre:** hecho antes, desde F1.
- **Los descuentos:** la tabla de precios por persona es un hecho (§3). La fila junta el descuento con `grupo-por-el-asesor` y
  `equipo-propio-por-el-asesor`: «di el precio por persona con el descuento que le toca, tal cual está en los hechos, y pasa con un asesor
  antes de pagar». Los totales son una regla (`sin-totales`).
- **El vuelo:** la hora desde la que puede volar es un hecho, y el vuelo del cliente se comprueba después (§3).
- **Reservar para otro:**
  - Un particular que reserva para otra persona (un regalo o un amigo), aunque ya sepa el plan y la fecha: el bot le da el precio por
    persona y, cuando quiere reservar, lo pasa con un asesor.
  - `por-otros` (el precio y el enlace, como a cualquiera) queda para las agencias y los instructores de otro centro.
  - La instrucción de `temas-3nov` vuelve a decir «regalo», para no mandar a las agencias al asesor.
- **La moneda, si quien paga y quien bucea son de distinta nacionalidad:** si hay un extranjero, todo en USD, como el grupo mixto.

**Lo que falta en la tabla:** los campos `en_el_bot`, que apuntan a piezas que F1 borra, se actualizan con ella.

**El prompt se congela con su huella.** Una fila cambia solo si cambia la decisión de Gadea, nunca por cómo la cumple Luna. **Cada fila
nueva o cambiada entra a la vez en la referencia del juez, y B se vuelve a juzgar con ella.**

## 5. Cómo trabajamos

### 5.1 Tres instrumentos, con papeles que no se mezclan

| Instrumento | Para qué | Para qué NO |
|---|---|---|
| **Sparring** | **Descubrir** familias de fallos y preguntas de negocio para Gadea | Para decir que algo mejoró, para añadir piezas ni para cambiar una fila |
| **Examen** | **Decidir** si una versión llega a la meta (§2) | Para buscar qué arreglar |
| **Contadores y banco sin IA** | **Vigilar** lo exacto y **comprobar** que un arreglo hace lo que dice | Para sustituir al juicio |

- **El examen lo corre un agente que solo devuelve las cifras de §2.** Las charlas y las razones del juez quedan fuera del repo, con su
  huella, y nadie las lee para arreglar nada.
- **El sparring:**
  - un Claude hace de cliente, nuevo cada vez, con la mezcla de los reales:
    - corto (31 caracteres de mediana) y en ráfagas (el 87 % de los episodios tiene alguna);
    - un tercio ya ha reservado;
    - un 11 % son agencias;
    - un 15 % pregunta lo que la base no contesta;
  - otro Claude, que no la escribió, lo juzga **dos veces** con la rúbrica y la hora. Un fallo cuenta si lo ven las dos pasadas;
  - corre **en local**, con el código de la rama (`charla_rama` o `--codigo-local`), y contra PRE por Chatwoot una vez por integración;
  - **los de casa ven un resumen y una muestra:** los peores y unos al azar (#3791).

### 5.2 Del fallo al arreglo

1. **La familia.** Un fallo se apunta en su familia. Una familia **pesa** si aparece en **3 o más charlas distintas** de un sparring de
   30, con las dos pasadas del juez de acuerdo. Por debajo, espera.
2. **¿Qué es?**
   - **Una regla que falta:** es una pregunta de negocio para Gadea. Si Gadea decide, entra como fila nueva, escrita como dice §4.
   - **Un hecho mal calculado:** se arregla el cálculo.
   - **Una comprobación de un hecho nueva:** solo con una decisión de Gadea.
   - **Luna no cumple una fila ya bien escrita:** **la fila no se reescribe.** Gadea elige entre cuatro salidas cerradas:
     - convertirlo en un hecho, si se puede calcular sin leer el mensaje;
     - una comprobación de un hecho;
     - aceptar la cifra tal cual;
     - probar otro modelo (Gadea, 10-nov: «si algo se complica, planteamos otras situaciones»).
   - **Si no es nada de esto, no se hace.**
3. **El diseño corto:** qué, por qué y qué borra. Lo revisa un agente independiente sin nuestra conclusión.
4. **El código**, con su banco sin IA y la suite. Otro agente revisa el diff contra el diseño.
5. **La comprobación del arreglo**, con su banco sin IA y los contadores. **No con el sparring.**
6. **La integración:** el examen, y una vez por PRE con Chatwoot.

### 5.3 Las señales del bucle, y qué se hace con cada una

| Señal | Qué se hace |
|---|---|
| Un examen de integración no mejora ninguna cifra más que su ruido (medido para cada cifra con las tiradas de B en F0; en graves, unos 4 puntos) y no cumple la meta | Se para. Se escribe «qué estamos haciendo mal» y se habla con Gadea y Álvaro antes de tocar nada |
| V1 en el bot (F1) sale peor que B en graves por más que el ruido | Se para y se habla con Gadea antes de seguir |
| Un arreglo necesita otro arreglo para no romper algo | Se revierte y se rediseña |
| Se ajusta una fila mirando el sparring o el examen, o una fila la escribe quien leyó la charla | **Prohibido** (§4) |
| Luna no cumple una fila bien escrita | Solo las cuatro salidas de §5.2 |
| Una pieza «comprueba», pero decide, escribe o lee lo entendido para juzgar la conducta | No entra: es un segundo pensador |
| Se añade un hecho o una comprobación sin una decisión escrita de Gadea | No entra |
| B y la versión nueva se miden con distinto arnés (ráfagas, relojes, referencia) | La comparación no vale |
| Se repite un examen de la misma versión para que salga | Prohibido. Solo vale el de confirmación al cumplir la meta |
| Alguien propone «¿y si añadimos…?» | Por defecto, no |
| Un Claude propone la siguiente versión sin mirar si la anterior movió algo | El otro Claude lo para (10-nov) |

### 5.4 Quién hace qué

- **Gadea** decide la tabla, las metas, qué entra y qué sube a PRE.
- **Álvaro** está informado de cada decisión y decide con Gadea lo de fuera (Andrés, los saldos).
- **Los dos Claude:**
  - proponen con datos y se revisan el uno al otro, cada diseño y cada diff con un agente independiente;
  - una medida a la vez en PRE, avisando en Coral y con los dos saldos comprobados;
  - reparten las ventanas según sus reinicios (§8).
- **Gonzalo**, cuando se conecte: una familia.

## 6. Fases

**Primero se congela la vara y se mide B; después se quitan piezas.** El juez arma hoy su referencia desde src:
`scripts/judge_golden_set.py:168` importa `src.prompts.info`, `:182` importa `src.flows.catalog`, y además lee `decisiones.json`. Si se
borran piezas antes, la vara se mueve sola. Solo por cambiar la referencia, la 0.61 pasó de 52 a 67 graves.

**F0 · La vara, congelada, y B medido** (sin tocar el bot).
- **La etiqueta de B en git:** hoy no existe ninguna (`git tag` sale vacío).
- **La tabla de decisiones cerrada con Gadea (§4).** Se reescriben los textos que choquen: `cambio-de-fecha` y la instrucción de
  `temas-3nov`.
- **La referencia del juez, congelada en un fichero con su huella**, sin armarla desde src:
  - sin `escalation_rules.json`, que está desfasado;
  - con la tabla de decisiones;
  - con el modelo fijado (claude-opus-5-5).
- **La rúbrica cerrada,** con los graves separados de la fricción. **Gadea confirma el 10 % con esa rúbrica**, porque cambiarla después
  movería la meta.
- **El arnés del examen, igual para B y para V1:**
  - **las ráfagas:** los mensajes seguidos del cliente se envían con huecos como los reales, sin esperar a la respuesta del bot. Antes,
    se rehace el minero con los segundos (`docs/robustness/golden-set/mine_whatsapp_exports.py:410` guarda `%H:%M`), en local y sin
    llamar a ningún modelo;
  - **dos relojes,** antes y después del cierre de las 4:30: un tercio de los primeros mensajes llega entre las 16:30 y las 6:00.
- **El examen (~200 clientes), escrito y congelado:**
  - **la mezcla, según las proporciones de los reales:** un tercio ya ha reservado, un 11 % son agencias, un 15 % pregunta lo que la base
    no contesta, y la mezcla de idiomas y de planes. Se fija por escrito antes de escribir un solo cliente;
  - **los 75 primeros mensajes reales, aparte, y sin contar para la meta:** ya se leyeron y se usaron para comparar V1 con B. Se dan sus
    cifras al lado;
  - **los reales nuevos de Andrés:** cuando lleguen (Gadea: «calma»), son un examen aparte que no se mezcla con este;
  - **lo de varios turnos, con clientes que reaccionan.** Un Claude hace de cliente con una **ficha de objetivo congelada**, escrita por un
    agente ciego que solo recibe el catálogo público y las proporciones. **La respuesta correcta de cada ficha** (plan, origen, moneda,
    enlace, el precio por persona que le toca y si debe pasar) **la calcula el código** a partir de la ficha, la tabla de decisiones y el
    catálogo, no el agente. Contra ella cuentan los contadores. No son guiones que no contestan, que explicaban 16-18 de los 67 graves.
- **El ruido, con números:** siempre 2 juicios por tirada, porque el juez se contradice en un 4-9 %. Con 200 clientes, 3 tiradas y 2
  juicios por lado, una diferencia en graves cuenta si supera unos 4 puntos. El ruido de cada cifra se calcula con las tiradas de B.
- **B, medido en el examen** desde su etiqueta, en local. En PRE, a partir de F1, estará V1.

**F1 · V1 dentro del bot** (la primera reducción y la primera integración).
- **Qué entra:**
  - el manejador del turno pasa a ser una llamada a Luna con la base del bot, las filas de la tabla y los hechos de §3;
  - «entendido» se guarda en el estado, con `idioma` y `vuelo`;
  - `pasar_a_persona` se llama cuando Luna marca «pasar»;
  - la puerta comprueba los hechos (§3);
  - **las ráfagas, con la opción (c)** (Gadea, 10-nov): se contesta en cuanto llega, y si mientras se genera llega otro mensaje, esa
    respuesta se tira sin enviarla y se genera otra con todo (§6.1);
  - Chatwoot sigue igual.
- **Qué se queda y se adapta:**
  - `escalate_to_human` (`src/agents/escalation.py`, que usa `src/channels/chatwoot.py:18`): se queda, sin sus imports de
    `src.prompts.router` (`:29`) y de Jev;
  - `lead_summary` (`src/agents/lead_summary.py`), la nota del pase: hoy lee campos que llenaba el extractor y pasa a leer «entendido».
    Si no, la nota sale vacía;
  - `_el_cierre` (`src/agents/rutas/contexto_rag.py`), que se saca a `domain/calendario.py` antes de borrar las rutas;
  - el aviso técnico (`_respuesta_fallo_tecnico`);
  - el guardado del estado y el candado de Chatwoot.
- **Qué decide Gadea antes de F1, con una propuesta:**
  - **`detect_sensitive_escalation`** (`escalation.py:187`): palabras clave sobre lo que escribe el cliente que deciden un pase. Es un
    regex que decide. Propuesta: se borra, y la salud y lo sensible las decide Luna con sus filas (`salud`, `datos-ajenos`).
  - **`src/privacy.py`:** regex de correos, teléfonos, cédulas y tarjetas que bloquea y escribe texto. Propuesta: se mira en el diseño de
    F1 qué hace exactamente. Si protege datos (no guardar ni repetir una tarjeta), se queda como comprobación de un hecho, sin escribir
    al cliente. Si decide la conducta, sale.
  - **El detector de idioma:** se borra y el idioma lo fija Luna (§3).
- **Qué se borra, sin interruptor**, con la lista fichero a fichero hecha en el diseño:
  - Jev (`jev_router`);
  - el extractor (`nucleo/extractor`, `extractor_turno`);
  - el lector de grupo;
  - el slotfill;
  - el compositor;
  - `origen_precio`, `redactor_hechos` y los correctores;
  - la cascada del pase, con `lo_contestable_en_cualquier_pase`;
  - los avisos que añaden texto (`src/flows/avisos.py`, `poner_avisos`);
  - el grafo y las rutas;
  - la búsqueda (V1 recibe la base entera);
  - la reescritura;
  - las notas.

  La vuelta atrás es la etiqueta de B.
- **Hecho cuando:**
  - pasan el banco sin IA del manejador nuevo y la suite que queda. Los tests de lo borrado se borran con ello, así que «la suite pasa»
    no prueba nada por sí solo;
  - los contadores funcionan;
  - un sparring de humo en local pasa;
  - el examen se ha pasado, frente a B y con el mismo arnés (§5.3);
  - un sparring pasa por Chatwoot en PRE (sube Gadea);
  - el saldo de código es negativo.
- **El diseño:** a medias entre los dos Claude, revisado por un agente.

**§6.1 Las ráfagas** (análisis de un agente sobre los 75 reales, 10-nov):
- **Cuántas:** 181 ráfagas en 65 de 75 episodios (87 %), con el 77 % de los mensajes del cliente. Mediana de 2 mensajes y un máximo
  de 11.
- **De qué tipo son:**
  - datos en trozos, 23 %;
  - un acuse y luego otra cosa, 21 %;
  - una pregunta partida, 17 %;
  - un saludo y luego la pregunta, 15 %;
  - correcciones, solo un 2 %.
- **La persona** contesta después de la ráfaga, nunca a cada trozo: tarda una mediana de 2 minutos.
- **Opciones:**
  - (a) contestar cada mensaje: deja una respuesta vieja cuando llega un mensaje mientras se genera, en un 6-15 % de los turnos como
    mucho;
  - (b) esperar unos segundos de silencio: solo cabe una espera de 3 s en el p90 de 7,5 s, y junta el 7-12 % de las ráfagas.
    Descartada;
  - (c) contestar y rehacer si llega otro: quita la respuesta vieja sin añadir latencia ni un número que ajustar. Unas 30-50 líneas. Es
    mecánica del canal: le pasa al único pensador todo lo que está sin contestar.
- **Elegida la (c) por Gadea.** Una espera que dependa del contenido («si no acaba en interrogación, espera») sería un segundo pensador
  y no entra.

**F2 · Sparring, familias y arreglos.** Ciclos con un sparring de 30 charlas: familias que pesan (§5.2), tabla con Gadea, arreglos, banco
sin IA y contadores. Cada ciclo deja escrito el saldo de código, los contadores y las familias abiertas, con su peso. Cada fila nueva entra
a la vez en el juez, y B se vuelve a juzgar (§4).

**F3 · Integrar y examen.**
- Cada integración pasa el examen y una vez Chatwoot en PRE.
- Si cumple la meta, se confirma (§2) y va a Andrés.
- Si no, del examen solo salen las cifras de §2, y se vuelve a F2 con lo que diga el sparring, no el examen.

## 7. Qué se queda y qué se retira

- **Se queda el diagnóstico** del análisis: decisiones sin dueño, código que estropea respuestas correctas, lectura que cambia entre
  vueltas y una vara que no se parece a los reales. V1 responde a las tres primeras por diseño; el examen con reales y clientes que
  reaccionan, a la cuarta.
- **Se retiran los bloques** (0, 0,5, 2a, 1, 4P, 4R, 3.1, 2b, 3.2 y 5) como forma de trabajar.
- **De lo ya escrito, solo se reutiliza lo que es hecho o comprobación y tiene su fila:**
  - el calendario del 3.1 (el cierre);
  - de V2m, solo **el reconocimiento de importes y enlaces en el texto de Luna**.

  **No entran** `decision()` (`simple_v2.py:86`, un clon de `como_reserva.entrega`), `precios_permitidos(ent)`, la plantilla ni los
  motivos que instruyen («sin aplicar descuentos ni sumar» contradice además la decisión de los descuentos). Tampoco entran
  `como_reserva`, el qué preguntar, P9 y P10 como decisión, la cascada del pase del 4P ni C5.
- **Las ramas** `bloque05-alvaro`, `bloque4r-alvaro`, `puerta-v2-alvaro`, `bloque1-gadea`, `bloque4p-gadea` y `bloque31-gadea` no se
  integran.

## 8. Presupuesto

Una sola unidad: **la ventana de 5 horas de cada Claude.** Se anota también cuánto gasta de la semanal.

- **El juez:** una pasada de 40 clientes gasta ~4-5 % de la ventana, y una de 200, ~20-25 %. Un examen (3 tiradas × 2 juicios) gasta
  1,2-1,5 ventanas.
- **El cliente que reacciona** (examen y sparring): un Claude por turno de cliente. Su gasto se mide en la primera tirada de F0 y se
  suma aquí. Hasta entonces, el examen se presupuesta en unas 2 ventanas y un sparring de 30 charlas (con 2 juicios), en ~0,5.
- **Por fase:**
  - F0: B, unas 2 ventanas, más escribir el examen;
  - F1: V1 en el bot, otras 2;
  - cada integración de F3, 2;
  - la confirmación, 2.
  - Cada fila nueva obliga a volver a juzgar B.
- **Reparto:** entre los dos Claude, según sus reinicios. La del Claude de Gadea se reinició a las 20:20 del 10-nov, con la semanal al
  29 %. La del de Álvaro, **por confirmar**.
- **El dinero:**
  - V1 va por OpenAI: ~0,45 $ por tirada de 200;
  - B: ~0,8 $ de OpenRouter por tirada de 200;
  - el sparring, céntimos por charla.
  - Antes de cada medida, los dos saldos.

## 9. Decidido por Gadea (10-nov) y lo que falta

**Decidido:**
- la meta «robusto», la de preguntas (≤ 50 %) y los pases sin meta, pero contados;
- sin tope de arreglos, pero sin parches;
- de momento solo Luna;
- la puerta, ante un segundo fallo, deja salir el segundo texto y lo cuenta como fallo;
- los descuentos, por persona, calculados por código;
- el vuelo se comprueba después;
- el horario fuera de lo normal pasa con un asesor;
- el cambio de fecha sin reserva no pasa con un asesor;
- el regalo y el particular que reserva para otro pasan con un asesor al reservar;
- con un extranjero en la reserva, todo en USD;
- las ráfagas, con la opción (c).

**Falta:**
- (a) las tres de F1: `detect_sensitive_escalation`, `privacy.py` y el detector de idioma;
- (b) la fecha para pedir a Andrés los reales nuevos («calma»);
- (c) quién da el visto bueno final para Andrés («calma»).
