# Marcador del Plan Gadea

Una línea por cada medida que cierra algo: un bloque o una tanda. Sirve para ver de un vistazo si mejoramos.

**Regla de parada:** si dos líneas seguidas no mueven el mecanismo del bloque, se para y se escribe «qué estamos haciendo mal» antes de
tocar nada más (`docs/plan/memoria.md`, norma 9). La última línea se copia en la sección 6 de la memoria.

**Cómo se rellena:**
- **Graves por vuelta:** media de 3 tiradas, cada una juzgada dos veces, con la referencia del juez congelada (se apunta su huella).
- **Mecanismo:** el indicador propio del bloque. Por ejemplo, para el 0,5: graves por tercera pregunta y por grupo; para el 1: clientes
  «a veces» y lecturas dobles.
- **Respuesta:** largo mediano y porcentaje de respuestas con pregunta, frente a la persona (119 caracteres, 23 %).

| Fecha | Versión o rama | Bloque | Mecanismo del bloque | Graves por vuelta (40) | Referencia del juez | Líneas de src | Tests sin IA | Llamadas de IA por turno | Respuesta: caracteres · con pregunta | Quién |
|---|---|---|---|---|---|---|---|---|---|---|
| 6-nov | PRE 0.61 | antes del plan | tercera pregunta: 22 graves en 3 vueltas | 21, 25 y 21 | 6-nov | 27.145 | — | ~4,1 | 703 · 77 % | Claude de Gadea (análisis por fases) |
| 10-nov | A: 5ee94c7b (`caln34-gadea`) | antes del 0,5 (con el 2a de Gadea a medias) | sin juez: misma pregunta 3 veces 4 · 2 · 4; grupo 5+ con enlace de pagar 5 · 6 · 4 | 27/25, 24/24, 23/24 → **24,5** | repo (`curada`, huella 0b6e2c7e3457) | 27.178 | — | 4,15 | 635 · 76 % | Claude de Álvaro |
| 10-nov | B: `bloque05-alvaro` 2e77937a | 0,5 (sin cerrar: falta el enlace solo con el origen conocido y la tanda) | sin juez: misma pregunta 3 veces **0 · 0 · 0**; grupo 5+ con enlace de pagar 2 · 4 · 3 (lo escribe el escritor) | 13/16, 14/18, 21/18 → **16,7** | la misma | 27.165 (−13) | 3.597 (suite) | 4,20 | 679 · 74 % | Claude de Álvaro (`docs/robustness/caln/medida-bloque05.md`) |

