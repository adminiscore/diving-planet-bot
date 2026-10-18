# MOD-1 · El revisor de la respuesta (juez de grounding) fuera de gpt-4.1 (18-oct)

La familia gpt-4 se retira en enero (decisión de Gadea: fase MOD). Banco: los 142 juicios REALES de PRE etiquetados con
Gadea en s4-33 (`docs/robustness/juez/s4-33/`), grupo de DISEÑO, 2 pasadas, código del revisor de hoy (pide la cita
antes de rechazar, `2e30547`). En local, `python -m scripts.banco_juez_reales --grupo diseño --modelo <m>`.

| Revisor | Inventos que deja pasar (mejor 0) | Verdades que pasan | Aprobadas que pasan | Mediana / p90 | Entrada $/M |
|---|---|---|---|---|---|
| **gpt-4.1 (PRE hoy)** | 5/8 | 24/30 | 43/43 | 3,38 / 5,93 s | 2,00 |
| **deepseek/deepseek-v4.1-flash** (OpenRouter, EE. UU.) | 4/8 | 22/30 | 42/43 | 3,16 / 6,06 s | 0,065 |
| anthropic/claude-haiku-5.5 (OpenRouter, otros proveedores) | 5/8 | 28/30 | 41/43 | 3,71 / 5,31 s | 0,10 |
| gpt-5.4-mini (sin razonamiento)* | 1/8 | 18/30 | 42/43 | 3,96 / 6,08 s | — |
| gpt-6-luna | 0/8 | 15/30 | 39/43 | 3,85 / 6,38 s | 0,10 |
| gpt-6-luna + `juez_v3_luna` (s4-33)* | 1/8 | 21/30 | 37/43 | 4,16 / 5,97 s | 0,10 |

\* Un juicio de estas dos corridas dio 429 (el crédito de OpenAI se agotó un momento) y el revisor deja pasar la
respuesta cuando falla: su cifra de inventos puede estar 1 por debajo de la real.

Lectura: hay un tira y afloja entre cazar inventos y dejar pasar las verdades (rechazar una verdad = reescritura y, a
veces, "no lo tengo"). **DeepSeek iguala a gpt-4.1** (un invento menos que deja pasar, dos verdades menos, una aprobada
menos) por unas 30 veces menos dinero y la misma latencia. Haiku deja pasar casi todas las verdades pero caza tan poco
como gpt-4.1. gpt-5.4-mini y Luna cazan casi todo pero tumban muchas verdades (como en s4-33).

Siguiente: confirmar DeepSeek frente a gpt-4.1 en el grupo CIEGO (sin tocar nada) y, si se mantiene, ronda core A/B
con `GROUNDING_V3_MODEL=deepseek/deepseek-v4.1-flash`. Antes de producción, la decisión de privacidad de OpenRouter
(mod-7).

## Grupo ciego y la adaptación de s4-33 (18-oct, tarde)

Ciego (sin tocar nada): gpt-4.1 inventos 0/2, verdades 24/24, aprobadas 53/53, 2,04 s; DeepSeek tal cual 0/2, **17/24**,
52/53, 1,86 s; Haiku 5.5 **2/2**, 17/24, 53/53 (descartado). DeepSeek tal cual tumbaba frases que no son datos del
negocio ("el equipo te confirma la disponibilidad", "no puedo darte el total por el chat", "la duración la confirma un
asesor", "no lo tengo a la mano"): justo lo que arregla la aclaración de s4-33 (`juez_v3_luna`, la tercera marca "NO ES
DATO"; el texto no es de Luna, vale para cualquier modelo).

| Revisor | Diseño: inventos / verdades / aprobadas | Ciego: inventos / verdades / aprobadas | Total inventos que pasan | Total verdades | Mediana |
|---|---|---|---|---|---|
| gpt-4.1 (PRE) | 5/8 · 24/30 · 43/43 | 0/2 · 24/24 · 53/53 | 5/10 | 48/54 | 2,0-3,4 s |
| **DeepSeek v4.1 Flash + `juez_v3_luna`** | 2/8 · 28/30 · 42/43 | 0/2 · 17/24 · 53/53 | **2/10** | 45/54 | **2,0 s** |

DeepSeek con la aclaración caza más inventos (deja pasar 2 de 10 frente a 5) y tumba 3 verdades más de 54; ~30 veces
más barato y algo más rápido. Siguiente: ronda core A/B con `GROUNDING_V3_MODEL=deepseek/deepseek-v4.1-flash` y
`JUEZ_V3_LUNA=true` frente a PRE.
