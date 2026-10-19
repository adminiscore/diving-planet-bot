"""ex-9b paso 2 (19-oct, flag `alcohol_detras_de_lo_medico`): el atajo del alcohol iba antes que la seguridad, así que
«estoy embarazada, ¿puedo bucear o tomar vino?» recibía el texto fijo del alcohol aunque Jev dijera que era médico.
Con el flag, si Jev dice `medical_questions`, manda la seguridad; la pregunta de alcohol sola sigue con su norma."""

import pytest

from src.config import settings
from src.flows.state import ConversationState
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_INFO, ROUTE_SAFETY

MEDICO = {"sensitive_topic": "medical_questions"}


def _estado() -> ConversationState:
    return ConversationState(conversation_id="alc", language="es")


@pytest.mark.parametrize("encendido, esperada", [(True, ROUTE_SAFETY), (False, ROUTE_INFO)])
def test_alcohol_con_algo_medico_va_a_seguridad_solo_con_el_flag(monkeypatch, encendido, esperada):
    monkeypatch.setattr(settings, "alcohol_detras_de_lo_medico", encendido)
    assert classify_route(_estado(), "estoy embarazada, ¿puedo bucear o tomar vino?", MEDICO) == esperada


def test_la_pregunta_de_alcohol_sola_sigue_con_su_norma(monkeypatch):
    monkeypatch.setattr(settings, "alcohol_detras_de_lo_medico", True)
    assert classify_route(_estado(), "¿puedo tomar una cerveza la noche antes de bucear?", {}) == ROUTE_INFO
