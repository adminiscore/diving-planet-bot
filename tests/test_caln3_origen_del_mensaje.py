"""CALN-3 (27-oct; CALN1-03 y el sparring CALN2 de Gadea, #2136): «al final vamos a estar en Isla Grande, ¿cambia el
precio?» se cotizaba desde Cartagena, el origen guardado ANTES del turno («No tengo aquí el precio para Isla Grande»).
Si los dos lectores de ESTE mensaje dicen el mismo origen (el extractor y Jev seguro), los hechos del escritor van con
ese. Con uno solo no: «snorkel en las islas» lo lee el extractor y Jev dice none (CAL-C3c). Sin red."""
import pytest

from src.agents import redactor_hechos
from src.flows.state import ConversationState


def _st(jev, guardado="cartagena"):
    st = ConversationState(conversation_id="caln3", language="es", location=guardado)
    st._jev_lugar = {"choice": jev[0], "confidence": jev[1]} if jev else None
    return st


@pytest.mark.parametrize("jev, origen", [
    (("islands", 0.95), "island"),    # los dos lectores: manda el mensaje
    (("none", 0.95), "cartagena"),    # Jev dice que el mensaje no lo da (CAL-C3c): lo guardado
    (("islands", 0.40), "cartagena"),  # Jev duda: lo guardado
    (None, "cartagena"),              # sin Jev: lo guardado
])
def test_el_origen_del_mensaje_solo_con_los_dos_lectores(jev, origen):
    assert redactor_hechos._origen(_st(jev), {"location": "island"}, leido=True) == origen


def test_sin_origen_guardado_sigue_como_antes():
    assert redactor_hechos._origen(_st(("none", 0.95), guardado=None), {"location": "island"}, leido=True) == "island"
