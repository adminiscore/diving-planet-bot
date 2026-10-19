"""Una oferta negada no es una opcion que se sopesa (hallazgo K, 2026-09-15).

"al final mi suegra tambien bucea, no hace snorkel" tras cerrar la reserva: el router
marcaba `comparing_options` y la puerta de deliberacion lo aceptaba, asi que el cambio de
reparto se iba a RAG a explicar la diferencia (2/2 con el LLM real). Se arreglo con un veto
sobre la señal del router (`_weighed_offerings`). ex-9b paso 5 (`deliberacion_por_jev`,
promocionado y quitado en la limpieza ex9b): si la IA contesta, manda `comparing_options`
(ni Jev ni DeepSeek cometen ya este error: 12/12 el 19-oct) y el veto se quito; si la IA
calla, decide la frase de duda escrita, que se sigue probando aqui.
"""

import pytest

from src.agents import conversational_core as core

COMPARING = {"comparing_options": {"comparing": True}}


@pytest.mark.parametrize("message, signals", [
    ("prefiero no bucear, snorkel o minicurso", COMPARING),
    ("no sé si buceo o snorkel", {}),            # la duda escrita gana, aunque empiece por "no"
    ("no me decido entre buceo y snorkel", {}),
])
def test_real_comparisons_are_kept(message, signals):
    assert core._is_deliberation_between_options(message, signals) is True
