"""G3-07a, la parte del RAG (18-oct, decisión de Gadea: en un mismo mensaje, UNA sola moneda).

"somos una pareja de Bogotá… ¿cuánto vale el snorkel?" salía con "126 USD" en el texto y "448.000 COP" en la tarjeta del plan del mismo mensaje: el RAG se escribe
antes de que el flujo aplique la extracción del turno. Cuando el turno lleva la tarjeta, el flujo pide
`rag_answer(sin_precio=True)` (flag `rag_sin_precio_con_tarjeta`) y el texto no da precio ni enlace."""
import pytest

from src.prompts.info import RAG_SIN_PRECIO_EN, RAG_SIN_PRECIO_ES


class _Completions:
    def __init__(self):
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        msg = type("M", (), {"content": "El snorkel incluye lancha, equipo y almuerzo."})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()],
                              "usage": type("U", (), {"total_tokens": 10})()})()


class _Client:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _Completions()})()

    def __call__(self, *args, **kwargs):
        return self


async def _sistema(monkeypatch, sin_precio: bool, lang: str = "es") -> str:
    from src.agents import rag_agent

    client = _Client()
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", client)

    async def _sin_docs(*args, **kwargs):
        return []

    async def _juez(answer, context, lang="es"):
        return True, "ok"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _sin_docs)
    monkeypatch.setattr(rag_agent, "_verify_grounding", _juez)

    async def _sin_aviso_al_final(*_a, **_k):  # CAL-A6, siempre encendido desde sim-5: aquí no cuenta
        return None

    from src.agents import rag_plan

    monkeypatch.setattr(rag_plan, "aviso_al_final", _sin_aviso_al_final)
    await rag_agent.rag_answer("¿cuánto vale el snorkel?" if lang == "es" else "how much is snorkeling?", lang=lang,
                               extra_context="Idioma: es.", sin_precio=sin_precio)
    return client.chat.completions.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_sin_precio_pide_al_rag_que_no_de_precios(monkeypatch):
    assert RAG_SIN_PRECIO_ES in await _sistema(monkeypatch, sin_precio=True)
    assert RAG_SIN_PRECIO_EN in await _sistema(monkeypatch, sin_precio=True, lang="en")


@pytest.mark.asyncio
async def test_por_defecto_el_rag_sigue_igual(monkeypatch):
    sistema = await _sistema(monkeypatch, sin_precio=False)
    assert RAG_SIN_PRECIO_ES not in sistema and RAG_SIN_PRECIO_EN not in sistema
