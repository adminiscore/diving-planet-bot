"""gen-14 (21-oct), flag `rag_espera_la_nacionalidad`: el RAG de un turno con pregunta recibe la nacionalidad que dice
ESE mensaje, que la extracción del turno ya leyó.

Banco docs/robustness/gen/dialogos-gen14-moneda.json en PRE: «Somos de Cali… ¿cuánto vale la salida?» salía con
is_colombian=True y la respuesta en USD 2/2 (la respuesta adelantada se aprovechaba antes de apuntar la nacionalidad);
con el flag, COP 2/2 y la misma latencia mediana.
"""

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="gen14", language="es")
    for c, v in campos.items():
        setattr(st, c, v)
    return st


@pytest.fixture
def lectura(monkeypatch):
    def con(datos):
        async def leer(state, message):
            return datos
        monkeypatch.setattr(core_extractor, "lectura_del_extractor", leer)
    return con


async def test_el_rag_recibe_la_nacionalidad_del_mensaje(monkeypatch, lectura):
    lectura({"is_colombian": True})
    st = _estado()
    copia = await core._con_la_nacionalidad_del_mensaje(st, "Somos de Cali, ¿cuánto vale?")
    assert copia.is_colombian is True
    assert st.is_colombian is None  # el estado de verdad lo escribe la extracción, no esto


@pytest.mark.parametrize("datos", [None, {}, {"is_colombian": None}, {"is_colombian": True, "mixed_nationality": True}])
async def test_sin_nacionalidad_clara_no_cambia_nada(monkeypatch, lectura, datos):
    lectura(datos)
    st = _estado()
    assert await core._con_la_nacionalidad_del_mensaje(st, "hola") is st


async def test_si_ya_se_sabe_no_se_lee_otra_vez(monkeypatch):

    async def no_llamar(state, message):
        raise AssertionError("no hace falta leer")
    monkeypatch.setattr(core_extractor, "lectura_del_extractor", no_llamar)
    st = _estado(is_colombian=False)
    assert await core._con_la_nacionalidad_del_mensaje(st, "no soy colombiano") is st
