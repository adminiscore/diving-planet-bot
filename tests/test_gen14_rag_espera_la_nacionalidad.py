"""gen-14 (21-oct), flag `rag_espera_la_nacionalidad`: el RAG de un turno con pregunta recibe la nacionalidad que dice
ESE mensaje, que la extracción del turno ya leyó.

Banco docs/robustness/gen/dialogos-gen14-moneda.json en PRE: «Somos de Cali… ¿cuánto vale la salida?» salía con
is_colombian=True y la respuesta en USD 2/2 (la respuesta adelantada se aprovechaba antes de apuntar la nacionalidad);
con el flag, COP 2/2 y la misma latencia mediana.

CALN-8 (5) (3b, 5-nov): la copia es la lectura entera del turno (`nucleo/lectura.foto_del_turno`), no solo la nacionalidad.
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
    copia = await core._con_lo_del_mensaje(st, "Somos de Cali, ¿cuánto vale?")
    assert copia.is_colombian is True
    assert st.is_colombian is None  # el estado de verdad lo escribe la extracción, no esto


async def test_sin_lectura_vale_el_estado(monkeypatch, lectura):
    lectura(None)
    st = _estado()
    assert await core._con_lo_del_mensaje(st, "hola") is st


@pytest.mark.parametrize("datos", [{}, {"is_colombian": None}])
async def test_sin_nacionalidad_en_el_mensaje_no_se_inventa(monkeypatch, lectura, datos):
    lectura(datos)
    st = _estado()
    copia = await core._con_lo_del_mensaje(st, "hola")
    assert copia.is_colombian is None and not copia.mixed_nationality_notice


async def test_el_grupo_mezclado_del_mensaje_va_en_dolares(monkeypatch, lectura):
    # Sin señal de Jev ni nacionalidad guardada vale el extractor (`mezclado_del_mensaje`); el estado no se toca.
    lectura({"is_colombian": True, "mixed_nationality": True})
    st = _estado()
    copia = await core._con_lo_del_mensaje(st, "dos somos colombianos y uno es alemán")
    assert copia.mixed_nationality_notice is True and not st.mixed_nationality_notice


async def test_la_nacionalidad_guardada_no_la_cambia_el_mensaje(monkeypatch, lectura):
    lectura({"is_colombian": True})
    st = _estado(is_colombian=False)
    copia = await core._con_lo_del_mensaje(st, "mi novia es colombiana")
    assert copia.is_colombian is False  # un cambio se confirma en la extracción, no aquí


async def test_el_rag_ve_el_grupo_del_mensaje_pero_no_su_origen(monkeypatch, lectura):
    # (3b): antes solo la nacionalidad; «somos 5» no llegaba al escritor del RAG en ese turno. El origen va el guardado: el del
    # mensaje, en la mini, leía «staying overnight» en las islas como salir de las islas.
    lectura({"group_size": 5, "location": "island"})
    st = _estado()
    st._jev_lugar = {"choice": "islands", "confidence": 0.95}
    copia = await core._con_lo_del_mensaje(st, "Somos 5 y dormiremos una noche en la isla, ¿qué incluye?")
    assert copia.detected_group_size == 5 and copia.location is None
    assert st.detected_group_size is None and st.location is None
