"""Nodo-agente `escalation` (Fase 2.2) — el segundo nodo REAL del grafo.

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.2 y §4.bis (taxonomía).

## Qué maneja

La ruta `ROUTE_SAFETY` (lo que `router.classify_route` clasifica como
"safety first"). En la cascada esa ruta se decide en SEIS gates, y el router
los devuelve todos como SAFETY. La clave de la equivalencia es DÓNDE están esos
gates respecto al núcleo conversacional (`maybe_handle_turn`):

**Gates PRE-núcleo** (la cascada los resuelve ANTES de tocar el núcleo → son
predicados puros → este nodo los reproduce directamente, equivalencia exacta):

1. **PII** (`detect_pii`) → bloqueo de privacidad (`privacy_block_message`),
   `step=ESCALATE`. No toca historial ni quick_replies (igual que la cascada).
2. **Link roto por keyword** (`_detect_broken_link_complaint`) →
   `_broken_link_escalation_response` (dueño de su propio estado).
3. **Link roto por señal LLM** (`broken_link_complaint` + `_has_link_tech_context`)
   → misma respuesta.
4. **Tema sensible por keyword** (`detect_sensitive_escalation`, suprimido si el
   turno es DIVE TO HEAL) → escala con `pending_note` (lead summary).
5. **Tema sensible por señal LLM** (`sensitive_topic` → `sensitive_response_for`).
6. **DIVE TO HEAL precio/reserva** (`adaptive_diving_context` + `_PRICE_OR_BOOKING_Q`)
   → respuesta de asesor, sin precios genéricos. Persiste `adaptive_diving_context`
   igual que la cascada.

**Gates POST-núcleo** (wants_human / keyword de escalado / afirmación que acepta
la oferta de asesor): en la cascada están DESPUÉS de `maybe_handle_turn`, así que
la cascada corre el núcleo PRIMERO y solo cae a estos gates si el núcleo devuelve
None. Reproducirlos aquí sin correr el núcleo cambiaría el orden → posible
divergencia. Por eso NO se reproducen: se **delega en la cascada**, que corre el
núcleo y luego el gate, exactamente como con el flag off. Es un no-op de
comportamiento pero mantiene la equivalencia garantizada (patrón del nodo
`deflection`: se maneja lo aislado, se delega la cola).

El audit del shadow (§1.5, 2026-07-29) midió **0 mismatches en SAFETY** sobre la
suite adversaria — router y cascada coinciden en toda la ruta —, lo que respalda
que reproducir los 6 gates pre-núcleo en este orden da la misma ruta.

## Orden y garantía del router

Cuando el router manda a SAFETY vía un gate concreto, todos los gates
intermedios de otras rutas (cancelar/reprogramar=CHANGE, contacto/identidad=
DEFLECT, mixta=BOOKING, edad=INFO, DIVE TO HEAL no-precio=INFO) ya dieron False
—si no, el router habría devuelto esa otra ruta—. Por eso el nodo no los
re-chequea: salta directo entre los gates SAFETY en el mismo orden de la cascada.

Detectores y copys viven todavía en `supervisor.py` (import perezoso, patrón del
repo); migrarán a un módulo propio del router en Fase 3.

## Resiliencia (principio #10, "sin fugas")

El caso por defecto (ningún gate pre-núcleo matchea) NO dropea el turno: delega
en la cascada, que siempre responde.
"""

from __future__ import annotations

import logging

from src.flows.state import Step
from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


async def escalation_node(state: BotState) -> dict:
    from src.agents.supervisor import (
        _ADAPTIVE_DIVING_PATTERN,
        _PRICE_OR_BOOKING_Q,
        _adaptive_diving_advisor_answer,
        _broken_link_escalation_response,
        _detect_broken_link_complaint,
        _has_link_tech_context,
        _route_message_inner,
        build_lead_summary,
        detect_pii,
        detect_sensitive_escalation,
        privacy_block_message,
        sensitive_response_for,
    )

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}

    # 1 · PII (pre-núcleo). Igual que la cascada: NO toca historial ni quick_replies.
    if detect_pii(message):
        conv.step = Step.ESCALATE
        conv.pending_escalation_reason = "datos sensibles detectados"
        logger.warning("[NODE:escalation] PII detectado -> bloqueo de privacidad")
        return {"reply": privacy_block_message(conv.language)}

    # 2 · Link roto por keyword (pre-núcleo).
    if _detect_broken_link_complaint(message, conv.history):
        logger.info("[NODE:escalation] link roto (keyword) -> escalado")
        return {"reply": _broken_link_escalation_response(conv, message)}

    # 3 · Link roto por señal LLM + contexto técnico (pre-núcleo).
    if signals.get("broken_link_complaint") and _has_link_tech_context(message, conv.history):
        logger.info("[NODE:escalation] link roto (señal LLM) -> escalado")
        return {"reply": _broken_link_escalation_response(conv, message)}

    # 4 · Tema sensible por keyword (suprimido si el turno es DIVE TO HEAL, igual
    #     que la cascada: sensitive_escalation_early es None si adaptive_diving_topic).
    sensitive_early = (
        None if signals.get("adaptive_diving_topic")
        else detect_sensitive_escalation(message, conv.language)
    )
    if sensitive_early:
        reason, response = sensitive_early
        conv.step = Step.ESCALATE
        conv.quick_replies = []
        conv.pending_escalation_reason = reason
        conv.pending_note = build_lead_summary(conv, escalation_reason=reason)
        logger.info(f"[NODE:escalation] sensible (keyword) reason={reason}")
        return {"reply": response}

    # 5 · Tema sensible por señal LLM.
    if signals.get("sensitive_topic"):
        found = sensitive_response_for(signals["sensitive_topic"], conv.language)
        if found:
            reason, response = found
            conv.step = Step.ESCALATE
            conv.quick_replies = []
            conv.pending_escalation_reason = reason
            conv.pending_note = build_lead_summary(conv, escalation_reason=reason)
            logger.info(f"[NODE:escalation] sensible (señal LLM) reason={reason}")
            return {"reply": response}

    # 6 · DIVE TO HEAL precio/reserva -> asesor (sin precios genéricos). Persiste
    #     el contexto adaptativo igual que la cascada (líneas 2130-2146). El router
    #     garantiza que si llegó aquí como SAFETY vía DIVE TO HEAL, hay pregunta de
    #     precio (si no, habría devuelto INFO), así que este gate dispara.
    adaptive_now = bool(_ADAPTIVE_DIVING_PATTERN.search(message)) or bool(signals.get("adaptive_diving_topic"))
    if adaptive_now:
        conv.adaptive_diving_context = True
    if conv.adaptive_diving_context and _PRICE_OR_BOOKING_Q.search(message):
        if conv.step in (Step.WELCOME, Step.LANGUAGE):
            conv.step = Step.MAIN_MENU
        answer = _adaptive_diving_advisor_answer(conv.language)
        conv.history.append({"role": "user", "content": message})
        conv.history.append({"role": "assistant", "content": answer})
        logger.info("[NODE:escalation] DIVE TO HEAL precio/reserva -> asesor")
        return {"reply": answer}

    # 7 · Gates SAFETY POST-núcleo (wants_human / keyword de escalado / afirmación
    #     que acepta la oferta de asesor) + defensa "sin fugas": delegar en la
    #     cascada preserva el orden exacto (corre el núcleo y luego el gate).
    logger.info("[NODE:escalation] gate post-núcleo / sin match -> delego en la cascada")
    return {"reply": await _route_message_inner(conv, message, routing_signals=signals)}
