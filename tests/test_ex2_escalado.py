"""ex-2 (fase EX, `escalado_solo_emergencias`, promocionado; sin interruptor desde mej-1d): las palabras clave que pasan a un asesor ANTES de que opine la IA
se quedan con las emergencias y las incidencias en tiempo real; lo médico, el tiempo y las quejas los decide Jev.

Banco ex2 (`docs/robustness/escalado/banco-ex2.json`, 2 pasadas con Jev): falsas alarmas 32-33 -> 11-12, perdidas 4-5 -> 5-7
(la diferencia, solo en el tiempo).
Aquí, sin red: qué caza la lista. Y el arreglo de la señal anidada del router LLM de respaldo
(`{"weather_conditions": true}` rompía el turno con un TypeError).
"""
import pytest

from src.agents.escalation import detect_sensitive_escalation, sensitive_response_for


@pytest.mark.parametrize("mensaje", [
    "We have both completed the medical form, could you confirm the meeting location?",
    "he oído que tienen buceo nocturno, ¿cuánto cuesta?",
    "mi amigo es abogado y también quiere bucear, somos 3",
    "el viento de la isla es delicioso, ¿se puede quedar uno a dormir allí?",
    # lat-deuda-u (26-oct, C9 del inventario): siempre hay disponibilidad (decisión del negocio); no es una incidencia.
    "hay cupo mañana para 4 personas en el buceo?",
])
def test_las_falsas_alarmas_de_la_lista_ya_no_pasan_a_un_asesor(mensaje):
    assert detect_sensitive_escalation(mensaje, "es") is None


@pytest.mark.parametrize("mensaje,motivo", [
    ("es una emergencia, llamen por favor", "complaints_or_emergencies"),
    ("hubo un accidente con la lancha, necesitamos ayuda", "complaints_or_emergencies"),
    ("my friend fainted on the boat", "complaints_or_emergencies"),
    ("no puedo pagar, me sale error en la tarjeta", "real_time_issues"),
])
def test_emergencias_e_incidencias_siguen_por_la_lista(mensaje, motivo):
    encontrado = detect_sensitive_escalation(mensaje, "es")
    assert encontrado is not None and encontrado[0] == motivo


@pytest.mark.parametrize("mensaje", [
    "tengo asma, ¿puedo hacer el minicurso?",
    "llevo 3 dias esperando respuesta de mi reserva, esto es pesimo servicio",
    "como esta el clima para bucear mañana, hay tormenta?",
])
def test_lo_medico_el_tiempo_y_las_quejas_los_decide_jev(mensaje):
    # La lista ya no los caza: pasan a un asesor si Jev marca `sensitive_topic` (banco ex2: los marca).
    assert detect_sensitive_escalation(mensaje, "es") is None
    assert sensitive_response_for("medical_questions", "es") is not None


def test_la_senal_anidada_del_router_no_rompe_el_turno():
    assert sensitive_response_for({"weather_conditions": True}, "en")[0] == "weather_conditions"
    assert sensitive_response_for({"weather_conditions": False}, "en") is None
    assert sensitive_response_for({"no_existe": True}, "en") is None
    assert sensitive_response_for(True, "en") is None
