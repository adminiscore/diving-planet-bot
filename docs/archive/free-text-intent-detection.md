# Detección Inteligente de Intención en Texto Libre

## Objetivo

Permitir que el bot detecte automáticamente información del usuario en mensajes de texto libre (idioma, actividad, certificación, número de personas, etc.) y **salte fases del árbol de decisión** que ya fueron respondidas implícitamente, guardando esta información en el estado de la conversación para uso posterior.

## Principios de Diseño

1. **Detección continua**: Funciona en cualquier momento de la conversación (mensaje inicial, mitad de flujo, o después de haber marcado opciones en el árbol)
2. **Memoria persistente**: La información detectada se guarda en `ConversationState` y se usa en decisiones posteriores
3. **Salto inteligente**: Si detectamos información, saltamos preguntas del árbol que ya están respondidas
4. **Confirmación natural**: Mostramos un mensaje de confirmación/resumen antes de continuar con el árbol
5. **Fallback graceful**: Si falta información, preguntamos solo lo necesario

---

## Fases de Implementación

### Fase 1: Detección de Idioma Automática

**Objetivo**: Detectar si el mensaje es español o inglés y saltar `Step.LANGUAGE_SELECTION`.

**Detección**:
- Usar heurísticas simples (palabras clave: "hola", "quiero", "buceo" → ES; "hello", "want", "diving" → EN)
- Opcionalmente: usar LLM para clasificación si es ambiguo

**Estado a guardar**:
```python
state.language = "es" | "en"
```

**Lógica de salto**:
- Si estamos en `Step.INIT` o `Step.LANGUAGE_SELECTION` y detectamos idioma → saltar a siguiente paso del árbol
- Si ya estamos en otro paso, solo guardar el idioma detectado

**Mensaje de confirmación**: Ninguno (transparente)

---

### Fase 2: Detección de Actividad Principal

**Objetivo**: Detectar qué actividad quiere el usuario (buceo certificado, minicurso, snorkel, curso PADI, etc.).

**Detección** (palabras clave y contexto):
- **Buceo certificado**: "buceo", "dive", "buzo", "certificado", "dos inmersiones"
- **Minicurso/Bautismo**: "minicurso", "bautismo", "primera vez", "nunca he buceado", "discover scuba"
- **Snorkel**: "snorkel", "snorkeling", "careteo"
- **Curso PADI**: "curso", "open water", "advanced", "rescue", "divemaster", "certificarme"
- **Especialidades**: "nitrox", "buoyancy", "flotabilidad", "naturalista", etc.

**Estado a guardar**:
```python
state.detected_activity = "certified_diving" | "minicourse" | "snorkel" | "padi_course" | "specialty"
state.detected_service_id = "2_dives_1_day" | "minicourse" | "snorkeling" | "open_water" | ...
```

**Lógica de salto**:
- Si detectamos actividad → saltar menús de selección de actividad
- Ir directamente al siguiente paso relevante del árbol para esa actividad

---

### Fase 3: Detección de Certificación (para buceo)

**Objetivo**: Si el usuario menciona buceo, detectar si está certificado o no.

**Detección**:
- **Certificado**: "certificado", "certified", "tengo licencia", "PADI", "SSI", "buzo certificado"
- **No certificado**: "no certificado", "primera vez", "nunca he buceado", "not certified", "beginner"
- **Ambiguo**: Solo dice "buceo" sin más contexto

**Estado a guardar**:
```python
state.is_certified = True | False | None  # None = no sabemos aún
```

**Lógica de salto**:
- Si `is_certified = True` → saltar pregunta de certificación, ir a `certified_last_dive`
- Si `is_certified = False` → saltar pregunta de certificación, ofrecer minicurso (1 día) o curso PADI (multi-día en islas)
- Si `is_certified = None` → preguntar con botones: "¿Eres buzo certificado?"

**Mensaje de confirmación** (si `is_certified = True`):
```
¡Genial! Veo que eres buzo certificado. Para ofrecerte la mejor experiencia, necesito saber:
```
Luego mostrar pregunta `certified_last_dive` del árbol.

**Mensaje de confirmación** (si `is_certified = False`):
```
Perfecto, puedo ayudarte a empezar en el buceo:
- Si estás **un día**: te recomiendo nuestro **Minicurso de Buceo** (bautismo)
- Si estás **varios días en las islas**: puedes hacer el **Curso PADI Open Water** completo

¿Qué prefieres?
```

---

### Fase 4: Detección de Número de Personas y Distribución de Actividades

**Objetivo**: Detectar cuántas personas son y qué actividad quiere cada una.

**Detección de cantidad**:
- Patrones: "somos 2", "somos dos", "venimos tres", "we are 4", "group of 5"
- Patrones de distribución: "yo buceo y mi novia snorkel", "dos quieren buceo y uno snorkel", "all diving"

**Estado a guardar**:
```python
state.detected_group_size = 2
state.detected_group_allocation = {
    "certified_diving": 2,  # 2 personas buceo certificado
    "snorkel": 0
}
# O distribución mixta:
state.detected_group_allocation = {
    "certified_diving": 1,  # yo
    "snorkel": 1           # mi novia
}
```

**Lógica de salto**:
- Si detectamos grupo mixto (diferentes actividades) → ir a `Step.MIXED_ENTRY` con items pre-cargados
- Si detectamos grupo homogéneo (todos misma actividad) → continuar flujo normal pero con cantidad detectada
- Si detectamos buceo en grupo → preguntar certificación de cada persona si no está clara

**Mensaje de confirmación** (grupo homogéneo certificado):
```
Perfecto, entiendo que son 2 personas certificadas que quieren hacer buceo. 
Para continuar, necesito saber cuándo fue su última inmersión:
```
Luego mostrar pregunta `certified_last_dive` del árbol.

**Mensaje de confirmación** (grupo mixto):
```
Entiendo que quieren hacer actividades diferentes:
- 1 persona: Buceo certificado
- 1 persona: Snorkel

Voy a preparar tu reserva con estas actividades. Primero necesito algunos datos...
```
Luego continuar con flujo `MIXED_ENTRY` (cart) con items pre-cargados.

---

### Fase 5: Detección de Última Inmersión (para certificados)

**Objetivo**: Si mencionan cuándo fue su última inmersión, guardar esa info.

**Detección**:
- "última inmersión hace 6 meses", "last dive 1 year ago", "buceo hace 3 años"
- Extraer tiempo: < 2 años o > 2 años

**Estado a guardar**:
```python
state.last_dive_over_2_years = True | False
```

**Lógica de salto**:
- Si `last_dive_over_2_years = False` → saltar pregunta, ir directo a resumen/colombian discount
- Si `last_dive_over_2_years = True` → saltar pregunta, ofrecer refresher (minicurso)

---

### Fase 6: Detección de Duración (un día vs multi-día)

**Objetivo**: Detectar si el usuario está un día o varios días.

**Detección**:
- "un día", "one day", "solo hoy", "varios días", "multi-day", "estoy en las islas 3 días"

**Estado a guardar**:
```python
state.detected_duration = "single_day" | "multi_day"
```

**Lógica de salto**:
- Si detectamos duración → saltar pregunta de paquetes vs tours
- Ofrecer directamente opciones relevantes (2 dives vs 5/7/9 dives)

---

### Fase 7: Detección de Ubicación/Isla/Hotel

**Objetivo**: Detectar si mencionan desde dónde salen (Cartagena, isla específica, hotel).

**Detección**:
- "desde Cartagena", "estoy en Isla Grande", "hotel Pao Pao", "San Pedro de Majagua"

**Estado a guardar**:
```python
state.detected_location = "cartagena" | "island"
state.detected_island = "isla_grande" | ...
state.detected_hotel = "pao_pao" | ...
```

**Lógica de salto**:
- Si detectamos ubicación → saltar pregunta de logística
- Pre-cargar en el árbol cuando llegue a `Step.ISLAND_MENU` o `Step.ISLAND_HOTEL_MENU`

---

## Arquitectura de Implementación

### Componente Principal: `IntentDetector`

**Ubicación**: `src/agents/intent_detector.py`

**Responsabilidades**:
1. Analizar mensaje de texto libre
2. Detectar múltiples dimensiones (idioma, actividad, certificación, grupo, etc.)
3. Devolver estructura de intención detectada
4. Usar tanto heurísticas (rápido) como LLM (preciso) según necesidad

**Interfaz**:
```python
@dataclass
class DetectedIntent:
    language: Optional[str] = None
    activity: Optional[str] = None
    service_id: Optional[str] = None
    is_certified: Optional[bool] = None
    group_size: Optional[int] = None
    group_allocation: Optional[Dict[str, int]] = None
    last_dive_over_2_years: Optional[bool] = None
    duration: Optional[str] = None
    location: Optional[str] = None
    island: Optional[str] = None
    hotel: Optional[str] = None
    confidence: float = 0.0

class IntentDetector:
    def detect(self, message: str, state: ConversationState) -> DetectedIntent:
        """Detecta intención en mensaje de texto libre"""
        pass
```

### Integración en `Supervisor`

**Modificaciones en `src/agents/supervisor.py`**:

1. **Llamar a `IntentDetector` en cada mensaje de texto libre**:
```python
def route_message(self, message: str, state: ConversationState) -> Response:
    # Detectar intención
    intent = self.intent_detector.detect(message, state)
    
    # Aplicar información detectada al estado
    self._apply_detected_intent(intent, state)
    
    # Decidir siguiente paso basado en estado actualizado
    return self._route_with_intent(message, state, intent)
```

2. **Método `_apply_detected_intent`**: Actualiza `ConversationState` con info detectada

3. **Método `_route_with_intent`**: Decide siguiente paso considerando:
   - ¿Estamos en paso del árbol que ya fue respondido? → Saltar
   - ¿Tenemos suficiente info para ir a paso específico? → Ir directo
   - ¿Falta info crítica? → Preguntar solo lo necesario

4. **Mensajes de confirmación**: Generar mensaje natural que resume lo detectado antes de continuar

### Persistencia en `ConversationState`

**Nuevos campos en `src/models/conversation_state.py`**:
```python
@dataclass
class ConversationState:
    # ... campos existentes ...
    
    # Información detectada de texto libre
    detected_language: Optional[str] = None
    detected_activity: Optional[str] = None
    detected_service_id: Optional[str] = None
    detected_is_certified: Optional[bool] = None
    detected_group_size: Optional[int] = None
    detected_group_allocation: Optional[Dict[str, int]] = None
    detected_last_dive_over_2_years: Optional[bool] = None
    detected_duration: Optional[str] = None
    detected_location: Optional[str] = None
    detected_island: Optional[str] = None
    detected_hotel: Optional[str] = None
```

---

## Plan de Ejecución

### Sprint 1: Fundamentos (Fases 1-3) ✅ COMPLETADO
- [x] Crear `IntentDetector` base con detección de idioma
- [x] Implementar detección de actividad principal
- [x] Implementar detección de certificación
- [x] Integrar en `Supervisor` con saltos básicos
- [x] Tests unitarios de detección (39 tests)
- [x] Tests de conversación end-to-end (21 tests)

**Ver**: `docs/SPRINT1_INTENT_DETECTION_SUMMARY.md`

### Sprint 2: Refinamiento de Carrito y Grupos ✅ COMPLETADO
- [x] Eliminación completa del flujo antiguo (no-carrito)
- [x] Detección de actividades específicas (minicurso, snorkel, PADI)
- [x] Salto inteligente de preguntas ya respondidas
- [x] Detección de número de personas mejorada
- [x] Detección de distribución de actividades (grupo mixto) mejorada
- [x] Detección de ubicación con botones y texto libre
- [x] Mensajes de confirmación personalizados para grupos mixtos
- [x] Tests específicos (ubicación, minicurso, grupos mixtos)

**Ver**: `docs/SPRINT2_CART_FLOW_REFINEMENT.md`

### Sprint 3: Contexto Avanzado (Fases 6-7) ✅ COMPLETADO
- [x] Detección de ubicación/isla/hotel mejorada
- [x] Pregunta de certificación cuando es ambigua
- [x] Pregunta de hotel específico según isla detectada
- [x] Resumen muestra isla específica (no genérico)
- [x] Mapeo automático hotel → isla
- [x] 28 hoteles con múltiples variantes y aliases
- [x] 12 islas con detección automática
- [x] Tests completos de flujo isla/hotel
- [ ] Detección de duración (un día vs multi-día) - pendiente
- [ ] Refinamiento de confianza y fallbacks - pendiente

**Ver**: `docs/FreeText/SPRINT3_LOCATION_HOTEL_DETECTION.md`

### Sprint 4: Refinamiento y Producción
- [ ] Logging y observabilidad de detecciones
- [ ] Métricas de precisión de detección
- [ ] Ajuste de umbrales de confianza
- [ ] Tests de regresión completos
- [ ] Validación con conversaciones reales
- [ ] Deploy a staging/producción

---

## Ejemplos de Flujo

### Ejemplo 1: Mensaje completo inicial
**Usuario**: "Hola somos dos personas que queremos hacer buceo y estamos certificados"

**Detección**:
- `language = "es"`
- `activity = "certified_diving"`
- `is_certified = True`
- `group_size = 2`
- `group_allocation = {"certified_diving": 2}`

**Flujo**:
1. Saltar `Step.LANGUAGE_SELECTION`
2. Saltar selección de actividad
3. Saltar pregunta de certificación
4. Mostrar mensaje: "¡Genial! Veo que son 2 buzos certificados. Para ofrecerles la mejor experiencia, necesito saber:"
5. Ir a `certified_last_dive` (pregunta de última inmersión)

---

### Ejemplo 2: Mensaje ambiguo
**Usuario**: "Hola quiero bucear"

**Detección**:
- `language = "es"`
- `activity = "diving"` (ambiguo: ¿certificado o minicurso?)
- `is_certified = None`

**Flujo**:
1. Saltar `Step.LANGUAGE_SELECTION`
2. Mostrar mensaje: "Perfecto, te ayudo con el buceo. Para continuar necesito saber:"
3. Mostrar pregunta con botones: "¿Eres buzo certificado?" (Sí / No)
4. Según respuesta → continuar árbol

---

### Ejemplo 3: Grupo mixto
**Usuario**: "Somos dos, yo quiero buceo y mi novia snorkel"

**Detección**:
- `language = "es"`
- `group_size = 2`
- `group_allocation = {"certified_diving": 1, "snorkel": 1}`
- `is_certified = None` (para el que quiere buceo)

**Flujo**:
1. Saltar `Step.LANGUAGE_SELECTION`
2. Mostrar mensaje: "Entiendo que quieren hacer actividades diferentes: 1 persona buceo, 1 persona snorkel."
3. Preguntar: "¿La persona que quiere buceo está certificada?" (Sí / No)
4. Según respuesta → pre-cargar cart en `Step.MIXED_ENTRY` con:
   - Item 1: Buceo certificado (qty 1) o Minicurso (qty 1)
   - Item 2: Snorkel (qty 1)
5. Continuar flujo mixto normal

---

### Ejemplo 4: Mitad de conversación
**Usuario** (ya en `Step.SUMMARY` de snorkel): "Mi amigo también quiere venir pero él quiere bucear"

**Detección**:
- `group_size = 2` (yo + amigo)
- `group_allocation = {"snorkel": 1, "certified_diving": 1}`
- `is_certified = None` (para el amigo)

**Flujo**:
1. Detectar que es caso de companion desde flujo single
2. Usar lógica existente de `_detect_companion_activity_intent`
3. Preguntar certificación del amigo
4. Ofrecer añadir al cart mixto

---

## Consideraciones Técnicas

### Performance
- Detección heurística primero (rápida, sin LLM)
- LLM solo si heurística no es concluyente (confianza < umbral)
- Cache de detecciones por mensaje para evitar re-procesamiento

### Confiabilidad
- Umbrales de confianza por dimensión
- Fallback a preguntas del árbol si confianza baja
- Logging de todas las detecciones para análisis posterior

### UX
- Mensajes de confirmación naturales (no robóticos)
- Nunca asumir sin confirmar si confianza < 80%
- Permitir corrección ("No, en realidad somos 3")

### Testing
- Tests unitarios de `IntentDetector` con casos edge
- Tests de integración de saltos de árbol
- Tests de conversación completa end-to-end
- Validación con conversaciones reales de WhatsApp

---

## Métricas de Éxito

1. **Tasa de salto**: % de conversaciones que saltan al menos 1 pregunta del árbol
2. **Precisión de detección**: % de detecciones correctas vs incorrectas (validado manualmente)
3. **Reducción de pasos**: Promedio de pasos ahorrados por conversación
4. **Satisfacción**: Feedback cualitativo de usuarios (menos repetitivo, más natural)

---

## Próximos Pasos

1. ✅ Crear este documento de diseño
2. ✅ Revisar y aprobar diseño con el equipo
3. ✅ Implementar Sprint 1 (Fases 1-3)
4. ✅ Implementar Sprint 2 (Refinamiento de carrito y grupos)
5. ✅ Validar con casos de prueba (60+ tests pasando)
6. 📋 Validar con conversaciones reales de WhatsApp
7. 📋 Implementar Sprint 3 (Contexto avanzado)
8. 📋 Implementar Sprint 4 (Refinamiento y producción)
9. 📋 Deploy a staging/producción
