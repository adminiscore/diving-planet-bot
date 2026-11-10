# Plan V1: llegar a «robusto» quitando piezas, sin el bucle de parches (borrador, 10-nov)

Borrador del Claude de Álvaro (#3793). Lo revisa un agente independiente (Claude de Gadea) y lo decide Gadea. Sustituye a los bloques
del Plan Gadea como forma de trabajar; el diagnóstico de aquel documento se queda (§7).

## 1. Por qué un plan nuevo

- Del 21-oct al 10-nov hubo ~60 versiones y 5 bloques. Los mecanismos caían uno a uno y los graves no se movían: 8,2 → 7,5 de 40.
  Luna sola, en una llamada, dio 7,3, y V2m 8,5.
- **El panel de 40 mide sobre todo azar** (#3786):
  - un solo cliente falla en los cuatro sistemas;
  - 25 fallan unas veces sí y otras no;
  - el juez se contradice en 5-11 de cada 120 juicios.
  - No distingue arquitecturas.
- **El bucle cambiaba de nombre y no de forma:** construir, medir, salen fallos, «es un detalle», arreglar, medir. El parche pasó del
  código a las reglas del prompt y a la puerta. Álvaro lo paró dos veces el 10-nov.
- **Decidido por Gadea:**
  - V1 es la base (#3790), y desde V1 solo se quitan piezas;
  - la calidad la revisan los Claude (#3791);
  - la meta, con cifras (#3793).

## 2. El objetivo: «robusto», con cifras fijadas antes de empezar

| Medida | Meta | Cómo se mide |
|---|---|---|
| Clientes con grave en el examen | ≤ 10 % (media de las tiradas) | Examen congelado (§4.2), al integrar |
| Importes fuera del catálogo | 0 | Contador por código, cada turno |
| Enlace e idioma correctos | 100 % | Contador por código, cada turno |
| p90 del turno | ≤ 7,5 s | Contador, cada turno |
| Largo mediano de la respuesta | ≤ 300 caracteres | Contador, cada turno |

- **Cuando un examen de integración cumple las cinco, se para y se presenta a Andrés.** No hay «un fallo más».
- Si una meta resulta imposible o absurda, la cambia Gadea por escrito, nunca un Claude a mitad de una medida.

## 3. La regla de diseño (una sola)

```
el código calcula HECHOS ──▶ Luna lee, DECIDE y ESCRIBE (1 llamada) ──▶ la puerta COMPRUEBA hechos ──▶ cliente
```

- **Hecho:** un dato que calcula el código. Por ejemplo, el primer día reservable (el cierre de las 4:30), la primera hora a la que
  puede volar, el precio por persona con un descuento si lo pide o el enlace de su plan y su origen.
- **Regla:** una decisión de Gadea escrita como dato (`decisiones.json`) que Luna lee.
  - Se escribe **una vez, desde la decisión**, nunca desde un fallo visto ni mirando un panel.
  - Si no hay decisión, se le pregunta a Gadea; no se inventa.
- **Comprobación:** la puerta solo mira hechos (importes contra el catálogo, el enlace contra su plan y su origen, el idioma).
  - Si no casa, se rehace una vez con el motivo.
  - Si vuelve a fallar, pinta el código.
  - Nunca recorta el texto de Luna (norma 5).
- **No entra:**
  - otro lector o pensador (Jev, el extractor, el lector de grupo, una tabla que decide la pregunta);
  - un corrector que edite el texto de Luna;
  - una regla por un caso;
  - un regex sobre lo que dice el cliente;
  - una comprobación de conducta que rehaga (lo que hizo C1/C4 en V2: 65 % de rehechos).
- **Al bot, de momento, solo Luna (#3793).** Los hechos y la puerta entran solo si el sparring enseña su familia (§4.3). Si algo se
  complica, como un cálculo, se replantea con Gadea.

## 4. Cómo trabajamos

### 4.1 Tres instrumentos, con papeles que no se mezclan

| Instrumento | Para qué | Para qué NO |
|---|---|---|
| **Sparring** | **Descubrir** familias de fallos | Para decir que algo mejoró |
| **Examen** | **Decidir** si una versión es mejor y si llega a la meta | Para buscar qué arreglar (de él solo salen cifras por familia) |
| **Contadores** | **Vigilar** lo exacto en cada turno | Para sustituir al juicio |

- **El sparring.** Un Claude hace de cliente, nuevo cada vez, con la mezcla de los reales:
  - corto y en ráfagas, y cambia de idea;
  - un tercio ya ha reservado;
  - un 11 % son agencias;
  - un 15 % pregunta lo que la base no tiene.
  
  Otro Claude, que no la escribió, juzga cada charla con la rúbrica y la hora fija. Cada fallo se clasifica en una familia. Como
  los clientes son nuevos cada vez, no se puede afinar contra ellos.
- **El examen** (§5, F1). Se congela con su huella y se juzga solo al integrar. Nadie lee sus charlas para arreglar nada.
- **Los contadores**, gratis y por código en cada turno: importes fuera del catálogo, enlace e idioma, pases, largo, preguntas y
  latencia.

### 4.2 Del fallo al arreglo, siempre por familia

1. **La familia.** Un fallo del sparring se apunta en su familia (precio, enlace, pase, pregunta, horas o vuelo, origen, idioma,
   tono…). Un fallo suelto no se arregla: espera a que su familia pese.
2. **El tipo de arreglo.** ¿Es un hecho, una regla o una comprobación? Si no es ninguno de los tres, no se hace. Si la familia no
   tiene decisión de Gadea, primero la pregunta.
3. **El diseño corto:** qué, por qué, qué borra y cómo se sabe que funcionó. Lo revisa un agente independiente sin nuestra conclusión.
4. **El código**, con su banco sin IA y la suite. Otro agente revisa el diff contra el diseño.
5. **La comprobación**, con un sparring nuevo (no los mismos clientes) y los contadores.
6. **La integración**, con el examen (F3).

### 4.3 Las señales del bucle, y qué se hace con cada una

| Señal | Qué se hace |
|---|---|
| Dos integraciones seguidas sin mover el examen más allá de su ruido | Se para. Se escribe «qué estamos haciendo mal» y se habla con Gadea y Álvaro antes de tocar nada |
| Un arreglo necesita otro arreglo para no romper algo | Se revierte y se rediseña |
| Una fase hace crecer el código | No se integra hasta que borre lo que sustituye |
| Se ajusta una instrucción mirando el examen | Prohibido |
| Se ajusta una instrucción mirando el sparring | Solo por su familia y desde una decisión de Gadea |
| Alguien propone «¿y si añadimos…?» | La respuesta por defecto es no: V1 y quitar |
| Un Claude propone la siguiente versión sin mirar si la anterior movió algo | El otro Claude lo para (lección del 10-nov) |

### 4.4 Quién hace qué

- **Gadea** decide el negocio, el rumbo y lo que sube a PRE.
- **Álvaro** está informado de cada decisión y decide con Gadea lo de fuera (Andrés, los saldos).
- **Los dos Claude:**
  - proponen con datos y se revisan el uno al otro, cada diseño y cada diff con un agente independiente;
  - una medida a la vez en PRE, avisando en Coral y con los dos saldos comprobados.
- **Gonzalo**, cuando se conecte: una familia.

## 5. Fases

**F0 · V1 dentro del bot.** Es la primera reducción.
- **Qué:** el manejador del turno pasa a ser una llamada a Luna con la base del bot y las reglas (`decisiones.json`). Además:
  - «entendido» se guarda en el estado de la conversación;
  - `pasar_a_persona` se llama cuando Luna marca «pasar»;
  - Chatwoot, igual.
- **Se saltan:** Jev, el extractor, el lector de grupo, el slotfill, el compositor, los correctores y la cascada del pase. Se borran
  en F2, cuando el sparring no los eche de menos.
- **Hecho cuando:**
  - la suite y su banco sin IA pasan;
  - un sparring de humo pasa por Chatwoot en PRE (sube Gadea);
  - los contadores funcionan.
- **Diseño:** a medias entre los dos Claude, revisado por un agente.

**F1 · El examen congelado y la línea base.**
- **Composición, ~200 clientes:**
  - los primeros mensajes reales: los 75 de hoy y los que dé Andrés, anonimizados y en la máquina de Gadea;
  - lo de varios turnos lo escribe un agente ciego. Solo recibe el catálogo público, las proporciones de los reales y una lista de
    objetivos de cliente sacados al azar; nada del repo ni del diagnóstico.
  - Se congela con su huella.
- **El juez:** rúbrica fija con las decisiones, reloj fijo y huella de la referencia.
- **La línea base:** B (el bot de hoy) frente a V1 en el bot, 3 tiradas cada uno.
  - Se mide una vez el desacuerdo del juez en el examen. Si es bajo, basta 1 juicio por tirada; si no, 2.
  - Con 200 clientes debería verse una diferencia de unos 5-6 puntos (con 40 hacían falta 3 clientes, el 7,5 %). Se recalcula con la
    línea base.

**F2 · Sparring, familias, arreglos y borrar piezas.**
- **Ciclos:** sparring de N charlas, luego familias, luego arreglos (hecho, regla o comprobación, §4.2), luego borrar lo que ya no
  hace falta.
- **Los hechos y la puerta ya diseñados son candidatos.** Entran solo si su familia aparece en el sparring:
  - el cierre de las 4:30 (3.1);
  - la primera hora para volar, que es el único cliente que falla en los cuatro sistemas;
  - el precio con descuento;
  - C2 (importes) y C3 (enlace e idioma) de V2m.
- **Cada ciclo deja escrito:**
  - el saldo de código, negativo;
  - los contadores;
  - las familias abiertas y su peso.

**F3 · Integrar y examen.**
- **Cada integración pasa el examen.** Si cumple las cinco metas (§2), Andrés. Si no, se miran las cifras por familia (no las charlas)
  y se vuelve a F2.
- **Regla de parada:** la de §4.3.

## 6. Presupuesto

- **La ventana de Claude (el juez):**
  - una pasada de 40 clientes gasta ~4-5 %, y una de 200, ~20-25 %;
  - un examen por versión, 3 tiradas × 1 juicio, son ~0,6-0,75 ventanas; con 2 juicios, ~1,2-1,5;
  - la línea base (B y V1), ~1,5-3 ventanas.
  - Se reparte entre los dos Claude según sus reinicios. La del Claude de Gadea estaba al 29 % de la semanal el 10-nov; la del de
    Álvaro, **por confirmar con Álvaro**.
- **El dinero:**
  - V1 va por OpenAI: ~0,09 $ por 40 clientes, ~0,45 $ por tirada de 200;
  - B en PRE: ~0,8 $ de OpenRouter por tirada de 200;
  - el sparring, céntimos por charla.
  - Antes de cada medida, los dos saldos.

## 7. Qué se queda y qué se retira

- **Se queda el diagnóstico** del documento de Gadea (Fases 1-5): decisiones sin dueño, código que estropea respuestas correctas,
  lectura que cambia entre vueltas y una vara que no se parece a los reales.
  - V1 responde a las tres primeras por diseño: una sola pieza decide, nadie edita su texto y hay una sola lectura.
  - El examen con mensajes reales responde a la cuarta.
- **Se retiran los bloques** (0, 0,5, 2a, 1, 4P, 4R, 3.1, 2b, 3.2 y 5) como forma de trabajar.
  - **De su código se aprovecha solo lo que es hecho o comprobación:**
    - el calendario del cierre (3.1);
    - los importes del 2a;
    - `como_reserva.entrega` y `recogida_por_confirmar` (4R), para comprobar el enlace;
    - C2 y C3 (V2m).
  - Todo con su diseño corto y solo cuando su familia lo pida.
- **Las ramas** `bloque05-alvaro`, `bloque4r-alvaro`, `puerta-v2-alvaro`, `bloque1-gadea`, `bloque4p-gadea` y `bloque31-gadea` no
  se integran tal cual.

## 8. Lo que decide Gadea antes de F0

- (a) ¿Pedimos a Andrés más conversaciones reales para el examen?
- (b) ¿Cuántas charlas de sparring por ciclo, y cada cuánto se integra?
- (c) ¿Quién da el visto bueno final para presentar a Andrés: Gadea sola, o Gadea y Álvaro?
- (d) Si F0 enseña que algo de lo saltado hacía falta (por ejemplo, el pase en Chatwoot), ¿se trata como una familia más, que es lo que
  propone este plan?
