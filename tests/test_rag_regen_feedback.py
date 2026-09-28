"""28-sep, flag `rag_regen_feedback`: la segunda muestra del RAG sabe QUÉ se rechazó en la primera.

Reproducido en PRE: con la misma petición repetida, el modelo repetía el invento ("llevamos 30 años" 2 de 2) y el
turno acababa en "no lo tengo". Se fija:
1. el motivo del juez v3 y de los guards se convierte en una lista legible (sin el "NO" final);
2. con el flag, la segunda llamada lleva la respuesta rechazada y el motivo; sin él, la misma petición que antes;
3. el juez sigue juzgando la segunda muestra (si también la rechaza, "no lo tengo" como antes);
4. sin motivo que contar (texto roto), se regenera como antes.
"""

import pytest

from src.agents import rag_agent
from src.agents.rag_agent import FALLBACK_ES, regen_feedback


def test_motivo_del_juez_a_lista():
    fb = regen_feedback("HALLUCINATED - Diving Planet tiene 30 años de experiencia. NO | - Cada inmersión dura 40 minutos NO", "es")
    assert "- Diving Planet tiene 30 años de experiencia\n- Cada inmersión dura 40 minutos\n" in fb
    assert "NO se envió" in fb and " NO\n" not in fb


def test_motivo_de_un_guard_y_sin_motivo():
    assert "un link que no aparece" in regen_feedback("ungrounded_url", "es")
    assert "a phone number" in regen_feedback("phone_number", "en")
    assert regen_feedback("garbled_output", "es") is None
    assert regen_feedback("HALLUCINATED", "es") is None


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
            llamadas.append(kwargs["messages"])
            return _Resp(respuestas[len(llamadas) - 1])

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    return _OpenAI


@pytest.fixture
def rag(monkeypatch):
    async def fake_search(query, lang="es"):
        return [{"content": "Punto de encuentro: Muelle de la Bodeguita a las 8:00 a.m.",
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


INVENTO = "Nos vemos en el Muelle de la Bodeguita a las 8:00 a.m. Llevamos 30 años buceando."
BIEN = "Nos vemos en el Muelle de la Bodeguita a las 8:00 a.m."
RECHAZO = (False, "HALLUCINATED - Llevamos 30 años buceando. NO")


@pytest.mark.asyncio
async def test_con_el_flag_la_segunda_muestra_sabe_que_quitar(rag, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_regen_feedback", True)
    llamadas = rag([INVENTO, BIEN], [RECHAZO, (True, "GROUNDED")])
    assert await rag_agent.rag_answer("¿dónde nos vemos?", lang="es") == BIEN
    assert len(llamadas) == 2
    segunda = llamadas[1]
    assert segunda[:-2] == llamadas[0]
    assert segunda[-2] == {"role": "assistant", "content": INVENTO}
    assert "- Llevamos 30 años buceando\n" in segunda[-1]["content"]


@pytest.mark.asyncio
async def test_sin_el_flag_se_repite_la_misma_peticion(rag, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_regen_feedback", False)
    llamadas = rag([INVENTO, BIEN], [RECHAZO, (True, "GROUNDED")])
    assert await rag_agent.rag_answer("¿dónde nos vemos?", lang="es") == BIEN
    assert llamadas[1] == llamadas[0]


@pytest.mark.asyncio
async def test_el_juez_sigue_juzgando_la_segunda(rag, monkeypatch):
    monkeypatch.setattr(rag_agent.settings, "rag_regen_feedback", True)
    rag([INVENTO, INVENTO], [RECHAZO, RECHAZO])
    assert await rag_agent.rag_answer("¿dónde nos vemos?", lang="es") == FALLBACK_ES
