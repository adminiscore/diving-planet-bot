"""ARQ-8b (23-oct, flag `hotel_de_las_islas_da_origen`; g10-051): «We'll be staying at the Ubuntu hotel… how much…?» con
Jev a 0,52 en el lugar. El extractor lee el hotel y CAL-C3e lo sabe de las islas, pero el origen solo lo ponía al
guardar el estado, después de contestar: el redactor daba las dos variantes y preguntaba desde dónde sale. Sin red."""
from src.agents import redactor_hechos
from src.config import settings
from src.flows.state import ConversationState


def _st():
    st = ConversationState(conversation_id="arq8b", language="en")
    st._jev_lugar = {"choice": "islands", "confidence": 0.52}
    return st


def test_el_hotel_de_las_islas_da_el_origen(monkeypatch):
    monkeypatch.setattr(settings, "hotel_de_las_islas_da_origen", True)
    assert redactor_hechos._origen(_st(), {"hotel": "Ubuntu hotel"}) == "island"
    assert redactor_hechos._origen(_st(), {"hotel": "Hotel Caribe"}) is None  # Cartagena: no adivina
    assert redactor_hechos._origen(_st(), {}) is None


def test_apagado_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "hotel_de_las_islas_da_origen", False)
    assert redactor_hechos._origen(_st(), {"hotel": "Ubuntu hotel"}) is None
