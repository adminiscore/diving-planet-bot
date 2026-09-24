# u3-1 paso 3 — Diseño (24-sep-2026, para revisar antes de programar)

## Qué se quería hacer y por qué cambia

El plan decía "una sola llamada al LLM para extraer los datos". Medido en la ronda A2 del 24-sep
(92 turnos, Langfuse):

| Medida | Resultado |
|---|---|
| Turnos con **extracción** | 78 llamadas, p50 **0,85 s**. Casi siempre **una sola** llamada por turno: la extracción ya se fusionó en su día (`extract_and_verify`, fase 7b) |
| Turnos con **acuse** (`compose_acknowledgement`, la frase cálida delante de la pregunta) | **58 de 92 (63 %)**, p50 **1,01 s** |
| Turnos con extracción **y después** acuse | **44 de 92 (48 %)**, **siempre en serie** |

Fusionar la extracción ahorraría casi nada. La cadena lenta es **extracción → acuse**, y **el acuse no
necesita esperar**.

## Qué es el acuse

`compose_acknowledgement` (src/agents/llm_extractor.py) escribe una frase cálida ("¡Qué bueno que ya
tienes tu curso básico!") que va delante de la respuesta. **Los datos duros NO pasan por él**: precio,
links, plan y la siguiente pregunta los pone el código. Recibe el mensaje del cliente y un resumen de la
reserva, y si se salta las reglas (precio, link, pregunta) se descarta. Hoy se llama al final del turno,
en `_slotfill_close_phase`, cuando la extracción ya terminó.

## Propuesta: el acuse en paralelo (mismo patrón que las notas de l1-4)

1. **Lanzarlo al principio** de las fases de reserva (tras el router), como tarea, con una **foto tomada
   en ese momento**: mensaje, resumen de la reserva, nombre e idioma. La foto se toma ANTES de lanzar la
   tarea (la lección de la carrera de l1-4).
2. **Esperarlo en el cierre** (`_slotfill_close_phase`), donde hoy se llama. Si el turno no llega al
   cierre (escalado, RAG sin cierre…), la tarea se cancela.
3. **Mismo prompt, mismo modelo, mismas reglas de descarte.** Lo único que cambia es el resumen: el de
   ANTES de la extracción de este turno, en lugar del de después. Lo que el cliente acaba de decir
   sigue llegando entero (va en el mensaje).
4. **Interruptor** `ack_in_parallel`, apagado por defecto. Marcha atrás: quitar la línea del compose.

**Ganancia esperada:** ~0,85 s en el ~48 % de los turnos → **~0,4 s de media por turno (~10-13 %)**.
**Coste:** una llamada de acuse de más en los turnos que no llegan al cierre (gpt-4o-mini, ~0,0001 $).

## Riesgos y cómo se controlan

| Riesgo | Control |
|---|---|
| El acuse no "ve" un dato que se acaba de extraer y lo dice distinto | El dato está en el mensaje que recibe; el resumen solo da contexto. Se mide leyendo el TEXTO en el A/B |
| Carrera con el estado (como en l1-4) | La foto se toma antes de lanzar la tarea; la tarea no lee el estado vivo |
| Un acuse fuera de lugar en un turno que acaba en otro camino | Se cancela si el turno no llega al cierre |

## Cómo se mide (protocolo de medición)

- **Escalón 0 (local):** tests del contrato (se lanza, se espera en el cierre, se cancela si no se usa,
  la foto no ve cambios posteriores). No hay una decisión que evaluar sobre los 257 mensajes: lo que
  cambia es el texto del acuse, y eso solo se ve en el bot.
- **Escalón 1 (PRE):** 1 ronda A + 1 ronda B en la misma franja, juez con cache, latencia con
  `turn_metrics`, y **leer el texto de los acuses** que cambien. Si algo empeora, escalón 2 (2 + 2).

## Qué queda para después

- Fusionar las variantes de extracción (`extract_and_verify`, `fill_gaps`, `detect_special_signals`,
  `resolve_slot_answer`): hoy casi siempre es una sola llamada, así que la ganancia es pequeña y el
  riesgo alto (prompts muy medidos). Se revisará en U3 junto con u3-4/u3-5 (calidad), no por latencia.
- Lo que sigue es la cadena del RAG (condense → respuesta → juez de grounding) para los turnos de
  información, que va con l1-6/l1-7.
