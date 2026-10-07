"""Flag `rag_origen_pregunta` (punto 3: el ORIGEN del cliente en los precios).

6-oct: un aviso en el contexto del RAG, medido y quitado (o repreguntaba o volvía a suponer Cartagena).
7-oct, opción C (decisión de Álvaro): lo hace el CÓDIGO. Se fija:
1. cuándo se pregunta el origen antes de cotizar: pide un precio, el origen no consta y el cliente no ha nombrado
   Cartagena ni las islas; no si el precio es del hotel, ni con el flag apagado;
2. en la reserva: la pregunta del origen ocupa el turno (sin el RAG, con sus botones) y se guarda la del precio;
3. cuando el cliente dice el origen, se contesta la pregunta del precio que quedó pendiente;
4. si una respuesta del RAG ya pregunta el origen, la reserva no repite la suya.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step

PREGUNTA_RAG = "El precio depende de desde dónde salgan. ¿Saldrían desde Cartagena o ya están en las islas?"


def _estado(location=None, historial=None) -> ConversationState:
    s = ConversationState(conversation_id="origen", language="es")
    s.step = Step.FREE_TEXT
    s.location = location
    s.history = historial or []
    return s


@pytest.mark.parametrize("flag,location,historial,mensaje,pregunta", [
    (True, None, [], "¿cuánto cuesta el minicurso?", True),
    (True, None, [], "Cuál es el costo para colombianos?", True),
    (True, None, [], "how much is the 5 dive package?", True),
    (False, None, [], "¿cuánto cuesta el minicurso?", False),                   # flag apagado
    (True, "cartagena", [], "¿cuánto cuesta el minicurso?", False),             # el origen consta
    (True, None, [], "¿qué incluye el minicurso?", False),                      # no pide precio
    (True, None, [], "¿me pasas el precio por noche del hotel?", False),        # precio ajeno
    (True, None, [], "salimos desde Cartagena, ¿cuánto cuesta?", False),        # lo dice en el mensaje
    (True, None, [{"role": "user", "content": "we will book our hotel on the island"}],
     "how much is the refresher?", False),                                       # lo dio a entender antes
    (True, None, [{"role": "assistant", "content": "saliendo desde Cartagena o desde las propias islas"}],
     "¿cuánto cuesta?", True),                                                   # lo que dice el BOT no cuenta
])
def test_cuando_se_pregunta_el_origen_antes_de_cotizar(monkeypatch, flag, location, historial, mensaje, pregunta):
    monkeypatch.setattr(settings, "rag_origen_pregunta", flag)
    assert bool(core._origen_antes_del_precio(_estado(location, historial), mensaje)) is pregunta


@pytest.mark.parametrize("flag,slot,respuesta,va_sola", [
    (True, core.SLOT_LOCATION, PREGUNTA_RAG, True),
    (True, core.SLOT_LOCATION, "Where would you be departing from: Cartagena or the islands?", True),
    (True, core.SLOT_LOCATION, "¿Desde dónde prefieren salir ustedes? Así te paso el link correcto.", True),
    (True, core.SLOT_LOCATION, "¿me confirmas si saldrían desde Cartagena o si ya están en las islas?", True),
    (False, core.SLOT_LOCATION, PREGUNTA_RAG, False),
    (True, core.SLOT_QTY, PREGUNTA_RAG, False),
    (True, core.SLOT_LOCATION, "El minicurso cuesta 655.000 COP desde Cartagena.", False),
])
def test_la_respuesta_que_ya_pregunta_el_origen_va_sola(monkeypatch, flag, slot, respuesta, va_sola):
    monkeypatch.setattr(settings, "rag_origen_pregunta", flag)
    state = _estado()
    state.core_pending_slot = slot
    assert core._answer_asks_the_origin(state, respuesta) is va_sola


@pytest.fixture
def conversacion(monkeypatch):
    """La reserva entera, sin red: señales vacías, extractores apagados y un RAG falso que apunta sus preguntas."""
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))
    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(settings, "ack_in_parallel", False)
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "rag_adelantado", False)

    async def _senales(message, **_k):
        return {}

    monkeypatch.setattr(supervisor, "detect_routing_signals", _senales)
    preguntas = []

    async def _rag(message, **kwargs):
        preguntas.append({"message": message, "extra_context": kwargs.get("extra_context") or ""})
        return "RESPUESTA_RAG"

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    return preguntas


async def test_pide_precio_sin_origen_se_pregunta_y_luego_se_contesta(monkeypatch, conversacion):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    st = ConversationState(conversation_id="origen-c", language="es")
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "¿cuánto cuesta?")
    assert core.ORIGEN_ANTES_DEL_PRECIO_ES in resp and "RESPUESTA_RAG" not in resp
    assert conversacion == []  # el RAG no cotiza sin origen
    assert st.core_pending_slot == core.SLOT_LOCATION and st.quick_replies  # con sus botones
    assert st.pregunta_precio_pendiente == "¿cuánto cuesta?"
    assert resp.count("¿") == 1  # una sola pregunta, sin la de la reserva detrás

    resp = await route_message(st, "desde cartagena")
    assert resp.startswith("RESPUESTA_RAG")  # se contesta la pregunta del precio que quedó pendiente
    assert conversacion[-1]["message"] == "¿cuánto cuesta?"
    assert st.pregunta_precio_pendiente is None
    assert st.location == "cartagena" or st.detected_location == "cartagena"


async def test_con_el_flag_apagado_el_rag_cotiza_como_siempre(monkeypatch, conversacion):
    monkeypatch.setattr(settings, "rag_origen_pregunta", False)
    st = ConversationState(conversation_id="origen-off", language="es")
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "¿cuánto cuesta?")
    assert resp.startswith("RESPUESTA_RAG")
    assert core.ORIGEN_ANTES_DEL_PRECIO_ES not in resp
