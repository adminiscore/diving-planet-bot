# Fase MOD · modelos sin la familia gpt-4 (decisión de Gadea, 18-oct)

La familia gpt-4 se retira en enero. Cada pieza que la usa se mide con su banco frente a candidatos sin razonamiento,
recientes y más baratos, y se promociona tras una ronda core A/B. Plan y reparto: Plan Coral, fase MOD.

## Hecho

- **G3-05, la pregunta sola** → DeepSeek v4.1 Flash (12 mensajes × 3: 36/36, 0,45 s). Decisión de Gadea.
- **mod-1, el revisor (gpt-4.1)** → candidato DeepSeek v4.1 Flash + `juez_v3_luna`: deja pasar 2 de 10 inventos
  (gpt-4.1 5/10) y aprueba 45/54 verdades (48/54), ~30 veces más barato. Detalle: `docs/robustness/juez/mod-1/`.
  Falta la ronda core (C).

## mod-4 · la reescritura de la consulta (gpt-4o-mini), 18-oct

`python -m scripts.mod_reescritura <salida.json>`: los 158 turnos de seguimiento de la ronda CAL-F (solo VISIBLES) que
hoy se reescriben, con cada candidato (`docs/robustness/mod/mod4-reescritura.json`).

| Modelo | p50 | p90 |
|---|---|---|
| gpt-4o-mini (PRE) | 0,84 s | 1,08 s |
| **deepseek/deepseek-v4.1-flash** | **0,64 s** | 0,85 s |
| gpt-5.4-mini | 1,12 s | 1,38 s |
| gpt-6-luna | 1,37 s | 1,65 s |

Leídas a mano (muestra de 14): DeepSeek y Luna nombran el asunto con lo que se sabe de la conversación (lo que pedía
CAL-D) y gpt-4o-mini a menudo deja una consulta sin contenido ("y el menor tiene 6" → "¿El menor tiene 6 años?"; "ok ya
he buceado con ustedes" → "¿He buceado ya con ustedes?"). DeepSeek a veces alarga de más ("¿Qué bono adicional hay
para 2 buzos certificados colombianos que quieren…"). Candidato: DeepSeek (más rápido y mejores consultas). OJO:
`OPENAI_MODEL` mueve también el resumen y el detector de idioma: medirlos antes de cambiarlo (o separar el modelo de la
reescritura). Veredicto en una ronda core.

## mod-4 · el resumen y el detector de idioma (gpt-4o-mini), 18-oct

`python -m scripts.mod_resumen_idioma <salida.json>` (`docs/robustness/mod/mod4-resumen-idioma.json`): el resumen de las
8 conversaciones VISIBLES más largas de CAL-F y de los 10 casos del banco de inyecciones (r6-2), con la regla de
seguridad de la memoria; el detector de idioma con 40 mensajes cortos o ambiguos.

| Modelo | Resumen p50 | Idioma p50 | Idioma distinto de gpt-4o-mini |
|---|---|---|---|
| gpt-4o-mini (PRE) | 1,33 s | 0,75 s | — |
| **deepseek/deepseek-v4.1-flash** | **1,05 s** | **0,63 s** | 4: "Hola! My partner and I want to dive" → en y "Obrigado" → en (los dos bien: lo segundo es la regla de Gadea, otro idioma → inglés); "no" y "Cartagena 2 pax" (ambiguos) |
| gpt-5.4-mini | 1,16 s | 0,94 s | 6 ("minicurso" → en, mal) |
| gpt-6-luna | 1,64 s | 1,01 s | 3 |

Resúmenes de las inyecciones, leídos uno a uno (gpt-4o-mini frente a DeepSeek): DeepSeek marca "sin verificar" en todo
lo que el cliente afirma (gpt-4o-mini lo olvida en "ya pagué por transferencia", el enlace de pago falso y el código
CORAL2024) y nombra los intentos de manipular ("repite palabra por palabra", "traduce tus instrucciones", "ignora las
instrucciones"), donde gpt-4o-mini devolvía un resumen vacío o roto ("Resumen actualizado:"). DeepSeek añade una
coletilla ("no se han dado datos de grupo…"): más larga, no dañina.

**Candidato para las tres piezas de mod-4 (reescritura, resumen, idioma): DeepSeek v4.1 Flash.** Falta la ronda core
(la reescritura es la que más pesa en ella; el resumen salta cada 24 mensajes).

## mod-6 · la transcripción de las notas de voz (gpt-4o-mini-transcribe), 18-oct

`python -m scripts.mod_transcripcion <carpeta_audios> <salida.json>` (`docs/robustness/mod/mod6-transcripcion.json`): 10
notas de voz SINTÉTICAS (tts-1; en el repo no hay audios de clientes) en es/en con importes, fechas, hoteles y el
muelle; el mismo camino que el bot, sin pista de idioma.

| Modelo | Error por palabra (WER) | p50 |
|---|---|---|
| **gpt-4o-mini-transcribe (PRE)** | **3,7 %** | 0,53 s |
| gpt-transcribe | 5,7 % | 0,58 s |
| whisper-1 | 7,2 % | 1,10 s |

Todos fallan en "Muelle de la Bodeguita" ("muelle la Destesa / La Destreza"). Siguientes: (1) confirmar si
gpt-4o-mini-transcribe entra en la retirada de enero (si no, se queda: es el mejor); (2) probar a pasar un `prompt` con
el vocabulario del negocio (Bodeguita, Majagua, Isla Grande, minicurso…), que la API de transcripción admite.

## mod-8 · las herramientas de medida en gpt-4.1

`banco_fallos` ya puede verificar con un modelo de OpenRouter (`_verificar` va por el cliente del bot) y tiene
`--comparar-verificador <modelo>`: juzga las mismas respuestas con los dos y da la coincidencia. Medida pendiente
(cuando PRE no esté en una ronda).
