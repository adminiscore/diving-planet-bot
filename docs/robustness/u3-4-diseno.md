# u3-4 — "Contesta y sigue" (24-sep-2026)

Estado: **escalón 0 cerrado** (programado detrás del flag `ANSWER_AND_CONTINUE`, apagado por defecto);
siguiente, escalón 1 en PRE.
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
