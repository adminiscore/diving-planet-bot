"""Alcance de la negacion en `certification_claim` y "N inmersiones" como buceo
certificado (2026-09-15).

"2 no tienen certificación" y "two aren't certified" casaban el patron positivo y
salian True. No se anade cada frase negativa: una afirmacion precedida de cerca por
una negacion no cuenta, y la doble negacion se cancela.
lat-11 T6d (26-oct): fuera el test de IntentDetector.detect ("N inmersiones" como buceo certificado; la clase se
quitó y la actividad la decide el extractor).
"""

import pytest

from src.agents.intent_detector import certification_claim


@pytest.mark.parametrize("message", [
    "no tenemos certificación",
    "we aren't certified divers",
    "no tengo licencia de buceo",
])
def test_negated_claim_is_not_certified(message):
    assert certification_claim(message) is False


@pytest.mark.parametrize("message", ["2 no tienen certificación", "two aren't certified"])
def test_negation_about_others_is_not_the_writers(message):
    # La negacion se sigue leyendo, pero habla de otros (2026-09-15): quien escribe queda
    # sin senal y el reparto usa `about_writer=False`.
    assert certification_claim(message, about_writer=False) is False
    assert certification_claim(message) is None


@pytest.mark.parametrize("message", [
    "tengo certificación padi",
    "somos 2 buzos certificados",
    "no, ya soy certificado",
    "no es que no estemos certificados, si lo estamos, los 2",
])
def test_affirmative_claim_survives(message):
    assert certification_claim(message) is True
