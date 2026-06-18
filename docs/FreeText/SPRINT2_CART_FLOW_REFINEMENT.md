# Sprint 2: Refinamiento del Flujo de Carrito - Resumen de Implementación

**Fecha**: 18 de junio de 2026  
**Estado**: ✅ Completado

## Objetivo

Refinar el flujo de detección de intención y routing para que el bot:
1. **Elimine completamente el flujo antiguo** de tours que no usa carrito
2. **Priorice el carrito** para todas las reservas (buceo certificado, minicurso, snorkel, PADI, etc.)
3. **Detecte actividades específicas** y salte directo a los pasos relevantes
4. **Detecte grupos mixtos** correctamente y muestre mensajes personalizados
5. **Mejore la detección de ubicación** con botones y texto libre

---

## Cambios Implementados

### 1. Eliminación del Flujo Antiguo ✅

**Problema**: Existían dos flujos paralelos para reservas:
- Flujo antiguo: `TOURS_LOCATION` → `GROUP_TYPE` → `TOURS_EXPERIENCE` → etc.
- Flujo nuevo (carrito): `MIXED_ENTRY` → `MIXED_ADD_ACTIVITY` → etc.

**Solución**: Eliminado completamente el flujo antiguo.

**Archivos modificados**:
- `src/flows/decision_tree.py`:
  - ❌ Eliminados steps: `TOURS_LOCATION`, `GROUP_TYPE`, `TOURS_EXPERIENCE`, `TOURS_CERTIFIED`, `CERTIFIED_4_DIVES_VARIANT`, `CERTIFIED_LAST_DIVE` (antiguo), `CERTIFIED_EXPERIENCE`, `REFRESHER_INTEREST`, `TOURS_BEGINNER`, `BEGINNER_AGE`
  - ❌ Eliminados mensajes asociados
  - ❌ Eliminados quick_replies asociados
  - ❌ Eliminados handlers: `_handle_tours_location`, `_handle_group_type`, `_handle_tours_experience`, `_handle_tours_certified`, `_handle_certified_4_dives_variant`, `_handle_certified_last_dive` (antiguo), `_handle_certified_experience`, `_handle_refresher_interest`, `_handle_tours_beginner`, `_handle_beginner_age`
  
- `src/agents/supervisor.py`:
  - ❌ Eliminadas referencias a steps antiguos en back navigation
  - ❌ Eliminadas referencias en `_STEPS_THAT_DONT_NEED_PII_DETECTION`
  - ❌ Eliminada referencia a `GROUP_TYPE` en `_maybe_handle_mixed_group_from_menu`

**Resultado**: Ahora **todo** va por el carrito (`MIXED_*` steps).

---

### 2. Detección de Actividades Específicas ✅

**Problema**: Cuando el usuario decía "Hola quiero hacer el minicurso de buceo", el bot:
1. Preguntaba ubicación ✅
2. Preguntaba "¿Qué actividad quieres añadir?" ❌ (ya sabemos que es minicurso!)
3. Preguntaba cantidad ✅

**Solución**: Saltar la pregunta de actividad cuando ya está detectada.

**Cambios en `src/agents/supervisor.py`**:
```python
# Detectar actividades específicas (minicurso, PADI, snorkel, etc.) → ir directo al carrito
elif intent.activity in ("minicourse", "snorkel", "padi_open_water", "padi_advanced", 
                          "padi_rescue", "padi_divemaster", "padi_specialty"):
    # Mapear actividad a tipo de carrito
    if intent.activity == "minicourse":
        state.mixed_pending_qty_type = "beginner"
    elif intent.activity == "snorkel":
        state.mixed_pending_qty_type = "snorkel"
    # ...
    
    # Si no tenemos ubicación, preguntar primero
    if not state.detected_location and not state.location:
        state.step = Step.MIXED_LOCATION
        # Preguntar ubicación
    else:
        # Si tenemos ubicación, ir directo a preguntar cantidad
        state.step = Step.MIXED_ADD_QTY
```

**Cambios en `src/flows/decision_tree.py`**:
```python
def _handle_mixed_location(self, state: ConversationState, message: str) -> str:
    # ...
    if choice == 1 or "cartagena" in msg or "ctg" in msg:
        state.location = "cartagena"
        # Si ya tenemos una actividad detectada, saltar directo a esa actividad
        if state.mixed_pending_qty_type == "cert":
            # Ir a pregunta de plan de buceo certificado
        elif state.mixed_pending_qty_type in ("beginner", "snorkel", "course", "companion"):
            # Ir directo a preguntar cantidad (SALTA pregunta de actividad)
            state.step = Step.MIXED_ADD_QTY
```

**Resultado**: 
- Usuario: "Hola quiero hacer el minicurso de buceo, es mi primera vez"
- Bot: "¡Perfecto! El minicurso..." → Pregunta ubicación
- Usuario: "Cartagena"
- Bot: "¿Para cuántas personas?" (✅ SALTA pregunta de actividad)

---

### 3. Detección de Grupos Mixtos Mejorada ✅

**Problema**: Cuando el usuario decía "Somos dos, yo quiero buceo certificado y mi novia snorkel", el bot:
- Detectaba solo buceo certificado (ignoraba snorkel)
- Decía "Veo que son 2 buzos certificados" ❌ (no todos son buzos!)

**Solución**: Mejorar detección de `group_allocation` y mensajes personalizados.

**Cambios en `src/agents/intent_detector.py`**:
```python
mixed_group_patterns = [
    # "yo quiero buceo certificado y mi novia snorkel" - captura hasta 3 palabras
    (r'\byo\s+(?:quiero|hago|haría|haré)\s+(?:el\s+)?(\w+(?:\s+\w+){0,2}?)\s+y\s+(?:mi\s+)?(?:novia|novio|amigo|amiga|pareja|compañero|compañera|él|ella)\s+(?:quiere|hace|haría|hará)?\s*(?:el\s+)?(\w+(?:\s+\w+){0,2})', 'es'),
    # ...
]

# Clasificación mejorada
for activity_text in [activity1, activity2]:
    # Primero verificar minicurso (tiene prioridad)
    if any(kw in activity_text for kw in ['minicurso', 'bautismo', 'discover', 'principiante']):
        allocation['minicourse'] = allocation.get('minicourse', 0) + 1
    # Luego snorkel
    elif any(kw in activity_text for kw in ['snorkel', 'careteo']):
        allocation['snorkel'] = allocation.get('snorkel', 0) + 1
    # Finalmente buceo (certificado o genérico)
    elif any(kw in activity_text for kw in ['buceo', 'dive', 'diving', 'certificado', 'certified']):
        allocation['certified_diving'] = allocation.get('certified_diving', 0) + 1
```

**Cambios en `src/agents/supervisor.py`**:

1. **Prioridad de evaluación**: Grupo mixto se evalúa PRIMERO
```python
# PRIMERO: Verificar si es grupo mixto (tiene prioridad sobre flujos individuales)
if _should_enter_mixed_flow(intent, state):
    # Ir al carrito
    
# DESPUÉS: Verificar buceo certificado individual
elif _should_skip_to_certified_flow(intent, state):
    # Ir a flujo de certificados
```

2. **Mensaje personalizado**:
```python
def _build_confirmation_message(intent, state: ConversationState) -> str | None:
    # PRIMERO: Verificar si es grupo mixto (tiene prioridad)
    if intent.group_allocation and len(intent.group_allocation) > 1:
        # Construir descripción de actividades
        activities_es = []
        total_people = 0
        for activity, qty in intent.group_allocation.items():
            total_people += qty
            if activity == "certified_diving":
                activities_es.append(f"{qty} para buceo certificado")
            elif activity == "snorkel":
                activities_es.append(f"{qty} para snorkel")
            # ...
        
        return f"¡Bienvenidos! Veo que son {total_people} personas: {' y '.join(activities_es)}."
```

**Resultado**:
- Usuario: "Somos dos, yo quiero buceo certificado y mi novia snorkel"
- Bot: "¡Bienvenidos! Veo que son 2 personas: 1 para buceo certificado y 1 para snorkel." ✅
- Bot: "¡Genial! Vamos a armar tu reserva paso a paso. 🛒..."

---

### 4. Detección de Ubicación Mejorada ✅

**Problema**: La pregunta de ubicación no tenía botones y no detectaba texto libre.

**Solución**: Agregar botones y detección de texto libre.

**Cambios en `src/flows/decision_tree.py`**:

1. **Quick replies con botones**:
```python
"tours_location": {
    "es": [
        {"title": "🚤 Salgo desde Cartagena", "value": "1"},
        {"title": "🏝️ Ya estoy en las islas", "value": "2"},
        {"title": "↩️ Volver", "value": "back"},
    ],
    "en": [
        {"title": "🚤 Departing from Cartagena", "value": "1"},
        {"title": "🏝️ Already on the islands", "value": "2"},
        {"title": "↩️ Back", "value": "back"},
    ],
},
```

2. **Detección de texto libre**:
```python
def _handle_mixed_location(self, state: ConversationState, message: str) -> str:
    # Detectar texto libre: Cartagena
    if choice == 1 or "cartagena" in msg or "ctg" in msg:
        state.location = "cartagena"
        # ...
    
    # Detectar texto libre: Islas del Rosario
    if choice == 2 or "isla" in msg or "rosario" in msg:
        state.location = "island"
        # ...
```

3. **Routing en supervisor para steps críticos**:
```python
# Si estamos en steps críticos y el clasificador devuelve "RAG", 
# enviar al decision_tree en lugar del RAG
critical_steps = [Step.MIXED_LOCATION, Step.MIXED_ADD_QTY, ...]
if state.step in critical_steps and intent == "RAG":
    # Enviar al decision_tree para que detecte texto libre
    response = decision_tree.process_message(state, message)
```

**Resultado**:
- Usuario: "Cartagena" (texto libre)
- Bot: Detecta ubicación y continúa ✅

---

### 5. Mensajes de Confirmación Optimizados ✅

**Problema**: Mensajes redundantes o incorrectos.

**Solución**: Eliminar mensajes innecesarios y personalizar según contexto.

**Cambios**:
- ❌ Eliminado: "Perfecto, te ayudo con el buceo. Para continuar necesito saber:" (cuando va al carrito sin certificación clara)
- ✅ Mejorado: "¡Bienvenidos! Veo que son X personas: Y para buceo certificado y Z para snorkel." (grupos mixtos)
- ✅ Mantenido: "¡Genial! Veo que son 2 buzos certificados..." (grupos homogéneos certificados)
- ✅ Mantenido: "¡Perfecto! El minicurso de buceo es ideal para principiantes..." (minicurso)

---

## Tests Creados

### 1. `test_location_detection.py` ✅
Prueba detección de ubicación con texto libre:
- ✅ "Cartagena" → `location = "cartagena"`
- ✅ "Ya estoy en las islas del rosario" → `location = "island"`
- ✅ "Estoy en las islas" → `location = "island"`

### 2. `test_minicurso_flow.py` ✅
Prueba flujo completo de minicurso:
- ✅ Detecta minicurso
- ✅ Pregunta ubicación
- ✅ SALTA pregunta de actividad
- ✅ Pregunta cantidad directamente

### 3. `test_mixed_group.py` ✅
Prueba detección de grupos mixtos:
- ✅ Detecta `group_allocation: {'certified_diving': 1, 'snorkel': 1}`
- ✅ Muestra mensaje personalizado
- ✅ Va al carrito

### 4. `test_intent_manual.py` ✅
Script manual para probar todos los casos:
- ✅ Ejemplo 1: Buzos certificados
- ✅ Ejemplo 2: Buzo certificado (inglés)
- ✅ Ejemplo 3: Buceo ambiguo
- ✅ Ejemplo 4: Minicurso
- ✅ Ejemplo 5: Grupo mixto
- ✅ Ejemplo 6: Con ubicación

**Resultado**: ✅ Todos los tests pasan

---

## Beneficios

### Para el Usuario
- ✅ **Menos preguntas repetitivas**: No pregunta actividad si ya la detectó
- ✅ **Más natural**: Puede escribir "Cartagena" en lugar de seleccionar botón
- ✅ **Mensajes personalizados**: "Veo que son 2 personas: 1 para buceo y 1 para snorkel"
- ✅ **Más rápido**: Menos pasos para completar reserva

### Para el Negocio
- ✅ **Mayor conversión**: Flujo más fluido
- ✅ **Mejor experiencia**: Usuarios más satisfechos
- ✅ **Menos abandonos**: Proceso más eficiente

### Técnico
- ✅ **Código más limpio**: Eliminado flujo antiguo duplicado
- ✅ **Mejor mantenibilidad**: Un solo flujo (carrito)
- ✅ **Bien testeado**: Tests específicos para cada caso

---

## Archivos Modificados/Creados

### Modificados
- ✅ `src/flows/decision_tree.py`
  - Eliminados steps, mensajes, quick_replies y handlers del flujo antiguo
  - Agregado mensaje `mixed_cert_last_dive`
  - Agregados quick_replies para `tours_location`
  - Mejorado `_handle_mixed_location` para detectar texto libre
  - Mejorado salto de actividad cuando ya está detectada

- ✅ `src/agents/supervisor.py`
  - Eliminadas referencias al flujo antiguo
  - Agregada lógica para actividades específicas (minicurso, snorkel, PADI)
  - Mejorada prioridad de evaluación (grupo mixto primero)
  - Mejorados mensajes de confirmación
  - Agregado routing especial para steps críticos

- ✅ `src/agents/intent_detector.py`
  - Mejorados patrones para capturar múltiples palabras ("buceo certificado")
  - Mejorada clasificación de actividades (prioridad correcta)

### Creados
- ✅ `test_location_detection.py`
- ✅ `test_minicurso_flow.py`
- ✅ `test_mixed_group.py`
- ✅ `test_intent_manual.py` (ya existía, actualizado)
- ✅ `docs/SPRINT2_CART_FLOW_REFINEMENT.md` (este archivo)

---

## Estado Actual

### ✅ Completado
- [x] Eliminación completa del flujo antiguo
- [x] Detección de actividades específicas con salto inteligente
- [x] Detección de grupos mixtos mejorada
- [x] Mensajes personalizados para grupos mixtos
- [x] Detección de ubicación con botones y texto libre
- [x] Routing especial para steps críticos
- [x] Tests para todos los casos nuevos

### 📋 Pendiente (Sprints futuros)
- [ ] Mejorar detección de cursos PADI específicos
- [ ] Pre-carga de carrito para grupos mixtos (actualmente solo muestra mensaje)
- [ ] Detección de duración más robusta (un día vs multi-día)
- [ ] Detección de hotel más precisa
- [ ] Logging y métricas de detección
- [ ] Validación con conversaciones reales de producción

---

## Próximos Pasos

1. ✅ Validar con pruebas manuales en desarrollo
2. ✅ Ejecutar todos los tests: `python -m pytest tests/ -v`
3. 📋 Validar con conversaciones reales de WhatsApp
4. 📋 Ajustar patrones según feedback
5. 📋 Medir métricas (tasa de salto, precisión)
6. 📋 Deploy a staging
7. 📋 Deploy a producción

---

## Conclusión

✅ **Sprint 2 completado exitosamente**

El bot ahora:
- Usa **exclusivamente el flujo de carrito** para todas las reservas
- **Detecta actividades específicas** y salta pasos innecesarios
- **Detecta grupos mixtos** correctamente con mensajes personalizados
- **Acepta texto libre** para ubicación además de botones
- Ofrece una **experiencia más natural y eficiente**

**Todos los tests pasan** y el sistema está listo para validación con usuarios reales.
