# Plan de mejora de memoria/contexto (B + C + A)

Estado: **Fase B implementada en local (2026-07-17), pendiente de desplegar a PRE y probar en vivo. C y A sin empezar.** Este documento es la referencia técnica para implementar, probar y desplegar a PRE las 3 fases acordadas, en orden **B → C → A**.

## Registro de progreso

- **2026-07-17 — Fase B implementada (local, no desplegada)**:
  - Tests escritos ANTES de la implementación (TDD): `tests/test_conversation_summarizer.py` (6 tests), confirmados en rojo primero (4 fallaban por `ImportError` — el módulo no existía; 1 confirmaba en vivo el hueco real en `_build_extra_context`).
  - Nuevos campos en `ConversationState` (`decision_tree.py`): `conversation_summary: str | None`, `conversation_summary_through: int = 0`. Verificado backward-compat: un estado ya guardado en Redis SIN estos campos (de antes de este cambio) carga con los defaults sin error.
  - Nuevo módulo `src/agents/conversation_summarizer.py`: `maybe_update_summary(state)` — dispara cada `_SUMMARY_TRIGGER_EVERY=12` mensajes nuevos, resumen incremental (resumen anterior + solo el tramo nuevo, nunca desde cero), mismo patrón de llamada LLM que `condense_query` (`redact_pii`, `temperature=0`, `try/except` que deja el resumen anterior intacto si falla).
  - Integrado en `supervisor.py`: `route_message` ahora es un wrapper fino que llama a `_route_message_inner` (la función original, renombrada) y luego a `maybe_update_summary` — se ejecuta una vez por turno sin importar qué rama interna atendió el mensaje. El resumen se inyecta en `_build_extra_context` (junto a `remembered_facts`), con la etiqueta "Resumen de la conversación hasta ahora:".
  - Suite completa: 1585 passed (6 nuevos), 15 skipped, mismos 8 fallos preexistentes sin relación (falta `OPENAI_API_KEY` local). `compileall` limpio.
  - **Pendiente antes de dar la Fase B por cerrada**: desplegar a PRE y probar en vivo el escenario del guion (detalle en turno 1, pregunta de seguimiento en turno 16) con el LLM real, no mockeado.
- **2026-07-17 — primer intento de prueba en vivo en PRE bloqueado por un bug NO relacionado, ya arreglado**: al probar el guion, la conversación entró en el flujo guiado (certificación → grupo → ubicación → plan → "¿hace más de 2 años que buceaste?") y ahí se quedó atascada — cualquier pregunta libre en ese paso (y en el de refresher) devolvía "no te entendí" sin llegar nunca a RAG. Causa: `supervisor.py` forzaba esos 2 pasos de vuelta al árbol de decisión asumiendo que el handler interpreta texto libre, cosa falsa para esos 2 en concreto. Arreglado en v0.20.18 (ver `docs/HISTORY.md`) — ahora esos pasos solo van al árbol si el mensaje resuelve como respuesta al botón; si no, caen a RAG normal. **Aún pendiente repetir la prueba de la Fase B en vivo con el guion completo**, ahora que este bloqueo ya no debería interponerse.

## Contexto (resumen del diagnóstico)

Hoy la memoria de la conversación tiene dos partes:

1. **Slots estructurados** (`ConversationState` en `decision_tree.py`): idioma, ubicación, certificación, edades, grupo, etc. — persisten bien, sin límite de tiempo dentro del TTL de 30 días.
2. **Memoria libre limitada**:
   - `state.history` (texto crudo) se guarda completo en Redis, pero **ningún consumidor lee más de los últimos 12 mensajes** (`rag_agent.py:1333` respuesta LLM, `rag_agent.py:1220` guard de grounding, `orchestrator.py:408` decisión del orquestador; `rag_agent.py:521` usa solo los últimos 6 para enriquecer retrieval).
   - `state.remembered_facts` (`decision_tree.py:222`) solo acepta 5 claves fijas (`budget`, `days`, `child_ages`, `experience_level`, `preference`), escritas por la tool `remember` del orquestador (`orchestrator.py:253-293`) y persistidas en `_persist_remembered` (`supervisor.py:3197-3252`, sobrescribiendo cada clave, sin acumular). Cualquier detalle que no encaje en esas 5 categorías no se guarda en ningún sitio permanente.
   - No existe ningún resumen progresivo de la conversación.

Las 3 fases:

- **B — Resumen progresivo (rolling summary)**: la pieza que falta del todo. Resuelve que una conversación larga pierda para siempre lo dicho al principio.
- **C — Hechos abiertos ("notes")**: amplía `remembered_facts` para capturar matices que no encajan en las 5 categorías actuales (salud, logística, preferencias no numéricas).
- **A — Ventana cruda más grande**: subir el tope de 12 mensajes, barato y sin downside, como margen extra antes de que el resumen entre en juego.

Orden de implementación acordado: **B, luego C, luego A**. Cada fase se despliega a PRE y se prueba en vivo antes de pasar a la siguiente.

⚠️ **Dependencia técnica entre B y A** (importante para no dejar un hueco): el disparador de B ("cuándo generar/actualizar el resumen") debe estar sincronizado con el tamaño de la ventana cruda que usan `rag_agent.py`/`orchestrator.py`. Si B se implementa primero con el disparador ajustado a la ventana ACTUAL (12), y luego A sube la ventana a, por ejemplo, 24, hay que subir el disparador de B al mismo número en ese momento — si no, quedaría un hueco de mensajes que ni están en la ventana cruda ni ya resumidos. Esto se señala explícitamente en la fase A más abajo.

---

## Fase B — Resumen progresivo

### Objetivo
Que ningún detalle relevante mencionado hace muchos turnos se pierda, aunque haya salido de la ventana de mensajes recientes.

### Diseño técnico

**Nuevos campos en `ConversationState`** (`src/flows/decision_tree.py`, junto a `remembered_facts`):
```python
conversation_summary: str | None = None
conversation_summary_through: int = 0  # índice de state.history hasta el que ya está resumido
```
Ambos con default seguro en `__post_init__` (ya existe el patrón para `history`/`remembered_facts`). Como `state_store.py` deserializa con `ConversationState(**data)`, los estados ya guardados en Redis sin estos campos cargan con el default sin migración necesaria.

**Nuevo módulo** `src/agents/conversation_summarizer.py`:
```python
async def maybe_update_summary(state: ConversationState) -> None:
    """Si hay suficientes mensajes nuevos desde el último resumen, genera uno
    actualizado (incremental: resumen anterior + tramo nuevo, no desde cero)."""
```
- **Disparador**: `len(state.history) - state.conversation_summary_through >= _SUMMARY_TRIGGER_EVERY` (constante compartida, empezar en `12` para alinear con la ventana cruda actual de la fase A).
- **Prompt**: system prompt tipo "Eres un asistente que mantiene un resumen conciso y factual de una conversación de reserva de buceo. Dado el resumen anterior (si existe) y el tramo nuevo de conversación, actualiza el resumen. Prioriza: composición del grupo, preferencias/restricciones mencionadas, decisiones ya tomadas, dudas ya resueltas. Sé breve (máx. ~150 palabras). No inventes nada que no se haya dicho."
- **Llamada**: mismo patrón que `condense_query` (`query_rewriter.py:87-104`): `AsyncOpenAI(api_key=settings.openai_api_key)`, `model=settings.openai_model`, `temperature=0`, `redact_pii()` sobre el texto antes de mandarlo, `try/except` que en caso de fallo deja `conversation_summary` sin tocar (nunca bloquea la respuesta al cliente).
- **Dónde se llama**: una vez por turno, en `supervisor.py` justo después de que se añade el mensaje a `state.history` (mismo punto donde ya se hacen otras actualizaciones de estado por turno) — llamada asíncrona, no bloqueante si es posible (o bloqueante pero barata; a decidir en implementación según latencia real medida).
- **Dónde se inyecta**: en el mismo lugar donde hoy se construye el contexto extra para el LLM (`supervisor.py:2756` y alrededores, la función que arma `parts` para `extra_context`) y en la construcción de historial de `rag_agent.py`/`orchestrator.py` — como un bloque al principio, ANTES de los mensajes crudos recientes, con una etiqueta clara tipo "Resumen de la conversación hasta ahora:" para que el LLM no lo confunda con un mensaje literal del cliente.

### Tests pre/post

**Escenario de prueba**: conversación de 16+ mensajes donde el detalle relevante aparece en el mensaje 2 y se pregunta algo que depende de él en el mensaje 16.

```
[Turno 1] Cliente: "Hola, somos 4, mi padre tiene la rodilla operada así que
                     mejor evitar planes muy físicos. Queremos bucear 2 días."
[Turnos 2-15] ... conversación normal resolviendo ubicación, precios, comida,
               política de cancelación, cantidad, edades ...
[Turno 16] Cliente: "Oye, y recuerdas lo que te comenté de mi padre? Qué me
                     recomiendas para él entonces?"
```

- **Pre-B (esperado FALLA)**: en el turno 16, el mensaje del turno 1 ya no está en los últimos 12 mensajes (`history[-12:]`). El bot no tiene ninguna referencia a "la rodilla operada" — responde genérico o pide que se lo repita.
- **Post-B (esperado PASA)**: `conversation_summary` ya contiene algo como "Grupo de 4, uno con rodilla operada — evitar planes muy físicos" desde que se generó en torno al turno 12-13. En el turno 16, esa frase viaja en el contexto aunque el mensaje original ya no esté en la ventana cruda, y el bot puede responder con una recomendación coherente (p. ej. snorkel/plan tranquilo para el padre).

**Test automatizado sugerido** (`tests/test_conversation_summarizer.py`, nuevo): mockear la llamada LLM del resumen (como se mockea `orchestrator.orchestrate` en `conftest.py`) para devolver un resumen fijo, simular >12 turnos vía `route_message`, y verificar que `state.conversation_summary` se generó y que aparece en el `extra_context` pasado a `rag_answer` en un turno posterior.

---

## Fase C — Hechos abiertos ("notes")

### Objetivo
Capturar matices puntuales que el cliente menciona y que no encajan en las 5 categorías fijas actuales (`budget`, `days`, `child_ages`, `experience_level`, `preference`), sin depender de que el resumen (fase B) los recoja bien.

### Diseño técnico

**Ampliar el schema de la tool `remember`** (`src/agents/orchestrator.py:265-293`), nueva propiedad:
```python
"notes": {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Otros detalles relevantes que no encajan en los demás campos: "
        "salud/movilidad, restricciones de horario, ocasión especial, "
        "miedos o preocupaciones concretas. Frase corta, en palabras del "
        "cliente. Ej: 'padre con rodilla operada, evitar planes físicos'."
    ),
},
```

**Cambiar `_persist_remembered`** (`supervisor.py:3197-3252`): a diferencia de las 5 claves actuales (que SOBRESCRIBEN el valor), `notes` debe ACUMULAR sin perder entradas anteriores:
```python
notes = remembered.get("notes")
if notes:
    existing = facts.get("notes") or []
    combined = existing + [n for n in notes if n and n not in existing]
    facts["notes"] = combined[-_MAX_NOTES:]  # cap, p.ej. 8, para no crecer sin límite
```

**Actualizar el renderer de contexto** (`supervisor.py:2756-2769`, la función que construye `parts` a partir de `facts`): añadir un bloque para `notes` (lista, no una sola línea):
```python
notes = facts.get("notes") or []
if notes:
    header = "Otros detalles mencionados por el cliente" if lang=="es" else "Other details the customer mentioned"
    parts.append(header + ":\n" + "\n".join(f"- {n}" for n in notes))
```

### Tests pre/post

**Escenario de prueba**: mensaje con un matiz que no es presupuesto/días/edad/experiencia/preferencia numérica.

```
Cliente: "Vamos a ir 3 personas, mi madre tiene vértigo así que ojalá el bote
          no sea muy movido, y es su cumpleaños así que algo especial estaría bien."
```

- **Pre-C (esperado FALLA o SE PIERDE)**: si el orquestador mapea esto a `preference`, solo sobrevive UN detalle (el último que se escriba en esa clave) — si más adelante el cliente menciona otra preferencia distinta, la del vértigo se sobrescribe y desaparece. Si no mapea a ninguna clave existente, se pierde directamente.
- **Post-C (esperado PASA)**: ambos detalles ("madre con vértigo, bote poco movido" y "es su cumpleaños") quedan como entradas independientes en `facts["notes"]`, y ambos siguen apareciendo en el contexto turnos después, sin que uno borre al otro.

**Test automatizado sugerido**: extender `tests/test_conversations.py` o crear `tests/test_remembered_notes.py` — usar `agent_decides(TOOL_ANSWER_QUESTION, remembered={"notes": ["madre con vértigo"]})` en un turno, y `remembered={"notes": ["es su cumpleaños"]}` en otro, verificar que `state.remembered_facts["notes"]` contiene ambas entradas (no que la segunda sobrescribió la primera).

---

## Fase A — Ventana cruda más grande

### Objetivo
Margen extra barato para conversaciones de longitud media, antes de depender del resumen (fase B) — y red de seguridad para el hueco que el resumen podría dejar si aún no se ha disparado.

### Diseño técnico

Subir el corte de `12` a un valor mayor (propuesta inicial: **24**, a validar por coste/latencia en PRE) en los 3 puntos ya identificados:
- `rag_agent.py:1333` (`history[-12:]` → `history[-24:]`, respuesta LLM principal)
- `rag_agent.py:1220` (`history[-12:]` → `history[-24:]`, guard de grounding)
- `orchestrator.py:408` (`(history or [])[-12:]` → `(history or [])[-24:]`)

Opcional, menor prioridad: `rag_agent.py:521` (enriquecimiento de retrieval, hoy `history[-6:]`) — subir a `10-12` si se detecta que preguntas de seguimiento pierden contexto de ubicación/tema.

**⚠️ Sincronizar con B**: actualizar `_SUMMARY_TRIGGER_EVERY` (fase B) de `12` a `24` en el mismo cambio, para que no quede un rango de mensajes "ni en la ventana cruda ni resumido todavía".

Extraer el número mágico a una constante única compartida (p. ej. `HISTORY_WINDOW_SIZE` en `src/config.py` o en un módulo común), en vez de repetir el literal en 3-4 sitios — así el ajuste fino post-producción ("pulir si sobra rango") es un solo cambio, no una búsqueda por el código.

### Tests pre/post

**Escenario de prueba**: conversación de 15-18 mensajes (por encima del tope viejo de 12, por debajo del nuevo de 24), con un detalle en el mensaje 3 relevante en el mensaje 15.

- **Pre-A (esperado FALLA, incluso con B activo si el resumen aún no se disparó)**: con ventana de 12, el mensaje 3 ya no está crudo en el turno 15. Si B todavía no ha llegado al umbral de disparo (o si el resumen es más impreciso que el texto original), el bot pierde precisión sobre ese detalle.
- **Post-A (esperado PASA)**: con ventana de 24, el mensaje 3 sigue disponible tal cual (texto crudo, no resumido) en el turno 15 — máxima fidelidad, sin depender de que el resumen haya capturado bien el matiz.

**Test automatizado sugerido**: extender los tests existentes de `test_conversations.py` que ya simulan conversaciones largas (buscar los que usan varios `route_message` seguidos) añadiendo aserciones sobre cuántos mensajes de `state.history` se pasan a `rag_answer`/`orchestrator.orchestrate` (se puede espiar el argumento `history` recibido por el mock).

---

## Checklist de despliegue a PRE (por fase)

Para cada fase, antes de pasar a la siguiente:
1. Implementar + tests unitarios en local (suite completa, sin regresión sobre los ~1580 tests existentes).
2. `/closework` → desplegar a PRE.
3. Probar en vivo en Chatwoot con el escenario pre/post de esa fase (usar los guiones de arriba palabra por palabra si es posible, para comparar antes/después de forma limpia).
4. Confirmar que no hay regresión en comportamientos ya validados (ubicación, certificación, precios) — al ser una capa de contexto adicional, no debería tocar la lógica determinista existente, pero conviene confirmarlo en vivo.
5. Anotar en `docs/HISTORY.md`/`session-handoff.md` el resultado real observado en PRE (no solo lo esperado en este plan).

## Palancas para ajustar después en producción ("pulir si sobra rango")

- **Frecuencia del resumen** (`_SUMMARY_TRIGGER_EVERY`): si se dispara demasiado seguido (coste) o casi nunca hace falta, subir/bajar el número.
- **Tamaño de la ventana cruda** (`HISTORY_WINDOW_SIZE`): si 24 resulta demasiado (latencia/coste) o insuficiente (se siguen perdiendo detalles medios), es un solo número que ajustar.
- **Modelo usado para el resumen**: hoy se propone reutilizar `settings.openai_model` (gpt-4o) por simplicidad; si el coste del resumen pesa, cambiar a un modelo más barato solo para esa llamada es un cambio aislado (mismo patrón que ya permite `settings.openai_model` para el resto del sistema).
- **Tope de `notes`** (`_MAX_NOTES`): si 8 se queda corto o resulta demasiado en el contexto, ajustar.
- **Longitud del resumen**: el límite de ~150 palabras del prompt es ajustable si se ve que pierde matices o que resulta demasiado largo en el contexto.
