"""ex-2 (fase EX, flag `escalado_solo_emergencias`): las palabras clave que pasan a un asesor ANTES de que opine la IA
se quedan con las emergencias y las incidencias en tiempo real; lo médico, el tiempo y las quejas los decide Jev.

Banco ex2 (`docs/robustness/escalado/banco-ex2.json`, 2 pasadas con Jev): falsas alarmas 32-33 -> 11-12, perdidas 4-5 -> 5-7
(la diferencia, solo en el tiempo).
Aquí, sin red: qué caza la lista con el flag y sin él. Y el arreglo de la señal anidada del router LLM de respaldo
(`{"weather_conditions": true}` rompía el turno con un TypeError).
"""
import pytest

from src.agents.escalation import detect_sensitive_escalation, sensitive_response_for
from src.config import settings


@pytest.fixture
def ex2(monkeypatch):
    monkeypatch.setattr(settings, "escalado_solo_emergencias", True)


@pytest.mark.parametrize("mensaje", [
    "We have both completed the medical form, could you confirm the meeting location?",
    "he oído que tienen buceo nocturno, ¿cuánto cuesta?",
    "mi amigo es abogado y también quiere bucear, somos 3",
    "el viento de la isla es delicioso, ¿se puede quedar uno a dormir allí?",
])
def test_las_falsas_alarmas_de_la_lista_ya_no_pasan_a_un_asesor(ex2, mensaje):
    assert detect_sensitive_escalation(mensaje, "es") is None


@pytest.mark.parametrize("mensaje", [
    "We have both completed the medical form, could you confirm the meeting location?",
    "mi amigo es abogado y también quiere bucear, somos 3",
])
def test_apagado_la_lista_entera_sigue_como_hoy(monkeypatch, mensaje):
    monkeypatch.setattr(settings, "escalado_solo_emergencias", False)
    assert detect_sensitive_escalation(mensaje, "es") is not None


@pytest.mark.parametrize("mensaje,motivo", [
    ("es una emergencia, llamen por favor", "complaints_or_emergencies"),
    ("hubo un accidente con la lancha, necesitamos ayuda", "complaints_or_emergencies"),
    ("my friend fainted on the boat", "complaints_or_emergencies"),
    ("hay cupo mañana para 4 personas en el buceo?", "real_time_issues"),
    ("no puedo pagar, me sale error en la tarjeta", "real_time_issues"),
])
def test_emergencias_e_incidencias_siguen_por_la_lista(ex2, mensaje, motivo):
    encontrado = detect_sensitive_escalation(mensaje, "es")
    assert encontrado is not None and encontrado[0] == motivo


@pytest.mark.parametrize("mensaje", [
    "tengo asma, ¿puedo hacer el minicurso?",
    "llevo 3 dias esperando respuesta de mi reserva, esto es pesimo servicio",
    "como esta el clima para bucear mañana, hay tormenta?",
])
def test_lo_medico_el_tiempo_y_las_quejas_los_decide_jev(ex2, mensaje):
    # La lista ya no los caza: pasan a un asesor si Jev marca `sensitive_topic` (banco ex2: los marca).
    assert detect_sensitive_escalation(mensaje, "es") is None
    assert sensitive_response_for("medical_questions", "es") is not None


def test_la_senal_anidada_del_router_no_rompe_el_turno():
    assert sensitive_response_for({"weather_conditions": True}, "en")[0] == "weather_conditions"
    assert sensitive_response_for({"weather_conditions": False}, "en") is None
    assert sensitive_response_for({"no_existe": True}, "en") is None
    assert sensitive_response_for(True, "en") is None
