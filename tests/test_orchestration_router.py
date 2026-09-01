"""Fase 1.2 (docs/multi-agent-refactor-plan.md) — router del grafo.

classify_route es determinista y offline (las señales LLM se pasan como dict,
no se llama a la red), así que se testea con frases reales que casan los
detectores del supervisor + dicts de señales fabricados. Fija que cada rama de
la taxonomía §4.bis enruta a donde debe.
"""

import pytest

from src.flows.state import ConversationState, Step
from src.orchestration.router import classify_route
from src.orchestration.state import (
    ROUTE_BOOKING,
    ROUTE_CHANGE,
    ROUTE_DEFLECT,
    ROUTE_INFO,
    ROUTE_SAFETY,
)


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="router-test")
    s.step = Step.MAIN_MENU  # fuera de WELCOME/LANGUAGE (donde availability se ignora)
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── SAFETY ──

def test_pii_routes_to_safety():
    assert classify_route(make_state(), "mi correo es juan@example.com", {}) == ROUTE_SAFETY


def test_broken_link_keyword_routes_to_safety():
    assert classify_route(make_state(), "el link de pago no funciona", {}) == ROUTE_SAFETY


def test_sensitive_medical_routes_to_safety():
    assert classify_route(make_state(), "estoy embarazada, puedo bucear?", {}) == ROUTE_SAFETY


def test_sensitive_topic_signal_routes_to_safety():
    # Sin keyword pero con señal LLM de tema sensible.
    st = classify_route(make_state(), "cuentame algo", {"sensitive_topic": "medical_questions"})
    assert st == ROUTE_SAFETY


def test_wants_human_signal_routes_to_safety():
    assert classify_route(make_state(), "necesito ayuda con esto", {"wants_human": True}) == ROUTE_SAFETY


def test_escalation_keyword_routes_to_safety():
    assert classify_route(make_state(), "quiero hablar con un asesor", {}) == ROUTE_SAFETY


# ── CHANGE ──

def test_cancellation_routes_to_change():
    assert classify_route(make_state(), "quiero cancelar mi reserva", {}) == ROUTE_CHANGE


def test_reschedule_routes_to_change():
    assert classify_route(make_state(), "puedo cambiar la fecha de mi reserva", {}) == ROUTE_CHANGE


def test_availability_routes_to_change():
    assert classify_route(make_state(), "que dias hay disponibles?", {}) == ROUTE_CHANGE


def test_availability_ignored_at_welcome_step_falls_to_booking():
    # En WELCOME/LANGUAGE la cascada no dispara el handler de disponibilidad.
    st = make_state(step=Step.WELCOME)
    assert classify_route(st, "que dias hay disponibles?", {}) == ROUTE_BOOKING


# ── DEFLECT ──

def test_contact_number_routes_to_deflection():
    assert classify_route(make_state(), "me pasas un numero de whatsapp?", {}) == ROUTE_DEFLECT


def test_ai_identity_routes_to_deflection():
    assert classify_route(make_state(), "eres un bot o una persona?", {}) == ROUTE_DEFLECT


# ── INFO / SAFETY (DIVE TO HEAL) ──

def test_adaptive_diving_non_price_routes_to_info():
    assert classify_route(make_state(), "tengo una discapacidad, puedo bucear?", {}) == ROUTE_INFO


def test_adaptive_diving_price_routes_to_safety_advisor():
    # Precio dentro de contexto DIVE TO HEAL persistido → asesor (SAFETY).
    st = make_state(adaptive_diving_context=True)
    assert classify_route(st, "cuanto cuesta?", {}) == ROUTE_SAFETY


def test_adaptive_diving_generic_followup_persists_to_info():
    """Hallazgo en vivo (batería de frontera contra PRE, 2026-09-01): un
    seguimiento genérico SIN palabra de discapacidad ("¿qué incluye el
    programa?") dentro de contexto DIVE TO HEAL persistido debe seguir yendo
    a INFO (info factual del programa), no al default BOOKING — el chequeo
    usaba `adaptive_now` (solo la señal de este turno) en vez del contexto
    persistido."""
    st = make_state(adaptive_diving_context=True)
    assert classify_route(st, "que incluye el programa", {}) == ROUTE_INFO


# ── BOOKING (default + sub-casos) ──

def test_plain_booking_routes_to_booking():
    assert classify_route(make_state(), "quiero reservar buceo para 2 personas", {}) == ROUTE_BOOKING


def test_mixed_nationality_routes_to_booking():
    assert classify_route(make_state(), "somos de nacionalidad mixta", {}) == ROUTE_BOOKING


def test_digit_button_click_routes_to_booking():
    # Clic de botón: signals={} (la cascada salta detect_routing_signals).
    assert classify_route(make_state(), "2", {}) == ROUTE_BOOKING


def test_generic_info_question_defaults_to_booking_core():
    # La frontera BOOKING/INFO vive dentro del núcleo (Fase 3.3); una pregunta
    # de info genérica cae al núcleo = BOOKING por ahora.
    assert classify_route(make_state(), "que incluye el tour?", {}) == ROUTE_BOOKING


# ── Prioridad: SAFETY gana sobre BOOKING cuando ambos aplican ──

def test_safety_takes_priority_over_booking_intent():
    # "bucear" es intención de reserva, pero el tema médico manda (safety-first).
    st = classify_route(make_state(), "estoy embarazada y quiero bucear", {})
    assert st == ROUTE_SAFETY


@pytest.mark.parametrize("msg", ["", "   ", "3"])
def test_trivial_messages_do_not_crash(msg):
    # Robustez: mensajes vacíos/numéricos no rompen la clasificación.
    assert classify_route(make_state(), msg, {}) in {
        ROUTE_SAFETY, ROUTE_BOOKING, ROUTE_INFO, ROUTE_CHANGE, ROUTE_DEFLECT
    }
