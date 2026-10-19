"""Mapa del estudio: cada grupo del inventario (en `src/`) con su grupo funcional, su clase (a/b/c/d) y la propuesta
(A-E). Genera docs/robustness/regex/estudio-ex9/grupos.csv y resumen.json, y cuenta por clase.

Clases: a = camino principal (decide la respuesta), b = pista/red que solo cuenta si la IA falla o no lee,
c = muerto (sin llamador, flag apagado, condición imposible o solo log/etiqueta), d = lista cerrada / formato /
guarda legítima (no es "entender"). Propuestas: A borrar, B campo del extractor, C pregunta de Jev, D mantener,
E diseño nuevo.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

from scripts.inventario_regex import inventario  # noqa: E402

# Grupos funcionales: código -> (nombre, fichero:función principal)
GF = {
    "ID-ACT": ("Actividad y productos nombrados", "intent_detector._detect_activity / matched_activity_categories / courses_mentioned"),
    "ID-NUM": ("Nº de inmersiones y días de paquete", "intent_detector.dive_counts_in / detect_cert_day_count"),
    "ID-DUR": ("Duración de la estancia (un día / varios)", "intent_detector._detect_duration"),
    "ID-CERT": ("Certificación de quien escribe (la tiene / la quiere)", "intent_detector.certification_claim / holds_padi_cert / _WANTS_CERT_RE"),
    "ID-PERS": ("Otra persona y sujeto de la frase (piezas)", "intent_detector._about_other_person / clause_subject / _PERSON_NOUN_*"),
    "ID-GRUPO-N": ("Cuántos son y 'solo yo'", "intent_detector._detect_group_info (total, solo_confirmed)"),
    "ID-GRUPO-R": ("Reparto del grupo por actividad", "intent_detector._detect_group_info (repartos)"),
    "ID-EDAD": ("Edades", "intent_detector._detect_ages"),
    "ID-BUCEO2": ("Última inmersión hace más de 2 años", "intent_detector._detect_last_dive"),
    "ID-ORIGEN": ("Origen: Cartagena o islas (y papel del lugar)", "intent_detector._detect_location / place_by_role"),
    "ID-HOTEL": ("Hoteles e islas del catálogo", "intent_detector._detect_location (hotel_patterns, island_patterns)"),
    "ID-NAC": ("Nacionalidad", "intent_detector._detect_nationality / nationality_is_ambiguous"),
    "ID-TOK": ("Tokenizar y construir patrones del registro", "re.findall(r'\\w+') y similares"),
    "N-CORTA": ("Respuestas cortas a la pregunta pendiente", "nucleo/routing._apply_short_answer"),
    "N-DELIB": ("Duda entre opciones (deliberación)", "nucleo/routing._is_deliberation_between_options"),
    "N-PAQUETE": ("'Quiero este paquete' (el que describió el bot)", "nucleo/routing._maybe_apply_confirmed_package"),
    "N-IDIOMA": ("Cambio de idioma pedido", "nucleo/setup._setup_phase"),
    "N-NOMBRE": ("Nombre del cliente", "nucleo/setup._capture_client_name"),
    "N-ACOMP": ("Acompañantes y personas (redes)", "nucleo/extraction (atajo de acompañante, red de señales, red de menciones)"),
    "N-SOLO": ("'Voy solo'", "nucleo/extraction._understand"),
    "N-MINI": ("Minicurso nombrado / buceo certificado fuerte", "conversational_core._mentioned_product_activities / _recommend_inferred_minicourse"),
    "N-CIFRA": ("¿Hay una cifra escrita? (valida a la IA)", "conversational_core._EXPLICIT_NUMBER_RE"),
    "N-PRECIO": ("¿Pide precio? / pista de origen antes de cotizar", "conversational_core._origen_antes_del_precio"),
    "N-PLAN": ("Plan de N inmersiones para el RAG", "conversational_core._plan_nombrado"),
    "N-SALUDO": ("Solo un saludo", "conversational_core._is_greeting_only"),
    "N-FMT": ("Formato de texto del bot / citas del LLM", "varios"),
    "S-ESCAL": ("Aceptar la oferta de asesor", "supervisor._shared_turn_handler"),
    "S-MUERTO": ("Patrones sin ningún uso", "supervisor"),
    "S-DTH": ("DIVE TO HEAL (buceo adaptado)", "orchestration/router.classify_route, rutas/safety, rutas/contexto_rag"),
    "S-PREG": ("¿Trae una pregunta?", "rutas/booking._looks_like_info_question"),
    "S-CORR": ("¿Corrige un dato?", "rutas/booking._CORRECTION_CUE_RE"),
    "S-CERRADO": ("Días cerrados (25-dic, 1-ene)", "nucleo/availability._availability_phase"),
    "S-DISPO": ("Pregunta de disponibilidad", "orchestration/router.classify_route"),
    "S-NOTAS": ("Notas para el RAG (acompañante no certificado, certificado inactivo)", "rutas/contexto_rag._build_extra_context"),
    "S-IA": ("¿Eres una IA?", "rutas/deflection._asks_about_ai_identity"),
    "S-ALCOHOL": ("Alcohol y alergias (respuesta fija)", "orchestration/router.classify_route + rutas/info"),
    "S-PRIVADO": ("Grupo privado / empresa", "rutas/info._private_group_event_answer"),
    "S-MISMOPRECIO": ("¿Cambia el precio por nacionalidad?", "rutas/info"),
    "S-EDADMIN": ("¿Puede bucear con N años? (respuesta fija de edad)", "rutas/info._maybe_answer_age_eligibility"),
    "S-REINICIO": ("Reinicio de escenario (borra la memoria)", "rutas/router._is_new_scenario_restart"),
    "S-NINOS": ("Mención de niños", "rutas/router._detect_kids_mention"),
    "S-LINK": ("Link roto", "rutas/safety._detect_broken_link_complaint"),
    "R-SEGUIR": ("Seguimiento: añadir historial a la búsqueda", "rag_agent._looks_like_follow_up"),
    "R-LUGAR": ("Lugar ambiguo (repregunta fija)", "rag_agent._is_ultra_short_ambiguous_location_query"),
    "R-RESUMEN": ("Resumen fijo de 'qué ofrecen' y sus acompañantes", "rag_agent._canonical_diving_overview_answer"),
    "R-TEMAS": ("Temas de la consulta (solo log)", "vector_store.detect_query_topics"),
    "R-FMT": ("Leer la salida del juez", "rag_agent.regen_feedback"),
    "J-CITA": ("Revisor con cita (apagado)", "juez_segunda_opinion"),
}

# (fichero acabado en, nombre, línea o None) -> (grupo funcional, clase, propuesta)
M = {}


def m(fichero, nombres, gf, clase, prop, linea=None):
    for n in nombres.split():
        M[(fichero, n, linea)] = (gf, clase, prop)


ID = "intent_detector.py"
m(ID, "_CERTIFIED_DIVING_PATTERNS _MINICOURSE_PATTERNS _SNORKEL_PATTERNS _PADI_COURSE_PATTERNS _COURSE_NAME_VARIANTS "
      "_NEVER_DIVED _NEVER_AUX _NEVER_TRIED_IT", "ID-ACT", "a", "B")
m(ID, "_DIVE_NUMBER _CERT_DIVE_COUNT_RE _BARE_PACKAGE_DIVE_RE _CERT_DAY_COUNT_RE", "ID-NUM", "a", "D")
m(ID, "_DURATION_UNITS _DURATION_QTY _DURATION_FILLER _DURATION_RES _ELAPSED_BEFORE_RE _ELAPSED_AFTER_RE "
      "_MULTI_DAY_PRODUCT_RE _TODAY_ONLY_RE", "ID-DUR", "a", "E")
m(ID, "_CERTIFIED_PATTERNS _NOT_CERTIFIED_PATTERNS _NEVER_CERTIFIED _WANTS_CERTIFICATION _CERT_NOUN _WANT_OBJECT_PREFIX "
      "_WANT_VERB _DESIRE_VERB _INTEREST_VERB_WRITER _INTEREST_VERB_OTHER _INTEREST_VERB _NEGATION_BEFORE_RE _CERT_LEVEL "
      "_HOLD_VERB_WRITER_ES _HOLD_VERB_OTHER_ES _HOLD_VERB_EN _HOLDS_WRITER _HOLDS_OTHER_PERSON _HOLDS_CERT_RE "
      "_WANTS_CERT_RE _CERTIFIED_OTHER_PERSON_PATTERNS cert", "ID-CERT", "b", "B")
m(ID, "_PERSON_NOUN_MENTION_ES _PERSON_NOUN_MENTION_EN _PERSON_NOUN_SINGULAR_ES _PERSON_NOUN_SINGULAR_EN "
      "_PERSON_NOUN_PLURAL_ES _PERSON_NOUN_PLURAL_EN _SINGULAR_PERSON _NAMED_OTHER_PERSON _THIRD_PERSON_VERB "
      "_OTHER_PERSON_SUBJECT _POSTVERBAL_OTHER_SUBJECT_RE _ELIDED_NEGATION_RE", "ID-PERS", "b", "C")
m(ID, "_CLAUSE_BOUNDARY_RE", "ID-PERS", "a", "D")
m(ID, "_FIRST_PERSON_PLURAL_RE", "ID-PERS", "c", "A")
m(ID, "_gendered_diver_noun _companion_noun group_size_patterns solo_self singular_diver companion other_num "
      "plural_self collective", "ID-GRUPO-N", "a", "B")
m(ID, "activity_kw num_pat sep_pat _split_infix verb_filler word_num cert_split_patterns clause pat_rest m_half "
      "m_half_total mixed_group_patterns", "ID-GRUPO-R", "b", "B")
m(ID, "_edad_re", "ID-EDAD", "a", "E")
m(ID, "LAST_DIVE_TOPIC_RE num", "ID-BUCEO2", "b", "B")
m(ID, "_CARTAGENA_NAME_RE _GENERIC_ISLAND_RE", "ID-ORIGEN", "a", "B")
m(ID, "island_patterns hotel_patterns", "ID-HOTEL", "d", "D")
m(ID, "_NOT_COLOMBIAN_RE _COLOMBIAN_RE _BARE_NEGATION_RE", "ID-NAC", "b", "B")
# El idioma por palabras clave (`_detect_language`) no se aplica nunca: `_apply_detected_intent` solo lo usa si
# `state.detected_language` está vacío y la fase de setup lo fija antes (nucleo/setup.py:169). Su tokenizador es c.
m(ID, "words", "ID-TOK", "c", "A", linea=1186)
m(ID, "text words writer token_sets alternatives name rest", "ID-TOK", "d", "D")

CC = "conversational_core.py"
m(CC, "_EXPLICIT_NUMBER_RE", "N-CIFRA", "d", "D")
m(CC, "_STRONG_CERTIFIED_DIVING_RE", "N-MINI", "a", "E")
m(CC, "_EXPLICIT_MINICOURSE_NAME_RE", "N-MINI", "b", "B")
m(CC, "_N_INMERSIONES_RE", "N-PLAN", "a", "A")
m(CC, "norm", "N-SALUDO", "d", "D")
m(CC, "texto _HORA_DEL_RESUMEN _PREGUNTA_ORIGEN_RE _IMPORTE_RE _FRASE_RE _DEPENDE_DEL_ORIGEN_RE", "N-FMT", "d", "D")
m(CC, "_PIDE_PRECIO_RE _PRECIO_AJENO_RE _PISTA_ORIGEN_RE", "N-PRECIO", "a", "C")
EX = "nucleo/extraction.py"
m(EX, "_COURSE_SOLO_RE _NOT_ALONE_RE", "N-SOLO", "b", "B")
m(EX, "_ADDITION_CUE _ADDITION_CUE_RE _MENTIONS_PERSON_RE _BARE_HEADCOUNT_RE", "N-ACOMP", "b", "C")
m(EX, "_ADDED_PERSON_RE _SINGULAR_COMPANION_RE", "N-ACOMP", "b", "B")
m(EX, "_PLURAL_COMPANION_RE", "N-ACOMP", "b", "A")
m(EX, "_LUGAR_DE_CARTAGENA_RE", "N-CORTA", "c", "A")
RO = "nucleo/routing.py"
m(RO, "_CONFIRMS_DESCRIBED_PACKAGE_RE", "N-PAQUETE", "a", "E")
m(RO, "_HOTEL_UNKNOWN_RE", "N-CORTA", "a", "B")
m(RO, "_LOCATION_DEFER_RE leftover", "N-CORTA", "a", "C")
m(RO, "ages", "N-CORTA", "a", "D")
m(RO, "_DELIBERATION_RE _COMMITMENT_RE", "N-DELIB", "a", "C")
SE = "nucleo/setup.py"
m(SE, "_SWITCH_TO_EN_RE _SWITCH_TO_ES_RE", "N-IDIOMA", "a", "C")
m(SE, "_NAME_TRIGGER_RE", "N-NOMBRE", "c", "A")
m(SE, "_NAME_TRIGGER_SIN_SOY_RE", "N-NOMBRE", "a", "B")
m("extractor_turno.py", "trozos texto", "N-FMT", "d", "D")
m("juez_segunda_opinion.py", "_CIFRA_O_ENLACE", "J-CITA", "c", "A")
SU = "agents/supervisor.py"
m(SU, "_ADAPTIVE_DIVING_PATTERN", "S-DTH", "a", "C")
m(SU, "_BARE_AFFIRMATION_RE _ADVISOR_OFFER_RE _OFFER_VERB_RE", "S-ESCAL", "c", "A")
m(SU, "_GENERAL_INTEREST_PATTERN _BOOKING_PROCESS_QUESTION_RE", "S-MUERTO", "c", "A")
RB = "rutas/booking.py"
m(RB, "_CLOSED_DATE_RE", "S-CERRADO", "a", "A")
m(RB, "_QUE_CONJUNCION _INFO_QUESTION_STARTER_PATTERN _INFO_REQUEST_ANYWHERE_RE _CLAUSE_QUESTION_RE", "S-PREG", "a", "C")
m(RB, "_CORRECTION_CUE_RE", "S-CORR", "a", "C")
m("rutas/changes.py", "_AVAILABILITY_PATTERN _AVAILABILITY_RE", "S-DISPO", "c", "A")
m("rutas/contexto_rag.py", "_DIVE_TO_HEAL_OVERRIDE_RE", "S-DTH", "a", "C")
m("rutas/contexto_rag.py", "_UNCERTIFIED_COMPANION_NOTE_RE _INACTIVE_MENTION_RE _CERTIFIED_MENTION_RE", "S-NOTAS", "a", "B")
m("rutas/deflection.py", "_AI_IDENTITY_RE", "S-IA", "a", "C")
RI = "rutas/info.py"
m(RI, "_ALCOHOL_BEFORE_DIVING_RE _ALLERGY_WORD_RE _FOOD_ALLERGEN_RE", "S-ALCOHOL", "a", "E")
m(RI, "_PRIVATE_GROUP_EVENT_RE", "S-PRIVADO", "a", "C")
m(RI, "_SAME_PRICE_DIFFERENT_NATIONALITY_RE", "S-MISMOPRECIO", "c", "A")
m(RI, "_AGE_ELIGIBILITY_CUE _AGE_NUMBER_HINT _AGE_PERSON_REF", "S-EDADMIN", "a", "E")
RR = "rutas/router.py"
m(RR, "_GREETING_START_RE _NAME_INTRO_RE _INTRO_PHRASE_RE", "S-REINICIO", "a", "C")
m(RR, "cleaned", "S-NINOS", "d", "D")
m(RR, "kids_patterns", "S-NINOS", "c", "A")
RS = "rutas/safety.py"
m(RS, "_PRICE_OR_BOOKING_Q", "S-DTH", "a", "E")
m(RS, "has_link_token_in_msg", "S-LINK", "a", "C")
RA = "rag_agent.py"
m(RA, "_FOLLOW_UP_INDICATORS _FOLLOW_UP_PREFIX _LOCATION_STATEMENT_PREFIX", "R-SEGUIR", "b", "E")
m(RA, "LOCATION_QUERY_INTENT_PATTERN cleaned", "R-LUGAR", "c", "A")
m(RA, "_OVERVIEW_PHRASE _OVERVIEW_BARE_WORD_RE _OVERVIEW_DIVING_WORD _OVERVIEW_EXCLUDE _MENTIONS_COMPANION_RE "
      "_NON_DIVER_SINGULAR_RE _NON_DIVER_PLURAL_RE _NON_DIVER_ELLIPTICAL_ES_RE _NON_DIVER_ELLIPTICAL_EN_RE "
      "_COMPANION_PLURAL_QUANTIFIER_RE", "R-RESUMEN", "c", "A")
m(RA, "item", "R-FMT", "d", "D")
m("vector_store.py", "TOPIC_PATTERNS", "R-TEMAS", "c", "A")

# Familias del inventario corregidas a mano (los módulos partidos en s4-2 quedan "sin clasificar" en el script).
ATAJOS = {"_AI_IDENTITY_RE", "_ALCOHOL_BEFORE_DIVING_RE", "_ALLERGY_WORD_RE", "_FOOD_ALLERGEN_RE",
          "_SAME_PRICE_DIFFERENT_NATIONALITY_RE"}
LEEN_AL_CLIENTE = {"_PIDE_PRECIO_RE", "_PRECIO_AJENO_RE", "_PISTA_ORIGEN_RE"}


def familia_corregida(g):
    f = g["familia"]
    if f == "sin clasificar":
        if g["fichero"].endswith(("extractor_turno.py",)):
            return "formato y datos internos"
        if g["fichero"].endswith("juez_segunda_opinion.py"):
            return "leer la salida de un LLM"
        if g["nombre"] in ATAJOS:
            return "atajo de texto fijo (activo)"
        return "entender al cliente"
    if g["nombre"] in LEEN_AL_CLIENTE:
        return "entender al cliente"
    return f


def busca(g):
    for (fich, nombre, linea), v in M.items():
        if g["fichero"].endswith(fich) and g["nombre"] == nombre and (linea is None or linea == g["linea"]):
            return v
    return None


filas, sin_mapa = [], []
for g in inventario():
    fc = familia_corregida(g)
    v = busca(g)
    if v is None:
        if fc in ("entender al cliente", "atajo de texto fijo (activo)") or g["familia"] == "sin clasificar":
            sin_mapa.append(g)
        continue
    gf, clase, prop = v
    filas.append({**g, "familia_corregida": fc, "grupo_funcional": gf, "nombre_gf": GF[gf][0], "clase": clase,
                  "propuesta": prop})
if sin_mapa:
    print("SIN MAPA:", [(x["fichero"], x["linea"], x["nombre"], x["patrones"]) for x in sin_mapa])

total = sum(g["patrones"] for g in inventario())
fam = Counter()
fam_corr = Counter()
for g in inventario():
    fam[g["familia"]] += g["patrones"]
    fam_corr[familia_corregida(g)] += g["patrones"]
ent = [f for f in filas if f["familia_corregida"] == "entender al cliente"]
por_clase = Counter()
por_prop = Counter()
por_gf = defaultdict(lambda: Counter())
for f in ent:
    por_clase[f["clase"]] += f["patrones"]
    por_prop[f["propuesta"]] += f["patrones"]
    por_gf[f["grupo_funcional"]][f["clase"]] += f["patrones"]
print("total patrones", total)
print("familias (script):", dict(fam))
print("familias corregidas:", dict(fam_corr))
print("ENTENDER corregido:", sum(f["patrones"] for f in ent), "por clase", dict(por_clase), "por propuesta", dict(por_prop))
for gf, c in sorted(por_gf.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  {gf:14} {sum(c.values()):4} {dict(c)}  {GF[gf][0]}")
dest = comun.REPO / "docs/robustness/regex/estudio-ex9"
dest.mkdir(parents=True, exist_ok=True)
with open(dest / "grupos.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["fichero", "linea", "nombre", "patrones", "familia_script", "familia_corregida", "grupo_funcional",
                "nombre_grupo_funcional", "clase", "propuesta"])
    for f in sorted(filas, key=lambda x: (x["grupo_funcional"], x["fichero"], x["linea"])):
        w.writerow([f["fichero"], f["linea"], f["nombre"], f["patrones"], f["familia"], f["familia_corregida"],
                    f["grupo_funcional"], f["nombre_gf"], f["clase"], f["propuesta"]])
json.dump({"total_patrones": total, "familias_script": dict(fam), "familias_corregidas": dict(fam_corr),
           "entender_corregido": sum(f["patrones"] for f in ent), "entender_por_clase": dict(por_clase),
           "entender_por_propuesta": dict(por_prop),
           "por_grupo_funcional": {gf: {"nombre": GF[gf][0], "donde": GF[gf][1], **dict(c)} for gf, c in por_gf.items()}},
          open(comun.OUT / "mapa.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
