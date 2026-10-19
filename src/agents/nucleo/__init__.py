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

Lo común (los huecos y sus preguntas, el plan, las notas y la respuesta en paralelo, el RAG del núcleo, el origen
antes del precio) y la entrada `maybe_handle_turn` siguen en `conversational_core.py`, que además re-exporta todo
lo movido: el resto del código, los scripts y los tests lo siguen encontrando allí.

Ojo con los parches de los tests: un nombre se busca en el módulo donde está DEFINIDA la función que lo usa. Para
cambiar `fill_gaps` dentro de `_understand` hay que parchear `nucleo.extraction.fill_gaps`, no
`conversational_core.fill_gaps`.

Este `__init__` carga antes `conversational_core`: los módulos de aquí importan de él lo común y él los importa al
final para re-exportarlos. Así da igual qué se importe primero.
"""

import src.agents.conversational_core  # noqa: F401
