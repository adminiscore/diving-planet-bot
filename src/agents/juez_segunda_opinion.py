"""J2 (1-oct): segunda opinión de Jev sobre las frases que el juez de grounding marca NO.

El juez (gpt-4.1) hace dos trabajos a la vez: decidir qué frases de la respuesta son datos del negocio y verificarlos.
En cuanto la respuesta trae algún dato, se salta el primero: copia la respuesta frase por frase y pone SÍ/NO a todo,
también a lo que su prompt excluye ("no lo tengo a la mano, un asesor te lo confirma", cortesía, repetir lo que dijo
el cliente), y a esas frases les toca NO al azar. Darle al mismo modelo una casilla de "no es dato" (juez v4,
`juez_por_tipo`) abrió el hueco contrario: escondía inventos en frases de "asesor" ("porque se suman impuestos").

Aquí el primer trabajo lo hace OTRO modelo, solo cuando el juez rechaza: Jev contesta, por cada frase marcada NO, si
afirma algo sobre la oferta de Diving Planet. Solo si está seguro de que NINGUNA afirma nada (p < SIN_DATOS_MAX), la
respuesta pasa. Un fallo o un tiempo de espera de Jev = el rechazo se mantiene (la conducta de hoy). Calibrado con
`scripts/sonda_juez_jev.py` (`docs/robustness/juez/README.md`).
"""

from __future__ import annotations

import asyncio
import logging

from src.config import settings

logger = logging.getLogger("uvicorn.error")

SIN_DATOS_MAX = 0.2
_CONTEXTO = (
    "One sentence from a reply of Coral, the WhatsApp assistant of Diving Planet (a scuba diving center in "
    "Cartagena, Colombia). The sentence may be in Spanish or English."
)
_AFIRMA_Q = {
    "type": "noul",
    "instructions": (
        "The sentence STATES something about Diving Planet's offer or how it works: prices, discounts, taxes or fees, "
        "what a plan includes or not, schedules, durations, places, requirements, policies (changes, cancellations, "
        "rescheduling, refunds, what happens to a booking), availability, which services exist or not, how bookings, "
        "links or payments work, or facts about the company. It counts even if it is only part of the sentence or "
        "comes together with an offer of help. It is FALSE only when the sentence just greets, shows enthusiasm or "
        "politeness, repeats what the customer said, asks the customer something, says a detail is not at hand or "
        "cannot be confirmed here, or offers help or to hand over to an advisor."
    ),
}


async def afirma(frase: str) -> float | None:
    """Probabilidad de que la frase afirme algo del negocio; None si Jev no contesta."""
    from src.agents.jev_router import JEV_URL, _http

    key = settings.openrouter_api_key
    if not key or not frase.strip():
        return None
    try:
        resp = await _http().post(
            JEV_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": settings.jev_model, "state": f"{_CONTEXTO}\n\nSentence: {frase}",
                  "questions": {"afirma": _AFIRMA_Q}},
            timeout=settings.jev_timeout_seconds,
        )
        resp.raise_for_status()
        return float((resp.json()["answers"].get("afirma") or {}).get("noul"))
    except Exception as exc:  # noqa: BLE001 — sin respuesta: el rechazo se mantiene
        logger.warning(f"[RAG][GROUNDING][JEV] sin segunda opinión: {type(exc).__name__}: {exc}")
        return None


async def ninguna_afirma(frases: list[str]) -> bool:
    """True solo si Jev está SEGURO de que ninguna de las frases rechazadas afirma algo del negocio."""
    if not frases:
        return False
    ps = await asyncio.gather(*(afirma(f) for f in frases))
    ok = all(p is not None and p < SIN_DATOS_MAX for p in ps)
    logger.info(f"[RAG][GROUNDING][JEV] {'pasa' if ok else 'se mantiene'}: "
                + " | ".join(f"{p if p is None else round(p, 2)} {f[:60]!r}" for p, f in zip(ps, frases, strict=True)))
    return ok
