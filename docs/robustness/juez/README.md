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
