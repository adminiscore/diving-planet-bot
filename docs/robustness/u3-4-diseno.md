# u3-4 — "Contesta y sigue" (24-sep-2026)

Estado (24-sep noche): **escalón 0 y escalón 1 hechos; NO promocionado todavía** (flag
`ANSWER_AND_CONTINUE`, apagado por defecto en el código y APAGADO en PRE desde el push del handoff,
`"false"` en docker-compose.vps.yml; para la siguiente ronda B se pone `"true"`).
Siguiente: dos arreglos y repetir solo la ronda B → ver "Siguiente paso" al final.
Protocolo: [protocolo-medicion.md](protocolo-medicion.md).

## El problema, medido

Ronda de cierre de L1 (24-sep, 465 turnos): hay **165 turnos en los que el cliente pregunta algo** y
**fallan 79**. El detector nuevo (ver abajo) ve la pregunta en 66 de esos 79. Reparto por causa:

| Causa | Turnos | ¿Lo arregla u3-4? |
|---|---|---|
| El bot **se salta la pregunta y sigue con la reserva** ("perfecto, como pago" → "¿lo cambio a sin certificación?") | **27** | **Sí** |
| Primer mensaje largo con datos y pregunta: bienvenida y contesta otra cosa | 12 | En parte |
| El RAG contesta "no lo tengo a la mano" | 15 | No (l1-7) |
| Pasa a asesor sin necesidad | 7 | No (l1-6/l1-7) |
| "Me habías dicho…" sin que se lo pidieran | 3 | No (u3-6) |
| Filtro de privacidad con "tarjeta de crédito" | 1 | No (s4) |

Volver a pedir un dato que el cliente ya dio en el mismo mensaje pasa poco (11 turnos): el fallo grande
es que **la pregunta se queda sin contestar**. En la muestra core hay 18 turnos afectados de 93.

## Por qué pasa

Desde el núcleo original (22-jul, commit e4ac20e) cada mensaje es **pregunta O dato**, nunca las dos cosas:

- **Con "?"** → RAG + volver a pedir el dato pendiente. **No se extraen** los datos del mensaje.
- **Sin "?"** → se extraen los datos. La pregunta solo se contesta **si la reserva no avanzó** ese turno
  (la red de `_extraction_phase`): si avanzó, la pregunta se pierde.
- **Sin "?" y sin que la vea el regex** ("perfecto, como pago") → se trata como dato.

Ese reparto no salió de ningún fallo medido: era el diseño de partida.

## El diseño

1. **Detectar la pregunta**: el regex/"?" de siempre, **o Jev** con una pregunta nueva de
   probabilidad (`asks_question`, ≥ 0,7) que **va en la misma llamada del router** (sin petición ni
   tiempo de más; regla del equipo: decisiones de opciones fijas, primero con Jev). Escalón 0, 257
   mensajes del golden sin examen oculto: el regex ve 114 de 157 preguntas; regex O Jev ≥ 0,7 ve
   **134, con 0 falsas alarmas**. Si Jev duda en las señales del router (cascada al LLM), su respuesta
   a `asks_question` viaja igual; si Jev falla, queda el regex.
2. **La respuesta del RAG se lanza en paralelo** en cuanto se detecta la pregunta (`_routing_phase`), con
   la foto del historial tomada al lanzarla (lección de l1-4).
3. **El turno sigue su camino normal**: extracción (ya no se salta en mensajes con pregunta) y elegir el
   siguiente paso de la reserva.
4. **La respuesta lleva las dos cosas**: primero la respuesta a la pregunta y después lo que toque de
   la reserva (el siguiente dato o el cierre con el resumen). Si la extracción cierra el turno por una
   salida anticipada (acompañante, carrito post-cierre…), la respuesta va delante igual. La respuesta
   ocupa el sitio del acuse cálido (que se cancela). Única excepción: si la respuesta ya invita a
   elegir actividad y lo siguiente sería el menú entero, no se repite (regla que ya existía).
5. **Sin cambios**: el "¿me recuerdas…?" (respuesta fija con el valor del estado; la respuesta del RAG
   se cancela), el saludo puro y la deliberación entre actividades sin "?".
6. **Latencia**: RAG y extracción en paralelo → el turno tarda lo que la más lenta, no la suma. **Coste**:
   una petición de extracción de más en los mensajes con "?" (hoy no extraen).
7. **Red de seguridad**: si el RAG falla, el turno sigue con la reserva; una respuesta lanzada que nadie
   usa se cancela al cerrar el turno (`supervisor.route_message`).

Código: `src/agents/conversational_core.py` (`_turn_has_question`, `_maybe_launch_answer`,
`_take_parallel_answer`, `_prepend_parallel_answer`, `_skips_gaps_as_question`),
`src/agents/jev_router.py` (`ASKS_QUESTION`, `detect_routing_signals_jev_full`),
`src/agents/escalation.py`. Tests: `tests/test_u3_answer_and_continue.py`.

## El riesgo principal: inventar datos

Al extraer también en los mensajes que solo preguntan, el extractor puede inventar datos (el riesgo de
u3-5: "¿cuánto cuesta para 2?" → apuntar 2 personas). **Listón: 0 datos inventados.** Si aparece alguno,
se corrige en la instrucción de extracción (vale para todos los mensajes), nunca con un parche por caso.

## Escalones

- **Escalón 0 (local)**: tests (flag apagado = conducta de hoy; flag encendido = 0 tests de conversación
  rotos) y reproducción local del golden sin examen oculto, con el flag apagado y encendido (RAG, acuse
  y notas sustituidos por respuestas fijas; extracción y router de verdad), comparando qué datos guarda
  cada versión. Resultados abajo.
- **Escalón 1 (PRE)**: A/B 1+1 en core, caché del juez, turn_metrics, leer el texto de los 18 turnos.
- **Escalón 2**: solo si hay dudas.

## Resultados

### Escalón 0 (local, 24-sep) — cerrado

**Tests.** Flag apagado: 2638 pasan (la conducta de hoy intacta). Flag encendido: 0 tests de
conversación rotos. 16 tests nuevos en `tests/test_u3_answer_and_continue.py`.

**Reproducción local del golden** (95 diálogos / 368 turnos sin examen oculto; flag apagado frente a
encendido; extracción y router Jev de verdad, RAG/acuse/notas con respuestas fijas):

| Medida | Flag apagado | Flag encendido |
|---|---|---|
| Turnos con pregunta (165) que el bot contesta | 94 | **123 (+29)** |
| …contestados **y** siguiendo con la reserva | — | 122 |
| Turnos sin pregunta según la etiqueta que ahora se contestan | — | 8: 6 eran preguntas reales que la etiqueta no marcó ("tienen algún descuento", "cómo reservamos") y 2 intentos de inyección (van al RAG, cuyo prompt prohíbe revelar instrucciones; `inyeccion-system-prompt` está en core → se lee en el escalón 1) |

**Datos que guarda de más** (turnos donde el flag cambia el camino y el estado previo era idéntico):

- **Primera versión** (regex + LLM en las preguntas): 32 turnos; los errores graves venían del
  **regex**, que lee palabras sueltas sin entender la frase: "I'm interested in taking PADI Open Water
  course" → ya certificado; "do you have any hotel in Rosario you recommend?" → se aloja en la isla.
- **Arreglo por causa**: en un turno con pregunta los datos los lee **el LLM, no el regex**
  (`_leave_question_fields_to_llm`), en la misma petición. No se amplió el veto a todo: ampliarlo en
  septiembre bajó la concordancia de actividad del 89 % al 73 %.
- **Segunda versión**: 28 turnos; ~21 son datos buenos que antes se perdían ("somos de Bogotá" →
  colombianos, "curso básico" → curso Open Water, "5 dive package" → buceo certificado, "Hotel
  Fragata, 2 personas"). **Quedan 4 errores**: 3 de **nacionalidad** inventada a partir de una
  pregunta ("¿el precio es en dólares o en pesos?" → no colombiano) y 1 de actividad ("curso básico"
  → minicurso). Hay 3 dudosos.
- **Los errores de nacionalidad no son nuevos**: el extractor ya los comete en mensajes sin pregunta
  (también salen en la pasada con el flag apagado), y en el eval-set de extracción `is_colombian` es
  el campo más flojo (58-68 %). Es la familia de **u3-5**.
- **Intento de arreglo en la instrucción, DESCARTADO**: una frase neutra en la definición del campo
  ("una pregunta no es una afirmación: preguntar en qué moneda está un precio o quién cuenta como
  colombiano no dice de dónde es el cliente"). Sonda de 12 frases genéricas × 6: arregla "y los
  extranjeros pagan en dólares?" (1/6 → 6/6) pero rompe dos: "¿hay descuento para colombianos?" pasa de
  True a **False** (moneda equivocada) y "we're german tourists" deja de rellenarse (5/6 → 1/6). Mismo
  efecto que el resultado negativo de septiembre documentado en `src/prompts/booking.py`: en la tarea
  de relleno, cualquier matiz de "no supongas" hace perder datos. Revertido.

**Coste**: una petición de extracción de más en los mensajes con "?" (hoy no extraen); el RAG va en
paralelo a la extracción, así que la latencia no debería sumar (se mide en el escalón 1).

Datos y salidas del escalón 0: `docs/robustness/u3-4/` (etiquetas de pregunta, reproducciones off/on,
diff). Herramientas: `scripts/replay_golden_local.py` + `scripts/replay_diff.py`.

### Escalón 1 (PRE, 24-sep noche) — hecho, veredicto: **AÚN NO se promociona**

Rondas core `2026-09-24-u34-A` (flag apagado, commit 96f5844) y `2026-09-24-u34-B` (flag encendido,
commit 4d85f04), misma franja (20:09 y 20:31). Fotos: `docs/robustness/snapshots/2026-09-24-u34-{A,B}.json`;
juez: `docs/robustness/golden-set/results/2026-09-24-u34-{A,B}__gpt-5-mini-medium.json`; textos de los 18
turnos afectados lado a lado: `docs/robustness/u3-4/escalon1-textos-A-vs-B.txt`. Comparar criterio a
criterio: `python -m scripts.ab_judge_compare 2026-09-24-u34-A 2026-09-24-u34-B`.

| | A (sin flag) | B (con flag) |
|---|---|---|
| Diálogos que pasan | 17/32 (53 %) | **19/32 (59 %)** |
| Criterios | 87,3 % | **88,5 %** |
| Turnos contestados por el RAG | 29 | **40** |
| Turnos con "no lo tengo" (fallback) | 6 | 9 |
| Turnos RAG, latencia p50 / media | 4,25 / 4,85 s | 4,30 / **4,55 s** |
| Turnos de reserva, latencia p50 / media | 1,64 / 1,89 s | **1,45 / 1,73 s** |

**Latencia: no empeora.** La media global sube (2,68 → 2,85 s) solo porque hay MÁS turnos de pregunta,
que son los lentos; por tipo de turno B va igual o mejor.

**9 mejoras** (moneda aclarada y origen preguntado, "no hay precio especial para colombianos",
domingo de Pascua, Isla Grande sin inventar, acompañante mayor…). **8 regresiones, leído el texto:**

- **Ruido (3), no es u3-4:** el descuento online escalado como "link roto" (Jev duda en ese mensaje,
  0,48, y el router LLM es inestable ahí, ya pasaba en u3-1; además el mensaje de escalado sale en
  español a un cliente en inglés → bug aparte del texto de escalado); "buceamos todos los días" (está en
  el saludo de A y de B, igual); un "revisar" de bioluminiscencia en una respuesta del RAG.
- **Sí son de u3-4 (3 causas):**
  1. **Doble pregunta cuando el RAG no sabe.** Si el RAG contesta "no lo tengo, ¿te paso con un asesor?",
     ahora se pega detrás "¿desde dónde saldrías?"; en `referral-mas-refresher…#3` además re-pregunta algo
     que el cliente acababa de decir ("reservaremos hotel en la isla"). El camino antiguo
     (`_answer_question`) no añadía la pregunta de la reserva si la respuesta ya acababa en pregunta; en
     `_slotfill_close_phase` se relajó a "solo si el siguiente paso es el menú de actividades".
  2. **El LLM guarda un dato hipotético.** "Transportation to rosario is included, in case I decided to do
     the Open Water course?" → apunta location=island y, dos turnos después, el RAG (que recibe el estado)
     le dice "como ya estás en las islas, tu punto de encuentro es el hotel". Mismo fallo de fondo que u3-5.
  3. **Aflora una respuesta floja del RAG** que antes quedaba escondida (antes la pregunta se ignoraba):
     "cómo reservo" → "un asesor te enviará el enlace". Es de l1-7.

### Arreglos 1 y 2 — hechos (25-sep, Gonzalo), pendientes de medir

Los dos arreglos que pedía el "siguiente paso" están implementados, con tests, detrás del
mismo flag. **Falta el escalón 0** (ver el bloqueo al final).

**Arreglo 1 — si el RAG no sabe, su respuesta va sola.** `_answer_replaces_the_booking_question`
(núcleo) decide cuándo la respuesta ocupa el turno entero: si es el fallback del RAG, o el caso
que ya existía (invita a elegir actividad y lo siguiente sería el menú). `core_pending_slot` se
queda como estaba, así que la reserva continúa en el turno siguiente, igual que el camino
antiguo. También en `_prepend_parallel_answer`, la otra puerta.
- De paso: `FALLBACK_ES in x or FALLBACK_EN in x` estaba copiado en el núcleo y en el
  supervisor, y este arreglo necesitaba dos más. Ahora hay una fuente,
  `rag_agent.is_fallback_answer()`, y ningún uso suelto fuera de `rag_agent`.

**Arreglo 2 — el regex lee y el LLM verifica.** Con dos bloqueos que hubo que resolver antes,
y que conviene conocer porque el enunciado original no los contemplaba:

1. **La verificación no distinguía "lo confirma" de "no opina".** `verify_fields` devolvía solo
   las DISCREPANCIAS, así que confirmar y abstenerse eran el mismo `{}`. Con eso no se puede
   implementar "solo se guarda lo que el cliente AFIRMA": ante "¿me recomiendas un hotel en
   Rosario?" el LLM se abstiene y el `location=island` del regex sobrevive — la regresión que
   el arreglo venía a matar. Lo demostraba un test que ya existía
   (`test_en_una_pregunta_el_regex_no_escribe_datos`), que pasaba con el diseño viejo y falló
   con el nuevo.
   → **`verify_fields(..., as_answers=True)`** devuelve la respuesta del LLM tal cual. El
   contrato de siempre (solo diff) sigue siendo el de por defecto: el eval-set, el supervisor y
   el resto del núcleo no se tocan. Un fallo de la llamada devuelve **`None`**, no `{}`, porque
   `{}` significaría "no afirmó nada" y un corte de red tiraría datos buenos.
2. **Tres de los campos tenían el veto apagado** (`location`, `is_certified`, `is_colombian`
   están en `False`; solo `activity`, `group_size` y `group_allocation` en `True`). Verificar
   `location` —el campo de la regresión— no habría corregido nada.
   → En el turno con pregunta la decisión se aplica **sin mirar esas banderas**, a propósito:
   gobiernan el veto del turno NORMAL, donde la pregunta es "¿el regex leyó mal?" y cada campo
   se midió por separado. Aquí la pregunta es otra ("¿lo afirma o es hipótesis?") y solo corre
   con `answer_and_continue` encendido y en turnos con pregunta.

Por campo: mismo valor → confirmado; otro valor → corrige; **ausente → nadie lo afirma y se
cae**. Los que no tienen verificador (`island`, `hotel`, `ages`, `last_dive_over_2_years`) se
descartan, por la misma regla. Y en ese turno **no se rellenan huecos**: rellenar es una
pregunta abierta e invita a suponer (así entró "in case I decided to…"). De paso se quitó una
condición duplicada (`gaps and not _skips_gaps... and not _is_greeting_only`, escrita dos veces)
que con este cambio divergía: arriba se dejaba de pedir huecos y abajo se pedían igual.

**Tests: 24/24** en `tests/test_u3_answer_and_continue.py` (16 de Gadea + 8 nuevos). Dos son
controles deliberados —que con el RAG sabiendo la pregunta de la reserva SIGUE encadenándose, y
que fuera del turno con pregunta se SIGUEN rellenando huecos—, porque sin ellos los otros
pasarían aunque se hubiera roto lo que u3-4 aporta. `ruff` y `compileall` limpios. Los 2 fallos
de `test_conversational_core` (familia `confirm_correction`, u3-5) son **preexistentes**:
verificados en un worktree en `d3dc51e` sin ninguno de estos cambios.

**🔴 Bloqueo para el escalón 0:** `replay_golden_local` fija `ENV_FILE=.env.dev` (esta máquina
solo tiene `.env`, se resuelve copiándolo) y fuerza `JEV_ROUTER_ENABLED=true`, pero **no hay
`OPENROUTER_API_KEY`**. Sin ella `jev_router` devuelve `None` y cae al router LLM — y la
detección de pregunta de u3-4 usa justo Jev (`asks_question ≥ 0,7`), así que la medición no
sería comparable en el mecanismo que decide qué turnos entran. Hace falta la clave, o aceptar
explícitamente medir sin Jev (mide qué datos guarda cada versión, que es el grueso, pero no la
detección).

## Siguiente paso (para quien siga)

Dos arreglos GENERALES y luego repetir **solo una ronda B** (se compara con esta A; la latencia no hace
falta repetirla porque por tipo de turno no cambió):

1. **Si la respuesta del RAG es el fallback** (`rag_agent.FALLBACK_ES/FALLBACK_EN`, "no lo tengo a la
   mano…"), **no** se añade la pregunta de la reserva: se deja como en el camino antiguo (respuesta sola,
   `core_pending_slot` fijado para el turno siguiente). Sitio: el bloque u3-4 de `_slotfill_close_phase` y
   `_prepend_parallel_answer` en `src/agents/conversational_core.py`.
2. **En un turno con pregunta, solo se guarda lo que el cliente AFIRMA y el LLM confirma**: en vez de
   borrar lo que leyó el regex y dejar que el LLM rellene huecos (lo de ahora, `_leave_question_fields_to_llm`),
   que el regex lea y el LLM **verifique** esos campos (el mecanismo de veto de `supervisor._VETO_FIELD_SPECS`
   / `extract_and_verify`), **sin rellenar huecos** en ese turno. Así "reservaremos hotel en la isla" se
   guarda (lo lee el regex y el LLM lo confirma), y ni "¿me recomiendas un hotel en Rosario?" (regex) ni
   "in case I decided to…" (LLM rellenando) dejan datos inventados. OJO: el veto de actividad amplio bajó
   la concordancia del 89 % al 73 % en septiembre (sesgo del LLM hacia minicurso en mensajes escuetos,
   ver `supervisor._activity_should_verify`): medirlo en el escalón 0 antes de subir.

Cómo medirlo: escalón 0 con `replay_golden_local` (off ya está en `docs/robustness/u3-4/replay-off.jsonl`,
basta la pasada on) + `replay_diff` (leer los "INVENTADO" a mano: el juez es estricto con mapeos de
producto correctos); tests. Luego escalón 1: SOLO ronda B (ver el banner del handoff para los comandos).

El error de nacionalidad (`is_colombian` inventado desde una pregunta) se deja para **u3-5** (decisión de
Gadea, 24-sep): ya existe sin el flag y arreglarlo en la instrucción de relleno hace perder datos.
