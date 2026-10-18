# Fase MOD · mod-2 (extractor) y mod-3 (señales, acuse, notas, resolutor), 18-oct (Álvaro con Claude)

La familia gpt-4 se retira en enero (decisión de Gadea: fase MOD antes de G9). Cada pieza se mide con su banco frente
a candidatos sin razonamiento. Nada está promocionado: cada pieza pasa una ronda core A/B antes de cambiar. Lo que va
por OpenRouter (DeepSeek, Haiku) espera a mod-7, la decisión de Gadea sobre la privacidad de los datos reales.

Cada pieza tiene ya su propio ajuste de modelo (`config.py` y compose), todos con el valor de hoy:
`extractor_turno_model` (gpt-4.1-mini), y de `extraction_model` (gpt-4o-mini): `senales_model`, `red_extractor_model`,
`resolutor_model`, `acuse_model` y `notas_model`.

## mod-2 · el extractor principal (gpt-4.1-mini)

`python -m scripts.estabilidad_extractor --grupo diseño --pasadas 3 --modelo M [--flag …]`, banco ex0 (200 casos).

Decisiones de Gadea del 18-oct ("no se adivina nada que el cliente no haya dicho"):
- preguntar el precio de un producto es una duda: no elige la actividad ni dice que sea certificado (revoca la del
  14/27-sep, `EXTRACTOR_PRECIO_ELIGE`) → flag `PRECIO_NO_ELIGE`, que cambia a la vez las cuatro frases del extractor que
  hablan del precio. Apagar el flag viejo no bastaba: volvía un texto que chocaba con la regla de `activity` y el modelo
  dejaba de elegir también lo que sí elige (109 → 101 aciertos);
- "quiero bucear certificado" o "fun dives" no dicen que sea certificado: se confirma → flag
  `CERTIFICADO_SOLO_SI_LO_DICE` (quita la regla del código "certified_diving ⇒ is_certified");
- "desde Argentina" no dice la nacionalidad; "We would both" no dice cuántos son.
Las etiquetas de ex0 se pusieron al día: 8 frases de "bucear certificado" ya no esperan is_certified.

Con las etiquetas nuevas (aciertos / inventados / estable / p50):

| Modelo | Reglas de hoy | Con `PRECIO_NO_ELIGE` + `CERTIFICADO_SOLO_SI_LO_DICE` |
|---|---|---|
| gpt-4.1-mini (PRE) | 109 / 10 / 97,5 % / 2,1 s | 104 / 8 / 94,0 % / 1,8 s |
| deepseek/deepseek-v4.1-flash | — | 100 / **42** / 89,5 % / 1,6 s |
| anthropic/claude-haiku-5.5 | — | 106 / 7 / 98,5 % / 1,7 s (0 equivocados) |
| **gpt-6-luna** | — | **107 / 8 / 97,5 % / 2,1 s (0 equivocados)** |
| gpt-5.4-mini | — | 106 / 8 / 95,5 % / 2,0 s (2 equivocados) |

Con las instrucciones de hoy y las etiquetas viejas, los demás candidatos: gpt-5.4-mini 113/16, gpt-5.4-nano 101/8
(9 equivocados), gpt-6-luna 112/12 (3,1 s), qwen/qwen3.8-flash 110/46 (descartado). DeepSeek es muy sensible a la
redacción (11 inventos con las de hoy, 42 con las nuevas: rellena `is_colombian=false` y `last_dive=false`); Haiku se
queda entre 7 y 9 inventos y por encima del 97 % estable en todas las variantes. Luna, que con las reglas viejas inventaba 12 (certificado por pedir un paquete…), con las reglas coherentes de "no adivinar" acierta 107 (más que gpt-4.1-mini) y es igual de estable que Haiku. **Candidato: gpt-6-luna** (OpenAI directo: no depende de mod-7); Haiku, la alternativa si mod-7 lo permite.

Etiquetas dudosas para Gadea: "Un solo buzo avanzado" (¿elige actividad o solo dice su nivel?), "quería regalarle a mi
esposo una experiencia del buceo" (¿minicourse?), "I have my open water certificate and I'm still a beginner".

## mod-3 · las piezas de `extraction_model` (gpt-4o-mini)

| Pieza (banco) | gpt-4o-mini (PRE) | DeepSeek v4.1 Flash | Haiku 5.5 | gpt-5.4-mini | Candidato |
|---|---|---|---|---|---|
| Señales del enrutador (`battery_router_signals`, 34 válidas × 3) | 32 | 32, pero "¿qué pasa si llueve?" → pase por el tiempo | 24 (formato: `sensitive_topic: "true"`) | 29 (pierde `wants_human`, contacto, cancelación) | gpt-4o-mini, o DeepSeek ajustando "si llueve" |
| Acuse (`banco_acuse`, inventos reales / controles) | 6/40 · 0/25 | 3/40 · 0/25 (10 vacías) | 5/40 · 2/25 | **0/40 · 0/25** | gpt-5.4-mini |
| Notas (`scripts/mod3_notas.py`, positivos / negativos limpios) | 21/24 · 38/44 · 0,91 s | **22/24 · 41/44** · 0,94 s | 22/24 · 37/44 · 1,25 s | 19/24 · 44/44 · 1,13 s | DeepSeek |
| Resolutor (`scripts/mod3_resolutor.py`, bien 3/3 · valores equivocados) | 30/30 · 0/90 | 26/30 · **6/90** ("¿dónde queda el muelle?" → cartagena) | 30/30 · 0/90 · 1,23 s | 28/30 · 0/90 (se abstiene) | gpt-5.4-mini o Haiku |

En las señales, r07/r08/r09 no los acierta ningún modelo: piden comparar cursos concretos y el enum de
`comparing_options` del ROUTING_TOOL solo tiene `padi_course` (fallo del instrumento, fuera del recuento). La red del
extractor (`red_extractor_model`) solo actúa si el extractor principal falla: sigue lo que se decida en mod-2.
