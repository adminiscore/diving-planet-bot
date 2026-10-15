# Diagnóstico: ¿por qué fallan los 73 casos del examen ex-10? (15-oct-2026, Gadea con Claude)

Pregunta de Gadea: sin regex, con Luna y el revisor de gpt-4.1, ¿qué nos falla? ¿Por qué un examen oculto nuevo
volvería a fallar después de CAL? Esto NO arregla nada: mide el porqué, para que CAL ataque la causa.

Ficheros: `fallos-por-turno-ex10.json` (cada fallo con el turno y la pieza que lo escribió, `scripts/fallos_por_turno`),
`repeticiones-2026-10-15-ex10-completa.jsonl` (los turnos del RAG repetidos en PRE, 2 veces, con el CONTEXTO exacto que
vio el modelo) y `por-que-falla-el-rag-2026-10-15-ex10-completa.json` (el veredicto de cada fallo,
`scripts/investiga_fallos_rag.py`, verificador gpt-4.1 a temperatura 0).

## 1. Quién escribe el turno que falla

| Pieza | Fallos |
|---|---|
| **RAG** (responde preguntas con la base) | **56 de 73 (77 %)** |
| Flujo de reserva (preguntas de la reserva) | 10 |
| Sin cita (criterio sobre toda la conversación) | 4 |
| Escalado / deflexión | 3 |

El problema no es el regex ni el flujo: **es cómo el RAG construye su respuesta.**

## 2. ¿Le llegaba el dato al RAG?

Repitiendo los 45 turnos de esos 56 fallos dentro de PRE, con su historial real:

| Veredicto | Fallos | Qué significa |
|---|---|---|
| **Redacción** | **34** | El dato ESTABA en el contexto y el modelo no lo usó (las dos repeticiones fallan igual) |
| **Azar** | **18** | El dato estaba; unas veces lo usa y otras no (la temperatura es 0,3) |
| Búsqueda | 3 | El dato no llegó al contexto |
| Fuera | 1 | Dependía de algo que el RAG no puede saber |

- **El dato estaba en el contexto en 50 de 56 (89 %)**; parcial en 2; no estaba en 4.
- **37 de 56 fallan de forma CONSISTENTE** (las dos repeticiones), 13 pasan en las dos (el fallo fue azar), 6 una sí y otra no.
- **No es ruido ni falta de datos: con la información delante, el modelo no la aplica.** Mejorar la búsqueda o la base
  arreglaría como mucho 4 de 56.

## 3. Por qué el modelo no aplica lo que tiene delante (mecanismos)

Leídos los 34 de redacción y los 18 de azar (columna `mecanismo` del JSON), salen cuatro patrones:

1. **Contesta la pregunta literal y no aplica las reglas transversales.** Las reglas que afectan a casi toda respuesta
   de precio —moneda según nacionalidad, grupo mixto en USD, preguntar el origen antes de un precio— están en el
   contexto (catálogo y políticas, siempre presentes) pero el modelo no las aplica: 11 de moneda en redacción, el
   grupo mixto "ignorado aunque está explícito en el contexto", "asume el origen sin preguntar".
2. **No usa lo que ya dijo el cliente** (historial): asume Cartagena cuando dijo que estaba en las islas, repregunta
   fechas ya dadas, olvida el acompañante, asume el año.
3. **No conecta implicaciones** que un asesor humano haría: "el Open Water son 2 días y te vas mañana al mediodía → no
   da tiempo"; "Barú no son las Islas del Rosario"; "refresher + buceo certificado pueden ir juntos".
4. **Se queda corto**: responde una parte de una pregunta con varias (pide almuerzo y descuentos → solo almuerzo).

## 4. Las causas de diseño detrás

1. **Una sola llamada hace demasiado.** El RAG recibe un prompt de ~3.600 tokens con **50 reglas (27 prohibiciones,
   8 "siempre")** + ~10.000 tokens de contexto (catálogo, 34 políticas, 8 fragmentos) + el historial + el estado, y en
   esa misma llamada tiene que entender la pregunta, decidir qué reglas aplican y redactar en tono WhatsApp breve. Las
   reglas compiten entre sí y gana lo que más pesa en el prompt: no inventar y ser breve ("frases cortas", "una o dos
   frases, sin alargarte").
2. **Presión asimétrica.** Cada arreglo de estas semanas añadió una PROHIBICIÓN; el revisor solo comprueba que no
   invente, nunca que esté COMPLETO. El sistema castiga decir algo mal y nunca castiga omitir: el modelo aprende que
   decir menos es más seguro. Es justo el grupo más grande de fallos.
3. **Las reglas de negocio viven como prosa, no como procedimiento.** La moneda, el origen antes del precio o el grupo
   mixto son reglas DETERMINISTAS (dependen del estado: nacionalidad, origen, reparto), pero se le piden al modelo como
   texto entre otras 49 reglas. El código ya sabe la nacionalidad y el origen; el precio correcto se puede calcular, y
   hoy se deja a que el modelo lo deduzca.
4. **Nadie hace la lista de "qué tengo que contestar".** No hay un paso que saque los puntos de la pregunta (y las
   implicaciones obvias) antes de escribir, ni uno que compruebe después que están todos.
5. **Temperatura 0,3** en la respuesta: 18 de 56 fallos son azar (con el mismo contexto unas veces sí y otras no).

**Respuesta directa a la pregunta de Gadea:** con CAL tal como está planteada, si arreglamos los casos (añadiendo
reglas al prompt), un examen oculto nuevo volvería a fallar, porque cada regla nueva es una más entre 50 que el modelo
aplica a medias. Lo que hay que cambiar es el MÉTODO con el que el RAG responde, no añadir contenido.

## 5. Qué cambiaría (para CAL-A, B y C), sin regex ni parches

| Causa | Cambio de diseño |
|---|---|
| Una llamada hace demasiado | **Responder en dos pasos:** (1) un PLAN barato: qué pregunta el cliente (cada punto), qué reglas de negocio aplican a esos puntos con el estado actual, qué datos faltan; (2) la REDACCIÓN contesta ese plan punto por punto con el contexto. |
| Presión asimétrica | **El revisor comprueba COMPLETITUD contra el plan** (¿están todos los puntos?), además de grounding. Dieta del prompt: cambiar prohibiciones por procedimientos positivos ("contesta cada punto con la base"); quitar la brevedad como regla, dejarla como estilo. |
| Reglas de negocio como prosa | **Lo determinista, en código:** el precio, la moneda (decisión de Gadea: sin nacionalidad → USD) y "sin origen no hay precio de un origen concreto" se calculan con el estado y se le dan al RAG ya resueltos ("precio a dar: X USD; falta el origen: pregúntalo"). El modelo redacta, no decide la regla. |
| Nadie hace la lista | Es el paso (1) del plan; incluye las implicaciones obvias (duración vs fechas del cliente, zona de buceo, combinaciones). |
| Azar | **Temperatura 0** (o muy baja) en la redacción; medir que no empeore el tono. |

Meta de comprobación: el banco de fallos (CAL-0) debe pasar CONSISTENTEMENTE (varias repeticiones), no una vez.
