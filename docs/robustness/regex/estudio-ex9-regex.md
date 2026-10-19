# Estudio ex-9: los regex que "intentan entender al cliente" (19-oct-2026, Gadea con Claude)

Pregunta de Gadea: qué hacen de verdad los regex de "entender al cliente" y qué podemos hacer para no usarlos, antes de
decidir la parte 2 de ex-9 (`plan-ex-entender-con-ia.md`: "entender al cliente" ≤ 15 % del inventario). Es un estudio:
no cambia código del bot. Datos y scripts en `docs/robustness/regex/estudio-ex9/` (ver el anexo).

## Resumen

**1. El 64,8 % del inventario es un espejismo; lo real es el 87,2 %.** `python -m scripts.inventario_regex` sí recorre
`src/agents/nucleo/` y `src/agents/rutas/` (usa `rglob`), pero sus reglas clasifican por NOMBRE de fichero
(`supervisor.py`, `conversational_core.py`) y tras el reparto de s4-2 esos 192 patrones salen "sin clasificar". Además
`_PIDE_PRECIO_RE`, `_PRECIO_AJENO_RE` y `_PISTA_ORIGEN_RE` (4) están como "guarda sobre la respuesta del bot" y leen el
mensaje del cliente. No he tocado el script (se dice aquí). Con las familias corregidas a mano:

| Familia | Script hoy | Corregido |
|---|---|---|
| Entender al cliente | 503 (64,8 %) | **677 (87,2 %)** |
| Sin clasificar | 192 | 0 |
| Atajos de texto fijo | 9 | 28 |
| Guardas sobre el texto del bot, formato, privacidad, leer un LLM | 72 | 71 |
| **Total** | **776** | **776** |

Además el inventario solo cuenta literales `r'...'` dentro de asignaciones: hay 59 más en llamadas sueltas (45 en
`intent_detector.py`: edades, última inmersión, ubicación) y listas de palabras que no son regex pero entienden igual
(`ESCALATION_KEYWORDS`, `CONTACT_NUMBER_REQUEST_PHRASES`, `kids_keywords`, frases de cancelar/cambiar, las palabras del
idioma del detector).

**2. Qué hace cada uno de los 677 (clase según corre con la config de PRE):**

| Clase | Patrones | Qué es |
|---|---|---|
| **a** · camino principal: decide la respuesta | **244 (36 %)** | atajos antes de la IA, respuestas cortas, deliberación, duración/nº de inmersiones/edades, señales en OR con Jev |
| **b** · pista o red que solo cuenta si la IA falla o no lee | **227 (34 %)** | lo que el extractor ya sustituye (certificación, grupo, nacionalidad, última inmersión) y las redes de acompañante |
| **c** · muerto: sin llamador, flag apagado, condición imposible o solo log/etiqueta | **98 (14 %)** | + 14 de atajos y del juez que también están muertos |
| **d** · lista cerrada, formato o validación (no es "entender") | **108 (16 %)** | hoteles e islas del catálogo (86), tokenizadores, ¿hay una cifra?, saludo |

**3. Cuánto saltan de verdad.**
- Golden visible (95 diálogos, 342 mensajes distintos; las rondas `2026-10-1*` repiten exactamente esos mensajes): el
  detector decide algún dato en **176 mensajes (51 %)**: 164 en campos que ya decide el extractor y 46 fuera de él
  (duración, nº de inmersiones, edades, "solo yo").
- PRE, 16 rondas solo visibles del 14 al 16-oct (2.725 turnos): **el extractor no falló ni una vez**, así que la pista
  del regex (clase b) no decidió nada. Cuando el regex leía algo en un campo del extractor, el extractor coincidía solo en
  la actividad 40 % (315 de 786), la ubicación 60 %, la certificación 61 % y el grupo 71 %. El regex decidió **solo**:
  duración 142 veces, nº de inmersiones 107, nº de días 29, isla 45, hotel 14 y edades 25.
- Donde el regex y el extractor discrepan en PRE y hay etiqueta (30 turnos distintos): **acierta el extractor 21, el regex
  5, ninguno 4**.

**4. Qué se puede quitar ya sin riesgo:** los **98 patrones de clase c** (+14 de atajos y del juez) y las funciones
muertas que los rodean (el veto LLM entero de `rutas/booking.py`, `_regex_contradictions`, `_quote_backs_boolean`,
`mentions_writer_and_others`, `certification_is_ambiguous`, el idioma por palabras de `_detect_language`, el resumen
fijo de `rag_agent`...). Medida: suite verde y el replay offline del golden igual turno a turno (es determinista: 0
diferencias entre dos pasadas).

**5. Qué necesita IA y cuál** (los 579 restantes, sin los muertos):

| Propuesta | Patrones | Qué IA |
|---|---|---|
| **B** · campo del extractor que ya existe | **258** | `is_certified`, `group_size`/`group_allocation`, `activity`, `location`, `is_colombian`, `last_dive_over_2_years`, `hotel`, `nombre` |
| **C** · pregunta de Jev | **127** | ya existen: `asks_question`, `corrects`, `broken_link_complaint`, `adaptive_diving_topic`, `comparing`, `pending_answer`, `needs_staff`, `wants_human`, `companion_joins`/`adds_person`; nuevas: "pide cambiar de idioma", "pregunta si es un bot", "empieza otra reserva", "pide un precio" |
| **E** · diseño nuevo | **56** | campos nuevos del extractor (duración, edades, plan elegido), el reescritor también para mensajes largos, alcohol y DIVE TO HEAL por el RAG |
| **D** · se queda | **128** | 108 de lista cerrada o formato + 20 de cifras ("5 inmersiones", edades a una pregunta cerrada) |
| **A** · borrar aunque hoy actúe | **10** | días cerrados (lo contesta el RAG), `_N_INMERSIONES_RE` (duplica `dive_counts_in`), `_PLURAL_COMPANION_RE` (se va con su red) |

**6. ≤ 15 % no sale solo borrando.** Quitando lo muerto (c) y la pista (b) queda un 55,8 %; hace falta pasar también las
clases a con preguntas de Jev y campos nuevos (ver "Orden propuesto"). Con todo hecho quedan 20 patrones de cifras de
"entender" sobre 213 (**9,4 %**), o 0 % si se cuentan como formato.

**7. Latencia: el regex no cuesta nada** (`detect()` tarda 1,6 ms p50, 5,4 ms p95). Lo que se gana es acierto (los
falsos positivos de abajo), código (el núcleo deja de tener dos lectores y cuatro redes) y las llamadas LLM de las redes
(la red de señales hizo 66 llamadas en los 2.725 turnos de PRE).

**8. Un riesgo de seguridad hoy:** el atajo del alcohol va antes que la puerta médica. "estoy embarazada, ¿puedo bucear o
tomar vino?" y "anoche tomé mucho alcohol y hoy me duele el pecho, ¿puedo bucear?" van a la ruta INFO aunque Jev diga
`sensitive_topic=medical_questions` (comprobado en local con `classify_route`), y allí `info_agent` contesta el texto
fijo del alcohol sin pasar a una persona.

## Cómo se ha hecho

| Fuente | Qué da | Script (`estudio-ex9/scripts/`) |
|---|---|---|
| Inventario + lectura del código, siguiendo los llamadores hasta `route_message` con la config de PRE (valores por defecto de `config.py` + `JEV_ROUTER_ENABLED=true`) | clase y propuesta de los 232 grupos | `mapa.py` → `grupos.csv` |
| Los 342 mensajes de cliente distintos del golden VISIBLE (sin el oculto), sin red | qué patrones casan y qué decide `detect()` | `parte1_detector.py`, `parte6_saltos.py` |
| Banco ex0 (342 turnos etiquetados): regex de hoy, sin red, frente al extractor Haiku ya medido (`estabilidad-mod2-cert-claude-haiku-5-5.json`, diseño, flags de PRE) | solape regex / IA por campo | `parte2_banco.py` |
| Trazas de estabilidad de CAL (`docs/robustness/cal/estabilidad/`, 24 diálogos visibles, 327 turnos) | regex frente a extractor en PRE, con la etiqueta del turno | `parte3_trazas_pre.py` |
| Logs de PRE de las 16 rondas del 14 al 16-oct cuyo JSONL no tiene ninguna fila del oculto | lo mismo en 2.725 turnos (aún con gpt-4.1-mini de extractor) | `parte4_logs_pre.py` |
| Replay de los 95 diálogos por `supervisor.route_message` en local, SIN RED (RAG, acuse y notas fijos; Jev sin clave; el extractor devuelve las etiquetas del banco = "oráculo") | qué cambia si el detector no lee X; cobertura de líneas | `parte5_replay.py`, `parte7_diff.py`, `parte8_cobertura.py` |
| Tres lecturas del código en paralelo (núcleo, rutas/supervisor, RAG), con falsos positivos ejecutados en local | tablas de cada zona | — |

No se ha llamado a ningún modelo ni a PRE, no se ha abierto el examen G9 ni usado ningún diálogo del oculto (las rondas
con filas del oculto, como `ex10-completa`, se han dejado fuera).

## Cómo entiende hoy el bot (lo que hay que saber para leer las tablas)

1. El grafo lanza a la vez el **extractor del turno** (Haiku, con cita) y **Jev** (señales del router y preguntas).
2. En la reserva, antes de entender, `_apply_short_answer` lee la respuesta corta a la pregunta pendiente **con regex**;
   si la resuelve y el mensaje tiene ≤ 12 caracteres, **no se aplican ni el extractor ni la respuesta de Jev a la
   pregunta pendiente** ("da igual", "somos 4").
3. `_understand` llama a `intent_detector.detect()` (todo el regex) y guarda como **pista** lo que leyó en los campos del
   extractor; `_aplicar_extractor` los borra y pone los del extractor. La pista solo vuelve si el extractor falla (con
   respaldo de gpt-5.4-mini a los 2 s) o en dos reglas: la actividad principal de un grupo repartido y el "minicurso
   deducido" que se recomienda.
4. Lo que el extractor no tiene lo decide el regex sin más: duración, nº de inmersiones o de días, edades, "solo yo",
   isla y hotel del catálogo.
5. En el router y en las rutas (`orchestration/router.classify_route`, `rutas/*`) muchas decisiones son "regex O señal
   de Jev": basta el regex para pasar a una persona, contestar un texto fijo o cambiar de ruta.

Las puertas de Jev sobre el regex (`_question_turn_fields`, `_drop_regex_fields_jev_denies`) siguen corriendo y en PRE
descartan lo del regex 327 veces en 2.725 turnos, pero en los campos del extractor ya no cambian nada: la pista se copia
antes y el extractor la sustituye después.

## Lo que dicen los datos

### Banco ex0: el regex como pista sobra

| Banco ex0 | Datos acertados | Casos con invento |
|---|---|---|
| Regex de hoy (342 casos) | 152/201 (75,6 %) | 59 (17,3 %) |
| Extractor Haiku de PRE (diseño, 200 casos, voto de 3 pasadas) | 111/122 (91,0 %) | 6 (3,0 %) |

Cruce caso a caso en diseño: el regex tiene el dato que Haiku pierde en **4** ocasiones ("somos buzos certificados",
"i'm certified, just me" y "Un solo buzo avanzado" → actividad; "naci en colombia pero vivo en miami hace 10 años,
cuento como colombiano?" → nacionalidad, discutible). Se inventa lo que Haiku no en **41**: actividad 23 ("hola quiero
bucear con mi amigo" → buceo certificado; "Solicitud tarifas 2026 - Tucaya Colombia - Diving Planet" → buceo
certificado), certificación 10 ("hola quiero bucear certificado" → ya certificado), ubicación 5 ("where is the meeting
point in cartagena?" → sale de Cartagena) y grupo 3 ("Hola! Como estan? Me llamo [NOMBRE] soy buza advanced" → 1 persona).

### PRE: cuándo coinciden

| Campo (16 rondas, 2.725 turnos) | El regex leía algo | Coincide | Valor distinto | El extractor: "no lo afirma" | Solo el extractor |
|---|---|---|---|---|---|
| activity | 786 | 315 (40 %) | 153 | 318 | 232 |
| location | 357 | 213 (60 %) | 26 | 118 | 5 |
| is_certified | 308 | 187 (61 %) | 44 | 77 | 152 |
| group_size | 205 | 146 (71 %) | 29 | 30 | 155 |
| last_dive_over_2_years | 32 | 32 (100 %) | 0 | 0 | 33 |

En las trazas de CAL con etiqueta, los descartes del extractor son casi siempre buenos: "Me pasas el contacto del hotel
cocoliso?" (el regex: está en las islas), "Hi, I'm trying to checkout to take PADI Open Water Diver certification course"
(el regex: certificado y buceo certificado), "Hola!! Te contacto desde Argentina. Estaremos visitando Cartagena y queria
coordinar inmersiones en…" (el regex: islas; el extractor: Cartagena). Los 5 en que acierta el regex son la actividad
"buceo certificado" deducida de "Buzos certificados", "somos buzos certificados", "soy certificado pero no buceo hace 5
anos" o "a 2 day dive package" (el extractor no la daba si el cliente no la elegía en ese mensaje).

### Replay offline: qué cambia si el detector deja de leer

| Comparación (95 diálogos, 368 turnos, determinista) | Diálogos con estado distinto | Con respuesta distinta |
|---|---|---|
| Hoy frente a **sin la pista** de los campos del extractor | 7 | 7 |
| Sin la pista frente a **sin nada** (tampoco duración, inmersiones, edades, idioma, "solo yo") | 35 | 7 (el RAG es de mentira: en PRE estos datos sí van a su contexto y a la recomendación del plan) |
| Extractor-oráculo frente a **extractor caído** (manda el regex con su puerta) | 55 | 47 |

- De los 7 que cambian sin la pista, **6 son la actividad principal de un grupo repartido** (`nucleo/extractor._poner_actividad`
  toma la del regex: "somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel" se queda en minicurso porque es la
  primera lista del `if/elif`; sin ella, el bot pregunta la actividad). Hay que poner antes esa regla con el reparto del
  extractor (ya existe para el caso contrario: CAL-F, `actividad_del_reparto`).
- Sin duración/inmersiones/edades cambia el estado en 35 diálogos. Ahí aparecen falsos positivos reales del regex:
  "hola, estoy embarazada de 4 meses, puedo bucear?" y "llevo 3 dias esperando respuesta de mi reserva, esto es pesimo
  servicio" → varios días; "Estoy pensando en ir en unos meses de nuevo" → varios días; "el sábado pasado nosotros
  hicimos 2 buceos con uds" y "alguien que hizo el paquete con ustedes e hicieron dos inmersiones" → 2 inmersiones
  pedidas. Y uno bueno que se perdería: "los ninos tienen 6 y 9 anos" (sin el regex, en local se vuelven a pedir las edades).
- Con el extractor caído, el regex deja la conversación distinta del oráculo en 55 de 95 diálogos: como degradación es
  mala. En PRE no hizo falta ni una vez.

## Tablas por grupo

Clase y propuesta según la leyenda del resumen. "Salta" = mensajes del golden visible (de 342) en que casa algún patrón
del grupo mirado aparte (entre paréntesis, en cuántos `detect()` pone el dato); "PRE" = de los logs de las 16 rondas.
El detalle por grupo del inventario está en `estudio-ex9/grupos.csv`.

### `intent_detector.py` (403 patrones)

| Grupo (patrones) | Dónde | Qué decide | Clase · por qué | Salta | Solape IA | Propuesta · riesgo · esfuerzo | Ejemplo real |
|---|---|---|---|---|---|---|---|
| Certificación de quien escribe (104) | `certification_claim`, `holds_padi_cert`, `_WANTS_CERT_RE`, `_detect_certification` | `is_certified`; si lo tiene o lo quiere sacar | **b**: lo sustituye `_poner_certificacion`; además `course_level_is_ambiguous` solo sin certificación del extractor; `certification_is_ambiguous` muerta (veto sin llamador) | 59 (46) · PRE: coincide 61 % | `is_certified` del extractor (ex-6), `affirms_certification` de Jev | **B** · bajo: 0 rescates en el banco; quitar a la vez `_flag_cert_or_course` · M | "hola quiero bucear certificado" → ya certificado (no lo dice) |
| Hoteles e islas (86) | `_detect_location` (`hotel_patterns`, `island_patterns`) | isla y hotel para la recogida; hotel → isla (CAL-C3e) | **d**: lista cerrada del catálogo | 24 (23) · PRE: isla 45, hotel 14 (con los del extractor) | `hotel` del extractor, sin lista | **D**, pero moverla a los datos del catálogo · S | "estoy en el hotel Isla del Sol" |
| Actividad y productos nombrados (56) | `_detect_activity`, `matched_activity_categories`, `courses_mentioned` | actividad del turno; qué productos nombra | **a**, en caminos estrechos: actividad principal de un grupo repartido, `_mentioned_product_activities` (respuestas cortas de acompañante y deliberación), minicurso deducido. Como actividad del turno es b | 117 (117) · PRE: coincide 40 % | `activity` y `group_allocation` del extractor | **B** + regla de la actividad principal desde el reparto · 6 diálogos cambian en el replay · M | "hola quiero bucear con mi amigo" → buceo certificado |
| Otra persona y sujeto (37) | `_about_other_person`, `clause_subject`, `_PERSON_NOUN_*` (piezas) | si la frase habla de otro | **b** (35): piezas de la certificación y de las redes; `_CLAUSE_BOUNDARY_RE` (1) a en los vetos de la deliberación; `_FIRST_PERSON_PLURAL_RE` (1) c | piezas | `companion_joins`, `adds_person` de Jev | **C**; se van con sus usuarios · S | "Amigo el precio que está allí es en dólares o pesos colombianos" (PRE: la regex ve a otra persona, Jev no, 106 veces en total) |
| Reparto del grupo (26) | `_detect_group_info` (repartos) | `group_allocation` | **b**: lo decide `_poner_grupo` (ex-7) | 12 (4) | `group_allocation` | **B** · bajo · S | "3 certificados y 2 minicurso" |
| Duración de la estancia (22) | `_detect_duration` | un día o varios → plan recomendado | **a**: el extractor no lo tiene | 27 (27) · PRE 142 | ninguno | **E**: campo de días con cita · M | "estoy embarazada de 4 meses" → varios días |
| Cuántos son y "solo yo" (21) | `_detect_group_info` (total, `solo_confirmed`) | total; viaja solo | **a**: `_quantity_answer` (respuesta a "¿cuántos sois?") y `solo_traveler_confirmed`, que se guarda sin el extractor | 48 (34) · PRE: coincide 71 % | `group_size` ("just me" = 1) | **B** · bajo · S | "soy buza advanced" → 1 persona (no lo dice) |
| Nº de inmersiones y días (18) | `dive_counts_in`, `detect_cert_day_count` | `cert_dives`/`cert_days` → plan del catálogo | **a**: el extractor no lo tiene | 18 (16) · PRE 107 + 29 | ninguno | **D** (cifra + unidad del catálogo); que "lo elige" lo diga el extractor más adelante (E) | "el sábado pasado nosotros hicimos 2 buceos con uds" → pide 2 |
| Nacionalidad (11) | `_detect_nationality`, `nationality_is_ambiguous` | `is_colombian` | **b** | 55 (18) · PRE: Jev la descarta 9 veces | `is_colombian`, `mixed_nationality` | **B** · bajo · S | "dos somos colombianos pero uno es extranjero" |
| Origen: Cartagena o islas (4 + 6 sueltos + `place_by_role`) | `_detect_location`, `place_by_role` | `location` | **a** en `_departure_place` (respuesta corta al origen); b en `_understand` | 55 (51) · PRE: coincide 60 %, 118 "no lo afirma" | `location` (con cita) y `customer_place` de Jev | **B**; la respuesta corta, con el extractor/`pending_answer` · M | "Me pasas el contacto del hotel cocoliso?" → en las islas |
| Última inmersión (3 + 12 sueltos) | `_detect_last_dive` | `last_dive_over_2_years` | **b** | 78 (5) · PRE: siempre coincide; el extractor saca 33 más | `last_dive_over_2_years` | **B/A** · nulo · S | "si, hace 3 años que no buceo" |
| Edades (2 + ~15 sueltos) | `_detect_ages` | edades de menores | **a**: el extractor no las tiene (las completa `fill_gaps`) | 9 (5) · PRE 25 + 14 de `fill_gaps` | `fill_gaps` (LLM) | **E**: edades con cita en el extractor; el regex como validación · M | "los ninos tienen 6 y 9 anos" |
| Tokenizar (13) | `re.findall(r"\w+")`, patrones derivados del registro | — | **d** (12); el de `_detect_language` **c** (1, ver abajo) | — | — | **D** / **A** | — |

`_detect_language` decide el idioma con dos listas de palabras (no son regex; solo su tokenizador está en el inventario)
en 287 mensajes, pero `_apply_detected_intent` solo lo usa si `state.detected_language` está vacío, y la fase de setup
lo fija antes en el primer turno (`nucleo/setup.py:169`): está muerto en la práctica, y en el replay quitarlo no cambió
el idioma de ningún turno.

### Núcleo: `conversational_core.py` y `nucleo/` (91 patrones de entender)

| Grupo (patrones) | Dónde | Qué decide | Clase · por qué | Salta | Solape IA | Propuesta · riesgo · esfuerzo | Ejemplo |
|---|---|---|---|---|---|---|---|
| Acompañantes y personas (23) | `nucleo/extraction`: `_ADDED_PERSON_RE`, `_ADDITION_CUE_RE`, `_MENTIONS_PERSON_RE`, `_BARE_HEADCOUNT_RE`, `_SINGULAR_COMPANION_RE`, `_PLURAL_COMPANION_RE` | añadir un acompañante, disparar la red LLM de señales, red de menciones | **b**: la red de menciones solo sin extractor (CAL-C5); el atajo solo si el extractor no repartió; Jev manda si está seguro | 37 · PRE: "manda Jev" 106; la red de señales hizo 66 llamadas LLM | `companion_joins`, `adds_person`; reparto del extractor | **C** (11), **B** (8), **A** (4, `_PLURAL_COMPANION_RE` con la red) · M | "Si cuantos dias son?" casa por "son" |
| Respuestas cortas (13) | `nucleo/routing._apply_short_answer` | "da igual" → Cartagena; hotel "por confirmar"; edades | **a**: antes del extractor; `_LUGAR_DE_CARTAGENA_RE` (2) **c** | 14 · replay: 19 respuestas al origen pasan por aquí; la duda no casa en ninguna | `pending_answer` de Jev (su spec ya dice "delegates → cartagena"), `hotel` del extractor | **C** (7), **B** (3), **D** (1), **A** (2) · M | "no tengo idea, el Hilton creo" → hotel "por confirmar" y se pierde Hilton |
| Duda entre opciones (16) | `routing._is_deliberation_between_options` | manda el turno a comparar en el RAG aunque Jev diga que no compara | **a** | 50 sueltos, 0 de 7 en el turno | `comparing`/`opt_*` de Jev | **C** · M | "mi novia hace snorkel y yo buceo, mejor por la mañana o por la tarde" → comparación, se pierde el reparto |
| "Voy solo" (11) | `_understand` (`_COURSE_SOLO_RE`, `_NOT_ALONE_RE`) | `group_size=1` | **b**: solo si el extractor no dio grupo | 7 (0 en el turno) | `group_size` | **B** · S | "voy solo" |
| Cambio de idioma (8) | `nucleo/setup` `_SWITCH_TO_EN/ES_RE` | cambia el idioma de toda la conversación | **a** | 3 | `idioma` del extractor (solo primer turno) | **C** (pregunta nueva) · S | "¿el curso es en inglés?" → pasa a inglés (comprobado) |
| ¿Pide precio? / pista de origen (4) | `conversational_core._origen_antes_del_precio` | cambia la cotización del RAG por la pregunta del origen | **a** (el inventario lo da por guarda) | 92 sueltos · CAL: 21 cotizaciones cambiadas por la pregunta del origen | `customer_place` de Jev; `location` del extractor | **C** · M | `_PRECIO_AJENO_RE` salta con "hotel" o "noche" en cualquier parte |
| Minicurso nombrado / buceo fuerte (5) | `_mentioned_product_activities`, `_recommend_inferred_minicourse` | si se nombra el minicurso; si "buceo" es oferta de buceo certificado | **a** (3) en respuestas cortas y deliberación; **b** (2) | 22 | `activity` | **E** (3) con `_mentioned_product_activities`; **B** (2) · S | "queremos hacer el minicurso" |
| Nombre (2) | `setup._capture_client_name` | nombre para el saludo | `_NAME_TRIGGER_SIN_SOY_RE` **a** (va antes que el extractor y gana); `_NAME_TRIGGER_RE` **c** (flag `nombre_por_extractor`) | 10 sueltos | `nombre` del extractor | **B** / **A** · S | "me llamo Ana" |
| "Quiero este paquete" (2) | `routing._maybe_apply_confirmed_package` | elige el paquete que acaba de describir el bot y vacía el carrito | **a** | 0 | ninguno | **E** (campo "elige lo que propuso el bot") · M | "quiero este paquete" |
| Plan de N inmersiones para el RAG (2) | `_plan_nombrado` (`_N_INMERSIONES_RE`) | añade al contexto del RAG el plan nombrado | **a**; duplica `dive_counts_in` | 16 | — | **A**: usar `dive_counts_in` · S | "¿el precio de las 2 inmersiones? desde ese hotel" |
| ¿Hay una cifra? (2), solo un saludo (2), formato (1) | `_EXPLICIT_NUMBER_RE`, `_is_greeting_only`, `_sin_importes` | validan la cifra de la IA; saludo; texto del bot | **d** | — | — | **D** | — |

### Router, rutas y supervisor (136 patrones de entender + 19 de atajos)

| Grupo (patrones) | Dónde | Qué decide | Clase · por qué | Salta | Solape IA | Propuesta · riesgo · esfuerzo | Ejemplo |
|---|---|---|---|---|---|---|---|
| Patrones sin uso (24) | `supervisor._GENERAL_INTEREST_PATTERN`, `_BOOKING_PROCESS_QUESTION_RE` | nada | **c** | — | — | **A** · nulo · S | — |
| Disponibilidad (22) | `rutas/changes` → `classify_route` | solo la etiqueta de ruta (CHANGE delega en la cascada) | **c** | 5 | `availability_question` (tampoco cambia nada) | **A** · S | "Hay disponibilidad?" |
| ¿Trae una pregunta? (18) | `rutas/booking._looks_like_info_question` | lanza el RAG; salta los resolutores de slot | **a**: en OR con `asks_question` | 46 · replay 30 | `asks_question` de Jev | **C** (regex solo si Jev no contesta) · M | "hay un niño de 5 años" lanza el RAG |
| DIVE TO HEAL (16) | `_ADAPTIVE_DIVING_PATTERN`, `_PRICE_OR_BOOKING_Q`, `_DIVE_TO_HEAL_OVERRIDE_RE` | ruta y contexto DTH (no se apaga); precio a medida + asesor | **a** | 51 sueltos | `adaptive_diving_topic` | **C** (13); **E** (3: el precio lo dice el RAG) · S | "¿Dónde cojo la lancha al muelle?" → contexto DTH por "cojo" |
| ¿Puede bucear con N años? (12) | `rutas/info._maybe_answer_age_eligibility` | respuesta fija de edad | **a**: disparador muy amplio ("puedo", "can I"); usa además el reparto del regex | 119 sueltos · replay 6 | ninguno (edades) | **E** + **B** ya para el reparto · M | "mi hijo de 10 años y yo queremos el minicurso, ¿se puede pagar en 2 cuotas?" → solo la nota de edad |
| Notas para el RAG (8) | `rutas/contexto_rag._build_extra_context` | añade reglas (minicurso no certifica; certificado inactivo = refresher) | **a** (contexto) | 33 | estado del extractor | **B** · S | "el no es certificado" |
| ¿Eres una IA? (8, atajo) | `rutas/deflection` | respuesta fija | **a** | 1 | ninguno | **C** (pregunta nueva) · S | "qué modelo de regulador usan?" → "soy Coral, la asistente virtual" (comprobado) |
| Alcohol y alergias (7, atajo) | `classify_route` + `info_agent` | texto fijo, **antes de la puerta médica** | **a** | 0 | `sensitive_topic` de Jev; RAG | **E**: detrás de la seguridad, el alcohol al RAG · **riesgo de seguridad** · S | "estoy embarazada, ¿puedo bucear o tomar vino?" → texto del alcohol |
| Aceptar la oferta de asesor (7) | `supervisor._shared_turn_handler` | solo el texto del motivo del pase | **c** en la práctica | 0 | `wants_human` | **A** · S | "sí" tras "¿quieres que te pase con un asesor?" |
| Reinicio de escenario (6) | `rutas/router._is_new_scenario_restart` | **borra toda la memoria** antes de clasificar | **a** | 70 sueltos (saludo) | ninguno (`wants_menu_or_restart` se calcula y nadie la lee) | **C** · S-M | "Hola, somos 3 al final, ¿sigue en pie lo del sábado?" → lo borra todo |
| Grupo privado (5) | `rutas/info` | respuesta fija + pase | **a** | 0 | `needs_staff` (`pase_si_pide_fuera_del_sistema`) | **C** · S | "queremos un servicio privado de lancha para 2" → INFO y pase |
| Mención de niños (10) | `rutas/router._detect_kids_mention` | pregunta las edades | `kids_patterns` (6) **c**: inalcanzables (antes mira `kids_keywords`); normalizar (4) **d** | — | ninguno | **A**; `kids_keywords` → **E** | "cuál es el precio menor?" → pregunta edades |
| Días cerrados (4) | `nucleo/availability` | solo el texto de cierre | **a** | 0 | RAG (`closed_days` ya en contexto) | **A** · S | "vamos a estar en cartagena para año nuevo, somos 4 y queremos bucear" → solo "cerramos el 25 y el 1" |
| Mismo precio por nacionalidad (4, atajo) | `rutas/info` | solo la etiqueta (`atajo_nacionalidad_por_rag=True`) | **c** | 0 | RAG | **A** · S | — |
| ¿Corrige? (2) | `_CORRECTION_CUE_RE` | aplica una corrección sin confirmar | **a**: en OR con `corrects` | 7 | `corrects` de Jev | **C** · S | "perdón, ¿cuánto cuesta?" |
| Link roto (2) | `rutas/safety` | pase "LINK ROTO" | **a** | 1 | `broken_link_complaint` | **C** · S | "¿está mal si hago el pago mañana?" → SAFETY (comprobado) |

Fuera del inventario, con el mismo problema: `ESCALATION_KEYWORDS` ("quiero hablar con mi esposa antes de reservar" →
SAFETY, comprobado), `CONTACT_NUMBER_REQUEST_PHRASES` (~44 frases; "me mandas el link por whatsapp?" → pase, comprobado)
y las frases de cancelar/cambiar, que se aplican sin la guarda de "carrito a medio montar" que sí lleva la señal de Jev.
Propuesta C para todas. Muertas: `MENU_KEYWORDS`, `BACK_KEYWORDS`, `LANGUAGE_SELECTION_KEYWORDS` y tres más del supervisor.

### RAG (`rag_agent.py`, `vector_store.py`: 47 de entender + 9 de atajo)

| Grupo (patrones) | Qué decide | Clase · por qué | Salta | Propuesta |
|---|---|---|---|---|
| Seguimiento (12): `_FOLLOW_UP_*`, `_LOCATION_STATEMENT_PREFIX` | añade historial a la búsqueda si la búsqueda sola no trae nada fiable | **b** (red) | 86 ("y el menor tiene 6"; falso: "hola, tengo un vuelo esa misma noche despues de bucear") | **E → A**: que el reescritor cubra también los mensajes de ≥ 8 palabras y luego borrar |
| Temas de la consulta (19): `TOPIC_PATTERNS` | **solo un log** (los empujones por tema se quitaron) | **c** | 14 | **A** |
| Resumen fijo y sus acompañantes (13 + 9 atajo) | atajo apagado por `atajo_resumen_por_rag=True` | **c** | — | **A** (con ~30 tests que fuerzan el flag apagado) |
| Lugar ambiguo (2) | condición imposible; la consulta ya llega reescrita (0 veces en 76 logs) | **c** | — | **A** (dejar `AMBIGUOUS_LOCATION_NAMES`, que usa el extractor) |
| Leer la salida del juez (1) | — | **d** | — | **D** |

## Orden propuesto

Las reglas de siempre: un flag por cambio que mueva conversaciones, escalón 0 (banco o replay) y mini-ronda A/B con
`--ids` de los diálogos que cambian; nada ajustado con el oculto.

| Paso | Qué | Medida | Gana | "Entender" después |
|---|---|---|---|---|
| 0 | Arreglar el inventario (reglas por carpeta `nucleo/`, `rutas/`; las 3 "guardas" que leen al cliente; familia "lista cerrada" para hoteles y tokenizadores). Sin tocar el bot | el script | medir bien ex-9 | 569 / 776 = **73,3 %** |
| 1 | **Borrar lo muerto** (clase c: 98 + 14) y las funciones muertas (veto de `booking.py`, `_regex_contradictions`, `_quote_backs_boolean`, `_boolean_patch_is_anchored`, `_recheck_proposals`, `_named_people`, `mentions_writer_and_others`, `certification_is_ambiguous`, `_detect_language`, resumen fijo y temas del RAG, disponibilidad, "mismo precio", `kids_patterns`, `_GENERAL_INTEREST_PATTERN`…) con sus tests | suite verde + replay offline igual turno a turno (`parte5` + `parte7`: 0 diferencias) | ~112 patrones, unos cientos de líneas y unos 18 ficheros de test de caminos que PRE no corre (≈10 del veto, 8 que fuerzan el resumen fijo). Sin cambios de conversación | 471 / 664 = 70,9 % |
| 2 | **Seguridad:** alcohol y alergia detrás de la puerta médica (o que lo conteste el RAG con la política) | banco de frases (alcohol, alergia, embarazo, dolor de pecho) + mini-ronda de los diálogos de alcohol y médicos | quita el riesgo del resumen §8 | igual |
| 3 | **Quitar la pista** (clase b salvo el seguimiento del RAG, que va en el paso 6: 215): primero la regla "actividad principal = la del reparto del extractor"; decidir qué pasa si el extractor falla (recomiendo **preguntar** en vez de volver al regex: 0 fallos en 2.725 turnos y ya hay respaldo) | banco ex0 en modo `actual` con y sin pista + mini-ronda de los 7 diálogos que cambian en el replay + ronda core | −215 patrones, las puertas de Jev sobre el regex (327 descartes) y la red de menciones; adiós a los inventos del regex en la degradación (55/95 diálogos) | 256 / 449 = 57,0 % |
| 4 | **Clase a con campo existente (B, 93) y borrables (A, 6):** respuestas cortas leídas por el extractor/`pending_answer` (también con ≤ 12 caracteres), `_quantity_answer`, `_departure_place`, `solo_confirmed`, hotel "por confirmar", nombre, notas del RAG desde el estado, días cerrados al RAG, `_N_INMERSIONES_RE` → `dive_counts_in` | banco ex0 (tiene el slot pendiente) + mini-ronda | arregla "el Hilton" perdido y el hotel guardado como el mensaje entero; un solo lector por dato | 157 / 350 = 44,9 % |
| 5 | **Clase a con Jev (C, 81):** regex solo si Jev no contesta (pregunta, corrección, link roto, DTH, deliberación, grupo privado, escalado, contacto) y preguntas nuevas (cambio de idioma, "¿eres un bot?", reserva nueva, pide precio) | banco de Jev por pregunta (falsos positivos de este estudio incluidos) + mini-ronda | los falsos positivos de las tablas: pases a persona por "hablar con mi esposa", "link por whatsapp", "¿está mal si pago mañana?"; "¿el curso es en inglés?"; memoria borrada; deliberación | 76 / 269 = 28,3 % |
| 6 | **Diseño nuevo (E, 44 + 12 del RAG):** duración, edades y plan elegido en el extractor (con cita y "no lo dice" en el banco); edad mínima y precio DTH por el RAG; reescritor para mensajes largos | ampliar el banco ex0 con esos campos (Gadea resuelve las dudas) + ronda | falsos positivos de duración ("embarazada de 4 meses", "3 días esperando") y de inmersiones (buceos ya hechos); edades en una sola fuente | 20 / 213 = **9,4 %** |

Se quedan (D): hoteles e islas (86, mejor como datos del catálogo), nº de inmersiones y días (cifra + unidad del
catálogo), las cifras como validación de la IA, el saludo y los tokenizadores. Si los 20 de cifras se cuentan como
formato, "entender" queda en 0.

Los pasos 1 y 2 son independientes del resto y baratos. El 3 es el que más quita y depende de una decisión de Gadea (qué
hacer cuando el extractor falla). Los pasos 4 a 6 se pueden repartir por persona.

## Otros hallazgos

- `_N_INMERSIONES_RE` duplica `intent_detector.dive_counts_in`, que se declara la "única lectura" de N inmersiones (solo
  difieren en 1 inmersión).
- La señal de Jev `wants_menu_or_restart` se calcula en cada turno y nada la lee.
- Sin verificar de punta a punta (lo vieron las lecturas del código): la negativa de `pide_datos_ajenos` solo actúa en
  `_needs_staff_handoff`, no en la ruta de reserva; `eligibility.age_eligibility_note(10)` dice que a esa edad ya puede
  hacer Advanced y Rescue "desde los 12"; en español con el origen sabido, la marca "[origen_cliente]" va como última
  línea de la consulta y BM25 busca esa marca en vez de la pregunta.

## Límites

- El replay es offline: el RAG da una respuesta fija, Jev no está y el extractor es un oráculo (las etiquetas del banco,
  no Haiku). Sirve para ver qué cambia en el estado y en el flujo, no la calidad de la respuesta.
- Los logs de PRE son del 14 al 16-oct, con gpt-4.1-mini de extractor (Haiku desde el 18-oct). Las trazas de CAL, del
  16 al 18-oct.
- "Salta" en el golden mide si el patrón casa con el mensaje, sin las condiciones del flujo; para eso está la columna de
  `detect()` y el replay.
- La clase de cada grupo es la de su uso más fuerte (un grupo a puede actuar también como pista en otro sitio).

## Anexo: ficheros

`docs/robustness/regex/estudio-ex9/`:

- `grupos.csv`: los 232 grupos del inventario con su familia (del script y corregida), grupo funcional, clase y propuesta.
- `datos/resumen.json` (números por familia, clase, propuesta y grupo funcional), `datos/detector-golden-visible.json`,
  `datos/saltos-golden-visible.json`, `datos/banco-ex0-regex-vs-haiku.json`, `datos/pre-trazas-cal.json`,
  `datos/pre-logs-rondas-visibles.json`, `datos/replay-diferencias.json`, `datos/cobertura-funciones-replay.json`.
- `scripts/`: todo sin red y sin modelos (bloquean la red al empezar). Salidas intermedias en `ESTUDIO_OUT` (por
  defecto, la carpeta temporal). Orden: `parte1` … `parte4`, `parte6`; `parte5_replay.py --modo oraculo|caido --variante
  base|sin_dominios|sin_todo [--cobertura --trazar]` (~3 min por pasada), `parte7_diff.py A.json B.json`, `parte8`,
  `mapa.py`, `resumen.py`.
