"""ARQ-8b (23-oct, flag `hotel_de_las_islas_da_origen`; g10-051): «We'll be staying at the Ubuntu hotel… how much…?» con
Jev a 0,52 en el lugar. El extractor lee el hotel y CAL-C3e lo sabe de las islas, pero el origen solo lo ponía al
guardar el estado, después de contestar: el redactor daba las dos variantes y preguntaba desde dónde sale. Sin red."""
from src.agents import redactor_hechos
from src.flows.state import ConversationState


def _st():
    st = ConversationState(conversation_id="arq8b", language="en")
    st._jev_lugar = {"choice": "islands", "confidence": 0.52}
    return st


def test_el_hotel_de_las_islas_da_el_origen(monkeypatch):
    assert redactor_hechos._origen(_st(), {"hotel": "Ubuntu hotel"}) == "island"
    assert redactor_hechos._origen(_st(), {"hotel": "Hotel Caribe"}) is None  # Cartagena: no adivina
    assert redactor_hechos._origen(_st(), {}) is None


def test_los_hoteles_de_la_base_que_el_detector_no_tiene(monkeypatch):
    """g10-051 es Las Palmeras: el detector (CAL-C3e) no lo tiene, la lista de la base (gen-15) sí."""
    for hotel in ("Eco Hotel Las Palmeras", "Las Palmeras", "hotel Mulata", "Rosario de Mar", "Hotel Majagua"):
        assert redactor_hechos._origen(_st(), {"hotel": hotel}) == "island", hotel


def test_un_hotel_de_cartagena_no_da_el_origen(monkeypatch):
    for hotel in ("Hotel Charleston Santa Teresa", "Hotel Caribe", "Hotel Las Américas", "hotel"):
        assert redactor_hechos._origen(_st(), {"hotel": hotel}) is None, hotel
