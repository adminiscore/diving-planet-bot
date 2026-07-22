# Sprint 1: Detección Inteligente de Intención - Resumen de Implementación

**Fecha**: 17 de junio de 2026  
**Estado**: ✅ Completado

## Objetivo

Implementar detección automática de intención en texto libre para que el bot pueda entender mensajes complejos del usuario y **saltar fases del árbol de decisión** que ya fueron respondidas implícitamente.

## Ejemplo de Uso

**Antes** (sin detección de intención):
```
Usuario: "Hola somos dos personas que queremos hacer buceo y estamos certificados"
Bot: "¡Hola! ¿En qué idioma prefieres continuar?"
Usuario: "Español"
Bot: "¿Qué tipo de grupo eres?"
Usuario: "Buzos certificados"
Bot: "¿Cuándo fue tu última inmersión?"
```

**Ahora** (con detección de intención):
```
Usuario: "Hola somos dos personas que queremos hacer buceo y estamos certificados"
Bot: "¡Genial! Veo que son 2 buzos certificados. Para ofrecerles la mejor experiencia, necesito saber:

¿Cuándo fue tu última inmersión?"
```

El bot detectó automáticamente:
- ✅ Idioma: Español
- ✅ Actividad: Buceo certificado
- ✅ Certificación: Sí
- ✅ Número de personas: 2

Y saltó directamente a la pregunta de última inmersión.

---

## Componentes Implementados

### 1. `IntentDetector` (`src/agents/intent_detector.py`)

Componente principal que analiza mensajes de texto libre y detecta:

#### Dimensiones Detectadas:
- **Idioma**: Español o inglés (heurísticas basadas en palabras clave)
- **Actividad**: Buceo certificado, minicurso, snorkel, cursos PADI, especialidades
- **Certificación**: Si el usuario es buzo certificado o no
- **Tamaño de grupo**: Número de personas (ej: "somos dos", "venimos tres")
- **Distribución de actividades**: Grupos mixtos (ej: "yo buceo y mi amigo snorkel")
- **Última inmersión**: Hace cuánto tiempo (< 2 años o > 2 años)
- **Duración**: Un día vs multi-día
- **Ubicación**: Cartagena, isla específica, hotel
- **Isla**: Isla Grande, Isla Marina, etc.
- **Hotel**: Pao Pao, Cocoliso, San Pedro de Majagua, etc.

#### Técnica:
- **Heurísticas con regex**: Rápido, sin costo de LLM
- **Scoring de confianza**: Calcula confianza basada en campos detectados
- **Extensible**: Fácil añadir nuevos patrones o usar LLM como fallback

### 2. Campos en `ConversationState` (`src/flows/decision_tree.py`)

Se añadieron campos para almacenar información detectada:

```python
detected_language: str | None
detected_activity: str | None
detected_service_id: str | None
detected_is_certified: bool | None
detected_group_size: int | None
detected_group_allocation: dict | None
detected_last_dive_over_2_years: bool | None
detected_duration: str | None
detected_location: str | None
detected_island: str | None
detected_hotel: str | None
```

### 3. Integración en `Supervisor` (`src/agents/supervisor.py`)

El supervisor ahora:

1. **Detecta intención** en cada mensaje de texto libre (no en selecciones de menú)
2. **Aplica información detectada** al estado de la conversación
3. **Decide saltos de árbol** basándose en la información detectada:
   - Si detecta buzo certificado → salta a pregunta de última inmersión
   - Si detecta buceo sin certificación → pregunta si es certificado
   - Si detecta grupo mixto → entra al flujo de cart mixto
   - Si detecta minicurso → salta certificación (ya sabemos que no está certificado)

4. **Genera mensajes de confirmación** naturales antes de continuar

#### Funciones auxiliares añadidas:
- `_apply_detected_intent()`: Aplica información detectada al estado
- `_build_confirmation_message()`: Genera mensaje de confirmación natural
- `_should_skip_to_certified_flow()`: Decide si saltar a flujo de certificados
- `_should_ask_certification()`: Decide si preguntar certificación
- `_should_enter_mixed_flow()`: Decide si entrar a flujo mixto

---

## Tests Implementados

### Tests Unitarios (`tests/test_intent_detector.py`)

**39 tests** que cubren:
- ✅ Detección de idioma (español/inglés)
- ✅ Detección de actividades (buceo, snorkel, minicurso, PADI, especialidades)
- ✅ Detección de certificación
- ✅ Detección de tamaño de grupo
- ✅ Detección de grupos mixtos
- ✅ Detección de última inmersión
- ✅ Detección de duración
- ✅ Detección de ubicación/isla/hotel
- ✅ Escenarios completos
- ✅ Scoring de confianza

**Resultado**: ✅ 39/39 tests pasando

### Tests End-to-End (`tests/test_conversations.py`)

**21 tests** que cubren:
- ✅ Salto a última inmersión con buzos certificados (ES/EN)
- ✅ Pregunta de certificación cuando es ambiguo
- ✅ Detección de minicurso (skip certificación)
- ✅ Grupos mixtos entrando a cart flow
- ✅ Detección de tamaño de grupo
- ✅ Detección de ubicación
- ✅ Detección de última inmersión
- ✅ Detección continua durante la conversación
- ✅ Detección de cursos PADI y especialidades
- ✅ Detección de hotel
- ✅ Detección de duración
- ✅ No se activa en inputs de menú (dígitos)
- ✅ No se activa en inputs muy cortos

**Resultado**: ✅ 21/21 tests pasando

---

## Casos de Uso Cubiertos

### 1. Buceo Certificado - Grupo
```
"Hola somos dos personas que queremos hacer buceo y estamos certificados"
→ Detecta: ES, 2 personas, buceo certificado, certificados
→ Salta a: Pregunta de última inmersión
```

### 2. Buceo Certificado - Individual
```
"Hello I am a certified diver and want to dive"
→ Detecta: EN, buceo certificado, certificado
→ Salta a: Pregunta de última inmersión
```

### 3. Buceo Ambiguo
```
"Hola quiero bucear"
→ Detecta: ES, buceo (sin certificación clara)
→ Pregunta: "¿Eres buzo certificado?"
```

### 4. Minicurso
```
"Hola quiero hacer el minicurso de buceo, es mi primera vez"
→ Detecta: ES, minicurso, no certificado
→ Salta certificación (ya sabemos que es principiante)
```

### 5. Grupo Mixto
```
"Somos dos, yo quiero buceo certificado y mi novia snorkel"
→ Detecta: ES, 2 personas, buceo certificado + snorkel, certificado
→ Salta a: Pregunta de última inmersión (para el certificado)
```

### 6. Grupo Mixto - Minicurso + Snorkel
```
"Hola somos dos, yo haría el minicurso y mi amigo snorkel"
→ Detecta: ES, 2 personas, minicurso + snorkel
→ Pre-carga cart con ambas actividades
→ Va directo a: Revisión de cart
```

### 7. Con Ubicación
```
"Quiero hacer buceo, estoy en Cartagena y soy certificado"
→ Detecta: ES, buceo, Cartagena, certificado
→ Guarda ubicación y salta a última inmersión
```

### 8. Curso PADI
```
"Hola quiero hacer el curso PADI Open Water"
→ Detecta: ES, curso PADI, Open Water
→ Entra al flujo de cursos PADI
```

### 9. Especialidad
```
"Hola quiero hacer el curso de nitrox"
→ Detecta: ES, especialidad, nitrox
→ Entra al flujo de especialidades
```

### 10. Con Hotel
```
"Hola estoy en el hotel Pao Pao y quiero hacer snorkel"
→ Detecta: ES, hotel Pao Pao, snorkel
→ Guarda hotel y continúa con snorkel
```

---

## Beneficios

### Para el Usuario
- ✅ **Conversaciones más naturales**: Puede escribir todo en un mensaje
- ✅ **Menos repetición**: No tiene que responder preguntas que ya contestó
- ✅ **Más rápido**: Menos pasos para llegar a la información que necesita
- ✅ **Más inteligente**: El bot "entiende" mensajes complejos

### Para el Negocio
- ✅ **Mejor experiencia**: Usuarios más satisfechos
- ✅ **Mayor conversión**: Menos fricción en el proceso de reserva
- ✅ **Menos abandonos**: Flujo más rápido y natural
- ✅ **Datos más ricos**: Captura más información desde el primer mensaje

### Técnico
- ✅ **Sin costo de LLM**: Usa heurísticas rápidas
- ✅ **Extensible**: Fácil añadir nuevos patrones
- ✅ **Bien testeado**: 60 tests cubriendo casos principales
- ✅ **Mantenible**: Código limpio y documentado

---

## Próximos Pasos (Sprint 2-4)

Según el documento de diseño `docs/free-text-intent-detection.md`:

### Sprint 2: Grupos y Contexto Avanzado
- [ ] Mejorar detección de distribución de actividades en grupos mixtos
- [ ] Detección de número de personas con mayor precisión
- [ ] Pre-carga completa de cart en flujo mixto
- [ ] Mensajes de confirmación más contextuales

### Sprint 3: Contexto Avanzado
- [ ] Detección de duración (un día vs multi-día) más robusta
- [ ] Detección de ubicación/isla/hotel más precisa
- [ ] Refinamiento de confianza y fallbacks
- [ ] Optimización de prompts (si se añade LLM)

### Sprint 4: Refinamiento y Producción
- [ ] Logging y observabilidad de detecciones
- [ ] Métricas de precisión de detección
- [ ] Ajuste de umbrales de confianza
- [ ] Validación con conversaciones reales de producción
- [ ] Deploy a staging/producción

---

## Métricas de Éxito (Para Medir)

1. **Tasa de salto**: % de conversaciones que saltan al menos 1 pregunta del árbol
2. **Precisión de detección**: % de detecciones correctas vs incorrectas
3. **Reducción de pasos**: Promedio de pasos ahorrados por conversación
4. **Satisfacción**: Feedback cualitativo de usuarios

---

## Archivos Modificados/Creados

### Creados
- ✅ `src/agents/intent_detector.py` (nuevo componente)
- ✅ `tests/test_intent_detector.py` (39 tests unitarios)
- ✅ `docs/free-text-intent-detection.md` (documento de diseño)
- ✅ `docs/SPRINT1_INTENT_DETECTION_SUMMARY.md` (este archivo)

### Modificados
- ✅ `src/flows/decision_tree.py` (campos detectados en ConversationState)
- ✅ `src/agents/supervisor.py` (integración de IntentDetector)
- ✅ `tests/test_conversations.py` (21 tests end-to-end añadidos)

---

## Conclusión

✅ **Sprint 1 completado exitosamente**

El bot ahora puede:
- Detectar automáticamente idioma, actividad, certificación, grupo, ubicación y más
- Saltar preguntas del árbol que el usuario ya respondió implícitamente
- Ofrecer una experiencia más natural y conversacional
- Reducir fricción en el proceso de reserva

**Todos los tests pasan** (60/60) y el sistema está listo para uso en desarrollo/staging.

El siguiente paso es validar con conversaciones reales y ajustar patrones según sea necesario antes de pasar a los Sprints 2-4.
