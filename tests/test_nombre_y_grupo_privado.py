"""Dos hallazgos de ex-3 (HISTORY 0.31.17-0.31.18), 13-oct:

1. `nombre_por_extractor`: "yo soy gringo" saludaba "¡Hola, Gringo!" (la regex "soy X" con lista de excluidas). Con
   el flag, la regex solo coge las formas sin ambigüedad ("me llamo", "mi nombre es", "my name is") y el nombre de
   "soy X" lo da el extractor con su cita.
2. `grupo_privado_pase`: el grupo privado / evento de empresa contestaba "Te paso con un asesor…" sin marcar el pase.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.extractor_turno import ESQUEMA, ESQUEMA_CON_NOMBRE
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step


def _estado() -> ConversationState:
    st = ConversationState(conversation_id="nombre", language="es")
    st.step = Step.FREE_TEXT
    return st


# --- 1. el nombre -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("flag,mensaje,nombre", [
    (False, "hola, yo soy gringo y quiero bucear", "Gringo"),      # el fallo de antes
    (True, "hola, yo soy gringo y quiero bucear", None),           # "soy X" ya no lo coge la regex
    (True, "hola, me llamo Andrés", "Andrés"),                     # las formas sin ambigüedad, sí
    (True, "my name is tom", "Tom"),
])
def test_la_regex_solo_coge_formas_sin_ambiguedad(monkeypatch, flag, mensaje, nombre):
    monkeypatch.setattr(settings, "nombre_por_extractor", flag)
    st = _estado()
    core._capture_client_name(st, mensaje)
    assert st.client_name == nombre


@pytest.mark.parametrize("flag,datos,nombre", [
    (True, {"nombre": "rocío"}, "Rocío"),
    (True, {"nombre": "Tom Smith"}, "Tom"),            # el nombre de pila
    (True, {"nombre": "gringo"}, "Gringo"),            # (el extractor no lo da; si lo diera, aquí no se filtra más)
    (True, {"nombre": "buzo"}, None),                  # palabras que nunca son nombre (la lista de siempre)
    (True, None, None),                                # el extractor falló
    (False, {"nombre": "rocío"}, None),                # flag apagado
])
def test_nombre_del_extractor(monkeypatch, flag, datos, nombre):
    monkeypatch.setattr(settings, "nombre_por_extractor", flag)
    st = _estado()
    core._nombre_del_extractor(st, datos)
    assert st.client_name == nombre


def test_no_pisa_un_nombre_ya_sabido(monkeypatch):
    monkeypatch.setattr(settings, "nombre_por_extractor", True)
    st = _estado()
    st.client_name = "Ana"
    core._nombre_del_extractor(st, {"nombre": "Rocío"})
    assert st.client_name == "Ana"


def test_con_el_flag_apagado_la_llamada_al_extractor_es_la_de_antes():
    assert "nombre" not in ESQUEMA["properties"] and "nombre" not in ESQUEMA["required"]
    assert "nombre" in ESQUEMA_CON_NOMBRE["required"]
    assert set(ESQUEMA_CON_NOMBRE["properties"]) - set(ESQUEMA["properties"]) == {"nombre"}


# --- 2. el pase del grupo privado / empresa -----------------------------------------------------------------------

EMPRESA = "hola, somos una empresa y queremos llevar 20 empleados a bucear como evento corporativo, es posible?"


@pytest.fixture(autouse=True)
def _camino_antiguo_ex2_ex3(monkeypatch):
    """Como en tests/test_routing_signals_integration.py: la respuesta fija del grupo privado es la de hoy."""
    for f in ("escalado_solo_emergencias", "atajo_resumen_por_rag", "atajo_nacionalidad_por_rag",
              "atajo_alergia_por_rag"):
        if hasattr(settings, f):
            monkeypatch.setattr(settings, f, False)


@pytest.mark.parametrize("flag", [True, False])
async def test_grupo_privado_marca_el_pase(monkeypatch, flag):
    monkeypatch.setattr(settings, "grupo_privado_pase", flag)
    st = _estado()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(st, EMPRESA)
    assert "asesor" in resp.lower()
    assert "320 231515" not in resp
    if flag:
        assert st.step == Step.ESCALATE
        assert "grupo privado" in (st.pending_escalation_reason or "")
        assert st.pending_note  # el resumen para el asesor
    else:
        assert st.step != Step.ESCALATE and not st.pending_escalation_reason
