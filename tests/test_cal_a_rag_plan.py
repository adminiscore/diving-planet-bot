"""CAL-A (16-oct): que el RAG conteste TODO lo que pregunta el cliente (diseño de Gadea, diagnóstico de los 73 fallos).

Se fija A1 `rag_temperatura_cero` (promocionado; su flag se borró en sim-5): la redacción va a temperatura 0. A2-A4 (el
plan del RAG y sus revisores de completitud y de avisos) se descartaron con banco y se borraron en sim-6, con
src/agents/rag_plan.py.
"""


import pytest

from src.agents import rag_agent


def _fake_openai(respuestas, llamadas):
    class _Msg:
        def __init__(self, c):
            self.content = c

    class _Resp:
        def __init__(self, c):
            self.choices = [type("C", (), {"message": _Msg(c)})()]
            self.usage = type("U", (), {"total_tokens": 10})()

    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            return _Resp(respuestas[len(llamadas) - 1])

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    return _OpenAI


@pytest.fixture
def rag(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{"content": "Minicurso: 120 USD. Almuerzo con opción vegetariana. Se reserva con un anticipo.",
                 "metadata": {"source": "faqs"}, "score": 0.9}]

    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent.settings, "rag_min_score", 0.5)
    llamadas = []
    veredictos = []

    def preparar(respuestas, juicios):
        veredictos.extend(juicios)
        monkeypatch.setattr(rag_agent, "AsyncOpenAI", _fake_openai(respuestas, llamadas))

        async def juez(answer, context, lang="es"):
            return veredictos.pop(0)

        monkeypatch.setattr(rag_agent, "is_grounded", juez)
        return llamadas

    return preparar


PREGUNTA = "¿cuánto cuesta el minicurso y el almuerzo tiene opción vegetariana?"
CORTA = "El minicurso cuesta 120 USD."
OK = (True, "GROUNDED")


@pytest.mark.asyncio
async def test_temperatura_cero(rag, monkeypatch):
    llamadas = rag([CORTA], [OK])
    await rag_agent.rag_answer(PREGUNTA, lang="es")
    assert llamadas[-1]["temperature"] == 0.0
