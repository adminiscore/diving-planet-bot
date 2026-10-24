"""flu-1 (22-oct), repreguntas del flujo de la reserva vistas en el G10 nº 2 (banco docs/robustness/arq/banco-flu1.json).

- `curso_preguntado_no_es_nivel`: «do you have open water available tomorrow?» pregunta por el CURSO (el extractor lo lee
  como la actividad de la que pregunta); no se pregunta «¿ya tienen el Open Water o quieren sacarlo?». Con el nivel a
  secas («somos 4 open water») se sigue preguntando (decisión del owner, 15-sep).
- `sin_certificacion_no_hace_falta`: al decir «no estoy certificado» para una actividad que no lo pide, el bot dice que
  no hace falta.
"""

import pytest

from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extraction
from src.agents.nucleo.slotfill_close import _no_hace_falta_certificacion
from src.flows.state import ConversationState


def _intent(preguntada):
    intent = DetectedIntent()
    intent._actividad_preguntada = preguntada
    return intent


@pytest.mark.parametrize("preguntada, pregunta", [
    ("padi_open_water", False),
    (None, True),  # «somos 4 open water»: el extractor no lee ninguna actividad preguntada
    ("snorkel", True),  # una actividad sin nivel no dice nada del curso
])
def test_preguntar_por_el_curso_no_es_un_nivel_dudoso(monkeypatch, preguntada, pregunta):
    monkeypatch.setattr(extraction, "course_level_is_ambiguous", lambda message: True)
    st = ConversationState(conversation_id="flu1", language="en")
    extraction._flag_cert_or_course(_intent(preguntada), st, "hi, do you have open water available tomorrow?")
    assert st.needs_cert_or_course is pregunta


def _estado(actividad, certificado, lang="en"):
    st = ConversationState(conversation_id="flu1", language=lang)
    st.detected_activity = actividad
    st.is_certified = certificado
    return st


@pytest.mark.parametrize("actividad, antes, ahora, dice", [
    ("snorkel", None, False, True),
    ("minicourse", None, False, True),
    ("padi_open_water", None, False, True),
    ("certified_diving", None, False, False),  # el buceo sí lo pide: eso lo lleva el flujo del minicurso
    ("snorkel", False, False, False),  # ya lo había dicho: no se repite en cada turno
    ("snorkel", None, True, False),
    ("companion", None, False, False),
])
def test_sin_certificacion_dice_que_no_hace_falta(monkeypatch, actividad, antes, ahora, dice):
    texto = _no_hace_falta_certificacion(_estado(actividad, ahora), {"prev_main_is_certified": antes})
    assert bool(texto) is dice
    if dice:
        assert "certification" in texto


def test_en_espanol(monkeypatch):
    texto = _no_hace_falta_certificacion(_estado("snorkel", False, "es"), {"prev_main_is_certified": None})
    assert texto.startswith("Para el *Snorkel* no necesitas certificación")
