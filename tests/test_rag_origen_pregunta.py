"""Flag `rag_origen_pregunta` (punto 3: el ORIGEN del cliente en los precios).

6-oct: un aviso en el contexto del RAG, medido y quitado (o repreguntaba o volvía a suponer Cartagena).
7-oct, opción C (decisión de Álvaro): lo hace el CÓDIGO. Se fija:
1. cuándo se pregunta el origen en vez de cotizar: la respuesta del RAG lleva un importe, el cliente pide un precio
   (o repregunta tras la pregunta del origen sin contestarla: "¿y en pesos?"), el origen no consta y el cliente no ha
   nombrado Cartagena ni las islas; no si el precio es del hotel, ni si la respuesta no cotiza (la MONEDA: ronda
   origen-c-B, 7-oct), ni con el flag apagado;
2. en la reserva: la pregunta del origen ocupa el turno (en lugar de la cotización, con sus botones) y se guarda la
   del precio;
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
COTIZA = "El minicurso cuesta 655.000 COP (o 178 USD)."


def _estado(location=None, historial=None, pendiente=None) -> ConversationState:
    s = ConversationState(conversation_id="origen", language="es")
    s.pregunta_precio_pendiente = pendiente
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
    assert bool(core._origen_antes_del_precio(_estado(location, historial), mensaje, COTIZA)) is pregunta


@pytest.mark.parametrize("mensaje,respuesta,pendiente,pregunta", [
    # ronda origen-c-B (7-oct): dice "precio" pero pregunta la MONEDA; la respuesta no cotiza -> va tal cual
    ("Amigo el precio que está allí es en dólares o pesos colombianos",
     "Los precios en dólares son para internacionales y en pesos (COP) para colombianos.", None, False),
    # ronda origen-c-B: repregunta sin palabras de precio tras la pregunta del origen -> el RAG cotizaba Cartagena
    ("Gracias - y en pesos? Para colombianos?", "El paquete de 5 inmersiones cuesta 1.429.000 COP.",
     "¿Cuál es el costo para colombianos?", True),
    ("Gracias - y en pesos? Para colombianos?", "El paquete de 5 inmersiones cuesta 1.429.000 COP.", None, False),
    ("¿qué incluye el minicurso?", COTIZA, None, False),  # un importe en la respuesta a otra cosa: como hoy
    ("how much is it?", "It costs USD 178 per person.", None, True),
])
def test_la_puerta_mira_si_la_respuesta_cotiza(monkeypatch, mensaje, respuesta, pendiente, pregunta):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    estado = _estado(pendiente=pendiente)
    assert bool(core._origen_antes_del_precio(estado, mensaje, respuesta)) is pregunta


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
        return f"RESPUESTA_RAG: {COTIZA}"

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    return preguntas


async def test_pide_precio_sin_origen_se_pregunta_y_luego_se_contesta(monkeypatch, conversacion):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    st = ConversationState(conversation_id="origen-c", language="es")
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "¿cuánto cuesta?")
    assert core.ORIGEN_ANTES_DEL_PRECIO_ES in resp and "RESPUESTA_RAG" not in resp  # la cotización no sale
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


async def test_y_en_pesos_tras_la_pregunta_del_origen_tampoco_cotiza(monkeypatch, conversacion):
    """Ronda origen-c-B (7-oct): "Gracias - y en pesos?" no lleva palabras de precio y el RAG cotizaba Cartagena."""
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    st = ConversationState(conversation_id="origen-pesos", language="es")
    await route_message(st, "queremos bucear, somos certificados")
    await route_message(st, "¿cuánto cuesta?")
    resp = await route_message(st, "Gracias - y en pesos?")
    assert conversacion[-1]["message"] == "Gracias - y en pesos?"  # el RAG contestó (y cotizaba)...
    assert "RESPUESTA_RAG" not in resp and core.ORIGEN_ANTES_DEL_PRECIO_ES in resp  # ...y se pregunta el origen
    assert st.pregunta_precio_pendiente  # sigue pendiente: se contesta cuando diga el origen


# s4-31 (8-oct, flag `origen_conserva_respuesta`): la puerta del origen ya no tira la respuesta entera. Ronda
# 2026-10-08-luna-visible: 6 de 33 fallos del RAG eran de perder lo que no era el precio.
MITO = ("¡Qué bueno que quieras hacer el curso! Para colombianos no hay un precio especial: el precio es el mismo para "
        "todos, solo cambia la moneda (pagas en pesos). El curso cuesta 2.450.000 COP online saliendo desde Cartagena. "
        "¿Quieres que te pase el link?")


def test_conserva_lo_que_no_es_precio_y_pregunta_el_origen(monkeypatch):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    monkeypatch.setattr(settings, "origen_conserva_respuesta", True)
    salida = core._origen_antes_del_precio(_estado(), "Cuál es el costo para colombianos?", MITO)
    assert "no hay un precio especial" in salida and "solo cambia la moneda" in salida  # lo que no es precio, queda
    assert "COP" not in salida and "2.450.000" not in salida                            # ningún importe
    assert "link" not in salida                                                         # su pregunta final, fuera
    assert salida.endswith(core.ORIGEN_ANTES_DEL_PRECIO_ES) and core._es_pregunta_de_origen(salida)


@pytest.mark.parametrize("respuesta", ["Cuesta 655.000 COP. ¿Te lo reservo?", "El minicurso: 183 USD online."])
def test_si_solo_habia_precio_queda_solo_la_pregunta(monkeypatch, respuesta):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    monkeypatch.setattr(settings, "origen_conserva_respuesta", True)
    assert core._origen_antes_del_precio(_estado(), "¿cuánto cuesta?", respuesta) == core.ORIGEN_ANTES_DEL_PRECIO_ES


def test_con_el_flag_apagado_la_pregunta_sustituye_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    monkeypatch.setattr(settings, "origen_conserva_respuesta", False)
    assert core._origen_antes_del_precio(_estado(), "Cuál es el costo para colombianos?", MITO) == \
        core.ORIGEN_ANTES_DEL_PRECIO_ES


def test_tambien_quita_el_link_y_lo_que_incluye(monkeypatch):
    """Escalón 0 en PRE (8-oct): se dejaba el link de Cartagena mientras se preguntaba el origen, y "Incluye lancha y
    almuerzo" (solo es de Cartagena) se quedaba sin sujeto."""
    monkeypatch.setattr(settings, "rag_origen_pregunta", True)
    monkeypatch.setattr(settings, "origen_conserva_respuesta", True)
    respuesta = ("¡Claro que sí! Incluye teoría online y 4 inmersiones.\nSon 2 días y hay que dormir una noche en las "
                 "islas; el alojamiento no está incluido. Reserva aquí: https://book.divingplanet.org/book/basic-course/4")
    salida = core._origen_antes_del_precio(_estado(), "¿cuánto cuesta el curso?", respuesta.replace("4 inmersiones.",
                                                                                                "4 inmersiones. 693 USD."))
    assert "book.divingplanet.org" not in salida and "Incluye" not in salida
    assert "el alojamiento no está incluido" in salida  # lo que vale para los dos orígenes, queda
