# Plan de reconstrucción: un asistente de reservas limpio, robusto y reutilizable

**Borrador del Claude de Álvaro, 11-nov-2026, por encargo de Álvaro. Lo deciden Gadea y Álvaro.**

No es código ni otra versión del Plan V1. Recoge las decisiones de Gadea del 10-nov y se apoya en:
- la investigación de `docs/investigacion/` (informe y seis notas con fuentes);
- el inventario del repo del 11-nov (`docs/investigacion/inventario-repo-11nov.md`);
- el Plan V1 v4.1 (`docs/plan/plan-v1.md`) y la memoria del equipo.

**Este documento ha tenido una revisión independiente y una corrección, y ahí se queda** (§18). Lo que cambie a partir de ahora lo
decidís vosotros.

**Estado al 11-nov:** Gadea y Álvaro han aprobado siete ajustes (§19 y §20). Están apuntados en §16.4 y pasados al texto. Si en algún punto queda una duda, manda §16.4.

Cómo leerlo:
- **Parte A (10 minutos):** qué vamos a construir, por qué de cero y qué tenéis que decidir.
- **Parte B:** la constitución, las reglas que no se cambian sin los dos dueños.
- **Partes C y D:** el diseño y la vara de medir.
- **Parte E:** las fases, cada una con su puerta de salida.
- **Parte F:** quién hace qué, riesgos, costes y la lista de decisiones.
- Al final hay un glosario.

---

# Parte A. Para decidir

## 1. El plan en una página

**Qué construimos.** Un asistente de WhatsApp que atiende a los clientes de Diving Planet como lo haría una buena persona del equipo:
breve, con los datos exactos, y que pasa con un asesor lo que no le toca. Por dentro son dos cosas separadas:

```
┌──────────────────────────────┐      ┌──────────────────────────────────────┐
│  EL MOTOR (igual para todos) │  +   │  EL PAQUETE DEL NEGOCIO (solo datos) │
│  conversa, comprueba, pasa   │      │  catálogo, precios, reglas, enlaces  │
└──────────────────────────────┘      └──────────────────────────────────────┘
        código, pequeño                    lo que cambia de una empresa a otra
```

Para otra empresa se escribe otro paquete. El motor no se toca.

**Por qué de cero.** El bot actual tiene 27.261 líneas, 42 módulos de agentes y varias piezas que deciden lo mismo. Lo que vale de él
son los datos y las lecciones, no el código. Un prototipo de una sola llamada (V1) ya igualó al bot entero en fallos graves, con
respuestas unas tres veces más cortas, un 30 % más rápido y una cuarta parte de las llamadas.

**Por qué esta vez no acaba en parches.** Por cuatro cambios en la forma de trabajar, no en el código:
1. **Cada corrección tiene un sitio fijo**, y casi nunca es el código (§5).
2. **Las metas y los umbrales se fijan antes de medir** y solo los cambiáis vosotros.
3. **Lo exacto se comprueba por código, no con un juez IA.** El juez queda como ayudante, y calibrado contra vuestro criterio.
4. **La salida a clientes reales es por peldaños y con personas delante:** primero el bot escribe sin que nadie lo vea, luego propone
   y una persona aprueba, y solo al final contesta solo, acción por acción.

**Las fases:**

| Fase | Qué se hace | Puerta de salida |
|---|---|---|
| F0 | Acuerdo, repo nuevo y cimientos | Constitución firmada y decisiones resueltas |
| F1 | El paquete de Diving Planet (solo datos) | Datos validados y aprobados por Gadea |
| F2 | La vara de medir, congelada, y el bot actual medido | Vara congelada y umbrales fijados |
| F3 | El motor mínimo, en local | No es peor que el bot actual, con un solo examen |
| F4 | El canal y la operación, en PRE | Funciona por Chatwoot, con vuelta atrás ensayada |
| F5 | Ciclos de mejora | El examen cumple las metas, confirmado |
| F6 | Sombra con conversaciones reales | Lo exacto bien en turnos reales y una muestra aprobada por personas |
| F7 | Borrador con aprobación y autonomía por acción | Cada acción se gana su autonomía con cifras |
| F8 | Apagar el bot viejo | Repo viejo archivado |
| F9 | Segundo negocio | Otro paquete funciona sin tocar el motor |

**Lo que os pide a vosotros:**
- las decisiones de §16;
- de 3 a 4 horas, una vez, para calibrar al juez (§10.4). Es lo único que cambia algo que ya habíais dicho («la calidad la comprueban
  los Claude»);
- unos 30 minutos por semana para aprobar correcciones;
- acordar entre los dos cuándo hablar con Andrés: el plan necesita de él unas 25-30 conversaciones nuevas y, más adelante, a su equipo (§16.4).

**Lo que no promete.** Fechas cerradas ni un bot perfecto. La investigación es clara: ningún bot de atención llega al 100 %. Por eso
el plan no depende de la perfección para dar valor: desde F7 el bot ya ayuda como borrador, con una persona aprobando.

## 2. Qué vamos a construir

**Lo que hace el asistente al acabar el plan:**
- Contesta por WhatsApp, en español e inglés, dudas de planes, precios, horarios, requisitos y logística.
- Da el precio por persona del catálogo y el enlace de reserva que toca, o dice por qué lo reserva un asesor.
- Pasa con una persona, con una nota resumen, cuando lo mandan las reglas de Gadea o el cliente lo pide.
- Dice que es un asistente virtual y ofrece siempre la salida a una persona.

**Lo que no hace, por diseño:**
- No cobra ni devuelve dinero. No cambia ni cancela una reserva ya hecha. No decide sobre una condición médica.
- No calcula: los precios, las fechas y los enlaces se los da el código.
- No promete nada que no esté en los datos.
- No aprende solo: cada cambio pasa por una persona.

**Cómo sabremos que es profesional:**

| Cualidad | Qué significa aquí |
|---|---|
| Limpio | Un motor pequeño; el negocio en datos; cada cosa en un solo sitio |
| Robusto | Un importe o un enlace que no esté en los datos se detecta y se rehace; si el importe sigue mal, pasa con una persona. Lo que esa comprobación no ve, como el precio de otro plan, lo miden las fichas. Si el modelo no contesta, pasa con una persona |
| Sencillo | Una pieza decide. Una llamada por mensaje, o dos si pide un cálculo (§16.4). Sin capas que se corrigen unas a otras |
| Reutilizable | Otro negocio es otro paquete de datos |
| Operable | Versiones, vuelta atrás, copias de seguridad, alertas y costes a la vista |

## 3. Por qué de cero, y qué cambia frente al Plan V1

**Lo que dice la evidencia** (detalle y fuentes en `docs/investigacion/informe-como-construyen-bots-fiables.md`):

| Lo que nos pasó | Lo que explica la investigación |
|---|---|
| Cada regla nueva rompía otra | Cumplir todas las instrucciones cae de ~0,95 con una a 0,21-0,48 con diez (ManyIFEval). Anthropic desaconseja las listas de casos límite en el prompt |
| Nada movía el número | Con 40 clientes y una pasada el margen es ±12 puntos. Ver 3 puntos pide ~1.000 conversaciones |
| El juez cambiaba de opinión | Un juez IA acuerda con personas solo «moderadamente» (kappa 0,4-0,5) y varía entre pasadas |
| El código pisaba las respuestas | Los líderes tienen vigilantes que bloquean o escalan, casi nunca editan |
| Varias piezas decidían | En casi todos los líderes, quien escribe es quien decide; el código calcula y ejecuta. (En Fin, el pase lo decide otro modelo.) |

**Lo que V1 no resolvía**, y este plan ataca: hacía mal las cuentas (el 81 % de sus graves eran el descuento de grupo y la hora de volar, §19.5; 13 importes fuera del catálogo de 272), fallaba el idioma y preguntaba en el 75 % de sus primeras respuestas. De sus 71 pases en 120 charlas (45 el bot actual), 52 eran por una regla de Gadea y 17 salían de una frase genérica que hay que arreglar. Además leía la misma base que el
juez, lo que la favorece.

**Qué se queda del Plan V1 v4.1** (del Claude de Gadea, con las decisiones de Gadea del 10-nov):
- la regla de diseño: el código calcula hechos, el modelo decide y escribe, la puerta comprueba hechos;
- la tabla de decisiones, escrita a ciegas desde cada decisión;
- los tres instrumentos (sparring, examen, contadores) y sus papeles;
- las señales del bucle y las cuatro salidas cerradas;
- las metas y todas las decisiones de negocio del 10-nov (§16.1).

**Qué cambia, y por qué:**

| Cambio | Por qué |
|---|---|
| Se construye en un **repo nuevo**, en vez de borrar piezas del viejo | El viejo sigue vivo en PRE como referencia y vuelta atrás. La vara deja de depender del código del bot (hoy el juez arma su referencia desde `src`). Nace sin 27.000 líneas que podar |
| **Motor y negocio separados** desde el primer día | Es lo que hace el bot reutilizable, y lo que impide que las reglas del negocio vuelvan al código |
| El juez IA se **calibra con etiquetas de personas** | Sin eso, todo son Claudes juzgando a Claudes. Es el círculo que queremos romper |
| La salida a clientes reales es **por peldaños, con personas** | El Plan V1 acababa en «presentar a Andrés». De las cuatro causas de los fracasos conocidos, dos son soltar el bot sin anclarlo a los datos y sin salida a una persona |
| **Operación profesional** | Hoy no hay copias de seguridad, el webhook no comprueba firma y el CI solo ejecuta 19 de 296 ficheros de pruebas |

**Los riesgos de empezar de cero** están en §14, con su antídoto. El principal es el «segundo sistema»: querer meterle al nuevo todo
lo aprendido. Antídoto: al repo nuevo solo entra lo que la constitución permite.

---

# Parte B. La constitución

Estas reglas van como `CONSTITUCION.md` en el repo nuevo. **No cambian sin la firma de Gadea y de Álvaro.**

## 4. Las doce reglas

1. **Un solo decisor.** El modelo lee el mensaje, decide y escribe. Ninguna otra pieza decide qué decir.
2. **El código calcula y ejecuta.** Precios, descuentos, fechas, horas, enlaces y el pase a una persona son del código. El modelo
   nunca hace cuentas.
3. **Los vigilantes comprueban hechos; no escriben.** Si un dato de la respuesta no casa, se rehace una vez nombrando el hecho. Nunca
   se recorta ni se reescribe el texto.
4. **Las reglas del negocio son datos.** Cada una sale de una decisión de un dueño, se escribe una vez desde esa decisión y no desde un
   fallo visto. Solo cambia si cambia la decisión. **El conocimiento describe; no manda:** un texto de conocimiento no lleva
   instrucciones de conducta.
5. **El prompt base es del motor y está congelado.** Es corto, no habla de buceo y no se toca en el día a día. Cambiarlo es una
   versión mayor.
6. **Cada cosa, en un solo sitio.** Un precio, una hora o una regla viven en un lugar. Los textos no repiten cifras a mano.
7. **Nada entra sin una decisión escrita, y las reglas tienen techo.** Ni una pieza, ni una comprobación, ni una regla entran sin
   decisión. El número de reglas con que se cierra F1 es el techo: para añadir una, otra se quita o se funde, salvo excepción firmada
   por los dos. Por defecto, la respuesta a «¿y si añadimos…?» es no.
8. **La vara se fija antes y no se mira para arreglar.** Metas y umbrales se acuerdan antes de la medida que los informa. Del examen
   solo salen cifras.
9. **La realidad manda.** Una conversación real pesa más que una simulada, y una simulada más que una inventada.
10. **La autonomía se gana por acción y con cifras, y hay cosas que siempre lleva una persona:**
    - cobros y devoluciones;
    - cambiar o cancelar una reserva ya hecha;
    - quejas;
    - lo médico de verdad, tal como lo define la decisión `salud` (un mareo o una pregunta de embarazo no se pasan);
    - quien pide hablar con una persona.

    El bot sí da precios y enlaces: cotizar es su trabajo.
11. **Todo cambio es una versión.** Nada llega a un cliente sin versión, pruebas y vuelta atrás.
12. **Parar es un resultado válido.** Si se cumple una señal de parada (§13.3), se para y se habla. No se «prueba una cosa más».

## 5. Dónde va cada corrección

Esta tabla es el antídoto contra el Frankenstein. Cuando el bot falla, la corrección solo puede ir a uno de estos sitios:

| El bot falló porque… | La corrección va a… | Quién la aprueba | ¿Toca código? |
|---|---|---|---|
| No tenía el dato | El conocimiento del paquete, como descripción y sin instrucciones | Gadea | No |
| El dato estaba mal | La tabla del paquete (precios, horas, enlaces) | Gadea | No |
| No sabía cómo actuar y no hay decisión | Primero, una decisión de un dueño; luego, una regla, dentro del techo | Gadea | No |
| Un cálculo o una acción salió mal | El código de ese hecho, con su prueba | Revisión entre Claudes | Sí, poco |
| No cumple una regla bien escrita | Una de las cuatro salidas cerradas (abajo). **La regla no se reescribe** | Los dueños | Depende |
| Se vio una sola vez | Se guarda como ficha de regresión y se apunta. No se arregla hasta que su familia pese | — | No |
| Otra cosa | No se toca hasta entender por qué | — | No |

**Las cuatro salidas cerradas** cuando el modelo no cumple una regla bien escrita (son las del Plan V1 v4.1):
1. convertirlo en un hecho que calcula el código, si sale solo del reloj y de los datos;
2. una comprobación, pero solo de un hecho, nunca de conducta;
3. aceptar la cifra tal cual (si es una meta, eso es cambiar la meta, y lo decidís por escrito);
4. cambiar el modelo de toda la llamada, que se mide como una integración completa.

**Una excepción pactada (11-nov, §19.6):** si las fichas de puerta de la reserva fallan por una regla más allá del umbral de §11, esas reglas pasan al código, dentro de una herramienta «cómo reservar». Es una excepción a la regla 1, firmada por Gadea y Álvaro, con sus guardas: solo devuelve hechos, Luna sigue siendo la única que escribe, sus datos tienen que estar en lo entendido y ningún motivo sale sin una decisión escrita. No se construye por adelantado.

## 6. Lo que los Claudes no hacemos solos

El 10-nov el bucle pasó tres veces por nosotros: en el código, en el prompt y en el propio plan (cinco versiones en cuatro horas).
Las revisiones con agentes no lo frenaron, porque un revisor siempre encuentra algo. Por eso:

- **Un entregable, una revisión, una corrección.** Cada diseño y cada cambio tiene una revisión independiente con una lista cerrada:
  hechos falsos, choques con la constitución o con una decisión, huecos que impiden cumplir la puerta y sitios por donde vuelva el
  bucle. Se corrige una vez. Lo demás va al registro de pendientes, que veis vosotros.
- **No proponemos la siguiente versión sin mirar si la anterior movió algo.** Si no lo movió, paramos (regla 12).
- **No tocamos sin vuestra decisión:** el prompt base, las metas, los umbrales, una regla del negocio, una pieza nueva o el examen
  congelado.
- **No desplegamos.** A PRE y a producción sube quien vosotros digáis.
- **No gastamos sin avisar:** antes de cada medida, los saldos comprobados y un aviso en Coral.
- **Si un Claude ve al otro en el bucle, lo para.** Si los dos lo estamos, lo paráis vosotros con una palabra.

---

# Parte C. El diseño

## 7. Arquitectura

### 7.1 Las cuatro capas

Es la forma que comparten Sierra, Decagon, Intercom Fin, Ada, Parloa, Zendesk y Agentforce:

```
                         ┌─────────────────────────────────────────┐
  cliente ──▶ canal ──▶  │  EL AGENTE: lee, decide y escribe       │ ──▶ puerta ──▶ cliente
            (WhatsApp)   │  (una llamada al modelo)                │      │
                         └───────┬───────────────────────┬─────────┘      └─▶ si toca: pasar a una persona
                        lee      │                       │  recibe
                                 ▼                       ▼
                  📚 CONOCIMIENTO y 📋 REGLAS      🔢 HECHOS del código
                  (lo escribe el negocio)        (precios, fechas, enlaces)
```

| Capa | Qué es | Quién la mantiene |
|---|---|---|
| Conocimiento | Planes, políticas, preguntas frecuentes, lugares | El negocio |
| Reglas | Las decisiones de Gadea, una por fila, en lenguaje normal | El negocio |
| Hechos y acciones | Lo que el código calcula o ejecuta | Código, con pruebas |
| Vigilancia | Comprobaciones de hechos sobre la respuesta | Código, con pruebas |

### 7.2 Un mensaje, paso a paso

1. **Llega el mensaje** por Chatwoot. Se comprueba la firma, se descarta si ya se procesó y se pone en la cola de su conversación.
2. **Ráfagas:** opción (c), decidida por Gadea. Se contesta en cuanto llega; si mientras se genera llega otro mensaje, esa respuesta
   se tira sin enviarla y se genera otra con todo.
3. **Se carga la conversación:** el historial y lo que ya se entendió del cliente.
4. **El código prepara los hechos.** Fija el idioma del cliente con un detector determinista (§19.6) y da de antemano lo que sale solo del reloj y de los datos: la hora, el primer día que se puede reservar, el catálogo y la tarifa. Los cálculos que dependen del mensaje (el precio por persona de ese grupo con su moneda, si su vuelo alcanza y el enlace que toca) son herramientas: se entregan de antemano en una tabla o a petición de Luna, según la medida de F3 (§20.6).
5. **Una llamada al modelo**, con el prompt base, el paquete del negocio, los hechos, lo entendido y el historial. Devuelve tres cosas: lo que ha entendido del cliente, si hay que pasar con una persona y el texto. Si gana la entrega a petición, Luna puede pedir antes un cálculo, y entonces son dos llamadas.
6. **La puerta comprueba hechos:** que cada importe esté en la tabla, que cada enlace sea de un plan del catálogo y en su idioma, que el idioma sea el que fijó el código y que el vuelo alcance. Si algo no casa, se rehace una vez. Si un importe sigue mal tras rehacer, no se envía: pasa con un asesor y se cuenta aparte. En lo demás, sale el segundo texto y se cuenta como fallo.
7. **Se actúa:** se guarda lo entendido; si hay pase, se ejecuta con su nota resumen; se envía el texto. Tras un pase, el bot calla hasta que el asesor devuelva la charla.
8. **Se guarda la traza** del turno: versión, tiempos, coste y comprobaciones. De ahí salen los contadores y las pruebas futuras. Cada pase se apunta en el registro de pases (§19.6).

Los pasos 2 a 8 son del motor y no dependen de Chatwoot. Por eso el examen puede probarlos sin canal.

### 7.3 Decisiones de diseño, con su motivo

| # | Decisión | Motivo |
|---|---|---|
| D1 | Un solo modelo, con salida estructurada. Una llamada por mensaje, o dos cuando pide un cálculo, si gana la entrega a petición (§20.6) | Es V1, que ya está medido: mismos graves que el bot entero, 1 llamada frente a 3,76 y p90 de 4,0 s frente a 5,8 s |
| D2 | El conocimiento va entero en el contexto, con caché. Sin buscador | Cabe (~67.000 tokens) y la caché acertó el 96-99,6 %. Se quitan la base vectorial, los embeddings y el reindexado en cada despliegue. Un negocio que no quepa usará un buscador como módulo aparte |
| D3 | Los cálculos son herramientas: funciones con nombre, entradas y salida declaradas. Lo que no depende del mensaje se da de antemano. Para lo que depende del mensaje, la medida de F3 decide si se entrega de antemano o a petición (§20.6) | El modelo no calcula. V1 tenía el dato delante y lo aplicó mal en el 81 % de sus graves (§19.5). La puerta puede comprobarlo |
| D4 | El motor sabe llamar herramientas desde el primer día. Solo devuelven hechos, nunca conducta ni texto para el cliente. Las de sistemas en vivo, cuando un negocio las tenga | Es como lo hacen las empresas (§20.5) y lo que hace el motor reutilizable. Diving Planet no tiene datos en vivo: ese hueco se diseña, no se construye a ciegas |
| D5 | El modelo queda fijado en cada versión. Sin modelo de respaldo | Como en el Plan V1 v4.1: un respaldo sería un segundo escritor. Si el modelo no contesta, aviso sincero y pase a una persona. Cambiar de modelo reinicia la evidencia |
| D6 | La puerta solo comprueba hechos y rehace una vez. Si un importe sigue mal, pasa con un asesor | Es la regla de diseño acordada el 10-nov, con la decisión de Gadea sobre el segundo fallo. Cuando la puerta juzgó conducta (V2), rehízo alrededor del 65 % de las respuestas a mensajes reales (medida del 10-nov, Coral #3772) |
| D7 | El idioma lo fija el código con un detector determinista, sin respaldo con LLM. La puerta comprueba que Luna conteste en ese idioma | Decidido el 11-nov (§19.6). V1 falló el idioma en 38 juicios; el bot actual, que lo fija por código, en ninguno |
| D8 | Una sola base de datos (Postgres) para conversaciones, estado y trazas | Menos piezas. Hoy el estado vive en Redis con 81 campos y las tablas de análisis nunca se escriben. Se confirma en el diseño de F4 |
| D9 | Cada despliegue es una foto: código, prompt base, paquete y modelo | Permite volver atrás y saber qué versión contestó cada mensaje |
| D10 | El motor no conoce el negocio. Una comprobación automática lo vigila | Es lo que lo hace reutilizable |
| D11 | Sin router ni segundo modelo: los saludos también los contesta Luna. Sin LangGraph ni MCP | §19.3 y §20.3. El recorrido es una línea recta de cuatro pasos. Lo de LangGraph se confirma en el diseño de F3 |

### 7.4 Lo que el motor hace igual para cualquier negocio

- Conversar con una llamada y salida estructurada.
- Cargar un paquete de negocio y validarlo.
- Calcular los hechos genéricos: reloj y zona horaria, primer día reservable con hora de corte y días cerrados, precios con descuentos e idioma del cliente. Cada uno es una herramienta, y el motor sabe llamarlas.
- La puerta de importes, enlaces e idioma.
- El pase a una persona con nota resumen.
- La mecánica de la conversación: duplicados, cola, ráfagas.
- El canal: firma y límites de WhatsApp.
- Las trazas, los contadores, el registro de pases y las versiones.

Lo propio de un negocio (por ejemplo, la espera antes de volar tras bucear) va en su paquete, como un cálculo pequeño con su prueba.

## 8. El paquete del negocio

```
negocios/diving-planet/
  negocio.yaml      identidad, idiomas, zona horaria, nombre del asistente, aviso de que es un asistente virtual
  conocimiento/     servicios, políticas, preguntas frecuentes, lugares (texto que lee el agente)
  tablas/           precios (fuente única), descuentos, horas oficiales, enlaces por plan, origen e idioma
  reglas.yaml       una fila por decisión: id, fecha, quién decidió, texto para el agente, tipo y sus casos de prueba
  hechos/           cálculos propios del negocio, con sus pruebas (la hora mínima de vuelo)
  casos/            las fichas de prueba de este negocio
```

**Reglas del paquete:**
- **Una sola fuente por dato.** Hoy los precios están en `pricing.json` y además escritos a mano en más de 70 líneas de textos (44 en
  las FAQ, 20 en las curadas, y más en políticas, decisiones y avisos). Las horas, en más de 50. En el paquete nuevo los textos no
  llevan cifras a mano: se insertan desde las tablas al construirlo, y un validador lo comprueba.
- **El conocimiento describe y las reglas mandan.** Un texto de conocimiento dice qué es un plan, qué incluye o cuánto dura. Si dice
  «si el cliente…» o «debes…», es una regla y va a `reglas.yaml`, con su decisión y dentro del techo. El validador lo avisa y la
  revisión de cada cambio lo comprueba.
- **Cada regla lleva su origen:** la decisión, la fecha y quién la tomó. Sin decisión no hay fila.
- **Cada regla lleva sus casos:** al menos uno donde aplica y uno donde no.
- **El paquete se valida solo:** que cada plan tenga precio en las dos monedas, que cada enlace exista, que no falte idioma.
- **Cambiar el paquete es un cambio con versión:** queda quién lo aprobó y qué pruebas pasó.

**De dónde sale el de Diving Planet:**

| Se lleva | Desde | Qué hay que hacer |
|---|---|---|
| Catálogo: 38 servicios, 18 de ellos variantes «ya en las islas» | `services.json` | Limpiar y quitar cifras de los textos |
| Tarifa 2026: 51 entradas, COP y USD, normal y online | `pricing.json` | Dejarla como única fuente de precios |
| Descuentos | `discounts.json` | Generar la tabla de precios por persona con descuento |
| 62 políticas y 112 preguntas curadas | `policies.json`, `curada/faqs.json` | Revisar duplicados, cifras a mano e instrucciones escondidas |
| Lugares: 8 hoteles con recogida, 37 sitios de las islas | `lugares.json` | Tal cual |
| Horas oficiales y cierres | `valores.json`, `availability.json` | Una sola tabla |
| 31 decisiones, más las del 10-nov | `decisiones.json`, memoria del equipo | La tabla de reglas (F1) |
| Tono de marca | `brand_tone.json` | Revisar con «breve y concisa» |

**No se lleva:** `escalation_rules.json` (desfasado, ningún código lo lee), `faqs.json` (el juego antiguo), `avisos.json` (textos
que el código pegaba) y `curada/preguntas.json` (solo servía al buscador).

## 9. Infraestructura y operación

**Entornos.** Hoy solo existe PRE: un servidor con el bot, Chatwoot y sus bases. Producción y la API de WhatsApp Business figuran como
pendientes, y a los clientes reales los atiende el equipo sin bot.

| Entorno | Para qué | Cuándo |
|---|---|---|
| Local | Desarrollo y pruebas | F0 |
| PRE | Pruebas por Chatwoot, con datos de prueba | F4 |
| Producción | Clientes reales | Se prepara desde F4 y se usa desde F6 |

**Lo que se monta, una vez y bien:**
- **Despliegue por versiones** con vuelta atrás de un comando. Hoy el último que sube gana y no hay control.
- **Copias de seguridad** de la base de datos, con una restauración ensayada. Hoy no hay.
- **Secretos** fuera del repo y con acceso mínimo. Hoy el despliegue entra como administrador del servidor.
- **Webhook con firma comprobada.** Hoy no la comprueba.
- **Alertas:** saldo bajo de los proveedores, errores del modelo, pases que nadie atiende, latencia alta. El saldo agotado ya nos
  dejó sin servicio varias veces.
- **Panel sencillo:** conversaciones, turnos, tiempo, coste, comprobaciones de la puerta y pases.
- **Pruebas en cada cambio:** todas, no una lista a mano. Hoy el CI ejecuta 19 de 296 ficheros.
- **Repo ligero:** las tiradas y los resultados de las medidas no van al repo de código. Hoy `docs/robustness` pesa 626 MB.

**WhatsApp** (datos de la documentación de Meta recogidos en la investigación; las tarifas de Colombia hay que confirmarlas):
- Se cobra por mensaje. Dentro de las 24 horas desde el último mensaje del cliente, las respuestas libres son gratis hasta 1.000 al
  mes por número desde el 1-oct-2026. Fuera de esa ventana solo valen plantillas aprobadas, que se pagan.
- Límite de 1 mensaje cada 6 segundos por cliente: una respuesta por ráfaga.
- Botones: 3 como mucho. Listas: 10 filas.
- El número de producción tiene que estar en la API de WhatsApp Business. Hay que comprobar si puede convivir con la aplicación que
  usa hoy el equipo (§16.3).

**Datos de clientes.** Hay tres casos distintos, y cada uno necesita su regla antes de la puerta de F4:

| Caso | Regla propuesta |
|---|---|
| Exportaciones antiguas de WhatsApp, sin anonimizar | No salen de quien las custodia. Se anonimizan en su máquina antes de cualquier uso |
| Mensajes en vivo (sombra, borrador, autónomo) | Los procesa el proveedor del modelo y se guardan en nuestra base. Hace falta el aviso al cliente, la base legal y las condiciones del proveedor (que no entrene con ellos). Hoy no está resuelto |
| Lo que leemos los Claudes | Solo lo anonimizado, o lo que autoricéis de forma expresa |

**Avisos legales.** No es asesoría legal; hay que confirmarlo con quien corresponda (§16.3):
- El asistente dice que es un asistente virtual. En la UE es obligatorio desde agosto de 2026 (AI Act, art. 50).
- La empresa responde por lo que dice su bot igual que por su web (caso Air Canada).
- No se guardan ni se repiten números de tarjeta. Qué hace el bot con un dato así es una decisión pendiente de Gadea (`privacy.py`).

---

# Parte D. La vara

## 10. Cómo sabemos si está bien

Cuatro preguntas distintas, cada una con su instrumento. No se mezclan.

| Pregunta | Instrumento | Quién juzga | Cuándo |
|---|---|---|---|
| ¿Los datos exactos salen bien? | Pruebas de código y fichas | El código | En cada cambio |
| ¿Se comporta como decidió el negocio? | Fichas por regla y el examen | El código y un juez calibrado | En cada cambio y en cada integración |
| ¿Sirve con clientes de verdad? | Sombra, borrador y autonomía por acción | Personas | Desde F6 |
| ¿Qué familias de fallo hay? | Sparring y lectura de conversaciones | Claudes, con muestra para vosotros | En cada ciclo |

### 10.1 Pruebas de código

Los cálculos (precios, descuentos, primer día reservable, vuelo), la puerta, la mecánica de la conversación, el canal y la validación
del paquete. Son gratis, no tienen ruido y corren todas en cada cambio.

### 10.2 Fichas

Una ficha es una conversación corta con su respuesta correcta ya calculada: qué precio debe salir, qué enlace o ninguno, en qué
idioma y si debe pasar con una persona.

- **El contrato de salida se fija en F2:** qué devuelve el bot por separado (lo entendido, si pasa y el texto). Gracias a eso, casi
  toda la conducta se comprueba sin juez: «marcó pasar», «entendió que sale de las islas», «el texto lleva 178 USD», «el texto no
  lleva enlace».
- **El bot actual se mide con un adaptador** que traduce lo que él guarda (su estado y su marca de pase) a ese mismo contrato.
- **Cada ficha se repite 5 veces.** El modelo no contesta siempre igual, y para un cliente lo que cuenta es acertar siempre.
- **La respuesta correcta la calcula un código de medida** que vive aparte y nunca entra en el bot (decisión del Plan V1).

**Hay dos juegos de fichas, y no se mezclan:**

| Juego | Qué contiene | Para qué |
|---|---|---|
| **Fichas de puerta** | Las de cada regla (una donde aplica y una donde no), las de los hechos y las de manipulación | Deciden las puertas. Se congelan en F2. Una regla nueva trae las suyas, escritas desde la decisión antes de tocar nada |
| **Fichas de regresión** | Cada fallo real que se vea, aunque sea una sola vez | Vigilan que algo arreglado no vuelva. No abren ni cierran puertas, y guardar una no obliga a arreglarla |

**Fichas de manipulación y de fuera de tema.** Un juego fijo de intentos de engañar al bot: que regale un precio, que cambie sus
reglas, que insulte, que hable de otra cosa. Dos de los fracasos públicos conocidos fueron por esto.

### 10.3 El examen

Es el del Plan V1, tal cual: unos 200 clientes que reaccionan, con la mezcla de los reales (un tercio ya ha reservado, un 11 % son
agencias, un 15 % pregunta lo que la base no contesta), dos relojes (antes y después del cierre), ráfagas como las reales y fichas de
objetivo escritas por un agente que no conoce el bot.

- **Se congela con su huella** antes de medir nada.
- **Solo devuelve cifras.** Nadie lee sus conversaciones para arreglar algo.
- **Un examen por integración**, anunciado antes. No se lanza uno «a ver si sale».
- **La confirmación:** si un examen cumple las metas, se repite una vez con la misma versión. Si la confirmación falla, esa versión
  no pasa y su examen no se vuelve a repetir.
- **Siempre 2 juicios por tirada.** Con 200 clientes y 3 tiradas, una diferencia en graves cuenta si supera unos 4 puntos. El ruido
  de cada cifra se mide en F2 con las tiradas del bot actual.
- **Una regla nueva o cambiada entra a la vez** en la referencia del juez y en las fichas de puerta, y la línea de partida se vuelve
  a juzgar con ella.

### 10.4 El juez, calibrado

El juez es un Claude. La calibración que existe es de septiembre y muy pequeña (17 ejemplos, 9 etiquetas de Gadea). La
investigación dice que, sin medir cuánto coincide con una persona, un juez no es fiable.

- **Lo que hace falta:** que una persona que sabe del negocio etiquete respuestas como «vale» o «no vale», con una línea de por qué.
- **Cuántas:** las necesarias para tener al menos 60 que valen y 60 que no. Serán entre 150 y 200, elegidas para que haya de las dos.
  Son de 3 a 4 horas, que se pueden repartir.
- **Cómo se usan:** la mitad sirve para ajustar las instrucciones del juez. La otra mitad se guarda y se usa una sola vez, para
  examinarlo.
- **El umbral se fija antes de etiquetar** (§16.2). Propuesta: que pille al menos 8 de cada 10 fallos de verdad y no dé por malas más
  de 2 de cada 10 respuestas buenas.
- **Si el juez no llega,** no decide los graves. Elegís entre dos caminos: cambiar de juez y repetir el examen del juez, o que los
  graves de cada integración los cuente una persona sobre 100 clientes del examen (con un margen de ±6 a ±8 puntos, dicho de antemano).
- **Se repite** si cambia la rúbrica o el modelo del juez.
- **Quién etiqueta:** Gadea y Álvaro, y Gonzalo si está (decidido el 11-nov). Las personas, no los Claude. Se pueden etiquetar respuestas a los 75 mensajes reales ya vistos: para calibrar basta con que sean reales.

### 10.5 Sparring y lectura de conversaciones

Sirven para **descubrir**, nunca para decir que algo mejoró.

- **Sparring:** un Claude hace de cliente nuevo cada vez y otro, que no lo escribió, lo juzga dos veces.
- **Lectura:** los Claudes leemos conversaciones anonimizadas, agrupamos los fallos por familia y contamos cuántas veces sale cada
  una.
- **Una familia pesa** si sale en 3 o más charlas distintas de 30, con las dos pasadas del juez de acuerdo. Por debajo, espera.
- **Vosotros veis un resumen de una página** y una muestra: los peores y unos al azar.

### 10.6 Las conversaciones reales

| Qué hay | Cuánto | Uso |
|---|---|---|
| Episodios reales anonimizados, con las respuestas del equipo | 75 episodios de 39 chats | Desarrollo: calibrar al juez, las proporciones y el estilo, la semilla del sparring y una comparación al lado. Ya se han leído y medido, así que no cuentan para ninguna puerta |
| «Examen oculto» | 13 chats, que son 21 de esos mismos 75 episodios | Igual que los anteriores: ya no es una reserva limpia |
| Conversaciones nuevas de Andrés | Por pedir: bastan unas 25-30 charlas recientes | **La única reserva limpia.** No se leen hasta la puerta de F6 |

**Sin conversaciones nuevas no hay sombra histórica.** Por eso pedirlas es una decisión de F0 (§16.2), no un detalle.

**Sombra histórica:** en cada turno de una conversación real, el bot escribe lo que habría contestado, con el historial real hasta ese
punto. Se compara con lo que contestó la persona. Límite conocido: no vale para juzgar el estilo de toda la charla, porque el bot la
habría llevado por otro camino.

## 11. Metas, umbrales y puertas

**Las metas de «robusto»** son las del Plan V1:

| Medida | Meta | Estado |
|---|---|---|
| Clientes con fallo grave en el examen | ≤ 10 % | Fijada por Gadea. La confirma con la rúbrica cerrada en F2 |
| Importes mal | 0, contados contra la ficha y antes de la puerta | Propuesta del Plan V1, pendiente de Gadea (§16.2) |
| Enlace e idioma mal | 0, contados contra la ficha y antes de la puerta | Como en el Plan V1 |
| p90 del turno | ≤ 7,5 s | Fijada |
| Largo mediano | ≤ 300 caracteres | Fijada |
| Primeras respuestas con pregunta | ≤ 50 % | Fijada por Gadea |
| Pases indebidos y pases que faltan | Sin meta, contados | Fijada por Gadea |

Se cuentan antes de la puerta porque después el cero sale solo. Lo que llega al cliente se cuenta también, aparte.

**Los umbrales que faltan, en una sola lista.** Cada uno se fija antes de la medida que lo informa:

| Umbral | Propuesta de partida | Quién lo fija | Cuándo |
|---|---|---|---|
| Acierto mínimo del juez | 8 de 10 fallos pillados; como mucho 2 de 10 buenas dadas por malas | Los dueños | F0, antes de etiquetar |
| Respuestas que la puerta rehace | ≤ 10 % de los turnos | Los dueños | F0 |
| Cumplimiento de las reglas críticas en sus fichas | Por decidir | Los dueños | Puerta de F2, con el bot actual medido y antes de medir el motor |
| Ruido de cada cifra de la tabla de metas | Se mide, no se decide | — | F2, con las tiradas del bot actual |
| Muestra de F6: «la habría enviado» | Por decidir, sobre 100 respuestas (margen de ±8 a ±10 puntos) | Los dueños | Puerta de F2 |
| Subir y bajar de peldaño en F7 | Ver F7 | Los dueños | Puerta de F6, antes de ver un solo borrador |
| Diferencia mínima entre entregar los cálculos de antemano o a petición (§20.6) | Por decidir | Los dueños | Puerta de F2, antes de la medida de F3 |

- **Reglas críticas** son las de la regla 10 y las de precio.
- **Solo vosotros cambiáis una meta o un umbral, y por escrito.**

---

# Parte E. Las fases

Una fase no empieza hasta que la anterior cruza su puerta. Cada puerta la abrís vosotros.

### F0 · Acuerdo y cimientos

- **Objetivo:** empezar con las reglas claras y el terreno preparado.
- **Qué se hace:**
  - leéis este plan y decidís lo que queda de §16.2;
  - se crea el repo nuevo con la constitución, la plantilla de decisiones de diseño, las pruebas automáticas y la rama principal
    protegida (todo cambio entra con revisión);
  - se etiqueta el bot actual en git (hoy no hay ninguna etiqueta) y queda congelado: solo se tocan datos y urgencias;
  - Gadea y Álvaro acuerdan cuándo y cómo hablar con Andrés, y qué se le pide: unas 25-30 conversaciones nuevas, la API de WhatsApp y su equipo en Chatwoot;
  - se arrancan los trámites largos, con su responsable: API de WhatsApp Business y entorno de producción.
- **Puerta:** constitución firmada, decisiones de §16.2 resueltas o aparcadas con dueño y fecha, repo creado y bot actual etiquetado.
- **No se hace:** ninguna línea del bot.

### F1 · El paquete de Diving Planet

- **Objetivo:** que todo lo que el bot tiene que saber esté en datos, una vez y bien.
- **Qué se hace:**
  - **la tabla de reglas:** una fila por decisión (las 31, «breve y concisa» y las del 10-nov). El estudio de §19.4 cuenta 77 reglas, 73 de ellas como texto. Se arregla lo que ese estudio encontró en el texto de V1, y la frase genérica de «si no está, pasas» se alinea con la decisión de lo que queda fuera de la base. Cada fila la escribe un agente que
    solo ve la decisión, y la revisa otro. Se resuelven los choques (`cambio-de-fecha`, `por-otros`, `temas-3nov`). Las decisiones
    que son un hecho o una comprobación no cuentan como regla;
  - **las tablas:** precios como única fuente, precios por persona con descuento, horas, enlaces;
  - **el conocimiento:** catálogo, políticas y preguntas, sin cifras a mano y sin instrucciones;
  - **el validador** del paquete;
  - **una «ficha del negocio» legible**, generada desde los datos, para que Gadea confirme que todo es correcto.
- **Puerta:** el validador pasa, no queda ningún choque abierto y Gadea aprueba la ficha del negocio y la tabla de reglas. **El número
  de reglas de ese día es el techo** (regla 7).
- **No se hace:** escribir reglas mirando conversaciones o fallos.

### F2 · La vara, congelada

- **Objetivo:** tener el instrumento antes que el bot, para no ajustar el uno al otro.
- **Qué se hace:**
  - el contrato de salida y el adaptador del bot actual (§10.2);
  - las fichas de puerta, con las de manipulación, y el código de medida que calcula la respuesta correcta;
  - el examen de ~200 clientes y su arnés (ráfagas, dos relojes), congelados con su huella;
  - la rúbrica cerrada, con los graves separados de la fricción;
  - la sesión de etiquetado y la calibración del juez (§10.4);
  - **se mide el bot actual** con todo ello: es la línea de partida, y de sus tiradas sale el ruido de cada cifra;
  - se fijan los umbrales que tocan en esta puerta (§11).
- **Puerta:** vara congelada, bot actual medido, juez por encima de su umbral (o decidido quién cuenta los graves), umbrales fijados
  y metas confirmadas por Gadea con esa rúbrica.
- **Aviso:** si el bot actual ya cumple el 10 % en el examen, se os avisa antes de seguir, porque la meta no distinguiría.
- **No se hace:** tocar el examen o las fichas de puerta después de congelarlos.

### F3 · El motor mínimo

- **Objetivo:** el agente funcionando en local, sin Chatwoot.
- **Qué se hace:**
  - el prompt base, corto y sin negocio. **Se escribe una vez, se revisa una vez y se congela con su huella antes del examen;**
  - la llamada con salida estructurada y caché;
  - los hechos, construidos como herramientas: reloj, primer día reservable, idioma, precios, vuelo y enlace;
  - la puerta: importes, enlaces, idioma, vuelo;
  - **la medida de entrega** (§20.6): con las fichas de puerta de cálculo, de antemano o a petición. Se hace una vez, antes del examen y con el criterio fijado en F2. La forma que pierde se borra;
  - la mecánica de la conversación: duplicados, cola y ráfagas con la opción (c);
  - las trazas y los contadores;
  - un **negocio de juguete** (tres servicios inventados de otra actividad) para probar que el motor no sabe de buceo.
- **Puerta:**
  - todas las pruebas de código pasan;
  - el motor funciona con el negocio de juguete sin cambiar una línea;
  - pasan las fichas de manipulación;
  - **un solo examen**, frente al bot actual y con el mismo arnés: no es peor en graves más allá del ruido.
- **Las metas completas no se exigen aquí.** Se apuntan todas las cifras. Lo que no llegue, incluido el estilo, va a F5 por las
  salidas de §5, nunca retocando el prompt base.
- **Señal de parada:** si sale peor que el bot actual en graves por más que el ruido, se para y se habla.
- **No se hace:** añadir reglas o comprobaciones para subir la nota, ni repetir el examen.

### F4 · El canal y la operación

- **Objetivo:** el motor atendiendo por Chatwoot en PRE, operado como un servicio serio.
- **Qué se hace:**
  - el canal: firma y límites de WhatsApp;
  - el pase a una persona: nota resumen y cambio de estado en Chatwoot. Después el bot calla hasta que el asesor devuelva la charla;
  - el fallo técnico: aviso sincero y pase;
  - el registro de pases (§19.6): el turno y la etapa, el motivo de la tabla de reglas, quién lo decidió y, después, la etiqueta de una persona;
  - la base de datos, las versiones, la vuelta atrás, las copias, los secretos, las alertas y el panel (§9);
  - el aviso, desde el primer mensaje, de que es un asistente virtual.
- **Puerta:**
  - una ronda de prueba completa por Chatwoot en PRE, con las fichas de manipulación;
  - ensayados: una vuelta atrás, una restauración de copia y una caída del proveedor del modelo;
  - resuelto, con responsable y fecha: los datos de clientes (§9) y el camino a producción (número de WhatsApp y quién atiende
    por Chatwoot);
  - sube Gadea, o quien ella diga.
- **No se hace:** conectar clientes reales.

### F5 · Ciclos de mejora

- **Objetivo:** llegar a las metas sin parches.
- **Cada ciclo:**
  1. sparring de 30 charlas y lectura;
  2. familias que pesan;
  3. para cada una, su sitio según §5. Si falta una decisión, es una pregunta para vosotros;
  4. arreglo, con una revisión;
  5. **el ciclo se cierra con las pruebas de código y las fichas del arreglo:** dicen si el arreglo hace lo que dice. No dicen si el
     bot mejoró, y el sparring tampoco;
  6. versión nueva.
- **Una integración** junta uno o más ciclos cerrados y es lo único que dice si el bot mejoró: pasa el examen. Se anuncia antes.
- **Si entra una regla nueva,** entra a la vez en la referencia del juez y en las fichas de puerta, y la línea de partida se vuelve a
  juzgar.
- **Revisión de rumbo cada 3 ciclos** con vosotros: qué se movió, cuánto código y cuántas reglas hay, y si seguimos.
- **Puerta:** un examen cumple todas las metas y el de confirmación también.
- **Señales de parada:** las de §13.3.

### F6 · Sombra con conversaciones reales

- **Objetivo:** ver el bot ante clientes de verdad sin que ninguno lo vea.
- **Qué hace falta antes:** las conversaciones nuevas de Andrés (al menos 200 turnos de cliente), anonimizadas por quien las
  custodia, o producción ya conectada.
- **Qué se hace:**
  - **sombra histórica** sobre esas conversaciones nuevas;
  - **sombra en vivo**, si producción ya está conectada: el bot escribe su respuesta como nota interna y el equipo contesta como
    siempre. Se compara después.
- **Puerta:**
  - en al menos 200 turnos reales: lo exacto bien según las metas de §11, y los pases indebidos y los que faltan, contados y
    aceptados por vosotros;
  - una muestra de 100 respuestas revisada por una persona del negocio, por encima del umbral fijado en F2;
  - fijados los umbrales de F7.
- **Hito:** presentación del bot a Andrés. Quién da el visto bueno final es una decisión de §16.2.

### F7 · Borrador con aprobación y autonomía por acción

- **Objetivo:** que el bot empiece a dar valor con una persona delante, y gane autonomía donde lo demuestre.
- **Las acciones.** Cada respuesta se clasifica por código, a partir de lo que devuelve el bot: informar, dar un precio, dar un
  enlace o pasar con una persona. La autonomía se gana acción por acción, no para todo el bot.
- **Los peldaños:**

| Peldaño | Qué hace el bot | Quién envía |
|---|---|---|
| 1. Borrador | Propone la respuesta | La persona, tras aprobar o corregir |
| 2. Autónomo con muestreo | Contesta solo esa acción. Se revisa una muestra | El bot |
| 3. Autónomo | Contesta solo esa acción | El bot |

- **Para subir un peldaño,** una acción necesita las dos cosas: al menos 200 borradores **y** al menos dos semanas. Y además, 9 de
  cada 10 enviados sin corregir el fondo y ningún error de precio. Son cifras de partida tomadas de la investigación; las fijáis en
  la puerta de F6.
- **Para bajar,** un interruptor automático: un error de precio, o demasiadas correcciones en los últimos 50 envíos, devuelven esa
  acción al borrador.
- **Lo que reinicia la evidencia:**
  - un cambio de modelo o de prompt base devuelve todas las acciones al peldaño 1;
  - un cambio de regla, las acciones que toca;
  - un cambio de dato (un precio), no, si pasan sus fichas.
- **Nunca suben:** las cosas de la regla 10.
- **Cada corrección de una persona** se guarda como ficha de regresión y pasa por §5.

### F8 · Apagar el bot viejo

- El repo viejo se archiva en solo lectura. Se conservan las decisiones, la historia y los datos de medida.
- Se escribe el manual de operación: cómo desplegar, volver atrás, cambiar un precio y añadir una regla.
- La memoria del equipo y Coral se mudan al repo nuevo.

### F9 · Segundo negocio

- **Objetivo:** demostrar que es reutilizable con un negocio real.
- **Qué se mide:** cuántos días cuesta montar su paquete y cuántas líneas del motor hubo que tocar.
- **Meta:** cero cambios en el motor, salvo una herramienta nueva declarada si ese negocio tiene datos en vivo.

---

# Parte F. Gobierno

## 12. Quién hace qué

Es una propuesta; los papeles los decidís vosotros (§16.2).

| Quién | Qué decide o hace |
|---|---|
| Gadea | Las reglas y los datos del negocio, las metas, y qué sube a PRE y a producción |
| Álvaro | La constitución con Gadea, el alcance, los costes, la relación con Andrés y los trámites de WhatsApp y producción |
| Los dos | Abrir cada puerta y cualquier excepción a la constitución |
| Equipo de Andrés | Dar conversaciones nuevas, aprobar borradores en F7 y, si se decide así, etiquetar para calibrar al juez |
| Claude de Gadea y Claude de Álvaro | Construir, medir y revisarse el uno al otro. Proponer con datos |
| Gonzalo | Cuando se conecte, una parte acotada que le asignéis |

**Dentro de cada fase**, los dos Claudes llevan entregables distintos y cada uno revisa el del otro. Nunca dos fases a la vez.

## 13. El ritmo y las señales de parada

### 13.1 El ritmo semanal

| Momento | Qué pasa | Vuestro tiempo |
|---|---|---|
| Inicio de semana | Los Claudes os pasan una página: qué se hizo, las cifras, las familias de fallo y las preguntas de negocio | 10 min de lectura |
| Decisión | Aprobáis o rechazáis las correcciones propuestas y contestáis las preguntas | 20 min |
| Resto de la semana | Se hace lo aprobado, se revisa y se versiona | — |
| Puerta de fase | Se os presenta la evidencia de la puerta | Cuando toque |

### 13.2 Dónde se apunta todo

- **Registro de decisiones:** cada decisión vuestra, con fecha. Es de donde salen las reglas.
- **Registro de pendientes:** lo que una revisión encontró y no entra ahora.
- **Marcador:** una línea por integración, con las cifras de §11, las líneas de código y el número de reglas.
- **Memoria del equipo:** se lee al empezar cada sesión, como hoy.

### 13.3 Señales de parada

| Señal | Qué se hace |
|---|---|
| El motor sale peor que el bot actual en graves por más que el ruido (F3) | Se para y se habla |
| Una integración no mejora ninguna de las metas de §11 más que su ruido, y no las cumple | Se para. Se escribe «qué estamos haciendo mal» antes de tocar nada |
| El examen de confirmación falla | Esa versión no pasa y su examen no se repite |
| Tres integraciones seguidas sin llegar a la meta | Decidís vosotros entre: salir solo en modo borrador, cambiar de modelo o replantear |
| Un arreglo necesita otro arreglo para no romper algo | Se revierte y se rediseña |
| El código del motor crece dos ciclos seguidos sin que mejore una meta | Revisión de rumbo |
| Alguien ajusta una regla, el conocimiento o el prompt base mirando el sparring o el examen | Prohibido. Se deshace |
| Se mide el bot actual y el nuevo con distinto arnés | La comparación no vale |
| Un entregable va por su tercera versión | Se para: decide un dueño |

## 14. Riesgos

| Riesgo | Antídoto |
|---|---|
| **Segundo sistema:** meterle al nuevo todo lo aprendido | Solo entra lo que permite la constitución. El marcador enseña líneas y reglas en cada integración |
| **Repetir el bucle en sala limpia** | Parte B, las señales de §13.3 y un entregable, una revisión, una corrección |
| **Demasiadas reglas a la vez:** salen 77 reglas, 73 como texto, y unas 11 juntas al reservar (§19.4). El modelo cumple peor cuantas más lee | El techo de reglas (regla 7), fundir las que se puedan en F1 y medir el cumplimiento regla a regla. Si las de la reserva fallan en sus fichas, pasan a la herramienta «cómo reservar», que es la excepción pactada (§16.4). Cargar solo las reglas de la situación del cliente sería otra excepción, que decidiríais los dos entonces |
| **El conocimiento como puerta trasera de parches** | El conocimiento describe y no manda (regla 4), con validador y revisión |
| **Afinar contra la vara** | Examen congelado que solo da cifras. Fichas de puerta congeladas. Reserva de reales que no se abre hasta F6 |
| **Falta de vuestro tiempo** | Lo que se os pide está acotado (§1). Si no hay tiempo, la fase espera; no se decide por vosotros |
| **Producción, la API de WhatsApp o Andrés tardan** | Se habla con él y se empiezan los trámites en F0. Tienen responsable y fecha en la puerta de F4 |
| **El modelo cambia o se retira** | Queda fijado por versión. Cambiarlo es una integración completa, con examen |
| **Un solo proveedor del modelo** | Si no contesta, aviso y pase a una persona. Alertas de saldo y de errores |
| **Dos repos vivos** | El viejo se congela en F0 y se archiva en F8 |
| **Los clientes simulados no se parecen a los reales** | Por eso el examen no es la última puerta: lo son la sombra y el borrador con personas |
| **El 10 % resulta inalcanzable** | El bot da valor antes: como borrador con aprobación. Lo decidís en la señal de las tres integraciones |
| **Datos de clientes** | Las tres reglas de §9, resueltas antes de la puerta de F4 |
| **Se pierden lecciones enterradas en el código viejo** | Viajan como decisiones en la tabla de reglas y como fichas. El repo viejo queda de consulta |

## 15. Costes

Son órdenes de magnitud, con lo medido hasta hoy.

| Concepto | Cifra | Nota |
|---|---|---|
| Una respuesta del motor | Alrededor de 0,1 céntimos de dólar | V1: unos 0,09 $ por 40 clientes, con la caché caliente. Con clientes reales la caché acertará menos, y si los cálculos se piden a petición hay una llamada más. Se mide en F3 y F4 |
| Una tirada del examen (200 clientes) con el motor | ~0,45 $ | Por OpenAI |
| Una tirada del examen con el bot actual | ~0,8 $ | Por OpenRouter. Solo en F2 y F3 |
| Un examen juzgado (3 tiradas, 2 juicios) | Unas 2 ventanas de Claude | Sin coste de API. Cada regla nueva obliga a volver a juzgar la línea de partida |
| Mensajes de WhatsApp | Gratis hasta 1.000 respuestas al mes por número; después, por mensaje | Tarifa de Colombia por confirmar |
| Servidor | El actual | Producción puede pedir otro |
| Plataformas comerciales, como referencia | Fin: 0,99 $ por resolución. Decagon y Ada: decenas de miles de dólares al año (estimaciones) | No encajan con una cotización propia |

**Tiempo.** No hay fechas cerradas, porque cada puerta depende de vuestras decisiones y de las ventanas de Claude. Como orientación,
con dos Claudes: F0 a F4, entre cuatro y seis semanas. F5 depende de cuántos ciclos hagan falta. F6 y F7 dependen de producción y
del equipo de Andrés.

## 16. Decisiones

### 16.1 Ya decididas por Gadea, que este plan respeta

**Constan en el Plan V1 v4.1 (§9, «Decidido»):**
- La meta «robusto», las preguntas (≤ 50 %) y los pases sin meta, pero contados.
- Sin tope de arreglos, pero sin parches. De momento, solo Luna.
- Si la puerta falla dos veces, sale el segundo texto y se cuenta como fallo.
- Los descuentos, por persona y calculados por código. Los totales siguen prohibidos.
- El vuelo se comprueba después, contra lo entendido.
- El horario fuera de lo normal pasa con un asesor.
- Cambiar la fecha sin reserva hecha no pasa con un asesor; con reserva hecha, sí.
- El regalo y el particular que reserva para otro pasan con un asesor al reservar. `por-otros` queda para agencias e instructores.
- Con un extranjero en la reserva, todo en USD.
- Las ráfagas, con la opción (c).

**Constan en Coral y en la memoria del equipo (10-nov; el Plan V1 las recoge en su §4):**
- Sin el origen, ningún enlace: los precios de las dos salidas y la pregunta (#3738).
- Al reservar sin origen, se pide una vez con su motivo y, si no lo dice, pasa con un asesor (#3742).
- Con la nacionalidad sin saber tras dos preguntas, el enlace con la línea para quien sea colombiano (#3741).
- Un plan que va con asesor se dice una vez y se pasa cuando quiera reservar (#3741).
- Lo que la base no tiene y no está en la lista pasa de verdad con una persona (#3766).

### 16.2 Para decidir antes de F0

**Estado al 11-nov:** decididas las n.º 1, 3, 5, 6, 7, 8, 10 y 12 (§16.4). Quedan las n.º 2, 4, 9, 11, 13 y 14. La columna de la tabla es la recomendación que se hizo; lo decidido está en §16.4.

| # | Decisión | Nuestra recomendación |
|---|---|---|
| 1 | ¿Repo nuevo, como propone este plan? | Sí |
| 2 | ¿Aprobáis la constitución (Parte B), con su techo de reglas? | Sí, con los cambios que queráis |
| 3 | **¿Aceptáis calibrar al juez con etiquetas de una persona?** Cambia «la calidad la comprueban los Claude». ¿Quién etiqueta? | Sí. Gadea, o Gadea con alguien del equipo de Andrés |
| 4 | El umbral del juez y el de respuestas rehechas (§11) | Los de la propuesta |
| 5 | **¿Quién habla con Andrés, cuándo, y qué se le pide?** Conversaciones nuevas (al menos 200 turnos), la API de WhatsApp y su equipo en Chatwoot | Álvaro, en F0 |
| 6 | Si un importe sigue mal tras rehacer, ¿sale y se cuenta (lo decidido para todo), o en dinero pasa con una persona? | En dinero, pasar con una persona: la empresa responde por lo que dice el bot |
| 7 | Tras un pase, ¿el bot calla hasta que el asesor lo devuelva, o sigue contestando lo que sepa? | Callar, con un aviso de que ya lo tiene una persona. Hoy sigue contestando |
| 8 | Las emergencias (ahogo, desmayo, sangrado) y las incidencias de pago o de reserva en el momento: ¿reglas para el modelo, o alarma por palabras clave en el código? Pendiente del Plan V1 | Alarma en el código solo para emergencias; las incidencias, como regla |
| 9 | ¿Qué hace el bot con datos como tarjetas o cédulas? (`privacy.py`, pendiente del Plan V1) | No guardarlos ni repetirlos; lo demás, en el diseño de F4 |
| 10 | ¿El idioma lo fija el agente, sin detector aparte? Pendiente del Plan V1 | Sí |
| 11 | ¿La meta de importes se cuenta «contra la ficha»? Pendiente del Plan V1 | Sí |
| 12 | ¿El asistente dice desde el primer mensaje que es virtual? | Sí |
| 13 | ¿Quién sube a PRE y a producción, quién abre cada puerta y quién da el visto bueno final para Andrés? | Gadea sube; las puertas y el visto bueno, los dos |
| 14 | ¿Nombre del repo y del motor? | El que elijáis |

### 16.3 Para averiguar en F0 (no bloquean el arranque, pero tienen responsable y fecha en la puerta de F4)

- Si el número de WhatsApp de producción puede usar la API y seguir en la aplicación del equipo.
- Las tarifas de WhatsApp para Colombia.
- Qué obliga la ley colombiana de datos personales, qué aviso hay que dar al cliente y si el de asistente virtual es exigible allí.
- Las condiciones del proveedor del modelo sobre los datos de los clientes.
- Si el equipo de Andrés atenderá por Chatwoot en producción.

### 16.4 Aprobado por Gadea y Álvaro el 11-nov

Gadea y Álvaro aprobaron el 11-nov los siete ajustes de §19 y §20. **Esta lista es la que manda:** si otro punto del plan dice algo distinto, vale esta.

| N.º | Ajuste | Lo propuso | Dónde se explica |
|---|---|---|---|
| 1 | Lo exacto lo calcula el código. El idioma lo fija el código con un detector determinista, sin respaldo con LLM, y la puerta comprueba que Luna conteste en ese idioma | Gadea | §19.6 |
| 2 | Las reglas van como texto y limpias. Si las fichas de puerta de la reserva fallan por una regla más allá del umbral de §11, esas reglas pasan a una herramienta «cómo reservar». Es una excepción pactada a la regla 1, firmada por los dos y con sus guardas. No se construye por adelantado | Gadea | §19.6 |
| 3 | Sin router. Los saludos también los contesta Luna | Gadea | §19.3 |
| 4 | Si un importe sigue mal tras rehacerlo, pasa con un asesor y se cuenta aparte | Gadea | §19.6 |
| 5 | Un registro de pases, para analizar y no como meta. Los motivos salen de la tabla de reglas y los apunta quien decide, en el momento | Gadea | §19.6 |
| 6 | A Andrés se le piden unas 25-30 conversaciones recientes. Los 75 reales ya vistos sirven para calibrar, para el estilo, para el sparring y como comparación; nunca para decidir | Gadea | §19.6 |
| 7 | Los cálculos se construyen como herramientas desde el primer día. Una sola medida en F3 decide si Luna los recibe de antemano o los pide. **Matiz de Gadea:** la herramienta del enlace solo devuelve el enlace de un plan, un origen y un idioma; no decide si se da | Álvaro | §20.6 |

**Decisiones de §16.2 ya tomadas.** Las tomó Gadea (§19.7) y Álvaro dio paso a apuntarlas el 11-nov:

| N.º | Decisión |
|---|---|
| 1 | Repo nuevo: sí, aprovechando todo lo útil (docs, pruebas, servidor, APIs y claves) |
| 3 | Calibrar al juez: sí, con etiquetas de Gadea y Álvaro, y de Gonzalo si está |
| 5 | Andrés: Gadea y Álvaro acuerdan cuándo y cómo hablarle |
| 6 | Importe mal tras rehacer: pase con un asesor (ajuste 4) |
| 7 | Tras un pase, el bot se calla. A Andrés le llega la nota resumen por Chatwoot |
| 8 | Alarma en el código solo para emergencias; las incidencias, como regla |
| 10 | El idioma lo fija el código (ajuste 1) |
| 12 | Sí: dice desde el primer mensaje que es un asistente virtual |

**Quedan por decidir entre Gadea y Álvaro, antes de cerrar F0:** las n.º 2 (la constitución), 4 (los umbrales), 9 (tarjetas y cédulas), 11 (importes contra la ficha), 13 (quién sube y quién abre las puertas) y 14 (los nombres).

## 17. Qué pasa con el repo viejo

- **Desde F0:** queda etiquetado y congelado. Sigue en PRE como referencia para medir y como vuelta atrás.
- **No se integran** las ramas de bloques ni las de V2 (`bloque05`, `bloque4r`, `puerta-v2`, `bloque1`, `bloque4p`, `bloque31`).
- **Se aprovecha como dato,** no como código: el catálogo, la tarifa, las decisiones, las conversaciones reales anonimizadas, el
  análisis por fases y la historia.
- **Se aprovecha como referencia de código,** reescrito limpio y con su diseño: V1 (`scripts/simple_v1.py`), el calendario del cierre
  (bloque 3.1), el reconocimiento de importes y enlaces en un texto, la conexión con Chatwoot y la nota del pase.
- **Se aprovecha como herramienta de equipo:** Coral y la memoria compartida.
- **En F8** se archiva.

## 18. La revisión de este plan

Un agente independiente revisó el borrador el 11-nov, con una lista cerrada: hechos falsos, contradicciones, huecos que bloquean y
sitios por donde vuelve el bucle. Encontró 20 puntos y se corrigieron todos, una vez. Los que más cambiaron el plan:

- **La reserva de conversaciones reales no existía:** el «examen oculto» son 21 de los 75 episodios ya leídos. La única reserva
  limpia son las conversaciones nuevas de Andrés, y pedirlas pasa a ser una decisión de F0.
- **Si el juez no pasaba la calibración, nadie podía medir los graves.** Ahora el umbral se fija antes de etiquetar y hay un camino
  escrito si no llega.
- **Las fases estaban en un orden imposible:** el examen pedía ráfagas que se construían después, y las fichas pedían una salida que
  el bot actual no da. Ahora las ráfagas son del motor (F3) y en F2 se define el contrato y un adaptador.
- **El conocimiento y las reglas nuevas eran una puerta trasera para parches.** Ahora el conocimiento no puede llevar instrucciones y
  las reglas tienen techo.
- **F3 empujaba a retocar el prompt base contra el examen.** Ahora se congela antes y hay un solo examen.
- **Una «quinta salida» que proponíamos era, en realidad, otro decisor.** Se ha quitado; queda como riesgo, con su remedio sujeto a
  una excepción que decidiríais vosotros.

**En dos puntos se hizo algo distinto de lo que pedía el revisor:** los umbrales de F7 se fijan en la puerta de F6 y no en F2, porque
son de producción; y el umbral de las reglas críticas se fija con el bot actual ya medido, pero antes de medir el motor nuevo.

**Este documento no se vuelve a revisar por nuestra cuenta.** Lo que cambie, lo decidís vosotros.

---

## 19. Estudio Gadea (11-nov)

**Qué es.** Lo que estudiaron Gadea y su Claude el 11-nov sobre este plan, con sus conclusiones. **No es otra versión del plan.** Son
seis ajustes y las respuestas de Gadea a §16.2, para que Álvaro los estudie y, si da el visto bueno, se empiece por F0.
- Cada cifra está comprobada en el código o en los juicios.
- Los estudios los hicieron agentes independientes y el Claude de Gadea los comprobó.
- No lleva datos de clientes. Los clientes del panel se citan solo por sus ids `visto-*`.

### 19.1 El problema, confirmado

Tiene dos capas.
1. **En el bot: muchas piezas piensan sobre lo mismo y ninguna es dueña.**
   - Cuatro lectores leen el mismo mensaje: una regex, Jev, Haiku y el lector de grupo.
   - Luna redacta y además decide, con una pregunta que se fija antes de leer el mensaje.
   - El código le cambia el texto en el 68 % de los turnos.
   - Se tropiezan, y de ahí salen la mayoría de los graves.
   - Encima, a Luna se le dejan cuentas que falla.
2. **En cómo trabajamos: cada fallo se arreglaba poniendo otra pieza alrededor del modelo.** El bucle pasó del código a los prompts y
   después al plan. Lo empujaban tres cosas:
   - modelos baratos que fallaban o se rompían al pedirles más;
   - la latencia;
   - una vara que no distinguía, porque con 40 clientes y un juez que se contradice un arreglo parecía bueno o malo por azar.

### 19.2 Cómo funciona hoy el bot de PRE (0.61, `feature/pre_gadea` b7cfa4e4)

Lo recorrió un agente en el código (`src/orchestration/graph.py`, `src/agents/supervisor.py`, el núcleo y el compositor).
- **El recorrido de un mensaje:**
  1. El código fija la pregunta del escritor antes de leer (`graph.py:164`).
  2. Jev y el extractor leen a la vez. Según Jev, salen además el lector de grupo y una 2.ª lectura de la nacionalidad (CALN-10b).
     Haiku lee la nacionalidad casi al 50 % en casos como «soy de Cali», y por eso se lee dos veces: con una lectura, el 2,5 % de las
     nacionalidades salían mal; con dos, ninguna, pero las preguntas pasaron del 5,6 % al 11,8 %.
  3. El router y el código eligen la ruta, y los nodos vuelven a mirar las mismas puertas, hasta tres veces.
  4. Luna va «en paralelo», pero espera al extractor, a sus dos lecturas y a las notas. Luego vienen las guardas regex y el revisor.
  5. Ya en serie y antes de enviar: los avisos, el compositor, el guardado de lo dicho (que espera al extractor hasta 4 s) y el
     resumen.
- **Quién decide cada cosa:**

  | Decisión | Sitios que la deciden o la cambian |
  |---|---|
  | Plan | 9 |
  | Importe y moneda | 8 |
  | Enlace | 7 |
  | La pregunta | 7 |
  | Pase | Jev, la regex, el «sí» a la oferta, el cierre del colombiano y el fallo técnico |
  | Idioma | 5 |

  Una regla puede vivir en dos sitios a la vez. Por ejemplo, la agencia estaba en la decisión de Gadea y en la pregunta `needs_staff`
  de Jev.
- **Llamadas por turno: 3,99,** más 1,84 búsquedas.

  | Pieza | Llamadas por turno |
  |---|---|
  | Extractor | 1,35 |
  | Jev | 1,00 |
  | Luna | 0,85 |
  | Lector de grupo | 0,30 |
  | Notas | 0,28 |
  | Reescritura | 0,16 |
  | Revisor y respaldos | 0,06 |

  Cada una entró como arreglo de un fallo concreto, no por diseño de conjunto. La reescritura solo existe para el buscador, y las notas
  porque las piezas no ven la charla entera. **Con una sola llamada que lee todo, ninguna de las dos hace falta. V1 midió 1,0 llamadas
  por turno.**
- **Los sitios que escriben o pegan texto en la respuesta:** unos 29 la escriben, unos 38 le añaden algo (más 15 saludos) y unos 14 le
  quitan algo. La cifra «26 y 27» del compositor está desfasada. Cada tipo nació de un fallo:
  - preguntas pegadas, 10;
  - correctores, 14;
  - textos de pase, 10;
  - tarjeta, 9;
  - respaldos, 7;
  - datos metidos en el texto de Luna, 6.
- **Por qué no hay herramientas:**
  - Las hubo del 17-jun al 28-jul: un orquestador con 9 herramientas sobre gpt-4o (HISTORY 0.16.6). Eran acciones del carrito de
    botones, no datos exactos para el modelo.
  - Se borraron como código muerto al quitar el árbol (0.21.0), no por una medida.
  - El 6-nov, «modelo con herramientas» se descartó sin medirlo.
  - Nunca se ha probado un modelo que decida con herramientas.
- **El patrón** que explica todo esto es la acumulación de arreglos sobre una desconfianza aprendida hacia el modelo. El mismo
  diagnóstico se escribió el 21-jul («rendimientos decrecientes»), el 29-jul («cada bug se arregla añadiendo otro interceptor») y el
  10-nov.

### 19.3 Tres arquitecturas comparadas

Gadea comparó este plan con un esquema de referencia: un router que solo clasifica y reescribe; un agente que decide y usa
herramientas (conocimiento, disponibilidad, reserva, pago, reglas y pase); la búsqueda con embeddings y un reranker; y las reglas en el
código, dentro de las herramientas.

| | Esquema de referencia | Este plan | PRE hoy |
|---|---|---|---|
| Quién decide | El agente, con un router que solo clasifica | Una llamada a Luna | Varias piezas |
| Datos exactos | Herramientas | Tablas preparadas por el código y la puerta | El código los mete en el texto que lee Luna y después corrige lo que escribe |
| Reglas | En el código, dentro de las herramientas | Texto para Luna | Repartidas entre el código, los prompts y Jev |
| Conocimiento | Búsqueda | Entero en el contexto, con caché | Búsqueda más contexto fijo |
| Llamadas | Router y 1-3 del agente | 1 | ~4 |

**Conclusiones:**
- **Sin router.** Un router aporta cuando el conocimiento no cabe, cuando cada tipo de mensaje lleva herramientas distintas o cuando
  hay que ahorrar con un modelo caro. Aquí no se da ninguna de las tres: Luna es el modelo barato y la base está en caché (V1: 96-99 %
  de caché y p90 de 4,0 s). Un router solo vale si clasifica y elige qué darle al modelo. Si decide el resultado, como hace hoy Jev con
  el pase, vuelven a ser dos pensadores.
- **El conocimiento, entero en el contexto.** Está medido en V1, y ningún grave nacía en la búsqueda.
- **Herramientas o tablas son dos formas de lo mismo: que el código ponga el dato.** Para Diving Planet, casi todo es fijo, así que
  van tablas. Las herramientas quedan para lo que dependa del mensaje.
- **Lo crítico de PRE no es que falten herramientas, sino que el código corrija el texto después, que las reglas estén repartidas y
  que Luna haga cuentas.**

### 19.4 Dónde van las reglas (estudio de las decisiones)

Un agente separó en reglas las 31 decisiones de `decisiones.json` y las de la memoria del 10 y el 11-nov. **Salen 77, no 33:**

| Tipo | Reglas |
|---|---|
| Hechos que calcula el código | 4 |
| Reglas con una condición clara sobre los datos del cliente | 35 |
| Conducta, que necesita juicio | 30 |
| Mixtas | 8 |

- **Con este plan, Luna aplicaría 73 como texto.** La mayoría solo se activan con su tema, pero **en el turno de reservar se juntan
  unas 11 a la vez**: moneda, origen, hotel, colombiano, grupo, el orden de P5, el enlace, breve, una pregunta, sin totales y no
  adivinar. Es la zona donde ManyIFEval cae al 21-48 %.
- **Con una herramienta «cómo reservar»,** que aplicara en código las 20 de la reserva, quedarían unas 5.
- **En contra de la herramienta:**
  - solo 16 de esas 35 reglas tienen sus datos en el «entendido» de V1. Faltan, entre otros, la nacionalidad por persona, el reparto,
    el equipo propio, si es para otro, otro horario y la fecha en ISO, y leer mal un dato era la causa de 4 de cada 16 graves
    (CALN-43);
  - se parece mucho a `como_reserva` y a la `decision()` de V2, descartadas porque deciden;
  - añade una llamada en esos turnos.
- **Cosas que arreglar en el prompt de V1:**
  - lleva el texto viejo de `cambio-de-fecha`;
  - la instrucción de `temas-3nov` manda a las agencias al asesor;
  - faltan todas las decisiones del 10-nov;
  - `sin-tercera-pregunta` no recoge la excepción del 4R-1b.

### 19.5 Los fallos medidos de V1

Otro agente clasificó los graves de V1 en el panel-vara. Son 20 clientes vistos, 3 tiradas y 2 juicios cada una. Se comparó con B.

| Causa de los graves de V1 (27 en 120 juicios, 7 clientes) | Graves |
|---|---|
| **Un dato exacto mal calculado** | **22 (81 %)** |
| · El precio con el descuento de grupo (visto-6929: encadena descuentos, 567.000 en vez de 560.000; visto-6938) | 10 |
| · La hora de volar o la fecha (visto-6942: dice que un vuelo a las 9:00 del día siguiente no llega, y llega; 6914; 6927) | 12 |
| Una regla con condición clara | 1 (+2 mixtos) |
| Conducta o conversación | 0 sola |
| Ruido del juez | 2 |

- **En los 22 casos, el dato correcto ya estaba en el prompt** (el «20 % en total», la regla `vuelo-hora`). Luna lo tenía delante y
  lo aplicó mal: **tenerlo escrito no basta.** Son unos 5 casos independientes, no 22.
- **Las reglas de pase, como texto, las cumple:**
  - de 71 pases, 52 son por una regla de Gadea y solo 2 son indebidos;
  - otros 17 salen de la línea genérica de V1 («si algo no está… pasas con una persona»);
  - hace pases que B no hace, como el del equipo propio, que a B le costaba 4 graves en visto-6901.
- **El idioma no se cumple como texto.** V1 falla `global:idioma` en 38 juicios de 8 clientes vistos, y en 4 siempre: contesta en
  español a quien escribe en inglés. B, en 0, porque fija el idioma en código al empezar.
- **El mismo arreglo ayuda a B:** 15 de sus 17 fallos de datos son horas.

### 19.6 Seis ajustes a este plan

Salen de 19.4 y 19.5 y los aprueba Gadea. **No cambian la arquitectura ni la constitución:**
1. **Lo exacto, siempre en el código, y con el idioma incluido.**
   - La tabla de precios por persona con descuento (ya en §7.2).
   - La comprobación del vuelo (ya en §7.2).
   - **El idioma pasa a ser un hecho:** lo fija el código a partir de lo que escribe el cliente, como hoy el bot, y la puerta comprueba
     que Luna conteste en ese idioma. Cambia D7 y la decisión n.º 10 de §16.2.
     - El detector es **determinista**, como la heurística que ya existe (`catalog.py:83`), **sin respaldo con LLM**, que sería otro
       lector.
     - Se fija en el primer mensaje que lo deja claro. Los mensajes cortos («ok», «hola», un número) no lo cambian: se queda el que
       había.
     - A mitad de la charla, solo cambia con un mensaje entero en otro idioma, según la decisión `idioma`: los nombres propios y las
       palabras sueltas no cuentan, y otro idioma que no sea español ni inglés pasa a inglés.
     - Lo que sea dudoso se decide en el diseño de F3, con su banco de casos.
2. **Las reglas, como texto y limpias, con la herramienta de reserva preparada.**
   - En F1 se arregla lo de 19.4, y la línea genérica de «si no está, pasas» se alinea con `fuera-de-la-base` y la P-a.
   - **Criterio fijado antes de medir:** si las **fichas de puerta de la reserva** (§10.2) fallan por una regla más allá del umbral
     de §11 (fijado en la puerta de F2), esas reglas pasan al código, dentro de una herramienta «cómo reservar». Se mide por regla en
     las fichas, nunca leyendo el examen. La herramienta no se construye por adelantado.
   - **No es la salida 1 de §5 ni la D4 tal como están escritas,** porque la herramienta decide con lo que Luna leyó del cliente, como
     `como_reserva` y la `decision()` de V2 (19.4). Por eso queda nombrada ahora como **excepción pactada a la regla 1, firmada por
     Gadea y Álvaro**, con estas guardas:
     - solo devuelve hechos: el precio, la moneda, el enlace o «va con un asesor por X», con el id de su decisión;
     - Luna sigue siendo la única que escribe;
     - sus datos de entrada tienen que estar en «entendido» (hoy, 16 de las 35 reglas con condición clara los tienen);
     - ningún motivo sale sin una decisión escrita.
3. **Sin router, y los saludos también con Luna.**
4. **Si un importe sigue mal después de rehacerlo, se pasa con un asesor,** y se cuenta aparte. En V2m, el doble fallo de la puerta
   salió en unos 2 de cada 100 turnos (9 de 384 en el panel y 5 de 225 en los reales), contando importes y enlaces. Es la decisión
   n.º 6 de §16.2.
5. **Un registro de pases, para analizar y no como meta.** De cada pase se guarda:
   - el turno y la etapa;
   - el motivo, de la tabla de reglas;
   - quién lo decidió;
   - después, la etiqueta de una persona: correcto, evitable o error.

   Va en la traza (§7.2, paso 8), en los contadores (§10) y en F4. Valen las dos condiciones del Claude de Álvaro (#3810): los motivos
   salen de la tabla de reglas, y el motivo lo apunta quien decide, en el momento. No se arregla pase a pase.
6. **Andrés y los reales.**
   - A Andrés le bastan unas 25-30 conversaciones recientes: 200 turnos son unas 30 charlas.
   - Los 75 reales que ya tenemos sirven para calibrar al juez, para las proporciones y el estilo, para el sparring y como comparación
     al lado. Nunca para decidir, y siempre en local.

### 19.7 Lo que ha decidido Gadea de §16.2

| # | Decisión |
|---|---|
| 1 | Repo nuevo: **sí**, aprovechando todo lo útil (docs, pruebas, servidor, APIs y claves) |
| 3 | Calibrar al juez: **sí, con etiquetas de Gadea y Álvaro** (y de Gonzalo si está). Las personas, no los Claude |
| 5 | Andrés: Gadea y Álvaro deciden por WhatsApp cuándo hablarle. Hace falta para F6 (las conversaciones) y para F7 (la API de WhatsApp y su equipo en Chatwoot). Bastan unas 25-30 conversaciones |
| 6 | Importe mal tras rehacer: **pase con un asesor**, contado aparte (ajuste 4) |
| 7 | Tras un pase, **el bot se calla**. A Andrés le llega la nota resumen por Chatwoot |
| 8 | **Alarma en el código solo para emergencias;** las incidencias, como regla |
| 10 | El idioma: **lo fija el código**, no el agente (ajuste 1) |
| 12 | **Sí:** dice desde el primer mensaje que es un asistente virtual |
| 2, 4, 9, 11, 13 y 14 | Pendientes, para decidir con Álvaro |

### 19.8 Lo que se pide a Álvaro

Que estudie este apartado, con un agente suyo si quiere, y diga si da el visto bueno a los seis ajustes. Si lo da:
- se apuntan **una vez** en §16;
- se deciden con Gadea las pendientes de §16.2;
- y se empieza por F0.

Si no lo da, lo hablan Gadea y Álvaro, y los Claude no hacen otra versión.

## 20. Estudio Álvaro (11-nov): un modelo con herramientas

**Qué es.** Lo que preguntó Álvaro el 11-nov al estudiar el plan y §19, lo que se contrastó y la conclusión. **No es otra versión del
plan.** Es un ajuste más, el n.º 7, para que Gadea lo estudie. Si da el visto bueno, se apunta una vez en §16 junto con los seis de §19.
- Lo contrastado sale del informe de `docs/investigacion/` y de las medidas de §19. No hay medidas nuevas.
- Álvaro aprobó los seis ajustes de §19 el 11-nov, y Gadea aprobó el n.º 7 con un matiz. Todo está apuntado en §16.4.

### 20.1 Lo que preguntó Álvaro, y la respuesta corta

Álvaro comparó el plan con el esquema habitual de un bot (un modelo que decide y usa herramientas) y con el mapa de piezas de moda
(LangChain, LangGraph, RAG con base de vectores y MCP).

| Pregunta | Respuesta corta |
|---|---|
| «Dijimos que no habría parches, solo un sistema con herramientas. ¿Qué es ese "código" del plan?» | Una herramienta también es código. Lo que se quita son los parches: el código que toca la respuesta (20.2) |
| «¿No sería mejor tener las piezas de siempre?» | El bot de hoy ya las tiene casi todas, y es el Frankenstein (20.3) |
| «¿No fallará por ser tan simple?» | Fallará, como todos. Más fases no dieron menos fallos. El riesgo de verdad son muchas reglas a la vez (20.4) |
| «¿Las empresas lo hacen con código o con herramientas?» | Con herramientas, sobre todo. El plan se aparta en un punto (20.5) |

### 20.2 Parche o herramienta

| Código que… | ¿Es un parche? | ¿Está en el plan? |
|---|---|---|
| Calcula un precio, una fecha o el idioma | No. Es lo que hace una herramienta | Sí |
| Comprueba que un importe existe y pide rehacer | No, porque no escribe | Sí: la puerta, con sus límites (regla 3) |
| Cambia, corta o añade texto a la respuesta | Sí | Prohibido (regla 3). Hoy hay unos 80 sitios así (19.2) |
| Decide qué contestar en lugar del modelo | Sí | Prohibido (regla 1) |

### 20.3 Las piezas del mapa

| Pieza | Bot de hoy | Este plan | ¿Hace falta? |
|---|---|---|---|
| Chat, modelo y prompt | Sí | Sí | Sí |
| LangGraph y LangChain (librerías para encadenar pasos y caminos) | LangGraph, sí; LangChain, apenas | No | No: el recorrido es una línea recta de cuatro pasos. Se confirma en el diseño de F3 |
| Base de vectores y RAG (un buscador que trae trozos del conocimiento) | Sí | No (D2) | Hoy no: la base cabe entera. Sí, como módulo aparte, para un negocio que no quepa |
| MCP (un enchufe estándar para conectar herramientas de otros sistemas) | No | No | Solo cuando un negocio tenga sistemas que conectar |

Tener esas piezas no hizo bueno al bot de hoy. Lo que comparten las empresas buenas no son las piezas, sino las cuatro capas de §7.1.

### 20.4 ¿Fallará por ser tan simple?

**Por qué había tantas fases** (19.1): los modelos de entonces no podían con todo a la vez, cada fallo se arreglaba con una pieza más y
la vara no distinguía si la pieza servía.

| Fuente | Qué dice |
|---|---|
| Anthropic | «La solución más simple posible, y solo aumentar la complejidad cuando haga falta». Con muchos pasos, los errores «se acumulan» |
| OpenAI | «Maximiza primero las capacidades de un solo agente», y añádele herramientas poco a poco |
| ManyIFEval | Cumplir todas las instrucciones a la vez cae de ~0,95 con una a 0,21-0,48 con diez |
| τ-bench | Un modelo con herramientas tampoco acierta siempre: gpt-4o resolvió el 61 % de las tareas de tienda, y menos del 25 % si tenía que acertar ocho veces seguidas |
| Sierra | De 10 a 15 modelos por turno, pero solo uno o dos «piensan». El resto vigila y no escribe |
| Nuestra medida | El bot entero, con unas 4 llamadas: 7,5 graves de 40. Luna sola, con 1: 7,5. Empate |

- **Dos lecturas de nuestra medida:** las llamadas de más no compraron calidad, y lo simple empató, no ganó.
- **El riesgo de lo simple no son las pocas fases: son muchas reglas a la vez para un solo modelo.** Salen 73 como texto y unas 11
  juntas al reservar (19.4).
- **Las defensas ya están en el plan:** las cuentas fuera del modelo, la puerta, una ficha por regla repetida 5 veces, la excepción
  pactada del ajuste 2, personas delante en F6 y F7, y la señal de parada de F3.
- **Si no basta,** se añaden piezas de una en una y con su medida. Las que vigilan valen. Las que deciden o corrigen el texto, no.

### 20.5 Cómo lo hacen las empresas

| Manera de usar el código | Quién, según el informe | En este plan |
|---|---|---|
| Herramientas que el modelo llama | Ada, Intercom Fin, Zendesk, Sierra, Parloa | Prevista (D4), pero no de entrada |
| Código dentro de los pasos: condiciones y cuentas que el modelo no puede saltarse | Fin, Agentforce, Decagon | La excepción pactada del ajuste 2 |
| Vigilantes que comprueban y bloquean | Decagon, Fin, Parloa, Sierra | La puerta |

- **El plan coincide en dos y se aparta en la primera:** da los datos de antemano, en tablas (D3), en vez de dejar que el modelo los pida.
- **Tiene su motivo.** Esas empresas atienden negocios con sistemas vivos (pedidos, cuentas, devoluciones) y no hay más remedio que
  pedir el dato. Diving Planet tiene una lista fija. Dar datos de antemano tampoco es raro: OpenAI lo recomienda para las políticas.
- **Pero no está medido.** Nunca se ha probado un modelo que decida con herramientas, y el 6-nov se descartó sin medirlo (19.2).
- **Y el atajo tiene un punto débil ya medido:** en los 22 graves de cuentas de V1, Luna tenía el dato delante y lo aplicó mal (19.5).
- **19.3 ya lo deja abierto:** «las herramientas quedan para lo que dependa del mensaje». El precio de este grupo y su vuelo dependen
  del mensaje.
- Casi todo lo de las empresas lo cuentan ellas mismas. Solo lo de Sierra viene de un resumen independiente.

### 20.6 El ajuste n.º 7

**Los cálculos se construyen como herramientas desde el primer día, y se mide una vez cómo se le entregan a Luna.** No cambia la
constitución: Luna sigue siendo la única que decide y escribe (regla 1) y el código sigue calculando (regla 2).

1. **Cada hecho del código es una función con nombre, entradas y salida declaradas, y con sus pruebas.** Eso es una herramienta, se
   la llame o no. Así el motor sirve igual para un negocio con datos en vivo.
2. **Lo que no depende del mensaje se sigue dando de antemano:** el reloj, el primer día reservable, el catálogo, la tarifa base y
   las horas. No hay nada que pedir.
3. **Lo que depende del mensaje tiene dos formas de entrega, con el mismo código por debajo.** Son tres cálculos: el precio por persona
   de este grupo con su moneda, si su vuelo alcanza y el enlace que toca.

   | | A. De antemano | B. A petición |
   |---|---|---|
   | Cómo | El código pone la tabla entera y la puerta comprueba después (lo de §7.2) | Luna llama a la herramienta con los datos del cliente y recibe el resultado exacto |
   | Llamadas al modelo | 1 | 2 en los mensajes con cálculo |
   | Su riesgo | Tener el dato delante y aplicarlo mal (19.5) | No llamarla, o llamarla con un dato mal leído |

4. **Una sola medida, en F3 y antes del examen:** las fichas de puerta de esos cálculos, repetidas 5 veces y comprobadas por código,
   sin juez. Se apuntan también el p90 y las llamadas por turno.
5. **El criterio se fija antes de medir,** en la puerta de F2 y en la lista de §11:
   - gana la forma que falle menos fichas, por más de la diferencia mínima que fijen los dueños;
   - si empatan, A, porque es una sola llamada;
   - B solo vale si cumple el p90 de 7,5 s;
   - **la que pierde se borra.** No quedan dos caminos en el motor.
6. **Guardas, para que una herramienta no sea otro decisor ni un parche:**
   - solo devuelve hechos: un número, una fecha, un enlace o un sí o no. Nunca texto para el cliente ni conducta. «Va con un asesor»
     no es de estas: eso es la excepción del ajuste 2;
   - Luna decide llamarla y es la única que escribe;
   - sus argumentos salen de «entendido», quedan en la traza y las fichas los comprueban;
   - pocas: una por cálculo y sin solaparse;
   - la puerta sigue. Con B puede ser más estricta: cada importe del texto tiene que ser uno que la herramienta devolvió en esa
     charla. Hoy la puerta no ve el precio de otro plan (§2).
7. **No entran:** LangGraph, el buscador con base de vectores, MCP, un router ni un segundo modelo. El motor deja el hueco para el
   buscador y para las herramientas de sistemas en vivo (D2 y D4).

### 20.7 Qué cambiaría en el texto del plan

| Sitio | Hoy dice | Diría |
|---|---|---|
| D1 | Una llamada al modelo con salida estructurada | Un solo modelo. Una llamada, o dos cuando pide un cálculo, si gana B |
| D3 | Los datos exactos llegan como tablas que genera el código | Los cálculos son herramientas. Cómo se entregan lo decide la medida de F3 |
| D4 | Herramientas «a petición» solo cuando un negocio las necesite | El motor sabe llamar herramientas desde el primer día. Las de sistemas en vivo, cuando un negocio las tenga |
| §7.2, pasos 4 a 6 | El código prepara los hechos, una llamada y la puerta | Igual, más la llamada a la herramienta si gana B |
| F3 | El motor mínimo y un solo examen | Lo mismo, con la medida de A y B antes del examen |
| §11 | La lista de umbrales | Un umbral más: la diferencia mínima entre A y B |
| §15 | Alrededor de 0,1 céntimos por respuesta | Con B, una llamada más en los mensajes con cálculo. Sin medir |

**No cambian** la constitución, las fases, la vara ni los seis ajustes de §19.

**Hecho el 11-nov:** estos cambios ya están pasados al texto. La tabla queda como registro de lo que decía antes.

### 20.8 Lo que se pide a Gadea

Que estudie este apartado y diga si da el visto bueno al ajuste n.º 7. Si lo da, se apunta **una vez** en §16, junto con los seis de
§19 cuando Álvaro los apruebe. Si no lo da, lo hablan Gadea y Álvaro, y los Claude no hacen otra versión.

**Hecho el 11-nov:** Gadea lo aprobó, con el matiz del enlace (§16.4).

## Glosario

| Término | Significado |
|---|---|
| Motor | El programa que conversa. Es igual para cualquier negocio |
| Paquete del negocio | Los datos de un negocio: lo que sabe, sus precios, sus reglas |
| Hecho | Un dato que calcula el código: un precio, una fecha, un enlace |
| Herramienta | Un trozo de código que da un dato exacto. El modelo lo recibe ya hecho o se lo pide |
| Registro de pases | La lista de cada pase con un asesor: cuándo, por qué y quién lo decidió |
| Regla | Una decisión de un dueño, escrita para que el asistente la siga |
| Puerta | La comprobación de hechos que pasa cada respuesta antes de enviarse. También, la condición para salir de una fase |
| Ficha | Una conversación de prueba con su respuesta correcta ya calculada |
| Examen | El conjunto grande y congelado de clientes simulados que decide si una versión llega a la meta |
| Integración | Una versión que junta uno o más ciclos y pasa el examen |
| Sparring | Un Claude que hace de cliente para descubrir fallos |
| Sombra | El bot escribe su respuesta sin que el cliente la vea, para compararla con la de una persona |
| Juez | Un modelo de IA que dice si una respuesta tiene un fallo grave |
| Calibrar | Medir cuánto coincide el juez con una persona |
| Ruido | Lo que cambia una cifra de una medida a otra sin que haya cambiado nada |
| p90 | El tiempo que tardan las respuestas lentas: 9 de cada 10 tardan menos |
| PRE | El entorno de pruebas. No atiende a clientes reales |
| Versión | Una foto del bot: su código, su prompt base, su paquete y su modelo |
