# ARQ: el modelo interpreta, el código decide, el modelo redacta (desde el 22-oct)

Decisión de Gadea (22-oct, 01:00), con la propuesta que trajo de ChatGPT y el diagnóstico de Claude, que coinciden.
Sustituye a la fase GEN y a la parte de ORD que trataba el RAG (ord-1, ord-8, ord-9 y mej-9).

## Por qué

- **G10 de control con todo lo promocionado el 21-oct salió plano:** 85,4 % y 20/72, frente a 85,6 % y 23/72 de la
  tarde. Mejoraron 33 criterios, justo los de los arreglos, y empeoraron otros 33 por la variación del RAG.
- **De los 82 fallos (sin desfasados), el RAG omite un dato que tiene en el 67 %** (26 son listas: qué incluye,
  requisitos, documentos; 29 son otros datos). Inventa o supone en el 18 % y repregunta en el 5 %.
- **No es la búsqueda.** El dato llegaba al contexto en 18 de 18 casos (ord-0) y en 50 de 56 (15-oct).
- **Una sola llamada hace demasiado.** El escritor (Luna, sin razonamiento) recibe unos 13.600 tokens (todo el
  catálogo, todas las políticas, los enlaces, 8-12 documentos, el historial y el estado) y unas 50 reglas, muchas de
  ellas prohibiciones. Elige qué decir y recorta. Además, las reglas que ya cumple el código (moneda, origen, edades,
  grupo) también le llegan en texto, así que **se decide dos veces**; los arreglos por capas lo agravaron.
- **Ejemplo (ord-9, 21-oct):** el código ponía la lista exacta de lo que incluye, pero el RAG tenía el catálogo y la
  escribía igualmente, aunque se le pidiera que no.

## Principio

**El modelo solo hace lo que exige entender o escribir lenguaje natural.**
- El extractor y Jev **interpretan**: qué pregunta el cliente (sus intenciones) y sus datos.
- El **código decide**: qué planes valen, el precio en su moneda, las variantes por origen, qué incluye, los requisitos
  y las edades, con las reglas del negocio aplicadas.
- El **redactor redacta**, con solo los hechos de esa intención y el estilo de Coral, sin el catálogo entero ni las
  reglas que ya cumplió el código.
- **Lo que no encaja en una intención** (el destino, la vida marina, dudas abiertas) sigue yendo al RAG de hoy.

Un mensaje con varias preguntas (idea de Gadea: fragmentar) es una lista de intenciones: el código saca los hechos de
cada una y **una sola llamada redacta todo**. No hay N respuestas que juntar.

## Fases y tareas (Plan Coral, fase ARQ)

| Tarea | Qué | Horas |
|---|---|---|
| **arq-0a** | Integrar las ramas de Álvaro: mej-1d (13 interruptores menos), ord-3 (la tarifa en pricing.json) y la limpieza del veto (~620 líneas). Son la base limpia. | 1-2 h |
| **arq-0b** | **Banco fijo del RAG** (~40 preguntas con frases nuestras, de los tipos de fallo de G9/G10: listas, otros datos, invenciones, varias preguntas por mensaje) ×3. Pasa a ser el **indicador del RAG**; G10 solo al final de cada fase. Medir la línea base. | 3-4 h |
| ~~arq-0c~~ | **DESCARTADA (Gadea, 22-oct 12:05):** se queda Luna, sin compararlo con gpt-5-mini ni gpt-5.4-mini. Con los hechos por código da 110-116/120 en el banco fijo ×3 (base 100/120). | — |
| **arq-0d** | ¿Qué parte de los fallos de G10/G9 cae en mensajes con varias preguntas? Para saber cuánto puede dar la fragmentación. | 1 h |
| **arq-1a** | **Diseño:** el esquema de intenciones y, para cada una, los hechos que da el código (documento y tests del contrato). | 2 h |
| **arq-1b** | **Interpretación:** el extractor devuelve la lista de intenciones del turno (con su actividad y plan), con banco propio. | 3-4 h |
| **arq-1c** | **Constructor de hechos** por código, con las reglas ya aplicadas: precio y variantes (moneda, origen), qué incluye, requisitos y documentos, disponibilidad y horarios, edades, recogida y punto de encuentro. | 4-6 h |
| **arq-1d** | **Redactor de hechos:** con intenciones cubiertas, el escritor recibe solo los hechos y el estilo (sin el catálogo ni las políticas enteras); lo demás va al RAG de hoy. Detrás de un flag, medido en el banco por intención y con su ronda core. | 4-6 h |
| **arq-1e** | **La tarjeta de edades no se come las preguntas** (sale de arq-1d: «mi hijo de 12, ¿cuánto cuesta el minicurso, qué incluye y desde qué edad?» solo recibía la tarjeta). Si Jev ve más intenciones que la edad, contesta el redactor. HECHA 22-oct. | 1 h |
| **arq-2a** | Quitar del prompt del RAG las reglas que ya cumple el código (absorbe ord-1). | 2-3 h |
| **arq-2b** | Recortar el contexto por intención y usar el estado en vez del historial entero (absorbe mej-9). | 2-3 h |
| **arq-2c** | Retirar las capas que corrigen el texto después: la puerta del origen con sus variantes (ord-7), la lista añadida (ord-9) y los avisos que cubran los hechos (absorbe ord-8). Menos flags. | 3-4 h |
| **arq-3** | **Validación por código:** que la respuesta cubra todos los hechos (la lista completa, las dos variantes, la edad), y ver si sustituye parte del juez de grounding. | 3-4 h |
| **arq-4** | **G10 de control** al acabar la fase 1 y la fase 3. | 1,5 h cada uno |

## Cómo se mide y cuándo se va a Andrés

- Cada tarea, con el **banco fijo ×3** (antes y después) y, si toca la conducta, con su ronda core A/B y el juez con
  votos. Promociona Gadea.
- **A Andrés no se va hasta cerrar los gaps de G9/G10:** G10 de control ≥ 92 % y ≥ 40/72 diálogos, con G9 en la misma
  línea. G11 (gen-18) solo después.
- **Reglas de siempre:** sin parches ni regex nuevas, por causa, bancos con frases propias (G9/G10 solo para
  diagnosticar), nada más caro que gpt-5-mini sin permiso de Gadea, avisar en Coral antes de tocar ficheros compartidos.
  El que quede libre coge la siguiente tarea del orden; si alguien no está, sus tareas se liberan.

## Qué se deja de hacer

- Arreglos sueltos de una causa sobre el RAG y capas nuevas de posprocesado.
- Promocionar con la ronda core sola (está saturada) o con una pasada suelta de G10 (tiene mucho ruido).
- **Antes de ARQ queda pendiente de ord-9** (lo decidido la noche del 21): «insistir al RAG» ya no hace falta, porque en
  ARQ el redactor no recibe el catálogo. **Sí** se hace «DIVE TO HEAL incluido» (quitar `_sanitize_includes`, decisión
  de Gadea), en arq-1c.
