# gen-1: dónde se pierde el dato cuando «el RAG contesta incompleto» (20-oct-2026)

Fase GEN de Plan Coral. En G9, la causa «el RAG contesta incompleto» sumaba unos 30 fallos (de 98), y 11 de los 26
diálogos que tenían un solo fallo. Este diagnóstico usa **solo material propio**:
- frases nuestras;
- la verdad de `data/knowledge_base`;
- ningún diálogo del examen, que ni se abre ni se atribuye.

## 1. El RAG a solas: bien (96 %)

`rag_piezas --preguntas docs/robustness/rag-piezas/preguntas-gen1.json --reps 2` (20 preguntas propias, 104 datos):

| Pieza | Resultado |
|---|---|
| Datos en el contexto que ve el modelo | 96 % |
| **Cobertura de la respuesta** | **96 %**. Faltan 4: búsqueda 2 (opcionales de «¿pago algo más?»), redacción 1 (no dice «una noche») y contradice 1 (el verificador pide «20 % en total»). |
| Prohibidas | 0 |
| Tiempo | p50 4,4 s |

Qué incluye cada plan, horarios de regreso y de recogida, días de cierre, cupo, edades, profundidad, seguro, descuentos,
moneda, referido, celíacos, pagos, alojamiento y buceo adaptado: **la base lo tiene, la búsqueda lo trae y el RAG lo
dice**.

Faltan en la base, y tiene que decidirlo el negocio:
- la lista de qué llevar (hoy solo hay recomendaciones: protector solar reef-safe, gafas, hidratarse, pastillas para el mareo);
- si hay un mínimo de personas para salir.

## 2. En una conversación: el dato se pierde en el pase a un asesor

`reproducir_juez_pre --banco docs/robustness/gen/dialogos-gen1.json` mete 12 diálogos propios (20 turnos) en el bot
real de PRE. Cada diálogo prueba una situación. La salida está en `2026-10-20-dialogos-gen1-base.jsonl`, con la
respuesta del RAG y la traza de cada turno.

| Situación | Resultado |
|---|---|
| Pregunta de información en mitad de una reserva (qué incluye, hora de regreso, cupo) | **bien**: contesta el RAG, completo, y se repite la pregunta pendiente de la reserva |
| Varias preguntas de información en un mensaje (precio + profundidad + seguro; inglés: qué incluye + diciembre) | **bien** |
| Refresher (3 años sin bucear) | **bien** |
| **Pregunta contestable + clima** («¿cómo estará el mar el jueves? ¿el precio incluye el equipo?») | **mal**: pasa a un asesor por el clima y NO contesta lo del equipo |
| **Pregunta contestable + tema médico** («tengo asma… ¿desde qué edad pueden mis hijos?») | **mal**: pasa a un asesor y NO contesta las edades |
| **Celíaca en mitad de una reserva** | **mal**: Jev lo marca como tema MÉDICO y pasa a un asesor, aunque la base contesta (arroz con vegetales, puede llevar su comida, avisar antes) |
| Colombiano: precio + qué incluye + hotel, sin decir el origen | regular: el RAG lo contesta todo, pero la puerta «origen antes del precio» quita el párrafo del precio y, con él, el de qué incluye |

**Causa principal:** el pase por tema sensible (médico, clima…) es una respuesta fija que se come el resto del mensaje.
La situación aparece mucho en los motivos de G9 de esta causa («en su lugar escaló por el clima», varias veces en un
mismo diálogo; también «solo trató la parte médica» y «escaló en vez de responder»).

Es la misma causa que gen-3 («pase a un asesor mal llevado»): gen-1 y gen-3 se arreglan juntas.

## 3. Propuesta de arreglo (global, sin regex)

1. **Contestar lo contestable y luego pasar.** Cuando el turno va a un asesor por un tema sensible y el mensaje trae
   otras preguntas, el RAG contesta esas otras, sin tocar el tema sensible (la regla de «nunca consejo médico» sigue
   igual), y después va la línea del pase. Es un solo punto: el nodo de pase a un asesor (`escalation_agent`).
2. **Qué es «médico».** En la definición del tema sensible: una dieta o una alergia alimentaria (celíacos,
   vegetarianos, alergias) no es médica, es la política de comida, que la base contesta. Es el mismo tipo de exclusión
   que ya tiene la definición para la discapacidad y los métodos de pago.
3. (Menor) La puerta del origen debería quitar solo el precio, no el párrafo entero.

Visto de paso: la pregunta de la nacionalidad usa «¿sois colombianos?» (España). En Cartagena se dice «¿son
colombianos?».

## 4. Resultado: PROMOCIONADO (20-oct, HISTORY 0.31.70)

Se hicieron los puntos 1 y 2 de la propuesta, más el clima con su política (decisión de Gadea). Flags:
`contesta_antes_de_pasar`, `clima_con_politica` y `dieta_no_es_medica`. Con el último, también se encendió
`atajo_alergia_por_rag`: la alergia la contesta el RAG y ya no sale el texto crudo de la política.

**Banco del pase** (`dialogos-gen3.json`, 10 diálogos ×2): **20/20 bien**.
- Contesta lo demás y luego pasa: asma + edades, embarazo + horario, medicación + seguro, clima + equipo (en inglés y
  en español).
- Solo pasa: los controles de solo médico y solo clima.
- La base contesta, sin pase: celíaca, vegetariana y alergia a los mariscos.

**Banco de gen-1:** sin regresiones.

**Ronda core:**

| Ronda | Criterios | Diálogos sin fallos |
|---|---|---|
| gen3-A (base del mismo día) | 97,4 % | 26/32 |
| gen3-B (con los flags) | **98,7 %** | **30/32** |

- 5 criterios mejoran y 1 empeora. El que empeora (repregunta de la actividad en `moneda-precios-principiante-y-snorkel`)
  sale igual con los flags apagados y encendidos (atribución 3+3); es de gen-8.
- La latencia de la ronda no cambia (p50 4 s, p95 7 s). Los turnos con pase pasan de ~1,5 s a 3-8 s porque ahora
  contestan algo.

Queda de gen-3 el otro lado: cuando hay que pasar directamente (servicio privado, cambio de fecha urgente), el bot
OFRECE pasar en vez de hacerlo.
