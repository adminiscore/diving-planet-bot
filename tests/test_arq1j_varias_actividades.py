"""ARQ-1j (22-oct): los hechos del acompañante (precio y qué incluye). El campo `actividades_preguntadas` del extractor
(flag `varias_actividades`) se descartó con banco y se borró en sim-6."""

from src.flows import hechos as h
from src.flows.state import ConversationState

MENSAJE = "Somos un buzo certificado y un acompañante, ¿cuánto pagamos?"


def _conv(**campos) -> ConversationState:
    st = ConversationState(conversation_id="arq1j", language="es")
    st.history = [{"role": "user", "content": MENSAJE}]
    st._intenciones = ["precio"]
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_los_hechos_del_acompanante():
    [buzo, acompanante] = h.hechos(_conv(location="cartagena", is_colombian=True), ["precio", "incluye"],
                                   ["certified_diving", "companion"])
    assert acompanante["precio"]["cartagena"]["online"] == "288.000 COP"
    assert "Almuerzo" in acompanante["incluye"]["cartagena"]
    [acompanante] = h.hechos(_conv(location="island"), ["incluye"], ["companion"])
    assert "Almuerzo" not in acompanante["incluye"]["island"]
