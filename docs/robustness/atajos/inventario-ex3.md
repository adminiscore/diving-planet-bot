# ex-3 · Respuestas de texto fijo ACTIVAS: inventario y decisión (12-oct-2026, Álvaro con Claude)

Fase EX (`../regex/plan-ex-entender-con-ia.md`). Las respuestas fijas contestan con un texto cerrado cuando una frase
casa con un patrón, sin pasar por el RAG. Las APAGADAS se borraron en ex-1 (HISTORY 0.31.13). Aquí van las que siguen
activas: qué las dispara, si la base del RAG ya tiene lo necesario para contestar igual, cuántas veces saltan de
verdad, y qué hacer con cada una.

## Inventario

| Respuesta fija | Dónde | La dispara | ¿Lo tiene la base del RAG? | Saltos reales | Decisión |
|---|---|---|---|---|---|
| Resumen de opciones ("¿qué ofrecen para bucear?") | `rag_agent._canonical_diving_overview_answer` (4 grupos de patrones `_OVERVIEW_*`) | frase de "qué ofrecen/opciones" + palabra de buceo | Sí: el catálogo entero va en el contexto | En las 38 rondas guardadas de PRE, **solo** con un mensaje: un buzo certificado que da fechas ("soy open… No sé qué tienen") y recibe "¿Nunca has buceado? → minicurso". Falsa alarma que llega al cliente (golden `certificado-fechas-fotos-y-reserva`, t1) | **Al RAG** con `ATAJO_RESUMEN_POR_RAG` |
| "¿Cambia el precio si es colombiano?" | `supervisor.fixed_same_price_answer` (en `info_node` y en la cascada) | "lo mismo/mismo precio … colombiano/extranjero", "colombiano … cambia" | Sí: regla de moneda del catálogo y 2 FAQs curadas (14, 116) | 0 en el golden visible | **Al RAG** con `ATAJO_NACIONALIDAD_POR_RAG`. Nació (2-sep) porque el RAG inventaba un precio al recalcular; desde `RAG_V2` el catálogo con la regla va en el contexto |
| Alergia a un alimento | `supervisor._alcohol_and_food_policy_answer` (`_ALLERGY_WORD_RE` + `_FOOD_ALLERGEN_RE`) | palabra de alergia + alérgeno (marisco, gluten, nueces, maní, lactosa) | Sí: FAQ curada 100 ("Soy vegetariano o tengo una alergia…") | 0 en el golden visible | **Al RAG** con `ATAJO_ALERGIA_POR_RAG`, salvo si el mensaje también habla de alcohol (va todo junto, como hoy). El enrutador la sigue mandando a info: que no llegue al aviso médico es entender, no responder |
| Alcohol antes de bucear | `supervisor._alcohol_and_food_policy_answer` (`_ALCOHOL_BEFORE_DIVING_RE`) | alcohol/cerveza/tragos cerca de bucear | **No**: solo está en `policies.json` (`no_alcohol_policy`), que el RAG no usa | 0 | **Se queda** (justificado). Para quitarla: pasar la política a una FAQ curada y medir |
| "¿Eres una IA / un bot?" | `supervisor._ai_identity_deflection` (`_AI_IDENTITY_RE`) | preguntas sobre bot/IA/modelo | Es texto que el negocio quiere literal (s4-15: honesto, sin revelar tecnología) | 1 (golden `es-un-bot`, correcto) | **Se queda** (política literal). Si se quiere decidir con Jev, haría falta una señal nueva |
| Grupo privado / evento de empresa | `supervisor._private_group_event_answer` (`_PRIVATE_GROUP_EVENT_RE`) | "evento corporativo", "grupo cerrado", "empresa … empleados" | Sí: FAQ curada 106 | 0 | **Se queda de momento, con un hallazgo:** el texto dice "Te paso con un asesor del equipo para armar la cotización" pero el nodo `info` solo devuelve el texto, sin marcar el pase. Solo llega a un asesor si el cliente contesta "sí/ok" justo después (`_BARE_AFFIRMATION_RE`). Propuesta aparte: que pase de verdad (o dejar que lo haga `needs_staff` de Jev) |
| Aclaración de un lugar ambiguo ("¿Cocoliso?" a secas) | `rag_agent._ambiguous_location_clarification` | el mensaje es solo un nombre de lugar | No aplica: es una repregunta, no una respuesta cerrada | — | Se queda (no es un atajo de respuesta) |

El inventario de regex (`scripts/inventario_regex.py`) cuenta 28 patrones / 9 grupos de "atajo activo": los 4 del
resumen, alcohol, los 2 de alergia, "¿eres una IA?" y nacionalidad.

## Cómo medir (cuando PRE esté libre)

1. **Escalón 0:** `scripts/sonda_atajos_pre.py` con `docs/robustness/atajos/preguntas-ex3.json` (16 preguntas: las
   que disparan cada atajo, otras formas de decirlo y la falsa alarma real) dentro de PRE, con los flags apagados y
   encendidos. Leer cada respuesta frente a su `debe`. Gasta ~0,4 $ (16 respuestas del RAG con su revisor).
2. **Mini-ronda A/B** solo si el escalón 0 pasa: el golden visible apenas los dispara (resumen 1, "¿eres una IA?" 1,
   el resto 0), así que la ronda es `certificado-fechas-fotos-y-reserva` más los diálogos que el escalón 0 señale.
3. Promocionar o revertir cada flag por separado.
