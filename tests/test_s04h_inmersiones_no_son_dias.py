"""Sparring s04h y s04k (4-nov): «two dives» y «2 fun dives» salían como 2 días de buceo: varios días se comía la salida de 2
inmersiones y la cifra llegaba a `cert_days`. CALN-25 (decisión de Gadea, 4-nov): lo decide Jev (`son_dias_de_buceo`) y no 2 regex."""
import pytest

from src.agents.jev_router import SON_DIAS_DE_BUCEO, _questions_for_turn, answers_to_signals
from src.agents.nucleo.extractor import dias_de_buceo_de, duracion_del_extractor
from src.flows.state import ConversationState


def _estado(p=None):
    estado = ConversationState(conversation_id="s04h")
    estado._senales_router = {} if p is None else {SON_DIAS_DE_BUCEO: p}
    return estado


def test_la_pregunta_va_en_la_llamada_y_se_emite_la_probabilidad():
    assert SON_DIAS_DE_BUCEO in _questions_for_turn()
    assert answers_to_signals({SON_DIAS_DE_BUCEO: {"type": "noul", "noul": 0.06}})[SON_DIAS_DE_BUCEO] == 0.06


def test_jev_seguro_de_que_no_son_dias_se_descartan():
    datos = {"dias_de_buceo": 2}
    assert dias_de_buceo_de(datos, _estado(0.06)) is None
    assert duracion_del_extractor(datos, _estado(0.06)) == (None, False)


@pytest.mark.parametrize("p", [0.41, 0.82, 0.95])  # «2 inmersiones en 2 días», «two dives on Saturday and Sunday»
def test_si_jev_no_esta_seguro_de_que_no_se_quedan(p):
    assert dias_de_buceo_de({"dias_de_buceo": 2}, _estado(p)) == 2


def test_con_un_dia_jev_no_opina():
    # La pregunta de Jev es por dos días o más: «solo un día» da bajo y sigue siendo un día.
    assert dias_de_buceo_de({"dias_de_buceo": 1}, _estado(0.05)) == 1
    assert duracion_del_extractor({"dias_de_buceo": 1}, _estado(0.05)) == ("single_day", True)


def test_si_jev_calla_vale_lo_del_extractor():
    assert dias_de_buceo_de({"dias_de_buceo": 2}, _estado()) == 2


@pytest.mark.parametrize("valor", [None, 0, -1, True, "2"])
def test_lo_que_no_es_un_numero_de_dias_no_vale(valor):
    assert dias_de_buceo_de({"dias_de_buceo": valor}, _estado()) is None


def test_la_duracion_con_dias_de_buceo():
    assert duracion_del_extractor({"dias_de_buceo": 3}, _estado()) == ("multi_day", True)
