"""Mini 0.53, en los dos lados: la misma pregunta una 3.ª vez (grave por criterio de Álvaro, #2716) por caminos que el freno de la
0.52 no cubría: sin nada más que decir, con «pago», y dentro de la tarjeta repetida."""
from unittest.mock import patch

from src.agents import conversational_core as core
from src.agents.compositor import componer
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor, slotfill_close
from src.flows.state import ConversationState

PREGUNTA = "¿Desde dónde saldrías? Puedes salir *desde Cartagena* o, si ya estás *en las islas*, coordinamos la recogida."


def _estado(actividad="minicourse", veces=2):
    estado = ConversationState(conversation_id="053b", language="es", is_colombian=False)
    estado.detected_activity = actividad
    estado.core_pending_slot = "location"
    estado._preguntas_del_turno = [("location", PREGUNTA)]
    estado._intenciones = []
    estado.preguntas_hechas = {"location": veces}
    return estado


def test_a_la_tercera_sin_nada_que_decir_van_las_dos_salidas():
    estado = _estado()
    texto = componer(estado, f"¡Perfecto! 🙌\n\n{PREGUNTA}", escribio=False)
    assert "Desde dónde" not in texto and "Desde Cartagena" in texto and "Ya en las islas" in texto
    assert "book.divingplanet.org" in texto and core.SIN_ENLACE_DE_LAS_ISLAS_ES in texto
    assert estado.core_pending_slot == "location"  # sigue pendiente, por si contesta


def test_con_varios_planes_por_origen_va_el_recordatorio():
    # CALN-43 P11: con varios planes por origen no hay dos salidas que dar, y tampoco sale una 3.ª vez: va el recordatorio, que no pregunta.
    from src.flows.que_preguntar import RECORDATORIO

    texto = componer(_estado(actividad="certified_diving"), f"¡Perfecto! 🙌\n\n{PREGUNTA}", escribio=False)
    assert texto == f"¡Perfecto! 🙌\n\n{RECORDATORIO['es']}"


def test_la_pregunta_sobre_el_pago_no_trae_el_origen_otra_vez():
    fija = core.ORIGEN_TRAS_LAS_VARIANTES_ES
    estado = _estado()
    estado._preguntas_del_turno, estado.core_pending_slot, estado._intenciones = [], None, ["pago"]
    respuesta = "La transferencia solo se usa si falla el pago online, y se mantiene el descuento."
    assert componer(estado, f"{respuesta}\n\n{fija}", escribio=True) == respuesta


def test_tras_los_dos_enlaces_la_pregunta_sobra_aunque_pida_el_enlace():
    fija = core.ORIGEN_TRAS_LOS_ENLACES_ES
    estado = _estado()
    estado._preguntas_del_turno, estado.core_pending_slot, estado._intenciones = [], None, ["enlace"]
    enlaces = "• Desde Cartagena: https://book.divingplanet.org/book/a/1\n• Ya en las islas: https://book.divingplanet.org/book/b/2"
    texto = componer(estado, f"{enlaces}\n\n{fija}", escribio=True)
    assert core.SIN_ENLACE_DE_LAS_ISLAS_ES in texto and "¿Saldrías" not in texto


def _con_las_islas_por_confirmar():
    return ConversationState(conversation_id="053b", language="es", pending_correction={"location": "island"})


def test_contesta_a_la_confirmacion_nombrando_un_hotel_de_la_lista():
    estado, intent = _con_las_islas_por_confirmar(), DetectedIntent()
    extractor._poner_ubicacion(intent, estado, "una noche en coral sand y la otra en majagua", {}, {"hotel": "majagua"})
    assert intent.location == "island" and intent.hotel == "majagua" and not estado.pending_correction


def test_sin_hotel_de_la_lista_sigue_por_confirmar():
    estado, intent = _con_las_islas_por_confirmar(), DetectedIntent()
    extractor._poner_ubicacion(intent, estado, "este me interesa", {}, {})
    assert intent.location is None and estado.pending_correction == {"location": "island"}


def test_si_dice_cartagena_no_vale_el_hotel():
    estado, intent = _con_las_islas_por_confirmar(), DetectedIntent()
    with patch.object(extractor, "_jev_dice_que_no_lo_dice", return_value=False), patch.object(
            extractor, "_jev_duda_del_lugar", return_value=False):
        extractor._poner_ubicacion(intent, estado, "salimos de Cartagena, ¿y Majagua?", {"location": "cartagena"},
                                   {"hotel": "majagua"})
    assert intent.location == "cartagena"


def _colombiano(veces):
    estado = ConversationState(conversation_id="053b", language="es", is_colombian=True, detected_group_size=2)
    estado.preguntas_hechas = {core.SLOT_SAFETY: veces}
    return estado


def test_tarjeta_ya_vista_la_pregunta_si_aun_toca_y_se_cuenta():
    estado = _colombiano(1)
    with patch.object(slotfill_close.cart_render, "refresher_price_text", return_value="475.000 COP"):
        texto = slotfill_close._tras_la_tarjeta_ya_vista(estado)
    assert texto.endswith("¿Es el caso de alguno de ustedes?") and "🤿" not in texto
    assert estado.preguntas_hechas[core.SLOT_SAFETY] == 2


def test_tarjeta_ya_vista_a_la_tercera_el_paso_siguiente():
    assert slotfill_close._tras_la_tarjeta_ya_vista(_colombiano(2)) == slotfill_close._OFERTA_DEL_ASESOR["es_grupo"]
    extranjero = _colombiano(2)
    extranjero.is_colombian = False
    assert "enlace" in slotfill_close._tras_la_tarjeta_ya_vista(extranjero)


def test_la_nota_sin_preguntar_deja_el_aviso():
    with patch.object(slotfill_close.cart_render, "refresher_price_text", return_value="475.000 COP"):
        texto = slotfill_close._nota_seguridad(_colombiano(2), preguntar=False)
    assert "refresher" in texto and "?" not in texto


def test_preguntar_como_reservar_cuenta_como_pedir_el_enlace():
    """La causa de regateo-grupo-6 (0 de 5): «como reservamos» daba pide_enlace 0,41 y pide_disponibilidad 0,62, y el turno se tomaba
    por un paso de la reserva, sin escritor. El texto de la pregunta es de lo que depende: que no vuelva a pedir «online»."""
    from src.agents.jev_router import _INTENCIONES_Q, PIDE_ENLACE

    texto = _INTENCIONES_Q[PIDE_ENLACE]["instructions"]
    assert "how to book or reserve" in texto and "only say that they want to book" in texto


def _grupo_de_tres(**senales):
    estado = ConversationState(conversation_id="053b", language="es", detected_group_size=3)
    estado._senales_router = senales
    return estado


def test_en_un_grupo_mixto_el_numero_que_baja_es_una_parte_del_grupo():
    from src.agents.jev_router import GRUPO_MIXTO

    estado, intent = _grupo_de_tres(**{GRUPO_MIXTO: True}), DetectedIntent()
    extractor._poner_grupo(intent, estado, "dos somos colombianos pero uno es extranjero", {"group_size": 2})
    assert intent.group_size is None and not estado.pending_correction


def test_sin_grupo_mixto_el_cambio_se_sigue_confirmando():
    estado, intent = _grupo_de_tres(), DetectedIntent()
    with patch.object(extractor, "_jev_dice_que_nadie_se_suma", return_value=False):
        extractor._poner_grupo(intent, estado, "al final vamos solo 2", {"group_size": 2})
    assert (estado.pending_correction or {}).get("group_size") == 2 or intent.group_size == 2


def test_si_el_escritor_se_deja_los_enlaces_los_pone_el_codigo():
    from src.agents.redactor_hechos import _con_los_enlaces_que_faltan

    a, b = "https://book.divingplanet.org/book/a/1?language=es", "https://book.divingplanet.org/book/b/2?language=es"
    bloques = [{"enlace": {"cartagena": a, "island": b}}]
    assert _con_los_enlaces_que_faltan("Es por la web.", bloques, "es") == f"Es por la web.\n\n• Desde Cartagena: {a}\n• Ya en las islas: {b}"
    con_uno = f"Desde Cartagena: {a}"
    assert _con_los_enlaces_que_faltan(con_uno, bloques, "es") == f"{con_uno}\n\n• Ya en las islas: {b}"
    assert _con_los_enlaces_que_faltan(f"{a} {b}", bloques, "es") == f"{a} {b}"
    assert _con_los_enlaces_que_faltan("Lo cierra un asesor.", [{"enlace": {"asesor": True}}], "es") == "Lo cierra un asesor."


def test_sin_los_enlaces_en_la_respuesta_tampoco_sale_la_pregunta():
    # CALN-43 P11: nunca una 3.ª vez, aunque pida el enlace; queda la indicación del hotel, que no pregunta.
    fija = core.ORIGEN_TRAS_LOS_ENLACES_ES
    estado = _estado()
    estado._preguntas_del_turno, estado.core_pending_slot, estado._intenciones = [], None, ["enlace"]
    texto = componer(estado, f"La reserva es por la web, y son unas cuantas palabras más.\n\n{fija}", escribio=True)
    assert "¿Saldrías" not in texto and core.SIN_ENLACE_DE_LAS_ISLAS_ES in texto


def test_la_salida_que_va_siempre_no_quita_sitio_a_los_paquetes():
    from src.flows import hechos

    st = ConversationState(conversation_id="053b", language="en", is_certified=True, detected_activity="certified_diving",
                           location="island", detected_location="island", detected_duration="multi_day", is_colombian=False)
    st.duracion_de_buceo = True
    planes = [p["plan"] for p in hechos.hechos(st, ["precio"], ["certified_diving"])[0]["otros_planes"]]
    assert any("Fun Dives - 2 dives" in p for p in planes)  # la salida de un día (s04j, días sueltos)
    assert any("night dive" in p for p in planes) and any("5-dive" in p for p in planes)  # y los paquetes (s04i)


def test_quien_bucea_dos_dias_no_recibe_el_paquete_de_tres():
    from src.flows import hechos

    st = ConversationState(conversation_id="053b", language="en", is_certified=True, detected_activity="certified_diving",
                           location="cartagena", detected_location="cartagena", detected_duration="multi_day",
                           detected_cert_days=2, is_colombian=False)
    st.duracion_de_buceo = True
    planes = [p["plan"] for p in hechos.hechos(st, ["precio"], ["certified_diving"])[0]["otros_planes"]]
    assert not any("3 days" in p for p in planes) and any("Fun Dives - 2 dives" in p for p in planes)


def test_la_politica_dice_que_el_residente_no_es_extranjero():
    """g-venezolano-cedula: «al ser un grupo mixto, se paga en dólares» con la lista en pesos (7 de 8 respuestas, también en la 0.52)."""
    import json
    from pathlib import Path

    politicas = json.loads(Path("data/knowledge_base/policies.json").read_text(encoding="utf-8-sig"))["policies"]
    assert "no cuenta como extranjero" in politicas["mixed_nationality_group"]["es"]
    assert "does not count as a foreigner" in politicas["mixed_nationality_group"]["en"]
    assert "no es un grupo mixto" in politicas["colombian_pricing"]["es"]


def _con_reparto(**senales):
    estado = ConversationState(conversation_id="s05a", language="es")
    estado._senales_router = senales
    return estado


def test_quien_ya_tiene_la_certificacion_no_hace_el_curso():
    from src.agents.jev_router import QUIERE_CURSO

    datos = {"group_allocation": {"padi_open_water": 3, "minicourse": 2, "snorkel": 2, "bubble_makers": None}, "group_size": 7}
    limpio = extractor._sin_los_cursos_que_ya_tienen(_con_reparto(**{QUIERE_CURSO: False}), datos)
    assert limpio["group_allocation"] == {"certified_diving": 3, "minicourse": 2, "snorkel": 2, "bubble_makers": None}
    assert limpio["group_size"] == 7
    assert extractor._sin_los_cursos_que_ya_tienen(_con_reparto(**{QUIERE_CURSO: True}), datos) == datos
    assert extractor._sin_los_cursos_que_ya_tienen(_con_reparto(), datos) == datos  # Jev calla: como hoy
    assert extractor._sin_los_cursos_que_ya_tienen(_con_reparto(**{QUIERE_CURSO: False}), None) is None


def test_el_curso_ya_elegido_no_se_toca():
    from src.agents.jev_router import QUIERE_CURSO

    estado = _con_reparto(**{QUIERE_CURSO: False})
    estado.detected_activity = "padi_open_water"
    datos = {"group_allocation": {"padi_open_water": 2, "snorkel": 1}}
    assert extractor._sin_los_cursos_que_ya_tienen(estado, datos) == datos


def test_al_snorkel_no_se_le_dice_la_espera_de_volar():
    from src.flows import hechos

    st = ConversationState(conversation_id="s05a", language="en", detected_activity="snorkel")
    assert "si_vuela" not in hechos.hechos(st, ["tiempo"], ["snorkel"])[0]
    st = ConversationState(conversation_id="s05a", language="en", detected_activity="certified_diving")
    assert "si_vuela" in hechos.hechos(st, ["tiempo"], ["certified_diving"])[0]


def test_la_pregunta_con_algo_delante_y_su_explicacion_se_van_si_ya_la_contesto():
    origen = ("¿Desde dónde saldrías? Este plan dura 2 días y hay que *dormir en las islas* (el alojamiento no está incluido): puedes salir "
              "*desde Cartagena* el primer día o, si ya estás *en las islas*, coordinamos la recogida en tu hotel.")
    cuantos = "¿Para cuántas personas sería: solo para ti o van más? 😊"
    estado = ConversationState(conversation_id="s05a", language="es")
    estado.core_pending_slot = "qty"
    estado._preguntas_del_turno = [("location", origen), ("qty", cuantos)]
    estado._intenciones = []
    respuesta = ("El curso dura 2 días y hay que completar las lecturas antes de las inmersiones.\n\n"
                 f"Para este plan de 2 días, hay que *dormir en las islas* (el alojamiento no está incluido): {origen}\n\n{cuantos}")
    texto = componer(estado, respuesta, escribio=True)
    assert "Desde dónde" not in texto and "coordinamos la recogida" not in texto
    assert "Para este plan de 2 días" in texto and texto.endswith(cuantos)


def test_varias_actividades_que_suman_los_ya_contados_son_ellos():
    estado = ConversationState(conversation_id="g21", language="es", detected_group_size=4)
    estado._jev_adds_person = 0.95
    reparto = {"certified_diving": 2, "padi_open_water": 1, "companion": 1}
    assert extractor._suma_a_un_grupo_sin_actividad(estado, reparto, None) == "todos"
    assert extractor._suma_a_un_grupo_sin_actividad(estado, {"minicourse": 4}, None) == "nuevos"  # una sola: decide Jev


def test_el_curso_sin_plan_desde_las_islas_da_el_de_cartagena_y_lo_dice():
    from src.flows import hechos

    st = ConversationState(conversation_id="s05c", language="en", detected_activity="padi_rescue", location="island",
                           detected_location="island", is_colombian=False)
    [sin_hotel] = hechos.hechos(st, ["precio", "enlace"], ["padi_rescue"])
    assert "enlace" not in sin_hotel and sin_hotel["hotel_primero"]  # CALN-35
    st.hotel = "cocoliso"
    [b] = hechos.hechos(st, ["precio", "enlace"], ["padi_rescue"])
    assert b["precio"]["cartagena"]["online"] == "796 USD" and "curso-de-rescate" in b["enlace"]["cartagena"]
    assert "advisor" in b["sin_plan_desde_las_islas"] and b["origen"] == "cartagena"
    [c] = hechos.hechos(st, ["precio"], ["padi_advanced"])  # el Advanced sí tiene plan desde las islas
    assert "island" in c["precio"] and "sin_plan_desde_las_islas" not in c


def test_el_anuncio_de_los_precios_no_queda_debajo_de_la_lista():
    from src.agents.redactor_hechos import con_la_pieza

    pieza = "*Prices per person*:\n• Fun Dives: 178 USD"
    texto = con_la_pieza("Bringing your gear gives you 5%.\n\nI'm leaving the prices below. Would you like the link?", pieza)
    assert texto == f"Bringing your gear gives you 5%.\n\nI'm leaving the prices below.\n\n{pieza}\n\nWould you like the link?"
    assert con_la_pieza("Lovely.\n\nWould you like the link?", pieza) == f"Lovely.\n\n{pieza}\n\nWould you like the link?"
