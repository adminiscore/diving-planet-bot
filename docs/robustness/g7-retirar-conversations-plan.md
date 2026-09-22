# G-7 · Retirar los chats antiguos (`conversations.json`) del RAG — plan con riesgo cero

> Tarea g-7 de la página Plan Coral (Fase G). Plan acordado con Gadea el 2026-09-22: **primero se
> documenta, luego se ejecuta paso a paso**. Principio: *nada se borra hasta haberlo medido y cada paso
> se deshace en segundos*.

## Por qué

`data/knowledge_base/conversations.json` (107 fragmentos de 40 chats de WhatsApp de 2025-26) se usa en
dos sitios:

| Uso | Dónde | Efecto hoy |
|---|---|---|
| **Índice del RAG** | `scripts/load_embeddings.py` los indexa como `source=conversations`; `src/knowledge/vector_store.py::source_weight_for_topics` les da **peso extra** (0,25 en punto de encuentro, 0,20 en pago y disponibilidad, 0,18 en precio colombiano...) | Sirven **datos caducados como vigentes**: "Marina Todo Mar" (un aviso puntual de un chat) como punto de encuentro, hoteles que no están en la KB, precios viejos. En la línea base m0-7, a "¿Dónde es el punto de encuentro?" el **primer** resultado es un chat antiguo, por delante de la FAQ oficial. |
| **Few-shot del RAG** | `src/agents/rag_agent.py::_select_fewshot_examples` / `_format_fewshot_block` | 2 líneas de ≤220 caracteres por respuesta del RAG (escenario + primer mensaje del asesor, a menudo la bienvenida automática). El **tono** sale de `brand_tone.json` y de los prompts, no de aquí. |

Además contiene **22 nombres completos de clientes reales** (anonimización básica) y los chats de su
examen se solapan con los casos reales del golden-set. El minado nuevo (`mine_whatsapp_exports.py`) lo
sustituye con mejor calidad (ver la comparación en g-1).

## Riesgo que hay que descartar

Que algún tema **solo** esté cubierto por un chat antiguo: al quitarlo, el bot pasaría a "no lo tengo"
en ese tema. Todo el plan va de encontrar esos huecos **antes** y taparlos en la **KB oficial**
(faqs / policies), nunca volviendo a meter chats.

## Pasos (cada uno con su puerta y su marcha atrás)

### Paso 0 — Análisis, sin tocar el bot
1. **Inventario de hechos de los chats.** Un script (LLM barato, ~0,3 $) extrae los hechos que afirman los
   107 fragmentos (lado del centro) y los cruza con la KB oficial. Tres grupos:
   - **(a) ya está en la KB** → nada que hacer;
   - **(b) desfasado o incorrecto** (precios viejos, "Todo Mar", descuento colombiano...) → se descarta;
   - **(c) válido y AUSENTE de la KB** → lista para Gadea.
2. **Recuperación A/B en local o en el contenedor de PRE (solo lectura):** `scripts/eval_retrieval.py`
   (20 preguntas ES + 20 EN) y `scripts/eval_rag_answers.py` (39 casos) **con y sin** la fuente
   `conversations` (filtro en la consulta, paso 1). Por pregunta: ¿el top-3 sin chats sigue teniendo un
   documento oficial que responde? Las que no, se suman a la lista (c).
3. **Few-shot:** contar qué ejemplos se eligen de verdad y cuántos son la bienvenida automática.
- **Puerta:** Gadea revisa la lista (c) y decide qué entra en la KB y con qué texto.
- **Marcha atrás:** no aplica (no se ha tocado nada).

### Paso 1 — Interruptores, sin cambiar la conducta
- `settings.rag_exclude_sources` (vacío por defecto) → filtro en las dos consultas SQL de
  `vector_store.py` (`AND NOT (metadata->>'source' = ANY($n))`) y en el reparto de pesos.
- `settings.rag_fewshot_enabled` (`true` por defecto) → `build_system_prompt` no añade el bloque si es
  `false`.
- Tests: con los valores por defecto la conducta es idéntica (mismo prompt, mismas consultas); con la
  fuente excluida no vuelve ningún documento `conversations`; con el few-shot apagado el prompt no lo lleva.
- Deploy a PRE con los valores por defecto + **core** para comprobar que nada cambia.
- **Puerta:** core igual que antes (mismos casos pasan/fallan, salvo ruido del LLM revisado a mano).
- **Marcha atrás:** revertir el commit (no cambia nada de conducta).

### Paso 2 — Tapar los huecos en la KB oficial
- Añadir a `faqs.json` / `policies.json` los hechos (c) aprobados por Gadea; reindexar (aditivo: los
  chats siguen en el índice).
- **Puerta:** tests de KB + `eval_retrieval` sin chats cubre las preguntas que antes dependían de ellos.
- **Marcha atrás:** revertir el commit de KB y reindexar.

### Paso 3 — A/B en PRE el MISMO día
1. Core con los interruptores por defecto (A).
2. En PRE: `RAG_EXCLUDE_SOURCES=conversations` y `RAG_FEWSHOT_ENABLED=false` (variables de entorno,
   reinicio del contenedor, **sin deploy de código**). Core otra vez (B).
3. Juez + revisión humana de las dos rondas; `failure_patterns.py` en las dos.
- **Criterios para aceptar (todos):**
  - ningún caso del core pasa de cumplir a fallar sin explicación revisada;
  - el "no lo tengo" (`rag-no-lo-tengo`) no sube;
  - punto de encuentro, pago y disponibilidad: ninguna respuesta peor;
  - `eval_retrieval` / `eval_rag_answers` ≥ línea base m0-7;
  - latencia no peor (mismo día).
- **Marcha atrás:** quitar las dos variables y reiniciar (segundos).

### Paso 4 — Consolidar (solo si el paso 3 pasa)
- Unos días con los interruptores activos en PRE (y el tráfico manual de m0-4).
- Después, en un solo commit: borrar `conversations.json` (+ `.bak`), dejar de indexarlo
  (`load_embeddings`), quitar su fila de pesos en `vector_store`, el código de few-shot o dejarlo
  alimentado por episodios anonimizados que NO sean examen (si el paso 3 mostró que el tono lo pide),
  scripts `import_whatsapp_conversations.py` / `cleanup_conversations_keep_chunked.py` y los tests que
  dependan. Reindexar. Ronda completa del golden al cerrar la fase.
- **Marcha atrás:** revertir el commit y reindexar.

### Aparte — privacidad (decisión del equipo)
- `feature/agent-arch` (Álvaro) tiene `mined-candidates.json` con >25 nombres reales, subido a GitHub:
  borrarlo de la rama. Su filtro de holdout sobre `conversations.json` queda obsoleto con este plan.
- Si se quiere que los nombres desaparezcan también del historial de git, hay que reescribirlo
  (afecta a todas las ramas): decisión aparte.

## Qué NO se hace
- No se borra nada antes del paso 4.
- No se vuelve a indexar ningún chat para "tapar" un hueco: los datos van a la KB oficial.
- No se toca el tono (`brand_tone.json`, prompts) en esta tarea.
