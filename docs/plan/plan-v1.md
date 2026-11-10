# Plan V1: llegar a «robusto» quitando piezas, sin el bucle de parches (borrador v3, 10-nov)

**Historia del borrador:**
- **v1 y v2:** del Claude de Álvaro (#3793-#3799). La v2 salió de la revisión de un agente independiente que encontró cuatro huecos por
  donde volvía el bucle.
- **v3:** del Claude de Gadea, a petición de Gadea. Recoge:
  - las decisiones de Gadea del 10-nov a las 21:50;
  - la segunda revisión independiente (#3800), con lo que afirma comprobado en el código;
  - el análisis de las ráfagas (§6, F1).

  La revisa el Claude de Álvaro.

El diagnóstico del análisis (`docs/plan/analisis-por-fases.md`) se queda (§7). Los bloques se retiran como forma de trabajar.

## 1. Por qué un plan nuevo

- **Del 21-oct al 10-nov:** unas 60 versiones y 5 bloques. Los mecanismos caían, pero los graves no: 8,2 → 7,5 de 40.
- **El panel de 40 mide sobre todo azar** (#3786). En el panel-vara, con 6 juicios por sistema:
  - A (antes de los bloques) 8,2, B 7,5, V1 7,5 y V2m 8,5;
  - solo 1 cliente falla en los cuatro: visto-6914, el vuelo;
  - 14 no fallan nunca y 25 fallan a veces;
  - el juez se contradice con la misma respuesta en 5-11 de cada 120 juicios (4-9 %).
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

## 2. La meta «robusto», fijada antes de empezar

| Medida | Meta | Sobre qué se cuenta |
|---|---|---|
| Clientes con grave | ≤ 10 % | El examen (F0), la media de sus tiradas, con la rúbrica cerrada en F0 |
| Importes fuera del catálogo y de los hechos del turno | 0 | Contador sobre lo que escribe Luna, **antes de la puerta** |
| Enlace (plan, origen e idioma) e idioma de la respuesta | 100 % bien | Contador **contra la ficha congelada de cada cliente**, antes de la puerta |
| p90 del turno | ≤ 7,5 s | Contador, en el examen |
| Largo mediano | ≤ 300 caracteres | Contador, en el examen |
| Primeras respuestas con pregunta | ≤ 50 % (**fijada por Gadea, 10-nov**) | Contador, en el examen. La persona pregunta en el 16 % de sus primeras respuestas a los 75 reales |
| Clientes que pasan a una persona | ≤ B (**propuesta, la confirma Gadea**) | Contador, en el examen |

- **Por qué los contadores van antes de la puerta y contra la ficha:** después de la puerta, el 0 y el 100 % salen solos (la puerta ya
  ha quitado lo que cuenta). Contra lo que dijo Luna, un importe de otro plan pasaría, porque 16 cifras casan con más de un plan.
- **Por qué las metas de pases y preguntas:** el juez casi nunca da grave por pasar de más ni por preguntar de más, así que el ≤ 10 % se
  podría cumplir de la forma equivocada. Hoy V1 pasa 71 de 120 (B, 45) y pregunta en el 75 % de las primeras respuestas reales.
- **La confirmación:** cuando un examen cumple todas las metas, se repite una vez con la misma versión.
  - Si la confirmación también cumple, se presenta a Andrés.
  - Si falla, la versión no pasa y ese examen no se vuelve a repetir.
  - Con 200 clientes y 3 tiradas, la media baila unos ±1,4 puntos: una versión que de verdad está al 8 % pasa los dos exámenes ~85 %
    de las veces, y una al 10 %, ~25 %.
- **Si solo fallan los pases o las preguntas:** decide Gadea, sin reescribir las reglas mirando el examen.
- **Solo Gadea cambia una meta, y por escrito.**

## 3. La regla de diseño

```
el código calcula HECHOS ──▶ Luna lee, DECIDE y ESCRIBE (1 llamada) ──▶ la puerta COMPRUEBA hechos ──▶ cliente
```

- **Hecho antes:** un dato que el código sabe sin leer el mensaje de este turno. Estos ya están aprobados por Gadea:
  - el primer día que se puede reservar (el cierre de las 4:30 y el de la noche): V1 ya lo recibe;
  - el precio por persona de cada plan con cada descuento que exista (grupo de 5 o más, equipo propio, online), calculado por código.
    Luna lo dice tal cual y no hace cuentas. Los totales siguen prohibidos (`sin-totales`). Decidido el 10-nov. Es lo que V1 calculaba
    mal: 13 de 272 importes, todos descuentos y totales.
- **Regla:** una decisión de Gadea escrita como dato para Luna, una vez y desde la decisión (§4).
- **Comprobación después:** solo de hechos, sobre lo que Luna escribió:
  - un importe que no está en el catálogo ni en los hechos del turno;
  - un enlace que no es de un plan del catálogo o no lleva su idioma;
  - el idioma de la respuesta.

  **La puerta no comprueba conducta:** cuándo pasar, cuándo preguntar o las condiciones del enlace (colombianos, hotel, grupo). Eso son
  reglas para Luna.
- **Si la puerta encuentra un fallo:** se rehace una vez con el motivo. Si vuelve a fallar, **sale el segundo texto y se cuenta como
  fallo**, decidido por Gadea el 10-nov. **La puerta nunca escribe, nunca decide y nunca recorta.**
- **Si Luna no contesta** (error o sin saldo): el aviso técnico que ya existe (`_respuesta_fallo_tecnico`, `src/agents/supervisor.py`),
  que dice la verdad y pasa con una persona. No hay respaldo en otro modelo: de momento solo Luna (decidido por Gadea el 10-nov).
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

**Una fila por decisión.** Son las 31 de `decisiones.json`, más «breve y concisa» (9-nov), que no está. Cada fila dice:
- si es **regla** (con su texto para Luna; 19 no tienen `instruccion_es` y Luna leería el texto del juez);
- o si es **hecho antes** o **comprobación después**, y quién la escribe.

**El prompt de V1 tampoco tiene reglas propias.** Antes de congelarlo, cada línea de conducta de `INSTRUCCIONES`
(`scripts/simple_v1.py`) se convierte en fila de la tabla o sale. Dos ya se sabe que chocan:
- `:36`, «si algo no está o no se puede resolver aquí… pasas al cliente con una persona», choca con `fuera-de-la-base` (va según el tema).
  Sale. Es la causa probable de los 71 pases.
- `:33`, «contestas en el idioma del cliente», choca con `idioma` (otro idioma → inglés). Se alinea con la decisión.

«Una pregunta como mucho» y «unos 300 caracteres» son filas de «breve y concisa».

**Ya decidido por Gadea:**
- **El cambio de fecha:** sin una reserva hecha, se cambia la fecha sin asesor, y con la reserva hecha va al asesor (10-nov). El texto
  de `cambio-de-fecha` (17-sep), que dice «antes de pagar, a un asesor», se reescribe con esa decisión.
- **El horario que no es el de siempre** (visto-6899): regla. La política `schedule_not_adjustable` («los horarios son fijos; un ajuste lo
  revisa un asesor») pasa con una persona. Confirmado por Gadea el 10-nov. No es la P4: la P4 es «2 días desde las islas sin nocturna».
- **El cierre:** hecho antes, desde F1.
- **Los descuentos:** hecho antes, por persona (§3). Los totales son una regla (`sin-totales`).

**Lo que falta cerrar en la tabla:**
- **El vuelo** (`vuelo-hora`, el único cliente que falla en los cuatro sistemas). La hora desde la que puede volar tras cada plan es un
  hecho antes. Comprobar el vuelo del cliente contra ella sería una comprobación después: la decide Gadea.
- **`temas-3nov` («reservar para otro con un asesor») contra `por-otros`** (quien escribe por otros recibe el mismo trato que un cliente):
  hay que ver si se contradicen.
- **Los campos `en_el_bot`** apuntan a piezas que F1 borra: se actualizan con la tabla.

**El prompt se congela con su huella.** Una fila cambia solo si cambia la decisión de Gadea, nunca por cómo la cumple Luna.

## 5. Cómo trabajamos

### 5.1 Tres instrumentos, con papeles que no se mezclan

| Instrumento | Para qué | Para qué NO |
|---|---|---|
| **Sparring** | **Descubrir** familias de fallos y preguntas de negocio para Gadea | Para decir que algo mejoró, para añadir piezas ni para cambiar una regla |
| **Examen** | **Decidir** si una versión llega a la meta (§2) | Para buscar qué arreglar: solo salen las cifras de §2 |
| **Contadores y banco sin IA** | **Vigilar** lo exacto y **comprobar** que un arreglo hace lo que dice | Para sustituir al juicio |

- **El sparring.** Un Claude hace de cliente, nuevo cada vez, con la mezcla de los reales:
  - corto (31 caracteres de mediana) y en ráfagas (el 77 % de los episodios), y que cambia de idea;
  - un tercio ya ha reservado;
  - un 11 % son agencias;
  - un 15 % pregunta lo que la base no contesta.

  Otro Claude, que no la escribió, lo juzga con la rúbrica y la hora. Corre **en local**, con el código de la rama (`charla_rama` o
  `--codigo-local`), para no chocar al subir. Contra PRE por Chatwoot, una vez por integración. **Los de casa ven un resumen y una
  muestra:** los peores y unos al azar (#3791).

### 5.2 Del fallo al arreglo

1. **La familia.** Un fallo se apunta en su familia. Una familia **pesa** si aparece en **3 o más charlas distintas** de un sparring de
   30. Por debajo, espera.
2. **¿Qué es?**
   - **Una regla que falta:** es una pregunta de negocio para Gadea. Si Gadea decide, entra como fila nueva. **El texto de una fila ya
     escrita solo cambia si cambia la decisión, nunca por cómo la cumple Luna.**
   - **Un hecho mal calculado:** se arregla el cálculo.
   - **Una comprobación de un hecho nueva:** solo con una decisión de Gadea.
   - **Si no es ninguna de las tres** (por ejemplo, Luna no cumple una regla que ya está bien escrita), no se toca el prompt. Se apunta,
     con su frecuencia, en las cifras del ciclo. Si impide la meta, se habla con Gadea (§5.3).
3. **El diseño corto:** qué, por qué y qué borra. Lo revisa un agente independiente sin nuestra conclusión.
4. **El código**, con su banco sin IA y la suite. Otro agente revisa el diff contra el diseño.
5. **La comprobación del arreglo**, con su banco sin IA y los contadores. **No con el sparring.**
6. **La integración:** el examen, y una vez por PRE con Chatwoot.

### 5.3 Las señales del bucle, y qué se hace con cada una

| Señal | Qué se hace |
|---|---|
| Un examen de integración no mejora ninguna cifra más que su ruido (en graves, 4 puntos o más) y no cumple la meta | Se para. Se escribe «qué estamos haciendo mal» y se habla con Gadea y Álvaro antes de tocar nada |
| Un arreglo necesita otro arreglo para no romper algo | Se revierte y se rediseña |
| Se ajusta una instrucción mirando el sparring o el examen | **Prohibido**: una fila solo cambia si cambia la decisión (§4) |
| Una pieza «comprueba», pero en realidad decide o escribe | No entra: es un segundo pensador |
| Se añade un hecho o una comprobación sin una decisión escrita de Gadea | No entra |
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

El orden cambia frente a la v2: **primero se congela la vara y se mide B, y solo después se quitan piezas.** El juez arma hoy su
referencia desde src (`scripts/judge_golden_set.py:168` importa `src.prompts.info` y `:182` importa `src.flows.catalog`, y además lee
`decisiones.json`). Si se borran piezas antes, la vara se mueve sola. Solo por cambiar la referencia, la 0.61 pasó de 52 a 67 graves.

**F0 · La vara, congelada, y B medido** (sin tocar el bot).
- **La etiqueta de B en git:** hoy no existe ninguna (`git tag` sale vacío).
- **La tabla de decisiones cerrada con Gadea (§4).** Se reescriben los textos que choquen (`cambio-de-fecha`).
- **La referencia del juez, congelada en un fichero con su huella**, sin armarla desde src.
  - Sin `escalation_rules.json`, que está desfasado.
  - Con la tabla de decisiones.
  - Modelo fijado (claude-opus-5-5).
- **La rúbrica cerrada,** con los graves separados de la fricción. **Gadea confirma el 10 % con esa rúbrica**, porque cambiarla después
  movería la meta.
- **El examen (~200 clientes), escrito y congelado:**
  - **los 75 primeros mensajes reales, aparte:** no son ciegos, ya se leyeron y se usaron para comparar V1 con B;
  - **los reales nuevos de Andrés:** Gadea se los pide, con fecha. Si no llegan para esa fecha, el examen va sin ellos y se añaden como
    un examen aparte cuando lleguen, sin mezclar las cifras;
  - **lo de varios turnos, con clientes que reaccionan.** Un Claude hace de cliente con una **ficha de objetivo congelada**, escrita por un
    agente ciego que solo recibe el catálogo público y las proporciones de los reales. La ficha dice también lo que hay que contestarle
    (plan, origen, moneda e idioma correctos): contra ella cuentan los contadores. No son guiones que no contestan, que explicaban 16-18 de
    los 67 graves;
  - **dos relojes,** antes y después del cierre de las 4:30: un tercio de los primeros mensajes llega entre las 16:30 y las 6:00.
- **El ruido, con números:** siempre 2 juicios por tirada. El juez se contradice en un 4-9 % de los juicios, y por debajo del 3 % no
  baja. Con 200 clientes, 3 tiradas y 2 juicios por lado, una diferencia cuenta si supera unos 4 puntos (se recalcula con B).
- **B, medido en el examen** desde su etiqueta, en local. En PRE, a partir de F1, estará V1.

**F1 · V1 dentro del bot** (la primera reducción y la primera integración).
- **Qué entra:**
  - el manejador del turno pasa a ser una llamada a Luna con la base del bot, las filas de la tabla y los hechos (el cierre y los precios
    por persona con descuento);
  - «entendido» se guarda en el estado;
  - `pasar_a_persona` se llama cuando Luna marca «pasar»;
  - la puerta comprueba los hechos (§3);
  - Chatwoot sigue igual.
- **Las ráfagas:** decisión de F1, según el análisis (§6.1).
- **Qué se queda y se adapta:**
  - `lead_summary` (`src/agents/lead_summary.py`), la nota del pase: hoy lee campos que llenaba el extractor y pasa a leer «entendido».
    Si no, la nota sale vacía;
  - `_el_cierre` (`src/agents/rutas/contexto_rag.py`), que se saca a `domain/calendario.py` antes de borrar las rutas;
  - el aviso técnico (`_respuesta_fallo_tecnico`);
  - el guardado del estado y el candado de Chatwoot.
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
  - el examen se ha pasado, que es la comparación con B;
  - un sparring pasa por Chatwoot en PRE (sube Gadea);
  - el saldo de código es negativo.
- **El diseño:** a medias entre los dos Claude, revisado por un agente.

**§6.1 Las ráfagas** (análisis de un agente sobre los 75 reales). *Pendiente: se rellena con el resultado.*

**F2 · Sparring, familias y arreglos.** Ciclos con un sparring de 30 charlas: familias que pesan (§5.2), tabla con Gadea, arreglos, banco
sin IA y contadores. Cada ciclo deja escrito el saldo de código, los contadores y las familias abiertas, con su peso.

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
  - la comprobación de importes y enlace de V2m (C2 y C3), como la puerta.

  No se reutilizan `como_reserva`, el qué preguntar, P9 y P10 como decisión, la cascada del pase del 4P ni C5.
- **Las ramas** `bloque05-alvaro`, `bloque4r-alvaro`, `puerta-v2-alvaro`, `bloque1-gadea`, `bloque4p-gadea` y `bloque31-gadea` no se
  integran.

## 8. Presupuesto

Una sola unidad: **la ventana de 5 horas de cada Claude.** Se anota también cuánto gasta de la semanal.

- **El juez:** una pasada de 40 clientes gasta ~4-5 % de la ventana, y una de 200, ~20-25 %. Un examen (3 tiradas × 2 juicios) gasta
  1,2-1,5 ventanas.
- **El cliente que reacciona** (examen y sparring): un Claude por turno de cliente. Su gasto se mide en la primera tirada de F0 y se
  suma aquí. Hasta entonces, el examen se presupuesta en unas 2 ventanas.
- **Por fase:**
  - F0: B, unas 2 ventanas, más escribir el examen;
  - F1: V1 en el bot, otras 2;
  - cada integración de F3, 2;
  - la confirmación, 2.
  - Un sparring de 30 charlas, por medir en F0.
- **Reparto:** entre los dos Claude, según sus reinicios. La del Claude de Gadea se reinició a las 20:20 del 10-nov, con la semanal al
  29 %. La del de Álvaro, **por confirmar**.
- **El dinero:**
  - V1 va por OpenAI: ~0,45 $ por tirada de 200;
  - B: ~0,8 $ de OpenRouter por tirada de 200;
  - el sparring, céntimos por charla.
  - Antes de cada medida, los dos saldos.

## 9. Decidido por Gadea (10-nov) y lo que falta

**Decidido:**
- la meta «robusto» y la de preguntas (≤ 50 %);
- sin tope de arreglos, pero sin parches;
- de momento solo Luna;
- la puerta, ante un segundo fallo, deja salir el segundo texto y lo cuenta como fallo;
- los descuentos, por persona, calculados por código;
- el horario fuera de lo normal pasa con un asesor;
- el cambio de fecha sin reserva no pasa con un asesor.

**Falta:**
- (a) la meta de pases (≤ B);
- (b) cerrar la tabla (§4): el vuelo y `temas-3nov` frente a `por-otros`;
- (c) las ráfagas (§6.1), cuando esté el análisis;
- (d) pedir a Andrés los reales nuevos, con fecha;
- (e) quién da el visto bueno final para Andrés: Gadea solo, o Gadea y Álvaro.
