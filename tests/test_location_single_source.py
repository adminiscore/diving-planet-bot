"""Ubicacion: una sola fuente de palabras de lugar (C), papel de cada lugar (C.2) y formas
cortas de isla (C.3) (2026-09-15/16).

- C: el resolutor corto del nucleo tenia su propio `_CARTAGENA_RE`/`_ISLAND_RE` (sin apodos
  ni hoteles, e isla en "rezar el rosario"); ahora usa el lector del detector.
- C.2: con Cartagena Y una isla, la preposicion que lleva cada lugar dice si es estancia,
  origen o destino. Dejarlo al LLM se midio y fue peor (tambien toma el destino por la
  ubicacion), asi que es estructura, sin palabras de dominio.
- C.3: "grande", "marina", "arena"... sueltas son palabras corrientes: solo cuentan como la
  isla "Isla X" si el mensaje nombra una isla.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import IntentDetector, place_by_role
from src.flows.state import ConversationState


@pytest.mark.parametrize("message, place", [
    ("isla", "island"),
    ("las islas", "island"),
    ("Barú", "island"),
    ("Hotel Pao Pao", "island"),         # hoteles: antes solo los conocia el detector
    ("La Heroica", "cartagena"),         # apodos: idem
    ("the Walled City", "cartagena"),
    ("desde cartagena", "cartagena"),
    ("salimos desde cartagenaa mañana", "cartagena"),
    ("rezar el rosario", None),          # la oracion no es la isla
    ("no sé", None),
    # C.2: el papel de cada lugar
    ("quiero ir a las islas del rosario desde cartagena", "cartagena"),
    ("estoy en cartagena pero el hotel es en isla grande", "island"),
    ("we're in cartagena now, staying on the islands tomorrow", "island"),
    ("salimos desde cartagena, no estamos en las islas", "cartagena"),
    ("llegamos a cartagena y luego nos vamos a baru", "cartagena"),
    ("vamos de cartagena a baru", "cartagena"),
])
def test_departure_place_answer(message, place):
    assert core._departure_place(message) == place


@pytest.mark.parametrize("text, place", [
    ("quiero ir a las islas del rosario desde cartagena", "cartagena"),   # destino frente a origen
    ("estoy en cartagena, mañana nos vamos a las islas", "cartagena"),    # estancia frente a destino
    ("nos quedamos en baru, vamos a cartagena de paseo", "island"),
    ("we are staying at isla grande, arriving from cartagena", "island"),  # estancia gana al origen
    ("estoy en cartagena pero el hotel es en isla grande", "island"),     # la ultima estancia
    ("salimos desde cartagena, no estamos en las islas", "cartagena"),    # la estancia negada no cuenta
    ("no sé si cartagena o las islas", None),                             # sin preposicion: precedencia de siempre
])
def test_place_by_role(text, place):
    assert place_by_role(text) == place


def test_an_island_hotel_is_lodging():
    assert place_by_role("estoy en cartagena y me hospedo en el hotel pao pao", lodging_island=True) == "island"


def _location(message):
    intent = IntentDetector().detect(message, ConversationState(conversation_id="loc"))
    return intent.location, intent.island


@pytest.mark.parametrize("message, expected", [
    ("estoy en Cartagena", ("cartagena", None)),
    ("estoy en Isla Grande", ("island", "isla_grande")),
    ("salimos de la heroica", ("cartagena", None)),
    ("estamos en las islas", ("island", None)),
    ("las mejores islas de colombia", (None, None)),
    ("estoy en cartagena pero el hotel es en isla grande", ("island", "isla_grande")),
    ("quiero ir a las islas del rosario desde cartagena", ("cartagena", None)),
    ("we're in cartagena now, staying on the islands tomorrow", ("island", None)),
    ("estoy en cartagena y me hospedo en el hotel pao pao", ("island", "isla_grande")),
    ("no sé si cartagena o las islas", ("cartagena", None)),
])
def test_detector_location(message, expected):
    assert _location(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("somos un grupo grande", (None, None)),
    ("nos vemos en la marina", (None, None)),
    ("la arena es blanca", (None, None)),
    ("estoy en la isla, la grande", ("island", "isla_grande")),   # con una isla nombrada, la forma corta vale
    ("estoy en isleta", ("island", "isleta")),
    ("me hospedo en cocoliso", ("island", "isla_grande")),        # los hoteles no cambian
])
def test_short_island_names_need_an_island(message, expected):
    assert _location(message) == expected


def test_the_core_has_no_place_words_of_its_own():
    assert not hasattr(core, "_CARTAGENA_RE")
    assert not hasattr(core, "_ISLAND_RE")
