# Plan V1: llegar a «robusto» quitando piezas, sin el bucle de parches (borrador v2, 10-nov)

Borrador del Claude de Álvaro (#3793). **v2:** un agente independiente revisó la v1 contra el análisis (`docs/plan/analisis-por-fases.md`),
`diseno-simple.md` y el acuerdo de #3786-#3795, sin mi conclusión. La v1 volvía a abrir el bucle por cuatro sitios:
- el sparring decidía qué se añadía;
- se podía ajustar una instrucción mirando el sparring;
- el examen elegía qué arreglar;
- los fallos que salen siempre quedaban a la suerte.

Además le faltaban dos metas y la tabla de decisiones. Esta v2 lo corrige. Lo revisa también el agente del Claude de Gadea y lo decide
Gadea. El diagnóstico del análisis se queda (§8); los bloques se retiran como forma de trabajar.

## 1. Por qué un plan nuevo

- Del 21-oct al 10-nov: ~60 versiones y 5 bloques. Los mecanismos caían; los graves, no (8,2 → 7,5 de 40). Luna sola dio 7,3 y V2m
  8,5.
- **El panel de 40 mide sobre todo azar** (#3786):
  - solo 1 cliente falla en los cuatro sistemas;
  - 25 fallan a veces;
  - el juez se contradice en 5-11 de cada 120 juicios.
- **El bucle cambiaba de nombre y no de forma** (construir, medir, «es un detalle», arreglar, medir): pasó del código a las reglas del
  prompt y a la puerta. Álvaro lo paró dos veces el 10-nov.
- **Decidido por Gadea:** V1 es la base, solo se quitan piezas y la calidad la revisan los Claude (#3790, #3791, #3793).

## 2. La meta «robusto», fijada antes de empezar

| Medida | Meta | Sobre qué se cuenta |
|---|---|---|
| Clientes con grave | ≤ 10 % | El examen (§5, F1), media de sus tiradas |
| Importes fuera del catálogo | 0 | Contador, en el examen |
| Enlace e idioma correctos | 100 % | Contador, en el examen |
| p90 del turno | ≤ 7,5 s | Contador, en el examen |
| Largo mediano | ≤ 300 caracteres | Contador, en el examen |
| **Clientes que pasan a una persona** | **≤ B** (propuesta; **la fija Gadea**) | Contador, en el examen |
| **Primeras respuestas con pregunta** | **≤ 50 %** (propuesta; la persona hace 23 %; **la fija Gadea**) | Contador, en el examen |

- **Por qué las dos últimas:**
  - el juez casi nunca da grave por pasar de más, así que los graves se pueden bajar pasando a más gente: V1 pasa 71 de 120 y B, 45;
  - V1 pregunta en el 75 % de las primeras respuestas a reales.
  - Sin estas dos metas, el ≤ 10 % se cumple de la forma equivocada.
- **Cuando un examen cumple todas, se confirma con un segundo examen de la misma versión y se presenta a Andrés.** No hay «un fallo más».
- **Un solo examen por versión** (más el de confirmación). No se repite hasta que salga.
- **El margen se dice antes.** Con 200 clientes y 3 tiradas, la media baila ~1,4 puntos: una versión que de verdad está al 11 % pasaría
  ~1 de cada 4 veces. Por eso se confirma.
- **Solo Gadea cambia una meta, y por escrito.**

## 3. La regla de diseño

```
el código calcula HECHOS ──▶ Luna lee, DECIDE y ESCRIBE (1 llamada) ──▶ la puerta COMPRUEBA hechos ──▶ cliente
```

- **Hecho antes:** un dato que el código sabe sin leer este mensaje. Por ejemplo, el primer día reservable (el cierre de las 4:30, ya en
  V1) o la hora desde la que se puede volar tras cada plan.
- **Regla:** una decisión de Gadea escrita como dato para Luna. Se escribe una vez, desde la decisión (§4).
- **Comprobación después:** sobre lo que Luna escribió y lo que dice que entendió. Por ejemplo, un importe que no está en el catálogo, un
  enlace de otro plan u origen, el idioma, o el vuelo del cliente frente a la hora desde la que puede volar. Lo que el código no puede
  saber antes, porque está en el mensaje de este turno, es una comprobación después, no un hecho antes.
- **Qué hace la puerta si falla:** se rehace una vez con el motivo. Si vuelve a fallar, el código pinta solo la línea del dato (el
  importe del catálogo o el enlace) o hace el pase. **Nunca sustituye ni recorta el texto de Luna.**
- **No entra nunca:**
  - otro lector o pensador;
  - un corrector que edite el texto de Luna;
  - una regla por un caso;
  - un regex sobre lo que dice el cliente;
  - una comprobación de conducta que rehaga (cuándo pasar, cuándo preguntar): eso son reglas para Luna;
  - un segundo escritor. Si Luna no contesta, el respaldo es el mismo prompt en otro modelo, y **lo decide Gadea**.
- **Añadir un hecho o una comprobación solo con una decisión escrita de Gadea**, nunca porque lo pida el sparring.
  - `como_reserva` (de B) no se reutiliza: decide.
  - Lo ya escrito (C2/C3 de V2m, el calendario del 3.1, los importes del 2a) solo se usa si Gadea lo pide para una fila de la tabla (§4).

## 4. Antes de F0: la tabla de decisiones, cerrada con Gadea

**Una fila por decisión.** Son las 31 de `decisiones.json`, más «breve y concisa» (9-nov), que no está. Cada fila dice:
- si es **regla** (con su texto para Luna; 19 no tienen `instruccion_es` y Luna leería el texto del juez);
- si es **hecho antes** o **comprobación después**, y quién la escribe.

Lo que ya se ve y tiene que cerrar Gadea:
- **`cambio-de-fecha` (17-sep) contra `temas-3nov`:** se contradicen. El primero dice que, sin pagar, va a un asesor; el segundo, que sin
  reserva no pasa. Luna leería las dos.
- **El vuelo** (`vuelo-hora`, el único cliente que falla en los cuatro sistemas): la hora desde la que puede volar ya está en la base.
  Lo que falla es compararla con su vuelo. Es una comprobación después, y Gadea dijo que lo replantearía (#3793).
- **El horario que no es el de siempre** (`schedule_not_adjustable`, visto-6899): una regla, que pasa con una persona (P4).
- **El cierre de las 4:30 y el de la noche** (`cierre-para-manana`): un hecho desde F0. V1 ya lo recibe.
- **«El precio con descuento»:** ninguna decisión pide dar importes con descuento. El de grupo y el de equipo propio van con un asesor,
  y el online se aplica en la web. Los totales son una regla (`sin-totales`). Este hecho no entra.
- **Las condiciones del enlace** (colombianos y residentes, el hotel, el grupo de 5 o más, los planes sin enlace, el equipo propio): son
  reglas de Luna. **Gadea decide** si la puerta, además, comprueba el enlace contra «entendido».
- **Los campos `en_el_bot`** apuntan a piezas que F0 se salta: se actualizan con la tabla.

**El prompt de V1 se congela con su huella.** Solo cambia por una fila de la tabla aprobada por Gadea. «Una pregunta como mucho» y
«unos 300 caracteres» se tratan como filas.

## 5. Cómo trabajamos

### 5.1 Tres instrumentos, con papeles que no se mezclan

| Instrumento | Para qué | Para qué NO |
|---|---|---|
| **Sparring** | **Descubrir** familias de fallos y preguntas para Gadea | Para decir que algo mejoró, ni para añadir piezas |
| **Examen** | **Decidir** si una versión llega a la meta (§2) | Para buscar qué arreglar: solo salen las siete cifras |
| **Contadores y banco sin IA** | **Vigilar** lo exacto y **comprobar** que un arreglo hace lo que dice | Para sustituir al juicio |

- **El sparring.** Un Claude hace de cliente, nuevo cada vez, con la mezcla de los reales:
  - corto y en ráfagas (77 % de los episodios) y que cambia de idea;
  - un tercio ya ha reservado;
  - un 11 % son agencias;
  - un 15 % pregunta lo que la base no contesta;
  - pide reservar hacia el tercer mensaje.
  
  Otro Claude, que no la escribió, lo juzga con la rúbrica y la hora. **Los de casa ven un resumen y una muestra** (los peores y unos al
  azar, #3791).

### 5.2 Del fallo al arreglo

1. **La familia.** Un fallo se apunta en su familia.
   - Una familia **pesa** si aparece en **≥ 3 charlas distintas** de un sparring de 30, o si es de las que fallan siempre (§6).
   - Por debajo, espera.
2. **¿Qué es?**
   - Una regla que falta o está mal escrita: va a la tabla (§4) y la decide Gadea.
   - Un hecho mal calculado: se arregla el cálculo.
   - Una comprobación de un hecho: solo con decisión de Gadea.
   - Si no es ninguna de las tres, no se hace.
3. **El diseño corto:** qué, por qué y qué borra. Lo revisa un agente independiente sin nuestra conclusión.
4. **El código**, con su banco sin IA y la suite. Otro agente revisa el diff contra el diseño.
5. **La comprobación del arreglo**, con su banco sin IA y los contadores. **No con el sparring.**
6. **La integración:** el examen, y una vez por PRE con Chatwoot (#3792).

### 5.3 Las señales del bucle, y qué se hace con cada una

| Señal | Qué se hace |
|---|---|
| Un examen de integración no mejora ninguna de las siete cifras y no cumple la meta | Se para. Se escribe «qué estamos haciendo mal» y se habla con Gadea y Álvaro antes de tocar nada |
| Un arreglo necesita otro arreglo para no romper algo | Se revierte y se rediseña |
| Se ajusta una instrucción mirando el sparring o el examen | **Prohibido**: las instrucciones solo cambian por la tabla (§4) |
| Se añade un hecho o una comprobación sin decisión escrita de Gadea | No entra |
| Se repite un examen de la misma versión para que salga | Prohibido (solo el de confirmación al cumplir la meta) |
| Alguien propone «¿y si añadimos…?» | Por defecto, no |
| Un Claude propone la siguiente versión sin mirar si la anterior movió algo | El otro Claude lo para (10-nov) |

### 5.4 Quién hace qué

- **Gadea** decide la tabla, las metas, qué entra y qué sube a PRE.
- **Álvaro** está informado de cada decisión y decide con Gadea lo de fuera (Andrés, los saldos).
- **Los dos Claude:**
  - proponen con datos y se revisan el uno al otro, cada diseño y cada diff con un agente independiente;
  - una medida a la vez en PRE, avisando en Coral y con los dos saldos comprobados.
- **Gonzalo**, cuando se conecte: una familia.

## 6. Lo que falla siempre, en la cola desde el primer día

No se espera a que el sparring lo encuentre:
- el vuelo: comprobación después, si Gadea la aprueba (§4);
- el horario que no es el de siempre: una regla, P4;
- el cierre de noche y el de las 4:30: un hecho, desde F0.

## 7. Fases

**F0 · V1 dentro del bot** (la primera reducción).
- **Qué entra:**
  - el manejador del turno pasa a ser una llamada a Luna con la base del bot, las reglas de la tabla y los hechos de F0 (el cierre);
  - «entendido» se guarda en el estado;
  - `pasar_a_persona` se llama cuando Luna marca «pasar»;
  - una ráfaga de mensajes seguidos se junta en un solo turno, como hoy en Chatwoot;
  - Chatwoot, igual.
- **Qué se borra en F0, sin interruptor:** Jev, el extractor, el lector de grupo, el slotfill, el compositor, los correctores y la
  cascada del pase. B se mide desde su etiqueta en git, no desde un interruptor.
- **Hecho cuando:**
  - la suite y su banco sin IA pasan;
  - un sparring de humo pasa por Chatwoot en PRE (sube Gadea);
  - los contadores funcionan;
  - el saldo de código es negativo.
- **El diseño:** a medias entre los dos Claude, revisado por un agente.

**F1 · El examen congelado y la línea base.** Se fija todo antes de juzgar nada:
- **Composición (~200 clientes):**
  - **los 75 reales se cuentan aparte**: no son ciegos, ya se leyeron y se usaron para comparar V1 con B;
  - **los reales nuevos de Andrés son condición**, no una pregunta. Gadea se los pide;
  - **lo de varios turnos:** clientes que **reaccionan**. Un Claude hace de cliente con una **ficha de objetivo congelada**, escrita por un
    agente ciego que solo recibe el catálogo público y las proporciones de los reales. No son guiones que no contestan: esos explicaban
    16-18 de los 67 graves.
- **Dos relojes**, antes y después del cierre de las 4:30: un tercio de los primeros mensajes llega entre las 16:30 y las 6:00.
- **El juez:**
  - modelo fijado (claude-opus-5-5) y referencia con su huella;
  - sin `escalation_rules.json`, que está desfasado;
  - los graves, separados por daño de la fricción.
- **El ruido, con números:**
  - en el panel, la desviación de la diferencia fue 0,76 de 40; en los reales, 2,45 de 75;
  - con 200 clientes, 3 tiradas y 2 juicios por lado, una diferencia cuenta si supera ~4 puntos (se recalcula con la línea base).
  - «Desacuerdo bajo» = el juez se contradice en menos del 3 % de los juicios del examen. Solo entonces vale 1 juicio por tirada.
- **La línea base:** B (su etiqueta) frente a V1 en el bot, 3 tiradas cada uno.

**F2 · Sparring, familias y arreglos.** Ciclos con un sparring de 30 charlas: familias que pesan (§5.2), tabla con Gadea, arreglos,
banco sin IA y contadores. Cada ciclo deja escrito el saldo de código, los contadores y las familias abiertas, con su peso.

**F3 · Integrar y examen.**
- Cada integración pasa el examen y una vez Chatwoot en PRE.
- Si cumple la meta, se confirma y va a Andrés.
- Si no, del examen solo salen las siete cifras, y se vuelve a F2 con lo que diga el sparring, no el examen.

## 8. Qué se queda y qué se retira

- **Se queda el diagnóstico** del análisis: decisiones sin dueño, código que estropea respuestas correctas, lectura que cambia entre
  vueltas y una vara que no se parece a los reales. V1 responde a las tres primeras por diseño; el examen con reales y clientes que
  reaccionan, a la cuarta.
- **Se retiran los bloques** (0, 0,5, 2a, 1, 4P, 4R, 3.1, 2b, 3.2 y 5) como forma de trabajar.
- **Lo ya escrito que es hecho o comprobación** (el calendario del 3.1, los importes del 2a, C2/C3 de V2m) solo entra si Gadea lo pide
  para una fila de la tabla. `como_reserva` no.
- **Las ramas** `bloque05-alvaro`, `bloque4r-alvaro`, `puerta-v2-alvaro`, `bloque1-gadea`, `bloque4p-gadea` y `bloque31-gadea` no se
  integran.

## 9. Presupuesto

- **La ventana de Claude (el juez):**
  - una pasada de 40 clientes, ~4-5 %; una de 200, ~20-25 %;
  - un examen por versión (3 tiradas × 2 juicios), 1,2-1,5 ventanas; con 1 juicio, si el desacuerdo es bajo, 0,6-0,75;
  - la línea base, ~1,5-3 ventanas, más el examen de confirmación.
  - Se reparte entre los dos Claude según sus reinicios. La del Claude de Gadea estaba al 29 % de la semanal el 10-nov; la del de
    Álvaro, **por confirmar**.
- **El dinero:**
  - V1 va por OpenAI: ~0,45 $ por tirada de 200;
  - B en PRE: ~0,8 $ de OpenRouter por tirada de 200;
  - el sparring, céntimos por charla.
  - Antes de cada medida, los dos saldos.

## 10. Lo que decide Gadea antes de F0

- (a) Las dos metas nuevas (§2): los pases y las primeras respuestas con pregunta.
- (b) La tabla de decisiones (§4), con la contradicción del cambio de fecha, el vuelo y si la puerta comprueba las condiciones del enlace.
- (c) El respaldo si Luna no contesta (§3).
- (d) Pedir a Andrés los reales nuevos (§7, F1).
- (e) Quién da el visto bueno final para Andrés: Gadea sola, o Gadea y Álvaro.
