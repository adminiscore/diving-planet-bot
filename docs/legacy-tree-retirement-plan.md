# Fase 4 — Retirada del árbol legacy `MIXED_*` (plan para revisión del equipo)

**Estado:** EN EJECUCIÓN en la rama `feature/fase4-p2` (sin mergear a `pre_gadea`).
Redactado 2026-07-24, en curso 2026-07-28 (Gadea + Claude). Ver el registro de
ejecución justo debajo.

## Estado de ejecución (2026-07-28) — rama `feature/fase4-p2`

Orden real seguido: **P1 (seam) → P4 (core-only) → P2 (borrar código)**.

**HECHO y verificado (suite 1444 passed, idéntica flag-off/on; ruff `check src` limpio):**
- **P1 seam** (v0.20.73): `src/flows/cart_render.py` desacopla el núcleo de `DecisionTree`. Cierre AST de 9 símbolos sin handlers `MIXED_*`.
- **Fix vivo de disponibilidad** (v0.20.74): gate del Bloque 2.5 estaba tras el hook → el núcleo alucinaba cupo; portado al núcleo.
- **Auditoría de los 302 fallos core-on**: TODOS legacy (aserciones de paso, idioma-botón, orquestador/MIXED, notes), NINGÚN gap real del núcleo.
- **Migración de tests (~11k líneas)**: `test_conversations` 330→66 (quirúrgico, los 66 pasan en ambos flags), `test_intent_robustness` −3 bare_pack, `test_padi_freetext` −clase Supervisor, `test_rag_safety` −2, y retirados enteros `test_decision_tree`, `test_companion_split`, `test_cert_multiday_matrix`, `test_orchestrator`, `test_dispatch_fallback_invariant`, `test_remembered_notes`, y los de flujo en `tests/FreeText/`. Conservados los de `IntentDetector`.
- **Flag flippeado a `True` por defecto** (`config.py`) — core-only en dev/tests.
- **Borrado de código del supervisor**: `_route_message_inner` −~566 líneas (bloque understanding-first + cola MENU_STEPS/SUMMARY/MIXED/fallback) + **48 funciones helper huérfanas** eliminadas en cascada. `supervisor.py`: **5908 → 3493 líneas**.

**HALLAZGO 2026-07-28 (importante): NO es solo `MIXED_*` — el ÁRBOL LEGACY ENTERO está muerto.** `process_message` (que despacha TODA la tabla de pasos: INFO/COURSES/PRICING/BOOKING/LOGISTICS/ISLAND/MIXED) solo se llama desde 2 bloques MUERTOS de `_route_message_inner` (un "back" que chequea pasos `MIXED_*` que nunca ocurren, y el "restart por saludo" que el núcleo ya maneja). Así que **~6000 líneas de handlers `_handle_*` en `decision_tree.py` son deletables**, no solo los 35 MIXED.

**DECISIÓN DE DISEÑO (owner Gadea, 2026-07-28): "menú"/"volver" = MENSAJE NORMAL.** Se quita el manejo especial del núcleo (deja de devolver None para menú/back en `conversational_core.py:1552-1556`) → el núcleo los trata como texto conversacional → los handlers de menú-reset/back del supervisor mueren → y con ellos el último caller vivo de `process_message`.

**PENDIENTE (siguiente lote — el corte MAYOR, hacer fresco):**
1. **Núcleo**: quitar el bloque de None-return de menú/back (`conversational_core.py:1552-1556`). Impacta ~7 archivos de test que asertan reset de menú (test_conversational_core, test_routing_signals_integration, test_conversations, etc.) — ajustar/retirar.
2. **Supervisor**: borrar los handlers menú-reset/back/greeting-restart (ahora muertos) + los 2 bloques con `process_message`.
3. **decision_tree.py**: borrar `process_message` + TODOS los handlers `_handle_*` legacy (~6000 líneas) con el eliminador iterativo de código muerto, PROTEGIENDO la base compartida (SERVICES/State/Step/MESSAGES/MESSAGE_SPLIT), los 9 símbolos que usa `cart_render` (`_service_for_location`, `_cart_label_for`, `_cart_service_id`, `_parse_mixed_quantity`, `_cart_booking_blocks`, `_format_activity_booking_messages`, `_goto_mixed_final_summary`, `_is_contact_only_service`, `_resolve_service_booking_url`), y `set_quick_replies` (si queda vivo). Verificar suite + smoke del render tras cada paso.
4. Módulo `orchestrator` + 27 pasos `Step.MIXED_*` (+ el resto del enum legacy si queda huérfano).
5. Quitar el flag `conversational_core` + gate en supervisor + `test_flag_off_core_not_engaged` + fixtures que parchean `detect_language_llm` + `CONVERSATIONAL_CORE` en `docker-compose.vps.yml`.

**Ya HECHO (2026-07-28, además de lo de arriba):** las 4 funciones dead-con-test-unitario (`_answer_offers_advisor`, `_detect_companion_intent`, `_mentions_diving_intent`, `_mentions_snorkeling_intent`) borradas + sus tests. supervisor.py: 5908 → **3257 líneas**.

### ¿Cómo funciona PRE hoy? (qué de `decision_tree.py` está VIVO vs MUERTO)

PRE conduce **todas** las conversaciones con el **núcleo** (`conversational_core.py`), no con el árbol. El árbol de botones está apagado en la práctica: el núcleo solo pone `state.step` en `FREE_TEXT`/`ESCALATE`, nunca en un paso legacy, y los 70 handlers `_handle_*` se despachan **por `state.step`** → nunca se ejecutan.

Pero `decision_tree.py` (**8.384 líneas**) es un archivo MIXTO. Reparto:

| VIVO (~2.400 líneas, lo usa PRE vía el núcleo — CONSERVAR) | MUERTO (~6.000 líneas, con el núcleo on — BORRAR) |
|---|---|
| `SERVICES` (catálogo: precios/servicios/links) | Los **70 handlers `_handle_*`** (menús info/cursos/precios/logística/islas + carrito mixto) |
| `MESSAGES` (~565 líneas de copy bilingüe), `MESSAGE_SPLIT`, `COMPANION_PRICE`, `ISLAND_SERVICE_MAP` | `process_message` (el dispatcher del árbol) + la tabla de dispatch |
| `ConversationState`, `Step` (modelo de estado, usado por toda la app) | Los pasos `Step.*` legacy que queden huérfanos |
| **Los 9 helpers de render** que el núcleo llama vía `cart_render` (resumen de reserva, links, cantidad, plan por ubicación) | El módulo `orchestrator` (el núcleo no lo usa) |
| `_detect_language_from_text`, `set_quick_replies` | |

En una frase: **PRE ya funciona 100% con el núcleo; del árbol solo quedan vivos los DATOS (catálogo/copy), el modelo de estado y ~9 funciones que renderizan el resumen de reserva.** Fase 4 borra la maquinaria de navegación por menús, que no conduce nada desde que el núcleo está encendido en PRE.

**Lección operativa**: `ruff --fix` quita imports que solo se usan vía monkeypatch en tests (`detect_language_llm`) → rompió 144 tests; los imports huérfanos se limpian a mano.

**Aviso previo (original):** revisar con Álvaro y Gonzalo antes de mergear a `pre_gadea` y antes de quitar el kill-switch (P4 final).

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

### ⚠️ ACTUALIZACIÓN CRÍTICA (2026-07-24) — el flujo legacy NO está muerto para tests/dev

Al arrancar P2 se destapó un hecho que **cambia el orden de las fases**: el flag
`conversational_core` está **OFF por defecto** (dev + la mayoría de tests), así
que el flujo `MIXED_*` es la ruta **activa y fuertemente probada** fuera de PRE.
Lo ejercitan **~15 archivos de test** (flag off):

- **Todo `tests/FreeText/`**: `test_cart_flow`, `test_diving_certification_flow`,
  `test_island_hotel_flow`, `test_mixed_group`, `test_100_conversations`.
- `test_conversations`, `test_companion_split`, `test_cert_multiday_matrix`,
  `test_padi_freetext`, `test_dispatch_fallback_invariant`, `test_eligibility`,
  `test_intent_robustness`, `test_orchestrator`, `test_remembered_notes`…

**Consecuencia**: los 35 handlers son inalcanzables **en PRE** (flag on) pero son
la ruta que **la suite valida** (flag off). Borrarlos rompe cientos de tests. Por
tanto **P2 no es "borrar código muerto", es DESMANTELAR un sistema paralelo que
sigue siendo la ruta probada + la de dev**.

**El orden correcto queda invertido**: primero **P4** (core-only en todas partes:
flip del default + quitar el flag + migrar/retirar toda la suite del flujo
legacy), y SOLO ENTONCES **P2** (borrar handlers/routing). Quitar el flag elimina
el kill-switch → requiere que el núcleo esté "probado en PRE" (umbral a decidir
por el equipo). Slice ya hecho en rama `feature/fase4-p2` (sin mergear): retirado
`test_decision_tree.py` — los unit tests del árbol — + `test_cart_render.py` fija
la cobertura de los helpers conservados.

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

> **Orden corregido tras el hallazgo del §2** (el flujo legacy es la ruta probada
> con el flag off): **P1 (hecho, seam) → P4 (core-only + retirar flag + migrar la
> suite legacy) → P2 (borrar handlers/routing) → P3 (limpieza final)**. La borrada
> de producción (P2) es lo ÚLTIMO, no lo siguiente. P1b (mover cuerpos) es
> opcional (no desbloquea nada).

### P1 — Aislar la base compartida (habilitador)
- Mover el **catálogo + mensajes + estado** a módulos limpios, p. ej.
  `src/flows/catalog.py` (`SERVICES`, `MULTI_DAY_SERVICES`, `MESSAGES`,
  `MESSAGE_SPLIT`) y `src/flows/state.py` (`ConversationState`, `Step`), con
  re-export temporal desde `decision_tree.py` para no romper imports de golpe.
- Extraer a `src/flows/cart_render.py` los símbolos que el núcleo usa (ver
  cierre verificado abajo) y hacer que el núcleo importe de ahí y **deje de
  instanciar `DecisionTree`**. Opción de mínimo diff: dejar métodos finos en
  `DecisionTree` que deleguen a las funciones nuevas (el legacy sigue vivo hasta
  P2).
- *Sin cambio de lógica; refactor de imports; suite verde.*

**Cierre transitivo VERIFICADO por AST (2026-07-24)** — superficie EXACTA que el
núcleo alcanza de la maquinaria de `DecisionTree`, y objetivo de la extracción:
- **7 métodos**: `_cart_booking_blocks`, `_cart_label_for`, `_cart_service_id`,
  `_format_activity_booking_messages`, `_goto_mixed_final_summary`,
  `_parse_mixed_quantity`, `_service_for_location`.
- **2 funciones módulo-nivel**: `_is_contact_only_service`,
  `_resolve_service_booking_url`.
- **Resultado de seguridad**: el cierre **NO** incluye ningún handler
  `_handle_mixed_*` y **NO** referencia ningún `Step.MIXED_*` → la extracción es
  un corte limpio; borrar los 35 handlers y los 27 pasos en P2 no rompe el
  render del núcleo. (Datos usados por estos helpers: `SERVICES`, `MESSAGES`,
  `COMPANION_PRICE`, `MESSAGE_SPLIT`, `ISLAND_SERVICE_MAP` y `Step.FREE_TEXT`/
  `ESCALATE` — todo de la base compartida que se conserva.)

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
