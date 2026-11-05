"""CALN-35: cómo reserva cada cliente, en un solo sitio (decisiones de Gadea `pago-y-reserva` y `hotel-antes-de-reservar`)."""
import json
from pathlib import Path

import pytest

from src.agents import compositor
from src.agents import conversational_core as core
from src.agents.intent_detector import DetectedIntent
from src.agents.jev_router import SIN_HOTEL
from src.agents.nucleo import extractor, slotfill_close
from src.agents.nucleo.origen_precio import (
    ORIGEN_TRAS_LAS_VARIANTES_EN,
    ORIGEN_TRAS_LAS_VARIANTES_ES,
    _con_la_pieza,
)
from src.agents.supervisor import route_message
from src.flows import hechos
from src.flows.como_reserva import (
    ASESOR,
    ENLACE,
    HOTEL_PRIMERO,
    como_reserva,
    cuando_tenga_el_hotel,
    hotel_conocido,
)
from src.flows.state import ConversationState

ENLACE_URL = "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln35")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize(("campos", "esperado"), [
    ({}, ENLACE),
    ({"location": "cartagena"}, ENLACE),
    ({"is_colombian": False}, ENLACE),
    ({"is_colombian": True}, ASESOR),
    ({"is_colombian": True, "mixed_nationality_notice": True}, ENLACE),
    ({"location": "island"}, HOTEL_PRIMERO),
    ({"location": "island", "hotel": "por confirmar"}, HOTEL_PRIMERO),
    ({"location": "island", "hotel": "to be confirmed"}, HOTEL_PRIMERO),
    ({"location": "island", "hotel": "Casa Azul"}, ENLACE),
    ({"location": "island", "is_colombian": True}, HOTEL_PRIMERO),  # sin hotel, tampoco pasa al asesor
    ({"location": "island", "hotel": "cocoliso", "is_colombian": True}, ASESOR),
    ({"pending_correction": {"location": "island"}}, HOTEL_PRIMERO),  # se le está confirmando
    ({"pending_correction": {"location": "cartagena"}}, ENLACE),
])
def test_como_reserva(campos, esperado):
    assert como_reserva(_estado(**campos)) == esperado


def test_por_confirmar_no_es_un_hotel():
    assert hotel_conocido(_estado(hotel="por confirmar", detected_hotel="por confirmar")) is None
    assert hotel_conocido(_estado(detected_hotel="ubuntu")) == "ubuntu"


@pytest.mark.parametrize(("hotel", "conocido"), [
    ("Isla Grande", False), ("En Isla Grande", False), ("en la isla grande.", False), ("isla marina", False),
    ("Casa Azul en Isla Grande", True), ("Hotel Isla del Sol", True), ("cocoliso", True),
])
def test_una_isla_no_es_un_hotel(hotel, conocido):
    assert bool(hotel_conocido(_estado(hotel=hotel))) is conocido
    assert (como_reserva(_estado(hotel=hotel, location="island")) == HOTEL_PRIMERO) is not conocido


def _sin_hotel(st):
    st._senales_router = {SIN_HOTEL: True}
    return st


def test_si_dice_que_no_tiene_hotel_no_se_le_pregunta():
    st = _sin_hotel(_estado(language="es", location="island", detected_activity="certified_diving", is_certified=True))
    extractor._poner_hotel(DetectedIntent(), st, {})
    assert st.hotel == "por confirmar" and core.next_missing_slot(st) is None


def test_sin_la_senal_o_con_hotel_no_se_marca():
    st = _estado(language="es", location="island")
    extractor._poner_hotel(DetectedIntent(), st, {})
    assert st.hotel is None
    st = _sin_hotel(_estado(language="es", location="island", hotel="cocoliso"))
    extractor._poner_hotel(DetectedIntent(), st, {})
    assert st.hotel == "cocoliso"


def test_decir_que_no_tiene_hotel_confirma_las_islas():
    st = _sin_hotel(_estado(language="es", pending_correction={"location": "island"}))
    intent = DetectedIntent()
    extractor._poner_ubicacion(intent, st, "todavía no tenemos hotel", {}, {})
    assert intent.location == "island" and not st.pending_correction


def test_sin_hotel_se_pregunta_y_luego_no_se_sigue_con_la_reserva():
    base = {"detected_activity": "certified_diving", "is_certified": True, "location": "island"}
    assert core.next_missing_slot(_estado(**base)) == core.SLOT_HOTEL
    assert core.next_missing_slot(_estado(**base, hotel="por confirmar")) is None
    assert core.next_missing_slot(_estado(**base, hotel="Casa Azul")) is not None


def test_la_pregunta_pide_el_hotel_no_la_isla():
    assert "isla" not in core.ask_slot(_estado(language="es", location="island"), core.SLOT_HOTEL)
    assert "island" not in core.ask_slot(_estado(language="en", location="island"), core.SLOT_HOTEL)


def test_la_regla_una_vez_y_despues_solo_que_vuelva():
    st = _estado(language="es", location="island", hotel="por confirmar")
    primera = slotfill_close._hotel_primero(st)
    assert "resérvalo primero" in primera and "Cocoliso" in primera
    assert "Cartagena" not in primera and "book.divingplanet.org" not in primera and "asesor" not in primera
    assert st.core_pending_slot == core.SLOT_HOTEL
    segunda = slotfill_close._hotel_primero(st)
    assert segunda == cuando_tenga_el_hotel(st) and "?" not in segunda
    assert core.ask_slot(st, core.SLOT_HOTEL) == segunda  # no se le vuelve a preguntar


def test_la_regla_en_plural_y_en_ingles():
    assert "resérvenlo" in slotfill_close._hotel_primero(_estado(language="es", detected_group_size=2))
    assert "book it first" in slotfill_close._hotel_primero(_estado(language="en"))


@pytest.mark.parametrize(("campos", "queda"), [
    ({"is_colombian": True}, False),
    ({"location": "island"}, False),
    ({"is_colombian": False}, True),
    ({"is_colombian": True, "mixed_nationality_notice": True}, True),
    ({"location": "island", "hotel": "cocoliso"}, True),
])
def test_el_compositor_quita_el_enlace_a_quien_no_le_toca(campos, queda):
    respuesta = f"El curso dura 2 días.\n\nTe dejo el enlace para reservar: {ENLACE_URL}\n\n¿Te ayudo con algo más?"
    salida = compositor.componer(_estado(language="es", **campos), respuesta, escribio=True)
    assert ("book.divingplanet.org" in salida) is queda
    assert "El curso dura 2 días." in salida and "¿Te ayudo con algo más?" in salida
    assert ("Te dejo el enlace" in salida) is queda  # lo que lo anunciaba se va con él


def test_un_hotel_dicho_despues_de_por_confirmar_cuenta():
    st = _estado(language="es", location="island", hotel="por confirmar", detected_hotel="por confirmar")
    intent = DetectedIntent()
    extractor._poner_hotel(intent, st, {"hotel": "Casa Azul"})
    assert intent.hotel == "Casa Azul"


def test_la_pregunta_del_origen_no_promete_el_enlace():
    for texto in (ORIGEN_TRAS_LAS_VARIANTES_ES, ORIGEN_TRAS_LAS_VARIANTES_EN):
        assert "enlace" not in texto and "link" not in texto


def test_el_descuento_online_de_un_colombiano_no_es_por_la_web():
    colombiano = " ".join(hechos._descuentos(_estado(is_colombian=True), "es"))
    assert "al reservar por la web" not in colombiano and "al mismo precio online" in colombiano
    extranjero = " ".join(hechos._descuentos(_estado(is_colombian=False), "es"))
    assert "al reservar por la web" in extranjero


def test_la_base_lleva_la_regla_y_la_decision():
    base = Path("data/knowledge_base")
    politicas = json.loads((base / "policies.json").read_text(encoding="utf-8-sig"))["policies"]
    assert {"es", "en"} <= set(politicas["hotel_before_booking"])
    decisiones = json.loads((base / "decisiones.json").read_text(encoding="utf-8-sig"))["decisiones"]
    assert any(d["id"] == "hotel-antes-de-reservar" for d in decisiones)
    preguntas = json.loads((base / "curada" / "preguntas.json").read_text(encoding="utf-8"))["reglas"]
    assert preguntas["politica:hotel_before_booking"]["es"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("sin_hotel", "location"), [(True, "island"), (False, None)])
async def test_a_ya_estaras_en_las_islas_sin_hotel_es_que_si(monkeypatch, sin_hotel, location):
    """A «¿ya estarás en las islas?», «todavía no tenemos hotel» volvía a preguntar desde dónde saldría."""
    monkeypatch.setattr(extractor, "_dice_que_no_tiene_hotel", lambda _state: sin_hotel)
    st = _estado(language="es", detected_activity="certified_diving", is_certified=True,
                 pending_correction={"location": "island"}, core_pending_slot=core.SLOT_CONFIRM_CORRECTION)
    respuesta = str(await route_message(st, "todavía no tenemos hotel"))
    assert st.location == location
    assert not st.pending_correction
    if sin_hotel:
        assert st.hotel == "por confirmar" and "resérvalo primero" in respuesta and "book.divingplanet.org" not in respuesta


def test_el_importe_de_la_otra_salida_no_se_queda():
    """Belgas: el respaldo escribe 392 USD (5 inmersiones desde Cartagena) a quien sale de las islas, que paga 319."""
    st = _estado(language="en", location="island", detected_location="island", hotel="cocoliso",
                 detected_activity="certified_diving", is_certified=True, is_colombian=False)
    respuesta = "The 5-dive package fits perfectly.\n\n- Price per person: 392 USD online (436 USD regular)\n\nWould you like to book?"
    salida = _con_la_pieza(st, respuesta)
    assert salida and "392" not in salida and "436" not in salida and "319 USD" in salida


def test_con_el_importe_de_su_salida_la_pieza_es_la_de_siempre():
    st = _estado(language="en", location="island", detected_location="island", hotel="cocoliso",
                 detected_activity="certified_diving", is_certified=True, is_colombian=False)
    salida = _con_la_pieza(st, "The 5-dive package costs 319 USD online.")
    assert salida and "319 USD" in salida


@pytest.mark.asyncio
@pytest.mark.parametrize(("senales", "mensaje", "hotel"), [
    ({"asks_question": True}, "Ustedes cotizan los hoteles san pedro y cocoliso", "por confirmar"),
    ({"pide_hoteles": True}, "cuál me recomiendan, san pedro o cocoliso", "por confirmar"),
    ({}, "en el Ubuntu", "ubuntu"),
])
async def test_preguntar_por_un_hotel_no_es_alojarse_en_el(monkeypatch, senales, mensaje, hotel):
    from src.agents.nucleo import routing

    st = _estado(language="es", location="island", core_pending_slot=core.SLOT_HOTEL)
    st._senales_router = senales
    assert routing._hotel_por_la_ia(st, mensaje, {"extractor": {}}) is True
    assert st.hotel == hotel


def test_el_hotel_que_dice_el_extractor_vale_aunque_pregunte():
    from src.agents.nucleo import routing

    st = _estado(language="es", location="island", core_pending_slot=core.SLOT_HOTEL)
    st._senales_router = {"asks_question": True}
    assert routing._hotel_por_la_ia(st, "estamos en el Ubuntu, ¿tiene lancha?", {"extractor": {"hotel": "Ubuntu"}}) is True
    assert st.hotel == "ubuntu"


def test_al_quitar_el_enlace_solo_se_va_la_frase_que_lo_anuncia():
    """Mini 0.56: se perdía «Yes, we operate on Easter Sunday» porque estaba en la misma línea que el anuncio del enlace."""
    respuesta = (f"Yes, we operate on Easter Sunday. The website applies the online price, and you can pay there:\n{ENLACE_URL}\n\n"
                 "For the course, bring your referral.")
    salida = compositor.componer(_estado(language="en", location="island"), respuesta, escribio=True)
    assert "Yes, we operate on Easter Sunday." in salida and "For the course, bring your referral." in salida
    assert "pay there" not in salida and "book.divingplanet.org" not in salida


def test_el_fragmento_del_enlace_se_va_con_el_enlace():
    url = "https://book.divingplanet.org/book/referral-already-on-the-island/26?language=en#rvrd-1"
    salida = compositor.componer(_estado(language="en", location="island"), f"We open on Sunday. Book here: {url}", escribio=True)
    assert "rvrd" not in salida and "We open on Sunday." in salida


def test_el_catalogo_no_dice_que_el_precio_online_es_por_reservar_en_la_web():
    from src.flows.catalog import catalog_facts

    for lang, frase in (("es", "por reservar en la web"), ("en", "for booking on the website")):
        assert frase not in catalog_facts(lang).split("\n")[0]
    assert "no reservan por la web" in catalog_facts("es")


def test_salidas_sueltas_no_son_un_paquete():
    """Tanda s05d: «dos salidas de un día, en vez del paquete» seguía con los 2 días de antes y la tarjeta del paquete de 5."""
    from src.agents.jev_router import SALIDAS_SUELTAS

    st = _estado(language="es", detected_activity="certified_diving", detected_duration="multi_day", detected_cert_days=2)
    st._senales_router = {SALIDAS_SUELTAS: True}
    intent = DetectedIntent()
    intent.cert_days = 2
    extractor._poner_duracion(intent, st, {"dias_de_buceo": 2})
    assert intent.duration == "single_day" and intent.cert_days is None and st.detected_cert_days is None
    assert extractor.dias_de_buceo_de({"dias_de_buceo": 2}, st) is None


def test_sin_la_senal_los_dias_siguen():
    st = _estado(language="es", detected_activity="certified_diving")
    intent = DetectedIntent()
    extractor._poner_duracion(intent, st, {"dias_de_buceo": 2})
    assert intent.duration == "multi_day" and intent.cert_days == 2


def test_lo_que_puede_cada_edad_va_en_los_hechos_y_se_exige():
    st = _estado(language="en", location="cartagena", detected_ages=[7, 11, 40], is_colombian=False)
    [b] = hechos.hechos(st, ["precio"], ["certified_diving"])
    notas = b["lo_que_puede_cada_edad"]
    assert len(notas) == 2 and "snorkel" in notas[0].lower()  # los adultos no
    assert any("snorkel" in x.lower() for x in hechos.faltan("The two dives cost 178 USD.", [b], ["precio"]))
    [c] = hechos.hechos(_estado(language="en", location="cartagena", is_colombian=False), ["precio"], ["certified_diving"])
    assert "lo_que_puede_cada_edad" not in c
