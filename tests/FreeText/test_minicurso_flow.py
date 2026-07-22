"""
Test del flujo de minicurso con detección de intención.
"""

import asyncio
import pytest
from src.agents import orchestrator
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState


@pytest.fixture(autouse=True)
def _agent_books(_agent_answers_by_default, agent_decides):
    agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "beginner"})


async def test_minicurso_flow():
    """
    Prueba que cuando el usuario dice "quiero hacer el minicurso",
    el bot detecte la actividad y salte directo a cantidad después de ubicación.
    """
    print("="*80)
    print("TEST: Flujo de minicurso con detección de intención")
    print("="*80)
    
    state = ConversationState(conversation_id="test-minicurso")
    state.language = "es"
    
    # Mensaje 1: Usuario menciona minicurso
    msg1 = "Hola quiero hacer el minicurso de buceo, es mi primera vez"
    print(f"\nUsuario: {msg1}")
    resp1 = await route_message(state, msg1)
    print(f"\nBot:\n{resp1}")
    print(f"\nEstado: step={state.step.value}, mixed_pending_qty_type={state.mixed_pending_qty_type}")
    
    # Verificar que detectó la actividad
    assert state.detected_activity == "minicourse", f"Expected activity='minicourse', got '{state.detected_activity}'"
    assert state.mixed_pending_qty_type == "beginner", f"Expected type='beginner', got '{state.mixed_pending_qty_type}'"
    assert state.step.value == "mixed_location", f"Expected step='mixed_location', got '{state.step.value}'"
    print("OK: Detectó minicurso y pregunta ubicación")
    
    # Mensaje 2: Usuario responde ubicación
    msg2 = "Cartagena"
    print(f"\nUsuario: {msg2}")
    resp2 = await route_message(state, msg2)
    print(f"\nBot:\n{resp2}")
    print(f"\nEstado: step={state.step.value}, location={state.location}")
    
    # Verificar que saltó directo a cantidad (NO preguntó actividad)
    assert state.location == "cartagena", f"Expected location='cartagena', got '{state.location}'"
    assert state.step.value == "mixed_add_qty", f"Expected step='mixed_add_qty', got '{state.step.value}'"
    assert "cuántas personas" in resp2.lower() or "how many" in resp2.lower(), "Debería preguntar cantidad"
    assert "actividad" not in resp2.lower() and "activity" not in resp2.lower(), "NO debería preguntar actividad"
    print("OK: Saltó directo a preguntar cantidad (sin preguntar actividad)")
    
    # Mensaje 3: Usuario responde cantidad
    msg3 = "2"
    print(f"\nUsuario: {msg3}")
    resp3 = await route_message(state, msg3)
    print(f"\nBot:\n{resp3}")
    print(f"\nEstado: step={state.step.value}")
    
    print("\n" + "="*80)
    print("EXITO: El flujo de minicurso funciona correctamente!")
    print("="*80)
    print("\nResumen del flujo:")
    print("1. Usuario: 'Hola quiero hacer el minicurso de buceo, es mi primera vez'")
    print("2. Bot: Detecta minicurso → Pregunta ubicación")
    print("3. Usuario: 'Cartagena'")
    print("4. Bot: Guarda ubicación → Pregunta cantidad (SALTA pregunta de actividad)")
    print("5. Usuario: '2'")
    print("6. Bot: Continúa con el flujo de reserva")


if __name__ == "__main__":
    asyncio.run(test_minicurso_flow())
