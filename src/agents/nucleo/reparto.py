"""El reparto del grupo (CALN-8 (5), 5-nov): cómo se reparten las personas entre las actividades cuando el cliente contesta. Si ya están certificados o quieren el curso, quién de los que no habían elegido se lleva una actividad, el acompañante que se suma a la de otro y el total del grupo que se reparte.

Movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging

from src.agents.conversational_core import (
    _set_concrete_activity,
)
from src.flows.state import ConversationState

logger = logging.getLogger("uvicorn.error")


def _apply_cert_or_course(state: ConversationState, value) -> bool:
    """Respuesta a "¿ya la tienen o quieren sacarla?": si ya la tienen, son buzos
    certificados; si la quieren, es el curso de ese nivel."""
    if value == "already_certified":
        state.is_certified = state.detected_is_certified = True
        _set_concrete_activity(state, "certified_diving")
    elif value == "wants_course":
        state.is_certified = state.detected_is_certified = False
        _set_concrete_activity(state, state.cert_or_course_level or "padi_course")
    else:
        return False
    state.needs_cert_or_course = False
    state.cert_or_course_level = None
    return True


def _take_undecided_members(intent, state: ConversationState) -> None:
    """Punto UNICO para las personas del grupo sin actividad elegida, vengan del
    regex o del LLM: salen del reparto (que se guarda sin ellas), su cantidad queda
    pendiente y se marca la recomendacion de opciones (F6). Va DESPUES de la
    invariante de la suma, que las cuenta porque aun estan dentro del reparto."""
    allocation = getattr(intent, "group_allocation", None)
    if not isinstance(allocation, dict):
        return
    qty = allocation.pop("undecided", None)
    if not (isinstance(qty, int) and qty > 0):
        return
    # El total incluye a esas personas (2026-09-15): sin total escrito ("mi amigo tiene
    # licencia, yo no"), el total se sincronizaba despues con la suma del reparto ya sin
    # ellas y quedaba en 1.
    with_undecided = sum(v for v in allocation.values() if isinstance(v, int) and v > 0) + qty
    if (intent.group_size or state.detected_group_size or 0) < with_undecided:
        intent.group_size = with_undecided
        if "group_size" not in intent.detected_fields:
            intent.detected_fields.append("group_size")
    intent.group_allocation = allocation or None
    state.pending_undecided_qty = qty  # CALN-8 (2a): con ellos en la lista, se pregunta qué harán


def _elige_quien_falta(state: ConversationState, activity: str, solo: int | None = None) -> None:
    """El cliente elige qué hará quien no había elegido (el botón o el nombre de la opción, el resolutor o el
    extractor). CALN-8 (2b): si se sabe cuántos son, entran ya en el reparto con su cantidad, sin preguntar «¿cuántos
    serían?» (antes quedaba la elección aparte y `_merge_pending_undecided` la juntaba más tarde en el turno); si no,
    queda elegida a falta de cuántos (`pending_companion_activity`). `solo` (sparring s04b): la elección es solo de esos
    (el mensaje nombra a quiénes); los demás siguen sin elegir."""
    cuantos = state.pending_undecided_qty
    if cuantos:
        n = cuantos if solo is None else max(0, min(solo, cuantos))
        if not n:
            return
        state.pending_undecided_qty = (cuantos - n) or None  # antes de juntar: el total ya no los cuenta aparte
        _merge_companion_activity(state, activity, n)
    else:
        state.pending_companion_activity = activity


def _merge_companion_activity(state: ConversationState, activity: str, qty: int) -> None:
    """Añade `qty` personas a `activity` como subgrupo del reparto sin pisar
    la actividad principal — punto único (fast-path regex, respuesta a
    «¿cuántos para X?», personas sin decidir que eligen) para que todos los
    caminos dejen el estado exactamente igual de consistente."""
    alloc = dict(state.detected_group_allocation or {})
    main_act = state.detected_activity
    if main_act and main_act not in alloc:
        alloc.setdefault(main_act, state.detected_group_size or 1)
    known = state.detected_group_size or 1  # DEUDA-EXT2: sin total, quien escribe es uno (como `setdefault(main, … or 1)`)
    alloc[activity] = alloc.get(activity, 0) + qty
    state.detected_group_allocation = alloc
    # Los que aún no han elegido (fuera del reparto, CALN-2; CALN-8 2a: también si `activity` es «undecided») van.
    state.detected_group_size = sum((state.detected_group_allocation or {}).values()) + (state.pending_undecided_qty or 0)
    if not main_act and known + qty > state.detected_group_size:
        # DEUDA-EXT (26-oct): sin actividad principal, los que ya se contaban se perdían: "two certified divers" + "my
        # wife will join us but she'll just snorkel" dejaba {snorkel: 1} y total 1 (banco-lat11 a3). El total suma a la
        # persona nueva; los demás esperan a la principal, que el bot pregunta (`booking._resto_a_la_principal`).
        state.detected_group_size = known + qty
    logger.info(f"[CORE] merged companion activity {activity} x{qty} -> alloc={alloc}")


def _apply_group_total(state: ConversationState, total: int) -> bool:
    """Respuesta al total del grupo. Con una persona pendiente de ubicar
    (`pending_companion_in_group`): si el total no crece, esa persona ya estaba
    contada y se MUEVE de la actividad principal; si crece, se AÑADEN los que faltan."""
    pending = state.pending_companion_in_group
    if not pending:
        state.detected_group_size = total
        return True
    state.pending_companion_in_group = None
    known = state.detected_group_size or 0
    activity, qty = pending["activity"], pending["qty"]
    if total > known:
        _merge_companion_activity(state, activity, total - known)
        return True
    alloc = dict(state.detected_group_allocation or {})
    main = state.detected_activity
    if not main:
        # DEUDA-EXT (26-oct): sin actividad principal, el que ya estaba contado pasa a su actividad y el resto espera a
        # la principal (antes `alloc[None]`).
        moved = min(qty, known or qty)
        alloc[activity] = alloc.get(activity, 0) + moved
        state.detected_group_allocation = alloc
        logger.info(f"[CORE] companion {activity} x{moved} ya contado, sin principal -> alloc={alloc}")
        return True
    alloc.setdefault(main, known or qty)
    moved = min(qty, alloc[main])
    alloc[main] -= moved
    alloc[activity] = alloc.get(activity, 0) + moved
    state.detected_group_allocation = {k: v for k, v in alloc.items() if v}
    logger.info(f"[CORE] companion {activity} x{moved} ya contado -> alloc={state.detected_group_allocation}")
    return True
