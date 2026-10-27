"""CALN-2 (27-oct): el grupo como lista de personas. Diseño: `docs/robustness/caln/diseno-caln2-grupo.md`.

Cada entrada vale por una persona o por varias iguales: `{"actividad": "certified_diving", "cantidad": 2}`; la
actividad es None mientras no la eligen (se les recomienda y elige el cliente). Se parte cuando llega un dato de una sola.

Paso 1: la lista es donde se GUARDA el grupo (`ConversationState.personas`), y el reparto de siempre
(`detected_group_allocation`, {actividad: cuántos}, con «undecided» para los que no han elegido) se calcula de ella y
se escribe en ella. Ida y vuelta exactas, así que nada cambia para quien lee o escribe el reparto.
"""
from __future__ import annotations

SIN_DECIDIR = "undecided"  # la clave del reparto de siempre para quien aún no ha elegido actividad


def entradas_de_reparto(reparto: dict | None) -> list[dict]:
    """El reparto de siempre como lista de entradas, en el mismo orden."""
    return [{"actividad": None if actividad == SIN_DECIDIR else actividad, "cantidad": cantidad}
            for actividad, cantidad in (reparto or {}).items()]


def reparto_de(personas: list[dict]) -> dict | None:
    """La lista como el reparto de siempre; None sin nadie (el valor por defecto de antes)."""
    if not personas:
        return None
    reparto: dict = {}
    for entrada in personas:
        clave = entrada.get("actividad") or SIN_DECIDIR
        reparto[clave] = reparto.get(clave, 0) + entrada.get("cantidad", 0)
    return reparto
