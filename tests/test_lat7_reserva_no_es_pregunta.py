"""lat-7 (25-oct, fase LAT): pedir algo de la reserva sin preguntar nada («quiero bucear certificado», «hi, i want to book
a dive») no es una pregunta para el RAG. Jev daba `asks_question` y la apertura pasaba por el RAG (3-9 s, con el saludo
repetido); ahora la contesta el flujo con su siguiente pregunta. Sin red."""
import pytest

from src.agents import conversational_core as core
from src.agents import jev_router as j


@pytest.mark.parametrize("mensaje", ["quiero bucear certificado", "hi, i want to book a dive", "Hola, me gustaría reservar"])
def test_pedir_reservar_sin_preguntar_no_es_pregunta(mensaje):
    senales = {"asks_question": True, j.PIDE_OTRA_COSA: False}
    assert core._turn_has_question(mensaje, senales) is False


@pytest.mark.parametrize("mensaje,senales", [
    ("quiero bucear certificado, cuanto cuesta", {"asks_question": True, j.PIDE_OTRA_COSA: False, j.PIDE_PRECIO: True}),
    ("quiero bucear y saber que peces se ven", {"asks_question": True, j.PIDE_OTRA_COSA: True}),
    ("perfecto, como pago", {"asks_question": True}),  # Jev no se pronuncia sobre «otra cosa»: como siempre
    ("quiero bucear certificado?", {"asks_question": False, j.PIDE_OTRA_COSA: False}),  # el «?» manda
])
def test_sigue_siendo_pregunta(mensaje, senales):
    assert core._turn_has_question(mensaje, senales) is True


def test_sin_jev_decide_el_regex_como_siempre():
    assert core._turn_has_question("cuánto cuesta el snorkel", {}) == core._looks_like_question("cuánto cuesta el snorkel")
