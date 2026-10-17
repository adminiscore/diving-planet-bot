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
import re

from src.config import settings
from src.observability import con_pieza_llm

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


# EX-RAG-3 (flag `juez_revisa_con_cita`, 14-oct). Rondas g10-A/B: el juez rechazó 7 de ~123 respuestas cada vez y la
# segunda opinión de Jev no salvó ninguna (las frases sí afirman datos del negocio), aunque varias estaban en el
# contexto: "si son colombianos pagan en pesos; el precio es el mismo" (política colombian_pricing), "la recogida
# depende de que el hotel tenga acceso marítimo" (island_pickup). Al regenerar, la respuesta salía peor (el cliente se
# quedaba sin la respuesta a su pregunta). Ahora, solo cuando el juez rechaza, cada frase rechazada tiene que traer la
# CITA LITERAL del contexto que la respalda, y el código comprueba que la cita está en el contexto y que toda cifra o
# enlace de la frase está en el contexto: un invento no puede presentar una cita real.
_VERIFICADOR_ES = (
    "Eres un verificador. Para cada FRASE de una respuesta, busca en el CONTEXTO un fragmento LITERAL (copiado tal "
    "cual) que respalde lo que la frase afirma del negocio. Si la frase afirma algo que el contexto no dice, o lo "
    "contradice, cita null. Responde SOLO JSON: {\"respaldos\": [{\"frase\": \"...\", \"cita\": \"...\" o null}]}"
)
_VERIFICADOR_EN = (
    "You are a verifier. For each SENTENCE of a reply, find in the CONTEXT a LITERAL fragment (copied exactly) that "
    "supports what the sentence states about the business. If the sentence states something the context doesn't say, "
    "or contradicts it, quote null. Answer ONLY JSON: {\"respaldos\": [{\"frase\": \"...\", \"cita\": \"...\" or null}]}"
)
_CIFRA_O_ENLACE = re.compile(r"https?://\S+|\d[\d.,]*")


def _cifras_y_enlaces(texto: str) -> set[str]:
    """Cifras (sin separadores de miles) y enlaces de un texto: lo que una cita parcial podría colar."""
    salida = set()
    for m in _CIFRA_O_ENLACE.findall(texto or ""):
        salida.add(m.rstrip(".,)") if m.startswith("http") else re.sub(r"[.,]", "", m))
    return {s for s in salida if s}


@con_pieza_llm("segunda_opinion")
async def respaldadas_con_cita(frases: list[str], contexto: str, lang: str = "es") -> bool:
    """True solo si TODAS las frases rechazadas traen una cita literal del contexto y sus cifras y enlaces están en él."""
    import json

    from openai import AsyncOpenAI

    from src.agents.extractor_turno import cita_verificable
    from src.llm_client import trace_openai

    if not frases or not contexto.strip():
        return False
    try:
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        resp = await client.chat.completions.create(
            model=settings.grounding_v3_model,
            temperature=0,
            max_tokens=900,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _VERIFICADOR_ES if lang == "es" else _VERIFICADOR_EN},
                      {"role": "user", "content": "CONTEXTO:\n" + contexto + "\n\nFRASES:\n"
                       + "\n".join(f"- {f}" for f in frases)}],
        )
        respaldos = json.loads(resp.choices[0].message.content or "{}").get("respaldos") or []
    except Exception as exc:  # noqa: BLE001 — sin verificación: el rechazo se mantiene (la conducta de hoy)
        logger.warning(f"[RAG][GROUNDING][CITA] sin verificación: {type(exc).__name__}: {exc}")
        return False
    citas = {}
    for r in respaldos:
        if isinstance(r, dict) and r.get("frase"):
            citas[r["frase"].strip()] = r.get("cita")
    en_contexto = _cifras_y_enlaces(contexto)
    resultado = []
    for f in frases:
        cita = citas.get(f.strip()) or next((c for k, c in citas.items() if k[:40] == f.strip()[:40]), None)
        ok = bool(cita) and cita_verificable(cita, contexto) and _cifras_y_enlaces(f) <= en_contexto
        resultado.append((ok, f, cita))
    todas = all(ok for ok, _, _ in resultado)
    logger.info(f"[RAG][GROUNDING][CITA] {'pasa' if todas else 'se mantiene'}: "
                + " | ".join(f"{'ok' if ok else 'no'} {f[:50]!r}" for ok, f, _ in resultado))
    return todas
