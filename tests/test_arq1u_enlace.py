"""ARQ-1u (22-oct, flag `enlace_con_como_pagar`): con el enlace de reserva, cómo se reserva y se paga por él, que la reserva
queda confirmada cuando el equipo concilia el pago (política `payment_confirmation`, el texto del aviso
reserva-confirmada-al-pagar) y, si la actividad pide certificación, el carné. Al colombiano no (lo coordina un asesor)."""
import pytest

from src.flows import hechos
from src.flows.state import ConversationState


def _bloque(actividad="certified_diving", lang="es", **campos):
    st = ConversationState(conversation_id="arq1u", language=lang)
    st.location = "cartagena"
    for k, v in campos.items():
        setattr(st, k, v)
    return hechos.hechos(st, ["enlace"], [actividad])[0]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_pago_de_los_colombianos_va_aparte(lang):
    """lat-deuda-u (26-oct): ya no se corta `foreign_card_payment` por una frase; son dos políticas."""
    assert "50" in hechos._politica("payment_colombian", lang) and "50" not in hechos._politica("foreign_card_payment", lang)
    assert hechos._politica("payment_confirmation", lang)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_con_el_enlace_va_como_reservar_pagar_y_la_confirmacion(monkeypatch, lang):
    b = _bloque(lang=lang)
    como = b["como_reservar"]
    assert hechos._politica("how_to_book", lang) in como
    assert hechos._politica("payment_confirmation", lang) in como
    assert hechos._politica("certification_required", lang) in como  # el buceo certificado
    pago = hechos._pago_extranjero(lang)
    assert pago in como and hechos._politica("payment_colombian", lang) not in como  # sin la parte de los colombianos


def test_sin_certificacion_no_va_el_carne(monkeypatch):
    assert hechos._politica("certification_required", "es") not in _bloque("snorkel")["como_reservar"]


def test_al_colombiano_no(monkeypatch):
    b = _bloque(is_colombian=True)
    assert b["enlace"] == {"asesor": True} and "como_reservar" not in b


def test_arq3_echa_de_menos_la_confirmacion(monkeypatch):
    b = _bloque("snorkel")
    sin_confirmacion = " ".join(c for c in b["como_reservar"] if "concilia" not in c) + " " + " ".join(b["enlace"].values())
    perdidos = hechos.faltan(sin_confirmacion, [b], ["enlace"])
    assert perdidos == [hechos._politica("payment_confirmation", "es")]
