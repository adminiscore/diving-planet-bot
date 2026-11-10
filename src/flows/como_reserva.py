"""Cómo reserva este cliente, en UN sitio (CALN-35, decisiones de Gadea `pago-y-reserva` y `hotel-antes-de-reservar`).

Lo decidían por separado los hechos, el cierre y el escritor, y cada uno miraba una cosa: en 5 de 13 conversaciones con
colombianos se hablaba de la web o del enlace (mini c055, en A y en B), y quien salía desde las islas sin hotel reservaba igual.
- `HOTEL_PRIMERO`: sale desde las islas y no nos ha dicho su hotel. No hay enlace ni asesor hasta que lo diga.
- `ASESOR`: colombianos y residentes pagan en pesos y les cierra un asesor por el chat. Sin enlace de la web.
- `RECOGIDA_POR_CONFIRMAR`: sale desde las islas y se aloja fuera de nuestras listas (una casa, un Airbnb, otro hotel): un asesor le
  confirma la recogida ANTES de reservar y pagar (Gadea, 5-nov; el Airbnb de la tanda s05d podía pagar sin saber si le recogían).
- `GRUPO`: 5 o más en actividades con descuento de grupo (buceo recreativo, minicurso, snorkel, acompañante; no cursos PADI ni Bubble
  Makers, `discounts.json`). Hay que pedirlo antes de pagar: un asesor se lo aplica (CALN-43 P9, Gadea 6-nov; panel 059c b03).
- `PARTE_SIN_ENLACE`: un grupo con una parte del plan con enlace y otra sin él (el acompañante, Bubble Makers, las 4 diurnas, el paquete
  cuyo precio cierra un asesor…): todo por el asesor, no por dos caminos (CALN-43 P10, Gadea 6-nov; tanda s05f 6951). Si no hay ninguna
  parte con enlace, como hoy: la tarjeta lo pasa al asesor.
- `ENLACE`: el resto, también un grupo mixto, que paga en dólares.
De momento solo «desde las islas», no los planes desde Cartagena con noche en las islas (Gadea, 5-nov).

Bloque 4R (Plan Gadea, `docs/robustness/caln/diseno-bloque4r.md`): `entrega` es la decisión entera del momento de reservar, encima de
`como_reserva` (que no mira el origen y se queda para quien la lee hoy):
- `ORIGEN_PRIMERO`: tocaría el enlace pero no se sabe si sale desde Cartagena o desde las islas. Nunca el enlace de un origen supuesto
  (Gadea, 10-nov, #3701 y #3738): los precios de las dos salidas y la pregunta del origen.
- `ENLACE` con la nacionalidad por saber: el enlace y la línea de quien es colombiano (Gadea, 10-nov, #3741).
"""
from __future__ import annotations

import copy
import functools
import json
from dataclasses import dataclass

from src.domain.lugares import recogida_conocida, solo_nombra_una_isla

ENLACE = "enlace"
ASESOR = "asesor"
HOTEL_PRIMERO = "hotel_primero"
RECOGIDA_POR_CONFIRMAR = "recogida_por_confirmar"
GRUPO = "grupo"
PARTE_SIN_ENLACE = "parte_sin_enlace"
ORIGEN_PRIMERO = "origen_primero"  # bloque 4R: solo sale de `entrega`, nunca de `como_reserva`
POR_EL_ASESOR = (ASESOR, RECOGIDA_POR_CONFIRMAR, GRUPO, PARTE_SIN_ENLACE)  # sin enlace de la web: reserva un asesor

# A qué aplica el descuento de grupo (discounts.json, `group_discount`: «buceo recreativo, minicurso, snorkel y el plan de acompañante»).
CON_DESCUENTO_DE_GRUPO = frozenset({"certified_diving", "minicourse", "snorkel", "companion"})
_ENLACE_DE_RESERVA = "book.divingplanet.org/book/"

# Lo que se guarda si la respuesta a «¿en qué hotel?» no trae ninguno: el lead dice «sin definir» y no se pregunta en bucle.
POR_CONFIRMAR = {"es": "por confirmar", "en": "to be confirmed"}

_CUANDO_TENGA_EL_HOTEL = {
    "es_uno": "Cuando tengas el hotel, escríbeme con el nombre y seguimos con la reserva. 🌊",
    "es_grupo": "Cuando tengan el hotel, escríbanme con el nombre y seguimos con la reserva. 🌊",
    "en": "Once you have the hotel, message me with its name and we'll carry on with the booking. 🌊",
}


def hotel_conocido(state) -> str | None:
    """El hotel que ha dicho el cliente; None si no ha dicho ninguno (o solo tenemos «por confirmar» o el nombre de una isla)."""
    hotel = getattr(state, "hotel", None) or getattr(state, "detected_hotel", None)
    return None if hotel in POR_CONFIRMAR.values() or solo_nombra_una_isla(hotel) else hotel


def clave_de_idioma_y_grupo(state) -> str:
    if getattr(state, "language", "es") != "es":
        return "en"
    return "es_grupo" if (getattr(state, "detected_group_size", None) or 1) > 1 else "es_uno"


def cuando_tenga_el_hotel(state) -> str:
    """El recordatorio, en vez de volver a preguntar el hotel a quien ya ha dicho que no lo tiene."""
    return _CUANDO_TENGA_EL_HOTEL[clave_de_idioma_y_grupo(state)]


def _sale_desde_las_islas(state) -> bool:
    """Lo ha dicho, o se le está confirmando porque lo parece: el enlace de una reserva no puede salir en ese turno."""
    return (getattr(state, "location", None) or (getattr(state, "pending_correction", None) or {}).get("location")) == "island"


def como_reserva(state) -> str:
    islas, hotel = _sale_desde_las_islas(state), hotel_conocido(state)
    if islas and not hotel:
        return HOTEL_PRIMERO
    if getattr(state, "is_colombian", None) and not getattr(state, "mixed_nationality_notice", False):
        return ASESOR
    if recogida_por_confirmar(state):
        return RECOGIDA_POR_CONFIRMAR
    partes = partes_del_plan(state)
    if personas_con_descuento_de_grupo(partes) >= minimo_del_grupo():
        return GRUPO
    con_enlace = [p for p in partes if _ENLACE_DE_RESERVA in (p.get("url") or "")]
    if con_enlace and len(con_enlace) < len(partes):
        return PARTE_SIN_ENLACE
    return ENLACE


def recogida_por_confirmar(state, lugar: str | None = None) -> bool:
    """Decisiones `hotel-antes-de-reservar` y `fuera-de-la-base`: sale desde las islas y se aloja fuera de los puntos de recogida de siempre
    (una casa, un Airbnb, otro hotel): la recogida la confirma una persona. `lugar`, el que nombra ahora (p. ej. quien ya reservó y pide que
    le recojan en otro sitio: el 4P la llama desde `decidir_pase`, #3723); si no, el hotel que ya dijo. Sin ninguno, no hay nada que
    confirmar todavía (es `HOTEL_PRIMERO`)."""
    hotel = lugar or hotel_conocido(state)
    return _sale_desde_las_islas(state) and bool(hotel) and not recogida_conocida(hotel)


def origen_sabido(state) -> bool:
    """¿Sabemos si sale desde Cartagena o desde las islas? Lo ha dicho y no se le está confirmando (`pending_correction`)."""
    return bool(getattr(state, "location", None)) and not (getattr(state, "pending_correction", None) or {}).get("location")


@dataclass(frozen=True)
class Entrega:
    forma: str
    nacionalidad_por_saber: bool = False  # ENLACE sin saber si es colombiano: va con la línea de quien lo es (#3741)


def entrega(state) -> Entrega:
    """Bloque 4R (C1): lo que se le da a este cliente en el momento de reservar. Pura: decide, no pinta ni pasa a nadie."""
    forma = como_reserva(state)
    if forma != HOTEL_PRIMERO and not origen_sabido(state):
        # P5 (Gadea, 10-nov, #3747): primero el origen, también para el colombiano y el grupo; después, el asesor o el hotel primero.
        # Si se le está confirmando que sale desde las islas, ya es HOTEL_PRIMERO (sin enlace ni asesor), como hoy.
        return Entrega(ORIGEN_PRIMERO)
    sin_saber = forma == ENLACE and getattr(state, "is_colombian", None) is None
    return Entrega(forma, nacionalidad_por_saber=sin_saber and not getattr(state, "mixed_nationality_notice", False))


def partes_del_plan(state) -> list[dict]:
    """Las partes de la tarjeta que tocaría con lo que ya se sabe (`cart_render.cart_booking_blocks`: cada actividad, con los niños en
    la suya por su edad, su cantidad y su enlace), sin tocar el estado. Sin actividad, ninguna."""
    if not getattr(state, "detected_activity", None) and not getattr(state, "detected_group_allocation", None):
        return []
    from src.agents.nucleo.slotfill_close import (
        _build_cart_from_slots,  # lazy: el núcleo importa este módulo
    )
    from src.flows import cart_render  # lazy

    copia = copy.copy(state)
    _build_cart_from_slots(copia)
    return cart_render.cart_booking_blocks(copia)


def personas_con_descuento_de_grupo(partes: list[dict]) -> int:
    return sum(p.get("qty") or 0 for p in partes if p.get("actividad") in CON_DESCUENTO_DE_GRUPO)


@functools.cache
def _descuento_de_grupo() -> dict:
    from src.flows.catalog import _KB_DIR  # lazy

    return json.loads((_KB_DIR / "discounts.json").read_text(encoding="utf-8-sig"))["discounts"]["group_discount"]


def minimo_del_grupo() -> int:
    """Cuántos hacen falta para el descuento de grupo, de discounts.json (`group_discount.min_people`)."""
    return int(_descuento_de_grupo()["min_people"])


def por_que_el_asesor(forma: str, lang: str | None) -> str | None:
    """Por qué reserva un asesor, en una frase nuestra, para `GRUPO` y `PARTE_SIN_ENLACE` (el cierre y los hechos del escritor). Las cifras,
    de discounts.json."""
    es = lang == "es"
    if forma == GRUPO:
        n, pct = minimo_del_grupo(), _descuento_de_grupo()["percentage"]
        return (f"Al ser {n} o más, tienen un {pct} % más de descuento de grupo, que hay que pedir antes de pagar: un asesor se lo aplica y "
                "les dice cómo pagar." if es else
                f"As a group of {n} or more, you get an extra {pct}% group discount, which has to be requested before paying: an advisor "
                "will apply it and tell you how to pay.")
    if forma == PARTE_SIN_ENLACE:
        return ("Una parte del plan no se reserva por la web, así que un asesor les reserva todo junto." if es else
                "Part of the plan can't be booked online, so an advisor will book everything together for you.")
    return None
