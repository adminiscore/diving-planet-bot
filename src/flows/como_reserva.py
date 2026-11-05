"""Cómo reserva este cliente, en UN sitio (CALN-35, decisiones de Gadea `pago-y-reserva` y `hotel-antes-de-reservar`).

Lo decidían por separado los hechos, el cierre y el escritor, y cada uno miraba una cosa: en 5 de 13 conversaciones con
colombianos se hablaba de la web o del enlace (mini c055, en A y en B), y quien salía desde las islas sin hotel reservaba igual.
- `HOTEL_PRIMERO`: sale desde las islas y no nos ha dicho su hotel. No hay enlace ni asesor hasta que lo diga.
- `ASESOR`: colombianos y residentes pagan en pesos y les cierra un asesor por el chat. Sin enlace de la web.
- `ENLACE`: el resto, también un grupo mixto, que paga en dólares.
Vale con cualquier nombre de alojamiento (casa, Airbnb): un asesor confirma la recogida. De momento solo «desde las islas», no los
planes desde Cartagena con noche en las islas (Gadea, 5-nov).
"""
from __future__ import annotations

from src.domain.lugares import solo_nombra_una_isla

ENLACE = "enlace"
ASESOR = "asesor"
HOTEL_PRIMERO = "hotel_primero"

# Lo que se guarda si la respuesta a «¿en qué hotel?» no trae ninguno: el lead dice «sin definir» y no se pregunta en bucle.
POR_CONFIRMAR = {"es": "por confirmar", "en": "to be confirmed"}


def hotel_conocido(state) -> str | None:
    """El hotel que ha dicho el cliente; None si no ha dicho ninguno (o solo tenemos «por confirmar» o el nombre de una isla)."""
    hotel = getattr(state, "hotel", None) or getattr(state, "detected_hotel", None)
    return None if hotel in POR_CONFIRMAR.values() or solo_nombra_una_isla(hotel) else hotel


def _sale_desde_las_islas(state) -> bool:
    """Lo ha dicho, o se le está confirmando porque lo parece: el enlace de una reserva no puede salir en ese turno."""
    return (getattr(state, "location", None) or (getattr(state, "pending_correction", None) or {}).get("location")) == "island"


def como_reserva(state) -> str:
    if _sale_desde_las_islas(state) and not hotel_conocido(state):
        return HOTEL_PRIMERO
    if getattr(state, "is_colombian", None) and not getattr(state, "mixed_nationality_notice", False):
        return ASESOR
    return ENLACE
