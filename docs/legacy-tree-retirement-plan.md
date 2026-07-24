# Fase 4 — Retirada del árbol legacy `MIXED_*` (plan para revisión del equipo)

**Estado:** propuesta, sin código todavía. Redactado 2026-07-24 (Gadea + Claude).
Revisar con Álvaro y Gonzalo antes de empezar el refactor.

> Regla de oro de esta sesión: **borrar solo lo que el núcleo NUNCA alcanza**;
> conservar (a) lo que el núcleo llama, (b) lo compartido (catálogo/estado),
> (c) los fall-through vivos en PRE (escalado/menú/idioma).

---

## 1. Objetivo y contexto

El bot tiene **dos sistemas de conducción en paralelo**:

- **Árbol legacy `MIXED_*`**: máquina de estados por menús de botones
  (`src/flows/decision_tree.py`, ~8.400 líneas + routing en `supervisor.py`).
- **Núcleo conversacional** (`src/agents/conversational_core.py`): bucle
  comprender→resolver→responder, detrás del flag `settings.conversational_core`.

**Realidad de despliegue (2026-07-24):** solo existen **dev** y **pre**. PRO no
está montado y no se promoverá hasta que PRE esté al 100%. En PRE el flag está
**encendido** (`docker-compose.vps.yml:113`, `CONVERSATIONAL_CORE: "true"`), así
que **el árbol legacy ya no conduce ninguna conversación en PRE**. El objetivo de
la Fase 4 es **eliminar la maquinaria obsoleta antes de promover a PRO**, para
que el código que llega a producción esté limpio.

## 2. Hecho de seguridad — por qué es seguro retirarlo

Con el núcleo encendido, `conversational_core` solo pone `state.step` en
`FREE_TEXT` o `ESCALATE` — **nunca** un `Step.MIXED_*` (verificado). Como TODOS
los handlers `MIXED_*` (en el árbol y sus interceptores en el supervisor) se
despachan **por `state.step`**, con el núcleo on son **inalcanzables** →
código muerto en el camino real de PRE.

Corolario: la retirada NO puede cambiar el comportamiento observable de PRE si
solo se toca código inalcanzable. La verificación es la suite + pruebas en vivo.

## 3. Inventario / dimensión

| Elemento | Cantidad | Dónde |
|---|---|---|
| Pasos `Step.MIXED_*` | **27** | `decision_tree.py` (enum `Step`) |
| Handlers `_handle_mixed*` / `_goto_mixed*` | **35** | `decision_tree.py` |
| Referencias a `Step.MIXED_*` en el supervisor | **158** | `supervisor.py` (routing + interceptores) |
| Tests del flujo legacy | **~880 líneas** | `tests/test_decision_tree.py` (+ partes de otros) |
| Flag + config | 1 | `settings.conversational_core`, `docker-compose.vps.yml:113` |

## 4. La frontera — qué se CONSERVA (no es "el árbol")

`decision_tree.py` es un archivo **mixto**. Lo que usan otros módulos (imports
reales, 2026-07-24) y NO se puede borrar:

| Símbolo | Lo importan |
|---|---|
| `ConversationState` | conversational_core, conversation_summarizer, intent_detector, lead_summary, chatwoot, main, state_store |
| `Step` | conversational_core, state_store |
| `SERVICES` (catálogo/precios) | conversational_core, lead_summary, rag_agent, supervisor |
| `MULTI_DAY_SERVICES` | supervisor |
| `MESSAGES` | supervisor (muchas veces) |
| `MESSAGE_SPLIT` | chatwoot, main |
| `_detect_language_from_text` | conversational_core, supervisor |

Además, **5 helpers de la clase `DecisionTree` que el núcleo llama** para
renderizar/resolver (viven entrelazados entre la maquinaria `MIXED_*`):

| Helper | Línea aprox. | Uso en el núcleo |
|---|---|---|
| `_goto_mixed_final_summary` | 6111 | resumen final del carrito (×3) |
| `_cart_booking_blocks` | 5940 | bloques de reserva/links |
| `_cart_label_for` | 3238 | etiquetas de ítem del carrito (×4) |
| `_service_for_location` | 2304 | resolver plan por ubicación (×3) |
| `_parse_mixed_quantity` | 3379 | parsear cantidad (×2) |

**El riesgo principal está aquí**: hay que separar estos 5 helpers (y su cierre
transitivo) de los 35 handlers muertos ANTES de borrar, o se rompe el render del
núcleo. Verificar que su cierre transitivo NO incluye ningún `_handle_mixed_*`.

## 5. Plan fasado (reversible, suite verde en cada paso)

### P1 — Aislar la base compartida (habilitador)
- Mover el **catálogo + mensajes + estado** a módulos limpios, p. ej.
  `src/flows/catalog.py` (`SERVICES`, `MULTI_DAY_SERVICES`, `MESSAGES`,
  `MESSAGE_SPLIT`) y `src/flows/state.py` (`ConversationState`, `Step`), con
  re-export temporal desde `decision_tree.py` para no romper imports de golpe.
- Extraer los **5 helpers** del núcleo a `src/flows/cart_render.py` como
  funciones (o una clase fina) que dependan solo del catálogo/estado. Confirmar
  que su cierre transitivo no toca los handlers `MIXED_*`.
- El núcleo pasa a importar de esos módulos y **deja de instanciar
  `DecisionTree`**.
- *Sin cambio de lógica; refactor de imports; suite verde.*

### P2 — Borrar la maquinaria muerta
- Eliminar los **35 handlers** `_handle_mixed*`, los **27 pasos** `Step.MIXED_*`
  y el despacho de routing legacy + interceptores `MIXED_*` en `supervisor.py`
  (las 158 referencias) y el mapa `BACK_STEP` de pasos mixtos.
- Eliminar el `MAIN_MENU`/entrada por botones si queda huérfano.

### P3 — Retirar/reescribir tests legacy
- `tests/test_decision_tree.py` (~880 líneas) y las partes de otros tests que
  ejerciten el flujo por botones. Lo que valga la pena, reescribir contra el
  núcleo.

### P4 — Quitar el flag (always-on) + limpiar config
- Retirar `settings.conversational_core` y el gate en `route_message` (el núcleo
  pasa a ser el único camino).
- Quitar `CONVERSATIONAL_CORE` de `docker-compose.vps.yml` (ya no es un flag).

## 6. Riesgos y mitigaciones

- **Helper compartido que resulte llamar a un handler muerto** → P1 primero,
  con verificación del cierre transitivo antes de cualquier borrado.
- **Fall-through vivo en PRE** (escalado/menú/idioma cuando `maybe_handle_turn`
  devuelve `None`) → NO tocar esos handlers; están fuera de la maquinaria
  `MIXED_*`.
- **Import roto en los 9 módulos** → re-export temporal desde `decision_tree.py`
  en P1; migrar imports módulo a módulo con suite verde.
- **Pérdida del kill-switch**: hoy apagar el flag revierte al legacy sin rollback
  de código. Tras P4 ya no existe; **aceptable solo cuando el núcleo esté
  probado** (decisión de equipo: ¿cuánto tráfico/tiempo en PRE antes de P4?).

## 7. Reversibilidad
- P1–P3 son commits independientes; cada uno revertible con `git revert`.
- Recomendado: rama `feature/fase4-retirar-legacy` para el trabajo grande, PR a
  `feature/pre_gadea` con la suite verde.

## 8. Preguntas abiertas para el equipo
1. ¿Umbral para dar el núcleo por "probado en PRE" y quitar el kill-switch (P4)?
   (p. ej. N días sin bugs nuevos del bucle de datos Fase 6.)
2. ¿Separamos catálogo/estado a módulos nuevos (P1) o los dejamos en
   `decision_tree.py` renombrado a algo neutro (p. ej. `flows/core_data.py`)?
3. ¿Reescribimos los tests legacy que aporten cobertura útil, o los retiramos
   sin más por estar sobre un flujo eliminado?

## 9. Checklist de verificación (cada fase)
- [ ] `pytest` completo verde.
- [ ] `test_chatwoot_buttons` + `test_decision_tree` (mientras exista) + `test_rag_safety`.
- [ ] `ruff check src` limpio; `compileall`.
- [ ] Prueba en vivo en PRE del guion completo (entrada libre, multi-actividad,
      acompañante, escalado, menú/volver) — sin regresiones.
