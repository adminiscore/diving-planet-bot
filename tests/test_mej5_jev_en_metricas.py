"""mej-5 (21-oct): Jev sale en [TURN_METRICS] con sus tokens y su coste, y también cuando falla.

Jev va por su propio cliente HTTP (no el medido de OpenAI) y no aparecía: el 21-oct, con la clave de OpenRouter en su
límite, Jev daba 403 en todos los turnos y las métricas no lo enseñaban.
"""

import json

import httpx
import pytest

import src.observability as obs
from src.agents import jev_router
from src.config import settings


class _S:
    langfuse_public_key = ""
    langfuse_secret_key = ""


def _llamadas(caplog) -> list[dict]:
    lineas = [m for m in caplog.messages if m.startswith(obs.TURN_METRICS_TAG)]
    assert len(lineas) == 1
    return json.loads(lineas[0][len(obs.TURN_METRICS_TAG):])["llamadas"]


@pytest.fixture
def jev(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-falsa")

    def con(respuesta):
        cliente = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: respuesta))
        monkeypatch.setattr(jev_router, "_http", lambda: cliente)
    return con


async def test_jev_sale_con_sus_tokens_y_su_coste(jev, caplog):
    jev(httpx.Response(200, json={"answers": {}, "usage": {"input_tokens": 6183, "output_tokens": 788,
                                                           "cost": 0.00026}}))
    with caplog.at_level("INFO", logger="uvicorn.error"):
        async with obs.turn_trace(_S(), "1", "hola"):
            await jev_router.detect_routing_signals_jev_full("hola, somos 2")
    (llamada,) = [c for c in _llamadas(caplog) if c["p"] == "jev"]
    assert llamada["m"] == settings.jev_model
    assert llamada["u"] == {"in": 6183, "out": 788, "usd": 0.00026}
    assert "e" not in llamada


async def test_jev_que_falla_sale_como_error(jev, caplog):
    """El 403 «Key limit exceeded» del 21-oct."""
    jev(httpx.Response(403, json={"error": {"message": "Key limit exceeded (total limit)"}}))
    with caplog.at_level("INFO", logger="uvicorn.error"):
        async with obs.turn_trace(_S(), "2", "hola"):
            resultado, _ = await jev_router.detect_routing_signals_jev_full("hola, somos 2")
    assert resultado is None  # el turno cae al router LLM, como siempre
    (llamada,) = [c for c in _llamadas(caplog) if c["p"] == "jev"]
    assert llamada["e"] == 403 and "u" not in llamada
