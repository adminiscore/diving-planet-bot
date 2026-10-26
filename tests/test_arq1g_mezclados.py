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


@pytest.fixture
def rag(monkeypatch):
    """El RAG con una búsqueda y un LLM de mentira: devuelve las llamadas que se hicieron. (Vivía en los tests de
    CAL-A5, que se fueron con los avisos dentro del RAG el 26-oct.)"""
    from src.agents import rag_agent
    from src.config import settings

    llamadas: list[dict] = []

    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            msg = type("M", (), {"content": "El minicurso es una experiencia guiada con instructor."})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()],
                                  "usage": type("U", (), {"total_tokens": 10, "prompt_tokens_details": None})()})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    async def fake_search(query, lang="es", **kw):
        return [{"content": "El minicurso es una experiencia guiada y no otorga certificación.",
                 "metadata": {"source": "policies", "key": "minicourse_scope", "topics": ["certification"]},
                 "score": 0.9}]

    async def fake_expand(docs, lang):
        return docs

    async def fake_condense(query, history=None, lang="es", hechos=None):
        return query

    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _OpenAI)
    monkeypatch.setattr(rag_agent, "search_knowledge_base", fake_search)
    monkeypatch.setattr(rag_agent, "_expand_with_parent_context", fake_expand)
    monkeypatch.setattr(rag_agent, "condense_query", fake_condense)
    monkeypatch.setattr(settings, "rag_plan_primero", False)
    monkeypatch.setattr(settings, "rag_revisor_completitud", False)
    monkeypatch.setattr(settings, "rag_revisor_avisos", False)
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "")
    return rag_agent, llamadas


@pytest.mark.asyncio
async def test_los_hechos_van_en_el_mensaje_y_los_ve_el_revisor(rag, monkeypatch):
    rag_agent, llamadas = rag
    vistos: list[str] = []

    async def fake_verify(answer, context, lang="es"):
        vistos.append(context)
        return True, ""

    monkeypatch.setattr(rag_agent, "_verify_grounding", fake_verify)
    hechos = '[{"actividad": "minicourse", "precio": {"cartagena": {"online": "183 USD"}}}]'
    await rag_agent.rag_answer("¿cuánto cuesta el minicurso y qué peces se ven?", lang="es", hechos=hechos)
    primera = next(m["content"] for m in reversed(llamadas[0]["messages"]) if m["role"] == "user")
    assert "Hechos del sistema" in primera and "183 USD" in primera
    assert primera.index("183 USD") < primera.index("Pregunta del cliente")
    assert vistos and "183 USD" in vistos[0]
