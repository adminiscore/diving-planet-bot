"""CALN-9a (30-oct; diseño docs/robustness/caln/diseno-caln9-origen.md): con el origen del cliente sabido, al escritor
solo le llega la ficha de su origen de cada plan."""
from src.agents.rag_agent import fichas_del_origen


def _ficha(service_id: str, origen: str) -> dict:
    return {"content": f"ficha de {service_id}",
            "metadata": {"source": "services", "key": f"ficha:{service_id}", "service_id": service_id, "origin": origen}}


FAQ = {"content": "¿Qué pasa si llueve?", "metadata": {"source": "faqs", "key": "faq:lluvia"}}


def test_si_vino_la_del_suyo_la_del_otro_origen_sale():
    """precio-desde-islas-vs-cartagena: en las islas, la ficha de Cartagena («lancha Cartagena-Islas incluida») sobra."""
    docs = [_ficha("2_dives_1_day", "cartagena"), _ficha("2_dives_1_day_already_on_island", "islas"), FAQ]
    assert fichas_del_origen(docs, "islas", "es") == [docs[1], FAQ]


def test_si_solo_vino_la_del_otro_se_cambia_por_la_del_suyo():
    salida = fichas_del_origen([_ficha("minicourse", "cartagena"), FAQ], "islas", "es")
    assert salida[0]["metadata"]["service_id"] == "minicourse_already_on_island"
    assert salida[0]["metadata"]["origin"] == "islas"
    assert "Islas del Rosario" in salida[0]["content"] and "Minicurso" in salida[0]["content"]
    assert salida[1] == FAQ
    vuelta = fichas_del_origen([_ficha("snorkeling_already_on_island", "islas")], "cartagena", "en")
    assert vuelta[0]["metadata"]["service_id"] == "snorkeling" and "Cartagena" in vuelta[0]["content"]


def test_sin_origen_o_sin_pareja_no_cambia_nada():
    docs = [_ficha("2_dives_1_day", "cartagena"), _ficha("2_dives_1_day_already_on_island", "islas"), FAQ]
    assert fichas_del_origen(docs, None, "es") == docs
    assert fichas_del_origen(docs, "", "es") == docs
    solo = [_ficha("divemaster", "cartagena")]  # sin servicio en las islas
    assert fichas_del_origen(solo, "islas", "es") == solo


def _pieza(actividad: str, lang: str = "es", location: str | None = None) -> str:
    from src.flows import cotizar, hechos
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="caln9b", language=lang)
    st.is_colombian, st.location = False, location
    return cotizar.pieza_de_precios(hechos.hechos(st, ["precio"], [actividad]), lang)


def test_sin_origen_cada_rotulo_dice_lo_que_cambia():
    """CALN-9b: precio-desde-islas t5 (2/2 en PRE 0.40), «El almuerzo no está incluido» encima de los precios desde
    Cartagena, que sí lo incluyen. Bajo cada origen, cómo se llega y el almuerzo, de la ficha de los planes de la lista."""
    mini = _pieza("minicourse")
    assert "*Desde Cartagena* — lancha desde el Muelle de la Bodeguita · con almuerzo\n" in mini
    assert "*Ya en las Islas del Rosario* — recogida en tu hotel si tiene acceso por lancha · sin almuerzo\n" in mini
    assert "*From Cartagena* — boat from Muelle de la Bodeguita · lunch included" in _pieza("minicourse", "en")
    # Los de varios días llevan solo el almuerzo del primer día (food_policy).
    assert "· con el almuerzo del primer día" in _pieza("padi_open_water")
    assert "· con almuerzo (en los de varios días, el del primer día)" in _pieza("certified_diving")


def test_lo_que_confirma_un_asesor_y_con_el_origen_sabido_no_se_dice():
    # Bubble Makers desde Cartagena: su ficha no trae el almuerzo porque lo confirma un asesor; no es «sin almuerzo».
    assert "*Desde Cartagena* — lancha desde el Muelle de la Bodeguita\n" in _pieza("bubble_makers")
    # Con el origen sabido, un solo origen y sin rótulo, como antes.
    sabido = _pieza("certified_diving", location="island")
    assert "Desde Cartagena" not in sabido and "recogida" not in sabido


def test_la_cita_de_un_barrio_de_cartagena_nombra_un_lugar():
    """CALN (30-oct, el origen de la pregunta): «Estamos en Bocagrande» y «We're staying in Getsemaní» los leía el
    extractor como cartagena y se tiraban por no nombrar un lugar (sparring s30a familia t1, s30e cambia-plan t2)."""
    from src.agents.extractor_turno import _solo_un_barrio, nombra_un_lugar

    for cita in ("Estamos en Bocagrande", "We're staying in Getsemaní.", "nos quedamos en el centro histórico",
                 "we're at the hotel in the old town"):
        assert nombra_un_lugar(cita) and _solo_un_barrio(cita)
    for cita in ("im getting in tmrw", "we'll be in town next week", "soy de Marbella", "vamos a San Diego"):
        assert not nombra_un_lugar(cita)
    # Con un sitio de las islas en la misma cita, no es «solo un barrio» (no se corrige a cartagena).
    assert _solo_un_barrio("dos noches en Bocagrande y luego Isla Grande") is None
