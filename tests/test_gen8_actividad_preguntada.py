"""gen-8 (21-oct), flag `actividad_de_la_pregunta`: quien pregunta por UNA actividad sin elegirla recibe la oferta de
esa, no el menú de 4 actividades (textos-B, curso-open-water-transporte: "Which one are you leaning toward — diving,
a mini-course…?" a quien llevaba 3 turnos preguntando por el Open Water). Banco docs/robustness/gen/dialogos-gen8-menu.json.
"""

import pytest

from src.agents import extractor_turno as ex
from src.agents.conversational_core import SLOT_ACTIVITY, ask_slot
from src.agents.nucleo import extractor as core_extractor
from src.config import settings
from src.flows.state import ConversationState

_MENU = ("Which one are you leaning toward", "¿Con cuál te animas", "what would you like to experience",
         "¿qué te gustaría vivir")


def _estado(lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="gen8-menu", language=lang)
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


@pytest.mark.parametrize("flag", [False, True])
def test_el_campo_del_extractor_sigue_el_flag(monkeypatch, flag):
    monkeypatch.setattr(settings, "actividad_de_la_pregunta", flag)
    assert ("actividad_preguntada" in ex.campos_paso6([])) is flag


@pytest.mark.parametrize("flag", [False, True])
def test_se_guarda_la_ultima_actividad_preguntada(monkeypatch, flag):
    monkeypatch.setattr(settings, "actividad_de_la_pregunta", flag)
    st = _estado()
    core_extractor._poner_actividad_preguntada(st, {"actividad_preguntada": "minicourse"})
    core_extractor._poner_actividad_preguntada(st, {})  # "¿y cuánto dura?" no nombra ninguna: sigue la misma
    assert st.actividad_preguntada == ("minicourse" if flag else None)


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("reasking", [False, True])
def test_con_el_flag_ofrece_la_actividad_y_no_el_menu(monkeypatch, lang, reasking):
    monkeypatch.setattr(settings, "actividad_de_la_pregunta", True)
    st = _estado(lang, actividad_preguntada="snorkel")
    texto = ask_slot(st, SLOT_ACTIVITY, reasking=reasking)
    assert not any(m in texto for m in _MENU)
    assert "Snorkel" in texto
    assert st.suggested_activity == "snorkel"  # "sí" la confirma (nucleo/routing)
    assert len(st.quick_replies) == 1


def test_sin_el_flag_el_menu_de_siempre(monkeypatch):
    monkeypatch.setattr(settings, "actividad_de_la_pregunta", False)
    st = _estado("en", actividad_preguntada="snorkel")
    assert "Which one are you leaning toward" in ask_slot(st, SLOT_ACTIVITY, reasking=True)
    assert st.suggested_activity is None


def test_un_producto_generico_no_se_ofrece(monkeypatch):
    monkeypatch.setattr(settings, "actividad_de_la_pregunta", True)
    st = _estado("en", actividad_preguntada="padi_course")
    assert "Which one are you leaning toward" in ask_slot(st, SLOT_ACTIVITY, reasking=True)


def test_una_recomendacion_distinta_manda(monkeypatch):
    """El bot ya recomendó otra (p. ej. el minicurso a quien empieza): se sigue con esa."""
    monkeypatch.setattr(settings, "actividad_de_la_pregunta", True)
    st = _estado("es", actividad_preguntada="snorkel", suggested_activity="minicourse")
    texto = ask_slot(st, SLOT_ACTIVITY, reasking=True)
    assert "minicurso" in texto
    assert st.suggested_activity == "minicourse"
