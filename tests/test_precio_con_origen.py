"""1-oct, flag `rag_precio_con_origen`: un precio que cambia según el origen va siempre con su origen.

Reproducido en PRE (`scripts/reproducir_juez_pre.py paquete-5-buceos-cop-refresh-y-hoteles`, 5 veces): en el 2º
mensaje el bot daba el precio de Cartagena del paquete de 5 sin decirlo; el juez lo tiraba (3 de 5) y el reintento
quitaba el precio. Se fija:
1. la comprobación salta solo con un importe del catálogo que depende del origen, sin origen en la respuesta y sin
   origen conocido del cliente;
2. el reintento pide ROTULAR el precio (no quitarlo);
3. solo actúa en el primer intento: si el segundo sigue sin origen, va al juez como siempre (nunca "no lo tengo").
"""

import pytest

from src.agents import rag_agent
from src.agents.grounding_check import precio_sin_origen, precios_que_dependen_del_origen
from src.agents.rag_agent import regen_feedback
from src.flows.catalog import ISLAND_SERVICE_MAP, SERVICES


def test_los_importes_salen_del_catalogo():
    importes = precios_que_dependen_del_origen()
    c, i = SERVICES["5_dives_2_days"], SERVICES[ISLAND_SERVICE_MAP["5_dives_2_days"]]
    assert {str(c["price_cop"]), str(i["price_cop"])} <= importes
    assert "80" not in importes  # el acompañante cuesta lo mismo en los dos orígenes


@pytest.mark.parametrize("respuesta,estado,salta", [
    ("Para colombianos el paquete de 5 inmersiones cuesta 1.429.000 COP online.", None, True),
    ("The 5-dive package is 392 USD online.", None, True),
    ("Saliendo desde Cartagena, el paquete de 5 cuesta 1.429.000 COP online.", None, False),
    ("Si ya estás en las islas, el paquete de 5 cuesta 1.000.000 COP online.", None, False),
    ("El paquete de 5 cuesta 1.429.000 COP online.", "El cliente indica que saldra desde Cartagena para su experiencia.", False),
    ("El acompañante cuesta 80 USD online.", None, False),
    ("Reservando online tienes un 10% de descuento.", None, False),
])
def test_cuando_salta(respuesta, estado, salta):
    assert precio_sin_origen(respuesta, estado) is salta


def test_el_reintento_pide_rotular_no_quitar():
    fb = regen_feedback("precio_sin_origen", "es")
    assert "NO quites el precio" in fb and "Cartagena" in fb
    assert "Do NOT remove the price" in regen_feedback("precio_sin_origen", "en")


def _openai(respuestas, llamadas):
    class _Msg:
        def __init__(self, c):
            self.content = c

    class _Resp:
        def __init__(self, c):
            self.choices = [type("C", (), {"message": _Msg(c)})()]
            self.usage = type("U", (), {"total_tokens": 10})()

    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs["messages"])
            return _Resp(respuestas[min(len(llamadas), len(respuestas)) - 1])

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    return _OpenAI


SIN_ORIGEN = "Para colombianos el paquete de 5 inmersiones cuesta 1.429.000 COP online."
CON_ORIGEN = "Saliendo desde Cartagena, el paquete de 5 inmersiones cuesta 1.429.000 COP online."


@pytest.fixture
def rag(monkeypatch):
    async def busqueda(query, lang="es"):
        return [{"content": "Paquete de 5 inmersiones: 1.429.000 COP online desde Cartagena; 1.000.000 COP ya en las islas.",
                 "metadata": {"source": "services"}, "score": 0.9}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", busqueda)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.5)
    monkeypatch.setattr(rag_agent.settings, "rag_regen_feedback", True)
    juicios = []

    async def juez(answer, context, lang="es"):
        juicios.append(answer)
        return True, "GROUNDED"

    monkeypatch.setattr(rag_agent, "is_grounded", juez)

    def preparar(respuestas, flag):
        monkeypatch.setattr(rag_agent.settings, "rag_precio_con_origen", flag)
        llamadas = []
        monkeypatch.setattr(rag_agent, "AsyncOpenAI", _openai(respuestas, llamadas))
        return llamadas, juicios

    return preparar


@pytest.mark.asyncio
async def test_con_el_flag_reescribe_rotulando(rag):
    llamadas, juicios = rag([SIN_ORIGEN, CON_ORIGEN], True)
    assert await rag_agent.rag_answer("¿y en pesos para colombianos?", lang="es") == CON_ORIGEN
    assert len(llamadas) == 2 and "NO quites el precio" in llamadas[1][-1]["content"]
    assert juicios == [CON_ORIGEN]


@pytest.mark.asyncio
async def test_si_el_segundo_tampoco_lo_dice_va_al_juez(rag):
    llamadas, juicios = rag([SIN_ORIGEN, SIN_ORIGEN], True)
    assert await rag_agent.rag_answer("¿y en pesos para colombianos?", lang="es") == SIN_ORIGEN
    assert juicios == [SIN_ORIGEN]  # no acaba en "no lo tengo" por esta comprobación


@pytest.mark.asyncio
async def test_sin_el_flag_no_cambia_nada(rag):
    llamadas, juicios = rag([SIN_ORIGEN], False)
    assert await rag_agent.rag_answer("¿y en pesos para colombianos?", lang="es") == SIN_ORIGEN
    assert len(llamadas) == 1
