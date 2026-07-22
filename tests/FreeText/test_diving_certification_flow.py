"""
Test del flujo mejorado de buceo con pregunta de certificación.
"""

import asyncio
import pytest
from src.agents import orchestrator
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step


@pytest.fixture(autouse=True)
def _agent_books(_agent_answers_by_default, agent_decides):
    """These flows send a clear booking request in free text; the conversation
    agent picks a booking tool, which reuses the deterministic entry routing."""
    agent_decides(orchestrator.TOOL_START_BOOKING, {"activity": "certified"})


async def test_diving_certification_flow():
    """
    Prueba que cuando el usuario dice "quiero bucear" sin especificar certificación,
    el bot pregunta si está certificado y luego lo lleva al flujo correcto.
    """
    print("="*80)
    print("TEST: Flujo de Buceo con Pregunta de Certificación")
    print("="*80)
    
    # Caso 1: Usuario dice "Hola, estoy en pao pao y quiero bucear"
    print("\n" + "="*80)
    print("CASO 1: Buceo sin certificación clara + ubicación detectada")
    print("="*80)
    
    state = ConversationState(conversation_id="test-cert-1")
    
    # Mensaje inicial
    msg1 = "Hola, estoy en pao pao y quiero bucear"
    print(f"\nUsuario: {msg1}")
    
    resp1 = await route_message(state, msg1)
    print(f"\nBot:\n{resp1}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    print(f"  Language: {state.language}")
    print(f"  Detected activity: {state.detected_activity}")
    print(f"  Detected hotel: {state.detected_hotel}")
    print(f"  Detected island: {state.detected_island}")
    print(f"  Detected location: {state.detected_location}")
    print(f"  Detected certified: {state.detected_is_certified}")
    
    # Verificar que pregunta certificación
    assert state.step == Step.MIXED_ASK_CERTIFICATION, f"Esperado MIXED_ASK_CERTIFICATION, obtenido {state.step}"
    assert "certificado" in resp1.lower(), "Debería preguntar si está certificado"
    print("\n✅ Pregunta certificación correctamente")
    
    # Respuesta: Sí, estoy certificado
    msg2 = "1"  # Opción 1: Sí, estoy certificado
    print(f"\nUsuario: {msg2} (Sí, estoy certificado)")
    
    resp2 = await route_message(state, msg2)
    print(f"\nBot:\n{resp2}")
    print(f"\nEstado:")
    print(f"  Step: {state.step}")
    print(f"  Detected certified: {state.detected_is_certified}")
    print(f"  Location: {state.location}")
    
    # Verificar que va directo a elegir plan (porque ya tenía ubicación)
    assert state.step == Step.MIXED_ADD_CERT_PLAN, f"Esperado MIXED_ADD_CERT_PLAN, obtenido {state.step}"
    assert state.detected_is_certified == True, "Debería marcar como certificado"
    assert "2 inmersiones" in resp2 or "paquete" in resp2.lower(), "Debería mostrar opciones de plan"
    print("\n✅ Va directo a elegir plan de buceo certificado")
    
    # Caso 2: Usuario dice "quiero bucear" sin ubicación
    print("\n" + "="*80)
    print("CASO 2: Buceo sin certificación clara + sin ubicación")
    print("="*80)
    
    state2 = ConversationState(conversation_id="test-cert-2")
    
    msg3 = "Hola quiero bucear"
    print(f"\nUsuario: {msg3}")
    
    resp3 = await route_message(state2, msg3)
    print(f"\nBot:\n{resp3}")
    print(f"\nEstado:")
    print(f"  Step: {state2.step}")
    print(f"  Detected activity: {state2.detected_activity}")
    
    # Verificar que pregunta certificación
    assert state2.step == Step.MIXED_ASK_CERTIFICATION, f"Esperado MIXED_ASK_CERTIFICATION, obtenido {state2.step}"
    print("\n✅ Pregunta certificación correctamente")
    
    # Respuesta: No, soy principiante
    msg4 = "2"  # Opción 2: No, soy principiante
    print(f"\nUsuario: {msg4} (No, soy principiante)")
    
    resp4 = await route_message(state2, msg4)
    print(f"\nBot:\n{resp4}")
    print(f"\nEstado:")
    print(f"  Step: {state2.step}")
    print(f"  Detected certified: {state2.detected_is_certified}")
    
    # Verificar que pregunta ubicación (porque no la tenía)
    assert state2.step == Step.MIXED_LOCATION, f"Esperado MIXED_LOCATION, obtenido {state2.step}"
    assert state2.detected_is_certified == False, "Debería marcar como no certificado"
    assert "cartagena" in resp4.lower() and "islas" in resp4.lower(), "Debería preguntar ubicación"
    print("\n✅ Pregunta ubicación para principiante")
    
    # Respuesta: Cartagena
    msg5 = "1"  # Opción 1: Cartagena
    print(f"\nUsuario: {msg5} (Cartagena)")
    
    resp5 = await route_message(state2, msg5)
    print(f"\nBot:\n{resp5}")
    print(f"\nEstado:")
    print(f"  Step: {state2.step}")
    print(f"  Location: {state2.location}")
    
    # Verificar que va a preguntar cantidad (minicurso)
    assert state2.step == Step.MIXED_ADD_QTY, f"Esperado MIXED_ADD_QTY, obtenido {state2.step}"
    assert state2.location == "cartagena", "Debería guardar ubicación"
    assert "cuántas personas" in resp5.lower() or "how many" in resp5.lower(), "Debería preguntar cantidad"
    print("\n✅ Va a preguntar cantidad para minicurso")
    
    print("\n" + "="*80)
    print("✅ TODOS LOS TESTS PASARON")
    print("="*80)
    print("\nResumen:")
    print("- ✅ Detecta buceo sin certificación clara")
    print("- ✅ Pregunta certificación con botones")
    print("- ✅ Si certificado + ubicación → plan de buceo")
    print("- ✅ Si principiante + sin ubicación → pregunta ubicación → cantidad")


if __name__ == "__main__":
    asyncio.run(test_diving_certification_flow())
