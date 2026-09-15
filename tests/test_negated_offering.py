"""Una oferta negada no es una opcion que se sopesa (hallazgo K, 2026-09-15).

"al final mi suegra tambien bucea, no hace snorkel" tras cerrar la reserva: el router
marcaba `comparing_options` y la puerta de deliberacion lo aceptaba (2 ofertas, sin cifra
ni "quiero"), asi que el cambio de reparto se iba a RAG a explicar la diferencia (2/2 con
el LLM real). El snorkel esta negado: se descarta, no se compara. La negacion es la pieza
del detector (`_is_negated`), sin palabras nuevas.
"""

import pytest

from src.agents import conversational_core as core

COMPARING = {"comparing_options": {"comparing": True}}


@pytest.mark.parametrize("message, weighed", [
    ("al final mi suegra tambien bucea, no hace snorkel", {"certified_diving"}),
    ("no quiero snorkel, mejor buceo", {"certified_diving"}),
    ("prefiero no bucear, snorkel o minicurso", {"snorkel", "minicourse"}),
    ("mi pareja se lo está pensando, buceo y snorkel", {"certified_diving", "snorkel"}),
    ("no es que no quiera bucear, pero el snorkel tambien me gusta", {"certified_diving", "snorkel"}),
    ("no quiero hacer snorkel, mejor bucear", {"certified_diving"}),
    # Una pregunta subordinada corta el alcance: el "no" niega saber, no las ofertas (control de E).
    ("mi amigo no sabe si bucear o hacer snorkel", {"certified_diving", "snorkel"}),
    ("not sure whether to snorkel or dive", {"certified_diving", "snorkel"}),
])
def test_negated_offerings_are_not_weighed(message, weighed):
    assert core._weighed_offerings(message) == weighed


@pytest.mark.parametrize("message", [
    "al final mi suegra tambien bucea, no hace snorkel",
    "no quiero snorkel, mejor buceo",
])
def test_a_discarded_offering_is_not_a_comparison(message):
    assert core._is_deliberation_between_options(message, COMPARING) is False


@pytest.mark.parametrize("message, signals", [
    ("prefiero no bucear, snorkel o minicurso", COMPARING),
    ("no sé si buceo o snorkel", {}),            # la duda escrita gana, aunque empiece por "no"
    ("no me decido entre buceo y snorkel", {}),
])
def test_real_comparisons_are_kept(message, signals):
    assert core._is_deliberation_between_options(message, signals) is True
