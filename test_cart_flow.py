"""
Test rápido del nuevo flujo de carrito con detección de intención.
"""

import asyncio
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState


async def test_certified_divers_cart_flow():
    """
    Prueba: "Hola somos dos personas que queremos hacer buceo y estamos certificados"
    
    Flujo esperado:
    1. Detecta: idioma=es, actividad=buceo certificado, certificados=True, grupo=2
    2. Pregunta: ubicación (Cartagena vs Islas)
    3. Después de ubicación → pregunta plan (2 inmersiones vs multi-día)
    4. Después de plan → pregunta última inmersión
    5. Después de última inmersión → muestra preview y añade al carrito
    """
    print("="*80)
    print("TEST: Flujo de carrito con detección de intención")
    print("="*80)
    
    state = ConversationState(conversation_id="test-cart-flow")
    
    # Mensaje 1: Usuario envía intención completa
    msg1 = "Hola somos dos personas que queremos hacer buceo y estamos certificados"
    print(f"\n👤 Usuario: {msg1}")
    resp1 = await route_message(state, msg1)
    print(f"\n🤖 Bot:\n{resp1}")
    print(f"\n📊 Estado: step={state.step.value}, location={state.location}")
    
    # Mensaje 2: Usuario responde ubicación
    msg2 = "1"  # Cartagena
    print(f"\n👤 Usuario: {msg2} (Cartagena)")
    resp2 = await route_message(state, msg2)
    print(f"\n🤖 Bot:\n{resp2}")
    print(f"\n📊 Estado: step={state.step.value}, location={state.location}")
    
    # Mensaje 3: Usuario elige plan
    msg3 = "1"  # 2 inmersiones / 1 día
    print(f"\n👤 Usuario: {msg3}")
    resp3 = await route_message(state, msg3)
    print(f"\n🤖 Bot:\n{resp3}")
    print(f"\n📊 Estado: step={state.step.value}")
    
    # Mensaje 4: Usuario responde última inmersión
    msg4 = "2"  # No (menos de 2 años)
    print(f"\n👤 Usuario: {msg4}")
    resp4 = await route_message(state, msg4)
    print(f"\n🤖 Bot:\n{resp4}")
    print(f"\n📊 Estado: step={state.step.value}")
    
    print("\n" + "="*80)
    print("✅ Test completado!")
    print("="*80)
    
    # Verificaciones
    print("\n🔍 Verificaciones:")
    print(f"  ✓ Idioma detectado: {state.detected_language}")
    print(f"  ✓ Actividad detectada: {state.detected_activity}")
    print(f"  ✓ Certificación detectada: {state.detected_is_certified}")
    print(f"  ✓ Grupo detectado: {state.detected_group_size}")
    print(f"  ✓ Ubicación guardada: {state.location}")
    print(f"  ✓ Carrito: {len(state.mixed_cart)} items")


if __name__ == "__main__":
    asyncio.run(test_certified_divers_cart_flow())
