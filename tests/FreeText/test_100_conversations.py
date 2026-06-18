"""
Test de 100 conversaciones reales para validar detección de intención.

Ejecutar: python -m tests.FreeText.test_100_conversations
o bien:   python tests/FreeText/test_100_conversations.py
"""

import sys
import io

# Fix encoding for Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState


MESSAGES = [
    "Hola somos 3 personas y queremos hacer snorkel mañana.",
    "Hi, we are 2 people interested in diving, is there availability tomorrow?",
    "Somos una pareja y queremos hacer bautismo de buceo.",
    "Hola, estamos en Cartagena y queremos precios para snorkel.",
    "Somos 5 amigos, dos certificados Open Water y tres sin experiencia.",
    "Hi, we are staying in Baru and would like to go snorkeling.",
    "Somos 4 personas y queremos saber horarios disponibles.",
    "Hola, tenemos licencia PADI Open Water.",
    "Somos 2 personas y queremos bucear el viernes si hay cupo.",
    "Hi, 3 of us want to do scuba diving, never tried before.",
    "Somos una familia de 6 personas, dos niños de 10 y 13 años.",
    "Hola, estamos en Islas del Rosario y queremos actividad mañana.",
    "Somos 2 certificados Advanced y queremos dos inmersiones.",
    "Hi, we are 4 people and need snorkeling trip.",
    "Hola, somos 3 personas y uno no sabe nadar.",
    "Somos 7 amigos de vacaciones, queremos saber precio grupo.",
    "Hi, we are 2 divers with SSI certification.",
    "Hola, queremos hacer snorkel por la mañana.",
    "Somos una pareja y uno tiene miedo al agua.",
    "Hi, we are arriving tomorrow by cruise ship.",
    "Somos 4 personas y queremos alquilar equipo completo.",
    "Hola, somos dos personas mayores y queremos actividad tranquila.",
    "Somos 5 personas, uno Rescue Diver.",
    "Hi, we are Open Water certified but no cards with us.",
    "Hola, estamos en Barú y queremos reservar.",
    "Somos 3 personas y queremos bucear mañana temprano.",
    "Hi, we are 6 friends from UK, no experience.",
    "Hola somos 2 personas y queremos saber si incluyen transporte.",
    "Somos una familia de 5, dos adolescentes.",
    "Hi, we want snorkeling and diving mix group.",
    "Hola somos 4 personas y uno tiene 12 años.",
    "Somos 2 personas certificados CMAS.",
    "Hi, we are 3 people and want discover scuba diving.",
    "Hola, estamos en Cartagena centro.",
    "Somos 8 personas de despedida de soltero.",
    "Hi, we are 2 divers with 50+ dives each.",
    "Hola, queremos hacer snorkel en la tarde.",
    "Somos 3 amigos y queremos buceo recreativo.",
    "Hi, we are staying in hotel in Baru, can you pick up?",
    "Hola, somos 2 personas y queremos información general.",
    "Somos 4 personas y queremos ver tortugas.",
    "Hi, we are 5 people, only one certified diver.",
    "Hola, somos una pareja y queremos hacer algo sencillo.",
    "Somos 6 personas, ninguno ha buceado antes.",
    "Hi, we are Open Water certified, 20 dives each.",
    "Hola, queremos saber si hay salida hoy.",
    "Somos 3 personas y uno tiene asma leve.",
    "Hi, we are 2 people and want snorkeling only.",
    "Hola, somos 4 amigos de Medellín.",
    "Somos 2 personas y queremos buceo mañana.",
    "Hi, we are 3 people, one Advanced diver.",
    "Hola, somos familia de 7 personas.",
    "Somos 2 personas y queremos bautismo de buceo.",
    "Hi, we are 4 friends and want scuba diving.",
    "Hola, estamos en Isla Grande y queremos salir hoy.",
    "Somos 5 personas, dos no saben nadar.",
    "Hi, we are 2 divers with Advanced certification.",
    "Hola, queremos snorkel y transporte desde Cartagena.",
    "Somos 3 personas y queremos información de precios.",
    "Hi, we are 6 people from Spain.",
    "Hola, somos 2 personas y queremos bucear.",
    "Somos 4 personas y uno es Divemaster.",
    "Hi, we are 3 people and want snorkeling tour.",
    "Hola, somos 5 amigos y queremos actividad mañana.",
    "Somos 2 personas certificados pero sin experiencia reciente.",
    "Hi, we are 4 people arriving tomorrow.",
    "Hola, somos familia con niño de 9 años.",
    "Somos 3 personas y queremos snorkel.",
    "Hi, we are 2 divers and need equipment rental.",
    "Hola, estamos en Barú hoy.",
    "Somos 7 personas y queremos precio grupal.",
    "Hi, we are 3 people, Open Water certified.",
    "Hola, somos 2 personas y queremos ver si hay cupo.",
    "Somos 4 personas y queremos buceo recreativo.",
    "Hi, we are 5 people staying in Cartagena.",
    "Hola, somos 3 personas y uno no sabe nadar.",
    "Somos 2 personas y queremos snorkel mañana.",
    "Hi, we are 4 divers with experience.",
    "Hola, somos 6 amigos y queremos buceo.",
    "Somos 3 personas y queremos información general.",
    "Hi, we are 2 people and want diving trip.",
    "Hola, somos 5 personas y queremos snorkel.",
    "Somos 4 personas y uno tiene certificación Open Water.",
    "Hi, we are 3 people arriving by cruise ship.",
    "Hola, somos 2 personas y queremos bautismo.",
    "Somos 6 personas y queremos actividad tranquila.",
    "Hi, we are 4 friends from UK.",
    "Hola, somos 3 personas y queremos bucear mañana.",
    "Somos 2 personas certificados SSI.",
    "Hi, we are 5 people and want snorkeling.",
    "Hola, somos familia de 4 personas.",
    "Somos 3 personas y uno es Rescue Diver.",
    "Hi, we are 2 divers and want two dives.",
    "Hola, estamos en Cartagena y queremos info.",
    "Somos 4 personas y queremos snorkel.",
    "Hi, we are 3 people and no experience.",
    "Hola, somos 2 personas y queremos actividad.",
    "Somos 5 personas y queremos buceo mañana.",
    "Hi, we are 4 people staying in Baru.",
    "Hola, somos 3 personas y queremos reservar snorkel.",
]


def classify_routing(intent) -> str:
    """Determine expected routing path from detected intent."""
    alloc = intent.group_allocation
    activity = intent.activity
    certified = intent.is_certified
    group = intent.group_size

    # Mixed group (2 activities)
    if alloc and len(alloc) >= 2:
        return "MIXED_FLOW -> carrito pre-cargado"

    # Certified diving
    if activity in ("certified_diving",) or certified is True:
        return "BUCEO_CERTIFICADO -> pregunta último buceo"

    # Minicourse / discover
    if activity in ("minicourse", "bautismo"):
        return "MINICURSO/BAUTISMO -> añadir al carrito"

    # Snorkel
    if activity == "snorkel":
        n = group or 1
        qty_note = f"({n} persona{'s' if n > 1 else ''})" if n else ""
        return f"SNORKEL {qty_note} -> añadir al carrito"

    # Diving ambiguous
    if activity == "diving":
        return "BUCEO_AMBIGUO -> preguntar certificación"

    return "RAG/INFO -> sin actividad clara"


def questions_needed(intent) -> list:
    """List which questions still need to be asked (skipped if already detected)."""
    questions = []
    alloc = intent.group_allocation
    activity = intent.activity
    certified = intent.is_certified
    group = intent.group_size
    location = intent.location

    # Skip group_size question if already detected
    if not group and not alloc:
        questions.append("¿Cuántas personas?")

    # Skip location if already detected
    if not location:
        questions.append("¿Dónde (Cartagena/Barú/Islas)?")

    # Skip certification if already known
    if activity in ("diving", "certified_diving") and certified is None and not alloc:
        plural = group and group > 1
        q = "¿Estáis certificados?" if plural else "¿Estás certificado?"
        questions.append(q)

    # For mixed alloc with cert divers
    if alloc:
        cert_qty = alloc.get("certified_diving", 0)
        if cert_qty and certified is None:
            plural = cert_qty > 1
            q = "¿Estáis certificados?" if plural else "¿Estás certificado?"
            questions.append(q)

    if (activity in ("certified_diving",) or certified is True):
        questions.append("¿Último buceo hace más de 2 años?")

    return questions


def main():
    detector = IntentDetector()

    # Counters
    routing_counts = {}
    issues = []
    detected_group = 0
    detected_activity = 0
    detected_cert = 0
    detected_mixed = 0
    detected_location = 0

    print("=" * 100)
    print("TEST: 100 CONVERSACIONES - ANÁLISIS DE DETECCIÓN")
    print("=" * 100)

    for i, msg in enumerate(MESSAGES, 1):
        state = ConversationState(conversation_id=f"test-{i}")
        intent = detector.detect(msg, state)

        routing = classify_routing(intent)
        questions = questions_needed(intent)
        routing_counts[routing.split(" ->")[0]] = routing_counts.get(routing.split(" ->")[0], 0) + 1

        if intent.group_size:
            detected_group += 1
        if intent.activity:
            detected_activity += 1
        if intent.is_certified is not None:
            detected_cert += 1
        if intent.group_allocation and len(intent.group_allocation) >= 2:
            detected_mixed += 1
        if intent.location:
            detected_location += 1

        # Print detailed line
        lang_flag = "ES" if intent.language == "es" else "EN" if intent.language == "en" else "??"
        group_str = f"g={intent.group_size}" if intent.group_size else "g=?"
        alloc_str = str(intent.group_allocation) if intent.group_allocation else "-"
        act_str = intent.activity or "-"
        cert_str = "cert=Y" if intent.is_certified is True else "cert=N" if intent.is_certified is False else "cert=?"
        loc_str = intent.location or "-"

        skip_str = f"skip {5 - len(questions)}/5 preguntas" if questions else "todo detectado"
        q_str = " | ".join(questions) if questions else "ninguna"

        print(f"\n[{i:3d}] [{lang_flag}] {msg[:60]:<60}")
        print(f"       Detección: act={act_str:<18} {cert_str}  {group_str}  alloc={alloc_str}  loc={loc_str}")
        print(f"       Routing:   {routing}")
        print(f"       Preguntas pendientes: {q_str}")

        # Flag potential issues
        msg_lower = msg.lower()
        if ("snorkel" in msg_lower or "buceo" in msg_lower or "diving" in msg_lower or "scuba" in msg_lower) and not intent.activity:
            issues.append((i, msg, "ACTIVIDAD no detectada"))
        if ("certificad" in msg_lower or "certified" in msg_lower or "open water" in msg_lower or "ssi" in msg_lower or "padi" in msg_lower or "cmas" in msg_lower) and intent.is_certified is None:
            issues.append((i, msg, "CERTIFICACIÓN no detectada"))
        if ("somos" in msg_lower or "we are" in msg_lower or "personas" in msg_lower or "friends" in msg_lower or "people" in msg_lower) and not intent.group_size and not intent.group_allocation:
            issues.append((i, msg, "GRUPO no detectado"))

    # Summary
    print("\n" + "=" * 100)
    print("RESUMEN")
    print("=" * 100)
    print(f"Total mensajes: {len(MESSAGES)}")
    print(f"Grupo detectado:      {detected_group:3d}/{len(MESSAGES)} ({detected_group/len(MESSAGES)*100:.0f}%)")
    print(f"Actividad detectada:  {detected_activity:3d}/{len(MESSAGES)} ({detected_activity/len(MESSAGES)*100:.0f}%)")
    print(f"Certificación:        {detected_cert:3d}/{len(MESSAGES)} ({detected_cert/len(MESSAGES)*100:.0f}%)")
    print(f"Flujo mixto:          {detected_mixed:3d}/{len(MESSAGES)} ({detected_mixed/len(MESSAGES)*100:.0f}%)")
    print(f"Ubicación:            {detected_location:3d}/{len(MESSAGES)} ({detected_location/len(MESSAGES)*100:.0f}%)")

    print("\nDistribución de rutas:")
    for route, count in sorted(routing_counts.items(), key=lambda x: -x[1]):
        print(f"  {route:<35} {count:3d} mensajes")

    if issues:
        print(f"\n⚠️  POSIBLES PROBLEMAS ({len(issues)}):")
        for idx, msg, issue in issues:
            print(f"  [{idx:3d}] {issue}: {msg[:70]}")
    else:
        print("\n✅  Sin problemas detectados")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
