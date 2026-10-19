"""ex-9b paso 2 (19-oct): el atajo del alcohol iba antes que la seguridad, así que «estoy embarazada, ¿puedo bucear o
tomar vino?» recibía el texto fijo del alcohol aunque Jev dijera que era médico. Si Jev dice `medical_questions`, manda
la seguridad; la pregunta de alcohol sola sigue con su norma. (Flag `alcohol_detras_de_lo_medico` promocionado y
quitado en la limpieza ex9b.)"""

from src.flows.state import ConversationState
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_INFO, ROUTE_SAFETY

MEDICO = {"sensitive_topic": "medical_questions"}


def _estado() -> ConversationState:
    return ConversationState(conversation_id="alc", language="es")


def test_alcohol_con_algo_medico_va_a_seguridad():
    assert classify_route(_estado(), "estoy embarazada, ¿puedo bucear o tomar vino?", MEDICO) == ROUTE_SAFETY


def test_la_pregunta_de_alcohol_sola_sigue_con_su_norma():
    assert classify_route(_estado(), "¿puedo tomar una cerveza la noche antes de bucear?", {}) == ROUTE_INFO
