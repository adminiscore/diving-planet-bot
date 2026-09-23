"""l1-1 (Fase L1) — el juez de grounding opina una vez, detrás de flag.

Lo que fijan estos tests es el **número de llamadas al juez**, que es justo lo
que L1 quiere bajar, y que la conducta por defecto no cambia: el flag nace
apagado y el bot sigue haciendo exactamente lo de siempre.

Por qué importa el conteo y no solo el resultado: `_verify_grounding_with_retry`
preguntaba dos veces al MISMO juez por la MISMA respuesta y el MISMO contexto.
El bucle de `_answer_with_llm` ya da la segunda oportunidad de verdad
(regenera la respuesta), así que la segunda consulta solo explota el ruido del
juez sobre un texto idéntico.
"""

from __future__ import annotations

import pytest

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


@pytest.fixture
def flag(monkeypatch):
    def _set(valor: bool):
        monkeypatch.setattr(rag_agent.settings, "rag_single_grounding_judge", valor)

    return _set


async def test_respuesta_sostenida_una_sola_llamada_en_los_dos_modos(flag, monkeypatch):
    """Si el juez aprueba a la primera, nunca hubo segunda llamada: el flag no
    toca el camino bueno, que es el de la inmensa mayoría de los turnos."""
    for valor in (False, True):
        juez, llamadas = _judge(True)
        monkeypatch.setattr(rag_agent, "is_grounded", juez)
        flag(valor)

        grounded, reason = await rag_agent._verify_grounding_with_retry("r", "ctx", lang="es")

        assert grounded is True
        assert reason == "ok"
        assert len(llamadas) == 1, f"flag={valor}: el camino aprobado debe costar 1 llamada"


async def test_sin_flag_el_segundo_juez_puede_rescatar(flag, monkeypatch):
    """Conducta de SIEMPRE (flag apagado): el primer juez rechaza, se le vuelve a
    preguntar por el mismo texto y su segunda opinión salva la respuesta."""
    juez, llamadas = _judge(False, True)
    monkeypatch.setattr(rag_agent, "is_grounded", juez)
    flag(False)

    grounded, reason = await rag_agent._verify_grounding_with_retry("r", "ctx", lang="es")

    assert grounded is True
    assert len(llamadas) == 2
    assert llamadas[0] == llamadas[1], "el reintento juzga el MISMO texto, no uno nuevo"
    assert "retry:" in reason


async def test_con_flag_no_hay_segunda_opinion(flag, monkeypatch):
    """Con el flag: un rechazo es un rechazo. La segunda oportunidad la da el
    bucle de `_answer_with_llm` regenerando la respuesta, no este juez."""
    juez, llamadas = _judge(False, True)
    monkeypatch.setattr(rag_agent, "is_grounded", juez)
    flag(True)

    grounded, reason = await rag_agent._verify_grounding_with_retry("r", "ctx", lang="es")

    assert grounded is False
    assert len(llamadas) == 1, "con el flag el juez opina una sola vez"
    assert reason == "motivo_1"
    assert "retry:" not in reason, "sin reintento, el motivo no debe fingir que lo hubo"


async def test_rechazo_doble_gasta_dos_llamadas_sin_flag(flag, monkeypatch):
    """El peor caso de hoy: dos llamadas al juez para acabar rechazando igual."""
    juez, llamadas = _judge(False, False)
    monkeypatch.setattr(rag_agent, "is_grounded", juez)
    flag(False)

    grounded, reason = await rag_agent._verify_grounding_with_retry("r", "ctx", lang="es")

    assert grounded is False
    assert len(llamadas) == 2
    assert reason == "motivo_1|retry:motivo_2"


async def test_el_rescate_deja_rastro_en_el_log(flag, monkeypatch, caplog):
    """El rescate devolvía True en silencio: en los logs solo quedaba rastro
    cuando FALLABA. Sin este log no se puede saber cuántas veces valía la pena
    la segunda llamada, que es el dato que decide si el flag se promociona."""
    juez, _ = _judge(False, True)
    monkeypatch.setattr(rag_agent, "is_grounded", juez)
    flag(False)

    with caplog.at_level("INFO", logger="uvicorn.error"):
        await rag_agent._verify_grounding_with_retry("r", "ctx", lang="es")

    assert any("[RAG][GROUNDING][RESCUE]" in m for m in caplog.messages)


def test_el_flag_nace_apagado():
    """Regla del equipo: todo cambio de conducta va detrás de flag y el valor por
    defecto es la conducta actual, hasta que la foto A/B lo apruebe."""
    from src.config import Settings

    assert Settings().rag_single_grounding_judge is False
