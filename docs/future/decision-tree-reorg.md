# Reorganización de `decision_tree.py` + decisiones pendientes post-Fase 4

Estado: **§1 HECHO (2026-07-28) · §2 HECHO**. Creado 2026-07-28 tras cerrar Fase 4
(retirada del árbol de decisión legacy `MIXED_*`). Ninguna de estas tareas cambia
comportamiento; son de organización/deuda.

---

## 1. ✅ HECHO (2026-07-28, Gonzalo+Claude) — `decision_tree.py` partido en módulos honestos

**El "cajón de sastre" de ~2.140 líneas se partió en 3 módulos + shim de compatibilidad.**
Cero cambio de comportamiento (suite **1396 passed**, ruff limpio, identidad de objetos
verificada). Reparto final:

- **`src/flows/state.py`** (~240 líneas) → `Step`, `ConversationState`, `ButtonOption`,
  `MESSAGE_SPLIT`. Módulo hoja (solo stdlib).
- **`src/flows/catalog.py`** (~390 líneas) → `SERVICES` + `ISLAND_SERVICE_MAP` +
  `SERVICE_TO_CART_TYPE` + `MULTI_DAY_SERVICES` + `COMPANION_PRICE` + umbrales +
  formateadores (`_format_price`/`_format_duration`/`_extra_notes`…) + heurística de
  idioma por stopwords. Módulo hoja (solo stdlib).
- **`src/flows/messages.py`** (~1.520 líneas) → el dict `MESSAGES`, `BUTTON_OPTIONS`,
  `get_button_options` y la clase `DecisionTree`. Depende solo de `state`.
- **`src/flows/decision_tree.py`** queda como **shim de re-export** (con `__all__`) que
  re-exporta los ~28 símbolos públicos. Así los **~40 importadores** (7 en `src/`, resto
  tests/scripts) y los **monkeypatches de la suite** (`src.flows.decision_tree.X`) siguen
  funcionando **sin tocar una sola línea** — se evita la churn frágil de reapuntar 40
  sitios por cero beneficio de comportamiento. Código nuevo debe importar de los módulos
  concretos.

Grafo de dependencias sin ciclos: `state` (hoja) ← `messages`; `catalog` (hoja);
`decision_tree` (shim) → los tres. **Pendiente opcional futuro** (aún menos prioritario):
reapuntar los importadores a los módulos concretos y borrar el shim; y convertir el
vestigio `DecisionTree` en funciones de módulo. No urge.

<details><summary>Estado original (histórico) — el cajón de sastre pre-split</summary>

Tras Fase 4, `src/flows/decision_tree.py` (~2.140 líneas) ya **no era un árbol de
decisión** — el nombre quedó mentiroso. Era un cajón de sastre con 4 responsabilidades
mezcladas:

| Bloque | Qué es | Aprox. |
|---|---|---|
| Catálogo/datos | `SERVICES`, `ISLAND_SERVICE_MAP`, `MULTI_DAY_SERVICES`, `COMPANION_PRICE` (cargados de JSON) + loaders (`_load_services`…) + formateadores (`_format_price`, `_format_duration`, `_detect_language_from_text`…) | ~290–630 |
| Estado/tipos | enum `Step`, dataclass `ConversationState`, `ButtonOption` | ~27–290 |
| Strings de UI | el dict gigante `MESSAGES` | ~637–2000 (~1.360 líneas) |
| Vestigio | la clase `DecisionTree`, ya minúscula (`set_quick_replies` + 3 métodos de opciones-isla; solo la usa el supervisor) | ~2007–fin |

**Propuesta:** partir en módulos honestos, p. ej.:
- `src/flows/catalog.py` → SERVICES + mapas + loaders + formateadores.
- `src/flows/state.py` → `Step`, `ConversationState`, `ButtonOption`.
- `src/flows/messages.py` → el dict `MESSAGES`.
- convertir el vestigio `DecisionTree` (set_quick_replies + isla) en funciones de módulo.
- `decision_tree.py` desaparece (o queda como shim de re-export temporal).

**Coste/riesgo:** cero cambio de comportamiento, pero toca los **~10 módulos** que
importan de `decision_tree` (`supervisor`, `conversational_core`, `cart_render`,
`rag_agent`, `intent_detector`, `state_store`, `chatwoot`, `main`, `lead_summary`,
`conversation_summarizer`) — hay que reapuntar cada `from src.flows.decision_tree
import X`. Churn mecánico grande → por eso va en PR aparte. La suite completa
(1393 passed) + `compileall` son la red.

**Nota:** `cart_render.py` ya importa catálogo/estado de `decision_tree` (seam P1b
cerrado); si se hace la extracción, `cart_render` pasaría a importar de
`catalog.py`/`state.py` directamente.

</details>

---

## 2. ✅ RESUELTO (2026-07-28, Gonzalo+Claude) — Fase C re-cableada al núcleo con LLM

**Decisión del owner: opción (a) — re-cablear con LLM.** Implementado:
- **`src/agents/notes_extractor.py`** (`extract_notes`): tool-call forzado (temp 0,
  `settings.extraction_model`) que extrae "hechos abiertos" que un asesor querría
  recordar (lesión/médico, accesibilidad, restricciones alimentarias, ocasiones
  especiales, restricciones de agenda/presupuesto) y NO son slots de reserva. Dedup vs
  las ya conocidas; en cualquier error/timeout → `[]` (nunca rompe el turno). 8 tests.
- **Escritor en el núcleo** (`conversational_core._maybe_capture_notes`, llamado tras
  añadir el mensaje del usuario en `maybe_handle_turn`): persiste en
  `state.remembered_facts["notes"]` con dedup + cap `_MAX_REMEMBERED_NOTES`; gate barato
  que salta mensajes triviales (`<3` palabras / numéricos). 4 tests de integración.
- Alimenta el render que ya existía en `supervisor._build_extra_context` (contexto del
  LLM) + la nota de lead del asesor.
- **Verificado en vivo (LLM real)**: "es nuestra luna de miel…" → notes=`['luna de
  miel', 'quieren algo especial de snorkel']`, en contexto; reserva sin hecho abierto →
  sin notes (0 falsos positivos).
- **División de labores** (hallazgo al verificar): lo **médico/adaptativo** lo intercepta
  antes la **red de precisión LLM de enrutado** (→ DIVE-TO-HEAL, vía dedicada al asesor),
  así que no llega al núcleo; la captura de notes cubre el espacio COMPLEMENTARIO (hechos
  abiertos no-sensibles). Ambos informan al asesor.
- Suite **1396 passed**, ruff limpio. `docs/archive/memory-context-improvement-plan.md` archivado
  (disparador de abajo cumplido).

### Registro de la decisión (histórico)

Al revisar `docs/archive/memory-context-improvement-plan.md` (2026-07-28) se detectó que la
**Fase C ("notes" = hechos abiertos que no encajan en las 5 categorías fijas, p. ej.
"padre con rodilla operada, evitar planes físicos")** quedó **INACTIVA** tras Fase 4:

- Su **escritor** (`_persist_remembered`, que acumulaba `remembered_facts["notes"]`
  desde la tool `remember` del `orchestrator`) lo llamaba `_dispatch_conversation_agent`
  — la vía del orquestador, **runtime-dead bajo el núcleo** — y se **borró en Fase 4**.
- El **núcleo nunca tuvo escritor propio** de "notes".
- Solo sobreviven **vestigios**: el render en `supervisor.py` (~1107-1114, lee un
  `facts["notes"]` siempre vacío), un comentario obsoleto (~`supervisor.py:1539`) y
  probablemente la constante `_MAX_REMEMBERED_NOTES`.

Es el mismo patrón que `language_detector` (feature que quedó desconectada al retirar
el legacy). **Fases B (resumen progresivo) y A (ventana) siguen VIVAS y funcionando.**

### Decisión a tomar (owner)
- **(a) Re-cablear Fase C al núcleo**: que el núcleo capture "notes" abiertas
  (equivalente a lo que hacía la tool `remember`) y las persista en
  `remembered_facts["notes"]`, alimentando el render que ya existe. Similar al
  re-cableo de `detect_language_llm`.
- **(b) Dar Fase C por cubierta con Fase B** (el resumen progresivo ya captura los
  matices relevantes de conversaciones largas) y **limpiar los vestigios** (render de
  notes + comentario + constante `_MAX_REMEMBERED_NOTES`).

### Disparador de archivado
**Una vez tomada la decisión E IMPLEMENTADA (opción a o b), mover
`docs/archive/memory-context-improvement-plan.md` a `docs/archive/`** — hasta entonces se
queda en `docs/` como recordatorio de este cabo suelto.
