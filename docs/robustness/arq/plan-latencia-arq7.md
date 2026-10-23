# ARQ-7 · Latencia (23-oct, decisión de Gadea: antes del G10 nº 6)

## Dónde se va el tiempo (G10 nº 5, 225 turnos, [TURN_METRICS])

| Quién contesta | Turnos | Mediana | Peor 10 % |
|---|---|---|---|
| Flujo de la reserva (preguntas de datos) | 51 | 1,4 s | 2,6 s |
| RAG | 63 | 5,9 s | 7,7 s |
| Redactor de hechos | 79 | 5,8 s | 7,8 s |
| RAG con hechos (mensajes mezclados) | 32 | 12,6 s | 18,3 s |
| **Todos** | 225 | **5,3 s** | **11,8 s** |

Causas, vistas en la línea de tiempo de turnos reales:

1. **El redactor escribe dos veces en 53 de 79 turnos.** El primer borrador resume las listas largas (qué incluye,
   requisitos) y la comprobación por código (arq-3) pide rehacerlo: +2,5 s.
2. **En los mezclados el RAG escribe tres veces:**
   - la respuesta adelantada, que se tira porque no lleva los hechos;
   - la que lleva los hechos;
   - el reintento de completitud, que repite el revisor y el aviso final: unos +5 s.
3. **El aviso final va con GPT-6 Luna** (1,4-2 s) mientras el revisor, que va a la vez, tarda 0,5 s: +1 s en cada
   respuesta del RAG.

## Tareas (Plan Coral, fase ARQ)

| Tarea | Qué cambia | Ahorro estimado | Flag |
|---|---|---|---|
| arq-7a | El modelo deja una marca (`[[incluye]]`, `[[requisitos]]`, `[[descuento]]`) y el código pone la lista entera del dato; sin segunda redacción | −2,5 s en 2 de cada 3 turnos del redactor | `listas_por_codigo` |
| arq-7b | En los mezclados, si al RAG le faltan puntos de los hechos, el código los añade en vez de rehacer la respuesta | −5 s en los mezclados que se rehacían | `rag_hechos_sin_reintento` |
| arq-7c | Un modelo rápido para el aviso final (DeepSeek Flash, el del revisor), con banco de avisos | −1 s en las respuestas del RAG | por variable de modelo |

Descartado antes: arq-5b (mezclados por partes). Era 4-6 s más lento y daba la misma calidad.

## Cómo se mide

- **Cada tarea:** banco propio ×3, con calidad (fragmentos e invenciones) y `segundos` por turno. arq-7a usa el banco fijo
  del RAG (`banco-rag.json`, 40 diálogos); ahí se cuentan los turnos del redactor con segunda redacción (`[ARQ3]` en la
  traza).
- **Al final:** el G10 nº 6 mide a la vez la calidad (meta: ≥ 92 % y ≥ 40/72) y la latencia (bajar de 5,3 s de
  mediana y de 11,8 s en el peor 10 %).
