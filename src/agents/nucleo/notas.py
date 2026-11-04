"""Las notas del cliente (CALN-8 (5), 5-nov): lo que cuenta y no es un dato de la reserva (una lesión, un miedo, la
boda), que `extract_notes` apunta en paralelo con el turno (l1-4): la foto de lo que debe leer, si Jev dice que no hay
nada que apuntar, la captura y la espera antes de usarlas.

Movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging

from src.agents.notes_extractor import extract_notes
from src.flows.state import ConversationState

logger = logging.getLogger("uvicorn.error")


async def await_pending_notes(state: ConversationState) -> None:
    """l1-4: espera a la captura de notas que `_setup_phase` lanzó en paralelo.

    Se llama en los dos sitios donde importa que ya estén: antes de
    `_build_extra_context` (el contexto del RAG las incluye) y al cerrar el turno
    en `supervisor.route_message`, antes de que el canal guarde el estado. Es
    idempotente: si no hay tarea, o ya se esperó, no hace nada.

    Si la captura falla, se traga el error a propósito: la nota es un extra para el
    asesor y no puede tumbar el turno del cliente (el código de siempre, cuando iba
    en serie, tampoco propagaba: `_maybe_capture_notes` ya registra y sigue).
    """
    task = getattr(state, "_pending_notes_task", None)
    if task is None:
        return
    state._pending_notes_task = None
    try:
        await task
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[NOTES][PARALELO] la captura de notas falló: {exc}")


def _notes_snapshot(state: ConversationState) -> dict:
    """l1-4: foto de lo que `extract_notes` debe leer, tomada al final de `setup`.

    En serie da lo mismo que leer el estado en el momento. En paralelo es lo que
    evita la carrera del A/B del 23-sep: una tarea de asyncio no arranca hasta que
    el turno espera algo, y en los turnos sin más llamadas al LLM eso es el final
    de `route_message`, cuando las fases ya han metido la respuesta del BOT en
    `state.history`. Las notas salían de esa respuesta y contaminaban los turnos
    siguientes. Copias: la lista del historial crece después, y sus mensajes no
    se modifican."""
    facts = state.remembered_facts or {}
    return {
        "history": list(state.history),
        "existing": list(facts.get("notes") or []),
        "lang": state.language,
    }


def _jev_sin_nada_que_apuntar(routing_signals: dict) -> bool:
    """rag-5 (flag `notas_puerta_jev`): ¿Jev está SEGURO de que el mensaje no cuenta nada del cliente que haya que
    apuntar? Entonces no se llama al extractor de notas, que en esos mensajes apuntaba la pregunta como si fuera un
    hecho ("how much would that be" -> "not Colombian"). Sin la respuesta de Jev (falló), lo de siempre."""
    from src.agents.jev_router import NOTES_SKIP_MAX, SHARES_OPEN_FACT
    from src.observability import note_turn

    p = routing_signals.get(SHARES_OPEN_FACT)
    if p is None:
        return False
    saltar = p < NOTES_SKIP_MAX
    note_turn(notas="saltadas" if saltar else "extraidas")
    if saltar:
        logger.info(f"[CORE][NOTAS] Jev: nada que apuntar ({p:.2f}): no se llama al extractor")
    return saltar


async def _maybe_capture_notes(
    state: ConversationState, message: str, *, snapshot: dict | None = None
) -> None:
    """(Fase C, re-cableado 2026-07-28 — decisión owner: con LLM) Captura hechos
    abiertos que un asesor querría recordar (lesión/médico, accesibilidad,
    ocasión especial, restricciones) y los persiste en
    `state.remembered_facts["notes"]` → alimenta `_build_extra_context` (contexto
    del LLM) y la nota de lead del asesor, que ya renderizan esa lista.

    Gate barato: se salta mensajes triviales (numéricos / <3 palabras) para no
    gastar una llamada en "sí"/"2"/"cartagena". Cualquier fallo se traga — nunca
    puede romper el turno (mismo principio que el resto del núcleo).

    `snapshot` (l1-4, en paralelo; sin flag desde s4-25): lo que hay que leer, tomado
    en `_setup_phase` antes de lanzar la tarea (ver `_notes_snapshot`). Sin él (una
    llamada directa) se toma ahora."""
    from src.agents import supervisor  # lazy

    stripped = message.strip()
    if stripped.isdigit() or len(stripped.split()) < 3:
        return
    try:
        snap = snapshot if snapshot is not None else _notes_snapshot(state)
        new_notes = await extract_notes(
            message, history=snap["history"], existing_notes=snap["existing"], lang=snap["lang"]
        )
        if not new_notes:
            return
        # Se fusiona con el estado de AHORA, no con el de la foto: en paralelo el
        # turno ha podido seguir escribiendo `remembered_facts` mientras tanto.
        facts = state.remembered_facts if state.remembered_facts is not None else {}
        existing = list(facts.get("notes") or [])
        notes = existing + [n for n in new_notes if n not in existing]
        facts["notes"] = notes[-supervisor._MAX_REMEMBERED_NOTES:]
        state.remembered_facts = facts
        logger.info(f"[CORE] notes captured -> {new_notes}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[CORE] notes capture failed (ignored): {exc}")
