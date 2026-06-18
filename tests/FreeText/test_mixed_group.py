"""
Test de detección de grupos mixtos.
"""

import asyncio
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState


async def test_mixed_group():
    """
    Prueba que cuando el usuario dice "Somos dos, yo quiero buceo certificado y mi novia snorkel",
    el bot detecte correctamente que son 2 actividades diferentes.
    """
    print("="*80)
    print("TEST: Detección de grupos mixtos")
    print("="*80)
    
    state = ConversationState(conversation_id="test-mixed")
    state.language = "es"
    
    # Mensaje: Usuario menciona grupo mixto
    msg = "Somos dos, yo quiero buceo certificado y mi novia snorkel"
    print(f"\nUsuario: {msg}")
    resp = await route_message(state, msg)
    print(f"\nBot:\n{resp}")
    print(f"\nEstado: step={state.step.value}")
    print(f"Actividad detectada: {state.detected_activity}")
    print(f"Grupo detectado: {state.detected_group_size}")
    print(f"Group allocation: {state.detected_group_allocation}")
    
    # Verificar que detectó grupo mixto
    assert state.detected_group_allocation is not None, "Debería detectar group_allocation"
    assert len(state.detected_group_allocation) == 2, f"Debería detectar 2 actividades, detectó {len(state.detected_group_allocation)}"
    assert 'certified_diving' in state.detected_group_allocation, "Debería detectar buceo certificado"
    assert 'snorkel' in state.detected_group_allocation, "Debería detectar snorkel"
    assert state.step.value == "mixed_entry", f"Debería ir al carrito, está en {state.step.value}"
    
    # Verificar mensaje de bienvenida
    assert "bienvenidos" in resp.lower() or "welcome" in resp.lower(), "Debería decir 'Bienvenidos'"
    assert "2 personas" in resp.lower() or "2 people" in resp.lower(), "Debería mencionar 2 personas"
    assert "buceo certificado" in resp.lower() or "certified diving" in resp.lower(), "Debería mencionar buceo certificado"
    assert "snorkel" in resp.lower(), "Debería mencionar snorkel"
    
    print("\n" + "="*80)
    print("EXITO: Detección de grupos mixtos funciona correctamente!")
    print("="*80)
    print("\nResumen:")
    print(f"- Detectó {len(state.detected_group_allocation)} actividades diferentes")
    print(f"- Actividades: {list(state.detected_group_allocation.keys())}")
    print(f"- Mensaje personalizado: 'Bienvenidos! Veo que son 2 personas: 1 para buceo certificado y 1 para snorkel.'")
    print(f"- Redirigió al carrito (step={state.step.value})")


if __name__ == "__main__":
    asyncio.run(test_mixed_group())
