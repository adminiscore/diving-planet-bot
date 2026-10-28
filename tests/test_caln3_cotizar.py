"""CALN-3 paso 1 (27-oct): cotizar() en sombra, qué importes tocan por código (src/flows/cotizar.py)."""
from src.flows import cotizar
from src.flows.state import ConversationState


def _st(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln3", language="es")
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_sin_actividad_elegida_los_candidatos_del_contexto():
    assert cotizar.actividades_a_cotizar(_st(quiere_bucear=True)) == ["certified_diving", "minicourse"]
    assert cotizar.actividades_a_cotizar(_st(is_certified=False)) == ["minicourse", "snorkel"]
    assert cotizar.actividades_a_cotizar(_st(is_certified=True)) == ["certified_diving"]
    assert cotizar.actividades_a_cotizar(_st()) == ["certified_diving", "minicourse"]  # pide precio sin saber nada


def test_el_grupo_manda_y_sin_origen_van_los_dos():
    st = _st(detected_group_allocation={"certified_diving": 1, "minicourse": 2}, detected_group_size=3, is_colombian=True)
    pieza = cotizar.cotizar(st)
    assert pieza["actividades"] == ["certified_diving", "minicourse"] and pieza["falta"] == ["origen"]
    assert {"630000", "655000"} <= set(pieza["importes"])  # desde Cartagena
    assert any(i in pieza["importes"] for i in ("489000", "475000"))  # y desde las islas


def test_la_sombra_no_cambia_la_respuesta_y_apunta_lo_que_falta(caplog):
    import logging

    st = _st(is_certified=False, location="cartagena", is_colombian=True)
    st._senales_router = {"pide_precio": True}
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        cotizar.en_sombra(st, "Para darte el precio exacto necesito saber desde dónde sales.")
    assert "faltan" in caplog.text and "655000" in caplog.text


# --- Paso 2: sin actividad elegida, el escritor recibe los hechos de los candidatos ---

def test_quien_nunca_ha_buceado_y_quiere_bucear_solo_el_minicurso():
    """CALN3-P01 t2: «nunca he buceado» a «¿cuánto cuesta bucear?» no pide el snorkel."""
    assert cotizar.candidatos(_st(is_certified=False, quiere_bucear=True)) == ["minicourse"]


def test_los_candidatos_sin_la_carta_de_paquetes():
    bloques = cotizar.hechos_de_los_candidatos(_st(quiere_bucear=True), ["precio"])
    assert [b["actividad"] for b in bloques] == ["certified_diving", "minicourse"]
    assert all("otros_planes" not in b and set(b["precio"]) == {"cartagena", "island"} for b in bloques)
    assert all(b["pregunta_pendiente"] == "origen" for b in bloques)


def test_el_descuento_de_grupo_solo_cuando_aplica():
    """CALN3-Q04 (decisión 4): con 5 o más, el de grupo en el snorkel; en el Open Water, que no aplica; con menos, nada."""
    from src.flows import hechos

    [snorkel] = hechos.hechos(_st(detected_group_size=5), ["precio"], ["snorkel"])
    assert "10%" in snorkel["descuento_de_grupo"] or "10 %" in snorkel["descuento_de_grupo"]
    [curso] = hechos.hechos(_st(detected_group_size=5), ["precio"], ["padi_open_water"])
    assert "no aplica a los cursos PADI" in curso["descuento_de_grupo"]
    [pareja] = hechos.hechos(_st(detected_group_size=2), ["precio"], ["snorkel"])
    assert "descuento_de_grupo" not in pareja


def test_la_lista_de_descuentos_dice_lo_mismo_que_el_precio():
    """CALN3-R03: 5 amigos y el Open Water; en la lista, el de grupo es el «no aplica», no el texto general."""
    from src.flows import hechos

    [curso] = hechos.hechos(_st(detected_group_size=5), ["precio", "descuento"], ["padi_open_water"])
    assert curso["descuento_de_grupo"] in curso["descuento"]
    assert not any("se suma al 10" in d for d in curso["descuento"])


def test_los_demas_planes_dos_por_origen():
    """CALN3-R04: el buzo que estará una semana (estancia) no recibe la carta de paquetes."""
    from src.flows import hechos

    [b] = hechos.hechos(_st(detected_duration="multi_day", is_certified=True), ["precio"], ["certified_diving"])
    por_origen = [p.get("origen") for p in b["otros_planes"]]
    assert por_origen.count("cartagena") <= 2 and por_origen.count("island") <= 2
