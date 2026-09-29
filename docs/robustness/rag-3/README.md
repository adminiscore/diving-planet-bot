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

**Lo que falta para promocionarlo:** `rag_piezas` de verdad. No se pudo lanzar: corre dentro de
`dp-pre-bot` por SSH y en esta máquina no está `~/.ssh/dp_pre_vps`. El modo `--solo-busqueda`
cuesta céntimos y ~1 min (el modo completo, ~3 $ y 12 min) — basta con tener la clave.

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
