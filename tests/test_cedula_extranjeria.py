"""Mini de la 0.52 (4-nov; Gadea #3202): «Yo tengo extrangeria» tras una charla que ya habla de colombianos y extranjeros lo
leía el extractor como «soy extranjero» y el bot cobraba en USD a un residente. Jev afirma que tiene la cédula de extranjería
(`tiene_cedula_extranjeria`); el grupo mixto manda sobre ella."""
import asyncio
from types import SimpleNamespace

from src.agents import conversational_core as core
from src.agents.jev_router import GRUPO_MIXTO, TIENE_CEDULA, _questions_for_turn, answers_to_signals
from src.agents.nucleo import extractor as nx
from src.agents.nucleo.extractor import _poner_nacionalidad, con_la_cedula
from src.flows.state import ConversationState


def _intent():
    return SimpleNamespace(is_colombian=None, detected_fields=[], overwrite=[])


def _estado(senales=None):
    estado = ConversationState(conversation_id="cedula")
    estado._senales_router = senales
    return estado


def test_jev_pregunta_por_la_cedula_y_su_umbral():
    assert TIENE_CEDULA in _questions_for_turn(None)
    assert answers_to_signals({TIENE_CEDULA: {"type": "noul", "noul": 0.82}})[TIENE_CEDULA] is True
    assert answers_to_signals({TIENE_CEDULA: {"type": "noul", "noul": 0.55}})[TIENE_CEDULA] is False


def test_con_la_cedula_es_residente_aunque_el_extractor_diga_extranjero():
    estado, intent = _estado({TIENE_CEDULA: True, GRUPO_MIXTO: False}), _intent()
    _poner_nacionalidad(intent, estado, "Yo tengo extrangeria", {"is_colombian": False})
    assert intent.is_colombian is True


def test_sin_la_senal_vale_el_extractor():
    estado, intent = _estado({TIENE_CEDULA: False}), _intent()
    _poner_nacionalidad(intent, estado, "Soy extranjero, de Chile", {"is_colombian": False})
    assert intent.is_colombian is False
    assert con_la_cedula(_estado(None), None) is None


def test_el_grupo_mixto_manda_sobre_la_cedula():
    # «soy mexicana con cédula de extranjería y mi novio vive en México»: los dos en USD.
    estado, intent = _estado({TIENE_CEDULA: True, GRUPO_MIXTO: True}), _intent()
    _poner_nacionalidad(intent, estado, "soy mexicana con cédula y mi novio vive en México", {"is_colombian": True})
    assert intent.is_colombian is False and estado.mixed_nationality_notice is True
    assert con_la_cedula(estado, False) is False


def test_lo_ya_guardado_de_otra_manera_se_confirma_no_se_pisa(monkeypatch):
    confirmados = []
    monkeypatch.setattr(nx, "_route_contradictions",
                        lambda state, message, intent, propuesto: confirmados.append(propuesto))
    estado, intent = _estado({TIENE_CEDULA: True, GRUPO_MIXTO: False}), _intent()
    estado.is_colombian = False
    _poner_nacionalidad(intent, estado, "Bueno, en realidad tengo la extranjería", {"is_colombian": False})
    assert confirmados == [{"is_colombian": True}] and intent.is_colombian is None


def test_el_escritor_del_turno_ya_recibe_la_nacionalidad_de_la_cedula(monkeypatch):
    async def lectura(state, message):
        return {"is_colombian": False}

    monkeypatch.setattr(nx, "lectura_del_extractor", lectura)
    estado = _estado({TIENE_CEDULA: True, GRUPO_MIXTO: False})
    copia = asyncio.run(core._con_la_nacionalidad_del_mensaje(estado, "Yo tengo extrangeria"))
    assert copia.is_colombian is True and estado.is_colombian is None
