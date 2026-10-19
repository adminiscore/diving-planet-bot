# ex-9b paso 3 · qué se podrá borrar cuando se promocione `extractor_sin_pista`

Rama `feature/ex9b-paso-3` (19-oct). Con el flag encendido el regex deja de ser la pista de los campos del extractor
(actividad, origen, certificación, grupo y reparto, nacionalidad, última inmersión); se quedan la isla y el hotel del
catálogo. El borrado va en **otro commit, después de la ronda que lo promocione**, con el flag fuera de `config.py`,
del compose y de `componentes.json`. Medida del borrado: suite verde y el replay offline del estudio (`parte5` +
`parte7`, modos oráculo y caído) con 0 diferencias frente al flag encendido.

**Lo que contradice al estudio:** el estudio contaba que el paso 3 quita 215 patrones (la clase b salvo el seguimiento
del RAG). No es así: el paso 3 deja sin uso el **pegamento** de la pista en el núcleo (abajo, §1), pero los patrones de
clase b los siguen leyendo, a través de `IntentDetector.detect()`, lectores de los pasos 4 y 6 que este paso no toca
(§2). Patrones de regex que se pueden borrar al promocionar: **ninguno**; con la decisión del §1.3 (quitar el veto
LLM de los campos del regex), 2 grupos (`certification_is_ambiguous` y sus `_CERTIFIED_ANY_RE` /
`_NOT_CERTIFIED_ANY_RE`, que no son patrones nuevos sino uniones de `_CERTIFIED_PATTERNS` / `_NOT_CERTIFIED_PATTERNS`).

## 1. Código del núcleo que queda sin uso

### 1.1 `src/agents/nucleo/extractor.py`

| Qué | Cómo queda | Por qué |
|---|---|---|
| `campos_de_la_pista()` | la constante `_CAMPOS_LISTA_CERRADA` (isla y hotel) | con el flag siempre es esa |
| `_aplicar_extractor`, rama `datos is None` | copiar de la pista la isla y el hotel con `_pasa_la_puerta_de_hoy(state, "location")`; fuera el bucle por dominios, la llamada a `_route_contradictions` (isla y hotel no están en `_CORRECTABLE_FIELDS`) y la llamada a `_lugar_por_jev` (`intent.location` ya es siempre None ahí) | la pista ya no trae los campos de clase b |
| `_lugar_por_jev` entera (s4-28) | se borra | su único llamador es la rama de arriba. **El flag `jev_lugar_cliente` NO se borra**: también decide si Jev hace la pregunta `customer_place` (`jev_router.py:555`), que sigue leyendo `_jev_dice_que_no_lo_dice` (CAL-C3c, `lugar_con_dos_lectores`); hay que reescribir su comentario y su ficha |
| `_poner_actividad`: el log `el regex leía activity` y el minicurso deducido (`intent._minicurso_deducido`) | se borran | la pista no trae actividad (la rama del grupo repartido por el regex ya se quitó en el commit de la regla, sin flag) |
| parámetro `pista` de `_poner_actividad`, `_poner_grupo` y `_poner_certificacion` | se quita (solo lo usaban para los logs `(regex: …)`) | `_poner_ubicacion` lo sigue necesitando para `_conservar_hotel` |
| `state._extractor_leyo = …` en `_aplicar_extractor` | se borra | solo lo lee la red de menciones (§1.2) |

### 1.2 `src/agents/nucleo/extraction.py`

| Qué | Cómo queda | Por qué |
|---|---|---|
| `_understand`: el bloque `if getattr(intent, "_minicurso_deducido", False) …` (3 líneas) | se borra | ya no hay minicurso deducido |
| `_recommend_inferred_minicourse` | se queda en dos líneas: si el extractor eligió el minicurso y no había actividad, se borra la recomendación (`state.suggested_activity = None`) | sin minicurso deducido, `intent.activity == "minicourse"` solo llega elegido (`_actividad_elegida`); la recomendación del minicurso la hace CAL-C1 (`actividad_por_lo_sabido`) con `quiere_bucear` e `is_certified` del extractor |
| `_asks_for_a_course` | se borra | único llamador: lo de arriba |
| `_drop_regex_fields_jev_denies` y su llamada en `_understand` | se borran | Jev solo da `affirms_*` de campos del extractor (`_AFFIRMS_SIGNAL_FIELDS`): sin pista no filtra nada (con el flag ya no corre) |
| `state._affirms_p` (`routing.py:652-654`), `AFFIRMS_DENY_MAX` y la salida `affirms_p` de Jev (`jev_router.py:150-151, 736-742`) | se borran | su único lector es la puerta de arriba |
| `_question_turn_fields` y `_campos_de_la_puerta()` | se simplifica: "en un turno con pregunta no se guardan las edades del regex" (lo único que queda); ya no mira `supervisor._VETO_FIELD_SPECS` | las edades son del regex hasta el paso 6; no están en `_AFFIRMS_SIGNAL_FIELDS` ni en el veto, así que siempre se quitan en un turno con pregunta, como hoy |
| `_menciones_para_la_red`, `_menciones_de_otro_producto` y el bloque de la red en `_extraction_phase_body` (desde `mentioned = _menciones_para_la_red(state, message)` hasta su `return response`) | se borran | la red de menciones (CAL-C5) solo corría sin extractor; con el flag no corre nunca |
| flags `red_menciones_solo_sin_extractor` y `red_menciones_con_principal` (`config.py`, compose, `componentes.json`) | se borran | sin lector |

`_EXPLICIT_MINICOURSE_NAME_RE` y `_STRONG_CERTIFIED_DIVING_RE` **se quedan**: los usa `_mentioned_product_activities`
(`conversational_core.py:904-906`), que es de las respuestas cortas y de la deliberación.

### 1.3 Decisión aparte: el veto LLM de los campos del regex (`src/agents/rutas/booking.py`)

Ya no lo llama nadie en `src/` (`_maybe_veto_resolved_fields_via_llm` no tiene llamador desde ex-9). El paso 1 lo dejó
porque lo usaban `_question_turn_fields` (las claves de `_VETO_FIELD_SPECS`) y `scripts/run_extraction_eval.py`. Con el
flag promocionado solo queda el script. Si Gadea decide retirar también el script, se borran:
`_VetoSpec`, `_VETO_FIELD_SPECS`, `_eligible_veto_fields`, `_maybe_veto_resolved_fields_via_llm`,
`_maybe_veto_resolved_field_via_llm`, `valid_veto_corrections`, `apply_veto_disagreements`, `_veto_would_generalize`,
`_apply_activity_veto`, `_activity_should_verify`, `_certification_should_verify`, `_nationality_should_verify`,
`_group_allocation_should_verify`, sus re-exports en `supervisor.py`, `llm_extractor.verify_fields` / `verify_field`
(sin otro llamador), los 12 flags `llm_*_veto_shadow_mode` / `llm_*_veto_cutover` y, en `intent_detector.py`,
`certification_is_ambiguous`, `_CERTIFIED_ANY_RE` y `_NOT_CERTIFIED_ANY_RE`. Tests: `test_activity_veto.py`,
`test_certification_veto_trigger.py`, `test_field_veto_generic_trigger_risk.py`, `test_group_allocation_veto.py`,
`test_veto_never_generalizes_activity.py` y el caso de `_activity_should_verify` de `test_referral_course.py`.
(`nationality_is_ambiguous` se queda: la usa `_detect_nationality`.)

## 2. Los patrones de clase b que NO se pueden borrar todavía

`detect()` sigue corriendo entero (lo llama `_understand` para la duración, las inmersiones, las edades, el idioma, la
isla, el hotel y "voy solo") y sus campos de clase b los leen estos lectores, todos de los pasos 4 a 6:

| Lector | Qué lee del regex | Paso que lo sustituye |
|---|---|---|
| `nucleo/routing._apply_short_answer`, la duda a "¿desde dónde sales?" ("no sé" → Cartagena) | `other_fields`: **todos** los campos que lee `detect()` (actividad, certificación, grupo, origen, nacionalidad, última inmersión…) para saber si el mensaje dice algo más | 4 (respuestas cortas) |
| `nucleo/routing._quantity_answer` | `group_size` (`_detect_group_info`, que también suma el reparto) | 4 |
| `nucleo/routing._departure_place` | `place_by_role` (origen) | 4 |
| `rutas/info._maybe_answer_age_eligibility` | `group_allocation` (cuántos certificados en el plan por edades) | 6 |
| `nucleo/extraction._number_of_something_else` | `cert_dives`, `cert_days`, edades | 4 / 6 |
| `nucleo/extraction._activity_has_textual_backing` (red de señales LLM) | `certification_claim(about_writer=False)` (piezas de otra persona) | 5 |
| `nucleo/extraction._flag_cert_or_course` | `course_level_is_ambiguous` (`_CERT_LEVEL`, `_WANTS_CERT_RE`, `_HOLDS_CERT_RE`, `certification_claim`): nivel PADI sin decir si lo tiene o lo quiere, se pregunta. No es pista: no escribe ningún dato del regex, solo hace la pregunta | 4 |
| `nucleo/routing` (deliberación) | `clause_subject` | 5 |
| atajo de acompañante de `_understand`, "voy solo", `_singular_companion`, `_menciona_a_alguien` | `_ADDED_PERSON_RE`, `_ADDITION_CUE_RE`, `_SINGULAR_COMPANION_RE`, `_PLURAL_COMPANION_RE`, `_MENTIONS_PERSON_RE`, `_BARE_HEADCOUNT_RE`, `_COURSE_SOLO_RE`, `_NOT_ALONE_RE`, `_PERSON_NOUN_*`, `_SINGULAR_PERSON` | 4 ("solo yo") y 5 (Jev `companion_joins` / `adds_person`) |

Por grupo de `grupos.csv` (clase b):

| Grupo | Patrones | ¿Se borra al promocionar? |
|---|---|---|
| ID-CERT · certificación | 104 | No: `other_fields`, `certification_claim` (red de señales), `course_level_is_ambiguous`, y `detect()` la usa para deducir la actividad (que lee `other_fields`) |
| ID-GRUPO-R · reparto | 26 | No: `_quantity_answer` (el total sale del reparto), plan por edades de `rutas/info`, `other_fields` |
| ID-NAC · nacionalidad | 11 | No: `other_fields` |
| ID-BUCEO2 · última inmersión | 3 (+12 sueltos) | No: `other_fields` |
| ID-PERS · otra persona (piezas) | 35 | No: piezas de la certificación y de las redes de acompañante |
| N-ACOMP · acompañantes | 23 | No: atajo de acompañante y red de señales (paso 5) |
| N-SOLO · "voy solo" | 11 | No: "solo yo" es del paso 4 |
| N-MINI · minicurso nombrado | 2 | No: `_mentioned_product_activities` |

## 3. Tests

Suite entera con `EXTRACTOR_SIN_PISTA=true` (19-oct): **76 fallan**, 3.061 pasan, 17 saltados. Con el flag apagado:
3.137 pasan.

**Hallazgo:** 74 de los 76 no simulan el extractor. En los tests no hay red, así que `datos_del_extractor` devuelve
None y el flujo lo lleva la pista del regex (la rama "el extractor falló"): buena parte de los tests de flujo del
núcleo prueban hoy el camino de degradación, no el de producción. Al promocionar hay que darles un extractor simulado
(un fixture en `tests/conftest.py` que devuelva lo que el cliente afirma en cada mensaje, como el oráculo de `parte5`)
o borrarlos si solo prueban la pista. Sin eso se pierde esa cobertura.

### 3.1 Prueban la pista o sus puertas: se borran (o se reescriben con extractor simulado) (8 de los 76)

- `tests/test_cal_c3_hotel_por_extractor.py::test_c5_la_red_de_menciones_solo_si_el_extractor_no_leyo`
- `tests/test_ex5_ubicacion_extractor.py::test_si_el_extractor_falla_se_queda_lo_de_hoy`
- `tests/test_u3_answer_and_continue.py::test_la_puerta_tira_nacionalidad_y_grupo_nombrados_dentro_de_la_pregunta`
- `tests/test_u3_answer_and_continue.py::test_en_una_pregunta_el_regex_no_escribe_datos`
- `tests/test_conversational_core.py::test_regex_last_dive_still_wins_over_the_backing_gate`
- `tests/test_mixed_nationality_llm.py::test_not_mixed_keeps_the_nationality_read`
- `tests/test_double_answer_evidence.py::test_boolean_quoting_the_pending_answer_is_still_dropped`
- `tests/test_u35_corrections.py::test_el_minicurso_deducido_se_recomienda_y_no_se_guarda` (lo cubre CAL-C1:
  `tests/test_extractor_sin_pista.py::test_encendido_la_recomendacion_sale_de_lo_que_dice_el_extractor`)
- En `tests/test_extractor_sin_pista.py`: los `test_apagado_*`, el caso `con_pista` de los tests parametrizados del
  grupo repartido y `test_puerta_de_jev_sin_pregunta_solo_corre_con_el_flag_apagado`.

### 3.2 Flujos que hoy corren con la pista: se adaptan con extractor simulado (68)

| Fichero | Tests |
|---|---|
| `tests/test_conversational_core.py` | 33: `test_colombian_checkout_escalates_no_direct_link`, `test_companion_activity_ambiguity_defers_instead_of_burying_pending_slot`, `test_companion_attribute_in_opening_message_keeps_main_activity`, `test_companion_qty_answer_mentioning_different_activity_not_misapplied`, `test_companion_signal_post_close_adds_snorkel_item`, `test_divemaster_contact_only_no_direct_link`, `test_explicit_language_switch_mid_conversation_is_honored`, `test_first_turn_greets_as_coral_diving_planet`, `test_full_flow_english`, `test_hallucinated_main_activity_restatement_is_not_queued_as_companion`, `test_kids_ages_split_cart_blocks`, `test_lead_note_built_at_close`, `test_llm_gap_fill_feeds_slots`, `test_mixed_allocation_builds_multi_item_cart`, `test_multi_slot_message_absorbed_in_one_turn`, `test_no_solo_signal_still_asks_quantity`, `test_other_companions_post_close_asks_before_adding_unconfirmed_item`, `test_padi_course_flow_no_cert_no_safety_questions`, `test_padi_course_island_variant_resolved`, `test_question_mid_flow_answers_and_reasks_pending_slot`, `test_reask_does_not_repeat_plan_recommendation`, `test_safety_answer_without_person_mention_does_not_spawn_phantom_companion`, `test_safety_never_reasked_after_answered`, `test_short_answer_island_then_hotel`, `test_short_answer_resolves_pending_location`, `test_single_activity_selection_not_treated_as_comparing`, `test_slot_resolver_discarded_when_turn_answered_another_slot`, `test_snorkel_companion_added_after_close`, `test_sofia_full_flow_spanish`, `test_solo_signal_infers_one_person_for_diving_too`, `test_solo_signal_infers_one_person_for_snorkel`, `test_tengo_n_amigos_counts_once_not_double`, `test_understand_still_fills_when_state_is_empty` |
| `tests/test_u3_answer_and_continue.py` | 5: `test_con_flag_y_jev_contesta_sin_interrogacion`, `test_recordar_sigue_con_su_respuesta_fija`, `test_si_el_rag_no_sabe_no_se_pega_la_pregunta_de_la_reserva`, `test_si_el_rag_si_sabe_la_pregunta_de_la_reserva_sigue_yendo_detras`, `test_si_jev_dice_que_pide_recordar_sigue_la_respuesta_fija` |
| `tests/test_companion_already_counted.py` | 6: `test_other_persons_activity_asks_the_total_instead_of_guessing` (3 casos), `test_the_total_decides_move_or_add` (2), `test_an_explicit_addition_is_added_without_asking` |
| `tests/test_conversations.py` | 5: `test_intent_group_size_detected`, `test_intent_location_detected`, `test_intent_minicourse_skips_certification`, `test_intent_padi_course_detection`, `test_intent_specialty_detection` |
| `tests/test_u35_corrections.py` | 4: `test_nombrarlo_es_elegirlo`, `test_si_no_contesta_si_o_no_se_queda_lo_guardado_y_no_se_repite`, `test_un_no_mantiene_lo_guardado`, `test_un_si_confirma_el_minicurso_recomendado` |
| `tests/test_named_people_back_allocation.py` | 4: `test_a_level_someone_holds_is_not_the_course_in_the_split`, `test_named_people_keep_the_split_and_the_total`, `test_total_backed_by_named_people_is_kept_without_a_split`, `test_writer_counts_even_without_saying_yo` |
| `tests/test_corrections_confirmed.py` | 2: `test_explicit_correction_after_the_price_changes_the_currency`, `test_own_change_of_activity_carries_a_single_activity_split` |
| `tests/test_eval_core_mode.py` | 2: `test_a_field_the_state_already_had_is_not_produced_again`, `test_undecided_members_are_scored_inside_the_allocation` |
| `tests/test_routing_signals_integration.py` | 2: `test_group_size_correction_with_filler_words_is_applied`, `test_group_size_not_overwritten_without_correction_cue` |
| `tests/test_s4_26_supuestos.py` | 2: `test_el_cierre_igual_no_se_repite_tras_una_respuesta` (`True-False`, `False-True`) |
| `tests/test_cert_or_course.py` | 1: `test_ambiguous_level_asks_before_quoting` |
| `tests/test_course_level_slot.py` | 1: `test_conversation_asks_the_course_and_continues_after_the_choice` |
| `tests/test_undecided_group_members.py` | 1: `test_undecided_member_is_not_assumed_and_rest_follow_main_activity` |

Y con el veto LLM (§1.3), sus 5 ficheros de tests.
