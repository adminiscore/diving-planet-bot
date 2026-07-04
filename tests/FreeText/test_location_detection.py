"""
Test de detección de ubicación con texto libre.
"""

import asyncio
import pytest
from src.agents import orchestrator
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState


def _route(message):
    """Deterministic stand-in for the agent's LLM decision: booking request ->
    start_booking; a location statement -> set_location."""
    m = message.lower()
    if "cartagena" in m:
        return orchestrator.TOOL_SET_LOCATION, {"origin": "cartagena"}
    if "isla" in m:
        return orchestrator.TOOL_SET_LOCATION, {"origin": "island"}
    return orchestrator.TOOL_START_BOOKING, {"activity": "certified"}


@pytest.fixture(autouse=True)
def _agent(_agent_answers_by_default, agent_decides):
    agent_decides(_route)


async def test_location_free_text():
    """
    Prueba que el bot detecte "Cartagena" o "Islas del Rosario" en texto libre.
    """
    print("="*80)
    print("TEST: Detección de ubicación con texto libre")
    print("="*80)
    
    # Test 1: Cartagena
    print("\n--- Test 1: Texto libre 'Cartagena' ---")
    state1 = ConversationState(conversation_id="test-location-1")
    state1.language = "es"
    
    msg1 = "Hola somos dos personas que queremos hacer buceo y estamos certificados"
    print(f"\nUsuario: {msg1}")
    resp1 = await route_message(state1, msg1)
    print(f"\nBot:\n{resp1}")
    print(f"Estado despues msg1: step={state1.step.value}, quick_replies={len(state1.quick_replies) if state1.quick_replies else 0}")
    
    msg2 = "Cartagena"
    print(f"\nUsuario: {msg2}")
    print(f"Estado antes msg2: step={state1.step.value}, quick_replies={len(state1.quick_replies) if state1.quick_replies else 0}")
    resp2 = await route_message(state1, msg2)
    print(f"\nBot:\n{resp2}")
    print(f"\nEstado despues msg2: location={state1.location}, step={state1.step.value}")
    
    assert state1.location == "cartagena", f"Expected location='cartagena', got '{state1.location}'"
    print("✅ Cartagena detectado correctamente")
    
    # Test 2: Islas del Rosario
    print("\n--- Test 2: Texto libre 'Islas del Rosario' ---")
    state2 = ConversationState(conversation_id="test-location-2")
    state2.language = "es"
    
    msg1 = "Hola somos dos personas que queremos hacer buceo y estamos certificados"
    print(f"\nUsuario: {msg1}")
    resp1 = await route_message(state2, msg1)
    print(f"\nBot:\n{resp1}")
    
    msg2 = "Ya estoy en las islas del rosario"
    print(f"\nUsuario: {msg2}")
    resp2 = await route_message(state2, msg2)
    print(f"\nBot:\n{resp2}")
    print(f"\nEstado: location={state2.location}")
    
    assert state2.location == "island", f"Expected location='island', got '{state2.location}'"
    print("✅ Islas del Rosario detectado correctamente")
    
    # Test 3: Variante "en las islas"
    print("\n--- Test 3: Texto libre 'en las islas' ---")
    state3 = ConversationState(conversation_id="test-location-3")
    state3.language = "es"
    
    msg1 = "Hola somos dos personas que queremos hacer buceo y estamos certificados"
    print(f"\nUsuario: {msg1}")
    resp1 = await route_message(state3, msg1)
    
    msg2 = "Estoy en las islas"
    print(f"\nUsuario: {msg2}")
    resp2 = await route_message(state3, msg2)
    print(f"\nBot:\n{resp2}")
    print(f"\nEstado: location={state3.location}")
    
    assert state3.location == "island", f"Expected location='island', got '{state3.location}'"
    print("✅ 'en las islas' detectado correctamente")
    
    print("\n" + "="*80)
    print("✅ Todos los tests de detección de ubicación pasaron!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_location_free_text())
