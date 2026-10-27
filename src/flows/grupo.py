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


def sin_certificar_no_hereda(state) -> bool:
    """CALN-2 paso 2 (27-oct): quien no está certificado no puede hacer una actividad que pide certificación. Si el
    cliente dijo que OTRA persona del grupo no lo está («voy con mi novia, que nunca ha buceado») y no dio el reparto,
    esa persona no hereda la actividad de quien escribe: quien escribe hace la suya y los demás quedan sin decidir (se les
    recomienda y elige el cliente). Antes el grupo entero hacía la principal (banco de grupos g02 y g18: dos buzos
    certificados). Los que quedan sin decidir se guardan como los guarda `_take_undecided_members` (fuera del reparto, su
    cantidad pendiente y la recomendación marcada): dentro del reparto el grupo contaba como completo y nadie les
    preguntaba (banco g24). True si cambia el grupo."""
    from src.domain import activities as dom  # lazy

    actividad = dom.by_id(state.detected_activity) if state.detected_activity else None
    total = state.detected_group_size
    if (not state.acompanante_sin_certificar or state.personas or state.pending_undecided_qty or actividad is None
            or not actividad.requires_certification or not isinstance(total, int) or total < 2):
        return False
    state.personas = [{"actividad": actividad.id, "cantidad": 1}]
    state.pending_undecided_qty = total - 1
    state.needs_companion_activity = True
    return True


def sin_decidir_aparte(state) -> None:
    """Quien no ha elegido nunca se queda DENTRO del reparto: el grupo contaría como completo, el circuito borraría la
    recomendación y nadie le preguntaría (banco g24; «mi amigo también quiere venir» sobre un grupo sabido). Sale a la
    cantidad pendiente con la recomendación marcada, como lo deja `_take_undecided_members`."""
    reparto = state.detected_group_allocation or {}
    cuantos = reparto.get(SIN_DECIDIR)
    if not cuantos:
        return
    state.detected_group_allocation = {a: n for a, n in reparto.items() if a != SIN_DECIDIR} or None
    state.pending_undecided_qty = (state.pending_undecided_qty or 0) + cuantos
    state.needs_companion_activity = True


def completa(reparto: dict | None, nuevo: dict, total) -> bool:
    """El reparto se escribe una vez y solo cambia con una corrección; pero «ella prefiere hacer snorkel» no corrige el
    grupo, lo completa: da actividad a quien no la tenía. True si el reparto nuevo no le quita la actividad a nadie que la
    tuviera y lo que añade cabe en los que faltaban por decidir (banco de grupos g24)."""
    decididos = {a: c for a, c in (reparto or {}).items() if a != SIN_DECIDIR}
    if not isinstance(total, int) or any(nuevo.get(a, 0) < c for a, c in decididos.items()):
        return False
    anadidos = sum(c for a, c in nuevo.items() if a != SIN_DECIDIR) - sum(decididos.values())
    return 0 < anadidos <= total - sum(decididos.values())


def reparto_de(personas: list[dict]) -> dict | None:
    """La lista como el reparto de siempre; None sin nadie (el valor por defecto de antes)."""
    if not personas:
        return None
    reparto: dict = {}
    for entrada in personas:
        clave = entrada.get("actividad") or SIN_DECIDIR
        reparto[clave] = reparto.get(clave, 0) + entrada.get("cantidad", 0)
    return reparto
