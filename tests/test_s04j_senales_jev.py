"""CALN-S04J (4-nov): dos señales de Jev. Quien cita un precio recibe el del plan, y el grupo mixto lo afirma Jev."""
from types import SimpleNamespace

from src.agents.jev_router import (
    ASKS_QUESTION,
    CITA_PRECIO,
    GRUPO_MIXTO,
    PIDE_PRECIO,
    _questions_for_turn,
    answers_to_signals,
    uncertain_answers,
)
from src.agents.nucleo.extractor import _poner_nacionalidad
from src.agents.rutas.contexto_rag import _build_extra_context
from src.flows.state import ConversationState
from src.orchestration.graph import _con_lo_que_implica


def _intent():
    return SimpleNamespace(is_colombian=None, detected_fields=[], overwrite=[])


def _estado(senales=None):
    estado = ConversationState(conversation_id="s04j")
    estado._senales_router = senales
    return estado


def test_las_dos_preguntas_van_en_la_misma_llamada_de_jev():
    preguntas = _questions_for_turn()
    assert CITA_PRECIO in preguntas and GRUPO_MIXTO in preguntas


def test_el_umbral_es_el_alto_y_se_emiten_tambien_en_false():
    senales = answers_to_signals({CITA_PRECIO: {"type": "noul", "noul": 0.82}, GRUPO_MIXTO: {"type": "noul", "noul": 0.59}})
    assert senales[CITA_PRECIO] is True
    assert senales[GRUPO_MIXTO] is False


def test_su_duda_no_cuenta_como_duda_del_router():
    respuestas = {CITA_PRECIO: {"type": "noul", "noul": 0.5}, GRUPO_MIXTO: {"type": "noul", "noul": 0.5}}
    assert uncertain_answers(respuestas) == []


def test_quien_cita_un_precio_recibe_el_precio_y_cuenta_como_pregunta():
    senales = _con_lo_que_implica(_estado(), {CITA_PRECIO: True, ASKS_QUESTION: False})
    assert senales[PIDE_PRECIO] is True and senales[ASKS_QUESTION] is True


def test_sin_citar_no_cambia_nada():
    original = {CITA_PRECIO: False, ASKS_QUESTION: False}
    estado = _estado()
    assert _con_lo_que_implica(estado, original) == original
    assert estado.mixed_nationality_notice is False


def test_el_grupo_mixto_se_apunta_antes_de_escribir():
    estado = _estado()
    _con_lo_que_implica(estado, {GRUPO_MIXTO: True})
    assert estado.mixed_nationality_notice is True


def test_jev_ve_el_grupo_mixto_que_el_extractor_no_ve():
    estado, intent = _estado({GRUPO_MIXTO: True}), _intent()
    _poner_nacionalidad(intent, estado, "soy mexicana con cédula y mi novio vive en México", {"is_colombian": True})
    assert intent.is_colombian is False
    assert estado.mixed_nationality_notice is True


def test_jev_quita_el_grupo_mixto_que_el_extractor_ve_de_mas():
    estado, intent = _estado({GRUPO_MIXTO: False}), _intent()
    _poner_nacionalidad(intent, estado, "soy venezolano con cédula y mi esposa es colombiana",
                        {"mixed_nationality": True, "is_colombian": None})
    assert intent.is_colombian is None
    assert estado.mixed_nationality_notice is False


def test_si_jev_calla_vale_lo_del_extractor():
    estado, intent = _estado(None), _intent()
    _poner_nacionalidad(intent, estado, "mi pareja es colombiana y yo española", {"mixed_nationality": True})
    assert intent.is_colombian is False
    assert estado.mixed_nationality_notice is True


def test_el_escritor_recibe_la_regla_del_grupo_y_no_la_de_una_persona():
    estado = _estado()
    estado.mixed_nationality_notice = True
    estado.is_colombian = False
    contexto = _build_extra_context(estado)
    assert "toda la reserva del grupo se paga en dólares" in contexto
    assert "no es colombiano/a" not in contexto
