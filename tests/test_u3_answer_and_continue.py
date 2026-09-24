"""u3-4: "contesta y sigue" (flag `answer_and_continue`).

Lo que se fija aquí:
1. el flag nace apagado y, apagado, Jev no recibe la pregunta nueva;
2. con "?" y un dato en el mismo mensaje: se contesta Y el dato se guarda (antes se
   perdía y se volvía a pedir);
   Los datos de un turno con pregunta los lee el LLM, no el regex (escalón 0: el regex
   lee palabras sueltas de la pregunta como si fueran datos);
3. sin "?" y sin que el regex la vea, con `asks_question` de Jev: se contesta Y la
   reserva sigue (antes la pregunta se perdía si la reserva avanzaba);
4. el "¿me recuerdas...?" sigue con su respuesta fija y la respuesta del RAG se cancela;
5. si el RAG falla, el turno sigue con la reserva;
6. el RAG recibe la foto del historial tomada al lanzarlo;
7. la duda de Jev en `asks_question` no manda el turno al router LLM, y su respuesta
   viaja también cuando Jev duda en las señales del router.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from src.agents import conversational_core as core
from src.agents import escalation, jev_router, supervisor
from src.agents.supervisor import route_message
from src.config import Settings, settings
from src.flows.state import ConversationState


def _state() -> ConversationState:
    s = ConversationState(conversation_id="u3-4")
    s.language = "es"
    return s


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))
    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(settings, "ack_in_parallel", False)


@pytest.fixture
def signals(monkeypatch):
    """Las señales del router que 've' este turno (por defecto ninguna)."""
    box = {"value": {}}

    async def _detect(message, **_k):
        return dict(box["value"])

    monkeypatch.setattr(supervisor, "detect_routing_signals", _detect)
    return box


@pytest.fixture
def rag(monkeypatch):
    calls = []

    async def _rag(message, **kwargs):
        calls.append({"message": message, "history": list(kwargs.get("history") or [])})
        return "RESPUESTA_RAG"

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    return calls


def test_el_flag_nace_apagado():
    assert Settings().answer_and_continue is False


def test_flag_apagado_jev_no_recibe_la_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", False)
    assert jev_router.ASKS_QUESTION not in jev_router._questions_for_turn()
    monkeypatch.setattr(settings, "answer_and_continue", True)
    assert jev_router.ASKS_QUESTION in jev_router._questions_for_turn()


async def test_flag_apagado_la_pregunta_con_dato_pierde_el_dato(monkeypatch, signals, rag):
    """La conducta de hoy, para que el contraste del test siguiente quede escrito."""
    monkeypatch.setattr(settings, "answer_and_continue", False)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena")
    assert st.core_pending_slot == core.SLOT_QTY
    resp = await route_message(st, "somos 3, ¿qué incluye el precio?")
    assert "RESPUESTA_RAG" in resp
    assert st.detected_group_size is None
    assert st.core_pending_slot == core.SLOT_QTY


def _llm_reads(monkeypatch, message, patch):
    """El extractor LLM devuelve `patch` solo para `message` (lo demás, nada)."""
    async def _fill(msg, *_a, **_k):
        return dict(patch) if msg == message else {}

    async def _combined(fields, veto_fields, msg, *_a, **_k):  # huecos + verificación, una petición
        return (dict(patch) if msg == message else {}), {}

    monkeypatch.setattr(core, "fill_gaps", _fill)
    monkeypatch.setattr(core, "extract_and_verify", _combined)


async def test_con_flag_contesta_y_guarda_el_dato(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    _llm_reads(monkeypatch, "somos 3, ¿qué incluye el precio?", {"group_size": 3})
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena")
    resp = await route_message(st, "somos 3, ¿qué incluye el precio?")
    assert resp.startswith("RESPUESTA_RAG")  # primero la respuesta
    assert st.detected_group_size == 3  # el dato no se pierde
    assert st.core_pending_slot == core.SLOT_SAFETY  # y la reserva sigue
    assert "2 años" in resp
    assert len(rag) == 1
    assert st.history[-1] == {"role": "assistant", "content": resp}


async def test_con_flag_y_jev_contesta_sin_interrogacion(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    assert st.core_pending_slot == core.SLOT_LOCATION
    signals["value"] = {"asks_question": True}
    resp = await route_message(st, "desde cartagena, y me cuentas lo de los hoteles")
    assert resp.startswith("RESPUESTA_RAG")
    assert st.location == "cartagena" or st.detected_location == "cartagena"
    assert st.core_pending_slot == core.SLOT_QTY


async def test_en_una_pregunta_el_regex_no_escribe_datos(monkeypatch, signals, rag):
    """"¿me recomiendas un hotel en Rosario?" no dice que se aloje allí: el regex leería
    location=island; el LLM (aquí, que se abstiene) es quien decide."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "do you have any hotel in Rosario you recommend?")
    assert resp.startswith("RESPUESTA_RAG")
    assert st.location is None and st.detected_location is None
    assert st.core_pending_slot == core.SLOT_LOCATION


async def test_sin_pregunta_no_se_lanza_nada(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "desde cartagena")
    assert rag == [] and "RESPUESTA_RAG" not in resp


async def test_recordar_sigue_con_su_respuesta_fija(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={"recall_field": "group_size"}))
    st = _state()
    await route_message(st, "quiero bucear, soy certificado, desde cartagena, somos 2")
    resp = await route_message(st, "¿cuántos te dije que éramos?")
    assert "RESPUESTA_RAG" not in resp
    assert "2" in resp
    assert getattr(st, "_pending_answer", None) is None


async def test_si_el_rag_falla_la_reserva_sigue(monkeypatch, signals):
    monkeypatch.setattr(settings, "answer_and_continue", True)

    async def _boom(message, **_k):
        raise RuntimeError("rag caído")

    monkeypatch.setattr(supervisor, "rag_answer", _boom)
    _llm_reads(monkeypatch, "somos 3, ¿qué incluye el precio?", {"group_size": 3})
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena")
    resp = await route_message(st, "somos 3, ¿qué incluye el precio?")
    assert st.detected_group_size == 3
    assert "2 años" in resp


async def test_el_rag_ve_la_foto_del_historial(monkeypatch, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    st.history.append({"role": "user", "content": "¿qué incluye?"})
    core._maybe_launch_answer(st, "¿qué incluye?", {})
    st.history.append({"role": "assistant", "content": "algo escrito después"})
    assert await core._take_parallel_answer(st) == "RESPUESTA_RAG"
    assert rag[0]["history"] == [{"role": "user", "content": "¿qué incluye?"}]


async def test_una_respuesta_sin_usar_se_cancela(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    started = asyncio.Event()

    async def _slow(message, **_k):
        started.set()
        await asyncio.sleep(10)
        return "tarde"

    monkeypatch.setattr(supervisor, "rag_answer", _slow)
    st = _state()
    core._maybe_launch_answer(st, "¿qué incluye?", {})
    task = st._pending_answer
    await started.wait()
    core.cancel_pending_answer(st)
    await asyncio.sleep(0)
    assert task.cancelled() and st._pending_answer is None


def test_saludo_no_es_pregunta():
    assert core._turn_has_question("hola, ¿qué tal?", {"asks_question": True}) is False
    assert core._turn_has_question("perfecto, como pago", {"asks_question": True}) is True
    assert core._turn_has_question("perfecto, como pago", {}) is False


def test_la_duda_en_asks_question_no_manda_al_router_llm():
    answers = {jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.5}, "wants_human": {"type": "noul", "noul": 0.0}}
    assert jev_router.uncertain_answers(answers) == []


def _mock_http(monkeypatch, answers):
    sent = {}

    def handler(request: httpx.Request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"answers": answers})

    monkeypatch.setattr(jev_router, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    return sent


async def test_jev_marca_la_pregunta_en_las_senales(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "jev_router_enabled", True)
    sent = _mock_http(monkeypatch, {jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.92}})
    got = await escalation.detect_routing_signals("perfecto, como pago")
    assert got == {"asks_question": True}
    assert jev_router.ASKS_QUESTION in sent["questions"]


async def test_por_debajo_de_07_no_es_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "jev_router_enabled", True)
    _mock_http(monkeypatch, {jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.65}})
    assert await escalation.detect_routing_signals("desde cartagena") == {}


async def test_si_jev_duda_en_el_router_la_pregunta_viaja_igual(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "jev_router_enabled", True)
    _mock_http(monkeypatch, {
        jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.9},
        "wants_human": {"type": "noul", "noul": 0.5},  # duda -> router LLM
    })

    class _NoTool:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_k):
                    raise RuntimeError("sin LLM en tests")

    monkeypatch.setattr(escalation, "AsyncOpenAI", lambda **_k: _NoTool())
    monkeypatch.setattr(escalation, "trace_openai", lambda c: c)
    got = await escalation.detect_routing_signals("perfecto, como pago")
    assert got == {"asks_question": True}
