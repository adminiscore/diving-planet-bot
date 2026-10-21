"""Lo que era de `supervisor.py`, partido por ruta del grafo (s4-2, 19-oct).

`supervisor.py` tenía ~3.300 líneas con los detectores y las respuestas de todas las rutas. Ahora cada ruta del
grafo (`orchestration/state.py`: ALL_ROUTES) tiene su módulo con lo que solo usa ella:

- `router.py`       → lo que hace el nodo router antes de clasificar (escenario nuevo, mención de niños).
- `safety.py`       → link roto, pase por posventa o empresa, precio dentro de DIVE TO HEAL, `_reply_language`.
- `deflection.py`   → petición de número o contacto directo, "¿eres un bot?".
- `changes.py`      → cancelar, reprogramar o cambiar el número de personas; preguntas de disponibilidad.
- `info.py`         → alcohol y alergias, grupo privado, "¿cambia el precio por nacionalidad?", edad.
- `booking.py`      → lo que el núcleo de la reserva toma del supervisor: aplicar la intención detectada, la
                      coherencia del reparto, grupo mixto, nota pendiente, fecha cerrada.
- `contexto_rag.py` → `_build_extra_context`, el contexto del estado que se le pasa al RAG (info y núcleo).

En `supervisor.py` quedan la entrada (`route_message`), la cascada compartida (`_shared_turn_handler`), el aviso de
fallo técnico y lo común a varias rutas (`_infer_language`, `_matches_escalation_keyword`, `_ADAPTIVE_DIVING_PATTERN`,
`_booking_change_buttons`...). Además re-exporta todo lo movido: la cascada, el router (`sup.<nombre>`), los nodos
(import perezoso desde `supervisor`), el núcleo (`supervisor.<nombre>`), los scripts y los tests lo siguen
encontrando allí.

Ojo con los parches de los tests: un nombre se busca en el módulo donde está DEFINIDA la función que lo usa: se
parchea `rutas.<módulo>.<nombre>`, no `supervisor.<nombre>`.

Este `__init__` carga antes `supervisor`: los módulos de aquí importan de él lo común y él los importa al final para
re-exportarlos. Así da igual qué se importe primero.
"""

import src.agents.supervisor  # noqa: F401
