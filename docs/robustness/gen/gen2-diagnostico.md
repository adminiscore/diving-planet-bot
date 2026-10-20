# gen-2: «inventa o da por hecho» (20-oct-2026)

Fase GEN de Plan Coral. En G9 aparecían 15 fallos de «sin invenciones». Este diagnóstico usa un banco propio,
`dialogos-gen2.json`: 12 diálogos, uno por cada clase de invento que salía en los motivos del juez, sin abrir el
examen. Se pasó 2 veces con `reproducir_juez_pre --banco` contra PRE `9e2ff07`, que ya lleva encendidos los flags de
gen-3. Salida: `2026-10-20-gen2-base.jsonl`.

## Bien

| Clase | Resultado |
|---|---|
| Género del cliente («somos colombianos», «me interesa bucear») | sin femenino ni masculino inventado, 4/4 |
| Servicio no dicho («ya hice la reserva, ¿llevo equipo?») | «el equipo está incluido», sin nombrar un plan, 2/2 |
| Precio tras un pase médico | da el precio sin inventar que el asesor resolvió algo, 2/2 |
| Open Water en un día | «no se puede: 2 días con noche en las islas», 2/2 |
| Recogida sin decir el origen | da los dos horarios y pregunta desde dónde sale, 2/2 |

## Mal: tres causas globales

1. **Abre con «¡Claro que sí!» antes de un «no» o un «depende»** (5 de 24 respuestas).
   - Ejemplos: «¡Claro que sí! … La recogida no es en el hotel», «¡Claro que sí, puedes quedarte! … el regreso en otra fecha no está incluido», «¡Claro! … no puedo confirmarte que acepten efectivo».
   - El tono le pide muletillas («¡Claro que sí!» está en la lista) y el modelo abre con ellas sin mirar la respuesta.
   - En G9 esto fue un invento cuando el resto también fallaba («¡Claro!» a pagar en el muelle, «¡Claro que sí!» a una recogida en Cartagena).
   - Arreglo propuesto: una regla del prompt del RAG. Si la respuesta es «no», «depende» o «solo en algunos casos», no se abre con una afirmación: se empieza por la respuesta.
2. **La base dice a medias lo que es «no».**
   - **Barú:** la FAQ 105 y el aviso `solo-operamos-en-rosario` dicen que no operamos allí, pero la política de recogida (`island_pickup`) no lo menciona. El bot contesta «no tengo confirmado si podemos recogerte en tu hotel de Barú, ¿te paso con un asesor?»; en una de las dos pasadas, el aviso de Barú sale después y se contradice con eso.
   - **Recogida en un hotel de Cartagena:** la base solo dice «no incluye transporte terrestre al muelle». No dice «no recogemos en hoteles de Cartagena», y el bot duda o pasa a un asesor.
   - Arreglo propuesto: decirlo en la política (`island_pickup`, `meeting_point`). Son datos que ya están, escritos donde la búsqueda los encuentra; nada nuevo.
3. **El dato no llega al modelo.**
   - «¿Puedo pagar en efectivo en el muelle?» → «no tengo confirmado». Las FAQ 114 y 115 dicen que colombianos y residentes pueden dejar el 50 % para pagar presencial (tarjeta o efectivo) y que el resto paga el 100 % online.
   - «¿Cuántas noches?» → 1 de 2 veces «la información no especifica cuántas noches», aunque la ficha dice «al menos 1 noche».
   - Hay que medirlo con `rag_piezas` para ver si falla la búsqueda o la redacción.

Visto de paso: en algunos primeros mensajes, tras la respuesta se añade el menú entero («Cuéntame, ¿qué te gustaría
vivir con nosotros?…»).
