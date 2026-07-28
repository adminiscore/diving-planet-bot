"""Fachada de render del carrito para el núcleo conversacional (Fase 4, P1).

El núcleo importa de aquí en vez de instanciar `DecisionTree` directamente. La
máquina de estados legacy `MIXED_*` (handlers + pasos del enum) se retiró entera
en Fase 4; estos helpers de render son lo único que sobrevive de `DecisionTree`,
y su cuerpo sigue por ahora en `decision_tree.py`. Se moverá FÍSICAMENTE a este
módulo en el paso siguiente (P1b), ya con este seam en su sitio y la suite verde
de testigo, tras extraer catálogo/estado.

Import lazy de `DecisionTree` (dentro de `_tree()`) para no crear un ciclo de
imports: `decision_tree.py` importa mucho y otros módulos lo importan a él.
"""

from __future__ import annotations

_dt = None  # instancia perezosa y compartida (los helpers no guardan estado)


def _tree():
    global _dt
    if _dt is None:
        from src.flows.decision_tree import DecisionTree
        _dt = DecisionTree()
    return _dt


def service_for_location(service_id, state):
    """Resuelve el `service_id` a su variante según la ubicación (isla vs Cartagena)."""
    return _tree()._service_for_location(service_id, state)


def parse_quantity(message):
    """Parsea una cantidad ('2', 'dos', 'un par' via fuzzy) o None."""
    return _tree()._parse_mixed_quantity(message)


def cart_label_for(item_type, plan, lang):
    """Etiqueta legible de un ítem del carrito (cert/beginner/snorkel/course)."""
    return _tree()._cart_label_for(item_type, plan, lang)


def goto_final_summary(state):
    """Resumen final determinista del carrito (precios + links del catálogo)."""
    return _tree()._goto_mixed_final_summary(state)


def cart_booking_blocks(state):
    """Bloques de reserva (servicio + link) por ítem del carrito."""
    return _tree()._cart_booking_blocks(state)
