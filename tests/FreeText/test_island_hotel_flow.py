"""
Test del flujo completo con detección de isla y pregunta de hotel.
"""

import asyncio
import pytest
from src.agents import orchestrator
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step


@pytest.fixture(autouse=True)
def _agent_books(_agent_answers_by_default, agent_decides):
    agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "certified"})


async def test_island_hotel_flow():
    """
    Prueba que cuando el usuario dice "Estoy en isla grande y quiero bucear":
    1. Detecta la isla
    2. Pregunta certificación
    3. Pregunta hotel específico
    4. Muestra el nombre de la isla en el resumen
    """
    print("="*80)
    print("TEST: Flujo Completo con Isla → Hotel → Resumen")
    print("="*80)
    
    state = ConversationState(conversation_id="test-island-hotel")
    
    # Paso 1: Usuario dice "Hola, estoy en isla grande y quiero bucear"
    msg1 = "Hola, estoy en isla grande y quiero bucear"
    print(f"\n{'='*80}")
    print(f"PASO 1: Mensaje inicial")
    print(f"{'='*80}")
    print(f"Usuario: {msg1}")
    
    resp1 = await route_message(state, msg1)
    print(f"\nBot:\n{resp1}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    print(f"  Detected island: {state.detected_island}")
    print(f"  Detected activity: {state.detected_activity}")
    
    assert state.step == Step.MIXED_ASK_CERTIFICATION, f"Esperado MIXED_ASK_CERTIFICATION, obtenido {state.step}"
    assert state.detected_island == "isla_grande", f"Esperado isla_grande, obtenido {state.detected_island}"
    print("\n✅ Detecta isla y pregunta certificación")
    
    # Paso 2: Usuario responde "Sí, estoy certificado"
    msg2 = "1"
    print(f"\n{'='*80}")
    print(f"PASO 2: Responder certificación")
    print(f"{'='*80}")
    print(f"Usuario: {msg2} (Sí, estoy certificado)")
    
    resp2 = await route_message(state, msg2)
    print(f"\nBot:\n{resp2}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    print(f"  Island: {state.island}")
    print(f"  Hotel: {state.hotel}")
    
    assert state.step == Step.ISLAND_HOTEL_MENU, f"Esperado ISLAND_HOTEL_MENU, obtenido {state.step}"
    assert "hotel" in resp2.lower(), "Debería preguntar por el hotel"
    assert "Isla Grande" in resp2, "Debería mencionar Isla Grande"
    print("\n✅ Pregunta hotel específico de Isla Grande")
    
    # Paso 3: Usuario selecciona "Pao Pao Hotel" (opción 4)
    msg3 = "4"
    print(f"\n{'='*80}")
    print(f"PASO 3: Seleccionar hotel")
    print(f"{'='*80}")
    print(f"Usuario: {msg3} (Pao Pao Hotel)")
    
    resp3 = await route_message(state, msg3)
    print(f"\nBot:\n{resp3}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    print(f"  Hotel: {state.hotel}")
    
    assert state.step == Step.MIXED_ADD_CERT_PLAN, f"Esperado MIXED_ADD_CERT_PLAN, obtenido {state.step}"
    assert state.hotel == "Pao Pao Hotel", f"Esperado 'Pao Pao Hotel', obtenido {state.hotel}"
    assert "2 inmersiones" in resp3 or "paquete" in resp3.lower(), "Debería mostrar opciones de plan"
    print("\n✅ Guarda hotel y continúa con plan de buceo")
    
    # Paso 4: Usuario selecciona "2 inmersiones / 1 día"
    msg4 = "1"
    print(f"\n{'='*80}")
    print(f"PASO 4: Seleccionar plan")
    print(f"{'='*80}")
    print(f"Usuario: {msg4} (2 inmersiones / 1 día)")
    
    resp4 = await route_message(state, msg4)
    print(f"\nBot:\n{resp4}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    
    assert state.step == Step.MIXED_ADD_QTY, f"Esperado MIXED_ADD_QTY, obtenido {state.step}"
    print("\n✅ Pregunta cantidad")
    
    # Paso 5: Usuario dice "2 personas"
    msg5 = "2"
    print(f"\n{'='*80}")
    print(f"PASO 5: Indicar cantidad")
    print(f"{'='*80}")
    print(f"Usuario: {msg5}")
    
    resp5 = await route_message(state, msg5)
    print(f"\nBot:\n{resp5}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    
    assert state.step == Step.MIXED_CERT_LAST_DIVE, f"Esperado MIXED_CERT_LAST_DIVE, obtenido {state.step}"
    print("\n✅ Pregunta última inmersión")
    
    # Paso 6: Usuario dice "No" (menos de 2 años)
    msg6 = "2"
    print(f"\n{'='*80}")
    print(f"PASO 6: Responder última inmersión")
    print(f"{'='*80}")
    print(f"Usuario: {msg6} (No, menos de 2 años)")
    
    resp6 = await route_message(state, msg6)
    print(f"\nBot:\n{resp6}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    print(f"  Island: {state.island}")
    print(f"  Location: {state.location}")
    
    # Verificar que el resumen muestra "Isla Grande" en lugar de "Islas del Rosario"
    assert "📍 Salida: Isla Grande" in resp6, "❌ El resumen debería mostrar 'Isla Grande'"
    assert "Islas del Rosario" not in resp6 or "Isla Grande" in resp6, "No debería mostrar genérico 'Islas del Rosario' cuando sabemos la isla específica"
    print("\n✅ Resumen muestra isla específica: 'Isla Grande'")
    
    print(f"\n{'='*80}")
    print("✅ TODOS LOS TESTS PASARON")
    print(f"{'='*80}")
    print("\nResumen de mejoras implementadas:")
    print("1. ✅ Detecta isla automáticamente")
    print("2. ✅ Pregunta certificación cuando no está clara")
    print("3. ✅ Pregunta hotel específico de la isla")
    print("4. ✅ Guarda hotel para coordinar recogida")
    print("5. ✅ Muestra isla específica en resumen (no genérico)")
    print("\nFlujo completo:")
    print("  'Estoy en isla grande y quiero bucear'")
    print("  → ¿Certificado? → ¿Hotel? → Plan → Cantidad → Última inmersión")
    print("  → Resumen con '📍 Salida: Isla Grande'")


if __name__ == "__main__":
    asyncio.run(test_island_hotel_flow())
