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
| 10-nov | `caln34-gadea` 5ee94c7b, con la vara nueva | 0 (partida en `panel-vara`, reloj del jueves 12) | — | 11/9, 11/10, 11/10 → **10,3** | 9-nov (huella 9326257c) | — | — | 3,96 | 564 · 67 % | Claude de Gadea |
| 10-nov | Luna sola (línea base: lo que lee el juez, sin nuestras piezas) | 0 (`panel-vara`, reloj del jueves 12) | — | 12/11, 11/11, 9/10 → **10,7** (+0,3: no cuenta) | 9-nov (huella 9326257c) | — | — | 1 | 330 · 32 % | Claude de Gadea |
| 10-nov | caln34 frente a 0,5+2a (`bloque2a-gadea`) | 0,5 y 2a en `panel-vara`, reloj del jueves 5, 6 juicios por lado | Rescue y tercera oferta del pase, caídos | 11/8, 10/12, 6/8 → **9,2** frente a 11/9, 9/5, 9/9 → **8,7** (−0,5, no cuenta) | 9-nov (huella 9326257c) | 2a: +38 | test_bloque2a | 3,99 → 3,93 | 571 · 67 % → 575 · 67 % | Claude de Gadea |
| 10-nov | caln34 frente a 0,5+2a, tanda de la vara (10 clientes que reaccionan por lado) | 0, 0,5 y 2a | graves del 2a: agencia al asesor y enlace sin hotel (bloque 4) | 0/1 → 2/2 de 10 (no cuenta) | 9-nov (huella 9326257c) | — | — | — | — | Claude de Gadea |
| 10-nov | 0,5+2a frente a bloque 1 (`bloque1-gadea` b16e3612) | 1 en `panel-vara`, reloj del jueves 5, 6 juicios por lado | sin juez: lecturas dobles 71 → 6 de 264 (las 6, la 2.ª de la nacionalidad, deliberada); estados que se separan 16 → 17 de 40; clientes «a veces» 18 → 11, «siempre» 1 → 2 | 11/9, 9/5, 9/9 → 8,7 frente a 8/10, 8/6, 9/8 → **8,2** (−0,5, no cuenta) | 9-nov (huella 9326257c) | 1: +86 −87 | suite 3628 | 3,93 → 3,70 | 575 · 67 % → 570 · 66 % (p50 3,52 → 3,83 s) | Claude de Gadea |
