"""El núcleo conversacional partido por nodo del subgrafo `booking` (s4-2, 19-oct).

`conversational_core.py` era un solo fichero de ~6.000 líneas. Ahora cada nodo del subgrafo de la reserva
(`booking_agent._build_booking_subgraph`: setup → availability → routing → extraction → slotfill_close) tiene su
módulo, con su fase y lo que solo usa esa fase:

- `setup.py`          → `_setup_phase`: idioma, saludo y nombre del cliente.
- `availability.py`   → `_availability_phase`: la puerta de disponibilidad, la posventa y lo de tras el pase.
- `routing.py`        → `_routing_phase`: respuestas cortas, deliberación y comparación de opciones.
- `extraction.py`     → `_extraction_phase`: entender el mensaje (`_understand`, `fill_gaps`), acompañantes,
                        multi-ítem, redes de precisión y el turno con pregunta.
- `extractor.py`      → el extractor del turno (ex-5) visto desde el núcleo: lanzarlo adelantado, aplicar sus
                        datos al estado (`_aplicar_extractor`, `_poner_*`) y guardar lo dicho en el pase. Es la
                        capa de abajo de `extraction.py`.
- `slotfill_close.py` → `_slotfill_close_phase`: preguntar el hueco que falta o cerrar la reserva, y el acuse en
                        paralelo.

Lo común, también aquí desde lat-9 paso 4 (27-oct):

- `huecos.py`    → los huecos de la reserva y cuál falta (`next_missing_slot`); no depende del núcleo.
- `preguntas.py` → la pregunta de cada hueco (`ask_slot`) y el plan que se recomienda.
- `origen.py`    → el origen antes del precio (la puerta, lo que Jev dice del lugar) y los recortes del escritor.
- `escritor.py`  → el RAG del núcleo y el escritor, el RAG adelantado y la respuesta en paralelo.

En `conversational_core.py` quedan la entrada `maybe_handle_turn`, las notas, el saludo, el grupo, el recuerdo y
el carrito; además re-exporta todo lo movido: el resto del código, los scripts y los tests lo siguen encontrando
allí. Los tres primeros los importa al principio; `escritor` (que importa del núcleo las notas y el saludo), al final,
antes que los nodos.

Ojo con los parches de los tests: un nombre se busca en el módulo donde está DEFINIDA la función que lo usa. Para
cambiar `fill_gaps` dentro de `_understand` hay que parchear `nucleo.extraction.fill_gaps`, no
`conversational_core.fill_gaps`.

Este `__init__` carga antes `conversational_core`: los módulos de aquí importan de él lo común y él los importa al
final para re-exportarlos. Así da igual qué se importe primero.
"""

import src.agents.conversational_core  # noqa: F401
