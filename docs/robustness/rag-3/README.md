# rag-3 — búsqueda con estado y nombres de servicio (29-sep, Gonzalo)

Dos mitades independientes. La primera arregla el **instrumento de medida**; la segunda, el **bot**.

---

## rag-3a · los nombres de servicio: el juez se equivocaba, no el bot

**Lo que dice el enunciado** (handoff del 29-sep): unificar los nombres entre `services.json` y
`pricing.json`, porque el juez usa `pricing.json` como referencia y marca de invento el nombre de
`services.json`. Decidir el nombre oficial y dejarlo en un solo sitio.

**Lo que hay de verdad, al mirarlo:**

| | |
|---|---|
| servicios con nombre distinto entre las dos fuentes | **34 de 36** (ninguno coincide) |
| ¿es un renombrado 1 a 1? | **no**: las 4 especialidades de `services.json` comparten UNA entrada de `pricing.json` |
| ¿quién lee los `name_*` de `pricing.json`? | **nadie en el bot** — solo el juez, dentro del volcado en crudo |
| ¿quién lee los de `services.json`? | el bot entero (`catalog.SERVICES`) |

No son dos grafías del mismo listado: son dos granularidades. Pero el arreglo es pequeño, porque el
bot solo mira una de las dos.

**Cuál es el nombre oficial.** El de la web, o sea `services.json`: sus entradas llevan `url` y
`booking_url` a divingplanet.org — el enlace de reserva del servicio del caso es literalmente
`book.divingplanet.org/book/salidas-de-buceo/1`. `pricing.json` no tiene URLs: su `_comment` dice
que sale de `TARIFA PLENA FINAL.csv`, la hoja de tarifas interna.

**Entonces el fallo era del instrumento.** El juez recibía `pricing.json` entero y NO recibía
`services.json`, así que medía al bot contra un vocabulario que ni el bot ni el cliente ven. Su
veredicto, literal: *"el servicio oficial se llama 'Certified Diver - 2 dives (1 day)'"*. No lo es.

**Arreglo:** `judge_golden_set.load_reference()` añade un extracto compacto de `services.json` con
los nombres oficiales, en el mismo estilo que ya usaba para `activities.json`, diciendo
explícitamente que son los válidos.

**Medido sin gastar una ronda en PRE.** Re-juzgando la ronda `2026-09-28-rag2-B` ya grabada en
disco (0,4889 $, sin desplegar nada). Control previo: con la referencia anterior la cache daba
**190/190** criterios reutilizados y con la nueva **0/190** — la única variable es el cambio.

Cambian **5 veredictos de 256**, y solo uno es atribuible:

- ✅ `reserva-ingles · global:sin-invenciones`: **no_cumple → cumple**. Es el caso exacto.
- Los otros 4 son de `global:sin-repreguntas` (3) y de si Isla Grande pertenece a Rosario (1):
  criterios sin relación con los nombres, y **flipan en las dos direcciones**.

### ⚠️ De aquí sale un dato que el proyecto solo tenía estimado: el ruido del juez

Re-juzgando **el mismo transcript** con el mismo juez, **4 de 256 veredictos (1,6 %) cambian sin
causa atribuible**. En el agregado: criterios 94,3 % → 93,9 % (−0,4) y diálogos limpios 22 → 24
(+2), **en la misma ronda**.

Consecuencias prácticas:

1. **Una diferencia de menos de 1 punto entre dos rondas no significa nada.** Lo que decide es la
   lectura por caso, que es lo que el protocolo ya pide.
2. **El instrumento cambió**, así que los números anteriores al 29-sep no son estrictamente
   comparables con los de después. Para un A/B nuevo, juzgar A y B con la MISMA referencia.

---

## rag-3b · la ficha del servicio elegido va al contexto

**De dónde sale.** De los 5 fallos de búsqueda que quedaban tras rag-2 (`rag_piezas`, ronda
`2026-09-28-rag2-B2`), **tres tienen `selected_service` en el estado y el dato existe**:

| caso | estado | dato que falta | ¿existe? |
|---|---|---|---|
| `ow-horario-dia1` | `selected_service=open_water` | hora de fin del día 1 y regreso del día 2 | sí, en el itinerario de la ficha |
| `referido-datos-centro` | `selected_service=referral` | dirección del centro | sí, en una FAQ curada |
| `salida-confirmada` | — | "solo depende del clima" | top-8 = 1 pero **no llega al contexto** |
| `refresher-antes-en` | (sin servicio) | formulario médico | — |

El contexto ya inyectaba algo del servicio activo, pero **solo incluye/no incluye**, que no lleva
horarios ni itinerario ni requisitos.

**El cambio** (flag `RAG_FICHA_DEL_SERVICIO`, apagado): si se sabe qué servicio mira el cliente, su
**ficha entera** va al contexto.

**Una sola fuente para la ficha.** El texto lo construía `kb_v2.ficha_servicio`, en `scripts/`,
cuando solo lo usaba la base. Ahora hay dos usos, así que el constructor está en
`catalog.service_fact_sheet` y `kb_v2` lo llama. Escribirlo dos veces permitiría que la ficha de la
base y la del contexto dijeran cosas distintas del mismo servicio — lo que rag-2 vino a evitar.
El refactor es **byte a byte idéntico** (72 fichas, foto en `tests/data/fichas_servicio_antes.json`):
importa porque CI regenera `kb_v2` en cada deploy.

**Medido en local y gratis** (`scripts/rag3_contexto_local.py`, mismas anclas y normalización que
`rag_piezas`):

| | datos en el contexto por el estado |
|---|---|
| flag apagado | 9 de 92 (10 %) |
| flag encendido | **19 de 92 (21 %)** |
| | **gana 10 · pierde 0** |

Entre los ganados, **los dos datos de `ow-horario-dia1`**, el caso que abrió rag-3.

**Lo que NO arregla:** la dirección del centro (está en una FAQ curada, no en la ficha), el
formulario médico y `salida-confirmada` (sin servicio en el estado). De los 5 fallos, cubre **2**.

### Medido con `rag_piezas` de verdad (29-sep, con la clave ya puesta)

Con `--codigo-local` (el código local dentro de `dp-pre-bot`, sin desplegar), los dos lados:

| | flag apagado | flag encendido |
|---|---|---|
| dato en el top-8 | 85 % | 85 % — **intacto**, no se toca la búsqueda |
| **dato en el contexto visto** | 94 % | **97 %** |
| causa `busqueda` | 5 | **3** |
| contexto medio | 33,8k | 34,2k caracteres (+1,2 %) |

Por dato: **gana 2, pierde 0**, y son exactamente `ow-horario-dia1 · dia1` y `· dia2-regreso`, los
dos con `top8=None` — la búsqueda no los encontraba nunca. Ficheros:
`2026-09-29-rag3-{off,on}.json`.

Esto **valida la limitación del medidor local**: predijo 10 ganancias y netas son 2, porque las
otras 8 ya llegaban por la búsqueda o el catálogo. La advertencia estaba escrita; ahora está
cuantificada.

### ⚠️ Pero el dato llega y el bot sigue sin decirlo — y cuesta 2 s

Modo completo sobre el caso (`--casos ow-horario-dia1 --reps 2`, ~0,12 $ los dos lados):

| | apagado | encendido |
|---|---|---|
| dato en el contexto | 0 % | **100 %** |
| **cobertura de la respuesta** | 50 % | **50 %** (igual) |
| falta por | búsqueda 2 | **redacción 2** |
| rechazos del juez · regeneraciones | 1 · 1 | 2 · 2 |
| p50 · llamadas LLM | 5,7 s · 4,0 | **7,7 s · 5,0** |

La causa se mueve de *búsqueda* a *redacción*: el modelo tiene el dato delante y no lo dice. Leída
la respuesta, el cuadro es de tres piezas:

1. **Mejora real y visible**: con el flag, el bot recita el día 1 entero (8:00 a.m. en la
   Bodeguita, lancha, piscina, 2 inmersiones de certificación, almuerzo, traslado al hotel). Sin
   él no tenía nada de eso.
2. **No menciona el día 2 aunque lo tiene delante** ("return to Cartagena at 3:00 p.m."). Eso es
   redacción: **rag-4**.
3. **Y lo que el cliente preguntaba literalmente —a qué hora ACABA el día 1— no existe en los
   datos**: el itinerario da la secuencia del día 1 pero no su hora de fin, mientras que del día 2
   sí da las 15:00 y la llegada a las 16:15. El bot dice "no lo tengo, un asesor te lo confirma",
   que para esa subpregunta es la conducta correcta. **Hueco de negocio, no de RAG**: candidato a
   la lista de decisiones (D1-D8).

Y el primer intento de respuesta fue tumbado por el juez de grounding por inventarse *"usually
finish in the early afternoon"* — de ahí la regeneración y los 2 s de más.

**Veredicto: NO se promociona solo.** Hace lo que se diseñó (el dato llega al contexto) pero no
mueve la nota por sí mismo y cuesta ~2 s y una llamada de más en ese caso. Tiene sentido
promocionarlo **junto con rag-4**, que es lo que convierte "está en el contexto" en "lo dice".
Aviso de muestra: las cifras de latencia y rechazos son de **2 repeticiones sobre 1 caso**; para
decidir por latencia hace falta la ronda core.

---

## Lo que queda visto y sin hacer

- **La otra mitad del enunciado de rag-3**: "la búsqueda prioriza su origen". Esto no se ha tocado,
  y es lo que movería el `top-8`; lo de aquí mueve `en_contexto`. El criterio de cierre del plan
  (top-8 ≥ 90 %) sigue pendiente de esa mitad.
- `salida-confirmada`: el dato está en el **top-8 pero no llega al contexto**. Huele a recorte por
  tamaño — sería de rag-5 (latencia estructural).
- `catalog.extra_block_es/en` es **código muerto**: nadie lo consume. Para la limpieza de s4-25.
- Los `name_*` de `pricing.json` no los lee el bot: marcarlos como etiquetas internas en su
  `_comment` para que nadie vuelva a tomarlos por oficiales.


---

# A/B completo de rag-3b + rag-4 (47 casos, 29-sep) — **NEGATIVO, no se promociona ninguno**

Los dos flags juntos, porque cada uno resuelve la mitad del otro: rag-3b mete el dato en el
contexto y rag-4 hace que el bot lo diga. Medido con `rag_piezas --codigo-local`, 47 casos × 1 por
lado (~2,8 $). Ficheros: `2026-09-29-rag34-{off,on}.json`.

| | apagado | encendido |
|---|---|---|
| **cobertura de la respuesta** | 89 % | **89 %** — no se mueve |
| falta por búsqueda | 4 | **2** ✅ (rag-3b sí hace lo suyo) |
| falta por redacción | 6 | 6 |
| falta por juez/guardas | 0 | **2** |
| **dice algo PROHIBIDO** | 0 | **1** |
| "no lo tengo" | 0 | 1 |
| **rechazos del juez · regeneraciones** | 2 · 2 | **8 · 7** |
| p50 · llamadas LLM | 2,9 s · 3,1 | 3,0 s · 3,4 |
| contexto medio | 33,8k | 34,9k |

**Por caso: gana 3, pierde 4.** Gana `salida-confirmada` (los dos datos, el caso diagnosticado) y
`edad-minima-ninos/snorkel-6`; pierde `dos-buceos-un-dia-en/mismo-dia`,
`equipaje-mochilas/una-por-persona` y los dos de `fotos-fotografo`.

**Lo que de verdad lo tumba: el dato prohibido.** En `refresher-antes-en` el bot dice *"you'll need
to complete the theory part of the refresher course, which takes about 4 hours"*. Las 4 horas de
teoría son del **curso Open Water**, no del refresher. El mecanismo se entiende y es la lección:
**con la ficha entera del servicio en el contexto (rag-3b) MÁS la instrucción de "di lo que tengas"
(rag-4), el modelo cruza datos entre servicios.** Los dos cambios se potencian mal: uno mete más
material y el otro empuja a usarlo.

Eso explica también los rechazos del juez (2 → 8): el guard de grounding está haciendo su trabajo y
frenando afirmaciones sin respaldo, a costa de 7 regeneraciones.

**Lo de 5 casos no generalizó.** rag-4 solo daba 57 % → 79 % de cobertura en los 5 casos de
redacción; en los 47 la cobertura no se mueve. Con 1 repetición por lado hay ruido de muestreo
(`equipaje-mochilas` mejoraba en la tanda de 5 y empeora aquí), pero el salto de rechazos y el dato
prohibido no son ruido.

**Veredicto: los dos flags se quedan APAGADOS.** PRE no cambia.

## Lo que hay que probar después, en este orden

1. **rag-4 SOLO, sobre los 47** (~2,8 $). No está medido: lo de hoy mezcla los dos flags, así que
   no se sabe si el daño lo mete rag-4, rag-3b o la interacción. Es la pregunta que decide si
   rag-4 es promocionable por su cuenta, y la hipótesis de arriba dice que el problema es la
   COMBINACIÓN.
2. **Si el problema es la interacción**, acotar rag-3b: en vez de la ficha entera, inyectar solo el
   itinerario y los requisitos (lo que la búsqueda no trae), para no dar material de otros
   servicios.
3. Y mirar `refresher-antes-en` aparte: el formulario médico del refresher ya salía como fallo de
   búsqueda en rag-2, y ahora además se confunde con el curso. Huele a que el refresher necesita su
   propia ficha en la base curada.
