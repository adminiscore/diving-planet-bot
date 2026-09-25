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

### Arreglos 1 y 2 — hechos y MEDIDOS (25-sep, Gonzalo). Arreglo 2: **resultado negativo**

Los dos arreglos que pedía el "siguiente paso" están implementados, con tests, detrás del mismo
flag, y **ya medidos en el escalón 0** (ver "Escalón 0 de los arreglos" más abajo). Resumen del
veredicto, por si no lees más: el **arreglo 1 no se puede medir aquí** (el replay sustituye el RAG
por un texto fijo que nunca es el fallback) y el **arreglo 2 NO cumple**: no quita el dato
hipotético y en tres casos de `location` lo *añade* donde la versión anterior no lo ponía.

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
pasarían aunque se hubiera roto lo que u3-4 aporta. `ruff` y `compileall` limpios.

> **Corregido el 25-sep**: ese "24/24" y los "2 fallos preexistentes de `test_conversational_core`"
> se midieron corriendo la suite con `.env` y la clave REAL (el `README` decía `pytest` a secas).
> Así las redes de extracción y verificación llaman de verdad: lento, facturable y no determinista.
> Con `ENV_FILE=.env.ci`, que es como corre CI, `test_conversational_core` pasa **237/237** y sale
> un fallo de verdad que la clave viva tapaba: `test_en_una_pregunta_el_regex_no_escribe_datos` (de
> los 16 de Gadea) **no sustituía el LLM**, así que con el LLM caído `verify_fields` devuelve `None`
> —contrato defensivo, un corte de red no puede tirar datos buenos— y el `island` del regex
> sobrevivía. Arreglado y hecho determinista, más un test nuevo que fija el otro lado del contrato.

### Escalón 0 de los arreglos (25-sep, Gonzalo) — veredicto: **NO promocionar el arreglo 2**

El bloqueo de la clave lo resolvió Gadea (pasó `OPENROUTER_API_KEY`, en `.env.dev` local, que está
en `.gitignore`). Sonda previa: Jev contesta en ~0,3 s y `asks_question` discrimina bien
(`True` en "¿puedo bucear si uso gafas graduadas?", "¿cuánto cuesta el bautizo?" y "soy epiléptica,
¿puedo…?"; `False` en "vale, perfecto"). Misma pasada `off` del 24-sep: sigue valiendo, porque el
replay sustituye el RAG por un texto fijo (`«RAG»`) que nunca es el fallback y el arreglo 2 está
detrás de `_has_pending_answer`. **Eso también significa que el arreglo 1 no se mide aquí.**

Tres versiones del mismo flag, misma pasada `off` de referencia (368 turnos, 95 diálogos, 0 errores):

| | contestadas (de 165) | contesta Y sigue | campos-turno que GANA | que PIERDE |
|---|---|---|---|---|
| v1 (extraer en la pregunta) | 123 | — | 220 | 17 |
| v2 (`_leave_question_fields_to_llm`, la del escalón 1) | 123 | 122 | 163 | 24 |
| **v3 (regex lee + LLM verifica)** | **123** | **122** | **119** | **29** |

**Contestar no cambia**: 94 → 123 (+29) en las tres. El arreglo 2 solo mueve el lado de los datos,
y lo mueve a más conservador.

**El juez y la lectura a mano.** 51 turnos con dato de más, el juez (`gpt-5-mini`) ve inventado en
30. `scripts/replay_diff_triage.py` (nuevo) aparta el ruido objetivo que el propio `replay_diff`
avisa —9 turnos sin pregunta, 5 con estado previo ya distinto— y deja **16 para leer**. Leídos uno a
uno en `u3-4/lectura-a-mano-v3.md`: 7 son mapeos de producto correctos ("paquete de 5 buceos" →
`certified_diving`), 1 es una inferencia de negocio legítima, 3 son dudosos y **5 son errores
reales**: 2 de nacionalidad (familia u3-5, ya existían) y **3 del dato hipotético, que es justo lo
que el arreglo 2 venía a matar**.

**La medida per-caso que decide.** En el caso que el "siguiente paso" nombra por su nombre:

```
curso-open-water-transporte-y-regreso-otro-dia#2
  "What if I decide to stay one day longer in rosario, can you provide de transfer back to cartagena?"
  off: (nada)   v2: padi_open_water   v3: padi_open_water + location=island + detected_location=island
```

Los **tres** `location` nuevos que solo introduce v3 son inventados, y ninguno es un dato bueno
recuperado: "…hoteles **en la isla** que recomiendes", "se quedar en **la isla** de apoyo" (la isla
es de la madre, no del cliente) y el "what if" de arriba. Una mejora agregada que empeora un caso no
cuenta, y aquí empeora el caso de referencia: **v3 no se promociona**.

**Por qué falla, que es lo que hay que llevarse.** El diseño suponía que verificar es una pregunta
cerrada ("¿el cliente AFIRMA esto?"). No lo es: `verify_fields` **vuelve a extraer** con el prompt de
verificación, y la definición de `location` dice *"'island' si se alojan o vienen de las Islas del
Rosario"*. Ante "¿me recomiendas hoteles en la isla?" el LLM ve una señal clara y contesta `island`.
No hay ninguna pregunta en el sistema que distinga afirmar de preguntar.

**Intento de arreglo por el prompt, DESCARTADO (segundo resultado negativo).** Se probó añadir el
matiz SOLO al prompt de verificación (no al de relleno, donde ya era negativo el 24-sep): *"un lugar,
producto, curso, nacionalidad o precio nombrado DENTRO de una pregunta o una hipótesis es lo que el
cliente PREGUNTA, no algo que afirme de sí mismo"*.

- Sonda de frases sueltas (10 frases × 4, determinista 0/4 o 4/4): arreglaba 1 de 4 y no rompía
  ninguno de los 6 controles. Parecía bueno.
- **Pero la sonda no era fiel**: llamaba a `verify_fields` con un campo y sin historial, y en el
  replay real se llama con la lista entera y con el historial. Sin historial el LLM **ya** se abstenía
  en 2 de los 3 casos de `location`, así que la sonda medía otra cosa.
- Sonda fiel (los mismos diálogos por el núcleo de verdad, `scripts/sonda_verificacion_fiel.py`): el matiz **no
  quita ni un `location` inventado** y **rompe un caso** — en "we want to complete our PADI open
  water: we have referrals and e-learning certificates", `is_certified` pasa de `False` a `True`.
  Revertido, no está en el código.

**Lo que sí queda**: `verify_fields(..., as_answers=True)` (poder distinguir "confirma" de "no
opina") es útil por sí mismo y no cambia nada por defecto; y `scripts/replay_diff_triage.py`
automatiza la separación de ruido que antes había que recordar hacer a mano.

Datos: `u3-4/replay-on.jsonl` (v3), `replay-on-v2.jsonl` (la del escalón 1), `replay-on-v1.jsonl`,
`diff.json` (v3) y `diff-v2.json`, `triaje-v3.txt`, `lectura-a-mano-v3.md`.

### La puerta de Jev (v4 y v5, 25-sep) — el mecanismo funciona; la redacción hay que calibrarla

La propuesta de abajo se implementó y se midió el mismo día. Dos preguntas nuevas a Jev
(`affirms_location`, `affirms_activity`) en la MISMA llamada del router, detrás del mismo flag: en
un turno con pregunta, un campo que Jev dice que el cliente NO afirma se cae **sin llegar siquiera
a la verificación**. Ausente (Jev apagado, o dudó en una señal del router) NO es `False`: es "no lo
sé" y se sigue con la conducta de hoy.

**v4, con la redacción escrita a ojo: negativo.** Mataba los 3 `location` inventados, sí — pero
fijaba **menos actividad que el propio flag apagado** (239 frente a 245) y se comía datos que el
cliente afirma sin ambigüedad: "I plan on being in Cartagena and do scuba diving on April 21 and
22. I have open water", "estaremos en islas del rosario en junio", y toda la familia "cuánto cuesta
el paquete de 5 / el fundive". Ganaba 67 campos-turno y perdía 53.

**Causa, medida en un banco de 20 casos reales** (`scripts/sonda_afirma_vs_pregunta.py`: los 3
inventados que hay que matar y los datos buenos que v4 destruyó, que el flag apagado ya capturaba).
La redacción fallaba en dos cosas concretas, las dos de negocio:

1. **un plan de futuro sí dice dónde estarán** — "I'll be in Cartagena in April" daba 0,35;
2. **nombrar un producto para preguntar su precio sí es elegirlo**, que es la regla del catálogo —
   "los valores del pack de 5 buceos" daba 0,63.

Con eso escrito en la pregunta: **19/20 frente a 15/20**, y los que deben morir siguen muriendo
(0,07-0,48) mientras los buenos suben a 0,85-0,97.

**v5, con la redacción calibrada:**

| | contestadas (165) | contesta Y sigue | GANA | PIERDE | juez "inventado" | a leer | errores reales |
|---|---|---|---|---|---|---|---|
| v2 (escalón 1) | 123 | 122 | 163 | 24 | — | — | 4 |
| v3 (regex + verificación) | 123 | 122 | 119 | 29 | 30 | 16 | 5 |
| v4 (Jev, redacción a ojo) | 123 | 122 | 67 | 53 | — | — | destruye ~10 buenos |
| **v5 (Jev calibrado)** | **123** | **122** | **69** | **33** | **13** | **7** | **2** (+3 de u3-5) |

Los **3 inventados objetivo desaparecen** y los datos buenos vuelven. Lectura de los 7 en
`u3-4/lectura-a-mano-v3.md` (sección v5).

**Lo que sigue estorbando, y está medido.** De las 20 pérdidas frente al flag apagado (sin contar
arrastre), **11 ya estaban en v3**: no las causa la puerta de Jev sino la **verificación** del
arreglo 2 — el LLM no vuelve a extraer "fundive" → `certified_diving`, ni "buceo certificado" →
`is_certified`. Las otras 9 son de la puerta, y la mayoría defendibles ("complete the certification
in Cartagena" no dice dónde se aloja; "sin ir de cartagena" es justo lo contrario de Cartagena).

Y los **2 errores reales** que quedan son de campos que la puerta NO vigila (`is_certified`,
`group_size`): misma causa, misma solución, una pregunta más — pero cada campo hay que calibrarlo
contra casos reales antes, que es la lección de v4.

### v6 — quitar la verificación y dejar solo la puerta: **medido y negativo**

La atribución de arriba señalaba a la verificación (11 de las 20 pérdidas), así que se probó
quitarla: en un turno con pregunta decide Jev y lo demás se queda como lo leyó el regex, **sin
segunda llamada** (más barato y más rápido, además).

| | GANA | PIERDE | juez "inventado" | a leer |
|---|---|---|---|---|
| v5 (puerta + verificación) | 69 | 33 | **13** | **7** |
| v6 (solo puerta) | 97 | 31 | 19 | 9 |

Recupera datos —`regateo-grupo-6#1` vuelve a guardar `is_certified=True` como el flag apagado, y
`referral…#2` queda idéntico a `off`— **pero devuelve inventados**: 19 frente a 13. Las dos piezas
hacen trabajo: la puerta de Jev decide si el cliente lo afirma, y la verificación arregla lo que el
regex leyó mal. **Se revierte y se queda v5.** Evidencia: `replay-on-v6.jsonl`, `diff-v6.json`.

Un aviso que salió de aquí: la hipótesis era que la verificación causaba esas 11 pérdidas, y **era
falsa en al menos un caso** — "costo de un fundive" → `certified_diving` se pierde igual en v3, v5 y
v6, así que no la causa ninguna de las dos piezas. Sigue sin explicar.

### Explicado (25-sep, tarde): por qué "fundive" se pierde en v3, v5 y v6

**No es la verificación ni la puerta: es que en un turno con pregunta no se rellenan huecos.** Es la
tercera pieza del arreglo 2, y la única que v3, v5 y v6 tienen en común (v6 quitó la verificación pero
siguió sin rellenar: "lo demás se queda como lo leyó el regex"). En el código:
`_wants_gaps` es falso cuando `question_turn_fields is not None` (`conversational_core.py`, bloque
"en un turno con pregunta NO se rellenan huecos"). Así que en ese turno **solo sobrevive lo que leyó el
regex**, y la verificación y la puerta solo filtran eso.

El regex **no lee "fundive"** (junto): `matched_activity_categories` da `[]`, y con "fun dive" (separado)
da `certified_diving`. Con el flag apagado la actividad la ponía el **relleno de huecos** del LLM. Por
eso Jev contesta 0,96 en el banco y no sirve de nada: la puerta deja pasar un dato, pero aquí nadie lo
propone.

**Es una familia, no un caso.** Pérdidas de v5 frente a `off` con criterio estricto (turnos con el
estado previo IDÉNTICO en las dos pasadas, `location`/`detected_location` contados una vez): **12**.
Pasando cada mensaje por `_detector.detect()` con el estado previo de `off`:

| | Pérdidas | Qué son |
|---|---|---|
| El regex **sí** lee el dato y la verificación o la puerta lo tiran | **8** | lo ya señalado arriba |
| El regex **no** lee nada: solo podía venir del relleno | **4** | ver abajo |

Las 4 del relleno, leídas a mano:

- `precio-fundive-datos-faltan#1` → `certified_diving`: **dato real** (nombra el producto para
  preguntar su precio, la regla de negocio de la calibración).
- `aprobacion-logs-padi#2` → `last_dive_over_2_years=False` ("el sábado pasado hicimos 2 buceos"):
  **dato real** (el juez de v5 lo da por afirmado un turno después).
- `principiante-hora-lugar-y-precio#4` → `group_size=1`: **dato real**, dicho en el turno 1 ("for
  1 person") dentro de una pregunta; `off` lo recuperaba del historial al rellenar en el turno 4.
- `nino-7-familia#2` → `snorkel` ("entonces qué actividad le recomiendan"): **aquí perder es
  acertar**: el cliente pide consejo, no elige. `off` se lo inventaba.

**Propuesta, SIN implementar (para después de la ronda B):** en un turno con pregunta, volver a
rellenar huecos **solo en los campos que tienen puerta de Jev**, y que lo rellenado pase por la
puerta igual que lo que lee el regex. Es la misma regla de la puerta aplicada a las dos fuentes: el
regex o el LLM proponen el valor y **Jev decide si el cliente lo afirma**. Con las puertas de hoy
(actividad, ubicación) recuperaría "fundive" (0,96) y debería dejar caer el snorkel de "¿qué
actividad le recomiendan?" (hay que meterlo en el banco). `group_size` y `last_dive_over_2_years`
necesitan su propia pregunta, igual que `is_certified`: **la misma lista que ya señalan los 2 errores
reales**. Así el relleno que se apagó por "in case I decided to do the Open Water course?" puede
volver sin reabrir ese agujero, porque `is_certified` solo se rellenaría con su puerta calibrada.

**Por qué no ahora:** cambiaría lo que mide la ronda B pendiente (que es de v5), y cada pregunta
nueva se calibra antes en `scripts/sonda_afirma_vs_pregunta.py` (lección de v4), lo que exige
`OPENROUTER_API_KEY`.

### ⚠️ Jev no es determinista entre tandas, y eso cambia cómo se leen estas tablas

Comparando v5 y v6, **9 turnos cambian en si la pregunta se contesta o no, en las dos direcciones**
— y el cambio de v6 no toca ese camino. Es varianza de Jev: `asks_question` cae cerca del umbral
(0,7) y baila entre tandas. El titular "94 → 123 preguntas contestadas" tiene por tanto un ruido de
**±5**, y las comparaciones del número de contestadas ENTRE versiones a esa resolución no
significan nada (dentro de una misma tanda, off frente a on, sí: es la misma).

Arrastra también a `GANA`/`PIERDE`: si un turno se contesta o no, el estado diverge a partir de
ahí. Por eso la lectura que decide es **por caso** y el recuento del juez tras apartar el ruido, no
el agregado. Quien repita esto: con dos tandas de la MISMA versión se mediría el ruido de verdad
(no se hizo hoy, por no gastar 20 min y otra tanda de peticiones en algo ya visible).

## Siguiente paso (para quien siga) — actualizado 25-sep, tarde

**Estado del código** (flag `answer_and_continue`, apagado en el código y en el compose; PRE no ha
cambiado):

1. **Arreglo 1** (si el RAG no sabe, su respuesta va sola): hecho. **Sin medir**, y no se puede
   medir en el escalón 0 — el replay sustituye el RAG por un texto fijo que nunca es el fallback.
   Se mide en el escalón 1.
2. **Arreglo 2** (el regex lee, el LLM verifica): hecho, medido, **no cumplía solo**.
3. **La puerta de Jev** (`affirms_location`, `affirms_activity`, misma llamada del router): hecho,
   medido, **es lo que lo arregla**. Con las dos piezas: los 3 `location` inventados desaparecen,
   el juez baja de 30 a 13 y los errores reales de 5 a 2.

**Lo que toca: escalón 1, SOLO ronda B.** Se compara con la ronda A del 24-sep
(`2026-09-24-u34-A`, flag apagado); la latencia no hace falta repetirla porque por tipo de turno no
cambió. Comandos en el banner de Gadea en el handoff. **Ojo con dos cosas antes de lanzarlo**:

- enciende el flag en PRE (`docker-compose.vps.yml`) y un push a `feature/pre_gadea` despliega:
  cambia lo que ve todo el mundo en PRE, así que se avisa antes;
- una ronda core gasta una parte seria del presupuesto de peticiones del día.

**Cuando se mire el resultado, leerlo por caso.** Jev no es determinista entre tandas (sección de
arriba): el número de preguntas contestadas tiene ±5 de ruido. Dentro de una misma tanda, A frente
a B, sí es comparable.

**Lo que queda señalado, con evidencia y sin hacer:**

- **Los 2 errores reales que sobreviven son de campos que la puerta NO vigila** (`is_certified` en
  "in case I decided to do PADI Open Water", `group_size` en un mensaje con 2 personas). Misma
  causa, misma solución —una pregunta más a Jev, en la misma llamada, coste 0— pero **calibrando
  cada campo antes** contra casos reales: esa es la lección de v4, que con la redacción escrita a
  ojo fijaba menos actividad que el propio flag apagado. El banco está en
  `scripts/sonda_afirma_vs_pregunta.py`; añadir casos y comparar cuesta 10 s.
- **`is_colombian` sigue siendo u3-5** (decisión de Gadea, 24-sep): 3 de los 7 casos que quedan a
  leer son suyos. La sonda de Jev sugiere que es la misma familia y tendría la misma solución.
- **Explicado (25-sep, tarde): "fundive"** se pierde porque en un turno con pregunta **no se
  rellenan huecos** y el regex no lee "fundive" junto. Es una familia: 4 de las 12 pérdidas
  estrictas de v5 (3 datos reales y 1 acierto). Propuesta: rellenar solo los campos con puerta de
  Jev y pasar lo rellenado por la puerta. Sección "Explicado" más arriba.
- **Recuperar las respuestas de Jev cuando duda en el router**: hoy, si Jev duda en cualquier señal
  del router, el turno se va al router LLM y las respuestas de `affirms_*` se pierden (~8 % de los
  turnos) — se cae a la conducta de hoy, que es seguro pero desaprovecha una respuesta buena.
  `asks_question` sí se rescata; estas no, porque hacerlo obliga a cambiar la firma de
  `detect_routing_signals_jev_full`. Es una mejora pequeña y acotada.
