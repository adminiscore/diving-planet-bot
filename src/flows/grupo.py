"""CALN-2 (27-oct): el grupo como lista de personas. Diseño: `docs/robustness/caln/diseno-caln2-grupo.md`.

Cada entrada vale por una persona o por varias iguales: `{"actividad": "certified_diving", "cantidad": 2}`; la
actividad es None mientras no la eligen (se les recomienda y elige el cliente). Se parte cuando llega un dato de una sola.

Paso 1: la lista es donde se GUARDA el grupo (`ConversationState.personas`), y el reparto de siempre
(`detected_group_allocation`, {actividad: cuántos}) se calcula de ella y se escribe en ella.
CALN-8 (2a, 28-oct; diseño `docs/robustness/caln/diseno-caln8-2-personas.md`): también quien no ha elegido vive en la
lista (`actividad: None`; `cantidad: None` si no se sabe cuántos son, «vienen unos amigos»). `pending_undecided_qty` y
`needs_companion_activity` se calculan de ella (abajo, las funciones; en el estado, las propiedades) y el reparto los
deja fuera, como antes los dejaba `sin_decidir_aparte`, que ya no hace falta.
CALN-8 (2b): y quien ya eligió sin saberse cuántos son (`{"actividad": "snorkel", "cantidad": None}`, «¿cuántos serían
para snorkel?»): `pending_companion_activity`.
"""
from __future__ import annotations

SIN_DECIDIR = "undecided"  # la clave del reparto de siempre para quien aún no ha elegido actividad


def entradas_de_reparto(reparto: dict | None) -> list[dict]:
    """El reparto de siempre como lista de entradas, en el mismo orden."""
    return [{"actividad": None if actividad == SIN_DECIDIR else actividad, "cantidad": cantidad}
            for actividad, cantidad in (reparto or {}).items()]


def sin_elegir(personas: list[dict]) -> list[dict]:
    """Las entradas de quien aún no ha elegido actividad."""
    return [e for e in personas if not e.get("actividad")]


def en_el_reparto(entrada: dict) -> bool:
    """¿Cuenta en el reparto? Quien ya eligió y se sabe cuántos son."""
    return bool(entrada.get("actividad")) and isinstance(entrada.get("cantidad"), int)


def con_reparto(personas: list[dict], reparto: dict | None) -> list[dict]:
    """La lista con un reparto nuevo de los que ya eligieron. Lo que está fuera del reparto se queda (quien no ha elegido
    y quien eligió sin saberse cuántos son), y los «undecided» del reparto se suman a quien no ha elegido: nunca se
    quedan dentro del reparto, donde el grupo contaría como completo y nadie les preguntaría (banco g24)."""
    entradas = entradas_de_reparto(reparto)
    nuevos = sum(e["cantidad"] for e in entradas if not e["actividad"] and isinstance(e["cantidad"], int))
    resto = [e for e in personas if not en_el_reparto(e)]
    if nuevos:
        resto = con_sin_elegir(resto, sin_elegir_contados(resto) + nuevos)
    return [e for e in entradas if e["actividad"]] + resto


def sin_elegir_contados(personas: list[dict]) -> int:
    """Cuántos no han elegido, de los que se sabe cuántos son."""
    return sum(e["cantidad"] for e in sin_elegir(personas) if isinstance(e.get("cantidad"), int))


def con_sin_elegir(personas: list[dict], cuantos: int) -> list[dict]:
    """La lista con `cuantos` sin elegir de cantidad sabida (0: ninguno); los de cantidad sin saber se quedan."""
    otras = [e for e in personas if e.get("actividad") or e.get("cantidad") is None]
    return otras + ([{"actividad": None, "cantidad": cuantos}] if cuantos else [])


def con_pregunta(personas: list[dict], preguntar: bool) -> list[dict]:
    """La lista para que haya (o no) que preguntar qué hará alguien (`needs_companion_activity`, que es «hay quien no ha
    elegido»): sin nadie sin elegir, preguntar es que viene alguien sin saber cuántos ni qué hará; no preguntar quita a
    esos (los de cantidad sabida los quita `pending_undecided_qty`)."""
    if preguntar:
        return personas if sin_elegir(personas) else [*personas, {"actividad": None, "cantidad": None}]
    return [e for e in personas if e.get("actividad") or e.get("cantidad") is not None]


def solo_el_reparto(personas: list[dict]) -> list[dict]:
    """La lista sin esperas (quien no ha elegido, lo elegido a falta de cuántos): para cuando el reparto ya cubre a
    todo el grupo y no puede quedar nadie por preguntar (el «circuit-breaker» de 2026-09-01)."""
    return [e for e in personas if en_el_reparto(e)]


def eligiendo(personas: list[dict]) -> str | None:
    """Lo que ya eligió quien viene sin saberse cuántos son («¿cuántos serían para snorkel?»)."""
    return next((e["actividad"] for e in personas if e.get("actividad") and e.get("cantidad") is None), None)


def con_eligiendo(personas: list[dict], actividad: str | None) -> list[dict]:
    """La lista con (o sin) una elección a falta de cuántos son: la toma quien venía sin saberse cuántos ni qué haría
    (g26) o, si no hay nadie así, queda sola hasta que se diga cuántos."""
    resto = [e for e in personas if not (e.get("actividad") and e.get("cantidad") is None)]
    if not actividad:
        return resto
    if any(e.get("cantidad") is None for e in sin_elegir(resto)):
        return [{**e, "actividad": actividad} if not e.get("actividad") and e.get("cantidad") is None else e
                for e in resto]
    return [*resto, {"actividad": actividad, "cantidad": None}]


def sin_certificar_no_hereda(state) -> bool:
    """CALN-2 paso 2 (27-oct): quien no está certificado no puede hacer una actividad que pide certificación. Si el
    cliente dijo que OTRA persona del grupo no lo está («voy con mi novia, que nunca ha buceado») y no dio el reparto,
    esa persona no hereda la actividad de quien escribe: quien escribe hace la suya y los demás quedan sin decidir (se les
    recomienda y elige el cliente). Antes el grupo entero hacía la principal (banco de grupos g02 y g18: dos buzos
    certificados). Los que quedan sin decidir son una entrada sin actividad (fuera del reparto, con la pregunta de qué
    harán): dentro del reparto el grupo contaba como completo y nadie les preguntaba (banco g24). True si cambia el
    grupo."""
    from src.domain import activities as dom  # lazy

    actividad = dom.by_id(state.detected_activity) if state.detected_activity else None
    total = state.detected_group_size
    if (not state.acompanante_sin_certificar or reparto_de(state.personas) or sin_elegir_contados(state.personas)
            or actividad is None
            or not actividad.requires_certification or not isinstance(total, int) or total < 2):
        return False
    state.personas = [{"actividad": actividad.id, "cantidad": 1}, {"actividad": None, "cantidad": total - 1}]
    return True


def completa(reparto: dict | None, nuevo: dict, total) -> bool:
    """El reparto se escribe una vez y solo cambia con una corrección; pero «ella prefiere hacer snorkel» no corrige el
    grupo, lo completa: da actividad a quien no la tenía. True si el reparto nuevo no le quita la actividad a nadie que la
    tuviera y lo que añade cabe en los que faltaban por decidir (banco de grupos g24)."""
    decididos = {a: c for a, c in (reparto or {}).items() if a != SIN_DECIDIR}
    return all(nuevo.get(a, 0) >= c for a, c in decididos.items()) and completado(reparto, nuevo, total) is not None


def completado(reparto: dict | None, nuevo: dict, total) -> dict | None:
    """El reparto completado: lo que ya se sabía más lo nuevo de quienes faltaban por elegir, si cabe en ellos; None si
    no es completar. Quien no se nombra no se quita: el extractor lee el mensaje, y «yo y la de 14 el minicurso» no habla
    del suegro que ya iba de acompañante (sparring contra la rama, 27-oct)."""
    if not isinstance(total, int):
        return None
    antes = {a: c for a, c in (reparto or {}).items() if a != SIN_DECIDIR}
    junto = dict(antes)
    for actividad, cuantos in nuevo.items():
        if actividad != SIN_DECIDIR and isinstance(cuantos, int) and cuantos > junto.get(actividad, 0):
            junto[actividad] = cuantos
    anadidos = sum(junto.values()) - sum(antes.values())
    return junto if 0 < anadidos <= total - sum(antes.values()) else None


def reparto_de(personas: list[dict]) -> dict | None:
    """Los que ya eligieron (y se sabe cuántos son) como el reparto de siempre; None sin nadie (el valor por defecto de
    antes)."""
    reparto: dict = {}
    for entrada in personas:
        if en_el_reparto(entrada):
            reparto[entrada["actividad"]] = reparto.get(entrada["actividad"], 0) + entrada["cantidad"]
    return reparto or None
