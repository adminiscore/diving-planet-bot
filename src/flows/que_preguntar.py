"""CALN-43, P11: la tabla de qué preguntar. Si una pregunta de la reserva puede salir otra vez y, si no, qué va en su lugar.

Decisión de Gadea (6-nov, `sin-tercera-pregunta` en data/knowledge_base/decisiones.json): tras 2 preguntas sin respuesta se sigue con lo
que hay (el precio por persona, o los dos orígenes). Nunca una 3.ª vez. Sin excepciones: hasta ahora salía una 3.ª si el cliente pedía el
enlace (0.52b), y así salieron las 3 terceras veces del panel 059c (a02 el origen, a03 la actividad, a06 cuántos son), las tres en el
turno de «¿cómo reservo?» (`docs/robustness/caln/inventario-decisiones.md`).

Aquí no se lee al cliente ni se redacta: entra cuántas veces salió la pregunta y si la respuesta dice algo más, y sale la decisión. Lo
cuenta y lo aplica el compositor (`src/agents/compositor.py`), por donde pasan todas las respuestas; el flujo
(`nucleo/slotfill_close._siguiente_pregunta`) pregunta antes otro dato que falte. Lo prueba `tests/test_que_preguntar.py`, sin IA.
"""
from __future__ import annotations

VECES_MAX = 2  # cuántas veces puede salir la misma pregunta en una conversación

PREGUNTAR = "preguntar"  # sale la pregunta (y se cuenta)
SIN_ELLA = "sin_ella"  # la respuesta va sin la pregunta: lo que ya dice
LAS_DOS_SALIDAS = "las_dos_salidas"  # el origen, sin nada más que decir: las dos salidas con su precio, y el cliente elige

ORIGEN = "location"

# Sin la pregunta y sin nada más que decir: un recordatorio que no pregunta (como `como_reserva.cuando_tenga_el_hotel`).
RECORDATORIO = {
    "es": "Cuando quieras, me lo dices y seguimos con la reserva. 🌊",
    "en": "Whenever you're ready, just tell me and we'll carry on with the booking. 🌊",
}


def se_puede_preguntar(veces: int) -> bool:
    """¿Puede salir la pregunta, si ya salió `veces` veces en la conversación?"""
    return veces < VECES_MAX


def que_hacer(slot: str | None, veces: int, *, hay_respuesta: bool) -> str:
    """Qué se hace con la pregunta de la reserva por `slot` en este turno. `veces`: las que ya salió. `hay_respuesta`: si sin ella la
    respuesta dice algo (contesta lo que preguntó el cliente)."""
    if se_puede_preguntar(veces):
        return PREGUNTAR
    if slot == ORIGEN and not hay_respuesta:
        return LAS_DOS_SALIDAS
    return SIN_ELLA


def agotadas(hechas: dict | None) -> set[str]:
    """Las preguntas que ya no pueden salir: el flujo pregunta antes otro dato que falte."""
    return {slot for slot, veces in (hechas or {}).items() if slot and not se_puede_preguntar(veces)}


def recordatorio(lang: str | None) -> str:
    return RECORDATORIO["es" if lang == "es" else "en"]
