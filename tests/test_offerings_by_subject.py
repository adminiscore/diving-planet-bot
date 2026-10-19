"""Reparto de ofertas por persona leido como comparacion (hallazgo E, 2026-09-15).

"tengo un amigo que quiere bucear y yo hago snorkel": el router marcaba
`comparing_options` 3/3 con el LLM real y el nucleo lo aceptaba, asi que iba a RAG a
explicar la diferencia en vez de a la reserva. Se arreglo con un veto sobre la señal del
router (cada oferta con su propio sujeto, `_offerings_with_own_subject`). ex-9b paso 5
(`deliberacion_por_jev`, promocionado y quitado en la limpieza ex9b): si la IA contesta,
manda `comparing_options` (Jev ya separa el reparto de la duda) y el veto se quito; si la
IA calla, decide la frase de duda escrita. `clause_subject` sigue en el detector.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import clause_subject


def test_explicit_doubt_wins_over_the_split():
    # La duda escrita decide cuando la IA calla: sigue siendo comparacion.
    assert core._is_deliberation_between_options("mi novia bucea y yo no sé si snorkel o minicurso", {}) is True


@pytest.mark.parametrize("clause, subject", [
    ("tengo un amigo que quiere bucear", "other"),
    ("mis amigos bucean", "other"),
    (" yo hago snorkel", "writer"),
    (" i'll dive", "writer"),
    ("yo buceo con mi novia", None),
    ("buceo y snorkel", None),
])
def test_clause_subject(clause, subject):
    assert clause_subject(clause) == subject
