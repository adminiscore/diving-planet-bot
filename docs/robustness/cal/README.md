# Fase CAL — CAL-0: el banco de fallos y POR QUÉ falla cada uno (15-oct, Gonzalo)

Primer paso de la fase CAL ("lo que está en la base no falla"; plan en `docs/robustness/ex10/informe-ex10-y-plan-cal.md`).
Los 73 fallos del examen ex-10 (`2026-10-15-ex10-completa`: 38 visibles reales, 32 del oculto —ya gastado, decisión de
Gadea— y 3 sintéticos), convertidos en casos reproducibles, y medido por qué falla cada uno antes de arreglar nada.

## Cómo está hecho

| Paso | Herramienta | Salida |
|---|---|---|
| 1. Cada fallo con su turno y la pieza que lo escribió | `scripts/fallos_por_turno.py 2026-10-15-ex10-completa` (Álvaro, s4-31) | `fallos-por-turno-ex10.json` |
| 2. El banco: fallo + criterio y lo que pedía (también los globales) + causa de Gadea + conversación REAL hasta el turno | `python -m scripts.banco_fallos construir` (sin API) | `banco-fallos.json` |
| 3. Diagnóstico de los turnos del RAG (56): se reproduce la conversación DENTRO de PRE hasta el turno que falla y un verificador (gpt-4.1, temperatura 0) dice si el fallo se repite hoy, si es de información y si esa información estaba en el CONTEXTO | `python -m scripts.banco_fallos diagnosticar` (~2 min por caso, ~1,5 $) | `banco-fallos.json` → `diagnostico` |
| 4. Los que no son del RAG (17), leídos a mano | — | `diagnostico-manual.json` |

Causas medidas: **busqueda** (el dato no llegó al contexto), **redaccion** (estaba en el contexto y la respuesta no lo
dice), **entendimiento** (repregunta, supone o no pide un dato: no es de información), **no_se_reproduce** (la respuesta
de hoy ya no falla: variación de la ronda o arreglado después), **regla** (falta aplicar una decisión de negocio:
moneda, teléfono, idioma), **escalado**.

El banco queda como test de regresión de la fase: `diagnosticar --ids …` vuelve a pasar los casos que se quieran.

## Los 17 que no son del RAG (leídos a mano)

| Causa | Casos | Qué pasa | Tarea |
|---|---|---|---|
| **El menú de actividades sale cuando no toca** | 6: cal-17, 34/35, 45, 54, 60 | "5 inmersiones", "no estamos certificados", "Muchas gracias!" (sabiendo ya que quiere bucear) o elegir uno de los planes que el bot acaba de ofrecer → "¿Con cuál te animas — buceo, minicurso, snorkel o un curso PADI?". Sabiendo que quiere bucear, lo que falta es la certificación; "N inmersiones" = buceo certificado; "no estamos certificados" = recomendar el minicurso. | CAL-C |
| Pregunta fija una a una | 2: cal-16, 57 | Con la fecha dada solo repite el origen; "beginner (4/5 dives)" → el origen en vez de aclarar certificado o minicurso. | CAL-C |
| Reglas de negocio sin aplicar | 4: cal-03, 12, 19, 51 | Teléfono → da el WhatsApp (decisión: pasar a persona); portugués → responde en español (decisión 14-oct: en inglés); cotiza USD y COP sin nacionalidad (decisión: USD). | CAL-B, CAL-E |
| Escalado por error | 2: cal-38/39 | "the discount of 10% is not showing up. what is the code?" → "Sorry the link didn't work" y asesor; no explica que el 10 % online es automático. | CAL-E |
| Omite información (sin RAG o sin cita) | 3: cal-13, 23, 55 | No dice que operamos todos los días; no aclara que Barú no es Islas del Rosario. | CAL-A |

## Los 56 de turnos del RAG (diagnóstico en PRE, 1 reproducción cada uno)

Medido por el verificador y **revisado a mano**: confundía "falta decir algo" con "no pide un dato" y con las reglas
nuevas de Gadea (8 corregidos: los de moneda que pedían preguntar la nacionalidad, "no pide personas", "link
especial", el teléfono, "cotiza sin origen"). Los 5 de búsqueda, comprobados uno a uno en la base.

| Causa | Casos | Qué es |
|---|---|---|
| **No se reproduce** | 17 | Hoy la misma conversación ya no falla. PRE sirve el mismo código que el examen (después solo hay documentos): es **variación**. Casi un cuarto de los 73 fallos son de azar → **en CAL hay que medir con varias repeticiones por caso**. |
| **Redacción** | 14 | El dato estaba en el contexto y la respuesta no lo dice: política de fotos, formulario médico tras reservar, el minicurso no certifica, comprar comida en el hotel, recogida en el hotel de Isla Grande, el cierre de las 4:30, descuentos vigentes, el precio en COP a un colombiano que lo pidió (4). |
| **Entendimiento** | 9 | Repregunta, supone o no pide: "cotiza sin origen", "asume que los dos son residentes", "repregunta la actividad"… |
| **Búsqueda** | 5 | El dato ESTÁ en la base y no llegó al contexto: confirmación al pagar por el enlace (FAQ), profundidad según el nivel (FAQ), la carta de referido (ficha del Curso Referido), refresher tras más de 2 años (FAQ), un tour con refresher y buceo juntos (FAQ). |
| **Regla** | 5 | Moneda: 4 criterios del golden de ANTES de la decisión de Gadea del 15-oct (pedían preguntar la nacionalidad; hoy, sin nacionalidad → USD): **hay que actualizarlos**. Y el teléfono. |
| Escalado | 1 | "link especial" → no ofrece el asesor. |
| No se pudo reproducir | 1 | cal-31 (repetir). |

## Resultado: los 73, por causa y por tarea

| Causa final | Casos |
|---|---|
| Entendimiento del flujo (repregunta, supone, no pide, menú que no toca) | 22 |
| No se reproduce (variación) | 17 |
| Redacción del RAG (el dato estaba) | 14 |
| Regla de negocio sin aplicar o criterio desfasado (moneda, teléfono, idioma) | 9 |
| Búsqueda (el dato está en la base y no llegó) | 5 |
| Escalado por error | 3 |
| Omite información sin cita / sin RAG | 2 |
| No se pudo reproducir | 1 |

| Tarea de CAL | Casos | Lo principal |
|---|---|---|
| **CAL-C** entender sin repreguntar ni suponer | 21 | el menú de actividades cuando no toca (6), cotizar sin origen, suponer residentes, no pedir personas |
| **CAL-A** el RAG contesta todo | 18 | 14 de redacción y 5 de búsqueda (los 5 datos están en la base) |
| **CAL-B** moneda | 10 | aplicar la regla de Gadea en un sitio y **actualizar 4 criterios del golden** que piden preguntar la nacionalidad |
| **CAL-E** sueltos | 6 | teléfono → persona, portugués → inglés, "el 10 % no aparece" no es un enlace roto, "link especial" → asesor |
| (variación) | 17 | medir con repeticiones |

**Conclusiones para el orden de CAL:**
1. **Lo que más pesa es el entendimiento (CAL-C, 21) y la redacción del RAG (CAL-A, 14)**; la búsqueda pesa poco (5):
   los datos llegan casi siempre, lo que falla es que la respuesta no los use todos.
2. **CAL-B empieza por los criterios**: 4 de los "fallos de moneda" son criterios del golden escritos antes de la
   decisión del 15-oct. Sin actualizarlos, el bot "falla" haciendo lo que decidió Gadea.
3. **Casi 1 de cada 4 fallos es variación**: las medidas de CAL deben repetir cada caso (≥ 3 veces) o el ruido tapa
   la mejora.

Banco: `banco-fallos.json` (73 casos con `causa_final`, `tarea` y `nota`; los del RAG con `diagnostico`: respuesta de
hoy, ¿se reproduce?, el dato y si estaba en el contexto). Coste del diagnóstico ≈ 1,5 $.

## Cruce con la investigación de Gadea (mismo día, `docs/robustness/investigacion/diagnostico-73-fallos.md`)

Los dos estudios se hicieron a la vez sin saberlo y miden lo mismo con método distinto: el de Gadea repite **2 veces**
los 45 turnos del RAG y mira solo si el dato estaba en el contexto; este repite **1 vez**, clasifica los 73 (también
los 17 que no son del RAG, leídos a mano) y corrige a mano lo que el verificador confundía.

| | Gadea (2 repeticiones) | Este (1 repetición + revisión) |
|---|---|---|
| Fallos en turnos del RAG | 56 de 73 (77 %) | 56 de 73 |
| El dato estaba en el contexto | 50 de 56 (89 %) | 14 redacción + 9 entendimiento + 5 regla + 17 que hoy no fallan |
| Búsqueda (el dato no llegó) | 3 | 5 (comprobados en la base: los 5 datos están) |
| Azar / no se reproduce | 18 | 17 |

**Coinciden en lo importante:**
1. **La búsqueda pesa poco (3-5 de 56).** El dato llega casi siempre; lo que falla es que el modelo no lo usa todo.
2. **El azar es grande (17-18).** Medir con repeticiones.

**Lo que añade cada uno:**
- **Gadea:** los mecanismos (contesta lo literal y no aplica las reglas transversales; no usa el historial; no conecta
  implicaciones; se queda corto) y las causas de diseño (una sola llamada con 50 reglas; el revisor castiga inventar y
  nunca omitir; reglas deterministas escritas como prosa; nadie hace la lista de qué contestar; temperatura 0,3). Su
  propuesta para CAL: **responder en dos pasos** (plan → redacción), **el revisor comprueba completitud**, **lo
  determinista en código** (precio, moneda, origen) y temperatura 0.
- **Este:** (1) **4 criterios de moneda del golden son de antes de la decisión del 15-oct** (piden preguntar la
  nacionalidad cuando la regla ya es "sin nacionalidad → USD"): Gadea los cuenta como redacción; son criterios a
  actualizar. (2) **De los 17 que no son del RAG, 6 son el menú de actividades que sale cuando no toca** ("5
  inmersiones", "no estamos certificados", "Muchas gracias!" sabiendo ya que quiere bucear): es del flujo, no del RAG, y
  la propuesta de los dos pasos no lo arregla. (3) Un banco reproducible caso a caso (`scripts/banco_fallos.py
  diagnosticar --ids …`) para medir cada arreglo de CAL contra los mismos 73.

**Orden que sale de los dos:** CAL-B (moneda en código + actualizar los 4 criterios) → CAL-A con el diseño de Gadea
(plan → redacción, completitud en el revisor) → CAL-C (el menú de actividades y las clases de frase) → CAL-E →
CAL-F, midiendo cada paso con ≥ 3 repeticiones sobre el banco.

# CAL-B — moneda (15-oct noche, Gonzalo) — EN CURSO

**Causa encontrada:** la regla de moneda del catálogo que lee el RAG decía *"Si no sabes la nacionalidad del cliente,
da las dos monedas"*, lo contrario de la decisión de Gadea del 15-oct (sin nacionalidad → USD), y el resumen del estado
no decía nada cuando no se sabe la nacionalidad: el modelo tenía que deducir la moneda solo.

**Arreglo** (flag `MONEDA_SIN_NACIONALIDAD_USD`, **APAGADO**): la regla del catálogo pasa a "da el precio en USD (si te
dice que es colombiano o residente, en COP)" (`catalog.MONEDA_SIN_NACIONALIDAD`; la caché del catálogo distingue el
flag) y el resumen del estado lleva la moneda ya resuelta ("Aún no sabemos la nacionalidad: si das un precio, en USD").
El grupo mixto ya quedaba como "no colombiano" → USD. Tests: `tests/test_calb_moneda.py` (8).

**Medida en el banco de fallos** (`banco_fallos medir --tarea CAL-B --reps 3`, nuevo: repeticiones, flags y código
local; el verificador usa el criterio corregido si lo hay):

| | Repeticiones que fallan (8 casos × 3) |
|---|---|
| A (PRE hoy) | **12/24** |
| B (código local + flag) | **7/24** |

Mejora en `refresher-rechaza-acepta` (2 → 0), `paquete-5-buceos-precio-overnight` (1 → 0) y
`colombianos-precio-minicurso` (3 → 1); ninguno empeora. **6 de los 7 que quedan no son de moneda**: en
`open-water-precio-para-colombianos` y `curso-open-water-precio-cop` la cliente colombiana pide el precio en COP pero
nunca dice desde dónde sale, y la puerta del origen (opción C) pregunta el origen: **choque entre dos decisiones**, para
Gadea.

**Criterios:** `criterios-moneda-propuestos.md` — 6 criterios del golden piden preguntar la nacionalidad antes de
cotizar (de antes de la decisión del 15-oct) y 2 chocan con la regla del origen. **Propuesta para Gadea, sin tocar el
golden**; el banco ya mide con la versión nueva (`pedia_corregido`).

**Mini-ronda `calb-A` (24 diálogos visibles con moneda): NO VALE** — a mitad se acabó el crédito de OpenAI (715 errores
"no credits remaining" en PRE; PRE no contestaba). Sus ficheros no se suben. **Siguiente:** recargar OpenAI, repetir
`calb-A` (flag apagado, como PRE) y `calb-B` (flag encendido) con `docs/robustness/cal/dialogos-calb.txt`, comparar y
decidir. Gadea: los criterios propuestos.
