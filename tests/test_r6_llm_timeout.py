"""r6-1 (Fase R6): toda llamada al LLM tiene un tiempo máximo.

Por qué existe esto: el cliente de OpenAI trae por defecto `read=600 s` con 2
reintentos, o sea hasta ~30 min colgado en UNA llamada. Medido en vivo el 23-sep:
`eval_rag_answers` se quedó 5 h 44 min con 40 s de CPU, parado en el 4º de 39 casos.
En producción eso es un turno que nunca responde.

Se fija aquí el CONTRATO, no la implementación:
1. un cliente real sale con el timeout de `settings`;
2. el valor es configurable (no una constante escondida);
3. los mocks de los tests pasan intactos — si esto se rompe, se caen decenas de
   tests de otros ficheros que parchean `AsyncOpenAI` en su módulo;
4. un timeout degrada el turno, no lo tumba.
"""

import httpx
import pytest
from openai import APITimeoutError, AsyncOpenAI

from src.agents.intent_detector import DetectedIntent
from src.agents.llm_extractor import fill_gaps
from src.config import settings
from src.llm_client import trace_openai


def test_cliente_real_sale_con_el_timeout_configurado():
    client = trace_openai(AsyncOpenAI(api_key="sk-test"))
    assert client.timeout == settings.llm_timeout_seconds


def test_el_timeout_es_configurable_no_una_constante(monkeypatch):
    monkeypatch.setattr(settings, "llm_timeout_seconds", 7.0)
    client = trace_openai(AsyncOpenAI(api_key="sk-test"))
    assert client.timeout == 7.0


def test_un_mock_pasa_intacto():
    """Los tests del repo parchean `AsyncOpenAI` en su módulo y luego afirman sobre
    ESE objeto. Si `trace_openai` devolviera una copia (`with_options`), mirarían a
    otro mock y fallarían en cadena. Por eso el timeout solo se aplica a clientes
    reales."""
    from unittest.mock import MagicMock

    fake = MagicMock()
    assert trace_openai(fake) is fake


@pytest.mark.asyncio
async def test_un_timeout_degrada_el_turno_pero_no_lo_tumba(caplog):
    """Un timeout NO debe propagarse y matar el turno: la extracción devuelve vacío
    (el bot sigue con lo que tenga) y queda registrado para poder verlo."""

    class _ClienteQueExpira:
        # Los nombres imitan la forma del SDK de OpenAI a propósito.
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(*args, **kwargs):
                    raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1"))

    with caplog.at_level("WARNING"):
        patch = await fill_gaps("quiero bucear", DetectedIntent(), client=_ClienteQueExpira())

    assert patch == {}, "un timeout debe degradar a vacío, no propagar"
    assert any("DEGRADED" in r.message or "DEGRADED" in r.getMessage() for r in caplog.records), (
        "un timeout que no deja rastro en el log es una degradación invisible"
    )
