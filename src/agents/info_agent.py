"""Nodo-agente `info` (Fase 2.4) — el cuarto nodo REAL del grafo.

Ver `docs/multi-agent-refactor-plan.md` §5 Fase 2.4 y §4.bis (taxonomía).

## Qué maneja

La ruta `ROUTE_INFO` (preguntas de información factual que la cascada resuelve
ANTES del núcleo). Dos gates, ambos **pre-núcleo** → se reproducen directamente:

1. **Elegibilidad por edad** (`_maybe_answer_age_eligibility`): respuesta
   determinista desde la única fuente de verdad (`eligibility.py`), sin RAG ni
   alucinación. Es el gate del "patrón A" del audit §1.5, ahora enrutado a INFO
   por `router._looks_like_age_eligibility_question` (predicado puro).
2. **DIVE TO HEAL no-precio** (`_ADAPTIVE_DIVING_PATTERN` / señal
   `adaptive_diving_topic`, sin pregunta de precio): info factual del programa de
   buceo adaptado vía `rag_answer` (RAG con grounding, en Python plano). Las
   preguntas de precio dentro de DIVE TO HEAL son SAFETY (nodo `escalation`), no
   INFO — el router ya las separa.

La RAG queda en Python plano dentro del nodo (no envuelta en abstracciones de
LangChain), como pide el plan. Detectores/handlers viven todavía en
`supervisor.py` (import perezoso, patrón del repo); migran en Fase 3.

## Orden y garantía del router

El router comprueba edad ANTES de DIVE TO HEAL (igual que la cascada: línea 2109
vs 2117), así que este nodo hace lo mismo. Si el router mandó INFO, los gates de
otras rutas (SAFETY/CHANGE/DEFLECT/mixta) ya dieron False.

## Resiliencia (principio #10, "sin fugas")

`_looks_like_age_eligibility_question` es una aproximación (puede sobre-disparar);
si el gate de edad real devuelve None y tampoco es DIVE TO HEAL, NO se dropea el
turno: se delega en la cascada, que siempre responde.
"""

from __future__ import annotations

import logging

from src.flows.state import Step
from src.orchestration.state import BotState

logger = logging.getLogger("uvicorn.error")


async def info_node(state: BotState) -> dict:
    from src.agents.supervisor import (
        _ADAPTIVE_DIVING_PATTERN,
        _PRIVATE_GROUP_EVENT_RE,
        _alcohol_and_food_policy_answer,
        _build_extra_context,
        _maybe_answer_age_eligibility,
        _private_group_event_answer,
        _shared_turn_handler,
        rag_answer,
    )

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}
    msg_lower = message.strip().lower()

    # 0 · Alcohol/alergia alimentaria (portado de pre_gadea v0.21.11): política
    #     plana conocida, respuesta determinista sin RAG ni escalado médico.
    #     El router ya distinguió estos casos del resto de ROUTE_INFO. Ambos
    #     temas se combinan si el mensaje menciona los dos a la vez (hallazgo
    #     en vivo, lote 9, 2026-09-02 — antes el primero que matcheaba
    #     pisaba al otro con un return inmediato).
    combined_policy_text = _alcohol_and_food_policy_answer(msg_lower, conv.language)
    if combined_policy_text is not None:
        logger.info("[NODE:info] Alcohol/food-allergy question -> real policy text, not medical escalation")
        conv.history.append({"role": "user", "content": message})
        conv.history.append({"role": "assistant", "content": combined_policy_text})
        return {"reply": combined_policy_text}

    # 0.bis · Evento corporativo/grupo privado (hallazgo en vivo, lote 11,
    #     2026-09-02): política plana conocida que RAG alucinaba en vez de
    #     retomar; respuesta determinista, redactada para no filtrar el
    #     número de WhatsApp de la política cruda.
    if _PRIVATE_GROUP_EVENT_RE.search(msg_lower):
        answer = _private_group_event_answer(conv.language)
        logger.info("[NODE:info] Private/corporate group event -> real deterministic answer")
        conv.history.append({"role": "user", "content": message})
        conv.history.append({"role": "assistant", "content": answer})
        return {"reply": answer}

    # 1 · Elegibilidad por edad (pre-núcleo, determinista desde eligibility.py).
    age_answer = _maybe_answer_age_eligibility(message, conv)
    if age_answer is not None:
        logger.info("[NODE:info] elegibilidad por edad -> respuesta determinista")
        conv.history.append({"role": "user", "content": message})
        conv.history.append({"role": "assistant", "content": age_answer})
        return {"reply": age_answer}

    # 2 · DIVE TO HEAL no-precio -> RAG (info factual del programa). Persiste el
    #     contexto adaptativo igual que la cascada (líneas 2130-2131). El usuario
    #     se añade al historial ANTES de llamar a RAG (para que lo vea), como en
    #     la cascada.
    adaptive_now = bool(_ADAPTIVE_DIVING_PATTERN.search(message)) or bool(signals.get("adaptive_diving_topic"))
    if adaptive_now:
        conv.adaptive_diving_context = True
    # Hallazgo en vivo (batería de frontera contra PRE, 2026-09-01): usar solo
    # `adaptive_now` aquí (en vez del flag persistido) perdía el contexto en
    # un seguimiento genérico sin palabra de discapacidad en ESE mensaje — el
    # router ya solo manda aquí cuando `adaptive_context` (persistido o de
    # este turno) es true, así que el nodo debe reproducir el mismo criterio.
    if conv.adaptive_diving_context:
        if conv.step in (Step.WELCOME, Step.LANGUAGE):
            conv.step = Step.MAIN_MENU
        conv.history.append({"role": "user", "content": message})
        extra_context = _build_extra_context(conv)
        answer = await rag_answer(
            message, lang=conv.language, history=conv.history, extra_context=extra_context
        )
        conv.history.append({"role": "assistant", "content": answer})
        logger.info("[NODE:info] DIVE TO HEAL no-precio -> RAG")
        return {"reply": answer}

    # 3 · Defensa "sin fugas": el router aproximó INFO pero ningún gate dispara
    #     (p. ej. `_looks_like_age_eligibility_question` sobre-disparó) -> delegar
    #     en la cascada, que siempre responde.
    logger.info("[NODE:info] sin match (aproximación del router) -> delego en la cascada")
    return {"reply": await _shared_turn_handler(conv, message, routing_signals=signals)}
