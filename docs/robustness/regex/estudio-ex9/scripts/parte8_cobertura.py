"""Parte 8: con la cobertura del replay con oráculo (parte 5 --cobertura), ¿qué funciones corren en el turno real?
Salida: out/parte8.json"""
import json, ast, sys
sys.path.insert(0,'.')
import comun
cov=json.load(open(comun.OUT/'replay-oraculo-base-cov.json',encoding='utf-8'))['cobertura']
cov={k.replace(chr(92),'/'):set(v) for k,v in cov.items()}
def funcs(path):
    t=ast.parse(open(comun.REPO/path,encoding='utf-8').read())
    out={}
    for n in ast.walk(t):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            body=[x.lineno for x in n.body if not (isinstance(x,ast.Expr) and isinstance(getattr(x,'value',None),ast.Constant))]
            out[n.name]=(n.lineno, body[0] if body else n.lineno, n.end_lineno)
    return out
objetivos={
 'src/agents/intent_detector.py':['detect','_detect_language','_detect_activity','_detect_certification','_detect_group_info','_detect_ages','_detect_last_dive','_detect_duration','_detect_location','_detect_nationality','certification_claim','certification_status','holds_padi_cert','nationality_is_ambiguous','certification_is_ambiguous','course_level_is_ambiguous','mentions_other_person_subject','mentions_writer_and_others','elided_certification','other_person_certification','place_by_role','matched_activity_categories','courses_mentioned','dive_counts_in','detect_cert_day_count','_split_out_uncertifiable_kids'],
 'src/agents/nucleo/extraction.py':['_understand','_question_turn_fields','_drop_regex_fields_jev_denies','_regex_contradictions','_quote_backs_boolean','_boolean_patch_is_anchored','_recheck_proposals','_named_people','_recommend_inferred_minicourse','_flag_cert_or_course','_asks_for_a_course','_add_or_ask_companion','_menciones_para_la_red','_number_of_something_else','_mentions_person','_menciona_a_alguien','_singular_companion'],
 'src/agents/nucleo/extractor.py':['_aplicar_extractor','_poner_actividad','_poner_grupo','_poner_certificacion','_poner_ubicacion','_conservar_hotel','_hotel_del_catalogo','_lugar_por_jev','_route_contradictions'],
 'src/agents/rutas/booking.py':['_apply_detected_intent','_maybe_veto_resolved_fields_via_llm','_activity_should_verify','_nationality_should_verify','_certification_should_verify','enforce_group_allocation_consistency','_looks_like_info_question'],
 'src/agents/nucleo/routing.py':['_apply_short_answer','_quantity_answer','_departure_place','_is_deliberation_between_options','_maybe_apply_confirmed_package','_word_ages'],
 'src/agents/nucleo/setup.py':['_capture_client_name','_setup_phase'],
 'src/agents/rutas/info.py':['_maybe_answer_age_eligibility','_looks_like_age_eligibility_question','_alcohol_and_food_policy_answer','_private_group_event_answer'],
 'src/agents/rutas/router.py':['_is_new_scenario_restart','_reset_to_fresh_scenario','_detect_kids_mention'],
}
resultado = {}
for path, names in objetivos.items():
    fs=funcs(path); lines=cov.get(path,set())
    res=[]
    for n in names:
        if n not in fs: res.append(f'{n}=?'); continue
        a,b,e=fs[n]
        ran = any(l in lines for l in range(b,e+1))
        res.append(f"{n}={'SI' if ran else 'no'}")
    print(path.split('/')[-1], ' '.join(res))
    resultado[path] = dict(x.split('=') for x in res)
json.dump(resultado, open(comun.OUT/'parte8.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
