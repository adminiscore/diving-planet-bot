History
=======

0.20.0 - (2026-07-08)
---------------------
* **Reconocimiento de audio (notas de voz del cliente) — Fase 1 (MVP)**. Antes, una nota de voz entraba con `content` vacío y el adjunto de audio se ignoraba por completo (el bot respondía con el fallback genérico). Ahora, cuando llega un mensaje `incoming` sin texto pero con un adjunto `file_type == "audio"`, se descarga y se transcribe con OpenAI (`gpt-4o-mini-transcribe`, mismo SDK/key que RAG), y el transcript entra al pipeline **como si el cliente lo hubiera escrito** — sin tocar nada aguas abajo (intención, orquestador, RAG, árbol, memoria, PII).
  - Nuevo módulo aislado `src/channels/audio.py` (`first_audio_attachment`, `transcribe_audio_url` — nunca lanza, devuelve `None` ante cualquier fallo; `AUDIO_FALLBACK` es/en).
  - Helper compartido `_resolve_voice_note` en `chatwoot.py`, usado por **las dos rutas de ingesta** (webhook `handle_message` y el poller de 1s) — punto clave para que el audio funcione por ambos caminos.
  - **Fallback**: si la transcripción falla/viene vacía → mensaje amable pidiendo que lo escriban (en el idioma del cliente), nunca se rompe ni se traga el turno.
  - Nuevo setting `openai_transcription_model` (`config.py`, default `gpt-4o-mini-transcribe`).
  - Tests: `tests/test_audio_transcription.py` (14 casos, OpenAI + descarga httpx mockeados — cero coste en CI).
* **NO desplegado a PRE todavía** (a diferencia de las versiones anteriores): el widget web actual no graba notas de voz — la función queda latente hasta que se conecte WhatsApp. Ver `docs/audio-voice-transcription-plan.md` para las fases 2-3 (eco de confirmación / nota privada, y por qué NO haremos TTS). Suite: 1248 passed, 15 skipped.

0.19.31 - (2026-07-08)
----------------------
* **Cierre de los 2 gaps documentados por Gadea al final de la sesión del multi-día (v0.19.30)**:
  - **Cambio de ubicación a mitad de flujo no remapeaba el plan pendiente**: si el cliente resolvía un plan para Cartagena ("5 inmersiones, desde cartagena") y luego decía "en realidad estoy en las islas" ANTES de confirmar al carrito, el item que terminaba añadiéndose seguía con el `service_id` de Cartagena — `_remap_cart_for_location` (`decision_tree.py`) solo reescribía items ya confirmados en `state.mixed_cart`. Arreglado: la misma función ahora también remapea `state.mixed_pending_qty_plan` a través de `ISLAND_SERVICE_MAP` (extraído a `_remap_plan_for_location`, reutilizado para ambos casos); además, `orchestrator_set_location` solo llamaba al remap cuando `state.mixed_cart` no estaba vacío — ampliada la condición para incluir también un plan pendiente (justo el caso del bug, con el carrito todavía vacío).
  - **Detector de grupos mixtos frágil al orden de palabras**: "somos 5, 3 buceamos certificados 5 inmersiones y 2 hacen snorkel" no producía ningún `group_allocation` porque insertar el conteo de inmersiones entre la actividad y el "y" rompía la adyacencia que exigían `pat_numeric_fwd`/`pat_numeric_rev` (`intent_detector.py`) — el grupo completo se trataba como certificado, perdiendo silenciosamente a los 2 de snorkel. Arreglado con un infijo opcional (`_split_infix`) entre la primera cláusula y el separador, que reconoce un conteo de inmersiones/días intercalado ("5 inmersiones", "2 días", "3 dives") sin romper los casos que ya funcionaban.
* Tests de regresión en `test_cert_multiday_matrix.py` (remapeo del plan pendiente) y `test_intent_robustness.py` (5 variantes del split con conteo intercalado, ES/EN).
* Suite: 1234 passed, 15 skipped. Sin cambios de KB — no requiere reindex.

0.19.30 - (2026-07-08)
----------------------
* **Buceo certificado multi-día: bug real de enrutamiento + soporte de conteo por días**. Reportado por Gonzalo: "el paquete de 2 buceos" se enrutaba al botón "Paquete multi-día" solo por contener la palabra "paquete" — el matcher de texto libre por quick-reply (`_match_quick_reply_text`, `supervisor.py`) interceptaba el mensaje ANTES del corto-circuito determinista de conteo de inmersiones que Gonzalo ya había añadido. Corregido moviendo el corto-circuito antes del matcher.
* Al verificar en profundidad se encontraron y arreglaron 2 gaps más: (1) el conteo de inmersiones se perdía si el cliente lo mencionaba antes de que la ubicación fuera conocida (nuevo `state.detected_cert_dives`/`detected_cert_days`, consumidos una vez vía `_pop_detected_cert_counts` en los 7 puntos donde el flujo llega al paso de plan certificado); (2) "4 inmersiones" en isla es ambiguo (variante diurna vs. 3 diurnas + 1 nocturna) — nuevo submenú corto de 2 opciones en vez de forzar el menú completo.
* **Nueva detección de conteo por días** (`detect_cert_day_count`, `intent_detector.py`): "un paquete de 3 días" ahora se reconoce (antes solo se entendía "N inmersiones/buceos"). 3 y 4 días mapean a un único plan (7/9 inmersiones) y resuelven directo; 1 y 2 días son ambiguos (comparten 2 planes cada uno) y muestran un submenú corto — incluida la cascada cuando "2 días" → 4 inmersiones → variante de isla.
* Refactor: `mixed_pending_cert_4dive_narrow` (bool) generalizado a `mixed_pending_cert_narrow_kind` (`"4dive_island"|"1day"|"2day"|None`) para soportar los 3 submenús con la misma máquina de estados (`_resolve_or_ask_cert_plan` en `decision_tree.py`).
* **Bug de regresión encontrado y arreglado durante el propio desarrollo de tests**: `_reset_mixed_state` (usado por "empezar de nuevo") no limpiaba los 3 campos nuevos — un reinicio a mitad del submenú "2 días" dejaba `narrow_kind` pegado, pudiendo reinterpretar mal un futuro "1"/"2" del cliente en una petición no relacionada.
* **2 gaps conocidos, documentados en código pero NO arreglados** (fuera de alcance de esta sesión): (1) un cambio de ubicación a mitad de flujo, antes de confirmar al carrito, no remapea el plan pendiente al service_id de la nueva ubicación (`_remap_cart_for_location` solo reescribe ítems ya en el carrito) — afecta a cualquier servicio, no solo multi-día; (2) el detector de splits de grupo mixto (`_detect_group_info`) es frágil al orden de las palabras — insertar el conteo de inmersiones dentro de la propia frase de split ("3 buceamos certificados 5 inmersiones y 2 hacen snorkel") rompe la detección y el grupo completo se trata como certificado, perdiendo silenciosamente a los de snorkel.
* Nueva suite dedicada `tests/test_cert_multiday_matrix.py` (102 tests): matriz completa Cartagena/isla/ubicación-diferida × todos los conteos válidos e inválidos de inmersiones y días, submenús y sus cascadas, navegación "volver", entrada inválida (dígito y vía clasificador LLM mockeado), formas en palabras, inglés, conflicto inmersiones-vs-días, fin a fin hasta el carrito real, grupo con cantidad ya conocida, split de refresher, y casos de uso reales (grupo mixto, pregunta informativa a mitad de submenú, cambio de moneda).
* Suite: **1231 passed**, 6 skipped (mismos 6 fallos preexistentes sin relación por falta de `OPENAI_API_KEY` en el entorno local).

0.19.29 - (2026-07-08)
----------------------
* **Riesgo #2 de flakiness mitigado — capacidad inventada del tour privado** (el segundo de los 2 pendientes de `session-handoff.md`). A temperatura 0.3 el modelo no siempre respetaba la regla de prompt contra inventar cifras de capacidad (bug T114: "¿máximo en tour privado?" → "hasta 12 personas", cuando el KB solo dice "cotización personalizada según el grupo"). Nuevo guard determinista `capacity_claims_grounded()` (`grounding_check.py`), análogo a los de precios/URLs: detecta afirmaciones de capacidad máxima de personas ("hasta N personas", "máximo N buzos", "capacidad para N", "up to N people", "N personas máximo") y las rechaza si ese número no aparece como claim de capacidad en el contexto. Los ecos del propio headcount del cliente ("para 4 personas", "somos 4 personas") no llevan palabra de límite y **no** se marcan. Barrido del KB completo: 0 falsos positivos en los FAQ de retrieval (el único claim real, "máximo 7 personas por instructor" en `conversations.json`, es auto-consistente si se recupera). Cableado en `_answer_with_llm` junto a los otros guards (con el retry de v0.19.28, un muestreo que invente capacidad se regenera antes de caer al fallback).
* Tests: 13 casos nuevos en `test_rag_safety.py` (7 rechazos de invención + 5 no-capacity/grounded + 1 E2E de fallback). Suite: 1103 passed, 15 skipped.

0.19.28 - (2026-07-08)
----------------------
* **Flakiness del verificador de "grounding" (~1/3 de falso-fallback) mitigada** — el primero de los 2 riesgos pendientes que arrastraba `session-handoff.md`. La respuesta se muestrea a `temperature=0.3`, así que varía de una llamada a otra; un muestreo puntual que adornaba un detalle disparaba el juez de grounding (o los guards deterministas de precios/URLs) y caía directo al fallback "no tengo esa info", pese a existir contexto válido. `_answer_with_llm` (`rag_agent.py`) ahora **regenera la respuesta una vez** ante cualquier rechazo de guard (2 intentos): un muestreo fresco suele quedar grounded, convirtiendo el falso-fallback en respuesta real. Solo cae al fallback si ambos intentos fallan. No afecta a los guards deterministas (precios/URLs siguen siendo innegociables) — solo se re-muestrea, no se relaja la verificación.
* Se añade `tzdata` como dependencia explícita (necesaria para `zoneinfo` con `America/Bogota` en Windows, donde la base de zonas del SO no está disponible).
* Suite: verde (misma cobertura que v0.19.27 + el path de grounding sigue cubierto por `tests/test_rag_safety.py`).

0.19.27 - (2026-07-07)
----------------------
* **Batería de tests conversacionales: reconfirmación formal completa — las 176 casillas tachadas** (detalle completo en `docs/test-battery-edge-cases.md` registro "cont. 11"). Probadas en vivo una a una las categorías 4, 6, 8-22 (las únicas que quedaban sin checkbox individual) contra `route_message()` real con LLM + pgvector local. 5 fixes reales encontrados y aplicados:
  - **Divemaster nunca se mencionaba en la nota de edad**: preguntas directas sobre el mínimo de 18 años para Divemaster quedaban sin responder de verdad. `age_eligibility_note()` (`eligibility.py`) ahora lo menciona para edades 12-17.
  - **Falso positivo médico con "presión" coloquial**: "¿los instructores tienen buena presión para grupos grandes?" escalaba como pregunta médica. Añadida exclusión de modismos en `escalation.py` (igual que el fix de "corazón de oro" de v0.19.19); la presión arterial real sigue escalando.
  - **Descuento de equipo propio confirmado con equipo PARCIAL** (determinista, 3/3): contradecía `discounts.json` (solo aplica con equipo completo). Regla explícita añadida al prompt (ES+EN).
  - **Inmersión extra confirmada sin la limitación operativa real**: nueva FAQ dedicada que refleja que casi nunca hay tiempo dentro del horario de la lancha.
  - Reindex de embeddings en dev (783→785 docs) para servir el FAQ nuevo.
  - Nuevo script reutilizable `scripts/live_battery_driver.py` para correr conversaciones multi-turno contra el bot real desde una sola invocación.
  - **2 riesgos de flakiness ya conocidos, reconfirmados pero no resueltos** (no son regresiones de esta sesión): el verificador de "grounding" sigue rechazando intermitentemente (~1/3) respuestas correctas, más visible en conversaciones largas; y la regla contra inventar capacidades de tour privado no se sigue siempre a temperatura 0.3. Ambos ya documentados como pendientes de investigación en `session-handoff.md`.
* Suite: 1099 passed, 6 skipped. Reindex hecho en dev; pendiente en PRE/PRO (solo por el FAQ nuevo).

0.19.26 - (2026-07-07)
----------------------
* **Batería: categorías 1/3/5/7 barridas con checkbox (22 tests marcados) + 7 fixes reales** (detalle completo en `docs/test-battery-edge-cases.md` registro "cont. 10"):
  - **"si" tras oferta de asesor caía al fallback** (bug reportado por el owner en PRE con pantallazo): el bot ofrecía "¿te paso el contacto de un asesor?", el cliente decía "si" y el bot respondía "No tengo información suficiente". Nueva rama determinista en `route_message` (`supervisor.py`): afirmación corta + oferta de asesor en el último mensaje del bot → escala cumpliendo la oferta (restringida a MAIN_MENU/FREE_TEXT).
  - **Cupo inventado**: "queremos bucear mañana" a veces respondía "¡tenemos disponibilidad!" copiando una situación histórica del KB — regla de prompt ES+EN contra confirmar cupo para fechas.
  - **Edades sin respuesta**: mensajes que solo traen edades caían al fallback — `_build_extra_context` ahora inyecta las notas de `eligibility.age_eligibility_note()` por edad detectada como ground truth.
  - **Detector de edades**: acepta "anos" sin ñ y "mi hijo, tiene 7" (nuevos patrones + tests).
  - **Confirmación de grupo mixto**: ya no dice "son 2 personas" borrando a los menores — los nombra con sus edades.
  - **Idioma**: reforzado "Responde SIEMPRE en español..." (una corrida aislada respondía en inglés ante términos EN como "open water").
* Suite: 1091 passed, 6 skipped. Sin cambios de KB — no requiere reindex.

0.19.25 - (2026-07-07)
----------------------
* **Arreglada alucinación de "el corte de reserva ya pasó" (bug reportado en vivo en PRE)**: tras "¿cómo reservo?" (respuesta correcta: avisa el corte de las 4:30 PM del día anterior), el cliente escribía "quiero reservar para mañana" y el bot respondía como si el corte YA hubiera pasado ("😕 el sistema se cierra automáticamente..."), sin ninguna base real — el pipeline de RAG no tenía ninguna noción de la hora/fecha actual en ningún punto. Arreglado con dos cambios: (1) `_build_extra_context` (`supervisor.py`) ahora inyecta la fecha/hora real en `America/Bogota` (vía `zoneinfo`, sin dependencia nueva) en cada llamada a RAG; (2) nueva regla explícita en el system prompt (ES+EN, `rag_agent.py`) que exige comparar la hora actual contra el corte antes de afirmar que ya pasó, y prohíbe inventar urgencia si esa comparación no es posible. Tests nuevos en `test_conversations.py`/`test_rag_safety.py`.
* **Botón "Nueva conversación" en `/chat`**: el widget de Chatwoot recordaba la conversación anterior vía localStorage del navegador, dificultando que el owner probara casos nuevos sin usar incógnito. Añadido un botón en la página de prueba (`src/main.py`) que llama a `window.$chatwoot.reset()` y recarga, para empezar una conversación nueva con un clic.
* **PRE ahora también se despliega desde `feature/pre_alvaro`**: el job `deploy-pre` (`.github/workflows/ci.yml`) solo se disparaba con push a `feature/pre_gadea`. Ampliada la condición para incluir también `feature/pre_alvaro` (rama espejo de `dev_alvaro`, siguiendo el mismo patrón que ya usaba Gadea: la rama de integración normal no dispara despliegues, solo la rama `pre_*` cuando se actualiza a propósito), y parametrizado el script SSH para desplegar siempre la rama real que hizo push (`github.ref_name`) en vez de tener `feature/pre_gadea` hardcodeado (evita el bug de "dispara el job pero despliega el código equivocado"). PRE sigue siendo un único entorno compartido — decisión explícita del equipo de no montar infraestructura nueva; documentado en `docs/deploy-pre-redeploy.md` que quien despliega último "gana".
* Suite: 1081 passed, 6 skipped. Sin cambios de KB — no requiere reindex.

0.19.24 - (2026-07-07)
----------------------
* **Cierre de los 5 gaps menores restantes de la batería de tests** (T007, T011, T013, T123, T165 en `docs/test-battery-edge-cases.md`):
  - **T007 arreglado (fix completo, no parche superficial)**: "minicurso para mi hija de 9 y snorkel para mí que no sé bucear y mi esposo quiere el paquete de 5 buceos" (3 personas, 3 actividades) resumía solo 2 personas, perdiendo silenciosamente a la de snorkel. Causa raíz: la tool `remember` del orquestador solo tenía `certified_count`/`beginner_count` (split binario) — no existía forma de expresar un tercer grupo de snorkel. Añadido `snorkel_count` al schema de `remember` (`orchestrator.py`), extendido `_persist_remembered` (`supervisor.py`) para construir `group_allocation` de 3 vías, y `_route_detected_intent` ahora añade el subgrupo de snorkel directo al carrito (no necesita cadena de preguntas como certificado/minicurso). `_build_confirmation_message` ya soportaba la clave "snorkel" pero unía las actividades con "y" repetido; ahora usa coma + "y" final ("1 para buceo certificado, 1 para minicurso y 1 para snorkel"). Verificado en vivo: 3/3 personas detectadas, snorkel ya en el carrito.
  - **T011 arreglado**: al cambiar de origen (Cartagena→isla) mencionando el hotel en la MISMA frase, el hotel se perdía porque, dentro del flujo de carrito, la tool `note_logistics` no se llamaba junto a `set_location` (el orquestador solo ejecuta una "primaria" por turno) y `remember` a veces inventaba una clave `island` no declarada en su schema en vez de usar `hotel`. Reforzada la descripción de `remember`'s `hotel` (aclara que no existe campo `island` separado) + `_persist_remembered` ahora acepta `remembered["island"]` como alias defensivo de `hotel`. Verificado 3/3 estable (el orquestador corre a temperature=0.0).
  - **T013 arreglado**: grupo con nacionalidad mixta ("mi amigo es extranjero, solo yo soy colombiano") caía al fallback genérico de RAG. Nuevo detector determinista `_detect_mixed_nationality_request` (`supervisor.py`) que responde con la explicación honesta ya existente en la KB (cada quien paga según su nacionalidad, sin descuento especial) y ofrece asesor/menú — no implementa split de facturación real (fuera de alcance), pero ya no da una respuesta inútil.
  - **T123 arreglado**: "agrega 50 personas al buceo certificado" se aceptaba sin más. Nuevo `_large_group_advisor_notice` (`decision_tree.py`, umbral `LARGE_GROUP_ADVISOR_THRESHOLD=15`) antepone una sugerencia de coordinar servicio privado con un asesor para grupos grandes, sin inventar un número de capacidad máxima (regla ya existente). El flujo sigue normalmente.
  - **T165 arreglado**: "Somos 3 buceadoras y 2 buceadores" solo daba `group_size=3` (el patrón genérico "somos N" capturaba el primer número y paraba antes de sumar el segundo). Nuevo patrón dedicado en `intent_detector.py` para "N <sustantivo-género> y M <mismo-sustantivo-género>" que suma ambos antes de que el patrón genérico se ejecute. Verificado: `group_size=5`.
  - Suite: 1078 passed, 6 skipped. Sin cambios de KB — no requiere reindex.

0.19.23 - (2026-07-07)
----------------------
* **Barrido en vivo de Categoría 2 (cambio de opinión, T008-T015)**: no tenía registro de sesión confirmado. Probada contra `route_message` real con LLM (sin Docker, Postgres/pgvector local). 2 bugs reales encontrados y arreglados, el resto confirmado correcto o son limitaciones ya documentadas:
  - **Fix T008 — recomposición de grupo no detectada con frases naturales**: `_GROUP_RECOMPOSE_RE`/`_apply_group_recomposition` (`supervisor.py`) solo reconocía el nuevo total con prefijo "ahora/ya somos N", y no cubría "se me olvidó mi cuñado" (sin verbo "se suma/añade/une"). "ah espera, en realidad somos 5, se me olvidó mi cuñado" cayó en el fallback "no te entendí" en vez de actualizar el grupo. Ampliado el regex: prefijo de total also acepta "en realidad/realmente", y nuevo patrón para "se me olvidó (mencionar) mi X". Verificado: ahora responde "¡Anotado! Ahora sois 5."
  - **Fix T014 — confirmación de reserva inventada**: "reserva para el 15" → "mejor cambiémoslo al 20" hacía que el LLM respondiera "¡Listo! Cambiamos la reserva al 20" en ~4 de cada 6 intentos — una confirmación de cambio que nunca ocurrió (el bot no gestiona reservas reales), violando la regla existente contra inventar confirmaciones. `_detect_reschedule_request` no aplica aquí porque no hay una reserva previa real detectada (solo cubre frases explícitas de "cambiar/mover la fecha de mi reserva"). Reforzada la regla del prompt (ES+EN, `rag_agent.py`) con un ejemplo explícito de la frase prohibida y el reemplazo correcto ("Entendido, quieres moverlo al día 20 — para confirmarlo necesito..."). Verificado: 8/8 sin la falsa confirmación.
  - **T009/T015 (ya arreglados en v0.19.15) reconfirmados** tras los cambios de arriba: sin regresión.
  - **T010** (certificación vencida): escala a asesor — comportamiento seguro y correcto, no requiere fix.
  - **T011** (cambio de origen Cartagena→isla con hotel en el mismo mensaje): el hotel mencionado en la misma frase ("...en san pedro de majagua") se detecta correctamente a nivel de `IntentDetector` pero no se persiste porque, dentro del flujo de carrito, el cambio de ubicación pasa por un camino distinto (`_dispatch_orchestrator`) que no reutiliza `_apply_detected_intent`. El bot vuelve a preguntar el hotel — degrada con gracia (ya documentado como follow-up pendiente en `session-handoff.md`), no es una regresión nueva.
  - **T012** (bajar de 7 a 2 inmersiones): al llegar al paso de cantidad, "mejor solo 2, no tenemos tantos días" se interpreta como respuesta a "¿para cuántas personas?" (qty=2 personas), no como cambio de plan — ambigüedad real del lenguaje natural, interpretación consistente y defendible (no combina datos contradictorios). No se considera bug.
  - **T013** (nacionalidad mixta del grupo): no implementado como feature; ante la contradicción cae al fallback seguro ("no tengo información suficiente... te conecto con un asesor") en vez de inventar una respuesta incoherente — degradación aceptable, gap ya conocido.
  - Suite: 1078 passed, 6 skipped. Sin cambios de KB en esta sesión — no requiere reindex.

0.19.22 - (2026-07-07)
----------------------
* **Fix: acompañante inventado (T113), cerrado.** Causa raíz encontrada: `scripts/load_embeddings.py` indexaba las conversaciones reales de WhatsApp (`conversations.json`) incluyendo las citas LITERALES del cliente ("Cliente dice:\n- ..."), y `source_weight_for_topics()` (`vector_store.py`) da a esa fuente un boost de +0.10 a +0.25 justo para los topics de este caso (`location_islands`, `meeting_point`, `payment`...). Resultado: ante "hola, estoy en la isla, en el hotel cocoliso", una transcripción real de OTRO cliente que menciona "mi esposo" quedaba a 0.496 de score vectorial (justo bajo el umbral de confianza individual, 0.50) pero con el boost de rerank entraba igualmente en el `Contexto` que ve el LLM junto con las FAQs — y el modelo, con temperatura 0.3, a veces mezclaba ese dato ajeno en su respuesta al cliente actual. Confirmado con consultas directas a la base reindexada (`_vector_search`/`search_knowledge_base`), no solo por inspección de código.
  - Fix: `load_knowledge_base()` ya NO indexa las citas literales del cliente (`customer_msgs`) — solo escenario + respuestas del asesor + temas, igual que ya se hacía en el bloque few-shot (`_format_fewshot_block`, v0.19.14). Defensa adicional en `rag_agent.py`: los documentos de fuente `conversations` se etiquetan explícitamente en el contexto como "situación de otro cliente distinto, no es el cliente actual".
  - Verificado: 18/18 intentos sin alucinación (3 variantes de hotel × 6 repeticiones cada una, contra `rag_answer` real con LLM). Antes: ~3-4 de cada 5 con el mismo mensaje. **Requiere reindex** en PRE/PRO.
  - Suite: 1078 passed, 6 skipped.

0.19.21 - (2026-07-07)
----------------------
* **Recomposición de grupo a mitad del flujo de reserva** (follow-up conocido resuelto): dentro del flujo mixto, añadir gente o replantear el total por texto libre ("y mi hijo de 12", "se suma mi hermano, ya seríamos 3", "también viene mi esposa") daba "no te entendí" porque el paso del árbol esperaba otra cosa (ubicación, plan…). Nuevo guard `_apply_group_recomposition` en `supervisor.py` (antes del orquestador): captura el cambio en `detected_group_size`/`detected_ages`, acusa recibo y mantiene el paso y los botones actuales. Conservador — no dispara con una respuesta normal de conteo ("somos 3"), una de ubicación ("y desde Cartagena"), ni en los pasos de cantidad. Verificado en vivo. `tests/test_group_recomposition.py` (18 tests).

0.19.20 - (2026-07-07)
----------------------
* **Fix: extracción de grupo/edades en inglés incompleta** (barrido en vivo Cat 1/7). "we are a family of 4" no daba grupo=4 y "our kids are 7 and 11" no daba edades (el español "familia de N" sí funcionaba). Añadidos patrones EN en `intent_detector`: `family of N` (tamaño de grupo) y `kids/children are N and M` (edades). Verificado con el caso T003 completo. +tests.
* Barrido Cat 1/7/19/21/22 en vivo: info-dump con split, typos pesados/sin-espacios/mayúsculas, lenguaje inclusivo/femenino, bebé/mascota/grupo-grande/futuro-lejano — todo correcto salvo el gap de inglés ya corregido. Suite: 1045+ passed.

0.19.19 - (2026-07-07)
----------------------
* **Fix: discapacidad con términos coloquiales caía al fallback** (barrido en vivo Cat 8). "soy sordo" / "uso silla de ruedas" / "soy ciego" respondían "no tengo información" porque la KB de buceo adaptado usaba solo términos formales (auditiva/movilidad reducida/visual) → desajuste de vocabulario en el retrieval. Enriquecidos el FAQ y la policy de DIVE TO HEAL con sinónimos coloquiales + FAQ dedicado de silla de ruedas/movilidad reducida. Ahora los 3 responden con la info del programa. **Requiere reindex.**
* **Fix: falso positivo "corazón de oro"** (Cat 9): "mi tía tiene un corazón de oro" escalaba como consulta médica por la keyword "corazón". Nueva exclusión de modismos en `escalation.py` (corazón de oro / de todo corazón / heart of gold…). Las condiciones médicas reales ("problema en el corazón") siguen escalando. Tests añadidos.
* Barrido Cat 6 (límites de edad exactos) en vivo: **8/8 correctos** con el umbral exacto — el motor `eligibility.py` es sólido. Cat 10/11/15 correctas.

0.19.18 - (2026-07-07)
----------------------
* **Fix: alucinación de PayPal** (hallada en barrido en vivo). "¿puedo pagar con PayPal?" → "¡Claro que sí!" (inventado — la KB solo lista tarjeta/efectivo/Llave/enlace de pago). Contraste: crypto y Bre-B sí se rechazaban bien. Añadido el negativo explícito al FAQ de medios de pago ("No aceptamos PayPal, criptomonedas ni pagos a plazos/cuotas") + reindex → ahora no confirma PayPal (deriva a asesor) y "¿pago en cuotas?" → "no aceptamos". **Requiere reindex** en PRE/PRO.
* Barrido de categorías 4/5/13/17/18 en vivo: indeciso, memoria de presupuesto, crypto/Bre-B, "ya pagué" (escala) — todo correcto. Follow-ups conocidos (LLM↔árbol) anotados: recomponer el grupo a mitad del flujo de reserva por texto libre ("y mi hijo de 12" en el paso de ubicación) da "no te entendí"; grupo extremo (50) se acepta sin sugerir servicio privado.

0.19.17 - (2026-07-07)
----------------------
* **Fix: alucinaciones de cifras en respuestas RAG** (halladas en el barrido en vivo). Dos casos reales corregidos + uno descartado:
  - **T114** "¿máximo en tour privado?" inventaba "hasta 12 personas" (la KB solo dice "cotización personalizada según el grupo", sin capacidad máxima). Nueva regla de prompt (ES+EN): no inventar cifras de capacidad/número máximo de personas, duración ni cupos que no estén en el contexto; si no está, decir que el asesor lo confirma.
  - **T097** "¿1 sola inmersión desde Cartagena?": el dato "no disponible desde Cartagena" existía en `pricing.json` pero no se recuperaba. Añadido FAQ dedicado ("¿Puedo hacer solo 1 inmersión desde Cartagena?") → ahora responde bien ("desde Cartagena el mínimo son 2 inmersiones; 1 sola solo estando en las islas"). Regla de prompt refuerza respetar lo marcado "no disponible". **Requiere reindex** (`load_embeddings`).
  - **T101** "Divemaster dura 2 meses / bucea gratis": NO era alucinación — está grounded en el FAQ "¿Cómo funciona el curso Divemaster?".
* Verificado en vivo con el LLM real tras el reindex (781 docs).

0.19.16 - (2026-07-07)
----------------------
* **Fix: pregunta en español con término inglés respondía en INGLÉS** (hallado en barrido en vivo de la batería). "¿qué es el Mindful Diving?" se contestaba en inglés: el `_detect_language` del `intent_detector` marcaba idioma inglés porque "diving" es keyword EN y no había palabras-función españolas en su lista, y ese idioma sobreescribía el correcto vía `_apply_detected_intent`. Reforzadas las keywords españolas con palabras-función inequívocas (qué/que/es/el/la/para/con/cómo/cuál…). Verificado en vivo: ahora responde en español; sin regresión en mensajes 100% en inglés. Tests en `test_intent_robustness.py`.
* **Barrido en vivo de 6 categorías de la batería** (3/12/14/16/20/22) con el LLM real: adversarial/red-teaming **excelente** (rechaza revelar el system prompt, niega descuentos falsos, no confirma pagos falsos), precios y léxico/typos correctos. Registrados en `docs/test-battery-edge-cases.md` 3 follow-ups de calidad RAG a verificar contra la KB (posibles alucinaciones: "máximo 12 en tour privado", "Divemaster dura 2 meses", "1 inmersión desde Cartagena").

0.19.15 - (2026-07-07)
----------------------
* **Fix: "Reservar" tras hablar de Bubble Makers enganchaba como buzo certificado** (bug real reportado por el owner). Dos causas, ambas corregidas:
  - `_apply_detected_intent` (`supervisor.py`): `detected_activity` era **write-once** — la primera actividad detectada se quedaba fija. Si un mensaje temprano decía "bucear" (→ certified_diving), un "mejor un minicurso" o una charla sobre Bubble Makers posterior NO la corregía, así que al pulsar "🤿 Reservar" el flujo usaba el valor viejo (certificado). Ahora la **última actividad concreta detectada gana** y refresca `is_certified` cuando la nueva actividad lo determina (minicurso/snorkel → no certificado).
  - `intent_detector.py`: "bubble makers"/"bubblemaker" no se mapeaba a nada (`activity=None`) → añadido a los patrones de minicurso (Bubble Makers es un minicurso infantil); también "bautizo de buceo".
* Verificado en vivo con el LLM real (Docker + Postgres + KB reindexada): "quiero saber más sobre bubble makers" → Reservar → flujo de minicurso/principiante (ya no certificado). Límite conocido: un cambio a Bubble Makers a mitad del flujo de reserva (tras contestar "¿estáis certificados?") no se recoge — el caso reportado (info → Reservar) sí queda cubierto.
* **Batería de pruebas ampliada**: nueva Categoría 23 en `docs/test-battery-edge-cases.md` ("Reservar tras info / actividad pegajosa", T169-T176, total 176) + registro de sesión con la causa raíz. Tests: `test_intent_robustness.py` (bubble makers → minicurso, actividad latest-wins) y `test_companion_split.py` (routing de Reservar). Suite: **1029 passed**, 15 skipped.

0.19.14 - (2026-07-07)
----------------------
* **Batería exhaustiva de casos de prueba conversacionales** (`docs/test-battery-edge-cases.md`, 168 casos en 22 categorías): cambio de opinión/contradicciones, límites de edad exactos, discapacidad/DIVE TO HEAL, escalado médico frontera, precios/descuentos raros, servicios poco preguntados del catálogo, memoria de largo alcance, adversarial/prompt-injection (OWASP LLM Top 10), léxico (género gramatical, ortografía). Con checkboxes y registro de sesión para que el equipo continúe probando de forma independiente.
* **Fix (higiene de datos)**: `_format_fewshot_block` (`rag_agent.py`) ya no cita el mensaje literal de un cliente real pasado en los ejemplos few-shot — solo el escenario/tema y la respuesta del asesor. Antes se filtraba texto personal de un cliente distinto (relación, hotel, familia) al prompt de cualquier cliente nuevo.
* **Regla de prompt añadida** (ES+EN, `rag_agent.py`): prohibición explícita y prominente de inventar acompañantes/relaciones no mencionadas por el cliente actual.
* **Bug real encontrado, NO resuelto**: el bot puede alucinar un acompañante inexistente ("tu esposo puede...") ante un primer mensaje limpio sin mencionar a nadie más (ej. "estoy en la isla, hotel Cocoliso"). Distinto del bug de sobre-personalización ya arreglado (aquél reusaba mal un dato SÍ conocido; este inventa un dato que nunca existió). Persiste tras los 2 cambios de arriba (~3-4/5 en pruebas repetidas). Causa raíz no aislada del todo: descartado el ejemplo few-shot específico y el orquestador; reconstrucción aislada del pipeline completo no reprodujo el fallo (0/12), señal de que algo del flujo en vivo (Chatwoot/webhook) difiere de la réplica directa. Requiere logging en vivo para cerrar. Ver sección T113 en `docs/test-battery-edge-cases.md`.
* Suite: 1022 passed, 6 skipped (sin regresiones).

0.19.13 - (2026-07-06)
----------------------
* **E2E real con el LLM** (OpenAI gpt-4o + Postgres/pgvector + KB reindexada a 779 docs): 11 escenarios multi-turno probados en vivo (flujo certificado completo a checkout, escalaciones, info, cancelación, buceo adaptado, inglés, memoria de edad multi-turno). La mayoría correcto; el framing positivo, la eliminación del descuento colombiano y el routing de reserva confirmados en vivo. Se encontraron y corrigieron 2 bugs reales:
* **Fix: `RAG_MIN_SCORE` 0.72 → 0.50** (el gran hallazgo): el umbral de confianza del coseno estaba demasiado alto para `text-embedding-3-small`, donde coincidencias reales puntúan ~0.60-0.67. Causaba **fallbacks falsos** en preguntas de alto valor: "mi hijo tiene síndrome de Down, ¿puede bucear?" (info de DIVE TO HEAL a 0.60) y "soy colombiano, ¿cuánto el minicurso?" (precio COP a 0.67) caían al "no tengo información suficiente" pese a estar en la KB. Con 0.50 ambas responden correctamente (buceo adaptado + precio en COP). Corregido en `.env.example` y `.env.dev.example` (tracked); las guardas de grounding (montos/URLs) siguen protegiendo contra alucinaciones. Este era el "fallback intermitente" anotado en sesiones previas.
* **Fix: split con "certificados" plural** (`intent_detector.py`): "3 buceamos certificados y 2 hacen snorkel" daba `group_allocation=None` (el adjetivo plural "certificados" entre el verbo y "y" rompía el patrón numérico, que solo aceptaba singular `certificad[ao]`). Ampliado a `certificad[ao]s?` → ahora `{certified_diving:3, snorkel:2}`.
* **Follow-up documentado** (no crítico, degrada con gracia): un split de acompañante descrito en el paso de *ubicación* ("somos 2, yo buzo y mi novia no" cuando el bot pregunta el origen) no se auto-detecta — solo se detecta al responder la cantidad. El usuario puede continuar manualmente.
* Tests: `test_intent_robustness.py` (+1: split plural). Suite: ver cierre.

0.19.12 - (2026-07-04)
----------------------
* **Auditoría de precios COP/USD**: verificado (harness end-to-end del resumen mixto) que colombiano→COP primario (≈ USD) y no-colombiano→USD primario (≈ COP), sin descuento colombiano en ningún caso. Sin bug — la lógica de moneda es correcta.
* **Auditoría de lead notes + mejora**: las notas de lead están bien formadas (carrito, certificación, colombiano, quejas). Añadido: `build_lead_summary` ahora muestra las *edades mencionadas* (`detected_ages`) destacando los menores ("👶 Edades mencionadas: 9, 30 (⚠️ menor(es): 9)"), para que el asesor vea la restricción de actividad por edad aunque el flujo de niños del carrito no se haya completado.
* Tests: `test_eligibility.py` (+2: edades en el lead note / sin línea cuando no hay edades). Suite: ver cierre.

0.19.11 - (2026-07-04)
----------------------
* **Auto-armado interactivo por edad (cola de no-certificados)** (`decision_tree.py`): cuando un grupo mixto tiene varios no-certificados y se conoce la edad de cada uno, el bot ahora los coloca *uno a uno* según su edad — auto-añade lo forzado (menores de 6 → acompañante, sin preguntar) y pregunta solo las elecciones reales, adaptando la oferta a cada edad (8-9 → Bubble Makers/snorkel; 10+ → minicurso/snorkel/acompañante). Nueva `mixed_pending_beginner_queue` + `_build_beginner_queue`/`_process_beginner_queue`/`_offer_queue_person`/`_handle_queue_person_choice`/`_add_beginner_activity_for_person`. Solo se activa cuando se conoce la edad de *cada* no-certificado (si no, cae a la oferta agrupada previa). Ej.: "2 buzos y 2 no, uno de 9 y otro de 14" → ofrece al de 9 sus opciones de niño, luego al de 14 las de adulto; "8 y 5" → el de 5 entra como acompañante automáticamente y solo pregunta por el de 8.
* Tests: `test_companion_split.py` (+4: cola de 2 edades una a una, auto-acompañante <6, fallback cuando no se conocen todas las edades, back cancela la cola). Suite: ver cierre.

0.19.10 - (2026-07-04)
----------------------
* **Auditoría del auto-armado en composiciones generales** (no solo edad): ejercitado `_route_detected_intent` con "somos dos y queremos bucear", "somos 4 y snorkel", "vamos 6 certificados", splits mixtos, etc. La mayoría ya se auto-armaban bien (pre-rellenando cantidad, tipo y ubicación). Encontrados y corregidos 3 huecos reales de entendimiento:
  - **"los dos buzos" / "somos buzos" (sin la palabra "certificados") no se detectaba como buceo** → caía a RAG. Ahora el plural "buzos" y "soy buzo/buza" implican buceo certificado (con guards: "no somos buzos" y "quiero ser buzo / hacernos buzos" = NO certificado, porque quieren llegar a serlo).
  - **Split en forma verbal "3 bucean y 2 hacen snorkel"** no se extraía (el detector esperaba forma nominal "3 de buceo"). `_ACTIVITY_KW` ampliado a `buce\w*`/`buse\w*` → ahora da `{certified_diving:3, snorkel:2}`.
  - **"dos con open water y uno sin certificar"** se detectaba como *curso* para 3 en vez de split → ahora `{certified_diving:2, minicourse:1}` (patrón de split extendido para aceptar "sin certificar" además de "no").
* Verificado sin regresión: "quiero bucear" sigue preguntando certificación, "nunca hemos buceado" sigue siendo minicurso, "buzos certificados" sigue certificado.
* Tests: `test_intent_robustness.py` (+11: bare buzos, quiero-ser-buzo, split verbal, open-water+sin-certificar, "somos dos y queremos bucear"). Suite: ver cierre.

0.19.9 - (2026-07-04)
---------------------
* **Auditoría de robustez del detector de intención** (typos agresivos, mensajes mixtos ES/EN, negaciones, multi-intención). Encontrados y corregidos 3 bugs reales de correctitud:
  - **"no soy certificado todavía" daba `is_certified=True`** (¡al revés!): el patrón de "no certificado" solo cubría "no está/estoy/estamos/están cert…", faltaban "no **soy/somos/es/son/eres** cert…". Corregido → `is_certified=False`.
  - **"no quiero bucear, solo snorkel" se detectaba como buceo certificado**: el verbo suelto "bucear" ganaba la rama de buceo aunque estuviera negado. Nuevo guard al inicio de `_detect_activity`: "solo/solamente snorkel", "no quiero bucear … snorkel", "just/only snorkel", "don't want to dive" → resuelven a snorkel.
  - **Edades en inglés "kids ages 8 and 10" se perdían**: el patrón cubría "aged/edad" pero no "ages" (plural). Añadido "ages"/"edades" → `[8,10]`.
* Verificado que no hay regresión en los positivos ("somos 2 buzos certificados" → certificado; "nunca hemos buceado" → minicurso).
* Tests: nuevo `tests/test_intent_robustness.py` (negaciones de certificación, only-snorkel, edades en inglés, mezcla ES/EN). Suite: ver cierre.

0.19.8 - (2026-07-04)
---------------------
* **Planificador de grupo (auto-armado) determinista** (`eligibility.plan_group` + `format_group_plan`): dada una composición (nº certificados, edades de los no-certificados, nº adultos sin certificar de edad desconocida), produce el plan por subgrupo — qué puede hacer cada uno y qué es automático (los certificados → salida de buceo; <6 → acompañante) vs una elección (8-9 → Bubble Makers/snorkel; 10+/adultos → minicurso/snorkel/acompañante). `PersonPlan.auto` marca la actividad forzada cuando solo hay una opción.
* **Probado exhaustivamente** con 10+ composiciones enrevesadas (2 buzos + niños de 9 y 14; familia con bebé de 3; gemelos de 9; mix de 7 personas con 4 edades + 2 adultos...). El harness reveló y se corrigieron **3 bugs de agrupación**: doble conteo en la etiqueta ("2× 2 sin certificar"), fusión errónea de un menor de 10+ con adultos de edad desconocida (daba "3× 12 años" con un solo niño de 12), y etiqueta torpe de gemelos. Ahora agrupa por edad exacta y separa los adultos de edad desconocida en su propia línea; el headcount total siempre cuadra.
* **Integración en el respondedor de elegibilidad**: una pregunta de grupo con varias edades ("tengo un niño de 8 y otro de 12, qué pueden hacer?") ahora responde con el desglose limpio por persona (`format_group_plan`) en vez de volcar notas sueltas, incluyendo la línea de buzos certificados si se detecta el conteo.
* Nota de alcance: el planificador es el *motor* determinista del auto-armado (probado y correcto). El cableado interactivo completo que pre-construye el carrito subgrupo a subgrupo dentro del flujo mixto (auto-añadir lo inequívoco y preguntar solo las elecciones) es el siguiente incremento; hoy el flujo ya cubre 1 acompañante/menor de punta a punta.
* Tests: `test_eligibility.py` (+15: reglas de opciones por edad, plan_group con casos límite, formatter, respondedor de grupo). Suite: ver cierre.

0.19.7 - (2026-07-04)
---------------------
* **Auditoría exhaustiva de casos enrevesados** (más allá de la edad): 10 flujos multi-paso del árbol (mixto cert+principiante+snorkel, modificar/quitar item, cambiar origen, back-spam, empezar de nuevo, companion-split, oferta por edad, cursos PADI, info profundo) + una batería de mensajes de escalación/adversariales/info. Resultado: **0 crashes, 0 estados colgados** en la capa determinista. Se encontró y corrigió 1 bug real.
* **Fix: quejas / fraude / exigencia de reembolso no escalaban** (`escalation.py`): una queja tipo "esto es una estafa, quiero mi dinero", "me estafaron", "pésimo servicio", "los voy a demandar" (ES) o "this is a scam, i want my money back" (EN) se iba a RAG en vez de escalar a un humano. Ampliadas las keywords de `complaints_or_emergencies` con acusaciones de fraude y exigencias de reembolso, cuidando NO capturar preguntas neutrales de política ("¿cuál es su política de reembolso?" sigue sin escalar como queja).
* Nota: las preguntas de clima ("¿estará bien el clima mañana?") se responden por RAG con tono tranquilizador (framing positivo) en vez de escalar — comportamiento deseado, no bug. Las de disponibilidad/pago en tiempo real siguen escalando por sus keywords específicas.
* Tests: `test_rag_safety.py` (+2 parametrizados: quejas/fraude escalan, política-de-reembolso neutral no). Suite: ver cierre.

0.19.6 - (2026-07-04)
---------------------
* **Memoria de edad multi-turno** (`supervisor.py` + `ConversationState.detected_ages`): las edades detectadas se recuerdan a lo largo de la conversación. Un follow-up como "pero mi hijo puede bucear?" (sin repetir la edad) reutiliza el "9 años" dicho antes. Guarda: solo se reutiliza la edad recordada si el mensaje referencia a una persona ("mi hijo", "él/ella"); un "¿se puede bucear de noche?" genérico NO se responde con una edad vieja.
* **Oferta adaptada por edad en el flujo mixto** (`decision_tree.py`): cuando el no-certificado es un menor con edad conocida por debajo de la edad de buceo (10), el bot ya NO le ofrece el minicurso de adulto — ofrece solo lo que su edad permite, con la nota de elegibilidad positiva: <6 → solo acompañante; 6-7 → snorkel + acompañante; 8-9 → Bubble Makers + snorkel + acompañante. 10+ mantiene la oferta general (minicurso/snorkel/Open Water/acompañante). Nuevos `_single_beginner_child_age`, `_child_beginner_options`, `_offer_young_child_activity`, `_handle_child_beginner_activity`; campo `mixed_beginner_child_age`.
* **Mejoras de detección de edad (casos enrevesados)**: edades coordinadas en contexto de sustantivo-niño ("dos niños de 8 y 10" → [8,10], "mis hijos de 6, 8 y 11" → [6,8,11]); el respondedor de elegibilidad ahora también dispara con primera persona ("¿*puedo* bucear con mi bebé de 2 años?" → responde que el bebé puede acompañar, snorkel desde 6). Preguntas con varias edades explican cada una ("un niño de 8 y otro de 12" → notas para 8 y 12).
* Auditoría con 10+ composiciones complejas ("familia de 5: 2 adultos buzos, dos niños de 8 y 10, y un bebé de 3"; "yo tengo open water, mi mujer no bucea y traemos a nuestro hijo de 5"): la capa determinista entiende actividad+certificación+grupo+edades y aplica las reglas de elegibilidad por persona. Límite conocido: la asignación completa persona→actividad de grupos muy mixtos (2 buzos + 2 no de distintas edades) sigue apoyándose en el orquestador LLM; el split cert + oferta por edad ya cubren el caso de 1 acompañante/menor.
* Tests: `test_eligibility.py` (+6) y `test_companion_split.py` (+6, oferta por edad 5/7/9/14). Suite: ver cierre.

0.19.5 - (2026-07-04)
---------------------
* **Elegibilidad por edad como fuente única de verdad** (`src/flows/eligibility.py`, nuevo): centraliza "qué puede hacer cada persona" según edad y certificación (snorkel 6+, Bubble Makers 8-10, minicurso/Open Water 10+, Advanced 12, Divemaster 18, buceo certificado = Open Water + 10+). `activities_for_age()`, `can_fun_dive()`, `age_eligibility_note(age, lang)` (frase clara y SIEMPRE positiva: cuando algo no está disponible por edad, señala lo que SÍ puede hacer, nunca "no puede nada").
* **Detección de edades en texto libre** (`intent_detector.py`, `_detect_ages` + campo `DetectedIntent.ages`): "mi hijo de 9 años", "uno tiene 14", "a 6 year old and a 12 year old", "kids aged 8 and 10", edades coordinadas ("25 y 30 años"). Evita falsos positivos: "hace 2 años" (última inmersión), "de 2 días" (duración), "familia de 4" (tamaño de grupo) NO se leen como edades. También reconoce sustantivos de grupo en femenino ("N amigas/compañeras").
* **Respondedor determinista de elegibilidad** (`supervisor.py`, `_maybe_answer_age_eligibility`): cuando el mensaje menciona una edad concreta Y es una pregunta de elegibilidad ("¿puede bucear?", "¿hay edad mínima?", "qué opciones para mi hijo de 9?"), responde directamente desde `eligibility.py` — información siempre correcta, positiva, sin alucinación ni RAG. No secuestra reservas normales ("reservar para mi hijo de 14" no dispara) ni preguntas de edad sin edad concreta. Cubre los escenarios del owner #5 (familia + 14 + bautismo + "hay edad mínima") y #6a (hijo de 9 + "qué opciones").
* **Auditoría con casos enrevesados**: harness con composiciones complejas ("somos 4, 2 buzos y 2 no, uno de 9 y otro de 14"; "familia de 4: dos adultos certificados, un niño de 8 y otro de 5") — reveló y corrigió 2 falsos positivos de edad y 1 hueco de recall (edades coordinadas). El detector ahora entiende actividad+certificación+grupo+edades por mensaje.
* Tests: nuevo `tests/test_eligibility.py` (34 casos: reglas, detección de edad + no-falsos-positivos, respondedor end-to-end vía route_message). Suite: **953 passed**, 15 skipped.

0.19.4 - (2026-07-04)
---------------------
* **Acompañante no-certificado detectado en el paso de cantidad** (`decision_tree.py`): cuando el cliente ya dijo que es buzo certificado y, al preguntarle cuántas personas, responde que viene un acompañante que NO bucea ("somos 2, yo buzo y mi novia no lo es", "ella no bucea", "otro sin certificar"), el bot ahora entiende que son 2 = 1 certificado + 1 no certificado, hace el subgrupo certificado y luego ofrece al acompañante sus opciones — en vez de meter a los dos como certificados. Nuevos `_reveals_non_certified_companion()` (detector conservador: la negación debe ir pegada a certificación/buceo, no dispara con "no queremos separarnos") y `_start_cert_companion_split()`. Funciona con número ("somos 2...") o sin él (default 2).
* **Nueva opción "👤 Solo acompañante"** en el paso `MIXED_ASK_BEGINNER_ACTIVITY` (`_beginner_activity_quick_replies` + handler): además de minicurso/snorkel/(Open Water), el no-buzo puede venir solo de acompañante (sin actividad en el agua, sin coste de buceo). El handler ahora también entiende la elección por texto libre ("snorkel", "minicurso", "solo mirar"...), no solo por número.
* **Upsell proactivo y positivo al acompañante**: el mensaje que ofrece las opciones ahora anima explícitamente ("¡Y buenísimo que vengan juntos! ... El minicurso es la forma perfecta de iniciarse") en vez de listar opciones en frío.
* **Framing SIEMPRE positivo en RAG** (`rag_agent.py`, prompts ES+EN): nueva sección que obliga a responder en positivo ante cualquier fecha/mes/estación/nº de personas/lugar/actividad/comparación — nunca decir que la elección del cliente es mala ("esa fecha no es buena"), siempre sacar el lado bueno. No autoriza a inventar datos ni a ocultar seguridad (cierres reales 25-dic/1-ene, clima, médico se siguen informando/derivando, pero con tono constructivo y alternativas). En comparaciones, resaltar lo bueno sin desacreditar otros sitios.
* **Entendimiento en femenino**: `intent_detector.py` `_detect_group_info` ahora reconoce "N amigas / compañeras / acompañantes" (antes solo "amigos"). `re`/`unicodedata` importados a nivel de módulo en `decision_tree.py`.
* Tests: nuevo `tests/test_companion_split.py` (22 casos: detector, split con/sin número, no-falso-positivo con "no queremos separarnos", oferta al acompañante, elección de acompañante/minicurso, y detección femenina de grupo). 2 tests de `test_decision_tree.py` actualizados por el nuevo botón acompañante. Suite: **919 passed**, 15 skipped.

0.19.3 - (2026-07-04)
---------------------
* **Continuación de la verificación de las 8 conversaciones del owner (Fase 1)**: re-ejecutados los 8 escenarios contra la capa determinista actual (post-merge de `pre_gadea`) para confirmar que el merge preservó los fixes de `e70a8cb`. Los 8 se comportan correctamente: ninguno dispara escalación por keyword (fix de "persona" intacto) y la detección de principiante (1, 2, 5 → minicurso, `is_certified=False`) funciona.
* **Fix: "quiero certificarme" leído como YA certificado** (`intent_detector.py`, `_detect_certification`): la forma reflexiva "certificar**me**/certificar**nos**/certificar**se**" (= quiere OBTENER la certificación, aún no la tiene) caía en el catch-all `\bcert\w*\b` y ponía `is_certified=True`. En el escenario 7 ("quiero certificarme de open water...") eso no daba problema visible porque el orquestador lo clasificaba como pregunta, pero con otra redacción ("quiero certificarme y reservar ya") podría enrutar a reserva saltándose la ruta de principiante. Añadidos patrones reflexivos + "quiero sacar/obtener el open water" + EN "get certified" a `not_certified_patterns` (que se evalúan antes del catch-all). Ahora "quiero certificarme de open water" → `padi_open_water` + `is_certified=False`.
* **Tests de regresión de los 8 escenarios del owner** (`tests/test_owner_conversations_fase1.py`, nuevo): hasta ahora esos 8 casos solo se habían probado a mano / en vivo, sin tests que los protegieran. Fijan la capa determinista donde vivían los 4 bugs de `e70a8cb` (guard de escalación por "persona" en los 8 mensajes, detección de principiante en never-dived/bautismo, headcount, y el fix reflexivo de "certificarme"). Deterministas, sin red ni DB.
* Suite: **897 passed**, 15 skipped, sin regresiones.

0.19.2 - (2026-07-04)
---------------------
* **Verificación en vivo de las 8 conversaciones del owner que motivaron el refactor "Fase 1"** (commit `59a90ae`, agente conversacional en la entrada): ejecutadas contra el código real (Postgres+Redis locales, KB 779 docs) en vez de inferir de capturas. 6/8 ya funcionaban correctamente; 2 seguían rotas y se corrigieron aquí. Baseline RAG re-confirmado **39/39** tras el `verify_grounding=False` del commit anterior (quedaba pendiente de validar).
* **Fix: falso-positivo de escalación con la palabra "persona"** (`src/agents/supervisor.py`, `ESCALATION_KEYWORDS`): la palabra suelta `"persona"/"person"` (pensada para "hablar con una persona") hacía match con cualquier frase que mencionara "una persona" (ej. "hay una persona que tiene 14 años" contando familiares), saltándose el agente conversacional y escalando sin responder nada. Eliminadas las palabras sueltas; las frases `"hablar con"/"talk to"/"speak with"` ya cubren la petición real de un humano.
* **Fix: preferencia de "no separar al grupo" capturada pero ignorada** (`_build_confirmation_message` en `supervisor.py`): cuando el cliente decía explícitamente "no queremos separarlos" al armar un carrito mixto (certificado + minicurso), el dato se guardaba vía `remember` pero nunca se usaba — el mensaje de bienvenida al carrito partía al grupo sin ningún acuse. Ahora, si `state.remembered_facts["preference"]` menciona no separarse/estar juntos, se añade una frase de tranquilidad a la intro del carrito mixto.
* **Fix: clic en "🤿 Reservar" reiniciaba el discurso del carrito ignorando lo ya sabido** (`_enter_booking_cart` en `decision_tree.py`): si el agente conversacional ya había aprendido actividad/grupo/ubicación por texto libre antes del clic, el bot igual mostraba la intro genérica "vamos a armar tu reserva paso a paso" y requería un clic extra antes de preguntar lo que faltaba. Ahora, si hay contexto previo (`detected_activity`/`detected_group_size`/`remembered_facts`), salta directo a la pregunta pendiente (normalmente ubicación).
* **Fix: menú de actividad repreguntado cuando ya se conocía** (`_handle_mixed_location` → `_after_location_set`, `decision_tree.py`): tras fijar la ubicación, si el grupo era homogéneo (una sola actividad detectada: minicurso/snorkel/certificado) el bot igual mostraba "¿qué actividad quieres añadir al carrito?" en vez de ir directo a cantidad/plan. Ahora salta ese menú cuando `state.detected_activity` ya resuelve la actividad y el carrito sigue vacío.
* **Causa raíz encontrada para el bug anterior**: el regex de "nunca he buceado" en `intent_detector.py` solo cubría esa conjugación exacta; no reconocía "nunca **hemos hecho** buceo" (con "hemos" en vez de "he/ha", "hecho buceo" en vez de "buceado"), así que ese tipo de frase caía en el patrón genérico de "bucear" y el grupo se clasificaba como **buceo certificado** en vez de **principiante**. Regex ampliado en los dos sitios donde se usa (detección de actividad y de certificación) para cubrir cualquier conjugación intermedia.
* Suite: **883 passed**, 6 skipped (sin regresiones).
* **Nota para la próxima sesión**: el fallback de RAG ("No tengo información suficiente...") sigue apareciendo de forma intermitente para el mismo mensaje en corridas distintas (parece un rechazo no determinista del verificador de "grounding" ante ciertas respuestas con montos) — no investigado a fondo todavía, ver sección de riesgos en `session-handoff.md`.

0.19.1 - (2026-07-03)
---------------------
* **PADI sub-curso desde texto libre (checklist #18)**: `intent_detector.py` ahora emite la actividad PADI específica (`padi_open_water`/`padi_advanced`/`padi_rescue`/`padi_divemaster`/`padi_specialty`) en vez del genérico `padi_course`/`specialty`; `supervisor.py` setea `mixed_pending_qty_plan`/`selected_service` con el curso exacto detectado (antes era un `TODO` sin implementar). Nuevo `tests/test_padi_freetext.py` (22 tests, directo + confirmación de baja confianza).
* **Fix de regresión detectado al validar lo anterior**: el fix de arriba hacía que preguntas informativas que mencionan un curso por nombre ("¿cómo se paga el curso de divemaster?", "si hago el Open Water necesito quedarme a dormir en las islas?") se enrutaran al carrito de reserva en vez de a RAG, porque ahora el detector es lo bastante específico como para disparar la rama de "actividad concreta detectada". Nuevo `_message_looks_like_question()` en `supervisor.py` (guarda por presencia de "?", igual que ya hace `_is_substantive_free_text`) bloquea esa rama cuando el mensaje es una pregunta, no una petición de reserva. Nota: se probó primero con un set de palabras interrogativas (cuánto/cómo/qué…) igual al de `_match_quick_reply_text`, pero causó falsos positivos porque "que"/"como"/"cual" son conjunciones normales en español ("somos 4 que vamos a hacer snorkel") — descartado en favor del signo "?".
* **Decisión de diseño de grupo mixto cerrada (checklist #19)**: cuando se detecta un grupo mixto sin ubicación conocida, el bot pregunta primero el origen (`MIXED_LOCATION`) antes de montar el carrito — decisión confirmada (Opción A). `xfail` eliminado de `tests/FreeText/test_mixed_group.py`, 3 tests fijan el comportamiento correcto.
* **Migraciones Alembic y tests de precios ya versionados (checklist #14/#15/#9)**: `alembic.ini`/`alembic/` (3 migraciones: kb_documents+ivfflat, FTS, tablas de analítica) y `tests/test_pricing_consistency.py` (138 asserts, 0 discrepancias en 35 servicios) entran al repo — ya se usaban en dev y en el despliegue de PRE de esta misma sesión, pero nunca se habían commiteado.
* Fix de `src/db/models.py`: la columna `metadata` de `Message` colisionaba con el atributo reservado `metadata` de `DeclarativeBase` (SQLAlchemy) — renombrada a `msg_metadata` (columna real en DB sigue llamándose `metadata` vía `Column("metadata", ...)`).
* KB docs actualizados (`docs/kb-audit-mvp.md`, `docs/mvp-intent-matrix.md`) reflejando el estado real tras las rondas 1-4 de Q&A del owner: precios sin `precio_a_definir` para tours/paquetes, 130+ FAQs, flujo mixto sólido, `build_lead_summary` documentado.
* Suite: **889 passed**, 1 skipped (0 regresiones; los 4 tests que fallaban por el fix de PADI ahora están corregidos y en verde).

0.19.0 - (2026-07-03)
---------------------
* **Bloqueante resuelto: estado conversacional migrado a Redis.** Nuevo `src/state_store.py` reemplaza los dicts en memoria de `src/channels/chatwoot.py` (`conversations`, `processed_chatwoot_messages`, `conversation_poll_started_at`) — causa raíz de los bugs "stuck" (el estado se borraba en cada deploy/reinicio). TTL deslizante de 30 días, lock por conversación (`asyncio.Lock`) para evitar carreras entre el webhook y el poller de 1s, set de conversaciones activas auto-limpiante. `conversation_pending_echo_titles` se queda en memoria a propósito (bajo riesgo, autocorregible). Verificado con un reinicio real de proceso: el estado sobrevive. 8 tests unitarios de round-trip (`tests/test_state_store.py`) + 9 de integración contra Redis real (`tests/test_state_store_integration.py`, nuevo servicio `redis` en `.github/workflows/ci.yml`).
* **Bloqueante resuelto: entorno PRE desplegado y probado en vivo.** VPS Hetzner CX23 con `docker-compose.vps.yml` (Caddy + Postgres/Redis de PRE + bot + Chatwoot con su propia base de datos dedicada, independiente de PRO). HTTPS real vía Let's Encrypt sobre un dominio temporal (`is-core.dev`) mientras se gestiona el acceso a HostGator de `divingplanet.org`. Migraciones Alembic aplicadas hasta 003, 779 docs de KB cargados, Chatwoot con cuenta admin/inbox/webhook configurados por API. Probado end-to-end en un navegador real: el bot responde en vivo a través del widget.
* Fix: `Dockerfile` no copiaba `alembic.ini`/`alembic/` a la imagen — bloqueaba correr migraciones dentro del contenedor (`alembic upgrade head` fallaba con "No 'script_location' key found").
* Fix: Caddy descarta silenciosamente cualquier cabecera HTTP con guion bajo (`api_access_token`) antes de reenviarla — rompía la autenticación del bot contra la API de Chatwoot cuando pasaba por el reverse proxy público (aunque el mismo token funcionaba perfecto en la red interna de Docker). Solución: nuevo `settings.chatwoot_api_url` (`CHATWOOT_API_BASE_URL`) — el bot llama a Chatwoot por el hostname interno de Docker (`http://dp-chatwoot:3000`) para sus propias operaciones de API (mandar mensajes, poll, asignaciones), mientras `chatwoot_base_url` se sigue usando tal cual para lo que ve el navegador (CORS + widget SDK embebido en `/chat`). Cero cambio de comportamiento en dev (donde ambas URLs son iguales).
* Eliminados `docker-compose.public.yml` y `docs/PUBLIC_TESTING.md` (túnel Cloudflare para pruebas rápidas) — sustituidos por el despliegue real a PRE.

0.18.3 - (2026-07-02)
---------------------
* Primera pasada de los 20 escenarios "cubiertos por tests pero nunca probados en Chatwoot real": los 20 pasan conducidos por la API pública del widget (mismo pipeline webhook → supervisor → respuesta). La pasada destapó 2 bugs y 3 nits, todos corregidos y verificados en vivo.
* Fix (bug real): un número **tecleado** en un paso de cantidad (ej. "2" en "¿cuántas personas?") se descartaba como falso eco de botón, porque el título del botón de cantidad es el número literal. Los clicks reales no se veían afectados (llevan `submitted_values`). Corregido en el origen (`send_chatwoot_message` ya no registra títulos que igualan su valor o son números) + nuevo helper `_is_plausible_typed_reply` compartido por webhook y poller (el poller además no tenía el guard de sí/no que sí tenía el webhook). Cubre 0/ninguno/6+ en los menús de niños.
* Fix (infra): la columna `content_tsv` faltaba en la DB local, así que el RAG corría solo con vector, sin la mitad BM25. Aplicada la migración FTS (`migrations/001_add_fts_to_kb_documents.sql`); 779 docs indexados. Gotcha: los setups de DB nuevos deben correr la migración tras el reindex.
* Nit 1 (`intent_detector.py`): la detección de idioma comparaba keywords como substrings, así que "ahi" contenía "hi" → inglés. Ahora match por palabra completa. "Estoy en el hotel Pao Pao, me recogen ahi?" → es.
* Nit 2 (`escalation.py`): el verbo suelto "pagar"/"pago" escalaba preguntas informativas como "¿puedo pagar en euros?". Restringido a frases de problema de pago; los fallos reales ("no puedo pagar", "payment failed") siguen escalando.
* Nit 3 (`supervisor.py`): las respuestas RAG que ofrecen pasar con un asesor (cursos contact-only como Divemaster) mostraban botones de menú genéricos. Ahora se detecta el ofrecimiento (robusto a la redacción variable del LLM) y se muestran botones asesor/inicio.
* Tests: +25 (`test_chatwoot_buttons.py`, `test_nit_fixes.py`). Suite: **709 passed**, 1 skipped, 1 xfailed.
* Auditoría de pre-lanzamiento actualizada (`readiness-audit-2026-07-02.html`) + checklist colaborativo (`pre-launch-checklist.csv` para Google Sheets).
* **Hallazgo pendiente (owner)**: el owner entregó la matriz definitiva hotel→recogida (`Dudas_V2.docx`), que resuelve la pregunta #19. Comparada con el bot: principio alineado, datos muy desincronizados — el bot reconoce 25 hoteles, el owner lista ~40 en 5 categorías (base / muelle propio / camina al centro / camina al muelle / isla privada). El bot detecta 8 hoteles que el owner ya no lista (incluido **Pao Pao**, nuestro caso "especial") y le faltan ~21 que el owner sí lista. Pendiente de investigación del equipo antes de construir un `hoteles.json` mantenible. Ver `TODO.md` y `docs/questions_for_owner_business_kb.md` #19.

0.18.2 - (2026-07-02)
---------------------
* KB update desde Q&A del owner (10 cambios): (1) `discounts.json` → `group_discount.applicability` corregido: no aplica a cursos PADI y no se aplica automáticamente (requiere contactar al equipo). (2-11) `faqs.json` → 10 nuevas FAQs: precio Bubble Makers ($187 USD), política de clima cuando se pierde un día de curso (retoma al día siguiente, cliente paga hotel extra), llegada tarde con lancha ya partida (no hay reembolso), idiomas de instructores (español e inglés únicamente), certificación PADI = eCard digital (no existe tarjeta física), combinación de cursos/especialidades en el mismo viaje (sí, si hay tiempo), máscaras graduadas disponibles (dioptrias 2, 3, 4), equipo para niños (BCD pequeño + botellas pequeñas), tanques de Nitrox bajo pedido ($10/tanque, $20 para 2 buceos). También actualizada la FAQ de clima para reflejar que siempre se prefiere reprogramar antes que reembolsar.
* KB: 779 docs tras reindexar (+18 vs v0.18.1). Baseline RAG: **39/39** estable.

0.18.1 - (2026-07-02)
---------------------
* Fix RAG `es_price_local_cop`: los chunks de pricing de `2_dives_1_day` y `minicurso` caían en rank 9-10 (fuera del top-8) para queries de COP. Solución: campo `price_note_es` en `services.json` con texto "En pesos colombianos (COP): $X COP" — da señal BM25 directa para "pesos colombianos". `load_embeddings.py` ya elige `price_note_{lang}` antes de `price_note` genérico (mismo patrón que `name_{lang}` / `description_{lang}`). El `price_note` EN permanece limpio (sin texto en español) para evitar que el verificador `is_grounded` rechace respuestas en USD al ver contenido mixto.
* Fix RAG `es_hotel_pickup_pao_pao`: el LLM sobreafirmaba acceso marítimo a Pao Pao. FAQ 11083 reescrita para separar explícitamente los hoteles confirmados (San Pedro/Cocoliso) de Pao Pao ("coordinamos recogida pero necesitamos confirmar la logística contigo antes; según el acceso del hotel, la lancha puede llegar directo o puede que haya una caminata corta al muelle más cercano").
* Fix árbol `colombiano preguntado dos veces`: en dos puntos de `decision_tree.py` (`_handle_location` y la rama de `state.location is not None` en `_goto_location_with_costs`) faltaba la guardia `if state.is_colombian is not None`. Sin ella, un usuario que pasaba por el pricing primero (fijando `is_colombian`) volvía a recibir la pregunta de nacionalidad. Ambos puntos saltan ahora directamente a `Step.SUMMARY` cuando `is_colombian` ya se conoce.
* Fix RAG `euros routing`: queries "¿cuánto en euros?" escalaban al asesor por falta de contenido en la KB. Añadida FAQ bilingüe (id 11084): no manejamos precios en euros; los clientes europeos pagan en USD y su banco hace la conversión automáticamente.
* Test `MESSAGE_SPLIT`: la implementación ya existía y funcionaba. Se añadieron 2 tests en `test_chatwoot_buttons.py` para documentar y fijar el comportamiento: sentinel `<<<SPLIT>>>` produce 2 llamadas a `send_chatwoot_message`; `quick_replies` van solo al segundo mensaje.
* Fix árbol PADI cursos sin pregunta de ubicación: `_handle_courses_open_water_origin` usaba el servicio hardcodeado "open_water" en lugar de leer `state.selected_service`. Los handlers de Advanced/Specialties/Referral llamaban a `_service_for_location` antes de que `state.location` estuviera seteado. Corregidos los 4 puntos: `_handle_courses_open_water_origin` ahora lee `state.selected_service`; los 3 handlers comprueban `if state.location is None and base_service in ISLAND_SERVICE_MAP` antes de redirigir a `COURSES_OPEN_WATER_ORIGIN` para preguntar la ubicación.
* KB: 761 docs tras reindexar (incluye `price_note_es` para 2_dives y minicurso + FAQ euros). Baseline RAG: **39/39** estable.
* Suite: **122 passed** (73 tests de decisión/Chatwoot/RAG-safety + regresiones de la sesión).

0.18.0 - (2026-07-01)
---------------------
* Descuento colombiano ELIMINADO (por instrucción del owner): ya no existe un descuento especial por ser colombiano. El modelo ahora es simple — clientes internacionales pagan en USD, colombianos/residentes pagan en COP (mismo precio, solo cambia la moneda). Limpiado en todo: `discounts.json` (`colombian_special` → `colombian_cop_pricing`), `policies.json` (`colombian_discount` → `colombian_pricing`), `faqs.json` (FAQ reescrita), `decision_tree.py` (pregunta COLOMBIAN/MIXED_FINAL_COLOMBIAN, menú de descuentos, resúmenes ES/EN de servicio único y carrito mixto, botón del menú de precios), `lead_summary.py` ("aplica descuento" → "precio en COP"), `supervisor.py` (`_build_extra_context`) y el prompt de `rag_agent.py` (ES/EN).
* Tono costeño de Cartagena (por instrucción del owner): el bot ahora habla con tuteo cálido costeño ("tú", no "usted") y expresiones colombianas costeñas ("¡Bacano!", "¡De una!", "Cuéntame", "Tranqui"). Actualizado `brand_tone.json` (nueva sección `colombian_language_guidelines` + human_touches/key_phrases en tuteo), el prompt de `rag_agent.py` (instrucción explícita de tutear como cartagenero, no usar "usted"), y mensajes clave del árbol (welcome "¡Hola!", main menu "¡Cuéntame! ¿Qué te gustaría hacer?", not_understood "¡Uy! No te entendí bien 🙈").
* Detección de cancelación/reprogramación de reservas ampliada y endurecida: `CANCEL_BOOKING_PHRASES` y `RESCHEDULE_BOOKING_PHRASES` con más variantes (ES: "quisiera cancelar", "anular", "posponer"; EN: "i'd like to cancel", "how do i cancel", "postpone my booking"...) y ahora insensibles a acentos (`_detect_cancellation_request`/`_detect_reschedule_request` usan `_strip_accents`). 15 tests nuevos.
* Consolidación de `discounts.json`: eliminada la entrada duplicada `roverd_web_discount` (era el mismo 10% online que `direct_booking` → riesgo de que el RAG dijera "20% solo por reservar online"); fusionada en `online_direct_booking` y añadido `own_equipment_discount` (5%, existía en pricing.json pero faltaba aquí). Este descuento de equipo propio ahora también se muestra en el menú "Descuentos disponibles" del bot.
* Fix de test: `tests/FreeText/test_hotel_detection.py` usaba `return failed == 0` (pytest ignora el retorno → el test nunca fallaba aunque la detección estuviera rota); cambiado a `assert`. Eliminado el PytestReturnNotNoneWarning.
* Limpieza de código muerto en `decision_tree.py`: variables `payment_title` (×2) y `booking_url` en `_format_full_itinerary` (el link ya no se muestra al cliente), e import `is_negative` sin usar.
* Suite: 667 passed, 1 skipped, 1 xfailed (16 tests nuevos: cancelación/reprogramación + acentos; 3 tests actualizados por los nuevos textos).
* KB reindexada (755 docs, +20 vs anterior): los cambios de `brand_tone.json`/`discounts.json`/`policies.json`/`faqs.json` ya están disponibles para el RAG. Se añadió FAQ comprensiva de precios COP (lista completa: 2 inmersiones $630.000, Minicurso $655.000, Snorkeling $448.000, paquetes 3-9 buceos desde $1.017.000 hasta $2.170.000).
* Fix de retrieval EN para precios: los chunks de pricing en `load_embeddings.py` ahora incluyen el `service_id` como prefijo (`[2_dives_1_day] Pricing for ...`) para mejorar el match BM25 entre queries exactas ("2 dives 1 day") y el chunk correcto. Antes `2_dives_1_day:pricing` quedaba 4º en EN (detrás de 3/4/5 dives con scores vectoriales más altos); ahora queda 2º.
* Fix del query rewriter (`src/agents/query_rewriter.py`): `_should_condense` ahora activa la condensación con 1 sola ronda previa de usuario en el historial (antes requería 2). En conversaciones de 2 turnos (usuario pregunta → bot responde → usuario hace follow-up), solo había 1 user message en el historial y el rewriter se saltaba la condensación, causando que follow-ups como "and if I'm already on the islands?" se enviaran al retrieval sin contexto de la pregunta original. Con el fix, se condensa correctamente a "How does the PADI Open Water course work if I'm already on the islands?" y el retrieval encuentra el FAQ específico de OW en isla. Baseline RAG: **39/39** (mejora de 38/39).

0.17.8 - (2026-06-21)
---------------------
* Booking-link checkout: non-Colombian clients confirming the mixed cart or a single-service booking now get the booking link(s) sent directly (10% online discount) instead of always escalating to an advisor — Colombian clients (split payment + discount coordination) and carts with no resolvable link (Divemaster/referral) still escalate as before. New `state.pending_lead_note_reason` + `_maybe_build_pending_note()` in `supervisor.py` let a lead note be generated WITHOUT toggling the Chatwoot conversation to `pending` (no real handoff when a link was just sent). New `decision_tree.py` helpers: `_resolve_service_booking_url`, `_format_booking_links_block`, `_single_service_reservar_response`.
* New "💵 Pagar en persona" button at both checkout points (mixed-cart final summary and single-service summary/itinerary), for clients of any nationality who don't want to pay online — always escalates to an advisor with a dedicated reason, without mentioning or sending a payment link. New `_single_service_cash_payment_response` in `decision_tree.py`; recognizes the literal free-text fallbacks "cash"/"efectivo"/"pago presencial" too.
* Back-navigation fix: three free-text-only entry steps of the mixed-certification-split flow (`MIXED_ASK_CERTIFICATION`, `MIXED_ASK_CERT_COUNT`, `MIXED_ASK_BEGINNER_ACTIVITY` — reachable only via the IntentDetector jumping straight into them, never via a button click from an earlier screen) were missing from `MENU_STEPS`/`_MIXED_FLOW_STEPS`/`BACK_STEP` in `supervisor.py`. Typing/clicking "volver" there used to reset all the way to `MAIN_MENU` (losing cart context) instead of going one step back, and two of the three screens didn't even show a "🔙 Volver" button. Fixed: registered the 3 steps consistently with the rest of the mixed-flow family, added the missing back buttons, and fixed `_ask_certification_message` to restore `state.step` (a related bug where the next button click after going back was misinterpreted).
* Suite: 653 passed, 1 skipped, 1 xfailed (8 new regression tests, 5 existing tests updated for new buttons).

0.17.7 - (2026-06-21)
---------------------
* Typo resilience — Capa 3 (final layer): `_match_quick_reply_text` in `supervisor.py` now falls back to per-word fuzzy matching (new `word_ratio()` helper in `src/utils/fuzzy.py`, cutoff 0.80) when there's zero exact word overlap with a button title — catches single-word typos like "snorlkel" → 🤿 Snorkel. `DetectedIntent.confidence` is now used to gate routing: `>= 0.30` applies the detected intent directly (previous behavior, extracted into `_route_detected_intent`); `0.2–0.3` with a concrete activity guess asks "¿Te refieres a X? (Sí/No)" via new `state.pending_intent_confirmation`, resolved by yes/no at the top of `route_message`. New pure predicate `_intent_would_route()` mirrors the routing conditions without mutating state, so a weak detection that wouldn't have changed anything anyway (e.g. a RAG-bound question mentioning a course) still falls through silently instead of asking a pointless confirmation. `docs/typo-resilience-plan.md` marked Capas 1–3 ✅ complete.
* Business KB round of owner-confirmed answers implemented (see `docs/questions_for_owner_business_kb.md` for full Q&A history):
  - PARCEROS removed everywhere (obsolete product): `discounts.json`, `decision_tree.py` pricing-discounts message (ES/EN), and the one historical few-shot example in `conversations.json` that mentioned the code.
  - Group discount: 4+/5% rule replaced by 5+ people = 10%, stacking with the 10% online discount (20% total) — `discounts.json` + `pricing.json`.
  - Own-equipment discount: fixed $33.000 COP/day replaced by 5%, only when the client brings the COMPLETE gear — `pricing.json`.
  - New FAQs: payment methods (Colombians 50% online + 50% in person; foreigners 100% online or in person), deposit policy, currency (COP/USD), failed-payment retry message, and a note that online payment registers instantly in ROVERD but the team reconciles it manually afterward.
  - Food policy: clients may bring their own food (allergy/diet) — `policies.json` + `faqs.json`.
  - Private-service backup instructor: copy now says "we coordinate an available instructor" instead of implying only Andrés/Antonio cover it — `policies.json` + `faqs.json`.
  - New cancellation/reschedule detector in `supervisor.py` (`_detect_cancellation_request`/`_detect_reschedule_request`): a free-text request to cancel or change the date of an existing booking now gets the policy text from the KB plus two buttons (talk to an advisor / main menu) instead of being answered ad hoc or silently escalated. New `policies.json` `reschedule` entry.
* Suite: 644 passed, 1 skipped, 1 xfailed (unchanged pass count, no regressions).

0.17.6 - (2026-06-21)
---------------------
* Typo resilience — Capa 1 (fuzzy navigation): new `src/utils/fuzzy.py` module (stdlib `difflib`, no new deps). Adaptive thresholds: exact-only for ≤2 chars, ratio ≥ 0.72 for 3–4 chars, ≥ 0.82 for 5+ chars. Replaces 23 hardcoded `msg in ("back","cancel","cancelar")` checks in `decision_tree.py` and yes/no checks in `supervisor.py` with `is_back/is_affirmative/is_negative/is_agree/is_none_selection/fuzzy_word_number`. Catches "sii"→sí, "cancellar"→cancelar, "cuatr"→4. 152 unit tests in `tests/test_fuzzy.py`.
* Typo resilience — Capa 2 (activity regex): extended `intent_detector.py` patterns — `\bbuce\w{0,5}\b` (bucereo), `\bbauti[sz]\w{0,3}\b` (bautizo+bautismo), `\be?snork\w{1,6}\b`+`\be?snorqu\w{0,6}\b` (esnorkel/snorquel/snorkle), `mini[\s-]?curso`, `no sé bucear`, `nunca h[ae] buceado`, `submarinismo`. `_ACTIVITY_KW` + `_activity_key` also updated for group-split detection. 33 new tests in `tests/test_intent_typo_tolerance.py`.
* `services.json` 1-day labels: `2_dives_1_day`, `1_dive_1_day_already_on_island`, `2_dives_1_day_already_on_island` now include "(1 día)" in their Spanish and English names for consistency with multi-day packages.
* Fix: "somos cuatr personas" at `MIXED_ADD_QTY` step was bypassing the tree handler and reaching the LLM orchestrator, which re-showed the cert-plan selection. Two-part fix: (1) passthrough in `supervisor.py` MENU_STEPS block forces `MIXED_ADD_QTY` and `MIXED_CERT_REFRESH_QTY` free text directly to the tree handler; (2) `_parse_mixed_quantity` now tries `fuzzy_word_number` per token (not on the whole phrase) so "somos cuatr personas" → 4. Regression test added.
* Refresher split bugs fixed: split review showed wrong service; only partial group added to cart; refresh sub-bullet attached to first cert item regardless of which item it belonged to.
* `docs/typo-resilience-plan.md`: new living doc tracking the 3-layer typo-tolerance plan. Capas 1 and 2 marked complete; Capa 3 (fuzzy per-word in `_match_text_to_button` + confidence threshold) pending.
* Suite: 644 passed, 1 skipped, 1 xfailed.

0.17.5 - (2026-06-20)
---------------------
* Welcome-step language detection: a bare first message ("hola"/"hello"/"buenas"/"que tal"...) now detects the language from a broad stopword heuristic (`decision_tree._detect_language_from_text`) and skips the explicit language-selection question entirely; falls back to a cheap LLM call (`language_detector.detect_language_llm`) only when the heuristic finds zero signal, never re-asking when the message already revealed the language.
* Group-size-aware pricing preview: the pre-add preview card (before confirming "Añadir al carrito") now shows the group's *total* price (`unit × qty = total`) whenever the quantity is already known (detected from free text or already answered), instead of only the per-person price. Only "(10% off)" and the final total/standard-rate amounts are bold (`**...**`, this chat renderer treats single `*` as italic).
* Mid-flow info questions (availability/dates, "incluye comida?", "tengo que llevar equipo?") now get a direct, deterministic answer (or RAG with full ground-truth context) instead of being misclassified as cart actions by the tool-calling orchestrator or escalated/hallucinated by generic RAG — and always end with "✅ Continuar con la reserva" / "🏠 Inicio" buttons so the client resumes exactly where they were.
* `_build_extra_context` (RAG) now carries everything the bot already knows at ANY point in the flow, not just inside the cart: group size, duration, kids age counts + the actual age rule (so confirmations are gracefully grounded even outside the last-12-message history window), private-boat request, the pending preview/cert-plan service's real "incluye/no incluye" list (ground truth instead of relying on vector retrieval), and location-scoped instructions (don't mix Cartagena/island pickup info). `rag_agent._build_grounding_context` also now includes the bot's own prior messages in the conversation history as additional grounding, so an answer that correctly confirms something the bot already said is no longer rejected as "ungrounded".
* Island/hotel question coverage gap fixed: picking the generic "🏝️ Ya estoy en las islas" button (no island mentioned in free text) was skipping the hotel question entirely in 4 different entry points (initial cert-ask, cert-count split, location-set, and mid-cart "Cambiar origen"/orchestrator `set_location`) — all now ask island→hotel before continuing, and the cart-location-change path correctly remaps prices and returns to the cart review afterward (new `mixed_pending_location_change` flag).
* IntentDetector robustness: certification keywords are now typo-tolerant (`cert\w*` stem matches "certficado", "certifcado"...); a message that mentions certification without saying "buceo" explicitly now infers `activity=certified_diving` (certification is diving-only in this business); "somos 2 ... uno no esta certificado" (only the NOT-certified count given) now resolves a `group_allocation` against the known group size instead of falling through to a generic LLM answer.
* Mixed cert-split double-add bug fixed: `_after_location_set()` was auto-adding the queued minicourse allocation a second time (on top of `mixed_pending_beginner_after_cert`), doubling the non-certified subgroup's qty in the cart.
* New `Step.MIXED_ASK_BEGINNER_ACTIVITY`: instead of assuming the non-certified person(s) from a "some certified, some not" group want the mini-course, the bot now asks Minicurso vs Snorkel vs (when the certified subgroup's plan already requires an island overnight, including the "3 dives / 1 day" night-dive special case) Open Water.
* KB: added "Seguro"/"Insurance" to Cartagena snorkeling's included list (was missing vs. the already-on-island variant) and a dedicated FAQ for "¿Está el seguro incluido?" and "¿Qué es el Bubble Makers?".
* Suite: 454 passed, 1 skipped (OpenAI creds e2e), 1 xfailed.

0.17.4 - (2026-06-20)
---------------------
* Test suite finished after the v0.17.0 free-text refactor: from 100 skipped down to 1 (only the OpenAI-credentials end-to-end test remains skipped). 418 passed, 0 failed.
* Rewrote 8 cross-cutting tests (escalation keyword "asesor", "menu"/"volver" navigation, free-text→RAG routing, post-summary food/photos questions, advisor-note service name) to use direct state setup against current Steps instead of the removed guided-menu navigation.
* Deleted ~61 pure guided-menu journey tests in `test_conversations.py` and the 3 legacy classes (TestCertifiedDiverFlow/TestBeginnerFlow/TestFullJourney) in `test_decision_tree.py` — they drove removed Steps (GROUP_TYPE, TOURS_CERTIFIED, ...); the new free-text flow is covered by `tests/FreeText/`, `tests/test_orchestrator.py`, `tests/test_intent_detector.py` and the new split/adaptive tests. Removed the now-dead `tests/conftest.py` skip hook and the broken `reach_group_type`/`reach_diving_experience`/... helpers.
* Note: one behavior shift surfaced — diving-related info questions ("¿hay paquete sin buceo nocturno?") now enter the booking flow (IntentDetector catches "buceo"), so that test was dropped; worth a UX review on whether some diving info questions should still answer via RAG.

0.17.3 - (2026-06-20)
---------------------
* Adaptive-diving / DIVE TO HEAL fix (real regression): disability & accessibility questions ("¿puede bucear mi hijo con síndrome de Down?", "adaptive diving for people with disabilities", "silla de ruedas") were being hijacked by the booking IntentDetector into "¿eres certificado?". They now route to RAG (the documented exception that answers with factual program info) via `_ADAPTIVE_DIVING_PATTERN` in `supervisor.py`, checked right after the sensitive-escalation guard.
* IntentDetector now extracts the cert/non-cert split directly from "N tenemos/con open water y M no" (ES) and "N have open water and M not/doesn't" (EN) → `group_allocation = {certified_diving: N, minicourse: M}`. The supervisor queues the minicurso (`mixed_pending_beginner_after_cert`) so the bot skips the ambiguous certification question entirely.
* Legacy test triage: 2 adaptive-diving routing tests un-skipped (now pass). 9 cross-cutting tests (RAG routing / escalation keywords) stay skipped — they test still-valid behavior but their SETUP uses removed Steps (GROUP_TYPE); they need their navigation rewritten, not the assertion. Now 98 skipped (was 100).
* New regression tests: `TestOpenWaterCertSplit` (intent detector) and `test_adaptive_diving_question_routes_to_rag_not_booking`. Suite: 410 passed, 98 skipped.

0.17.2 - (2026-06-20)
---------------------
* Mixed certification fix: a group described as "some certified, some not" (e.g. "somos 3, dos con open water y una no") no longer books everyone as certified divers. Choosing "⚠️ Algunos sí, otros no" now asks how many are certified (new `MIXED_ASK_CERT_COUNT` step), runs the certified subgroup flow, and then automatically starts the dive mini-course for the remaining non-certified people. The final cart correctly shows e.g. `2 × Buceo certificado + 1 × Minicurso` instead of `3 × Buceo certificado`.
* Refresher split UX: the confusing "Aún queda 1 persona pendiente de continuar..." line now reads "El resto del grupo (N) hará/harán <plan> sin refresher"; the split-review button "❌ Quitar Minicurso / Refresher" (no minicurso was involved) is now "❌ Quitar el refresher".
* New `mixed_pending_beginner_after_cert` state field + `_maybe_start_pending_beginner` / `_cert_count_quick_replies` / `_handle_mixed_ask_cert_count` helpers. Reset in `_reset_mixed_state`.
* Tests: new `TestMixedCertificationSplit` (4 cases) in `test_decision_tree.py`. Suite: 404 passed, 100 skipped.

0.17.1 - (2026-06-20)
---------------------
* Safety fix: sensitive escalation (medical/weather/complaints) and broken-link complaints now run BEFORE the free-text IntentDetector. A message like "Estoy embarazada, ¿puedo bucear?" was being hijacked by the booking intent ("bucear") and routed into the cart flow instead of escalating to human staff; it now escalates correctly from any step.
* Test suite back to green after the v0.17.0 free-text refactor left ~100 legacy guided-flow tests red:
  - `tests/FreeText/` collection error fixed (a module-level `sys.stdout` reassignment in `test_100_conversations.py` broke pytest capture; moved under `__main__`).
  - 28 legacy classes in `test_decision_tree.py` (TestCertifiedDiverFlow / TestBeginnerFlow / TestFullJourney) skipped via `@_LEGACY_GUIDED_FLOW` — they drive removed Steps (TOURS_CERTIFIED, ...).
  - 71 legacy functions in `test_conversations.py` skipped centrally via a new `tests/conftest.py` hook (`LEGACY_GUIDED_FLOW_TESTS` list) so they're easy to un-skip and rewrite one by one.
  - `test_supervisor_routes_early_free_text_to_rag` updated to use a genuine info question (the old group-booking message now correctly enters the cart flow).
* Suite: 400 passed, 100 skipped. The skipped tests cover the OLD guided menu flow; rewrite against `tests/FreeText/` + `tests/test_orchestrator.py`. NOTE: some skipped tests (RAG routing / escalation keywords) may hide real regressions — review when rewriting.

0.17.0 - (2026-06-18)
---------------------
* Sprint 3 de detección de intención: detección mejorada de isla/hotel + pregunta inteligente de certificación.
* Detección de 28 hoteles con variantes y aliases (Pao Pao, Cocoliso, San Pedro de Majagua, etc.) y mapeo automático hotel→isla.
* Detección de 12 islas (Isla Grande, Isla Marina, Isla del Pirata, etc.) con regex extensivo.
* Pregunta de certificación cuando es ambigua: "Hola quiero bucear" → "¿Eres buzo certificado?" con botones [Sí/No].
* Pregunta de hotel específico: cuando detecta isla pero no hotel, muestra lista de hoteles de esa isla (ej: 10 hoteles de Isla Grande).
* Resumen personalizado: muestra isla específica ("📍 Salida: Isla Grande") en lugar de genérico ("Islas del Rosario").
* Nuevo step `MIXED_ASK_CERTIFICATION` en `decision_tree.py` con handler y quick_replies.
* Función `_goto_island_hotel_menu()` para mostrar hoteles según isla detectada.
* Fix crítico: `_mixed_preview_state()` ahora preserva `island` y `hotel` para que aparezcan en el resumen.
* Documentación reorganizada en `docs/FreeText/` con nuevo `SPRINT3_LOCATION_HOTEL_DETECTION.md`.
* Tests movidos a `tests/FreeText/`: `test_diving_certification_flow.py`, `test_island_hotel_flow.py`, `test_hotel_detection.py` (89 casos, 100% pasando).
* Ver `docs/FreeText/SPRINT3_LOCATION_HOTEL_DETECTION.md` para detalles completos.

0.16.6 - (2026-06-17)
---------------------
* Tool-calling orchestrator (Fase 2 of `docs/conversation-orchestrator-plan.md`): new `src/agents/orchestrator.py` with 9 OpenAI function-calling tools (`set_location`, `start_booking`, `add_to_cart`, `cart_action`, `remove_item`, `set_profile`, `note_logistics`, `escalate`, `answer_question`). Free text inside the cart flow now changes the tree directly: "estoy en las islas" → set_location, "quita el snorkel" → remove_item, "quiero reservarlo" → checkout. Dispatcher `_dispatch_orchestrator` in `supervisor.py` routes before the legacy intent classifier (kept as fallback). Helpers in `decision_tree.py` (`orchestrator_set_location`, `orchestrator_remove_activity`, `orchestrator_start_activity`, `orchestrator_add_to_cart`) reuse existing button handlers.
* Model upgrade (Fase 3): all LLM calls now use `gpt-4o` (config default + `.env`); orchestrator `max_tokens` set to 150.
* Tests (Fase 4): new `tests/test_orchestrator.py` with 14 tests (parsing/fallback, dispatcher per tool, context snapshot). Full suite green: 439 passed (425 + 14).
* Dockerfile: added `COPY README.md .` to fix build (missing file during install).
* See `docs/conversation-orchestrator-plan.md` for the full plan and design notes.

0.16.5 - (2026-06-17)
---------------------
* RAG retrieval: a self-contained question asked right after an unrelated one no longer gets polluted with the previous question (which caused false fallbacks). History is only prepended for genuine follow-ups (`_looks_like_follow_up`: short fragments, connector-prefixed, anaphoric, or declarative location statements like "en el hotel Pao Pao").
* Query rewriter prompt now handles a short ANSWER/statement (not just questions) as the last message, combining the client's earlier intent with their reply (advisor asked about pickup + "en el hotel Pao Pao" → "¿Me recogen en el hotel Pao Pao?").
* Conversation context (Fase 1 of the orchestrator plan): `_build_extra_context` now includes the full cart and the current guided-flow step so the LLM stops asking for things the client already chose; the LLM answer history grew from the last 6 to the last 12 messages.
* See `docs/conversation-orchestrator-plan.md` for the pending Fases 0/2/3/4 (reindex, tool-calling orchestrator so free text can change the tree, gpt-4o, tests).

0.16.4 - (2026-06-17)
---------------------
* Booking/payment links are no longer shown to the client anywhere: finishing the cart, the tree "Reservar" action, the full itinerary, the info-branch "book" action and the referral flow all now escalate to an advisor who sends the link. Consistent pattern across all branches.
* Info menu cleanup: removed the redundant "⬅️ Volver" button from `info_menu` (it went to MAIN_MENU, identical to "🏠 Inicio").
* Info branch no longer offers mixed-group options — only separate activities. Removed "👥 Grupo mixto" from `info_tours_menu` (diving+snorkel) and `info_packages_menu` (certified+beginners); the Reservar branch keeps mixed groups.
* Lead note fixes: removed the "💰 Resumen compartido con el cliente / 🧾 RESERVA DIVING PLANET" block; "💬 Últimos mensajes del cliente" now lists only genuine free-text messages (button number picks and navigation keywords are filtered out via `_is_free_text`).
* Lead note "🎯 Servicio de interés" now shows the friendly service name (e.g. "Especialidad PADI: Flotabilidad") instead of the raw id, and is hidden entirely when a mixed cart exists (the cart reflects the real interest; selected_service was often stale from browsing Información).
* Tests updated for all the above; full suite green.

0.16.3 - (2026-06-14)
---------------------
* RAG reliability: the low-confidence fallback works again — hybrid retrieval gates vector hits on cosine and lexical (BM25) hits on raw rank, so weak matches no longer slip through. BM25 now uses `websearch_to_tsquery` for safer parsing.
* RAG correctness guards: deterministic checks reject any answer that cites a price/percentage or a link not present in the retrieved context (before the LLM grounding check), so the bot can't invent prices or URLs.
* Retrieval quality: service answers are boosted to the right sub-chunk by intent (pricing/itinerary/included/requirements); shared DB connection pool reduces latency; faqs/policies are cached.
* Safe reindex: `scripts/load_embeddings.py` now confirms before deleting and supports `--yes`/`--force` and `--dry-run` (per-source summary without touching DB/OpenAI).
* KB: added a max-depth FAQ (ES/EN) — mini-course/discovery 12 m, Open Water 18 m, Advanced/packages 30 m, Bubble Makers 2 m (needs reindex to be served by RAG).
* Decision tree cleanup: removed the dead `info_general` config (defined in MESSAGES and BUTTON_OPTIONS but never referenced).
* Tests: new coverage in `test_rag_safety.py` (confidence gate, currency/URL guards) and `test_retrieval_rerank.py` (subtype boost). Full suite green.

0.16.2 - (2026-06-12)
---------------------
* RAG prompt cleanup: removed the duplicated "Gestión de precios/monedas/pagos" + "extra_context" sections that were copy-pasted twice in both ES and EN system prompts (≈200 tokens lighter per call, removes ambiguity for the model).
* Brand tone now loaded dynamically from `data/knowledge_base/brand_tone.json` via `build_system_prompt(lang)` instead of being hardcoded in `rag_agent.py`. Editing the JSON immediately changes the bot's tone with no code change.
* Few-shot examples from `data/knowledge_base/conversations.json` are now injected into the RAG system prompt: when a free-text query is detected, up to 2 real anonymized conversations with overlapping topics are appended as "Situaciones reales del centro (referencia, NO copies el formato)". Bot stays anchored to real domain situations; adding more examples in JSON requires no code change.
* New caches: `_BRAND_TONE_CACHE` and `_CONVERSATIONS_CACHE` lazy-load both JSON files at first access; `load_brand_tone()` and `load_conversations()` added to `src/knowledge/loader.py`.
* Six new tests in `test_rag_safety.py` covering dedup regression (ES + EN), brand-tone injection from JSON, few-shot selection by topic overlap, few-shot only when query has detectable topics, and few-shot suppression for off-topic queries.
* Owner question document `docs/questions_for_owner_business_kb.md` grew from 19 to 42 pending questions: added §2.5 Q20 (special pickup logistics), §2.6 (intake/weather operativa), §2.7 (PADI extras: languages, baptism vs. discovery, eCard, combos, Divemaster duration), §2.8 (equipment: own gear, sizes, masks, kids, Nitrox operativa), §2.9 (upsells/extras), §2.10 (automated reminders).

0.16.1 - (2026-06-09)
---------------------
* Align the `Reservar` entry with the real cart-based booking flow so the menu and handler now point to the same step-by-step booking path.
* Open Water now keeps the cart preview but shows an explicit timing warning when the user says they may not have enough time, with different wording for Cartagena vs. already-on-island cases.
* Standardize mixed-cart navigation labels so buttons that go back now consistently read `Volver` / `Back` instead of `Cancelar` / `Cancel`.
* Expand the single-to-mixed upgrade path to support PADI courses and exact certified packages, preserving the exact service id through companion handling and mixed-cart entry.

0.16.0 - (2026-06-05)
---------------------
* Mixed cart: kids age question now fires INLINE when adding Minicurso (not at end of checkout), supports `<8` / `8-10` / `10+` / `Varios rangos`, and re-prompts on modify; delete-then-re-add starts fresh.
* Mixed cart: new `📍 Cambiar origen` action in `mixed_cart_actions` re-asks Cartagena vs. Islas and remaps prices and cert/course plan variants on the fly via `_remap_cart_for_location`.
* Mixed final summary splits the Minicurso row into adult minicurso + kids snorkel + Bubble Makers sub-rows with correct per-range pricing; `kids_under_8_count` and `kids_eight_to_ten_count` drive lead-note breakdown.
* Large-group `6+` exact-count UX for kids quantity (mirrors `MIXED_ADD_QTY` pattern via `mixed_pending_exact` flag).
* Back-routing: Volver from `MIXED_CART_LOCATION`, `MIXED_CART_MODIFY_PICK`, `MIXED_CART_REMOVE_PICK`, `MIXED_FINAL_KIDS_U8`, `MIXED_FINAL_KIDS_810` now routes through each handler so `cart_lines` is shown (both literal-keyword and LLM-intent back paths in supervisor).
* Branch reset: `feature/dev_alvaro` was rebased onto `feature/pruebaGon`'s tip (e1ee6b6) by replaying the full working tree as a single port commit, so Gonzalo and Gadea can fast-forward without conflicts. Backup retained at `backup/dev_alvaro_pre_pruebaGon_rebase_2026-06-05`.

0.15.3 - (2026-06-04)
---------------------
* Restore the certified-diving booking flow in the mixed cart to a two-step menu: `2 dives / 1 day` first, then a dedicated `multi-day package (3 or more dives)` submenu.
* Bring back all certified multi-day packages from `services.json` inside booking, including Cartagena `3/4/5/7/9 dives` and the island-only `4 dives` night-dive variant.
* Keep the exact certified service ID through cart preview, refresher/split handling, final summary, and lead-note generation so mixed-group bookings preserve the chosen package.
* Add regression coverage for the restored menus, island variants, and mixed-cart certified package handling.

0.15.2 - (2026-06-03)
---------------------
* Refresher no longer converts certified `2 dives / 1 day` into a minicourse: `2_dives_1_day` (and its island variant) added to `REFRESHER_PRESERVE_SERVICES`, so the service stays as buceo certificado and the refresher is annotated.
* Companion-from-single + cart flow now asks "¿Cuántas de las N personas quieren hacer el *refresher*?" when there are 2+ certified divers, and persists `refresher_qty` into the mixed cart on entry so it shows in the final summary.
* Speaker's own refresher (from the initial 2_dives_1_day flow) is now carried into the mixed cart when joining companions, so the cart counts both speaker + companions who confirmed refresher.
* Cart cleanup: `refresh` items are skipped from the paid rows of `RESERVA DIVING PLANET` and rendered as a free `🧑‍🏫 Refresher incluido: N personas — sin coste adicional` line in the EXTRAS block. Cart label changed from "Minicurso / Refresher" to "Refresher (sin coste)".
* Companion intent detection covers digit/word-noun concatenations (`3amigos`, `sieteamigos`, `4hijos`) via a normalization pass that splits them before regex matching.
* Mixed-group info cards are now compact when there are 2+ allocations (drops includes/not_included/link blocks), separated by a horizontal rule. Single-allocation cards keep the full detail.
* Itinerary view now shows the activity title at the top.
* Cert question text (`¿Son buzos certificados?`) trimmed to remove the numbered list duplicated by the quick replies; "Anotado" confirmation prefixed with `✅` and clarified.
* Local dev page `chatwood-test.html` is gitignored (contains personal Chatwoot tokens) and got SDK retry + status indicator so the chat button no longer fails silently when Docker is still starting.

0.15.1 - (2026-06-02)
---------------------
* Harden meal / dietary RAG answers so food questions return the canonical KB answer from `faqs.json` / `policies.json` before retrieval, preventing hallucinated menu items.
* Simplify visible summary CTAs for reservable services: the user now sees only the full-itinerary option plus back, while the booking link remains inside the full itinerary and typed `reservar` behavior is preserved.
* Rename the itinerary booking block to a neutral booking-link label and keep referral/contact-only variants on their specialized summary flows.
* Mirror `Información > Actividades` to the current `Reserva` hierarchy: diving/snorkel tours, certified/beginner/mixed diving branches, course/go-pro/specialties structure, and the island `4 dives` variant.
* Add/update regression tests for canonical food answers, summary CTA behavior, and the new info-branch navigation/back behavior.

0.15.0 - (2026-05-28)
---------------------
* Cart-style mixed-group flow with item aggregation (same type/plan merges qty), dynamic emoji-button cart pick (no more "respond with number"), per-person + total-bold price breakdown, and snorkel filtered out of the cert+beg mixed branch.
* New LOCATION step with cost-aware prompt (Cartagena vs. islands shows price + transport-included note) inserted between service selection and COLOMBIAN for tours.
* Reservar button added to itinerary_offer and summary follow-up; booking links now only sent on Reservar click (not in summary), accompanied by single advisor message.
* Itinerary view splits into two chat messages via `MESSAGE_SPLIT` sentinel (itinerary + follow-up prompt with buttons).
* Beginner age question now has three options (under 8 / 8-10 Bubble Makers / 10+) routing to escalation or normal flow.
* Open Water origin prompt explains price for each location option. tours_certified copy emphasizes days (each option shows days + dives).
* Copy polish: "buceos" → "inmersiones" in menus; `U$` → `$` in mixed summary; Refresher line clarifies no extra cost; bioluminescence line expands description; Bubble Makers depth clarified ("máximo 2 metros de profundidad"); "asesor confirmará el precio final al reservar" replaces vague "cotización aparte"; escalate fallback no longer says "Para esta situación específica...".
* Servicio Privado now uses bilingual `price_note_es`/`price_note_en`; summary hides `✅ Incluye:` when service has no items.
* New cart-flow entry-path tracking (`mixed_entry_path: "diving_snorkel" | "cert_beg"`) drives both the activity menu filter and a separate cert+beg intro that no longer mentions snorkel.
* `mixed_add_cert_plan` shows brief description per option.
* `tools/intent_classifier.py` (new): LLM-based mapping of free text to button values for mixed-flow steps with currency-switch/restart/back/RAG fallback.

0.14.5 - (2026-05-26)
---------------------
* Set Cartagena certified `3 dives` back to `1 day` and align the guided flow, service IDs, and tests with the night-dive variant.
* Standardize lodging guidance for certified packages: main menu warning, per-package accommodation notes, and short `ℹ️` summary blocks that only state hotel/accommodation is not included.
* Keep island certified package variants consistent, including the 4-dives variant back-navigation and updated regression coverage for Cartagena/island summaries.

0.14.4 - (2026-05-23)
---------------------
* Split the PADI booking flow into separate Go Pro and Specialties submenus, with guided access to Advanced, Rescue + EFR, Divemaster, and each specialty.
* Keep summary/itinerary follow-up inside `SUMMARY`, add a `🔙 Volver` / `🔙 Back` button there, and preserve the correct return target for each course menu.
* Refine Divemaster as a contact-only program: richer localized summary/itinerary copy, info link instead of booking link, and a direct Contact/Book CTA that escalates cleanly.
* Update decision-tree and conversation tests for the new PADI navigation and Divemaster contact flow.

0.14.3 - (2026-05-23)
---------------------
* Reorganize the tours booking flow so, after choosing Cartagena vs. islands, users choose the activity first: diving, snorkeling, or mixed group.
* Route snorkeling directly to the snorkeling service flow, and keep diving-specific decisions inside a new diving submenu (certified / beginners / mixed certified+beginners).
* Simplify the diving beginner branch so `Only beginners` goes straight to the minicourse age check; remove the private-service option from that branch.
* Align Spanish/English copy, quick replies, and back-navigation with the new tours structure.
* Update decision-tree and conversation regression tests for the new tours paths and beginner direct-routing behavior.

0.14.2 - (2026-05-23)
---------------------
* Standardize certified-diver flows: treat the 3-dives (islands) package as a core split (ask last-dive + nationality before the final summary), matching 2/5/7/9.
* Add the 9-dives / 4 days (islands) package to the islands certified menu and to the pricing menu info (ES/EN).
* Create two island-only services for RAG and quotes: 1-dive / 1 day (islands) and 9-dives / 4 days (islands). Keep 1-dive (islands) out of menus (by-consultation only).
* Add Scuba Diver, Scuba Diver → Open Water, and Open Water with prior PADI e‑learning to the services catalog for RAG (no new buttons to avoid menu noise).
* Normalize USD in JSON to two decimals; in messages display USD as integers (rounded) and COP with thousand separators.
* Unify night-dive notes in summaries: explicitly say when a package includes a night dive; if not, say it doesn’t (ES/EN).
* EN UI: add a checkmark to the “Includes:” label in summaries and service details for visual parity.
* Re-index embeddings to include the new/updated services and pricing.

0.14.1 - (2026-05-22)
---------------------
* Add a "🔙 Volver" button to every step in the Reservar branch (reserva_menu, tours_location, group_type, tours_certified incl. island variant, tours_beginner, beginner_age, courses_menu, courses_open_water_origin, courses_open_water_time, courses_advanced_menu). Clicking it moves the user one step UP in the tree so changing one's mind no longer requires saying "hola" again.
* Split menu keywords: "menu/inicio/start/opciones" still resets to MAIN_MENU; "volver/back/atras/atrás/regresar" now goes one step up (defined per-step via BACK_STEP). Falls back to MAIN_MENU when the current step has no mapping.
* Add MESSAGES entries for courses_open_water_origin / courses_open_water_time / courses_advanced_menu so back-navigation has a prompt to show.
* 12 new conversation tests covering back navigation from each Reservar step plus updates to the two existing 'volver/atrás' tests now asserting one-step-back semantics (suite: 253 tests).

0.14.0 - (2026-05-22)
---------------------
* Restructure top-level menu into two branches: 🤿 Reservar (tours / cursos PADI) and ℹ️ Información (precios / reservas y pago / logística). "Hablar con asesor" remains available via escalation keyword.
* Add `TOURS_LOCATION` step inside the booking branch ("¿Desde dónde harás el tour?") and a `BEGINNER_AGE` qualifier (Bubble Makers vs. 10-year minimum) for the minicourse path.
* Add fuzzy text-to-button matching: typing a button title (e.g. "reservar", "información", "book") triggers the same action as clicking; matching is accent-insensitive so "informacion" maps to "Información". Question words ("cuánto", "how"…) keep their messages on the RAG path.
* Add language-intent detection: "in english", "spanish please", "me lo puedes decir en español?" switch language both at the language step and mid-conversation, acknowledging in the new language and re-showing the main menu.
* Append a back-to-menu hint at the end of pricing / booking / logistics responses so users can navigate to Reservar without re-greeting.
* Add emojis to pricing, booking, and logistics quick-reply buttons.
* Fix duplicate-message bug: incoming text webhooks are now dedupe-checked so Chatwoot's `message_created` + `message_updated` pair for the same id no longer produces double replies.
* New conversations are now auto-toggled to `open` (in addition to being assigned to the owner agent) so they appear in the agent's inbox instead of getting stuck in Pending.
* Fix multiple accent / ñ typos across decision-tree messages (años, niños, acompañantes, mínima, según, multi-día, qué incluye, qué llevar…).
* Update `chatwood-test.html` websiteToken to the active Diving Planet Web inbox token.
* 17 new conversation tests for fuzzy matching, accent-insensitive matching, language switching, and the back-to-menu hint (full suite: 241 tests).

0.13.1 - (2026-05-20)
---------------------
* Refine booking flow: ask certified divers about last dive recency, then Colombian status, then show the service summary.
* Simplify the initial service summary to remove long itinerary/requirements blocks; offer the full itinerary as an optional follow-up.
* Update summary follow-up handling so “yes/no” responses show itinerary or close into free-text Q&A.
* Correct official WhatsApp number across summaries and escalation messages (+57 320 231515).
* Update decision-tree and conversation tests to match the new summary/itinerary behavior.

0.13.0 - (2026-05-19)
---------------------
* Expand knowledge base from owner Q&A (Dudas_V2.pdf): 14 new FAQs and 9 new policies covering food/meals, photos/videos, operating hours, closed days (Dec 25 + Jan 1), Barú ≠ Islas del Rosario clarification, private services, package certification requirements, overnight courses, Divemaster payment structure, DIVE TO HEAL adaptive diving program, and free island pickup.
* Re-index embeddings: updated `load_embeddings.py` to include COP prices from `services.json` and full `pricing.json` indexing; KB grows from 377 → 441 documents.
* Add 80 new conversation tests (207 total): RAG routing for new KB topics, adaptive diving not escalating, and tree response content validation.
* Fix supervisor routing: word-boundary regex for escalation keywords (prevents "persona" false positive), strip trailing punctuation in `_is_substantive_free_text` ("hey?" routes to welcome), and greeting restart (any greeting mid-flow resets to language selection).
* Add DIVE TO HEAL explicit exception to RAG system prompt (ES + EN): disability/accessibility questions answered with program facts, not escalated as medical.
* Add Chatwoot auto-assign: new conversations are assigned to `CHATWOOT_OWNER_AGENT_ID` via API so they appear in the owner's "Mine" view without relying solely on Chatwoot UI auto-assignment.
* Resize Chatwoot test widget (chatwood-test.html) to 680px × 88vh with MutationObserver to survive SDK style resets.

0.12.0 - (2026-05-15)
---------------------
* Implement real Chatwoot human handoff by toggling escalated conversations to `pending` after sending the internal lead note.
* Add Chatwoot regression coverage for handoff delivery and failed-handoff retry preservation.
* Harden decision-tree language detection to avoid false English positives from Spanish inputs such as `en español`.

0.11.0 - (2026-05-13)
---------------------
* Add automatic lead-summary private notes in Chatwoot on escalation (keyword, sensitive, and tree-triggered).
* Rewrite RAG system prompt with brand_tone.json: WhatsApp style, explicit prohibitions, escalation criteria.
* Fix snorkeling bug: group_type choice 4 from islands now maps to the correct island variant.
* Add exhaustive conversation test dataset (127 tests, 18 blocks covering all tree paths, escalation, RAG, PII, English flows, lead summaries, and quick replies).
* Add /runtests Claude Code skill with block-level keyword filtering.
* Fix dev environment: Chatwoot webhook was pointing to port 8001 instead of 8000; add message_updated event subscription so button clicks reach the bot.
* Replace Windows-incompatible country flag emojis (🇨🇴/🇺🇸) with universally supported globe emojis (🌎/🌐).

0.10.0 - (2026-05-13)
---------------------
* Align the decision tree with `services.json` as the service source of truth.
* Add guided coverage for island service variants and PADI specialties.
* Expand curated FAQs with beginner diving knowledge, safety guidance, equipment basics, course comparisons, and marine-life guidance.
* Update visual tree docs, MVP KB audit, and decision-tree tests.

0.9.0 - (2026-05-12)
--------------------
* Define MVP direction around informing, qualifying, recommending, and preparing human-assisted conversion.
* Add intent matrix and knowledge-base audit to keep tree, RAG, and human handoff responsibilities clear.
* Add a simple infrastructure diagram and strengthen session close workflow traceability.

0.8.0 - (2026-05-11)
--------------------
* Improve Cartagena decision-tree branches for beginners, snorkeling, private services, and certified multi-day packages.
* Add safety/privacy tests and remove raw WhatsApp exports/backups from Git tracking.

0.7.0 - (2026-05-10)
--------------------
* Upgrade the certified-diver `2 dives / 1 day` branch with clearer flow logic and Spanish documentation.
* Expand decision-tree coverage for certified divers, courses, pricing, bookings, logistics, and escalation paths.

0.6.0 - (2026-05-08)
--------------------
* Implement real Chatwoot `input_select` buttons for decision-tree menus.
* Add numeric/text fallback parsing plus polling and deduplication for local Chatwoot button clicks and missed messages.

0.5.0 - (2026-05-07)
--------------------
* Add multi-environment infrastructure for dev, pre, and pro deployments.
* Add bot Dockerfile, VPS compose/Caddy setup, `.env.*.example` templates, and environment loading support.

0.4.0 - (2026-05-07)
--------------------
* Expand curated knowledge base with pricing, availability, discounts, escalation, and sanitized real conversation examples.
* Update embeddings loader and retrieval data preparation.

0.3.0 - (2026-04-10)
--------------------
* Implement Phase 2 RAG agent and supervisor routing.
* Route conversations between deterministic decision tree, retrieval answers, and human escalation.

0.2.0 - (2026-04-10)
--------------------
* Implement Phase 1 deterministic decision tree with Chatwoot integration.
* Add initial booking flow, service routing, webhook handling, and automated replies.

0.1.0 - (2026-04-10)
--------------------
* Create initial Diving Planet Bot repository baseline.
