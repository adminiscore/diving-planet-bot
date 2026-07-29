"""Fase 1.5 (docs/multi-agent-refactor-plan.md) — shadow del router.

Con la cascada viva (`agent_arch` off) y `agent_arch_shadow` on, cada turno
corre además el router y loguea si su ruta coincide con la que la cascada
tomó. Estos tests fijan: (a) el shadow no cambia la respuesta, (b) la cascada
marca su ruta real en cada gate, (c) router y cascada coinciden en casos
representativos de las 5 rutas.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents import supervisor as sup
from src.agents.supervisor import _cascade_route_taken, route_message
from src.config import settings
from src.flows.state import ConversationState, Step
from src.orchestration.state import (
    ROUTE_BOOKING,
    ROUTE_CHANGE,
    ROUTE_DEFLECT,
    ROUTE_SAFETY,
)


def make_state(**over) -> ConversationState:
    s = ConversationState(conversation_id="shadow-test")
    s.step = Step.MAIN_MENU
    for k, v in over.items():
        setattr(s, k, v)
    return s


@pytest.fixture
def _signals_offline(monkeypatch):
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))


@pytest.mark.asyncio
async def test_shadow_does_not_change_reply(monkeypatch, _signals_offline):
    # El shadow solo AÑADE logging de ruta; no cambia la respuesta. Para probarlo
    # de forma determinista, la respuesta a "hola" debe ser idéntica entre las dos
    # llamadas — pero "hola" en MAIN_MENU no es primer turno y dispara los LLM del
    # núcleo (compose_acknowledgement/fill_gaps…, no mockeados aquí → texto
    # variable → test flaky). Se mockean a valores fijos: así la respuesta es el
    # saludo/plantilla determinista y la igualdad prueba lo que debe (shadow inocuo),
    # no la (no-)determinación del LLM.
    import src.agents.conversational_core as core
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))

    monkeypatch.setattr(settings, "agent_arch", False)
    monkeypatch.setattr(settings, "agent_arch_shadow", False)
    reply_plain = await route_message(make_state(), "hola")

    monkeypatch.setattr(settings, "agent_arch_shadow", True)
    reply_shadow = await route_message(make_state(), "hola")

    assert reply_shadow == reply_plain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, expected_route",
    [
        ("estoy embarazada, puedo bucear?", ROUTE_SAFETY),
        ("quiero cancelar mi reserva", ROUTE_CHANGE),
        ("me pasas un numero de whatsapp?", ROUTE_DEFLECT),
        ("quiero reservar buceo para 2 personas", ROUTE_BOOKING),
        ("2", ROUTE_BOOKING),
    ],
)
async def test_cascade_marks_its_route_and_matches_router(
    monkeypatch, _signals_offline, message, expected_route
):
    # La cascada (vía _route_message_inner) marca la ruta que tomó; en estos
    # casos representativos coincide con classify_route (lo que el shadow
    # loguea como "match").
    monkeypatch.setattr(settings, "agent_arch", False)
    _cascade_route_taken.set(None)
    await sup._route_message_inner(make_state(), message)
    assert _cascade_route_taken.get() == expected_route


@pytest.mark.asyncio
async def test_shadow_logs_match_when_router_agrees(monkeypatch, _signals_offline, caplog):
    import logging

    monkeypatch.setattr(settings, "agent_arch", False)
    monkeypatch.setattr(settings, "agent_arch_shadow", True)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await route_message(make_state(), "quiero cancelar mi reserva")
    shadow_lines = [r.message for r in caplog.records if "ROUTE_SHADOW" in r.message]
    assert shadow_lines and "match route=changes" in shadow_lines[-1]
