# Cómo Probar la Detección Inteligente de Intención

## Ejecutar Tests

### Tests Unitarios (IntentDetector)
```bash
# Todos los tests del detector
python -m pytest tests/test_intent_detector.py -v

# Tests específicos
python -m pytest tests/test_intent_detector.py::TestLanguageDetection -v
python -m pytest tests/test_intent_detector.py::TestActivityDetection -v
python -m pytest tests/test_intent_detector.py::TestCompleteScenarios -v
```

### Tests End-to-End (Conversaciones completas)
```bash
# Todos los tests de detección de intención
python -m pytest tests/test_conversations.py -k "intent_" -v

# Test específico
python -m pytest tests/test_conversations.py::test_intent_certified_divers_spanish_skips_to_last_dive -v
```

### Todos los Tests
```bash
# Ejecutar todos los tests del proyecto
python -m pytest tests/ -v

# Solo tests de intent detection
python -m pytest tests/test_intent_detector.py tests/test_conversations.py -k "intent_" -v
```

---

## Probar Manualmente en Python

### 1. Probar el Detector Directamente

```python
from src.agents.intent_detector import IntentDetector
from src.flows.decision_tree import ConversationState

# Crear detector
detector = IntentDetector()

# Crear estado de conversación
state = ConversationState(conversation_id="test-123")

# Probar diferentes mensajes
messages = [
    "Hola somos dos personas que queremos hacer buceo y estamos certificados",
    "Hello I am a certified diver and want to dive",
    "Hola quiero bucear",
    "Quiero hacer el minicurso de buceo",
    "Somos dos, yo buceo y mi novia snorkel",
    "Estoy en el hotel Pao Pao y quiero hacer snorkel",
]

for msg in messages:
    intent = detector.detect(msg, state)
    print(f"\nMensaje: {msg}")
    print(f"  Idioma: {intent.language}")
    print(f"  Actividad: {intent.activity}")
    print(f"  Certificado: {intent.is_certified}")
    print(f"  Grupo: {intent.group_size}")
    print(f"  Confianza: {intent.confidence:.2f}")
    print(f"  Campos detectados: {intent.detected_fields}")
```

### 2. Probar el Flujo Completo con Supervisor

```python
import asyncio
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState

async def test_conversation():
    # Crear estado
    state = ConversationState(conversation_id="test-456")
    
    # Enviar mensaje
    message = "Hola somos dos personas que queremos hacer buceo y estamos certificados"
    response = await route_message(state, message)
    
    print(f"Usuario: {message}")
    print(f"Bot: {response}")
    print(f"\nEstado después:")
    print(f"  Step: {state.step}")
    print(f"  Language: {state.language}")
    print(f"  Detected activity: {state.detected_activity}")
    print(f"  Detected certified: {state.detected_is_certified}")
    print(f"  Detected group size: {state.detected_group_size}")

# Ejecutar
asyncio.run(test_conversation())
```

---

## Casos de Prueba Recomendados

### Caso 1: Buzos Certificados (Español)
```
Mensaje: "Hola somos dos personas que queremos hacer buceo y estamos certificados"

Esperado:
✅ Detecta: idioma=es, actividad=certified_diving, certificado=True, grupo=2
✅ Salta a: Step.CERTIFIED_LAST_DIVE
✅ Respuesta incluye: "Genial" y "última inmersión"
```

### Caso 2: Buzo Certificado (Inglés)
```
Mensaje: "Hello I am a certified diver and want to dive"

Esperado:
✅ Detecta: idioma=en, actividad=certified_diving, certificado=True
✅ Salta a: Step.CERTIFIED_LAST_DIVE
✅ Respuesta incluye: "Great" y "last dive"
```

### Caso 3: Buceo Ambiguo
```
Mensaje: "Hola quiero bucear"

Esperado:
✅ Detecta: idioma=es, actividad=certified_diving, certificado=None
✅ Va a: Step.TOURS_EXPERIENCE
✅ Respuesta pregunta: certificación o composición de grupo
```

### Caso 4: Minicurso
```
Mensaje: "Hola quiero hacer el minicurso de buceo, es mi primera vez"

Esperado:
✅ Detecta: idioma=es, actividad=minicourse, certificado=False
✅ Salta certificación (ya sabemos que no está certificado)
```

### Caso 5: Grupo Mixto
```
Mensaje: "Somos dos, yo quiero buceo certificado y mi novia snorkel"

Esperado:
✅ Detecta: idioma=es, grupo=2, certificado=True
✅ Salta a: Step.CERTIFIED_LAST_DIVE
✅ Respuesta incluye: confirmación de grupo y pregunta de última inmersión
```

### Caso 6: Grupo Mixto - Minicurso + Snorkel
```
Mensaje: "Hola somos dos, yo haría el minicurso y mi amigo snorkel"

Esperado:
✅ Detecta: idioma=es, grupo=2, actividades mixtas
✅ Pre-carga cart con minicurso + snorkel
✅ Va a: Step.MIXED_CART_REVIEW
```

### Caso 7: Con Ubicación
```
Mensaje: "Quiero hacer buceo, estoy en Cartagena y soy certificado"

Esperado:
✅ Detecta: actividad=certified_diving, ubicación=cartagena, certificado=True
✅ Guarda ubicación en state.location
✅ Salta a: Step.CERTIFIED_LAST_DIVE
```

### Caso 8: Curso PADI
```
Mensaje: "Hola quiero hacer el curso PADI Open Water"

Esperado:
✅ Detecta: idioma=es, actividad=padi_course, servicio=open_water
✅ Entra al flujo de cursos PADI
```

### Caso 9: Con Hotel
```
Mensaje: "Hola estoy en el hotel Pao Pao y quiero hacer snorkel"

Esperado:
✅ Detecta: idioma=es, hotel=pao_pao, actividad=snorkel
✅ Guarda hotel en state.hotel
```

### Caso 10: Última Inmersión
```
Mensaje: "Mi última inmersión fue hace 6 meses"

Esperado:
✅ Detecta: last_dive_over_2_years=False
✅ Guarda en state
```

---

## Verificar en Logs

Cuando ejecutes el bot, busca en los logs líneas como:

```
[INTENT] Detected language: es
[INTENT] Detected activity: certified_diving (service: 2_dives_1_day)
[INTENT] Detected certification: True
[INTENT] Detected group size: 2
[INTENT] Skipping to certified flow
```

Estas líneas confirman que la detección está funcionando.

---

## Debugging

### Si la detección no funciona:

1. **Verificar confianza**:
   ```python
   intent = detector.detect(message, state)
   print(f"Confidence: {intent.confidence}")
   print(f"Detected fields: {intent.detected_fields}")
   ```
   - Si confianza < 0.2, no se aplicará
   - Revisar qué campos se detectaron

2. **Verificar patrones regex**:
   - Abrir `src/agents/intent_detector.py`
   - Buscar los patrones en `_detect_activity()`, `_detect_certification()`, etc.
   - Añadir nuevos patrones si es necesario

3. **Verificar que no sea input de menú**:
   - La detección NO se ejecuta si el mensaje es un dígito
   - La detección NO se ejecuta si el mensaje tiene menos de 4 caracteres

4. **Verificar step actual**:
   - Algunos saltos solo funcionan desde ciertos steps
   - Ver `_should_skip_to_certified_flow()`, `_should_ask_certification()`, etc.

---

## Añadir Nuevos Patrones

Si necesitas detectar nuevas frases:

1. Abrir `src/agents/intent_detector.py`
2. Encontrar el método relevante (ej: `_detect_activity()`)
3. Añadir nuevo patrón regex:
   ```python
   certified_diving_patterns = [
       # ... patrones existentes ...
       r'\bnuevo_patron\b',  # Tu nuevo patrón
   ]
   ```
4. Añadir test en `tests/test_intent_detector.py`:
   ```python
   def test_detect_nuevo_patron(self, detector, state):
       intent = detector.detect("mensaje con nuevo patron", state)
       assert intent.activity == "certified_diving"
   ```
5. Ejecutar tests: `python -m pytest tests/test_intent_detector.py -v`

---

## Próximos Pasos

Una vez validado en desarrollo:

1. ✅ Ejecutar todos los tests: `python -m pytest tests/ -v`
2. ✅ Probar manualmente casos principales
3. ✅ Revisar logs en desarrollo
4. 📋 Validar con conversaciones reales de WhatsApp
5. 📋 Ajustar patrones según feedback
6. 📋 Medir métricas (tasa de salto, precisión)
7. 📋 Deploy a staging
8. 📋 Deploy a producción

---

## Recursos

- **Documento de diseño**: `docs/free-text-intent-detection.md`
- **Resumen Sprint 1**: `docs/SPRINT1_INTENT_DETECTION_SUMMARY.md`
- **Código detector**: `src/agents/intent_detector.py`
- **Integración supervisor**: `src/agents/supervisor.py`
- **Tests unitarios**: `tests/test_intent_detector.py`
- **Tests end-to-end**: `tests/test_conversations.py`
