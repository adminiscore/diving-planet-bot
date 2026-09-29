# Análisis del RAG (29-sep-2026)

Pedido por Gadea antes de seguir con el bloque "RAG, calidad y latencia": el RAG es hoy el mayor lastre en calidad
(60 de los 113 fallos del paso 8) y en segundos (turnos con RAG p50 ~4-4,6 s, p95 ~8 s). Pregunta: ¿por qué tiene
tantas lagunas? ¿Es la estructura, el modelo o cómo está montado?

**Respuesta corta: es la estructura y los datos, no el modelo.** Tenemos un RAG genérico ("busca trozos de texto y
que el LLM redacte") aplicado a un dominio pequeño, cerrado y muy estructurado (36 servicios con precio, duración,
qué incluye, pernocta), y le hemos ido poniendo parches encima (reglas en el prompt, atajos, juez, catálogo). Cada
parche arregla un síntoma y añade contexto, contradicciones y segundos.

---

## 1. Cómo está montado hoy

Un turno con pregunta (u3-4: en paralelo con la extracción de datos):

| Paso | Qué hace | Modelo | Tiempo |
|---|---|---|---|
| Reescritura | `condense_query` si el mensaje es corto y hay historial | gpt-4o-mini | ~0,5 s (a veces) |
| Búsqueda | vector (pgvector, `text-embedding-3-small`) + palabras (Postgres) → fusión RRF + "temas" por regex → 8 fragmentos; a veces 2 búsquedas (pregunta sola y con historial) | embeddings | ~0,4 s |
| Expansión | trae el fragmento "padre" si el hijo lo tiene | — | — |
| Respuesta | prompt de sistema (~3.300 tokens de reglas + ~3.200 de catálogo y links) + hasta 24 mensajes de historial + 8 fragmentos + resumen del estado (~7.000-8.000 tokens) | gpt-4.1-mini, temp 0,3, máx. 500 | ~1,9 s (crece con la longitud: 220 car. 1,1 s, 720 car. 2,8 s) |
| Guardas | importes, URLs, teléfono, datos personales, capacidad… (deterministas) | — | ~0 |
| Juez | enumera y marca cada dato del negocio frente a TODO el contexto | gpt-4.1 | ~1,2 s |
| Regeneración | si el juez o una guarda rechaza: otra respuesta (con la lista de lo rechazado, `RAG_REGEN_FEEDBACK`) y otro juicio | gpt-4.1-mini + gpt-4.1 | +~3 s en ~10-15 % de los turnos |
| Fallback | "ese detalle no lo tengo a la mano" si fallan las dos | — | — |

**Suelo de latencia de esta forma de montarlo: ~4 s** (reescritura + búsqueda + respuesta + juez en serie), ~7 s con
una regeneración. El caché del prompt (l2-2) funciona pero no baja el tiempo: lo domina la generación.

## 2. Qué dicen los datos

- **Fallos del RAG en el paso 8 (60 de 113):** inventa o contradice 25 · respuesta incompleta 22 · "no lo tengo"
  teniendo el dato 11 · cotiza sin origen/nacionalidad 7 (`fallos-por-causa-2026-09-28-paso8.json`).
- **Base de conocimiento: 718 fragmentos (359 por idioma), ~40.000 tokens por idioma.** Servicios 176 fragmentos
  (36 servicios × 5 trozos: resumen, precio, qué incluye, requisitos, itinerario), FAQs 135, políticas 34, precios 14.
- **El mismo dato vive en 3-4 sitios con formatos distintos.** Ej.: el paquete de 5 buceos está en su fragmento de
  precio ("392 USD"), en una FAQ ("U$392", "$1,429,000 COP"), en el documento de precios y en el catálogo del prompt
  ("1.429.000 COP"). Casi todos los servicios existen DOS veces (desde Cartagena / ya en las islas) con textos casi
  iguales.
- **La base arrastra el tono y los datos de los chats antiguos:** 25 fragmentos (ES) con el teléfono o WhatsApp,
  15 FAQs con "escríbenos" o "te paso con un asesor". El prompt dice "NUNCA des el teléfono" y una guarda lo
  rechaza → regeneración o "no lo tengo" que nacen de la propia base.
- **Contradicciones base ↔ catálogo ↔ prompt:** "Paquete de 3 inmersiones (1 día)" que obliga a dormir; el Curso
  Referido con pernocta opcional; el prompt con "el pago lo cierra el equipo" y a la vez "manda al link".
- **La búsqueda no sabe nada del cliente:** recibe el texto y el idioma; no usa la actividad, el origen ni el servicio
  que ya conocemos. Resultado típico: fragmentos del servicio hermano (islas en vez de Cartagena), o 8 trozos de 8
  servicios distintos cuando la pregunta es sobre el plan que el cliente ya eligió.
- **Prompt de reglas: 42 viñetas, 30 prohibiciones ("NUNCA", "NO").** Cada una salió de un fallo real; juntas diluyen
  la atención, se contradicen a ratos y alargan cada llamada.
- **No medimos por piezas.** `eval_retrieval.py` / `eval_rag_answers.py` no se usan desde julio: solo vemos el
  resultado final con el juez del golden (ruido ±2 diálogos). No sabemos qué parte de los fallos es de búsqueda
  (no trae el dato) y cuál de redacción (lo tiene y lo cambia).

## 3. Qué tiene un RAG sólido para un dominio así (y nosotros no)

| Práctica | Qué es | Nosotros |
|---|---|---|
| **Una sola fuente de verdad, curada** | cada dato en un sitio, sin duplicados ni contradicciones; texto neutro escrito para el bot | ❌ 3-4 copias por dato, tono de chats antiguos, teléfono en la base |
| **Fragmentos autocontenidos** | una ficha por producto con todo lo que se pregunta de él | ❌ 5 trozos por servicio × 2 orígenes |
| **Lo estructurado, sin búsqueda difusa** | precios, duración, qué incluye: de la tabla, por el servicio en juego (búsqueda por clave o herramienta) | 🟡 el catálogo va entero al prompt (paso 5), pero convive con los trozos → duplicado |
| **Búsqueda que usa el contexto** | filtros por lo que ya se sabe (servicio, origen, idioma) + reordenador (reranker) | ❌ solo texto e idioma; "temas" por regex; sin reranker |
| **Prompt corto y jerárquico** | pocas reglas priorizadas (seguridad y dinero primero), estilo aparte | ❌ 42 reglas, parches acumulados |
| **Verificación proporcional** | lo numérico, determinista; el juez LLM solo para lo que no se puede comprobar así, y con poco contexto | 🟡 guardas deterministas bien; juez sobre ~7.000 tokens → necesita gpt-4.1 y 1,2 s |
| **Medir por piezas** | recall de la búsqueda (¿trae los datos necesarios?), fidelidad de la respuesta, relevancia | ❌ solo de punta a punta |

## 4. Por qué tiene tantas lagunas

1. **Tres pasos probabilísticos en serie para datos que son deterministas.** Un precio pasa por buscar (puede no
   traer el trozo o traer el del hermano) → redactar (puede mezclar o resumir mal) → juzgar (puede rechazar lo
   correcto si el contexto es largo y contradictorio). Los errores se multiplican, y el juez convierte muchos en
   "no lo tengo" (seguro, pero no contesta) y en segundos.
2. **Contexto largo, repetido y contradictorio.** ~8.000 tokens con el mismo dato en varios formatos y algunas
   contradicciones: al modelo le cuesta más no mezclar, y al juez más no equivocarse (por eso los modelos pequeños
   fallan como juez: 48/70 y 37/70 frente a 70/70 de gpt-4.1).
3. **La base no está escrita para un bot.** Arrastra el tono y los datos de los agentes humanos (teléfono,
   "escríbenos", "te paso") y los huecos de lo que nunca se escribió (punto de encuentro en inglés, descuento de
   grupo, cómo pagar): donde no hay dato, el modelo rellena y el juez corta.
4. **Cada fallo se arregló con un parche local** (una regla más, un atajo, una guarda): funciona para el síntoma y
   empeora el conjunto (más prompt, más contradicciones, más tiempo).

**¿Es el modelo?** No principalmente: gpt-4.1-mini redacta bien cuando el contexto trae el dato limpio (los casos de
precio en COP pasan en cuanto el catálogo está en el contexto), y gpt-4.1 verifica 70/70 en el banco. Cambiar de
modelo sin cambiar el montaje movería poco.

## 5. Propuestas (orden recomendado) y medida

| # | Propuesta | Qué ataca | Riesgo | Cómo se mide |
|---|---|---|---|---|
| **A** | **Base curada como fuente única:** una ficha por servicio y origen, autocontenida, generada desde `services.json` (sustituye los 5 trozos); FAQs neutras, sin teléfono ni "escríbenos", sin repetir precios; contradicciones resueltas; paridad ES/EN | inventa/contradice, "no lo tengo", tokens | bajo (datos) | recall de búsqueda (E) + ronda core |
| **B** | **Búsqueda que usa el estado:** con servicio u origen conocidos, su ficha va SIEMPRE al contexto y la búsqueda filtra/prioriza por ellos | hermanos cruzados, incompletas | bajo | E + casos del mapa |
| **C** | **Catálogo por servicio en juego** en vez del catálogo entero: con A+B, el prompt baja de ~3.200 tokens de catálogo a la ficha que toca | tokens → segundos | medio | latencia + core |
| **D** | **Dieta del prompt:** de 42 reglas a ~10-12 priorizadas; fuera las que ya cubren guardas o catálogo y las que contradicen la base | atención, contradicciones, tokens | medio | banco del juez + core |
| **E** | **Medir por piezas:** set de preguntas visibles (sin examen oculto) con los datos que la respuesta necesita; recall@8 de la búsqueda + fidelidad; reutiliza `eval_retrieval.py` y `sonda_rag_turnos_pre.py` | saber qué arreglar | ninguno | — (es el instrumento) |
| **F** | **Latencia estructural:** con contexto de ~3.000-4.000 tokens, respuesta y juez más rápidos; reescritura en paralelo con la búsqueda de la pregunta sola; juez solo si la respuesta trae datos del negocio que no salen del catálogo | segundos | medio | `turn_metrics` |
| G | *Experimento, después de A:* la base curada ENTERA en el prompt (caché) en vez de búsqueda (dominio pequeño: ~15-20.000 tokens curada) | "no lo tengo" por búsqueda | a medir | banco + core |

**Estimación honesta:** A+B+D atacan la raíz de la mayoría de los 60 fallos del RAG (inventa/incompleta/no sabe
dependen casi siempre de qué contexto llega); C+F son los que pueden bajar de ~4 s a ~2,5-3 s. No hay número fiable
hasta tener E.

## 6. Tareas pendientes de Plan Coral relacionadas

| Tarea | Estado real | Propuesta |
|---|---|---|
| l2-1 · juez y reescritura en modelo pequeño | medido por Álvaro el 28-sep (0.29.66): descartado para el juez | cerrar (la reescritura, dentro de F) |
| s4-17 · "¿cuánto tiempo dura?" → lista de precios | resuelto por `RAG_V2` (sin atajos de precio); pasa en las rondas desde el paso 5 | cerrar |
| l2-2 (2.ª mitad) · caché semántica de FAQs | no ataca la latencia real (generación) | aparcar; G la sustituye |
| `RAG_CONCISE` (0.29.67) | aparcado: con tope inventa huecos | subsumido por A/C/D (respuestas cortas con contexto limpio) |
| Falso rechazo del COP del paquete de 5 · huecos en inglés (punto de encuentro, cómo pagar) · descuento de grupo | handoff de Álvaro | síntomas de A/B/C: se arreglan por la raíz |
| s4-10 (nacido en Colombia), s4-12 (paquetes sin saber la salida), s4-19 (DIVE TO HEAL pegado), s4-13 (bucle del origen) | pendientes | mixtas flujo/RAG: revisar tras A-D |

## 7. Recomendación

Antes de otro parche: **E (instrumento) → A (base curada) → B (búsqueda con estado) → D (prompt) → C/F (latencia)**,
cada uno con su medida. A y B son cambios de datos y de montaje de bajo riesgo y alto impacto; D y C tocan cómo
redacta el bot y necesitan su ronda. El experimento G solo tiene sentido con la base ya curada.
