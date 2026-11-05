"""Mini 0.53, en los dos lados: la misma pregunta una 3.ª vez (grave por criterio de Álvaro, #2716) por caminos que el freno de la
0.52 no cubría: sin nada más que decir, con «pago», y dentro de la tarjeta repetida."""
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.compositor import componer
from src.agents.nucleo import extractor, slotfill_close
from src.agents.intent_detector import DetectedIntent
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
    assert "book.divingplanet.org" in texto and "Reserva con el de tu punto de salida." in texto
    assert estado.core_pending_slot == "location"  # sigue pendiente, por si contesta


def test_con_varios_planes_por_origen_se_pregunta():
    assert PREGUNTA in componer(_estado(actividad="certified_diving"), f"¡Perfecto! 🙌\n\n{PREGUNTA}", escribio=False)


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
    assert "Reserva con el de tu punto de salida." in texto and "¿Saldrías" not in texto


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


@pytest.mark.asyncio
async def test_el_escritor_contesta_y_cierra_con_lo_que_sigue():
    estado = _colombiano(2)
    estado.core_pending_slot = core.SLOT_SAFETY
    estado._pregunta_del_escritor = "algo"
    sigue = slotfill_close._tras_la_tarjeta_ya_vista(estado)
    with patch.object(slotfill_close, "_rag_answer", AsyncMock(return_value="¡Anotado, el 21 y el 22!")):
        texto = await slotfill_close._sin_dato(estado, "El 21 y 22", core.SLOT_SAFETY, sigue)
    assert texto == f"¡Anotado, el 21 y el 22!\n\n{sigue}"


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


def test_sin_los_enlaces_en_la_respuesta_la_pregunta_se_queda():
    fija = core.ORIGEN_TRAS_LOS_ENLACES_ES
    estado = _estado()
    estado._preguntas_del_turno, estado.core_pending_slot, estado._intenciones = [], None, ["enlace"]
    assert fija in componer(estado, f"La reserva es por la web, y son unas cuantas palabras más.\n\n{fija}", escribio=True)


def test_la_salida_que_va_siempre_no_quita_sitio_a_los_paquetes():
    from src.flows import hechos

    st = ConversationState(conversation_id="053b", language="en", is_certified=True, detected_activity="certified_diving",
                           location="island", detected_location="island", detected_duration="multi_day", is_colombian=False)
    st.duracion_de_buceo = True
    planes = [p["plan"] for p in hechos.hechos(st, ["precio"], ["certified_diving"])[0]["otros_planes"]]
    assert any("Fun Dives - 2 dives" in p for p in planes)  # la salida de un día (s04j, días sueltos)
    assert any("night dive" in p for p in planes) and any("5-dive" in p for p in planes)  # y los paquetes (s04i)
