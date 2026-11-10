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

import re

VECES_MAX = 2  # cuántas veces puede salir la misma pregunta en una conversación

PREGUNTAR = "preguntar"  # sale la pregunta (y se cuenta)
SIN_ELLA = "sin_ella"  # la respuesta va sin la pregunta: lo que ya dice
LAS_DOS_SALIDAS = "las_dos_salidas"  # el origen, sin nada más que decir: las dos salidas con su precio, y el cliente elige

ORIGEN = "location"

# Las que, agotadas, no paran la reserva: se sigue con lo que hay (P11) y, si no falta otra cosa, sale la tarjeta. Sin el número, la tarjeta
# va por persona (`cart_render.linea_de_precio`); sin la nacionalidad, en las dos monedas (`moneda`, G3-07a); sin las edades, sin repartir a
# los niños; sin el refresher, sin él; sin la actividad del acompañante, con los que ya eligieron; sin el hotel, el recordatorio de
# `como_reserva` (hotel primero). Las demás sí la paran: sin el origen no hay plan (van las dos salidas), y sin la actividad, la
# certificación o una corrección por confirmar no hay nada que reservar. La seguridad tiene su camino: la tarjeta con el aviso
# (`slotfill_close._tarjeta_sin_seguridad`).
SE_SIGUE_SIN_ELLA = frozenset({"qty", "nationality", "ages", "refresher", "companion_activity_choice", "hotel"})

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


def se_sigue_sin(hechas: dict | None) -> set[str]:
    """Las agotadas sin las que la reserva sigue: el flujo las salta, y si no falta nada más, cierra con lo que hay."""
    return agotadas(hechas) & SE_SIGUE_SIN_ELLA


def recordatorio(lang: str | None) -> str:
    return RECORDATORIO["es" if lang == "es" else "en"]


_ENLACE_RE = re.compile(r"https?://\S+")


def trae_pregunta(texto: str | None) -> bool:
    """¿El texto pregunta algo? (un «?» fuera de los enlaces, que llevan «?language=es»). Para el contador del bloque 0,5 del Plan Gadea:
    en un turno de la reserva el escritor no debe preguntar; si lo hace, se apunta (`escritor_pregunta` en [TURN_METRICS]). El borrado de
    sus copias en el compositor sigue activo y se quitará cuando esto marque cero en un panel y una tanda («primero cubre, luego borra»)."""
    return bool(texto) and "?" in _ENLACE_RE.sub("", texto)


def tapar_enlaces(texto: str) -> tuple[str, list[str]]:
    """Bloque 4R (C5): los enlaces, tapados, para buscar preguntas o frases sin partirlos. El «?language=es» de un enlace casaba
    con las preguntas y el «.» de «divingplanet.org» cortaba la frase: `compositor._una_oferta_del_asesor` dejaba
    «https://book.divingplanet.language=es» (comprobado) y `redactor_hechos.con_la_pieza`, el enlace partido."""
    enlaces = _ENLACE_SIN_PUNTO_RE.findall(texto)
    for i, enlace in enumerate(enlaces):
        texto = texto.replace(enlace, _tapa(i), 1)
    return texto, enlaces


# Sin el punto, la coma o el cierre de negrita que lo siguen: son de la frase, no del enlace (si no, la frase del enlace y la pregunta de
# detrás parecían una sola y se iban juntas).
_ENLACE_SIN_PUNTO_RE = re.compile(r"https?://\S+?(?=[.,;:!?)\]*_]*(?:\s|$))")


def destapar_enlaces(texto: str, enlaces: list[str]) -> str:
    for i, enlace in enumerate(enlaces):
        texto = texto.replace(_tapa(i), enlace, 1)
    return texto


def _tapa(i: int) -> str:
    return f"\x00{chr(0xE000 + i)}\x00"  # sin cifras ni puntuación: ningún patrón de importes o frases la toca
