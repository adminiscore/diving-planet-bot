# ORD-0: por qué omite el RAG (medido el 21-oct)

**Qué se midió.** 18 omisiones del RAG sacadas de G10 y de G9 de control (ya exámenes de control, usados solo para
diagnosticar). Cada diálogo se repitió 3 veces en PRE con el código desplegado (`reproducir_juez_pre --banco
docs/robustness/ord/banco-omisiones.json --reps 3`, salida en `2026-10-21-omisiones.jsonl`, 147 turnos). En cada
caso se miró: (a) si el dato está en la base, (b) si llegó al contexto del escritor del RAG, (c) si la respuesta lo
dice en cada repetición y (d) si el cliente lo preguntó. Coste: céntimos.

## Resultado

| Clase | Casos | Cuáles | Qué lo arregla |
|---|---|---|---|
| **Búsqueda** (el dato no llega al contexto) | **0** | — | nada |
| **Redacción** (lo preguntó, está en el contexto y no lo dice en 3/3) | **4** | g10-029 (¿hay comida?), g10-058 (qué llevar al Advanced: el carné), g9-003 (¿se reserva online?: sin enlace ni qué incluye), g10-041 (cuántas inmersiones trae cada paquete) | 3 de 4 son la **puerta del origen** (abajo); ord-5 |
| **Azar** (lo dice en 1 o 2 de 3) | **3** | g10-023 (edad del minicurso 2/3), g10-069 (enlace 1/3), g10-013 (enlace 1/3) | ord-4 (temperatura 0), gen-19 |
| **Examen exigente** (pide algo que el cliente no preguntó o que no aplica) | **8** | g9-027, g9-065 (25-dic al preguntar por mañana o el jueves), g10-049 (cierre de las 4:30 para el 23 de julio), g10-027 (el descuento de grupo «no aplica a cursos» cuando preguntan por salidas), g9-021 (excepción de 500 inmersiones sin que diga su experiencia), g9-047 (formulario médico en un cambio de fecha), g9-034 (formulario médico al explicar el refresher), g10-010 (la cifra de la edad: el bot aplica bien la regla sin decir «10 años») | **ord-6**: decide Gadea qué se añade siempre |
| **Decisión de negocio** (criterio desfasado) | **1** | g9-006 (enlace a un colombiano: por decisión va al asesor sin enlace) | nada |
| **Ya no pasa** | **2** | g10-057 (carta del Referido, 3/3), g9-014 (entrada al Parque, 3/3) | la base de hoy (mej-2) |

**Frente al 15-oct** (56 fallos: búsqueda 3, redacción 34, azar 18): la búsqueda sigue sin ser el problema, la
redacción baja mucho y aparece lo que entonces no se medía: casi la mitad (8 de 18) es **exigencia del examen**.

## La puerta del origen (lo nuevo)
Cuando no sabe si el cliente sale de Cartagena o ya está en las islas, el bot pregunta el origen y **se calla todo
lo que depende de él**: el precio, qué incluye, si hay almuerzo y el enlace. Pasa en g10-029, g9-003, g10-041,
g10-013 (en el turno 4 vuelve a preguntar el origen después de haber dado el precio de Cartagena en el turno 3) y
g10-010. El examen además es contradictorio aquí: en g9-014 castiga dar el precio de Cartagena sin saber el origen
y en g10-029/g9-003 pide las inclusiones de Cartagena. Lo que contesta bien las dos cosas: **dar las dos variantes
cortas** (desde Cartagena X, con lancha y almuerzo; ya en las islas Y, recogida en el hotel, sin almuerzo) y
preguntar el origen para seguir. Así lo hizo en g10-023 (rep 0) y g10-010 (turno 4). Decisión de Gadea (ord-6).

## Otras cosas vistas (no son omisiones)
- **Contradicción en la base, ARREGLADA:** `policies.json` (photos_videos, ES y EN) seguía diciendo «no se realizan
  fotos ni videos en el minicurso», al revés de la decisión de Gadea del 21-oct (sí, voluntarias del instructor). Se
  corrigió la FAQ 98 en mej-2, pero no la política, que va siempre en el contexto. En g9-003 (rep 0) el bot dijo «en
  el minicurso no se hacen».
- **Bubble Makers** (niños de 8 a 10) está en la base como actividad, pero sin precio en el catálogo: el bot lo ofrece
  y dice «el precio no aparece» (g10-023). Pregunta para Gadea/Andrés: ¿se ofrece y a qué precio?
- **La tarjeta de edades se come la pregunta** (g10-049, turno 2): a «¿podemos ir todos en el mismo tour?» contesta
  con la lista de «qué puede hacer cada quien», y en inglés con «8 años».
- **Repreguntas** (gen-16): «¿ya tienes el Open Water?» a quien pide el curso Open Water (g10-069); «¿son buzos
  certificados?» a quien pidió «buceo certificado» (g9-065).
- **Origen** (gen-15): Ecohotel Las Palmeras no se reconoce como hotel de las islas (g10-069).
- **Inventa** (ord-1): «no hace falta imprimir nada» (g10-058, 3/3).

## Qué cambia en el orden
1. **ord-6 primero** (es una decisión, no código): las 8 de examen exigente más la puerta del origen.
2. **La puerta del origen** como tarea propia (P1) si Gadea elige las dos variantes: es la mayor parte de la
   redacción que queda.
3. **ord-4** (temperatura 0): barato y ataca el azar (3 de 18).
4. **ord-5** (revisor de completitud): para la redacción que quede tras la puerta del origen.
5. **ord-1 + mej-9**: siguen, pero el diagnóstico ya no apunta a que el prompt largo sea la causa principal.
