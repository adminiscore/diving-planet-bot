"""Medición propia sin Langfuse (2026-09-24): una línea `[TURN_METRICS]` por turno.

Se superó el plan gratuito de Langfuse; las cifras de latencia y llamadas salen ahora
del log del bot. Lo que se fija aquí:
1. cada turno escribe su línea, con llamadas al LLM y tiempo por nodo, SIN texto del
   cliente ni de la respuesta;
2. el cliente HTTP de OpenAI cronometra las llamadas de chat y embeddings;
3. el cronómetro de nodos sigue el criterio de la foto de Langfuse;
4. `scripts/turn_metrics.py` convierte las líneas en la misma foto que `langfuse_snapshot`.
"""

import json
import uuid

import httpx

import src.observability as obs
from scripts import turn_metrics


class _S:  # ajustes sin claves de Langfuse: solo la medición propia
    langfuse_public_key = ""
    langfuse_secret_key = ""


async def test_cada_turno_escribe_su_linea_sin_texto(caplog):
    with caplog.at_level("INFO", logger="uvicorn.error"):
        async with obs.turn_trace(_S(), "1234", "tengo una lesion en la rodilla, mi DNI es 123") as turn:
            obs.note_turn(route="booking", rag_used=True, language="es")
            obs.record_llm_call("chat", 0.8, "gpt-4o-mini")
            obs.record_llm_call("chat", 0.4, "gpt-4.1-mini")
            obs.record_llm_call("embedding", 0.1, "text-embedding-3-small")
            turn.update(reply="Respuesta con datos del cliente")
    lines = [m for m in caplog.messages if m.startswith(obs.TURN_METRICS_TAG)]
    assert len(lines) == 1
    payload = json.loads(lines[0][len(obs.TURN_METRICS_TAG):])
    assert payload["conv"] == "1234"
    assert payload["turn_type"] == "rag"
    assert payload["llm_calls"] == 2 and payload["embeddings"] == 1
    assert payload["llm_seconds"] == 1.2
    assert payload["models"] == {"gpt-4o-mini": 1, "gpt-4.1-mini": 1}
    assert payload["latency"] >= 0
    assert "rodilla" not in lines[0] and "DNI" not in lines[0] and "Respuesta" not in lines[0]


async def test_el_cliente_http_cronometra_las_llamadas_al_llm():
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [obs._on_request], "response": [obs._on_response]},
    )
    async with obs.turn_trace(_S(), "1", "hola") as turn:
        await client.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o-mini"})
        await client.post("https://api.openai.com/v1/embeddings", json={"model": "text-embedding-3-small"})
        await client.get("https://api.openai.com/v1/models")  # no es una llamada al LLM
        calls = list(turn.get("_llm") or [])
    assert [c["kind"] for c in calls] == ["chat", "embedding"]
    assert calls[0]["model"] == "gpt-4o-mini"


def test_cronometro_de_nodos_con_el_criterio_de_langfuse():
    facts: dict = {}
    timer = obs.node_timer(facts)
    for name in ("router", "_route_decision", "LangGraph", "booking"):
        rid = uuid.uuid4()
        timer.on_chain_start({}, {}, run_id=rid, name=name)
        timer.on_chain_end({}, run_id=rid)
    assert set(facts["_nodes"]) == {"router", "booking"}


def test_el_script_hace_la_misma_foto_que_langfuse():
    def line(conv, turn_type, latency, calls, nodes, router=None):
        m = {"conv": conv, "start": "2026-09-24T10:00:00Z", "latency": latency, "turn_type": turn_type,
             "route": "booking", "llm_calls": calls, "embeddings": 0, "llm_seconds": 0.5,
             "models": {"gpt-4o-mini": calls}, "nodes": nodes, "router": router, "router_ms": 300 if router else None}
        return f"INFO:     {obs.TURN_METRICS_TAG} {json.dumps(m)}"

    lines = [
        "INFO:     otra linea cualquiera",
        line("1", "reserva", 2.0, 3, {"router": 0.3, "booking": 1.5}, "jev"),
        line("1", "rag", 6.0, 5, {"router": 0.3, "booking": 5.0}, "jev"),
        line("2", "reserva", 3.0, 3, {"router": 1.3, "booking": 1.6}),
    ]
    snap = turn_metrics.build(turn_metrics.parse_lines(lines), "prueba", "a", "b")
    assert snap["all"]["turns"] == 3
    assert snap["all"]["latency_p50"] == 3.0
    assert snap["by_type"]["rag"]["turns"] == 1
    assert snap["nodes"]["booking"]["n"] == 3
    assert snap["router"]["by_backend"] == {"jev": 2, "llm": 1}
    assert snap["business"]["conversations"] == 2
