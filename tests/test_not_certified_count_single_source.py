""""N no estan certificados" usa la misma fuente de certificacion (2026-09-15).

El reparto "{certificados: resto, undecided: N}" tenia un patron propio que solo
conocia "cert*": "dos no tienen licencia" o "uno no es buzo" quedaban sin reparto, y
"we are 4 and two are not certified" repartia 3/1. Ahora la frase que sigue a la
cantidad se juzga con `certification_claim`.
"""

import pytest

from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState


def _alloc(message):
    return IntentDetector().detect(message, ConversationState(conversation_id="c")).group_allocation


@pytest.mark.parametrize("message, expected", [
    ("somos 4 y dos no tienen licencia", {"certified_diving": 2, "undecided": 2}),
    ("somos 4 personas, dos no son buzos", {"certified_diving": 2, "undecided": 2}),
    ("we are 4 and two are not certified", {"certified_diving": 2, "undecided": 2}),
    ("somos 3, uno no tiene licencia", {"certified_diving": 2, "undecided": 1}),
    ("somos 4, 2 sin certificar", {"certified_diving": 2, "undecided": 2}),
    ("somos 5, dos no están certificados", {"certified_diving": 3, "undecided": 2}),
])
def test_negated_count_splits_the_group(message, expected):
    assert _alloc(message) == expected


def test_main_activity_never_contradicts_the_allocation():
    """"somos 5 y 2 nunca han buceado" reparte 3 certificados; la actividad principal
    no puede quedarse en minicurso (regla general de detect(), 2026-09-15)."""
    intent = IntentDetector().detect("somos 5 y 2 nunca han buceado", ConversationState(conversation_id="c"))
    assert intent.group_allocation == {"certified_diving": 3, "undecided": 2}
    assert intent.activity == "certified_diving"


@pytest.mark.parametrize("message", [
    "somos 3 y 1 quiere certificarse",   # ya eligio: no es un tramo sin actividad
    "somos 4 y los 4 estamos certificados",
    "somos 3",
])
def test_no_split_without_a_negated_count(message):
    assert _alloc(message) is None
