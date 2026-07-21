# Plan: extracción semántica por LLM (Opción 2 de robustness-strategy-options.md)

Estado global: **no empezada**. Ver `progress-log.md` para el estado exacto y
sesión-a-sesión.

Decidido por: owner + Álvaro + Gonzalo, 2026-07-21, tras leer
`docs/robustness-strategy-options.md`. Objetivo textual del owner: "ser competitivos y
sólidos, el cliente no puede encontrar tantos bugs".

Este documento es la guía persistente del proyecto. Está pensado para sobrevivir a
múltiples sesiones/agentes distintos trabajando en momentos distintos — cada uno debe
poder llegar aquí sin contexto previo, entender exactamente qué hacer, y dejarlo listo
para el siguiente. Lee `README.md` primero si no lo has hecho.

---

## 1. Por qué esto y no otra cosa

Contexto completo en `docs/robustness-strategy-options.md`. Resumen de la causa raíz:
`intent_detector.py`/`supervisor.py`/`decision_tree.py` extraen información del mensaje
(¿está certificado? ¿cuántos son? ¿desde dónde? ¿cambió de plan?) mediante **regex
especializadas, una familia por caso**. Cada bug real encontrado en vivo (y llevamos
docenas en el historial de versiones — ver `docs/HISTORY.md`) es la misma forma:
*alguien dijo algo de una manera que el regex no anticipó*. Los 2 bugs de la sesión de
hoy (`v0.20.31`) son el ejemplo perfecto: "not certfied" (typo) y "vucea" (typo b/v de
"bucea") — cada uno arreglado con una línea de regex nueva, cada uno encontrado
manualmente, cada uno con el mismo patrón de fondo: el enfoque regex-por-caso tiene un
techo estructural.

Ojo con la ambición: esto **no** es "tirar todo el regex y meter un LLM que lo haga
todo". Álvaro ya lo planteó así en `docs/project-history/estado-pendientes.md` (punto
#10): la extracción LLM debe ser **una red de seguridad que rellena huecos que el
regex deja vacíos**, no un reemplazo de golpe. Razones:

- El regex actual funciona MUY bien para el caso común (miles de tests lo confirman).
- El LLM orquestador que ya existe (`src/agents/orchestrator.py`) es conocidamente
  **no-determinista** — mismo mensaje, clasificación distinta entre ejecuciones. Si
  reemplazamos el regex determinista por LLM sin red de seguridad, cambiamos "bugs
  reproducibles y fáciles de testear" por "bugs intermitentes", que son peores para un
  negocio real (impredecibles, difíciles de reproducir en test, difíciles de explicar
  al owner).
- Un reemplazo de golpe arriesga una regresión masiva en un flujo que ya está bien
  probado (suite de ~1700 tests).

## 2. Principios de diseño (no negociables)

1. **Strangler fig, no big-bang.** Migrar dominio por dominio (certificación, grupo,
   ubicación, cambios de plan…), nunca "reescribir intent_detector.py entero".
2. **Regex sigue siendo el camino rápido y primario.** El LLM solo entra cuando el
   regex deja un campo relevante sin resolver (`None`) — o, durante la fase de
   evaluación, en modo *shadow* (corre en paralelo, no decide nada, solo se compara).
3. **Nunca sin red de seguridad.** Cada integración de LLM tiene un fallback
   determinista si la llamada falla, tarda demasiado, o devuelve algo fuera de schema.
4. **Salida estructurada, temperatura 0.** Nunca texto libre parseado a mano — usar
   structured output / function calling con un JSON schema explícito (mismo patrón que
   ya usa `orchestrator.py` para sus tools).
5. **Eval set explícito antes de cualquier cutover.** Ningún campo pasa a usar LLM como
   fuente de verdad sin que su exactitud esté medida contra un dataset etiquetado (ver
   §5) — mismo rigor que se usó para calibrar `RAG_MIN_SCORE` en
   `docs/rag-threshold-calibration.md`.
6. **TDD + verificación en vivo sigue siendo obligatorio**, sin excepciones, para cada
   cambio de comportamiento — es la disciplina que ya usa todo el repo (ver
   `docs/project-history/session-handoff.md`).
7. **Kill switch por fase.** Cada dominio migrado debe poder revertirse a "solo regex"
   con un flag, sin deploy de emergencia con cambio de código.
8. **Este documento se mantiene vivo.** Cualquier sesión que trabaje aquí actualiza
   `progress-log.md` antes de terminar — ver README.md.

## 3. Arquitectura objetivo

### 3.1 Dónde vive la extracción hoy

`src/agents/intent_detector.py` → clase `IntentDetector`, método `detect(message,
state) -> DetectedIntent`. `DetectedIntent` es un dataclass con campos sueltos:
`activity`, `is_certified`, `group_size`, `group_allocation`, `ages`, `location`,
`island`, `hotel`, `is_colombian`, `cert_dives`, `cert_days`, `language`,
`detected_fields` (lista de qué campos se resolvieron), `confidence`. Es la única
entrada — `supervisor.py` la llama y actúa sobre el resultado
(`_route_detected_intent`, `_should_ask_certification`, `_should_enter_mixed_flow`,
etc.).

Esto es una ventaja arquitectónica clave para la migración: **ya existe un contrato de
salida único y bien tipado** (`DetectedIntent`). No hace falta inventar un schema nuevo
desde cero — el LLM debe rellenar el MISMO dataclass, así que todo lo que consume
`DetectedIntent` aguas abajo no se entera del cambio.

### 3.2 Diseño de la capa LLM (gap-filler, no reemplazo)

```
mensaje del cliente
        │
        ▼
IntentDetector.detect()  (regex, determinista, igual que hoy)
        │
        ▼
DetectedIntent parcial (algunos campos en None)
        │
        ├── ¿hay campos relevantes en None Y el mensaje tiene señal
        │   suficiente (heurística barata, ver 3.3)?
        │                       │
        │                  sí   │   no
        │                       │
        ▼                       ▼
LLMExtractor.fill_gaps()   devolver tal cual
(solo rellena los None,
 NUNCA sobreescribe un
 campo que el regex ya
 resolvió)
        │
        ▼
DetectedIntent completo (regex + LLM donde hiciera falta)
```

Puntos clave:

- **El LLM nunca pisa un campo que el regex ya resolvió.** Si en el futuro un dominio
  demuestra (vía eval set, con datos) que el LLM es más fiable que el regex incluso
  cuando el regex "cree" haber resuelto algo, eso es una decisión de cutover explícita
  y documentada por campo (§4, Fase 2+), no un comportamiento por defecto.
- **`fill_gaps()` es una función pura de (mensaje, historial reciente, campos ya
  resueltos) → parche de campos nuevos**, igual de testeable que cualquier otra pieza
  del pipeline (se puede mockear la llamada LLM en tests, igual que ya se hace con
  `rag_answer`/`classify_menu_intent`/`orchestrator.orchestrate` en `test_conversations.py`).
- Reutiliza la infraestructura de tool-calling que ya existe en `orchestrator.py` (schema
  JSON, cliente OpenAI, patrón de parseo de respuesta) — no hace falta un cliente nuevo.

### 3.3 Cuándo se invoca (control de coste/latencia)

Llamar al LLM en cada mensaje sería caro y añadiría latencia siempre, incluso cuando el
regex ya lo resolvió todo bien (el caso común, la mayoría de los mensajes). Regla de
activación:

- **Fase de evaluación (shadow mode, ver §4 Fase 0)**: se llama SIEMPRE, en paralelo,
  pero el resultado nunca decide nada — solo se loguea para medir acuerdo/desacuerdo
  contra el regex y construir el eval set inicial con casos reales.
- **Fase de producción (tras cutover de un dominio)**: se llama solo si, tras el regex,
  queda al menos un campo relevante para el paso actual del árbol sin resolver Y el
  mensaje tiene señal suficiente para no ser una pregunta genérica ya destinada a RAG
  (reusar `_message_looks_like_question`/`_looks_like_info_question` ya existentes en
  `supervisor.py` como guardas — si ya se sabe que es una pregunta de info, no tiene
  sentido gastar una llamada extra en extracción).

### 3.4 Fallback y manejo de errores

- Timeout o error de la llamada LLM → devolver `DetectedIntent` tal cual (solo regex),
  loguear el fallo. El bot sigue funcionando exactamente como hoy, nunca peor.
- Respuesta fuera de schema / campo con tipo inesperado → descartar ese campo
  específico (no todo el resultado), loguear.
- Nunca bloquear la respuesta al cliente esperando reintentos de la extracción — un
  fallo aquí degrada a "como hoy", no debe convertirse en un nuevo punto de fallo.

## 4. Fases

Checklist de estado — actualizar aquí Y en el bloque correspondiente de
`progress-log.md` cuando cambie:

- [✅] **Fase 0 — Fundaciones** (sin cambio de comportamiento) — completa, 100.0% de acuerdo con LLM real (tras corregir un caso mal etiquetado), ver `progress-log.md`
- [✅] **Fase 1 — Dominio certificación** (primer vertical slice) — cutover implementado detrás de `settings.llm_extraction_cutover_certification` (default `False`), verificado en vivo con LLM real, ver `progress-log.md`
- [ ] **Fase 2 — Dominio grupo/cantidad/edades**
- [ ] **Fase 3 — Dominio ubicación/actividad/cambios de plan**
- [ ] **Fase 4 — Integración con acciones de carrito (orchestrator)**
- [ ] **Fase 5 — Limpieza y consolidación**

### Fase 0 — Fundaciones

Objetivo: tener la infraestructura de shadow-mode + eval-set funcionando, **sin tocar
el comportamiento del bot en producción**. Es la fase de "medir antes de cortar".

Pasos:

1. ✅ **Definir el schema de extracción** — se reutiliza `DetectedIntent` tal cual
   (`src/agents/intent_detector.py`) como contrato de salida; `EXTRACTABLE_FIELDS` en
   `src/agents/llm_extractor.py` es el subconjunto de campos que el LLM puede rellenar
   (excluye `language`, `service_id`, `confidence`, `detected_fields` — derivados/meta,
   no extraídos directamente del mensaje).
2. ✅ **Eval-set inicial construido**: `docs/robustness/eval-set.json`, 50 casos —
   42 semillas derivadas de `tests/test_intent_detector.py` (regex como ground truth,
   incluidos los 2 bugs reales de v0.20.31 marcados con su fuente) + 8 adversariales
   nuevos (negación con contracción EN, doble negación ES, edad+actividad de un
   tercero, certificación implícita por nombre de curso PADI, mensaje elíptico sin
   verbo de bucear, code-switching ES/EN, typo de letra duplicada, abreviatura de chat
   "ppl"). Formato exacto en §5.
3. ✅ **`LLMExtractor.fill_gaps()` construido** en `src/agents/llm_extractor.py` —
   función aislada, mockeable (mismo patrón de fake-client que
   `tests/test_orchestrator.py`), con su propio test file
   (`tests/test_llm_extractor.py`, 14 tests) validando: relleno correcto de huecos,
   que NUNCA sobreescribe un campo que el regex ya resolvió (ni siquiera si el LLM
   "opina" distinto), manejo de `is_certified=False`/`last_dive_over_2_years=False`/
   `is_colombian=False` como valores resueltos (no "missing" solo por ser falsy — bug
   real cazado por el propio test antes de escribir la implementación correcta), y
   fallback a `{}` en cualquier error/timeout/JSON malformado. Aún NO integrada en
   `supervisor.py`/`intent_detector.py` como fuente de verdad — solo shadow (paso 4).
4. ✅ **Shadow-mode harness construido**: `settings.llm_extraction_shadow_mode`
   (`src/config.py`, default `False`) + `_maybe_log_llm_extraction_shadow()` en
   `supervisor.py`, enganchado justo después de `intent_detector.detect()` dentro de
   `_dispatch_conversation_agent` (el entry-point principal de comprensión de texto
   libre). Con el flag apagado (default en todos los entornos), NUNCA llama al LLM —
   verificado con test dedicado (`tests/test_llm_extraction_shadow_mode.py`, 4 tests)
   que usa un mock que lanza `AssertionError` si se le llama, para probar la propiedad
   de seguridad de forma dura, no solo observacional. Loguea con el tag grepable
   `[EXTRACT][SHADOW] msg=... gaps_before=[...] llm_patch={...}`. Cualquier excepción
   en la sonda se traga (no puede romper un turno real).
5. ✅ **Corrido con LLM real** (`ENV_FILE=.env.dev python -m scripts.run_extraction_eval`,
   2026-07-21): primera pasada dio 99/100 (99.0%), con 1 desacuerdo en un caso
   adversarial. Al investigarlo (ver `progress-log.md`) resultó ser un **error de
   autoría del eval-set** (un "expected" escrito a mano sin correr antes el detector
   real), no un fallo del LLM ni una ambigüedad real de schema. Corregido el caso →
   **100/100 (100.0%) de acuerdo, 0 desacuerdos, 0 huecos** en la segunda pasada.
   Resultado muy por encima del baseline solo-regex (94%) y del umbral propuesto para
   el cutover de Fase 1 (≥98%). Con esto, el criterio de salida de Fase 0 queda
   cumplido para el dominio de certificación — la Fase 1 puede empezar.

Criterio de salida de la Fase 0: eval-set con al menos ~40-60 casos reales (✅ 50,
cumplido), harness de shadow-mode desplegado y logueando (✅ construido y testeado),
primer análisis de acuerdo/desacuerdo por campo con el LLM real documentado (✅ 100.0%,
ver arriba). **Fase 0 completa.**

### Fase 1 — Dominio certificación (primer vertical slice)

Por qué este dominio primero: es el más pequeño (un campo booleano, `is_certified`,
más el campo derivado `activity`), y es el que más bugs reales ha producido esta
sesión y en el historial (v0.20.9, v0.20.12, v0.20.17-21, v0.20.30-31 tocan todos este
área en algún punto). Buen banco de pruebas de bajo riesgo para validar el patrón
completo (shadow → eval → cutover → kill switch) antes de escalarlo a dominios más
grandes.

Pasos:

1. ✅ **Umbral de corte cumplido**: 100.0% de acuerdo en el eval-set con LLM real
   (Fase 0, `progress-log.md`) — por encima del ≥98% propuesto.
2. ✅ **Cutover implementado**: `_maybe_apply_llm_extraction_cutover()` en
   `supervisor.py`, gated por `settings.llm_extraction_cutover_certification`
   (default `False`). Rellena SOLO `is_certified`/`activity` cuando el regex los deja
   sin resolver — cualquier otro campo del patch LLM se descarta (queda para su
   propia Fase N). Corre ANTES de `_apply_detected_intent(intent, state)` para que lo
   rellenado se propague a `state` por el camino normal.
3. ✅ **TDD**: `tests/test_llm_extraction_cutover.py` (7 tests) — flag apagado no
   llama al LLM (verificado con `AssertionError` forzado, no solo observacional);
   flag encendido rellena SOLO los 2 campos del dominio aunque el patch LLM traiga
   más; nunca sobreescribe un campo ya resuelto por regex; no llama al LLM si lo
   único que falta es de OTRO dominio; fallo del LLM degrada silenciosamente a
   regex-only; el resultado se propaga correctamente a `state` vía
   `_apply_detected_intent`.
4. ✅ Suite completa (**1738 passed**, mismos 8 fallos preexistentes) + `ruff`/
   `compileall` en verde.
5. ✅ **Verificado en vivo con LLM real** (localmente, `ENV_FILE=.env.dev`, flag
   activado manualmente): mensaje `"never been underwater before, wanna give it a
   try, solo"` — el regex NO resuelve nada (`activity=None`, `is_certified=None`).
   **Con el cutover apagado** (comportamiento de hoy): cae a una respuesta genérica
   de RAG, se queda en `main_menu`, sin `detected_activity`. **Con el cutover
   encendido**: entra directo al flujo guiado de minicurso
   (`step=mixed_location`, `detected_activity=minicourse`,
   `detected_is_certified=False`) — mejora real y medible, no solo teórica.
6. ⬜ Pendiente (decisión de despliegue, no de código): activar
   `llm_extraction_cutover_certification=True` en un entorno real (dev/PRE) cuando
   el equipo decida — el código ya está listo y probado; el flag sigue en `False`
   por defecto en todos los entornos hasta esa decisión explícita.

**Fase 1 completa** (código + tests + verificación en vivo). Falta solo la decisión
del equipo de cuándo encender el flag en un entorno real — eso es una decisión de
producto/timing, no un bloqueador técnico.

### Fase 2 — Dominio grupo/cantidad/edades

`group_size`, `group_allocation`, `ages`. Más complejo que certificación (hay lógica de
split cert/no-cert, edades mínimas, etc. — ver `_split_out_uncertifiable_kids`). Mismo
patrón de pasos que la Fase 1, adaptado.

### Fase 3 — Dominio ubicación/actividad/cambios de plan

`location`, `island`, `hotel`, y los interceptores de cambio de plan/acompañante que
generalizamos en el Fix 3 de `docs/live-test-inconsistencies-plan.md` (los que causaron
la regresión que el Fix 4 tuvo que cazar). Este es el dominio con más regex dispersa
y más frágil — el más beneficiado por esta migración, pero también el que requiere más
cuidado (más superficie de regresión).

### Fase 4 — Integración con acciones de carrito (orchestrator)

Evaluar si, una vez los campos de `DetectedIntent` son fiables vía LLM, tiene sentido
fusionar esta extracción con el orquestador de acciones ya existente
(`src/agents/orchestrator.py`) en una sola llamada (ahorro de latencia/coste) o
mantenerlos separados (más simple de razonar, cada uno con su propio contrato). Decisión
pendiente de tomar con datos de las fases 1-3.

### Fase 5 — Limpieza y consolidación

Una vez todos los dominios migrados y estables en producción durante un periodo
razonable (a decidir con el equipo, ej. 2-4 semanas sin incidentes): eliminar el código
regex ya muerto, actualizar toda la documentación, y cerrar este plan como completado
(mover a `docs/project-history/` como referencia histórica, igual que se hizo con
`docs/memory-context-improvement-plan.md`).

## 5. Formato del eval-set

Seguir el mismo patrón ya usado en `docs/rag-eval-set.json` (usado para calibrar
`RAG_MIN_SCORE`, ver `docs/rag-threshold-calibration.md`) — un JSON versionable en el
repo, no una hoja de cálculo externa (`docs/project-history/estado-pendientes.md` ya
señala que el Google Sheet es solo para el checklist de lanzamiento, no para esto).

Propuesta de estructura (`docs/robustness/eval-set.json`, a crear en la Fase 0):

```json
{
  "cases": [
    {
      "id": "cert-typo-not-certfied-en",
      "message": "hi i wanna dive, im not certfied tho, just me",
      "lang": "en",
      "expected": {
        "is_certified": false,
        "activity": "certified_diving",
        "group_size": 1
      },
      "source": "live-PRE-2026-07-21",
      "notes": "Typo 'certfied' — bug real arreglado en v0.20.31"
    },
    {
      "id": "cert-typo-vucea-es",
      "message": "vamos 2, mi novia y yo, ella no vucea solo yo",
      "lang": "es",
      "expected": {
        "activity": "certified_diving",
        "group_size": 2
      },
      "source": "live-PRE-2026-07-21",
      "notes": "Typo b/v 'vucea'/'bucea' — bug real arreglado en v0.20.31"
    }
  ]
}
```

Cada caso nuevo encontrado (en vivo, o reportado por el owner) se añade aquí primero
—convirtiéndolo en regresión permanente— y luego se arregla, sea cual sea el mecanismo
(regex o LLM). Este archivo crece indefinidamente y es compartido por la Fase 0 (medir
acuerdo) y por cualquier fase de cutover posterior (medir regresiones).

## 6. Riesgos conocidos y cómo se mitigan

| Riesgo | Mitigación |
|---|---|
| No-determinismo del LLM (mismo mensaje, resultado distinto) | Temperatura 0, structured output, eval-set con umbral de acuerdo antes de cualquier cutover, kill switch por fase |
| Coste/latencia (llamada extra por mensaje) | Activación condicional (§3.3): solo cuando el regex deja huecos, no siempre |
| Regresión en un flujo ya validado | Nunca sobreescribe lo que el regex ya resolvió (fase inicial); suite completa + verificación en vivo obligatoria antes de cada cutover |
| El plan se abandona a medio camino entre sesiones | `progress-log.md` obligatorio, checklist de fases en este documento, README con instrucciones explícitas de "cómo retomar" |
| Se repite el error del Fix 3 de hoy (ampliar una regla sin darse cuenta de que incluye un caso donde el contexto asumido no es cierto) | Cada fase tiene su propio eval-set y su propia ronda de TDD — no se generaliza "por analogía", se mide con datos antes de cada cutover |

## 7. Referencias

- `docs/robustness-strategy-options.md` — las 4 opciones evaluadas, esta es la Opción 2.
- `docs/project-history/estado-pendientes.md` (punto #10) — la propuesta original de Álvaro.
- `docs/live-test-inconsistencies-plan.md` — los 4 fixes de la sesión que motivó esta decisión.
- `docs/HISTORY.md` v0.20.30-31 — los bugs concretos que ilustran el problema.
- `docs/rag-threshold-calibration.md` — precedente de metodología (eval-set + umbral medido con datos) ya usado en este repo para otra decisión de calibración.
