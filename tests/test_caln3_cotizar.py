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


def test_si_pregunta_por_un_descuento_no_se_exigen_los_demas():
    """CALN3-Q05: «¿el de grupo nos aplica?»: la lista va en los hechos, pero arq-7b no exige ni pega las demás."""
    from src.flows import hechos

    st = _st(detected_group_size=5)
    st._un_descuento = True
    [b] = hechos.hechos(st, ["descuento"], ["snorkel"])
    assert b["descuento"] and b["solo_el_preguntado"] is True
    assert hechos.faltan("Sí, con 5 personas el de grupo les aplica: 10 % más.", [b], ["descuento"]) == []
    st._un_descuento = False
    [b] = hechos.hechos(st, ["descuento"], ["snorkel"])
    assert hechos.faltan("Sí, con 5 personas el de grupo les aplica: 10 % más.", [b], ["descuento"])


def test_en_la_pregunta_general_cada_descuento_por_sus_palabras_propias():
    """rot-029: con palabras que comparten todos los descuentos («descuento», «buceo», «cursos PADI», «aplica»), el del
    equipo propio se daba por dicho sin nombrar el equipo; ahora cuentan solo sus palabras propias."""
    from src.flows import hechos

    lista = ["5% de descuento si traes tu propio equipo, solo en buceo y cursos PADI.",
             "10% de descuento para grupos de 5 personas, solo en buceo y no en cursos PADI.",
             "10% de descuento online en buceo y cursos PADI."]
    respuesta = "Hay descuento online del 10 %, solo en buceo y en los cursos PADI, y otro para grupos de 5 personas."
    raices = hechos._raices(respuesta)
    assert hechos._elemento_dado(lista[0], raices, respuesta)  # antes: las palabras comunes bastaban
    assert not hechos._elemento_dado(lista[0], raices, respuesta, hechos._palabras_comunes(lista))
    assert hechos._elemento_dado(lista[1], raices, respuesta, hechos._palabras_comunes(lista))


def test_paso3_el_paquete_que_nombra_el_cliente_va_en_la_pieza():
    """CALN-3 paso 3 (p11, p12): «el paquete de 5 inmersiones» no quedaba en el estado; sin el catálogo del escritor,
    la pieza daba la salida de 2. Ahora el plan nombrado (este mensaje o el último suyo que lo nombre) es el del precio."""
    from src.agents import redactor_hechos as rh
    from src.flows import hechos

    historia = [{"role": "user", "content": "Quiero el paquete de 5 buceos, ya estaremos en las islas"},
                {"role": "assistant", "content": "¡Genial!"}, {"role": "user", "content": "¿Cuánto es por persona?"}]
    foto = rh._foto(_st(location="island"), {}, "island", "¿Cuánto es por persona?", historia)
    assert foto.detected_service_id == "5_dives_2_days"
    pieza = cotizar.pieza_de_precios(hechos.hechos(foto, ["precio"], ["certified_diving"]), "es")
    assert pieza.splitlines()[1].startswith("• Paquete de 5 inmersiones") and len(pieza.splitlines()) == 4
    assert rh._paquete_nombrado("¿El de 2 inmersiones o el de 5 inmersiones?", []) is None  # dos planes: no se elige


def test_paso3_con_la_tarjeta_va_la_nota_del_de_grupo(monkeypatch):
    """CALN-3 paso 3 (r01): con la tarjeta (G3-07a, sin precio) no va la pieza, pero sí si el de grupo aplica."""
    import asyncio

    from src.agents import conversational_core as core
    from src.agents import redactor_hechos, supervisor

    nota = "El descuento de grupo (10 % desde 5 personas) no aplica a los cursos PADI, así que este curso no lo tiene."

    async def rag_answer(query, **kw):
        assert kw.get("sin_precio") is True
        return "El Open Water dura 2 días.\n\n¿Te ayudo con algo más?"

    async def nota_de_grupo(state, message, history):
        return nota

    monkeypatch.setattr(supervisor, "rag_answer", rag_answer)
    monkeypatch.setattr(redactor_hechos, "nota_de_grupo", nota_de_grupo)
    st = _st(location="cartagena")
    answer = asyncio.run(core._rag_answer(st, "somos 5, ¿descuento de grupo?", sin_precio=True, history=[]))
    assert answer == f"El Open Water dura 2 días.\n\n{nota}\n\n¿Te ayudo con algo más?"


def test_paso3_con_la_nota_del_de_grupo_fuera_lo_que_dice_el_escritor_de_el():
    """r01 (×3 tras 1a84026): con la nota «no aplica» debajo, el escritor seguía diciendo encima que se suma al online."""
    from src.agents import redactor_hechos as rh

    nota = "El descuento de grupo (10 % desde 5 personas) no aplica a los cursos PADI, así que este curso no lo tiene."
    texto = ("El Open Water dura 2 días. Para grupos de 5 o más hay un 10% de descuento, que se suma al online. "
             "Deben solicitarlo al equipo antes de pagar.\n\n¿Te ayudo con algo más?")
    salida = rh.con_la_pieza(texto, nota)
    assert "se suma" not in salida and salida.startswith("El Open Water dura 2 días. Deben solicitarlo")
    assert nota in salida and salida.endswith("¿Te ayudo con algo más?")
    # Sin nota del de grupo, lo que diga el escritor de él se queda (los demás descuentos, si los pregunta).
    assert "se suma" in rh.con_la_pieza(texto, "*Precios por persona*:\n• Minicurso: 183 USD · 204 USD")


def test_paso3_quien_no_ha_elegido_tambien_tiene_precio():
    """Sparring t3 (pareja de Barú): «mi marido es buzo y yo quiero probar» daba solo el buceo; la pieza también lleva
    las 2 primeras opciones de quien no ha elegido."""
    from src.agents import redactor_hechos as rh

    st = _st(location="cartagena", is_certified=True, detected_group_size=2, acompanante_sin_certificar=True,
             detected_group_allocation={"certified_diving": 1}, pending_undecided_qty=1)
    opciones = rh._de_quien_no_ha_elegido(st, {})
    assert "minicourse" in opciones and "certified_diving" not in opciones and len(opciones) <= 2
    assert rh._de_quien_no_ha_elegido(_st(detected_group_allocation={"snorkel": 2}), {}) == []


def test_paso3_el_reparto_del_mensaje_antes_que_los_candidatos():
    """Sparring t3 (6 de Medellín): «2 quieren hacer snorkel» llegaba como candidatos buceo y minicurso."""
    from src.agents import redactor_hechos as rh

    assert rh._del_reparto_del_mensaje({"group_allocation": {"snorkel": 2, "undecided": 4}}) == ["snorkel"]


def test_paso3_la_nota_del_de_grupo_se_ve_aunque_vaya_en_otra_linea():
    from src.agents import redactor_hechos as rh

    pieza = ("*Precios por persona* (online · normal):\n• Tour de Snorkeling: 448.000 COP · 497.000 COP\n\n"
             "10% de descuento para grupos de 5 personas o más, que se suma al 10% de descuento online.")
    salida = rh.con_la_pieza("Sí, por ser un grupo de 6 aplica el descuento de grupo. Salen a las 8.", pieza)
    assert salida.startswith("Salen a las 8.") and salida.count("grupo") == 1


def test_paso3_el_parrafo_final_del_escritor_tambien_se_limpia():
    """Sparring t3b: «Sí, por ser un grupo de 6 aplica el descuento de grupo… ¿Quieres que te pase con un asesor?»."""
    from src.agents import redactor_hechos as rh

    pieza = "*Precios por persona*:\n• Tour de Snorkeling: 448.000 COP · 497.000 COP\n\n10% de descuento para grupos de 5."
    salida = rh.con_la_pieza("Te dejo los precios.\n\nSí, por ser un grupo de 6 aplica el descuento de grupo. "
                             "¿Quieres que te pase con un asesor?", pieza)
    assert salida.endswith(pieza + "\n\n¿Quieres que te pase con un asesor?")


def test_paso3_un_descuento_con_su_umbral():
    """Sparring t3b: el mensaje largo con «¿…y hay descuento de grupo?» da 0,60-0,68; la pregunta general, 0,05."""
    from src.agents import jev_router as j

    assert j.answers_to_signals({j.PIDE_UN_DESCUENTO: {"noul": 0.64}})[j.PIDE_UN_DESCUENTO] is True
    assert j.answers_to_signals({j.PIDE_UN_DESCUENTO: {"noul": 0.19}})[j.PIDE_UN_DESCUENTO] is False


def test_caln3c_buzo_con_novia_que_nunca_ha_buceado():
    """p07: «yo soy buzo certificado y mi novia nunca ha buceado» sin reparto: el buceo y el minicurso."""
    assert cotizar.candidatos(_st(is_certified=True, acompanante_sin_certificar=True)) == ["certified_diving", "minicourse"]


def test_caln3c_quien_no_ha_elegido_es_el_buzo_que_escribe():
    """p08: «I'm a certified diver and my 12 year old son wants to snorkel» → {snorkel 1} + 1 sin elegir: el buceo."""
    from src.agents import redactor_hechos as rh

    st = _st(is_certified=True, detected_group_allocation={"snorkel": 1}, pending_undecided_qty=1, detected_ages=[12])
    assert rh._de_quien_no_ha_elegido(st, {}) == ["certified_diving"]


def test_quinta_quien_no_ha_elegido_y_esta_certificado_solo_el_buceo():
    """5.ª ronda (precio-desde-islas-vs-cartagena t5): la pareja Advanced con uno sin elegir llevaba el minicurso."""
    from src.agents import redactor_hechos as rh

    st = _st(is_certified=True, detected_group_allocation={"certified_diving": 1}, pending_undecided_qty=1,
             sin_decidir_certificados=True)
    assert rh._de_quien_no_ha_elegido(st, {}) == ["certified_diving"]


def test_quinta_sin_pedir_precio_ni_origen_no_va_la_pieza(monkeypatch):
    """5.ª ronda: con la pregunta de precio guardada, arq-8f añade «precio» a cada turno; sin que el
    cliente pida precio ahora ni se sepa el origen, la pieza no va (el escritor contesta lo que pregunta)."""
    import asyncio

    from src.agents import redactor_hechos as rh
    from src.agents import supervisor
    from src.flows import hechos

    llamadas = {}

    async def rag_answer(query, **kw):
        llamadas.update(kw)
        return "La lancha vuelve a las 3:00 p. m."

    monkeypatch.setattr(supervisor, "rag_answer", rag_answer)
    st = _st()
    st._jev_pide_precio = False
    bloques = hechos.hechos(st, ["precio", "horario"], ["certified_diving"])
    answer = asyncio.run(rh._con_el_escritor(st, "¿a qué hora se vuelve?", [], bloques, ["precio", "horario"]))
    assert "Precios por persona" not in answer and not llamadas.get("precios_por_codigo")
