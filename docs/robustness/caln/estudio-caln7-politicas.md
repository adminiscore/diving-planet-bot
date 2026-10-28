# CALN-7 · El escritor dice lo que la política exige — estudio (28-oct)

Tarea nueva de Gadea (28-oct): «cógelo tú como una nueva tarea y así nos cercioramos de que esta causa la podemos
solventar en su mayor medida».

## 1. De dónde sale

Los fallos que se repiten ronda tras ronda (≥ 4 de 5 rondas del golden visible, integra5 → caln3-B; ≥ 3 de 4 de la
rotativa 2026-10-26-13): 34. La clase más grande, **17**, es el escritor que no dice lo que la política exige
(formulario médico, «¿hace cuánto no buceas?», fotos, formularios de niños, plan de acompañante, condiciones del
descuento por equipo, «el minicurso no certifica», la comida desde las islas, la carta del Referido, DIVE TO HEAL, el
tiempo de la teoría). Las demás: repreguntas 6 (CALN-3b y el lector del grupo), precio según el origen 4 (CALN-3), el
enlace del colombiano 3 (era el criterio: arreglado en el juez, e1384f1), el idioma del enlace 2.

## 2. Paso 1: ¿el dato llegaba al escritor?

Se reprodujo cada caso con el código de hoy (caln-gadea e1384f1) espiando la llamada del escritor
(`rag_agent.generar_con_respaldo`): en cada turno, si el dato estaba en el prompt del sistema, en el contexto de la
pregunta (documentos recuperados y hechos) y en la respuesta. Script en el scratchpad de la sesión (no en el repo).

- **Todas las políticas van SIEMPRE en el prompt del sistema** (EX-RAG-1, con el catálogo): el escritor las «tiene» en
  todos los turnos, en un texto muy largo. Lo que cuenta es si venían en el contexto de la pregunta.
- De los 17: **10 ya lo dicen** con el código de hoy (lo de ayer y hoy, o el azar del escritor); **7 tienen el dato en el
  contexto y no lo dicen**; ninguno «sin el dato en ningún sitio».

Mirando los 7 uno a uno, las causas son de CÓDIGO (qué hechos se dan), no del prompt:

| Caso | Causa | Arreglo |
|---|---|---|
| Especialidad: «4 horas de teoría» (rot-012) | La ficha lo tiene en `preparation_*` y los requisitos solo leen `requirements` | Los requisitos de un servicio llevan su preparación (solo cuando se preguntan requisitos; en el catálogo de todos los turnos se descartó el 17-oct) |
| Buceo adaptado: formulario médico (rot-024) | Sin actividad elegida, los requisitos generales eran el seguro y qué llevar | `hechos_sin_actividad` lleva también la política del formulario médico (`medical_restrictions`, que dice a qué aplica) |
| Refresher: formulario médico (golden) | El extractor da el buceo certificado de la conversación y la regla de arq-1n (el buzo que necesita el repaso hace el refresher) se miraba DESPUÉS | La regla vale también con la actividad del extractor; si el cliente PREGUNTA por el buceo certificado, se le contesta de eso (arq-1n) |
| Descuento por equipo en el minicurso (rot-029) | Pregunta general («¿algún descuento?»); arq-7b no añade el de equipo propio porque su «¿ya lo dijo?» cuenta palabras comunes («discount», «diving») | Comparar solo las palabras propias de cada elemento: va con Gonzalo (Q05, pregunta genérica o concreta), toca lo mismo |
| Plan de acompañante (rot-022) | «Dos solo acompañan» sin pregunta: nadie explica el plan | Lo sabe el código del grupo → Álvaro (lector del grupo) |
| Recogida en Isla Grande (golden) | Información que el cliente necesita y no pregunta | Avisos (pendiente de estudiar) |
| Edades de los niños (rot-010) | Dice «8–10» pero no la mínima del snorkel en cifra ni que la logística la confirma un asesor; contesta en inglés a un cliente en portugués | Pendiente |

## 3. Medida de los tres arreglos de código

Banco `docs/robustness/caln/banco-politicas.json` (3 casos + 2 de control), ×2, `puntua_banco_edades`, A = caln-gadea
e1384f1, B = con los arreglos (--codigo-local): **4/10 → 10/10** (los tres 0/2 → 2/2; los controles 2/2 = 2/2).

Lo que queda por ver: las respuestas de requisitos son largas por la lista de arq-7b («También necesitas:»), y a veces
repiten algo que el escritor ya dijo con otras palabras (el carné del buzo en el refresher): es la misma comprobación
«¿ya lo dijo?» del caso del descuento.

## 4. Estado (28-oct, 11:45)

| Caso | Estado |
|---|---|
| Especialidad: 4 h de teoría | ✅ 818f820 (los requisitos llevan la preparación de la ficha) |
| Buceo adaptado: formulario médico | ✅ 818f820 (los requisitos sin actividad llevan el formulario) |
| Refresher: formulario médico | ✅ 818f820 (el buzo que necesita el refresher recibe sus requisitos) |
| Bubble Makers: la logística la confirma un asesor | ✅ 71f9b19 (`lo_confirma_un_asesor` en los hechos del plan; banco 1/2 → 2/2) |
| Descuento por equipo en el minicurso (rot-029) | ✅ Gonzalo, paso 3 de CALN-3 (cada descuento por sus palabras propias) |
| Plan de acompañante (rot-022) | Álvaro, después del lector del grupo |
| Recogida en Isla Grande («¿cuenta como Islas del Rosario?») | NO se toca: el aviso `recogida-en-hotel-islas` salta con el origen sabido; aquí no se sabe dónde se aloja y la pregunta es del lugar. Un disparador nuevo para un solo diálogo del golden sería sobreajuste. |
| Edades de los niños: la mínima del snorkel en cifra | Lo dice («cumple la edad mínima») sin la cifra; el criterio es estricto. Sin cambio. |

Banco banco-politicas (6 casos) ×2: 4/10 → 12/12 entre los dos arreglos.
