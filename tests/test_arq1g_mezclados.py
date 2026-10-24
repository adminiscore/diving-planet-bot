"""ARQ-1g (22-oct, flag `hechos_al_rag`): en un mensaje MEZCLADO (intenciones de la tabla y algo más), el RAG contesta,
pero la parte cubierta la escribe con los hechos del código y no de memoria."""
import asyncio

import pytest

from src.agents import conversational_core as cc
from src.agents import redactor_hechos
from src.agents.nucleo import extractor
from src.flows.state import ConversationState

MENSAJE = "¿Cuánto cuesta el minicurso y qué peces se ven?"


def _conv(**campos) -> ConversationState:
    st = ConversationState(conversation_id="arq1g", language="es")
    st.history = [{"role": "user", "content": MENSAJE}]
    st._intenciones = ["precio"]
    st._otra_cosa = True
    st.location = "cartagena"
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.fixture
def con_flags(monkeypatch):
    async def lectura(state, message):
        return {"actividad_preguntada": "minicourse"}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)


def test_en_un_mensaje_mezclado_el_rag_recibe_los_hechos(con_flags):
    st = _conv()
    hechos = asyncio.run(cc._hechos_para_el_rag(st, MENSAJE, st.history))
    assert '"183 USD"' in hechos and "pregunta_pendiente" not in hechos


@pytest.mark.parametrize("campos", [{"_otra_cosa": False}, {"_intenciones": []}])
def test_sin_mezcla_no(con_flags, campos):
    """Todo de la tabla lo contesta el redactor; sin intenciones, el RAG de siempre."""
    st = _conv(**campos)
    assert asyncio.run(cc._hechos_para_el_rag(st, MENSAJE, st.history)) is None


def test_la_huella_distingue_los_hechos():
    """La respuesta adelantada sale antes que Jev, sin hechos: si al terminar los hay, se rehace."""
    base = {"lang": "es", "history": [], "extra_context": ""}
    assert cc._huella_rag("x", base) != cc._huella_rag("x", {**base, "hechos": "[...]"})
    assert len(cc._PARTES_HUELLA) == len(cc._huella_rag("x", base))


def test_hechos_del_turno_da_las_cubiertas(con_flags):
    st = _conv(_intenciones=["precio", "incluye"])
    bloques, cubiertas = asyncio.run(redactor_hechos.hechos_del_turno(st, MENSAJE, st.history))
    assert cubiertas == ["precio", "incluye"] and bloques[0]["actividad"] == "minicourse"


def test_si_el_redactor_dijo_falta_tambien_recibe_los_hechos(con_flags):
    st = _conv(_otra_cosa=False, _redactor_dijo_falta=True)
    assert asyncio.run(cc._hechos_para_el_rag(st, MENSAJE, st.history))
