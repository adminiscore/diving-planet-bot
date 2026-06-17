"""
Script de prueba manual para la detección de intención.
Ejecutar: python test_intent_manual.py
"""

import asyncio
from src.agents.intent_detector import IntentDetector
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState


def print_separator():
    print("\n" + "="*80 + "\n")


async def test_example(message: str, example_num: int):
    """Prueba un mensaje y muestra la detección y respuesta del bot."""
    print(f"📝 EJEMPLO {example_num}")
    print(f"Usuario: {message}")
    print("-" * 80)
    
    # Crear estado limpio
    state = ConversationState(conversation_id=f"test-{example_num}")
    
    # Detectar intención
    detector = IntentDetector()
    intent = detector.detect(message, state)
    
    print("🔍 DETECCIÓN:")
    print(f"  • Idioma: {intent.language or '❌ No detectado'}")
    print(f"  • Actividad: {intent.activity or '❌ No detectado'}")
    print(f"  • Servicio: {intent.service_id or '❌ No detectado'}")
    print(f"  • Certificado: {intent.is_certified if intent.is_certified is not None else '❌ No detectado'}")
    print(f"  • Grupo: {intent.group_size or '❌ No detectado'} personas")
    print(f"  • Ubicación: {intent.location or '❌ No detectado'}")
    print(f"  • Hotel: {intent.hotel or '❌ No detectado'}")
    print(f"  • Confianza: {intent.confidence:.2f}")
    print(f"  • Campos detectados: {', '.join(intent.detected_fields) or 'ninguno'}")
    
    # Obtener respuesta del bot
    response = await route_message(state, message)
    
    print("\n🤖 RESPUESTA DEL BOT:")
    print(response)
    
    print("\n📊 ESTADO DESPUÉS:")
    print(f"  • Step actual: {state.step.value}")
    print(f"  • Idioma guardado: {state.language}")
    print(f"  • Actividad detectada: {state.detected_activity or 'ninguna'}")
    print(f"  • Certificación detectada: {state.detected_is_certified if state.detected_is_certified is not None else 'ninguna'}")
    print(f"  • Grupo detectado: {state.detected_group_size or 'ninguno'}")
    
    print_separator()


async def main():
    print_separator()
    print("🧪 PRUEBAS DE DETECCIÓN INTELIGENTE DE INTENCIÓN")
    print_separator()
    
    # Ejemplo 1: Buzos certificados en español
    await test_example(
        "Hola somos dos personas que queremos hacer buceo y estamos certificados",
        1
    )
    
    # Ejemplo 2: Buzo certificado en inglés
    await test_example(
        "Hello I am a certified diver and want to dive",
        2
    )
    
    # Ejemplo 3: Buceo ambiguo (sin certificación clara)
    await test_example(
        "Hola quiero bucear",
        3
    )
    
    # Ejemplo 4: Minicurso
    await test_example(
        "Hola quiero hacer el minicurso de buceo, es mi primera vez",
        4
    )
    
    # Ejemplo 5: Grupo mixto
    await test_example(
        "Somos dos, yo quiero buceo certificado y mi novia snorkel",
        5
    )
    
    # Ejemplo 6: Con ubicación
    await test_example(
        "Quiero hacer buceo, estoy en Cartagena y soy certificado",
        6
    )
    
    print("✅ Pruebas completadas!")
    print("\nAhora prueba tus propios mensajes y comparte las respuestas.")


if __name__ == "__main__":
    asyncio.run(main())
