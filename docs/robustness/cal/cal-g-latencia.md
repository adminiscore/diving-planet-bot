# CAL-G · latencia tras MOD (19-oct, Gadea con Claude)

Meta del plan: turno p95 ≤ 7 s. Fotos de `turn_metrics --from-run` de las rondas core del 18-19 oct (93 turnos, 32
diálogos; tiempo del bot, de que entra el mensaje a que sale la respuesta; "cliente" = el que mide el script):

| Ronda | p50 | p95 | RAG p50 / p95 | Reserva p50 / p95 | p95 cliente | Llamadas por turno |
|---|---|---|---|---|---|---|
| mod-C (revisor y reescritura en DeepSeek) | 2,29 | 6,03 | 4,18 / 7,57 | 1,25 / 2,04 | 6,4 | 4,18 |
| mod-E (+ RAG_NO_ADIVINA, respaldo DeepSeek) | 2,85 | 6,88 | 4,28 / 7,64 | 1,26 / 1,93 | 7,0 | 4,34 |
| mod-F (el flujo fuera de gpt-4, sin respaldo del extractor) | 3,25 | 7,05 | 4,34 / 7,55 | 1,81 / 3,67 | 8,0 | 4,32 |
| **mod-G2** (+ respaldo del extractor, resolutor Haiku) | **2,50** | **5,40** | 3,82 / 6,68 | 1,61 / 2,46 | 6,0 | 4,32 |
| **limpieza-1** (PRE de hoy: G2 + s4-25 paso 1) | 2,79 | **5,51** | 4,15 / 6,22 | 1,57 / 2,48 | 5,4 | 4,35 |

**La meta se cumple: p95 5,4-5,5 s** (antes de MOD, con gpt-4.1 de revisor, 6-7 s). El p50 global salta entre 2,3 y
3,2 s según cuántos turnos del RAG caigan en la mitad (45-47 de 93): por tipo de turno es estable.

Dónde se va el tiempo en limpieza-1 (por llamada: n en 93 turnos, p50 / p95):

| Pieza | Modelo | n | p50 | p95 |
|---|---|---|---|---|
| Respuesta del RAG | gpt-6-luna | 52 | 1,75 s | 2,76 s |
| Aviso al final | gpt-6-luna | 47 | 1,05 s | 1,64 s |
| Extractor | Haiku 5.5 (respaldo gpt-5.4-mini a los 2 s) | 92 | 0,83 s | 1,24 s |
| Acuse | gpt-5.4-nano | 51 | 0,63 s | 0,77 s |
| Revisor | DeepSeek | 48 | 0,50 s | 0,83 s |
| Reescritura / pregunta sola | DeepSeek | 43 / 44 | 0,46 / 0,39 s | 1,08 / 1,00 s |

Lo que queda por mirar si hiciera falta bajar más: los turnos del RAG (p95 6,2-6,7 s) son respuesta de Luna + aviso al
final (también Luna, en serie) + revisor; la reescritura y la pregunta sola ya van en paralelo con la búsqueda. El
respaldo del extractor (gpt-5.4-mini a los 2 s) cortó la cola de Haiku por OpenRouter: los turnos de reserva p95 3,67 →
2,46 s. **CAL-G: cumplida sin cambios; vigilarla en G9.**
