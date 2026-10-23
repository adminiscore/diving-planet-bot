"""gen-4 (21-oct), flag `vivir_no_es_residir`: vivir en Colombia no es ser residente (G9, causa 6).

Banco docs/robustness/gen/banco_gen4_moneda.py (Haiku, 18 frases, 5 pasadas): 65/90 → 85/90; quien solo dice que vive
(o nació) en Colombia 5/30 → 25/30 sin nacionalidad; colombianos y residentes con cédula 40/40 igual; extranjeros sin
cédula 20/20 igual.
"""

import pytest

from src.agents import extractor_turno as ex
from src.agents.conversational_core import SLOT_NATIONALITY, ask_slot
from src.flows.state import ConversationState


@pytest.mark.parametrize("prompt", [ex.SISTEMA_ES, ex.SISTEMA_EN], ids=["es", "en"])
def test_cada_frase_que_se_cambia_esta_en_el_prompt(prompt):
    """Si alguien reescribe el prompt, el cambio dejaría de aplicarse sin avisar: se fija aquí (con la regla de la
    cédula y la del residente encendidas, como en PRE)."""
    texto = prompt.replace(ex.SIN_CEDULA_HOY_ES, ex.SIN_CEDULA_ES).replace(ex.SIN_CEDULA_HOY_EN, ex.SIN_CEDULA_EN)
    texto = texto.replace(ex.RESIDENTE_HOY_ES, ex.RESIDENTE_ES).replace(ex.RESIDENTE_HOY_EN, ex.RESIDENTE_EN)
    idioma = [(a, b) for a, b in ex._VIVIR_NO_ES_RESIDIR if a in texto]
    assert len(idioma) == 1  # la frase de su idioma, a la que se añade la regla


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("plural", [False, True])
def test_la_pregunta_nombra_la_cedula_con_el_flag(monkeypatch, lang, plural):
    st = ConversationState(conversation_id="gen4", language=lang)
    st.detected_group_size = 3 if plural else 1
    con = ask_slot(st, SLOT_NATIONALITY)
    assert "cédula de extranjería" in con
    assert "resident" not in con  # ni "residente" ni "resident": se contestaba "vivo aquí" (Gonzalo, #852)
    assert "colombiano" not in con  # sin género supuesto


@pytest.mark.parametrize("prompt", [ex.SISTEMA_ES, ex.SISTEMA_EN], ids=["es", "en"])
def test_gen14_la_frase_que_cambia_sigue_en_el_prompt(prompt):
    """gen-14 (`gentilicio_es_colombiano`): se aplica sobre el texto que deja `vivir_no_es_residir`."""
    texto = prompt
    for a, b in ex._VIVIR_NO_ES_RESIDIR:
        texto = texto.replace(a, b)
    assert sum(1 for a, _b in ex._GENTILICIO_ES_COLOMBIANO if a in texto) == 1


def test_en_ingles_la_cedula_se_explica_sin_residents(monkeypatch):
    """Decisión de Gadea (#1078): en inglés, «cédula de extranjería» con una explicación corta y sin «residents»."""
    st = ConversationState(conversation_id="gen4-en", language="en")
    pregunta = ask_slot(st, SLOT_NATIONALITY)
    assert "Colombia's ID card for foreigners" in pregunta and "resident" not in pregunta
