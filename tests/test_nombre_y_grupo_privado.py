"""Dos hallazgos de ex-3 (HISTORY 0.31.17-0.31.18), 13-oct:

1. `nombre_por_extractor`: "yo soy gringo" saludaba "¡Hola, Gringo!" (la regex "soy X" con lista de excluidas). La
   regex solo coge las formas sin ambigüedad ("me llamo", "mi nombre es", "my name is") y el nombre de "soy X" lo da
   el extractor con su cita.
2. `grupo_privado_pase`: el grupo privado / evento de empresa contestaba "Te paso con un asesor…" sin marcar el pase.

Los dos promocionados el 13-oct; sin interruptor desde mej-1d.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.extractor_turno import ESQUEMA, ESQUEMA_CON_NOMBRE
from src.agents.supervisor import route_message
from src.flows.state import ConversationState, Step


def _estado() -> ConversationState:
    st = ConversationState(conversation_id="nombre", language="es")
    st.step = Step.FREE_TEXT
    return st


# --- 1. el nombre -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("mensaje,nombre", [
    ("hola, yo soy gringo y quiero bucear", None),           # "soy X" ya no lo coge la regex
    ("hola, me llamo Andrés", "Andrés"),                     # las formas sin ambigüedad, sí
    ("my name is tom", "Tom"),
])
def test_la_regex_solo_coge_formas_sin_ambiguedad(mensaje, nombre):
    st = _estado()
    core._capture_client_name(st, mensaje)
    assert st.client_name == nombre


@pytest.mark.parametrize("datos,nombre", [
    ({"nombre": "rocío"}, "Rocío"),
    ({"nombre": "Tom Smith"}, "Tom"),            # el nombre de pila
    ({"nombre": "gringo"}, "Gringo"),            # (el extractor no lo da; si lo diera, aquí no se filtra más)
    ({"nombre": "buzo"}, None),                  # palabras que nunca son nombre (la lista de siempre)
    (None, None),                                # el extractor falló
])
def test_nombre_del_extractor(datos, nombre):
    st = _estado()
    core._nombre_del_extractor(st, datos)
    assert st.client_name == nombre


def test_no_pisa_un_nombre_ya_sabido(monkeypatch):
    st = _estado()
    st.client_name = "Ana"
    core._nombre_del_extractor(st, {"nombre": "Rocío"})
    assert st.client_name == "Ana"


def test_el_nombre_es_el_unico_campo_que_se_anade_al_extractor():
    assert "nombre" not in ESQUEMA["properties"] and "nombre" not in ESQUEMA["required"]
    assert "nombre" in ESQUEMA_CON_NOMBRE["required"]
    assert set(ESQUEMA_CON_NOMBRE["properties"]) - set(ESQUEMA["properties"]) == {"nombre"}


# --- 2. el pase del grupo privado / empresa -----------------------------------------------------------------------

EMPRESA = "hola, somos una empresa y queremos llevar 20 empleados a bucear como evento corporativo, es posible?"


async def test_grupo_privado_marca_el_pase():
    st = _estado()
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        resp = await route_message(st, EMPRESA)
    assert "asesor" in resp.lower()
    assert "320 231515" not in resp
    assert st.step == Step.ESCALATE
    assert "grupo privado" in (st.pending_escalation_reason or "")
    assert st.pending_note  # el resumen para el asesor
