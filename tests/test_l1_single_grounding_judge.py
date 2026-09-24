"""l1-1 (Fase L1) — el juez de grounding opina una sola vez.

Lo que fijan estos tests es el **número de llamadas al juez**, que es justo lo que
L1 bajó. Antes se volvía a preguntar al MISMO juez por la MISMA respuesta cuando
rechazaba; en el A/B del 23-sep esa segunda consulta solo salvó 1 de 24 rechazos
(4 %) y se quitó del código en el cierre de L1 (2026-09-24). La segunda oportunidad
real la da el bucle de `_answer_with_llm`, que regenera la respuesta.
"""

from __future__ import annotations

from src.agents import rag_agent


def _judge(*veredictos: bool):
    """Juez de mentira que responde la secuencia dada y cuenta sus llamadas."""
    llamadas: list[str] = []

    async def _is_grounded(answer: str, context: str, lang: str = "es"):
        i = len(llamadas)
        llamadas.append(answer)
        ok = veredictos[i] if i < len(veredictos) else veredictos[-1]
        return ok, "ok" if ok else f"motivo_{i + 1}"

    return _is_grounded, llamadas


async def test_respuesta_sostenida_una_sola_llamada(monkeypatch):
    juez, llamadas = _judge(True)
    monkeypatch.setattr(rag_agent, "is_grounded", juez)

    grounded, reason = await rag_agent._verify_grounding("r", "ctx", lang="es")

    assert (grounded, reason) == (True, "ok")
    assert len(llamadas) == 1


async def test_un_rechazo_es_un_rechazo_sin_segunda_opinion(monkeypatch):
    """Aunque una segunda consulta hubiera aprobado, no se hace."""
    juez, llamadas = _judge(False, True)
    monkeypatch.setattr(rag_agent, "is_grounded", juez)

    grounded, reason = await rag_agent._verify_grounding("r", "ctx", lang="es")

    assert grounded is False
    assert len(llamadas) == 1, "el juez opina una sola vez"
    assert reason == "motivo_1"


def test_el_flag_del_juez_unico_ya_no_existe():
    """El juez único es la única conducta del código: el flag se retiró al cerrar L1."""
    from src.config import Settings

    assert not hasattr(Settings(), "rag_single_grounding_judge")
