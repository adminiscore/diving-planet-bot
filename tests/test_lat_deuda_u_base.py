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
    from src.prompts.info import (  # noqa: F401 — el prompt carga
        JUEZ_PRESENTACION_EN,
        JUEZ_PRESENTACION_ES,
    )

    assert "más de 30 años" in Path(info.__file__).read_text(encoding="utf-8")
