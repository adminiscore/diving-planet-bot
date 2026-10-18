"""r6-1 (17-oct): cada llamada al LLM sale en [TURN_METRICS] con su pieza, su inicio dentro del turno y su duración.

Gadea lo necesita para CAL-G (qué se puede lanzar en paralelo): la línea solo traía el total de llamadas y la suma
de segundos. Se fija:
1. `pieza_llm("…")` etiqueta las llamadas hechas dentro del bloque (también las del cliente HTTP cronometrado);
2. sin etiqueta, la llamada sale con su tipo ("chat"/"embedding") como pieza;
3. el inicio se mide desde el inicio del turno y las llamadas en paralelo se ven solapadas;
4. `scripts/turn_metrics.py` resume la ronda por pieza (n, p50, p95, modelos);
5. sigue sin texto del cliente ni de la respuesta.
"""

import asyncio
import json

import httpx

import src.observability as obs
from scripts import turn_metrics


class _S:
    langfuse_public_key = ""
    langfuse_secret_key = ""


def _linea(caplog) -> dict:
    lineas = [m for m in caplog.messages if m.startswith(obs.TURN_METRICS_TAG)]
    assert len(lineas) == 1
    return json.loads(lineas[0][len(obs.TURN_METRICS_TAG):])


async def test_cada_llamada_con_su_pieza_inicio_y_duracion(caplog):
    async def lento(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(lento),
                               event_hooks={"request": [obs._on_request], "response": [obs._on_response]})

    async def llamar(pieza: str | None, model: str):
        if pieza:
            with obs.pieza_llm(pieza):
                await client.post("https://api.openai.com/v1/chat/completions", json={"model": model})
        else:
            await client.post("https://api.openai.com/v1/chat/completions", json={"model": model})

    with caplog.at_level("INFO", logger="uvicorn.error"):
        async with obs.turn_trace(_S(), "9", "mi DNI es 123") as turn:
            await asyncio.gather(llamar("extractor", "gpt-4.1-mini"), llamar("rag_escritor", "gpt-6-luna"))
            await llamar(None, "gpt-4o-mini")
            turn.update(reply="texto de la respuesta")
    payload = _linea(caplog)
    llamadas = payload["llamadas"]
    assert [c["p"] for c in llamadas[:2]] == ["extractor", "rag_escritor"] or \
        [c["p"] for c in llamadas[:2]] == ["rag_escritor", "extractor"]
    assert llamadas[2]["p"] == "chat" and llamadas[2]["m"] == "gpt-4o-mini"
    assert all(c["t"] is not None and c["t"] >= 0 and c["s"] >= 0.04 for c in llamadas)
    # las dos primeras van en paralelo: empiezan casi a la vez; la tercera empieza cuando acaban
    primera, segunda, tercera = sorted(llamadas, key=lambda c: c["t"])
    assert segunda["t"] - primera["t"] < 0.04
    assert tercera["t"] >= primera["t"] + 0.04
    linea = json.dumps(payload)
    assert "DNI" not in linea and "texto de la respuesta" not in linea


def test_la_foto_resume_por_pieza():
    linea = obs.TURN_METRICS_TAG + " " + json.dumps({
        "conv": "1", "start": "2026-10-17T19:00:00Z", "latency": 3.0, "turn_type": "rag", "llm_calls": 3,
        "llamadas": [{"p": "extractor", "m": "gpt-4.1-mini", "t": 0.1, "s": 1.5},
                     {"p": "rag_escritor", "m": "gpt-6-luna", "t": 0.2, "s": 2.0},
                     {"p": "extractor", "m": "gpt-4.1-mini", "t": 2.5, "s": 0.5}]})
    turnos = turn_metrics.parse_lines([linea])
    foto = turn_metrics.build(turnos, "prueba", "a", "b")
    assert foto["por_pieza"]["extractor"]["n"] == 2
    assert foto["por_pieza"]["extractor"]["modelos"] == {"gpt-4.1-mini": 2}
    assert foto["por_pieza"]["rag_escritor"]["n"] == 1


async def test_la_etiqueta_no_se_escapa_del_bloque():
    async with obs.turn_trace(_S(), "2", "hola") as turn:
        with obs.pieza_llm("extractor"):
            obs.record_llm_call("chat", 0.1, "m")
        obs.record_llm_call("chat", 0.1, "m")
        piezas = [c["pieza"] for c in turn["_llm"]]
    assert piezas == ["extractor", None]


async def test_el_decorador_etiqueta_todas_las_llamadas_de_la_funcion():
    @obs.con_pieza_llm("senales_router")
    async def funcion():
        obs.record_llm_call("chat", 0.1, "m")
        await asyncio.sleep(0)
        obs.record_llm_call("chat", 0.1, "m")
        return "hecho"

    async with obs.turn_trace(_S(), "3", "hola") as turn:
        assert await funcion() == "hecho"
        obs.record_llm_call("chat", 0.1, "m")
        piezas = [c["pieza"] for c in turn["_llm"]]
    assert piezas == ["senales_router", "senales_router", None]
    assert funcion.__name__ == "funcion"


async def test_el_respaldo_del_rag_etiqueta_escritor_y_respaldo(monkeypatch):
    from src.agents import rag_agent
    from src.config import settings

    vistas = []

    class _Completions:
        async def create(self, *, model, **kw):
            vistas.append((model, obs._LLM_PIEZA.get()))
            await asyncio.sleep(0.2 if model == "lento" else 0.0)
            return model

    cliente = type("C", (), {"chat": type("Ch", (), {"completions": _Completions()})()})()
    monkeypatch.setattr(settings, "rag_answer_model", "lento")
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "rapido")
    monkeypatch.setattr(settings, "rag_respaldo_segundos", 0.05)
    assert await rag_agent.generar_con_respaldo(cliente, [{"role": "user", "content": "hola"}]) == "rapido"
    assert sorted(vistas) == [("lento", "rag_escritor"), ("rapido", "rag_respaldo")]


# --- r6-1(b) `aviso_si_openai_falla`: si ninguna llamada a OpenAI funciona, se dice y se pasa a un asesor ---

async def test_fallo_de_openai_solo_si_ninguna_llamada_funciono():
    async with obs.turn_trace(_S(), "4", "hola"):
        assert obs.fallo_de_openai_en_el_turno() is None  # sin llamadas
        obs.record_llm_call("chat", 0.1, "gpt-6-luna", status=429)
        assert obs.fallo_de_openai_en_el_turno() == 429
        obs.record_llm_call("chat", 0.1, "gpt-6-luna", status=200)  # el reintento del SDK funcionó
        assert obs.fallo_de_openai_en_el_turno() is None


async def test_con_openai_caido_el_bot_lo_dice_y_pasa_a_un_asesor(monkeypatch):
    from src.agents import supervisor
    from src.config import settings
    from src.flows.state import ConversationState, Step

    async def turno_degradado(state, message, routing_signals=None):
        obs.record_llm_call("chat", 0.1, "gpt-4.1-mini", status=429)
        obs.record_llm_call("chat", 0.1, "gpt-6-luna", status=429)
        return "Ese detalle en concreto no lo tengo a la mano."

    monkeypatch.setattr(settings, "agent_arch", False)
    monkeypatch.setattr(supervisor, "_shared_turn_handler", turno_degradado)
    for flag in (False, True):
        monkeypatch.setattr(settings, "aviso_si_openai_falla", flag)
        st = ConversationState(conversation_id="r61b", language="es")
        respuesta = await supervisor.route_message(st, "¿dónde es el punto de encuentro?")
        if not flag:
            assert respuesta == "Ese detalle en concreto no lo tengo a la mano."
            assert st.pending_escalation_reason is None
        else:
            assert "problema técnico" in respuesta
            assert st.step == Step.ESCALATE
            assert "FALLO TÉCNICO" in st.pending_escalation_reason and "429" in st.pending_escalation_reason


async def test_respaldo_mismo_modelo_lanza_otra_peticion_a_luna(monkeypatch):
    from src.agents import rag_agent
    from src.config import settings

    vistas = []

    class _Completions:
        async def create(self, *, model, **kw):
            pieza = obs._LLM_PIEZA.get()
            vistas.append((model, pieza))
            await asyncio.sleep(0.2 if pieza == "rag_escritor" else 0.0)  # la primera petición se queda en la cola
            return pieza

    cliente = type("C", (), {"chat": type("Ch", (), {"completions": _Completions()})()})()
    monkeypatch.setattr(settings, "rag_answer_model", "gpt-6-luna")
    monkeypatch.setattr(settings, "rag_respaldo_modelo", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "rag_respaldo_segundos", 0.05)
    monkeypatch.setattr(settings, "respaldo_mismo_modelo", True)
    assert await rag_agent.generar_con_respaldo(cliente, [{"role": "user", "content": "hola"}]) == "rag_respaldo"
    assert sorted(vistas) == [("gpt-6-luna", "rag_escritor"), ("gpt-6-luna", "rag_respaldo")]
    # sin el flag, el respaldo es gpt-4.1-mini, como hoy
    vistas.clear()
    monkeypatch.setattr(settings, "respaldo_mismo_modelo", False)
    await rag_agent.generar_con_respaldo(cliente, [{"role": "user", "content": "hola"}])
    assert ("gpt-4.1-mini", "rag_respaldo") in vistas


def test_el_aviso_conserva_el_motivo_del_pase_que_ya_habia():
    from src.agents import supervisor
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="r61-motivo")
    st.language = "es"
    st.pending_escalation_reason = "LINK ROTO: el enlace de reserva no abre"
    supervisor._respuesta_fallo_tecnico(st, 429)
    assert st.pending_escalation_reason.startswith("LINK ROTO") and "FALLO TÉCNICO" in st.pending_escalation_reason
