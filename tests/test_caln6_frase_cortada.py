"""CALN (27-oct, sparring CALN1-04): si el escritor llega al tope de tokens a mitad de frase, el cliente no la ve cortada."""
import pytest

from src.agents.rag_agent import sin_la_frase_cortada


@pytest.mark.parametrize("cortada,queda", [
    # el turno 1 de la familia de 5: el plan persona a persona no cabía en el tope
    ("Tu hija de 9: Bubble Makers.\n\nUn detalle importante: el minicurso **no certifica**. Así",
     "Tu hija de 9: Bubble Makers.\n\nUn detalle importante: el minicurso **no certifica**."),
    ("¿Te animas? Así sería el pl", "¿Te animas?"),
    ("Opciones:\n• Minicurso\n• Snor", "Opciones:\n• Minicurso"),  # una lista sin puntos: hasta la última línea
    ("Cuesta 630.000 COP online (con el 10 % inclu", "Cuesta 630.000 COP online (con el 10 % inclu"),  # nada acabado
])
def test_se_queda_hasta_la_ultima_frase_acabada(cortada, queda):
    assert sin_la_frase_cortada(cortada) == queda


def test_una_cifra_con_punto_no_es_el_final_de_una_frase():
    assert sin_la_frase_cortada("Son 630.000 COP. Y el minicurso 655.000 C") == "Son 630.000 COP."
