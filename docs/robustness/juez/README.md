# El juez que rechaza datos buenos (análisis del 1-oct, Gadea con Claude)

Sustituye a rag-6 (la base curada entera en el prompt), descartada sin gastar: la base curada ocupa ~40.700 tokens
en español (~30.000 solo el origen del cliente) frente a ~9.000 del prompt de hoy, la búsqueda ya trae el 92 % de los
datos que dependen de ella y rag-3b mostró que más material en el contexto hace cruzar datos entre servicios.

## Material

Todos los rechazos del juez de grounding (gpt-4.1, juez v3) en las rondas core con la base curada (`kb_v2`),
sacados de los logs de PRE con `scripts/juez_rechazos.py`:

- **diseño** (leídas antes de decidir nada): rag5-A, rag5-B, rag5-C → 28 rechazos, 39 hechos marcados NO
  (`rechazos-diseno-rag5-ABC.json`);
- **ciego** (clasificadas después, con las mismas categorías y sin cambiarlas): rag2-B, rag3-A, rag3-B → 26 rechazos,
  36 hechos (`rechazos-ciego-rag2B-rag3AB.json`).

Cada rechazo cuesta una segunda redacción + otra llamada al juez (~3 s) y, si se rechaza también, el cliente recibe
"no lo tengo a la mano".

## Causas (54 rechazos)

| causa | diseño | ciego | total | ¿acierta el juez? |
|---|---|---|---|---|
| **1. La regla de moneda del catálogo** ("NO existe precio ni descuento especial para colombianos"): rechaza el precio CORRECTO en cuanto la respuesta dice "para colombianos", y la oferta de asesor que lo menciona | 9 | 5 | **14** | no |
| **2. La reescritura de la pregunta estropea la búsqueda** ("great, how do i pay" → "How do I pay for the Fun Dives?"): los datos de pago SÍ están en la base, pero con la pregunta reescrita no llegan al top-8 | 4 | 3 | **7** | sí, con lo que ve; el fallo es de búsqueda |
| **3. Falta en la base** | 11 | 11 | **22** | sí (pero el dato a menudo es cierto) |
| · plan de acompañante (no hay ficha: solo una línea del catálogo; el bot inventa qué incluye y el precio desde las islas) | 7 | 5 | 12 | |
| · empresa (30 años, PADI 5 Estrellas) | 4 | 3 | 7 | |
| · Isla Grande es parte de las Islas del Rosario | 0 | 3 | 3 | |
| **4. Ofrecer un asesor** rechazado sin mencionar colombianos | 3 | 3 | **6** | no |
| **5. Inventos de política** (reagendar "sin perder la reserva", quedarse un día más) y 1 vago | 2 | 4 | **6** | **sí** |

Las mismas causas en los dos grupos: no es un patrón de tres diálogos.

**Comprobación de la causa 1** (juez real, 3 repeticiones, el catálogo que recibe en PRE): "Para colombianos, el
paquete de 5 inmersiones cuesta 1.429.000 COP…" → rechazado 3/3 ("El precio es para colombianos. NO"); sin la frase
"NO existe precio ni descuento especial para colombianos" → aceptado 3/3. El mismo precio sin "para colombianos" →
aceptado con y sin la frase. La oferta de asesor que menciona colombianos: 2/3 rechazada con la frase, 0/3 sin ella.
Es la causa de la regresión "no lo tengo a la mano" con el precio en COP del paquete de 5 que salía en A, B y C.

**Comprobación de la causa 2** (búsqueda en la base de PRE, top-8): "great, how do i pay" trae las 6 piezas de pago
(faq:114, faq:115, faq:118, faq:119, politica:payment_fallback, politica:foreign_card_payment); "How do I pay for the
Fun Dives?" no trae ninguna (fichas de Fun Dives). La reescritura además cambia el sentido de otros mensajes ("not
colombian" → "Are you a Colombian resident?", "Hello, im getting in tmrw" → "What time should I expect to arrive
tomorrow?").

## Arreglos propuestos (por causa, globales)

1. **Regla de moneda sin ambigüedad**: que diga lo que quiere decir (los colombianos pagan en COP el precio del
   catálogo; lo que no existe es un descuento o tarifa rebajada para colombianos). Es un dato del catálogo que se
   contradice, no un matiz del prompt; se valida con el juez real antes de medir. → 14 rechazos.
2. **Buscar con la pregunta original Y con la reescrita** y unir los resultados (era la "F" de la propuesta
   original de rag-5); la búsqueda con la original puede empezar sin esperar a la reescritura. → 7 rechazos, y más
   robustez frente a reescrituras que cambian el sentido.
3. **Datos** (decisiones de negocio): ficha del acompañante, datos de la empresa (30 años y PADI 5 Estrellas,
   confirmados por Gadea el 1-oct), Isla Grande dentro de las Islas del Rosario. → 22 rechazos.
4. Ofrecer un asesor: volver a medir después de 1-3 (la mitad mencionaban colombianos); si persiste, arreglo aparte.

Abordables: ~43 de 54 rechazos (80 %). Los 6 inventos de política deben seguir rechazándose.

## Arreglos 1-3 hechos y medidos en local (1-oct, rag_piezas, sin desplegar)

Datos (decisiones de Gadea, 1-oct): **acompañante** desde Cartagena incluye lancha, almuerzo, seguro y entrada al
Parque Nacional Natural (80 USD / 288.000 COP online, 89 / 320.000 normal); ya en las islas, el mismo precio, sin
almuerzo (regla D5). FAQ propia del acompañante y de Isla Grande; FAQ 23 con los 30 años. Base de prueba cargada en
`kb_v2_prueba` (372 documentos).

**Regla de moneda: una para el que redacta y otra para el juez.** Primera redacción común ("decir 'para colombianos
cuesta X COP' es correcto"): el juez bien, pero el bot dejó de corregir el mito del precio especial (1/4 frente a
4/4). Segunda (el hecho sin la instrucción): el bot bien (4/4), el juez volvió a rechazar. Causa: necesitan cosas
distintas. Ahora `catalog.para_el_juez` cambia solo esa línea en el catálogo que ve el juez. `scripts/sonda_juez_moneda.py`
(juez real, N=3): 15/15 respuestas correctas aceptadas (antes: paquete de 5 "para colombianos" 0/3), 12/12 inventos
rechazados (descuento para colombianos, tarifa especial, acompañante a 50 USD, almuerzo en islas). rag_piezas, 4
casos de moneda × 4: todo 100 % y el mito corregido 4/4.

**Búsqueda doble** (`RAG_BUSQUEDA_DOBLE`): primera versión (intercalar por posición y quedarse en 8) sacaba del top-8
la FAQ de los hoteles base; segunda: solo si la reescritura cambió la pregunta (con la reescrita igual, la única
diferencia era la marca de origen) y la reescrita INTACTA + hasta 4 piezas que solo trae la original. rag_piezas
medía el top-8 sobre la última búsqueda registrada (la secundaria): corregido para medir la principal.

rag_piezas, 48 casos × 1 (A = PRE, B = local con `kb_v2_prueba`): top-8 de búsqueda 92 % = 92 %; cobertura 89 → 87 %
(ruido de 1 muestra); casos que cambiaban, × 3: hoteles base 3/3 = 3/3, plan de acompañante 2/3 → 3/3, **pago por
transferencia 3/3 → 1/3**: el juez rechaza "el pago por transferencia no tiene descuento especial" (se deduce de la
lista cerrada de descuentos) y después la frase "no lo tengo a la mano, un asesor te lo confirma" → "no lo tengo".
Es la causa 4 (la oferta de asesor rechazada), que sigue viva.

---

## Ronda core en PRE: J2 y búsqueda doble (1-oct tarde, Gonzalo) — J2 PROMOCIONADO, búsqueda doble SIN DECIDIR

Paso 1 del "Siguiente" del handoff. `run_synthetic_pre --sample core` contra PRE sirviendo `4c330ef` (J2 y
`RAG_BUSQUEDA_DOBLE` encendidos), 32 conversaciones / 93 turnos, sin respuestas perdidas. A = `2026-10-01-rag5-C`.
Ficheros: `synthetic-runs/2026-10-01-juez-B.jsonl`, `snapshots/2026-10-01-juez-B.json`,
`logs-pre-2026-10-01-juez-B.txt`, `golden-set/results/2026-10-01-{rag5-C,juez-B}__gpt-5-mini-medium.json`.

### ⚠️ Antes de comparar: A se re-juzgó con la referencia de hoy

A se juzgó a las 11:38 del 1-oct; a las 14:44 `d900c71` cambió `policies.json` (la regla del 10 % con transferencia),
que forma parte de la REFERENCIA del juez del golden. Juzgar B con la referencia nueva y comparar con A con la vieja
habría medido el instrumento, no el bot. Comprobado: con la referencia de hoy, A daba 0/190 en caché. **Solo el cambio
de referencia mueve A de 94,2 % a 92,6 %**: comparada con su cifra vieja, B (93,0 %) habría parecido 1,2 puntos PEOR.

### Resultados

| | A | B |
|---|---|---|
| criterios cumplidos (misma referencia) | 92,6 % (17 fallos) | **93,0 %** (16 fallos) |
| diálogos sin fallos | 22/32 | **22/32** |
| latencia del cliente p50 · p95 · máx | 3,0 · 6,0 · 8 s | **3,0 · 6,0 · 8 s** |
| llamadas LLM por turno · máximo | 2,70 · 8 | **2,69 · 6** |
| búsquedas (embeddings) por turno | 0,98 | **1,30** (+33 %, la búsqueda doble) |
| **rechazos del juez de grounding** | **8** | **3** (+1 rescatado por J2) |

Calidad y latencia, iguales. Los rechazos del juez bajan de 8 a 4 (3 + 1 rescatado), sobre todo por los arreglos de
moneda y datos del 1-oct, no por J2.

### J2: lectura a mano (`scripts/j2_rescates.py`, nuevo)

La línea `[RAG][GROUNDING][JEV]` del registro trae las frases cortadas a 60 caracteres y sin conversación. El script
empareja cada una con su turno (validado: las 32 conversaciones tienen los mismos turnos en registro y ronda).

**1 rescate, correcto.** `paquete-5-buceos-cop-refresh-y-hoteles`, turno 2, "¿y en pesos? ¿para colombianos?": Jev
deja pasar "El detalle exacto del costo actualizado te lo puede confirmar un asesor" (p = 0,17). No afirma nada del
negocio. **Ningún invento coló.** (La respuesta rescatada no es buena — no da el precio en pesos que está en el
catálogo —, pero eso no es de J2: ver abajo.)

**3 rechazos mantenidos, bien mantenidos** (las frases sí afirman cosas): los precios en pesos del paquete de 5
(0,96-0,97), "30 años" / "PADI 5 estrellas" / "instructores expertos" (0,90-0,91), y "Para proceder con la
cancelación, te paso con un asesor…" (**0,25**).

**Veredicto J2: PROMOCIONADO.** Por construcción nunca empeora: solo convierte un rechazo en aprobado, y solo si Jev
está seguro; si falla, se mantiene el rechazo. Umbral: se queda en 0,2. La cancelación a 0,25 es el primer dato real
a favor de subirlo, pero un caso no basta (la afirmación más baja del banco está en 0,28).

### Las regresiones las causa el JUEZ, no los interruptores

4 mejoras y 4 regresiones por criterio. **3 de las 4 regresiones están en las 3 conversaciones donde el juez de
grounding rechazó algo, y en las 3 lo rechazado era verdadero o inofensivo:**

| conversación | qué tiró el juez | ¿era falso? | regresión |
|---|---|---|---|
| `clima-y-cancelacion-reserva-existente` ("¿Podemos cancelar porfa?") | "te paso con un asesor" | inofensivo; J2 no lo rescató por 0,05 | **no pasa al cliente con un asesor** |
| `certificado-fechas-fotos-y-reserva` | "30 años", "PADI 5 estrellas" | **verdadero**: está en las instrucciones del propio bot | vuelve a preguntar el plan |
| `paquete-5-buceos-cop-refresh-y-hoteles` | 1.429.000 / 1.587.000 COP | **correcto**: es el precio del catálogo | repregunta la certificación |

En la ronda A esas mismas conversaciones pasaron porque el juez, que no es determinista, no golpeó en esos turnos.
**El juez de grounding rechaza datos verdaderos**, y la segunda redacción estropea la respuesta:

1. **Precios en pesos en conversación.** El arreglo de la regla de moneda (`catalog.para_el_juez`) se midió con
   preguntas sueltas (15/15); aquí la pregunta llega en el SEGUNDO turno y falla igual. Es la causa real del pendiente
   "no lo tengo a la mano con el precio en COP del paquete de 5": no es el bot, es el juez.
2. **Los datos de marca del propio bot.** "30 años" y "PADI 5 estrellas" están en `RAG_INTRO` (`src/prompts/info.py`,
   la presentación que el bot tiene ORDENADO decir). El juez comprueba contra el contexto de la búsqueda, donde esa
   presentación no está. (El 28-sep "llevamos 30 años" se anotó como invento en el comentario de
   `RAG_REGEN_FEEDBACK_ES`; no lo es.)
3. **La oferta de asesor**, la causa 4 de siempre, ahora en una cancelación: el cliente se queda sin quien le gestione
   la cancelación.

### Búsqueda doble: SIN DECIDIR, a propósito

B cambia a la vez la búsqueda doble, J2 y los datos nuevos del 1-oct, así que la ronda no aísla su efecto; y
`rag_piezas` no la ve (preguntas sueltas; la reescritura depende del historial). Indicio a favor: el formulario médico
del refresher pasa a cumplir (era un fallo de búsqueda conocido) y J2 no actuó en esa conversación. Coste: +33 % de
búsquedas, baratas. **Para decidir: una ronda core con SOLO este interruptor cambiado.**

### Paso 1 (Álvaro, 1-oct noche): el juez ve la presentación — `JUEZ_PRESENTACION` PROMOCIONADO

- **Qué:** la presentación oficial (PADI 5 Estrellas, 30 años) vive en `prompts/info.py` `PRESENTACION_ES/EN`; la usan
  `RAG_INTRO` (idéntico byte a byte) y `JUEZ_PRESENTACION_*`, que va en el contexto del juez tras el catálogo.
- **Banco** (`scripts/sonda_juez_presentacion.py`, juez de producción con J2, contexto real, ×3; criterio fijado antes:
  ciertos ≥ 2/3 y ningún invento pasa): ciertos 3 → **12/12**; inventos parecidos 17 → **18/18**
  (`presentacion-2026-10-01.json`).
- **Ronda core `2026-10-01-presentacion-B`** frente a `juez-B` (solo cambia este flag): rechazos del juez 3 → **0**
  (los 3 de A eran verdades), "no lo tengo" 0 → 0, turnos con pregunta p50 4,29 → 3,91 s, cliente igual. La
  cancelación pasa a una persona.
- **El juez de las rondas** suspendía "tenemos 30 años" por la misma razón: `judge_golden_set.load_reference` incluye la
  presentación. Re-juzgadas A y B con esa referencia: 94,3 % (24/32) y 93,4 % (23/32), −0,9 puntos, dentro del ruido.
  Regresiones leídas: repreguntas de la reserva (2), "sales de Cartagena" supuesto y un link oficial tomado por fuga;
  ninguna en un turno donde actuara el flag (en B el juez no rechazó nada).
- **Pendiente visto:** cruce referido/refresher ("ambos requieren teoría y piscina previas") que el juez no caza.

### Siguiente

1. **Darle al juez lo que el bot tiene ordenado decir** (la presentación de `RAG_INTRO`), igual que `para_el_juez` le da
   el catálogo: una fuente, y el juez deja de tirar los datos de marca. Calibrar con una sonda antes.
2. **Los precios en pesos en conversación**: reproducir el turno 2 de `paquete-5-buceos-cop` y ver qué contexto ve el
   juez.
3. **La oferta de asesor por código** (paso 3 del handoff): el caso de la cancelación es justo eso, y ahora con daño
   real al cliente.
4. La ronda aislada de la búsqueda doble.
