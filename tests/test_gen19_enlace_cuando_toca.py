"""gen-19 (21-oct, flag `enlace_cuando_toca`): con el origen y el plan sabidos, si la respuesta da el precio de ese plan
sin su enlace de reserva, el código añade el del catálogo. No a colombianos ni a grupos mixtos ni en los planes que
cierra un asesor. Y el Referido ya se reserva con su enlace (decisión de Gadea, 21-oct)."""
import pytest

from src.agents import conversational_core as cc
from src.config import settings
from src.flows import cart_render
from src.flows.catalog import catalog_booking_links
from src.flows.state import ConversationState

ISLAS_SNORKEL = "El snorkel ya en las islas cuesta 45 USD online.\n\n¿Quieres que te cuente cómo es el día?"


@pytest.fixture(autouse=True)
def con_flag(monkeypatch):
    monkeypatch.setattr(settings, "enlace_cuando_toca", True)


def _conv(lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="gen19", language=lang)
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_con_origen_plan_y_precio_va_el_enlace_antes_de_la_pregunta():
    texto = cc._con_enlace_si_toca(_conv(location="island", actividad_preguntada="snorkel"), ISLAS_SNORKEL)
    parrafos = texto.split("\n\n")
    assert "snorkeling-already-on-the-island" in parrafos[1] and parrafos[-1].endswith("?")


def test_en_ingles_el_enlace_en_ingles():
    texto = cc._con_enlace_si_toca(_conv("en", location="cartagena", actividad_preguntada="minicourse"),
                                   "The mini-course costs 183 USD online.")
    assert "language=en" in texto and "You can book it here" in texto


@pytest.mark.parametrize("campos, respuesta", [
    ({"location": "island", "actividad_preguntada": "snorkel", "is_colombian": True}, ISLAS_SNORKEL),
    ({"location": "island", "actividad_preguntada": "snorkel", "mixed_nationality_notice": True}, ISLAS_SNORKEL),
    ({"actividad_preguntada": "snorkel"}, ISLAS_SNORKEL),                         # sin origen
    ({"location": "island"}, ISLAS_SNORKEL),                                       # sin plan
    ({"location": "island", "actividad_preguntada": "snorkel"}, "El snorkel es precioso."),  # sin precio
    ({"location": "island", "actividad_preguntada": "minicourse"}, ISLAS_SNORKEL),  # el precio es de otro plan
    ({"location": "cartagena", "actividad_preguntada": "padi_divemaster"}, "Cuesta 1.000 USD."),  # lo cierra un asesor
    ({"location": "island", "actividad_preguntada": "snorkel"},
     "Cuesta 45 USD: https://book.divingplanet.org/book/snorkeling-already-on-the-island/25"),  # ya lo lleva
])
def test_cuando_no_toca_no_cambia(campos, respuesta):
    assert cc._con_enlace_si_toca(_conv(**campos), respuesta) == respuesta


def test_apagado_no_cambia(monkeypatch):
    monkeypatch.setattr(settings, "enlace_cuando_toca", False)
    st = _conv(location="island", actividad_preguntada="snorkel")
    assert cc._con_enlace_si_toca(st, ISLAS_SNORKEL) == ISLAS_SNORKEL


def test_el_referido_se_reserva_con_su_enlace():
    assert not cart_render._is_contact_only_service("referral")
    assert "book/referral/6" in catalog_booking_links("es")
    assert "referral-already-on-the-island" in catalog_booking_links("es")
