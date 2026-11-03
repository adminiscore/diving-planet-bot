"""Sparring s30a (30-oct, contra la candidata 0.39; docs/robustness/g3/hallazgos.md, CALN-S30A-03): el buzo que lleva
años sin bucear y viene varios días hace el refresher el primero y bucea los demás; los hechos llevan los dos. Sin red."""
from src.agents import redactor_hechos
from src.flows import hechos
from src.flows.state import ConversationState


def _buzo(duracion):
    st = ConversationState(conversation_id="s30a", language="en")
    st.detected_activity, st.is_certified, st.last_dive_over_2_years = "certified_diving", True, True
    st.location, st.detected_duration = "cartagena", duracion
    return st


def test_varios_dias_el_refresher_y_el_buceo_de_los_demas_dias():
    assert redactor_hechos._actividades(_buzo("multi_day"), {}) == ["refresher", "certified_diving"]
    assert redactor_hechos._actividades(_buzo("single_day"), {}) == ["refresher"]
    assert redactor_hechos._actividades(_buzo(None), {}) == ["refresher"]


def test_con_el_refresher_el_buceo_va_con_su_plan_de_un_dia():
    st = _buzo("multi_day")
    solo = {b["actividad"]: b for b in hechos.hechos(st, ["precio"], ["certified_diving"])}
    juntos = {b["actividad"]: b for b in hechos.hechos(st, ["precio"], ["refresher", "certified_diving"])}
    assert set(juntos) == {"refresher", "certified_diving"}
    assert "2 days" in solo["certified_diving"]["precio"]["cartagena"]["plan"]  # sin el refresher: el paquete de 2 días
    assert "(1 day)" in juntos["certified_diving"]["precio"]["cartagena"]["plan"]  # con él: el día de buceo que queda


def test_preguntando_por_los_descuentos_la_pieza_no_quita_lo_que_dice_el_escritor_del_de_grupo(monkeypatch):
    """s30a-02: «¿nos suman el de grupo, el de equipo y el online?» → la pieza quitaba la respuesta del escritor (sus
    frases del de grupo) y quedaba «no puedo calcular…». Con la intención de descuento, la nota del de grupo que aplica
    no va en la pieza; la de que no aplica (un curso PADI, r01) sí."""
    import asyncio

    from src.agents import supervisor
    from src.flows import cotizar

    aplica = "10% de descuento para grupos de 5 personas o más, que se suma al 10% de descuento online."
    no_aplica = hechos._SIN_DESCUENTO_DE_GRUPO["es"].format(pct=10, n=5)
    respuesta = "El de grupo y el de equipo propio no se suman entre sí: cada uno se suma solo al online, del grupo el 20 %."
    piezas = []

    async def rag(message, **kw):
        return respuesta

    def pieza(bloques, lang):
        piezas.append([b.get("descuento_de_grupo") for b in bloques])
        return "*Precios por persona*:\n• Salidas de Buceo: 178 USD · 197 USD"

    monkeypatch.setattr(supervisor, "rag_answer", rag)
    monkeypatch.setattr(cotizar, "pieza_de_precios", pieza)
    st = ConversationState(conversation_id="s30a-2", language="es")
    st._jev_pide_precio = True
    for nota, queda in ((aplica, None), (no_aplica, no_aplica)):
        bloques = [{"actividad": "certified_diving", "origen": "cartagena", "descuento_de_grupo": nota}]
        salida = asyncio.run(redactor_hechos._con_el_escritor(st, "m", [], bloques, ["precio", "descuento"]))
        assert piezas[-1] == [queda] and respuesta in salida
    assert hechos.no_aplica_el_de_grupo(no_aplica) and not hechos.no_aplica_el_de_grupo(aplica)


def test_las_politicas_del_30_oct_las_lee_el_bot():
    """Decisiones de Gadea (30-oct): el embarazo, el mareo y la factura, en el bloque que leen el bot y la base curada."""
    from src.domain.politicas import politica

    for clave, marca in (("pregnancy", "snorkel"), ("seasickness", "desayuna ligero"), ("invoice", "factura")):
        assert marca in politica(clave, "es") and politica(clave, "en")


def test_el_acompanante_tiene_el_descuento_de_grupo():
    from src.domain import activities as dom

    st = ConversationState(conversation_id="s30a-acomp", language="es")
    st.detected_group_size = 5
    assert hechos._descuento_de_grupo(st, dom.by_id("companion"), "es")


def test_s30e_para_el_mismo_dia_no_se_puede_reservar():
    """s30e (30-oct): «¿podemos bucear HOY?» a la 1:45 pm → «sí, reservad para hoy». La disponibilidad lo dice ya."""
    from src.domain.politicas import politica

    assert "MISMO día ya no se puede reservar" in politica("availability_always", "es")
    assert "SAME day is no longer possible" in politica("availability_always", "en")


def test_s30e_la_edad_del_buceo_certificado_dice_que_hay_que_estar_certificado():
    """s30e: el nieto de 13 «puede hacer buceo certificado» sin decir que lo esté; y lo nuevo no se exige en el texto."""
    st = ConversationState(conversation_id="s30e-edad", language="es")
    cert, snorkel = (hechos.hechos(st, ["edad"], [a])[0]["edad"] for a in ("certified_diving", "snorkel"))
    assert cert.get("solo_si_esta_certificado") is True and "solo_si_esta_certificado" not in snorkel
    bloque = {"actividad": "certified_diving", "edad": cert}
    assert hechos.faltan(f"Desde los {cert['minima']} años, si ya está certificado.", [bloque], ["edad"]) == []
