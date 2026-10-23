"""arq-5d (23-oct, sin flag): dos errores del G10 nº 5 que no pueden empeorar nada al arreglarlos.

- g10-065: el aviso final devolvió la frase «null» y llegó al cliente como un párrafo suelto.
- g10-020: el redactor contestó en portugués en una conversación en inglés (decisión de Gadea: inglés).
"""

import pytest

from src.agents import rag_plan
from src.agents.redactor_hechos import _en_otro_idioma


@pytest.mark.parametrize("frase", ["null", "None", " NULL. ", '""', "n/a", ""])
def test_el_nulo_de_un_modelo_no_se_inserta(frase):
    assert rag_plan.insertar_frase("La propina es voluntaria.", frase) == "La propina es voluntaria."


def test_una_frase_de_verdad_si_se_inserta():
    assert rag_plan.insertar_frase("Hola.", "Operamos todos los días.").endswith("Operamos todos los días.")


_PT = ("Claro! Você pode reservar pelo site neste link. Há 10% de desconto ao reservar diretamente pelo nosso site; ele é "
       "aplicado automaticamente. O sistema fecha às 16h30 do dia anterior e depois desse horário dá para reservar.")
_EN = ("From Cartagena, snorkeling includes the National Park entrance fee, activity insurance, boat transport and lunch. "
       "You meet at Muelle de la Bodeguita, 5 minutes from the historic center, at 8:00 AM, in the Islas del Rosario.")


@pytest.mark.parametrize("texto, lang, otro", [(_PT, "en", True), (_EN, "en", False), (_EN, "es", True),
                                                ("Sí, a las 8:00.", "en", False)])
def test_la_redaccion_en_otro_idioma(texto, lang, otro):
    assert _en_otro_idioma(texto, lang) is otro
