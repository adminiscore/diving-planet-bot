"""LAT-10 (27-oct): la duración de una llamada incluye el cuerpo de la respuesta. El gancho de httpx salta con las
cabeceras, y OpenRouter las manda antes de que el modelo acabe de escribir: el extractor salía con 0,86 s de mediana y
los ~0,6 s de su JSON quedaban como un hueco sin llamadas (integra6b-B; el hueco crecía con sus tokens de salida, a
~2,75 ms por token). Sin red."""
import asyncio
import json

import httpx

import src.observability as obs


class _S:
    langfuse_public_key = ""
    langfuse_secret_key = ""


class _CuerpoLento(httpx.AsyncByteStream):
    """Cabeceras ya; el cuerpo, cuando el «modelo» acaba de escribir."""

    async def __aiter__(self):
        await asyncio.sleep(0.15)
        yield json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 200}}).encode()


async def test_la_duracion_cuenta_hasta_el_final_del_cuerpo(caplog):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=_CuerpoLento())),
                               event_hooks={"request": [obs._on_request], "response": [obs._on_response]})
    with caplog.at_level("INFO", logger="uvicorn.error"):
        async with obs.turn_trace(_S(), "lat10", "hola") as turn:
            with obs.pieza_llm("extractor"):
                await client.post("https://openrouter.ai/api/v1/chat/completions", json={"model": "anthropic/x"})
            turn.update(reply="ok")
    linea = next(m for m in caplog.messages if m.startswith(obs.TURN_METRICS_TAG))
    llamada = json.loads(linea[len(obs.TURN_METRICS_TAG):])["llamadas"][0]
    assert llamada["s"] >= 0.14  # con el cuerpo; antes salía ~0
    assert llamada["u"]["out"] == 200
