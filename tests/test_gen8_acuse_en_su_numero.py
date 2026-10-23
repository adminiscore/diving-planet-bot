"""gen-8 (21-oct), flag `acuse_en_su_numero`: el ejemplo del acuse ya no da una frase en plural para copiar.

Banco docs/robustness/gen/banco_gen8_acuse.py (gpt-5.4-nano, 5 pasadas): a quien va solo, frases en plural 4/35 → 0/35
("I'm not Colombian" → "none of you are Colombian"); los grupos siguen en plural.
"""

import pytest

from src.agents import llm_extractor
from src.prompts import booking


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_ejemplo_del_acuse_va_en_su_numero(lang):
    texto = llm_extractor._acuse_en_su_numero(booking.acknowledgement_system_prompt(lang, None))
    viejo = booking.ACUSE_EJEMPLO_ES if lang == "es" else booking.ACUSE_EJEMPLO_EN
    nuevo = booking.ACUSE_EN_SU_NUMERO_ES if lang == "es" else booking.ACUSE_EN_SU_NUMERO_EN
    assert viejo not in texto
    assert nuevo in texto


def test_el_ejemplo_viejo_esta_en_el_prompt_de_siempre():
    """Si alguien reescribe el prompt, el reemplazo dejaría de aplicarse sin avisar: se fija aquí."""
    assert booking.ACUSE_EJEMPLO_ES in booking.acknowledgement_system_prompt("es", None)
    assert booking.ACUSE_EJEMPLO_EN in booking.acknowledgement_system_prompt("en", None)
