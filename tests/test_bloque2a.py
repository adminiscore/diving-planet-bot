"""Bloque 2a del Plan Gadea (10-nov): plan e importe, lo determinista. Sin IA: casos de clientes vistos o frases nuestras."""
from src.flows import catalog, hechos
from src.flows.state import ConversationState

# ── 1. El Rescue solo sale desde Cartagena (visto-6916; decisión de Gadea, mej-2) ──────────────────────────────────────────

def test_el_plan_que_no_se_ofrece_desde_las_islas_sale_de_la_base():
    assert catalog.no_sale_de_las_islas("rescue")
    assert not catalog.no_sale_de_las_islas("advanced")  # tiene plan desde las islas
    assert not catalog.no_sale_de_las_islas("divemaster")  # sin tarifa: lo cierra un asesor


def test_el_catalogo_dice_que_el_rescue_solo_sale_desde_cartagena():
    for lang, nombre, frase in (("es", "Rescate", "solo sale desde Cartagena"), ("en", "Rescue", "only departs from Cartagena")):
        catalog._FACTS_CACHE.pop(lang, None)
        rescue = next(ln for ln in catalog.catalog_facts(lang).splitlines() if nombre in ln)
        assert frase in rescue


def test_a_quien_esta_en_las_islas_se_le_dice_que_el_rescue_sale_de_cartagena():
    st = ConversationState(conversation_id="b2a-rescue", language="es", detected_activity="padi_rescue", location="island",
                           detected_location="island", is_colombian=False, hotel="cocoliso")
    [b] = hechos.hechos(st, ["precio"], ["padi_rescue"])
    assert b["origen"] == "cartagena" and "solo sale desde Cartagena" in b["sin_plan_desde_las_islas"]
    assert "asesor" not in b["sin_plan_desde_las_islas"]
