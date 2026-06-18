"""
Test de detección mejorada de hoteles e islas.
"""

from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState


def test_hotel_detection():
    """
    Prueba que el detector identifica correctamente hoteles e islas,
    incluyendo variantes y aliases comunes.
    """
    detector = IntentDetector()
    state = ConversationState(conversation_id="test-hotel")
    
    test_cases = [
        # Hotel Pao Pao
        ("Estoy en el Pao Pao", "pao_pao", "isla_grande", "island"),
        ("Me hospedo en el hotel Pao Pao", "pao_pao", "isla_grande", "island"),
        ("Pao Pao hotel", "pao_pao", "isla_grande", "island"),
        
        # San Pedro de Majagua
        ("Estoy en San Pedro de Majagua", "san_pedro_majagua", "isla_grande", "island"),
        ("Hotel Majagua", "san_pedro_majagua", "isla_grande", "island"),
        ("San Pedro", "san_pedro_majagua", "isla_grande", "island"),
        
        # Cocoliso
        ("Estoy en el Cocoliso", "cocoliso", "isla_grande", "island"),
        ("Hotel Cocoliso Island Resort", "cocoliso", "isla_grande", "island"),
        
        # Bora Bora
        ("Me hospedo en Bora Bora", "bora_bora", "isla_grande", "island"),
        ("Bora Bora Beach Club", "bora_bora", "isla_grande", "island"),
        
        # Fragata
        ("Estoy en Fragata", "fragata", "isla_grande", "island"),
        ("Fragata Island House", "fragata", "isla_grande", "island"),
        
        # Secreto
        ("Hostel Secreto", "secreto", "isla_grande", "island"),
        
        # Gente de Mar
        ("Gente de Mar Resort", "gente_de_mar", "isla_grande", "island"),
        
        # Luxury Beach
        ("Luxury Beach Club", "luxury_beach", "isla_grande", "island"),
        
        # Ecohotel Las Flores
        ("Ecohotel Las Flores", "ecohotel_flores", "isla_grande", "island"),
        ("Las Flores", "ecohotel_flores", "isla_grande", "island"),
        
        # Playa Libre
        ("Ecohostal Playa Libre", "playa_libre", "isla_grande", "island"),
        
        # Isla Marina - Islabela
        ("Estoy en Islabela", "islabela", "isla_marina", "island"),
        
        # Isla Marina - Hamaquero
        ("Hotel El Hamaquero", "hamaquero", "isla_marina", "island"),
        
        # Isla Marina - Ubuntu
        ("Centro Ubuntu", "ubuntu", "isla_marina", "island"),
        
        # Coralina (Isleta)
        ("Coralina Island", "coralina", "isleta", "island"),
        
        # Isleta Beach
        ("Isleta Beach", "isleta_beach", "isleta", "island"),
        
        # Isla Arena
        ("Isla Arena Eco Resort", "isla_arena_resort", "isla_arena", "island"),
        
        # Lizamar
        ("Hotel Lizamar", "lizamar", "isla_lizamar", "island"),
        
        # Gigi
        ("Casa de Isla Gigi", "gigi", "isla_gigi", "island"),
        
        # Rosario Ecohotel
        ("Rosario EcoHotel", "rosario_ecohotel", "isla_rosario", "island"),
        
        # San Tropel
        ("Hotel San Tropel", "san_tropel", "isla_rosario", "island"),
        
        # Solo isla (sin hotel)
        ("Estoy en Isla Grande", None, "isla_grande", "island"),
        ("Isla Marina", None, "isla_marina", "island"),
        ("Islas del Rosario", None, "isla_rosario", "island"),
        
        # Cartagena
        ("Estoy en Cartagena", None, None, "cartagena"),
        ("Salgo desde Cartagena", None, None, "cartagena"),
    ]
    
    print("="*80)
    print("TEST: Detección Mejorada de Hoteles e Islas")
    print("="*80)
    
    passed = 0
    failed = 0
    
    for msg, expected_hotel, expected_island, expected_location in test_cases:
        intent = detector.detect(msg, state)
        
        # Verificar hotel
        if expected_hotel:
            if intent.hotel == expected_hotel:
                status_hotel = "✅"
                passed += 1
            else:
                status_hotel = f"❌ (esperado: {expected_hotel}, obtenido: {intent.hotel})"
                failed += 1
        else:
            status_hotel = "N/A"
        
        # Verificar isla
        if expected_island:
            if intent.island == expected_island:
                status_island = "✅"
                if expected_hotel:  # Solo contar si también esperábamos hotel
                    passed += 1
            else:
                status_island = f"❌ (esperado: {expected_island}, obtenido: {intent.island})"
                if expected_hotel:
                    failed += 1
        else:
            status_island = "N/A"
        
        # Verificar ubicación
        if intent.location == expected_location:
            status_location = "✅"
            passed += 1
        else:
            status_location = f"❌ (esperado: {expected_location}, obtenido: {intent.location})"
            failed += 1
        
        print(f"\nMensaje: '{msg}'")
        print(f"  Hotel: {status_hotel} ({intent.hotel})")
        print(f"  Isla: {status_island} ({intent.island})")
        print(f"  Ubicación: {status_location} ({intent.location})")
    
    print("\n" + "="*80)
    print(f"RESULTADO: {passed} pasaron, {failed} fallaron")
    print("="*80)
    
    if failed == 0:
        print("\n🎉 ¡Todos los tests pasaron!")
    else:
        print(f"\n⚠️  {failed} tests fallaron")
    
    return failed == 0


if __name__ == "__main__":
    success = test_hotel_detection()
    exit(0 if success else 1)
