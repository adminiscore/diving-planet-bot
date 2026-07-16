# Atajos canónicos del RAG: ¿lista de exclusión o lista de permitidos?

Estado: **pendiente de decisión**. No implementado. Ver contexto en `docs/HISTORY.md` (fix de "paquetes multidía" devolviendo precio genérico).

## Qué es un "atajo canónico"

Antes de que el bot busque en la base de conocimiento (RAG real) o llame al LLM, hay 4 funciones en `src/agents/rag_agent.py` que responden con un texto fijo/plantilla cuando detectan, por regex, que la pregunta es de un tipo conocido: comida (`_canonical_food_answer`), resumen de qué se ofrece (`_canonical_diving_overview_answer`), precio genérico (`_canonical_price_overview_answer`) y lugar ambiguo (`_ambiguous_location_clarification`). Se crearon porque, en esos casos concretos, el RAG real daba respuestas malas (aleatorias, evasivas o que no encajaban) — así que se decidió interceptar el patrón con una respuesta fija y correcta.

El caso que motiva este documento es `_canonical_price_overview_answer`: dispara cuando el mensaje "parece" una pregunta de precio genérica (regex amplio: "cuánto cuesta", "precio", "vale"...) **y no** menciona nada específico (regex de exclusión: lista de palabras como "minicurso", "snorkel", "multi-día", etc.). Si el cliente nombra algo específico que no está en esa lista de exclusión, el atajo dispara igual y le da el resumen genérico — que no cubre lo que preguntó.

## Las dos formas de decidir "esto es genérico"

### A) Como está ahora: lista de exclusión ("deny-list")

Dispara si **parece** pregunta de precio Y **no** reconoce nada específico.

```
disparo_amplio = "cuánto cuesta / precio / vale / ..."
exclusion      = "minicurso / snorkel / paquetes / multi-día / X / Y / Z ..."

SI disparo_amplio Y NO exclusion → respuesta genérica
```

**Pros:**
- Cubre más casos con el atajo (más preguntas obtienen la respuesta rápida, sin esperar a retrieval real).
- Ya está en producción, probada, no requiere tocar nada.

**Contras:**
- Cada palabra específica que un cliente pueda usar y que **no** esté en la lista de exclusión hace que el atajo dispare igual, en silencio, dando una respuesta que parece completa pero no lo es.
- La lista de exclusión nunca puede ser exhaustiva — cada regionalismo, sinónimo o error tipográfico nuevo requiere que alguien lo reporte como bug para añadirlo (es lo que pasó con "paquetes" en plural y "multi-día").
- El fallo es "abierto": por defecto se asume que la respuesta genérica está bien, salvo prueba en contra.

### B) Alternativa propuesta: lista de permitidos ("safe-list")

Dispara **solo** si el mensaje coincide con un conjunto corto y confirmado de frases realmente genéricas, sin nada más.

```
frases_permitidas = ["cuánto cuesta", "precios", "qué precios manejan", "tarifas", pocas más]

SI mensaje coincide EXACTAMENTE (o casi) con frases_permitidas → respuesta genérica
SINO → retrieval real (RAG), que entiende mejor la semántica y el contexto
```

**Pros:**
- Cualquier mensaje con contenido adicional (aunque no reconozcamos esa palabra concreta) cae automáticamente a RAG real, que sí generaliza bien ante sinónimos, regionalismos y paráfrasis.
- El fallo es "cerrado": por defecto se asume que hace falta retrieval real, salvo que sea clarísimamente el caso trivial. Elimina de raíz la clase de bug que tuvimos.
- Menos mantenimiento reactivo: no hace falta ir ampliando una lista de exclusión cada vez que aparece una expresión nueva.

**Contras:**
- Algunas preguntas genéricas hoy cubiertas por el atajo (frases que hoy sí reconocemos pero no están en la lista corta de permitidos) pasarían a RAG real — una llamada más lenta y con coste de LLM, aunque el resultado siga siendo correcto.
- Hay que curar bien esa lista corta inicial para no perder cobertura de los casos más frecuentes.

## Ejemplo concreto (recordatorio)

Pregunta: *"¿Cuánto cuesta el buceo de toda la semana?"* (usa "semana" en vez de "días", que sí reconocemos).

- **Con A (actual):** el atajo dispara igual → responde con el resumen genérico de 4 servicios, sin mencionar precios multi-día. El cliente tiene que darse cuenta del error y volver a preguntar.
- **Con B (safe-list):** el mensaje trae contenido adicional ("de toda la semana") que no coincide con la lista corta de frases permitidas → pasa automáticamente a RAG real, que sí entiende "toda la semana" ≈ multi-día y responde bien, sin que el cliente tenga que insistir.

## Recomendación

Migrar a B (safe-list) para `_canonical_price_overview_answer`, manteniendo además la frase de invitación a precisar ("si tu pregunta era sobre algo más concreto...") como red de seguridad adicional para lo que aún se cuele. Esto ya se implementó (ver `docs/HISTORY.md`).

## Próximo paso

Decidir si migrar a B. Si se aprueba, hay que:
1. Curar la lista corta de frases realmente genéricas (revisar logs `[RAG][CANONICAL_SHORTCUT]` para ver qué frases genéricas aparecen más).
2. Reescribir `_canonical_price_overview_answer` para usar esa lista en vez de la exclusión actual.
3. Revisar tests existentes (`test_price_overview_fires_for_bare_price_question` y similares) — probablemente necesiten ajuste porque algunos casos hoy cubiertos por el atajo pasarían a RAG real.
