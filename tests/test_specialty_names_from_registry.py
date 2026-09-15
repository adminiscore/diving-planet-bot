"""Nombres de especialidad desde las etiquetas del registro (2026-09-15).

El vocabulario de especialidades estaba escrito tres veces en el detector y la tabla
de cursos que usa el nucleo solo conocia nitrox: "dudo entre la especialidad de nitrox
y la de flotabilidad" nombraba una sola oferta y se reservaba nitrox. Ahora el nombre
es la etiqueta sin el sustantivo de la familia ("Especialidad Flotabilidad").
"""

import pytest

from src.agents import conversational_core as core
from src.agents import intent_detector as det
from src.domain import activities as dom
from src.flows.state import ConversationState


def test_every_specialty_has_its_name_in_the_course_table():
    specialties = {a.id for a in dom.registry().activities if a.family == "specialty" and not a.generic}
    assert specialties <= {activity_id for activity_id, _ in det._COURSE_NAME_PATTERNS}
    assert not hasattr(det, "_SPECIALTY_KEYWORD_TO_ACTIVITY")


@pytest.mark.parametrize("message, activity_id", [
    ("quiero la especialidad de flotabilidad", "specialty_buoyancy"),
    ("I'd like the buoyancy specialty", "specialty_buoyancy"),
    ("I'd like the naturalist specialty", "specialty_naturalist"),
    ("especialidad de identificacion de peces", "specialty_fish_identification"),
    ("fish identification specialty", "specialty_fish_identification"),
    ("mindful diving", "specialty_mindful_diving"),
    ("enriched air", "specialty_nitrox"),        # variante que ninguna etiqueta contiene
])
def test_specialty_names(message, activity_id):
    assert det.courses_mentioned(message) == [activity_id]


@pytest.mark.parametrize("message, activity_id", [
    ("quiero hacer la especialidad naturalist", "specialty_naturalist"),
    ("I'd like to do the identificacion de peces specialty", "specialty_fish_identification"),
])
def test_detector_activity_uses_the_same_names(message, activity_id):
    assert det.IntentDetector().detect(message, ConversationState(conversation_id="c")).activity == activity_id


def test_doubt_between_two_specialties_is_a_comparison():
    message = "dudo entre la especialidad de nitrox y la de flotabilidad"
    assert core._mentioned_offerings(message) == ["specialty_nitrox", "specialty_buoyancy"]
    assert core._is_deliberation_between_options(message, {}) is True


def test_bare_words_are_not_specialty_names():
    assert det.courses_mentioned("quiero ver peces y fish") == []
