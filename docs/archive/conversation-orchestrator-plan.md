# Plan — Orquestador conversacional: hilo continuo + texto libre que modifica el árbol

Documento de diseño para resolver la pérdida de contexto, las alucinaciones y la
incapacidad del texto libre para cambiar el estado del árbol. Pensado para revisarse
en equipo y repartir el trabajo (Alvaro / Gonzalo / Gadea).

**Decisión de modelo tomada:** todas las llamadas LLM pasan a `gpt-4o`.

---

## ESTADO ACTUAL (handoff para Gadea / Gonzalo)

> Última actualización: 2026-06-17. Alvaro dejó la **Fase 1 hecha**; quedan 0, 2, 3, 4.

| Fase | Estado | Quién sigue |
|---|---|---|
| **0** — Reindexar + reiniciar | ⏳ PENDIENTE (no requiere código) | cualquiera, ejecutar ya |
| **1** — Contexto completo al LLM | ✅ **HECHA** (commit en esta sesión) | — |
| **2** — Orquestador con tool-calling | ⏳ PENDIENTE (la pieza grande) | a repartir |
| **3** — Modelo a gpt-4o | ⏳ PENDIENTE (trivial, al final) | — |
| **4** — Tests del orquestador | ⏳ PENDIENTE (en paralelo a Fase 2) | — |

### Qué se hizo en Fase 1 (ya en `feature/dev_alvaro`)

- `_build_extra_context` (`src/agents/supervisor.py`) ahora incluye **el carrito completo** ("3 x Buceo certificado, 1 x Snorkel") con la instrucción de no volver a preguntar por esas actividades, y el **step actual** del flujo guiado (para que el LLM sepa qué está esperando el bot).
- El historial que ve el LLM al responder pasó de `history[-6:]` a `history[-12:]` (`src/agents/rag_agent.py`, dentro de `_answer_with_llm`). Ojo: el `history[-6:]` de `build_retrieval_query` se dejó igual a propósito (solo usa los 2 últimos mensajes de usuario para enriquecer el retrieval).

### Por dónde empezar la Fase 2 (lo más importante)

1. Crear `src/agents/orchestrator.py` con función `orchestrate(message, state_snapshot, history, tools, lang)` usando **function calling** de OpenAI (ver §3.2). Devuelve un `tool_call` (acción + args) o `answer_question`.
2. En `supervisor.py`, sustituir el bloque `if state.step in _MIXED_FLOW_STEPS and state.quick_replies:` (~línea 2819, donde hoy se llama a `classify_menu_intent`) por la llamada al orquestador + un **dispatcher** que ejecuta cada tool contra el árbol (tabla de tools en §3.2.2 — todas reusan código que ya existe: `_remap_cart_for_location`, `process_message`, `_start_mixed_course_add`, `build_lead_summary`...).
3. Mantener los cortocircuitos deterministas previos al LLM (PII, escalación sensible, link roto) — esos NO pasan por el orquestador.
4. `classify_menu_intent` (`intent_classifier.py`) queda absorbido/reemplazado.

El contexto completo de la Fase 1 ya está disponible vía `_build_extra_context`: pásaselo al orquestador como `state_snapshot` para que decida con todo el contexto (incluido el carrito).

---

## 1. Diagnóstico (basado en el código actual)

Hoy conviven **dos mundos que no se comunican**:

1. **El árbol** (`src/flows/decision_tree.py`): sabe reservar, tiene el carrito (`state.mixed_cart`), y el estado (`location`, `is_certified`, `is_colombian`, `selected_service`...).
2. **El LLM/RAG** (`src/agents/rag_agent.py`): solo *conversa*. Responde preguntas pero **nunca modifica `state`**.

El único puente es `classify_menu_intent` (`src/agents/intent_classifier.py`), invocado en `supervisor.py` (~línea 2819) cuando hay texto libre en un step del flujo MIXED. Pero solo puede devolver:
- un **valor de botón que ya exista** en pantalla,
- `back`, `restart`, `currency_switch_cop/usd`,
- o `RAG` (que solo conversa).

No puede expresar intenciones ricas como "cambia el origen a las islas", "quiero reservar esto", "quita el snorkel".

### Fallos observados y su causa raíz

| Mensaje del cliente | Esperado | Real | Causa |
|---|---|---|---|
| "quiero cambiar, **estoy en las islas**" (en `MIXED_ADD_ACTIVITY`) | `location=island` | Hizo `restart` | El clasificador no puede "setear location", solo mapea a botones existentes |
| "**quiero reservarlo**" (texto libre) | Entrar al flujo de reserva | El RAG inventó "necesito el hotel" y entró en bucle | El RAG no sabe reservar → improvisa (alucina) |
| "**hotel pao pao, no quiero lancha**" | Anotar hotel + sin lancha | Fallback | Sin acción asociada + retrieval frágil |
| "en el hotel pao pao" falla / "estoy en el hotel pao pao" funciona | Misma respuesta | Inconsistente | Arreglado en `c91eb01` (pendiente de desplegar) |

### Memoria incompleta

`_build_extra_context` (`supervisor.py:2241`) le pasa al LLM un resumen del estado, **pero NO incluye el carrito**. Por eso, con 3 buceos ya en el carrito, "quiero reservarlo" provoca que el LLM pregunte cosas que el árbol ya sabe. Además el RAG solo ve `history[-6:]` (6 mensajes) → pierde el hilo largo.

---

## 2. Objetivos

1. **Hilo continuo:** el LLM siempre ve el estado completo (incluido el carrito) y suficiente historial.
2. **Texto libre que actúa:** "estoy en las islas", "quiero reservarlo", "quita el snorkel" **modifican el árbol**, no solo charlan.
3. **Menos alucinación:** el LLM nunca improvisa el proceso de reserva; eso lo hace el árbol determinista.
4. **Coherencia:** las respuestas tienen sentido respecto a dónde está el cliente en el flujo.

---

## 3. Diseño por fases

### Fase 0 — Desplegar lo que ya está hecho (inmediato, 15 min)

Los fixes de hoy (`c91eb01`: Pao Pao / contaminación de queries; `23c7520`: query autosuficiente) **no están desplegados**. El bot corre código viejo.

```powershell
python scripts/load_embeddings.py --dry-run   # ver qué cambia
python scripts/load_embeddings.py --yes        # reindexar (incluye FAQ Pao Pao de Gadea + depth)
# reiniciar el bot
```

**Resultado esperado:** "en el hotel pao pao" y las preguntas autosuficientes ya funcionan. Sirve de línea base antes de medir el resto.

---

### Fase 1 — Contexto completo al LLM (1-2 días, bajo riesgo)

Reescribir `_build_extra_context` (`supervisor.py:2241`) para que **siempre** entregue un snapshot estructurado y completo:

- **Step actual** y qué está preguntando el bot ahora mismo (ej. "el bot acaba de mostrar el resumen final del carrito y espera Reservar / Empezar de nuevo").
- **Carrito completo**: iterar `state.mixed_cart` → "3 × Buceo certificado (2 inmersiones), 1 × Snorkel".
- location, is_certified, is_colombian, selected_service (nombre legible), kids, refresher.
- **Historial ampliado:** pasar `history[-12:]` al RAG en vez de `history[-6:]` (en `rag_agent.py` y en las llamadas de `supervisor.py`). Para conversaciones muy largas, resumir los turnos antiguos en 1-2 frases (resumen incremental, opcional en esta fase).

**Archivos:** `supervisor.py` (`_build_extra_context`, llamadas a `rag_answer`), `rag_agent.py` (límite de history).

**Resultado esperado:** desaparecen los bucles del tipo "necesito saber el hotel" cuando el carrito ya está armado; el LLM responde coherente con lo que el cliente ya eligió.

---

### Fase 2 — Orquestador con tool-calling (3-5 días, el cambio clave)

Reemplazar `classify_menu_intent` por un **orquestador** que, en lugar de mapear a botones, usa **function calling** de OpenAI para elegir una **acción estructurada**. El supervisor ejecuta esa acción de forma determinista contra el árbol existente (no reescribimos el árbol, lo *conducimos*).

#### 3.2.1 Arquitectura

```
Texto libre del cliente
   ↓
orchestrate(message, full_state_snapshot, history, tools)   ← gpt-4o, function calling
   ↓
 ┌─ devuelve tool_call ──→ el supervisor ejecuta la acción contra el árbol
 │                          (muta state y/o inyecta inputs a decision_tree)
 │                          → renderiza el step resultante
 └─ devuelve "answer" ───→ RAG (rag_answer) responde la pregunta
```

#### 3.2.2 Catálogo de herramientas (tools)

Cada tool mapea a capacidades que el árbol YA tiene. Implementación: un dispatcher en el supervisor que traduce el tool_call a llamadas existentes.

| Tool | Argumentos | Ejecución (reusa código existente) |
|---|---|---|
| `set_location` | `origin: cartagena\|island` | set `state.location`; si hay carrito, `decision_tree._remap_cart_for_location(state)`; re-render del step actual |
| `start_booking` | `activity: certified\|beginner\|snorkel\|course\|mixed` | entrar al flujo MIXED correspondiente (reusa `_maybe_handle_mixed_group_from_menu` / `_start_mixed_course_add`) |
| `add_to_cart` | `activity, qty` | conducir el sub-flujo de añadir item |
| `cart_action` | `action: add\|modify\|remove\|confirm\|change_origin\|restart` | `decision_tree.process_message(state, <valor del botón correspondiente>)` |
| `set_profile` | `field: certified\|colombian\|refresher, value: bool` | setear el campo del state + avanzar el step si corresponde |
| `note_logistics` | `hotel?, island?, wants_pickup?, wants_private_boat?` | anotar en state (para la nota del asesor) |
| `escalate` | `reason` | `state.step = ESCALATE` + `build_lead_summary` |
| `answer_question` | — | fall-through a `rag_answer` (con el contexto completo de Fase 1) |

#### 3.2.3 Reglas del orquestador (system prompt)

- Si la intención requiere reservar/cambiar el carrito/origen → **usa una tool**, nunca describas el proceso tú mismo.
- Si es una pregunta informativa → `answer_question`.
- Si es médico / disponibilidad real / queja / pago → `escalate`.
- Nunca inventes precios, hoteles, links (igual que las reglas actuales del RAG).
- Conserva nombres propios (hoteles, islas) literales.

#### 3.2.4 Integración en `supervisor.py`

- Sustituir el bloque `if state.step in _MIXED_FLOW_STEPS and state.quick_replies:` (~2819) por la llamada al orquestador.
- El orquestador recibe el snapshot completo (Fase 1) + las tools válidas según el step.
- Tras ejecutar una tool, re-renderizar el step y devolver el mensaje del árbol.
- Mantener los cortocircuitos deterministas previos al LLM (PII, escalación sensible, link roto) — esos NO pasan por el orquestador.

**Archivos:** nuevo `src/agents/orchestrator.py` (reemplaza/extiende `intent_classifier.py`), cambios en `supervisor.py` (dispatcher de tools), helpers nuevos en `decision_tree.py` si hace falta exponer entradas limpias (ej. un método público para "entrar a reservar actividad X").

**Resultado esperado:** "estoy en las islas" cambia el origen; "quiero reservarlo" entra al carrito; "quita el snorkel" lo quita. El texto libre y el árbol son un solo sistema coherente.

---

### Fase 3 — Modelo a gpt-4o (30 min)

`src/config.py`: `openai_model: str = "gpt-4o"`. Afecta a las 4 llamadas (`rag_agent`, `query_rewriter`, `grounding_check`, orquestador) porque todas usan `settings.openai_model`.

- Opcional (recomendado para coste): añadir `openai_model_cheap: str = "gpt-4o-mini"` y usarlo en `grounding_check` y `query_rewriter` (tareas simples). Pero la decisión tomada es **todo a gpt-4o**; el split se puede hacer después si el coste molesta.
- Revisar `max_tokens` del orquestador (subir a ~150 para tool-calling con argumentos).

---

### Fase 4 — Tests y validación (2 días)

1. **Tests del orquestador** (mockeando el tool-call del LLM):
   - "estoy en las islas" en `MIXED_ADD_ACTIVITY` → `set_location(island)` → `state.location == "island"`.
   - "quiero reservar buceo certificado" → `start_booking(certified)` → step de reserva.
   - "quita el snorkel" con snorkel en carrito → `cart_action(remove)` → carrito sin snorkel.
   - "tengo asma" → `escalate`.
   - "¿qué incluye?" → `answer_question` → RAG.
2. **Tests de contexto completo:** `_build_extra_context` incluye el carrito y el step actual.
3. **Smoke test manual** sobre los flujos exactos del reporte (el del carrito + el del Pao Pao + reserva en texto libre).
4. **Regresión:** la suite completa sigue verde (`python -m pytest tests/ -q`).

---

## 4. Archivos a tocar (resumen)

| Archivo | Fase | Cambio |
|---|---|---|
| `scripts/load_embeddings.py` | 0 | reindexar (ejecutar, no editar) |
| `src/agents/supervisor.py` | 1, 2 | `_build_extra_context` completo; dispatcher de tools; history a 12 |
| `src/agents/rag_agent.py` | 1 | límite de history configurable |
| `src/agents/orchestrator.py` | 2 | NUEVO — function calling + tools |
| `src/agents/intent_classifier.py` | 2 | reemplazado/absorbido por el orquestador |
| `src/flows/decision_tree.py` | 2 | helpers públicos para entrar a flujos desde el orquestador |
| `src/config.py` | 3 | `openai_model = "gpt-4o"` |
| `tests/test_conversations.py`, `tests/test_rag_safety.py` | 4 | tests nuevos |

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Tool-calling elige acción equivocada y modifica el carrito sin querer | Confirmar cambios destructivos (ej. "restart") antes de ejecutar; loggear cada tool_call para revisar |
| Latencia: orquestador + posible RAG = 2 llamadas | gpt-4o es rápido; el orquestador resuelve la mayoría sin pasar a RAG |
| Coste de gpt-4o en todas las llamadas | Medir tras la demo; mover grounding/rewrite a `gpt-4o-mini` si hace falta (split ya previsto) |
| Romper flujos del árbol que hoy funcionan | El orquestador solo se activa para texto libre; los clicks de botón siguen el camino determinista actual |
| Conversaciones largas saturan el prompt | Resumen incremental de turnos antiguos (Fase 1, opcional) |

---

## 6. Reparto de trabajo sugerido

- **Fase 0** (reindex/restart): cualquiera, ahora.
- **Fase 1** (contexto completo): 1 persona, independiente. Desbloquea mejora rápida.
- **Fase 2** (orquestador): la pieza grande. 1 persona liderando `orchestrator.py` + dispatcher; otra preparando los helpers públicos en `decision_tree.py`.
- **Fase 3** (modelo): trivial, al final.
- **Fase 4** (tests): en paralelo a Fase 2, escribiendo tests contra el contrato de tools.

Cada fase es mergeable por separado y deja el bot funcionando.

---

## 7. Fuera de alcance (post-demo)

- Persistencia del state (Redis/Postgres) — sigue en memoria; se pierde al reiniciar.
- Resumen incremental sofisticado de conversaciones muy largas.
- Cascading de modelos afinado por tipo de tarea.
- Observabilidad/evals del orquestador (qué tool eligió, acierto).
