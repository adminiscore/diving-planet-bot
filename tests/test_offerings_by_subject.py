"""Reparto de ofertas por persona leido como comparacion (hallazgo E, 2026-09-15).

"tengo un amigo que quiere bucear y yo hago snorkel": el router marcaba
`comparing_options` 3/3 con el LLM real y el nucleo lo aceptaba, asi que iba a RAG a
explicar la diferencia en vez de a la reserva. Se arreglo con un veto sobre la señal del
router (cada oferta con su propio sujeto, `_offerings_with_own_subject`). ex-9b paso 5
(`deliberacion_por_jev`, promocionado y quitado en la limpieza ex9b): si la IA contesta,
manda `comparing_options` (Jev ya separa el reparto de la duda) y el veto se quito; si la
IA calla, decide la frase de duda escrita. `clause_subject` sigue en el detector.
lat-11 T6d (26-oct): fuera el test de `clause_subject` (se quitó con IntentDetector; el reparto lo decide el extractor).
"""

from src.agents import conversational_core as core


def test_explicit_doubt_wins_over_the_split():
    # La duda escrita decide cuando la IA calla: sigue siendo comparacion.
    assert core._is_deliberation_between_options("mi novia bucea y yo no sé si snorkel o minicurso", {}) is True
