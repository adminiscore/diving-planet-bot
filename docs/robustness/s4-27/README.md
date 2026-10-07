# s4-27 — el plan concreto en el contexto del RAG (7-oct, Gonzalo)

**El caso.** `precio-desde-islas-vs-cartagena`, turno 5: una pareja de buzos ya en las islas pregunta "¿Me puedes
decir el precio de las 2 inmersiones? Desde ese hotel?". El plan existe (*Salidas de Buceo - 2 inmersiones (1 día,
ya en las islas)*: 124 USD online), pero el bot ofrecía el **paquete de 3 inmersiones** (2 diurnas + 1 nocturna,
188 USD) y decía que "desde las islas no ofrecemos solo 2 inmersiones sueltas".

## Dónde se pierde (escalón barato, primer paso del relevo)

| prueba | cómo | 124 USD |
|---|---|---|
| PRE hoy, conversación entera | `reproducir_juez_pre … --reps 3` → `precio-desde-islas-pre-hoy.jsonl` | **0/3** (paquete de 3) |
| la pregunta sola, historial limpio | `rag_piezas`, caso `dos-buceos-desde-islas` (nuevo) | 3/3 |
| la pregunta con el historial REAL de PRE | caso `dos-buceos-desde-islas-historial-real` (nuevo) | 1/3 (y 2 lo niegan) |
| historial real + el plan puesto en el estado | caso `dos-buceos-desde-islas-ficha-forzada` (`selected_service`) | **3/3** |

- **No es el catálogo:** el prompt del sistema trae "Salidas de Buceo - 2 inmersiones (1 día, ya en las islas): 124
  USD" en las cuatro pruebas.
- **La búsqueda trae lo mismo en las cuatro:** las fichas de los paquetes de las islas (3, 4, 4 mixto, 5, 7 y 9), porque
  sus itinerarios repiten "2 inmersiones en aguas abiertas"; la ficha del plan de 2 inmersiones no entra en el top-8.
- **Lo que inclina al modelo es el historial real** (el bot ofrece "los paquetes" desde las islas en cada turno) junto
  con esas fichas. Con el plan nombrado en el contexto, acierta siempre.

## El arreglo (flag `RAG_PLAN_NOMBRADO`)

`conversational_core._plan_nombrado`: si el cliente **nombra cuántas inmersiones** ("las 2 inmersiones", "5 buceos",
"two dives") y **su origen consta**, el contexto del RAG lleva una línea: "El cliente nombra 2 inmersion(es). En el
catálogo, para su origen, eso es: - Salidas de Buceo - 2 inmersiones (1 día, ya en las islas): 124 USD…". Con varios
planes del mismo número (4 inmersiones desde las islas: 4 diurnas o 3 + 1 nocturna) salen los dos.

- Solo **añade un dato**, no decide nada (en la línea de s4-28: la regex propone).
- El número de inmersiones de cada plan sale de **su id** (`2_dives_1_day…`), no de una lista escrita a mano.
- No sale sin origen (eso lo pregunta la opción C del punto 3), ni si el número no es de inmersiones ("somos 2"), ni
  con ese plan ya elegido (entonces ya va su ficha).
- Entra por `_entradas_rag`, así que vale igual para la llamada normal y para la adelantada de rag-5 (misma huella).
- **Lo que no cubre:** referencias sin número ("ese plan", "el de un día"). Para eso, la propuesta del relevo sigue
  en pie: una pregunta de Jev en la misma llamada.

Tests: `tests/test_s4_27_plan_nombrado.py` (11).

## Escalón 0 en PRE (código local, sin desplegar)

`reproducir_juez_pre precio-desde-islas-vs-cartagena --reps 3 --codigo-local --flag rag_plan_nombrado` →
`precio-desde-islas-plan-nombrado.jsonl`: **turno 5 da los 124 USD 3/3** (hoy 0/3) y ya no ofrece el paquete de 3; el
turno 7 ("¿es el mismo costo desde el continente o la isla?") compara bien las 2 inmersiones 3/3.

Nota: `rag_piezas` arma el contexto por su cuenta (`_build_extra_context`), no pasa por `_entradas_rag`, así que este
arreglo se mide con la conversación entera, no con `rag_piezas`.
