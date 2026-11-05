"""CALN-35: cómo reserva cada cliente, en un solo sitio (decisiones de Gadea `pago-y-reserva` y `hotel-antes-de-reservar`)."""
import json
from pathlib import Path

import pytest

from src.agents import compositor
from src.agents import conversational_core as core
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor, slotfill_close
from src.agents.nucleo.origen_precio import (
    ORIGEN_TRAS_LAS_VARIANTES_EN,
    ORIGEN_TRAS_LAS_VARIANTES_ES,
)
from src.flows import hechos
from src.flows.como_reserva import ASESOR, ENLACE, HOTEL_PRIMERO, como_reserva, hotel_conocido
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
])
def test_como_reserva(campos, esperado):
    assert como_reserva(_estado(**campos)) == esperado


def test_por_confirmar_no_es_un_hotel():
    assert hotel_conocido(_estado(hotel="por confirmar", detected_hotel="por confirmar")) is None
    assert hotel_conocido(_estado(detected_hotel="ubuntu")) == "ubuntu"


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
    assert segunda == slotfill_close._HOTEL_PRIMERO_YA_DICHO["es_uno"]


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
