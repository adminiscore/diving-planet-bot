"""lat-deuda-u (26-oct): las decisiones de Gadea sobre la base, tras el inventario de fuentes
(docs/robustness/lat/inventario-fuentes.md). Cada dato en un sitio, en los dos idiomas y sin notas internas en lo que
lee el cliente."""
import json
from pathlib import Path

import pytest

from src.domain import activities as dom
from src.flows import catalog, hechos
from src.flows.state import ConversationState

KB = Path(__file__).resolve().parents[1] / "data" / "knowledge_base"


def _json(nombre: str):
    return json.loads((KB / nombre).read_text(encoding="utf-8-sig"))


def _vuelo(actividad: str, lang: str = "es") -> list[str]:
    st = ConversationState(conversation_id="lat-deuda-u", language=lang)
    bloques = hechos.hechos(st, ["requisitos"], [actividad])
    palabra = "vuelo" if lang == "es" else "flying"
    return [r for r in (bloques[0].get("requisitos") or []) if palabra in r] if bloques else []


# --- C2: el vuelo tras el refresher (seguridad) -------------------------------------------------------------------

@pytest.mark.parametrize("actividad, horas", [("refresher", 18), ("minicourse", 12), ("certified_diving", 18),
                                              ("padi_open_water", 18)])
def test_las_horas_de_vuelo_son_de_la_actividad(actividad, horas):
    assert _vuelo(actividad) == [f"Después de bucear, esperar mínimo {horas} horas antes de tomar un vuelo"]
    assert _vuelo(actividad, "en") == [f"After diving, wait at least {horas} hours before flying"]


def test_la_ficha_del_refresher_dice_18_horas():
    from scripts.kb_v2 import fichas_refresher

    for ficha in fichas_refresher(catalog.RAW_SERVICES):
        assert ("18 horas" in ficha["content"] or "18 hours" in ficha["content"]), ficha["metadata"]
        assert "12 horas" not in ficha["content"] and "12 hours" not in ficha["content"]


def test_las_fichas_no_copian_la_regla_de_vuelo():
    for sid, svc in _json("services.json")["services"].items():
        for lang in ("es", "en"):
            copias = [r for r in svc.get(f"requirements_{lang}") or [] if "vuelo" in r or "flying" in r]
            assert not copias, f"{sid}: la regla de vuelo sale del registro de actividades, no de la ficha"


# --- edades, cursos y planes con noche ----------------------------------------------------------------------------

def test_el_rescue_es_desde_los_12():
    assert dom.by_id("padi_rescue").min_age == 12 == dom.by_id("padi_advanced").min_age
    politica = _json("policies.json")["policies"]["age_minimum"]
    assert "Rescue desde los 12" in politica["es"] and "Rescue course from 12" in politica["en"]


def test_rescue_y_mindful_diving_con_noche():
    politica = _json("policies.json")["policies"]["courses_overnight_requirement"]
    assert "Rescue y Mindful Diving" in politica["es"] and "Rescue and Mindful Diving" in politica["en"]


def test_las_faq_no_ofrecen_el_scuba_diver_ni_dicen_3_4_dias():
    texto = json.dumps(_json("curada/faqs.json"), ensure_ascii=False)
    assert "3-4 días" not in texto and "3-4 days" not in texto and "5 sesiones" not in texto
    assert "También existe el Curso Scuba Diver" not in texto
    assert "no ofrecemos el curso Scuba Diver" in texto


def test_divemaster_aproximadamente_dos_meses():
    texto = json.dumps(_json("services.json")["services"]["divemaster"], ensure_ascii=False)
    assert "al menos 2 meses" not in texto and "mínimo 2 meses" not in texto
    assert "aproximadamente 2 meses" in texto


# --- lo que lee el cliente ----------------------------------------------------------------------------------------

def test_sin_notas_internas_en_lo_que_lee_el_cliente():
    for sid, svc in _json("services.json")["services"].items():
        for campo in ("description_es", "description_en"):
            assert "Gadea" not in (svc.get(campo) or "") and "Andrés" not in (svc.get(campo) or ""), sid
    for clave, politica in _json("policies.json")["policies"].items():
        for lang in ("es", "en"):
            assert "Gadea" not in politica.get(lang, ""), clave


def test_el_formulario_en_ingles_avisa_de_que_esta_en_espanol():
    politica = _json("policies.json")["policies"]["medical_restrictions"]["en"]
    assert politica.count("(the form is in Spanish)") == politica.count("en-espanol")


def test_pao_pao_esta_en_la_lista_de_hoteles():
    politica = _json("policies.json")["policies"]["other_island_hotels"]
    assert "Pao Pao" in politica["es"] and "Pao Pao" in politica["en"]


def test_el_equipo_no_va_en_todos_los_planes():
    politica = _json("policies.json")["policies"]["what_to_bring"]
    assert "todos los planes" not in politica["es"] and "every plan" not in politica["en"]
    assert "Divemaster" in politica["es"]


def test_mas_de_30_anos():
    from src.prompts import info

    assert "más de 30 años" in info.JUEZ_PRESENTACION_ES or "más de 30 años" in Path(info.__file__).read_text(
        encoding="utf-8")


def test_bubble_makers_con_precio_definitivo():
    """Gadea, 26-oct: los precios ya no son provisionales."""
    for nombre in ("pricing.json", "services.json", "curada/faqs.json"):
        assert "provisional" not in (KB / nombre).read_text(encoding="utf-8-sig").lower(), nombre


def test_el_paquete_de_3_vuelve_al_dia_siguiente():
    """Gadea, 26-oct: tras la noche en las islas se vuelve al día siguiente en nuestra lancha."""
    svc = _json("services.json")["services"]["3_dives_1_day"]
    assert any(p.startswith("Día 2: regreso a Cartagena") for p in svc["itinerary_es"])
    assert any(p.startswith("Day 2: return to Cartagena") for p in svc["itinerary_en"])


# --- limpieza del inventario (26-oct): políticas partidas, una lista de hoteles, días de cierre, nada muerto -------

@pytest.mark.parametrize("actividad, con", [
    ("certified_diving", {"refresh_requirement", "insurance_form_requirement"}),
    ("refresher", {"medical_restrictions", "refresh_requirement", "insurance_form_requirement"}),
    ("minicourse", {"medical_restrictions", "insurance_form_requirement"}),
    ("padi_open_water", {"medical_restrictions", "insurance_form_requirement"}),
    ("snorkel", {"insurance_form_requirement"}),
])
def test_los_requisitos_que_son_politicas_salen_de_un_sitio(actividad, con):
    requisitos = catalog.requisitos_de_politica(actividad, "es")
    for clave in ("medical_restrictions", "refresh_requirement", "insurance_form_requirement"):
        assert (catalog.politica(clave, "es") in requisitos) == (clave in con), clave


def test_las_fichas_no_copian_politicas_ni_la_edad():
    for sid, svc in _json("services.json")["services"].items():
        assert len(svc.get("requirements_es") or []) == len(svc.get("requirements_en") or []), sid
        for r in svc.get("requirements_es") or []:
            assert not any(x in r for x in ("seguro", "Si llevas más de 2 años", "exoneracion-curso", "años de edad",
                                            "Tener al menos", "Edad mínima")), (sid, r)


def test_las_politicas_ya_no_se_cortan_por_frases():
    import inspect

    fuente = inspect.getsource(hechos)
    assert "_CORTE_" not in fuente and ".find(" not in fuente


def test_una_sola_lista_de_hoteles():
    from src.agents import extractor_turno, jev_router, rag_agent
    from src.domain import lugares

    assert extractor_turno.HOTELES_DE_LA_BASE == lugares.hoteles_con_recogida()
    assert rag_agent.AMBIGUOUS_LOCATION_NAMES == lugares.lugares_de_las_islas()
    assert "Pao Pao" in lugares.hoteles_con_recogida()
    pregunta = jev_router._questions_for_turn(None)[jev_router.CUSTOMER_PLACE]
    assert "Pao Pao" in pregunta["criteria"]["islands"]
    texto = _json("policies.json")["policies"]["other_island_hotels"]
    for hotel in lugares.hoteles_con_recogida():
        assert hotel.replace("San Pedro de ", "") in texto["es"] and hotel.replace("San Pedro de ", "") in texto["en"]


def test_los_dias_de_cierre_salen_de_la_base():
    from src.agents import escalation
    from src.domain.calendario import dias_cerrados
    from src.prompts import info

    assert dias_cerrados("es") == "el 25 de diciembre y el 1 de enero"
    assert dias_cerrados("es", articulo=False) == "25 de diciembre y 1 de enero"
    assert dias_cerrados("en") == "December 25 and January 1"
    for texto in (catalog.catalog_facts("es"), escalation._CLIMA_CON_POLITICA["es"], info.RAG_DISPONIBILIDAD_NUEVA_ES):
        assert dias_cerrados("es") in texto


def test_nada_muerto():
    assert not ({"price", "extra_notes_es", "extra_block_es", "flight_rule_es", "summary_intro_es"}
                & set(catalog.SERVICES["2_dives_1_day"]))
    from scripts import load_embeddings

    assert not hasattr(load_embeddings, "load_knowledge_base")
    ci = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m scripts.load_embeddings" not in ci and "python -m scripts.kb_v2 --yes" in ci


# --- contradicciones que quedaban (C9, C10, C13, C14, C15) y el pago de colombianos en un sitio -------------------

def test_las_edades_del_contexto_salen_del_registro():
    from src.agents.rutas import contexto_rag

    st = ConversationState(conversation_id="lat-deuda-u", language="es")
    st.kids_under_8_count, st.kids_eight_to_ten_count = 1, 1
    texto = contexto_rag._build_extra_context(st) or ""
    assert "Advanced y Rescue desde los 12" in texto and "Divemaster desde los 18" in texto
    assert "cursos PADI." not in texto


def test_el_pase_del_clima_dice_el_reembolso():
    from src.agents import escalation

    assert "100 %" in escalation._CLIMA_CON_POLITICA["es"] and "100%" in escalation._CLIMA_CON_POLITICA["en"]


def test_hay_cupo_no_es_una_incidencia():
    from src.agents.escalation import detect_sensitive_escalation

    assert detect_sensitive_escalation("¿hay cupo mañana?", "es") is None


def test_los_paquetes_de_3_y_4_tambien_piden_certificacion():
    texto = _json("policies.json")["policies"]["packages_certification_requirement"]
    assert "3, 4, 5, 7 y 9" in texto["es"] and "3, 4, 5, 7 and 9" in texto["en"]


def test_el_enlace_va_en_el_idioma_del_cliente_en_todos_los_sitios():
    en = catalog.service_fact_sheet("2_dives_1_day", "en")
    assert "language=en" in en and "language=es" not in en
    assert "language=es" not in catalog.catalog_booking_links("en")


def test_el_pago_de_los_colombianos_en_un_sitio():
    from src.domain.politicas import politica_breve
    from src.prompts import info

    breve = politica_breve("payment_colombian", "es")
    assert "Llave" in breve and breve.replace("*", "") in info.REDACTOR_HECHOS_ES
    assert politica_breve("payment_colombian", "en").replace("*", "") in info.REDACTOR_HECHOS_EN
