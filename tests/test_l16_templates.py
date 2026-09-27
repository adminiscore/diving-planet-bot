"""Paso 5 (RAG, l1-6): textos fijos que contradecían la base de conocimiento en la ronda A (27-sep).

- El saludo decía "buceamos todos los días" y la política cierra el 25-dic y el 1-ene (10 fallos).
- La recomendación del plan decía "nuestro plan más popular", algo que la base no dice.
- La pregunta del origen ofrecía "ida y vuelta el mismo día" para cursos de 2 días y paquetes
  multi-día, que obligan a dormir en las islas.
"""

from src.agents import conversational_core as core
from src.flows.state import ConversationState


def _state(lang="es", **kw) -> ConversationState:
    s = ConversationState(conversation_id="l16")
    s.language = lang
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_el_saludo_no_promete_todos_los_dias():
    for lang in ("es", "en"):
        text = core._greeting(_state(lang)).lower()
        assert "todos los días" not in text and "every day" not in text
    assert "todo el año" in core._greeting(_state("es"))
    assert "year-round" in core._greeting(_state("en"))


def test_la_recomendacion_no_dice_mas_popular():
    for lang in ("es", "en"):
        text = core._recommended_plan_intro(_state(lang, detected_activity="certified_diving")).lower()
        assert text and "popular" not in text


def test_plan_de_varios_dias_necesita_dormir_en_las_islas():
    assert core._plan_needs_overnight(_state(detected_activity="padi_open_water"))
    assert core._plan_needs_overnight(_state(detected_activity="padi_advanced"))
    assert core._plan_needs_overnight(_state(detected_activity="certified_diving", detected_duration="multi_day"))
    assert not core._plan_needs_overnight(_state(detected_activity="certified_diving"))
    assert not core._plan_needs_overnight(_state(detected_activity="minicourse"))
    assert not core._plan_needs_overnight(_state(detected_activity="snorkel"))
    assert not core._plan_needs_overnight(_state())


def test_la_pregunta_del_origen_no_ofrece_ida_y_vuelta_a_un_curso_de_dos_dias():
    for lang, same_day, overnight in (("es", "mismo día", "dormir en las islas"),
                                      ("en", "same day", "stay on the islands")):
        course = core.ask_slot(_state(lang, detected_activity="padi_open_water"), core.SLOT_LOCATION)
        assert same_day not in course and overnight in course
    day_trip = core.ask_slot(_state("es", detected_activity="minicourse"), core.SLOT_LOCATION)
    assert "ida y vuelta el mismo día" in day_trip
