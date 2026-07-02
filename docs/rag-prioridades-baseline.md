# Prioridades RAG y baseline de evaluación

Este documento ordena los siguientes trabajos recomendados sobre el pipeline RAG y define la baseline inicial para medir el estado real del sistema antes de tocar pesos, thresholds o heurísticas.

## Prioridades en orden recomendado

### 1. Afinar retrieval y rerank para que gane la fuente correcta

Objetivo:
- Conseguir que `services.json` gane más veces cuando la intención del usuario es detalle de servicio, precio, requisitos o itinerario.

Trabajo:
- Revisar pesos de `source`.
- Revisar pesos de `topic`.
- Revisar pesos de `subtype`.
- Curar la KB donde `services` debería ser claramente la fuente principal.

Señal de que sigue pendiente:
- En algunas queries el top doc sigue viniendo de `conversations` o `faqs` antes que de `services`.

### 2. Extender la heurística de queries ambiguas ultra-cortas

Objetivo:
- Ampliar el catálogo de aliases/nombres cortos como `Pao Pao`, `Cocoliso`, `San Pedro de Majagua`, etc.

Trabajo:
- Revisar logs y conversaciones reales.
- Añadir aliases y variantes abreviadas.
- Cubrir nuevos hoteles o lugares que aparezcan en producción.

### 3. Recalibrar `rag_min_bm25_rank` con tráfico real

Objetivo:
- Ajustar el umbral BM25 para separar mejor coincidencias léxicas fuertes de ruido.

Trabajo:
- Revisar consultas reales.
- Identificar falsos positivos y falsos negativos.
- Ajustar el threshold con evidencia y no a ojo.

### 4. Evaluar bypass del grounding check cuando la confianza sea muy alta

Objetivo:
- Reducir latencia en casos de retrieval muy fuerte sin comprometer seguridad.

Trabajo:
- Definir qué significa “alta confianza”.
- Probar primero con logging o modo sombra.
- Mantener siempre los guards deterministas de importes y URLs.

### 5. Replicar validación operativa en otros entornos

Objetivo:
- Confirmar que staging y producción, si aplican, tengan migración FTS, índice GIN y reindex actualizado.

Trabajo:
- Verificar `content_tsv`.
- Verificar `kb_documents_content_tsv_idx`.
- Verificar conteos por `source` y presencia de `subtype` y `parent_id`.

### 6. Crear baseline de evaluación y regresión RAG

Objetivo:
- Tener una batería estable de queries para comparar el comportamiento del sistema antes y después de cada ajuste.

Por qué es la prioridad inmediata:
- Sin baseline, cualquier ajuste de retrieval o prompts se valida “a ojo”.
- La baseline permite medir si un cambio mejora una categoría pero empeora otra.

Entregables de esta fase:
- Un set de queries agrupadas por categoría.
- Un script reproducible que ejecute `rag_answer` y capture la respuesta real.
- Un snapshot inicial del estado actual para comparar futuras iteraciones.

Categorías mínimas a cubrir:
- Punto de encuentro y horarios.
- Qué incluye / qué llevar.
- Precios en USD y COP.
- Booking / pagos / formularios.
- Weather / cancelaciones / cambios.
- Certificación / refresher / profundidad.
- Alojamiento / islas / recogida.
- Queries ambiguas ultra-cortas.
- Follow-ups multi-turno.
- Temas operativos varios como fotos, videos, Barú y servicio privado.

Criterios de revisión por query:
- Si responde o hace fallback.
- Si aclara cuando debe aclarar.
- Si la respuesta es útil y concreta.
- Si evita inventar precios, links o disponibilidad.
- Si la fuente dominante parece razonable para la intención.

Herramientas del repo útiles para esta fase:
- `scripts/eval_retrieval.py` para ver top docs del retrieval.
- `scripts/eval_rag_answers.py` para snapshot de respuesta final del RAG.

### 7. Backlog post-demo / no urgente

- Observabilidad.
- Evals automáticos más amplios.
- Semantic cache.
- Local reranker.
- Model cascading.
- Feedback loop.
- Persistencia de estado fuera de memoria.

## Estado local validado antes de empezar esta baseline

Verificado en local el 2026-06-14:
- Migración FTS aplicada.
- Índice GIN presente.
- Reindex local ejecutado con `.env.dev`.
- `kb_documents` alineado con el repo actual.
- Conteo total validado: `737` documentos.

## Siguiente paso recomendado

1. Ejecutar la baseline inicial de respuestas RAG.
2. Revisar resultados por categoría.
3. Detectar los primeros 5-10 fallos o comportamientos mejorables.
4. Priorizar cambios pequeños y medibles a partir de esa evidencia.

## Primera baseline ejecutada (2026-06-14)

Script usado:
- `python -m scripts.eval_rag_answers --lang all --output-json docs/project-history/rag-baseline-2026-06-14.json`

Snapshot generado:
- `docs/project-history/rag-baseline-2026-06-14.json`

Resumen global:
- Total de casos: `39`
- Respuestas normales: `33`
- Fallbacks: `2`
- Clarificaciones: `4`
- Casos que cumplieron la expectativa de modo: `38/39`

Resumen por categoría:
- `meeting_point_schedule`: 4/4 correctos
- `food`: 3/3 correctos
- `pricing`: 3/4 correctos
- `pricing_included`: 1/1 correcto
- `booking_payment`: 2/2 aceptables
- `forms`: 2/2 aceptables
- `weather_policy`: 2/2 aceptables
- `certification`: 3/3 correctos
- `courses_location`: 1/1 correcto
- `followup_rewrite`: 2/2 correctos en modo
- `accommodation`: 3/3 correctos en modo
- `islands_pickup`: 2/2 correctos en modo
- `ambiguous_location`: 4/4 correctos
- `misc_ops`: 4/4 correctos en modo

Única desviación clara detectada por la baseline actual:
- `en_price_2_dives`: se esperaba respuesta y devolvió fallback. El log mostró rechazo por importe no grounded, así que este caso apunta a revisar el camino EN de pricing + grounding.

Casos que conviene revisar manualmente aunque hayan pasado en modo:
- `en_followup_islands`: responde, pero deriva a varias opciones y no se mantiene tan centrado en Open Water como debería.
- `es_price_local_cop`: responde con una lista amplia de precios; puede ser correcta, pero quizá demasiado genérica para una pregunta abierta.
- `es_hotel_pickup_pao_pao`: responde de forma útil, pero conviene revisar si el tono/certeza se alinea con la regla real de acceso marítimo y ausencia de matriz hotel→sí/no totalmente explícita.

Siguiente uso recomendado de esta baseline:
- Repetir exactamente el mismo script tras cada ajuste de retrieval, rerank, thresholds o prompt.
- Comparar especialmente `pricing`, `followup_rewrite`, `islands_pickup` y `ambiguous_location`.

## Estado actualizado tras fixes de grounding y rerun completo (2026-06-14)

Snapshot nuevo:
- `docs/project-history/rag-baseline-2026-06-14-all-after-grounding-fixes.json`

Resultado global actualizado:
- `39/39` casos coinciden ahora con el modo esperado.
- `34` respuestas, `1` fallback y `4` clarificaciones.
- El caso `en_price_2_dives` quedó corregido: pasó de `fallback` a `answer` tras ajustar la equivalencia `178` / `178.0` / `178.00` y añadir un retry conservador al grounding LLM.

Pendientes recomendados para continuar mañana, en orden:

1. `en_followup_islands`
   - Por qué va primero: ya responde en modo correcto, pero sigue siendo el mejor candidato de calidad. El follow-up venía de Open Water y la respuesta todavía se abre demasiado al catálogo general en vez de mantenerse centrada en el caso “si ya estoy en las islas” para ese flujo concreto.

2. `es_price_local_cop`
   - Por qué va segundo: no falla en seguridad ni en modo, pero la respuesta actual es demasiado amplia/genérica para una pregunta abierta de precio local en COP. Aquí el trabajo es más de UX/foco que de grounding.

3. `es_hotel_pickup_pao_pao`
   - Por qué va tercero: la respuesta es útil, pero conviene suavizar o afinar el grado de certeza para alinearlo mejor con la regla real de “muelle / acceso marítimo” y con la falta de una matriz hotel→sí/no completamente explícita en KB.

4. `es_payment_transfer_qr`
   - Por qué queda después: sigue en fallback, pero el caso está dentro de lo aceptable (`answer_or_fallback`) y apunta más a ausencia de confirmación de negocio/KB que a un bug técnico claro del pipeline.

Recomendación de continuación:
- Empezar por `en_followup_islands`.
- Mantener `es_price_local_cop` y `es_hotel_pickup_pao_pao` como siguiente tanda de refinamiento de calidad.
- Repetir la baseline completa `all` después de cada cambio que toque prompt, rewriter o grounding.

## Baseline 2026-07-01 (post merge feature/pruebaGon + fix retrieval EN)

### Cambios aplicados antes de esta baseline

1. **Merge feature/pruebaGon → feature/dev_gadea**: cambios de negocio v0.18.0 (tono costeño, descuento colombiano eliminado, cancelación/reprogramación).
2. **KB reindexada**: 753 documentos (faqs: 234, services: 350, policies: 44, pricing: 18, conversations: 107). Sirve los cambios de `brand_tone.json`, `discounts.json`, `policies.json`, `faqs.json`.
3. **Fix de retrieval EN** (`scripts/load_embeddings.py`): los chunks de pricing ahora llevan el `service_id` como prefijo (`[2_dives_1_day] Pricing for ...`). El `service_id` con guiones bajos se tokeniza como palabras separadas en el índice BM25 (`simple` dictionary), dando ventaja léxica al chunk correcto cuando la query menciona el número de inmersiones exacto. `2_dives_1_day:pricing` pasó de posición 4ª a 2ª en EN para "How much is the 2 dives 1 day plan in USD?".

### Resultado

- Snapshot: `docs/project-history/rag-baseline-2026-07-01-final.json`
- **39/39** casos cumplen la expectativa de modo (mejora de 38/39 de junio).
- 35 respuestas, 0 fallbacks, 4 clarificaciones.
- `en_price_2_dives` corregido: dejó de dar fallback gracias al fix de retrieval.
- `es_payment_transfer_qr` también corregido: antes era fallback, ahora responde (mejoró con la nueva KB).

### Pendientes cualitativos (modo correcto pero calidad mejorable)

1. ~~**`en_followup_islands`**~~ ✅ **RESUELTO** — Fix en `query_rewriter._should_condense`: umbral bajado de 2 user messages previos a 1. La query "and if I'm already on the islands?" ahora se condensa a "How does the PADI Open Water course work if I'm already on the islands?" y el retrieval devuelve el FAQ específico de OW en isla.
2. ~~**`es_price_local_cop`**~~ ✅ **RESUELTO (2026-07-02)** — La respuesta ahora incluye `2_dives_1_day` ($630,000 COP) y `minicourse` ($655,000 COP) en los 3 runs de verificación. Baseline 39/39 sin regresiones.
   - **Causa raíz**: el top-8 cutoff excluía `2_dives_1_day:pricing` (rank 9) y `minicourse:pricing` (rank 10). Los 6 paquetes grandes tenían mayor cosine similarity para "pesos colombianos" porque los chunks de 1 día no contenían esos tokens.
   - **Fix aplicado**: se añadió `"En pesos colombianos (COP): $630,000 COP online / $700,000 COP precio normal."` al campo `price_note` de `2_dives_1_day` en `services.json`. Igual para `minicourse` con sus valores. Esto introduce los tokens BM25 `pesos` + `colombianos` exclusivamente en esos dos chunks → RRF los sube a ranks 1 y 2 (scores 0.5637 y 0.5389).
   - **Intentos previos (todos revertidos)**: `top_k=8→10` (inestabilidad del verifier LLM), FAQ comprensivo largo (embedding dilution, rank 21+), enriquecimiento del FAQ de moneda (conflicto de formato periodo vs coma con el verifier).
   - **También corregido**: formato `$727.000` → `$727,000` en `price_note` de minicourse para evitar confusión futura del verifier LLM.
3. **`es_hotel_pickup_pao_pao`**: responde pero sin certeza sobre si el hotel tiene muelle propio. La KB no tiene una matriz hotel→acceso marítimo explícita; pendiente confirmar con el owner.

### Lección sobre el verifier LLM

El verifier LLM (`is_grounded`) tiene no-determinismo inherente incluso a `temperature=0`. Los guards deterministas (`currency_amounts_grounded`, `urls_grounded`) son los que realmente protegen contra precios inventados — el verifier añade una segunda capa para otro tipo de hallucinations pero no debe considerarse 100% estable run a run. Cambios en su prompt deben validarse con al menos 3 runs del baseline para descartar que son solo ruido aleatorio.

## Baseline 2026-07-02 (fix es_price_local_cop via price_note BM25 enrichment)

### Cambios aplicados antes de esta baseline

1. **`services.json` — `price_note` enrichment**: añadido `"En pesos colombianos (COP): $630,000 COP online / $700,000 COP precio normal."` a `2_dives_1_day`. Añadido `"En pesos colombianos (COP): $655,000 COP online / $727,000 COP precio normal."` a `minicourse`. Corregido también formato `$727.000` → `$727,000` en el `price_note` previo de minicourse.
2. **`faqs.json`** — FAQ corto de precios COP para colombianos añadido (para cobertura de consultas directas). FAQ comprensivo de precios COP ya existente: formato corregido de periodo a coma en todos los montos.
3. **KB reindexada**: 757 documentos tras el reindex.
4. `2_dives_1_day:pricing` subió de rank 9 (score 0.5184) a rank 1 (score 0.5637). `minicourse:pricing` subió de rank 10 (score 0.5053) a rank 2 (score 0.5389).

### Resultado

- **39/39** casos cumplen la expectativa de modo.
- 35 respuestas, 0 fallbacks, 4 clarificaciones.
- `es_price_local_cop` corregido: ahora incluye 2_dives ($630,000 COP) y minicurso ($655,000 COP) de forma consistente (3/3 runs verificados).

### Pendientes cualitativos

1. **`es_hotel_pickup_pao_pao`**: responde pero sin certeza sobre si el hotel tiene muelle propio. Pendiente confirmar matriz hotel→acceso marítimo con el owner.
