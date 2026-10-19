"""ex-9b (19-oct, flag `aviso_pago_al_reservar`): el aviso "el pago se registra al momento y el equipo lo concilia para
confirmar la reserva" salía solo con el tema "pago". Cuando la pregunta iba de CÓMO reservar, el RAG decía "al pagar
quedas confirmado", en contra de la decisión de Gadea (16-17 oct). Con el flag, `tambien` añade el tema "reservar" y
las fuentes de cómo reservar."""

import pytest

from src.config import settings
from src.flows import avisos as av
from src.flows.state import ConversationState

AVISO = "reserva-confirmada-al-pagar"


def _hechos() -> dict:
    return av.hechos_del_estado(ConversationState(conversation_id="aviso-pago", language="es"))


@pytest.mark.parametrize("encendido, sale", [(False, False), (True, True)])
def test_sale_cuando_la_pregunta_va_de_como_reservar(monkeypatch, encendido, sale):
    monkeypatch.setattr(settings, "aviso_pago_al_reservar", encendido)
    elegidos = [a["id"] for a in av.seleccionar(_hechos(), {"reservar"}, {"how_to_book"})]
    assert (AVISO in elegidos) is sale


@pytest.mark.parametrize("encendido", [False, True])
def test_con_el_tema_pago_sale_como_siempre(monkeypatch, encendido):
    monkeypatch.setattr(settings, "aviso_pago_al_reservar", encendido)
    assert AVISO in [a["id"] for a in av.seleccionar(_hechos(), {"pago"}, {"payment_fallback"})]


def test_sin_su_fuente_entre_las_primeras_no_sale(monkeypatch):
    monkeypatch.setattr(settings, "aviso_pago_al_reservar", True)
    assert AVISO not in [a["id"] for a in av.seleccionar(_hechos(), {"reservar"}, {"food_policy"})]
