# Plan EX — Entender con IA: el regex deja de decidir (9-oct-2026, Gadea con Claude)

Fase nueva de Plan Coral (código **EX**). Sale del estudio `estudio-regex-2026-10-09.md` (léelo primero). Decisión de
Gadea (9-oct): ir a por el 84 % del regex que intenta **entender al cliente**; queremos un chatbot profesional, que
entienda cualquier forma de decir las cosas, no uno que dependa de una lista de frases.

## Por qué

| Dato | Valor | Fuente |
|---|---|---|
| Patrones regex en `src/` | ~855 (796 en 234 grupos con nombre) | `scripts/inventario_regex.py` |
| De ellos, para ENTENDER al cliente | **668 (84 %)**: `intent_detector` 401, `supervisor` 136, `conversational_core` 84, `rag_agent` 28, `vector_store` 19 | idem |
| Turnos en que una red corrige al regex | **42 de 202 (≈ 1 de cada 5)**: ubicación 17, "otra persona" 12, actividad 7, nacionalidad 4, certificación 2 | logs PRE 9-oct (`logs-pre-2026-10-09-*`) |
| Fallos del flujo de reserva en la ronda visible con Luna | 17 de 58 (varios por no entender: "pareja Advanced O.W.", "1 buzo avanzado y 2 para bautismo", "3 buzos (2 adultos + 1 joven)") | `fallos-por-causa-2026-10-08-luna-visible.json` |
| Tiempo del paso de extracción en turnos de reserva | p50 0,81 s / p90 1,61 s; > 0,5 s en 82 de 94 (ya se llama casi siempre a un LLM) | TURN_METRICS 9-oct |
| Regla que lo bloquea | el LLM "solo rellena huecos, nunca corrige lo que el regex ya puso" | `supervisor._maybe_apply_llm_extraction_cutover`, `conversational_core._understand` |

Hoy el regex lee primero y manda; encima hay 4 redes (Jev quita lo no afirmado, veto LLM, relleno de huecos,
re-comprobación) que se añadieron una a una por cada fallo. Cada red es latencia, código y otro sitio donde
equivocarse (el 9-oct, el regex leyó bien "Cocoliso" = islas y Jev lo descartó).

## Arquitectura objetivo

1. **El LLM extrae** (una llamada estructurada por turno, `gpt-4o-mini`, la herramienta que ya existe en
   `llm_extractor.extract_and_verify`): recibe el mensaje, el dato que el bot acaba de preguntar (slot pendiente) y lo
   ya sabido, y devuelve cada campo con su **cita** del mensaje (`evidence`). Si no hay cita, no hay dato.
2. **Jev decide si el cliente lo AFIRMA** (la puerta de u3-4, ya en producción). Respeta la regla de Gadea del 24-sep:
   Jev para decisiones de opciones fijas; NO extrae valores.
3. **El código valida** contra el catálogo y el estado (listas cerradas, sumas del grupo, rangos): lo determinista
   sigue siendo determinista.
4. **El regex queda solo como PISTA** para lo cerrado y seguro (nombres de hoteles → islas, cifras, emails), que se
   pasa al LLM o sirve para validar; nunca decide solo. Si la API falla, se cae al regex de hoy (degradación).

Lo que NO se toca (y está bien con regex): las guardas sobre la respuesta del bot (49), privacidad (8), formato (13),
leer la salida del revisor (2).

## Reglas del trabajo (las de siempre)

- Un flag por cambio; escalón 0 (banco) → mini-ronda A/B de los diálogos afectados, misma franja → promocionar o
  revertir. Leer a mano lo que empeora.
- Nada de ajustar con el examen oculto ni con casos concretos del golden (sobreajuste): el banco se parte en
  diseño/ciego por diálogo y se ajusta SOLO con diseño.
- Latencia: medir p50, p95 y máx. Objetivo: no empeorar (margen +0,2 s p50).
- Ahorro: mini-rondas con `--ids`, caché del juez; tests con `ENV_FILE=.env.ci`.

## Fases

### ex-0 · Banco de extracción y línea base (escalón 0 de todo lo demás)
- Ampliar `docs/robustness/eval-set.json` (130 casos; muchos salen de los tests del regex y lo favorecen: el regex saca
  96 % ahí) con **≥ 150 mensajes de vocabulario real**: mensajes de cliente del golden VISIBLE (nunca el oculto), los 42
  turnos corregidos del 9-oct, los 17 fallos de flujo, y variantes (regional: parce/pana/bautismo/"Advanced O.W.";
  inglés; faltas; respuestas cortas a una pregunta pendiente: "Cocoliso", "sin recojos", "Frances").
- Cada caso con `history`/`state` (slot pendiente) y valor esperado por campo, incluido "no lo dice" (para medir
  inventos). Partir diseño/ciego por diálogo (`sha1 % 2`, fijado antes de medir).
- `scripts/run_extraction_eval.py`: añadir `--modo regex|actual|llm-primero` y `--grupo`. Métricas por campo:
  acierto, **inventado** (dice un valor que el cliente no dijo), perdido; tiempo y coste por turno.
- **Hecho cuando:** banco ≥ 280 casos etiquetados (Gadea resuelve las dudas de negocio), línea base de los 3 modos
  guardada en `docs/robustness/regex/`.

### ex-1 · Borrar los atajos apagados (sin riesgo)
- 28 patrones de respuestas fijas de precio, comida y refresher en `rag_agent.py`, apagados con `RAG_V2`/`S4_FIXES`
  (código muerto), y sus tests de "camino antiguo". Es parte del punto 1 de s4-25.
- **Hecho cuando:** suite verde y foto antes/después sin LLM igual en los mensajes del eval-set. Sin ronda.

### ex-2 · Escalado: palabras clave solo para emergencias
- Hoy 114 palabras clave pasan a un asesor ANTES de que opine la IA (falsos positivos reales: "timo" en "último").
- Dejar como red rápida solo emergencias médicas y de seguridad; quejas, incidencias y tiempo → la señal
  `sensitive_topic` de Jev (ya existe en la misma llamada). Flag `ESCALADO_SOLO_EMERGENCIAS`.
- Escalón 0: banco de frases (quejas reales, emergencias, falsos positivos tipo "último día", "impresión").
- **Hecho cuando:** ninguna emergencia perdida en el banco, menos falsos escalados; mini-ronda de los diálogos de
  escalado/queja sin regresiones.

### ex-3 · Atajos de texto fijo activos (28)
- "Qué ofrecen para bucear" (`_OVERVIEW_*`), alcohol/alergias, "¿eres una IA?", "mismo precio por nacionalidad":
  contestan con texto fijo cuando casa una palabra. Uno a uno, con flag: ¿el RAG lo contesta igual o mejor con la
  base? Los que sean política obligatoria (texto que el negocio quiere literal) se quedan, pero decididos por Jev.
- **Hecho cuando:** cada atajo medido (mini-ronda) y quitado o justificado.

### ex-4 · Diseño del extractor "LLM primero"
- Prompt y esquema únicos por turno (sobre `extract_and_verify`): campos, cita obligatoria, slot pendiente, lo ya
  sabido, pistas del regex de listas cerradas. Regla "el valor del LLM manda si trae cita y Jev dice que lo afirma";
  sin cita → no se guarda; API caída → regex de hoy.
- Medirlo en el banco (diseño) frente a "actual". Latencia en local y luego en PRE (escalón 0 con `--codigo-local`).
- **Hecho cuando:** en el banco ciego, "LLM primero" ≥ "actual" en acierto y ≤ en inventos, y p50 de extracción ≤ 0,9 s.

### ex-5 · Dominio 1: UBICACIÓN (absorbe lo que queda de s4-28)
- `location`/`island`/`hotel`: el que más falla (17 de 42 correcciones). Casos de s4-28 pendientes: el origen dado a
  entender tarde ("desde ese hotel", "quedándonos en el hotel") y el extractor que se inventa `location` con la
  pregunta del origen pendiente.
- Flag `EXTRACCION_LLM_UBICACION`. Banco → mini-ronda A/B de los diálogos visibles con origen u hotel.

### ex-6 · Dominio 2: CERTIFICACIÓN Y NIVEL
- `is_certified`, `last_dive_over_2_years`, nivel/curso ("Advanced O.W.", "bautismo", e-learning hecho). Incluye el
  bucle "¿Sois buzos certificados?" y el "no están certificados" inventado de `paquete-5-buceos-islas-residente-...`.
- Flag `EXTRACCION_LLM_CERTIFICACION`.

### ex-7 · Dominio 3: GRUPO Y REPARTO
- `group_size`, `group_allocation`, acompañantes ("1 buzo avanzado y 2 para bautismo", "3 buzos (2 adultos + 1
  joven)", jerga). Hoy hay 3 redes solo para esto (`_mentions_person`, `adds_person`, `companion_joins`).
- Flag `EXTRACCION_LLM_GRUPO`.

### ex-8 · Dominio 4: ACTIVIDAD, NACIONALIDAD E IDIOMA
- `activity` (curso / buceo / minicurso / snorkel), `is_colombian`, idioma ("Frances" = idioma, no un curso).
- Flag `EXTRACCION_LLM_ACTIVIDAD`.

### ex-9 · Retirar el camino antiguo (absorbe s4-3, s4-4 y parte de s4-25)
- Con los 4 dominios promocionados: reducir `intent_detector.py` a listas cerradas y pistas; quitar las redes que ya
  no hacen falta (veto, re-comprobación, puertas duplicadas) y los flags viejos; partir los módulos gigantes
  (`conversational_core` 5.500 líneas, `supervisor` 3.400).
- **Hecho cuando:** ronda core de equivalencia sin regresiones y `inventario_regex` muestra "entender al cliente" ≤ 15 %.

### ex-10 · Cierre: ronda completa con el examen oculto (una vez)
- Ronda completa del golden + examen oculto frente a `2026-10-08-luna-visible`.
- **Objetivos:** reales 88,7 % → **≥ 92 %**; fallos de flujo de reserva 17 → **≤ 6**; correcciones de redes en PRE
  1/5 turnos → ~0 (las redes ya no existen); latencia p50 y p95 no peores.

## Orden y dependencias

ex-0 → (ex-1, ex-2, ex-3 en paralelo, son independientes) → ex-4 → ex-5 → ex-6 → ex-7 → ex-8 → ex-9 → ex-10.
ex-0 bloquea ex-4…ex-8. Se puede repartir: un dominio por persona una vez hecho ex-4.

## Riesgos

- **El LLM supone datos** (es el fallo de s4-28): la cita obligatoria + la puerta de Jev + el banco con casos "no lo
  dice" lo miden y lo frenan.
- **Latencia**: hoy ya se paga la llamada en la mayoría de turnos; el objetivo es UNA llamada en vez de regex + redes.
  Si sube, se mide p95 y se decide.
- **Coste**: gpt-4o-mini; céntimos por cada 1.000 turnos.
- **Cambio grande**: por eso va por dominios, con flag, y se retira lo viejo solo al final (ex-9).
