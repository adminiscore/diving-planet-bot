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


def test_named_companion_counts_as_one_with_the_known_total():
    """"mi amigo no esta certificado" con el grupo de 2 ya sabido (r11, decision del owner):
    el amigo queda sin decidir y se le recomiendan opciones (2026-09-15)."""
    state = ConversationState(conversation_id="c")
    state.detected_group_size = 2
    intent = IntentDetector().detect("mi amigo no esta certificado", state)
    assert intent.group_allocation == {"certified_diving": 1, "undecided": 1}
    assert intent.is_certified is None


def test_named_companion_without_a_total_is_not_split():
    assert _alloc("mi amigo no esta certificado") is None


@pytest.mark.parametrize("message", [
    "mi novia es buza certificada y yo nunca he buceado",
    "soy buzo certificado y mi novia no esta certificada",
])
def test_one_other_person_and_the_writer_with_opposite_status(message):
    """Una persona nombrada y quien escribe, cada uno con su certificacion y de signo
    contrario: 1 certificado y 1 sin decidir, total 2, sin depender del LLM (2026-09-15)."""
    intent = IntentDetector().detect(message, ConversationState(conversation_id="c"))
    assert intent.group_allocation == {"certified_diving": 1, "undecided": 1}
    assert intent.group_size == 2


@pytest.mark.parametrize("known_total, expected", [
    (2, {"certified_diving": 1, "undecided": 1}),      # las dos personas cuadran con el total
    (4, None),                                         # serian 2 de 4: no se reparte
])
def test_person_split_respects_the_known_total(known_total, expected):
    state = ConversationState(conversation_id="c")
    state.detected_group_size = known_total
    intent = IntentDetector().detect("mi novia es buza certificada y yo nunca he buceado", state)
    assert intent.group_allocation == expected


@pytest.mark.parametrize("message", [
    "mi novia es buza certificada y yo tambien",       # mismo estado: nada que repartir
    # "mi amigo tiene licencia, yo no" ya reparte: la frase eliptica se lee por su
    # polaridad (hallazgo I, 2026-09-15, tests/test_elided_certification_contrast.py).
    "mi amigo no tiene licencia y yo tampoco",         # misma polaridad: nada que repartir
    "soy buzo certificado y vengo con mi pareja",      # la pareja sin certificacion dicha
])
def test_no_person_split_without_both_opposite_statements(message):
    assert _alloc(message) is None


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
