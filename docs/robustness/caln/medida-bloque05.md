# Bloque 0,5 (Plan Gadea): la medida del cierre (9 y 10-nov)

**Ficha.** Bloque 0,5 · mecanismo: qué preguntar se decide en una tabla antes de escribir (P11, el escritor no recibe órdenes
de preguntar en la reserva), el pase en una función (`pasar_a_persona`, de Gonzalo) y el grupo de 5 o más o con una parte sin
enlace reserva con un asesor (P9/P10) · familias: tercera pregunta y grupo · **src −13 líneas** frente a 5ee94c7b (+514 −527 en
24 ficheros) · bancos sin IA: `tests/test_que_preguntar.py` (las 4096 combinaciones ×2) y los de P9/P10 · contador:
`escritor_pregunta` en [TURN_METRICS].

**Cómo.** A = 5ee94c7b (`feature/caln34-gadea`, antes del bloque), B = 2e77937a (`feature/bloque05-alvaro`). Los dos con
`reproducir_juez_pre --codigo-local --reps 1`, a la vez y a la misma hora (22:58-23:46), base y modelos de PRE. Panel fijo
(`panel-graves.json`, 40 clientes) ×3 por lado, cada tirada juzgada dos veces con `juez_claude` (Opus 5.5, referencia del repo,
la misma en A y en B; la del 9-nov, c7c7268a, sigue en local de Gadea). 0 turnos con errores de la IA salvo 1 de 157 en la 3.ª
de B (Luna 503). Gasto de OpenRouter: 1,48 $. Un primer intento a las 22:00 no vale: OpenAI estaba sin saldo.

## Bancos (por código)

| Banco | A | B | Nota |
|---|---|---|---|
| caln39 (el plan que pide o rechaza) | 13/13 | 13/13 | |
| caln35 (cómo reserva cada cliente) | 22/22 | 22/22 | |
| graves (55) | 52/55 | 50/55 | g-tres-dias-plan: B pasa al grupo de 5 con el asesor (P9) y el banco aún pide el enlace: **el banco está desfasado**. s04j-293 ×4: A 3/4, B 4/4 (azar) |

## Panel: clientes con grave (de 40)

| Tirada | A j1 | A j2 | B j1 | B j2 |
|---|---|---|---|---|
| 1 | 27 | 25 | 13 | 16 |
| 2 | 24 | 24 | 14 | 18 |
| 3 | 23 | 24 | 21 | 18 |
| **Media** | **24,5** | | **16,7** | |

- **B − A = −7,8 clientes** (norma 8: cuenta si es de 4 o más). Ciegos: 15,8 → 12,2 (−3,7).
- Tercera vez, según el juez: 5,3 → 0,7. Grupo o asesor, según el juez: 6,2 → 4,0.
- visto-6927 («el miércoles ya cerró»), mal en las dos primeras de B y en ninguna de A: repetido ×4, A lo dice 2 de 4 y B 1 de 4.
  Es de horas y fechas (bloque 3), no del 0,5.

## El mecanismo, sin juez (`C:/t/medidas/b05/mecanismo.py`)

| | A (3 tiradas) | B (3 tiradas) |
|---|---|---|
| La misma pregunta de la reserva en 3 respuestas | 4 · 2 · 4 | **0 · 0 · 0** |
| Grupo de 5 o más con el enlace de pagar | 5 · 6 · 4 | 2 · 4 · 3 |
| Turnos con `escritor_pregunta` (de 157) | — | 7 · 5 · 6 |

## Marcador

| | Llamadas de IA por turno | Caracteres (mediana) | Con pregunta | Latencia p50 · p90 |
|---|---|---|---|---|
| A | 4,15 | 635 | 76 % | 4,25 · 6,03 s |
| B | 4,20 | 679 | 74 % | 4,13 · 6,45 s |

## Lo que no cierra el bloque

1. **El grupo no queda a cero.** P9 está en la tarjeta del cierre de la reserva; en los grupos que siguen recibiendo el enlace
   (ciego-a03, a05, a10, visto-6938) lo escribe **el escritor**, en un turno `rag` («¿cómo reservamos todos juntos?»). El
   enlace sigue teniendo dos dueños: es la pieza «el enlace solo lo pone el código» (sin dueño), no un caso.
2. **La oferta del pase la repite el escritor:** «Would you like me to connect you with an advisor?» tres turnos seguidos
   (visto-6940, en A y en B). No pasa por la tabla de qué preguntar: el pase lo decide el escritor y no el código (bloque 4).
3. El contador confirma que el escritor sigue preguntando en la reserva (5-7 turnos de 157): el corrector del compositor se
   queda (norma 6).
4. Respuestas más largas en B (+44 caracteres de mediana), lejos de los ~120 decididos.
5. Falta la tanda.
6. **Punto de parada:** B 16,7 por vuelta, en el borde de 16, con el 2a sin terminar (la meta tras el 0,5 y el 2a es 8-11).
