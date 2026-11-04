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


def test_los_descuentos_van_en_los_hechos_y_no_se_exigen():
    """CALN3-Q05 y mini de la 0.43: la lista va en los hechos, pero arq-7b no la exige ni la pega, pregunte por uno o no."""
    from src.flows import hechos

    st = _st(detected_group_size=5)
    [b] = hechos.hechos(st, ["descuento"], ["snorkel"])
    assert b["descuento"] and hechos.faltan("Sí, con 5 personas el de grupo les aplica: 10 % más.", [b], ["descuento"]) == []


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


def test_paso3_el_anuncio_de_una_lista_de_importes_que_se_va_no_queda_con_dos_puntos():
    """Sparring s04d (Múnich t1): «you have two options for certified divers:» quedaba con la lista vacía."""
    from src.agents import redactor_hechos as rh

    pieza = "*Prices per person*:\n• 5 Dives - 2 days: 392 USD · 436 USD"
    texto = ("Great place for a two-day trip! From Cartagena, you have two options for certified divers:\n\n"
             "- 4-dive package: 316 USD\n- 5 dives: 392 USD\n\nBoth include the boat and lunch on day 1.")
    salida = rh.con_la_pieza(texto, pieza)
    assert salida == f"Great place for a two-day trip!\n\nBoth include the boat and lunch on day 1.\n\n{pieza}"
    # Si la lista se queda (sin importes), el anuncio también.
    assert rh.con_la_pieza("Options:\n\n- 4 dives\n- 5 dives", pieza).startswith("Options:\n\n- 4 dives")


def test_paso3_la_lista_que_pierde_los_planes_se_va_entera_con_su_anuncio():
    """Sparring s04l (Navidad t2): de la lista quedaban las frases de cada plan sin nombrarlo, y el anuncio sin lista."""
    from src.agents import redactor_hechos as rh

    pieza = "*Prices per person*:\n• 4-dive package: 316 USD · 351 USD"
    texto = ("Yes, those dates work. For certified divers departing from Cartagena, the options are:\n\n"
             "4-dive package: 316 USD. You'll need to stay overnight. 5 dives: 392 USD. You'll need to stay overnight.\n\n"
             "Since you're from Canada, the booking is in USD.")
    assert rh.con_la_pieza(texto, pieza) == f"Yes, those dates work.\n\nSince you're from Canada, the booking is in USD.\n\n{pieza}"
    # El anuncio solo, sin nada delante, se va también.
    assert rh.con_la_pieza("The options are:\n\n- 4 dives: 316 USD", pieza) == pieza
    # Un párrafo que acaba en dos puntos y cuyo siguiente no pierde nada no se toca.
    assert "Bring this:" in rh.con_la_pieza("Bring this:\n\nA towel.\n\nIt costs 316 USD.", pieza)


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


def test_con_el_precio_la_nota_corta_del_de_grupo_y_con_la_pregunta_la_descripcion_entera():
    """Sparring s30e: la descripción entera de discounts.json, con su «ANTES», pegada bajo los precios."""
    from src.flows import hechos  # lazy

    st = _st(detected_activity="snorkel", detected_group_size=6)
    [precio] = hechos.hechos(st, ["precio"], ["snorkel"])
    nota = precio["descuento_de_grupo"]
    assert "antes de pagar" in nota and "ANTES" not in nota and "20%" in nota and "No aplica a cursos PADI" in nota
    assert nota in cotizar.pieza_de_precios([precio], "es")
    [descuento] = hechos.hechos(st, ["descuento"], ["snorkel"])
    assert any("ANTES" in texto for texto in descuento["descuento"])  # la pregunta recibe las condiciones enteras
    st.language = "en"
    [precio_en] = hechos.hechos(st, ["precio"], ["snorkel"])
    assert "before paying" in precio_en["descuento_de_grupo"] and "BEFORE" not in precio_en["descuento_de_grupo"]


def test_los_dias_de_buceo_de_este_mensaje_llegan_a_los_hechos():
    """Sparring s04b: «un plan de 2 días» en ESTE mensaje, aún sin guardar, daba los planes de un día y no el de 5."""
    from src.agents import redactor_hechos
    from src.flows import hechos

    st = _st(detected_activity="certified_diving", is_certified=True, is_colombian=True)
    foto = redactor_hechos._foto(st, {"dias_de_buceo": 2, "group_size": 5}, "cartagena", "un plan de 2 días")
    assert foto.detected_duration == "multi_day" and foto.duracion_de_buceo is True
    assert st.detected_duration is None  # el estado de verdad lo escribe la extracción
    pieza = cotizar.pieza_de_precios(hechos.hechos(foto, ["precio"], ["certified_diving"]), "es")
    assert "Paquete de 5 inmersiones" in pieza and "Salidas de Buceo - 2" not in pieza
    # sin días en el mensaje, como hoy
    foto = redactor_hechos._foto(st, {"group_size": 5}, "cartagena", "¿cuánto cuesta?")
    assert foto.detected_duration is None


def test_caln19_el_escritor_recibe_las_opciones_de_quien_no_ha_elegido():
    """Sparring s04c y s04e: «¿y mi esposa qué puede hacer?» recibía una sola opción."""
    from src.agents.rutas.contexto_rag import _build_extra_context

    contexto = _build_extra_context(_st(language="es", location="cartagena", is_certified=True, detected_group_size=2,
                                        acompanante_sin_certificar=True, pending_undecided_qty=1))
    assert "elige el cliente" in contexto
    for opcion in ("inicurso", "norkel", "compañante"):
        assert opcion in contexto.split("elige el cliente")[1].split(".")[0], opcion
    assert "elige el cliente" not in (_build_extra_context(_st(language="es", location="cartagena")) or "")
