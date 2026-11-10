# Plan de reconstrucción: un asistente de reservas limpio, robusto y reutilizable

**Borrador del Claude de Álvaro, 11-nov-2026, por encargo de Álvaro. Lo deciden Gadea y Álvaro.**
No es código ni otra versión del Plan V1. Recoge las decisiones de Gadea del 10-nov (Plan V1 v4.1) y la investigación de
`docs/investigacion/` (informe y seis notas con fuentes). Los datos del sistema actual salen del inventario del 11-nov
(`docs/investigacion/inventario-repo-11nov.md`).

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
respuestas tres veces más cortas, un 30 % más rápido y una cuarta parte de las llamadas.

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
| F3 | El motor mínimo, en local | No es peor que el bot actual y lo exacto sale bien |
| F4 | El canal y la operación, en PRE | Funciona por Chatwoot, con vuelta atrás ensayada |
| F5 | Ciclos de mejora | El examen cumple las metas, confirmado |
| F6 | Sombra con conversaciones reales | Lo exacto, a cero fallos, y una muestra aprobada por personas |
| F7 | Borrador con aprobación y autonomía por acción | Cada acción se gana su autonomía con cifras |
| F8 | Apagar el bot viejo | Repo viejo archivado |
| F9 | Segundo negocio | Otro paquete funciona sin tocar el motor |

**Lo que os pide a vosotros:** las decisiones de §16, unas 3 horas una sola vez para calibrar al juez (§10.4) y unos 30 minutos por
semana para aprobar correcciones.

**Lo que no promete.** Fechas cerradas ni un bot perfecto. La investigación es clara: ningún bot de atención llega al 100 %. Por eso
el plan no depende de la perfección para dar valor: desde F7 el bot ya ayuda como borrador, con una persona aprobando.

## 2. Qué vamos a construir

**Lo que hace el asistente al acabar el plan:**
- Contesta por WhatsApp, en español e inglés, dudas de planes, precios, horarios, requisitos y logística.
- Da el precio por persona exacto y el enlace de reserva correcto, o dice por qué lo reserva un asesor.
- Pasa con una persona, con una nota resumen, cuando lo mandan las reglas de Gadea o el cliente lo pide.
- Dice que es un asistente virtual y ofrece siempre la salida a una persona.

**Lo que no hace, por diseño:**
- No cobra, no cambia ni cancela reservas, no decide sobre salud y no promete nada que no esté en los datos.
- No calcula: los precios, las fechas y los enlaces se los da el código.
- No se «aprende» cosas solo: cada cambio pasa por una persona.

**Cómo sabremos que es profesional:**

| Cualidad | Qué significa aquí |
|---|---|
| Limpio | Un motor pequeño; el negocio en datos; cada cosa en un solo sitio |
| Robusto | Lo exacto no puede salir mal sin que el código lo vea; si algo falla, pasa con una persona |
| Sencillo | Una pieza decide. Una llamada por mensaje. Sin capas que se corrigen unas a otras |
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
| Varias piezas decidían | En todos los líderes decide una sola pieza; el código calcula y ejecuta |

**Lo que V1 no resolvía**, y este plan ataca: pasaba con una persona de más (71 de 120 charlas frente a 45), hacía cuentas con los
precios (13 importes fuera del catálogo de 272) y preguntaba en el 75 % de sus primeras respuestas. Además leía la misma base que el
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
| La salida a clientes reales es **por peldaños, con personas** | El Plan V1 acababa en «presentar a Andrés». Los fracasos conocidos vienen de soltar el bot sin salida humana |
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
   fallo visto. Solo cambia si cambia la decisión.
5. **El prompt base es del motor y está congelado.** Es corto, no habla de buceo y no se toca en el día a día. Cambiarlo es una
   versión mayor.
6. **Cada cosa, en un solo sitio.** Un precio, una hora o una regla viven en un lugar. Los textos no repiten cifras a mano.
7. **Nada entra sin una decisión escrita.** Ni una pieza, ni una comprobación, ni una regla. Por defecto, la respuesta a «¿y si
   añadimos…?» es no.
8. **La vara se fija antes y no se mira para arreglar.** Metas y umbrales se acuerdan antes de medir. Del examen solo salen cifras.
9. **La realidad manda.** Una conversación real pesa más que una simulada, y una simulada más que una inventada.
10. **La autonomía se gana por acción y con cifras.** Dinero, cambios, cancelaciones, quejas, salud y «quiero una persona» van
    siempre con una persona.
11. **Todo cambio es una versión.** Nada llega a un cliente sin versión, pruebas y vuelta atrás.
12. **Parar es un resultado válido.** Si se cumple una señal de parada (§13.3), se para y se habla. No se «prueba una cosa más».

## 5. Dónde va cada corrección

Esta tabla es el antídoto contra el Frankenstein. Cuando el bot falla, la corrección solo puede ir a uno de estos sitios:

| El bot falló porque… | La corrección va a… | Quién la aprueba | ¿Toca código? |
|---|---|---|---|
| No tenía el dato | El conocimiento del paquete | Gadea | No |
| El dato estaba mal | La tabla del paquete (precios, horas, enlaces) | Gadea | No |
| No sabía cómo actuar y no hay decisión | Primero, una decisión de un dueño; luego, una regla | Gadea | No |
| Un cálculo o una acción salió mal | El código de ese hecho, con su prueba | Revisión entre Claudes | Sí, poco |
| No cumple una regla bien escrita | Una de las cinco salidas cerradas (abajo). **La regla no se reescribe** | Los dueños | Depende |
| Se vio una sola vez | El registro. Espera a que su familia pese | — | No |
| Otra cosa | No se toca hasta entender por qué | — | No |

**Las cinco salidas cerradas** cuando el modelo no cumple una regla bien escrita. Las cuatro primeras son las del Plan V1 v4.1:
1. convertirlo en un hecho que calcula el código;
2. una comprobación, pero solo de un hecho, nunca de conducta;
3. aceptar la cifra tal cual (si es una meta, eso es cambiar la meta);
4. cambiar el modelo de toda la llamada;
5. **nueva, la proponemos:** cargar solo las reglas de la situación del cliente (por ejemplo, las de «ya reservó» solo si ya
   reservó). Las elige el código por el estado de la conversación, no otro modelo. Motivo: cuantas más reglas lee a la vez, peor las
   cumple todas. Necesita vuestra aprobación (§16.2).

## 6. Lo que los Claudes no hacemos solos

El 10-nov el bucle pasó tres veces por nosotros: en el código, en el prompt y en el propio plan (cinco versiones en cuatro horas).
Las revisiones con agentes no lo frenaron, porque un revisor siempre encuentra algo. Por eso:

- **Un entregable, una revisión, una corrección.** Cada diseño y cada cambio tiene una revisión independiente con una lista cerrada:
  hechos falsos, choques con la constitución o con una decisión, y huecos que impiden cumplir la puerta. Se corrige una vez. Lo demás
  va al registro de pendientes, que veis vosotros.
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
4. **El código prepara los hechos** que no dependen del mensaje: la hora, el primer día que se puede reservar, la tabla de precios por
   persona con sus descuentos y la hora desde la que se puede volar tras cada plan.
5. **Una llamada al modelo**, con el prompt base, el paquete del negocio, los hechos, lo entendido y el historial. Devuelve tres cosas:
   lo que ha entendido del cliente, si hay que pasar con una persona y el texto.
6. **La puerta comprueba hechos:** que cada importe esté en la tabla, que cada enlace sea de un plan del catálogo y en su idioma, que el
   idioma sea el del cliente y que el vuelo alcance. Si algo no casa, se rehace una vez.
7. **Se actúa:** se guarda lo entendido; si hay pase, se ejecuta con su nota resumen; se envía el texto.
8. **Se guarda la traza** del turno: versión, tiempos, coste y comprobaciones. De ahí salen los contadores y las pruebas futuras.

### 7.3 Decisiones de diseño, con su motivo

| # | Decisión | Motivo |
|---|---|---|
| D1 | Una llamada al modelo con salida estructurada | Es V1, que ya está medido: mismos graves que el bot entero, 1 llamada frente a 3,76 y p90 de 4,0 s frente a 5,8 s |
| D2 | El conocimiento va entero en el contexto, con caché. Sin buscador | Cabe (~67.000 tokens) y la caché acertó el 96-99,6 %. Se quitan la base vectorial, los embeddings y el reindexado en cada despliegue. Un negocio que no quepa usará un buscador como módulo aparte |
| D3 | Los datos exactos llegan como tablas que genera el código | El modelo lee y no calcula. La puerta puede comprobarlo |
| D4 | Herramientas «a petición» (consultar un sistema en vivo) solo cuando un negocio las necesite | Diving Planet no tiene datos en vivo: siempre hay disponibilidad. Se diseña el hueco, no se construye a ciegas |
| D5 | El modelo queda fijado en cada versión. Sin modelo de respaldo | Como en el Plan V1 v4.1: un respaldo sería un segundo escritor. Si el modelo no contesta, aviso sincero y pase a una persona. Cambiar de modelo reinicia la evidencia |
| D6 | La puerta solo comprueba hechos y rehace una vez | Decidido por Gadea. Cuando la puerta juzgó conducta (V2), rehízo el 65 % de las respuestas |
| D7 | Una sola base de datos (Postgres) para conversaciones, estado y trazas | Menos piezas. Hoy el estado vive en Redis con 81 campos y las tablas de análisis nunca se escriben. Se confirma en el diseño de F4 |
| D8 | Cada despliegue es una foto: código, prompt base, paquete y modelo | Permite volver atrás y saber qué versión contestó cada mensaje |
| D9 | El motor no conoce el negocio. Una comprobación automática lo vigila | Es lo que lo hace reutilizable |

### 7.4 Lo que el motor hace igual para cualquier negocio

- Conversar con una llamada y salida estructurada.
- Cargar un paquete de negocio y validarlo.
- Calcular los hechos genéricos: reloj y zona horaria, primer día reservable con hora de corte y días cerrados, tabla de precios con
  descuentos.
- La puerta de importes, enlaces e idioma.
- El pase a una persona con nota resumen.
- El canal: firma, duplicados, cola por conversación, ráfagas y límites de WhatsApp.
- Las trazas, los contadores y las versiones.

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
- **Cada regla lleva su origen:** la decisión, la fecha y quién la tomó. Sin decisión no hay fila.
- **Cada regla lleva sus casos:** al menos uno donde aplica y uno donde no.
- **El paquete se valida solo:** que cada plan tenga precio en las dos monedas, que cada enlace exista, que no falte idioma.
- **Cambiar el paquete es un cambio con versión:** queda quién lo aprobó y qué pruebas pasó.

**De dónde sale el de Diving Planet** (inventario del 11-nov):

| Se lleva | Desde | Qué hay que hacer |
|---|---|---|
| Catálogo: 38 servicios, 18 de ellos variantes «ya en las islas» | `services.json` | Limpiar y quitar cifras de los textos |
| Tarifa 2026: 51 entradas, COP y USD, normal y online | `pricing.json` | Dejarla como única fuente de precios |
| Descuentos | `discounts.json` | Generar la tabla de precios por persona con descuento |
| 62 políticas y 112 preguntas curadas | `policies.json`, `curada/faqs.json` | Revisar duplicados y cifras a mano |
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

**Datos personales y avisos legales.** No es asesoría legal; hay que confirmarlo con quien corresponda (§16.3):
- El asistente dice que es un asistente virtual. En la UE es obligatorio desde agosto de 2026 (AI Act, art. 50).
- La empresa responde por lo que dice su bot igual que por su web (caso Air Canada).
- Las conversaciones reales con datos de clientes no salen de la máquina de quien las custodia. Al repo solo va lo anonimizado.
- No se guardan ni se repiten números de tarjeta. Qué hace el bot con un dato así es una decisión pendiente de Gadea (`privacy.py`).

---

# Parte D. La vara

## 10. Cómo sabemos si está bien

Tres preguntas distintas, cada una con su instrumento. No se mezclan.

| Pregunta | Instrumento | Quién juzga | Cuándo |
|---|---|---|---|
| ¿Los datos exactos salen bien? | Pruebas de código y fichas | El código | En cada cambio |
| ¿Se comporta como decidió el negocio? | Fichas por regla y el examen | El código y un juez calibrado | En cada cambio y en cada integración |
| ¿Sirve con clientes de verdad? | Sombra, borrador y autonomía por acción | Personas | Desde F6 |
| ¿Qué familias de fallo hay? | Sparring y lectura de conversaciones | Claudes, con muestra para vosotros | En cada ciclo |

### 10.1 Pruebas de código

Los cálculos (precios, descuentos, primer día reservable, vuelo), la puerta, el canal y la validación del paquete. Son gratis, no
tienen ruido y corren todas en cada cambio.

### 10.2 Fichas

Una ficha es una conversación corta con su respuesta correcta ya calculada: qué precio debe salir, qué enlace o ninguno, en qué
idioma y si debe pasar con una persona.

- Como el agente devuelve por separado lo que entendió y si pasa, **casi toda la conducta se comprueba sin juez**: «marcó pasar»,
  «entendió que sale de las islas», «el texto lleva 178 USD», «el texto no lleva enlace».
- **Cada regla tiene sus fichas**, y de ahí sale el cumplimiento regla a regla. Así se sabe cuál no se cumple, sin adivinar.
- **Cada ficha se repite 5 veces.** El modelo no contesta siempre igual, y para un cliente lo que cuenta es acertar siempre.
- **La respuesta correcta la calcula un código de medida** que vive aparte y nunca entra en el bot (decisión del Plan V1).
- **Cada fallo real se convierte en ficha**, para que no vuelva.

### 10.3 El examen

Es el del Plan V1, tal cual: unos 200 clientes que reaccionan, con la mezcla de los reales (un tercio ya ha reservado, un 11 % son
agencias, un 15 % pregunta lo que la base no contesta), dos relojes (antes y después del cierre), ráfagas como las reales y fichas de
objetivo escritas por un agente que no conoce el bot.

- **Se congela con su huella** antes de medir nada.
- **Solo devuelve cifras.** Nadie lee sus conversaciones para arreglar algo.
- **Un examen por versión**, más uno de confirmación si cumple las metas.
- **Siempre 2 juicios por tirada.** Con 200 clientes y 3 tiradas, una diferencia en graves cuenta si supera unos 4 puntos.

### 10.4 El juez, calibrado

Hoy el juez es un Claude y nadie ha medido cuánto coincide con vosotros. La investigación dice que sin esa medida no es fiable.

- **Lo que hace falta:** que una persona que sabe del negocio etiquete entre 100 y 150 respuestas como «vale» o «no vale», con una
  línea de por qué. Son unas 3 horas, una sola vez.
- **Con eso se mide al juez:** cuántos fallos de verdad pilla y cuántas respuestas buenas da por malas.
- **Si el juez no llega al umbral** que fijemos en F2, no decide nada: solo señala conversaciones para que las mire una persona.
- **Quién etiqueta** es una decisión vuestra (§16.2): vosotros, alguien del equipo de Andrés o repartido.

### 10.5 Sparring y lectura de conversaciones

Sirven para **descubrir**, nunca para decir que algo mejoró.

- **Sparring:** un Claude hace de cliente nuevo cada vez y otro, que no lo escribió, lo juzga dos veces.
- **Lectura:** los Claudes leemos las conversaciones reales en sombra, agrupamos los fallos por familia y contamos cuántas veces sale
  cada una.
- **Una familia pesa** si sale en 3 o más charlas distintas de 30. Por debajo, espera.
- **Vosotros veis un resumen de una página** y una muestra: los peores y unos al azar.

### 10.6 Las conversaciones reales

| Qué hay | Cuánto | Uso |
|---|---|---|
| Episodios reales anonimizados, con las respuestas del equipo | 75 episodios de 39 chats | Desarrollo. Ya se han leído, así que no cuentan para la meta |
| Examen oculto | 13 chats apartados | Caja fuerte: no se abre hasta la puerta de F6 |
| Conversaciones nuevas de Andrés | Por pedir | Caja fuerte y sombra |

**Sombra histórica:** en cada turno de una conversación real, el bot escribe lo que habría contestado, con el historial real hasta ese
punto. Se compara con lo que contestó la persona. Límite conocido: no vale para juzgar el estilo de toda la charla, porque el bot la
habría llevado por otro camino.

## 11. Metas y puertas

**Las metas de «robusto»** son las del Plan V1, fijadas por Gadea, con dos precisiones que proponemos:

| Medida | Meta | Estado |
|---|---|---|
| Clientes con fallo grave en el examen | ≤ 10 % | Fijada |
| Importes mal que llegan al cliente | 0 | Fijada. Falta confirmar «contra la ficha» (§16.2) |
| Enlace e idioma mal que llegan al cliente | 0 | Fijada |
| p90 del turno | ≤ 7,5 s | Fijada |
| Largo mediano | ≤ 300 caracteres | Fijada |
| Primeras respuestas con pregunta | ≤ 50 % | Fijada |
| Pases indebidos y pases que faltan | Sin meta, contados | Fijada |
| Respuestas que la puerta tiene que rehacer | Umbral por fijar en F2 | Propuesta |
| Cumplimiento regla a regla | Se publica. Umbral para las reglas críticas, por fijar en F2 | Propuesta |

- **Los umbrales que faltan se fijan en F2**, con el bot actual ya medido y antes de medir el motor nuevo. Después se congelan.
- **Reglas críticas** son las de dinero, salud, seguridad y pase a una persona.
- **Solo vosotros cambiáis una meta, y por escrito.**

---

# Parte E. Las fases

Una fase no empieza hasta que la anterior cruza su puerta. Cada puerta la abrís vosotros.

### F0 · Acuerdo y cimientos

- **Objetivo:** empezar con las reglas claras y el terreno preparado.
- **Qué se hace:**
  - leéis este plan y decidís §16;
  - se crea el repo nuevo con la constitución, la plantilla de decisiones de diseño, las pruebas automáticas y la rama principal
    protegida (todo cambio entra con revisión);
  - se etiqueta el bot actual en git (hoy no hay ninguna etiqueta) y queda congelado: solo se tocan datos y urgencias;
  - se arrancan los trámites largos: API de WhatsApp Business y entorno de producción.
- **Puerta:** constitución firmada, decisiones de §16.2 resueltas o aparcadas con dueño y fecha, repo creado y bot actual etiquetado.
- **No se hace:** ninguna línea del bot.

### F1 · El paquete de Diving Planet

- **Objetivo:** que todo lo que el bot tiene que saber esté en datos, una vez y bien.
- **Qué se hace:**
  - **la tabla de reglas:** una fila por decisión (las 31, «breve y concisa» y las del 10-nov). Cada fila la escribe un agente que
    solo ve la decisión, y la revisa otro. Se resuelven los choques (`cambio-de-fecha`, `por-otros`, `temas-3nov`);
  - **las tablas:** precios como única fuente, precios por persona con descuento, horas, enlaces;
  - **el conocimiento:** catálogo, políticas y preguntas, sin cifras a mano;
  - **el validador** del paquete;
  - **una «ficha del negocio» legible**, generada desde los datos, para que Gadea confirme que todo es correcto.
- **Puerta:** el validador pasa, no queda ningún choque abierto y Gadea aprueba la ficha del negocio y la tabla de reglas.
- **No se hace:** escribir reglas mirando conversaciones o fallos.

### F2 · La vara, congelada

- **Objetivo:** tener el instrumento antes que el bot, para no ajustar el uno al otro.
- **Qué se hace:**
  - las fichas por regla y por hecho, y el código de medida que calcula la respuesta correcta;
  - el examen de ~200 clientes y su arnés (ráfagas, dos relojes), congelados con su huella;
  - la rúbrica cerrada, con los graves separados de la fricción;
  - la sesión de etiquetado y la calibración del juez (§10.4);
  - **se mide el bot actual** con todo ello. Es la línea de partida;
  - se fijan los umbrales que faltan (§11).
- **Puerta:** vara congelada, bot actual medido, juez calibrado o rebajado a ayudante, y metas confirmadas por Gadea con esa rúbrica.
- **Aviso:** si el bot actual ya cumple el 10 % en el examen, se os avisa antes de seguir, porque la meta no distinguiría.
- **No se hace:** tocar el examen después de congelarlo.

### F3 · El motor mínimo

- **Objetivo:** el agente funcionando en local, sin canal.
- **Qué se hace:**
  - el prompt base, corto y sin negocio;
  - la llamada con salida estructurada y caché;
  - los hechos: reloj, primer día reservable, tabla de precios, vuelo;
  - la puerta: importes, enlaces, idioma, vuelo;
  - las trazas y los contadores;
  - un **negocio de juguete** (tres servicios inventados de otra actividad) para probar que el motor no sabe de buceo.
- **Puerta:**
  - todas las pruebas de código pasan;
  - lo exacto que llega al cliente, a cero fallos en las fichas;
  - el motor funciona con el negocio de juguete sin cambiar una línea;
  - en el examen, frente al bot actual y con el mismo arnés: no es peor en graves más allá del ruido, y cumple estilo y tiempo.
- **Señal de parada:** si sale peor que el bot actual en graves por más que el ruido, se para y se habla.
- **No se hace:** añadir reglas o comprobaciones para subir la nota.

### F4 · El canal y la operación

- **Objetivo:** el motor atendiendo por Chatwoot en PRE, operado como un servicio serio.
- **Qué se hace:**
  - el canal: firma, duplicados, cola por conversación, ráfagas (c), límites de WhatsApp;
  - el pase a una persona: nota resumen, cambio de estado en Chatwoot y qué hace el bot después (§16.2);
  - el fallo técnico: aviso sincero y pase;
  - la base de datos, las versiones, la vuelta atrás, las copias, los secretos, las alertas y el panel (§9);
  - el aviso de que es un asistente virtual.
- **Puerta:**
  - una ronda de prueba completa por Chatwoot en PRE;
  - ensayados: una vuelta atrás, una restauración de copia y una caída del proveedor del modelo;
  - lista de seguridad repasada;
  - sube Gadea, o quien ella diga.
- **No se hace:** conectar clientes reales.

### F5 · Ciclos de mejora

- **Objetivo:** llegar a las metas sin parches.
- **Cada ciclo:**
  1. sparring de 30 charlas y lectura;
  2. familias que pesan;
  3. para cada una, su sitio según §5. Si falta una decisión, es una pregunta para vosotros;
  4. arreglo, con una revisión;
  5. comprobación con pruebas de código y fichas, no con el sparring;
  6. versión nueva.
- **Cada integración** pasa el examen.
- **Revisión de rumbo cada 3 ciclos** con vosotros: qué se movió, cuánto código y cuántas reglas hay, y si seguimos.
- **Puerta:** un examen cumple todas las metas y el de confirmación también.
- **Señales de parada:** las de §13.3.

### F6 · Sombra con conversaciones reales

- **Objetivo:** ver el bot ante clientes de verdad sin que ninguno lo vea.
- **Qué se hace:**
  - **sombra histórica** sobre la caja fuerte: el examen oculto y las conversaciones nuevas de Andrés;
  - **sombra en vivo**, si producción ya está conectada: el bot escribe su respuesta como nota interna y el equipo contesta como
    siempre. Se compara después.
- **Puerta:**
  - en al menos 200 turnos reales: lo exacto, a cero fallos; pases indebidos y que faltan, contados y aceptados por vosotros;
  - una muestra de 30 a 50 respuestas revisada por una persona del negocio, con un umbral de «la habría enviado» fijado en F2.
- **Hito:** presentación a Andrés.

### F7 · Borrador con aprobación y autonomía por acción

- **Objetivo:** que el bot empiece a dar valor con una persona delante, y gane autonomía donde lo demuestre.
- **Los peldaños**, por tipo de acción y no para todo el bot:

| Peldaño | Qué hace el bot | Quién envía |
|---|---|---|
| 1. Borrador | Propone la respuesta | La persona, tras aprobar o corregir |
| 2. Autónomo con muestreo | Contesta solo lo informativo. Se revisa una muestra | El bot |
| 3. Autónomo | Contesta solo esa acción | El bot |

- **Para subir un peldaño:** una acción necesita 200 borradores o dos semanas, con 9 de cada 10 enviados sin corregir el fondo y
  ningún error de dinero. Cifras de partida tomadas de la investigación; las confirmáis en F2.
- **Nunca suben:** dinero, cambios y cancelaciones, quejas, salud y «quiero una persona» (regla 10).
- **Cualquier cambio de modelo o de prompt base** devuelve las acciones afectadas al peldaño 1.
- **Cada corrección de una persona** se convierte en ficha y pasa por §5.

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

Es una propuesta; los papeles los decidís vosotros.

| Quién | Qué decide o hace |
|---|---|
| Gadea | Las reglas y los datos del negocio, las metas, y qué sube a PRE y a producción |
| Álvaro | La constitución con Gadea, el alcance, los costes y la relación con Andrés |
| Los dos | Abrir cada puerta y cualquier excepción a la constitución |
| Equipo de Andrés | Aprobar borradores en F7 y, si se decide así, etiquetar para calibrar al juez |
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
| Una integración no mejora ninguna cifra más que su ruido y no cumple la meta | Se para. Se escribe «qué estamos haciendo mal» antes de tocar nada |
| Tres integraciones seguidas sin llegar a la meta | Decidís vosotros entre: salir solo en modo borrador, cambiar de modelo o replantear |
| Un arreglo necesita otro arreglo para no romper algo | Se revierte y se rediseña |
| El código del motor o el número de reglas crece dos ciclos seguidos sin que mejore una cifra | Revisión de rumbo |
| Alguien ajusta una regla mirando el sparring o el examen | Prohibido. Se deshace |
| Un entregable va por su tercera versión | Se para: decide un dueño |

## 14. Riesgos

| Riesgo | Antídoto |
|---|---|
| **Segundo sistema:** meterle al nuevo todo lo aprendido | Solo entra lo que permite la constitución. El marcador enseña líneas y reglas en cada integración |
| **Repetir el bucle en sala limpia** | Parte B, las señales de §13.3 y un entregable, una revisión, una corrección |
| **Afinar contra la vara** | Examen congelado que solo da cifras. Caja fuerte de reales que no se abre hasta F6 |
| **Falta de vuestro tiempo** | Lo que se os pide está acotado: §16, 3 horas una vez y 30 minutos por semana. Si no hay tiempo, la fase espera; no se decide por vosotros |
| **Producción y la API de WhatsApp tardan** | Se empiezan en F0. F6 puede hacerse solo con sombra histórica |
| **El modelo cambia o se retira** | Queda fijado por versión. Cambiarlo es una integración completa, con examen |
| **Un solo proveedor del modelo** | Si no contesta, aviso y pase a una persona. Alertas de saldo y de errores |
| **Dos repos vivos** | El viejo se congela en F0 y se archiva en F8 |
| **Los clientes simulados no se parecen a los reales** | Por eso el examen no es la última puerta: lo son la sombra y el borrador con personas |
| **El 10 % resulta inalcanzable** | El bot da valor antes: como borrador con aprobación. Lo decidís en la tercera señal de §13.3 |
| **Datos de clientes** | Lo real sin anonimizar no sale de quien lo custodia. Al repo, solo lo anonimizado |
| **Se pierden lecciones enterradas en el código viejo** | Viajan como decisiones en la tabla de reglas y como fichas. El repo viejo queda de consulta |

## 15. Costes

Son órdenes de magnitud, con lo medido hasta hoy.

| Concepto | Cifra | Nota |
|---|---|---|
| Una respuesta del motor | Alrededor de 0,1 céntimos de dólar | V1: unos 0,09 $ por 40 clientes |
| Una tirada del examen (200 clientes) con el motor | ~0,45 $ | Por OpenAI |
| Una tirada del examen con el bot actual | ~0,8 $ | Por OpenRouter. Solo en F2 y F3 |
| Un examen juzgado (3 tiradas, 2 juicios) | Unas 2 ventanas de Claude | Sin coste de API |
| Mensajes de WhatsApp | Gratis hasta 1.000 respuestas al mes por número; después, por mensaje | Tarifa de Colombia por confirmar |
| Servidor | El actual | Producción puede pedir otro |
| Plataformas comerciales, como referencia | Fin: 0,99 $ por resolución. Decagon y Ada: decenas de miles de dólares al año (estimaciones) | No encajan con una cotización propia |

**Tiempo.** No hay fechas cerradas, porque cada puerta depende de vuestras decisiones y de las ventanas de Claude. Como orientación,
con dos Claudes: F0 a F4, entre cuatro y seis semanas. F5 depende de cuántos ciclos hagan falta. F6 y F7 dependen de producción y
del equipo de Andrés.

## 16. Decisiones

### 16.1 Ya decididas por Gadea (10-nov), que este plan respeta

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
- Sin el origen, ningún enlace. Al reservar, se pide una vez con su motivo y, si no lo dice, pasa con un asesor.
- Con la nacionalidad sin saber tras dos preguntas, el enlace con la línea para quien sea colombiano.
- Un plan que va con asesor se dice una vez y se pasa cuando quiera reservar.
- Lo que la base no tiene y no está en la lista pasa de verdad con una persona.

### 16.2 Para decidir antes de F0

| # | Decisión | Nuestra recomendación |
|---|---|---|
| 1 | ¿Repo nuevo, como propone este plan? | Sí |
| 2 | ¿Aprobáis la constitución (Parte B)? | Sí, con los cambios que queráis |
| 3 | ¿Quién etiqueta las 100-150 respuestas para calibrar al juez? | Gadea, o Gadea con alguien del equipo de Andrés |
| 4 | ¿Aprobáis la quinta salida: reglas por situación, elegidas por el estado? | Sí, pero usarla solo si el cumplimiento regla a regla lo pide |
| 5 | Si un importe sigue mal tras rehacer, ¿sale y se cuenta (decidido para todo), o en dinero pasa con una persona? | En dinero, pasar con una persona: la empresa responde por lo que dice el bot |
| 6 | Tras un pase, ¿el bot calla hasta que el asesor lo devuelva, o sigue contestando lo que sepa? | Callar, con un aviso de que ya lo tiene una persona. Hoy sigue contestando |
| 7 | Las emergencias (ahogo, desmayo, sangrado): ¿regla para el modelo, o alarma por palabras clave en el código? | Alarma en el código solo para emergencias: ahí un fallo cuesta demasiado |
| 8 | ¿Qué hace el bot con datos como tarjetas o cédulas? (`privacy.py`) | No guardarlos ni repetirlos; lo demás, en el diseño de F4 |
| 9 | ¿La meta de importes se cuenta «contra la ficha»? | Sí |
| 10 | ¿El asistente dice desde el primer mensaje que es virtual? | Sí |
| 11 | ¿Quién sube a PRE y a producción, y quién abre cada puerta? | Gadea sube; las puertas, los dos |
| 12 | ¿Nombre del repo y del motor? | El que elijáis |

### 16.3 Para averiguar en F0 (no bloquean el arranque)

- Si el número de WhatsApp de producción puede usar la API y seguir en la aplicación del equipo.
- Las tarifas de WhatsApp para Colombia.
- Qué obliga la ley colombiana de datos personales y si el aviso de asistente virtual es exigible allí.
- La fecha para pedir a Andrés conversaciones nuevas, y cuántas.
- Si el equipo de Andrés atenderá por Chatwoot en producción.

## 17. Qué pasa con el repo viejo

- **Desde F0:** queda etiquetado y congelado. Sigue en PRE como referencia para medir y como vuelta atrás.
- **No se integran** las ramas de bloques ni las de V2 (`bloque05`, `bloque4r`, `puerta-v2`, `bloque1`, `bloque4p`, `bloque31`).
- **Se aprovecha como dato,** no como código: el catálogo, la tarifa, las decisiones, las conversaciones reales anonimizadas, el
  análisis por fases y la historia.
- **Se aprovecha como referencia de código,** reescrito limpio y con su diseño: V1 (`scripts/simple_v1.py`), el calendario del cierre
  (bloque 3.1), el reconocimiento de importes y enlaces en un texto, la conexión con Chatwoot y la nota del pase.
- **Se aprovecha como herramienta de equipo:** Coral y la memoria compartida.
- **En F8** se archiva.

---

## Glosario

| Término | Significado |
|---|---|
| Motor | El programa que conversa. Es igual para cualquier negocio |
| Paquete del negocio | Los datos de un negocio: lo que sabe, sus precios, sus reglas |
| Hecho | Un dato que calcula el código: un precio, una fecha, un enlace |
| Regla | Una decisión de un dueño, escrita para que el asistente la siga |
| Puerta | La comprobación de hechos que pasa cada respuesta antes de enviarse |
| Ficha | Una conversación de prueba con su respuesta correcta ya calculada |
| Examen | El conjunto grande y congelado de clientes simulados que decide si una versión llega a la meta |
| Sparring | Un Claude que hace de cliente para descubrir fallos |
| Sombra | El bot escribe su respuesta sin que el cliente la vea, para compararla con la de una persona |
| Juez | Un modelo de IA que dice si una respuesta tiene un fallo grave |
| Calibrar | Medir cuánto coincide el juez con una persona |
| p90 | El tiempo que tardan las respuestas lentas: 9 de cada 10 tardan menos |
| PRE | El entorno de pruebas. No atiende a clientes reales |
| Versión | Una foto del bot: su código, su prompt base, su paquete y su modelo |
