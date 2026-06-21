# Plan — Tolerancia a errores tipográficos (3 capas)

> Última actualización: 2026-06-21.
> Branch: `feature/dev_alvaro`
> **Estado global: Capa 1 ✅ · Capa 2 ✅ · Capa 3 ⏳**

---

## Contexto

El bot tiene tres zonas distintas donde los errores tipográficos del usuario producen fallos silenciosos:

| Capa | Zona | Ejemplo real que falla | Impacto |
|------|------|----------------------|---------|
| 1 | Inputs estructurados (yes/no, cancelar, números) | "sii" → no reconoce "sí" | Alto — el usuario queda atascado |
| 2 | Detección de actividad en texto libre | "bucereo" → no detecta "buceo" | Medio — cae a RAG |
| 3 | Selección de menú sin botón | "snorlkel" → no coincide con botón | Medio — "no entendido" |

**Capa 1 es la más urgente**: ~23 comprobaciones `msg in ("back", "cancel", "cancelar")` y
2 funciones de yes/no en supervisor.py tienen tolerancia cero a typos.

**Capas 2 y 3 son parches** hasta que el orquestador LLM (Fase 2 del plan de orquestador)
entre en producción. Con el orquestador, el LLM maneja intención y typos de forma nativa.

---

## Capa 1 — Inputs estructurados ✅ COMPLETADA

### Qué cambia

- **Nuevo módulo:** `src/utils/fuzzy.py` — helper reutilizable con umbrales conservadores.
- **`src/flows/decision_tree.py`** — todos los `msg in ("back", "cancel", "cancelar")` →
  `is_back(msg)`. Plus yes/no inline y word-numbers.
- **`src/agents/supervisor.py`** — `_detect_binary_yes_no_answer` y
  `_detect_companion_certification_answer`.

### Algoritmo

`difflib.SequenceMatcher` (incluido en stdlib, sin dependencias nuevas):

- Strings ≤ 2 chars → **solo exact match** (evita falsos positivos en "si"/"no").
- Strings 3–4 chars → ratio ≥ **0.72** (cubre "sii"→"si", "bak"→"back", "doss"→"dos").
- Strings ≥ 5 chars → ratio ≥ **0.82** (cubre "cancellar"→"cancelar", "empezarr"→"empezar").

### Conjuntos canónicos

```python
_BACK    = {"back", "cancel", "cancelar", "volver", "atras", "atrás", "salir"}
_YES     = {"si", "sí", "yes", "sip", "yep", "yeah"}
_NO      = {"no", "nope", "nop"}
_AGREE   = {"si", "sí", "yes", "ok", "okey", "k", "vale", "start", "empezar",
             "claro", "venga", "dale", "vamos"}
_NONE_0  = {"0", "ninguno", "ninguna", "none", "no"}
```

### Funciones públicas

```python
is_back(msg)            → bool   # "cancellar", "bak", "volver"
is_affirmative(msg)     → bool   # "sii", "yess" — para preguntas sí/no estrictas
is_negative(msg)        → bool   # "nno", "nope"
is_agree(msg)           → bool   # ampliado: "ok", "vale", "sii", "dale"
is_none_selection(msg)  → bool   # "ninguno", "0", "none"
fuzzy_word_number(msg)  → int|None  # "doss"→2, "tre"→3, "cuatr"→4
```

### Archivos a tocar

| Archivo | Cambio |
|---------|--------|
| `src/utils/__init__.py` | Nuevo (vacío) |
| `src/utils/fuzzy.py` | Nuevo — toda la lógica |
| `src/flows/decision_tree.py` | Import + replace_all de 23 `msg in ("back",...)` + 5 casos adicionales |
| `src/agents/supervisor.py` | Import + actualizar 4 comprobaciones yes/no |

### Tests

- `tests/test_fuzzy.py` — 152 tests unitarios del helper (affirmative, negative, back, numbers, edge-cases). ✅
- Smoke en `tests/test_conversations.py` — "sii" en paso sí/no de refresher avanza. ✅
- Suite completa: **609 tests green** tras Capa 1.

### Ejemplos para probar en producción

```
"sii, somos cuatr personas"
→ "sii" → afirmativo ✓   "cuatr" → 4 personas ✓

"cancellar, quiero vovler al menu"
→ "cancellar" → back/cancelar ✓
```

---

## Capa 2 — Regex de actividades en IntentDetector ✅ COMPLETADA

### Qué cambió en `src/agents/intent_detector.py`

**`certified_diving_patterns`:**
```python
r'\bbuce\w{0,5}\b(?!\s+(bautismo|principiante|primera\s+vez|minicurso))'
# Cubre: buceo, bucear, buceando, bucereo (typo), bucea
r'\bbuse[ao]\w{0,2}\b'   # buseo (typo u/c swap)
r'\bsubmarinismo\b'       # sinónimo
```

**`minicourse_patterns`:**
```python
r'\bmini[\s\-]?curso\b'              # mini curso, mini-curso, minicurso
r'\bbauti[sz]\w{0,3}\b'             # bautismo, bautizo, bautismos, bautizos
r'\bnunca\s+(?:h[ae]\s+)?bucea\w*\b' # nunca ha/he buceado, nunca buceado
r'\bno\s+s[eé]\s+bucear\b'          # no sé bucear / no se bucear
```

**`snorkel_patterns`:**
```python
r'\be?snork\w{1,6}\b'    # snorkel, snorkeling, snorkle, esnorkel, esnorkeling
r'\be?snorqu\w{0,6}\b'   # snorquel, esnorquel, snorqueling, esnorqueling
r'\bcarete[ao]\w{0,3}\b' # careteo, caretear
```

**`_ACTIVITY_KW` + `_activity_key`** (split de grupo "3 de buceo y 2 de snorkel"):
- Añadidos: `buseo`, `esnorkel`, `mini curso`, `bautizo`, `submarinismo`.

### Tests

- `tests/test_intent_typo_tolerance.py` — 33 tests nuevos cubriendo typos y sinónimos. ✅
- Suite completa: **642 tests green** tras Capa 2.

### Ejemplos para probar en producción

```
"somos 2, queremos hacer esnorkel mañana"
→ activity = snorkel ✓  (esnorkel detectado)

"mi novia quiere un bautizo de buceo, nunca ha buceado"
→ activity = minicourse ✓  (bautizo + nunca ha buceado, minicourse gana sobre buceo)
```

### Nota

Parche de corto plazo. El orquestador LLM (Fase 2) resolverá esto de forma nativa.

---

## Capa 3 — Menú sin botón + umbral de confianza ⏳ PENDIENTE

### Problema A — `_match_text_to_button` (supervisor.py)

El word-overlap (≥ 0.5) falla con palabras sueltas mal escritas.
"snorlkel" no coincide con el botón "🤿 Snorkel".

### Solución A

Añadir fuzzy por palabra en el scoring:

```python
# Antes
score = len(user_words & button_words) / max(...)

# Después — si no hay coincidencia exacta, intentar fuzzy por palabra
for uw in user_words:
    for bw in button_words:
        if uw == bw or _ratio(uw, bw) >= 0.80:
            fuzzy_matches += 1
score = fuzzy_matches / max(...)
```

### Problema B — Confidence threshold en IntentDetector

`DetectedIntent.confidence` se calcula pero nunca se usa para enrutar.
Resultado: una detección con 0.1 de confianza se trata igual que 0.9.

### Solución B

Añadir un umbral en supervisor.py: si `confidence < 0.30`, antes de avanzar
pedir confirmación al usuario:

```
"¿Te refieres a [actividad detectada]? (Sí / No)"
```

### Archivos a tocar

| Archivo | Cambio |
|---------|--------|
| `src/agents/supervisor.py` | `_match_text_to_button` + confidence threshold |

### Nota

La Capa 3 es también un parche temporal. El orquestador con `answer_question` y
`confidence` en el JSON de respuesta reemplazará todo esto.

---

## Estado por fase

| Fase | Estado | Tests | Notas |
|------|--------|-------|-------|
| **Capa 1** — fuzzy navegación | ✅ Completada | 152 tests | `src/utils/fuzzy.py` · 609 suite green |
| **Capa 2** — regex actividades | ✅ Completada | +33 tests | `intent_detector.py` · 642 suite green |
| **Capa 3** — menú fuzzy + confidence | ⏳ Pendiente | — | `supervisor.py` · ver sección abajo |
| **Orquestador (Fase 2)** | ⏳ Pendiente (plan separado) | — | Reemplaza Capas 2 y 3 |

---

## Reglas de diseño

1. **Sin dependencias nuevas** — solo stdlib (`difflib`). Sin `thefuzz`, sin `Levenshtein`.
2. **Exact match siempre primero** — el fuzzy solo entra si el exact falla.
3. **Strings ≤ 2 chars: solo exact** — evita falsos positivos en "si"/"no"/"ok".
4. **Nombres propios protegidos** — sin spell-correction automática que pueda alterar
   "Rosario", "PADI", "Pao Pao". El fuzzy opera sobre comandos conocidos, no sobre contenido.
5. **Tests antes de merge** — cada cambio tiene test unitario. La suite completa debe
   seguir verde.
