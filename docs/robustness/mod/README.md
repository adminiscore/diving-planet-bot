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
