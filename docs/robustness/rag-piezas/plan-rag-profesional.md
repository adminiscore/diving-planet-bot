# Plan · RAG profesional (3-nov)

Para Gadea, Gonzalo y Álvaro. Origen: Álvaro trajo una lista de buenas prácticas de RAG (un vídeo). La revisión está en
Coral #2686, y las cifras de R0 en `2026-11-03-r0-informe.md`. Regla de CALN: cada pieza dice qué quita y se mide
frente a la base a la misma hora.

## La lista frente a nuestro RAG (0.40)

| # | Práctica | ¿La tenemos? | Prueba | Qué metemos | Cuándo |
|---|---|---|---|---|---|
| 0 | Los RAG fallan sobre todo por la búsqueda | 🟡 Era así en septiembre (~la mitad de los fallos); en ex-10, ~7 % | `rag-piezas` 28-sep; ex-10 15-oct | Medir la búsqueda sola, por pieza | ✅ R0, 3-nov |
| 1 | Búsqueda híbrida (significado + palabras exactas) | 🟡 Hay RRF, pero la rama de palabras casi no encuentra (48 de 51 sin resultado, 18-oct): `'simple'`, sin raíces ni tildes, exige todas las palabras. **Fallo:** busca solo la última línea, que en español con el origen sabido es `[origen_cliente]=…` | `src/knowledge/vector_store.py:237`, `src/agents/rag_agent.py:851-864` | Pregunta sin marca; `unaccent` + raíces por idioma; «alguna palabra»; fusión por posiciones (RRF puro) | ⏭️ R1 |
| 2 | Re-ranker | ❌ Solo `penalizar_otro_origen`. La puerta de 0,40 es todo o nada | `vector_store.py:199-216`, `rag_agent.py:387-415, 1102-1113` | Top-30 → re-ranker → top-8; su nota en vez de la puerta | 🔜 R2, después de CALN |
| 3 | Trozos con contexto | 🟡 Las fichas, sí (título, origen, sección); las FAQ y las políticas, solo «Pregunta / Respuesta» | `catalog.py:289-309`, `scripts/kb_v2.py:129-165` | Categoría y nombre de la política en el texto; una frase de contexto por documento, generada al construir la base y guardada por hash | 🔜 R3, después de CALN |
| 4 | Trozos que no se rompen | ✅ Una pieza = un documento (≤ ~3.000 caracteres). Pero una ficha es UN vector de ~2.300 caracteres y 9 bloques | `kb_v2.py:144-166` | Fichas por sección («small-to-big»: se busca la sección y se da la ficha entera); dejar de copiar las políticas en las fichas (el seguro está en 40) | 🔜 R3, después de CALN |

## R0 · Medido (58314005)

PRE 0.40, `rag_piezas --solo-busqueda --techo`, 107 casos, céntimos:
- **Top-8:** 87 % (51 de siempre), 83 % (gen1), 67 % (gen2), 96 % (30 nuevos).
- **Techo** en los 48 candidatos: 96-100 %.
- **22 datos rescatables por un re-ranker**, 10 de ellos en los puestos 9-12.
- **La puerta de 0,40** deja pasar documentos en 6 de 10 preguntas sin respuesta, y ningún umbral del vector las separa.
- **«December 25th»** no trae `closed_days` ni entre los 48: es de palabras exactas.
- **Las rondas** llevan ya la búsqueda en `[TURN_METRICS]` (`rag_docs`).

## Orden y dueños

1. **R1** (Álvaro), después de los barrios y con el visto bueno de Gadea. Toca `vector_store`, `rag_agent` y el DDL de
   `kb_v2`:
   - la rama de palabras con la pregunta;
   - `to_tsvector`/`websearch_to_tsquery` con `unaccent` y la configuración del idioma del documento (`spanish` /
     `english`), y «alguna palabra» (`OR`);
   - la fusión por posiciones, sin `max(coseno, palabras normalizadas)`, para que un acierto suelto de palabras no tape
     al vector (el «cualquier palabra» del 18-oct bajó de 86 a 65 % por eso);
   - fuera lo muerto: `_expand_with_parent_context` y `parent_id`, salvo que R3 lo reuse, y `metadata.topics`.

   Se mide en un esquema aparte (`kb_v2_r1`, `RAG_KB_ESQUEMA`, como hizo Gadea con `kb_v2_gadea`) con los cuatro juegos
   y `--comparar`, a la misma hora, y luego la mini de los visibles afectados (juez solo en ellos, con caché).
   **Quita:** la rama de palabras muerta (o la mata del todo, si no gana) y el código del padre.
2. **R2** (Álvaro), después de CALN y si R1 deja margen: probar un re-ranker dedicado (Cohere o Jina; cuenta y clave de
   Álvaro) frente a Haiku por OpenRouter en los 107 casos. Se miden la recuperación, el MRR, la latencia p95 y el coste.
   **Quita:** la puerta de 0,40 y los documentos flojos (menos tokens al escritor).
3. **R3** (Álvaro, con Gadea por la base): contexto en las FAQ y las políticas, fichas por sección y re-embeber por hash.
   **Quita:** las políticas copiadas en las fichas y pagar las 414 incrustaciones en cada despliegue.

## Normas

- Una medida a la vez en PRE (`mi_estado`), y nada de sondas directas a Haiku mientras alguien mide.
- El juez, solo en lo afectado y con caché.
- Nunca el examen oculto ni los contaminados.
- Frases nuestras en los juegos.
