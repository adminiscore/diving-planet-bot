# Plan: una sola fuente del dominio de actividades

> Borrador 2026-09-14, pendiente de aprobación del owner. Sin código todavía.

## El problema

El bot no tiene **una** definición de qué actividades vende, para quién es cada una y
cómo se llama en cada capa. Tiene muchas, escritas a mano, que no se hablan entre sí.
Cuando una capa aprende algo (un valor nuevo, un matiz de negocio), las demás no se
enteran. Síntomas ya vistos:

- `padi_course` existe para el regex, el router y el núcleo, pero **no** para el
  extractor LLM; y si llega al carrito, el cliente recibe un curso **sin precio ni link**.
- El LLM entiende "4 con título y 2 snorkel", pero una guarda de vocabulario del núcleo
  (`_activity_has_textual_backing`) no conoce "con título" y tira el reparto.
- La descripción de negocio ("el minicurso es un bautismo de un día para quien no sabe
  bucear y no quiere certificarse") vive en glosas y reglas sueltas de un solo prompt; los
  demás prompts no la ven.

## Inventario (2026-09-14)

**Vocabularios distintos para lo mismo**

| vocabulario | valores | dónde |
|---|---|---|
| actividad (extractor LLM) | `certified_diving`, `minicourse`, `snorkel`, `padi_open_water`, `padi_advanced`, `padi_rescue`, `padi_divemaster`, `padi_specialty` | `prompts/booking.py::EXTRACTION_TOOL` |
| actividad (regex) | lo anterior + `padi_course` | `intent_detector._detect_activity` |
| categorías del regex | `certified_diving`, `minicourse`, `snorkel`, `padi_course`, `specialty` | `intent_detector._ACTIVITY_CATEGORY_PATTERNS` |
| acompañante (señales) | `certified_diving`, `minicourse`, `snorkel` (×2 enums) | `prompts/booking.py::SIGNALS_TOOL` |
| elección de acompañante | `snorkel`, `minicourse` | `prompts/booking.py` (slot `companion_activity_choice`) |
| opciones al comparar (router) | `certified_diving`, `minicourse`, `snorkel`, `padi_course` | `prompts/router.py` |
| tipo de ítem del carrito | `cert`, `beginner`, `snorkel`, `course` (+ `refresh`, `companion`) | `cart_render`, `catalog.SERVICE_TO_CART_TYPE`, `conversational_core` |
| `remember` | `certified`, `beginner`, `snorkel`, `course` | `supervisor._REMEMBER_ACTIVITY_MAP` (**código muerto**) |
| elegibilidad | `certified_diving`, `minicourse`, `bubble_makers`, `snorkel`, `open_water`, `companion` | `flows/eligibility.py` |
| bloques del RAG | `beginner`, `certified`, `course`, `snorkel` | `rag_agent` (overview de actividades) |
| servicios del catálogo | 36 ids (`2_dives_1_day`, `minicourse`, `open_water`, …) | `data/knowledge_base/services.json` |

**Tablas escritas a mano sobre esos vocabularios** (≈30): `_PRODUCT_ACTIVITIES`,
`_ACTIVITY_TO_CART_TYPE`, `_OFFERING_TO_SERVICE`, `_OFFERING_BLURB_ES/EN`,
`_DELIB_LABELS_ES/EN`, `_RECALL_LABELS_ES/EN`, `_COURSE_MENTION_RE` (núcleo);
`_ACTIVITY_TO_SERVICE_ID` (supervisor); `_PRICE_SINGLE_SERVICE_PATTERNS`,
`_PRICE_CATALOG_LABELS_ES/EN`, bloques del overview (RAG); `_ACTIVITY_LABELS`
(elegibilidad); `SERVICE_TO_CART_TYPE`, `ISLAND_SERVICE_MAP`, `MULTI_DAY_SERVICES`, edades
mínimas deducidas por id y por nombre en `_load_services` (catálogo);
`_ENUM_VALUE_GLOSSES_*`, `_FIELD_RULES_*["activity"]`, descripciones de los enums
(prompts).

Ejemplos de desincronización ya presentes: `ISLAND_SERVICE_MAP` no tiene las variantes de
isla de 3 y 4 inmersiones; las edades mínimas se deducen buscando "Minicurso" dentro del
nombre del servicio; el overview del RAG describe el minicurso con un texto propio que no
comparte con ningún prompt.

## Diseño

### 1. La fuente: `data/knowledge_base/activities.json`

Junto a `services.json`, editable por negocio sin tocar código. Una entrada por actividad:

```jsonc
{
  "id": "minicourse",                     // el identificador canónico, único en todo el bot
  "cart_type": "beginner",                // hasta migrar el carrito (fase 3)
  "services": {"cartagena": "minicourse", "island": "minicourse_already_on_island"},
  "requires_certification": false,
  "certifies": false,
  "course_level": null,                   // 1 = Open Water, 2 = Advanced... (orden PADI)
  "label": {"es": "Minicurso de buceo", "en": "Dive mini-course"},
  "for_whom": {                           // contexto de negocio: lo que ve el LLM
    "es": "Bautismo de un día para quien no sabe bucear y quiere probar con instructor, sin certificarse ni quedarse varios días.",
    "en": "..."
  }
}
```

`padi_course` es una entrada más ("curso PADI, nivel sin decidir") cuyo `for_whom`
explica cómo se decide el nivel: sin certificación → Open Water; con certificación →
según su nivel actual.

### 2. El acceso: `src/domain/activities.py`

Carga el JSON, lo valida contra `services.json` (cada servicio referenciado existe, cada
servicio vendible pertenece a una actividad) y expone lo que hoy está copiado:

- `activity_ids()`, `by_id(id)`, `service_for(id, location)`, `cart_type(id)`, `label(id, lang)`
- `activity_for_service(service_id)` → sustituye `SERVICE_TO_CART_TYPE`/`ISLAND_SERVICE_MAP`
- `business_context(lang, ids=None)` → el bloque de "qué es cada actividad y para quién"
  que se inyecta en **todos** los prompts que hablen de actividades

Un test estructural recorre los enums de todos los tools y falla si alguno usa un valor
que no sale de aquí (mismo patrón que `test_prompt_enum_enumeration.py`).

### 3. Qué NO hace

- No añade patrones regex. Los patrones de `intent_detector` siguen siendo el camino
  rápido; lo que cambia es que su **salida** tiene que ser un id del registro.
- No mete reglas de negocio en código cuando el LLM puede decidir con contexto (p. ej.
  el nivel de un curso): la regla va en `for_whom`, que ven todos los prompts.

## Fases (cada una se mide antes de pasar a la siguiente)

| fase | qué | cómo se valida |
|---|---|---|
| **F1** ✅ | `activities.json` + `src/domain/activities.py` + test de coherencia con `services.json`. Sin consumidores. | tests (10, contra los datos reales) |
| **F2a** | Prompts: el **contexto de negocio** (`for_whom`) del registro entra en **todos** los prompts que hablan de actividades, **solo para los valores que el código ya entiende hoy**. Los enums no cambian todavía. | eval-set + batería, A/B por caso |
| **F3** | Código: las ≈30 tablas (etiquetas, mapas al carrito y a servicios, isla, edades mínimas, overview del RAG) pasan a leer del registro, aceptando ya todos sus ids. Se borra `_REMEMBER_ACTIVITY_MAP`. | suite completa (sin cambio de comportamiento salvo los huecos corregidos) |
| **F2b** 📏 (medida, no aplicada) | Enums al vocabulario reservable del registro. Extractor: rompe otros campos. Router: acierta las opciones, pero hoy nadie las usa. Ninguno se aplica; pasa a F5 (ver abajo). | eval-set + batería, A/B por caso |
| **F4** | `padi_course` en el flujo: si el LLM no pudo decidir el nivel con el contexto, el núcleo pregunta el nivel con opciones del registro; nunca un curso sin precio. | tests + conversación en batería |
| **F5** | Evidencia citada: sustituye `_activity_has_textual_backing` y `_boolean_has_textual_backing` (guardas de vocabulario) por "el LLM cita el fragmento literal y el código lo comprueba". | eval-set + batería + tests de alucinación existentes |

**F2a — lo medido (2026-09-14)**

- Superficie de prompts: cambian exactamente los 17 prompts que deciden actividades
  (de 77); ninguno más.
- Regla de arquitectura precisada: `src/prompts` puede importar **solo** `src.domain`,
  que a su vez es hoja (test en `tests/test_prompts_surface.py`). Los tool schemas son
  constantes de módulo: sin importar el registro no podrían generar sus enums (F2b).
- Primera tanda del eval-set: **203/207** frente a 204/207. Un caso regresionó de forma
  determinista (`adv-en-elliptical-no-dive-verb`: el extractor dejó de rellenar
  `is_certified`). Ablación (3 repeticiones por variante): la causa era una sola frase
  del `for_whom` de `certified_diving`, "**y eso se confirma después**", que el modelo
  tomó como orden de no extraer la certificación. Quitar también "requiere carné"
  volvía a fallar: el requisito ayuda, lo que estropea es aplazarlo. Regla escrita en
  el propio `activities.json` y fijada con un test.
- Hipótesis descartada con datos: partir `for_whom` en "criterios" y "descripción"
  no arreglaba el caso; no se aplicó.

**Mapa de F3** (usos reales, 2026-09-14):

| tabla | usos | destino |
|---|---|---|
| `_PRODUCT_ACTIVITIES` (núcleo) | **0** | borrar |
| `_REMEMBER_ACTIVITY_MAP` (supervisor) | **0** | borrar |
| `SERVICE_TO_CART_TYPE` (catálogo) | **0** en `src` | borrar |
| `_ACTIVITY_TO_CART_TYPE` (núcleo) | 6 | `cart_type` del registro |
| `_ACTIVITY_TO_SERVICE_ID` (supervisor) | 1 | `service_ids(id, "cartagena")[0]` |
| `ISLAND_SERVICE_MAP` (catálogo) | 1 (`cart_render._service_for_location`) | `services["island"]` del registro (corrige D5) |
| `MULTI_DAY_SERVICES` (catálogo) | 1 (supervisor) | `duration_days` de `services.json` |
| `_RECALL_LABELS_*`, `_DELIB_LABELS_*` (núcleo) | 3 + 2 | `label` del registro |
| `_OFFERING_TO_SERVICE`, `_OFFERING_BLURB_*` (núcleo) | 1 + 1 | `services` + `for_whom` del registro |
| `_COURSE_MENTION_RE` (núcleo) | 1 | revisar en F5 (es detección por vocabulario) |
| `_PRICE_CATALOG_LABELS_*`, `_PRICE_SINGLE_SERVICE_PATTERNS` (RAG) | 1 + 1 | etiquetas del registro; los patrones, revisar en F5 |
| `_ACTIVITY_LABELS` (elegibilidad) | 1 | `label` del registro |
| edades mínimas en `_load_services` (catálogo) | — | `min_age` del registro |

**F3 — hecha (2026-09-14)**

- **F3a** (datos): `_ACTIVITY_TO_CART_TYPE`, `_ACTIVITY_TO_SERVICE_ID`, mapa de isla
  (corrige D5), multi-día (corrige el contexto del LLM de los cursos de 2 días), edades
  mínimas; borradas las 3 tablas sin uso. Prompts idénticos.
- **F3b** (textos): las 6 tablas de textos para el cliente (`_DELIB_LABELS`,
  `_OFFERING_TO_SERVICE`, `_OFFERING_BLURB`, `_RECALL_LABELS`, `_PRICE_CATALOG_LABELS`,
  `_ACTIVITY_LABELS`) pasan al registro: `texts` por actividad con una variante por uso
  (`name_in_sentence`, `recall`, `price_label`, `plan_label`, `pitch`) y
  `default_level` en `padi_course`. Las claves propias de los cursos (`open_water`,
  `advanced`…) pasan a ids del registro. Migración literal: 94 salidas visibles
  comparadas antes/después, **idénticas**.

**F4 — hecha (2026-09-14)**

- **Paso 1, el servicio sale siempre del registro**, en el único punto que guarda la
  actividad (`supervisor._apply_detected_intent`). Arregla tres fallos vivos
  reproducidos: un Open Water decidido por el LLM llegaba sin servicio (curso sin precio
  ni link); las especialidades del regex apuntaban a servicios inexistentes ("nitrox" en
  vez de "nitrox_specialty"); y cada detector escribía su propia tabla. El regex emite
  ahora ids del registro (`specialty_nitrox`…) con las mismas palabras clave de siempre.
- **Paso 2, el bot aclara el nivel** (decisión del owner): `padi_course`/`padi_specialty`
  llevan al slot `course_level`, con las opciones del registro por nivel (botones,
  número, nombre exacto; respuesta libre → resolutor LLM con enum generado del
  registro). Regla del owner aplicada en el mismo punto único: quien no tiene
  certificación va al `default_level` (Open Water) sin preguntar.
- Pendiente de F2b/F5 (no es regresión): "identificacion" sin tilde y "mindful **diving**"
  (gana "diving") son vocabulario del regex; los ids de especialidad todavía no están en
  el enum del extractor.

**F2b — lo medido (2026-09-14)**

Vocabulario = `dom.bookable_activity_ids()`: actividades con servicio propio o genéricas
(F4 pregunta el nivel). Sin `refresher` (se vende como minicurso) ni `bubble_makers` (D2).

- **Router** (`comparing_options`), `scripts/battery_activity_choice.py`, 3 repeticiones:
  base 6/9, solo contexto 6/9, solo vocabulario 8/9, **vocabulario + contexto 9/9**. Los
  casos nuevos (Open Water o Advanced, Nitrox o flotabilidad, Rescue o Divemaster) no se
  podían expresar con los 4 valores escritos a mano. Señales y resolutor del acompañante,
  idénticos en las cuatro variantes: no se tocan. **No aplicado**: en los tres casos
  nuevos la base ya marcaba `comparing=true` y solo erraba las opciones
  (`padi_course`, `certified_diving`). Hoy el núcleo solo lee el booleano: las opciones
  van al log y la comparación sale de `_mentioned_offerings` (regex). Aplicarlo no
  cambiaría ninguna respuesta. En cambio, alarga en cada turno un tool que emite otras
  señales (contacto, escalado…) que esta batería no mide, y el extractor acaba de
  demostrar que eso mueve campos vecinos. Su sitio es F5: que la comparación use las
  opciones del LLM en vez del regex, y medirlo entonces junto con las demás señales del
  router.
- **Extractor** (enum de `activity`, 8 → 15 valores). Eval-set 116 casos: 212/216 frente
  a 211/216, pero caso a caso **no pasa**:
  - arregla `ambig-curso-padi-generico-no-se-bucear` y `f2b-specialty-mindful-en`;
  - rompe `prof-en-from-states` ("im from the states, wanna dive"): `is_colombian=False`
    3/3 con el enum anterior, abstención 3/3 con el nuevo;
  - rompe `b08-ninos` en la batería de grupo ("2 adultos bucean y 2 niños hacen
    snorkel"): el reparto sale vacío en las cuatro variantes de vetos.

  Los dos fallos están en **otros campos** del mismo prompt de relleno: un enum más largo
  cambia lo que el modelo se atreve a rellenar en todo lo demás (misma lección que las
  glosas en F2a). Probado también mandar solo las propiedades pedidas: arregla
  `is_colombian`, pero rompe `is_certified` en "no es que no estemos certificados, sí lo
  estamos, los 2". **No aplicado.** Las especialidades concretas siguen llegando por el
  regex y el curso genérico se resuelve en F4. Queda para F5: con evidencia citada, el
  extractor podría devolver cualquier id del registro sin depender del tamaño del enum.
- Se queda como infraestructura: `dom.bookable_activity_ids()` con su test, 9 casos
  `f2b-*` en el eval-set (y `activity-nitrox` corregido a `specialty_nitrox`), y las
  variantes `vocab`/`vocab+ctx` con los casos r07–r09 en la batería de elección. Todo
  sirve para medir F5 contra esta línea base.

**F5 — tamaño del problema, medido antes de diseñar (2026-09-14)**

El eval-set no pasa por las guardas del núcleo (`run_extraction_eval.py` = `fill_gaps` +
veto), así que su nota no ve lo que ellas descartan. Medido aparte:

- **Sin LLM**, sobre los valores esperados del eval-set: la guarda de tema de los
  booleanos (`_boolean_has_textual_backing`) no respalda el valor correcto en 7 de 46
  casos que el regex tampoco resuelve; la de actividad, en 5 de 18 entradas de reparto;
  en los acompañantes de la batería de elección, 0 de 8.
- **Con turnos reales en `_understand`** (esos 10 casos, con y sin guardas): **3/10 con
  guardas, 8/10 sin ellas**. Todo lo que se pierde son booleanos: "soy paisa", "somos
  paisas", "ya soy sertificado", "tengo el AOWD", "nunca lo he hecho". Los tres repartos
  salen bien con y sin guarda. En los 2 casos restantes el LLM ya se abstiene solo.

Conclusión: F5 empieza por los booleanos. La guarda protege contra alucinaciones reales
(el LLM contestando desde el historial un slot que el mensaje no toca), así que
sustituirla exige mantener esa protección sin depender del vocabulario.

**F5a — booleanos: anclaje estructural en vez de vocabulario (hecha, 2026-09-14)**

- La protección que había que conservar, con LLM real: con la ubicación pendiente,
  "Desde Cartagena" hace que el LLM añada `is_colombian=True` 3/3 si nadie lo filtra.
- La evidencia citada **no** lo arreglaría: "Cartagena" está en el mensaje. No es una
  fuga del historial, es una sobreinferencia sobre el propio texto. Lo que separa
  "Desde Cartagena" de "soy paisa" es la estructura: el primero **contesta otra
  pregunta pendiente**. Es el principio que ya usaba `_turn_answered_a_different_slot`.
- Batería nueva, `scripts/battery_boolean_anchoring.py` (14 escenarios × 3; los filtros
  se compararon sobre la misma salida del LLM y después se midió la implementación):

  | filtro | legítimos | alucinaciones evitadas |
  |---|---|---|
  | vocabulario (retirado) | 0/24 | 18/18 |
  | sin guarda | 24/24 | 15/18 |
  | "hay otro slot pendiente" | 15/24 | 18/18 |
  | **"el turno contestó otro slot pendiente" (aplicado)** | **18/24** | **18/18** |

  Ningún escenario empeora respecto a la guarda de vocabulario. Coste conocido: una
  respuesta doble legítima ("desde cartagena, somos paisas") pierde el booleano y el bot
  lo pregunta después.
- Código: `_boolean_patch_is_anchored` sustituye a `_boolean_has_textual_backing`. Se
  borran `CERTIFICATION_TOPIC_RE` y `NATIONALITY_TOPIC_RE`, que ya no usaba nadie más.
  `LAST_DIVE_TOPIC_RE` se queda porque lo usa el propio detector regex. La guarda (a)
  también se aplica al patch: el booleano del slot pendiente nunca sale del LLM de
  huecos.
- Pendiente de F5: la guarda de actividad (`_activity_has_textual_backing`). Medida sin
  mordida real en los 3 repartos del eval-set; falta una batería de acompañantes con
  historial antes de tocarla.

**F5b — guarda de actividad del acompañante: medida (2026-09-14)**

`detect_special_signals` (`companion_activity`) con LLM real, 16 frases × 3, historial
de 2 turnos:

| | casos 3/3 |
|---|---|
| solo LLM | 13/16 |
| LLM + guarda de vocabulario (hoy) | 7/16 |

- La guarda tira 9 aciertos del LLM: "tiene el AOWD", "licencia SSI", "buzo avanzado",
  "el open water de hace años", "bajar con tanque", "respirar bajo el agua", "quedarse
  arriba viendo los peces", "máscara y tubo", "float and look at fish".
- Los 3 fallos del LLM son la misma familia: frases **sin actividad**. "mi amigo no
  está certificado" (con y sin tilde) → `minicourse`; "viene mi primo" →
  `certified_diving`. La guarda los evita.
- Aquí no hay atajo estructural: separar "quiere nadar con máscara y tubo" de "no está
  certificado" depende del significado. Es el caso para la evidencia citada.
- Bug encontrado de paso, **arreglado**: `certification_claim("mi amigo no está
  certificado")` daba `True` con tilde y `False` sin ella, así que el detector regex ponía
  `is_certified=True`. El patrón de negación escribía "esta" sin tilde. Arreglo general,
  sin añadir variantes: texto y patrones se comparan sin tildes (`src/utils/text.py`,
  que también usa `rag_agent`). Sobre los 177 mensajes del eval-set y las baterías solo
  cambia ese caso.

Variantes del prompt de señales, sobre los 10 casos de `battery_activity_choice` y las 16
frases (26 × 3):

| variante | casos 3/3 |
|---|---|
| base (LLM solo) | 22/26 |
| V1: `undecided` en el enum ("se une pero no dice qué hará") | **24/26**, sin empeorar ninguno |
| V2: cita literal obligatoria | 15/26 (el modelo casi nunca rellena la cita) |

V1 arregla "viene mi primo" y un caso inestable, pero sigue diciendo `minicourse` para
"mi amigo no está certificado" (con historial de buceo), que hoy la guarda sí evita.
Aplicar V1 sin guarda empeoraría 2 casos, así que no vale tal cual.

Dos redacciones más, explicando que "no estar certificado" no es una actividad (V3a en la
descripción del campo, V3b en la definición de `undecided`): **23/26 las dos**. Ninguna
arregla ese caso: con historial de buceo el modelo dice `minicourse` 3/3 en todas las
variantes. V3a además rompe "bajar con tanque" y V3b vuelve inestable "viene mi primo".

**Estado: sin aplicar. Decisión de negocio pendiente.** El modelo aplica de forma
consistente "acompañante sin certificación que se suma a un grupo que bucea → minicurso".
La auditoría del 2026-07-23 decidió preguntar. Si negocio acepta esa suposición por
defecto (el minicurso no exige certificación y el resumen de la reserva lo muestra), V1
sin la guarda de vocabulario da 24/26 y recupera los 9 casos que la guarda descarta. Si
se mantiene "preguntar", la guarda sigue y el hueco queda abierto.

**Incoherencias de textos que quedan en el registro (decisión de negocio, editar en
`activities.json` sin tocar código):**

| actividad | qué pasa |
|---|---|
| Rescue | tres nombres: "el curso Rescue" (recordar), "curso Rescue Diver" (comparar), "Curso Rescue Diver + EFR" (etiqueta y catálogo) |
| Especialidad genérica | `recall` dice "un curso PADI" en español y "a PADI specialty" en inglés |
| Minicurso | EN: "the mini-course" (recordar), "beginner mini-course" (comparar), "Dive mini-course" (precio) |
| Snorkel | `recall` en inglés dice "snorkel"; el resto dice "snorkeling" |
| Buceo certificado | `pitch` usa voseo ("explorás") y el resto del bot tutea |
| Buceo certificado | la etiqueta del plan de grupo dice "certified fun dive" en inglés y "Certified diving" en el resto |

**Por qué F2 se parte en dos** (corregido al empezar, 2026-09-14): si los enums de los
prompts pasaran al vocabulario completo antes de migrar el código, el LLM devolvería ids
(`specialty_nitrox`, `padi_open_water_referral`…) que `_ACTIVITY_TO_SERVICE_ID` y las
tablas del núcleo no saben tratar. F2a cambia lo que el LLM **sabe** sin cambiar lo que
puede **responder**, y se mide sola; F3 prepara el código; F2b abre el vocabulario.

## Decisiones del owner (2026-09-14)

1. La fuente vive en `data/knowledge_base/activities.json`.
2. Los textos parten de `services.json`, contrastados con los demás ficheros que el
   código usa de verdad (`policies.json`, `faqs.json`, `pricing.json`).
3. Una actividad por especialidad (`specialty_nitrox`, `specialty_buoyancy`,
   `specialty_naturalist`, `specialty_fish_identification`, `specialty_mindful_diving`),
   más `padi_specialty` genérica para "una especialidad, sin decir cuál".
4. El nivel de un curso sin nivel lo decide el LLM con contexto de negocio (`for_whom` de
   `padi_course`), no una regla en código.

## Ficheros de datos: vivos y sin uso

Cargados por el código (fuente válida): `services.json`, `policies.json`, `faqs.json`,
`pricing.json`, `brand_tone.json`, `conversations.json`. **Sin ningún uso en código**
(ni cargador del RAG ni `load_embeddings`): `availability.json`, `discounts.json`,
`escalation_rules.json`, `conversations.json.bak`. No se han usado como fuente.

## Discrepancias encontradas al contrastar (a decidir por negocio)

| # | tema | qué dice cada fuente | impacto |
|---|---|---|---|
| D1 | **Precio del refresher** — ✅ **decidido por el owner (2026-09-14): se cobra, tarifa 2026** | `pricing.json` (tarifa 2026): "Minicurso de Buceo / Refresh" 655.000 COP / 183 USD online desde Cartagena, 475.000 COP / 134,1 USD desde islas (idéntico al servicio `minicourse` del catálogo). El bot decía que **no tiene coste adicional** en 4 sitios (pregunta del flujo, nota de cierre, respuesta canónica del RAG, contexto del LLM en `supervisor`). Arreglo: entrada `refresher` en el registro vendida como el servicio del minicurso (`sold_as`); el precio por persona sale del catálogo, sin cifras a mano. | **Alto**: se prometía gratis algo que se cobra. |
| D2 | **Bubble Makers** | `faqs.json` lo vende (187 USD) y `eligibility` lo ofrece a niños de 8-10; **no existe en `services.json`** (sin link ni precio de catálogo). En el registro está como actividad sin servicios. | Medio: un niño de 8-10 no puede cerrar reserva con link. |
| D3 | **Edad mínima Advanced/Rescue** | `policies.json:age_minimum`: "cursos PADI desde los 10". `faqs.json` (Advanced: "edad mínima habitual de 12") y el código (`eligibility`, `_load_services`): 12. El registro usa 12. | Bajo. |
| D4 | **Requisito del Rescue** | `faqs.json`: requiere Advanced + EFR reciente. `services.json:rescue` no lo lista en requisitos. | Bajo. |
| D5 | **Mapas de isla incompletos** | `catalog.ISLAND_SERVICE_MAP` no tiene las variantes de isla de 3 y 4 inmersiones que sí existen en `services.json`. El registro las cubre; se corrige al migrar (F3). | Bajo/medio. |
| D6 | `_REMEMBER_ACTIVITY_MAP` | Definido en `supervisor.py`, sin ningún uso. Se borra en F3. | Ninguno. |
