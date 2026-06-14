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
