"""l1-2 (Fase L1) — los checks deterministas corren ANTES del juez LLM.

**Ya se cumplía** cuando se revisó (2026-09-23): en `_answer_with_llm` los siete
guards deterministas van en una cadena `if/elif` y la llamada al juez está en el
`else` final, así que un rechazo determinista nunca llega a gastar la petición.
`is_grounded` solo se invoca desde `_verify_grounding`.

Pero se cumplía **por la disposición del código**, no por nada que lo fijara: mover
el juez arriba "para leerlo mejor", o meter un guard nuevo detrás, lo rompería sin
que fallara ni un test. Como el ahorro es justo el objetivo de L1, aquí queda
clavado: si el guard determinista rechaza, el juez NO se llama.
"""

from __future__ import annotations

import pytest

from src.agents import rag_agent


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Usage:
    total_tokens = 42


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = _Usage()


def _openai_devolviendo(respuesta: str):
    class _Completions:
        async def create(self, **kwargs):
            return _Resp(respuesta)

    class _Chat:
        completions = _Completions()

    class _Cliente:
        def __init__(self, api_key=None):
            self.chat = _Chat()

    return _Cliente


@pytest.fixture
def juez_contador(monkeypatch):
    """Sustituye al juez por uno que cuenta cuántas veces se le pregunta."""
    llamadas: list[tuple[str, str]] = []

    async def _is_grounded(answer, context, lang="es"):
        llamadas.append((answer, context))
        return True, "GROUNDED"

    monkeypatch.setattr(rag_agent, "is_grounded", _is_grounded)
    return llamadas


# Consulta deliberadamente NEUTRA: `rag_answer` tiene una cadena de atajos
# canónicos (comida, overview de buceo, coste del refresher, precios, ubicación
# ambigua) que responden SIN tocar el LLM. Una pregunta de precio nunca llega al
# juez, así que un test escrito con ella pasaría en falso — de hecho pasó, y lo
# cazó el test de control de abajo.
_CONSULTA_SIN_ATAJO = "¿puedo bucear si uso gafas graduadas?"


async def _responder(monkeypatch, respuesta: str, contexto: str) -> str:
    """Un turno de RAG con un único documento recuperado y el LLM amañado."""

    async def _busqueda(*args, **kwargs):
        return [{"content": contexto, "score": 0.99, "metadata": {"source": "faqs"}}]

    async def _sin_expandir(docs, lang="es"):
        return docs

    async def _sin_reescribir(query, history=None, lang="es"):
        return query

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _busqueda)
    monkeypatch.setattr(rag_agent, "_expand_with_parent_context", _sin_expandir)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _openai_devolviendo(respuesta))
    monkeypatch.setattr(rag_agent, "condense_query", _sin_reescribir)
    return await rag_agent.rag_answer(_CONSULTA_SIN_ATAJO, lang="es")


async def test_un_precio_inventado_no_llega_a_gastar_el_juez(monkeypatch, juez_contador):
    """El guard de importes rechaza un precio que no está en el contexto. Ese
    rechazo es gratis: el juez LLM no debe llegar a ejecutarse."""
    await _responder(
        monkeypatch,
        respuesta="El plan de 2 inmersiones cuesta 999 USD.",
        contexto="El plan de 2 inmersiones cuesta 178 USD.",
    )

    assert juez_contador == [], (
        "un rechazo determinista debe cortar antes del juez; si el juez se llama, "
        "L1 está pagando una petición por una respuesta que ya se iba a descartar"
    )


async def test_un_telefono_no_llega_a_gastar_el_juez(monkeypatch, juez_contador):
    """Mismo principio con otro guard (nunca dar un teléfono, decisión del owner)."""
    await _responder(
        monkeypatch,
        respuesta="Escríbenos al +57 300 123 4567 y te ayudamos.",
        contexto="El equipo te contacta por este mismo chat.",
    )

    assert juez_contador == []


async def test_una_respuesta_limpia_si_llega_al_juez(monkeypatch, juez_contador):
    """El control del test anterior: sin rechazo determinista, el juez SÍ opina.
    Sin esto, los dos tests de arriba pasarían aunque el juez no se llamara nunca."""
    respuesta = await _responder(
        monkeypatch,
        respuesta="El plan de 2 inmersiones cuesta 178 USD.",
        contexto="El plan de 2 inmersiones cuesta 178 USD.",
    )

    assert len(juez_contador) == 1
    assert "178" in respuesta


async def test_los_atajos_canonicos_no_gastan_ni_llm_ni_juez(monkeypatch, juez_contador):
    """Hallazgo al escribir esto (2026-09-23): `rag_answer` tiene una cadena de
    atajos canónicos (comida, overview, coste del refresher, precios, ubicación
    ambigua) que responden **sin una sola llamada al LLM**. Ya son un ahorro de
    L1 que no estaba anotado, así que queda fijado: si alguien los desmonta, el
    coste por turno sube sin que falle nada más."""

    def _explota(*args, **kwargs):  # el LLM no debe instanciarse siquiera
        raise AssertionError("un atajo canónico no puede llamar al LLM")

    async def _busqueda(*args, **kwargs):
        raise AssertionError("un atajo canónico no puede llegar a recuperar")

    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _explota)
    monkeypatch.setattr(rag_agent, "search_knowledge_base", _busqueda)

    respuesta = await rag_agent.rag_answer("¿cuánto cuesta el buceo?", lang="es")

    assert respuesta, "el atajo debe responder algo"
    assert juez_contador == []
