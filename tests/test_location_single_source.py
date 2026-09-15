"""Palabras de lugar con una sola fuente (hallazgo C, 2026-09-15).

El resolutor corto del nucleo tenia su propio `_CARTAGENA_RE`/`_ISLAND_RE` y discrepaba de
`_detect_location` en 29 de 155 mensajes con palabra de lugar: no conocia los apodos de la
ciudad ni los hoteles, y leia isla en "rezar el rosario". Ahora usa el lector del detector,
con su precedencia de siempre en la respuesta (Cartagena nombrada gana).

Medido y revertido: dejar al LLM los mensajes que nombran Cartagena y una isla (salida o
alojamiento frente a destino) fue peor ("vamos de cartagena a baru" pasaba a isla 2/2). Los
dos lectores conservan su precedencia; ese caso sigue abierto.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import IntentDetector
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
    # Precedencia de siempre con los dos lugares: Cartagena nombrada gana en la respuesta.
    ("quiero ir a las islas del rosario desde cartagena", "cartagena"),
    ("estoy en cartagena pero el hotel es en isla grande", "cartagena"),
])
def test_departure_place_answer(message, place):
    assert core._departure_place(message) == place


def _location(message):
    intent = IntentDetector().detect(message, ConversationState(conversation_id="loc"))
    return intent.location, intent.island


@pytest.mark.parametrize("message, expected", [
    ("estoy en Cartagena", ("cartagena", None)),
    ("estoy en Isla Grande", ("island", "isla_grande")),
    ("salimos de la heroica", ("cartagena", None)),
    ("estamos en las islas", ("island", None)),
    ("las mejores islas de colombia", (None, None)),
    ("estoy en cartagena pero el hotel es en isla grande", ("island", "isla_grande")),  # precedencia del detector
])
def test_detector_location_unchanged(message, expected):
    assert _location(message) == expected


def test_the_core_has_no_place_words_of_its_own():
    assert not hasattr(core, "_CARTAGENA_RE")
    assert not hasattr(core, "_ISLAND_RE")
