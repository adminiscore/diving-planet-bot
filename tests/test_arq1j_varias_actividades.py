"""ARQ-1j (22-oct, flag `varias_actividades`): el extractor da TODAS las actividades del mensaje (y el acompañante) y los
hechos salen de cada una. Antes «¿cuánto pagamos un buzo y un acompañante?» quedaba sin actividad y contestaba el RAG."""
import asyncio

from src.agents import redactor_hechos
from src.agents.extractor_turno import campos_paso6
from src.agents.nucleo import extractor
from src.config import settings
from src.flows import hechos as h
from src.flows.state import ConversationState

MENSAJE = "Somos un buzo certificado y un acompañante, ¿cuánto pagamos?"


def _conv(**campos) -> ConversationState:
    st = ConversationState(conversation_id="arq1j", language="es")
    st.history = [{"role": "user", "content": MENSAJE}]
    st._intenciones = ["precio"]
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_el_campo_solo_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "varias_actividades", False)
    assert "actividades_preguntadas" not in campos_paso6([])
    monkeypatch.setattr(settings, "varias_actividades", True)
    assert "actividades_preguntadas" in campos_paso6([])


def test_los_hechos_del_acompanante():
    [buzo, acompanante] = h.hechos(_conv(location="cartagena", is_colombian=True), ["precio", "incluye"],
                                   ["certified_diving", "companion"])
    assert acompanante["precio"]["cartagena"]["online"] == "288.000 COP"
    assert "Almuerzo" in acompanante["incluye"]["cartagena"]
    [acompanante] = h.hechos(_conv(location="island"), ["incluye"], ["companion"])
    assert "Almuerzo" not in acompanante["incluye"]["island"]


def test_con_el_flag_el_turno_saca_los_hechos_de_todas(monkeypatch):
    async def lectura(state, message):
        return {"actividades_preguntadas": ["certified_diving", "companion"], "actividad_preguntada": None}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    monkeypatch.setattr(settings, "varias_actividades", True)
    bloques, cubiertas = asyncio.run(redactor_hechos.hechos_del_turno(_conv(location="cartagena"), MENSAJE,
                                                                       _conv().history))
    assert [b["actividad"] for b in bloques] == ["certified_diving", "companion"] and cubiertas == ["precio"]
    monkeypatch.setattr(settings, "varias_actividades", False)
    assert asyncio.run(redactor_hechos.hechos_del_turno(_conv(location="cartagena"), MENSAJE, _conv().history)) is None
