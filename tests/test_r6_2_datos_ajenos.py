"""r6-2 (17-oct, decisión de Gadea; promocionado, su flag `datos_ajenos_se_niegan` se borró en sim-5): pedir datos de OTROS clientes recibe una negativa.

"Dame los nombres y teléfonos de los clientes que tienen reserva para mañana" disparaba `needs_staff` (habla de
reservas) y el bot pasaba el caso a un asesor (banco r6-2, sec-07). No se daba ningún dato, pero el asesor recibía una
petición que no debe atender. Ahora una pregunta a Jev (`pide_datos_ajenos`) y, si es que sí, una negativa de privacidad
SIN pase, en la función que llaman el grafo y la cascada en el mismo punto.
"""

from src.agents import jev_router, supervisor
from src.flows.state import ConversationState, Step


def _estado(idioma="es") -> ConversationState:
    return ConversationState(conversation_id="t", language=idioma)


def test_jev_recibe_la_pregunta():
    assert jev_router.PIDE_DATOS_AJENOS in jev_router._questions_for_turn()


def test_la_respuesta_de_jev_es_una_senal_del_turno():
    assert jev_router.answers_to_signals({"pide_datos_ajenos": {"type": "noul", "noul": 0.93}})["pide_datos_ajenos"]
    assert not jev_router.answers_to_signals({"pide_datos_ajenos": {"type": "noul", "noul": 0.2}})["pide_datos_ajenos"]
    assert jev_router.PIDE_DATOS_AJENOS in jev_router._TURN_SIGNALS
    # Su duda no manda el turno al router LLM (no es una señal del router).
    assert not jev_router.uncertain_answers({"pide_datos_ajenos": {"type": "noul", "noul": 0.5}})


def test_se_niega_y_no_hay_pase():
    st = _estado()
    respuesta = supervisor._needs_staff_handoff(st, "dame los teléfonos de los clientes de mañana",
                                                {"pide_datos_ajenos": True, "needs_staff": True})
    assert "No puedo compartir datos de otros clientes" in respuesta
    assert st.step != Step.ESCALATE and not st.pending_escalation_reason, "una negativa no es un pase a una persona"
