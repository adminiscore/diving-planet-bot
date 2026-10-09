# Estudio del regex en el bot (9-oct-2026, Gadea con Claude)

Pregunta de Gadea: ¿tiene sentido el regex que usamos? ¿Nos está lastrando (si el cliente usa otro vocabulario, no lo
coge)? Inventario reproducible: `python -m scripts.inventario_regex --json docs/robustness/regex/inventario.json`.

## 1. Cuánto hay y para qué

~855 patrones en `src/` (796 en grupos con nombre, 234 grupos), en ~24.000 líneas de código.

| Familia | Patrones | Qué hace | ¿Riesgo de vocabulario? |
|---|---|---|---|
| **Entender al cliente** | **668 (84 %)** | leer del mensaje actividad, certificación, grupo, ubicación, nacionalidad, edades, fechas; decidir rutas y señales | **Sí** |
| Guardas sobre la respuesta del bot | 49 (6 %) | importes y links que no están en el contexto, teléfonos, pedir datos personales, frases con precio | No (miran el texto del bot) |
| Atajos de texto fijo, APAGADOS | 28 (3,5 %) | respuestas fijas de precio, comida y refresher; apagadas con `RAG_V2`/`S4_FIXES` | Código muerto |
| Atajos de texto fijo, activos | 28 (3,5 %) | resumen de "qué ofrecen para bucear", alcohol/alergias, "¿eres una IA?", mismo precio por nacionalidad | Sí |
| Formato y datos internos | 13 | Markdown → WhatsApp, ids internos | No |
| Privacidad | 8 | tapar emails, teléfonos, tarjetas, documentos | No |
| Leer la salida de un LLM | 2 | el veredicto del revisor | No |

Además: **114 palabras clave de escalado** (`escalation.SENSITIVE_RULES`: médicas 26, tiempo 14, incidencias 26,
quejas/emergencias 48) que pasan a un asesor ANTES de que la IA opine.

"Entender al cliente" por fichero: `intent_detector.py` 401, `supervisor.py` 136, `conversational_core.py` 84,
`rag_agent.py` 28, `vector_store.py` 19.

## 2. Cómo funciona hoy: el regex manda y hay redes encima

En la reserva, el regex lee el mensaje primero (`intent_detector.detect`) y encima hay capas que se fueron añadiendo
cada vez que el regex leía mal:

1. **Jev quita lo que el cliente no afirma** (u3-3/u3-4/s4-26/s4-27/s4-28).
2. **Veto LLM** de campos que el regex resolvió (solo con ciertos disparadores).
3. **Relleno de huecos LLM** (`fill_gaps`/`extract_and_verify`): solo rellena lo que el regex dejó vacío; **nunca corrige
   un valor que el regex ya puso** (`_maybe_apply_llm_extraction_cutover`: "never overwrite regex").
4. **Re-comprobación** de campos ya sabidos que el mensaje podría corregir.

## 3. Lo que dicen los datos

- **Logs de PRE del 9-oct (4 mini-rondas, 202 turnos):** **42 veces** una red corrige al regex (≈ 1 de cada 5 turnos):
  ubicación "islas" que el cliente no dijo 15, "menciona a otra persona" que no era 12, actividad "buceo certificado" 5,
  "es colombiano" 4, otras 6.
- **Las redes también fallan:** en `paquete-5-buceos-islas-residente-sin-recogida`, el regex leyó bien "Cocoliso" →
  islas y Jev lo descartó ("no lo afirma"). Cada capa es otro sitio donde equivocarse.
- **Lo que se escapa:** de los 58 fallos de la ronda visible con Luna, 17 son del flujo de reserva, varios de no
  entender el mensaje: "Somos una pareja Advanced O.W." → pregunta si están certificados; "1 buzo avanzado y 2 para
  bautismo" → "minicurso para una persona"; "3 buzos (2 adultos + 1 joven)" → vuelve a preguntar cuántos.
- **Historial:** 75 líneas de HISTORY hablan de regex; una buena parte son arreglos de vocabulario ("nunca **hemos
  hecho** buceo", "parce/pana/cuate", "son" = hijo en inglés, "timo" dentro de "último", "¿cuánto dura?" → lista de
  precios). Ampliar el regex frase a frase es justo lo que la memoria de Gadea prohíbe (sobreajuste).
- **Latencia:** el paso de extracción en turnos de reserva ya tarda **p50 0,81 s / p90 1,61 s**, y en 82 de 94 turnos
  pasa de 0,5 s: casi siempre se acaba llamando a un LLM. **Que el LLM extraiga primero no añadiría latencia.**

## 4. Valoración

| Familia | Veredicto |
|---|---|
| Guardas, privacidad, formato, leer LLM (72) | **Mantener.** Son deterministas y miran texto que controlamos; un LLM aquí sería más caro y menos fiable. |
| Atajos apagados (28) | **Borrar.** Código muerto; cero riesgo. |
| Atajos activos (28) | **Medir y probablemente quitar**: contestan con texto fijo cuando casa una palabra; el RAG ya sabe contestarlo con la base. Uno a uno con flag y mini-ronda. |
| Palabras clave de escalado (114) | **Reducir a emergencias reales** (médico/seguridad) como red rápida; quejas e incidencias → la señal de Jev (`sensitive_topic`), que ya existe. |
| **Entender al cliente (668)** | **Es el lastre.** Invertir el orden: el LLM extrae (una llamada estructurada, la misma que hoy ya se hace en la mayoría de turnos), Jev decide si el cliente lo afirma, y el regex queda solo para lo cerrado y seguro (nombres de hoteles, cifras, emails) como pista. Por dominio, con flag y mini-ronda A/B, empezando por **ubicación** (la que más falla) y siguiendo por certificación, grupo y actividad. |

Riesgos de invertir: que el LLM suponga datos (es justo s4-28: el extractor se inventa `location` con la pregunta del
origen pendiente) → la puerta de Jev ("¿lo afirma el cliente?") se mantiene. Coste: gpt-4o-mini, céntimos.

Encaja con s4-28 (cuyo plan ya incluía "inventario de regex"): este estudio es ese inventario.
