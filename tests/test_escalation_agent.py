"""Fase 2.2 — nodo-agente `escalation` real + equivalencia con la cascada.

Cubre: (a) el nodo en aislamiento por gate (PII, link roto, sensible, DIVE TO
HEAL precio, delegación post-núcleo), (b) equivalencia flag on (grafo con el
nodo real) == flag off (cascada) para mensajes de cada gate SAFETY — el corte
strangler no cambia la respuesta.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.escalation_agent import escalation_node
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="escalation-test")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


# ── nodo en aislamiento (State in → update out) ──

@pytest.mark.asyncio
async def test_node_pii_blocks_and_escalates():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "mi correo es juan.perez@gmail.com", "signals": {}}
    )
    assert result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason == "datos sensibles detectados"


@pytest.mark.asyncio
async def test_node_broken_link_keyword():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "el link de pago no me funciona", "signals": {}}
    )
    assert "asesor" in result["reply"].lower()
    assert conv.step == Step.ESCALATE
    assert "LINK ROTO" in conv.pending_escalation_reason


@pytest.mark.asyncio
async def test_node_broken_link_via_signal():
    """La señal LLM `broken_link_complaint` + contexto técnico también escala,
    aunque la keyword del fast-path no matchee."""
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "le doy al boton de pagar y no pasa nada",
         "signals": {"broken_link_complaint": True}}
    )
    assert conv.step == Step.ESCALATE
    assert "LINK ROTO" in conv.pending_escalation_reason
    assert result["reply"]


@pytest.mark.asyncio
async def test_node_sensitive_keyword():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "estoy embarazada, puedo bucear?", "signals": {}}
    )
    assert result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason
    assert conv.pending_note  # lead summary construido


@pytest.mark.asyncio
async def test_node_dive_to_heal_price_to_advisor():
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "voy en silla de ruedas, cuanto cuesta bucear?", "signals": {}}
    )
    assert result["reply"]
    assert conv.adaptive_diving_context is True  # el contexto persiste
    # No vuelca precios genéricos de Cartagena — es una respuesta de asesor.
    assert "$" not in result["reply"]
    assert conv.history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_node_wants_human_delegates_to_cascade(monkeypatch):
    """Gate SAFETY post-núcleo (wants_human/keyword): el nodo NO lo reproduce
    (cambiaría el orden respecto al núcleo) → delega en la cascada."""
    monkeypatch.setattr(
        "src.agents.supervisor._shared_turn_handler",
        AsyncMock(return_value="respuesta de la cascada"),
    )
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "quiero hablar con una persona", "signals": {}}
    )
    assert result["reply"] == "respuesta de la cascada"


# ── grupo B (post-núcleo): comportamiento final directo, SIN mockear
# `_shared_turn_handler` (Fase 5.2, prep del corte — ver docs/multi-agent-
# refactor-plan.md §5). A diferencia del test de arriba (que solo verifica que
# el nodo DELEGA), estos verifican que la delegación produce el resultado
# correcto por sí sola — cobertura que hoy solo existe indirectamente vía los
# tests de `_shared_turn_handler` en test_routing_signals_integration.py y los
# `*_equivalent_graph_vs_cascade` (que dejarán de existir cuando se quite el
# flag `agent_arch`).

@pytest.mark.asyncio
async def test_node_wants_human_signal_escalates_directly():
    """wants_human/keyword de escalado: el nodo delega en `_shared_turn_handler`
    (gate post-núcleo, corre el núcleo primero) y el resultado final debe
    escalar, sin necesidad de mockear la delegación."""
    conv = make_state()
    result = await escalation_node(
        {"conv_state": conv, "message": "quiero hablar con una persona", "signals": {"wants_human": True}}
    )
    assert result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason == "solicitó asesor"


@pytest.mark.asyncio
async def test_node_bare_affirmation_accepts_pending_advisor_offer():
    """"sí" tras una oferta del propio bot de pasar con un asesor debe escalar
    con el motivo específico "aceptó la oferta..." (bug real visto en PRE
    2026-07-07: un "sí" demasiado corto para el agente conversacional caía a
    RAG y daba el fallback genérico). Gate post-núcleo, sin cobertura a nivel
    de nodo hasta ahora.

    Solo alcanzable cuando `maybe_handle_turn` declina (`_setup_phase`
    devuelve `None`) — y la ÚNICA condición para eso es escalado-keyword/
    `wants_human` (confirmado leyendo `_setup_phase`, idéntico en pre_gadea).
    En producción esto se cumple porque la señal LLM `wants_human` ve el
    historial completo: un "sí" justo después de que el bot ofreciera un
    asesor se clasifica en contexto como aceptación, no un "sí" aislado sin
    esa oferta previa (el propio regex `_ADVISOR_OFFER_RE`/`_OFFER_VERB_RE`
    exige la oferta en el turno anterior, así que el escalado sigue siendo
    específico a este caso, no cualquier "sí" con wants_human)."""
    conv = make_state()
    conv.step = Step.FREE_TEXT
    conv.history = [
        {"role": "user", "content": "tengo una duda sobre el pago"},
        {"role": "assistant", "content": "¿quieres que te pase con un asesor para resolver eso?"},
    ]
    result = await escalation_node(
        {"conv_state": conv, "message": "sí", "signals": {"wants_human": True}}
    )
    assert result["reply"]
    assert conv.step == Step.ESCALATE
    assert conv.pending_escalation_reason == "aceptó la oferta del bot de hablar con un asesor"


# ── equivalencia flag on/off (el corte strangler no cambia la respuesta) ──

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "mi correo es juan.perez@gmail.com",           # PII (pre-núcleo)
    "el link de pago no me funciona",              # link roto keyword (pre-núcleo)
    "estoy embarazada, puedo bucear?",             # sensible keyword (pre-núcleo)
    "voy en silla de ruedas, cuanto cuesta bucear?",  # DIVE TO HEAL precio (pre-núcleo)
    "quiero hablar con una persona",               # wants_human (post-núcleo → delega)
])
async def test_escalation_equivalent_graph_vs_cascade(monkeypatch, message):
    # Routing LLM offline → determinista (los detectores regex manejan cada gate);
    # la ruta SAFETY no toca el núcleo salvo en el caso wants_human (que delega).
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))

    monkeypatch.setattr(settings, "agent_arch", False)
    reply_cascade = await route_message(make_state(), message)

    monkeypatch.setattr(settings, "agent_arch", True)
    reply_graph = await route_message(make_state(), message)

    assert reply_graph == reply_cascade
    assert reply_graph  # no se dropea el turno
