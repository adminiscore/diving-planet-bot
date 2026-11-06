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
2-5. **Link roto, tema sensible y post-venta**: 6-nov (#3664), ya no se copian aquí; los mira la cascada, a la
   que se delega, con el mismo orden y las mismas condiciones (más el filtro del clima en general, que aquí faltaba).
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
    if any(m in reason for m in _PASE_QUE_VA_SOLO):
        return None
    from src.agents.conversational_core import _turn_has_question  # lazy
    from src.agents.supervisor import _reply_language  # lazy

    if not _turn_has_question(message, getattr(conv, "_senales_router", None) or {}):
        return None
    # s4-21 (5): en la apertura el idioma aún no está fijado; se estima del mensaje, como el aviso del pase.
    key = "es" if _reply_language(conv, message) == "es" else "en"
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

    entradas = _entradas_rag(conv, conv.history, message)
    # arq-5a (G10 nº 5, ~15 fallos con hechos=None): antes del pase el RAG contestaba de memoria lo que el mensaje
    # preguntaba de la tabla (qué incluye, precios, recogida, descuentos). Recibe los hechos del código, como en la
    # ruta normal. El mensaje aún no está en el historial: se añade para que los hechos sean los de este mensaje.
    historial = list(conv.history or [])
    if not historial or historial[-1].get("role") != "user" or historial[-1].get("content") != message:
        historial.append({"role": "user", "content": message})
    if hechos := await _hechos_para_el_rag(conv, message, historial, siempre=True):
        entradas["hechos"] = hechos
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
        _shared_turn_handler,
        detect_pii,
        pasar_a_persona,
        pase_pedido_o_aceptado,
        privacy_block_message,
        regex_decide,
    )

    conv = state["conv_state"]
    message = state["message"]
    signals = state.get("signals") or {}

    # 1 · PII (pre-núcleo). Igual que la cascada: NO toca historial ni quick_replies.
    if detect_pii(message):
        pasar_a_persona(conv, "datos sensibles detectados", con_nota=False, sin_botones=False)
        logger.warning("[NODE:escalation] PII detectado -> bloqueo de privacidad")
        return {"reply": privacy_block_message(conv.language)}

    # 2-5 · El link roto, el tema sensible y la post-venta los mira la cascada (`supervisor._shared_turn_handler`),
    #     a la que se delega abajo: antes estaban copiados aquí (6-nov, «el pase en una función», #3664). Lo que el
    #     mensaje pregunta aparte del tema sensible lo contesta el cierre del turno (`lo_contestable_en_cualquier_pase`).

    # 6 · DIVE TO HEAL precio/reserva -> asesor (sin precios genéricos). Persiste
    #     el contexto adaptativo igual que la cascada (líneas 2130-2146). El router
    #     garantiza que si llegó aquí como SAFETY vía DIVE TO HEAL, hay pregunta de
    #     precio (si no, habría devuelto INFO), así que este gate dispara.
    adaptive_now = (regex_decide(signals) and bool(_ADAPTIVE_DIVING_PATTERN.search(message))) or bool(
        signals.get("adaptive_diving_topic"))
    if adaptive_now:
        if not signals.get("adaptive_diving_topic"):
            from src.observability import marca_regex  # lazy

            marca_regex("R23")  # CALN-8 (6): DIVE TO HEAL por regex, sin la señal de la IA
        conv.adaptive_diving_context = True
    if conv.adaptive_diving_context and (pase := pase_pedido_o_aceptado(conv, message, signals)):
        logger.info("[NODE:escalation] DIVE TO HEAL: pide o acepta el asesor -> pase")
        return {"reply": pase}  # s03a: antes que el texto del programa
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
