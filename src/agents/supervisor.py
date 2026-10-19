"""
LangGraph Supervisor Agent.

Routes incoming messages to the appropriate handler:
- Decision tree: for structured menu flows (user is navigating options)
- RAG agent: for free-text questions outside the menu flow
- Escalation: when user explicitly asks for a human

The routing logic is deterministic (no LLM call for routing),
keeping costs minimal.
"""

import logging
import re

from src.agents import conversation_summarizer
from src.agents.escalation import (
    detect_routing_signals,  # noqa: F401 — el nodo router del grafo lo importa de aquí (y los tests lo parchean aquí)
    detect_sensitive_escalation,
    sensitive_response_for,
)
from src.agents.lead_summary import build_lead_summary
from src.agents.rag_agent import (  # noqa: F401 — el núcleo llama a `supervisor.rag_answer`
    is_fallback_answer,
    rag_answer,
)
from src.config import settings
from src.flows.state import ConversationState, Step
from src.privacy import (  # noqa: F401 — los usan el router y el nodo `escalation`
    detect_pii,
    privacy_block_message,
)

logger = logging.getLogger("uvicorn.error")


# Adaptive diving / DIVE TO HEAL: disability & accessibility questions that must
# be answered with the program's factual info (via RAG) instead of being routed
# into the booking flow. NOT a medical escalation — it's the documented exception.
_ADAPTIVE_DIVING_PATTERN = re.compile(
    r"\b("
    r"dive\s*to\s*heal|buceo\s+adaptado|adaptive\s+diving|"
    r"discapacidad|discapacitad[ao]s?|disabilit(?:y|ies)|disabled|accesibilidad|accessibilit(?:y)|"
    r"s[ií]ndrome\s+de\s+down|down\s+syndrome|autismo|autis(?:m|tic)|"
    r"par[aá]lisis\s+cerebral|cerebral\s+palsy|"
    r"movilidad\s+reducida|reduced\s+mobility|silla\s+de\s+ruedas|wheelchair|"
    r"coj[oa]s?|cojera|limp(?:s|ing)?|"
    r"sord[ao]s?|deaf|cieg[ao]s?|invidente|blind|"
    r"discapacidad\s+(?:visual|auditiva|motora|f[ií]sica|intelectual)"
    r")\b",
    re.IGNORECASE,
)


def regex_decide(signals: dict | None) -> bool:
    """ex-9b paso 5 (flag `regex_solo_si_ia_calla`, estudio docs/robustness/regex/estudio-ex9-regex.md): ¿puede decidir
    este turno una lista de palabras o un regex que tiene su señal de IA (link roto, tema sensible, cancelar/cambiar,
    contacto, "hablar con", DIVE TO HEAL)? Siempre con el flag apagado; con él, solo si la IA calla (Jev y el router
    LLM de respaldo no han dejado señales: fallo de los dos o clic de botón). Es la única regla y la usan todos los
    lectores: el router, los nodos, `setup` y la cascada. Si solo la mirara el router, el nodo de reserva volvía a ver
    "hablar con" en "quiero hablar con mi esposa antes de reservar" y pasaba igual a una persona."""
    return not (settings.regex_solo_si_ia_calla and bool(signals))


# Afirmacion "a secas" ("si", "dale", "ok") — usada para cumplir una oferta que
# el propio bot hizo en el turno anterior (p.ej. "¿te paso con un asesor?").
_BARE_AFFIRMATION_RE = re.compile(
    r"^\s*(s[ií]+|yes|yep|yeah|ok(?:ay)?|dale|claro(?:\s+que\s+s[ií])?|vale|"
    r"por\s+favor|s[ií]\s+por\s+favor|de\s+una|perfecto|me\s+gustar[ií]a|sure|please)"
    r"[\s!.,)]*$",
    re.IGNORECASE,
)
# La oferta del bot que ese "si" acepta: mencion de asesor + verbo de oferta.
_ADVISOR_OFFER_RE = re.compile(r"\b(asesor|advisor|mi jefe|my boss)\b", re.IGNORECASE)
_OFFER_VERB_RE = re.compile(
    r"(te paso|puedo pasarte|te conecto|puedo conectarte|te pongo en contacto|"
    r"pasarte el contacto|te gustar[ií]a|quieres que|connect you|put you in touch|"
    r"pass you the contact|would you like)",
    re.IGNORECASE,
)


# Keywords that indicate escalation to a human
ESCALATION_KEYWORDS = {
    "humano", "human", "agente", "agent", "asesor", "advisor",
    "hablar con", "speak with", "talk to",
}


def _booking_change_buttons(lang: str) -> list[dict]:
    if lang == "es":
        return [
            {"title": "🧑‍💬 Hablar con un asesor", "value": "asesor"},
            {"title": "🏠 Menú principal", "value": "inicio"},
        ]
    return [
        {"title": "🧑‍💬 Talk to an advisor", "value": "asesor"},
        {"title": "🏠 Main menu", "value": "inicio"},
    ]


ENGLISH_HINTS = {
    "we", "are", "family", "certified", "divers", "snorkel", "snorkeling",
    "can", "together", "price", "book", "booking", "discount", "payment",
    "meeting", "point", "open water",
}

SPANISH_HINTS = {
    "somos", "familia", "buzos", "certificados", "bucear", "snorkel",
    "precio", "reservar", "reserva", "descuento", "pago", "juntos",
    "punto de encuentro",
}


def _matches_escalation_keyword(msg_lower: str) -> bool:
    """Word-boundary matching for escalation keywords to avoid false positives.

    Multi-word phrases ("hablar con") use substring matching; single words use
    word boundaries so "persona" does not match inside "personas".
    """
    for kw in ESCALATION_KEYWORDS:
        if " " in kw:
            if kw in msg_lower:
                return True
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", msg_lower):
                return True
    return False


def _infer_language(message: str, fallback: str = "es") -> str:
    # Verificado en vivo (2026-08-26, al validar el fix de idioma en el
    # bloque de cancelación, portado de pre_gadea): el padding literal
    # `f" {hint} "` fallaba con puntuación pegada al hint — "cancel my
    # booking, something came up" tiene "booking," (coma sin espacio), así
    # que " booking " nunca matcheaba y el mensaje entero se clasificaba
    # como español por defecto. `\b` (límite de palabra real, ciego a la
    # puntuación adyacente) es el criterio correcto.
    normalized = message.strip().lower()
    english_matches = sum(
        1 for hint in ENGLISH_HINTS if re.search(rf"\b{re.escape(hint)}\b", normalized)
    )
    spanish_matches = sum(
        1 for hint in SPANISH_HINTS if re.search(rf"\b{re.escape(hint)}\b", normalized)
    )
    if english_matches > spanish_matches:
        return "en"
    if spanish_matches > english_matches:
        return "es"
    return fallback


async def route_message(state: ConversationState, message: str) -> str:
    """Public entry point. Delegates to the actual routing logic, then
    updates the rolling conversation summary (Fase B, see
    docs/archive/memory-context-improvement-plan.md) once per turn — a thin wrapper
    so the summary check runs regardless of which internal branch below
    handled the message, without threading it through every early return.

    El turno pasa siempre por el grafo LangGraph (`orchestration.graph` — router
    → 5 nodos-agente reales + subgrafo booking), y esos nodos delegan en
    `_shared_turn_handler` para el núcleo + tail post-núcleo + fallback de
    resiliencia (ver su docstring). s4-1 (19-oct) quitó el flag `agent_arch`
    (Fase 1.4, docs/multi-agent-refactor-plan.md), que llevaba semanas en True,
    y con él el camino apagado: la cascada llamada aquí directamente.

    Observabilidad (m0-1): todo el turno va dentro de `turn_trace` — una traza
    raíz `turno` por mensaje, en contexto limpio y con el resumen del turno.
    """
    from src.agents.conversational_core import _is_greeting_only
    from src.observability import note_turn, turn_trace

    escalation_before = state.pending_escalation_reason
    async with turn_trace(settings, state.conversation_id, message) as turn:
        note_turn(language=state.language, greeting=_is_greeting_only(message))
        from src.orchestration.graph import run_turn_via_graph
        response = await run_turn_via_graph(state, message)
        # l1-4: red de seguridad. Si el turno no pasó por RAG, la captura de notas
        # que `_setup_phase` lanzó en paralelo puede seguir viva; hay que esperarla
        # ANTES de que el canal guarde el estado o se perdería la nota. Es no-op
        # cuando el flag está apagado o cuando ya se esperó en el RAG.
        from src.agents.conversational_core import (
            attach_unused_answer,
            await_pending_notes,
            cancel_pending_ack,
            cancel_pending_answer,
            cancelar_extraccion_adelantada,
            cancelar_rag_adelantado,
            guardar_lo_dicho_en_el_pase,
            guardar_lo_dicho_sin_nucleo,
        )
        if state.pending_escalation_reason == escalation_before:  # un traspaso a persona va solo
            response = await attach_unused_answer(state, response)
        await await_pending_notes(state)
        # u3-1 paso 3 / u3-4: un acuse o una respuesta lanzados en paralelo que el turno no
        # usó se cancelan.
        cancel_pending_ack(state)
        cancel_pending_answer(state)
        cancelar_rag_adelantado(state)  # rag-5: la respuesta adelantada que nadie usó
        if state.pending_escalation_reason not in (None, escalation_before):
            await guardar_lo_dicho_en_el_pase(state)  # EX-EST-2: lo que dijo en el turno del pase no se pierde
        await guardar_lo_dicho_sin_nucleo(state)  # G3-01: ni en un turno con respuesta fija (núcleo sin correr)
        cancelar_extraccion_adelantada(state)  # ex-5: la extracción adelantada que nadie usó
        await conversation_summarizer.maybe_update_summary(state)
        turn.update(
            reply=response,
            language=state.language,
            step=getattr(state.step, "value", state.step),
            escalated=state.pending_escalation_reason is not None and state.pending_escalation_reason != escalation_before,
            # Embudo de negocio (m0-5): qué tiene la conversación al acabar el turno.
            activity_chosen=bool(state.selected_service or state.mixed_cart),
            cart_items=sum(int(item.get("qty") or 0) for item in state.mixed_cart) if state.mixed_cart else 0,
            fallback=is_fallback_answer(response),
        )
        if settings.aviso_si_openai_falla:
            from src.observability import fallo_de_openai_en_el_turno

            codigo = fallo_de_openai_en_el_turno()
            if codigo is not None:
                response = _respuesta_fallo_tecnico(state, codigo)
                turn.update(reply=response, escalated=True, fallo_openai=codigo)
        return response


# r6-1(b) (17-oct, flag `aviso_si_openai_falla`): con OpenAI caído (sin saldo, clave inválida, saturado), cada pieza se
# degradaba por su cuenta y el bot contestaba "ese detalle no lo tengo a la mano" a todo, incluso al punto de
# encuentro: el cliente creía que el bot no sabía y nadie del equipo se enteraba (esta semana PRE se quedó así dos
# veces). Si en un turno NINGUNA llamada a OpenAI funcionó, se dice la verdad y se pasa a una persona; el motivo del
# pase es la alerta para el equipo en Chatwoot.
_FALLO_TECNICO_ES = ("Perdona, estoy teniendo un problema técnico y ahora mismo no puedo responderte bien. Ya he avisado "
                     "a un asesor del equipo, que te escribe por aquí en cuanto pueda. 🙏")
_FALLO_TECNICO_EN = ("Sorry, I'm having a technical problem and can't answer you properly right now. I've already let an "
                     "advisor from the team know, and they'll write to you here as soon as they can. 🙏")


def _respuesta_fallo_tecnico(state: ConversationState, codigo: int) -> str:
    motivo = {401: "clave inválida", 429: "sin saldo o saturado"}.get(codigo, "no responde")
    reason = f"⚠️ FALLO TÉCNICO: OpenAI {motivo} (código {codigo}) — revisar saldo y clave de OpenAI"
    if state.pending_escalation_reason and "FALLO TÉCNICO" not in state.pending_escalation_reason:
        # El turno ya pasaba a un asesor por otra cosa ("LINK ROTO"…): ese motivo se conserva y se añade el técnico.
        reason = f"{state.pending_escalation_reason} | {reason}"
    state.step = Step.ESCALATE
    state.quick_replies = []
    state.pending_escalation_reason = reason
    state.pending_note = build_lead_summary(state, escalation_reason=reason)
    logger.error(f"[ALERTA][OPENAI] ningún modelo de OpenAI respondió en el turno (código {codigo}): pase a un asesor")
    return _FALLO_TECNICO_ES if state.language == "es" else _FALLO_TECNICO_EN


async def _shared_turn_handler(
    state: ConversationState, message: str, routing_signals: dict
) -> str:
    """
    Handler de turno COMPARTIDO — renombrado (Fase 5.2 paso 2,
    docs/multi-agent-refactor-plan.md §5) desde `_route_message_inner` porque
    ese nombre sugería "cascada legacy a punto de borrarse" y ya no es
    correcto: esta función NO es un camino muerto en paralelo al grafo — es
    la pieza que los 5 nodos-agente reales
    (`deflection`/`escalation`/`changes`/`info`/`booking`) siguen usando por
    dos motivos, documentados en el 🔎 PREP de reachability del plan:

    1. **Núcleo + tail post-núcleo**: `booking/setup` delega aquí el núcleo
       conversacional completo (slot-fill, multi-ítem, cierre) y el tail que
       viene después (idioma, bare-affirmation). Ningún nodo reproduce el
       núcleo por su cuenta — sería duplicar ~2200 líneas.
    2. **Fallback de resiliencia (principio #10, "sin fugas")**: cuando un
       nodo no matchea ningún gate pre-núcleo que sí reproduce directamente,
       delega aquí en vez de dropear el turno — esta función SIEMPRE
       responde algo.

    s4-1 (19-oct) quitó el flag `agent_arch`: ya no hay cascada que
    `route_message` llame directamente, solo la llaman los nodos. Con eso se
    borró lo que desde el grafo no se alcanza nunca: el reinicio de escenario
    nuevo y la mención de niños (los hace el nodo router antes de clasificar),
    el cálculo de las señales (las trae siempre el router), los gates de PII,
    alcohol/alergia, evento de empresa y "mismo precio" (el router los manda a
    su nodo, que los resuelve antes de delegar) y, detrás del núcleo, el link
    roto y el tema sensible repetidos, la disponibilidad y el cambio de idioma:
    el núcleo solo declina por escalado-keyword/`wants_human` (`_setup_phase`),
    y el gate de escalado de abajo mira exactamente lo mismo.

    Los gates pre-núcleo que quedan SÍ se alcanzan desde el grafo: el nodo
    `info` delega cuando el router lo mandó allí por "mismo precio" (su
    respuesta fija se borró en ex-9b: la contesta el RAG) sin
    mirar lo que va detrás, o por una pregunta de edad que no lo era; y la
    negativa de datos ajenos de `_needs_staff_handoff` no la mira el router.

    Borrarla del todo requeriría antes migrar el grupo (B) de gates
    post-núcleo a nodos propios (5.2 paso 3, aún no hecho) — hasta entonces
    sigue siendo la fuente de verdad compartida, no un vestigio.

    Reglas de enrutado sin LLM (documentado, no cambia con el grafo):
    1. Si el usuario está en un paso de menú Y manda un número -> decision tree
    2. Si manda una keyword de menú/volver -> reset al menú principal
    3. Si manda una keyword de escalado -> escalar
    4. Si está en paso SUMMARY/ESCALATE/FREE_TEXT -> agente RAG
    5. Si manda texto libre en un paso de menú -> agente RAG

    `routing_signals`: las que calculó el nodo router del grafo
    (`detect_routing_signals`, una vez por turno); se reutilizan, sin
    recomputar la llamada LLM.
    """
    msg_lower = message.strip().lower()

    # SAFETY FIRST: broken-link complaints and sensitive topics (medical,
    # weather, complaints) must escalate BEFORE the intent detector runs.
    # Otherwise a message like "Estoy embarazada, puedo bucear?" gets hijacked
    # by the booking intent ("bucear") and routed into the cart flow instead of
    # being handed to human staff. Broken-link runs before sensitive on purpose:
    # phrases like "reserva no funciona" otherwise match the generic
    # real_time_issues rule.
    if regex_decide(routing_signals) and _detect_broken_link_complaint(message, state.history):
        return _broken_link_escalation_response(state, message)

    # Respaldo LLM del gate de LINK ROTO (Bloque 2.3): el detector por keyword
    # de arriba exige frase-de-queja + token de link (o URL en el turno previo)
    # — medido en vivo que 10 de 10 quejas realistas se escapaban ("el link no
    # me deja pagar", "me sale página en blanco", "le doy al botón y no pasa
    # nada", "the payment page crashes"). La señal `broken_link_complaint`
    # (misma llamada de routing, sin coste extra) las recupera. Se coloca justo
    # tras calcular las señales y antes del bloque sensible, manteniendo la
    # prioridad "safety first" del gate por keyword de más arriba.
    if routing_signals.get("broken_link_complaint") and _has_link_tech_context(message, state.history):
        return _broken_link_escalation_response(state, message)

    # s4-21 (5): en la apertura el idioma aun no esta fijado (ver `escalation_agent`).
    sensitive_lang = _reply_language(state, message)
    sensitive_escalation_early = (
        None if routing_signals.get("adaptive_diving_topic") or not regex_decide(routing_signals)
        else detect_sensitive_escalation(message, sensitive_lang)
    )
    if sensitive_escalation_early:
        reason, response = sensitive_escalation_early
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        logger.info(f"[SUPERVISOR] Sensitive escalation triggered (early) reason={reason}")
        return response

    if routing_signals.get("sensitive_topic"):
        found = sensitive_response_for(routing_signals["sensitive_topic"], sensitive_lang)
        if found:
            reason, response = found
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = reason
            state.pending_note = build_lead_summary(state, escalation_reason=reason)
            logger.info(f"[SUPERVISOR] Sensitive escalation triggered (LLM signal, early) reason={reason}")
            return response

    staff = _needs_staff_handoff(state, message, routing_signals)
    if staff:
        return staff

    # Booking cancellation/reschedule requests: inform the policy text from
    # the KB and let the customer choose between talking to an advisor or
    # going back to the main menu, instead of the bot deciding on its own.
    # La lista de keywords (`_detect_cancellation_request`) solo caza frases
    # casi exactas — medido en vivo (2026-07-23) que 16 de 18 frases realistas
    # de cancelación/reprogramación (indirectas, jerga, typos, ES+EN) se
    # escapaban. Respaldo LLM `booking_change_topic` en la MISMA llamada
    # `detect_routing_signals` de arriba (sin coste extra), estricto como
    # wants_human (una pregunta por la política NO lo dispara). Mismo patrón
    # que DIVE TO HEAL (v0.20.58).
    if (regex_decide(routing_signals) and _detect_cancellation_request(msg_lower)) or (
        routing_signals.get("booking_change_topic") == "cancellation"
        and not _in_active_cart_building(state)
    ):
        logger.info("[SUPERVISOR] Cancellation request detected -> policy info + escalate/home buttons")
        return _booking_change_response(state, message, "cancellation")

    if (regex_decide(routing_signals) and _detect_reschedule_request(msg_lower)) or (
        routing_signals.get("booking_change_topic") == "reschedule"
        and not _in_active_cart_building(state)
    ) or _jev_changes_date(routing_signals):
        logger.info("[SUPERVISOR] Reschedule request detected -> policy info + escalate/home buttons")
        return _booking_change_response(state, message, "reschedule")

    # Hallazgo G (batería sintética contra PRE, 2026-08-26): "ya tengo una
    # reserva hecha, quiero agregar una persona más" caía al menú genérico de
    # bienvenida, sin ningún reconocimiento — asimetría con cancelación/
    # reprogramación (arriba), que sí se reconocían. Mismo patrón exacto.
    if (regex_decide(routing_signals) and _detect_modify_booking_request(msg_lower)) or (
        routing_signals.get("booking_change_topic") == "modify_headcount"
        and not _in_active_cart_building(state)
    ):
        logger.info("[SUPERVISOR] Modify-headcount request detected -> policy info + escalate/home buttons")
        return _booking_change_response(state, message, "modify_headcount")

    # Deflexión (Bloque 2.2): petición de número/WhatsApp/correo o vía de
    # contacto directa. El bot no da un número (política); en vez de escalar o
    # dar el fallback evasivo, deflexión honesta: límite 🔒 + lo que SÍ puede +
    # redirige a la reserva. Keyword fast-path + respaldo LLM (misma llamada de
    # routing de arriba, sin coste extra), estricto. Se coloca ANTES del escalado
    # genérico para ser consistente (hoy a veces escalaba, a veces caía a RAG).
    # Auditoría 2026-08-26 (batería sintética contra PRE, Grupo 4/hallazgo B,
    # portado de pre_gadea): este bloque (y el de dominio blindado, justo
    # debajo) corren ANTES de que `maybe_handle_turn` haga su detección de
    # idioma de apertura — en el PRIMER mensaje, `state.language` sigue en
    # su valor por defecto ("es"), así que "can you give me your whatsapp
    # number" (inglés) recibía la deflexión en español. `_infer_language`
    # es una heurística barata (sin LLM) — se usa aquí solo como mejor
    # estimación local para ESTA respuesta puntual, sin tocar
    # `state.language` de forma permanente.
    if (regex_decide(routing_signals) and _asks_for_contact_number(msg_lower)) or routing_signals.get(
            "asks_for_contact_number"):
        effective_lang = state.language if state.detected_language else _infer_language(message, state.language)
        if settings.contacto_pasa_a_persona:
            # Decisión de Gadea (16-oct): el chatbot no da números; quien quiere un contacto directo pasa con un asesor.
            response = _contacto_pasa_a_persona(state, effective_lang)
            state.history.append({"role": "user", "content": message})
            state.history.append({"role": "assistant", "content": response})
            return response
        response = _contact_number_deflection(effective_lang)
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        logger.info("[SUPERVISOR] Contact-number request -> deflection (limit + redirect, no escalation)")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    # Dominio blindado (Bloque 2.4): pregunta meta sobre qué IA/modelo/bot es.
    # No se revela nada (el prompt de RAG endurecido ya lo prohíbe); se responde
    # en persona (Coral) y se reconduce al buceo, en vez del fallback evasivo.
    if pregunta_si_es_ia(msg_lower, routing_signals):
        effective_lang = state.language if state.detected_language else _infer_language(message, state.language)
        response = _ai_identity_deflection(effective_lang)
        state.step = Step.FREE_TEXT
        state.quick_replies = []
        logger.info("[SUPERVISOR] AI/model-identity meta-question -> in-persona redirect (no reveal)")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": response})
        return response

    # Age-eligibility question ("mi hijo de 9 años puede bucear?", "hay edad
    # mínima?", "una persona de 14 puede?"). Answer deterministically from the
    # single source of truth (eligibility.py) so age limitations are always
    # correct and framed positively — no hallucination, no need for RAG.
    age_answer = _maybe_answer_age_eligibility(message, state)
    if age_answer is not None:
        logger.info("[SUPERVISOR] Age-eligibility question answered deterministically")
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": age_answer})
        return age_answer

    # Adaptive diving / DIVE TO HEAL. The topic is detected per-turn by keyword,
    # but must be REMEMBERED: a follow-up like "¿cuánto cuesta?" carries no
    # disability word, so without a persisted flag it fell through to the
    # generic price handler (dumping Cartagena prices and losing the thread —
    # the reported bug). So we (1) persist the context, and (2) route price/
    # booking follow-ups within it to a coherent advisor answer (no generic
    # prices), while non-price questions still get the program's factual info.
    # + red de precisión LLM (auditoría 2026-07-23): _ADAPTIVE_DIVING_PATTERN es
    # una lista cerrada que no reconoce amputación, prótesis, párkinson, lesión
    # medular, sordomuda, "no vidente"... routing_signals ya se calculó arriba
    # (mismo turno, sin llamada extra) y trae adaptive_diving_topic cuando la
    # lista de palabras no encontró nada.
    adaptive_now = (regex_decide(routing_signals) and bool(_ADAPTIVE_DIVING_PATTERN.search(message))) or bool(
        routing_signals.get("adaptive_diving_topic"))
    if adaptive_now:
        state.adaptive_diving_context = True

    if (
        state.adaptive_diving_context
        and _PRICE_OR_BOOKING_Q.search(message)
    ):
        logger.info("[SUPERVISOR] DIVE TO HEAL price/booking -> advisor (no generic prices)")
        # Advance out of WELCOME/LANGUAGE so a following "sí" is handled by the
        # bare-affirmation-accepts-advisor branch (which gates on MAIN_MENU).
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            state.step = Step.MAIN_MENU
        answer = _adaptive_diving_advisor_answer(state.language)
        state.history.append({"role": "user", "content": message})
        state.history.append({"role": "assistant", "content": answer})
        return answer

    if state.adaptive_diving_context:
        # Hallazgo en vivo (batería de frontera contra PRE, 2026-09-01): igual
        # que arriba, este chequeo usaba `adaptive_now` (solo la señal de ESTE
        # turno) en vez del flag persistido — un seguimiento genérico dentro
        # de DIVE TO HEAL sin palabra de discapacidad en ESE mensaje concreto
        # caía al núcleo normal (menú genérico de actividades) en vez de
        # seguir dando info factual del programa adaptado.
        logger.info("[SUPERVISOR] Adaptive-diving/DIVE TO HEAL question -> RAG")
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            state.step = Step.MAIN_MENU
        state.history.append({"role": "user", "content": message})
        # rag-5: aprovecha la respuesta adelantada si el contexto es el mismo (si no, la llamada de siempre).
        from src.agents.conversational_core import rag_con_adelantado

        answer = await rag_con_adelantado(state, message, state.history)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Núcleo conversacional de slot-filling (docs/archive/conversational-refactor-plan.md).
    # Es el único camino de enrutado desde Fase 4. Corre DESPUÉS del gating de
    # seguridad de arriba (PII, sensibles, cancelación, DIVE TO HEAL, edad).
    # Devuelve None solo para las clases que deben seguir en los handlers
    # deterministas de abajo (keywords de escalado / menú / volver).
    from src.agents import conversational_core
    core_response = await conversational_core.maybe_handle_turn(
        state, message, routing_signals=routing_signals
    )
    if core_response is not None:
        # El núcleo mezcla reserva (slot-fill) e info (RAG interno); ambas mapean
        # a BOOKING en el router de Fase 1 (la frontera se separa en Fase 3.3).
        return core_response

    # Cliente acepta con un "si"/"dale"/"ok" una oferta que el propio bot hizo
    # en el turno anterior de pasarle con un asesor ("¿te paso el contacto de
    # un asesor?"). Sin esta rama, el "si" (demasiado corto para el agente
    # conversacional) caia a RAG y respondia el fallback generico — bug real
    # visto en PRE (2026-07-07). Restringido a pasos conversacionales para no
    # pisar los "si/no" de preguntas del arbol.
    if (
        state.step in (Step.MAIN_MENU, Step.FREE_TEXT)
        and _BARE_AFFIRMATION_RE.match(message.strip())
    ):
        last_bot = next(
            (h.get("content", "") for h in reversed(state.history or []) if h.get("role") == "assistant"),
            "",
        )
        if _ADVISOR_OFFER_RE.search(last_bot) and _OFFER_VERB_RE.search(last_bot):
            reason = "aceptó la oferta del bot de hablar con un asesor"
            state.step = Step.ESCALATE
            state.quick_replies = []
            state.pending_escalation_reason = reason
            state.pending_note = build_lead_summary(state, escalation_reason=reason)
            from src.flows.messages import MESSAGES
            logger.info("[SUPERVISOR] Bare affirmation accepted pending advisor offer -> escalate")
            return MESSAGES["escalate"][state.language]

    # Check for escalation keywords (+ red de precisión LLM, auditoría 2026-07-22)
    if (regex_decide(routing_signals) and _matches_escalation_keyword(msg_lower)) or routing_signals.get("wants_human"):
        state.step = Step.ESCALATE
        state.quick_replies = []
        state.pending_escalation_reason = "solicitó asesor"
        state.pending_note = build_lead_summary(state, escalation_reason="solicitó asesor")
        from src.flows.messages import MESSAGES
        logger.info("[SUPERVISOR] Escalation triggered by keyword or LLM signal")
        return MESSAGES["escalate"][state.language]

    # Núcleo = único camino (Fase 4): todo mensaje se resuelve arriba. El núcleo
    # solo declina por escalado-keyword/`wants_human` (`_setup_phase`), la misma
    # condición del gate de escalado de arriba, así que esto no se alcanza: s4-1
    # borró lo que había entre ese gate y este fallback defensivo (link roto y
    # tema sensible repetidos, disponibilidad y cambio de idioma).
    logger.warning(f"[SUPERVISOR] fallthrough inesperado step={state.step.value}")
    from src.flows.messages import MESSAGES
    return MESSAGES["main_menu"][state.language]


# s4-2 (19-oct): los detectores y las respuestas de cada ruta del grafo viven en `src/agents/rutas/<ruta>.py`
# (ver su `__init__`). Se re-exportan aquí para que la cascada (`_shared_turn_handler`), el router, los nodos, el
# núcleo (que los usa como `supervisor.<nombre>`), los scripts y los tests los sigan encontrando en este módulo. Va
# al final a propósito: esos módulos importan de aquí lo común, que tiene que estar ya definido.
from src.agents.rutas.booking import (  # noqa: E402, F401
    _ACTIVITY_TO_SERVICE_ID,
    _CLAUSE_QUESTION_RE,
    _CLOSED_DATE_RE,
    _CORRECTION_CUE_RE,
    _INFO_QUESTION_STARTER_PATTERN,
    _INFO_REQUEST_ANYWHERE_RE,
    _INTENT_TRIGGER_STEPS,
    _MAX_REMEMBERED_NOTES,
    _QUE_CONJUNCION,
    _VETO_FIELD_SPECS,
    GREETING_ONLY_KEYWORDS,
    GREETING_SMALLTALK_KEYWORDS,
    _activity_should_verify,
    _append_mixed_cart_item,
    _apply_activity_veto,
    _apply_detected_intent,
    _certification_should_verify,
    _eligible_veto_fields,
    _finalize_tree_response,
    _group_allocation_should_verify,
    _group_size_that_will_persist,
    _log_safe_message,
    _looks_like_info_question,
    _maybe_build_pending_note,
    _maybe_veto_resolved_field_via_llm,
    _maybe_veto_resolved_fields_via_llm,
    _mixed_nationality_response,
    _nationality_should_verify,
    _principal_sigue_en_el_reparto,
    _should_skip_to_certified_flow,
    _veto_would_generalize,
    _VetoSpec,
    apply_veto_disagreements,
    enforce_group_allocation_consistency,
    valid_veto_corrections,
)
from src.agents.rutas.changes import (  # noqa: E402, F401
    _AVAILABILITY_PATTERN,
    _AVAILABILITY_RE,
    CANCEL_BOOKING_PHRASES,
    MODIFY_BOOKING_PHRASES,
    RESCHEDULE_BOOKING_PHRASES,
    _asks_about_availability,
    _booking_change_response,
    _detect_cancellation_request,
    _detect_modify_booking_request,
    _detect_reschedule_request,
    _in_active_cart_building,
    _jev_changes_date,
)
from src.agents.rutas.contexto_rag import (  # noqa: E402, F401
    _CERTIFIED_MENTION_RE,
    _DIVE_TO_HEAL_OVERRIDE_RE,
    _INACTIVE_MENTION_RE,
    _UNCERTIFIED_COMPANION_NOTE_RE,
    _build_extra_context,
    _mentions_inactive_but_certified_companion,
)
from src.agents.rutas.deflection import (  # noqa: E402, F401
    _AI_IDENTITY_RE,
    CONTACT_NUMBER_REQUEST_PHRASES,
    _ai_identity_deflection,
    _asks_about_ai_identity,
    _asks_for_contact_number,
    _contact_number_deflection,
    _contacto_pasa_a_persona,
    _official_whatsapp,
    pregunta_si_es_ia,
)
from src.agents.rutas.info import (  # noqa: E402, F401
    _AGE_ELIGIBILITY_CUE,
    _AGE_NUMBER_HINT,
    _AGE_PERSON_REF,
    _ALCOHOL_BEFORE_DIVING_RE,
    _ALLERGY_WORD_RE,
    _FOOD_ALLERGEN_RE,
    _PRIVATE_GROUP_EVENT_RE,
    _SAME_PRICE_DIFFERENT_NATIONALITY_RE,
    _alcohol_and_food_policy_answer,
    _looks_like_age_eligibility_question,
    _maybe_answer_age_eligibility,
    _private_group_event_answer,
    intent_detector,
    private_group_event_reply,
)
from src.agents.rutas.router import (  # noqa: E402, F401
    _GREETING_START_RE,
    _INTRO_PHRASE_RE,
    _NAME_INTRO_RE,
    _detect_kids_mention,
    _has_accumulated_memory,
    _is_new_scenario_restart,
    _normalize_for_menu_match,
    _reset_to_fresh_scenario,
)
from src.agents.rutas.safety import (  # noqa: E402, F401
    _PRICE_OR_BOOKING_Q,
    BROKEN_LINK_COMPLAINT_PHRASES,
    BROKEN_LINK_TARGET_TOKENS,
    _adaptive_diving_advisor_answer,
    _broken_link_escalation_response,
    _detect_broken_link_complaint,
    _has_link_tech_context,
    _needs_staff_handoff,
    _reply_language,
)
