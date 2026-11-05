"""CALN-30 (5-nov): «yo soy residente» dicho sin que se pregunte salía sin dato o en USD; lo afirma Jev (`es_residente_colombia`)."""
from src.agents import jev_router as j
from src.agents.nucleo.extractor import con_la_cedula
from src.flows.state import ConversationState


def _estado(**senales) -> ConversationState:
    st = ConversationState(conversation_id="c30", language="es")
    st._senales_router = senales
    return st


def test_si_jev_dice_residente_paga_en_pesos():
    assert con_la_cedula(_estado(**{j.ES_RESIDENTE: True}), None) is True
    assert con_la_cedula(_estado(**{j.ES_RESIDENTE: True}), False) is True


def test_si_no_lo_dice_vale_lo_del_extractor():
    assert con_la_cedula(_estado(**{j.ES_RESIDENTE: False}), False) is False
    assert con_la_cedula(_estado(), None) is None


def test_el_grupo_mixto_manda_sobre_el_residente():
    assert con_la_cedula(_estado(**{j.ES_RESIDENTE: True, j.GRUPO_MIXTO: True}), False) is False


def test_es_una_fila_de_la_tabla():
    assert j.ES_RESIDENTE in [s.nombre for s in j._DEL_TURNO] and j.ES_RESIDENTE in j._questions_for_turn(None)
