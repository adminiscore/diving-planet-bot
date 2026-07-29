"""Router del grafo (Fase 1.2) — clasifica cada mensaje en una de las 5 rutas.

Ver `docs/agent-arch-design.md` §2 y `docs/multi-agent-refactor-plan.md` §1.2
+ §4.bis (taxonomía).

## Qué hace y qué NO hace

`classify_route(conv_state, message, signals) -> ROUTE_*` decide **a qué nodo**
iría el mensaje, SIN ejecutar ningún handler ni mutar estado (salvo lo mínimo
inevitable, ver abajo). Reúsa los detectores reales del supervisor
(determinista-primero) + las señales LLM ya calculadas (`detect_routing_
signals`, pasadas como `signals` para no recomputar) + los backstops medidos
en vivo (`_in_active_cart_building`, `_has_link_tech_context`).

## Filosofía: enrutado *intencional*, no réplica exacta de la cascada

La cascada actual (`supervisor._route_message_inner`) **decide-haciendo**:
mezcla la decisión de ruta con la acción, y algunos gates (disponibilidad,
keyword de escalado) se comprueban DESPUÉS del núcleo — que es una caja negra
que "devuelve None para caer al siguiente gate". Eso hace **imposible**
predecir la ruta exacta de la cascada sin ejecutar el núcleo.

Así que este router encode el enrutado **que la taxonomía §4.bis quiere**
(el diseño limpio), no una réplica de la cascada. Es lo que pide el plan: el
shadow (Fase 1.5) compara este router contra lo que la cascada realmente hace
y **las discrepancias son la señal útil** ("≥99% coincidencia; las
discrepancias reales = bugs de la cascada a documentar"). No son fallos del
router.

## La frontera BOOKING/INFO

La cascada mete la reserva (slot-fill) Y las preguntas de info (RAG) dentro
del mismo núcleo (`conversational_core.maybe_handle_turn`), que decide
pregunta-vs-reserva internamente. Por eso el router de Fase 1 **no separa**
BOOKING de INFO en el caso general: todo lo que "cae al núcleo" se clasifica
como BOOKING (su casa). Las únicas INFO que el router sí aísla son las que la
propia cascada resuelve ANTES del núcleo (DIVE TO HEAL no-precio → RAG). La
separación BOOKING↔INFO se vuelve una decisión real del router cuando el
subgrafo del núcleo se parte (Fase 3.3).

## Dependencia perezosa de `supervisor`

Los detectores viven hoy en `supervisor.py`, que (Fase 1.4) importará el grafo
→ importaría este router → ciclo. Se rompe con un import perezoso de
`supervisor` dentro de la función (patrón ya usado en todo el repo). Los
detectores migrarán a un módulo propio del router en Fase 3.
"""

from __future__ import annotations

from src.flows.state import ConversationState, Step
from src.orchestration.state import (
    ROUTE_BOOKING,
    ROUTE_CHANGE,
    ROUTE_DEFLECT,
    ROUTE_INFO,
    ROUTE_SAFETY,
)


def classify_route(conv_state: ConversationState, message: str, signals: dict) -> str:
    """Decide la ruta (una de ROUTE_*) para este mensaje. Read-only sobre
    `conv_state` (no muta estado). `signals` = resultado de
    `detect_routing_signals` de este turno (dict vacío para clics de botón
    numéricos, igual que en la cascada)."""
    from src.agents import supervisor as sup

    msg_lower = message.strip().lower()
    history = conv_state.history
    lang = conv_state.language

    # ── SAFETY (safety-first, como la cascada) ──
    if sup.detect_pii(message):
        return ROUTE_SAFETY
    if sup._detect_broken_link_complaint(message, history):
        return ROUTE_SAFETY
    if signals.get("broken_link_complaint") and sup._has_link_tech_context(message, history):
        return ROUTE_SAFETY
    # El tema sensible se suprime si el turno es DIVE TO HEAL (mismo criterio que
    # la cascada: sensitive_escalation_early es None si adaptive_diving_topic).
    adaptive_signal = bool(signals.get("adaptive_diving_topic"))
    if not adaptive_signal and sup.detect_sensitive_escalation(message, lang):
        return ROUTE_SAFETY
    if signals.get("sensitive_topic") and sup.sensitive_response_for(signals["sensitive_topic"], lang):
        return ROUTE_SAFETY

    # ── CHANGE (cancelar / reprogramar) ──
    if sup._detect_cancellation_request(msg_lower) or (
        signals.get("booking_change_topic") == "cancellation"
        and not sup._in_active_cart_building(conv_state)
    ):
        return ROUTE_CHANGE
    if sup._detect_reschedule_request(msg_lower) or (
        signals.get("booking_change_topic") == "reschedule"
        and not sup._in_active_cart_building(conv_state)
    ):
        return ROUTE_CHANGE

    # ── DEFLECT (contacto / identidad IA) ──
    if sup._asks_for_contact_number(msg_lower) or signals.get("asks_for_contact_number"):
        return ROUTE_DEFLECT
    if sup._asks_about_ai_identity(msg_lower):
        return ROUTE_DEFLECT

    # ── BOOKING (sub-caso: nacionalidad mixta) ──
    # La taxonomía §4.bis lo clasifica como reserva; la cascada lo responde con
    # una explicación + botones de asesor. Candidato claro a discrepancia de
    # shadow (comportamiento advisor vs. ruta booking) — a documentar en 1.5.
    if sup._detect_mixed_nationality_request(msg_lower):
        return ROUTE_BOOKING

    # ── SAFETY / INFO (DIVE TO HEAL) ──
    adaptive_now = bool(sup._ADAPTIVE_DIVING_PATTERN.search(message)) or adaptive_signal
    # El contexto adaptativo persiste entre turnos: un "¿cuánto cuesta?" sin
    # palabra de discapacidad, tras haber entrado en DIVE TO HEAL, sigue yendo
    # a asesor. Read-only: leemos el flag persistido O el de este turno (la
    # cascada lo SETea; el router solo lo lee).
    adaptive_context = conv_state.adaptive_diving_context or adaptive_now
    if adaptive_context and sup._PRICE_OR_BOOKING_Q.search(message):
        return ROUTE_SAFETY  # precio/reserva dentro de DIVE TO HEAL → asesor
    if adaptive_now:
        return ROUTE_INFO    # resto de DIVE TO HEAL → RAG (info factual del programa)

    # ── CHANGE (disponibilidad) ──
    if (
        sup._AVAILABILITY_PATTERN.search(msg_lower)
        or (
            (sup._asks_about_availability(msg_lower) or signals.get("availability_question"))
            and not sup._in_active_cart_building(conv_state)
        )
    ) and conv_state.step not in (Step.WELCOME, Step.LANGUAGE):
        return ROUTE_CHANGE

    # ── SAFETY (quiere humano / keyword de escalado) ──
    if sup._matches_escalation_keyword(msg_lower) or signals.get("wants_human"):
        return ROUTE_SAFETY

    # ── Default: el núcleo (reserva slot-fill + info vía RAG interno) ──
    # La frontera BOOKING/INFO vive dentro del núcleo hoy (ver docstring);
    # todo lo no-capturado arriba es su tráfico. Casa = BOOKING.
    return ROUTE_BOOKING
