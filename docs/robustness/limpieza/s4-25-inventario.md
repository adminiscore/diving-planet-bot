# s4-25 · los caminos antiguos de los flags ya encendidos — inventario (18-oct)

Orden decidido por Gadea (18-oct): MOD → **limpieza** (s4-25 Gadea, s4-1 / ex-9 parte 2 / s4-2 Álvaro, en ese orden) →
CAL-G → G9 → Andrés. Cada paso con su suite y una ronda core de **equivalencia** (mismo % y mismas respuestas en lo que
no debería cambiar).

## Qué hay

91 flags `bool = True` en `src/config.py` (sin contar los de ronda). Cada uno deja en el código su camino APAGADO, que
en PRE no corre nunca, y tests que lo fijan apagado. Los que más pesan (usos en `src` · tests que los apagan):

| Flag | usos | tests | Flag | usos | tests |
|---|---|---|---|---|---|
| s4_fixes | 13 | 9 | rag_adelantado | 1 | 8 |
| corrections_v2 | 7 | 3 | notes_in_parallel | 1 | 8 |
| rag_v2 | 6 | 7 | escalado_solo_emergencias | 1 | 8 |
| answer_and_continue | 6 | 7 | aplazar_pregunta_sin_respuesta | 2 | 8 |
| grounding_v3 | 6 | 1 | atajo_resumen_por_rag | 1 | 7 |
| recommend_inferred_minicourse | 5 | 3 | atajo_nacionalidad_por_rag | 1 | 7 |
| rag_plan_elegido | 5 | 0 | contacto_pasa_a_persona | 3 | 6 |
| agent_arch (s4-1, Álvaro) | 4 | 9 | ack_in_parallel | 1 | 5 |
| llm_extraction_cutover_* (4) | 1 c/u | 4 c/u | | | |

OJO: `llm_group_size_veto_cutover`, `llm_group_allocation_veto_cutover` y `llm_activity_veto_cutover` salen con 0 usos
de `settings.X` pero se leen por nombre (`_VetoSpec(cutover_flag="…")` en supervisor.py): no son código muerto. Antes de
borrar un flag, buscar también su nombre entre comillas.

## Regla para borrar

Solo flags promocionados hace al menos una semana (antes del 11-oct) y medidos en una ronda completa (CAL-F, 17-oct,
95,8 %): los de los últimos días se quedan como flag un tiempo para poder revertir. Por flag: quitar la rama apagada,
el campo de config, la línea del compose, su ficha en `componentes.json` y los tests que fijan el camino viejo (buscar
"camino antiguo: el flag sigue existiendo").

## Pasos (propuesta)

1. **RAG (zona Gadea):** rag_v2, grounding_v3, rag_kb_v2, rag_prompt_cache, rag_adelantado, rag_busqueda_doble,
   rag_busqueda_origen, juez_segunda_opinion, rag_regen_feedback, atajo_resumen_por_rag, atajo_nacionalidad_por_rag y
   los catalogo_* antiguos. Ronda de equivalencia.
2. **Flujo (zona Álvaro, avisando):** answer_and_continue, s4_fixes, corrections_v2, recommend_inferred_minicourse,
   ack_in_parallel, notes_in_parallel, llm_extraction_cutover_*, escalado_solo_emergencias, aplazar_pregunta_sin_respuesta.
   Mejor lo hace Álvaro o con él: es su código y va justo antes de su s4-2.
3. Lo que quede, con la fecha de promoción de cada uno a la vista (HISTORY).
