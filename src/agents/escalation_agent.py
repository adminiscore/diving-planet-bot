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
núcleo y luego el gate, en el mismo orden que la cascada antigua. Es un no-op de
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

# gen-1 + gen-3 (20-oct, flag `contesta_antes_de_pasar`): el pase por tema sensible era una respuesta fija que se comía
# el resto del mensaje ("tengo asma… ¿y desde qué edad pueden bucear mis hijos?" -> solo el aviso médico). Con el flag,
# el RAG contesta las OTRAS preguntas, sin tocar el tema sensible, y después va la línea del pase. Solo médico y clima:
# una queja, una emergencia o un pago que falla se pasan sin más.
_TEMA_QUE_PASA = {
    "medical_questions": {"es": "su salud o una condición médica", "en": "their health or a medical condition"},
    "weather_conditions": {"es": "el tiempo o el estado del mar de un día concreto",
                           "en": "the weather or sea conditions on a specific day"},
}
_NADA = "NADA"
_SOLO_LO_DEMAS = {
    "es": ("El cliente pregunta también por {tema}: de eso se encarga una persona del equipo, así que NO lo contestes, "
           "no lo comentes y no des ningún consejo sobre ello. Busca en su mensaje las OTRAS preguntas (cualquier "
           "cosa que pregunte aparte de eso) y contéstalas todas, solo esas, con el contexto. No cierres con una "
           "pregunta ni ofrezcas nada: después de tu respuesta el cliente pasa con el equipo. Solo si el mensaje no "
           "pregunta nada aparte de {tema}, responde exactamente: " + _NADA),
    "en": ("The customer also asks about {tema}: a person from the team handles that, so do NOT answer it, do not "
           "comment on it and give no advice about it. Look in their message for the OTHER questions (anything they "
           "ask apart from that) and answer all of them, only those, from the context. Do not close with a question "
           "or offer anything: after your answer the customer is passed to the team. Only if the message asks "
           "nothing apart from {tema}, reply exactly: " + _NADA),
}


async def _lo_contestable(conv, message: str, reason: str, lang: str) -> str | None:
    """Lo que el RAG contesta del mensaje APARTE del tema sensible, o None (flag apagado, otro tema, nada más que
    contestar, "no lo tengo" o un fallo: entonces el pase va solo, como siempre)."""
    if reason not in _TEMA_QUE_PASA:
        return None
    conv._contestado_antes_del_pase = True  # gen-13: el cierre del turno no lo repite
    key = "es" if lang == "es" else "en"
    return await _contestar_lo_demas(conv, message, _TEMA_QUE_PASA[reason][key], key, reason)


# gen-13 (21-oct, flag `contesta_antes_de_cualquier_pase`): en G9 y G10, ~27 fallos en unos 15 diálogos eran pases a un
# asesor (contacto, pago, grupo privado, cambios de reserva, necesidades especiales, post-venta, «pásame con alguien»)
# que se comían el resto del mensaje: el cliente preguntaba también el precio, qué incluye o el enlace y se quedaba sin
# respuesta. Lo mismo que gen-1 para lo médico y el clima, pero para CUALQUIER pase y en un solo sitio: el cierre del
# turno (`supervisor.route_message`). No se contesta nada más en los pases que van solos a propósito.
_PASE_QUE_VA_SOLO = ("datos sensibles", "complaints_or_emergencies", "FALLO TÉCNICO")
_TEMA_DEL_PASE = {"es": "lo que va a gestionar una persona del equipo (motivo del pase: {motivo})",
                  "en": "what a person from the team will handle (handoff reason: {motivo})"}


async def lo_contestable_en_cualquier_pase(conv, message: str) -> str | None:
    """Cierre de un turno que acaba de pasar a un asesor: lo que el RAG contesta de las OTRAS preguntas del mensaje,
    sin tocar el motivo del pase, o None (flag apagado, ya contestado por gen-1, pase que va solo, mensaje sin
    pregunta, nada más que contestar, «no lo tengo» o un fallo)."""
    reason = conv.pending_escalation_reason or ""
    if getattr(conv, "_contestado_antes_del_pase", False) or any(m in reason for m in _PASE_QUE_VA_SOLO):
        return None
    from src.agents.conversational_core import _turn_has_question  # lazy

    if not _turn_has_question(message, getattr(conv, "_senales_router", None) or {}):
        return None
    key = "es" if conv.language == "es" else "en"
    tema = _TEMA_QUE_PASA[reason][key] if reason in _TEMA_QUE_PASA else _TEMA_DEL_PASE[key].format(motivo=reason)
    return await _contestar_lo_demas(conv, message, tema, key, reason)


def _es_nada(answer: str) -> bool:
    """¿El RAG contestó la palabra de control (`_NADA`: no había nada más que contestar)?

    22-oct (flag `nada_en_primera_linea`, Gonzalo con Claude): se miraba `startswith("NADA") and len(answer) < 30`, pero
    `rag_answer` pega detrás el aviso al final (`avisos_al_final`: «Operamos todos los días…»), así que la respuesta
    pasaba de 30 caracteres y «NADA» le llegaba al cliente (8 turnos en las rondas del 21-22, también en G10). Con el
    flag, cuenta la PRIMERA LÍNEA entera, sin límite de longitud; una respuesta real que empieza por «Nada, no hace
    falta…» no es la palabra sola. Lo mismo que FALTA en el redactor de hechos (a3e233f)."""
    lineas = answer.strip().splitlines()
    return bool(lineas) and lineas[0].strip(" .!¡*\"'").upper() == _NADA


async def _contestar_lo_demas(conv, message: str, tema: str, key: str, reason: str) -> str | None:
    from src.agents import rag_agent, supervisor  # lazy
    from src.agents.conversational_core import _entradas_rag, _hechos_para_el_rag  # lazy
    from src.config import settings  # lazy

    entradas = _entradas_rag(conv, conv.history, message)
    if settings.hechos_en_el_pase:
        # arq-5a (G10 nº 5, ~15 fallos con hechos=None): antes del pase el RAG contestaba de memoria lo que el mensaje
        # preguntaba de la tabla (qué incluye, precios, recogida, descuentos). Recibe los hechos del código, como en la
        # ruta normal. El mensaje aún no está en el historial: se añade para que los hechos sean los de este mensaje.
        historial = list(conv.history or [])
        if not historial or historial[-1].get("role") != "user" or historial[-1].get("content") != message:
            historial.append({"role": "user", "content": message})
        if hechos := await _hechos_para_el_rag(conv, message, historial, siempre=True):
            entradas["hechos"] = hechos
            if settings.rag_comprueba_los_hechos:
                entradas["hechos_bloques"] = conv._hechos_del_rag
    instruccion = _SOLO_LO_DEMAS[key].format(tema=tema)
    entradas["extra_context"] = f"{entradas['extra_context']}\n\n{instruccion}" if entradas.get("extra_context") \
        else instruccion
    try:
        answer = (await supervisor.rag_answer(message, **entradas) or "").strip()
    except Exception as exc:  # noqa: BLE001 — sin respuesta parcial, el pase va solo
        logger.warning(f"[NODE:escalation] contestar antes de pasar falló: {type(exc).__name__}: {exc}")
        return None
    if not answer or _es_nada(answer) or rag_agent.is_fallback_answer(answer):
        return None
    logger.info(f"[NODE:escalation] contesta antes de pasar ({reason}): {len(answer)} caracteres")
    return answer


# arq-1l (22-oct, flag `adaptado_contesta_lo_demas`): con el contexto de DIVE TO HEAL activo, CUALQUIER mensaje con
# «precio» o «reserva» recibía el texto fijo del buceo adaptado (precio a medida con un asesor, decisión del dueño del
# 17-jul), aunque preguntara por el acompañante, la moneda de un grupo mixto o una cancelación (G10 nº 2: 4 fallos). Lo
# del buceo adaptado sigue igual; lo demás lo contesta antes el RAG, con el mismo mecanismo que el pase (gen-13).
_TEMA_ADAPTADO = {"es": "el precio y la organización del buceo adaptado (DIVE TO HEAL)",
                  "en": "the price and arrangements of adaptive diving (DIVE TO HEAL)"}


async def respuesta_dive_to_heal(conv, message: str) -> str:
    """La respuesta a un precio o una reserva dentro de DIVE TO HEAL: el texto fijo del asesor y, con el flag, delante
    lo que el mensaje pregunta aparte del buceo adaptado."""
    from src.agents.rutas.safety import _adaptive_diving_advisor_answer  # lazy

    fija = _adaptive_diving_advisor_answer(conv.language)
    lang = "es" if conv.language == "es" else "en"
    resto = await _contestar_lo_demas(conv, message, _TEMA_ADAPTADO[lang], lang, "dive_to_heal")
    return f"{resto}\n\n{fija}" if resto else fija


async def escalation_node(state: BotState) -> dict:
    from src.agents.supervisor import (
        _ADAPTIVE_DIVING_PATTERN,
        _PRICE_OR_BOOKING_Q,
        _broken_link_escalation_response,
        _detect_broken_link_complaint,
        _has_link_tech_context,
        _needs_staff_handoff,
        _reply_language,
        _shared_turn_handler,
        build_lead_summary,
        detect_pii,
        detect_sensitive_escalation,
        privacy_block_message,
        regex_decide,
        sensitive_response_for,
    )

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}
    # s4-21 (5): en el mensaje de apertura el idioma aun no esta fijado; el aviso medico salia en
    # espanol a quien escribe en ingles. Misma estimacion local que la deflexion (`deflection_agent`).
    sensitive_lang = _reply_language(conv, message)

    # 1 · PII (pre-núcleo). Igual que la cascada: NO toca historial ni quick_replies.
    if detect_pii(message):
        conv.step = Step.ESCALATE
        conv.pending_escalation_reason = "datos sensibles detectados"
        logger.warning("[NODE:escalation] PII detectado -> bloqueo de privacidad")
        return {"reply": privacy_block_message(conv.language)}

    # 2 · Link roto por keyword (pre-núcleo).
    if regex_decide(signals) and _detect_broken_link_complaint(message, conv.history):
        logger.info("[NODE:escalation] link roto (keyword) -> escalado")
        return {"reply": _broken_link_escalation_response(conv, message)}

    # 3 · Link roto por señal LLM + contexto técnico (pre-núcleo).
    if signals.get("broken_link_complaint") and _has_link_tech_context(message, conv.history):
        logger.info("[NODE:escalation] link roto (señal LLM) -> escalado")
        return {"reply": _broken_link_escalation_response(conv, message)}

    # 4 · Tema sensible por keyword (suprimido si el turno es DIVE TO HEAL, igual
    #     que la cascada: sensitive_escalation_early es None si adaptive_diving_topic).
    sensitive_early = (
        None if signals.get("adaptive_diving_topic") or not regex_decide(signals)
        else detect_sensitive_escalation(message, sensitive_lang)
    )
    if sensitive_early:
        reason, response = sensitive_early
        # Antes de marcar el pase: con el paso en ESCALATE el RAG creía que ya estaba hecho ("el asesor ya tiene tu
        # caso") justo encima de "te paso ahora".
        antes = await _lo_contestable(conv, message, reason, sensitive_lang)
        conv.step = Step.ESCALATE
        conv.quick_replies = []
        conv.pending_escalation_reason = reason
        conv.pending_note = build_lead_summary(conv, escalation_reason=reason)
        logger.info(f"[NODE:escalation] sensible (keyword) reason={reason}")
        return {"reply": f"{antes}\n\n{response}" if antes else response}

    # 5 · Tema sensible por señal LLM.
    if signals.get("sensitive_topic"):
        found = sensitive_response_for(signals["sensitive_topic"], sensitive_lang)
        if found:
            reason, response = found
            antes = await _lo_contestable(conv, message, reason, sensitive_lang)  # antes del pase (ver arriba)
            conv.step = Step.ESCALATE
            conv.quick_replies = []
            conv.pending_escalation_reason = reason
            conv.pending_note = build_lead_summary(conv, escalation_reason=reason)
            logger.info(f"[NODE:escalation] sensible (señal LLM) reason={reason}")
            return {"reply": f"{antes}\n\n{response}" if antes else response}

    # 5b · s4-20: post-venta / empresa (Jev `needs_staff`) -> una persona.
    staff = _needs_staff_handoff(conv, message, signals)
    if staff:
        return {"reply": staff}

    # 6 · DIVE TO HEAL precio/reserva -> asesor (sin precios genéricos). Persiste
    #     el contexto adaptativo igual que la cascada (líneas 2130-2146). El router
    #     garantiza que si llegó aquí como SAFETY vía DIVE TO HEAL, hay pregunta de
    #     precio (si no, habría devuelto INFO), así que este gate dispara.
    adaptive_now = (regex_decide(signals) and bool(_ADAPTIVE_DIVING_PATTERN.search(message))) or bool(
        signals.get("adaptive_diving_topic"))
    if adaptive_now:
        conv.adaptive_diving_context = True
    if conv.adaptive_diving_context and _PRICE_OR_BOOKING_Q.search(message):
        if conv.step in (Step.WELCOME, Step.LANGUAGE):
            conv.step = Step.MAIN_MENU
        answer = await respuesta_dive_to_heal(conv, message)
        conv.history.append({"role": "user", "content": message})
        conv.history.append({"role": "assistant", "content": answer})
        logger.info("[NODE:escalation] DIVE TO HEAL precio/reserva -> asesor")
        return {"reply": answer}

    # 7 · Gates SAFETY POST-núcleo (wants_human / keyword de escalado / afirmación
    #     que acepta la oferta de asesor) + defensa "sin fugas": delegar en la
    #     cascada preserva el orden exacto (corre el núcleo y luego el gate).
    logger.info("[NODE:escalation] gate post-núcleo / sin match -> delego en la cascada")
    return {"reply": await _shared_turn_handler(conv, message, routing_signals=signals)}
