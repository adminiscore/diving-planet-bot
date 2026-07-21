# Plan: 4 inconsistencias reales encontradas en pruebas en vivo (2026-07-21)

Estado: **Fixes 1-4 implementados y con suite completa en verde. Pendiente: re-test en vivo contra PRE (paso 7 del checklist) y cierre/despliegue.** Encontrado simulando 2 conversaciones realistas (con errores de escritura, en español e inglés) directamente contra PRE (SSH + `live_battery_driver.py`, LLM real). Transcripts completos en el chat de esa sesión.

## Resumen de causas raíz (verificadas, no especulación)

### #1 — La pregunta de certificación se pierde cuando el orquestador interpreta otra cosa
**Escenario real**: bot pregunta "¿Estáis certificados?" (`Step.MIXED_ASK_CERTIFICATION`); cliente responde "desde cartagena" (no responde certificación, da ubicación); el orquestador LLM clasifica esto como `TOOL_SET_LOCATION`; `decision_tree.orchestrator_set_location` (`decision_tree.py:5412`) fija la ubicación y salta **incondicionalmente** a `_goto_mixed_entry`/`_goto_mixed_add_activity` (líneas 5446-5450) sin comprobar que había una pregunta de certificación pendiente sin responder. El dato de certificación nunca se vuelve a preguntar en toda la conversación.

**Causa raíz**: `orchestrator_set_location` no sabe que `state.step` estaba en un paso "pregunta pendiente" antes de decidir a dónde saltar después de fijar la ubicación.

### #2 — Preguntas legítimas del KB rechazadas como "HALLUCINATED" (dos causas distintas, verificadas con retrieval real)
**Caso A — enriquecimiento de "pregunta de seguimiento" contamina la búsqueda**: "y si llueve que pasa" es corta y empieza por "y" → `_looks_like_follow_up` la marca como seguimiento → `build_retrieval_query` (`rag_agent.py:510`) le pega los últimos 2 mensajes del usuario **sin comprobar si son del mismo tema**. Verificado en vivo: la pregunta sola recupera la FAQ correcta ("¿Que pasa si hace mal tiempo?") con `score_vector=0.42` (por encima del umbral 0.40); enriquecida con los 2 turnos anteriores (precio/comida, temas no relacionados), el score de esa misma FAQ **baja a 0.377** (por debajo del umbral) y ganan las FAQs de comida. Sin contexto suficiente, la respuesta cae al camino "solo extra_context" y el juez de grounding la rechaza.

**Caso B — el chunk de "políticas de descuento" mezcla los 5 tipos en un bloque único**: "can i bring my own gear" no se enriquece (no es un seguimiento), pero el chunk que contiene el dato real (5% de descuento por equipo propio) está mezclado con las otras 4 políticas de descuento en un solo chunk largo (`scripts/load_embeddings.py`, sección `discount_policies`, arreglada en v0.20.22 pero seguía siendo UN chunk con las 5 políticas juntas). Verificado: el score más alto para esta pregunta es 0.376 (por debajo del umbral) — la señal específica de "equipo propio" se diluye entre las otras 4 políticas del mismo chunk.

### #3 — Un cambio de plan explícito se ignora fuera de 3 pasos concretos
El interceptor de switch multi-día y de acompañante-en-texto-libre (v0.20.29) solo vigila `Step.MIXED_ADD_QTY`, `Step.MIXED_CERT_LAST_DIVE`, `Step.MIXED_ADD_PREVIEW` (`supervisor.py:5001`, `:5024`). Un usuario real que se queda haciendo preguntas libres (precio, equipo, cancelación) antes de resolver el paso de ubicación permanece en `Step.MIXED_LOCATION` — fuera de esos 3 pasos — así que "actually i changed my mind, i want to do it for 3 days instead" no lo detecta nadie y cae a una rama genérica que ni siquiera responde a la petición.

**Causa raíz**: los interceptores están acotados por **nombre exacto de paso**, no por **contexto de reserva** (¿ya sabemos que es buceo certificado, en cualquier punto del flujo mixto?).

### #4 — La conversación no converge hacia una reserva estructurada
Relacionado con #1 y #3: mientras el cliente pregunta cosas (precio, comida, clima), la información que da libremente (cambios de grupo, preferencias) queda en memoria conversacional (Fase B/C, ya funciona bien) pero **no siempre se traduce en progreso real del carrito/estado estructurado**. Causa adicional verificada: de ~8 sitios donde `rag_answer()` se llama dentro del flujo mixto (`supervisor.py`), **solo 2 sitios** (líneas 4761, 5050) adjuntan `_continue_booking_quick_replies` — el resto (incluido el camino más usado, línea 5201, "RAG free text in menu step") no ofrece ningún recordatorio de continuar la reserva tras responder. No es indeterminismo, es inconsistencia real de cobertura.

---

## Plan de fixes

### Fix 1 — Preservar preguntas pendientes al saltar por ubicación
En `orchestrator_set_location` (`decision_tree.py`), antes de caer a `_goto_mixed_entry`/`_goto_mixed_add_activity`: si `state.step` es uno de los pasos "pregunta pendiente sin resolver por esto" (`MIXED_ASK_CERTIFICATION`, `MIXED_ASK_CERT_COUNT`, `MIXED_ASK_BEGINNER_ACTIVITY`), **re-mostrar esa pregunta** (reutilizando `_ask_certification_message`/equivalente) en vez de saltar al menú de actividades. Definir explícitamente el set `_PENDING_QUESTION_STEPS` para que quede documentado y sea fácil de ampliar si aparece un caso hermano.

### Fix 2 — Precisión de retrieval
**2a.** `build_retrieval_query` (`rag_agent.py`): antes de enriquecer con turnos anteriores, probar primero la consulta corta SOLA contra `search_knowledge_base`; si ya devuelve un doc por encima del umbral de confianza, usar esa (no enriquecer). Solo enriquecer con turnos previos cuando la consulta corta por sí sola NO encuentra nada confiable — así "y si llueve" nunca se diluye si ya se puede resolver sola.
**2b.** `scripts/load_embeddings.py`: partir el chunk único `discount_policies` en un chunk por cada política (`online_booking`, `own_equipment`, `group_discount`, `second_day_discount`, `roverd`) en vez de uno mezclado — mismo patrón que ya se usa para otras secciones de `pricing.json`. Requiere reindex (automático en cada deploy vía CI, como ya confirmamamos con el fix del descuento de grupo).

### Fix 3 — Generalizar los interceptores de switch/acompañante por contexto, no por paso exacto
Cambiar la condición de entrada de ambos interceptores (`supervisor.py:5001`, `:5024`) de `state.step in (3 pasos concretos)` a: `state.step in _MIXED_FLOW_STEPS` (el set ya existente, mucho más amplio) **Y** hay señal de que la reserva es de buceo certificado (`state.mixed_pending_qty_type == "cert"` O `state.detected_activity == "certified_diving"` O ya hay un ítem `cert` en `state.mixed_cart`). Así el interceptor cubre a un cliente que todavía está en `MIXED_LOCATION`/`MIXED_ASK_CERTIFICATION` haciendo preguntas antes de resolver esos pasos.

### Fix 4 — Nudge consistente + auditoría de saltos de estado
**4a.** Adjuntar `_continue_booking_quick_replies` (o equivalente) de forma consistente en TODOS los caminos donde `rag_answer()` se llama dentro de un paso de `_MIXED_FLOW_STEPS`, no solo en 2 de ~8. Requiere revisar cada sitio para no romper el comportamiento ya validado (v0.20.26: no forzar botones de asesor).
**4b.** Auditar el resto de funciones `orchestrator_*` (`orchestrator_remove_activity`, `orchestrator_add_to_cart`, `orchestrator_start_activity`) para el mismo patrón del Fix 1 — ¿alguna otra salta por encima de una pregunta pendiente sin comprobarlo?

## Tests pre/post
Para cada fix, TDD: reproducir el fallo exacto con un test dirigido (mockeable, sin LLM real) ANTES de arreglar, confirmar rojo, implementar, confirmar verde. Al final, repetir las 2 conversaciones reales completas contra PRE (SSH) para confirmar en vivo con el LLM real.

## Checklist
1. ✅ Fix 1 + tests + suite completa.
2. ✅ Fix 2a + tests + suite completa.
3. ✅ Fix 2b + tests + suite completa + reindex (automático en deploy).
4. ✅ Fix 3 + tests + suite completa.
5. ✅ Fix 4a/4b + tests + suite completa.
6. `/closework` → desplegar.
7. Repetir las 2 conversaciones reales contra PRE, comparar transcript antes/después.
8. Actualizar este documento y `docs/HISTORY.md`/`session-handoff.md` con el resultado real.

## Registro de progreso

**Fix 1** (`decision_tree.py`): añadido `_PENDING_QUESTION_STEPS = {Step.MIXED_ASK_CERTIFICATION}`; `orchestrator_set_location` re-pregunta certificación en vez de saltar al menú si estaba pendiente. Test: `test_location_answer_does_not_swallow_pending_certification_question`.

**Fix 2a** (`rag_agent.py`): `rag_answer()` prueba primero la query corta sola; solo usa la versión enriquecida con turnos previos si la corta no encuentra nada confiable. Test: `test_bare_followup_query_not_diluted_by_unrelated_history`.

**Fix 2b** (`scripts/load_embeddings.py`): cada política de descuento (`discount_own_equipment`, `discount_group_discount`, etc.) se indexa también como chunk individual además del chunk combinado. Tests: `test_individual_discount_policy_chunks_exist_per_language`, `test_own_equipment_discount_chunk_is_not_diluted_by_other_policies`.

**Fix 3** (`supervisor.py` + `decision_tree.py`): los interceptores de switch multi-día y acompañante-en-texto-libre se generalizaron de 2-3 pasos exactos a `_CERT_FLOW_IN_PROGRESS_STEPS`/`_CERT_COMPANION_SPLIT_STEPS` (gate por contexto vía `_is_certified_diving_booking_in_progress`, no por nombre de paso). Requirió dos ajustes adicionales encontrados por la propia suite:
- `_detect_multiday_switch` no reconocía un conteo de días "pelado" sin cualificador ("3 days" sin "of diving") — añadido un fallback acotado.
- La generalización inicial colisionaba con preguntas de info genuinas que contienen la palabra señuelo ("paquete") — añadido el guard `not _looks_like_info_question(message)` a ambos interceptores.
Tests: `test_multiday_switch_by_text_at_location_step`, `test_multiday_phrasing_at_location_step_does_not_misfire_for_other_activity`.

**Fix 4a** (`supervisor.py`): el fallback más usado dentro del flujo mixto (`classify_menu_intent` → `"RAG"`, rama "Free text while in menu") no adjuntaba `_continue_booking_quick_replies`. Se añadió, condicionado a `state.step in _MIXED_FLOW_STEPS` (no afecta a los pasos de menú informativo puro, y no contradice la decisión del owner de 2026-07-20 de no forzar botones de *asesor* — son conceptos distintos). Test: `test_intent_classifier_rag_fallback_keeps_continue_booking_nudge`.

**Fix 4b** (auditoría, `decision_tree.py`): se encontró que `orchestrator_remove_activity` y `orchestrator_start_activity` tenían el mismo patrón del Fix 1 — ambas saltaban incondicionalmente (a `_goto_mixed_cart_review` / al add-flow de otra actividad) sin comprobar `_PENDING_QUESTION_STEPS`. Corregidas igual que `orchestrator_set_location`. Además, escribir el test de `orchestrator_start_activity` destapó una regresión real introducida por el propio Fix 3: al ampliar `_CERT_COMPANION_SPLIT_STEPS` se incluyó `MIXED_ASK_CERTIFICATION`/`MIXED_ASK_CERT_COUNT` — pasos donde precisamente NO se sabe aún si el hablante está certificado — así que "también snorkel" en ese punto se interpretaba como "buzo certificado revela acompañante no certificado" y resolvía la certificación como "sí" en silencio. Se excluyeron esos dos pasos de `_CERT_COMPANION_SPLIT_STEPS`. Tests: `test_start_activity_does_not_swallow_pending_certification_question`, `test_remove_activity_does_not_swallow_pending_certification_question`.

Suite completa tras los 4 fixes: 1711 passed, 15 skipped, 8 failed (los mismos 8 fallos pre-existentes de siempre por falta de `OPENAI_API_KEY` local, no relacionados).
