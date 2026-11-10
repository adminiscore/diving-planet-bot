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


# ── 3. Una cifra de más de un plan no decide qué plan cotizó el escritor (visto-6941: el 204) ───────────────────────────────

def _buzo_en_cartagena(nombre: str) -> ConversationState:
    return ConversationState(conversation_id=nombre, language="es", detected_activity="certified_diving", is_certified=True,
                             location="cartagena", detected_location="cartagena", is_colombian=False)


def test_el_204_no_mete_el_paquete_de_4_en_el_precio_del_refresher():
    from src.agents.nucleo import origen_precio

    salida = origen_precio._con_la_pieza(_buzo_en_cartagena("b2a-204"),
                                         "El refresher incluye piscina y una inmersión. Cuesta 183 USD online o 204 USD normal.")
    assert "Minicurso" in salida and "Paquete de 4" not in salida


def test_una_cifra_de_un_solo_plan_sigue_diciendo_que_plan_cotizo():
    from src.agents.nucleo import origen_precio

    salida = origen_precio._con_la_pieza(_buzo_en_cartagena("b2a-392"), "El paquete de 5 inmersiones cuesta 392 USD online.")
    assert "5 inmersiones" in salida


def test_una_cifra_solo_ambigua_no_pega_ningun_plan():
    from src.agents.nucleo import origen_precio

    assert origen_precio._con_la_pieza(_buzo_en_cartagena("b2a-616"), "Ese curso cuesta 616 USD online.") is None


# ── 4. Lo que falta de cada plan va con el nombre de su plan (frases nuestras: el refresher y la salida en el mismo turno) ──

def test_lo_que_incluye_cada_plan_no_se_mezcla_con_el_de_otro():
    from src.agents.rag_agent import _completar_con_hechos

    bloques = [{"nombre": "Refresher", "incluye": {"cartagena": ["entrenamiento en piscina", "1 inmersión en el mar con instructor"]}},
               {"nombre": "Buceo certificado", "incluye": {"cartagena": ["2 inmersiones guiadas", "almuerzo"]}}]
    salida = _completar_con_hechos("Claro, te cuento qué lleva cada uno.", bloques, ["incluye"], "es")
    refresher, buceo = salida.split("También incluye (Refresher):")[1].split("También incluye (Buceo certificado):")
    assert "1 inmersión" in refresher and "2 inmersiones" not in refresher
    assert "2 inmersiones guiadas" in buceo


def test_con_un_solo_plan_el_rotulo_es_el_de_siempre():
    from src.agents.rag_agent import _completar_con_hechos

    bloques = [{"nombre": "Refresher", "incluye": {"cartagena": ["entrenamiento en piscina", "1 inmersión en el mar con instructor"]}}]
    salida = _completar_con_hechos("El refresher es un repaso.", bloques, ["incluye"], "es")
    assert "También incluye:\n" in salida and "(Refresher)" not in salida
